"""Central Person Registry service: smart search, register-or-link, profile updates, guardians.

Framework-agnostic.  Every function takes an open psycopg2 connection and an `Actor`; none of
them commits — the caller owns the transaction (the HTTP adapter commits on success and rolls
back on any error).  Authorisation is the database's (`authz_*`, `person_field_policy`, the
`persons_guard` trigger); this module adds friendly errors on top and NEVER weakens them.
"""
import re
from datetime import date
from typing import Dict, List, Optional

import psycopg2
import psycopg2.errors as pgerr
import psycopg2.extras

from . import matching
from .errors import (FieldLocked, IdentifierInUse, NeedsConfirmation, NotFound, PermissionDenied,
                     ValidationError)
from ..db import Actor, bind_actor, cursor

NAME_PARTS = ('first_name', 'second_name', 'third_name', 'fourth_name')
PROFILE_FIELDS = NAME_PARTS + ('date_of_birth', 'place_of_birth', 'national_id', 'passport_id',
                               'mother_name', 'phone', 'residence', 'occupation', 'photo_path')
CANDIDATE_LIMIT = 200
PERSON_REF_RE = re.compile(r'^\s*P-\d{4}-\d{1,9}\s*$', re.I)       # as issued by next_ref('P'): P-2026-000123

_PERSON_SELECT = """
    SELECT p.id, p.person_ref, p.first_name, p.second_name, p.third_name, p.fourth_name, p.full_name,
           p.date_of_birth, p.place_of_birth, p.national_id, p.passport_id, p.mother_name, p.phone,
           p.residence, p.occupation, p.photo_path, p.name_tokens, p.mother_norm,
           norm_ident(p.national_id) AS nid_norm, norm_ident(p.passport_id) AS pid_norm,
           p.created_at, p.updated_at, u.code AS created_unit_code, u.name AS created_unit_name
      FROM persons p LEFT JOIN org_units u ON u.id = p.created_in_unit_id"""


# =============================================================================
# input handling
# =============================================================================
def _clean(data: Dict, key: str) -> str:
    v = data.get(key)
    return ' '.join(str(v).split()) if v not in (None, '') else ''


def _parse_dob(value, required=False) -> Optional[date]:
    if value in (None, ''):
        if required:
            raise ValidationError('Date of birth is required', fields=['date_of_birth'])
        return None
    if isinstance(value, date):
        d = value
    else:
        try:
            d = date.fromisoformat(str(value).strip())
        except ValueError:
            raise ValidationError('Date of birth must be YYYY-MM-DD', fields=['date_of_birth'])
    if d > date.today():
        raise ValidationError('Date of birth cannot be in the future', fields=['date_of_birth'])
    if d.year < 1900:
        raise ValidationError('Date of birth is not plausible', fields=['date_of_birth'])
    return d


def _age(dob: Optional[date]) -> Optional[int]:
    if not dob:
        return None
    t = date.today()
    return t.year - dob.year - ((t.month, t.day) < (dob.month, dob.day))


def _build_query(cur, data: Dict) -> (matching.Query, Dict):
    """Normalise the raw input with the DATABASE's functions (single source of truth)."""
    raw = {k: _clean(data, k) for k in PROFILE_FIELDS if k != 'date_of_birth'}
    dob = _parse_dob(data.get('date_of_birth'))
    raw['date_of_birth'] = dob.isoformat() if dob else ''
    cur.execute("SELECT norm_text(%s) AS name, norm_ident(%s) AS nid, norm_ident(%s) AS pid, norm_text(%s) AS mother",
                (' '.join(raw[k] for k in NAME_PARTS if raw[k]), raw['national_id'], raw['passport_id'],
                 raw['mother_name']))
    r = cur.fetchone()
    q = matching.Query(tokens=r['name'].split(' ') if r['name'] else [], dob=dob,
                       national_id=r['nid'], passport_id=r['pid'], mother=r['mother'])
    return q, raw


def parse_free_text(text: str) -> Dict:
    """Map the single search box onto structured fields: Person ID | ID/passport | name."""
    t = ' '.join((text or '').split())
    if not t:
        return {}
    if PERSON_REF_RE.match(t):
        return {'person_ref': t.upper()}
    if ' ' not in t and re.search(r'\d', t):
        return {'national_id': t, 'passport_id': t}
    parts = t.split(' ')
    if len(parts) > 4:
        parts = parts[:3] + [' '.join(parts[3:])]
    return dict(zip(NAME_PARTS, parts))


# =============================================================================
# reads
# =============================================================================
def _require(cur, actor: Actor, perm: str, message: str):
    cur.execute('SELECT authz_has(%s, %s) AS ok', (actor.user_id, perm))
    if not cur.fetchone()['ok']:
        raise PermissionDenied(message, permission=perm)


def _get_by_ref(cur, ref: str, lock=False) -> Optional[Dict]:
    cur.execute(_PERSON_SELECT + ' WHERE p.person_ref = %s' + (' FOR UPDATE OF p' if lock else ''), (ref,))
    return cur.fetchone()


def _candidates(cur, q: matching.Query, ref: Optional[str]) -> List[Dict]:
    if ref:
        row = _get_by_ref(cur, ref)
        return [row] if row else []
    clauses, params = [], {'lim': CANDIDATE_LIMIT}

    def id_clause(col, key, value):
        # a 1-character prefix would scan the table: require an exact value until 2+ chars are typed
        op = "LIKE %(" + key + ")s || '%%'" if len(value) >= matching.ID_PREFIX_MIN else '= %(' + key + ')s'
        clauses.append(f'norm_ident(p.{col}) {op}')
        params[key] = value

    for key, value in (('nid', q.national_id), ('pid', q.passport_id)):
        if value:                                   # an ID typed in either box may sit in either column
            id_clause('national_id', key, value)
            id_clause('passport_id', key, value)
    if q.tokens:
        clauses.append('p.name_keys && %(keys)s::text[]')
        params['keys'] = sorted({t[:3] for t in q.tokens})
    if not clauses:
        return []
    order = ("ORDER BY (SELECT count(*) FROM unnest(p.name_keys) k WHERE k = ANY(%(keys)s::text[])) DESC, p.id"
             if q.tokens else 'ORDER BY p.id')
    cur.execute(_PERSON_SELECT + ' WHERE ' + ' OR '.join(clauses) + ' ' + order + ' LIMIT %(lim)s', params)
    return cur.fetchall()


def _field_states(cur, actor: Actor, person_id: int) -> Dict[str, Dict]:
    cur.execute('SELECT * FROM person_field_states(%s, %s)', (actor.user_id, person_id))
    return {r['field']: {'state': r['state'], 'mutability': r['mutability'], 'label': r['label']}
            for r in cur.fetchall()}


def _guardians(cur, person_id: int) -> List[Dict]:
    cur.execute("""SELECT g.person_ref AS guardian_ref, g.full_name, pg.relationship, g.phone, g.residence,
                          g.occupation, pg.created_at
                     FROM person_guardians pg JOIN persons g ON g.id = pg.guardian_person_id
                    WHERE pg.person_id = %s ORDER BY pg.id""", (person_id,))
    return cur.fetchall()


def _missing(row: Dict, guardians: List[Dict]) -> List[Dict]:
    labels = [('date_of_birth', 'Date of birth'), ('place_of_birth', 'Place of birth'),
              ('mother_name', "Mother's name"), ('residence', 'Address'), ('phone', 'Phone'),
              ('occupation', 'Occupation'), ('photo_path', 'Photo')]
    out = [{'field': f, 'label': l} for f, l in labels if row.get(f) in (None, '')]
    if not row.get('national_id') and not row.get('passport_id'):
        out.append({'field': 'national_id', 'label': 'National ID or Passport'})
    age = _age(row.get('date_of_birth'))
    if age is not None and age < 18 and not guardians:
        out.append({'field': 'guardian', 'label': 'Guardian'})
    return out


def person_view(cur, actor: Actor, row: Dict, with_states=True) -> Dict:
    guardians = _guardians(cur, row['id'])
    view = {k: row.get(k) for k in ('person_ref', 'first_name', 'second_name', 'third_name', 'fourth_name',
                                    'full_name', 'date_of_birth', 'place_of_birth', 'national_id',
                                    'passport_id', 'mother_name', 'phone', 'residence', 'occupation',
                                    'photo_path', 'created_at', 'updated_at')}
    view['age'] = _age(row.get('date_of_birth'))
    view['registered_at'] = ({'code': row['created_unit_code'], 'name': row['created_unit_name']}
                             if row.get('created_unit_code') else None)
    view['guardians'] = guardians
    view['missing_fields'] = _missing(row, guardians)
    if with_states:
        view['field_states'] = _field_states(cur, actor, row['id'])
    return view


def _alert_flag(cur, actor: Actor, person_id: int) -> Optional[bool]:
    """Yes/no only (never the case).  None when the actor is not allowed to check alerts."""
    cur.execute("SELECT authz_has(%s,'alert:check') AS ok", (actor.user_id,))
    if not cur.fetchone()['ok']:
        return None
    cur.execute('SELECT person_alert_flag(%s, %s) AS f', (actor.user_id, person_id))
    return cur.fetchone()['f']


def search(conn, actor: Actor, query: Optional[Dict] = None, q: Optional[str] = None, limit: int = 8) -> Dict:
    """Smart search.  Accepts structured fields, or one free-text box (`q`).

    Returns a decision: status = exists | confirm | suggestions | new  (see matching.py) plus
    the master profile, ranked candidates, per-field lock states for THIS actor, conflicts,
    differences between what was typed and the locked stored values, and the alert yes/no.
    """
    cur = cursor(conn)
    bind_actor(cur, actor)
    _require(cur, actor, 'person:search', 'You are not allowed to search the Central Person Registry')
    data = dict(query or {})
    if q:
        data = {**parse_free_text(q), **data}
    ref = _clean(data, 'person_ref') or None
    nq, raw = _build_query(cur, data)
    if not nq.has_anything and not ref:
        return {'status': 'new', 'exists': False, 'tier': 0, 'tier_label': matching.TIER_LABELS[0],
                'reason': 'Enter a name, National ID or Passport.', 'person': None, 'candidates': [],
                'conflicts': [], 'core_differences': [], 'has_active_alert': None, 'auto_select': False}

    rows = _candidates(cur, nq, ref)
    by_id = {r['id']: r for r in rows}
    if ref:        # direct Person-ID lookup: a certain match
        if not rows:
            decision = matching.Decision('new', 0, None, [], 'No record with that Person ID.')
        else:
            ev = matching.Evaluation(person_id=rows[0]['id'], tier=1, id_exact=True, score=100,
                                     reasons=['Exact Person ID match'])
            decision = matching.Decision('exists', 1, ev, [ev], 'Exact Person ID match')
    else:
        decision = matching.decide(nq, rows)

    candidates = []
    for ev in decision.ranked[:max(1, limit)]:
        row = by_id[ev.person_id]
        v = person_view(cur, actor, row)
        v.update({'tier': ev.tier, 'score': ev.score, 'reasons': ev.reasons, 'dob_match': ev.dob_match,
                  'mother_match': ev.mother_match})
        candidates.append(v)

    primary = None
    if decision.primary and decision.status in ('exists', 'confirm'):
        primary = next((c for c in candidates if c['person_ref'] == by_id[decision.primary.person_id]['person_ref']), None)
    diffs = []
    if primary:
        diffs = matching.core_differences(
            raw, primary, [f for f in NAME_PARTS + ('date_of_birth', 'place_of_birth', 'national_id', 'passport_id')])
    conflicts = [{**c, 'person_refs': [by_id[i]['person_ref'] for i in c['person_ids'] if i in by_id]}
                 for c in decision.conflicts]
    for c in conflicts:
        c.pop('person_ids', None)
    return {
        'status': decision.status,
        'exists': decision.exists,
        'auto_select': decision.exists,              # UI: fill the form + show the "already exists" banner
        'tier': decision.tier,
        'tier_label': matching.TIER_LABELS.get(decision.tier, ''),
        'reason': decision.reason,
        'person': primary,
        'candidates': candidates,
        'conflicts': conflicts,
        'core_differences': diffs,
        'has_active_alert': _alert_flag(cur, actor, decision.primary.person_id) if primary else None,
    }


def get_person(conn, actor: Actor, person_ref: str) -> Dict:
    cur = cursor(conn)
    bind_actor(cur, actor)
    _require(cur, actor, 'person:search', 'You are not allowed to view the Central Person Registry')
    row = _get_by_ref(cur, person_ref)
    if not row:
        raise NotFound('Person not found')
    view = person_view(cur, actor, row)
    view['has_active_alert'] = _alert_flag(cur, actor, row['id'])
    return view


# =============================================================================
# writes
# =============================================================================
def _same(field: str, entered: str, stored) -> bool:
    if field == 'date_of_birth':
        return stored is not None and entered == stored.isoformat()
    if field in ('national_id', 'passport_id'):
        return ' '.join(str(stored or '').split()).upper() == entered.upper()
    return ' '.join(str(stored or '').split()) == entered


def _normalise_value(field: str, value) -> str:
    if field == 'date_of_birth':
        d = _parse_dob(value)
        return d.isoformat() if d else ''
    v = ' '.join(str(value).split()) if value not in (None, '') else ''
    return v.upper() if field in ('national_id', 'passport_id') else v


def _apply(cur, row: Dict, sets: Dict[str, str]):
    if not sets:
        return
    cols = ', '.join(f'{k} = %({k})s' for k in sets)
    try:
        cur.execute('SAVEPOINT apply_changes')
        cur.execute(f'UPDATE persons SET {cols} WHERE id = %(_id)s', {**sets, '_id': row['id']})
        cur.execute('RELEASE SAVEPOINT apply_changes')
    except pgerr.InsufficientPrivilege as e:
        cur.execute('ROLLBACK TO SAVEPOINT apply_changes')
        field = e.diag.column_name or ''
        raise FieldLocked(e.diag.message_primary or 'Field is locked',
                          fields=[{'field': field, 'reason': e.diag.message_primary}])
    except pgerr.CheckViolation as e:
        cur.execute('ROLLBACK TO SAVEPOINT apply_changes')
        raise ValidationError(e.diag.message_primary, fields=[e.diag.column_name or ''])
    except pgerr.UniqueViolation:
        cur.execute('ROLLBACK TO SAVEPOINT apply_changes')
        raise IdentifierInUse('That National ID / Passport already belongs to another person record.')


def _audit(cur, actor: Actor, action: str, ref: str, details: Optional[Dict] = None):
    cur.execute("INSERT INTO audit_events (user_id, unit_id, action, entity, entity_id, details) "
                "VALUES (%s, %s, %s, 'person', %s, %s::jsonb)",
                (actor.user_id, actor.unit_id, action, ref, psycopg2.extras.Json(details or {})))


def _enrich_existing(cur, actor: Actor, row: Dict, data: Dict) -> Dict:
    """Intake on a person who already exists: fill blanks, refresh DYNAMIC fields, and REPORT
    (never apply) anything that disagrees with a locked value."""
    states = _field_states(cur, actor, row['id'])
    sets, filled, updated, ignored = {}, [], [], []
    for f in PROFILE_FIELDS:
        entered = _normalise_value(f, data.get(f))
        if not entered or _same(f, entered, row.get(f)):
            continue
        st = states[f]
        stored_blank = row.get(f) in (None, '')
        if stored_blank and st['state'] in ('fillable', 'editable'):
            sets[f] = entered
            filled.append(f)
        elif not stored_blank and st['mutability'] == 'dynamic' and st['state'] == 'editable':
            sets[f] = entered
            updated.append(f)
        else:
            ignored.append({'field': f, 'label': st['label'], 'stored': row.get(f), 'entered': entered,
                            'reason': 'locked' if not stored_blank else 'not permitted'})
    if sets:
        _apply(cur, row, sets)
    return {'filled': filled, 'updated': updated, 'ignored': ignored}


def _validate_new(data: Dict, require_dob: bool, allow_no_id: bool):
    problems = []
    for f, label in (('first_name', 'First name'), ('second_name', 'Second name'), ('third_name', 'Third name')):
        if not _clean(data, f):
            problems.append({'field': f, 'message': f'{label} is required'})
    if not require_dob:
        _parse_dob(data.get('date_of_birth'))          # still validate if present
    else:
        try:
            _parse_dob(data.get('date_of_birth'), required=True)
        except ValidationError as e:
            problems.append({'field': 'date_of_birth', 'message': e.message})
    if not allow_no_id and not _clean(data, 'national_id') and not _clean(data, 'passport_id'):
        problems.append({'field': 'national_id', 'message': 'National ID or Passport ID is required'})
    if problems:
        raise ValidationError(problems[0]['message'], fields=problems)


def register(conn, actor: Actor, data: Dict, *, confirm_new: bool = False,
             link_person_ref: Optional[str] = None, allow_no_id: bool = False,
             require_dob: bool = True, confirm_on_suggestions: bool = False) -> Dict:
    """Register-or-link at intake.

    * existing person (Tier 1/2, or `link_person_ref`)  -> NO duplicate is created; blanks are
      filled, dynamic fields refreshed, locked disagreements reported in `ignored`.
    * possible duplicate (Tier 3)                       -> NeedsConfirmation unless `confirm_new`.
    * otherwise                                         -> a new master record is created.
    """
    cur = cursor(conn)
    bind_actor(cur, actor)
    _require(cur, actor, 'person:search', 'You are not allowed to search the Central Person Registry')

    nq, raw = _build_query(cur, data)
    if link_person_ref:
        row = _get_by_ref(cur, link_person_ref, lock=True)
        if not row:
            raise NotFound('Person to link was not found')
        result = _link(cur, actor, row, data, 'PERSON_LINK_SELECTED', reason='Linked to the selected existing record')
        return result

    _validate_new(data, require_dob, allow_no_id)
    # serialise concurrent intakes of the same person (two units registering at the same time)
    cur.execute("SELECT pg_advisory_xact_lock(hashtextextended(%s, 0))",
                ('|'.join([nq.national_id or '', nq.passport_id or '', ' '.join(nq.tokens),
                           raw['date_of_birth']]),))

    for attempt in (1, 2):
        rows = _candidates(cur, nq, None)
        decision = matching.decide(nq, rows)
        if decision.exists:
            row = _get_by_ref(cur, next(r for r in rows if r['id'] == decision.primary.person_id)['person_ref'], lock=True)
            return _link(cur, actor, row, data, 'PERSON_LINK_EXISTING', decision=decision,
                         reason=decision.reason)
        _require(cur, actor, 'person:create', 'You are not allowed to register new people')   # before any prompt
        needs_confirm = decision.status == 'confirm' or (confirm_on_suggestions and decision.status == 'suggestions')
        if needs_confirm and not confirm_new:
            res = search(conn, actor, query=data)
            raise NeedsConfirmation(
                'A similar person already exists. Link to the existing record, or confirm that this is a different person.',
                search=res)
        try:
            cur.execute('SAVEPOINT new_person')
            cur.execute("SELECT next_ref('P') AS ref")
            ref = cur.fetchone()['ref']
            cols = ['person_ref'] + [f for f in PROFILE_FIELDS if _normalise_value(f, data.get(f))]
            vals = {'person_ref': ref, **{f: _normalise_value(f, data.get(f)) for f in cols if f != 'person_ref'}}
            cur.execute(
                f"INSERT INTO persons ({', '.join(cols)}, full_name, created_in_unit_id) "
                f"VALUES ({', '.join('%(' + c + ')s' for c in cols)}, '', %(_unit)s) RETURNING person_ref",
                {**vals, '_unit': actor.unit_id})
            cur.execute('RELEASE SAVEPOINT new_person')
            break
        except pgerr.InsufficientPrivilege as e:
            cur.execute('ROLLBACK TO SAVEPOINT new_person')
            raise PermissionDenied(e.diag.message_primary)
        except pgerr.UniqueViolation:
            cur.execute('ROLLBACK TO SAVEPOINT new_person')
            if attempt == 2:
                raise IdentifierInUse('That National ID / Passport already belongs to another person record.')
            # lost a race on an identifier: loop once more, which now resolves to the existing record
    row = _get_by_ref(cur, ref)
    _audit(cur, actor, 'PERSON_CREATE' if not (needs_confirm and confirm_new) else 'PERSON_DUPLICATE_OVERRIDE', ref,
           {'tier': decision.tier, 'status': decision.status, 'reason': decision.reason})
    return {'created': True, 'exists': False, 'person': person_view(cur, actor, row),
            'match': {'status': decision.status, 'tier': decision.tier, 'reason': decision.reason},
            'filled': [], 'updated': [], 'ignored': []}


def _link(cur, actor: Actor, row: Dict, data: Dict, audit_action: str, decision=None, reason='') -> Dict:
    changes = {'filled': [], 'updated': [], 'ignored': []}
    cur.execute("SELECT authz_has(%s,'person:create') AS ok", (actor.user_id,))
    if cur.fetchone()['ok']:
        changes = _enrich_existing(cur, actor, row, data)
    row = _get_by_ref(cur, row['person_ref'])
    _audit(cur, actor, audit_action, row['person_ref'],
           {'filled': changes['filled'], 'updated': changes['updated'],
            'ignored': [i['field'] for i in changes['ignored']]})
    return {'created': False, 'exists': True, 'person': person_view(cur, actor, row),
            'match': {'status': 'exists', 'tier': decision.tier if decision else 1,
                      'reason': reason or (decision.reason if decision else '')},
            **changes}


def update_profile(conn, actor: Actor, person_ref: str, changes: Dict, reason: Optional[str] = None) -> Dict:
    """Strict, explicit profile edit.  Atomic: if ANY field is locked for this actor nothing is
    written and FieldLocked lists every offending field.  Unchanged values are ignored, so a UI
    may safely post the whole form.  Changing a core/identifier value needs the National Admin
    role and a reason."""
    cur = cursor(conn)
    bind_actor(cur, actor, reason)
    row = _get_by_ref(cur, person_ref, lock=True)
    if not row:
        raise NotFound('Person not found')
    _require(cur, actor, 'person:search', 'You are not allowed to view the Central Person Registry')
    states = _field_states(cur, actor, row['id'])
    cur.execute('SELECT field, needs_reason FROM person_field_policy')
    needs_reason = {r['field']: r['needs_reason'] for r in cur.fetchall()}

    unknown = [k for k in changes if k not in PROFILE_FIELDS]
    if unknown:
        raise ValidationError('These fields cannot be edited through this endpoint: ' + ', '.join(sorted(unknown)),
                              fields=[{'field': k, 'message': 'not editable'} for k in unknown])
    sets, locked, kinds = {}, [], {}
    for f, v in changes.items():
        entered = _normalise_value(f, v)
        if _same(f, entered, row.get(f)) or (entered == '' and row.get(f) in (None, '')):
            continue
        st = states[f]
        stored_blank = row.get(f) in (None, '')
        allowed = st['state'] in ('fillable', 'editable') if stored_blank else st['state'] == 'editable'
        if not allowed:
            locked.append({'field': f, 'label': st['label'], 'mutability': st['mutability'],
                           'reason': (f"{st['label']} is locked after registration. "
                                      + ('Only the National Admin can correct it.' if st['mutability'] in ('core', 'identifier')
                                         else 'Your role cannot change it.'))})
            continue
        sets[f] = entered or None
        kinds[f] = 'fill' if stored_blank else 'change'
    if locked:
        raise FieldLocked('Locked identity fields cannot be changed: ' + ', '.join(l['label'] for l in locked),
                          fields=locked)
    reasoned = [f for f, k in kinds.items() if k == 'change' and needs_reason.get(f)]
    if reasoned and not (reason or '').strip():
        raise ValidationError('A reason is required to correct ' + ', '.join(states[f]['label'] for f in reasoned),
                              fields=[{'field': f, 'message': 'reason required'} for f in reasoned])
    _apply(cur, row, sets)
    if reasoned:
        _audit(cur, actor, 'PERSON_CORE_CHANGE', person_ref, {'fields': reasoned, 'reason': reason})
    row = _get_by_ref(cur, person_ref)
    return {'person': person_view(cur, actor, row),
            'filled': [f for f, k in kinds.items() if k == 'fill'],
            'updated': [f for f, k in kinds.items() if k == 'change']}


def add_guardian(conn, actor: Actor, person_ref: str, guardian: Dict, relationship: Optional[str] = None,
                 guardian_person_ref: Optional[str] = None, confirm_new: bool = False) -> Dict:
    """Attach a guardian to a person — typically on a LATER visit at a different unit.

    The guardian is itself a person record (resolved/created with the same matching rules),
    the link is append-only, and the guardian's own blank fields are enriched."""
    cur = cursor(conn)
    bind_actor(cur, actor)
    _require(cur, actor, 'person:create', 'You are not allowed to add guardian details')
    person = _get_by_ref(cur, person_ref, lock=True)
    if not person:
        raise NotFound('Person not found')
    res = register(conn, actor, guardian, confirm_new=confirm_new, link_person_ref=guardian_person_ref,
                   allow_no_id=True, require_dob=False, confirm_on_suggestions=True)
    g = _get_by_ref(cur, res['person']['person_ref'])
    if g['id'] == person['id']:
        raise ValidationError('A person cannot be their own guardian')
    rel = _clean({'r': relationship}, 'r') or None
    try:
        cur.execute('SAVEPOINT guardian_link')
        cur.execute("INSERT INTO person_guardians (person_id, guardian_person_id, relationship) "
                    "VALUES (%s, %s, %s) RETURNING id", (person['id'], g['id'], rel))
        linked, link_new = cur.fetchone()['id'], True
        cur.execute('RELEASE SAVEPOINT guardian_link')
    except pgerr.UniqueViolation:
        cur.execute('ROLLBACK TO SAVEPOINT guardian_link')
        link_new = False
        if rel:
            cur.execute("UPDATE person_guardians SET relationship = %s WHERE person_id = %s AND guardian_person_id = %s "
                        "AND relationship IS NULL", (rel, person['id'], g['id']))
    except pgerr.InsufficientPrivilege as e:
        cur.execute('ROLLBACK TO SAVEPOINT guardian_link')
        raise PermissionDenied(e.diag.message_primary)
    _audit(cur, actor, 'GUARDIAN_ADD' if link_new else 'GUARDIAN_CONFIRM', person_ref,
           {'guardian': g['person_ref'], 'relationship': rel})
    return {'person': person_view(cur, actor, _get_by_ref(cur, person_ref)), 'guardian': res['person'],
            'link_created': link_new, 'guardian_created': res['created'],
            'guardian_filled': res['filled'], 'guardian_updated': res['updated']}

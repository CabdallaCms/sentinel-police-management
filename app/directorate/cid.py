"""CID — case tracking and suspect alerts.  Ported from legacy /api/crime-cases, /evidence, PATCH and /api/suspect-alerts
(backend/server.py ~l.5004–5120, 5484–5560, 5884).

Legacy                                               Unified
---------------------------------------------------  ----------------------------------------------------------
free-text suspect names (`suspect_alerts.full_name`)  every participant is a PERSON of the Central Registry; the
                                                      alert row links to person_id (so a checkpoint's yes/no
                                                      screening finds the same person at any unit).
one global CID desk                                   cases are OWNED by the CID directorate or one of its bureaus
                                                      (a data insert); the owner scopes who may read / update.
hand-rolled status list in code                       policy data (`case.statuses`, `case.participant_roles`, ...)
no state boundary                                     a case / alert owner must sit inside the Northeastern State
                                                      (DB trigger); a bureau claims its region with attrs.region.
alerts could only be created                          alerts can be LIFTED (reason + who + when), never deleted.
"""
from typing import Dict, List, Optional

import psycopg2.errors as pgerr
import psycopg2.extras

from .. import db
from ..identity import registry
from ..identity.errors import Duplicate, NeedsConfirmation, NotFound, PermissionDenied, ValidationError
from ..operations import common as C

PERSON_KEYS = registry.PROFILE_FIELDS
EDITABLE = ('category', 'location', 'status', 'incident_summary', 'notes')      # legacy PATCH field list


def _person_data(d: Optional[Dict]) -> Dict:
    return {k: d[k] for k in PERSON_KEYS if d and d.get(k) not in (None, '')}


def _owner(cur, actor: db.Actor, code: Optional[str], perm: str) -> Dict:
    """The CID unit that will own the record: the directorate by default, or one of its bureaus."""
    if not code:
        cur.execute("SELECT code FROM org_units WHERE id = service_unit('cid')")
        code = cur.fetchone()['code']
    unit = C.resolve_unit(cur, actor, code, perm, ('directorate', 'bureau'), 'CID unit', scope='state')
    cur.execute("SELECT authz_can(%s, %s, %s) AS ok, (SELECT %s IN (SELECT descendant_id FROM org_unit_closure "
                "WHERE ancestor_id = service_unit('cid'))) AS in_cid", (actor.user_id, perm, unit['id'], unit['id']))
    if not cur.fetchone()['in_cid']:
        raise ValidationError(f'{unit["name"]} is not part of the CID directorate', fields=['owner_unit'])
    return unit


def _ref(cur, prefix: str, unit_code: str) -> str:
    cur.execute('SELECT next_ref(%s, %s) AS ref', (prefix, unit_code))
    return cur.fetchone()['ref']


def _case(cur, actor: db.Actor, ref: str, lock=False) -> Dict:
    cur.execute("""SELECT c.id, c.case_ref, c.category, c.status, c.location, c.incident_summary, c.notes, c.created_at,
                          c.updated_at, o.id AS owner_id, o.code AS owner_code, o.name AS owner_name,
                          unit_region_name(o.id) AS region,
                          authz_can(%(u)s, 'case:update', c.owner_unit_id) AS can_update,
                          authz_can(%(u)s, 'alert:create', c.owner_unit_id) AS can_alert,
                          i.file_number AS source_incident
                     FROM crime_cases c JOIN org_units o ON o.id = c.owner_unit_id
                     LEFT JOIN crime_incidents i ON i.id = c.source_incident_id
                    WHERE c.case_ref = %(r)s""", {'u': actor.user_id, 'r': ref})
    row = cur.fetchone()
    if not row:
        raise NotFound('Case not found (or it belongs to a unit outside your scope)')
    if lock and row['can_update']:                       # serialise writers; only once we know the user may write
        cur.execute('SELECT 1 FROM crime_cases WHERE id = %s FOR UPDATE', (row['id'],))
    return row


def _participant(conn, cur, actor: db.Actor, act: db.Actor, case: Dict, p: Dict, index: int = 0) -> Dict:
    """Register-or-link ONE participant and write the case-linked alert row."""
    roles = C.policy(cur, 'case.participant_roles', [])
    role = C.choice(p.get('role') or 'Suspect', roles, 'Participant role', 'role', required=True)
    person = _person_data(p)
    if not person and not p.get('person_ref'):
        raise ValidationError('Each participant needs a name (or an existing person_ref)', fields=['participants'])
    try:
        reg = registry.register(conn, act, person, confirm_new=bool(p.get('confirm_new')),
                                link_person_ref=p.get('person_ref'), allow_no_id=True, require_dob=False,
                                confirm_on_suggestions=True)
    except NeedsConfirmation as e:
        e.extra.update(scope='participant', index=index)
        raise
    ref = reg['person']['person_ref']
    pid = C.person_id(cur, ref)
    notes = C.text(p, 'reason') or f'Linked to CID case {case["case_ref"]} — {case["category"]}'
    alert_ref = _ref(cur, 'AL', case['owner_code'])
    try:
        cur.execute('SAVEPOINT ins_part')
        cur.execute("""INSERT INTO suspect_alerts (alert_ref, person_id, case_id, owner_unit_id, role, origin, notes)
                       VALUES (%s, %s, %s, %s, %s, 'Case Link', %s)""",
                    (alert_ref, pid, case['id'], case['owner_id'], role, notes))
    except pgerr.UniqueViolation:
        cur.execute('ROLLBACK TO SAVEPOINT ins_part')
        raise Duplicate(f'{reg["person"]["full_name"]} is already recorded on case {case["case_ref"]}', person_ref=ref)
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_part')
        C.translate_db_error(e)
    return {'alert_ref': alert_ref, 'role': role, 'raises_alert': role == 'Suspect', 'person_ref': ref,
            'full_name': reg['person']['full_name'], 'person_created': reg['created']}


# =============================================================================================
def create_case(conn, actor: db.Actor, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    owner = _owner(cur, actor, data.get('owner_unit') or data.get('unit'), 'case:create')
    act = C.at_unit(actor, owner)
    category = C.text(data, 'category')
    if not category:
        raise ValidationError('Crime category is required', fields=['category'])
    statuses = C.policy(cur, 'case.statuses', [])
    status = C.choice(data.get('status'), statuses, 'Case status', 'status') or statuses[0]
    source_id = None
    if data.get('source_incident'):
        cur.execute('SELECT id FROM crime_incidents WHERE file_number = %s', (str(data['source_incident']).strip(),))
        r = cur.fetchone()
        if not r:
            raise ValidationError('That incident file does not exist or is outside your scope', fields=['source_incident'])
        source_id = r['id']
    parts_in = data.get('participants') or []
    ref = _ref(cur, 'CS', owner['code'])
    try:
        cur.execute('SAVEPOINT ins_case')
        cur.execute("""INSERT INTO crime_cases (case_ref, owner_unit_id, source_incident_id, category, status, incident_summary,
                                                 location, notes)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING id, created_at""",
                    (ref, owner['id'], source_id, category, status, C.text(data, 'incident_summary') or None,
                     C.text(data, 'location') or None, C.text(data, 'notes') or None))
        row = cur.fetchone()
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_case')
        C.translate_db_error(e)
    case = {'id': row['id'], 'case_ref': ref, 'category': category, 'owner_id': owner['id'], 'owner_code': owner['code']}
    participants = [_participant(conn, cur, actor, act, case, p, i) for i, p in enumerate(parts_in)]
    C.audit(cur, actor, owner, 'CASE_CREATE', 'crime_case', ref,
            {'category': category, 'status': status, 'participants': [x['person_ref'] for x in participants]})
    return {'case': {'case_ref': ref, 'category': category, 'status': status, 'owner': owner['code'],
                     'created_at': row['created_at']}, 'participants': participants}


def list_cases(conn, actor: db.Actor, status: Optional[str] = None, q: Optional[str] = None, limit: int = 50) -> Dict:
    cur = C.new_cursor(conn, actor)
    like = f'%{q.strip()}%' if q and q.strip() else None
    cur.execute("""SELECT c.case_ref, c.category, c.status, c.location, c.created_at, c.updated_at, o.code AS owner_code,
                          o.name AS owner_name,
                          (SELECT count(*) FROM suspect_alerts a WHERE a.case_id = c.id) AS participants
                     FROM crime_cases c JOIN org_units o ON o.id = c.owner_unit_id
                    WHERE (%(s)s::text IS NULL OR c.status = %(s)s)
                      AND (%(q)s::text IS NULL OR c.case_ref ILIKE %(q)s OR c.category ILIKE %(q)s
                           OR c.incident_summary ILIKE %(q)s OR c.location ILIKE %(q)s)
                    ORDER BY c.created_at DESC, c.id DESC LIMIT %(n)s""",
                {'s': status or None, 'q': like, 'n': max(1, min(200, limit))})
    return {'items': cur.fetchall()}


def get_case(conn, actor: db.Actor, ref: str) -> Dict:
    cur = C.new_cursor(conn, actor)
    case = _case(cur, actor, ref)
    cur.execute("""SELECT a.alert_ref, a.role, a.alert_status, a.origin, a.notes, a.created_at, a.lifted_at, a.lift_reason,
                          p.person_ref, p.full_name, p.national_id
                     FROM suspect_alerts a JOIN persons p ON p.id = a.person_id WHERE a.case_id = %s ORDER BY a.id""",
                (case['id'],))
    participants = cur.fetchall()
    cur.execute("""SELECT e.evidence_ref, e.caption, e.file_name, e.file_type, e.created_at, u.display_name AS uploaded_by
                     FROM case_evidence e LEFT JOIN users u ON u.id = e.uploaded_by WHERE e.case_id = %s ORDER BY e.id""",
                (case['id'],))
    evidence = cur.fetchall()
    for k in ('id', 'owner_id'):
        case.pop(k)
    return {**case, 'participants': participants, 'evidence': evidence}


def update_case(conn, actor: db.Actor, ref: str, changes: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    case = _case(cur, actor, ref, lock=True)
    unknown = [k for k in (changes or {}) if k not in EDITABLE]
    if unknown:
        raise ValidationError('These fields cannot be edited: ' + ', '.join(unknown) +
                              '. Editable: ' + ', '.join(EDITABLE), fields=unknown)
    if not case['can_update']:
        raise PermissionDenied('You may not update cases owned by ' + case['owner_name'])
    sets = {}
    for k in EDITABLE:
        if k in (changes or {}):
            sets[k] = C.text(changes, k) or None
    if 'status' in sets:
        sets['status'] = C.choice(sets['status'], C.policy(cur, 'case.statuses', []), 'Case status', 'status', required=True)
    if 'category' in sets and not sets['category']:
        raise ValidationError('Crime category cannot be empty', fields=['category'])
    if not sets:
        raise ValidationError('Nothing to update', fields=list(EDITABLE))
    try:
        cur.execute('SAVEPOINT upd_case')
        cur.execute('UPDATE crime_cases SET ' + ', '.join(f'{k} = %({k})s' for k in sets) + ' WHERE id = %(id)s',
                    {**sets, 'id': case['id']})
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT upd_case')
        C.translate_db_error(e)
    C.audit(cur, actor, {'id': case['owner_id']}, 'CASE_UPDATE', 'crime_case', ref,
            {k: {'from': case.get(k), 'to': v} for k, v in sets.items() if case.get(k) != v})
    return get_case(conn, actor, ref)


def add_evidence(conn, actor: db.Actor, ref: str, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    case = _case(cur, actor, ref)
    if not case['can_update']:
        raise PermissionDenied('You may not add evidence to cases owned by ' + case['owner_name'])
    name = str(data.get('file') or '').strip()
    if not name:
        raise ValidationError('Attach an evidence file (upload it first)', fields=['file'])
    C.check_uploads(cur, actor, [name], 'file', 'Evidence file')
    types = C.policy(cur, 'case.evidence_types', [])
    ftype = C.choice(data.get('file_type'), types, 'Evidence type', 'file_type') or types[0]
    eref = _ref(cur, 'EV', case['owner_code'])
    try:
        cur.execute('SAVEPOINT ins_ev')
        cur.execute("INSERT INTO case_evidence (evidence_ref, case_id, caption, file_name, file_type) "
                    "VALUES (%s, %s, %s, %s, %s) RETURNING created_at",
                    (eref, case['id'], C.text(data, 'caption') or None, name, ftype))
        created = cur.fetchone()['created_at']
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_ev')
        C.translate_db_error(e)
    C.audit(cur, actor, {'id': case['owner_id']}, 'CASE_EVIDENCE', 'crime_case', ref, {'evidence': eref, 'type': ftype})
    return {'evidence': {'evidence_ref': eref, 'case_ref': ref, 'file_name': name, 'file_type': ftype,
                         'caption': C.text(data, 'caption') or None, 'created_at': created}}


def add_participants(conn, actor: db.Actor, ref: str, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    case = _case(cur, actor, ref, lock=True)
    if not case['can_update']:
        raise PermissionDenied('You may not add participants to cases owned by ' + case['owner_name'])
    items = data.get('participants') or ([data] if data.get('role') or data.get('first_name') or data.get('person_ref') else [])
    if not items:
        raise ValidationError('Add at least one participant', fields=['participants'])
    act = C.at_unit(actor, {'id': case['owner_id']})
    out = [_participant(conn, cur, actor, act, case, p, i) for i, p in enumerate(items)]
    C.audit(cur, actor, {'id': case['owner_id']}, 'CASE_PARTICIPANTS', 'crime_case', ref,
            {'added': [(x['person_ref'], x['role']) for x in out]})
    return {'case_ref': ref, 'participants': out}


# ---- direct intelligence listings ----------------------------------------------------------------
def list_alerts(conn, actor: db.Actor, status: Optional[str] = 'Active alert', limit: int = 100) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute("""SELECT a.alert_ref, a.role, a.alert_status, a.origin, a.notes, a.created_at, a.lifted_at, a.lift_reason,
                          c.case_ref, p.person_ref, p.full_name, p.national_id, o.code AS owner_code,
                          authz_can(%(u)s, 'alert:create', a.owner_unit_id) AS can_lift
                     FROM suspect_alerts a JOIN persons p ON p.id = a.person_id JOIN org_units o ON o.id = a.owner_unit_id
                     LEFT JOIN crime_cases c ON c.id = a.case_id
                    WHERE (%(s)s::text IS NULL OR a.alert_status = %(s)s)
                    ORDER BY a.created_at DESC, a.id DESC LIMIT %(n)s""",
                {'u': actor.user_id, 's': status or None, 'n': max(1, min(500, limit))})
    return {'items': cur.fetchall()}


def create_alert(conn, actor: db.Actor, data: Dict) -> Dict:
    """A DIRECT intelligence listing (no case): the person is registered/linked in the registry; a reason is required."""
    cur = C.new_cursor(conn, actor)
    owner = _owner(cur, actor, data.get('owner_unit') or data.get('unit'), 'alert:create')
    act = C.at_unit(actor, owner)
    reason = C.text(data, 'reason') or C.text(data, 'notes')
    if not reason:
        raise ValidationError('A reason is required for a direct listing', fields=['reason'])
    person = _person_data(data.get('person') or data)
    if not person and not data.get('person_ref'):
        raise ValidationError('Identify the person (name, or an existing person_ref)', fields=['person'])
    try:
        reg = registry.register(conn, act, person, confirm_new=bool(data.get('confirm_new')),
                                link_person_ref=data.get('person_ref'), allow_no_id=True, require_dob=False,
                                confirm_on_suggestions=True)
    except NeedsConfirmation as e:
        e.extra['scope'] = 'person'
        raise
    ref = reg['person']['person_ref']
    pid = C.person_id(cur, ref)
    aref = _ref(cur, 'AL', owner['code'])
    try:
        cur.execute('SAVEPOINT ins_alert')
        cur.execute("""INSERT INTO suspect_alerts (alert_ref, person_id, case_id, owner_unit_id, role, origin, notes)
                       VALUES (%s, %s, NULL, %s, 'Suspect', 'Direct Intelligence Listing', %s) RETURNING created_at""",
                    (aref, pid, owner['id'], reason))
        created = cur.fetchone()['created_at']
    except pgerr.UniqueViolation:
        cur.execute('ROLLBACK TO SAVEPOINT ins_alert')
        raise Duplicate(f'{reg["person"]["full_name"]} already has an active direct listing', person_ref=ref)
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_alert')
        C.translate_db_error(e)
    C.audit(cur, actor, owner, 'ALERT_CREATE', 'suspect_alert', aref, {'person': ref})
    return {'alert': {'alert_ref': aref, 'person_ref': ref, 'full_name': reg['person']['full_name'], 'role': 'Suspect',
                      'origin': 'Direct Intelligence Listing', 'alert_status': 'Active alert', 'notes': reason,
                      'created_at': created}, 'person_created': reg['created']}


def lift_alert(conn, actor: db.Actor, alert_ref: str, reason: str) -> Dict:
    cur = C.new_cursor(conn, actor)
    reason = C.text({'r': reason}, 'r')
    if not reason:
        raise ValidationError('A reason is required to lift an alert', fields=['reason'])
    cur.execute("""SELECT a.id, a.alert_status, a.owner_unit_id, authz_can(%s, 'alert:create', a.owner_unit_id) AS ok
                     FROM suspect_alerts a WHERE a.alert_ref = %s""", (actor.user_id, alert_ref))
    a = cur.fetchone()
    if not a:
        raise NotFound('Alert not found (or it belongs to a unit outside your scope)')
    if not a['ok']:
        raise PermissionDenied('You may not lift alerts owned by this CID unit')
    cur.execute('SELECT alert_status FROM suspect_alerts WHERE id = %s FOR UPDATE', (a['id'],))
    if cur.fetchone()['alert_status'] != 'Active alert':
        raise Duplicate(f'Alert {alert_ref} is already lifted')
    try:
        cur.execute('SAVEPOINT lift')
        cur.execute("UPDATE suspect_alerts SET alert_status = 'Lifted', lift_reason = %s WHERE id = %s "
                    "RETURNING lifted_at", (reason, a['id']))
        at = cur.fetchone()['lifted_at']
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT lift')
        C.translate_db_error(e)
    C.audit(cur, actor, {'id': a['owner_unit_id']}, 'ALERT_LIFT', 'suspect_alert', alert_ref, {'reason': reason})
    return {'alert_ref': alert_ref, 'alert_status': 'Lifted', 'lifted_at': at, 'lift_reason': reason}

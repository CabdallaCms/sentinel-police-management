"""Checkpoint stops — ported from legacy POST /api/checkpoint-events (backend/server.py ~l.5589).

Legacy                                             Unified
-------------------------------------------------  --------------------------------------------------------
location 'South'/'East'/'West' (hardcoded tuple,   `unit` = a checkpoint unit in the org tree (data, not code);
 3 text columns, RBAC by string equality)           RBAC = authz_can('checkpoint:create', unit) + DB RLS
ensure_person(): match-or-create                   registry.register(): the SAME smart search, locks and
                                                    duplicate confirmation as the intake screen
guardian: free text + optional find_by_id          guardian is a PERSON (registry.add_guardian), linked
screening: suspect_alerts lookup, any role          person_alert_flag(); a user who may not check alerts
                                                    cannot record a stop (never a silent false 'clear')
event_id 'CP-'+epoch ms (can collide)              next_ref('CP', unit) — concurrency-safe
all validation in one handler                      same rules, policy-driven (policy 'checkpoint.required')
"""
from typing import Dict, List, Optional

import psycopg2.errors as pgerr
import psycopg2.extras

from .. import db
from ..identity import registry
from ..identity.errors import NeedsConfirmation, PermissionDenied, ValidationError
from . import common as C

PERSON_KEYS = registry.PROFILE_FIELDS


def _person_data(d: Optional[Dict]) -> Dict:
    return {k: d[k] for k in PERSON_KEYS if d and d.get(k) not in (None, '')}


def _confirming(scope: str):
    """Re-raise NeedsConfirmation tagged with WHO is ambiguous (the traveler or the guardian)."""
    def deco(fn):
        def wrapped(*a, **kw):
            try:
                return fn(*a, **kw)
            except NeedsConfirmation as e:
                e.extra['scope'] = scope
                raise
        return wrapped
    return deco


def record_stop(conn, actor: db.Actor, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    unit = C.resolve_unit(cur, actor, data.get('unit'), 'checkpoint:create', ('checkpoint',), 'checkpoint')
    act = C.at_unit(actor, unit)
    cur.execute("SELECT authz_has(%s, 'alert:check') AS ok", (actor.user_id,))
    if not cur.fetchone()['ok']:
        raise PermissionDenied('You are not allowed to screen travelers against active alerts, so you cannot record a stop')

    req = C.policy(cur, 'checkpoint.required', {})
    traveler = _person_data(data.get('traveler'))
    guardian_in = _person_data(data.get('guardian'))
    guardian_rel = C.text(data, 'guardian_relationship')

    # ---- legacy validation, before anything is written --------------------------------------
    problems: List[Dict] = []

    def need(ok, field, message):
        if not ok:
            problems.append({'field': field, 'message': message})

    purpose = C.text(data, 'purpose_of_visit')
    current_address = C.text(data, 'current_address') or C.text(traveler, 'residence')
    need(purpose, 'purpose_of_visit', 'Purpose of visit is required')
    need(current_address, 'current_address', 'Traveler current address is required')
    try:
        dob = registry._parse_dob(traveler.get('date_of_birth'), required=True)  # legacy: DoB required
    except ValidationError as e:
        dob = None
        problems.append({'field': 'date_of_birth', 'message': e.message})
    photo = (data.get('traveler_photo') or '').strip()
    traveler_docs = [d for d in (data.get('traveler_docs') or []) if str(d or '').strip()]
    need(photo or not req.get('photo', True), 'traveler_photo', 'Traveler photo is required')
    need(len(traveler_docs) >= int(req.get('traveler_docs', 1)), 'traveler_docs',
         f'At least {int(req.get("traveler_docs", 1))} traveler document(s) required')

    mode = req.get('guardian', 'all')
    age = registry._age(dob)
    guardian_needed = mode == 'all' or (mode == 'minors' and age is not None and age < 18)
    guardian_given = bool(guardian_in)
    guardian_docs = [d for d in (data.get('guardian_docs') or []) if str(d or '').strip()]
    if guardian_needed or guardian_given:
        need(guardian_in, 'guardian', 'Guardian full name is required')
        need(guardian_rel, 'guardian_relationship', 'Guardian relationship is required')
        need(C.text(guardian_in, 'phone'), 'guardian_phone', 'Guardian contact number is required')
        need(C.text(guardian_in, 'residence'), 'guardian_address', 'Guardian permanent address is required')
        need(C.text(guardian_in, 'occupation'), 'guardian_occupation', 'Guardian occupation is required')
        need(len(guardian_docs) >= int(req.get('guardian_docs', 1)), 'guardian_docs',
             f'At least {int(req.get("guardian_docs", 1))} guardian document(s) required')
    if problems:
        raise ValidationError(' · '.join(p['message'] for p in problems), fields=[p['field'] for p in problems],
                              problems=problems)
    photo = C.check_uploads(cur, actor, [photo], 'traveler_photo', 'Traveler photo', images_only=True)[0] if photo else None
    traveler_docs = C.check_uploads(cur, actor, traveler_docs, 'traveler_docs', 'Traveler document')
    guardian_docs = C.check_uploads(cur, actor, guardian_docs, 'guardian_docs', 'Guardian document')

    # ---- the traveler goes through the Central Person Registry --------------------------------
    person_in = dict(traveler)
    person_in.setdefault('residence', current_address)
    if photo:
        person_in['photo_path'] = photo
    reg = _confirming('traveler')(registry.register)(
        conn, act, person_in, confirm_new=bool(data.get('confirm_new')),
        link_person_ref=data.get('link_person_ref'), allow_no_id=True)           # legacy: IDs optional at a checkpoint
    ref = reg['person']['person_ref']
    pid = C.person_id(cur, ref)

    # ---- screening (yes/no only — the alert's content is never shown here) -----------------------
    cur.execute('SELECT person_alert_flag(%s, %s) AS flag', (actor.user_id, pid))
    alerted = bool(cur.fetchone()['flag'])
    screening, action = ('Flagged match', 'Supervisor contacted') if alerted else ('No active alert', 'Cleared')

    # ---- guardian: a person too, linked append-only ---------------------------------------------
    guardian_out = None
    if guardian_needed or guardian_given:
        g = _confirming('guardian')(registry.add_guardian)(
            conn, act, ref, guardian_in, relationship=guardian_rel,
            guardian_person_ref=data.get('guardian_person_ref'), confirm_new=bool(data.get('guardian_confirm_new')))
        guardian_out = {'person_ref': g['guardian']['person_ref'], 'full_name': g['guardian']['full_name'],
                        'relationship': guardian_rel, 'created': g['guardian_created']}

    # ---- the event ------------------------------------------------------------------------------------
    details = {'current_address': current_address, 'permanent_address': C.text(data, 'permanent_address'),
               'traveler_photo': photo, 'traveler_docs': traveler_docs, 'guardian_docs': guardian_docs}
    if guardian_out:
        details['guardian'] = {**guardian_out, 'phone': C.text(guardian_in, 'phone'),
                               'address': C.text(guardian_in, 'residence'), 'occupation': C.text(guardian_in, 'occupation')}
    cur.execute("SELECT next_ref('CP', %s) AS ref", (unit['code'],))
    event_ref = cur.fetchone()['ref']
    try:
        cur.execute('SAVEPOINT ins_event')
        cur.execute("""INSERT INTO checkpoint_events (event_ref, unit_id, person_id, screening_result, action_taken,
                              purpose_of_visit, notes, details)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING created_at""",
                    (event_ref, unit['id'], pid, screening, action, purpose, C.text(data, 'notes') or None,
                     psycopg2.extras.Json(details)))
        created_at = cur.fetchone()['created_at']
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_event')
        C.translate_db_error(e)
    C.audit(cur, actor, unit, 'CHECKPOINT_STOP', 'checkpoint_event', event_ref,
            {'person': ref, 'screening': screening, 'guardian': guardian_out and guardian_out['person_ref'],
             'person_created': reg['created']})
    return {'event': {'event_ref': event_ref, 'unit': {'code': unit['code'], 'name': unit['name'],
                                                        'district': unit['district'], 'region': unit['region']},
                      'screening_result': screening, 'action_taken': action, 'alerted': alerted,
                      'created_at': created_at},
            'person': reg['person'], 'guardian': guardian_out,
            'identity': {'created': reg['created'], 'exists': reg['exists'], 'filled': reg['filled'],
                         'updated': reg['updated'], 'ignored': reg['ignored'], 'match': reg['match']}}


def list_stops(conn, actor: db.Actor, unit: Optional[str] = None, person_ref: Optional[str] = None,
               limit: int = 50) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute("""SELECT e.event_ref, u.code AS unit_code, u.name AS unit_name, e.screening_result, e.action_taken,
                          e.purpose_of_visit, e.notes, e.created_at, e.details,
                          p.person_ref, p.full_name, usr.display_name AS recorded_by
                     FROM checkpoint_events e
                     JOIN org_units u ON u.id = e.unit_id
                     JOIN persons p ON p.id = e.person_id
                     LEFT JOIN users usr ON usr.id = e.created_by
                    WHERE authz_can(%(u)s, 'checkpoint:view', e.unit_id)
                      AND (%(unit)s::text IS NULL OR u.code = %(unit)s)
                      AND (%(ref)s::text  IS NULL OR p.person_ref = %(ref)s)
                    ORDER BY e.created_at DESC, e.id DESC LIMIT %(n)s""",
                {'u': actor.user_id, 'unit': unit or None, 'ref': person_ref or None, 'n': max(1, min(200, limit))})
    return {'items': cur.fetchall()}

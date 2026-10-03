"""HR — officer register.  Ported from legacy register_officer / officer_view (backend/server.py l.2149–2440).

Legacy                                         Unified
---------------------------------------------  ---------------------------------------------------------------
`officers.station_id` -> police_stations       the POSTING is any unit of the tree inside the Northeastern State
                                               (DB trigger); the roster is NATIONAL — read/written by whoever
                                               holds officer:view / officer:create at the HR directorate (T2).
free-text identity on the officer row          the officer is a PERSON of the Central Registry (photo, DoB, mother's
                                               name, contact live there; core identity stays locked there).
rank / duty status edited freely               rank changes ONLY through an approved conduct file; duty status
                                               through the audited route below; both leave service-history rows.
"""
from typing import Dict, Optional

import psycopg2.errors as pgerr
import psycopg2.extras

from .. import db
from ..identity import registry
from ..identity.errors import NeedsConfirmation, NotFound, PermissionDenied, ValidationError
from ..operations import common as C

PERSON_KEYS = registry.PROFILE_FIELDS


def _person_data(d: Optional[Dict]) -> Dict:
    return {k: d[k] for k in PERSON_KEYS if d and d.get(k) not in (None, '')}


def _hr_can(cur, actor: db.Actor, perm: str) -> bool:
    cur.execute("SELECT authz_can(%s, %s, service_unit('hr')) AS ok", (actor.user_id, perm))
    return bool(cur.fetchone()['ok'])


def register_officer(conn, actor: db.Actor, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    unit = C.resolve_unit(cur, actor, data.get('unit'), 'officer:create', None, 'posting unit', scope='state',
                          or_at_service='hr')
    act = C.at_unit(actor, unit)
    pol = lambda k: C.policy(cur, k, [])
    problems = []

    def need(v, field, msg):
        if not v:
            problems.append({'field': field, 'message': msg})
        return v

    rank = unit_role = None
    for fn, field, label, key in (('rank', 'rank', 'Rank', 'officer.ranks'),
                                  ('unit_role', 'unit_role', 'Unit / Division', 'officer.divisions')):
        try:
            v = C.choice(data.get(field), pol(key), label, field, required=True)
            rank, unit_role = (v, unit_role) if field == 'rank' else (rank, v)
        except ValidationError as e:
            problems.append({'field': field, 'message': e.message})
    try:
        enlist = C.parse_date(data.get('date_of_enlistment'), 'date_of_enlistment', 'Date of enlistment')
    except ValidationError as e:
        enlist = None
        problems.append({'field': 'date_of_enlistment', 'message': e.message})
    try:
        duty = C.choice(data.get('duty_status'), pol('officer.duty_statuses'), 'Duty status', 'duty_status') or 'Active'
        if duty == 'Terminated':
            problems.append({'field': 'duty_status', 'message': 'A new officer cannot start as Terminated'})
        blood = C.choice(data.get('blood_group'), pol('officer.blood_groups'), 'Blood group', 'blood_group')
        g_rel = C.choice((data.get('guarantor') or {}).get('relationship'), pol('officer.guarantor_relationships'),
                         'Guarantor relationship', 'guarantor')
        d1t = C.choice(data.get('doc1_type'), pol('officer.doc_types_primary'), 'Document slot 1 type', 'doc1_type', required=True)
        d2t = C.choice(data.get('doc2_type'), pol('officer.doc_types_secondary'), 'Document slot 2 type', 'doc2_type')
    except ValidationError as e:
        problems.append({'field': (e.extra.get('fields') or ['form'])[0], 'message': e.message})
        d1t = d2t = blood = g_rel = None
    person = _person_data(data.get('person'))
    for k, label in (('mother_name', "Mother's name"), ('date_of_birth', 'Date of birth'), ('place_of_birth', 'Place of birth'),
                     ('phone', 'Contact number')):
        need(person.get(k) or (data.get('person_ref') and True), k, f'{label} is required')
    need(person.get('first_name') or data.get('person_ref'), 'first_name', 'First name is required')
    g = data.get('guarantor') or {}
    for k, label in (('name', 'Guarantor name'), ('address', 'Guarantor permanent address'), ('contact', 'Guarantor contact')):
        need(C.text(g, k), 'guarantor', f'{label} is required')
    photo = (data.get('photo') or '').strip()
    need(photo, 'photo', 'Officer picture is required')
    doc1 = (data.get('doc1_file') or '').strip()
    need(doc1, 'doc1_file', 'Document slot 1 file is required')
    doc2 = (data.get('doc2_file') or '').strip()
    if doc2 and not d2t:
        problems.append({'field': 'doc2_type', 'message': 'Document slot 2 type is required when a file is attached'})
    if d2t and not doc2:
        problems.append({'field': 'doc2_file', 'message': 'Document slot 2 file is required when a type is selected'})
    if problems:
        raise ValidationError(' · '.join(p['message'] for p in problems), fields=sorted({p['field'] for p in problems}),
                              problems=problems)
    photo = C.check_uploads(cur, actor, [photo], 'photo', 'Officer picture', images_only=True)[0]
    gphoto = C.check_uploads(cur, actor, [g.get('photo')], 'guarantor', 'Guarantor picture', images_only=True)
    docs = C.check_uploads(cur, actor, [doc1] + ([doc2] if doc2 else []), 'doc1_file', 'Document')

    person_in = dict(person)
    person_in['photo_path'] = photo
    try:
        reg = registry.register(conn, act, person_in, confirm_new=bool(data.get('confirm_new')),
                                link_person_ref=data.get('person_ref'), allow_no_id=True)
    except NeedsConfirmation as e:
        e.extra['scope'] = 'officer'
        raise
    pref = reg['person']['person_ref']
    pid = C.person_id(cur, pref)
    cur.execute('SELECT id, service_ref FROM officers WHERE person_id = %s', (pid,))
    prior = cur.fetchone()
    if prior:
        from ..identity.errors import Duplicate
        raise Duplicate(f'{reg["person"]["full_name"]} is already registered as officer {prior["service_ref"]}',
                        service_ref=prior['service_ref'], person_ref=pref)
    details = {'date_of_enlistment': enlist.isoformat(), 'height_cm': C.text(data, 'height_cm') or None,
               'weight_kg': C.text(data, 'weight_kg') or None, 'blood_group': blood,
               'origin': {'region': C.text(data, 'region_of_origin') or None,
                          'district': C.text(data, 'district_of_origin') or None,
                          'town_village': C.text(data, 'town_village') or None},
               'guarantor': {'name': C.text(g, 'name'), 'address': C.text(g, 'address'),
                             'occupation': C.text(g, 'occupation') or None, 'relationship': g_rel,
                             'contact': C.text(g, 'contact'), 'photo': gphoto[0] if gphoto else None},
               'documents': [{'type': d1t, 'file': docs[0]}] + ([{'type': d2t, 'file': docs[1]}] if doc2 else [])}
    if details['origin']['district'] and not details['origin']['region']:
        raise ValidationError('Select the region of origin before the district', fields=['region_of_origin'])
    cur.execute("SELECT next_ref('POL') AS ref")
    sref = cur.fetchone()['ref']
    try:
        cur.execute('SAVEPOINT ins_off')
        cur.execute("""INSERT INTO officers (service_ref, person_id, unit_id, rank, unit_role, duty_status, full_name, details)
                       VALUES (%s, %s, %s, %s, %s, %s, %s, %s) RETURNING created_at""",
                    (sref, pid, unit['id'], rank, unit_role, duty, reg['person']['full_name'], psycopg2.extras.Json(details)))
        created = cur.fetchone()['created_at']
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_off')
        C.translate_db_error(e)
    C.audit(cur, actor, unit, 'OFFICER_REGISTER', 'officer', sref, {'person': pref, 'rank': rank, 'person_created': reg['created']})
    return {'officer': {'service_ref': sref, 'full_name': reg['person']['full_name'], 'rank': rank, 'unit_role': unit_role,
                        'duty_status': duty, 'unit': {'code': unit['code'], 'name': unit['name'], 'region': unit['region']},
                        'created_at': created},
            'person': reg['person'], 'identity': {'created': reg['created'], 'exists': reg['exists']}}


_BASE = """SELECT o.service_ref, o.full_name, o.rank, o.unit_role, o.duty_status, o.created_at,
                  u.code AS unit_code, u.name AS unit_name, unit_region_name(u.id) AS region,
                  p.person_ref, p.photo_path
             FROM officers o JOIN org_units u ON u.id = o.unit_id LEFT JOIN persons p ON p.id = o.person_id"""


def list_officers(conn, actor: db.Actor, q: Optional[str] = None, unit: Optional[str] = None,
                  duty_status: Optional[str] = None, limit: int = 100) -> Dict:
    cur = C.new_cursor(conn, actor)
    like = f'%{q.strip()}%' if q and q.strip() else None
    cur.execute(_BASE + """ WHERE (%(q)s::text IS NULL OR o.full_name ILIKE %(q)s OR o.service_ref ILIKE %(q)s)
                              AND (%(unit)s::text IS NULL OR u.id IN (SELECT descendant_id FROM org_unit_closure c
                                                                       JOIN org_units a ON a.id = c.ancestor_id WHERE a.code = %(unit)s))
                              AND (%(d)s::text IS NULL OR o.duty_status = %(d)s)
                            ORDER BY o.created_at DESC, o.id DESC LIMIT %(n)s""",
                {'q': like, 'unit': unit or None, 'd': duty_status or None, 'n': max(1, min(500, limit))})
    return {'items': cur.fetchall(), 'national_register': _hr_can(cur, actor, 'officer:view')}


def get_officer(conn, actor: db.Actor, ref: str) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute(_BASE + ' WHERE o.service_ref = %s', (ref,))
    o = cur.fetchone()
    if not o:
        raise NotFound('Officer not found (or posted outside your scope)')
    hr = _hr_can(cur, actor, 'officer:view')
    cur.execute('SELECT id, details FROM officers WHERE service_ref = %s', (ref,))
    r = cur.fetchone()
    o = dict(o, details=r['details'] if hr else None, can_update=_hr_can(cur, actor, 'officer:update'))
    cur.execute("""SELECT entry_type, summary, from_rank, to_rank, duty_status, created_at, c.action_ref
                     FROM officer_service_history h LEFT JOIN conduct_actions c ON c.id = h.conduct_id
                    WHERE h.officer_id = %s ORDER BY h.created_at DESC, h.id DESC""", (r['id'],))
    o['history'] = cur.fetchall()
    return o


def set_duty_status(conn, actor: db.Actor, ref: str, status: str, reason: str) -> Dict:
    reason = C.text({'r': reason}, 'r')
    if not reason:
        raise ValidationError('A reason is required to change a duty status', fields=['reason'])
    cur = db.cursor(conn)
    db.bind_actor(cur, actor, reason)
    cur.execute('SELECT id, duty_status, unit_id FROM officers WHERE service_ref = %s', (ref,))
    o = cur.fetchone()
    if not o:
        raise NotFound('Officer not found (or posted outside your scope)')
    if not _hr_can(cur, actor, 'officer:update'):
        raise PermissionDenied('Only the HR directorate may change an officer\'s duty status')
    cur.execute('SELECT duty_status FROM officers WHERE id = %s FOR UPDATE', (o['id'],))
    o['duty_status'] = cur.fetchone()['duty_status']
    status = C.choice(status, C.policy(cur, 'officer.duty_statuses', []), 'Duty status', 'duty_status', required=True)
    if status == o['duty_status']:
        raise ValidationError(f'The officer is already {status}', fields=['duty_status'])
    try:
        cur.execute('SAVEPOINT duty')
        cur.execute('UPDATE officers SET duty_status = %s WHERE id = %s', (status, o['id']))
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT duty')
        C.translate_db_error(e)
    C.audit(cur, actor, {'id': o['unit_id']}, 'OFFICER_DUTY_STATUS', 'officer', ref,
            {'from': o['duty_status'], 'to': status, 'reason': reason})
    return {'service_ref': ref, 'duty_status': status, 'previous': o['duty_status']}

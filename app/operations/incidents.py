"""Station crime-incident intake ("Register Crime") — ported from legacy register_crime (~l.2379)
and POST /api/crimes.

Legacy                                          Unified
----------------------------------------------  ------------------------------------------------------------
station_id text -> police_stations row          `unit` = a station (or checkpoint / airport) unit in the tree;
                                                 filing needs incident:create AT that unit (RBAC + RLS)
officer_id REQUIRED, any officer in the table   desk officer OPTIONAL (HR officer register is not ported yet)
                                                 but, if named, must be an ACTIVE officer posted at this unit
victim = free text, never linked                victim is linked to the Central Person Registry when they are
                                                 already in it; a victim is NEVER created as a person from
                                                 here, and an anonymous victim stores NO identity at all
file_number CRM-<year>-<code>-NNNN scanned      next_ref('CRM', unit)  — concurrency-safe, same shape
 with a SELECT of every number
incident_at stored as a string                  timestamptz, wall-clock = Africa/Mogadishu, never in the future
vocabularies in Python constants                vocabularies in policy_settings, enforced by the DB as well
evidence slots 1/2 with a path                  evidence = list of {type, file} (files must be the uploader's own)
a filed row could be edited                     immutable except case_status (DB trigger)
"""
from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional

import psycopg2.extras
import psycopg2.errors as pgerr

from .. import db
from ..identity import registry
from ..identity.errors import ValidationError
from . import common as C

SLOTS = (1, 2)


def _policy_list(cur, key):
    return C.policy(cur, key, [])


def file_incident(conn, actor: db.Actor, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    unit = C.resolve_unit(cur, actor, data.get('unit'), 'incident:create', ('station', 'checkpoint', 'airport'),
                          'station')
    problems: List[Dict] = []

    def attempt(fn, field):
        try:
            return fn()
        except ValidationError as e:
            problems.append({'field': field, 'message': e.message})

    category = attempt(lambda: C.choice(data.get('category'), _policy_list(cur, 'incident.categories'),
                                        'Crime category', 'category', required=True), 'category')
    severity = attempt(lambda: C.choice(data.get('severity'), _policy_list(cur, 'incident.severities'),
                                        'Severity', 'severity'), 'severity')
    status = attempt(lambda: C.choice(data.get('case_status') or data.get('status'),
                                      _policy_list(cur, 'incident.statuses'), 'Case status', 'case_status'),
                     'case_status') or 'Reported / Open'
    party = attempt(lambda: C.choice(data.get('reporting_party_type'), _policy_list(cur, 'incident.reporting_parties'),
                                     'Reporting party type', 'reporting_party_type'), 'reporting_party_type')
    gender = attempt(lambda: C.choice(data.get('victim_gender'), _policy_list(cur, 'incident.victim_genders'),
                                      'Victim gender', 'victim_gender'), 'victim_gender')
    incident_at = attempt(lambda: C.parse_local_datetime(data.get('incident_at'), 'incident_at', 'Incident date/time'),
                          'incident_at')
    if incident_at and incident_at > datetime.now(timezone.utc) + timedelta(minutes=5):
        problems.append({'field': 'incident_at', 'message': 'An incident cannot be dated in the future'})
    location = C.text(data, 'location_of_occurrence')
    description = ' '.join(str(data.get('description') or '').split())
    if not location:
        problems.append({'field': 'location_of_occurrence', 'message': 'Location of occurrence is required'})
    if not description:
        problems.append({'field': 'description', 'message': 'Incident description is required'})

    anonymous = str(data.get('victim_anonymous') or '').strip().lower() in ('1', 'true', 'yes', 'on')
    age = None
    if not anonymous and C.text(data, 'victim_age'):
        try:
            age = int(C.text(data, 'victim_age'))
            if not 0 <= age <= 120:
                raise ValueError
        except ValueError:
            problems.append({'field': 'victim_age', 'message': 'Victim age must be a whole number (0-120)'})

    evidence = []
    etypes = _policy_list(cur, 'incident.evidence_types')
    for slot in SLOTS:
        f = (data.get(f'evidence{slot}_file') or '').strip()
        t = attempt(lambda: C.choice(data.get(f'evidence{slot}_type'), etypes, f'Evidence slot {slot} type',
                                     f'evidence{slot}_type'), f'evidence{slot}_type')
        if f and not t and not any(p['field'] == f'evidence{slot}_type' for p in problems):
            problems.append({'field': f'evidence{slot}_type', 'message': f'Evidence slot {slot} type is required when a file is attached'})
        if f and t:
            evidence.append({'type': t, 'file': f})

    desk = None
    ref_in = C.text(data, 'officer_ref')
    if ref_in:
        cur.execute('SELECT * FROM desk_officer(%s, %s)', (unit['id'], ref_in))
        desk = cur.fetchone()
        if not desk:
            problems.append({'field': 'officer_ref', 'message':
                             f'"{ref_in}" is not an active officer posted at {unit["name"]}'})
    if problems:
        raise ValidationError(' · '.join(p['message'] for p in problems), fields=[p['field'] for p in problems],
                              problems=problems)
    C.check_uploads(cur, actor, [e['file'] for e in evidence], 'evidence', 'Evidence file')

    # ---- victim: linked, never created --------------------------------------------------------------------------
    details: Dict = {'reporting_party_type': party, 'victim_anonymous': anonymous, 'evidence': evidence,
                     'statement': C.text(data, 'statement') or None}
    victim_pid, victim_ref = None, None
    if anonymous:
        details['victim'] = None                     # data minimisation: nothing identifying is kept
    else:
        details['victim'] = {k: v for k, v in {
            'full_name': C.text(data, 'victim_full_name'), 'contact': C.text(data, 'victim_contact'),
            'national_id': C.text(data, 'victim_national_id'), 'gender': gender, 'age': age,
            'address': C.text(data, 'victim_address')}.items() if v not in (None, '')} or None
        wanted = C.text(data, 'victim_person_ref')
        if wanted:
            cur.execute('SELECT id, person_ref FROM persons WHERE person_ref = %s', (wanted,))
            row = cur.fetchone()
            if not row:
                raise ValidationError(f'Person {wanted} was not found in the registry', fields=['victim_person_ref'])
            victim_pid, victim_ref = row['id'], row['person_ref']
        elif C.text(data, 'victim_national_id'):
            res = registry.search(conn, actor, query={'national_id': C.text(data, 'victim_national_id')})
            if res.get('exists'):                       # an exact ID match only; never a fuzzy guess for a victim
                victim_ref = res['person']['person_ref']
                victim_pid = C.person_id(cur, victim_ref)

    cur.execute("SELECT next_ref('CRM', %s) AS ref", (unit['code'],))
    file_number = cur.fetchone()['ref']
    if desk:
        details['desk_officer'] = {'service_ref': desk['service_ref'], 'full_name': desk['full_name'], 'rank': desk['rank']}
    try:
        cur.execute('SAVEPOINT ins_inc')
        cur.execute("""INSERT INTO crime_incidents (file_number, unit_id, officer_id, category, incident_at, severity,
                              description, case_status, details, location_of_occurrence, victim_person_id)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING created_at""",
                    (file_number, unit['id'], desk['id'] if desk else None, category, incident_at, severity,
                     description, status, psycopg2.extras.Json(details), location, victim_pid))
        created_at = cur.fetchone()['created_at']
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_inc')
        C.translate_db_error(e)
    C.audit(cur, actor, unit, 'INCIDENT_FILED', 'crime_incident', file_number,
            {'category': category, 'severity': severity, 'victim_linked': victim_ref, 'anonymous': anonymous})
    return {'incident': {'file_number': file_number, 'unit': {'code': unit['code'], 'name': unit['name'],
                                                              'district': unit['district'], 'region': unit['region']},
                         'category': category, 'severity': severity, 'case_status': status,
                         'incident_at': incident_at, 'location_of_occurrence': location, 'created_at': created_at,
                         'desk_officer': details.get('desk_officer'), 'victim_anonymous': anonymous,
                         'victim_person_ref': victim_ref}}


def list_incidents(conn, actor: db.Actor, unit: Optional[str] = None, category: Optional[str] = None,
                   limit: int = 50) -> Dict:
    cur = C.new_cursor(conn, actor)
    cur.execute("""SELECT i.file_number, u.code AS unit_code, u.name AS unit_name, i.category, i.severity, i.case_status,
                          i.incident_at, i.location_of_occurrence, i.description, i.created_at, i.details,
                          vp.person_ref AS victim_person_ref
                     FROM crime_incidents i
                     JOIN org_units u ON u.id = i.unit_id
                     LEFT JOIN persons vp ON vp.id = i.victim_person_id
                    WHERE authz_can(%(u)s, 'incident:view', i.unit_id)
                      AND (%(unit)s::text IS NULL OR u.code = %(unit)s)
                      AND (%(cat)s::text IS NULL OR i.category = %(cat)s)
                    ORDER BY i.incident_at DESC, i.id DESC LIMIT %(n)s""",
                {'u': actor.user_id, 'unit': unit or None, 'cat': category or None, 'n': max(1, min(200, limit))})
    return {'items': cur.fetchall()}

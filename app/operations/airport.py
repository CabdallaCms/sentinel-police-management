"""Airport arrival / departure passenger log — ported from legacy POST /api/airport-records (~l.5368).

Legacy                                      Unified
------------------------------------------  ----------------------------------------------------------------
no location at all (one airport assumed)    `unit` = an airport unit; ANY number of airports, added as data
                                            (e.g. Buuhoodle Airport under the Buuhoodle district)
ensure_person() match-or-create             registry.register(): same smart search / locks / confirmation.
                                            ID (national or passport) REQUIRED, exactly as the legacy call
movement / date / flight NOT validated      movement is Arrival|Departure, a real date inside a policy window,
                                            a flight number — all required
'route' text stored                         origin_city / destination_city stored; route is derived for display
record id 'AR-'+epoch ms                    next_ref('AR', unit)
duplicates possible                         one record per person/movement/flight/day/airport (DB unique index)
(none)                                      informational yes/no alert flag for the passenger (never the detail)
"""
import re
from datetime import date, timedelta
from typing import Dict, Optional

import psycopg2.errors as pgerr

from .. import db
from ..identity import registry
from ..identity.errors import Duplicate, NeedsConfirmation, ValidationError
from . import common as C

FLIGHT_RE = re.compile(r'^[A-Z0-9][A-Z0-9-]{1,9}$')
MOVEMENTS = ['Arrival', 'Departure']


def record_passenger(conn, actor: db.Actor, data: Dict) -> Dict:
    cur = C.new_cursor(conn, actor)
    unit = C.resolve_unit(cur, actor, data.get('unit'), 'airport:create', ('airport',), 'airport')
    act = C.at_unit(actor, unit)

    problems = []
    try:
        movement = C.choice(data.get('movement'), MOVEMENTS, 'Movement', 'movement', required=True)
    except ValidationError as e:
        problems.append({'field': 'movement', 'message': e.message}); movement = None
    flight = re.sub(r'\s+', '', str(data.get('flight_number') or '')).upper()
    if not FLIGHT_RE.match(flight):
        problems.append({'field': 'flight_number', 'message': 'Flight number is required (e.g. FZ123)'})
    travel_date: Optional[date] = None
    try:
        travel_date = C.parse_date(data.get('travel_date'), 'travel_date', 'Travel date')
        win = C.policy(cur, 'airport.travel_window_days', {'past': 60, 'future': 7})
        today = date.today()
        if travel_date < today - timedelta(days=int(win['past'])) or travel_date > today + timedelta(days=int(win['future'])):
            problems.append({'field': 'travel_date', 'message':
                             f'Travel date must be within {win["past"]} days back and {win["future"]} days ahead'})
    except ValidationError as e:
        problems.append({'field': 'travel_date', 'message': e.message})
    origin = C.text(data, 'origin_city') or C.text(data, 'origin')
    destination = C.text(data, 'destination_city') or C.text(data, 'destination')
    if movement == 'Arrival' and not origin:
        problems.append({'field': 'origin_city', 'message': 'Origin city is required for an arrival'})
    if movement == 'Departure' and not destination:
        problems.append({'field': 'destination_city', 'message': 'Destination city is required for a departure'})
    if problems:
        raise ValidationError(' · '.join(p['message'] for p in problems), fields=[p['field'] for p in problems],
                              problems=problems)

    passenger = {k: data['passenger'][k] for k in registry.PROFILE_FIELDS
                 if isinstance(data.get('passenger'), dict) and data['passenger'].get(k) not in (None, '')}
    try:
        reg = registry.register(conn, act, passenger, confirm_new=bool(data.get('confirm_new')),
                                link_person_ref=data.get('link_person_ref'), allow_no_id=False)
    except NeedsConfirmation as e:
        e.extra['scope'] = 'passenger'
        raise
    ref = reg['person']['person_ref']
    pid = C.person_id(cur, ref)
    cur.execute('SELECT person_alert_flag(%s, %s) AS flag', (actor.user_id, pid))
    flag = cur.fetchone()['flag']

    cur.execute("SELECT next_ref('AR', %s) AS ref", (unit['code'],))
    record_ref = cur.fetchone()['ref']
    try:
        cur.execute('SAVEPOINT ins_pax')
        cur.execute("""INSERT INTO airport_passengers (record_ref, unit_id, person_id, movement, travel_date, flight_number,
                              airline, origin_city, destination_city, notes)
                       VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING created_at""",
                    (record_ref, unit['id'], pid, movement, travel_date, flight, C.text(data, 'airline') or None,
                     origin or None, destination or None, C.text(data, 'notes') or None))
        created_at = cur.fetchone()['created_at']
    except pgerr.UniqueViolation:
        cur.execute('ROLLBACK TO SAVEPOINT ins_pax')
        raise Duplicate(f'{reg["person"]["full_name"]} is already logged for {movement.lower()} flight {flight} on '
                        f'{travel_date.isoformat()} at {unit["name"]}.', person_ref=ref)
    except (pgerr.InsufficientPrivilege, pgerr.CheckViolation) as e:
        cur.execute('ROLLBACK TO SAVEPOINT ins_pax')
        C.translate_db_error(e)
    C.audit(cur, actor, unit, 'AIRPORT_RECORD', 'airport_passenger', record_ref,
            {'person': ref, 'movement': movement, 'flight': flight, 'person_created': reg['created']})
    return {'record': {'record_ref': record_ref, 'unit': {'code': unit['code'], 'name': unit['name'],
                                                          'district': unit['district'], 'region': unit['region']},
                       'movement': movement, 'travel_date': travel_date, 'flight_number': flight,
                       'airline': C.text(data, 'airline') or None, 'origin_city': origin or None,
                       'destination_city': destination or None,
                       'route': ' / '.join(x for x in (origin, destination) if x) or None, 'created_at': created_at},
            'person': reg['person'], 'has_active_alert': flag,
            'identity': {'created': reg['created'], 'exists': reg['exists'], 'filled': reg['filled'],
                         'updated': reg['updated'], 'ignored': reg['ignored'], 'match': reg['match']}}


def list_passengers(conn, actor: db.Actor, unit: Optional[str] = None, person_ref: Optional[str] = None,
                    movement: Optional[str] = None, date_from: Optional[str] = None, date_to: Optional[str] = None,
                    limit: int = 50) -> Dict:
    cur = C.new_cursor(conn, actor)
    mv = C.choice(movement, MOVEMENTS, 'Movement', 'movement') if movement else None
    d_from = C.parse_date(date_from, 'date_from', 'From date') if date_from else None
    d_to = C.parse_date(date_to, 'date_to', 'To date') if date_to else None
    cur.execute("""SELECT a.record_ref, u.code AS unit_code, u.name AS unit_name, a.movement, a.travel_date, a.flight_number,
                          a.airline, a.origin_city, a.destination_city, a.notes, a.created_at,
                          concat_ws(' / ', a.origin_city, a.destination_city) AS route,
                          p.person_ref, p.full_name, p.national_id, p.passport_id
                     FROM airport_passengers a
                     JOIN org_units u ON u.id = a.unit_id
                     JOIN persons p ON p.id = a.person_id
                    WHERE authz_can(%(u)s, 'airport:view', a.unit_id)
                      AND (%(unit)s::text IS NULL OR u.code = %(unit)s)
                      AND (%(ref)s::text IS NULL OR p.person_ref = %(ref)s)
                      AND (%(mv)s::text IS NULL OR a.movement = %(mv)s)
                      AND (%(df)s::date IS NULL OR a.travel_date >= %(df)s)
                      AND (%(dt)s::date IS NULL OR a.travel_date <= %(dt)s)
                    ORDER BY a.travel_date DESC, a.id DESC LIMIT %(n)s""",
                {'u': actor.user_id, 'unit': unit or None, 'ref': person_ref or None, 'mv': mv,
                 'df': d_from, 'dt': d_to, 'n': max(1, min(200, limit))})
    return {'items': cur.fetchall()}

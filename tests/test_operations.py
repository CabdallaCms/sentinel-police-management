"""Phase 2 — operational units: checkpoint stops, airport passenger logs, station crime incidents.

Three layers are exercised, all against a real PostgreSQL built from migrations/ (001+002+003):
  * DB rules   (region scope, provenance, append-only, RLS, unique)    — raw SQL under the non-owner role app_rw
  * services   (app.operations.*) hooked into the Central Person Registry
  * HTTP       (real server, real sockets)
The whole module runs with SENTINEL_DB_ROLE=app_rw, so row-level security is ON for every service call.
Fixtures expand the org tree with DATA ONLY (Buuhoodle Airport, a planned airport, a region outside the
operational list) — no schema or code change — which is itself one of the things under test.
"""
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, datetime, timedelta

import psycopg2

from app import server
from app.db import Actor
from app.identity import registry
from app.identity.errors import (Duplicate, NeedsConfirmation, NotFound, PermissionDenied, ValidationError)
from app.operations import airport, checkpoint, incidents, timeline, uploads, units
from app.operations.common import LOCAL_TZ
from . import pg_support
from .base import DbCase

_state = {}

PNG = b'\x89PNG\r\n\x1a\n' + b'\x00' * 32
TRAV = dict(first_name='Faadumo', second_name='Jaamac', third_name='Warsame', fourth_name='Ismaaciil',
            date_of_birth='1992-03-04', place_of_birth='Burao', national_id='SO7001', mother_name='Hawa Cali')
GUARD = dict(first_name='Warsame', second_name='Ismaaciil', third_name='Dhegaweyne', national_id='SO7002',
             phone='+252 63 111 2222', residence='Laascaanood, Hodan', occupation='Trader')
PAX = dict(first_name='Cabdi', second_name='Rashiid', third_name='Maxamuud', fourth_name='Jaamac',
           date_of_birth='1980-11-30', place_of_birth='Burao', national_id='SO8001')


OFFICERS_SQL = """
    INSERT INTO officers (service_ref, unit_id, rank, unit_role, full_name, duty_status) VALUES
      ('OFF-T-1', (SELECT id FROM org_units WHERE code='ST-004'), 'Sergeant', 'Desk', 'Sgt Desk One', 'Active'),
      ('OFF-T-2', (SELECT id FROM org_units WHERE code='ST-007'), 'Sergeant', 'Desk', 'Sgt Desk Two', 'Active'),
      ('OFF-T-3', (SELECT id FROM org_units WHERE code='ST-004'), 'Sergeant', 'Desk', 'Sgt Suspended', 'Suspended');
"""


def setUpModule():
    os.environ['SENTINEL_DB_ROLE'] = 'app_rw'
    uri = pg_support.create_database('sentinel_ops')
    c = psycopg2.connect(uri)
    cur = c.cursor()
    cur.execute("""
        -- DATA-ONLY expansion of the tree -----------------------------------------------------------------
        INSERT INTO org_units (parent_id, unit_type, code, name, status) VALUES
          ((SELECT id FROM org_units WHERE code='D-BUUHOODLE'), 'airport', 'AP-BUU',  'Buuhoodle Airport', 'active'),
          ((SELECT id FROM org_units WHERE code='D-OODWEYNE'),  'airport', 'AP-PLAN', 'Planned Airstrip',   'planned'),
          ((SELECT id FROM org_units WHERE code='HQ'),          'region',  'XREG',    'Unlisted Test Region', 'active');
        INSERT INTO org_units (parent_id, unit_type, code, name, status) VALUES
          ((SELECT id FROM org_units WHERE code='XREG'), 'district', 'D-X', 'X District', 'active');
        INSERT INTO org_units (parent_id, unit_type, code, name, status) VALUES
          ((SELECT id FROM org_units WHERE code='D-X'), 'airport', 'AP-X', 'X Airport', 'active'),
          ((SELECT id FROM org_units WHERE code='D-X'), 'station', 'ST-X', 'X Station', 'active');
        -- a role that may stop travelers but may NOT check alerts (must be refused: a silent 'clear' would be a lie)
        INSERT INTO roles (code, name) VALUES ('blind_checkpoint', 'Checkpoint without alert check');
        INSERT INTO role_permissions SELECT (SELECT id FROM roles WHERE code='blind_checkpoint'), p
          FROM unnest(ARRAY['person:search','person:create','checkpoint:view','checkpoint:create']) p;
        INSERT INTO users (username, display_name, password_hash) VALUES
          ('ap.buu','AP Buuhoodle','!t'), ('st.laas','Station Las Anod','!t'), ('st.buu','Station Buuhoodle','!t'),
          ('rc.sool','Sool commander','!t'), ('x.airport','X airport','!t'), ('x.station','X station','!t'),
          ('blind','No alert check','!t');
        CREATE FUNCTION pg_temp.asg(u text, r text, unit text, d boolean DEFAULT false) RETURNS void LANGUAGE sql AS $f$
          INSERT INTO user_assignments (user_id, role_id, unit_id, include_descendants)
          VALUES ((SELECT id FROM users WHERE username=u), (SELECT id FROM roles WHERE code=r),
                  (SELECT id FROM org_units WHERE code=unit), d) $f$;
        SELECT pg_temp.asg('ap.buu','airport_officer','AP-BUU'), pg_temp.asg('st.laas','station_officer','ST-004'),
               pg_temp.asg('st.buu','station_officer','ST-007'), pg_temp.asg('rc.sool','regional_commander','SOOL', true),
               pg_temp.asg('x.airport','airport_officer','AP-X'), pg_temp.asg('x.station','station_officer','ST-X'),
               pg_temp.asg('blind','blind_checkpoint','CP-SOUTH');
    """ + OFFICERS_SQL)
    c.commit()
    c.close()
    _state['uri'] = uri


def tearDownModule():
    os.environ.pop('SENTINEL_DB_ROLE', None)


def now_local(delta_hours=0):
    return (datetime.now(LOCAL_TZ) + timedelta(hours=delta_hours)).strftime('%Y-%m-%dT%H:%M')


class OpsCase(DbCase):
    @classmethod
    def setUpClass(cls):
        cls.uri = _state['uri']

    _keep_role = False          # True only while a test is deliberately querying AS a user under RLS

    def one(self, sql, params=None):
        if not self._keep_role:
            self.cur.execute('RESET ROLE')              # a service call leaves the transaction in app_rw
        return super().one(sql, params)

    def all(self, sql, params=None):
        if not self._keep_role:
            self.cur.execute('RESET ROLE')
        return super().all(sql, params)

    # ---- fixtures / helpers --------------------------------------------------------------------
    def as_db_user(self, username):
        """Raw SQL as this user under row-level security — what the API does on every request."""
        self._keep_role = False
        uid = self.uid(username)                        # (resets the role) — compute BEFORE dropping into it
        self.cur.execute("SELECT set_config('app.user_id', %s, true)", (str(uid),))
        self.cur.execute('SET ROLE app_rw')
        self._keep_role = True

    def upload(self, username, kind='png'):
        name = os.urandom(16).hex() + '.' + kind
        self.one("INSERT INTO uploads (name, content_type, size_bytes, uploaded_by) VALUES (%s, %s, 10, %s) RETURNING name",
                 (name, 'image/png' if kind == 'png' else 'application/pdf', self.uid(username)))
        return name

    def stop_payload(self, who='cp.south', unit='CP-SOUTH', **over):
        p = dict(unit=unit, traveler=dict(TRAV), purpose_of_visit='Family visit', current_address='Burao, Gacan Libaax',
                 traveler_photo=self.upload(who), traveler_docs=[self.upload(who, 'pdf')],
                 guardian=dict(GUARD), guardian_relationship='Uncle', guardian_docs=[self.upload(who, 'pdf')])
        p.update(over)
        return p

    def stop(self, who='cp.south', unit='CP-SOUTH', **over):
        return checkpoint.record_stop(self.conn, self.actor(who, unit), self.stop_payload(who, unit, **over))

    def pax_payload(self, **over):
        p = dict(unit='AP-LAA', passenger=dict(PAX), movement='Arrival', travel_date=date.today().isoformat(),
                 flight_number='fz 123', airline='flydubai', origin_city='Dubai')
        p.update(over)
        return p

    def pax(self, who='ap.officer', unit='AP-LAA', **over):
        return airport.record_passenger(self.conn, self.actor(who, unit), self.pax_payload(unit=unit, **over))

    def inc_payload(self, **over):
        p = dict(unit='ST-004', category='Theft/Burglary', incident_at=now_local(-2), location_of_occurrence='Central market',
                 description='Shop broken into overnight', severity='Medium', victim_full_name='Axmed Cali')
        p.update(over)
        return p

    def incident(self, who='st.laas', unit='ST-004', **over):
        return incidents.file_incident(self.conn, self.actor(who, unit), self.inc_payload(unit=unit, **over))

    def error(self, exc, fn, *a, **kw):
        with self.assertRaises(exc) as cm:
            fn(*a, **kw)
        return cm.exception


# =====================================================================================================
class TestDatabaseRules(OpsCase):
    """The guarantees that hold no matter which code path writes."""

    def _airport_row(self, unit, user='ap.officer', person=None, flight='FZ1', **kw):
        pid = person or self.raw_person(national_id=None)
        unit_id = self.unit(unit)
        self.as_db_user(user)
        return ("INSERT INTO airport_passengers (record_ref, unit_id, person_id, movement, travel_date, flight_number) "
                "VALUES (%s, %s, %s, 'Arrival', current_date, %s) RETURNING id",
                (f'AR-T-{os.urandom(3).hex()}', unit_id, pid, flight))

    def test_region_scope_comes_from_policy_data_not_code(self):
        sql, p = self._airport_row('AP-X', 'x.airport')
        self.assertEqual(self.fails(sql, p, code='23514').diag.message_primary.split(' records')[0], 'airport_passengers')
        # ...and the same insert is fine in a unit under an operational region:
        self.assertTrue(self.one('SELECT unit_in_operational_region(%s)', (self.unit('AP-BUU'),)))
        self.assertFalse(self.one('SELECT unit_in_operational_region(%s)', (self.unit('XREG'),)))
        self.assertFalse(self.one('SELECT unit_in_operational_region(%s)', (self.unit('DIR-FP'),)))

    def test_all_three_official_regions_are_in_scope_and_nothing_else_is(self):
        regions = self.all("""SELECT r.code FROM org_units r WHERE r.unit_type='region' AND unit_in_operational_region(r.id)
                              ORDER BY 1""")
        self.assertEqual([r[0] for r in regions], ['ETOG', 'SANAAG', 'SOOL'])

    def test_data_only_new_airport_works_in_its_district(self):
        """Buuhoodle Airport was added by INSERT only (fixtures).  It records passengers like any airport."""
        res = self.pax('ap.buu', 'AP-BUU')
        self.assertTrue(res['record']['record_ref'].startswith('AR-AP-BUU-'))
        self.assertEqual((res['record']['unit']['district'], res['record']['unit']['region']),
                         ('Buuhoodle', 'East Togdheer'))

    def test_a_planned_unit_takes_no_records_until_it_is_activated(self):
        self.one("SELECT 1")
        self.cur.execute("INSERT INTO user_assignments (user_id, role_id, unit_id) VALUES (%s, (SELECT id FROM roles WHERE code='airport_officer'), %s)",
                         (self.uid('ap.officer'), self.unit('AP-PLAN')))
        e = self.error(ValidationError, self.pax, 'ap.officer', 'AP-PLAN')
        self.assertIn('not active', e.message)
        self.cur.execute("UPDATE org_units SET status='active' WHERE code='AP-PLAN'")        # data-only activation
        self.assertEqual(self.pax('ap.officer', 'AP-PLAN')['record']['unit']['code'], 'AP-PLAN')

    def test_unit_type_is_enforced(self):
        sql, p = self._airport_row('ST-004')                       # a station is not an airport
        self.fails(sql, p, code='23514')

    def test_no_anonymous_writes_even_for_the_table_owner(self):
        pid = self.raw_person(national_id=None)
        self.cur.execute('RESET ROLE')
        self.cur.execute("SELECT set_config('app.user_id','',true)")
        self.fails("INSERT INTO airport_passengers (record_ref, unit_id, person_id, movement, travel_date, flight_number) "
                   "VALUES ('AR-T-ANON', %s, %s, 'Arrival', current_date, 'FZ1')", (self.unit('AP-LAA'), pid), code='42501')

    def test_created_by_cannot_be_forged(self):
        pid = self.raw_person(national_id=None)
        liar, laa = self.uid('admin'), self.unit('AP-LAA')
        self.as_db_user('ap.officer')
        rid = self.one("INSERT INTO airport_passengers (record_ref, unit_id, person_id, movement, travel_date, flight_number, created_by) "
                       "VALUES ('AR-T-FORGE', %s, %s, 'Arrival', current_date, 'FZ1', %s) RETURNING id",
                       (laa, pid, liar))
        self.assertEqual(self.one('SELECT created_by FROM airport_passengers WHERE id=%s', (rid,)), self.uid('ap.officer'))

    def test_checkpoint_and_airport_logs_are_append_only(self):
        self.stop()
        self.pax()
        for sql in ("UPDATE checkpoint_events SET notes='edited'", "DELETE FROM checkpoint_events",
                    "UPDATE airport_passengers SET flight_number='XX999'", "DELETE FROM airport_passengers"):
            self.cur.execute('RESET ROLE')
            self.fails(sql, code='42501')
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")             # explicit, deliberate bypass only
        self.cur.execute("UPDATE checkpoint_events SET notes='fixed by maintenance'")

    def test_an_incident_can_only_change_its_case_status(self):
        ref = self.incident()['incident']['file_number']
        self.cur.execute('RESET ROLE')
        self.fails("UPDATE crime_incidents SET description='rewritten' WHERE file_number=%s", (ref,), code='42501')
        self.fails("UPDATE crime_incidents SET unit_id=%s WHERE file_number=%s", (self.unit('ST-007'), ref), code='42501')
        self.fails("DELETE FROM crime_incidents WHERE file_number=%s", (ref,), code='42501')
        self.cur.execute("UPDATE crime_incidents SET case_status='Under Investigation' WHERE file_number=%s", (ref,))
        self.fails("UPDATE crime_incidents SET case_status='Made Up' WHERE file_number=%s", (ref,))   # vocabulary stays enforced on the table? (insert-time)

    def test_the_same_passenger_cannot_be_logged_twice_for_one_flight_and_day(self):
        self.pax()
        e = self.error(Duplicate, self.pax, flight_number='FZ 123')
        self.assertEqual(e.status, 409)

    def test_row_level_security_isolates_units(self):
        self.stop('cp.south', 'CP-SOUTH')
        self.pax('ap.officer', 'AP-LAA')
        self.as_db_user('cp.east')
        self.assertEqual(self.one('SELECT count(*) FROM checkpoint_events'), 0)              # other checkpoint: nothing
        self.as_db_user('cp.south')
        self.assertEqual(self.one('SELECT count(*) FROM checkpoint_events'), 1)
        self.assertEqual(self.one('SELECT count(*) FROM airport_passengers'), 0)             # checkpoint role: no airport data
        self.as_db_user('chief')
        self.assertEqual((self.one('SELECT count(*) FROM checkpoint_events'), self.one('SELECT count(*) FROM airport_passengers')), (1, 1))
        self.as_db_user('ap.buu')
        self.assertEqual(self.one('SELECT count(*) FROM airport_passengers'), 0)             # sister airport: nothing

    def test_rls_blocks_writing_into_a_unit_you_are_not_assigned_to(self):
        pid = self.raw_person(national_id=None)
        buu = self.unit('AP-BUU')
        self.as_db_user('ap.officer')                                                          # assigned to AP-LAA only
        self.fails("INSERT INTO airport_passengers (record_ref, unit_id, person_id, movement, travel_date, flight_number) "
                   "VALUES ('AR-T-X', %s, %s, 'Arrival', current_date, 'FZ1')", (buu, pid), code='42501')

    def test_a_victim_link_is_impossible_for_an_anonymous_victim(self):
        pid = self.raw_person(national_id=None)
        st = self.unit('ST-004')
        self.as_db_user('st.laas')
        self.fails("INSERT INTO crime_incidents (file_number, unit_id, category, incident_at, description, details, victim_person_id) "
                   "VALUES ('CRM-T-1', %s, 'Assault', now() - interval '1 hour', 'x', '{\"victim_anonymous\": true}', %s)",
                   (st, pid), code='23514')

    def test_alert_details_stay_hidden_from_a_checkpoint_officer(self):
        pid = self.raw_person(national_id=None)
        self.cur.execute('RESET ROLE')
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute("INSERT INTO suspect_alerts (alert_ref, person_id) VALUES ('AL-T-1', %s)", (pid,))
        self.as_db_user('cp.south')
        self.assertEqual(self.one('SELECT count(*) FROM suspect_alerts'), 0)                  # cannot read the alert...
        self.assertTrue(self.one('SELECT person_alert_flag(%s, %s)', (self.uid('cp.south'), pid)))   # ...only learn yes/no


# =====================================================================================================
class TestCheckpoint(OpsCase):

    def test_a_stop_registers_a_new_traveler_links_the_guardian_and_files_the_event(self):
        r = self.stop()
        self.assertTrue(r['identity']['created'])
        ev = r['event']
        self.assertRegex(ev['event_ref'], r'^CP-CP-SOUTH-\d{4}-000001$')
        self.assertEqual((ev['screening_result'], ev['action_taken'], ev['alerted']), ('No active alert', 'Cleared', False))
        self.assertEqual((ev['unit']['code'], ev['unit']['district'], ev['unit']['region']), ('CP-SOUTH', 'Laascaanood', 'Sool'))
        self.assertEqual(r['guardian']['relationship'], 'Uncle')
        self.assertEqual(self.one('SELECT count(*) FROM person_guardians'), 1)
        self.assertEqual(self.one("SELECT count(*) FROM persons"), 2)                           # traveler + guardian, once each
        # the photo became the person's (dynamic) profile photo; the unit that first met them is stamped
        self.assertTrue(self.one("SELECT photo_path FROM persons WHERE person_ref=%s", (r['person']['person_ref'],)))
        self.assertEqual(self.one("SELECT u.code FROM persons p JOIN org_units u ON u.id=p.created_in_unit_id WHERE p.person_ref=%s",
                                  (r['person']['person_ref'],)), 'CP-SOUTH')
        self.assertEqual(self.one("SELECT count(*) FROM audit_events WHERE action='CHECKPOINT_STOP'"), 1)

    def test_every_legacy_requirement_is_still_enforced(self):
        e = self.error(ValidationError, checkpoint.record_stop, self.conn, self.actor('cp.south', 'CP-SOUTH'),
                       dict(unit='CP-SOUTH', traveler={**TRAV, 'date_of_birth': ''}))
        for f in ('purpose_of_visit', 'current_address', 'traveler_photo', 'traveler_docs', 'guardian', 'guardian_relationship',
                  'guardian_phone', 'guardian_address', 'guardian_occupation', 'guardian_docs', 'date_of_birth'):
            self.assertIn(f, e.extra['fields'], f)

    def test_files_must_be_the_uploaders_own(self):
        theirs = self.upload('cp.east')
        e = self.error(ValidationError, self.stop, traveler_photo=theirs)
        self.assertIn('not uploaded by you', e.message)

    def test_officer_can_only_record_at_their_own_checkpoint(self):
        self.error(PermissionDenied, self.stop, 'cp.south', 'CP-EAST')
        self.assertEqual(self.stop('cp.east', 'CP-EAST')['event']['unit']['code'], 'CP-EAST')
        self.error(PermissionDenied, self.stop, 'ap.officer', 'CP-SOUTH')                      # wrong kind of officer
        self.error(PermissionDenied, self.stop, 'chief', 'CP-SOUTH')                           # read-only commander

    def test_a_unit_that_is_not_a_checkpoint_or_is_unknown_is_refused(self):
        self.error(ValidationError, self.stop, 'admin', 'ST-004')                              # admin has no checkpoint:create anyway
        e = self.error((ValidationError, PermissionDenied), self.stop, 'cp.south', 'NOPE')
        self.assertEqual(e.status, 422)

    def test_the_same_traveler_at_another_checkpoint_is_one_person_with_two_events(self):
        a = self.stop('cp.south', 'CP-SOUTH')
        b = self.stop('cp.east', 'CP-EAST', guardian_person_ref=None)
        self.assertEqual(a['person']['person_ref'], b['person']['person_ref'])
        self.assertTrue(b['identity']['exists'] and not b['identity']['created'])
        self.assertEqual(self.one("SELECT count(*) FROM persons"), 2)
        self.assertEqual(self.one("SELECT count(*) FROM checkpoint_events"), 2)
        # each checkpoint sees only its own stop in the person's history; the Chief Commander sees both
        ref = a['person']['person_ref']
        kinds = lambda who: [(e['unit_code'], e['kind']) for e in timeline.person_timeline(self.conn, self.actor(who), ref)['events']]
        self.assertEqual(kinds('cp.east'), [('CP-EAST', 'checkpoint')])
        self.assertEqual(sorted(kinds('chief')), [('CP-EAST', 'checkpoint'), ('CP-SOUTH', 'checkpoint')])

    def test_an_active_alert_flags_the_stop_without_revealing_it(self):
        pid = self.raw_person(name='Faadumo Jaamac Warsame Ismaaciil', dob='1992-03-04', pob='Burao', national_id='SO7001')
        self.cur.execute('RESET ROLE')
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute("INSERT INTO suspect_alerts (alert_ref, person_id) VALUES ('AL-T-9', %s)", (pid,))
        r = self.stop()
        self.assertEqual((r['event']['screening_result'], r['event']['action_taken'], r['event']['alerted']),
                         ('Flagged match', 'Supervisor contacted', True))
        self.assertNotIn('alert_ref', json.dumps(r, default=str))

    def test_a_user_who_cannot_check_alerts_cannot_record_a_stop(self):
        e = self.error(PermissionDenied, self.stop, 'blind', 'CP-SOUTH')
        self.assertIn('screen', e.message)

    def test_similar_name_needs_confirmation_and_names_who_is_ambiguous(self):
        registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), dict(TRAV))
        e = self.error(NeedsConfirmation, self.stop, traveler={**TRAV, 'national_id': None, 'passport_id': None,
                                                              'second_name': 'Jaamaca'})
        self.assertEqual(e.extra['scope'], 'traveler')
        self.assertTrue(e.extra['search']['candidates'])

    def test_a_possible_duplicate_can_be_linked_or_confirmed_as_new(self):
        first = registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), dict(TRAV))['person']['person_ref']
        variant = {**TRAV, 'national_id': None, 'second_name': 'Jaamaca'}
        linked = self.stop(traveler=variant, link_person_ref=first)
        self.assertEqual(linked['person']['person_ref'], first)
        other = self.stop('cp.east', 'CP-EAST', traveler={**variant, 'national_id': None}, confirm_new=True)
        self.assertNotEqual(other['person']['person_ref'], first)

    def test_guardian_rule_is_policy_data(self):
        self.cur.execute("""UPDATE policy_settings SET value='{"photo": true, "traveler_docs": 1, "guardian": "minors", "guardian_docs": 1}'
                            WHERE key='checkpoint.required'""")
        adult = self.stop(guardian=None, guardian_relationship=None, guardian_docs=[])
        self.assertIsNone(adult['guardian'])
        minor = {**TRAV, 'national_id': 'SO7500', 'first_name': 'Sahra', 'second_name': 'Nuur', 'third_name': 'Cabdi',
                 'fourth_name': 'Aadan', 'date_of_birth': (date.today() - timedelta(days=365 * 9)).isoformat()}
        e = self.error(ValidationError, self.stop, traveler=minor, guardian=None, guardian_relationship=None, guardian_docs=[])
        self.assertIn('guardian', e.extra['fields'])

    def test_a_failed_stop_leaves_nothing_behind(self):
        self.cur.execute('SAVEPOINT s')
        with self.assertRaises(ValidationError):
            self.stop(purpose_of_visit='')
        self.assertEqual(self.one('SELECT count(*) FROM persons'), 0)

    def test_list_is_scoped_to_what_the_viewer_may_see(self):
        self.stop('cp.south', 'CP-SOUTH'); self.stop('cp.east', 'CP-EAST')
        mine = checkpoint.list_stops(self.conn, self.actor('cp.south'))['items']
        self.assertEqual([i['unit_code'] for i in mine], ['CP-SOUTH'])
        self.assertEqual(len(checkpoint.list_stops(self.conn, self.actor('chief'))['items']), 2)
        self.assertEqual(checkpoint.list_stops(self.conn, self.actor('ap.officer'))['items'], [])


# =====================================================================================================
class TestAirport(OpsCase):

    def test_arrival_is_logged_against_one_registry_person(self):
        r = self.pax()
        self.assertTrue(r['identity']['created'])
        rec = r['record']
        self.assertRegex(rec['record_ref'], r'^AR-AP-LAA-\d{4}-000001$')
        self.assertEqual((rec['movement'], rec['flight_number'], rec['route']), ('Arrival', 'FZ123', 'Dubai'))
        self.assertFalse(r['has_active_alert'])

    def test_a_person_already_known_to_another_unit_is_linked_not_duplicated(self):
        known = registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), {**PAX, 'mother_name': 'Faduma Aadan'})
        r = self.pax()
        self.assertTrue(r['identity']['exists'] and not r['identity']['created'])
        self.assertEqual(r['person']['person_ref'], known['person']['person_ref'])
        self.assertEqual(self.one('SELECT count(*) FROM persons'), 1)

    def test_passenger_locked_fields_are_not_overwritten_by_the_desk(self):
        known = registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), dict(PAX))
        r = self.pax(passenger={**PAX, 'place_of_birth': 'Hargeysa-Typo', 'occupation': 'Pilot'})
        self.assertIn('place_of_birth', [i['field'] for i in r['identity']['ignored']])
        self.assertEqual(self.one('SELECT place_of_birth FROM persons WHERE person_ref=%s', (known['person']['person_ref'],)), 'Burao')
        self.assertEqual(self.one('SELECT occupation FROM persons WHERE person_ref=%s', (known['person']['person_ref'],)), 'Pilot')

    def test_passport_or_national_id_is_required_as_in_the_legacy_flow(self):
        e = self.error(ValidationError, self.pax, passenger={**PAX, 'national_id': None})
        self.assertTrue(e.extra['fields'])

    def test_validation_the_legacy_handler_never_had(self):
        e = self.error(ValidationError, self.pax, movement='Teleport', flight_number='', travel_date='not-a-date')
        self.assertEqual(sorted(e.extra['fields']), ['flight_number', 'movement', 'travel_date'])
        far = (date.today() + timedelta(days=90)).isoformat()
        self.assertIn('travel_date', self.error(ValidationError, self.pax, travel_date=far).extra['fields'])
        self.assertIn('origin_city', self.error(ValidationError, self.pax, origin_city='').extra['fields'])
        self.assertIn('destination_city', self.error(ValidationError, self.pax, movement='Departure').extra['fields'])

    def test_movement_is_case_insensitive_and_departure_needs_a_destination(self):
        r = self.pax(movement='departure', origin_city=None, destination_city='Nairobi', flight_number='kq 7')
        self.assertEqual((r['record']['movement'], r['record']['flight_number'], r['record']['route']),
                         ('Departure', 'KQ7', 'Nairobi'))

    def test_only_an_airport_officer_at_that_airport_can_log(self):
        self.error(PermissionDenied, self.pax, 'ap.officer', 'AP-BUU')                         # AP-LAA officer, other airport
        self.error(PermissionDenied, self.pax, 'cp.south', 'AP-LAA')
        self.error(PermissionDenied, self.pax, 'chief', 'AP-LAA')

    def test_same_person_arrives_in_laascaanood_and_departs_from_buuhoodle_as_one_person(self):
        a = self.pax('ap.officer', 'AP-LAA')
        d = self.pax('ap.buu', 'AP-BUU', movement='Departure', origin_city=None, destination_city='Dubai', flight_number='FZ9')
        self.assertEqual(a['person']['person_ref'], d['person']['person_ref'])
        ref = a['person']['person_ref']
        t = timeline.person_timeline(self.conn, self.actor('chief'), ref)['events']
        self.assertEqual(sorted(e['unit_code'] for e in t), ['AP-BUU', 'AP-LAA'])
        sool = timeline.person_timeline(self.conn, self.actor('rc.sool'), ref)['events']      # regional view: Sool only
        self.assertEqual([e['unit_code'] for e in sool], ['AP-LAA'])

    def test_listing_filters_and_scope(self):
        self.pax(); self.pax('ap.buu', 'AP-BUU')
        self.assertEqual(len(airport.list_passengers(self.conn, self.actor('ap.officer'))['items']), 1)
        self.assertEqual(len(airport.list_passengers(self.conn, self.actor('chief'))['items']), 2)
        self.assertEqual(len(airport.list_passengers(self.conn, self.actor('chief'), unit='AP-BUU')['items']), 1)
        self.assertEqual(airport.list_passengers(self.conn, self.actor('chief'), movement='departure')['items'], [])


# =====================================================================================================
class TestIncidents(OpsCase):

    def test_a_station_files_an_incident(self):
        r = self.incident(officer_ref='OFF-T-1')['incident']
        self.assertRegex(r['file_number'], r'^CRM-ST-004-\d{4}-000001$')
        self.assertEqual((r['category'], r['case_status'], r['unit']['district']), ('Theft/Burglary', 'Reported / Open', 'Laascaanood'))
        self.assertEqual(r['desk_officer']['full_name'], 'Sgt Desk One')
        self.assertEqual(self.one("SELECT count(*) FROM audit_events WHERE action='INCIDENT_FILED'"), 1)

    def test_a_known_victim_is_linked_to_the_registry_but_an_unknown_one_is_never_created(self):
        known = registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), dict(PAX))['person']['person_ref']
        before = self.one('SELECT count(*) FROM persons')
        linked = self.incident(victim_national_id=' so 8001 ')['incident']
        self.assertEqual(linked['victim_person_ref'], known)
        stranger = self.incident(victim_national_id='SO999999')['incident']
        self.assertIsNone(stranger['victim_person_ref'])
        self.assertEqual(self.one('SELECT count(*) FROM persons'), before)                      # nobody registered as a side-effect

    def test_a_fuzzy_name_never_links_a_victim(self):
        registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), dict(PAX))
        r = self.incident(victim_full_name='Cabdi Rashiid Maxamuud Jaamac')['incident']        # exact name, but no ID given
        self.assertIsNone(r['victim_person_ref'])

    def test_an_anonymous_victim_keeps_no_identity(self):
        registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), dict(PAX))
        r = self.incident(victim_anonymous=True, victim_full_name='Secret Person', victim_national_id='SO8001',
                          victim_contact='+252 1')['incident']
        self.assertTrue(r['victim_anonymous'] and r['victim_person_ref'] is None)
        details = self.one('SELECT details FROM crime_incidents WHERE file_number=%s', (r['file_number'],))
        self.assertIsNone(details['victim'])
        self.assertNotIn('Secret', json.dumps(details))

    def test_explicit_victim_pick_from_the_search_box(self):
        known = registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), dict(PAX))['person']['person_ref']
        self.assertEqual(self.incident(victim_person_ref=known, victim_full_name='x')['incident']['victim_person_ref'], known)
        self.assertIn('victim_person_ref', self.error(ValidationError, self.incident, victim_person_ref='P-2026-999999').extra['fields'])

    def test_legacy_validation(self):
        e = self.error(ValidationError, self.incident, category='Pickpocketing', description='', location_of_occurrence='',
                       incident_at='', severity='Apocalyptic', reporting_party_type='Dog', victim_gender='?',
                       evidence1_file='x.png', evidence1_type='')
        for f in ('category', 'description', 'location_of_occurrence', 'incident_at', 'severity', 'reporting_party_type', 'victim_gender'):
            self.assertIn(f, e.extra['fields'], f)
        self.assertIn('victim_age', self.error(ValidationError, self.incident, victim_age='abc').extra['fields'])
        self.assertIn('incident_at', self.error(ValidationError, self.incident, incident_at=now_local(+5)).extra['fields'])

    def test_category_is_case_insensitive_and_vocabulary_is_policy_data(self):
        self.assertEqual(self.incident(category='assault')['incident']['category'], 'Assault')
        self.cur.execute("""UPDATE policy_settings SET value = value || '["Smuggling"]'::jsonb WHERE key='incident.categories'""")
        self.assertEqual(self.incident(category='smuggling')['incident']['category'], 'Smuggling')   # no code change

    def test_desk_officer_must_be_active_and_posted_here(self):
        for ref in ('OFF-T-2', 'OFF-T-3', 'NOBODY'):
            self.assertIn('officer_ref', self.error(ValidationError, self.incident, officer_ref=ref).extra['fields'], ref)

    def test_incident_time_is_the_officers_wall_clock_in_mogadishu(self):
        r = self.incident(incident_at='2026-01-15T09:30')['incident']
        self.assertEqual(r['incident_at'].utcoffset(), timedelta(hours=3))
        self.assertEqual(r['incident_at'].hour, 9)

    def test_only_a_station_officer_of_that_station_may_file(self):
        self.error(PermissionDenied, self.incident, 'st.buu', 'ST-004')
        self.error(PermissionDenied, self.incident, 'ap.officer', 'ST-004')                     # airport role: no incident:create
        self.error(PermissionDenied, self.incident, 'chief', 'ST-004')
        self.error(PermissionDenied, self.incident, 'rc.sool', 'ST-004')                        # commanders view, they do not file
        self.assertEqual(self.incident('st.buu', 'ST-007')['incident']['unit']['region'], 'East Togdheer')

    def test_a_unit_outside_the_operational_regions_is_refused(self):
        e = self.error(PermissionDenied, self.incident, 'st.laas', 'ST-X')                      # not their unit
        e = self.error(ValidationError, self.incident, 'x.station', 'ST-X')                      # theirs, but unlisted region
        self.assertIn('outside the operational regions', e.message)

    def test_listing_follows_the_command_chain(self):
        self.incident('st.laas', 'ST-004'); self.incident('st.buu', 'ST-007')
        mine = incidents.list_incidents(self.conn, self.actor('st.laas'))['items']
        self.assertEqual([i['unit_code'] for i in mine], ['ST-004'])
        self.assertEqual([i['unit_code'] for i in incidents.list_incidents(self.conn, self.actor('rc.sool'))['items']], ['ST-004'])
        self.assertEqual(len(incidents.list_incidents(self.conn, self.actor('chief'))['items']), 2)
        self.assertEqual(incidents.list_incidents(self.conn, self.actor('cp.south'))['items'], [])

    def test_an_incident_never_appears_in_a_persons_registry_timeline(self):
        known = registry.register(self.conn, self.actor('fp.officer', 'DIR-FP'), dict(PAX))['person']['person_ref']
        self.incident(victim_national_id='SO8001')
        self.assertEqual(timeline.person_timeline(self.conn, self.actor('chief'), known)['events'], [])


# =====================================================================================================
class TestUploadsAndUnits(OpsCase):

    def test_store_validates_type_size_and_content(self):
        a = self.actor('cp.south', 'CP-SOUTH')
        ok = uploads.store(self.conn, a, 'Photo.PNG', PNG)
        self.assertRegex(ok['name'], uploads.NAME_RE)
        for name, data in (('evil.exe', b'MZ'), ('fake.pdf', PNG), ('empty.png', b''), ('big.png', PNG + b'0' * uploads.MAX_BYTES)):
            self.error(ValidationError, uploads.store, self.conn, a, name, data)
        self.error(PermissionDenied, uploads.store, self.conn, self.actor('chief'), 'a.png', PNG)

    def test_file_access_follows_record_access(self):
        a = self.actor('cp.south', 'CP-SOUTH')
        r = self.stop()
        name = self.one('SELECT photo_path FROM persons WHERE person_ref=%s', (r['person']['person_ref'],))
        self.assertTrue(uploads.store.__name__)
        self.cur.execute('RESET ROLE')
        self.assertTrue(self.one('SELECT can_view_upload(%s, %s)', (self.uid('cp.south'), name)))          # uploader
        self.assertTrue(self.one('SELECT can_view_upload(%s, %s)', (self.uid('chief'), name)))             # may view the stop
        self.assertTrue(self.one('SELECT can_view_upload(%s, %s)', (self.uid('ap.officer'), name)))        # profile photo: any searcher
        doc = r['event'] and self.one("SELECT details->'traveler_docs'->>0 FROM checkpoint_events")
        self.assertFalse(self.one('SELECT can_view_upload(%s, %s)', (self.uid('cp.east'), doc)))          # other checkpoint: no
        self.assertFalse(self.one('SELECT can_view_upload(%s, %s)', (self.uid('ap.officer'), doc)))

    def test_open_file_hides_existence_from_those_who_may_not_see_it(self):
        name = uploads.store(self.conn, self.actor('cp.south', 'CP-SOUTH'), 'a.pdf', b'%PDF-1.4 x')['name']
        data, ctype = uploads.open_file(self.conn, self.actor('cp.south'), name)
        self.assertEqual((data[:5], ctype), (b'%PDF-', 'application/pdf'))
        self.error(NotFound, uploads.open_file, self.conn, self.actor('cp.east'), name)
        self.error(NotFound, uploads.open_file, self.conn, self.actor('cp.east'), '../../etc/passwd')

    def test_unit_pickers_are_built_from_the_tree_and_each_users_rights(self):
        u = units.operational_units(self.conn, self.actor('ap.buu'))
        self.assertEqual([(x['code'], x['can_create']) for x in u['airport']], [('AP-BUU', True)])
        self.assertEqual((u['checkpoint'], u['station']), ([], []))
        self.assertEqual([x['code'] for x in units.operational_units(self.conn, self.actor('cp.east'))['checkpoint']], ['CP-EAST'])
        c = units.operational_units(self.conn, self.actor('chief'))
        self.assertEqual(sorted(x['code'] for x in c['airport']), ['AP-BUU', 'AP-LAA', 'AP-PLAN'])
        self.assertFalse(any(x['can_create'] for k in c.values() for x in k))                # read-only commander
        self.assertNotIn('AP-X', [x['code'] for x in c['airport']])                          # outside the official regions
        self.assertEqual([x['code'] for x in units.operational_units(self.conn, self.actor('x.airport'))['airport']], [])
        regional = units.operational_units(self.conn, self.actor('rc.sool'))
        self.assertEqual(sorted(x['code'] for x in regional['checkpoint']), ['CP-EAST', 'CP-SOUTH', 'CP-WEST'])
        self.assertNotIn('AP-BUU', [x['code'] for x in regional['airport']])


# =====================================================================================================
class TestHttpOperations(OpsCase):

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['SENTINEL_DATABASE_URL'] = cls.uri
        os.environ['SENTINEL_DEV_AUTH'] = '1'
        os.environ['SENTINEL_UPLOAD_DIR'] = os.path.join(pg_support.ROOT, 'tests', '_uploads_tmp')
        cls.srv = server.make_server('127.0.0.1', 0)
        cls.base = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        threading.Thread(target=cls.srv.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown(); cls.srv.server_close()
        import shutil
        shutil.rmtree(os.environ.pop('SENTINEL_UPLOAD_DIR'), ignore_errors=True)

    def setUp(self):
        super().setUp()
        self.clean()

    def tearDown(self):
        self.clean()
        super().tearDown()

    def clean(self):
        self.conn.rollback()
        self.cur.execute('RESET ROLE')
        self.cur.execute('TRUNCATE persons, ref_sequences, audit_events, uploads RESTART IDENTITY CASCADE')
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute('DELETE FROM officers')                      # CASCADE reached them through officers.person_id
        self.cur.execute(OFFICERS_SQL)
        self.conn.commit()

    def call(self, method, path, body=None, user='cp.south', unit=None, raw=None, headers=None):
        h = {'Content-Type': 'application/json', **(headers or {})}
        if user:
            h['X-Dev-User'] = user
        if unit:
            h['X-Unit'] = unit
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(self.base + path, method=method, headers=h, data=data)
        try:
            with urllib.request.urlopen(req) as r:
                b = r.read()
                return r.status, (json.loads(b) if r.headers['Content-Type'].startswith('application/json') else b)
        except urllib.error.HTTPError as e:
            b = e.read()
            return e.code, (json.loads(b) if b[:1] == b'{' else b)

    def put_file(self, user, name='photo.png', data=PNG):
        s, b = self.call('POST', '/api/uploads', user=user, raw=data, headers={'X-Filename': name, 'Content-Type': 'application/octet-stream'})
        self.assertEqual(s, 201, b)
        return b['name']

    def http_stop(self, user='cp.south', unit='CP-SOUTH', **over):
        body = dict(unit=unit, traveler=dict(TRAV), purpose_of_visit='Trade', current_address='Burao',
                    traveler_photo=self.put_file(user), traveler_docs=[self.put_file(user, 'id.pdf', b'%PDF-1.4 x')],
                    guardian=dict(GUARD), guardian_relationship='Uncle', guardian_docs=[self.put_file(user, 'g.pdf', b'%PDF-1.4 y')])
        body.update(over)
        return self.call('POST', '/api/checkpoint-events', body, user)

    def test_requires_authentication(self):
        for path in ('/api/checkpoint-events', '/api/airport-records', '/api/crimes', '/api/operations/units'):
            self.assertEqual(self.call('GET', path, user=None)[0], 401, path)

    def test_checkpoint_stop_end_to_end_and_the_file_ACL(self):
        s, b = self.http_stop()
        self.assertEqual(s, 201, b)
        self.assertEqual(b['event']['screening_result'], 'No active alert')
        s, lst = self.call('GET', '/api/checkpoint-events')
        self.assertEqual([i['event_ref'] for i in lst['items']], [b['event']['event_ref']])
        doc = lst['items'][0]['details']['traveler_docs'][0]
        self.assertEqual(self.call('GET', '/api/uploads/' + doc)[0], 200)                               # uploader / viewer
        self.assertEqual(self.call('GET', '/api/uploads/' + doc, user='chief')[0], 200)
        self.assertEqual(self.call('GET', '/api/uploads/' + doc, user='cp.east')[0], 404)               # other checkpoint
        self.assertEqual(self.call('GET', '/api/uploads/' + doc, user='ap.officer')[0], 404)
        s, f = self.call('GET', '/api/uploads/' + doc)
        self.assertEqual(f[:5], b'%PDF-')

    def test_http_status_codes(self):
        self.assertEqual(self.http_stop('cp.south', 'CP-EAST')[0], 403)                                 # not your checkpoint
        s, b = self.http_stop(purpose_of_visit='')
        self.assertEqual((s, b['error']), (422, 'validation_error'))
        self.assertIn('purpose_of_visit', b['fields'])
        s, b = self.call('POST', '/api/uploads', user='cp.south', raw=b'MZ\x90', headers={'X-Filename': 'a.pdf'})
        self.assertEqual(s, 422)
        s, b = self.call('POST', '/api/uploads', user='chief', raw=PNG, headers={'X-Filename': 'a.png'})
        self.assertEqual(s, 403)
        self.assertEqual(self.call('GET', '/api/uploads/' + 'a' * 32 + '.png')[0], 404)

    def test_possible_duplicate_is_a_409_naming_the_ambiguous_party(self):
        self.call('POST', '/api/persons', {'person': dict(TRAV)}, 'fp.officer', 'DIR-FP')
        s, b = self.http_stop(traveler={**TRAV, 'national_id': None, 'second_name': 'Jaamaca'})
        self.assertEqual((s, b['error'], b['scope']), (409, 'possible_duplicate', 'traveler'))
        self.assertTrue(b['search']['candidates'])

    def test_airport_end_to_end_with_the_data_only_airport(self):
        body = dict(unit='AP-BUU', passenger=dict(PAX), movement='Departure', travel_date=date.today().isoformat(),
                    flight_number='FZ 55', destination_city='Dubai')
        s, b = self.call('POST', '/api/airport-records', body, 'ap.buu')
        self.assertEqual(s, 201, b)
        self.assertEqual((b['record']['unit']['name'], b['record']['unit']['district']), ('Buuhoodle Airport', 'Buuhoodle'))
        s, b2 = self.call('POST', '/api/airport-records', body, 'ap.buu')
        self.assertEqual((s, b2['error']), (409, 'duplicate_record'))
        self.assertEqual(self.call('POST', '/api/airport-records', {**body, 'unit': 'AP-LAA'}, 'ap.buu')[0], 403)
        s, lst = self.call('GET', '/api/airport-records?movement=Departure', user='chief')
        self.assertEqual(len(lst['items']), 1)
        s, tl = self.call('GET', '/api/persons/' + b['person']['person_ref'] + '/timeline', user='chief')
        self.assertEqual([e['kind'] for e in tl['events']], ['airport'])

    def test_incident_end_to_end(self):
        body = self.inc_payload()
        s, b = self.call('POST', '/api/crimes', body, 'st.laas')
        self.assertEqual(s, 201, b)
        self.assertEqual(self.call('POST', '/api/crimes', body, 'ap.officer')[0], 403)
        self.assertEqual(self.call('POST', '/api/crimes', {**body, 'category': 'Nope'}, 'st.laas')[0], 422)
        s, lst = self.call('GET', '/api/crimes', user='rc.sool')
        self.assertEqual([i['file_number'] for i in lst['items']], [b['incident']['file_number']])
        self.assertEqual(self.call('GET', '/api/crimes', user='st.buu')[1]['items'], [])

    def test_vocabularies_are_policy_data(self):
        s, b = self.call('GET', '/api/operations/vocabularies', user='st.laas')
        self.assertIn('Assault', b['incident']['categories'])
        self.assertEqual(b['checkpoint']['guardian'], 'all')
        self.assertEqual(b['airport'], {'past': 60, 'future': 7})

    def test_operations_units_endpoint(self):
        s, b = self.call('GET', '/api/operations/units', user='ap.buu')
        self.assertEqual([(u['code'], u['district']) for u in b['airport']], [('AP-BUU', 'Buuhoodle')])


if __name__ == '__main__':
    unittest.main()

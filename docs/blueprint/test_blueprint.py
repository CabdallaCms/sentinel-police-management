#!/usr/bin/env python3
"""Executable acceptance tests for the Sentinel unified schema (Migration 001).

Applies every migration in migrations/ (001 base schema, 002 person identity) plus the dev seeds to a
scratch database and asserts the invariants the unified codebase must preserve: tree
integrity, code-free expansion, the unified scope check, root-level read-only
oversight, national-service ownership, conduct filing rules, and row-level security.

Run against any PostgreSQL 14+ you can create a database on:

    BLUEPRINT_PG_URI=postgresql://user:pass@host/postgres python3 docs/blueprint/test_blueprint.py

or, with no server available, `pip install pgserver psycopg2-binary` and run it bare
(an embedded PostgreSQL is started in a temp dir).
"""
import contextlib
import glob
import os
import sys
import tempfile
import unittest

import psycopg2
import psycopg2.errors as pgerr

HERE = os.path.dirname(os.path.abspath(__file__))
MIGRATIONS = os.path.join(HERE, '..', '..', 'migrations')
# Every numbered migration in order, then the dev-only seed data (demo accounts, demo persons).
SQL_FILES = (sorted(glob.glob(os.path.join(MIGRATIONS, '[0-9]*.sql')))
             + sorted(glob.glob(os.path.join(MIGRATIONS, 'dev', '*_demo_accounts.sql'))))
DBNAME = 'sentinel_blueprint_test'
_server = None
_admin_uri = None


def admin_uri():
    global _server, _admin_uri
    if _admin_uri:
        return _admin_uri
    _admin_uri = os.environ.get('BLUEPRINT_PG_URI')
    if not _admin_uri:
        import pgserver  # embedded PostgreSQL fallback
        _server = pgserver.get_server(tempfile.mkdtemp(prefix='sentinel_pg_'), cleanup_mode='stop')
        _admin_uri = _server.get_uri()
    return _admin_uri


def db_uri():
    uri = admin_uri()
    if '?' in uri:                       # unix-socket form: ...?host=/path
        base, q = uri.split('?', 1)
        return base.rsplit('/', 1)[0] + '/' + DBNAME + '?' + q
    return uri.rsplit('/', 1)[0] + '/' + DBNAME


def setUpModule():
    c = psycopg2.connect(admin_uri())
    c.autocommit = True
    cur = c.cursor()
    cur.execute(f'DROP DATABASE IF EXISTS {DBNAME}')
    cur.execute(f'CREATE DATABASE {DBNAME}')
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname='app_rw'")
    if not cur.fetchone():
        cur.execute('CREATE ROLE app_rw NOLOGIN')
    c.close()
    c = psycopg2.connect(db_uri())
    cur = c.cursor()
    for f in SQL_FILES:                  # one session, one transaction (the files use pg_temp helpers)
        with open(f) as fh:
            cur.execute(fh.read())
    cur.execute('GRANT USAGE ON SCHEMA public TO app_rw')
    cur.execute('GRANT ALL ON ALL TABLES IN SCHEMA public TO app_rw')
    c.commit()
    c.close()


class Base(unittest.TestCase):
    def setUp(self):
        self.conn = psycopg2.connect(db_uri())
        self.cur = self.conn.cursor()

    def tearDown(self):
        self.conn.rollback()
        self.conn.close()

    # ---- helpers ---------------------------------------------------------
    def one(self, sql, params=None):
        self.cur.execute(sql, params)
        row = self.cur.fetchone()
        return row[0] if row else None

    def all(self, sql, params=None):
        self.cur.execute(sql, params)
        return self.cur.fetchall()

    def uid(self, username):
        return self.one('SELECT id FROM users WHERE username=%s', (username,))

    def unit(self, code):
        return self.one('SELECT id FROM org_units WHERE code=%s', (code,))

    def role(self, code):
        return self.one('SELECT id FROM roles WHERE code=%s', (code,))

    def new_user(self, username, role, unit, descendants=True, **assign):
        u = self.one("INSERT INTO users(username,display_name,password_hash) VALUES(%s,%s,'!t') RETURNING id",
                     (username, username))
        self.cur.execute(
            'INSERT INTO user_assignments(user_id,role_id,unit_id,include_descendants,valid_until,revoked_at) '
            'VALUES(%s,%s,%s,%s,%s,%s)',
            (u, self.role(role), self.unit(unit), descendants, assign.get('valid_until'), assign.get('revoked_at')))
        return u

    def person(self, name='Test Person', **kw):
        # fixtures are written without an authenticated user -> explicit, transaction-local opt-in
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        ref = self.one("SELECT next_ref('P')")
        return self.one('INSERT INTO persons(person_ref,full_name) VALUES(%s,%s) RETURNING id', (ref, name))

    def cp_event(self, unit_code, person):
        return self.one(
            "INSERT INTO checkpoint_events(event_ref,unit_id,person_id,screening_result) "
            "VALUES(%s,%s,%s,'No active alert') RETURNING id",
            (self.one("SELECT next_ref('CP',%s)", (unit_code,)), self.unit(unit_code), person))

    def fails(self, sql, params=None):
        """Run a statement that MUST raise; keeps the transaction usable."""
        self.cur.execute('SAVEPOINT chk')
        try:
            self.cur.execute(sql, params)
        except psycopg2.Error as e:
            self.cur.execute('ROLLBACK TO SAVEPOINT chk')
            return e
        self.cur.execute('RELEASE SAVEPOINT chk')
        self.fail('statement should have failed: ' + sql[:90])

    @contextlib.contextmanager
    def as_user(self, username_or_id):
        uid = username_or_id if isinstance(username_or_id, int) else self.uid(username_or_id)
        self.cur.execute('SET LOCAL ROLE app_rw')
        self.cur.execute("SELECT set_config('app.user_id', %s, true)", (str(uid),))
        try:
            yield uid
        finally:
            self.cur.execute('RESET ROLE')

    def can(self, user, perm, unit_code):
        return self.one('SELECT authz_can(%s,%s,%s)', (user, perm, self.unit(unit_code)))


# =============================================================================
class TestTree(Base):
    def test_single_root_and_structure_rules(self):
        self.assertEqual(self.one("SELECT count(*) FROM org_units WHERE parent_id IS NULL"), 1)
        self.assertIn(('001', 'initial_schema'), self.all("SELECT version, name FROM schema_migrations"))
        hq = self.unit('HQ')
        # official regional scope: the regions under HQ are exactly these three — nothing else
        self.assertEqual({r[0] for r in self.all("SELECT name FROM org_units WHERE unit_type='region'")},
                         {'Sool', 'Sanaag', 'East Togdheer'})
        self.assertEqual(self.one("SELECT count(*) FROM org_units WHERE unit_type='region' AND parent_id=%s", (hq,)), 3)
        # every geographic / operational unit resolves to one of the three regions
        self.assertEqual(self.all("""
            SELECT o.code FROM org_units o
             WHERE o.unit_type IN ('district','station','checkpoint','airport')
               AND NOT EXISTS (SELECT 1 FROM org_unit_closure c JOIN org_units r ON r.id = c.ancestor_id
                                WHERE c.descendant_id = o.id AND r.unit_type = 'region')"""), [])
        # every airport and checkpoint sits in a district of one of the three regions
        self.assertEqual(self.all("""
            SELECT o.code FROM org_units o
             WHERE o.unit_type IN ('airport','checkpoint')
               AND NOT EXISTS (SELECT 1 FROM org_unit_closure c JOIN org_units d ON d.id = c.ancestor_id
                                WHERE c.descendant_id = o.id AND d.unit_type = 'district')"""), [])
        # a second root
        self.fails("INSERT INTO org_units(unit_type,code,name) VALUES('hq','HQ2','x')")
        # a checkpoint straight under HQ, a district under a station, a station under a directorate
        self.fails("INSERT INTO org_units(parent_id,unit_type,code,name) VALUES(%s,'checkpoint','X1','x')", (hq,))
        self.fails("INSERT INTO org_units(parent_id,unit_type,code,name) VALUES(%s,'district','X2','x')",
                   (self.unit('ST-004'),))
        self.fails("INSERT INTO org_units(parent_id,unit_type,code,name) VALUES(%s,'station','X3','x')",
                   (self.unit('DIR-CID'),))
        # type/parent cannot be edited behind move_unit()'s back
        self.fails('UPDATE org_units SET parent_id=%s WHERE code=%s', (self.unit('SANAAG'), 'D-BURAO'))
        # service_key only on directorates
        self.fails("UPDATE org_units SET service_key='x' WHERE code='ST-001'")

    def test_closure_matches_paths(self):
        # every unit has exactly one closure row per path element, and depths agree
        bad = self.all("""
            SELECT o.code FROM org_units o
             WHERE (SELECT count(*) FROM org_unit_closure c WHERE c.descendant_id=o.id)
                   <> array_length(string_to_array(trim(both '/' from o.path), '/'), 1)
                OR (SELECT max(depth) FROM org_unit_closure c WHERE c.descendant_id=o.id) <> o.depth""")
        self.assertEqual(bad, [])

    def test_move_unit_rewires_scope(self):
        rc = self.new_user('rc_sanaag', 'regional_commander', 'SANAAG')
        rc2 = self.new_user('rc_etog', 'regional_commander', 'ETOG')
        self.assertTrue(self.can(rc, 'incident:view', 'ST-002'))
        self.assertFalse(self.can(rc2, 'incident:view', 'ST-002'))
        self.cur.execute('SELECT move_unit(%s,%s)', (self.unit('ST-002'), self.unit('D-BURAO')))
        self.assertFalse(self.can(rc, 'incident:view', 'ST-002'))      # lost with the move
        self.assertTrue(self.can(rc2, 'incident:view', 'ST-002'))      # gained with the move
        self.assertEqual(self.one("SELECT path FROM org_units WHERE code='ST-002'"),
                         '/{0}/{1}/{2}/{3}/'.format(self.unit('HQ'), self.unit('ETOG'),
                                                    self.unit('D-BURAO'), self.unit('ST-002')))
        self.test_closure_matches_paths()

    def test_move_into_own_subtree_rejected(self):
        child = self.one("INSERT INTO org_units(parent_id,unit_type,code,name) VALUES(%s,'station','ST-004A','sub') RETURNING id",
                         (self.unit('ST-004'),))
        e = self.fails('SELECT move_unit(%s,%s)', (self.unit('ST-004'), child))
        self.assertIn('own subtree', str(e))
        self.fails('SELECT move_unit(%s,%s)', (self.unit('HQ'), self.unit('SOOL')))   # root immovable
        self.fails('SELECT move_unit(%s,%s)', (self.unit('ST-004'), self.unit('DIR-CID')))  # type rule

    def test_reference_numbers_are_sequential(self):
        a = self.one("SELECT next_ref('CP','ST-004',2026)")
        b = self.one("SELECT next_ref('CP','ST-004',2026)")
        self.assertEqual((a, b), ('CP-ST-004-2026-000001', 'CP-ST-004-2026-000002'))

    def test_audit_is_append_only(self):
        self.cur.execute("INSERT INTO audit_events(action,entity) VALUES('X','y')")
        self.fails("UPDATE audit_events SET action='Z'")
        self.fails('DELETE FROM audit_events')


# =============================================================================
class TestCodeFreeExpansion(Base):
    def test_new_airport_is_data_only(self):
        """The Buuhoodle Airport scenario: rows, no code."""
        ap = self.one("INSERT INTO org_units(parent_id,unit_type,code,name,status,attrs) "
                      "VALUES(%s,'airport','AP-BUH','Buuhoodle Airport','planned','{}') RETURNING id",
                      (self.unit('D-BUUHOODLE'),))
        officer = self.new_user('buh_officer', 'airport_officer', 'AP-BUH', False)
        p = self.person()
        ins = ("INSERT INTO airport_passengers(record_ref,unit_id,person_id,movement,travel_date,flight_number) "
               "VALUES('R1',%s,%s,'Arrival',current_date,'XX1')")
        self.fails(ins, (ap, p))                      # planned units cannot take records yet
        self.cur.execute("UPDATE org_units SET status='active' WHERE id=%s", (ap,))
        with self.as_user(officer):
            self.cur.execute(ins, (ap, p))            # RLS + type + active all pass
            self.assertEqual(self.one('SELECT count(*) FROM airport_passengers'), 1)
        # the new officer is confined to their airport; the Laascaanood airport officer cannot touch it
        self.assertFalse(self.can(officer, 'airport:create', 'AP-LAA'))
        self.assertFalse(self.can(self.uid('ap.officer'), 'airport:create', 'AP-BUH'))
        # an airport record cannot point at a station
        self.fails(ins, (self.unit('ST-004'), p))

    def test_new_checkpoint_and_district_are_data_only(self):
        # the official regions stay fixed at three; districts and units beneath them are data
        d = self.one("INSERT INTO org_units(parent_id,unit_type,code,name) VALUES(%s,'district','D-TEST','Test District') RETURNING id",
                     (self.unit('SANAAG'),))
        self.one("INSERT INTO org_units(parent_id,unit_type,code,name) VALUES(%s,'checkpoint','CP-NORTH','North Checkpoint') RETURNING id", (d,))
        u = self.new_user('cp_north', 'checkpoint_officer', 'CP-NORTH', False)
        self.assertTrue(self.can(u, 'checkpoint:create', 'CP-NORTH'))
        self.assertTrue(self.can(self.uid('chief'), 'checkpoint:view', 'CP-NORTH'))   # root sees it automatically
        self.assertFalse(self.can(self.uid('cp.south'), 'checkpoint:view', 'CP-NORTH'))
        # a Sanaag regional commander covers it; a Sool one does not
        rc = self.new_user('rc_sanaag_x', 'regional_commander', 'SANAAG')
        rs = self.new_user('rc_sool_x', 'regional_commander', 'SOOL')
        self.assertTrue(self.can(rc, 'checkpoint:view', 'CP-NORTH'))
        self.assertFalse(self.can(rs, 'checkpoint:view', 'CP-NORTH'))

    def test_directorate_bureau_inherits_national_service(self):
        bureau = self.one("INSERT INTO org_units(parent_id,unit_type,code,name) VALUES(%s,'bureau','BUR-FP-LA','Fingerprint Bureau Las Anod') RETURNING id",
                          (self.unit('DIR-FP'),))
        self.assertEqual(self.one('SELECT owning_service_unit(%s)', (bureau,)), self.unit('DIR-FP'))
        self.assertIsNone(self.one('SELECT owning_service_unit(%s)', (self.unit('ST-004'),)))
        # national fingerprint officer (assigned at directorate) covers the bureau automatically
        self.assertTrue(self.can(self.uid('fp.officer'), 'clearance:view', 'BUR-FP-LA'))
        # a bureau-only officer works at the bureau but can NOT approve nationally
        b = self.new_user('fp_bureau', 'fingerprint_officer', 'BUR-FP-LA')
        self.assertTrue(self.can(b, 'clearance:view', 'BUR-FP-LA'))
        self.assertFalse(self.can(b, 'clearance:approve', 'DIR-FP'))
        self.assertFalse(self.can(b, 'clearance:view', 'DIR-FP'))
        # a bureau of CID cannot own a clearance
        p = self.person()
        self.fails("INSERT INTO clearance_applications(application_ref,person_id,intake_unit_id,owner_unit_id,purpose) "
                   "VALUES('A',%s,%s,%s,'Travel')", (p, self.unit('ST-004'), self.unit('DIR-CID')))
        self.fails("INSERT INTO clearance_applications(application_ref,person_id,intake_unit_id,owner_unit_id,purpose) "
                   "VALUES('A',%s,%s,%s,'Travel')", (p, self.unit('ST-004'), self.unit('ST-004')))


# =============================================================================
class TestScopeEngine(Base):
    def test_checkpoint_officer_is_isolated_by_rls(self):
        p = self.person()
        self.cp_event('CP-SOUTH', p)
        self.cp_event('CP-SOUTH', p)
        self.cp_event('CP-EAST', p)
        with self.as_user('cp.south'):
            self.assertEqual(self.one('SELECT count(*) FROM checkpoint_events'), 2)
            e = self.fails("INSERT INTO checkpoint_events(event_ref,unit_id,person_id,screening_result) "
                           "VALUES('X',%s,%s,'No active alert')", (self.unit('CP-EAST'), p))
            self.assertIsInstance(e, pgerr.InsufficientPrivilege)
            self.cur.execute("INSERT INTO checkpoint_events(event_ref,unit_id,person_id,screening_result) "
                             "VALUES('OK',%s,%s,'No active alert')", (self.unit('CP-SOUTH'), p))
        with self.as_user('cp.east'):
            self.assertEqual(self.one('SELECT count(*) FROM checkpoint_events'), 1)
        # an event cannot be attached to a non-checkpoint unit
        self.fails("INSERT INTO checkpoint_events(event_ref,unit_id,person_id,screening_result) "
                   "VALUES('Y',%s,%s,'x')", (self.unit('ST-004'), p))

    def test_scope_function_equals_subtree(self):
        rc = self.new_user('rc_sool', 'regional_commander', 'SOOL')
        scope = {r[0] for r in self.all('SELECT authz_scope(%s,%s)', (rc, 'incident:view'))}
        subtree = {r[0] for r in self.all('SELECT descendant_id FROM org_unit_closure WHERE ancestor_id=%s', (self.unit('SOOL'),))}
        self.assertEqual(scope, subtree)
        self.assertIn(self.unit('ST-004'), scope)
        self.assertNotIn(self.unit('ST-005'), scope)
        # a permission the role does not hold yields an empty scope (fail closed)
        self.assertEqual(self.all('SELECT authz_scope(%s,%s)', (rc, 'clearance:approve')), [])
        # unknown permission / unknown user: empty
        self.assertEqual(self.all("SELECT authz_scope(%s,'nope:nope')", (rc,)), [])
        self.assertEqual(self.all("SELECT authz_scope(-1,'incident:view')"), [])

    def test_chief_commander_root_is_read_only_everywhere(self):
        chief = self.uid('chief')
        units = [r[0] for r in self.all('SELECT code FROM org_units')]
        reads = [r[0] for r in self.all("SELECT code FROM permissions WHERE NOT is_write AND scope_kind='unit'")]
        writes = [r[0] for r in self.all("SELECT code FROM permissions WHERE is_write AND scope_kind='unit'")]
        for code in units:
            for perm in reads:
                self.assertTrue(self.can(chief, perm, code), (perm, code))
            for perm in writes:
                self.assertFalse(self.can(chief, perm, code), (perm, code))
        for perm in [r[0] for r in self.all("SELECT code FROM permissions WHERE is_write AND scope_kind='global'")]:
            self.assertFalse(self.one('SELECT authz_has(%s,%s)', (chief, perm)), perm)
        # the guard makes it impossible to even configure a write onto a read-only role
        e = self.fails("INSERT INTO role_permissions VALUES(%s,'checkpoint:create')", (self.role('chief_commander'),))
        self.assertIn('read-only role', str(e))
        # …and RLS agrees: sees every checkpoint event, writes none
        p = self.person()
        self.cp_event('CP-SOUTH', p)
        self.cp_event('CP-WEST', p)
        with self.as_user('chief'):
            self.assertEqual(self.one('SELECT count(*) FROM checkpoint_events'), 2)
            self.fails("INSERT INTO checkpoint_events(event_ref,unit_id,person_id,screening_result) "
                       "VALUES('Z',%s,%s,'x')", (self.unit('CP-SOUTH'), p))

    def test_unknown_or_disabled_users_get_nothing(self):
        self.assertFalse(self.one("SELECT authz_can(-1,'checkpoint:view',%s)", (self.unit('CP-SOUTH'),)))
        self.assertFalse(self.one("SELECT authz_can(%s,'checkpoint:view',NULL)", (self.uid('chief'),)))
        cp = self.uid('cp.south')
        self.assertTrue(self.can(cp, 'checkpoint:view', 'CP-SOUTH'))
        self.cur.execute('UPDATE users SET active=false WHERE id=%s', (cp,))
        self.assertFalse(self.can(cp, 'checkpoint:view', 'CP-SOUTH'))

    def test_expired_and_revoked_assignments(self):
        expired = self.new_user('exp', 'checkpoint_officer', 'CP-SOUTH', False, valid_until='2020-01-01')
        revoked = self.new_user('rev', 'checkpoint_officer', 'CP-SOUTH', False, revoked_at='2020-01-01')
        live = self.new_user('liv', 'checkpoint_officer', 'CP-SOUTH', False)
        self.assertFalse(self.can(expired, 'checkpoint:view', 'CP-SOUTH'))
        self.assertFalse(self.can(revoked, 'checkpoint:view', 'CP-SOUTH'))
        self.assertTrue(self.can(live, 'checkpoint:view', 'CP-SOUTH'))

    def test_no_descendants_flag_is_respected(self):
        # an assignment WITH children below it but without include_descendants covers only the unit itself
        self.one("INSERT INTO org_units(parent_id,unit_type,code,name) VALUES(%s,'checkpoint','CP-LAA-GATE','Gate') RETURNING id",
                 (self.unit('D-LAASCAANOOD'),))
        u = self.new_user('district_only', 'regional_commander', 'D-LAASCAANOOD', False)
        self.assertTrue(self.can(u, 'checkpoint:view', 'D-LAASCAANOOD'))
        self.assertFalse(self.can(u, 'checkpoint:view', 'CP-LAA-GATE'))
        self.assertFalse(self.can(u, 'incident:view', 'ST-004'))
        v = self.new_user('district_full', 'regional_commander', 'D-LAASCAANOOD', True)
        self.assertTrue(self.can(v, 'checkpoint:view', 'CP-LAA-GATE'))
        self.assertTrue(self.can(v, 'incident:view', 'ST-004'))

    def test_delegated_admin_cannot_escalate(self):
        rc = self.new_user('rc_sool2', 'regional_commander', 'SOOL')
        self.assertTrue(self.one('SELECT can_grant(%s,%s,%s)', (rc, self.role('unit_admin'), self.unit('SOOL'))))
        self.assertFalse(self.one('SELECT can_grant(%s,%s,%s)', (rc, self.role('unit_admin'), self.unit('ETOG'))))      # outside scope
        self.assertFalse(self.one('SELECT can_grant(%s,%s,%s)', (rc, self.role('system_admin'), self.unit('SOOL'))))    # escalation
        self.assertFalse(self.one('SELECT can_grant(%s,%s,%s)', (rc, self.role('station_officer'), self.unit('ST-004'))))  # perms rc lacks
        # a station commander has no assignment:manage at all
        sc = self.new_user('sc4', 'station_commander', 'ST-004')
        self.assertFalse(self.one('SELECT can_grant(%s,%s,%s)', (sc, self.role('unit_admin'), self.unit('ST-004'))))


# =============================================================================
class TestNationalServices(Base):
    def _app(self, person, intake, ref):
        return ("INSERT INTO clearance_applications(application_ref,person_id,intake_unit_id,purpose) "
                "VALUES(%s,%s,%s,'Travel')", (ref, person, self.unit(intake)))

    def test_clearance_files_locally_and_approves_nationally(self):
        p = self.person()
        so4 = self.new_user('so4', 'station_officer', 'ST-004')
        # filing: allowed at own station, denied elsewhere; owner defaults to the directorate
        with self.as_user(so4):
            self.cur.execute(*self._app(p, 'ST-004', 'A-1'))
            e = self.fails(*self._app(p, 'ST-005', 'A-2'))
            self.assertIsInstance(e, pgerr.InsufficientPrivilege)
        self.assertEqual(self.one("SELECT owner_unit_id FROM clearance_applications WHERE application_ref='A-1'"),
                         self.unit('DIR-FP'))
        self.assertEqual(self.one("SELECT intake_unit_id FROM clearance_applications WHERE application_ref='A-1'"),
                         self.unit('ST-004'))
        # Migration 004: the 12 h review window and the signing-key FK are enforced by the database.
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")
        self.cur.execute("INSERT INTO signing_keys(key_id,algorithm,public_key) VALUES('k1','ed25519','x')")
        self.cur.execute("UPDATE clearance_applications SET created_at = now() - interval '13 hours'")
        self.cur.execute("SELECT set_config('sentinel.maintenance','off',true)")
        approve = ("UPDATE clearance_applications SET status='Approved', certificate_number='CERT-1', "
                   "certificate_signature='sig', signing_key_id='k1', reviewed_by=%s, reviewed_at=now() "
                   "WHERE application_ref='A-1'")
        # the filing officer sees it but cannot approve (UPDATE matches 0 rows)
        with self.as_user(so4):
            self.assertEqual(self.one('SELECT count(*) FROM clearance_applications'), 1)
            self.cur.execute(approve, (so4,))
            self.assertEqual(self.cur.rowcount, 0)
        # a regional commander can see it, still cannot approve
        rc = self.new_user('rc_s', 'regional_commander', 'SOOL')
        with self.as_user(rc):
            self.assertEqual(self.one('SELECT count(*) FROM clearance_applications'), 1)
            self.cur.execute(approve, (rc,))
            self.assertEqual(self.cur.rowcount, 0)
        # an unrelated station sees nothing
        so5 = self.new_user('so5', 'station_officer', 'ST-005')
        with self.as_user(so5):
            self.assertEqual(self.one('SELECT count(*) FROM clearance_applications'), 0)
        # the Fingerprint directorate officer approves
        fp = self.uid('fp.officer')
        with self.as_user(fp):
            self.cur.execute(approve, (fp,))
            self.assertEqual(self.cur.rowcount, 1)
        # an 'Approved' row without a signature is structurally impossible
        self.fails("UPDATE clearance_applications SET status='Approved', certificate_number=NULL WHERE application_ref='A-1'")

    def test_person_timeline_is_scope_filtered(self):
        p = self.person()
        self.cp_event('CP-SOUTH', p)
        self.cp_event('CP-EAST', p)
        self.cur.execute("INSERT INTO airport_passengers(record_ref,unit_id,person_id,movement,travel_date,flight_number) "
                         "VALUES('R',%s,%s,'Arrival',current_date,'F1')", (self.unit('AP-LAA'), p))
        self.cur.execute(*self._app(p, 'ST-004', 'A-9'))
        tl = lambda who: self.all('SELECT kind FROM person_timeline(%s,%s)', (self.uid(who), p))
        self.assertEqual(sorted(k for (k,) in tl('chief')), ['airport', 'checkpoint', 'checkpoint', 'clearance'])
        self.assertEqual([k for (k,) in tl('cp.south')], ['checkpoint'])
        self.assertEqual([k for (k,) in tl('ap.officer')], ['airport'])
        self.assertEqual([k for (k,) in tl('fp.officer')], ['clearance'])   # owner side
        self.assertEqual(tl('hr.officer'), [])

    def test_alert_flag_without_detail_leak(self):
        p = self.person()
        self.cur.execute("SELECT set_config('sentinel.maintenance','on',true)")        # alerts carry DB-stamped provenance (004)
        self.cur.execute("INSERT INTO suspect_alerts(alert_ref,person_id,notes) VALUES('AL-1',%s,'secret case detail')", (p,))
        self.cur.execute("SELECT set_config('sentinel.maintenance','off',true)")
        south = self.uid('cp.south')
        with self.as_user(south):
            self.assertEqual(self.one('SELECT count(*) FROM suspect_alerts'), 0)      # no detail
            self.assertTrue(self.one('SELECT person_alert_flag(%s,%s)', (south, p)))  # yes/no only
        # a user without alert:check gets False, not an error
        self.assertFalse(self.one('SELECT person_alert_flag(%s,%s)', (self.uid('hr.officer'), p)))
        # CID sees the detail
        with self.as_user('cid.officer'):
            self.assertEqual(self.one('SELECT count(*) FROM suspect_alerts'), 1)

    def test_cid_ownership_and_incident_escalation(self):
        so4 = self.new_user('so4b', 'station_officer', 'ST-004')
        inc = None
        with self.as_user(so4):
            self.cur.execute("INSERT INTO crime_incidents(file_number,unit_id,category,incident_at,description) "
                             "VALUES('CRM-1',%s,'Robbery',now(),'d')", (self.unit('ST-004'),))
            self.assertEqual(self.one('SELECT count(*) FROM crime_incidents'), 1)
        with self.as_user('cp.south'):
            self.assertEqual(self.one('SELECT count(*) FROM crime_incidents'), 0)
        inc = self.one("SELECT id FROM crime_incidents WHERE file_number='CRM-1'")
        cid = self.uid('cid.officer')
        with self.as_user(cid):
            self.cur.execute("INSERT INTO crime_cases(case_ref,category,source_incident_id) VALUES('C-1','Robbery',%s)", (inc,))
        self.assertEqual(self.one("SELECT owner_unit_id FROM crime_cases"), self.unit('DIR-CID'))
        # station staff cannot open or read national cases
        with self.as_user(so4):
            self.assertEqual(self.one('SELECT count(*) FROM crime_cases'), 0)
            e = self.fails("INSERT INTO crime_cases(case_ref,category) VALUES('C-2','x')")
            self.assertIsInstance(e, pgerr.InsufficientPrivilege)
        # incidents may only live in stations / checkpoints / airports
        self.fails("INSERT INTO crime_incidents(file_number,unit_id,category,incident_at,description) "
                   "VALUES('CRM-2',%s,'x',now(),'d')", (self.unit('SOOL'),))

    def _officer(self, unit_code, ref):
        return self.one("INSERT INTO officers(service_ref,unit_id,rank,unit_role,full_name) "
                        "VALUES(%s,%s,'Constable','General Patrol','O') RETURNING id", (ref, self.unit(unit_code)))

    def test_conduct_filing_is_limited_to_own_subtree(self):
        o4, o5 = self._officer('ST-004', 'OFF-4'), self._officer('ST-005', 'OFF-5')
        ins = ("INSERT INTO conduct_actions(action_ref,officer_id,officer_unit_id,action_type,classification,narrative,submitted_by,submitted_unit_id) "
               "VALUES(%s,%s,%s,'Disciplinary / Penalty','Official Reprimand','twenty chars narrative!!',%s,%s)")
        sc = self.new_user('sc4c', 'station_commander', 'ST-004')
        with self.as_user(sc):
            self.cur.execute(ins, ('K-1', o4, self.unit('ST-004'), sc, self.unit('ST-004')))                    # own unit
            e = self.fails(ins, ('K-2', o5, self.unit('ST-005'), sc, self.unit('ST-005')))                      # other jurisdiction
            self.assertIsInstance(e, pgerr.InsufficientPrivilege)
        rc = self.new_user('rc_sool3', 'regional_commander', 'SOOL')
        with self.as_user(rc):
            self.cur.execute(ins, ('K-3', o4, self.unit('ST-004'), rc, self.unit('SOOL')))                    # subordinate unit
            self.fails(ins, ('K-4', o5, self.unit('ST-005'), rc, self.unit('SOOL')))                          # ETOG is not theirs
        # review is national-only
        with self.as_user(sc):
            self.cur.execute("UPDATE conduct_actions SET status='Verified & Approved'")
            self.assertEqual(self.cur.rowcount, 0)
        hr = self.uid('hr.officer')
        with self.as_user(hr):
            self.assertEqual(self.one('SELECT count(*) FROM conduct_actions'), 2)
            self.cur.execute("UPDATE conduct_actions SET status='Verified & Approved', reviewed_by=%s", (hr,))
            self.assertEqual(self.cur.rowcount, 2)

    def test_inactive_unit_keeps_history_but_takes_no_new_records(self):
        p = self.person()
        self.cp_event('CP-EAST', p)
        self.cur.execute("UPDATE org_units SET status='inactive' WHERE code='CP-EAST'")
        self.fails("INSERT INTO checkpoint_events(event_ref,unit_id,person_id,screening_result) VALUES('N',%s,%s,'x')",
                   (self.unit('CP-EAST'), p))
        with self.as_user('cp.east'):
            self.assertEqual(self.one('SELECT count(*) FROM checkpoint_events'), 1)    # history still readable

    def test_police_fleet_needs_a_unit_and_lookup_is_global(self):
        self.fails("INSERT INTO vehicles(vehicle_ref,category,plate_number,vin,make_model) "
                   "VALUES('V1','Police Fleet','P1','V1','Hilux')")                     # fleet without unit
        self.cur.execute("INSERT INTO vehicles(vehicle_ref,category,plate_number,vin,make_model,unit_id) "
                         "VALUES('V2','Police Fleet','P2','V2','Hilux',%s)", (self.unit('ST-004'),))
        self.cur.execute("INSERT INTO vehicles(vehicle_ref,category,plate_number,vin,make_model) "
                         "VALUES('V3','Civilian / Commercial','P3','V3','Corolla')")
        with self.as_user('cp.south'):                                                  # holds vehicle:lookup
            self.assertEqual(self.one('SELECT count(*) FROM vehicles'), 2)
        with self.as_user('ap.officer'):                                                # holds neither
            self.assertEqual(self.one('SELECT count(*) FROM vehicles'), 0)


# =============================================================================
class TestLegacyParity(Base):
    """The nine legacy accounts must land with the same effective powers."""

    def test_legacy_roles_map_to_equivalent_scope(self):
        # fingerprint officer: clearance workflow, NO police search (legacy denylist = absent permission)
        fp = self.uid('fp.officer')
        self.assertTrue(self.can(fp, 'clearance:approve', 'DIR-FP'))
        for perm in ('officer:view', 'vehicle:view', 'unit:view', 'airport:view', 'checkpoint:view', 'case:view'):
            self.assertFalse(self.can(fp, perm, 'ST-004'), perm)
        # CID: cases + incidents, no officer register
        cid = self.uid('cid.officer')
        self.assertTrue(self.can(cid, 'case:create', 'DIR-CID'))
        self.assertFalse(self.can(cid, 'officer:view', 'ST-004'))
        # HR: officers + conduct review, no clearance, no cases
        hr = self.uid('hr.officer')
        self.assertTrue(self.can(hr, 'conduct:review', 'DIR-HR'))
        self.assertFalse(self.can(hr, 'clearance:view', 'DIR-FP'))
        # checkpoint South/East/West: own checkpoint only
        for me, mine, others in (('cp.south', 'CP-SOUTH', ('CP-EAST', 'CP-WEST')),
                                 ('cp.east', 'CP-EAST', ('CP-SOUTH', 'CP-WEST')),
                                 ('cp.west', 'CP-WEST', ('CP-SOUTH', 'CP-EAST'))):
            self.assertTrue(self.can(self.uid(me), 'checkpoint:create', mine))
            for o in others:
                self.assertFalse(self.can(self.uid(me), 'checkpoint:view', o))
        # unknown role strings no longer exist: a user with NO assignment has no powers (fail closed)
        nobody = self.one("INSERT INTO users(username,display_name,password_hash) VALUES('nobody','n','!') RETURNING id")
        self.assertEqual(self.all('SELECT authz_scope(%s,%s)', (nobody, 'checkpoint:view')), [])
        self.assertFalse(self.one("SELECT authz_has(%s,'person:search')", (nobody,)))


if __name__ == '__main__':
    try:
        unittest.main(verbosity=2, exit=False)
    finally:
        if _server is not None:
            _server.cleanup()

#!/usr/bin/env python3
"""Credential security: seeding, hashing, verification and session impact.

Covers Stage 0 work packages WP-02 (SR-02 / finding C-2, shared seeded default
password) and WP-03 (SR-03 / finding C-3, unsalted single-round SHA-256), plus
the session consequences of a password change (finding N-8).

Runs the REAL backend over HTTP against throwaway PostgreSQL databases
provisioned with `pgserver`. No operational database and no real police
record is touched.

What is asserted
----------------
  SEEDING
    1. No default password constant survives in the application source.
    2. With no SENTINEL_BOOTSTRAP_PASSWORD, every seeded account gets a
       DIFFERENT random password, the old shared default no longer works, and
       the generated credentials are reported once to an owner-only file.
    3. With SENTINEL_BOOTSTRAP_PASSWORD set, that password — and only that
       password — works.

  HASHING
    4. Nothing in the users table is a bare SHA-256 digest; every row is
       PBKDF2-HMAC-SHA256 at >= 600,000 iterations.
    5. The hash is salted: two accounts with the SAME password have DIFFERENT
       stored hashes (this is what defeats rainbow tables).
    6. A legacy unsalted SHA-256 row still authenticates once and is then
       transparently upgraded in place — no DDL, no forced reset.

  VERIFICATION
    7. Correct password -> 200; wrong / empty / near-miss -> 401.
    8. The stored hash is never accepted as the password (pass-the-hash).
    9. An unknown username and a wrong password are indistinguishable.

  SESSIONS
   10. A self-service password change keeps the current session and revokes
       every OTHER session for that account — including the in-process token
       cache (finding N-8).
   11. Sessions issued before the change cannot read protected data after it.
   12. The behaviour of an ADMIN-initiated password reset is measured and
       recorded exactly as it is (finding H-5).

Usage:
    python3 -m venv .venv
    .venv/bin/pip install -r requirements-dev.txt
    .venv/bin/python backend/test_password_security.py
"""
import hashlib
import os
import re
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import test_review_gate as harness
import server

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
RETIRED_DEFAULT = 'ChangeMe123!'
TEST_PASSWORD = 'Sentinel-Test-Pw-9174!'

SEEDED_ACCOUNTS = ('admin', 'fp.officer', 'ap.officer', 'cid.officer', 'hr.officer',
                   'cp.south', 'cp.east', 'cp.west', 'chief')


def strip_comments(text, markers=('#', '//')):
    """Drop whole-line comments so documentation of a removed constant is not
    mistaken for the constant itself."""
    kept = []
    for line in text.splitlines():
        stripped = line.strip()
        if any(stripped.startswith(m) for m in markers):
            continue
        kept.append(line)
    return '\n'.join(kept)


class _ServerFixture:
    """A backend process with its own freshly created database."""

    def __init__(self, tmp, cluster_env, label, extra_env=None):
        self.label = label
        dbname = f'sentinel_{label}_{secrets.token_hex(4)}'
        admin_env = {**os.environ, **cluster_env}
        import psycopg2
        import psycopg2.extensions
        conn = psycopg2.connect(
            host=admin_env['SENTINEL_DB_HOST'], port=admin_env['SENTINEL_DB_PORT'],
            user=admin_env['SENTINEL_DB_USER'],
            password=admin_env['SENTINEL_DB_PASSWORD'] or None, dbname='postgres')
        conn.set_isolation_level(psycopg2.extensions.ISOLATION_LEVEL_AUTOCOMMIT)
        with conn.cursor() as cur:
            cur.execute(f'CREATE DATABASE {dbname}')
        conn.close()
        self.db_env = {**cluster_env, 'SENTINEL_DB_NAME': dbname}
        self.dbname = dbname
        self.port = harness.free_port()
        self.base = f'http://127.0.0.1:{self.port}'
        self.credentials_file = os.path.join(tmp, f'{label}-bootstrap.txt')
        self.uploads = os.path.join(tmp, f'{label}-uploads')
        self.logpath = os.path.join(tmp, f'{label}-server.log')
        self.log = open(self.logpath, 'w+')
        env = {k: v for k, v in os.environ.items()
               if k != 'SENTINEL_BOOTSTRAP_PASSWORD'}
        env.update(self.db_env)
        env.update({
            'PORT': str(self.port),
            'SENTINEL_NO_PORT_TAKEOVER': '1',
            'SENTINEL_UPLOADS': self.uploads,
            'SENTINEL_BOOTSTRAP_CREDENTIALS_FILE': self.credentials_file,
        })
        env.update(extra_env or {})
        self.proc = subprocess.Popen([sys.executable, harness.SERVER], env=env,
                                     stdout=self.log, stderr=self.log)
        for _ in range(150):
            try:
                if harness.request(self.base, 'GET', '/api/health')[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(.1)
        else:
            self.log.seek(0)
            raise RuntimeError(f'{label} server did not start:\n' + self.log.read())

    def connect(self):
        """psycopg2 connection to THIS fixture's database."""
        import psycopg2
        from psycopg2.extras import RealDictCursor
        return psycopg2.connect(
            host=self.db_env['SENTINEL_DB_HOST'], port=self.db_env['SENTINEL_DB_PORT'],
            user=self.db_env['SENTINEL_DB_USER'],
            password=self.db_env['SENTINEL_DB_PASSWORD'] or None,
            dbname=self.dbname, cursor_factory=RealDictCursor)

    def hashes(self):
        conn = self.connect()
        try:
            with conn.cursor() as cur:
                cur.execute('SELECT username,password_hash FROM users ORDER BY username')
                return {r['username']: r['password_hash'] for r in cur.fetchall()}
        finally:
            conn.close()

    def login(self, username, password):
        return harness.request(self.base, 'POST', '/api/login',
                               body={'username': username, 'password': password})

    def stop(self):
        self.proc.terminate()
        self.proc.wait(timeout=10)
        self.log.close()


class PasswordSecurityTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='sentinel-password-')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith('SENTINEL_DB_') and k != 'SENTINEL_DATABASE_URL'}
        env.pop('SENTINEL_BOOTSTRAP_PASSWORD', None)
        cls.env_patch = patch.dict(os.environ, env, clear=True)
        cls.env_patch.start()
        cls.addClassCleanup(cls.env_patch.stop)
        cls.addClassCleanup(cls.temp.cleanup)
        database = harness.provision_database(cls.temp.name)
        if database is None:
            raise unittest.SkipTest('Install pgserver for isolated integration tests')
        cluster_env, stop, _ = database
        cls.addClassCleanup(stop)
        cls.cluster_env = {k: os.environ[k] for k in harness.DB_ENV_KEYS
                           if k in os.environ}

        # Fixture A: NO bootstrap password supplied -> random per account.
        cls.random_srv = _ServerFixture(cls.temp.name, cls.cluster_env, 'random')
        cls.addClassCleanup(cls.random_srv.stop)
        # Fixture B: bootstrap password supplied explicitly.
        cls.known_srv = _ServerFixture(
            cls.temp.name, cls.cluster_env, 'known',
            extra_env={'SENTINEL_BOOTSTRAP_PASSWORD': TEST_PASSWORD})
        cls.addClassCleanup(cls.known_srv.stop)

    # =================================================== SEEDING ==========
    def test_01_no_default_password_constant_in_the_source(self):
        for rel in ('backend/server.py', 'index.html', 'backend/migrate_rbac.py'):
            path = os.path.join(ROOT, rel)
            body = strip_comments(open(path, encoding='utf-8').read())
            self.assertNotIn(RETIRED_DEFAULT, body,
                             f'{rel} still contains the retired default password')

    def test_02_random_seeding_gives_every_account_a_different_password(self):
        hashes = self.random_srv.hashes()
        for account in SEEDED_ACCOUNTS:
            self.assertIn(account, hashes, f'{account} should have been seeded')
        self.assertEqual(len(set(hashes.values())), len(hashes),
                         'every seeded account must have a distinct password hash')

    def test_03_the_retired_default_password_no_longer_works(self):
        for account in SEEDED_ACCOUNTS:
            status, payload = self.random_srv.login(account, RETIRED_DEFAULT)
            self.assertEqual(status, 401,
                             f'{account} must not accept the retired default password '
                             f'(got {status}: {payload})')

    def test_04_generated_credentials_are_reported_once_and_owner_only(self):
        path = self.random_srv.credentials_file
        self.assertTrue(os.path.exists(path),
                        'first-run credentials must be written for the operator')
        mode = os.stat(path).st_mode & 0o777
        self.assertEqual(mode, 0o600,
                         f'the credentials file must be owner-only, got {oct(mode)}')
        content = open(path, encoding='utf-8').read()
        for account in SEEDED_ACCOUNTS:
            self.assertIn(account, content, f'{account} must appear in the report')
        # And those credentials must genuinely work.
        issued = dict(re.findall(r'^\s+(\S+)\s+(\S+)$', content, re.M))
        self.assertIn('admin', issued, f'could not parse the credentials file:\n{content}')
        status, payload = self.random_srv.login('admin', issued['admin'])
        self.assertEqual(status, 200,
                         f'the reported first-run password must work: {payload}')
        # Every issued password is distinct.
        self.assertEqual(len(set(issued.values())), len(issued),
                         'each account must receive its own random password')

    def test_05_explicit_bootstrap_password_is_honoured(self):
        status, payload = self.known_srv.login('admin', TEST_PASSWORD)
        self.assertEqual(status, 200, f'the supplied password must work: {payload}')
        status, _ = self.known_srv.login('admin', RETIRED_DEFAULT)
        self.assertEqual(status, 401, 'only the supplied password may work')
        self.assertFalse(os.path.exists(self.known_srv.credentials_file),
                         'a password the operator chose must never be echoed to disk')

    # =================================================== HASHING ==========
    def test_06_no_stored_hash_is_a_bare_sha256_digest(self):
        for fixture in (self.random_srv, self.known_srv):
            for username, stored in fixture.hashes().items():
                self.assertFalse(
                    re.fullmatch(r'[0-9a-fA-F]{64}', stored or ''),
                    f'{username} is still stored as an unsalted SHA-256 digest')

    def test_07_hashes_are_pbkdf2_with_at_least_600k_iterations(self):
        for username, stored in self.known_srv.hashes().items():
            parts = stored.split('$')
            self.assertEqual(len(parts), 4, f'{username}: unexpected hash format')
            self.assertEqual(parts[0], 'pbkdf2_sha256', f'{username}: wrong algorithm')
            self.assertGreaterEqual(int(parts[1]), 600_000,
                                    f'{username}: iteration count is too low')
            self.assertGreaterEqual(len(parts[2]), 16, f'{username}: salt too short')

    def test_08_identical_passwords_produce_different_hashes(self):
        """Every account in the 'known' fixture shares TEST_PASSWORD, so this
        is a direct test that the hash is salted."""
        hashes = self.known_srv.hashes()
        self.assertGreater(len(hashes), 1)
        self.assertEqual(len(set(hashes.values())), len(hashes),
                         'accounts sharing a password must not share a hash')

    def test_09_legacy_sha256_row_authenticates_once_then_upgrades(self):
        """An existing deployment must migrate with no DDL and no reset."""
        legacy_password = 'LegacyPassword!42'
        legacy_digest = hashlib.sha256(legacy_password.encode()).hexdigest()
        username = f'legacy.{secrets.token_hex(3)}'
        conn = self.known_srv.connect()
        try:
            with conn.cursor() as cur:
                cur.execute(
                    'INSERT INTO users(username,display_name,role,branch,password_hash,active)'
                    ' VALUES(%s,%s,%s,%s,%s,1)',
                    (username, 'Legacy Officer', 'FingerprintUnit',
                     'Fingerprint Unit', legacy_digest))
            conn.commit()
        finally:
            conn.close()

        self.assertEqual(self.known_srv.hashes()[username], legacy_digest)
        status, payload = self.known_srv.login(username, legacy_password)
        self.assertEqual(status, 200,
                         f'a legacy account must not be locked out: {payload}')
        upgraded = self.known_srv.hashes()[username]
        self.assertNotEqual(upgraded, legacy_digest,
                            'the legacy hash must be rewritten after a successful login')
        self.assertTrue(upgraded.startswith('pbkdf2_sha256$'),
                        f'the upgraded hash must be PBKDF2, got {upgraded[:20]}')
        # Still works afterwards, and the old digest is not accepted as input.
        self.assertEqual(self.known_srv.login(username, legacy_password)[0], 200)
        self.assertEqual(self.known_srv.login(username, legacy_digest)[0], 401)

    # ============================================== VERIFICATION ==========
    def test_10_wrong_passwords_are_refused(self):
        for bad in ('', ' ', TEST_PASSWORD + ' ', TEST_PASSWORD.lower(),
                    TEST_PASSWORD[:-1], TEST_PASSWORD.upper(), RETIRED_DEFAULT,
                    "' OR '1'='1", 'null'):
            status, _ = self.known_srv.login('admin', bad)
            self.assertEqual(status, 401, f'password {bad!r} must be refused')

    def test_11_the_stored_hash_is_not_a_valid_password(self):
        stored = self.known_srv.hashes()['admin']
        for probe in (stored, stored.split('$')[-1]):
            status, _ = self.known_srv.login('admin', probe)
            self.assertEqual(status, 401, 'the stored hash must never authenticate')

    def test_12_unknown_user_and_wrong_password_are_indistinguishable(self):
        unknown = self.known_srv.login(f'nobody.{secrets.token_hex(3)}', TEST_PASSWORD)
        wrong = self.known_srv.login('admin', 'definitely-not-the-password')
        self.assertEqual(unknown[0], wrong[0], 'status codes must match')
        self.assertEqual(unknown[1], wrong[1],
                         'error bodies must not reveal whether the account exists')

    def test_13_correct_password_still_authenticates(self):
        status, payload = self.known_srv.login('fp.officer', TEST_PASSWORD)
        self.assertEqual(status, 200, payload)
        self.assertIn('token', payload)
        status, me = harness.request(self.known_srv.base, 'GET', '/api/me',
                                     payload['token'])
        self.assertEqual(status, 200, me)

    # ================================================== SESSIONS ==========
    def test_14_password_change_revokes_other_sessions_but_keeps_this_one(self):
        """Finding N-8: the DB rows were deleted but the in-process token cache
        was not, so other browsers stayed signed in."""
        srv = self.known_srv
        username = f'rotate.{secrets.token_hex(3)}'
        status, payload = harness.request(
            srv.base, 'POST', '/api/admin/users',
            srv.login('admin', TEST_PASSWORD)[1]['token'],
            {'username': username, 'display_name': 'Rotate Officer',
             'role': 'FingerprintUnit', 'branch': 'Fingerprint Unit',
             'password': TEST_PASSWORD})
        self.assertIn(status, (200, 201), f'could not create the probe user: {payload}')

        first = srv.login(username, TEST_PASSWORD)[1]['token']
        second = srv.login(username, TEST_PASSWORD)[1]['token']
        other = srv.login(username, TEST_PASSWORD)[1]['token']
        for token in (first, second, other):
            self.assertEqual(
                harness.request(srv.base, 'GET', '/api/me', token)[0], 200)

        new_password = 'Rotated-Pw-5521!'
        status, payload = harness.request(
            srv.base, 'POST', '/api/me/password', first,
            {'current_password': TEST_PASSWORD, 'new_password': new_password})
        self.assertEqual(status, 200, f'password change failed: {payload}')

        self.assertEqual(harness.request(srv.base, 'GET', '/api/me', first)[0], 200,
                         'the session that changed the password must stay signed in')
        for token, label in ((second, 'second'), (other, 'third')):
            self.assertEqual(
                harness.request(srv.base, 'GET', '/api/me', token)[0], 401,
                f'the {label} session must be revoked by a password change '
                '(finding N-8: the in-memory token cache must be purged too)')

        self.assertEqual(srv.login(username, new_password)[0], 200)
        self.assertEqual(srv.login(username, TEST_PASSWORD)[0], 401,
                         'the old password must stop working immediately')

    def test_15_admin_password_reset_session_behaviour_is_recorded(self):
        """Measures what an ADMIN-initiated reset does to the target's live
        sessions. Finding H-5 (no session revocation) is a separate, unfunded
        work package; this test records the behaviour so a change is noticed.
        """
        srv = self.known_srv
        admin_token = srv.login('admin', TEST_PASSWORD)[1]['token']
        username = f'reset.{secrets.token_hex(3)}'
        status, payload = harness.request(
            srv.base, 'POST', '/api/admin/users', admin_token,
            {'username': username, 'display_name': 'Reset Officer',
             'role': 'FingerprintUnit', 'branch': 'Fingerprint Unit',
             'password': TEST_PASSWORD})
        self.assertIn(status, (200, 201), payload)
        uid = payload.get('user', payload).get('id')
        self.assertIsNotNone(uid, f'could not read the new user id: {payload}')

        victim = srv.login(username, TEST_PASSWORD)[1]['token']
        self.assertEqual(harness.request(srv.base, 'GET', '/api/me', victim)[0], 200)

        status, payload = harness.request(
            srv.base, 'PATCH', f'/api/admin/users/{uid}', admin_token,
            {'password': 'Admin-Reset-Pw-8842!'})
        self.assertEqual(status, 200, f'admin reset failed: {payload}')

        self.assertEqual(srv.login(username, 'Admin-Reset-Pw-8842!')[0], 200,
                         'the new password must work')
        self.assertEqual(srv.login(username, TEST_PASSWORD)[0], 401,
                         'the old password must stop working')

        still_live = harness.request(srv.base, 'GET', '/api/me', victim)[0]
        if still_live == 401:
            self.skipTest('admin reset now revokes sessions — tighten this test')
        self.assertEqual(
            still_live, 200,
            'RECORDED EXPOSURE (finding H-5, not in Stage 0 scope): an '
            'administrator resetting an officer\'s password does NOT end that '
            'officer\'s existing sessions, so a stolen session survives the '
            'reset. Fixing this requires owner authorisation.')


if __name__ == '__main__':
    unittest.main(verbosity=2)

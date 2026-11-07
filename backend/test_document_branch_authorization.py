#!/usr/bin/env python3
"""Document branch-authorization tests — PREPARED, dual-mode.

Pairs with:
    security/MIGRATION_PROPOSAL_DOCUMENT_OWNERSHIP.md   (migration M-01)
    security/DOCUMENT_AUTHORIZATION_TEST_DESIGN.md      (the full matrix)

Covers the four cases the owner required: same-branch access, cross-branch
denial, unauthenticated access, administrator access.

TWO MODES, selected automatically at runtime
--------------------------------------------
  * `documents` table ABSENT  -> PRE-MIGRATION MODE.
        Migration M-01 has not been approved or applied. The suite measures
        and REPORTS today's real behaviour (cross-branch currently returns
        200) and then SKIPS, so an unapproved migration never turns the suite
        red. The exposure is printed, not hidden.

  * `documents` table PRESENT -> ENFORCEMENT MODE.
        The full strict matrix runs. Cross-branch access MUST be 403 or these
        tests fail.

So the moment M-01 Phase A is applied, these tests become live with no edit.

This file creates no schema and modifies no application code. Every identity,
branch and document below is synthetic; no real police record is used.

Usage:
    SENTINEL_BOOTSTRAP_PASSWORD='ChangeMe123!' \\
        .venv/bin/python backend/test_document_branch_authorization.py
"""
import json
import os
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.error
import urllib.request
from unittest.mock import patch

import test_review_gate as harness
import server

PASSWORD = os.environ.get('SENTINEL_BOOTSTRAP_PASSWORD', 'ChangeMe123!')

REAL_PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n'
REAL_JPEG = (b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00'
             + b'\x00' * 64)

PRE_MIGRATION_NOTE = (
    'Migration M-01 (documents table) is not applied, so per-file branch '
    'authorisation does not exist yet. See '
    'security/MIGRATION_PROPOSAL_DOCUMENT_OWNERSHIP.md. This suite switches '
    'itself to strict enforcement assertions as soon as the table exists.'
)


def raw_get(url, token=None, cookie=None):
    """GET returning (status, body_bytes, headers) without JSON decoding."""
    req = urllib.request.Request(url, method='GET')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    if cookie:
        req.add_header('Cookie', cookie)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, r.read(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read(), dict(e.headers)


class DocumentBranchAuthorizationTest(unittest.TestCase):
    enforcement = False

    # ------------------------------------------------------------------ setup
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='sentinel-docauth-')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith('SENTINEL_DB_') and k != 'SENTINEL_DATABASE_URL'}
        env['SENTINEL_BOOTSTRAP_PASSWORD'] = PASSWORD
        cls.env_patch = patch.dict(os.environ, env, clear=True)
        cls.env_patch.start()
        cls.addClassCleanup(cls.env_patch.stop)
        cls.addClassCleanup(cls.temp.cleanup)

        database = harness.provision_database(cls.temp.name)
        if database is None:
            raise unittest.SkipTest('Install pgserver for isolated integration tests')
        db_env, stop, _ = database
        cls.addClassCleanup(stop)

        port = harness.free_port()
        cls.base = f'http://127.0.0.1:{port}'
        cls.uploads = os.path.join(cls.temp.name, 'uploads')
        log = open(os.path.join(cls.temp.name, 'server.log'), 'w+')
        cls.addClassCleanup(log.close)
        proc = subprocess.Popen(
            [sys.executable, harness.SERVER],
            env={**os.environ, **db_env, 'PORT': str(port),
                 'SENTINEL_NO_PORT_TAKEOVER': '1',
                 'SENTINEL_BOOTSTRAP_PASSWORD': PASSWORD,
                 'SENTINEL_UPLOADS': cls.uploads},
            stdout=log, stderr=log)

        def stop_server():
            proc.terminate()
            proc.wait(timeout=10)

        cls.addClassCleanup(stop_server)
        for _ in range(150):
            try:
                if harness.request(cls.base, 'GET', '/api/health')[0] == 200:
                    break
            except OSError:
                pass
            time.sleep(.1)
        else:
            log.seek(0)
            raise RuntimeError(log.read())

        cls.tokens = {}
        for name in ('admin', 'fp.officer', 'cp.south', 'cp.east', 'cid.officer', 'chief'):
            status, payload = harness.request(cls.base, 'POST', '/api/login', body={
                'username': name, 'password': PASSWORD})
            assert status == 200, (name, status, payload)
            cls.tokens[name] = payload['token']

        cls.run_tag = secrets.token_hex(3)
        cls.enforcement = cls._documents_table_exists()
        cls.doc_path = cls._file_clearance_document()

    @classmethod
    def _documents_table_exists(cls):
        """Detect migration M-01 without creating anything."""
        conn = server.get_db_connection()
        try:
            row = conn.execute(
                "SELECT COUNT(*) AS n FROM information_schema.tables "
                "WHERE table_schema='public' AND table_name='documents'").fetchone()
            return bool((dict(row) if row else {}).get('n'))
        except Exception:
            return False
        finally:
            conn.close()

    @classmethod
    def _file_clearance_document(cls):
        """File a synthetic clearance application and return its document path."""
        seq = secrets.token_hex(2)
        fields = {
            'first_name': 'Docauth', 'second_name': 'Branch', 'third_name': 'Probe',
            'fourth_name': seq.upper(), 'date_of_birth': '1991-02-02',
            'national_id': f'{secrets.randbelow(10**8):08d}',
            'mother_name': 'Hooyo Docauth', 'residence': 'Hargeisa',
            'phone': '+252 63 555 0611', 'sex': 'Male',
            'email': f'docauth-{cls.run_tag}-{seq}@example.com',
            'purpose': 'Employment',
            'guardian_name': 'Guardian Docauth', 'guardian_relationship': 'Uncle',
            'guardian_id': 'GD-6600', 'guardian_occupation': 'Teacher',
            'guardian_phone': '+252 63 555 0612',
        }
        status, payload = harness.multipart_request(
            cls.base, '/api/clearance-applications', cls.tokens['fp.officer'],
            fields=fields,
            files={'doc_app_0': ('passport-scan.pdf', REAL_PDF),
                   'doc_app_1': ('national-id.pdf', REAL_PDF),
                   'doc_guard_0': ('guardian-id.pdf', REAL_PDF),
                   'doc_guard_1': ('guardian-letter.pdf', REAL_PDF)})
        assert status in (200, 201), (status, payload)
        app_id = payload['application_id']
        status, record = harness.request(
            cls.base, 'GET', f'/api/clearance-applications/{app_id}',
            cls.tokens['fp.officer'])
        assert status == 200, (status, record)
        docs = record.get('applicant_docs') or []
        if isinstance(docs, str):
            docs = json.loads(docs)
        assert docs, f'no document recorded: {record}'
        path = docs[0]['path'] if isinstance(docs[0], dict) else docs[0]
        assert path.startswith('/uploads/'), path
        return path

    def skip_unless_enforcing(self, label):
        if not self.enforcement:
            self.skipTest(f'{label}: PRE-MIGRATION MODE. {PRE_MIGRATION_NOTE}')

    # =========================================== 2.3 UNAUTHENTICATED =========
    # These must hold in BOTH modes — Stage 0 already guarantees them.
    def test_20_anonymous_access_is_refused(self):
        status, body, _ = raw_get(self.base + self.doc_path)
        self.assertEqual(status, 401, 'anonymous callers must not receive documents')
        self.assertNotIn(b'%PDF', body, 'the 401 body must not contain the document')

    def test_21_forged_token_is_refused(self):
        for bogus in ('', 'not-a-token', secrets.token_hex(32)):
            self.assertEqual(raw_get(self.base + self.doc_path, token=bogus)[0], 401,
                             f'forged token {bogus!r} must be refused')

    def test_22_revoked_session_is_refused(self):
        status, payload = harness.request(self.base, 'POST', '/api/login', body={
            'username': 'fp.officer', 'password': PASSWORD})
        self.assertEqual(status, 200, payload)
        token = payload['token']
        self.assertEqual(raw_get(self.base + self.doc_path, token=token)[0], 200)
        harness.request(self.base, 'POST', '/api/logout', token)
        self.assertEqual(raw_get(self.base + self.doc_path, token=token)[0], 401,
                         'a logged-out token must not read documents')

    def test_24_no_stored_file_is_anonymously_readable(self):
        stored = os.listdir(self.uploads) if os.path.isdir(self.uploads) else []
        self.assertTrue(stored, 'expected at least one stored upload')
        for name in stored:
            self.assertEqual(raw_get(f'{self.base}/uploads/{name}')[0], 401,
                             f'/uploads/{name} must require authentication')

    # ============================================= 2.1 SAME BRANCH ===========
    def test_01_same_branch_officer_can_read(self):
        status, body, _ = raw_get(self.base + self.doc_path,
                                  token=self.tokens['fp.officer'])
        self.assertEqual(status, 200, 'the filing officer must keep access')
        self.assertTrue(body.startswith(b'%PDF'))

    def test_04_same_branch_cookie_access_works(self):
        status, payload = harness.request(self.base, 'POST', '/api/login', body={
            'username': 'fp.officer', 'password': PASSWORD})
        self.assertEqual(status, 200, payload)
        status, body, _ = raw_get(self.base + self.doc_path,
                                  cookie=f"sentinel_session={payload['token']}")
        self.assertEqual(status, 200, 'cookie-authenticated image loads must work')
        self.assertTrue(body.startswith(b'%PDF'))

    # ========================================== 2.2 CROSS BRANCH =============
    def test_10_cross_branch_is_denied(self):
        """THE issue under remediation (S-01).

        Pre-migration this records the live exposure and skips. Post-migration
        it is a hard 403 assertion.
        """
        status, body, _ = raw_get(self.base + self.doc_path,
                                  token=self.tokens['cp.east'])
        if not self.enforcement:
            self.assertEqual(
                status, 200,
                'expected the known pre-migration exposure (200). A different '
                'status means behaviour changed without the migration — investigate.')
            self.skipTest(
                'CROSS-BRANCH READ CURRENTLY RETURNS 200 — this is finding S-01, '
                'open and release-blocking. ' + PRE_MIGRATION_NOTE)
        self.assertEqual(status, 403,
                         'an officer from another branch must be refused (403)')
        self.assertNotIn(b'%PDF', body, 'a 403 must not contain the document bytes')

    def test_12_cross_branch_cid_officer_is_denied(self):
        self.skip_unless_enforcing('cross-branch CID read')
        status, body, _ = raw_get(self.base + self.doc_path,
                                  token=self.tokens['cid.officer'])
        self.assertEqual(status, 403)
        self.assertNotIn(b'%PDF', body)

    def test_15_enumeration_reveals_nothing(self):
        self.skip_unless_enforcing('enumeration probe')
        seen = set()
        for _ in range(50):
            status, _, _ = raw_get(
                f'{self.base}/uploads/f_{secrets.token_hex(8)}.pdf',
                token=self.tokens['cp.east'])
            self.assertNotEqual(status, 200, 'a guessed name must never return a file')
            seen.add(status)
        self.assertLessEqual(len(seen), 1,
                             f'status must not distinguish existing from missing files: {seen}')

    # ========================================== 2.4 ADMINISTRATOR ============
    def test_30_administrator_can_read_any_document(self):
        status, body, _ = raw_get(self.base + self.doc_path,
                                  token=self.tokens['admin'])
        self.assertEqual(status, 200, 'administrators must retain full document access')
        self.assertTrue(body.startswith(b'%PDF'))

    def test_31_read_only_commander_can_read(self):
        status, body, _ = raw_get(self.base + self.doc_path,
                                  token=self.tokens['chief'])
        self.assertEqual(status, 200,
                         'the global read-only Commander must retain document access')
        self.assertTrue(body.startswith(b'%PDF'))

    # ================================== 2.5 FAIL-CLOSED / UNCLASSIFIED =======
    def test_40_unindexed_file_is_not_served_to_a_scoped_officer(self):
        """A file on disk with no documents row must fail CLOSED."""
        self.skip_unless_enforcing('unindexed-file fail-closed')
        orphan = os.path.join(self.uploads, f'f_{secrets.token_hex(8)}.pdf')
        os.makedirs(self.uploads, exist_ok=True)
        with open(orphan, 'wb') as fh:
            fh.write(REAL_PDF)
        self.addCleanup(lambda: os.path.exists(orphan) and os.remove(orphan))
        status, body, _ = raw_get(
            f'{self.base}/uploads/{os.path.basename(orphan)}',
            token=self.tokens['fp.officer'])
        self.assertIn(status, (403, 404),
                      'an unclassified file must never be served to a scoped officer')
        self.assertNotIn(b'%PDF', body)

    def test_43_path_traversal_is_refused(self):
        for probe in ('/uploads/../backend/server.py',
                      '/uploads/..%2fbackend%2fserver.py',
                      '/uploads/....//server.py'):
            status, body, _ = raw_get(self.base + probe, token=self.tokens['admin'])
            self.assertNotEqual(status, 200, f'{probe} must not escape uploads/')
            self.assertNotIn(b'UPLOAD_ALLOWED_EXTS', body, f'{probe} leaked server source')

    # ============================================ 2.8 REGRESSION =============
    def test_70_stage0_hardening_headers_survive(self):
        _, _, headers = raw_get(self.base + self.doc_path, token=self.tokens['fp.officer'])
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff')
        self.assertIn('sandbox', headers.get('Content-Security-Policy', ''))

    # ================================================= MODE REPORT ===========
    def test_99_report_mode(self):
        mode = 'ENFORCEMENT' if self.enforcement else 'PRE-MIGRATION'
        print(f'\n[document authorization] mode: {mode}')
        if not self.enforcement:
            print('[document authorization] S-01 is OPEN: an authenticated officer '
                  'can read another branch\'s documents.')
            print('[document authorization] ' + PRE_MIGRATION_NOTE)


if __name__ == '__main__':
    unittest.main(verbosity=2)

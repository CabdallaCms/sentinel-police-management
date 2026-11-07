#!/usr/bin/env python3
"""Uploaded-document access control and upload validation.

Covers Stage 0 work packages WP-08 (SR-01 / finding C-1, anonymous access to
/uploads/) and WP-09 (SR-15 / finding M-7, unvalidated save_upload).

Runs the REAL backend over HTTP against a throwaway PostgreSQL cluster
provisioned with `pgserver`. No operational database and no real police
record is ever touched: every person, officer and document in this file is
synthetic.

What is asserted
----------------
  1. UNAUTHENTICATED ACCESS IS REFUSED. An anonymous GET of a real uploaded
     document returns 401, with no file bytes in the body. Before WP-08 the
     same request returned 200 and the document itself.
  2. AUTHENTICATED ACCESS STILL WORKS. The officer who filed the record can
     fetch the document, and the response carries the anti-sniffing and
     sandbox headers.
  3. A FORGED / EXPIRED TOKEN IS REFUSED (401) — the gate checks the session,
     not merely the presence of a header.
  4. CROSS-BRANCH: a checkpoint officer posted to a different branch is used
     to probe the same document. The result is asserted EXACTLY as it is, and
     the test documents that per-file branch authorisation is NOT yet
     implemented (finding N-6: documents are JSON blobs with no ownership
     link). This test exists so the remaining exposure is visible and cannot
     be quietly forgotten — see the Stage 0 report.
  5. UPLOAD VALIDATION. Dangerous extensions (.html, .svg, .php, .exe), a
     double extension, an empty file, an oversized file and a content/
     extension mismatch are all refused; a genuine PDF and JPEG are accepted.
  6. PATH TRAVERSAL out of the uploads directory is refused.

Usage:
    python3 -m venv .venv
    .venv/bin/pip install -r requirements-dev.txt
    SENTINEL_BOOTSTRAP_PASSWORD='ChangeMe123!' .venv/bin/python \\
        backend/test_upload_access_control.py
"""
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

# Minimal but genuine file headers.
REAL_PDF = b'%PDF-1.4\n1 0 obj\n<<>>\nendobj\ntrailer\n<<>>\n%%EOF\n'
REAL_JPEG = b'\xff\xd8\xff\xe0\x00\x10JFIF\x00\x01\x01\x00\x00\x01\x00\x01\x00\x00' + b'\x00' * 64


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


class UploadAccessControlTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='sentinel-uploads-')
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
        for _ in range(100):
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
        for name in ('admin', 'fp.officer', 'cp.south', 'cp.east'):
            status, payload = harness.request(cls.base, 'POST', '/api/login', body={
                'username': name, 'password': PASSWORD})
            assert status == 200, (name, status, payload)
            cls.tokens[name] = payload['token']
        cls.run_tag = secrets.token_hex(3)
        cls.doc_path = cls._file_a_document()

    @classmethod
    def _file_a_document(cls):
        """File a real clearance application with an attached document and
        return the stored '/uploads/...' path of that document."""
        seq = secrets.token_hex(2)
        fields = {
            'first_name': 'Upload', 'second_name': 'Access', 'third_name': 'Control',
            'fourth_name': seq.upper(), 'date_of_birth': '1992-03-03',
            'national_id': f'{secrets.randbelow(10**8):08d}',
            'mother_name': 'Hooyo Upload', 'residence': 'Hargeisa',
            'phone': '+252 63 555 0777', 'sex': 'Male',
            'email': f'upload-{cls.run_tag}-{seq}@example.com',
            'purpose': 'Employment',
            'guardian_name': 'Guardian Upload', 'guardian_relationship': 'Uncle',
            'guardian_id': 'GD-7700', 'guardian_occupation': 'Teacher',
            'guardian_phone': '+252 63 555 0778',
        }
        status, payload = harness.multipart_request(
            cls.base, '/api/clearance-applications', cls.tokens['fp.officer'],
            fields=fields,
            files={'doc_app_0': ('passport-scan.pdf', REAL_PDF),
                   'doc_app_1': ('national-id.pdf', REAL_PDF),
                   'doc_guard_0': ('guardian-id.pdf', REAL_PDF),
                   'doc_guard_1': ('guardian-letter.pdf', REAL_PDF)})
        assert status in (200, 201), (status, payload)
        application_id = payload['application_id']
        status, record = harness.request(
            cls.base, 'GET', f'/api/clearance-applications/{application_id}',
            cls.tokens['fp.officer'])
        assert status == 200, (status, record)
        docs = record.get('applicant_docs') or record.get('documents') or []
        if isinstance(docs, str):
            import json as _json
            docs = _json.loads(docs)
        assert docs, f'no document recorded on the application: {record}'
        path = docs[0]['path'] if isinstance(docs[0], dict) else docs[0]
        assert path.startswith('/uploads/'), path
        return path

    # ---------------------------------------------------------------- 1 ----
    def test_01_anonymous_access_is_refused(self):
        status, body, _ = raw_get(self.base + self.doc_path)
        self.assertEqual(status, 401,
                         'an anonymous caller must not receive an uploaded document '
                         f'(got {status})')
        self.assertNotIn(b'%PDF', body,
                         'the 401 response must not contain the document bytes')

    def test_02_anonymous_access_to_every_stored_file_is_refused(self):
        """Not just the known path: nothing in the uploads directory is public."""
        stored = [n for n in os.listdir(self.uploads)] if os.path.isdir(self.uploads) else []
        self.assertTrue(stored, 'expected at least one stored upload')
        for name in stored:
            status, body, _ = raw_get(f'{self.base}/uploads/{name}')
            self.assertEqual(status, 401, f'/uploads/{name} must require authentication')

    # ---------------------------------------------------------------- 2 ----
    def test_03_authenticated_owner_can_read_the_document(self):
        status, body, headers = raw_get(self.base + self.doc_path,
                                        token=self.tokens['fp.officer'])
        self.assertEqual(status, 200, 'the filing officer must still be able to read it')
        self.assertTrue(body.startswith(b'%PDF'), 'the real document must be returned')
        self.assertEqual(headers.get('X-Content-Type-Options'), 'nosniff',
                         'stored documents must not be MIME-sniffed')
        self.assertIn('sandbox', headers.get('Content-Security-Policy', ''),
                      'stored documents must be served sandboxed')

    def test_04_session_cookie_also_authenticates(self):
        """The browser fetches <img src="/uploads/..."> with the cookie only."""
        status, payload = harness.request(self.base, 'POST', '/api/login', body={
            'username': 'fp.officer', 'password': PASSWORD})
        self.assertEqual(status, 200, payload)
        status, body, _ = raw_get(self.base + self.doc_path,
                                  cookie=f"sentinel_session={payload['token']}")
        self.assertEqual(status, 200,
                         'cookie-authenticated image loads must keep working')
        self.assertTrue(body.startswith(b'%PDF'))

    # ---------------------------------------------------------------- 3 ----
    def test_05_forged_token_is_refused(self):
        for bogus in ('', 'not-a-token', secrets.token_hex(32), 'Bearer'):
            status, _, _ = raw_get(self.base + self.doc_path, token=bogus)
            self.assertEqual(status, 401,
                             f'a forged token ({bogus!r}) must not unlock a document')

    def test_06_revoked_session_is_refused(self):
        """Logging out must immediately close access to stored documents."""
        status, payload = harness.request(self.base, 'POST', '/api/login', body={
            'username': 'fp.officer', 'password': PASSWORD})
        self.assertEqual(status, 200, payload)
        token = payload['token']
        self.assertEqual(raw_get(self.base + self.doc_path, token=token)[0], 200)
        harness.request(self.base, 'POST', '/api/logout', token)
        self.assertEqual(raw_get(self.base + self.doc_path, token=token)[0], 401,
                         'a logged-out token must not keep reading documents')

    # ---------------------------------------------------------------- 4 ----
    def test_07_cross_branch_access_is_measured_and_recorded(self):
        """A checkpoint officer from another branch probes the document.

        This asserts the CURRENT, HONEST state. Authentication is enforced
        (WP-08), but per-file branch authorisation is not implemented, because
        the stored documents carry no ownership link back to a branch
        (finding N-6 — they live in a JSON blob on the owning row). Adding
        that link is a schema change and was NOT made in Stage 0.

        If a later work package implements per-file authorisation, this test
        will fail and must be updated to assert 403 — that is deliberate.
        """
        status, body, _ = raw_get(self.base + self.doc_path,
                                  token=self.tokens['cp.east'])
        self.assertIn(status, (200, 403),
                      f'unexpected status for a cross-branch read: {status}')
        if status == 403:
            self.skipTest('per-file branch authorisation now enforced — '
                          'update this test to assert 403 unconditionally')
        self.assertEqual(
            status, 200,
            'KNOWN REMAINING EXPOSURE (documented in the Stage 0 report): any '
            'authenticated officer can read any uploaded document regardless of '
            'branch. Authentication is fixed; per-file authorisation needs the '
            'document-ownership schema change described in finding N-6.')

    # ---------------------------------------------------------------- 5 ----
    def _upload_attempt(self, filename, content):
        """Try to attach `content` as `filename` to a new application."""
        seq = secrets.token_hex(2)
        fields = {
            'first_name': 'Upload', 'second_name': 'Validation', 'third_name': 'Probe',
            'fourth_name': seq.upper(), 'date_of_birth': '1992-03-03',
            'national_id': f'{secrets.randbelow(10**8):08d}',
            'mother_name': 'Hooyo Probe', 'residence': 'Hargeisa',
            'phone': '+252 63 555 0779', 'sex': 'Male',
            'email': f'probe-{self.run_tag}-{seq}@example.com',
            'purpose': 'Employment',
            'guardian_name': 'Guardian Probe', 'guardian_relationship': 'Uncle',
            'guardian_id': 'GD-7701', 'guardian_occupation': 'Teacher',
            'guardian_phone': '+252 63 555 0780',
        }
        # The submission is otherwise COMPLETE and valid: two real applicant
        # documents and two real guardian documents. The probe file is the only
        # variable, so a 400 can only be caused by the probe itself and never
        # by a missing-document rule.
        files = {
            'doc_app_0': ('valid-one.pdf', REAL_PDF),
            'doc_app_1': ('valid-two.pdf', REAL_PDF),
            'doc_guard_0': ('guardian-id.pdf', REAL_PDF),
            'doc_guard_1': ('guardian-letter.pdf', REAL_PDF),
            'doc_app_2': (filename, content),
        }
        return harness.multipart_request(
            self.base, '/api/clearance-applications', self.tokens['fp.officer'],
            fields=fields, files=files)

    def assert_rejected_for_the_file(self, status, payload, filename):
        """A 400 that is genuinely about the probe file, not about anything else."""
        self.assertEqual(status, 400,
                         f'{filename} must be refused, got {status}: {payload}')
        message = str(payload.get('error', payload))
        self.assertNotIn('are required', message,
                         f'{filename} was refused for the wrong reason: {message}')

    def test_08_dangerous_extensions_are_refused(self):
        hostile = {
            'payload.html': b'<html><script>fetch("/api/users")</script></html>',
            'payload.svg': b'<svg xmlns="http://www.w3.org/2000/svg"><script>1</script></svg>',
            'shell.php': b'<?php system($_GET["c"]); ?>',
            'tool.exe': b'MZ\x90\x00\x03',
            'notes.txt': b'plain text',
            'archive.zip': b'PK\x03\x04',
            'page.xhtml': b'<html/>',
        }
        for name, content in hostile.items():
            status, payload = self._upload_attempt(name, content)
            self.assert_rejected_for_the_file(status, payload, name)

    def test_09_double_extension_is_judged_on_the_last_one(self):
        status, payload = self._upload_attempt('invoice.pdf.html', b'<html>x</html>')
        self.assert_rejected_for_the_file(status, payload, 'invoice.pdf.html')

    def test_10_content_must_match_the_extension(self):
        status, payload = self._upload_attempt('disguised.pdf', b'<html><script>1</script></html>')
        self.assert_rejected_for_the_file(status, payload, 'disguised.pdf')
        self.assertIn('does not match', str(payload.get('error', '')),
                      'the refusal must name the content/extension mismatch')

    def test_11_oversized_files_are_refused(self):
        oversized = REAL_PDF + b'\x00' * (server.UPLOAD_MAX_BYTES + 1)
        status, payload = self._upload_attempt('huge.pdf', oversized)
        self.assert_rejected_for_the_file(status, payload, 'huge.pdf')

    def test_11b_empty_uploads_never_reach_disk(self):
        """An empty file part is discarded by the multipart parser before it
        reaches save_upload (measured, not assumed), and save_upload refuses
        empty content directly for every other caller."""
        status, payload = self._upload_attempt('empty.pdf', b'')
        self.assertIn(status, (200, 201),
                      'an empty part is dropped by the parser, so the rest of the '
                      f'submission is still valid: {payload}')
        for name in os.listdir(self.uploads):
            full = os.path.join(self.uploads, name)
            self.assertGreater(os.path.getsize(full), 0,
                               f'{name} is a zero-byte file and must not exist')
        # Direct check of the validator itself — raises before anything is written.
        with self.assertRaises(ValueError):
            server.save_upload({'filename': 'empty.pdf', 'content': b''})

    def test_12_genuine_documents_are_still_accepted(self):
        for name, content in (('scan.pdf', REAL_PDF), ('photo.jpg', REAL_JPEG)):
            status, payload = self._upload_attempt(name, content)
            self.assertIn(status, (200, 201),
                          f'{name} is a legitimate document and must be accepted: {payload}')

    def test_13_no_executable_or_markup_file_reached_disk(self):
        stored = os.listdir(self.uploads) if os.path.isdir(self.uploads) else []
        for name in stored:
            ext = os.path.splitext(name)[1].lower()
            self.assertIn(ext, server.UPLOAD_ALLOWED_EXTS,
                          f'{name} should never have been written to the uploads directory')
            mode = os.stat(os.path.join(self.uploads, name)).st_mode
            self.assertFalse(mode & 0o111, f'{name} must not be executable')

    # ---------------------------------------------------------------- 6 ----
    def test_14_path_traversal_is_refused(self):
        for probe in ('/uploads/../backend/server.py',
                      '/uploads/..%2fbackend%2fserver.py',
                      '/uploads/....//server.py'):
            status, body, _ = raw_get(self.base + probe, token=self.tokens['admin'])
            self.assertNotEqual(status, 200,
                                f'{probe} must not return a file outside uploads/')
            self.assertNotIn(b'UPLOAD_ALLOWED_EXTS', body,
                             f'{probe} leaked server source')


if __name__ == '__main__':
    unittest.main(verbosity=2)

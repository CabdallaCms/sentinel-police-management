#!/usr/bin/env python3
"""Tests for the Sentinel checkpoint traveler-screening backend.

Runs against a live (in-process) instance of backend/server.py with a
throwaway SQLite database. Only the Python standard library is used.

Run from the project root:

    python3 -m unittest backend.test_checkpoint -v
"""
import io, json, os, shutil, sqlite3, sys, tempfile, threading, unittest, urllib.request, urllib.error, uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import server as srv  # backend/server.py (standard library only)


def encode_multipart(fields, files):
    """Build a multipart/form-data body. `files` maps name -> (filename, bytes)."""
    boundary = '----SentinelBoundary' + uuid.uuid4().hex
    body = io.BytesIO()
    for k, v in fields.items():
        body.write(('--%s\r\n' % boundary).encode())
        body.write(('Content-Disposition: form-data; name="%s"\r\n\r\n' % k).encode())
        body.write((v if isinstance(v, str) else str(v)).encode())
        body.write(b'\r\n')
    for k, (filename, content) in files.items():
        body.write(('--%s\r\n' % boundary).encode())
        body.write(('Content-Disposition: form-data; name="%s"; filename="%s"\r\n'
                    % (k, filename)).encode())
        body.write(b'Content-Type: application/octet-stream\r\n\r\n')
        body.write(content)
        body.write(b'\r\n')
    body.write(('--%s--\r\n' % boundary).encode())
    return body.getvalue(), 'multipart/form-data; boundary=%s' % boundary


class CheckpointBackendTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = tempfile.mkdtemp()
        srv.DB_PATH = os.path.join(cls.tmp, 'sentinel.db')
        srv.UPLOAD_DIR = os.path.join(cls.tmp, 'uploads')
        srv.init_db()
        cls.httpd = srv.ThreadingHTTPServer(('127.0.0.1', 0), srv.API)
        cls.port = cls.httpd.server_address[1]
        cls.thread = threading.Thread(target=cls.httpd.serve_forever, daemon=True)
        cls.thread.start()
        cls.token = cls._req('POST', '/api/login',
                             json.dumps({'username': 'admin', 'password': 'ChangeMe123!'}))[1]['token']

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()
        cls.httpd.server_close()
        shutil.rmtree(cls.tmp, ignore_errors=True)

    @staticmethod
    def _req(method, path, body=None, content_type='application/json', token=None):
        url = 'http://127.0.0.1:%d%s' % (CheckpointBackendTest.port, path)
        headers = {}
        if content_type:
            headers['Content-Type'] = content_type
        token = token if token is not None else getattr(CheckpointBackendTest, 'token', None)
        if token:
            headers['Authorization'] = 'Bearer ' + token
        data = body.encode() if isinstance(body, str) else body
        req = urllib.request.Request(url, data=data, headers=headers, method=method)
        try:
            with urllib.request.urlopen(req) as resp:
                payload = resp.read()
                return resp.status, json.loads(payload) if payload else {}
        except urllib.error.HTTPError as e:
            payload = e.read()
            try:
                return e.code, json.loads(payload) if payload else {}
            except Exception:
                return e.code, {'raw': payload.decode('utf-8', 'replace')}

    def _submit(self, **overrides):
        fields = {
            'full_name': 'Test Traveler', 'mother_name': 'Test Mother',
            'date_of_birth': '1995-01-01', 'place_of_birth': 'Hargeisa',
            'current_address': 'Hargeisa', 'permanent_address': 'Hargeisa',
            'purpose_of_visit': 'Transit', 'location': 'South',
            'guardian_name': 'Test Guardian', 'guardian_relationship': 'Father',
            'guardian_contact': '+252 63 000 0000', 'guardian_address': 'Hargeisa',
            'guardian_occupation': 'Trader',
        }
        fields.update(overrides)
        files = {
            'doc_trav_0': ('trav.pdf', b'%PDF-traveler'),
            'doc_guard_0': ('guard.pdf', b'%PDF-guardian'),
        }
        body, ctype = encode_multipart(fields, files)
        return self._req('POST', '/api/checkpoint-stops', body, content_type=ctype)

    def test_01_seed_screening_flag(self):
        status, data = self._req('GET', '/api/checkpoint-stops')
        self.assertEqual(status, 200)
        self.assertTrue(any(s['person_id'] == 'P-0002' and s['screening_result'] == 'Flagged match'
                            for s in data['items']))

    def test_02_duplicate_search_autofill_source(self):
        status, data = self._req('GET', '/api/persons?q=Ayaan')
        self.assertEqual(status, 200)
        self.assertTrue(any(p['person_id'] == 'P-0001' for p in data['items']))
        status, data = self._req('GET', '/api/persons?q=10067890')
        self.assertEqual(status, 200)
        self.assertTrue(any(p['person_id'] == 'P-0002' for p in data['items']))

    def test_03_guardian_search(self):
        status, data = self._req('GET', '/api/guardian-search?q=yuusuf')
        self.assertEqual(status, 200)
        self.assertTrue(any(g['name'] == 'Yuusuf Axmed' for g in data['items']))

    def test_04_suspect_instant_alert(self):
        status, data = self._submit(full_name='Maxamed Nuur Cali', mother_name='Khadra Jaamac',
                                    date_of_birth='1989-11-02', national_id='10067890',
                                    location='South')
        self.assertEqual(status, 201)
        self.assertTrue(data['alerted'])
        self.assertEqual(data['screening_result'], 'Flagged match')
        self.assertEqual(data['action_taken'], 'Supervisor contacted')
        self.assertIsNotNone(data['notification_id'])
        # A notification must have been recorded for the match.
        status, nlist = self._req('GET', '/api/alert-notifications')
        self.assertTrue(any(n['notification_id'] == data['notification_id'] for n in nlist['items']))

    def test_05_no_id_traveler_created_and_merged(self):
        status, first = self._submit(full_name='Liibaan Yuusuf Warsame', mother_name='Cawo',
                                     date_of_birth='2002-05-11', location='East')
        self.assertEqual(status, 201)
        self.assertFalse(first['alerted'])
        self.assertEqual(first['screening_result'], 'No active alert')
        # Submitting the same traveler again must merge to the same central person.
        status, second = self._submit(full_name='Liibaan Yuusuf Warsame', mother_name='Cawo',
                                      date_of_birth='2002-05-11', location='West')
        self.assertEqual(status, 201)
        self.assertEqual(second['person_id'], first['person_id'])

    def test_06_passport_lookup_links_existing_person(self):
        status, data = self._submit(full_name='Ayaan Cabdi Xasan', passport_id='P0011223',
                                    location='West')
        self.assertEqual(status, 201)
        self.assertEqual(data['person_id'], 'P-0001')

    def test_07_validation_rules(self):
        # At least one traveler document is mandatory.
        fields = {'full_name': 'X', 'location': 'South', 'guardian_name': 'G'}
        body, ctype = encode_multipart(fields, {'doc_guard_0': ('g.pdf', b'x')})
        status, _ = self._req('POST', '/api/checkpoint-stops', body, content_type=ctype)
        self.assertEqual(status, 400)
        # Guardian name mandatory.
        fields = {'full_name': 'X', 'location': 'South'}
        body, ctype = encode_multipart(fields, {'doc_trav_0': ('t.pdf', b'x'),
                                                'doc_guard_0': ('g.pdf', b'x')})
        status, _ = self._req('POST', '/api/checkpoint-stops', body, content_type=ctype)
        self.assertEqual(status, 400)
        # Location mandatory.
        fields = {'full_name': 'X', 'guardian_name': 'G'}
        body, ctype = encode_multipart(fields, {'doc_trav_0': ('t.pdf', b'x'),
                                                'doc_guard_0': ('g.pdf', b'x')})
        status, _ = self._req('POST', '/api/checkpoint-stops', body, content_type=ctype)
        self.assertEqual(status, 400)

    def test_08_acknowledge_notification(self):
        status, nlist = self._req('GET', '/api/alert-notifications')
        self.assertTrue(nlist['items'])
        nid = nlist['items'][0]['notification_id']
        status, data = self._req('POST', '/api/alert-notifications/%s/acknowledge' % nid, '{}')
        self.assertEqual(status, 201)
        self.assertTrue(data['acknowledged'])
        status, nlist = self._req('GET', '/api/alert-notifications')
        row = next(n for n in nlist['items'] if n['notification_id'] == nid)
        self.assertEqual(row['acknowledged'], 1)

    def test_09_stop_detail(self):
        status, nlist = self._req('GET', '/api/checkpoint-stops')
        sid = nlist['items'][0]['stop_id']
        status, detail = self._req('GET', '/api/checkpoint-stops/' + sid)
        self.assertEqual(status, 200)
        self.assertEqual(detail['stop_id'], sid)
        self.assertIn('guardian_name', detail)


class MigrationTest(unittest.TestCase):
    """The central registry must accept travelers without a National ID."""

    def test_persons_national_id_becomes_nullable(self):
        tmp = tempfile.mkdtemp()
        try:
            legacy = os.path.join(tmp, 'legacy.db')
            c = sqlite3.connect(legacy)
            c.execute('''CREATE TABLE persons(
              id INTEGER PRIMARY KEY, person_id TEXT UNIQUE NOT NULL,
              full_name TEXT NOT NULL, national_id TEXT UNIQUE NOT NULL,
              date_of_birth TEXT, phone TEXT, mother_name TEXT, place_of_birth TEXT,
              residence TEXT, occupation TEXT, passport_id TEXT, photo_path TEXT,
              created_at TEXT DEFAULT CURRENT_TIMESTAMP, updated_at TEXT DEFAULT CURRENT_TIMESTAMP)''')
            c.execute("INSERT INTO persons(person_id,full_name,national_id) VALUES('P-1','Old Person','111')")
            c.execute("CREATE TABLE users(id INTEGER PRIMARY KEY, username TEXT UNIQUE NOT NULL, display_name TEXT NOT NULL, role TEXT NOT NULL, branch TEXT NOT NULL, password_hash TEXT NOT NULL, active INTEGER DEFAULT 1)")
            c.execute("INSERT INTO users(username,display_name,role,branch,password_hash) VALUES('admin','A','Administrator','HQ','x')")
            c.commit(); c.close()

            old_db, old_uploads = srv.DB_PATH, srv.UPLOAD_DIR
            try:
                srv.DB_PATH = legacy
                srv.UPLOAD_DIR = os.path.join(tmp, 'uploads')
                srv.init_db()
                conn = sqlite3.connect(legacy)
                info = {r[1]: r for r in conn.execute('PRAGMA table_info(persons)')}
                self.assertEqual(info['national_id'][3], 0)  # NOT NULL dropped
                self.assertIn('permanent_address', info)
                self.assertEqual(conn.execute('SELECT COUNT(*) FROM persons').fetchone()[0], 1)
                conn.close()
            finally:
                srv.DB_PATH, srv.UPLOAD_DIR = old_db, old_uploads
        finally:
            shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    unittest.main(verbosity=2)

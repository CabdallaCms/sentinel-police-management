#!/usr/bin/env python3
"""Field-level RBAC and clearance certificate print-lock integration tests.

Runs against a throwaway PostgreSQL cluster provisioned with `pgserver`
(never an operational database) and the real backend on a free port.

Verifies two mandated rules end to end over HTTP:

  1. PERSON FIELD-LEVEL RBAC — a regular officer may change only the mutable
     contact fields (phone / residence / occupation) on an existing person.
     Any protected biographic/legal identity change (names, date of birth,
     place of birth, mother's name, National ID, Passport ID, photo) is
     refused with 403 `field_edit_forbidden`, atomically, and the row stays
     untouched. An unchanged echo of the record keeps working (so an older
     client cannot break), and Administrators / SystemAdmins may edit every
     field. The read-only Commander is still refused by the global firewall.

  2. CERTIFICATE PRINT LOCK — an approved certificate reports
     `certificate_print.unlocked = false` for a regular officer until the
     scanned signed application document is uploaded; uploading it flips the
     flag for that officer. Administrators bypass the lock, and the view-only
     Commander role keeps read-only print access.

Usage:
    python3 -m venv .venv
    .venv/bin/pip install psycopg2-binary pgserver
    .venv/bin/python backend/test_field_level_rbac.py
"""
import os
import secrets
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import test_review_gate as harness
import server


class FieldLevelRbacTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='sentinel-field-rbac-')
        env = {k: v for k, v in os.environ.items()
               if not k.startswith('SENTINEL_DB_') and k != 'SENTINEL_DATABASE_URL'}
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
        log = open(os.path.join(cls.temp.name, 'server.log'), 'w+')
        cls.addClassCleanup(log.close)
        proc = subprocess.Popen([sys.executable, harness.SERVER],
            env={**os.environ, **db_env, 'PORT': str(port),
                 'SENTINEL_NO_PORT_TAKEOVER': '1',
                 'SENTINEL_UPLOADS': os.path.join(cls.temp.name, 'uploads')},
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
        for name in ('admin', 'fp.officer', 'chief'):
            status, payload = harness.request(cls.base, 'POST', '/api/login', body={
                'username': name, 'password': 'ChangeMe123!'})
            assert status == 200, payload
            cls.tokens[name] = payload['token']
        cls.run_tag = secrets.token_hex(3)

    # ---- helpers -----------------------------------------------------------
    @classmethod
    def create_person(cls, suffix):
        """Insert a synthetic person directly and return its person_id."""
        pid = f'P-FIELD-{cls.run_tag}-{suffix}'
        token = secrets.token_hex(3)
        conn = server.get_db_connection()
        try:
            conn.execute(
                'INSERT INTO persons(person_id,full_name,first_name,second_name,third_name,'
                'fourth_name,national_id,passport_id,date_of_birth,place_of_birth,mother_name,'
                'phone,residence,occupation) '
                'VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)',
                (pid, 'Field Rbac Person', 'Field', 'Rbac', 'Person', suffix.upper(),
                 f'NID-{cls.run_tag}-{suffix}', f'PP-{cls.run_tag}-{suffix}',
                 '1990-01-01', 'Lasanod', 'Hooyo Field', '+252 63 000 0001',
                 'Lasanod, Sool', 'Trader'))
            conn.commit()
        finally:
            conn.close()
        return pid

    def patch(self, account, person_id, body):
        return harness.request(self.base, 'PATCH', f'/api/persons/{person_id}',
                               self.tokens.get(account), body)

    def read_person(self, person_id):
        status, payload = harness.request(self.base, 'GET', f'/api/persons/{person_id}',
                                          self.tokens['admin'])
        self.assertEqual(status, 200, payload)
        return payload

    def certificate_print_flag(self, account, application_id):
        status, payload = harness.request(
            self.base, 'GET', f'/api/clearance-applications/{application_id}',
            self.tokens[account])
        self.assertEqual(status, 200, payload)
        self.assertIn('certificate_print', payload)
        return payload

    def new_application(self):
        seq = secrets.token_hex(2)
        fields = {
            'first_name': 'Print', 'second_name': 'Lock', 'third_name': 'Test',
            'fourth_name': seq.upper(), 'date_of_birth': '1993-04-04',
            'national_id': f'{secrets.randbelow(10**8):08d}',
            'mother_name': 'Hooyo Print', 'residence': 'Hargeisa',
            'phone': '+252 63 555 0910', 'sex': 'Female',
            'email': f'print-{self.run_tag}-{seq}@example.com', 'purpose': 'Employment',
            'guardian_name': 'Guardian Print', 'guardian_relationship': 'Aunt',
            'guardian_id': 'GD-9900', 'guardian_occupation': 'Teacher',
            'guardian_address': 'Burao', 'guardian_phone': '+252 63 555 0911',
        }
        files = {
            'photo': ('applicant-photo.jpg', b'\xff\xd8\xff\xe0sentinel-test-photo'),
            'doc_app_0': ('a1.pdf', b'%PDF-a1'),
            'doc_app_1': ('a2.pdf', b'%PDF-a2'),
            'doc_guard_0': ('g1.pdf', b'%PDF-g1'),
            'doc_guard_1': ('g2.pdf', b'%PDF-g2'),
        }
        status, payload = harness.multipart_request(
            self.base, '/api/clearance-applications', self.tokens['fp.officer'],
            fields, files)
        self.assertEqual(status, 201, payload)
        return payload

    def approve(self, application_id):
        status, payload = harness.request(
            self.base, 'POST',
            f'/api/fingerprint/applications/{application_id}/approve',
            self.tokens['admin'], {})
        self.assertEqual(status, 201, payload)
        self.assertTrue(payload.get('certificate_number'), payload)
        return payload

    # ---- 1. person field-level RBAC ---------------------------------------
    def test_01_officer_may_edit_mutable_contact_fields(self):
        pid = self.create_person('mutable')
        status, payload = self.patch('fp.officer', pid, {
            'phone': '+252 63 888 1111',
            'residence': 'Burao, Togdheer',
            'occupation': 'Farmer',
        })
        self.assertEqual(status, 200, payload)
        person = self.read_person(pid)
        self.assertEqual(person['phone'], '+252 63 888 1111')
        self.assertEqual(person['residence'], 'Burao, Togdheer')
        self.assertEqual(person['occupation'], 'Farmer')
        print('ok 1: regular officer -> phone / residence / occupation updated (200)')

    def test_02_officer_identity_edits_are_refused_atomically(self):
        pid = self.create_person('identity')
        before = self.read_person(pid)
        attempts = {
            'first_name': 'Changed',
            'full_name': 'Changed Legal Name',
            'date_of_birth': '1980-12-31',
            'place_of_birth': 'Mogadishu',
            'mother_name': 'Changed Mother',
            'national_id': f'NID-HIJACK-{self.run_tag}',
            'passport_id': f'PP-HIJACK-{self.run_tag}',
            'photo_path': '/uploads/hijacked.jpg',
        }
        for field, value in attempts.items():
            with self.subTest(field=field):
                status, payload = self.patch('fp.officer', pid, {field: value})
                self.assertEqual(status, 403, (field, status, payload))
                self.assertEqual(payload.get('code'), 'field_edit_forbidden', payload)
                self.assertIn(field, payload.get('restricted_fields', []), payload)
                self.assertEqual(payload.get('editable_fields'),
                                 ['phone', 'residence', 'occupation'], payload)
        # A combined change is refused as a whole: the phone is not applied.
        status, payload = self.patch('fp.officer', pid, {
            'first_name': 'Changed', 'phone': '+252 63 888 2222'})
        self.assertEqual(status, 403, payload)
        after = self.read_person(pid)
        self.assertEqual(after['first_name'], before['first_name'])
        self.assertEqual(after['national_id'], before['national_id'])
        self.assertEqual(after['passport_id'], before['passport_id'])
        self.assertEqual(after['phone'], before['phone'],
                         'a rejected identity change must not persist the phone either')
        print('ok 2: officer identity edits -> 403 field_edit_forbidden, row untouched, atomic')

    def test_03_unchanged_identity_echo_is_allowed(self):
        pid = self.create_person('echo')
        current = self.read_person(pid)
        status, payload = self.patch('fp.officer', pid, {
            'first_name': current['first_name'],
            'second_name': current['second_name'],
            'third_name': current['third_name'],
            'fourth_name': current['fourth_name'],
            'full_name': current['full_name'],
            'national_id': current['national_id'],
            'passport_id': current['passport_id'],
            'date_of_birth': current['date_of_birth'],
            'mother_name': current['mother_name'],
            'place_of_birth': current['place_of_birth'],
            'phone': '+252 63 888 3333',
        })
        self.assertEqual(status, 200, payload)
        self.assertEqual(self.read_person(pid)['phone'], '+252 63 888 3333')
        print('ok 3: unchanged identity echo + phone update -> 200 (backward compatible)')

    def test_04_administrator_may_edit_every_field(self):
        pid = self.create_person('admin')
        update = {
            'first_name': 'Admin', 'second_name': 'Edited', 'third_name': 'Every',
            'fourth_name': 'Field', 'full_name': 'Admin Edited Every Field',
            'date_of_birth': '1991-02-03', 'place_of_birth': 'Burao',
            'mother_name': 'Mother Admin', 'national_id': f'NID-ADMIN-{self.run_tag}',
            'passport_id': f'PP-ADMIN-{self.run_tag}', 'phone': '+252 63 111 2222',
            'residence': 'Burco', 'occupation': 'Officer',
            'photo_path': '/uploads/admin-updated.jpg',
        }
        status, payload = self.patch('admin', pid, update)
        self.assertEqual(status, 200, payload)
        person = self.read_person(pid)
        for field, value in update.items():
            self.assertEqual(person[field], value, field)
        # The spec's 'admin' alias resolves to the same authority.
        status, payload = self.patch('admin', pid, {'first_name': 'AdminAlias'})
        self.assertEqual(status, 200, payload)
        print('ok 4: Admin / SystemAdmin -> every biographic and legal field editable')

    def test_05_read_only_commander_is_still_refused(self):
        pid = self.create_person('chief')
        status, payload = self.patch('chief', pid, {'phone': '+252 63 444 0000'})
        self.assertEqual(status, 403, payload)
        self.assertEqual(payload.get('code'), 'read_only_role', payload)
        print('ok 5: Commander / High Command -> 403 read_only_role (global firewall)')

    # ---- 2. certificate print lock ---------------------------------------
    def test_06_certificate_print_lock_and_admin_bypass(self):
        created = self.new_application()
        aid = created['application_id']
        self.approve(aid)

        officer_view = self.certificate_print_flag('fp.officer', aid)
        state = officer_view['certificate_print']
        self.assertEqual(state['unlocked'], False, state)
        self.assertEqual(state['locked'], True, state)
        self.assertEqual(state['signed_scan_present'], False, state)
        self.assertEqual(state['admin_bypass'], False, state)
        self.assertIn('signed', state['reason'].lower())
        self.assertEqual(officer_view['status'], 'Approved')
        self.assertTrue(officer_view['certificate_number'])

        admin_state = self.certificate_print_flag('admin', aid)['certificate_print']
        self.assertEqual(admin_state['unlocked'], True, admin_state)
        self.assertEqual(admin_state['admin_bypass'], True, admin_state)
        self.assertIn('bypass', admin_state['reason'].lower())

        chief_state = self.certificate_print_flag('chief', aid)['certificate_print']
        self.assertEqual(chief_state['unlocked'], True, chief_state)
        self.assertEqual(chief_state['read_only_bypass'], True, chief_state)

        # The register row carries the same per-caller verdict.
        status, register = harness.request(
            self.base, 'GET', '/api/clearance-applications', self.tokens['fp.officer'])
        self.assertEqual(status, 200, register)
        listed = next(item for item in register['items']
                      if item['application_id'] == aid)
        self.assertEqual(listed['certificate_print']['unlocked'], False, listed)
        self.assertFalse(listed['signed_scan_present'], listed)

        # Uploading the scanned signed application unlocks printing for the
        # officer (never for an anonymous caller — that path 401s elsewhere).
        status, scanned = harness.multipart_request(
            self.base, f'/api/clearance-applications/{aid}/signed-document',
            self.tokens['fp.officer'],
            files={'signed_application_document': ('signed-application.pdf',
                                                   b'%PDF-signed-print-lock')})
        self.assertEqual(status, 201, scanned)
        unlocked = self.certificate_print_flag('fp.officer', aid)['certificate_print']
        self.assertEqual(unlocked['unlocked'], True, unlocked)
        self.assertEqual(unlocked['signed_scan_present'], True, unlocked)
        self.assertFalse(unlocked['admin_bypass'], unlocked)

        status, register = harness.request(
            self.base, 'GET', '/api/clearance-applications', self.tokens['fp.officer'])
        listed = next(item for item in register['items']
                      if item['application_id'] == aid)
        self.assertEqual(listed['certificate_print']['unlocked'], True, listed)
        print('ok 6: certificate print locked for officers until the signed scan is '
              'uploaded; Admin + view-only command bypass')

    def test_07_applicant_photograph_is_an_image_document(self):
        created = self.new_application()
        status, detail = harness.request(
            self.base, 'GET', f"/api/clearance-applications/{created['application_id']}",
            self.tokens['fp.officer'])
        self.assertEqual(status, 200, detail)
        photo = detail.get('applicant_photo') or ''
        self.assertTrue(photo.lower().endswith('.jpg'), detail)
        person_id = detail.get('applicant_person_id') or detail['person_id']
        status, docs = harness.request(
            self.base, 'GET', f'/api/persons/{person_id}/documents',
            self.tokens['fp.officer'])
        self.assertEqual(status, 200, docs)
        # The application photograph is stored on the application and (for a
        # newly-created person) also as the registry profile photograph. The
        # document manifest de-duplicates that shared path, so assert the path
        # is exposed as a readable image document under either category.
        photo_docs = [d for d in docs['documents'] if d.get('path') == photo]
        self.assertTrue(photo_docs, 'the applicant photograph must be listed as a document')
        self.assertIn(photo_docs[0].get('category'),
                      ('Applicant photograph', 'Profile photograph'), photo_docs)
        self.assertTrue(photo_docs[0]['path'].lower().endswith('.jpg'), photo_docs)
        print('ok 7: applicant photograph is exposed as an image attachment (jpg path)')


if __name__ == '__main__':
    unittest.main(verbosity=2)

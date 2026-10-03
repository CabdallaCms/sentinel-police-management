"""End-to-end HTTP tests: a real server thread, real sockets, real commits."""
import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from datetime import date, timedelta

import psycopg2

from app import server
from .base import DbCase

AYAAN = dict(first_name='Ayaan', second_name='Cabdi', third_name='Xasan', fourth_name='Axmed',
             date_of_birth='1990-05-17', place_of_birth='Laascaanood', national_id='SO1001', mother_name='Hodan Cali')


class TestHttp(DbCase):
    DBNAME = 'sentinel_identity_http'

    @classmethod
    def setUpClass(cls):
        super().setUpClass()
        os.environ['SENTINEL_DATABASE_URL'] = cls.uri
        os.environ['SENTINEL_DEV_AUTH'] = '1'
        cls.srv = server.make_server('127.0.0.1', 0)
        cls.base = f'http://127.0.0.1:{cls.srv.server_address[1]}'
        cls.thread = threading.Thread(target=cls.srv.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.srv.shutdown()
        cls.srv.server_close()

    def setUp(self):
        super().setUp()
        self.cur.execute('TRUNCATE persons, ref_sequences, audit_events RESTART IDENTITY CASCADE')
        self.conn.commit()

    # ---- client ------------------------------------------------------------------
    def call(self, method, path, body=None, user='ap.officer', unit='AP-LAA'):
        headers = {'Content-Type': 'application/json'}
        if user:
            headers['X-Dev-User'] = user
        if unit:
            headers['X-Unit'] = unit
        req = urllib.request.Request(self.base + path, method=method, headers=headers,
                                     data=json.dumps(body).encode() if body is not None else None)
        try:
            with urllib.request.urlopen(req) as r:
                raw = r.read()
                return r.status, (json.loads(raw) if r.headers['Content-Type'].startswith('application/json') else raw)
        except urllib.error.HTTPError as e:
            raw = e.read()
            return e.code, (json.loads(raw) if raw[:1] == b'{' else raw)

    def register(self, person=None, user='fp.officer', unit='DIR-FP', **extra):
        return self.call('POST', '/api/persons', {'person': person or AYAAN, **extra}, user, unit)

    # ---- tests -------------------------------------------------------------------
    def test_health_is_open_and_everything_else_requires_a_user(self):
        self.assertEqual(self.call('GET', '/api/health', user=None, unit=None)[0], 200)
        for path in ('/api/me', '/api/persons/search?q=x', '/api/field-policy'):
            self.assertEqual(self.call('GET', path, user=None, unit=None)[0], 401, path)
        self.assertEqual(self.call('GET', '/api/me', user='ghost', unit=None)[0], 401)

    def test_auth_fails_closed_when_dev_auth_is_off(self):
        os.environ['SENTINEL_DEV_AUTH'] = '0'
        try:
            self.assertEqual(self.call('GET', '/api/me')[0], 401)
            self.assertEqual(self.call('GET', '/api/dev/users', user=None, unit=None)[0], 404)
        finally:
            os.environ['SENTINEL_DEV_AUTH'] = '1'

    def test_a_unit_outside_the_officers_assignments_is_refused(self):
        s, b = self.call('GET', '/api/me', unit='CP-SOUTH')                         # ap.officer is only at AP-LAA
        self.assertEqual((s, b['error']), (403, 'unit_not_allowed'))

    def test_me_lists_only_the_officers_units_and_abilities(self):
        s, b = self.call('GET', '/api/me', user='ap.officer', unit=None)
        self.assertEqual((s, [u['code'] for u in b['units']]), (200, ['AP-LAA']))
        self.assertEqual((b['abilities']['can_register'], b['abilities']['is_national_admin']), (True, False))
        s, b = self.call('GET', '/api/me', user='admin', unit=None)
        self.assertTrue(b['abilities']['is_national_admin'])
        s, b = self.call('GET', '/api/me', user='chief', unit=None)
        self.assertEqual((b['abilities']['can_register'], b['abilities']['can_search']), (False, True))

    def test_full_intake_journey_new_then_exists_at_a_second_unit(self):
        s, b = self.call('POST', '/api/persons/search', {'query': AYAAN})
        self.assertEqual((s, b['status'], b['exists']), (200, 'new', False))
        s, b = self.register()
        self.assertEqual((s, b['created']), (201, True))
        ref = b['person']['person_ref']
        # airport officer searches: the master profile already exists -> banner data
        s, b = self.call('POST', '/api/persons/search', {'query': AYAAN})
        self.assertEqual((s, b['status'], b['exists'], b['auto_select'], b['tier']), (200, 'exists', True, True, 1))
        self.assertEqual(b['person']['person_ref'], ref)
        self.assertEqual(b['person']['field_states']['first_name']['state'], 'locked')
        # airport registers the same person again with new details: linked, not duplicated
        s, b = self.register({**AYAAN, 'residence': 'Laascaanood', 'occupation': 'Teacher'}, 'ap.officer', 'AP-LAA')
        self.assertEqual((s, b['created'], b['person']['person_ref']), (200, False, ref))
        self.assertEqual(sorted(b['filled']), ['occupation', 'residence'])
        self.assertEqual(self.one('SELECT count(*) FROM persons'), 1)
        # dates travel as ISO strings
        self.assertEqual(b['person']['date_of_birth'], '1990-05-17')

    def test_quick_search_box(self):
        self.register()
        s, b = self.call('GET', '/api/persons/search?q=so-1001')
        self.assertEqual((s, b['status']), (200, 'exists'))
        s, b = self.call('GET', '/api/persons/search?q=ayaan%20cabdi')
        self.assertEqual((b['status'], b['candidates'][0]['full_name']), ('suggestions', 'Ayaan Cabdi Xasan Axmed'))

    def test_possible_duplicate_is_a_409_with_the_candidates_then_confirm_or_link(self):
        ref = self.register()[1]['person']['person_ref']
        typo = {**AYAAN, 'second_name': 'Cabdii', 'national_id': 'SO5555'}
        s, b = self.register(typo, 'ap.officer', 'AP-LAA')
        self.assertEqual((s, b['error']), (409, 'possible_duplicate'))
        self.assertEqual(b['search']['person']['person_ref'], ref)
        self.assertEqual(self.one('SELECT count(*) FROM persons'), 1)
        s, b = self.register(typo, 'ap.officer', 'AP-LAA', link_person_ref=ref)
        self.assertEqual((s, b['created']), (200, False))
        s, b = self.register(typo, 'ap.officer', 'AP-LAA', confirm_new=True)
        self.assertEqual((s, b['created']), (201, True))

    def test_locked_field_edit_is_403_with_field_detail_and_nothing_changes(self):
        ref = self.register()[1]['person']['person_ref']
        s, b = self.call('PATCH', f'/api/persons/{ref}', {'changes': {'date_of_birth': '1999-01-01', 'occupation': 'x'},
                                                          'reason': 'because'})
        self.assertEqual((s, b['error']), (403, 'field_locked'))
        self.assertEqual([f['field'] for f in b['fields']], ['date_of_birth'])
        s, b = self.call('GET', f'/api/persons/{ref}')
        self.assertEqual((b['date_of_birth'], b['occupation']), ('1990-05-17', None))

    def test_dynamic_fields_and_enrichment_over_http(self):
        ref = self.register()[1]['person']['person_ref']
        s, b = self.call('PATCH', f'/api/persons/{ref}', {'changes': {'residence': 'Caynabo', 'occupation': 'Driver'}})
        self.assertEqual((s, sorted(b['filled'])), (200, ['occupation', 'residence']))
        s, b = self.call('PATCH', f'/api/persons/{ref}', {'changes': {'residence': 'Burao'}}, 'cp.south', 'CP-SOUTH')
        self.assertEqual((s, b['updated']), (200, ['residence']))

    def test_only_the_national_admin_corrects_core_identity_and_needs_a_reason(self):
        ref = self.register()[1]['person']['person_ref']
        patch = lambda body, user: self.call('PATCH', f'/api/persons/{ref}', body, user, None)
        self.assertEqual(patch({'changes': {'first_name': 'Ayaana'}, 'reason': 'r'}, 'fp.officer')[0], 403)
        self.assertEqual(patch({'changes': {'first_name': 'Ayaana'}, 'reason': 'r'}, 'cid.officer')[0], 403)
        self.assertEqual(patch({'changes': {'first_name': 'Ayaana'}, 'reason': 'r'}, 'chief')[0], 403)
        s, b = patch({'changes': {'first_name': 'Ayaana'}}, 'admin')
        self.assertEqual((s, b['error']), (422, 'validation_error'))
        s, b = patch({'changes': {'first_name': 'Ayaana'}, 'reason': 'Typo on birth certificate'}, 'admin')
        self.assertEqual((s, b['person']['full_name']), (200, 'Ayaana Cabdi Xasan Axmed'))
        self.assertEqual(self.one("SELECT reason FROM person_field_audit WHERE field='first_name' AND kind='change'"),
                         'Typo on birth certificate')

    def test_validation_errors_are_422_with_field_names(self):
        s, b = self.register({**AYAAN, 'date_of_birth': 'tomorrow'})
        self.assertEqual((s, b['error']), (422, 'validation_error'))
        self.assertIn('date_of_birth', json.dumps(b['fields']))

    def test_guardian_added_later_at_another_unit(self):
        dob = (date.today() - timedelta(days=365 * 6)).isoformat()
        child = {'first_name': 'Hodan', 'second_name': 'Nuur', 'third_name': 'Cali', 'date_of_birth': dob}
        s, b = self.register(child, allow_no_id=True)
        self.assertEqual(s, 201)
        self.assertIn('guardian', [m['field'] for m in b['person']['missing_fields']])
        ref = b['person']['person_ref']
        s, b = self.call('POST', f'/api/persons/{ref}/guardians',
                         {'guardian': {'first_name': 'Cabdi', 'second_name': 'Faarax', 'third_name': 'Cali',
                                       'national_id': 'SO900', 'phone': '+252 63 1'}, 'relationship': 'Parent'})
        self.assertEqual((s, b['link_created']), (201, True))
        self.assertEqual(b['person']['guardians'][0]['relationship'], 'Parent')
        self.assertNotIn('guardian', [m['field'] for m in b['person']['missing_fields']])

    def test_read_only_chief_commander_over_http(self):
        self.register()
        self.assertEqual(self.call('POST', '/api/persons/search', {'query': AYAAN}, 'chief', None)[1]['status'], 'exists')
        s, b = self.register({**AYAAN, 'first_name': 'Zed', 'second_name': 'Other', 'third_name': 'Name', 'national_id': 'SO42'},
                             'chief', None)
        self.assertEqual((s, b['error']), (403, 'permission_denied'))

    def test_bad_requests(self):
        self.assertEqual(self.call('POST', '/api/persons', {'nope': 1})[0], 400)
        self.assertEqual(self.call('GET', '/api/persons/not-a-ref')[0], 404)
        self.assertEqual(self.call('GET', '/api/persons/P-2026-999999')[0], 404)
        self.assertEqual(self.call('DELETE', '/api/persons/P-2026-000001')[0], 404)

    def test_static_ui_is_served_and_cannot_escape_the_web_directory(self):
        s, b = self.call('GET', '/', user=None, unit=None)
        self.assertEqual(s, 200)
        self.assertIn(b'Central Person Registry', b)
        self.assertEqual(self.call('GET', '/../app/server.py', user=None, unit=None)[0], 404)
        self.assertEqual(self.call('GET', '/%2e%2e/app/server.py', user=None, unit=None)[0], 404)


if __name__ == '__main__':
    unittest.main()

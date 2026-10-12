#!/usr/bin/env python3
"""Scoped identity provenance integration tests against throwaway PostgreSQL.
Run: python backend/test_linked_records.py (psycopg2-binary + pgserver).
Never uses an operational/configured database.
"""
import os
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

import test_review_gate as harness
import server


class LinkedRecordsTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temp = tempfile.TemporaryDirectory(prefix='sentinel-linked-')
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
            env={**os.environ, **db_env, 'PORT': str(port), 'SENTINEL_NO_PORT_TAKEOVER': '1',
                 'SENTINEL_UPLOADS': os.path.join(cls.temp.name, 'uploads')}, stdout=log, stderr=log)
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
        for name in ('admin', 'fp.officer', 'ap.officer', 'cid.officer', 'cp.south', 'cp.east', 'chief'):
            status, payload = harness.request(cls.base, 'POST', '/api/login', body={
                'username': name, 'password': 'ChangeMe123!'})
            assert status == 200, payload
            cls.tokens[name] = payload['token']
        c = server.get_db_connection()
        try:
            uid = c.execute("SELECT id FROM users WHERE username='admin'").fetchone()['id']
            pid = c.execute("INSERT INTO persons(person_id,full_name,residence) VALUES "
                            "('P-PROVENANCE','Provenance Test','Lasanod, Sool') RETURNING id").fetchone()['id']
            c.execute("INSERT INTO persons(person_id,full_name) VALUES ('P-EMPTY','No Links')")
            branches = {r['unit_type']: r['id'] for r in c.execute(
                "SELECT id,unit_type FROM police_branches WHERE region='Sool'").fetchall()}
            c.execute("""INSERT INTO airport_passengers(record_id,person_id,branch_id,movement,
                travel_date,flight_number,route,origin_city,destination_city,created_by)
                VALUES ('AR-PROV',%s,%s,'Arrival','2026-10-09','AA-1','Berbera / Lasanod','Berbera','Lasanod',%s)""",
                (pid, branches['airport'], uid))
            c.execute("""INSERT INTO clearance_applications(application_id,person_id,branch_id,purpose,created_by)
                VALUES ('FP-PROV',%s,%s,'Citizenship',%s)""", (pid, branches['fingerprint'], uid))
            c.execute("""INSERT INTO clearance_applications(application_id,person_id,purpose)
                VALUES ('FP-LEGACY',%s,'Education')""", (pid,))
            cid = c.execute("""INSERT INTO crime_cases(case_id,branch_id,category,location,created_by)
                VALUES ('CID-PROV',%s,'Theft','Recorded incident location',%s) RETURNING id""",
                (branches['crime'], uid)).fetchone()['id']
            c.execute("""INSERT INTO suspect_alerts(alert_id,person_id,case_id,created_by)
                VALUES ('SA-PROV',%s,%s,%s)""", (pid, cid, uid))
            for location in ('South', 'East'):
                c.execute("""INSERT INTO checkpoint_events(event_id,person_id,branch_id,location,
                    location_code,screening_result,created_by) VALUES (%s,%s,%s,%s,%s,'Clear',%s)""",
                    ('CP-'+location, pid, branches['checkpoint'], location, location, uid))
            c.commit()
        finally:
            c.close()

    def get(self, account='admin', person='P-PROVENANCE'):
        return harness.request(self.base, 'GET', f'/api/persons/{person}/linked-records',
                               self.tokens.get(account))

    def test_all_sources_and_legacy(self):
        status, data = self.get()
        self.assertEqual(status, 200)
        self.assertEqual(len(data['items']), 6)
        self.assertEqual(self.get('chief')[1]['items'], data['items'])
        self.assertEqual(data['residence'], 'Lasanod, Sool')
        self.assertIsNone(data['nearby_branch'])
        self.assertIn('historical', data['proximity_note'])
        records = {row['record_id']: row for row in data['items']}
        for rid in ('AR-PROV', 'FP-PROV', 'SA-PROV', 'CP-South', 'CP-East'):
            self.assertEqual(records[rid]['branch_name'], 'Lasanod Branch')
            self.assertEqual(records[rid]['branch_region'], 'Sool')
            self.assertTrue(records[rid]['uploaded_by'])
            self.assertTrue(records[rid]['uploader_branch'])
            self.assertIn('current account', records[rid]['uploader_source'])
        self.assertEqual(records['AR-PROV']['location_context'], 'Berbera → Lasanod')
        self.assertEqual(records['AR-PROV']['branch_source'], 'airport_passengers.branch_id')
        self.assertIn('via suspect_alerts.case_id', records['SA-PROV']['branch_source'])
        self.assertIsNone(records['FP-LEGACY']['branch_name'])
        self.assertIsNone(records['FP-LEGACY']['uploaded_by'])

    def test_unit_and_checkpoint_scope(self):
        expected = {'fp.officer': {'FP-PROV', 'FP-LEGACY'}, 'ap.officer': {'AR-PROV'},
                    'cid.officer': {'SA-PROV'}, 'cp.south': {'CP-South'}, 'cp.east': {'CP-East'}}
        for account, ids in expected.items():
            with self.subTest(account=account):
                status, data = self.get(account)
                self.assertEqual(status, 200)
                self.assertEqual({r['record_id'] for r in data['items']}, ids)

    def test_empty_unknown_and_unauthenticated(self):
        status, data = self.get(person='P-EMPTY')
        self.assertEqual(status, 200)
        self.assertEqual(data['items'], [])
        self.assertEqual(self.get(person='P-DOES-NOT-EXIST')[0], 404)
        self.assertEqual(self.get(account='anonymous')[0], 401)


if __name__ == '__main__':
    unittest.main(verbosity=2)

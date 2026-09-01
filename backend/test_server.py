#!/usr/bin/env python3
"""Regression tests for the Sentinel backend.

Standard library only. Starts the API against a temporary SQLite database,
then verifies the identity-resolution tiers, optional suspect case linking,
auto-create behaviour and the migrations.

Usage:
    python3 backend/test_server.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(ROOT, 'server.py')


def free_port():
    s = socket.socket()
    s.bind(('127.0.0.1', 0))
    port = s.getsockname()[1]
    s.close()
    return port


def request(base, method, path, token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=data, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def main():
    port = free_port()
    tmp = tempfile.mkdtemp(prefix='sentinel-test-')
    db_path = os.path.join(tmp, 'test.db')
    env = dict(os.environ, SENTINEL_DB=db_path, PORT=str(port), SENTINEL_UPLOADS=os.path.join(tmp, 'uploads'))
    proc = subprocess.Popen([sys.executable, SERVER], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(50):
            try:
                status, _ = request(base, 'GET', '/api/health')
                if status == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('server did not start')

        status, login = request(base, 'POST', '/api/login',
                                body={'username': 'admin', 'password': 'ChangeMe123!'})
        assert status == 200 and login.get('token'), 'login failed'
        token = login['token']

        def resolve(payload):
            return request(base, 'POST', '/api/persons/resolve', token, payload)[1]

        # Tier 1 — exact national ID
        r = resolve({'first_name': 'Ayaan', 'second_name': 'Cabdi', 'third_name': 'Xasan',
                     'fourth_name': 'Axmed', 'date_of_birth': '1997-04-18',
                     'national_id': '10012345', 'mother_name': 'Faadumo Cali'})
        assert r['matched'] and r['tier'] == 1 and r['person']['person_id'] == 'P-0001', r

        # Tier 1 — exact passport, case-insensitive
        r = resolve({'first_name': 'A', 'second_name': 'B', 'third_name': 'C',
                     'fourth_name': 'D', 'passport_id': 'p0011223'})
        assert r['matched'] and r['tier'] == 1 and r['person']['person_id'] == 'P-0001', r

        # Tier 2 — 4-part name + DOB
        r = resolve({'first_name': 'Maxamed', 'second_name': 'Nuur', 'third_name': 'Cali',
                     'fourth_name': 'Awil', 'date_of_birth': '1989-11-02',
                     'mother_name': 'Khadra Jaamac'})
        assert r['matched'] and r['tier'] == 2 and r['person']['person_id'] == 'P-0002', r

        # Tier 3 — 3-part name + mother (fuzzy, candidates returned)
        r = resolve({'first_name': 'Maxamed', 'second_name': 'Nuur', 'third_name': 'Cali',
                     'fourth_name': 'Farah', 'date_of_birth': '1990-01-01',
                     'mother_name': 'Khadra Jaamac', 'national_id': '', 'passport_id': ''})
        assert r['matched'] and r['tier'] == 3 and r['candidates'], r

        # No match
        r = resolve({'first_name': 'Zakariye', 'second_name': 'Xasan', 'third_name': 'Cali',
                     'fourth_name': 'Axmed', 'date_of_birth': '2000-01-01',
                     'national_id': '90909090', 'mother_name': 'Maryan Cali'})
        assert not r['matched'] and r['tier'] == 0, r

        # Flexible matching: 3-part name only -> single strong partial match (Tier 4)
        r = resolve({'first_name': 'Maxamed', 'second_name': 'Nuur', 'third_name': 'Cali'})
        assert r['matched'] and r['tier'] == 4 and r['person']['person_id'] == 'P-0002', r
        assert any(s['person_id'] == 'P-0002' for s in r['suggestions']), r

        # Flexible matching: 2-part name only -> suggestions (no auto match)
        r = resolve({'first_name': 'Ayaan', 'second_name': 'Cabdi'})
        assert not r['matched'] and r['tier'] == 0, r
        assert any(s['person_id'] == 'P-0001' for s in r['suggestions']), r

        # Flexible matching: case-insensitive + whitespace trimmed
        r = resolve({'first_name': '  ayaan  ', 'second_name': 'CABDI', 'third_name': ' xasan '})
        assert r['matched'] and r['tier'] == 4 and r['person']['person_id'] == 'P-0001', r

        # Flexible matching: partial passport prefix appears in suggestions
        r = resolve({'passport_id': 'p0011'})
        assert any(s['person_id'] == 'P-0001' for s in r['suggestions']), r

        # 4-part name without DOB still surfaces the partial match
        r = resolve({'first_name': 'Sahra', 'second_name': 'Yuusuf', 'third_name': 'Axmed',
                     'fourth_name': 'Aadan'})
        assert r['matched'] and r['tier'] == 4 and r['person']['person_id'] == 'P-0003', r

        # Suspect WITHOUT a case -> origin recorded, person auto-created
        s, r = request(base, 'POST', '/api/suspect-alerts', token, {
            'first_name': 'Zakariye', 'second_name': 'Xasan', 'third_name': 'Cali',
            'fourth_name': 'Axmed', 'date_of_birth': '2000-01-01', 'national_id': '90909090',
            'mother_name': 'Maryan Cali', 'residence': 'Hargeisa 1',
            'origin': 'Direct Intelligence Listing', 'notes': 'market sighting'})
        assert s == 201 and r['case_id'] is None and r['origin'] == 'Direct Intelligence Listing', r
        zak_pid = r['person_id']

        # Duplicate no-case suspect -> 409
        s2, _ = request(base, 'POST', '/api/suspect-alerts', token, {
            'first_name': 'Zakariye', 'second_name': 'Xasan', 'third_name': 'Cali',
            'fourth_name': 'Axmed', 'date_of_birth': '2000-01-01', 'national_id': '90909090',
            'mother_name': 'Maryan Cali', 'residence': 'Hargeisa 1', 'origin': 'Manual Entry'})
        assert s2 == 409, s2

        # Suspect linked to a case -> Case Link origin
        s, r = request(base, 'POST', '/api/suspect-alerts', token, {
            'first_name': 'Ayaan', 'second_name': 'Cabdi', 'third_name': 'Xasan',
            'fourth_name': 'Axmed', 'date_of_birth': '1997-04-18', 'national_id': '10012345',
            'mother_name': 'Faadumo Cali', 'residence': 'Hargeisa, Jigjiga Yar',
            'case_id': 'CID-2026-009', 'role': 'Suspect'})
        assert s == 201 and r['case_id'] == 'CID-2026-009' and r['origin'] == 'Case Link', r

        # Suspect list exposes the case code (or null) for no-case listings
        s, r = request(base, 'GET', '/api/suspect-alerts', token)
        assert s == 200, r
        items = r['items']
        assert any(x['case_id'] == 'CID-2026-009' for x in items), items
        assert any(x['person_id'] == zak_pid and x['case_id'] is None
                   and x['origin'] == 'Direct Intelligence Listing' for x in items), items

        # Checkpoint stop for a direct-listed suspect -> Flagged match
        s, r = request(base, 'POST', '/api/checkpoint-events', token, {
            'first_name': 'Zakariye', 'second_name': 'Xasan', 'third_name': 'Cali',
            'fourth_name': 'Axmed', 'date_of_birth': '2000-01-01', 'national_id': '90909090',
            'mother_name': 'Maryan Cali', 'residence': 'Hargeisa 1',
            'location': 'West', 'notes': 'pickup truck'})
        assert s == 201 and r['screening_result'] == 'Flagged match' \
            and r['action_taken'] == 'Supervisor contacted', r

        # Airport record auto-creates the central person
        s, r = request(base, 'POST', '/api/airport-records', token, {
            'first_name': 'Hodan', 'second_name': 'Cali', 'third_name': 'Faarax',
            'fourth_name': 'Axmed', 'date_of_birth': '1996-06-06', 'national_id': '90909091',
            'mother_name': 'Amina', 'residence': 'Hargeisa 2', 'movement': 'Departure',
            'travel_date': '2026-09-02', 'flight_number': 'HL-301', 'route': 'Hargeisa / Bosaso'})
        assert s == 201 and r['identity']['person_id'], r
        hodan_pid = r['identity']['person_id']
        s, r = request(base, 'GET', '/api/airport-records', token)
        assert any(x['person_id'] == hodan_pid for x in r['items']), r

        # Person upsert merges on Tier 2 (no duplicate)
        s, r = request(base, 'POST', '/api/persons/upsert', token, {
            'first_name': 'Sahra', 'second_name': 'Yuusuf', 'third_name': 'Axmed',
            'fourth_name': 'Aadan', 'date_of_birth': '2001-02-26', 'mother_name': 'Amina Maxamed',
            'residence': 'Hargeisa, 26 June', 'occupation': 'Student',
            'phone': '+252 63 555 0144'})
        assert s == 201 and r['person']['person_id'] == 'P-0003' and r['created'] is False, r

        # Invalid case -> 400
        s, _ = request(base, 'POST', '/api/suspect-alerts', token, {
            'first_name': 'X', 'second_name': 'Y', 'third_name': 'Z', 'fourth_name': 'W',
            'date_of_birth': '1999-01-01', 'national_id': '90909092', 'mother_name': 'M',
            'residence': 'X', 'case_id': 'CID-9999'})
        assert s == 400, s

        print('ALL BACKEND TESTS PASSED')
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == '__main__':
    sys.exit(main())

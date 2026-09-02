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


def multipart_request(base, path, token=None, fields=None, files=None):
    """POST a multipart/form-data request (fields: {name: value}, files: {name: (filename, bytes)})."""
    boundary = '----sentinel-test-boundary'
    lines = []
    for k, v in (fields or {}).items():
        lines.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"\r\n\r\n{v}\r\n')
    for k, (fn, content) in (files or {}).items():
        lines.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{k}"; filename="{fn}"\r\n'
                     f'Content-Type: application/octet-stream\r\n\r\n')
        lines.append(content)
    lines.append(f'--{boundary}--\r\n')
    body = b''.join(l.encode('utf-8') if isinstance(l, str) else l for l in lines)
    req = urllib.request.Request(base + path, data=body, method='POST')
    req.add_header('Content-Type', f'multipart/form-data; boundary={boundary}')
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

        # Suspect WITHOUT a case and WITHOUT a reason -> 400 (mandatory reason)
        s, r = request(base, 'POST', '/api/suspect-alerts', token, {
            'first_name': 'Zakariye', 'second_name': 'Xasan', 'third_name': 'Cali',
            'fourth_name': 'Axmed', 'date_of_birth': '2000-01-01', 'national_id': '90909090',
            'mother_name': 'Maryan Cali', 'residence': 'Hargeisa 1', 'origin': 'Manual Entry'})
        assert s == 400 and 'reason' in r['error'].lower(), r

        # Suspect WITHOUT a case WITH a reason -> origin recorded, person auto-created
        s, r = request(base, 'POST', '/api/suspect-alerts', token, {
            'first_name': 'Zakariye', 'second_name': 'Xasan', 'third_name': 'Cali',
            'fourth_name': 'Axmed', 'date_of_birth': '2000-01-01', 'national_id': '90909090',
            'mother_name': 'Maryan Cali', 'residence': 'Hargeisa 1',
            'origin': 'Direct Intelligence Listing', 'notes': 'market sighting'})
        assert s == 201 and r['case_id'] is None and r['origin'] == 'Direct Intelligence Listing' \
            and r['reason'] == 'market sighting', r
        zak_pid = r['person_id']

        # Duplicate no-case suspect -> 409
        s2, _ = request(base, 'POST', '/api/suspect-alerts', token, {
            'first_name': 'Zakariye', 'second_name': 'Xasan', 'third_name': 'Cali',
            'fourth_name': 'Axmed', 'date_of_birth': '2000-01-01', 'national_id': '90909090',
            'mother_name': 'Maryan Cali', 'residence': 'Hargeisa 1', 'origin': 'Manual Entry',
            'notes': 'duplicate listing'})
        assert s2 == 409, s2

        # Suspect linked to a case without a reason -> reason defaults to case details
        s, r = request(base, 'POST', '/api/suspect-alerts', token, {
            'first_name': 'Ayaan', 'second_name': 'Cabdi', 'third_name': 'Xasan',
            'fourth_name': 'Axmed', 'date_of_birth': '1997-04-18', 'national_id': '10012345',
            'mother_name': 'Faadumo Cali', 'residence': 'Hargeisa, Jigjiga Yar',
            'case_id': 'CID-2026-009', 'role': 'Suspect'})
        assert s == 201 and r['case_id'] == 'CID-2026-009' and r['origin'] == 'Case Link' \
            and r['reason'] == 'Linked to CID case CID-2026-009 \u2014 Fraud', r

        # Suspect list exposes the case code (or null) for no-case listings
        s, r = request(base, 'GET', '/api/suspect-alerts', token)
        assert s == 200, r
        items = r['items']
        assert any(x['case_id'] == 'CID-2026-009' for x in items), items
        assert any(x['person_id'] == zak_pid and x['case_id'] is None
                   and x['origin'] == 'Direct Intelligence Listing' for x in items), items

        # Checkpoint stop: full traveler + guardian multipart (direct-listed suspect -> Flagged)
        cp_fields = {
            'first_name': 'Zakariye', 'second_name': 'Xasan', 'third_name': 'Cali',
            'fourth_name': 'Axmed', 'date_of_birth': '2000-01-01', 'national_id': '90909090',
            'mother_name': 'Maryan Cali', 'current_address': 'Hargeisa 1', 'permanent_address': 'Burao, Road 4',
            'purpose_of_visit': 'Family visit', 'location': 'West', 'notes': 'pickup truck',
            'guardian_first_name': 'Cabdi', 'guardian_second_name': 'Faarax', 'guardian_third_name': 'Cali',
            'guardian_fourth_name': 'Axmed', 'guardian_relationship': 'Legal Guardian',
            'guardian_phone': '+252 63 555 0777', 'guardian_address': 'Burao, Road 4',
            'guardian_occupation': 'Farmer', 'guardian_national_id': '80808080',
        }
        cp_files = {
            'doc_tr_0': ('ticket.pdf', b'%PDF-traveler'),
            'doc_tr_1': ('hotel.pdf', b'%PDF-hotel'),
            'doc_gd_0': ('guardian_id.pdf', b'%PDF-guardian'),
            'photo': ('traveler.jpg', b'\xff\xd8\xff\xe0fakejpeg'),
        }
        s, r = multipart_request(base, '/api/checkpoint-events', token, cp_fields, cp_files)
        assert s == 201, r
        assert r['screening_result'] == 'Flagged match' and r['action_taken'] == 'Supervisor contacted', r
        assert r['traveler_docs'] == 2 and r['guardian_docs'] == 1, r
        assert r['guardian_person_id'] is None, r  # guardian is stored event-scoped unless centrally known

        # Checkpoint stop: traveler WITHOUT any ID auto-creates a central person
        cp_fields2 = dict(cp_fields)
        cp_fields2['first_name'] = 'Fadumo'; cp_fields2['second_name'] = 'Cali'
        cp_fields2['third_name'] = 'Xasan'; cp_fields2['fourth_name'] = 'Axmed'
        cp_fields2['date_of_birth'] = '1994-09-09'; cp_fields2.pop('national_id', None)
        cp_fields2['current_address'] = 'Hargeisa, Airport Rd'; cp_fields2['location'] = 'East'
        cp_files2 = {'doc_tr_0': ('ticket2.pdf', b'%PDF-traveler2'),
                     'doc_gd_0': ('guardian2.pdf', b'%PDF-guardian2'),
                     'doc_gd_1': ('guardian3.pdf', b'%PDF-guardian3'),
                     'photo': ('traveler2.jpg', b'\xff\xd8\xff\xe0fakejpeg2')}
        s, r2 = multipart_request(base, '/api/checkpoint-events', token, cp_fields2, cp_files2)
        assert s == 201 and r2['identity']['person_id'], r2
        noid_pid = r2['identity']['person_id']
        s, r2 = request(base, 'GET', '/api/persons/' + noid_pid, token)
        assert s == 200 and not r2.get('national_id') and r2['full_name'] == 'Fadumo Cali Xasan Axmed', r2

        # Missing traveler doc / guardian doc / photo -> 400
        s, r = multipart_request(base, '/api/checkpoint-events', token, cp_fields,
                                 {'photo': ('p.jpg', b'x')})
        assert s == 400, r
        s, r = multipart_request(base, '/api/checkpoint-events', token, cp_fields,
                                 {'doc_tr_0': ('t.pdf', b'x'), 'photo': ('p.jpg', b'x')})
        assert s == 400, r

        # Stored checkpoint item exposes traveler + guardian + docs
        s, r = request(base, 'GET', '/api/checkpoint-events', token)
        assert s == 200, r
        item = next(x for x in r['items'] if x['person_id'] == zak_pid)
        assert item['purpose_of_visit'] == 'Family visit' and item['guardian_name'] == 'Cabdi Faarax Cali Axmed', item
        assert item['guardian_relationship'] == 'Legal Guardian' and len(json.loads(item['guardian_docs'])) == 1, item
        assert len(json.loads(item['traveler_docs'])) == 2 and item['traveler_photo'], item

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

        # ---- Central Person enrichment on linked unit records ----
        # New central person (no mother/phone/IDs) created via a checkpoint stop
        cp_enrich = {'first_name': 'Nuradin', 'second_name': 'Cali', 'third_name': 'Faarax',
                     'fourth_name': 'Axmed', 'date_of_birth': '1992-03-03',
                     'current_address': 'Hargeisa 5', 'permanent_address': 'Burao Rd',
                     'purpose_of_visit': 'Business', 'location': 'South',
                     'guardian_first_name': 'Cabdi', 'guardian_second_name': 'Faarax',
                     'guardian_third_name': 'Cali', 'guardian_fourth_name': 'Awil',
                     'guardian_relationship': 'Relative', 'guardian_phone': '+252 63 555 0500',
                     'guardian_address': 'Burao Rd', 'guardian_occupation': 'Driver'}
        cp_enrich_files = {'doc_tr_0': ('t.pdf', b'%PDF-t'),
                           'doc_gd_0': ('g.pdf', b'%PDF-g'),
                           'photo': ('p.jpg', b'\xff\xd8\xff\xe0x')}
        s, r = multipart_request(base, '/api/checkpoint-events', token, cp_enrich, cp_enrich_files)
        assert s == 201, r
        enrich_pid = r['person_id']
        s, p = request(base, 'GET', '/api/persons/' + enrich_pid, token)
        assert s == 200 and not p.get('mother_name') and not p.get('phone'), p

        # Airport links to that person_id and fills missing Mother's name + phone + flight fields
        s, r = request(base, 'POST', '/api/airport-records', token, {
            'person_id': enrich_pid, 'first_name': 'Nuradin', 'second_name': 'Cali',
            'third_name': 'Faarax', 'fourth_name': 'Axmed', 'date_of_birth': '1992-03-03',
            'mother_name': 'Hawa Cali', 'phone': '+252 63 555 0678', 'residence': 'Hargeisa 5',
            'movement': 'Departure', 'travel_date': '2026-09-05', 'flight_number': 'HL-410',
            'airline': 'Sentinel Air', 'origin_city': 'Hargeisa', 'destination_city': 'Bosaso'})
        assert s == 201, r
        s, p = request(base, 'GET', '/api/persons/' + enrich_pid, token)
        assert s == 200 and p.get('mother_name') == 'Hawa Cali', p
        assert p.get('phone') == '+252 63 555 0678', p

        # Airport record persists the module-specific travel fields
        s, ar = request(base, 'GET', '/api/airport-records', token)
        item = next(x for x in ar['items'] if x['person_id'] == enrich_pid)
        assert item['airline'] == 'Sentinel Air' and item['origin_city'] == 'Hargeisa', item
        assert item['destination_city'] == 'Bosaso' and item['movement'] == 'Departure', item

        # Enrichment also works when the unit record resolves by identity (no person_id):
        # a checkpoint person without passport is enriched via the upsert merge path.
        cp_enrich2 = dict(cp_enrich)
        cp_enrich2.update({'first_name': 'Ubax', 'second_name': 'Xasan',
                           'third_name': 'Aadan', 'fourth_name': 'Cali',
                           'date_of_birth': '1988-08-08', 'location': 'West'})
        cp_enrich_files2 = {'doc_tr_0': ('t2.pdf', b'%PDF-t2'),
                            'doc_gd_0': ('g2.pdf', b'%PDF-g2'),
                            'photo': ('p2.jpg', b'\xff\xd8\xff\xe0y')}
        s, r = multipart_request(base, '/api/checkpoint-events', token, cp_enrich2, cp_enrich_files2)
        assert s == 201, r
        enrich_pid2 = r['person_id']
        s, r = request(base, 'POST', '/api/airport-records', token, {
            'first_name': 'Ubax', 'second_name': 'Xasan', 'third_name': 'Aadan',
            'fourth_name': 'Cali', 'date_of_birth': '1988-08-08', 'mother_name': 'Maryan',
            'passport_id': 'P0004567', 'occupation': 'Nurse', 'residence': 'Hargeisa Centre',
            'movement': 'Arrival', 'travel_date': '2026-09-06', 'flight_number': 'HL-515',
            'route': 'Bosaso / Hargeisa'})
        assert s == 201, r
        s, p = request(base, 'GET', '/api/persons/' + enrich_pid2, token)
        assert s == 200 and p.get('passport_id') == 'P0004567', p
        assert p.get('occupation') == 'Nurse', p

        # ---- Name + Passport ONLY (no mother/occupation) -> Airport fills blanks ----
        # Create a person with only the name parts and a passport id.
        s, up = request(base, 'POST', '/api/persons/upsert', token, {
            'first_name': 'Nuur', 'second_name': 'Cali', 'third_name': 'Aadan',
            'fourth_name': 'Xasan', 'date_of_birth': '1987-07-07', 'passport_id': 'P5550011'})
        assert s == 201, up
        blank_pid = up['person']['person_id']
        s, p = request(base, 'GET', '/api/persons/' + blank_pid, token)
        assert s == 200 and not str(p.get('mother_name') or '').strip(), p
        assert not str(p.get('occupation') or '').strip(), p

        # Match in Airport Control (links by person_id + passport) and complete blanks.
        s, r = request(base, 'POST', '/api/airport-records', token, {
            'person_id': blank_pid, 'first_name': 'Nuur', 'second_name': 'Cali',
            'third_name': 'Aadan', 'fourth_name': 'Xasan', 'date_of_birth': '1987-07-07',
            'passport_id': 'P5550011', 'mother_name': 'Hawa Aadan', 'occupation': 'Nurse',
            'residence': 'Hargeisa, Jigjiga Yar', 'movement': 'Departure',
            'travel_date': '2026-09-10', 'flight_number': 'HL-707', 'airline': 'Sentinel Air',
            'origin_city': 'Hargeisa', 'destination_city': 'Bosaso'})
        assert s == 201 and r['identity'].get('matched') and r['identity']['person_id'] == blank_pid, r

        # Central record is enriched with the newly completed blanks (never dup).
        s, p = request(base, 'GET', '/api/persons/' + blank_pid, token)
        assert s == 200 and p.get('mother_name') == 'Hawa Aadan', p
        assert p.get('occupation') == 'Nurse', p
        assert p.get('passport_id') == 'P5550011', p
        s, ar = request(base, 'GET', '/api/airport-records', token)
        item = next(x for x in ar['items'] if x['person_id'] == blank_pid)
        assert item['airline'] == 'Sentinel Air' and item['flight_number'] == 'HL-707', item

        # ---- Role-Based Access Control (RBAC) ----
        # Login each role, verify /api/me reports role + modules + scope.
        roles = {
            'admin':       ('SystemAdmin',     None,   {'admin', 'analytics'}),
            'fp.officer':  ('FingerprintUnit', None,   set()),
            'ap.officer':  ('AirportControl',  None,   set()),
            'cid.officer': ('CIDUnit',         None,   set()),
            'cp.south':    ('CheckpointSouth', 'South', set()),
            'cp.east':     ('CheckpointEast',  'East',  set()),
            'cp.west':     ('CheckpointWest',  'West',  set()),
        }
        tokens = {}
        for u, (role, scope, extras) in roles.items():
            s, r = request(base, 'POST', '/api/login',
                           body={'username': u, 'password': 'ChangeMe123!'})
            assert s == 200 and r['user']['role'] == role, (u, r)
            assert r['user']['location_scope'] == scope, (u, r['user'])
            expected_mods = {'dashboard'}
            if role == 'SystemAdmin':
                expected_mods |= {'admin', 'analytics', 'airport', 'checkpoints',
                                  'cid', 'fingerprint', 'people'}
            elif role == 'FingerprintUnit':
                expected_mods |= {'fingerprint', 'people'}
            elif role == 'AirportControl':
                expected_mods |= {'airport', 'people'}
            elif role == 'CIDUnit':
                expected_mods |= {'cid', 'people'}
            elif role.startswith('Checkpoint'):
                expected_mods |= {'checkpoints'}
            assert set(r['user']['modules']) == expected_mods, (u, r['user'])
            s, me = request(base, 'GET', '/api/me', r['token'])
            assert s == 200 and me['role'] == role, (u, me)
            assert me['visibility']['is_admin'] is (role == 'SystemAdmin')
            assert me['visibility']['can_manage_users'] is (role == 'SystemAdmin')
            assert me['visibility']['can_view_analytics'] is (role == 'SystemAdmin')
            tokens[u] = r['token']

        # Cross-module RBAC: each unit role can only access its own module.
        cases = [
            ('fp.officer',  '/api/airport-records',     401),
            ('fp.officer',  '/api/clearance-applications', 200),
            ('ap.officer',  '/api/clearance-applications', 401),
            ('ap.officer',  '/api/airport-records',     200),
            ('cid.officer', '/api/crime-cases',         200),
            ('cid.officer', '/api/airport-records',     401),
            ('cp.south',    '/api/clearance-applications', 401),
            ('cp.south',    '/api/checkpoint-events',   200),
        ]
        for user, path, expected in cases:
            s, r = request(base, 'GET', path, tokens[user])
            assert s == expected, (user, path, s, r)

        # Admin-only endpoints are rejected for non-admins.
        for user in ('fp.officer', 'cp.south', 'cid.officer'):
            for path in ('/api/admin/users', '/api/admin/analytics'):
                s, r = request(base, 'GET', path, tokens[user])
                assert s == 401, (user, path, s, r)

        # Admins can see all checkpoint events; Checkpoint users only see their location.
        s, admin_cp = request(base, 'GET', '/api/checkpoint-events', tokens['admin'])
        assert s == 200 and admin_cp['scope'] is None, admin_cp
        for u, expected_loc in (('cp.south', 'South'),
                                ('cp.east', 'East'),
                                ('cp.west', 'West')):
            s, r = request(base, 'GET', '/api/checkpoint-events', tokens[u])
            assert s == 200 and r['scope'] == expected_loc, (u, r)
            for ev in r['items']:
                assert ev['location'] == expected_loc, (u, ev)
        # Admin should see at least as many checkpoint events as any one location.
        assert len(admin_cp['items']) >= 1
        # Every admin-visible checkpoint event must now carry the explicit
        # location metadata so the identity profile can render
        # "Checkpoint (South)" instead of a generic "Checkpoint" pill.
        for ev in admin_cp['items']:
            assert ev.get('location_code'), ev
            assert ev.get('checkpoint_location'), ev
            assert ev['checkpoint_location'].endswith('Checkpoint'), ev

        # ---- Role-Scoped Operations Dashboard ----
        # /api/dashboard must be reachable by every authenticated user but
        # the cards / quick actions / activity feed must be strictly
        # filtered to the caller's role and location scope.
        s, d_admin = request(base, 'GET', '/api/dashboard', tokens['admin'])
        assert s == 200, d_admin
        assert d_admin['is_admin'] is True
        assert d_admin['location_scope'] is None
        admin_card_ids = {c['id'] for c in d_admin['cards']}
        assert admin_card_ids == {'central_persons', 'open_cases',
                                  'pending_clearances', 'active_alerts'}, d_admin['cards']
        admin_quick = {q['id'] for q in d_admin['quick_actions']}
        assert admin_quick == {'add_airport', 'add_clearance',
                                'add_case', 'add_checkpoint'}, d_admin['quick_actions']
        # Activity feed for an admin is a cross-unit feed (all 4 modules
        # can be present in the same response).
        admin_mods = {e['module'] for e in d_admin['activity']}
        assert admin_mods & {'fingerprint', 'airport', 'cid', 'checkpoints'}, d_admin['activity']

        s, d_south = request(base, 'GET', '/api/dashboard', tokens['cp.south'])
        assert s == 200, d_south
        assert d_south['is_admin'] is False
        assert d_south['location_scope'] == 'South'
        # Checkpoint users see ONLY location-scoped cards and ONLY the
        # checkpoint quick action. They must never see admin / cross-unit
        # cards or quick actions.
        south_card_ids = {c['id'] for c in d_south['cards']}
        assert south_card_ids == {'cp_screenings_today', 'cp_travelers_flagged',
                                  'cp_total_travelers', 'cp_peak_hour'}, d_south['cards']
        assert {q['id'] for q in d_south['quick_actions']} == {'add_checkpoint'}, d_south['quick_actions']
        # Card labels must explicitly mention 'South' so the officer
        # can see at a glance which location the metrics are for.
        for c in d_south['cards']:
            assert 'South' in c['label'], c
            assert c.get('location_scope') == 'South', c
        # The peak-hour card value is a time-range string like "08:00 – 10:00".
        peak = next(c for c in d_south['cards'] if c['id'] == 'cp_peak_hour')
        assert isinstance(peak['value'], str) and ('–' in peak['value'] or peak['value'] == '—'), peak
        # Activity feed for cp.south must include only checkpoints module
        # entries that match the South location flexibly.
        for e in d_south['activity']:
            assert e['module'] == 'checkpoints', e
            assert e.get('location_code') == 'South', e
            # Real-time feed rows should carry a human-readable time_ago
            # and the actual screened person in the title.
            assert e.get('time_ago') is not None, e
            assert e.get('title'), e
            # The title should mention the screened / flagged name. Seed
            # person is 'Maxamed Nuur Cali Awil' for the only South event.
            assert 'Maxamed' in e['title'] or 'Screened' in e['title'] or 'Flagged' in e['title'], e

        s, d_east = request(base, 'GET', '/api/dashboard', tokens['cp.east'])
        assert s == 200, d_east
        assert d_east['location_scope'] == 'East'
        for c in d_east['cards']:
            assert 'East' in c['label'], c

        # Unit officers see only their module's cards / quick action.
        s, d_fp = request(base, 'GET', '/api/dashboard', tokens['fp.officer'])
        assert s == 200, d_fp
        assert {c['id'] for c in d_fp['cards']} == {'fp_pending', 'fp_today', 'fp_approved', 'fp_total'}, d_fp['cards']
        assert {q['id'] for q in d_fp['quick_actions']} == {'add_clearance'}, d_fp['quick_actions']
        for e in d_fp['activity']:
            assert e['module'] == 'fingerprint', e

        s, d_ap = request(base, 'GET', '/api/dashboard', tokens['ap.officer'])
        assert s == 200, d_ap
        assert {c['id'] for c in d_ap['cards']} == {'ap_today', 'ap_arrivals', 'ap_departures', 'ap_total'}, d_ap['cards']
        assert {q['id'] for q in d_ap['quick_actions']} == {'add_airport'}, d_ap['quick_actions']
        for e in d_ap['activity']:
            assert e['module'] == 'airport', e

        s, d_cid = request(base, 'GET', '/api/dashboard', tokens['cid.officer'])
        assert s == 200, d_cid
        assert {c['id'] for c in d_cid['cards']} == {'cid_open', 'cid_active_alerts', 'cid_cases_today', 'cid_suspects'}, d_cid['cards']
        assert {q['id'] for q in d_cid['quick_actions']} == {'add_case'}, d_cid['quick_actions']
        for e in d_cid['activity']:
            assert e['module'] == 'cid', e

        # ---- /api/dashboard routing resilience ---------------------------
        # Trailing slash, sub-paths and unknown query strings must all
        # still return the dashboard payload — never 404.
        for path in ('/api/dashboard', '/api/dashboard/', '/api/dashboard/summary',
                     '/api/dashboard?range=24h', '/api/dashboard?role=cp.south'):
            s, body = request(base, 'GET', path, tokens['admin'])
            assert s == 200, (path, body)
            assert 'cards' in body and 'activity' in body, (path, body)

        # Missing / invalid auth tokens must return 401 (and never 404),
        # so the frontend can show a proper "please sign in" message.
        s, body = request(base, 'GET', '/api/dashboard')
        assert s == 401, body
        s, body = request(base, 'GET', '/api/dashboard', token='bogus-token-xxx')
        assert s == 401, body

        # ---- Identity Profile: explicit checkpoint location pills ----
        # Find the seeded checkpoint event's person and verify the
        # /api/persons/{person_id} response carries the per-event explicit
        # location metadata so the modal can render "Checkpoint (South)".
        assert admin_cp['items'], 'no checkpoint events seeded'
        susp_pid = admin_cp['items'][0]['person_id']
        s, p2 = request(base, 'GET', f'/api/persons/{susp_pid}', tokens['admin'])
        assert s == 200, p2
        assert p2['checkpoints'], p2
        for ev in p2['checkpoints']:
            assert ev.get('location_code'), ev
            assert ev.get('checkpoint_location'), ev
            assert ev['checkpoint_location'].endswith('Checkpoint'), ev

        # Admin user management: create / update / deactivate.
        s, r = request(base, 'POST', '/api/admin/users', tokens['admin'], {
            'username': 'new.user', 'password': 'secret1',
            'display_name': 'Officer New', 'role': 'CheckpointWest',
            'branch': 'Checkpoint West', 'location_scope': 'West'})
        assert s == 201 and r['user']['role'] == 'CheckpointWest', r
        new_uid = r['user']['id']

        s, r = request(base, 'POST', '/api/admin/users', tokens['admin'], {
            'username': 'new.user', 'password': 'secret1',
            'display_name': 'X', 'role': 'SystemAdmin'})
        assert s == 409, r

        s, r = request(base, 'POST', '/api/admin/users', tokens['admin'], {
            'username': 'bad.role', 'password': 'secret1',
            'display_name': 'X', 'role': 'NotARole'})
        assert s == 400, r

        s, r = request(base, 'POST', '/api/admin/users', tokens['admin'], {
            'username': 'short.pw', 'password': '1',
            'display_name': 'X', 'role': 'SystemAdmin'})
        assert s == 400, r

        s, r = request(base, 'PATCH', f'/api/admin/users/{new_uid}', tokens['admin'],
                       {'display_name': 'Officer Renamed', 'active': False})
        assert s == 200 and r['user']['display_name'] == 'Officer Renamed', r
        assert r['user']['active'] is False, r

        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'new.user', 'password': 'secret1'})
        assert s == 401, r  # deactivated user cannot log in

        s, r = request(base, 'POST', '/api/admin/users', tokens['cp.south'], {
            'username': 'evil', 'password': 'secret1', 'display_name': 'X',
            'role': 'SystemAdmin'})
        assert s == 401, r

        # Analytics: admin only and shape-stable for charts.
        s, analytics = request(base, 'GET', '/api/admin/analytics', tokens['admin'])
        assert s == 200, analytics
        a = analytics
        for key in ('total_central_persons', 'active_suspect_alerts',
                    'airport_movements', 'fingerprint_records', 'checkpoint_events'):
            assert key in a['summary'], a['summary']
        assert 'by_location' in a['crime_distribution']
        assert 'by_time_of_day' in a['crime_distribution']
        for bucket in ('Morning (06-12)', 'Afternoon (12-18)',
                       'Evening (18-24)', 'Night (00-06)'):
            assert any(b['label'] == bucket for b in a['crime_distribution']['by_time_of_day']), a
        assert 'by_location' in a['checkpoint_volume']
        for loc in ('South', 'East', 'West'):
            assert any(b['label'] == loc for b in a['checkpoint_volume']['by_location']), a
        for loc in a['checkpoint_volume']['demographics']:
            for b in a['checkpoint_volume']['demographics'][loc]:
                assert b['label'] in ('<18', '18-30', '31-50', '50+', 'Unknown'), a

        # Checkpoint create: a South officer cannot record an East event.
        cp_south = {'first_name': 'Test', 'second_name': 'A', 'third_name': 'B',
                    'fourth_name': 'C', 'date_of_birth': '2000-01-01',
                    'current_address': 'X', 'permanent_address': 'Y',
                    'purpose_of_visit': 'Family', 'location': 'East',
                    'guardian_first_name': 'G', 'guardian_second_name': 'A',
                    'guardian_third_name': 'B', 'guardian_fourth_name': 'C',
                    'guardian_relationship': 'Father', 'guardian_phone': '+1',
                    'guardian_address': 'X', 'guardian_occupation': 'Worker'}
        cp_files = {'doc_tr_0': ('t.pdf', b'x'), 'doc_gd_0': ('g.pdf', b'x'),
                    'photo': ('p.jpg', b'\xff\xd8\xff\xe0x')}
        s, r = multipart_request(base, '/api/checkpoint-events', tokens['cp.south'],
                                 cp_south, cp_files)
        assert s == 400 and 'assigned location' in r['error'].lower(), r

        # Checkpoint create: cp.south creates a new event at South, it
        # appears in their own /api/checkpoint-events response immediately
        # (and not for cp.east / cp.west).
        cp_south_ok = dict(cp_south)
        cp_south_ok['location'] = 'South'
        s, before = request(base, 'GET', '/api/checkpoint-events', tokens['cp.south'])
        before_ids = {x['event_id'] for x in before['items']}
        s, r = multipart_request(base, '/api/checkpoint-events', tokens['cp.south'],
                                 cp_south_ok, cp_files)
        assert s == 201, r
        new_event_id = r['event_id']
        assert r.get('location_code') == 'South', r
        assert r.get('checkpoint_location') == 'South Checkpoint', r
        s, after = request(base, 'GET', '/api/checkpoint-events', tokens['cp.south'])
        after_ids = {x['event_id'] for x in after['items']}
        assert new_event_id in after_ids, (new_event_id, after_ids)
        # Newly created event must be visible with explicit location metadata.
        new_event = next(x for x in after['items'] if x['event_id'] == new_event_id)
        assert new_event['location_code'] == 'South', new_event
        assert new_event['checkpoint_location'] == 'South Checkpoint', new_event
        # And it must NOT be visible to officers at other checkpoints
        # (cp.east / cp.west). The airport / CID officers do not have
        # access to /api/checkpoint-events at all (module gate returns
        # 401), so we only check the in-scope checkpoint officers.
        for user in ('cp.east', 'cp.west'):
            s, scoped = request(base, 'GET', '/api/checkpoint-events', tokens[user])
            assert s == 200, (user, scoped)
            assert new_event_id not in {x['event_id'] for x in scoped['items']}, (user, scoped)
        # And not via the admin endpoint either — admin can see all
        # events across locations, but cp.south's POST must not duplicate
        # the row at any other location.
        s, all_evs = request(base, 'GET', '/api/checkpoint-events', tokens['admin'])
        all_for_new = [x for x in all_evs['items'] if x['event_id'] == new_event_id]
        assert len(all_for_new) == 1, all_for_new
        assert all_for_new[0]['location_code'] == 'South', all_for_new[0]
        # The new event bumps cp.south's dashboard totals (total travelers
        # is the absolute count of distinct Central Persons screened at the
        # location, so it must include the new traveler).
        s, d_after = request(base, 'GET', '/api/dashboard', tokens['cp.south'])
        unique_card = next(c for c in d_after['cards'] if c['id'] == 'cp_total_travelers')
        assert unique_card['value'] >= 1, unique_card
        # Dashboard activity feed for cp.south must now include the new
        # event with the explicit South Checkpoint title, the South
        # location_code, and a "time_ago" stamp.
        feed = [e for e in d_after['activity'] if e['id'] == new_event_id]
        assert feed, d_after['activity']
        assert 'South Checkpoint' in feed[0]['title'] or 'South Checkpoint' in feed[0].get('subtitle',''), feed[0]
        assert feed[0]['location_code'] == 'South', feed[0]
        assert feed[0].get('time_ago'), feed[0]

        # ----------------------------------------------------------------
        # Session-collision regression test: signing in as cp.south, then
        # logging out, then logging in as admin must NOT leave the admin
        # seeing the South-scoped dashboard. This is the user-reported
        # "Admin sees South Checkpoint Operations" bug. The backend is
        # stateless across sessions, so the regression is exclusively
        # frontend (`db.dashboard` cache); this test guards the contract
        # the frontend relies on: every /api/dashboard response is keyed
        # on the bearer token and reflects the active user, never a
        # previous user.
        # ----------------------------------------------------------------
        s, _ = request(base, 'POST', '/api/login',
                       body={'username': 'cp.south', 'password': 'ChangeMe123!'})
        assert s == 200
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'admin', 'password': 'ChangeMe123!'})
        assert s == 200
        admin_token2 = r['token']
        s, d_admin = request(base, 'GET', '/api/dashboard', admin_token2)
        assert s == 200
        # Admin must see the GLOBAL cards, NOT the South cards.
        admin_card_ids = {c['id'] for c in d_admin['cards']}
        assert admin_card_ids == {'central_persons','open_cases','pending_clearances','active_alerts'}, \
            f"admin cards not global: {admin_card_ids}"
        assert d_admin['is_admin'] is True
        assert d_admin['location_scope'] is None
        # And the quick actions must be all 4 — admin has all of them.
        assert {q['id'] for q in d_admin['quick_actions']} == {'add_airport','add_clearance','add_case','add_checkpoint'}
        # Admin can read all location events including the South one.
        s, cps_admin = request(base, 'GET', '/api/checkpoint-events', admin_token2)
        assert s == 200
        assert any(e['event_id'] == new_event_id for e in cps_admin['items']), \
            "admin must see the South event in the cross-unit /api/checkpoint-events"

        # ----------------------------------------------------------------
        # Immediate-appearance test: cp.south POST then GET must return
        # the new event in the very next response. (Frontend also
        # optimistically pushes it into db.checkpoints, so the user sees
        # it before the network roundtrip completes.)
        # ----------------------------------------------------------------
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'cp.south', 'password': 'ChangeMe123!'})
        assert s == 200
        south_token2 = r['token']
        f2 = dict(cp_fields)
        f2['first_name'] = 'Faadumo'
        f2['second_name'] = 'Yusuf'
        f2['third_name'] = 'Cabdalle'
        f2['fourth_name'] = 'Cabdi'
        f2['location'] = 'South'  # cp.south is locked to their assigned location
        s2, post2 = multipart_request(base, '/api/checkpoint-events',
                                      token=south_token2, fields=f2, files=cp_files)
        assert s2 == 201, f"second POST failed: {s2} {post2}"
        # Read it back immediately; the new event must be in the list.
        s, cps = request(base, 'GET', '/api/checkpoint-events', south_token2)
        assert s == 200
        assert any(e['event_id'] == post2['event_id'] for e in cps['items']), \
            "newly-posted event must appear in the immediate /api/checkpoint-events response"
        # And must be tagged with location_code='South'.
        new_row = next(e for e in cps['items'] if e['event_id'] == post2['event_id'])
        assert new_row['location_code'] == 'South'
        assert new_row['checkpoint_location'] == 'South Checkpoint'

        print('ALL BACKEND TESTS PASSED')
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == '__main__':
    sys.exit(main())

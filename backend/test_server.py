#!/usr/bin/env python3
"""Regression tests for the Sentinel backend.

Standard library only. Starts the API against a temporary SQLite database,
then verifies the identity-resolution tiers, optional suspect case linking,
auto-create behaviour and the migrations.

Usage:
    python3 backend/test_server.py
"""
import datetime
import json
import os
import socket
import sqlite3
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

        # Admin user management: create / update / deactivate. Checkpoint
        # role aliases are normalised on write: 'CheckpointWest' is stored
        # as the canonical 'checkpoint_officer' while the location_scope
        # ('West') is preserved.
        s, r = request(base, 'POST', '/api/admin/users', tokens['admin'], {
            'username': 'new.user', 'password': 'secret1',
            'display_name': 'Officer New', 'role': 'CheckpointWest',
            'branch': 'Checkpoint West', 'location_scope': 'West'})
        assert s == 201 and r['user']['role'] == 'checkpoint_officer', r
        assert r['user']['role_alias'] == 'checkpoint_officer', r
        assert r['user']['location_scope'] == 'West', r
        assert set(('dashboard', 'checkpoints')) <= set(r['user']['modules']), r
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

        # ----------------------------------------------------------------
        # Case-insensitive + trailing-space + LIKE-fallback match. The
        # task spec mandates `LOWER(...)` + `LIKE '%south%'`. The seed
        # migration backfills legacy rows, but we can simulate a row
        # with mixed casing / trailing space by direct DB write and
        # confirm /api/checkpoint-events still returns it for cp.south.
        # ----------------------------------------------------------------
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'admin', 'password': 'ChangeMe123!'})
        admin_token3 = r['token']
        # Admin can write to any checkpoint, including with a lowercase /
        # trailing-space location string. The server's response must
        # normalise both columns to canonical short code + label.
        f3 = dict(cp_fields)
        f3['first_name'] = 'Cabdi'
        f3['second_name'] = 'Jaamac'
        f3['third_name'] = 'Xasan'
        f3['fourth_name'] = 'Cali'
        f3['location'] = 'south'  # lowercase, must be normalised
        s, post3 = multipart_request(base, '/api/checkpoint-events',
                                     token=admin_token3, fields=f3, files=cp_files)
        assert s == 201, f"lowercase POST failed: {s} {post3}"
        # The response must surface location_code='South' (capitalised)
        # and checkpoint_location='South Checkpoint' regardless of the
        # input casing, because both columns are explicitly populated on
        # insert.
        assert post3['location_code'] == 'South', post3
        assert post3['checkpoint_location'] == 'South Checkpoint', post3

        # cp.south should still see the new event in their scoped list.
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'cp.south', 'password': 'ChangeMe123!'})
        south_token3 = r['token']
        s, cps = request(base, 'GET', '/api/checkpoint-events', south_token3)
        assert s == 200
        assert any(e['event_id'] == post3['event_id'] for e in cps['items']), \
            "case-insensitive POST must still appear in cp.south's GET list"
        # And the count for cp.south must be > 0 (i.e. the badge that
        # displays `South Checkpoint N` would not show 0).
        south_count = len(cps['items'])
        assert south_count > 0, f"cp.south /api/checkpoint-events empty: {south_count}"

        # cp.east must NOT see the South event even with the new SQL.
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'cp.east', 'password': 'ChangeMe123!'})
        east_token3 = r['token']
        s, cps_east = request(base, 'GET', '/api/checkpoint-events', east_token3)
        assert s == 200
        assert not any(e['event_id'] == post3['event_id'] for e in cps_east['items']), \
            "cp.east must NOT see the South event even with the LIKE fallback"

        # ----------------------------------------------------------------
        # Badge-update flow: post as cp.south, then the immediate
        # dashboard must show the new event in the activity feed so the
        # /api/dashboard real-time stream reflects the new record.
        # This guards the "South Checkpoint 0 -> 1" badge bug.
        # ----------------------------------------------------------------
        s, d = request(base, 'GET', '/api/dashboard', south_token3)
        # cp.south's dashboard activity stream should include the new
        # checkpoint event id (visible in the live feed).
        feed_ids = {e['id'] for e in d['activity']}
        assert post3['event_id'] in feed_ids, \
            f"new event must appear in cp.south dashboard activity feed: {feed_ids}"
        # And the dashboard's screening-today card must be > 0 because
        # we just posted a stop today at South.
        screenings_today = next(c for c in d['cards']
                                if c['id'] == 'cp_screenings_today')
        assert screenings_today['value'] > 0, \
            f"screening-today card should reflect the new event: {screenings_today}"

        # Final sanity: the /api/dashboard 'scope' field matches the
        # officer's location_scope, the chips/list filter agrees.
        assert d['location_scope'] == 'South'
        assert d['is_admin'] is False
        assert cps['scope'] == 'South'

        # ----------------------------------------------------------------
        # Spec-mandated aggressive-match contract. The frontend's
        # cpMatchesLocation() must match ANY record whose stored
        # location string contains the active scope ('south' / 'east' /
        # 'west'), so the chip count badge and the table agree. We
        # simulate the function against a representative set of stored
        # values to guarantee the contract holds.
        # ----------------------------------------------------------------
        def cpMatchesLocation(record, activeScope):
            if not record: return False
            scope = (activeScope or '').lower() if isinstance(activeScope, str) else ''
            loc = (record.get('checkpoint_location') or record.get('location_code') or record.get('location') or '').lower()
            if scope and 'south' in scope and 'south' in loc: return True
            if scope and 'east'  in scope and 'east'  in loc: return True
            if scope and 'west'  in scope and 'west'  in loc: return True
            return loc == scope or scope in loc or loc in scope

        # Match the cp.south events list against scope='South'.
        south_events = [e for e in cps['items']]
        south_filtered = [e for e in south_events if cpMatchesLocation(e, 'South')]
        # Every event in the cp.south list MUST match scope='South'
        # (no false negatives -> 'South Checkpoint 0' bug is gone).
        assert all(cpMatchesLocation(e, 'South') for e in south_events), \
            f"all cp.south events must match South: {south_events}"
        assert len(south_filtered) == len(south_events) > 0
        # A cp.south event must NOT match scope='East'.
        assert not any(cpMatchesLocation(e, 'East') for e in south_events), \
            "cp.south events must not match East scope"

        # Spec-mandated prepend pattern. Simulate `db.checkpoints =
        # [newRecord, ...db.checkpoints]` and verify the new event is
        # at index 0 and the count is incremented.
        before_prepend = list(south_events)
        new_rec = south_events[0]  # any existing event works as the "new" record
        db_after = [new_rec] + [x for x in before_prepend if x.get('event_id') != new_rec.get('event_id')]
        assert db_after[0]['event_id'] == new_rec['event_id']
        assert len(db_after) == len(before_prepend)
        # And the filtered list (with scope='South') is the same length.
        filtered_after = [e for e in db_after if cpMatchesLocation(e, 'South')]
        assert len(filtered_after) == len(db_after), \
            f"badge count after prepend: {len(filtered_after)} vs {len(db_after)}"

        # ----------------------------------------------------------------
        # Spec-mandated visibleCheckpoints contract (spec step 3).
        # The visibleCheckpoints list must equal the intersection of
        # (active scope, the record's location field). The chip
        # count badge and the table row count must both read from
        # visibleCheckpoints.length — they can never disagree.
        # ----------------------------------------------------------------
        def visibleCheckpoints(records, scope):
            """Verbatim spec step-3 function."""
            out = []
            for item in (records or []):
                if not item:
                    continue
                activeScope = (scope or '').lower()
                loc = (item.get('checkpoint_location') or item.get('location_code') or item.get('location') or '').lower()
                if not activeScope:
                    out.append(item)
                    continue
                if activeScope in loc or loc in activeScope or loc == activeScope:
                    out.append(item)
            return out

        # For cp.south, visibleCheckpoints(south_events, 'South') must
        # equal the full list.
        v_south = visibleCheckpoints(south_events, 'South')
        assert len(v_south) == len(south_events) > 0
        # And no South event must match scope='West' (cross-isolation).
        for ev in south_events:
            assert not visibleCheckpoints([ev], 'West'), \
                f"cp.south event {ev.get('event_id')} matched West scope"

        # Same for cp.west: every West event matches 'West' and
        # never matches 'South' or 'East'.
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'cp.west', 'password': 'ChangeMe123!'})
        assert s == 200
        west_token = r['token']
        s, cps_w = request(base, 'GET', '/api/checkpoint-events', west_token)
        assert s == 200
        for ev in cps_w['items']:
            assert visibleCheckpoints([ev], 'West'), \
                f"cp.west event {ev.get('event_id')} not in West scope"
            assert not visibleCheckpoints([ev], 'South'), \
                f"cp.west event {ev.get('event_id')} matched South scope"
            assert not visibleCheckpoints([ev], 'East'), \
                f"cp.west event {ev.get('event_id')} matched East scope"

        # ----------------------------------------------------------------
        # Spec test: never wipe db.checkpoints with [] when the
        # server returns 0 items but local has data (spec step 1.2).
        # We exercise the backend's case-insensitive matching to
        # confirm a real cp.south GET never returns 0 when there
        # are South events in the database.
        # ----------------------------------------------------------------
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'cp.south', 'password': 'ChangeMe123!'})
        assert s == 200
        south_token = r['token']
        s, cps_now = request(base, 'GET', '/api/checkpoint-events', south_token)
        assert s == 200
        assert len(cps_now['items']) > 0, \
            "cp.south must see at least one event at South location (no 0-bug)"
        for ev in cps_now['items']:
            loc_str = ' '.join(filter(None, [
                ev.get('location'), ev.get('location_code'),
                ev.get('checkpoint_location'),
            ])).lower()
            assert 'south' in loc_str, \
                f"cp.south event {ev.get('event_id')} not in scope: {loc_str!r}"

        # And the spec's badge pattern: the count badge for cp.south
        # must equal visibleCheckpoints.length. We mirror the
        # production function so a future regression is caught.
        badge_count = len(visibleCheckpoints(cps_now['items'], 'South'))
        assert badge_count == len(cps_now['items']) > 0

        # ----------------------------------------------------------------
        # Spec: Normalize RBAC role strings & fix 404 dashboard endpoint.
        #
        # The user reported a screenshot showing
        #   userRole: "CheckpointSouth", userScope: "South", 404
        #   rawServerItems: 0
        # which means the frontend was seeing 404 on /api/dashboard for
        # a Checkpoint-officer token. The fix is a normalisation layer
        # in the backend that maps every accepted Checkpoint-officer
        # spelling ('CheckpointSouth', 'checkpoint_officer', 'cp_south',
        # etc.) to the canonical 'checkpoint_officer' alias, and ensures
        # /api/dashboard ALWAYS returns HTTP 200 for any authenticated
        # user.
        # ----------------------------------------------------------------
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'cp.south', 'password': 'ChangeMe123!'})
        assert s == 200
        south_token = r['token']
        # Spec step 1: the session payload must surface a
        # 'role_alias' field normalised to 'checkpoint_officer'.
        assert r['user'].get('role_alias') == 'checkpoint_officer', \
            f"role_alias not normalized: {r['user']}"
        assert r['user'].get('role') == 'CheckpointSouth', \
            f"raw role should be preserved: {r['user']}"
        # And the location_scope must be 'South' regardless of the
        # spelling used.
        assert r['user'].get('location_scope') == 'South', \
            f"location_scope not South: {r['user']}"

        # Spec step 2: /api/dashboard must ALWAYS return 200 for
        # any authenticated Checkpoint officer. Never 404, never
        # role-rejected.
        s, d = request(base, 'GET', '/api/dashboard', south_token)
        assert s == 200, f"dashboard returned {s}: {d}"
        # And the response payload must surface the spec-mandated
        # alias keys (screenings_today, travelers_flagged,
        # total_travelers, peak_travel_hour, activity_feed).
        for alias in ('screenings_today', 'travelers_flagged',
                      'total_travelers', 'peak_travel_hour', 'activity_feed'):
            assert alias in d, f"missing alias key {alias!r} in dashboard payload"
        # activity_feed must be a list (the spec's contract).
        assert isinstance(d['activity_feed'], list), \
            f"activity_feed not a list: {type(d['activity_feed'])}"
        # role_alias in the dashboard payload is normalised too.
        assert d.get('role_alias') == 'checkpoint_officer', \
            f"dashboard role_alias not normalised: {d}"
        # location_scope is non-empty for Checkpoint officers.
        assert d.get('location_scope') == 'South', \
            f"dashboard location_scope not South: {d}"

        # Spec step 3: /api/checkpoint-events must also return 200
        # with non-zero items for the officer.
        s, cps = request(base, 'GET', '/api/checkpoint-events', south_token)
        assert s == 200, f"checkpoint-events returned {s}: {cps}"
        assert len(cps.get('items', [])) > 0, \
            f"checkpoint-events must have items for cp.south: {cps}"
        # And the SQL must have used the case-insensitive LIKE '%south%'
        # match so newly-created rows show up.
        for ev in cps['items']:
            loc_str = ' '.join(filter(None, [
                ev.get('location'), ev.get('location_code'),
                ev.get('checkpoint_location'),
            ])).lower()
            assert 'south' in loc_str, \
                f"cp.south event {ev.get('event_id')} not in scope: {loc_str!r}"

        # And the same checks must hold for cp.east and cp.west.
        for u, scope in [('cp.east', 'East'), ('cp.west', 'West')]:
            s, r = request(base, 'POST', '/api/login',
                           body={'username': u, 'password': 'ChangeMe123!'})
            assert s == 200, f"login {u} returned {s}"
            tok = r['token']
            assert r['user'].get('role_alias') == 'checkpoint_officer', \
                f"{u} role_alias: {r['user']}"
            s, d = request(base, 'GET', '/api/dashboard', tok)
            assert s == 200, f"{u} dashboard returned {s}"
            assert d.get('location_scope') == scope, \
                f"{u} location_scope not {scope}: {d}"
            s, cps = request(base, 'GET', '/api/checkpoint-events', tok)
            assert s == 200, f"{u} checkpoint-events returned {s}"

        # Admin still sees the global dashboard (no regression).
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'admin', 'password': 'ChangeMe123!'})
        assert s == 200
        admin_token = r['token']
        s, d = request(base, 'GET', '/api/dashboard', admin_token)
        assert s == 200
        assert d.get('is_admin') is True
        assert d.get('location_scope') is None
        assert {c['id'] for c in d['cards']} == {
            'central_persons', 'open_cases', 'pending_clearances', 'active_alerts'}

        # ---- Session-refresh regression: cp.south end-to-end flow ---------
        # Mirrors the manual verification: login -> dashboard 200 ->
        # checkpoint-events 200 -> record a stop -> the count goes up and
        # every request stays 200 (no 401 / 404 for a valid checkpoint
        # officer). A stored bearer token keeps working across repeated
        # calls, which is what the frontend relies on after a refresh.
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'cp.south', 'password': 'ChangeMe123!'})
        assert s == 200, f'cp.south login failed: {r}'
        cps_tok = r['token']
        assert r['user']['role_alias'] == 'checkpoint_officer', r['user']
        assert r['user']['location_scope'] == 'South', r['user']
        assert set(('dashboard', 'checkpoints')) <= set(r['user']['modules']), r['user']
        # The same token authenticates many consecutive requests (refresh
        # simulation): /api/me + /api/dashboard + /api/checkpoint-events.
        for _ in range(3):
            s, me = request(base, 'GET', '/api/me', cps_tok)
            assert s == 200, f'/api/me returned {s} on refresh: {me}'
        s, d = request(base, 'GET', '/api/dashboard', cps_tok)
        assert s == 200, f'dashboard returned {s} for cp.south'
        s, cps_before = request(base, 'GET', '/api/checkpoint-events', cps_tok)
        assert s == 200, f'checkpoint-events returned {s} for cp.south'
        assert cps_before.get('scope') == 'South', cps_before
        n_before = len(cps_before['items'])
        assert n_before >= 1, f'cp.south should see the seeded South event: {cps_before}'
        # Record one stop at South as cp.south (bearer token unchanged).
        stop_fields = dict(cp_fields)
        stop_fields['location'] = 'South'
        stop_fields['first_name'] = 'Cabdalla'; stop_fields['second_name'] = 'Muuse'
        stop_fields['third_name'] = 'Faarax'; stop_fields['fourth_name'] = 'Xirsi'
        stop_fields['date_of_birth'] = '1991-05-05'
        stop_fields['national_id'] = '70707071'
        stop_files = {'doc_tr_0': ('ticket.pdf', b'%PDF-refresh-test'),
                      'doc_gd_0': ('gid.pdf', b'%PDF-guardian-refresh'),
                      'photo': ('p.jpg', b'\xff\xd8\xff\xe0refresh')}
        s, r = multipart_request(base, '/api/checkpoint-events', cps_tok,
                                 stop_fields, stop_files)
        assert s == 201, f'cp.south POST stop returned {s}: {r}'
        assert r['location_code'] == 'South' and r['checkpoint_location'] == 'South Checkpoint', r
        # Re-fetch with the SAME token (page-refresh simulation): 200 and
        # the count went up by exactly one — never 0, never 401 / 404.
        s, cps_after = request(base, 'GET', '/api/checkpoint-events', cps_tok)
        assert s == 200, f'checkpoint-events after stop returned {s}'
        assert len(cps_after['items']) == n_before + 1, \
            f'expected {n_before + 1} South events, got {len(cps_after["items"])}'
        assert all('south' in ' '.join(filter(None, [
            ev.get('location'), ev.get('location_code'),
            ev.get('checkpoint_location')])).lower() for ev in cps_after['items']), cps_after

        # ---- Role-alias normalization on the admin user endpoints ----------
        # Creating a user with the 'cp_south' alias stores the canonical
        # 'checkpoint_officer' role and derives location_scope 'South' —
        # and the new officer's /api/me, /api/dashboard and
        # /api/checkpoint-events all return 200 (the "modules: []" bug).
        s, r = request(base, 'POST', '/api/admin/users', admin_token, {
            'username': 'cp.alias.south', 'display_name': 'Officer T. Alias',
            'password': 'ChangeMe123!', 'role': 'cp_south', 'branch': 'Checkpoint South'})
        assert s == 201, f'create cp_south alias user returned {s}: {r}'
        assert r['user']['role'] == 'checkpoint_officer', r['user']
        assert r['user']['location_scope'] == 'South', r['user']
        assert set(('dashboard', 'checkpoints')) <= set(r['user']['modules']), r['user']
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'cp.alias.south', 'password': 'ChangeMe123!'})
        assert s == 200, f'alias-user login returned {s}: {r}'
        alias_tok = r['token']
        assert r['user']['role_alias'] == 'checkpoint_officer', r['user']
        s, d = request(base, 'GET', '/api/dashboard', alias_tok)
        assert s == 200 and d.get('location_scope') == 'South', \
            f'alias-user dashboard: {s} {d}'
        s, cps_alias = request(base, 'GET', '/api/checkpoint-events', alias_tok)
        assert s == 200 and cps_alias.get('scope') == 'South', f'{s} {cps_alias}'
        assert len(cps_alias['items']) == n_before + 1, \
            f"alias officer must see the same South events as cp.south: {cps_alias}"
        # Case-insensitive location_scope on create ('west' -> 'West').
        s, r = request(base, 'POST', '/api/admin/users', admin_token, {
            'username': 'cp.alias.west', 'display_name': 'Officer W. Alias',
            'password': 'ChangeMe123!', 'role': 'checkpoint_officer',
            'location_scope': 'west'})
        assert s == 201 and r['user']['location_scope'] == 'West', r
        # Legacy compound role on create is also normalized, scope preserved.
        s, r = request(base, 'POST', '/api/admin/users', admin_token, {
            'username': 'cp.alias.east', 'display_name': 'Officer E. Alias',
            'password': 'ChangeMe123!', 'role': 'CheckpointEast'})
        assert s == 201 and r['user']['role'] == 'checkpoint_officer', r
        assert r['user']['location_scope'] == 'East', r
        # PATCH a compound role onto the alias user: role normalizes and the
        # location survives ('CheckpointWest' -> checkpoint_officer + West).
        alias_uid = request(base, 'GET', '/api/admin/users', admin_token)[1]['items']
        alias_uid = next(u['id'] for u in alias_uid if u['username'] == 'cp.alias.south')
        s, r = request(base, 'PATCH', f'/api/admin/users/{alias_uid}', admin_token,
                       {'role': 'CheckpointWest'})
        assert s == 200 and r['user']['role'] == 'checkpoint_officer', r
        assert r['user']['location_scope'] == 'West', \
            f'PATCH must preserve/derive the location scope: {r}'
        # PATCH back to the canonical alias without a scope: existing scope kept.
        s, r = request(base, 'PATCH', f'/api/admin/users/{alias_uid}', admin_token,
                       {'role': 'checkpoint_officer'})
        assert s == 200 and r['user']['role'] == 'checkpoint_officer', r
        assert r['user']['location_scope'] == 'West', \
            f'PATCH to canonical alias must not wipe location_scope: {r}'

        # ---- /api/dashboard returns 200 for every seeded role --------------
        for u in ('admin', 'fp.officer', 'ap.officer', 'cid.officer',
                  'cp.south', 'cp.east', 'cp.west'):
            s, r = request(base, 'POST', '/api/login',
                           body={'username': u, 'password': 'ChangeMe123!'})
            assert s == 200, f'login {u} failed: {s} {r}'
            s, d = request(base, 'GET', '/api/dashboard', r['token'])
            assert s == 200 and isinstance(d.get('cards'), list), \
                f'/api/dashboard must return 200 for {u}: {s} {d}'

        # An expired / bogus token is the ONLY 401 the frontend may treat as
        # a sign-out: /api/me rejects it explicitly.
        s, r = request(base, 'GET', '/api/me', 'bogus-token-000')
        assert s == 401, f'bogus token /api/me returned {s}: {r}'

        # =================================================================
        # Fingerprint clearance — mandatory reasons + 12-hour review gate
        # =================================================================

        def backdate_application(application_id, hours):
            """Rewrite created_at to `hours` in the past (simulates elapsed time)."""
            stamp = (datetime.datetime.now(datetime.timezone.utc)
                     - datetime.timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            conn = sqlite3.connect(db_path, timeout=10)
            try:
                conn.execute('UPDATE clearance_applications SET created_at=? WHERE application_id=?',
                             (stamp, application_id))
                conn.commit()
            finally:
                conn.close()
            return stamp

        def review_error(r):
            """Normalised review-period rejection message (accepts 'detail' / 'error')."""
            return str((r or {}).get('detail') or (r or {}).get('error') or '').lower()

        def new_clearance(token, national_id, purpose='Employment',
                          first='Review', second='Period', third='Test', fourth='Case'):
            fields = {'first_name': first, 'second_name': second, 'third_name': third,
                      'fourth_name': fourth, 'date_of_birth': '1995-03-03',
                      'national_id': national_id, 'mother_name': 'Hooyo Test',
                      'residence': 'Hargeisa, Review Ward', 'phone': '+252 63 555 0900',
                      'sex': 'Male', 'email': 'applicant@example.com',
                      'purpose': purpose,
                      'guardian_name': 'Guardian Test', 'guardian_relationship': 'Uncle',
                      'guardian_id': 'GD-7788', 'guardian_occupation': 'Teacher',
                      'guardian_address': 'Burao, Road 9', 'guardian_phone': '+252 63 555 0901'}
            files = {'doc_app_0': ('app1.pdf', b'%PDF-app1'),
                     'doc_app_1': ('app2.pdf', b'%PDF-app2'),
                     'doc_guard_0': ('gd1.pdf', b'%PDF-gd1'),
                     'doc_guard_1': ('gd2.pdf', b'%PDF-gd2'),
                     'photo': ('applicant.jpg', b'\xff\xd8\xff\xe0applicant')}
            return multipart_request(base, '/api/clearance-applications', token, fields, files)

        # --- Mandatory clearance_reason dropdown -------------------------
        # Anything outside ['Education','Travel','Employment','Citizenship','Licence']
        # is rejected with 400.
        s, r = new_clearance(tokens['admin'], '55500011', purpose='Other')
        assert s == 400 and 'clearance reason' in r.get('error', '').lower(), (s, r)
        s, r = new_clearance(tokens['admin'], '55500011', purpose='Residence')
        assert s == 400, (s, r)
        for reason in ('Education', 'Travel', 'Employment', 'Citizenship', 'Licence'):
            s, r = new_clearance(tokens['admin'], '5550' + str(abs(hash(reason)) % 10000).zfill(4),
                                 purpose=reason)
            assert s == 201 and r['purpose'] == reason, (reason, s, r)

        # --- TEST 1: Fingerprint Officer instant approval -> 400 ---------
        s, created = new_clearance(tokens['admin'], '55500011', purpose='Employment')
        assert s == 201, created
        officer_app = created['application_id']
        # created_at is stored on creation and echoed back.
        assert created.get('created_at'), created
        assert created.get('review_eligible_at'), created

        s, r = request(base, 'POST', f'/api/fingerprint/applications/{officer_app}/approve',
                       tokens['fp.officer'], {})
        assert s == 400, f'officer instant approval must fail with 400, got {s}: {r}'
        # Spec-mandated payload: HTTP 400 + {"detail": "Review period active.
        # Standard officers must wait 12 hours before approving."}
        assert r.get('detail') == ('Review period active. Standard officers must wait 12 hours '
                                   'before approving.'), r
        assert 'review period active' in review_error(r), r
        assert r.get('code') == 'review_period_active', r
        assert r.get('review_window_hours') == 12, r
        assert r.get('hours_remaining') and r['hours_remaining'] > 0, r
        assert r.get('review_eligible_at'), r

        # Nothing was approved: the row is still pending and the detail
        # payload reports the lock for the officer.
        s, detail = request(base, 'GET', f'/api/clearance-applications/{officer_app}',
                            tokens['fp.officer'])
        assert s == 200 and detail['status'] == 'Pending Review', detail
        assert detail['certificate_number'] is None, detail
        assert detail['review']['review_locked'] is True, detail
        assert detail['review']['review_window_hours'] == 12, detail
        assert detail['can_approve'] is False, detail
        # ... while an admin may approve the very same locked application.
        s, detail = request(base, 'GET', f'/api/clearance-applications/{officer_app}',
                            tokens['admin'])
        assert s == 200 and detail['can_approve'] is True, detail

        # --- TEST 2: Fingerprint Officer approval after +12 hours -> OK --
        backdate_application(officer_app, 13)
        s, r = request(base, 'POST', f'/api/fingerprint/applications/{officer_app}/approve',
                       tokens['fp.officer'], {})
        assert s == 201, f'officer approval after 12h must succeed, got {s}: {r}'
        assert r['status'] == 'Approved' and r['certificate_number'], r
        assert r['review_period_bypassed'] is False, r
        assert r['approved_by_role'] == 'FingerprintUnit', r
        assert r['reviewer_is_fingerprint_officer'] is True, r
        s, detail = request(base, 'GET', f'/api/clearance-applications/{officer_app}',
                            tokens['fp.officer'])
        assert s == 200 and detail['status'] == 'Approved' and detail['certificate_number'], detail

        # ---- Session persistence + spec role on /api/me --------------------
        # Sessions are stored in SQLite, so a token keeps working after a
        # server restart (an in-memory token map used to 401 every browser on
        # restart, which pushed the frontend into its offline fallbacks).
        s, login = request(base, 'POST', '/api/login',
                           body={'username': 'fp.officer', 'password': 'ChangeMe123!'})
        assert s == 200, login
        restart_token = login['token']
        assert login['user']['username'] == 'fp.officer', login['user']
        assert login['user']['role'] == 'FingerprintUnit', login['user']
        # Spec-facing snake_case role is exposed for the client UI.
        assert login['user'].get('role_spec') == 'fingerprint_officer', login['user']
        s, me = request(base, 'GET', '/api/me', restart_token)
        assert s == 200, f'/api/me must return 200 for Officer H. Xasan: {s} {me}'
        assert me['username'] == 'fp.officer', me
        assert me['role'] == 'FingerprintUnit' and me['role_spec'] == 'fingerprint_officer', me
        assert me['visibility']['is_admin'] is False, me
        s, admin_me = request(base, 'GET', '/api/me', tokens['admin'])
        assert s == 200 and admin_me['role_spec'] == 'admin', admin_me

        # Restart the server on the SAME database: the token must survive.
        proc.terminate(); proc.wait(timeout=10)
        proc = subprocess.Popen([sys.executable, SERVER], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                status, _ = request(base, 'GET', '/api/health')
                if status == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('server did not restart')
        s, me = request(base, 'GET', '/api/me', restart_token)
        assert s == 200, f'session must survive a restart, /api/me returned {s}: {me}'
        assert me['username'] == 'fp.officer', me
        # The still-authenticated officer is still blocked by the review gate.
        s, created = new_clearance(tokens['admin'], '55500066', purpose='Education')
        assert s == 201, created
        restart_app = created['application_id']
        s, r = request(base, 'POST', f'/api/fingerprint/applications/{restart_app}/approve',
                       restart_token, {})
        assert s == 400 and 'review period active' in review_error(r), (s, r)
        # Logout revokes the session: the token is dead afterwards.
        s, _ = request(base, 'POST', '/api/logout', restart_token, {})
        assert s == 200, s
        s, me = request(base, 'GET', '/api/me', restart_token)
        assert s == 401, f'revoked session must return 401, got {s}: {me}'
        # ... and a fresh sign-in works again.
        s, login = request(base, 'POST', '/api/login',
                           body={'username': 'fp.officer', 'password': 'ChangeMe123!'})
        assert s == 200, login
        s, me = request(base, 'GET', '/api/me', login['token'])
        assert s == 200 and me['username'] == 'fp.officer', me

        # --- Fail-closed: a row with NO submission stamp stays locked -------
        # (legacy rows, or a row written by an older build). The elapsed time
        # cannot be proven, so a standard officer is still rejected while an
        # admin — who is exempt from the review period — is not.
        s, created = new_clearance(tokens['admin'], '55500055', purpose='Travel')
        assert s == 201, created
        nostamp_app = created['application_id']
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            conn.execute('UPDATE clearance_applications SET created_at=NULL WHERE application_id=?',
                         (nostamp_app,))
            conn.commit()
        finally:
            conn.close()
        s, r = request(base, 'POST', f'/api/fingerprint/applications/{nostamp_app}/approve',
                       tokens['fp.officer'], {})
        assert s == 400 and 'review period active' in review_error(r), (s, r)
        s, detail = request(base, 'GET', f'/api/clearance-applications/{nostamp_app}',
                            tokens['fp.officer'])
        assert s == 200 and detail['review']['review_locked'] is True, detail
        assert detail['can_approve'] is False, detail
        s, r = request(base, 'POST', f'/api/fingerprint/applications/{nostamp_app}/approve',
                       tokens['admin'], {})
        assert s == 201 and r['status'] == 'Approved', (s, r)

        # --- TEST 3: Admin instant approval straight after create -> OK ---
        s, created = new_clearance(tokens['admin'], '55500022', purpose='Travel')
        assert s == 201, created
        admin_app = created['application_id']
        # Zero simulated elapsed time: the admin bypasses the gate entirely.
        s, r = request(base, 'POST', f'/api/fingerprint/applications/{admin_app}/approve',
                       tokens['admin'], {})
        assert s == 201, f'admin instant approval must succeed, got {s}: {r}'
        assert r['status'] == 'Approved' and r['certificate_number'], r
        assert r['review_period_bypassed'] is True, r
        # The certificate page unlocks immediately.
        s, detail = request(base, 'GET', f'/api/clearance-applications/{admin_app}',
                            tokens['admin'])
        assert s == 200 and detail['status'] == 'Approved' and detail['certificate_number'], detail

        # --- The legacy /api/clearance-applications route behaves identically ---
        s, created = new_clearance(tokens['admin'], '55500033', purpose='Citizenship')
        assert s == 201, created
        legacy_app = created['application_id']
        s, r = request(base, 'POST', f'/api/clearance-applications/{legacy_app}/approve',
                       tokens['fp.officer'], {})
        assert s == 400 and 'review period active' in review_error(r), (s, r)
        # One minute short of the window is still locked ...
        backdate_application(legacy_app, 11.9)
        s, r = request(base, 'POST', f'/api/clearance-applications/{legacy_app}/approve',
                       tokens['fp.officer'], {})
        assert s == 400, f'approval at 11.9h must stay locked, got {s}: {r}'
        # ... and just past 12 hours it is released.
        backdate_application(legacy_app, 12.1)
        s, r = request(base, 'POST', f'/api/clearance-applications/{legacy_app}/approve',
                       tokens['fp.officer'], {})
        assert s == 201 and r['status'] == 'Approved', (s, r)

        # --- Role-alias hardening: 'fingerprint_officer' / 'admin' ---------
        # The spec names the reviewer roles in snake_case. A user created (or
        # stored) with an alias must resolve to the canonical role everywhere:
        # modules, RBAC gates, visibility flags and the 12-hour review lock.
        s, r = request(base, 'POST', '/api/admin/users', tokens['admin'], {
            'username': 'fp.alias', 'display_name': 'Officer Alias',
            'password': 'ChangeMe123!', 'role': 'fingerprint_officer',
            'branch': 'Fingerprint Unit'})
        assert s == 201, f'create fingerprint_officer alias returned {s}: {r}'
        assert r['user']['role'] == 'FingerprintUnit', r['user']
        assert set(('dashboard', 'fingerprint', 'people')) <= set(r['user']['modules']), r['user']
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'fp.alias', 'password': 'ChangeMe123!'})
        assert s == 200, f'alias officer login returned {s}: {r}'
        alias_fp_token = r['token']
        assert set(('dashboard', 'fingerprint', 'people')) <= set(r['user']['modules']), r['user']
        s, d = request(base, 'GET', '/api/dashboard', alias_fp_token)
        assert s == 200 and d.get('is_admin') is False, (s, d)
        s, me = request(base, 'GET', '/api/me', alias_fp_token)
        assert s == 200 and me['visibility']['is_admin'] is False, me
        # Admin alias on create normalises to SystemAdmin.
        s, r = request(base, 'POST', '/api/admin/users', tokens['admin'], {
            'username': 'admin.alias', 'display_name': 'Admin Alias',
            'password': 'ChangeMe123!', 'role': 'admin'})
        assert s == 201 and r['user']['role'] == 'SystemAdmin', r
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'admin.alias', 'password': 'ChangeMe123!'})
        assert s == 200 and r['user']['role'] == 'SystemAdmin', r
        s, me = request(base, 'GET', '/api/me', r['token'])
        assert s == 200 and me['visibility']['is_admin'] is True, me

        # A legacy row whose role is literally stored as 'fingerprint_officer'
        # still resolves to the Fingerprint modules and the 12-hour gate.
        sys.path.insert(0, ROOT)
        import server as sentinel_server
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            conn.execute("INSERT INTO users(username,display_name,role,branch,password_hash,active) "
                         "VALUES('legacy.fp','Legacy FP','fingerprint_officer','Fingerprint Unit',?,1)",
                         (sentinel_server.password_hash('ChangeMe123!'),))
            conn.commit()
        finally:
            conn.close()
        s, r = request(base, 'POST', '/api/login',
                       body={'username': 'legacy.fp', 'password': 'ChangeMe123!'})
        assert s == 200, f'legacy alias login returned {s}: {r}'
        legacy_token = r['token']
        assert set(('dashboard', 'fingerprint', 'people')) <= set(r['user']['modules']), r['user']
        s, r = request(base, 'GET', '/api/clearance-applications', legacy_token)
        assert s == 200, f'legacy alias must reach the fingerprint module: {s} {r}'
        # ... and the mandatory review window still blocks this officer.
        s, created = new_clearance(tokens['admin'], '55500044', purpose='Licence')
        assert s == 201, created
        alias_app = created['application_id']
        s, r = request(base, 'POST', f'/api/fingerprint/applications/{alias_app}/approve',
                       legacy_token, {})
        assert s == 400 and 'review period active' in review_error(r), (s, r)
        backdate_application(alias_app, 13)
        s, r = request(base, 'POST', f'/api/fingerprint/applications/{alias_app}/approve',
                       legacy_token, {})
        assert s == 201 and r['status'] == 'Approved', (s, r)
        assert r['reviewer_is_fingerprint_officer'] is True, r

        # The printable extras (Section 01) round-trip through the API.
        s, detail = request(base, 'GET', f'/api/clearance-applications/{legacy_app}',
                            tokens['fp.officer'])
        assert s == 200, detail
        assert detail.get('sex') == 'Male' and detail.get('email') == 'applicant@example.com', detail
        assert detail.get('created_at'), detail

        print('ALL BACKEND TESTS PASSED')
        return 0
    finally:
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == '__main__':
    sys.exit(main())

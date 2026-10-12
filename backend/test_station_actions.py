#!/usr/bin/env python3
"""Regression test — Registered Stations row actions (View) + admin-only Edit.

Covers the two capabilities the Police Stations register exposes in its Actions
column, end to end against a real server process and a real PostgreSQL database
(the backend serves PostgreSQL only):

  1. VIEW IS A READ — `GET /api/stations/<id>` returns the full station record
     (registry fields, officer / vehicle deployment counters and the mirrored
     Police Stations branch lineage) to every session that may open the station
     register: SystemAdmin, the HR Directorate and the read-only Commander.
     A session without the `stations` module is still refused (401).

  2. EDIT IS AN ADMINISTRATION WRITE — `PATCH` and `PUT /api/stations[/<id>]`
     succeed for the System Administrator / Admin role and answer **403
     Forbidden** (`code: admin_only`) for every other authenticated role — the
     HR Directorate (which may READ the register), a checkpoint officer (which
     may not) and the globally read-only Commander (refused earlier by the
     read-only firewall with `code: read_only_role`). A refused write never
     changes the row.

     The edit validation mirrors station registration (name required, district
     must belong to the region, status from the fixed list), a mirrored
     `BR-<id>` branch entry is refused with an explanation instead of a silent
     no-op, and the successful update is audited (`UPDATE police_station`).

Database resolution (mirrors the other suites):
  * SENTINEL_DATABASE_URL or SENTINEL_DB_HOST / _NAME / _USER / _PASSWORD / _PORT when set, or
  * a throwaway cluster booted with the `pgserver` pip package
    (`pip install pgserver`) in a temporary directory, or
  * SKIP (exit 0) with a message when neither is available.

Usage:
    python3 backend/test_station_actions.py
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
sys.path.insert(0, ROOT)
import importlib.util                                       # noqa: E402

_spec = importlib.util.spec_from_file_location('sentinel_server', SERVER)
srv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(srv)

PASS, FAIL = [], []


def check(condition, label):
    (PASS if condition else FAIL).append(label)
    print(('  PASS ' if condition else '  FAIL ') + label)
    return condition


def load_project_database_environment():
    """Mirror server.py's .env fallback so provisioning sees configured URLs too."""
    env_path = os.path.join(os.path.dirname(ROOT), '.env')
    if not os.path.exists(env_path):
        return
    with open(env_path, encoding='utf-8') as env_file:
        for line in env_file:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ.setdefault(key.strip(), value.strip())


load_project_database_environment()


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
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            return e.code, json.loads(raw)
        except Exception:
            return e.code, {'error': raw}


def login(base, username, password='ChangeMe123!'):
    status, body = request(base, 'POST', '/api/login',
                           body={'username': username, 'password': password})
    assert status == 200 and body.get('token'), (username, status, body)
    return body['token'], body


PG_SERVE = '''
import pathlib, sys, time, pgserver
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
srv = pgserver.get_server(str(d))
print(d, flush=True)
sys.stdin.read()
'''


def provision_database(tmp):
    """Return (env_overrides, stop_callable) or (None, None) when unavailable."""
    if (os.environ.get('SENTINEL_DATABASE_URL', '').strip()
            or any(os.environ.get(key) for key in (
                'SENTINEL_DB_HOST', 'SENTINEL_DB_PORT', 'SENTINEL_DB_USER',
                'SENTINEL_DB_PASSWORD', 'SENTINEL_DB_NAME'))):
        return ({}, lambda: None)
    try:
        import pgserver  # noqa: F401
    except ImportError:
        return (None, None)
    proc = subprocess.Popen([sys.executable, '-c', PG_SERVE, os.path.join(tmp, 'pgdata')],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    socket_dir = ''
    deadline = time.time() + 90
    while time.time() < deadline and proc.poll() is None:
        line = proc.stdout.readline().strip()
        if line:
            socket_dir = line
            break
    if not socket_dir:
        proc.kill()
        return (None, None)
    return ({'SENTINEL_DB_HOST': socket_dir, 'SENTINEL_DB_NAME': 'postgres',
             'SENTINEL_DB_USER': 'postgres', 'SENTINEL_DB_PASSWORD': ''},
            proc.kill)


def db_connect(env):
    """Direct connection to the test cluster (fixtures + audit assertions)."""
    import psycopg2
    import psycopg2.extras
    if env.get('SENTINEL_DATABASE_URL'):
        conn = psycopg2.connect(env['SENTINEL_DATABASE_URL'],
                                cursor_factory=psycopg2.extras.RealDictCursor)
    else:
        conn = psycopg2.connect(
            host=env.get('SENTINEL_DB_HOST') or os.environ.get('SENTINEL_DB_HOST'),
            dbname=env.get('SENTINEL_DB_NAME') or os.environ.get('SENTINEL_DB_NAME', 'postgres'),
            user=env.get('SENTINEL_DB_USER') or os.environ.get('SENTINEL_DB_USER', 'postgres'),
            password=env.get('SENTINEL_DB_PASSWORD') or os.environ.get('SENTINEL_DB_PASSWORD', ''),
            port=(env.get('SENTINEL_DB_PORT') or os.environ.get('SENTINEL_DB_PORT') or 5432),
            cursor_factory=psycopg2.extras.RealDictCursor)
    conn.autocommit = True
    return conn


# ---------------------------------------------------------------------------
# 0. Role authority, server module only (no HTTP, no database)
# ---------------------------------------------------------------------------
def admin_authority_suite():
    print('== 0. Administration edit authority (server module, no HTTP) ==')
    for spelling in ('SystemAdmin', 'system_admin', 'admin', 'Admin', 'ADMIN',
                     'administrator', 'Administrator', 'System Administrator'):
        check(srv.is_records_admin({'role': spelling}),
              f'{spelling!r} holds the management-table edit authority')
    for spelling in ('hr_officer', 'HR Directorate', 'FingerprintUnit',
                     'fingerprint_officer', 'CIDUnit', 'AirportControl',
                     'CheckpointSouth', 'cp_south', 'chief_commander',
                     'commander', 'HighCommand', '', None, 'Deputy Dog'):
        check(not srv.is_records_admin({'role': spelling}),
              f'{spelling!r} does NOT hold the management-table edit authority')
    # The refusal is a 403, never the 401 used for a missing permission.
    try:
        srv.require_records_admin({'role': 'hr_officer'}, 'Editing a station record')
        check(False, 'a non-admin edit raises AdminOnlyWriteError')
    except srv.AdminOnlyWriteError as exc:
        check(getattr(exc, 'status_code', None) == 403 and srv.ADMIN_ONLY_CODE == 'admin_only',
              'the non-admin refusal carries HTTP 403 / admin_only')
        check('System Administrator' in str(exc),
              'the refusal names the required role')
    try:
        srv.require_records_admin({'role': 'admin', 'id': 1}, 'Editing a station record')
        check(True, 'an administrator passes require_records_admin()')
    except srv.AdminOnlyWriteError:
        check(False, 'an administrator passes require_records_admin()')
    # The station edit vocabulary the frontend renders/validates against.
    check(srv.STATION_STATUSES == ('Active', 'Inactive', 'Maintenance'),
          f'station statuses {srv.STATION_STATUSES}')
    check(srv.STATION_DISTRICTS['Sool'] == ('Laascaanood', 'Caynabo', 'Xudun', 'Taleex'),
          'district validation table is intact')


# ---------------------------------------------------------------------------
# 1. View — the station record endpoint
# ---------------------------------------------------------------------------
def view_suite(base, tokens):
    print('== 1. Actions → View: GET /api/stations/<id> ==')
    admin, hr, cp, chief = (tokens['admin'], tokens['hr.officer'],
                            tokens['cp.south'], tokens['chief'])
    status, listing = request(base, 'GET', '/api/stations', admin)
    check(status == 200 and listing.get('items'),
          f'administrator reads the station register ({status})')
    seeded = next(i for i in listing['items'] if i['station_id'] == 'ST-001')

    status, payload = request(base, 'GET', '/api/stations/ST-001', admin)
    station = payload.get('station') if isinstance(payload, dict) else None
    check(status == 200 and station is not None, f'GET /api/stations/ST-001 -> {status}')
    for field in ('id', 'station_id', 'name', 'code', 'region', 'district', 'village',
                  'operational_status', 'officer_count', 'vehicle_count', 'branch',
                  'branch_lineage', 'can_edit'):
        check(station is not None and field in station,
              f'the View payload carries `{field}`')
    check(station and station['name'] == seeded['name'] and station['code'] == 'SAN-C-01',
          'the detail record matches the register row')
    check(station and isinstance(station['officer_count'], int)
          and isinstance(station['vehicle_count'], int),
          'officer / vehicle deployment counters are integers')
    check(station and station['can_edit'] is True,
          'an administrator sees can_edit: true')
    check(station and station['persisted'] is True and station['mirrored'] is False,
          'a seeded registry row is persisted and not a branch mirror')

    # Read-only view for a non-admin session that may open the register.
    status, hr_payload = request(base, 'GET', '/api/stations/ST-001', hr)
    hr_station = hr_payload.get('station') if isinstance(hr_payload, dict) else None
    check(status == 200 and hr_station and hr_station['can_edit'] is False,
          'the HR Directorate may VIEW the record (can_edit: false)')
    check(bool(hr_station and hr_station.get('edit_disabled_reason')
               and 'System Administrator' in hr_station['edit_disabled_reason']),
          'the View payload explains why Edit is unavailable')

    status, _ = request(base, 'GET', '/api/stations/ST-001', chief)
    check(status == 200, 'the read-only Commander may VIEW the record')
    status, _ = request(base, 'GET', '/api/stations/ST-001', cp)
    check(status == 401, 'a session without the stations module cannot read the record')
    status, missing = request(base, 'GET', '/api/stations/ST-999', admin)
    check(status == 404 and 'does not exist' in (missing.get('error') or ''),
          f'an unknown station id answers 404 ({status})')
    status, by_pk = request(base, 'GET', '/api/stations/1', admin)
    check(status == 200 and by_pk['station']['station_id'] == 'ST-001',
          'the numeric primary key also resolves a station record')
    status, by_code = request(base, 'GET', '/api/stations/SAN-C-01', admin)
    check(status == 200 and by_code['station']['station_id'] == 'ST-001',
          'the station code also resolves a station record')
    return station


# ---------------------------------------------------------------------------
# 2. Deployment counters come from the live registers
# ---------------------------------------------------------------------------
def deployment_suite(base, tokens, db):
    print('== 2. Deployment counters (officers / vehicles registers) ==')
    admin = tokens['admin']
    with db.cursor() as cur:
        cur.execute("SELECT id FROM police_stations WHERE station_id='ST-001'")
        row_id = cur.fetchone()['id']
        # A minimal but complete officer posting (the register's NOT NULL set).
        cur.execute('''INSERT INTO officers(service_id,rank,unit,station_id,date_of_enlistment,
                       duty_status,full_name,mother_name,date_of_birth,place_of_birth,
                       contact_number,guarantor_name,guarantor_address,guarantor_contact,
                       doc1_type,doc1_path)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                       ON CONFLICT (service_id) DO NOTHING''',
                    ('POL-TEST-9001', 'Inspector', 'General Patrol', row_id, '2026-01-01',
                     'Active', 'Test Officer One', 'Test Mother', '1990-01-01', 'Ceerigaabo',
                     '+252 63 555 9001', 'Test Guarantor', 'Ceerigaabo', '+252 63 555 9002',
                     'National ID', 'uploads/test-officer.txt'))
        cur.execute('''INSERT INTO vehicles(vehicle_id,plate_number,category,vin,engine_number,
                       make_model,year_of_manufacture,body_type,station_id,security_alert)
                       VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s) ON CONFLICT (vehicle_id) DO NOTHING''',
                    ('VEH-TEST-9001', 'TEST-9001', 'Police Fleet', '1HGBH41JXMN109186',
                     'ENG-TEST-9001', 'Toyota Hilux', 2024, 'Pickup 4x4', row_id, 'Clean / Normal'))
    status, payload = request(base, 'GET', '/api/stations/ST-001', admin)
    station = payload['station']
    check(status == 200 and station['officer_count'] >= 1,
          f'officer_count reflects the officers register ({station.get("officer_count")})')
    check(station['vehicle_count'] >= 1,
          f'vehicle_count reflects the vehicles register ({station.get("vehicle_count")})')
    status, officers = request(base, 'GET', '/api/officers', admin)
    linked = [o for o in officers.get('items', []) if o.get('service_id') == 'POL-TEST-9001']
    check(bool(linked) and linked[0].get('station_name') == station['name'],
          'the officer posting resolves against the same station row')


# ---------------------------------------------------------------------------
# 3. Edit — admin succeeds, validation holds
# ---------------------------------------------------------------------------
def admin_edit_suite(base, tokens):
    print('== 3. Actions → Edit: SystemAdmin PATCH / PUT /api/stations ==')
    admin = tokens['admin']
    status, created = request(base, 'POST', '/api/stations', admin, {
        'name': 'Arena Edit Target', 'station_tier': 'Outpost', 'region': 'Sool',
        'district': 'Xudun', 'village': 'Xudun', 'contact_phone': '+252 63 555 9001'})
    check(status == 201, f'administrator creates the station under test ({status})')
    sid = created['station']['station_id']

    status, patched = request(base, 'PATCH', f'/api/stations/{sid}', admin, {
        'name': 'Arena Edit Target (Renamed)', 'region': 'Sanaag', 'district': 'Badhan',
        'village': 'Badhan', 'operational_status': 'Maintenance'})
    station = patched.get('station') if isinstance(patched, dict) else None
    check(status == 200 and patched.get('updated') is True,
          f'PATCH /api/stations/{sid} -> {status}')
    check(station and station['name'] == 'Arena Edit Target (Renamed)'
          and station['region'] == 'Sanaag' and station['district'] == 'Badhan'
          and station['village'] == 'Badhan'
          and station['operational_status'] == 'Maintenance',
          'name, region, district, village and status are all updated')
    check(station and station['code'] == created['station']['code']
          and station['station_id'] == sid,
          'the station id / code are immutable')
    check(station and station.get('updated_at') and station.get('updated_by'),
          'the update stamps updated_at / updated_by (administration provenance)')
    check(station and set(['name', 'region', 'district', 'village',
                           'operational_status']) <= set(station.get('changed_fields') or []),
          f"changed_fields reports the edit ({station.get('changed_fields')})")
    check(patched.get('detail', {}).get('can_edit') is True,
          'the response carries the refreshed View payload')

    status, listing = request(base, 'GET', '/api/stations', admin)
    saved = next((i for i in listing['items'] if i['station_id'] == sid), None)
    check(status == 200 and saved and saved['name'] == 'Arena Edit Target (Renamed)'
          and saved['region'] == 'Sanaag' and saved['operational_status'] == 'Maintenance',
          'the register listing reflects the saved edit')
    status, detail = request(base, 'GET', f'/api/stations/{sid}', admin)
    check(status == 200 and detail['station']['district'] == 'Badhan',
          'the View payload reflects the saved edit')

    # PUT is served for the same administration edit (spec verb).
    status, put = request(base, 'PUT', f'/api/stations/{sid}', admin,
                          {'operational_status': 'Active'})
    check(status == 200 and put.get('method') == 'PUT'
          and put['station']['operational_status'] == 'Active',
          f'PUT /api/stations/{sid} applies the edit for an administrator ({status})')
    status, put_body = request(base, 'PUT', '/api/stations', admin,
                               {'station_id': sid, 'village': 'Xudun Town'})
    check(status == 200 and put_body['station']['village'] == 'Xudun Town',
          'PUT /api/stations with station_id in the body applies the edit')
    status, patched_body = request(base, 'PATCH', '/api/stations', admin,
                                   {'station_id': sid, 'notes': 'Edited through the collection path'})
    check(status == 200 and patched_body['station']['notes'] == 'Edited through the collection path',
          'PATCH /api/stations with station_id in the body applies the edit')
    status, _ = request(base, 'PUT', '/api/stations', admin, {'notes': 'no id'})
    check(status == 400, f'a station edit without an identifier is a 400 ({status})')

    # ---- validation mirrors station registration ---------------------------
    status, bad = request(base, 'PATCH', f'/api/stations/{sid}', admin,
                          {'district': 'Burao'})            # Burao belongs to East Togdheer
    check(status == 400 and 'district' in (bad.get('error') or '').lower(),
          f'a district outside the region is refused ({status})')
    status, bad = request(base, 'PATCH', f'/api/stations/{sid}', admin,
                          {'region': 'Sool'})               # orphans 'Xudun Town'? district stays Badhan
    check(status == 400,
          f'a region change that orphans the district is refused ({status})')
    status, bad = request(base, 'PATCH', f'/api/stations/{sid}', admin,
                          {'operational_status': 'Exploded'})
    check(status == 400 and 'operational status' in (bad.get('error') or '').lower(),
          f'an unknown operational status is refused ({status})')
    status, bad = request(base, 'PATCH', f'/api/stations/{sid}', admin, {'name': '   '})
    check(status == 400 and 'name' in (bad.get('error') or '').lower(),
          f'an empty station name is refused ({status})')
    status, bad = request(base, 'PATCH', f'/api/stations/{sid}', admin, {})
    check(status == 400, f'an edit with no editable field is refused ({status})')
    status, bad = request(base, 'PATCH', '/api/stations/ST-999', admin, {'name': 'Nope'})
    check(status == 404, f'editing an unknown station is a 404 ({status})')
    # partial edit: only the supplied field changes
    status, partial = request(base, 'PATCH', f'/api/stations/{sid}', admin,
                              {'name': 'Partial Edit Only'})
    check(status == 200 and partial['station']['name'] == 'Partial Edit Only'
          and partial['station']['region'] == 'Sanaag'
          and partial['station']['district'] == 'Badhan',
          'PATCH semantics: untouched fields keep their values')
    return sid


# ---------------------------------------------------------------------------
# 4. Permission enforcement — non-admins are refused with 403 (never a write)
# ---------------------------------------------------------------------------
def permission_suite(base, tokens, sid):
    print('== 4. Non-admin roles: 403 Forbidden on every station write ==')
    admin, hr, cp, chief = (tokens['admin'], tokens['hr.officer'],
                            tokens['cp.south'], tokens['chief'])
    _, before = request(base, 'GET', f'/api/stations/{sid}', admin)
    original = before['station']

    attempts = [
        ('hr.officer (may read stations)', hr),
        ('cp.south (no stations module)', cp),
    ]
    for label, token in attempts:
        for method, path, body in (
                ('PATCH', f'/api/stations/{sid}', {'name': 'HR Rename Attempt'}),
                ('PATCH', '/api/stations', {'station_id': sid, 'name': 'HR Rename Attempt'}),
                ('PUT', f'/api/stations/{sid}', {'name': 'HR Rename Attempt'}),
                ('PUT', '/api/stations', {'station_id': sid, 'name': 'HR Rename Attempt'}),
                ('PATCH', '/api/stations/ST-001', {'operational_status': 'Inactive'})):
            status, payload = request(base, method, path, token, body)
            code = payload.get('code') if isinstance(payload, dict) else None
            check(status == 403 and code == 'admin_only',
                  f'{method} {path} as {label} -> {status} ({code})')
            check(isinstance(payload, dict) and payload.get('admin_only') is True
                  and payload.get('path') == path,
                  f'{method} {path} as {label} carries the admin_only contract')

    # The refused writes must not have touched the row.
    status, after = request(base, 'GET', f'/api/stations/{sid}', admin)
    check(status == 200 and after['station']['name'] == original['name']
          and after['station']['operational_status'] == original['operational_status'],
          'no refused write altered the station record')
    status, listing = request(base, 'GET', '/api/stations', admin)
    check(all(i['name'] != 'HR Rename Attempt' for i in listing['items']),
          'no refused write leaked into the register listing')

    # Read-only Commander: refused earlier, by the global write firewall.
    for method in ('PATCH', 'PUT'):
        status, payload = request(base, method, f'/api/stations/{sid}', chief,
                                  {'name': 'Commander Rename Attempt'})
        code = payload.get('code') if isinstance(payload, dict) else None
        check(status == 403 and code == 'read_only_role',
              f'{method} /api/stations/{sid} as chief -> {status} ({code})')

    # Other verbs keep their existing routing contract.
    status, payload = request(base, 'PUT', '/api/persons/P-0001', admin, {'phone': 'x'})
    check(status == 405 and payload.get('method') == 'PUT',
          f'PUT /api/persons keeps the explicit 405 for a write-capable role ({status})')
    status, _ = request(base, 'POST', f'/api/stations/{sid}', admin, {'name': 'x'})
    check(status in (404, 405),
          f'POST on a station member path keeps its routing response ({status})')

    # ---- session payload advertises the same authority ---------------------
    for token, who, expected in ((admin, 'admin', True), (hr, 'hr.officer', False),
                                 (chief, 'chief', False)):
        status, me = request(base, 'GET', '/api/me', token)
        vis = me.get('visibility') or {}
        check(status == 200 and me.get('can_edit_records') is expected
              and me.get('can_edit_stations') is expected,
              f'/api/me reports can_edit_records={expected} for {who}')
        check(vis.get('can_edit_stations') is expected
              and vis.get('can_edit_records') is expected,
              f'the visibility block reports can_edit_stations={expected} for {who}')
    status, hr_me = request(base, 'GET', '/api/me', hr)
    check('stations' in (hr_me.get('modules') or []) and hr_me.get('read_only') is False,
          'the HR Directorate still READS the register (module present, not read-only)')
    status, health = request(base, 'GET', '/api/health')
    check(status == 200 and health.get('station_edit_roles') == ['SystemAdmin', 'admin'],
          'the health payload documents the station-edit role')


# ---------------------------------------------------------------------------
# 5. Mirrored Police Stations branches + the audit trail
# ---------------------------------------------------------------------------
def mirror_and_audit_suite(base, tokens, db, sid):
    print('== 5. Mirrored branch entries + the audit trail ==')
    admin = tokens['admin']
    branch_name = f'Arena Station Action Branch {time.time_ns()}'
    status, created = request(base, 'POST', '/api/branches', admin, {
        'name': branch_name, 'region': 'Sool', 'district': 'Taleex', 'unit_type': 'police_station'})
    check(status == 201, f'administrator creates a Police Stations branch ({status})')
    branch_id = created['branch']['id']
    with db.cursor() as cur:
        # The mirroring write stamps a real police_stations row; the detail
        # endpoint must resolve the same record through GET /api/stations/BR-x.
        cur.execute("SELECT station_id, code FROM police_stations WHERE notes ILIKE %s",
                    (f'%branch {branch_id}%',))
        mirrored = cur.fetchone()
    status, payload = request(base, 'GET', f'/api/stations/BR-{branch_id}', admin)
    station = payload.get('station') if isinstance(payload, dict) else None
    check(status == 200 and station is not None,
          f'the mirrored branch resolves through the View endpoint ({status})')
    check(station and station['branch'] and station['branch']['name'] == branch_name,
          'the View payload carries the mirrored branch lineage')
    check(station and station['mirrored'] is True
          and station['persisted'] is (mirrored is not None),
          f"the mirror reports persisted={mirrored is not None} (a mirrored registry row)")
    if mirrored is not None:
        status, edited = request(base, 'PATCH', f"/api/stations/{mirrored['station_id']}", admin,
                                 {'operational_status': 'Active'})
        check(status == 200 and (edited.get('detail') or {}).get('mirrored') is True
              and (edited.get('detail') or {}).get('can_edit') is True,
              'the persisted mirror row is editable by the administrator')

    # Force the synthetic path: a branch that has not been mirrored into the
    # register yet is rendered as `BR-<id>` and may not be edited here.
    with db.cursor() as cur:
        cur.execute('DELETE FROM police_stations WHERE notes ILIKE %s',
                    (f'%branch {branch_id}%',))
    status, payload = request(base, 'GET', f'/api/stations/BR-{branch_id}', admin)
    synthetic = payload.get('station') if isinstance(payload, dict) else None
    check(status == 200 and synthetic is not None,
          f'an un-mirrored branch still resolves through the View endpoint ({status})')
    check(synthetic and synthetic['persisted'] is False and synthetic['can_edit'] is False,
          'the synthetic entry is view-only (persisted: false, can_edit: false)')
    check(synthetic and 'Branch Management' in (synthetic.get('edit_disabled_reason') or ''),
          'Edit is refused on a synthetic mirror, pointing at Branch Management')
    status, refused = request(base, 'PATCH', f'/api/stations/BR-{branch_id}', admin,
                              {'name': 'Mirror Rename'})
    check(status == 400 and 'branch mirror' in (refused.get('error') or '').lower(),
          f'an administrator cannot rename a synthetic mirror entry ({status})')
    status, _ = request(base, 'GET', '/api/stations/BR-999999', admin)
    check(status == 404, 'an unknown branch id answers 404 on the View endpoint')

    # The successful administration edits are audited.
    with db.cursor() as cur:
        cur.execute('''SELECT a.action, a.entity, a.entity_id, a.details, u.username
                         FROM audit_events a LEFT JOIN users u ON u.id=a.user_id
                        WHERE a.entity='police_station' AND a.action='UPDATE'
                          AND a.entity_id=%s ORDER BY a.id DESC''', (sid,))
        rows = cur.fetchall()
    check(bool(rows) and all(r['username'] == 'admin' for r in rows),
          f'the station edits are audited against the administrator ({len(rows)} event(s))')
    check(bool(rows) and any(r['details'] and 'name=' in r['details'] for r in rows),
          'the audit detail records the changed fields')


def main():
    tmp = tempfile.mkdtemp(prefix='sentinel-stations-')
    env_overrides, stop_db = provision_database(tmp)
    if env_overrides is None:
        print('SKIP: no PostgreSQL test database available.')
        print('      Set SENTINEL_DB_HOST / SENTINEL_DB_NAME (and _USER / _PASSWORD / _PORT)')
        print('      or install the bundled engine with:  pip install pgserver')
        return 0

    port = free_port()
    env = dict(os.environ, **env_overrides)
    env.update(PORT=str(port), SENTINEL_UPLOADS=os.path.join(tmp, 'uploads'))
    proc = subprocess.Popen([sys.executable, SERVER], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    db = None
    try:
        for _ in range(90):
            try:
                if request(base, 'GET', '/api/health')[0] == 200:
                    break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError('the backend did not start (is PostgreSQL reachable?)')

        admin_authority_suite()

        tokens = {}
        for username in ('admin', 'hr.officer', 'cp.south', 'chief'):
            token, _ = login(base, username)
            tokens[username] = token
        check(len(tokens) == 4, 'the demo accounts sign in')

        db = db_connect(env_overrides)
        view_suite(base, tokens)
        deployment_suite(base, tokens, db)
        sid = admin_edit_suite(base, tokens)
        permission_suite(base, tokens, sid)
        mirror_and_audit_suite(base, tokens, db, sid)
    finally:
        if db is not None:
            db.close()
        proc.terminate()
        try:
            proc.wait(timeout=10)
        except subprocess.TimeoutExpired:
            proc.kill()
        stop_db()

    print()
    print(f'{len(PASS)} checks passed, {len(FAIL)} failed')
    if FAIL:
        print('FAILURES:')
        for f in FAIL:
            print(' -', f)
        return 1
    print('ALL STATION VIEW / EDIT ACTION TESTS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())

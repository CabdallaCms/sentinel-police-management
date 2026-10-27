#!/usr/bin/env python3
"""Strict branch scoping + posting resolution (real API, throwaway PostgreSQL).

  1. POSTING → BRANCH RESOLUTION
     A user's `branch` / `location_scope` is free text. GET /api/me resolves it
     to exactly one registered branch of their unit ('Lasanod Branch',
     '  lasanod branch ', 'Lasanod Branch · Laascaanood · Sool',
     'Fingerprint Unit · Sool'), reports it as `branch_scope` and never guesses
     when the posting is ambiguous.

  2. STRICT READ SCOPING
     A scoped unit officer only receives the clearance applications, airport
     movements and CID cases filed under their own branch, cannot read another
     branch's record or its audit history by identifier (403), and keeps the
     free choice only when their posting names no single branch.

  3. STRICT WRITE SCOPING
     A scoped officer cannot file a record under another branch (403
     `branch_scope_forbidden`); the System Administrator and the multi-branch
     Commander keep the override.

Usage: python3 backend/test_branch_scope.py
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
PROJECT_ROOT = os.path.dirname(ROOT)
PASSWORD = 'ChangeMe123!'


def load_project_database_environment():
    env_path = os.path.join(PROJECT_ROOT, '.env')
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
    sock = socket.socket()
    sock.bind(('127.0.0.1', 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


def request(base, method, path, token=None, body=None, form=None):
    """JSON (or multipart form) request helper -> (status, payload)."""
    if form is not None:
        boundary = '----sentinel-branch-scope-boundary'
        chunks = []
        for name, value in form.items():
            values = value if isinstance(value, list) else [value]
            for entry in values:
                if isinstance(entry, tuple):
                    filename, content, ctype = entry
                    chunks.append(
                        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                        f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
                        + content + b'\r\n')
                else:
                    chunks.append(
                        f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                        f'{entry}\r\n'.encode())
        chunks.append(f'--{boundary}--\r\n'.encode())
        payload = b''.join(chunks)
        content_type = f'multipart/form-data; boundary={boundary}'
    else:
        payload = json.dumps(body).encode() if body is not None else None
        content_type = 'application/json'
    req = urllib.request.Request(base + path, data=payload, method=method)
    req.add_header('Content-Type', content_type)
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=30) as response:
            raw = response.read().decode()
            try:
                return response.status, json.loads(raw)
            except ValueError:
                return response.status, {'raw': raw}
    except urllib.error.HTTPError as error:
        raw = error.read().decode()
        try:
            return error.code, json.loads(raw)
        except ValueError:
            return error.code, {'raw': raw}


PG_SERVE = '''
import pathlib, sys, pgserver
data = pathlib.Path(sys.argv[1]); data.mkdir(parents=True, exist_ok=True)
server = pgserver.get_server(str(data))
print(data, flush=True)
sys.stdin.read()
'''


def provision_database(tmp):
    if (os.environ.get('SENTINEL_DATABASE_URL', '').strip()
            or any(os.environ.get(key) for key in (
                'SENTINEL_DB_HOST', 'SENTINEL_DB_PORT', 'SENTINEL_DB_USER',
                'SENTINEL_DB_PASSWORD', 'SENTINEL_DB_NAME'))):
        return {}, lambda: None
    try:
        import pgserver  # noqa: F401
    except ImportError:
        return None, None
    proc = subprocess.Popen(
        [sys.executable, '-c', PG_SERVE, os.path.join(tmp, 'pgdata')],
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
        return None, None
    return ({'SENTINEL_DB_HOST': socket_dir, 'SENTINEL_DB_NAME': 'postgres',
             'SENTINEL_DB_USER': 'postgres', 'SENTINEL_DB_PASSWORD': ''},
            lambda: proc.kill())


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print('ok:', message)


def login(base, username, password=PASSWORD):
    status, body = request(base, 'POST', '/api/login',
                           body={'username': username, 'password': password})
    check(status == 200 and body.get('token'), f'{username} signs in ({status})')
    return body['token'], body['user']


def branch_ids(base, token):
    """{(unit_type, name): id} for the seeded branch catalogue."""
    status, body = request(base, 'GET', '/api/branches', token)
    check(status == 200, 'the branch catalogue is readable')
    return {(item['unit_type'], item['name']): item['id'] for item in body['items']}


def create_user(base, admin, username, role, **posting):
    payload = {'username': username, 'display_name': f'Officer {username}',
               'password': PASSWORD, 'role': role}
    payload.update(posting)
    status, body = request(base, 'POST', '/api/admin/users', admin, payload)
    check(status in (200, 201), f'{username} is created ({status} {body.get("error", "")})')
    return body['user']


def create_clearance(base, token, suffix, branch_id=None):
    form = {
        'first_name': 'Scope', 'second_name': 'Probe', 'third_name': suffix,
        'fourth_name': 'Case',
        'date_of_birth': '1992-02-02', 'national_id': 'SC' + suffix,
        'mother_name': 'Hooyo Scope', 'residence': 'Laascaanood',
        'phone': '+252 63 555 0100', 'sex': 'Male',
        'email': f'scope-{suffix}@example.com', 'purpose': 'Employment',
        'guardian_name': 'Guardian Scope', 'guardian_relationship': 'Uncle',
        'guardian_id': 'GD-9', 'guardian_occupation': 'Trader',
        'guardian_address': 'Burao', 'guardian_phone': '+252 63 555 0101',
    }
    if branch_id is not None:
        form['branch_id'] = branch_id
    pdf = b'%PDF-1.4 branch scope test'
    for slot in ('doc_app_0', 'doc_app_1', 'doc_guard_0', 'doc_guard_1'):
        form[slot] = (f'{slot}.pdf', pdf, 'application/pdf')
    return request(base, 'POST', '/api/clearance-applications', token, form=form)


def db_connection():
    """Direct connection to the test database (seeding rows the API needs a
    full multipart submission to create)."""
    import psycopg2
    import psycopg2.extras
    kwargs = {'dbname': os.environ.get('SENTINEL_DB_NAME', 'postgres'),
              'user': os.environ.get('SENTINEL_DB_USER', 'postgres'),
              'password': os.environ.get('SENTINEL_DB_PASSWORD') or None}
    if os.environ.get('SENTINEL_DB_HOST'):
        kwargs['host'] = os.environ['SENTINEL_DB_HOST']
    if os.environ.get('SENTINEL_DB_PORT'):
        kwargs['port'] = os.environ['SENTINEL_DB_PORT']
    conn = psycopg2.connect(**kwargs)
    conn.autocommit = True
    return conn, psycopg2.extras.RealDictCursor


def seed_airport_rows(rows):
    conn, cursor_factory = db_connection()
    with conn.cursor(cursor_factory=cursor_factory) as cur:
        for record_id, person_person_id, branch_id, movement in rows:
            cur.execute('SELECT id FROM persons WHERE person_id=%s', (person_person_id,))
            person = cur.fetchone()
            cur.execute('''INSERT INTO airport_passengers(record_id,person_id,branch_id,movement,
                travel_date,flight_number,origin_city,destination_city,route)
                VALUES(%s,%s,%s,%s,%s,%s,%s,%s,%s)''',
                (record_id, person['id'], branch_id, movement, '2026-09-01',
                 'HL-900', 'Berbera', 'Hargeisa', 'Berbera / Hargeisa'))
    conn.close()


def scope_of(token, base):
    status, me = request(base, 'GET', '/api/me', token)
    check(status == 200, 'the session payload is readable')
    return me


def run_api_suite(base):
    admin, admin_user = login(base, 'admin')
    ids = branch_ids(base, admin)
    lasanod_fp = ids[('fingerprint', 'Lasanod Branch')]
    erigavo_fp = ids[('fingerprint', 'Erigavo Branch')]
    lasanod_air = ids[('airport', 'Lasanod Branch')]
    erigavo_air = ids[('airport', 'Erigavo Branch')]

    print('== 1. the posting is resolved to one registered branch ==')
    create_user(base, admin, 'fp.lasanod', 'FingerprintUnit',
                unit='Lasanod Branch', district='Laascaanood', region='Sool')
    create_user(base, admin, 'fp.erigavo', 'FingerprintUnit',
                unit='Erigavo Branch', district='Ceerigaabo', region='Sanaag')
    create_user(base, admin, 'fp.legacy', 'FingerprintUnit', branch='Fingerprint Unit')
    create_user(base, admin, 'fp.fuzzy', 'FingerprintUnit', branch='  lasanod branch ')
    create_user(base, admin, 'ap.lasanod', 'AirportControl',
                unit='Lasanod Branch', district='Laascaanood', region='Sool')

    fp_lasanod, _ = login(base, 'fp.lasanod')
    me = scope_of(fp_lasanod, base)
    check(me.get('branch_scope') and me['branch_scope']['branch_id'] == lasanod_fp,
          f"the composed posting resolves to its branch ({me.get('branch_scope')})")
    check(me['branch_scope']['region'] == 'Sool'
          and me['branch_scope']['district'] == 'Laascaanood',
          'the resolved posting keeps its region and district')
    check(me.get('branch_scope_status', {}).get('resolved') is True,
          'the session reports the posting as resolved')
    check(me.get('branch_scope_status', {}).get('override') is False,
          'a standard officer holds no override')

    # A clean / noisy / legacy-region posting resolves to the same branch.
    fp_fuzzy, _ = login(base, 'fp.fuzzy')
    fuzzy = scope_of(fp_fuzzy, base)
    check(fuzzy.get('branch_scope') and fuzzy['branch_scope']['branch_id'] == lasanod_fp,
          "the legacy '  lasanod branch ' spelling resolves to the same branch")

    fp_legacy, _ = login(base, 'fp.legacy')
    legacy = scope_of(fp_legacy, base)
    check(legacy.get('branch_scope') is None,
          'an ambiguous unit-level posting ("Fingerprint Unit") resolves to nothing')
    check(legacy.get('branch_scope_status', {}).get('resolved') is False,
          'the session explains that the unit-level posting is unresolved')

    admin_me = scope_of(admin, base)
    check(admin_me.get('branch_scope') is None,
          'a System Administrator is never scoped to one branch')
    check(admin_me.get('branch_scope_status', {}).get('override') is True,
          'the administrator payload carries the override flag')

    print('== 2. strict read scoping on the clearance register ==')
    status, own = create_clearance(base, fp_lasanod, '1001', lasanod_fp)
    check(status in (200, 201), f'the scoped officer files at their own branch ({status} '
                                f'{own.get("error", "")})')
    own_id = own.get('application_id')
    status, other = create_clearance(base, admin, '1002', erigavo_fp)
    check(status in (200, 201), 'the administrator files at another branch')
    other_id = other.get('application_id')

    status, listing = request(base, 'GET', '/api/clearance-applications', fp_lasanod)
    check(status == 200, 'the scoped officer reads the clearance register')
    check(listing.get('branch_scope', {}).get('branch_id') == lasanod_fp if listing.get('branch_scope')
          else False, 'the register echoes the caller branch scope')
    listed = {item['application_id'] for item in listing['items']}
    check(own_id in listed, 'the officer sees their own branch application')
    check(other_id not in listed,
          'the officer never sees another branch application')

    status, detail = request(base, 'GET', f'/api/clearance-applications/{other_id}', fp_lasanod)
    check(status == 403 and detail.get('code') == 'branch_scope_forbidden',
          f'another branch application is refused by identifier ({status})')
    status, own_detail = request(base, 'GET', f'/api/clearance-applications/{own_id}', fp_lasanod)
    check(status == 200, 'their own application opens normally')

    status, admin_list = request(base, 'GET', '/api/clearance-applications', admin)
    admin_ids = {item['application_id'] for item in admin_list['items']}
    check(own_id in admin_ids and other_id in admin_ids,
          'the administrator still reads every branch')

    chief, _ = login(base, 'chief')
    status, chief_list = request(base, 'GET', '/api/clearance-applications', chief)
    chief_ids = {item['application_id'] for item in chief_list['items']}
    check(status == 200 and own_id in chief_ids and other_id in chief_ids,
          'the multi-branch Commander keeps the cross-branch override')
    status, chief_detail = request(base, 'GET', f'/api/clearance-applications/{other_id}', chief)
    check(status == 200, 'the Commander opens any branch record')

    print('== 3. strict write scoping ==')
    status, denied = create_clearance(base, fp_lasanod, '1003', erigavo_fp)
    check(status == 403 and denied.get('code') == 'branch_scope_forbidden',
          f'a cross-branch filing is refused ({status})')
    check('Lasanod Branch' in str(denied.get('error', '')),
          'the refusal names the officer posting')
    # A legacy client that omits branch_id is pinned to the officer's branch.
    status, implicit = create_clearance(base, fp_lasanod, '1004')
    check(status in (200, 201), 'a filing without an explicit branch still succeeds')
    status, implicit_list = request(base, 'GET', '/api/clearance-applications', fp_lasanod)
    match = [item for item in implicit_list['items']
             if item['application_id'] == implicit.get('application_id')]
    check(match and match[0].get('branch_name') == 'Lasanod Branch',
          'the omitted branch is adopted from the posting, never left empty')

    print('== 4. audit history respects the branch scope ==')
    status, audit_own = request(
        base, 'GET', f'/api/audit/entity/clearance_application/{own_id}', fp_lasanod)
    check(status == 200 and audit_own.get('items'),
          'the officer reads the history of their own record')
    status, audit_other = request(
        base, 'GET', f'/api/audit/entity/clearance_application/{other_id}', fp_lasanod)
    check(status == 403 and audit_other.get('code') == 'branch_scope_forbidden',
          f'another branch history is refused ({status})')
    status, audit_admin = request(
        base, 'GET', f'/api/audit/entity/clearance_application/{other_id}', admin)
    check(status == 200, 'the administrator reads any history')

    print('== 5. the same rule covers the other unit registers ==')
    seed_airport_rows([('AR-SCOPE-1', 'P-0001', lasanod_air, 'Arrival'),
                       ('AR-SCOPE-2', 'P-0002', erigavo_air, 'Departure')])
    ap_lasanod, _ = login(base, 'ap.lasanod')
    status, air_list = request(base, 'GET', '/api/airport-records', ap_lasanod)
    check(status == 200, 'the posted Airport officer reads the movement register')
    check(all(item.get('branch_id') == lasanod_air for item in air_list['items']),
          'every airport row belongs to the officer branch')
    air_ids = {item['record_id'] for item in air_list['items']}
    check('AR-SCOPE-1' in air_ids and 'AR-SCOPE-2' not in air_ids,
          'another branch movement is never listed')
    status, air_denied = request(base, 'POST', '/api/airport-records', ap_lasanod,
                                 {'person_id': 'P-0002', 'branch_id': erigavo_air,
                                  'movement': 'Departure', 'travel_date': '2026-09-02'})
    check(status == 403, f'a cross-branch airport movement is refused ({status})')

    # CID: the seeded cases carry no branch, so a scoped CID officer sees none
    # of them and never another branch's new case.
    create_user(base, admin, 'cid.lasanod', 'CIDUnit',
                unit='Lasanod Branch', district='Laascaanood', region='Sool')
    cid_lasanod, _ = login(base, 'cid.lasanod')
    status, case = request(base, 'POST', '/api/crime-cases', cid_lasanod,
                           {'branch_id': ids[('crime', 'Lasanod Branch')],
                            'category': 'Fraud', 'location': 'Laascaanood',
                            'incident_summary': 'Scope probe case'})
    check(status in (200, 201), f'the CID officer files a case at their branch ({status})')
    case_id = case.get('case_id')
    status, case_other = request(base, 'POST', '/api/crime-cases', admin,
                                 {'branch_id': ids[('crime', 'Erigavo Branch')],
                                  'category': 'Fraud', 'location': 'Ceerigaabo',
                                  'incident_summary': 'Other branch probe'})
    other_case = case_other.get('case_id')
    status, cases = request(base, 'GET', '/api/crime-cases', cid_lasanod)
    case_ids = {item['case_id'] for item in cases['items']}
    check(case_id in case_ids, 'the officer sees their own case')
    check(other_case not in case_ids, 'the officer never sees another branch case')
    status, case_detail = request(base, 'GET', f'/api/crime-cases/{other_case}', cid_lasanod)
    check(status == 403 and case_detail.get('code') == 'branch_scope_forbidden',
          f'another branch case is refused by identifier ({status})')
    status, own_case_detail = request(base, 'GET', f'/api/crime-cases/{case_id}', cid_lasanod)
    check(status == 200, 'their own case opens normally')

    print('== 6. an unresolved posting is never silently narrowed ==')
    status, legacy_list = request(base, 'GET', '/api/clearance-applications', fp_legacy)
    legacy_ids = {item['application_id'] for item in legacy_list['items']}
    check(status == 200 and other_id in legacy_ids and own_id in legacy_ids,
          'the unit-level posting keeps the pre-existing register view')
    check(legacy_list.get('branch_scope') is None,
          'the payload reports "no scope" instead of inventing one')


def main():
    tmp = tempfile.mkdtemp(prefix='sentinel-branch-scope-')
    db_env, stop_db = provision_database(tmp)
    if db_env is None:
        print('SKIP: no PostgreSQL test database available; configure SENTINEL_DB_* or install pgserver.')
        return 0
    os.environ.update({k: v for k, v in db_env.items() if v})
    port = free_port()
    env = dict(os.environ, **db_env)
    env.update(PORT=str(port), SENTINEL_UPLOADS=os.path.join(tmp, 'uploads'))
    server = subprocess.Popen([sys.executable, SERVER], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(120):
            try:
                status, _ = request(base, 'GET', '/api/health')
                if status == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('branch-scope test server did not start')
        run_api_suite(base)
        print('ALL BRANCH SCOPE / POSTING RESOLUTION TESTS PASSED')
        return 0
    finally:
        server.terminate()
        server.wait(timeout=10)
        stop_db()


if __name__ == '__main__':
    sys.exit(main())

#!/usr/bin/env python3
"""Integration coverage for the dynamic police branch catalogue.

The suite starts the Sentinel API against an explicitly configured PostgreSQL
server or a throwaway `pgserver` cluster, then checks the default seed rows,
unit/region filtering, administrator-only writes, duplicate validation, and
branch persistence on CID cases. It prints SKIP when no PostgreSQL test engine
is available.

Usage: python3 backend/test_dynamic_branches.py
"""
import json
import os
import socket
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.parse
import urllib.request

ROOT = os.path.dirname(os.path.abspath(__file__))
SERVER = os.path.join(ROOT, 'server.py')
PROJECT_ROOT = os.path.dirname(ROOT)
INDEX = os.path.join(PROJECT_ROOT, 'index.html')


def load_project_database_environment():
    """Mirror server.py's .env fallback so provisioning sees configured URLs too."""
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


def request(base, method, path, token=None, body=None):
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=payload, method=method)
    req.add_header('Content-Type', 'application/json')
    if token:
        req.add_header('Authorization', 'Bearer ' + token)
    try:
        with urllib.request.urlopen(req, timeout=15) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode())


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


def run_api_suite(base):
    status, unauthenticated = request(base, 'GET', '/api/branches')
    check(status == 401, 'branch catalogue requires an authenticated session')

    tokens = {}
    for username in ('admin', 'fp.officer', 'cid.officer'):
        status, result = request(base, 'POST', '/api/login', body={
            'username': username, 'password': 'ChangeMe123!'})
        check(status == 200 and result.get('token'), f'{username} demo account signs in')
        tokens[username] = result['token']

    admin, fp, cid = tokens['admin'], tokens['fp.officer'], tokens['cid.officer']
    status, catalogue = request(base, 'GET', '/api/branches', admin)
    check(status == 200, 'administrator reads the branch catalogue')
    branches = catalogue['items']
    expected = {
        ('East Togdheer', 'Buuhoodle Branch'),
        ('Sool', 'Lasanod Branch'),
        ('Sanaag', 'Erigavo Branch'),
    }
    seeded = {(row['region'], row['name']) for row in branches}
    check(all(pair in seeded for pair in expected), 'three requested regional branch names are seeded')
    default_rows={(name,region,unit) for region,name in expected
                  for unit in ('fingerprint','crime','checkpoint','airport')}
    actual_rows={(row['name'],row['region'],row['unit_type']) for row in branches}
    check(default_rows.issubset(actual_rows), 'each default branch is seeded for all four unit departments')

    status, filtered = request(base, 'GET', '/api/branches?unit_type=crime&region=Sool', cid)
    check(status == 200 and len(filtered['items']) == 1
          and filtered['items'][0]['name'] == 'Lasanod Branch',
          'GET filters by both unit_type and region')
    status, filtered = request(base, 'GET', '/api/branches?region=East%20Togdheer', fp)
    check(status == 200 and len(filtered['items']) == 4,
          'GET region-only filter returns the four unit rows for that region')
    status, invalid_filter = request(base, 'GET', '/api/branches?unit_type=unknown', admin)
    check(status == 400, 'unknown unit_type is rejected with HTTP 400')

    status, denied = request(base, 'POST', '/api/branches', fp, {
        'name': 'Unauthorized Branch', 'region': 'Sool', 'unit_type': 'fingerprint'})
    check(status == 401, 'non-admin unit officer cannot create branches')

    branch_name=f'Arena Test Branch {time.time_ns()}'
    status, created = request(base, 'POST', '/api/branches', admin, {
        'name': branch_name, 'region': 'Sool', 'unit_type': 'crime'})
    check(status == 201 and created.get('branch', {}).get('unit_type') == 'crime',
          'administrator creates a branch for one unit')
    branch = created['branch']
    status, duplicate = request(base, 'POST', '/api/branches', admin, {
        'name': branch_name.lower(), 'region': 'sool', 'unit_type': 'crime'})
    check(status == 409, 'duplicate branch names are rejected case-insensitively')
    status, visible = request(base, 'GET', '/api/branches?unit_type=crime&region=Sool', cid)
    check(status == 200 and any(row['id'] == branch['id'] for row in visible['items']),
          'new branch is immediately visible to the matching unit')

    wrong_unit = next(row for row in branches if row['unit_type'] == 'fingerprint')
    status, mismatch = request(base, 'POST', '/api/crime-cases', cid, {
        'category': 'Other', 'branch_id': wrong_unit['id']})
    check(status == 400, 'intake rejects a branch belonging to a different unit')
    status, created_case = request(base, 'POST', '/api/crime-cases', cid, {
        'category': 'Other', 'location': branch_name, 'branch_id': branch['id']})
    check(status == 201, 'CID case intake accepts a matching dynamic branch')
    status, cases = request(base, 'GET', '/api/crime-cases', cid)
    saved = next((row for row in cases.get('items', [])
                  if row.get('case_id') == created_case.get('case_id')), None)
    check(status == 200 and saved and saved['branch_id'] == branch['id']
          and saved['branch_name'] == branch_name,
          'selected branch persists on the crime case and is returned by GET')


def run_frontend_contract():
    html = open(INDEX, encoding='utf-8').read()
    for selector, unit in (('fpBranch', 'fingerprint'), ('airBranch', 'airport'),
                           ('cpBranch', 'checkpoint'), ('caseBranch', 'crime'),
                           ('crmBranch', 'crime')):
        check(f'id="{selector}"' in html and f'data-branch-unit="{unit}"' in html,
              f'{selector} is wired to dynamic {unit} branch data')
    check('+ Add New Branch' in html and '<section id="branches" class="page">' in html
          and 'data-page="branches" data-modules="admin"' in html,
          'SystemAdmin Administration navigation exposes a dedicated Branch Management page')
    check('<th>Branch Name</th>' in html and '<th>Region</th>' in html
          and '<th>Unit Department</th>' in html,
          'Branch Management lists Branch Name, Region and Unit Department')
    check("branches:'admin'" in html
          and "(page==='admin'||page==='branches') && !(sessionVisibility && sessionVisibility.is_admin)" in html,
          'Branch Management is routed and guarded as SystemAdmin-only')
    check('refreshBranchSelect' in html and "'/api/branches?unit_type='" in html,
          'intake dropdowns request branches from the database API')


def main():
    tmp = tempfile.mkdtemp(prefix='sentinel-branches-')
    db_env, stop_db = provision_database(tmp)
    if db_env is None:
        print('SKIP: no PostgreSQL test database available; configure SENTINEL_DB_* or install pgserver.')
        return 0
    port = free_port()
    env = dict(os.environ, **db_env)
    env.update(PORT=str(port), SENTINEL_UPLOADS=os.path.join(tmp, 'uploads'))
    server = subprocess.Popen([sys.executable, SERVER], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(90):
            try:
                status, _ = request(base, 'GET', '/api/health')
                if status == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('branch test server did not start')
        run_api_suite(base)
        run_frontend_contract()
        print('ALL DYNAMIC BRANCH TESTS PASSED')
        return 0
    finally:
        server.terminate()
        server.wait(timeout=10)
        stop_db()


if __name__ == '__main__':
    sys.exit(main())

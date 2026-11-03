#!/usr/bin/env python3
"""Crime Department (CID) regional scope: session payload, register isolation
and the strict regional hard-pruning of the sidebar crime tree.

  1. SESSION SCOPE FOR THE CID UNIT
     A CID officer's composed posting ('Laascaanood CID Office · Laascaanood ·
     Sool') resolves to exactly one registered CRIME branch and the session
     payload carries its region and district. A REGIONAL posting that names
     the territory but not one single branch ('Crime Department · Sool') is
     honestly reported unresolved by the API — the server never silently
     narrows — which is exactly the signal the sidebar uses to hard-prune the
     crime tree to the officer's region.

  2. CRIME REGISTER ISOLATION (regression guard)
     A scoped CID officer only receives the cases filed under their own
     branch, cannot open another branch's case by identifier (403
     `branch_scope_forbidden`) and cannot file a cross-branch case; the
     System Administrator keeps the national register.

  3. SERVED UI SHIPS THE CID HARD-PRUNE
     GET / must contain the CID-only regional scope renderer, the
     identity-beats-geography filter and the scope-aware paint-cache
     signature, and `python backend/server.py --ui-check` must exit 0.

  4. DOM PROOF (optional, needs node + jsdom)
     When node and jsdom are available, the served page is driven in jsdom:
     a regional CID officer's crime tree contains ONLY their parent region
     (foreign regions / unassigned groups are pruned from the DOM), the paint
     signature is scope-aware, and `unitInNavScope` rejects a foreign branch
     id inside the officer's own region/district.

Usage: python3 backend/test_crime_department_scope.py
"""
import json
import os
import shutil
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


def request(base, method, path, token=None, body=None):
    payload = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(base + path, data=payload, method=method)
    req.add_header('Content-Type', 'application/json')
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


def create_user(base, admin, username, role, branch):
    payload = {'username': username, 'display_name': f'Officer {username}',
               'password': PASSWORD, 'role': role, 'branch': branch}
    status, body = request(base, 'POST', '/api/admin/users', admin, payload)
    check(status in (200, 201), f'{username} is created ({status} {body.get("error", "")})')
    return body['user']


def create_branch(base, admin, name, region, district, unit_type='crime'):
    status, body = request(base, 'POST', '/api/branches', admin,
                           {'name': name, 'region': region, 'district': district,
                            'unit_type': unit_type})
    check(status in (200, 201), f'the crime branch {name} is registered ({status} '
                                f'{body.get("error", "")})')
    return body['branch']


def served_ui(base):
    """The index.html the server actually serves (falls back to the file)."""
    try:
        with urllib.request.urlopen(base + '/', timeout=15) as response:
            html = response.read().decode()
            if '<html' in html.lower():
                return html
    except Exception:
        pass
    with open(os.path.join(PROJECT_ROOT, 'index.html'), encoding='utf-8') as fh:
        return fh.read()


def run_api_suite(base):
    admin, _ = login(base, 'admin')

    print('== 1. the CID catalogue spans the three regions ==')
    create_branch(base, admin, 'Laascaanood CID Office', 'Sool', 'Laascaanood')
    create_branch(base, admin, 'Xudun CID Post', 'Sool', 'Xudun')
    status, catalogue = request(base, 'GET', '/api/branches', admin)
    check(status == 200, 'the branch catalogue is readable')
    crime_branches = [b for b in catalogue['items'] if b['unit_type'] == 'crime']
    crime_regions = {b['region'] for b in crime_branches}
    check({'Sool', 'Sanaag', 'East Togdheer'} <= crime_regions,
          f'crime branches exist in all three regions ({sorted(crime_regions)})')
    ids = {(b['region'], b['name']): b['id'] for b in crime_branches}
    lasanod_cid = ids[('Sool', 'Laascaanood CID Office')]
    erigavo_cid = ids[('Sanaag', 'Erigavo Branch')]

    print('== 2. the session payload scopes a CID officer to their branch + region ==')
    create_user(base, admin, 'cid.lasanod', 'CIDUnit',
                'Laascaanood CID Office · Laascaanood · Sool')
    cid_token, _ = login(base, 'cid.lasanod')
    status, me = request(base, 'GET', '/api/me', cid_token)
    check(status == 200, 'the CID session payload is readable')
    scope = me.get('branch_scope') or {}
    check(scope.get('branch_id') == lasanod_cid,
          f"the composed posting resolves to the Sool crime branch ({scope})")
    check(scope.get('region') == 'Sool' and scope.get('district') == 'Laascaanood',
          'the resolved scope carries the region and district')
    check(me.get('branch_scope_status', {}).get('resolved') is True
          and me['branch_scope_status'].get('override') is False,
          'the CID session reports a resolved, non-override posting')

    print('== 3. a regional CID posting is honestly unresolved server-side ==')
    # 'Crime Department · Sool' names the territory but not one single branch
    # (two crime branches exist in Sool): the API must say so instead of
    # inventing a scope — the sidebar then hard-prunes the tree regionally.
    create_user(base, admin, 'cid.regional', 'CIDUnit', 'Crime Department · Sool')
    regional_token, _ = login(base, 'cid.regional')
    status, regional_me = request(base, 'GET', '/api/me', regional_token)
    check(status == 200, 'the regional CID session payload is readable')
    check(regional_me.get('branch_scope') is None,
          'an ambiguous regional posting resolves to no single branch (never guessed)')
    regional_status = regional_me.get('branch_scope_status') or {}
    check(regional_status.get('resolved') is False
          and regional_status.get('posting') == 'Crime Department · Sool',
          'the payload explains the posting is unresolved and echoes it verbatim')

    print('== 4. the crime register stays strictly branch-isolated ==')
    status, own_case = request(base, 'POST', '/api/crime-cases', cid_token,
                               {'branch_id': lasanod_cid, 'category': 'Fraud',
                                'location': 'Laascaanood',
                                'incident_summary': 'CID scope probe (own branch)'})
    check(status in (200, 201), f'the scoped CID officer files at their own branch ({status} '
                                f'{own_case.get("error", "")})')
    own_case_id = own_case.get('case_id')
    status, other_case = request(base, 'POST', '/api/crime-cases', admin,
                                 {'branch_id': erigavo_cid, 'category': 'Robbery',
                                  'location': 'Ceerigaabo',
                                  'incident_summary': 'CID scope probe (foreign branch)'})
    check(status in (200, 201), 'the administrator files at the Sanaag crime branch')
    other_case_id = other_case.get('case_id')

    status, listing = request(base, 'GET', '/api/crime-cases', cid_token)
    check(status == 200, 'the scoped CID officer reads the crime register')
    check((listing.get('branch_scope') or {}).get('branch_id') == lasanod_cid,
          'the register echoes the caller branch scope')
    listed = {item['case_id'] for item in listing['items']}
    check(own_case_id in listed, 'the officer sees their own branch case')
    check(other_case_id not in listed, 'the officer never sees another branch case')
    status, denied = request(base, 'GET', f'/api/crime-cases/{other_case_id}', cid_token)
    check(status == 403 and denied.get('code') == 'branch_scope_forbidden',
          f'another branch case is refused by identifier ({status})')
    status, own_detail = request(base, 'GET', f'/api/crime-cases/{own_case_id}', cid_token)
    check(status == 200, 'the officer own case opens normally')
    status, cross = request(base, 'POST', '/api/crime-cases', cid_token,
                            {'branch_id': erigavo_cid, 'category': 'Theft/Burglary',
                             'location': 'Ceerigaabo', 'incident_summary': 'cross-branch'})
    check(status == 403 and cross.get('code') == 'branch_scope_forbidden',
          f'a cross-branch filing is refused ({status})')
    status, admin_listing = request(base, 'GET', '/api/crime-cases', admin)
    admin_ids = {item['case_id'] for item in admin_listing['items']}
    check(own_case_id in admin_ids and other_case_id in admin_ids,
          'the administrator still reads every branch')


def run_ui_marker_suite(base):
    print('== 5. the served UI ships the CID-only regional hard-prune ==')
    html = served_ui(base)
    markers = (
        ('Crime unit tree mount', 'data-nav-regions="crime"'),
        ('Branch-scoped navigation scope', 'function navUnitScope('),
        ('CID-only regional scope renderer', 'function crimeRegionalNavScope('),
        ('CID-only fallback call', "if(type==='crime') return crimeRegionalNavScope();"),
        ('Identity-beats-geography filter', 'UNIT IDENTITY BEATS GEOGRAPHY'),
        ('Scope-aware paint cache', 'SCOPE-AWARE'),
        ('Scope folded into the paint signature', 'scope:scope?'),
    )
    for label, marker in markers:
        check(marker in html, f'GET / ships the {label}: {marker!r}')
    check(html.count("return crimeRegionalNavScope();") == 1,
          'the regional fallback is wired exactly once, for the crime tree only')
    # The other units' trees are untouched by the fix.
    for unit in ('fingerprint', 'airport', 'checkpoint', 'police_station'):
        check(f'data-nav-regions="{unit}"' in html,
              f'the {unit} tree mount is still present')

    print('== 6. the UI self-check still passes ==')
    result = subprocess.run([sys.executable, SERVER, '--ui-check'],
                            cwd=PROJECT_ROOT, capture_output=True, text=True, timeout=120)
    check(result.returncode == 0, 'python backend/server.py --ui-check exits 0')


DOM_HARNESS = r'''
// DOM proof for the CID regional hard-prune, driven against the served page.
const fs = require('fs');
const vm = require('vm');
const { JSDOM } = require('jsdom');
const html = fs.readFileSync(process.argv[2], 'utf8');
const dom = new JSDOM(html, { url: 'http://sentinel.test', runScripts: 'outside-only' });
const w = dom.window;
const ctx = dom.getInternalVMContext();
w.matchMedia = () => ({ matches: false });
w.fetch = async () => { throw new Error('no network'); };
const run = (s) => vm.runInContext(s, ctx);
const query = (sel) => w.document.querySelector(sel);
const script = html.match(/<script>([\s\S]*?)<\/script>/)[1]
  .replace(/if\(document\.readyState==='loading'\)[\s\S]*$/, '');
run(script);
const ALL = ['dashboard','people','fingerprint','airport','cid','checkpoints','admin',
  'stations','crimes','officers','conduct','cars','policesearch','executive','oversight'];
function signIn(role, extra, isAdmin) {
  const user = { role, modules: ALL, display_name: 'T', role_label: role, ...extra };
  run(`sessionUser=${JSON.stringify(user)};currentUser=sessionUser;
    sessionVisibility={is_admin:${!!isAdmin},can_manage_users:${!!isAdmin},
      can_manage_records:${!!isAdmin},can_manage_stations:${!!isAdmin}};
    applyNavForRole();updateUserPill();`);
}
const BRANCHES = [
  { id:'c1', name:'Laascaanood CID Office', region:'Sool', district:'Laascaanood', unit_type:'crime' },
  { id:'c2', name:'Xudun CID Post',       region:'Sool', district:'Xudun',      unit_type:'crime' },
  { id:'c3', name:'Laascaanood CID Annex',region:'Sool', district:'Laascaanood', unit_type:'crime' },
  { id:'c4', name:'Erigavo CID Office',   region:'Sanaag', district:'Ceerigaabo', unit_type:'crime' },
  { id:'c5', name:'Burao CID Office',     region:'East Togdheer', district:'Burao', unit_type:'crime' },
  { id:'f1', name:'Lasanod Branch',       region:'Sool', district:'Laascaanood', unit_type:'fingerprint' },
  { id:'f3', name:'Taleex Branch',        region:'Sool', district:'Taleex',      unit_type:'fingerprint' },
  { id:'f2', name:'Erigavo Branch',       region:'Sanaag', district:'Ceerigaabo', unit_type:'fingerprint' },
];
run(`branchCatalog={loaded:true,items:${JSON.stringify(BRANCHES)},regions:[],unit_types:[],districts:[]};renderUnitNavTrees();`);
const mount = () => query('#nav [data-nav-regions="crime"]');
const regions = () => [...mount().querySelectorAll('.nav-region')].map(r=>r.dataset.navRegion);
const units = () => [...mount().querySelectorAll('.nav-unit')].map(u=>u.dataset.unitLabel);
const assert = require('node:assert/strict');

// A regional CID officer (Sool): foreign parent regions are pruned from the DOM.
signIn('CIDUnit', { branch:'Crime Department · Sool',
  branch_scope_status:{ resolved:false, scoped:false, override:false, posting:'Crime Department · Sool', branch:null } }, false);
assert.deepEqual(regions(), ['Sool'], 'regional CID officer: only their own parent region renders');
assert.equal(mount().querySelector('[data-nav-region="Sanaag"]'), null, 'Sanaag pruned from the DOM');
assert.equal(mount().querySelector('[data-nav-region="East Togdheer"]'), null, 'East Togdheer pruned from the DOM');
assert.equal(mount().querySelector('[data-nav-region="Unassigned region"]'), null, 'unassigned region pruned');
assert.deepEqual(units().sort(), ['Laascaanood CID Annex','Laascaanood CID Office','Xudun CID Post']);

// Branch identity beats geography: the resolved branch scope rejects the
// sibling branch id inside the same region + district.
signIn('CIDUnit', { branch:'Laascaanood CID Office · Laascaanood · Sool',
  branch_scope_status:{ resolved:true, scoped:true, override:false,
    branch:{ branch_id:'c1', branch_name:'Laascaanood CID Office', region:'Sool',
             district:'Laascaanood', unit_type:'crime' } } }, false);
assert.deepEqual(regions(), ['Sool']);
assert.deepEqual(units(), ['Laascaanood CID Office'], 'foreign branch id in own region+district pruned');
run(`var __s={branch_id:'c1',branch_name:'Laascaanood CID Office',region:'Sool',district:'Laascaanood'};`);
assert.equal(run(`unitInNavScope({label:'Laascaanood CID Annex',region:'Sool',district:'Laascaanood',branch_id:'c3'},__s)`), false);
assert.equal(run(`unitInNavScope({label:'Laascaanood CID Office',region:'Sool',district:'Laascaanood',branch_id:'c1'},__s)`), true);

// The paint cache is scope-aware: the admin national paint is never reused.
signIn('SystemAdmin', {}, true);
const adminSig = mount().dataset.navSig;
assert.equal(JSON.parse(adminSig).scope, null);
assert.ok(regions().includes('Sanaag'), 'admin keeps the national crime tree');
signIn('CIDUnit', { branch:'Crime Department · Sool',
  branch_scope_status:{ resolved:false, scoped:false, override:false, posting:'Crime Department · Sool', branch:null } }, false);
assert.notEqual(mount().dataset.navSig, adminSig, 'scope change forces a repaint');
assert.deepEqual(JSON.parse(mount().dataset.navSig).scope, { b:'', n:'', r:'Sool', d:'' });
assert.deepEqual(regions(), ['Sool'], 'repaint pruned the foreign regions');

// Isolation: the fingerprint tree keeps its legacy national view.
assert.ok([...query('#nav [data-nav-regions="fingerprint"]').querySelectorAll('.nav-region')]
  .map(r=>r.dataset.navRegion).includes('Sanaag'), 'fingerprint tree untouched (national view)');
console.log('DOM-PROBE-PASS');
w.close();
'''


def run_dom_probe(base, tmp):
    node = shutil.which('node')
    if not node:
        print('SKIP: node is not available — the DOM probe needs node + jsdom '
              '(backend/test_sidebar_navigation.mjs covers it)')
        return
    probe = subprocess.run(
        [node, '-e', "require.resolve('jsdom')"], cwd=PROJECT_ROOT,
        capture_output=True, text=True)
    if probe.returncode != 0:
        print('SKIP: jsdom is not installed — run '
              '`npm install --no-save --package-lock=false jsdom@26` '
              '(backend/test_sidebar_navigation.mjs covers the DOM probe)')
        return
    print('== 7. DOM probe: the crime tree is hard-pruned for a regional CID officer ==')
    harness = os.path.join(tmp, 'cid_dom_probe.cjs')
    with open(harness, 'w', encoding='utf-8') as fh:
        fh.write(DOM_HARNESS)
    env = dict(os.environ, NODE_PATH=os.path.join(PROJECT_ROOT, 'node_modules'))
    result = subprocess.run([node, harness, os.path.join(PROJECT_ROOT, 'index.html')],
                            cwd=PROJECT_ROOT, env=env, capture_output=True, text=True, timeout=180)
    output = result.stdout + result.stderr
    check('DOM-PROBE-PASS' in output and result.returncode == 0,
          'the jsdom DOM probe passes (regional prune, identity-beats-geography, '
          f'scope-aware paint cache) — node exit {result.returncode}\n{output[-2000:]}')


def main():
    tmp = tempfile.mkdtemp(prefix='sentinel-crime-dept-scope-')
    db_env, stop_db = provision_database(tmp)
    if db_env is None:
        print('SKIP: no PostgreSQL test database available; configure SENTINEL_DB_* or install pgserver.')
        return 0
    os.environ.update({k: v for k, v in db_env.items() if v})
    port = free_port()
    env = dict(os.environ, **db_env)
    env.update(PORT=str(port), SENTINEL_UPLOADS=os.path.join(tmp, 'uploads'))
    server = subprocess.Popen([sys.executable, SERVER], env=env, cwd=PROJECT_ROOT,
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
            raise RuntimeError('crime-department-scope test server did not start')
        run_api_suite(base)
        run_ui_marker_suite(base)
        run_dom_probe(base, tmp)
        print('ALL CRIME DEPARTMENT SCOPE TESTS PASSED')
        return 0
    finally:
        server.terminate()
        server.wait(timeout=10)
        stop_db()


if __name__ == '__main__':
    sys.exit(main())

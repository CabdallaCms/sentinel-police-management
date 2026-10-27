#!/usr/bin/env python3
"""PyTest coverage — Branch Management full CRUD (Edit / Deactivate) + cleanup.

What this pins, in the same order the feature ships:

  1. PURE VALIDATION (no database, always runs)
     `plan_branch_update()` is the one place a Branch Management edit is
     validated: PATCH semantics (only the supplied fields move), the name /
     region / district rules, the gazetteer check (a district must belong to
     its region), the Active / Inactive coercion and the changed-field
     bookkeeping the audit row prints. `branch_view()` publishes the lifecycle
     and placement metadata the UI renders, `branch_legacy_reason()` is the
     single predicate behind the "Unassigned district" cleanup queue.

  2. FRONTEND CONTRACT (no database, always runs)
     The served page carries the Actions → Edit modal, the Active / Inactive
     toggle, the legacy batch-placement panel and the live catalogue repaint,
     and the asset version stamps agree with the server.

  3. LIVE API (needs PostgreSQL — SKIPped otherwise)
     `PATCH /api/admin/branches/<id>` renames / re-places / retires a branch in
     place (same id, so every FK survives), answers 403 for a non-admin and
     409 for a duplicate, relabels the free-text officer posting, moves the
     mirrored Police Stations row and writes an audit row;
     `GET /api/branches?active=1` drops a deactivated branch while its records
     and postings keep their link; `POST /api/admin/branches/bulk-assign`
     places the legacy rows in one batch.

Usage:
    python3 -m pytest backend/test_branch_management_crud.py -q
    python3 backend/test_branch_management_crud.py          # same, no pytest

Database resolution mirrors the other suites: SENTINEL_DATABASE_URL or the
SENTINEL_DB_* variables when set, otherwise a throwaway `pgserver` cluster,
otherwise SKIP (the pure + contract tests still run and pass).
"""
import importlib.util
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
PROJECT_ROOT = os.path.dirname(ROOT)
SERVER = os.path.join(ROOT, 'server.py')
INDEX = os.path.join(PROJECT_ROOT, 'index.html')


def load_server_module():
    """Import backend/server.py without requiring psycopg2 for the pure tests.

    `--ui-check` is the module's documented "inspect files only" mode; adding it
    to argv for the duration of the import lets the file import on a machine
    without the PostgreSQL driver (exactly like `python server.py --ui-check`),
    while the live suite below still needs a real database.
    """
    spec = importlib.util.spec_from_file_location('sentinel_branch_crud_server', SERVER)
    module = importlib.util.module_from_spec(spec)
    saved = list(sys.argv)
    if '--ui-check' not in sys.argv:
        sys.argv.append('--ui-check')
    try:
        spec.loader.exec_module(module)
    finally:
        sys.argv[:] = saved
    return module


srv = load_server_module()


# ---------------------------------------------------------------------------
# 1. pure validation — the edit plan
# ---------------------------------------------------------------------------
def placed_branch(**overrides):
    row = {'id': 12, 'name': 'Lasanod Branch', 'region': 'Sool',
           'district': 'Laascaanood', 'unit_type': 'checkpoint', 'active': 1,
           'updated_at': None, 'updated_by': None}
    row.update(overrides)
    return row


def test_branch_view_publishes_lifecycle_and_placement():
    view = srv.branch_view(placed_branch())
    assert view['id'] == 12
    assert view['active'] is True and view['status'] == 'Active'
    assert view['unit_label'] == 'Checkpoint Unit'
    assert view['legacy_reason'] is None
    # A pre-migration row (no `active`, no `district`) is Active, not crashed on.
    legacy = srv.branch_view({'id': 99, 'name': 'East Checkpoint',
                              'region': 'Sool', 'unit_type': 'checkpoint'})
    assert legacy['active'] is True and legacy['status'] == 'Active'
    assert legacy['district'] is None
    assert legacy['legacy_reason'] == 'No district assigned'
    retired = srv.branch_view(placed_branch(active=0))
    assert retired['active'] is False and retired['status'] == 'Inactive'
    assert srv.branch_view(None) is None


def test_branch_legacy_reason_matches_the_sidebar_groups():
    reason = srv.branch_legacy_reason
    assert reason(placed_branch()) == ''
    assert reason({'region': 'Sool', 'district': ''}) == 'No district assigned'
    assert reason({'region': '', 'district': ''}) == 'No region assigned'
    assert reason({'region': 'Unassigned region', 'district': 'X'}) == 'No region assigned'
    assert reason({'region': 'Sool', 'district': 'Burao'}) == \
        'District “Burao” is not part of Sool'
    # The legacy 'district = region' fallback is not a placed branch.
    assert reason({'region': 'East', 'district': 'East'}) == 'No district assigned'
    assert reason({'region': 'Awdal', 'district': 'Borama'}).startswith(
        'Region “Awdal” is outside the gazetteer')


def test_normalise_branch_active_accepts_every_toggle_spelling():
    assert srv.normalise_branch_active(True) == 1
    assert srv.normalise_branch_active(False) == 0
    assert srv.normalise_branch_active(1) == 1
    assert srv.normalise_branch_active(0) == 0
    for value in ('Active', 'active', 'true', 'yes', 'on', '1'):
        assert srv.normalise_branch_active(value) == 1, value
    for value in ('Inactive', 'inactive', 'false', 'no', 'off', '0', 'Deactivated'):
        assert srv.normalise_branch_active(value) == 0, value
    for bad in (None, 'maybe', 7, []):
        try:
            srv.normalise_branch_active(bad)
        except ValueError:
            pass
        else:                                       # pragma: no cover - diagnostic
            raise AssertionError(f'{bad!r} should be rejected')


def test_branch_is_active_treats_missing_flag_as_active():
    assert srv.branch_is_active({}) is True
    assert srv.branch_is_active({'active': None}) is True
    assert srv.branch_is_active({'active': True}) is True
    assert srv.branch_is_active({'active': 0}) is False
    assert srv.branch_is_active({'active': '0'}) is False
    assert srv.branch_is_active({'active': 'Inactive'}) is False


def test_validate_branch_placement_enforces_the_gazetteer():
    assert srv.validate_branch_placement('Sool', 'Laascaanood') == ('Sool', 'Laascaanood')
    assert srv.validate_branch_placement(' Sanaag ', ' Ceerigaabo ') == ('Sanaag', 'Ceerigaabo')
    # A district cannot belong to another region …
    for region, district in (('Sool', 'Burao'), ('Sanaag', 'Laascaanood'),
                             ('East Togdheer', 'Badhan')):
        try:
            srv.validate_branch_placement(region, district)
        except ValueError as exc:
            assert 'District must belong to' in str(exc), exc
        else:                                       # pragma: no cover - diagnostic
            raise AssertionError(f'{region}/{district} should be rejected')
    # … and the legacy 'region repeated as the district' fallback is refused.
    try:
        srv.validate_branch_placement('Awdal', 'Awdal')
    except ValueError:
        pass
    else:                                           # pragma: no cover - diagnostic
        raise AssertionError('region-as-district should be rejected')
    assert srv.validate_branch_placement('Awdal', 'Awdal', allow_unchanged=True) == \
        ('Awdal', 'Awdal')
    for region, district in (('', 'Laascaanood'), ('Sool', ''), ('Sool', '   ')):
        try:
            srv.validate_branch_placement(region, district)
        except ValueError:
            pass
        else:                                       # pragma: no cover - diagnostic
            raise AssertionError(f'{region!r}/{district!r} should be rejected')


def test_plan_branch_update_renames_without_touching_placement():
    plan = srv.plan_branch_update(placed_branch(), {'name': '  East   Lasanod  Checkpoint '})
    assert plan['changed'] == ['name']
    assert plan['values'] == {'name': 'East Lasanod Checkpoint'}
    assert plan['unchanged'] is False
    assert plan['result']['district'] == 'Laascaanood'
    assert plan['previous']['name'] == 'Lasanod Branch'


def test_plan_branch_update_replaces_region_and_district():
    plan = srv.plan_branch_update(placed_branch(), {'region': 'Sanaag',
                                                    'district': 'Badhan'})
    assert sorted(plan['changed']) == ['district', 'region']
    assert plan['result']['region'] == 'Sanaag'
    assert plan['result']['district'] == 'Badhan'
    # Renaming + re-placing in one save is the "East → East Lasanod Checkpoint"
    # flow from the specification.
    plan = srv.plan_branch_update(placed_branch(name='East', district='',
                                                region='Sool'),
                                  {'name': 'East Lasanod Checkpoint', 'region': 'Sool',
                                   'district': 'Laascaanood'})
    assert set(plan['changed']) == {'name', 'district'}
    assert plan['result'] == {'name': 'East Lasanod Checkpoint', 'region': 'Sool',
                              'district': 'Laascaanood', 'unit_type': 'checkpoint',
                              'active': 1}


def test_plan_branch_update_toggles_the_lifecycle_flag():
    plan = srv.plan_branch_update(placed_branch(), {'active': False})
    assert plan['changed'] == ['active'] and plan['values'] == {'active': 0}
    plan = srv.plan_branch_update(placed_branch(active=0), {'active': 'Active'})
    assert plan['changed'] == ['active'] and plan['values'] == {'active': 1}
    # A no-op toggle is still a valid PATCH; it just writes nothing.
    plan = srv.plan_branch_update(placed_branch(), {'active': True})
    assert plan['unchanged'] is True and plan['values'] == {}


def test_plan_branch_update_changes_the_unit_department():
    plan = srv.plan_branch_update(placed_branch(), {'unit_type': 'Police Stations'})
    assert plan['changed'] == ['unit_type']
    assert plan['values'] == {'unit_type': 'police_station'}


def test_plan_branch_update_rejects_invalid_edits():
    cases = [
        ({}, 'Nothing to update'),
        ({'name': ''}, 'Branch name is required'),
        ({'name': 'x' * 161}, '160 characters or fewer'),
        ({'region': ''}, 'Branch region is required'),
        ({'district': ''}, 'District is required'),
        ({'district': 'Burao'}, 'District must belong to Sool'),
        ({'active': 'maybe'}, 'active must be'),
        ({'unit_type': 'bogus'}, 'unit_type must be one of'),
    ]
    for payload, expected in cases:
        try:
            srv.plan_branch_update(placed_branch(), payload)
        except ValueError as exc:
            assert expected in str(exc), f'{payload} -> {exc}'
        else:                                       # pragma: no cover - diagnostic
            raise AssertionError(f'{payload} should be rejected')


def test_plan_branch_update_allows_an_unrelated_edit_on_a_legacy_row():
    """The cleanup queue must not block a rename / toggle on an unplaced row."""
    legacy = {'id': 7, 'name': 'West Checkpoint', 'region': 'Sool',
              'district': 'Sool', 'unit_type': 'checkpoint', 'active': 1}
    plan = srv.plan_branch_update(legacy, {'name': 'West Lasanod Checkpoint'})
    assert plan['changed'] == ['name']
    plan = srv.plan_branch_update(legacy, {'active': False})
    assert plan['changed'] == ['active']
    # Touching the placement now forces a valid gazetteer pair.
    plan = srv.plan_branch_update(legacy, {'district': 'Laascaanood'})
    assert plan['changed'] == ['district']
    try:
        srv.plan_branch_update(legacy, {'district': 'Sool'})
    except ValueError as exc:
        assert 'District must belong to Sool' in str(exc)
    else:                                           # pragma: no cover - diagnostic
        raise AssertionError('region-as-district should be rejected')


def test_branch_member_alias_resolves_to_the_admin_route():
    assert srv.canonical_api_path('/branches/42') == '/api/branches/42'
    assert srv.canonical_api_path('/api/branches/42') == '/api/branches/42'
    assert srv.canonical_api_path('/branches') == '/api/branches'
    assert srv.canonical_api_path('/api/branches/') == '/api/branches'


# ---------------------------------------------------------------------------
# 2. frontend / asset contract
# ---------------------------------------------------------------------------
def test_frontend_contract_for_branch_editing():
    html = open(INDEX, encoding='utf-8').read()
    branch_section = html.split('<section id="branches" class="page">')[1]
    header = branch_section.split('<tbody id="branchTable">')[0]
    assert '<th>Actions</th>' in header, 'the branch table exposes an Actions column'
    assert header.index('<th>Actions</th>') > header.index('<th>Unit Department</th>')
    assert 'data-branch-action="edit"' in html and 'function openBranchEdit(' in html
    assert 'id="branchEditModal"' in html and 'id="branchEditForm"' in html
    assert 'async function saveBranchEdit(' in html
    assert "/api/admin/branches/" in html, 'the modal PATCHes the admin member route'
    assert 'method:\'PATCH\'' in html or 'method:"PATCH"' in html or "method:'PATCH'" in html
    assert 'function branchIsActive(' in html and 'function activeBranchItems(' in html
    assert 'id="branchEditActive"' in html, 'the Active / Inactive toggle is in the modal'
    assert 'id="branchLegacyPanel"' in html and 'id="branchLegacyTable"' in html
    assert 'async function assignLegacyBranches(' in html
    assert '/api/admin/branches/bulk-assign' in html
    # Real-time sidebar re-placement: the saved row is merged into the ONE
    # catalogue the tree reads, then every consumer repaints.
    assert 'function applyBranchUpdate(' in html and 'function repaintBranchConsumers(' in html
    assert 'renderUnitNavTrees();' in html
    # The sidebar tree and the intake dropdowns skip a retired branch.
    assert 'branchIsActive(b)' in html
    # Edit / toggle controls are inside the SystemAdmin-only hide rule.
    assert 'body:not(.can-edit-records) .admin-edit{display:none !important}' in html
    assert '<div class="admin-edit">\n<div class="cmodal-ov" id="branchEditOv"' in html


def test_asset_stamps_agree_with_the_server():
    assert srv.ASSET_VERSION == 'e7c41b90'
    assert srv.UI_BUILD.endswith(srv.ASSET_VERSION)
    assert srv.static_asset_version_consistent(), \
        'every ?v= stamp in index / application / certificate matches ASSET_VERSION'
    html = open(INDEX, encoding='utf-8').read()
    assert f'?v={srv.ASSET_VERSION}' in html
    assert f'content="{srv.UI_BUILD}"' in html
    # A stale page is refused at startup, so the new feature must be a marker.
    markers = dict(srv.UI_REQUIRED_MARKERS)
    for label in ('Branch Actions column', 'Branch edit modal',
                  'Branch active/inactive toggle', 'Legacy placement cleanup tool',
                  'Legacy batch assignment', 'Live branch catalogue repaint'):
        assert label in markers, label
        assert markers[label] in html, f'{label} marker missing from index.html'
    assert not srv.ui_self_test()


# ---------------------------------------------------------------------------
# 3. live API (PostgreSQL) — skipped when no engine is available
# ---------------------------------------------------------------------------
PG_SERVE = '''
import pathlib, sys, pgserver
data = pathlib.Path(sys.argv[1]); data.mkdir(parents=True, exist_ok=True)
server = pgserver.get_server(str(data))
print(data, flush=True)
sys.stdin.read()
'''


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
        with urllib.request.urlopen(req, timeout=20) as response:
            return response.status, json.loads(response.read().decode())
    except urllib.error.HTTPError as error:
        return error.code, json.loads(error.read().decode())


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


def provision_database(tmp):
    """A throwaway PostgreSQL cluster, or None when nothing is available."""
    load_project_database_environment()
    if (os.environ.get('SENTINEL_DATABASE_URL', '').strip()
            or any(os.environ.get(key) for key in (
                'SENTINEL_DB_HOST', 'SENTINEL_DB_PORT', 'SENTINEL_DB_USER',
                'SENTINEL_DB_PASSWORD', 'SENTINEL_DB_NAME'))):
        return {}, lambda: None
    try:
        import pgserver  # noqa: F401
    except ImportError:
        return None, None
    try:
        import psycopg2  # noqa: F401
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


def test_live_branch_edit_deactivate_and_cleanup():
    tmp = tempfile.mkdtemp(prefix='sentinel-branch-crud-')
    db_env, stop_db = provision_database(tmp)
    if db_env is None:
        message = ('SKIP: no PostgreSQL test database available; configure '
                   'SENTINEL_DB_* or install pgserver.')
        if os.environ.get('PYTEST_CURRENT_TEST') is not None:
            import pytest
            pytest.skip(message)
        print(message)
        return
    port = free_port()
    env = dict(os.environ, **db_env)
    env.update(PORT=str(port), SENTINEL_UPLOADS=os.path.join(tmp, 'uploads'))
    server = subprocess.Popen([sys.executable, SERVER], env=env,
                              stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(120):
            try:
                if request(base, 'GET', '/api/health')[0] == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:                                       # pragma: no cover - environment
            raise RuntimeError('branch CRUD test server did not start')
        run_live_suite(base)
    finally:
        server.terminate()
        server.wait(timeout=15)
        stop_db()


def sign_in(base, username):
    status, payload = request(base, 'POST', '/api/login', body={
        'username': username, 'password': 'ChangeMe123!'})
    assert status == 200 and payload.get('token'), f'{username} signs in'
    return payload['token']


def run_live_suite(base):
    admin = sign_in(base, 'admin')
    fingerprint = sign_in(base, 'fp.officer')

    # ---- read: the administration catalogue carries lifecycle + cleanup ----
    status, catalogue = request(base, 'GET', '/api/admin/branches', admin)
    assert status == 200, catalogue
    assert set(catalogue['counts']) >= {'total', 'active', 'inactive', 'unassigned'}
    assert 'Laascaanood' in catalogue['gazetteer']['Sool']
    assert set(catalogue['gazetteer_regions']) == {'Sool', 'Sanaag', 'East Togdheer'}
    status, denied = request(base, 'GET', '/api/admin/branches', fingerprint)
    assert status in (401, 403), 'the admin catalogue is SystemAdmin-only'

    checkpoint_branch = next(b for b in catalogue['items']
                             if b['unit_type'] == 'checkpoint')
    branch_id = checkpoint_branch['id']

    # ---- write gate: non-admin is refused and nothing moves ----
    status, refused = request(base, 'PATCH', f'/api/admin/branches/{branch_id}',
                              fingerprint, {'name': 'Hijacked Branch'})
    assert status == 403, refused
    assert refused.get('code') == 'admin_only', refused
    # The read-only Commander is refused even earlier by the global firewall.
    chief = sign_in(base, 'chief')
    status, chief_refused = request(base, 'PATCH', f'/api/admin/branches/{branch_id}',
                                    chief, {'active': False})
    assert status == 403 and chief_refused.get('code') == 'read_only_role', chief_refused
    # An unknown branch is a 404, an invalid body a 400 — never a silent write.
    status, missing = request(base, 'PATCH', '/api/admin/branches/99999999', admin,
                              {'name': 'Ghost Branch'})
    assert status == 404, missing
    status, invalid = request(base, 'PATCH', f'/api/admin/branches/{branch_id}',
                              admin, {'region': 'Sool', 'district': 'Burao'})
    assert status == 400, invalid
    status, health = request(base, 'GET', '/api/health')
    assert health['branch_edit_roles'] == ['SystemAdmin', 'admin'], health
    assert health['branch_write_verbs'] == ['POST', 'PATCH'], health
    status, unchanged = request(base, 'GET', '/api/branches?unit_type=checkpoint', admin)
    assert any(b['name'] == checkpoint_branch['name'] for b in unchanged['items'])

    # ---- edit: rename + re-place Region / District in one save ----
    stamp = str(time.time_ns())[-8:]
    new_name = f'East Lasanod Checkpoint {stamp}'
    status, edited = request(base, 'PATCH', f'/api/admin/branches/{branch_id}', admin,
                             {'name': new_name, 'region': 'Sool',
                              'district': 'Laascaanood', 'unit_type': 'checkpoint',
                              'active': True})
    assert status == 200, edited
    assert edited['branch']['id'] == branch_id, 'the branch keeps its id (FKs survive)'
    assert edited['branch']['name'] == new_name
    assert edited['branch']['region'] == 'Sool'
    assert edited['branch']['district'] == 'Laascaanood'
    assert edited['branch']['active'] is True
    assert edited['branch']['legacy_reason'] is None
    assert set(edited['changed_fields']) >= {'name', 'region', 'district'}
    assert edited['updated'] is True
    assert any(b['id'] == branch_id for b in edited['catalogue'])

    # The public catalogue (what the sidebar tree and intake read) moved it.
    status, moved = request(base, 'GET',
                            '/api/branches?unit_type=checkpoint&region=Sool&district=Laascaanood',
                            admin)
    assert status == 200
    assert any(b['id'] == branch_id and b['name'] == new_name
               for b in moved['items']), moved

    # ---- duplicate validation (409, same unit + region + name) ----
    duplicate_name = f'Branch CRUD duplicate {stamp}'
    status, first = request(base, 'POST', '/api/branches', admin, {
        'name': duplicate_name, 'region': 'Sool', 'district': 'Laascaanood',
        'unit_type': 'crime'})
    assert status == 201, first
    status, second = request(base, 'POST', '/api/branches', admin, {
        'name': duplicate_name, 'region': 'Sool', 'district': 'Taleex',
        'unit_type': 'crime'})
    assert status in (201, 409), second
    if status == 201:
        status, clash = request(base, 'PATCH',
                                f"/api/admin/branches/{second['branch']['id']}",
                                admin, {'district': 'Laascaanood'})
        assert status == 409, clash

    # ---- legacy cleanup: a region outside the gazetteer is unassigned ----
    legacy_name = f'Bare East Checkpoint {stamp}'
    status, legacy = request(base, 'POST', '/api/branches', admin, {
        'name': legacy_name, 'region': 'East', 'unit_type': 'checkpoint'})
    assert status == 201, legacy
    legacy_id = legacy['branch']['id']
    status, catalogue = request(base, 'GET', '/api/admin/branches', admin)
    legacy_queue = [b for b in catalogue['unassigned'] if b['id'] == legacy_id]
    assert legacy_queue, 'the unplaced branch is queued for cleanup'
    assert legacy_queue[0]['legacy_reason']
    status, assigned = request(base, 'POST', '/api/admin/branches/bulk-assign',
                               admin, {'ids': [legacy_id], 'region': 'Sool',
                                       'district': 'Laascaanood'})
    assert status == 200, assigned
    assert [b['id'] for b in assigned['updated']] == [legacy_id]
    assert assigned['updated'][0]['region'] == 'Sool'
    assert assigned['updated'][0]['district'] == 'Laascaanood'
    status, catalogue = request(base, 'GET', '/api/admin/branches', admin)
    assert not [b for b in catalogue['unassigned'] if b['id'] == legacy_id]
    # A nonsense placement is refused (district must belong to the region).
    status, rejected = request(base, 'POST', '/api/admin/branches/bulk-assign',
                               admin, {'ids': [legacy_id], 'region': 'Sool',
                                       'district': 'Burao'})
    assert status == 400, rejected

    # ---- active toggle: retired from intake, records keep their link ----
    status, retired = request(base, 'PATCH', f'/api/admin/branches/{legacy_id}',
                              admin, {'active': False})
    assert status == 200 and retired['branch']['active'] is False
    assert retired['branch']['status'] == 'Inactive'
    status, active_only = request(base, 'GET',
                                  '/api/branches?unit_type=checkpoint&active=1', admin)
    assert all(b['id'] != legacy_id for b in active_only['items'])
    status, inactive_only = request(base, 'GET',
                                    '/api/branches?unit_type=checkpoint&active=0', admin)
    assert any(b['id'] == legacy_id for b in inactive_only['items'])
    status, switched_back = request(base, 'PATCH', f'/api/admin/branches/{legacy_id}',
                                    admin, {'active': True})
    assert status == 200 and switched_back['branch']['active'] is True

    # ---- a Police Stations branch rename moves the mirrored station ----
    ps_name = f'CRUD Station Checkpoint {stamp}'
    status, ps_branch = request(base, 'POST', '/api/branches', admin, {
        'name': ps_name, 'region': 'Sool', 'district': 'Xudun',
        'unit_type': 'police_station'})
    assert status == 201, ps_branch
    ps_id = ps_branch['branch']['id']
    status, stations = request(base, 'GET', '/api/stations', admin)
    mirrored = next((s for s in stations.get('items', [])
                     if ps_name.split(' Branch')[0].split(' Station')[0] in (s.get('name') or '')), None)
    status, renamed = request(base, 'PATCH', f'/api/admin/branches/{ps_id}', admin,
                              {'name': f'{ps_name} Renamed'})
    assert status == 200, renamed
    if mirrored:
        status, stations = request(base, 'GET', '/api/stations', admin)
        assert any(s['id'] == mirrored['id'] and s['name'] == f'{ps_name} Renamed'
                   for s in stations['items']), 'the mirrored station followed the branch'

    # ---- officer posting label follows a rename (FK-free link preserved) ----
    posting_branch = f'CRUD Posting Branch {stamp}'
    status, created = request(base, 'POST', '/api/branches', admin, {
        'name': posting_branch, 'region': 'Sool', 'district': 'Caynabo',
        'unit_type': 'fingerprint'})
    assert status == 201, created
    posting_id = created['branch']['id']
    status, users = request(base, 'GET', '/api/admin/users', admin)
    admin_user = next(u for u in users['items'] if u['username'] == 'admin')
    status, patched = request(base, 'PATCH', f"/api/admin/users/{admin_user['id']}", admin,
                              {'branch': posting_branch})
    assert status == 200, patched
    status, reposted = request(base, 'PATCH', f'/api/admin/branches/{posting_id}', admin,
                               {'name': posting_branch + ' Central'})
    assert status == 200
    assert reposted['relabelled_postings'] >= 1
    status, users = request(base, 'GET', '/api/admin/users', admin)
    admin_user = next(u for u in users['items'] if u['username'] == 'admin')
    assert admin_user['branch'] == posting_branch + ' Central', admin_user['branch']

    # ---- the edit is audited (UPDATE police_branch) ----
    status, audit_rows = request(base, 'GET', '/api/admin/audit', admin)
    assert status == 200
    entries = audit_rows.get('items', audit_rows if isinstance(audit_rows, list) else [])
    assert any((row.get('entity') or '') == 'police_branch'
               and (row.get('action') or '') == 'UPDATE'
               and str(row.get('entity_id')) == str(branch_id) for row in entries), \
        'the branch edit is on the audit trail'


# ---------------------------------------------------------------------------
# standalone runner (no pytest required)
# ---------------------------------------------------------------------------
def main():
    import inspect
    failures = []
    tests = [(name, fn) for name, fn in sorted(globals().items())
             if name.startswith('test_') and inspect.isfunction(fn)]
    for name, fn in tests:
        try:
            fn()
            print(f'PASS {name}')
        except Exception as exc:                     # noqa: BLE001 - runner report
            failures.append((name, exc))
            print(f'FAIL {name}: {exc}')
    print()
    print(f'{len(tests) - len(failures)}/{len(tests)} tests passed')
    return 1 if failures else 0


if __name__ == '__main__':
    sys.exit(main())

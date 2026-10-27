#!/usr/bin/env python3
"""Officer identity, role-driven location assignment and audit attribution.

Runs the real API against a throwaway PostgreSQL cluster provisioned with
`pgserver` (or the explicitly configured SENTINEL_DB_* / SENTINEL_DATABASE_URL
engine), then verifies the three capabilities of this release end to end:

  1. ROLE-DRIVEN CASCADING LOCATION ASSIGNMENT
     A Checkpoint role is posted to one checkpoint of the chosen
     Region → District (the station/branch field is hidden in the UI); a
     Station / Unit role is posted to a station, branch or unit of that
     district (the checkpoint field is hidden). The legacy contract is
     preserved: a Checkpoint role created without any posting or scope is
     still rejected, and an explicit non-canonical location_scope is still
     rejected unless a checkpoint posting is supplied.

  2. BADGE ATTRIBUTION
     /api/admin/users and /api/me return the officer's badge_number plus the
     ready-to-print badge_label ('Badge #FP-102'); /api/admin/audit attributes
     every entry to that badge and falls back to '#Not recorded' only for a
     row that genuinely carries none.

  3. OFFICER PROFILE (self-service)
     PATCH /api/me (display name), POST /api/me/avatar (preset + uploaded
     picture) and POST /api/me/password (current-password check, other
     sessions revoked). The global read-only Commander role keeps its zero
     write contract (403 read_only_role).

Usage: python3 backend/test_officer_profile_locations.py
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
INDEX = os.path.join(PROJECT_ROOT, 'index.html')
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
        boundary = '----sentinel-profile-test-boundary'
        chunks = []
        for name, value in form.items():
            if isinstance(value, tuple):
                filename, content, ctype = value
                chunks.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"; '
                    f'filename="{filename}"\r\nContent-Type: {ctype}\r\n\r\n'.encode()
                    + content + b'\r\n')
            else:
                chunks.append(
                    f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"\r\n\r\n'
                    f'{value}\r\n'.encode())
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
        with urllib.request.urlopen(req, timeout=20) as response:
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


def run_api_suite(base):
    print('== 1. Officer badge attribution in every user payload ==')
    admin, admin_user = login(base, 'admin')
    fp, fp_user = login(base, 'fp.officer')

    check(admin_user.get('badge_number') == 'ADM-101',
          f"admin badge is ADM-101 ({admin_user.get('badge_number')})")
    check(fp_user.get('badge_number') == 'FP-102',
          f"fp.officer badge is FP-102 ({fp_user.get('badge_number')})")
    check(fp_user.get('badge_label') == 'Badge #FP-102',
          f"badge_label prints 'Badge #FP-102' ({fp_user.get('badge_label')})")

    status, me = request(base, 'GET', '/api/me', fp)
    check(status == 200 and me.get('badge_number') == 'FP-102',
          '/api/me returns the signed-in officer badge_number')
    check(me.get('badge_label') == 'Badge #FP-102', '/api/me returns badge_label')
    check(me.get('can_edit_profile') is True, '/api/me grants self-service profile authority')

    status, roster = request(base, 'GET', '/api/admin/users', admin)
    check(status == 200, 'administrator reads the user roster')
    by_name = {row['username']: row for row in roster['items']}
    check(by_name['fp.officer'].get('badge_number') == 'FP-102',
          'the user roster query fetches users.badge_number (no #Not recorded fallback)')
    check(by_name['fp.officer'].get('badge_label') == 'Badge #FP-102',
          'the user roster returns the printable badge label')
    check(all(row.get('badge_number') for row in roster['items']),
          'every seeded account carries a badge number')

    print('== 2. Role-driven cascading location assignment ==')
    # Checkpoint role → Region + District + checkpoint posting. The posting is
    # a real police station with station_tier 'Checkpoint' (ST-008).
    status, created_cp = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'cp.laascaanood',
        'display_name': 'Officer L. Cadeeye',
        'role': 'CheckpointEast',
        'password': PASSWORD,
        'region': 'Sool',
        'district': 'Laascaanood',
        'checkpoint': 'Adhi Cadeeye Outpost',
    })
    check(status == 201, f'checkpoint officer created with a district checkpoint ({status})')
    cp_user = created_cp['user']
    check(cp_user['branch'] == 'Adhi Cadeeye Outpost · Laascaanood · Sool',
          f"posting label is composed into users.branch ({cp_user['branch']})")
    check(cp_user['location_scope'] == 'Adhi Cadeeye Outpost',
          f"named checkpoint is the officer scope ({cp_user['location_scope']})")
    check(cp_user['badge_number'].startswith('CP-'),
          f'checkpoint badge auto-assigned ({cp_user["badge_number"]})')

    # Canonical checkpoint areas still resolve to the short code.
    status, canonical_cp = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'cp.east.branch',
        'display_name': 'Officer E. Branch',
        'role': 'checkpoint_officer',
        'password': PASSWORD,
        'region': 'East Togdheer',
        'district': 'Buuhoodle',
        'checkpoint': 'South Checkpoint',
    })
    check(status == 201 and canonical_cp['user']['location_scope'] == 'South',
          'a canonical checkpoint area keeps the South / East / West scope contract')

    # Station / Unit role → Region + District + station/branch/unit.
    status, created_unit = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'fp.lasanod',
        'display_name': 'Officer F. Laascaanood',
        'role': 'FingerprintUnit',
        'password': PASSWORD,
        'region': 'Sool',
        'district': 'Laascaanood',
        'unit': 'Lasanod Branch',
    })
    check(status == 201, f'station / unit officer created with a district unit ({status})')
    unit_user = created_unit['user']
    check(unit_user['branch'] == 'Lasanod Branch · Laascaanood · Sool',
          f"unit posting label ({unit_user['branch']})")
    check(unit_user['location_scope'] in (None, ''),
          'a station / unit officer carries no checkpoint scope')
    check(unit_user['badge_number'].startswith('FP-'),
          f'unit badge auto-assigned ({unit_user["badge_number"]})')

    # Explicit badge wins; a duplicate badge is refused.
    status, badged = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'fp.custombadge',
        'display_name': 'Officer B. Badge',
        'role': 'FingerprintUnit',
        'password': PASSWORD,
        'badge_number': 'FP-777',
    })
    check(status == 201 and badged['user']['badge_number'] == 'FP-777',
          'an explicit badge number is stored verbatim')
    status, duplicate = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'fp.dupebadge',
        'display_name': 'Officer D. Badge',
        'role': 'FingerprintUnit',
        'password': PASSWORD,
        'badge_number': 'FP-777',
    })
    check(status == 400, f'a duplicate badge number is refused ({status})')

    # ---- legacy contracts preserved -------------------------------------
    # A scoped Checkpoint alias still derives its area with no posting at all
    # (legacy drawer behaviour), while the canonical alias has no default.
    status, alias_scope = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'cp.south.legacy', 'display_name': 'Officer S. Legacy',
        'role': 'CheckpointSouth', 'password': PASSWORD,
    })
    check(status == 201 and alias_scope['user']['location_scope'] == 'South',
          'a CheckpointSouth account with no posting still defaults to the South area')
    status, missing_scope = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'cp.noscope', 'display_name': 'Officer N. Scope',
        'role': 'checkpoint_officer', 'password': PASSWORD,
    })
    check(status == 400,
          f'a checkpoint role with no posting and no scope is still rejected ({status})')
    status, bad_scope = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'cp.badscope', 'display_name': 'Officer B. Scope',
        'role': 'CIDUnit', 'password': PASSWORD, 'location_scope': 'North',
    })
    check(status == 400, f'an unknown location_scope is still rejected ({status})')

    # ---- Edit drawer: re-post an officer through the cascade ------------
    uid = created_unit['user']['id']
    status, edited = request(base, 'PATCH', f'/api/admin/users/{uid}', admin, {
        'display_name': 'Officer F. Laascaanood',
        'role': 'CIDUnit',
        'region': 'Sanaag',
        'district': 'Ceerigaabo',
        'unit': 'Erigavo Branch',
    })
    check(status == 200 and edited['user']['branch'] == 'Erigavo Branch · Ceerigaabo · Sanaag',
          f"the edit cascade re-posts the officer ({edited['user']['branch']})")
    check(edited['user']['role'] == 'CIDUnit', 'the edit cascade stores the new role')

    # The drawer sends the composed selection AND the checkpoint scope it
    # derived (checkpointScopeFor); that explicit non-canonical value must be
    # accepted for a checkpoint posting instead of being read as an area code.
    status, drawer_cp = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'cp.drawer',
        'display_name': 'Officer D. Drawer',
        'role': 'checkpoint_officer',
        'password': PASSWORD,
        'region': 'Sool',
        'district': 'Laascaanood',
        'checkpoint': 'Lasanod Branch',
        'unit': None,
        'branch': '',
        'location_scope': 'Lasanod Branch',
    })
    check(status == 201 and drawer_cp['user']['location_scope'] == 'Lasanod Branch',
          'the exact payload the New Officer drawer sends is accepted '
          f"({status} {drawer_cp.get('error', '')})")
    check(drawer_cp['user']['branch'] == 'Lasanod Branch · Laascaanood · Sool',
          'the drawer payload stores the composed posting label')

    # A station / unit posting clears a stale checkpoint scope on update.
    status, cleared = request(base, 'PATCH',
                              f"/api/admin/users/{drawer_cp['user']['id']}", admin, {
        'role': 'FingerprintUnit',
        'region': 'Sool',
        'district': 'Laascaanood',
        'unit': 'Las Anod Station',
        'location_scope': None,
    })
    check(status == 200 and not cleared['user']['location_scope'],
          f"a station / unit role clears the checkpoint scope ({cleared['user']['location_scope']})")

    print('== 3. Audit trail with badge attribution ==')
    status, audit = request(base, 'GET', '/api/admin/audit?limit=100', admin)
    check(status == 200 and audit.get('items'), 'administrator reads the audit trail')
    check(audit.get('badge_fallback') == '#Not recorded',
          'the documented fallback is published with the payload')
    entries = audit['items']
    check(all('badge_label' in item and 'actor' in item for item in entries),
          'every audit entry carries badge attribution')
    create_rows = [item for item in entries
                   if item['entity'] == 'user' and item['entity_id'] == str(uid)]
    check(create_rows or any(item['entity'] == 'user' for item in entries),
          'user management writes are audited')
    admin_rows = [item for item in entries if item['actor']['username'] == 'admin']
    check(admin_rows and all(item['badge_label'] == 'Badge #ADM-101' for item in admin_rows),
          "administrator actions are attributed to 'Badge #ADM-101'")

    # A row without a badge must render the fallback, never a guess.
    try:
        import psycopg2
        conn = psycopg2.connect(
            dbname=os.environ.get('SENTINEL_DB_NAME', 'postgres'),
            user=os.environ.get('SENTINEL_DB_USER', 'postgres'),
            password=os.environ.get('SENTINEL_DB_PASSWORD', ''),
            host=os.environ.get('SENTINEL_DB_HOST', 'localhost'),
            port=os.environ.get('SENTINEL_DB_PORT', '5432'))
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username='cid.officer'")
        legacy_id = cur.fetchone()[0]
        cur.execute("UPDATE users SET badge_number=NULL WHERE id=%s", (legacy_id,))
        cur.execute("INSERT INTO audit_events(user_id,action,entity,entity_id,details) "
                    "VALUES(%s,'UPDATE','user','%s','legacy attribution probe')" % ('%s', legacy_id),
                    (legacy_id,))
        conn.commit()
        cur.close(); conn.close()
        status, audit2 = request(base, 'GET', '/api/admin/audit?limit=5', admin)
        probe = [item for item in audit2['items'] if item['details'] == 'legacy attribution probe']
        check(probe and probe[0]['badge_label'] == '#Not recorded'
              and probe[0]['badge_recorded'] is False,
              "an entry without a badge falls back to '#Not recorded'")
        cur = None
    except ImportError:
        print('skip: psycopg2 unavailable — fallback probe not exercised')

    status, denied = request(base, 'GET', '/api/admin/audit', fp)
    check(status in (401, 403), f'a unit officer cannot read the audit trail ({status})')

    print('== 4. Officer profile: display name / avatar / password ==')
    status, renamed = request(base, 'PATCH', '/api/me', fp,
                              {'display_name': 'Officer H. Xasan (FP)'})
    check(status == 200 and renamed['user']['display_name'] == 'Officer H. Xasan (FP)',
          'the display name is updated through PATCH /api/me')
    status, too_short = request(base, 'PATCH', '/api/me', fp, {'display_name': 'X'})
    check(status == 400, f'a one-character display name is rejected ({status})')
    status, me2 = request(base, 'GET', '/api/me', fp)
    check(me2.get('display_name') == 'Officer H. Xasan (FP)', '/api/me reflects the new name')

    status, preset = request(base, 'POST', '/api/me/avatar', fp, {'avatar_preset': 'gold'})
    check(status == 200 and preset['user']['avatar_preset'] == 'gold',
          'an avatar preset is selectable')
    status, bad_preset = request(base, 'POST', '/api/me/avatar', fp, {'avatar_preset': 'neon'})
    check(status == 400, f'an unknown avatar preset is rejected ({status})')

    # 1x1 transparent PNG
    png = bytes.fromhex(
        '89504e470d0a1a0a0000000d49484452000000010000000108060000001f15c489'
        '0000000a49444154789c6360000002000100ffff03000006000557bfabd4000000'
        '0049454e44ae426082')
    status, uploaded = request(base, 'POST', '/api/me/avatar', fp, form={
        'avatar': ('officer.png', png, 'image/png')})
    check(status == 200 and uploaded['user'].get('avatar_path', '').startswith('/uploads/'),
          f"an uploaded picture is linked to the profile ({uploaded.get('user', {}).get('avatar_path')})")

    status, wrong = request(base, 'POST', '/api/me/password', fp, {
        'current_password': 'not-the-password', 'new_password': 'NewSecret123!'})
    check(status == 400, f'a wrong current password is refused ({status})')
    status, changed = request(base, 'POST', '/api/me/password', fp, {
        'current_password': PASSWORD, 'new_password': 'NewSecret123!'})
    check(status == 200 and changed.get('password_changed') is True,
          'the password change succeeds for the correct current password')
    status, old_login = request(base, 'POST', '/api/login',
                                body={'username': 'fp.officer', 'password': PASSWORD})
    check(status == 401, 'the previous password no longer signs in')
    fp2, _ = login(base, 'fp.officer', 'NewSecret123!')

    # ---- read-only Commander keeps the zero-write contract -------------
    chief, chief_user = login(base, 'chief')
    check(chief_user.get('can_edit_profile') is False,
          'the Commander profile is flagged view-only')
    for method, path, payload in (
            ('PATCH', '/api/me', {'display_name': 'Commander Renamed'}),
            ('POST', '/api/me/avatar', {'avatar_preset': 'gold'}),
            ('POST', '/api/me/password',
             {'current_password': PASSWORD, 'new_password': 'AnotherPass123!'})):
        status, refused = request(base, method, path, chief, payload)
        code = refused.get('code') if isinstance(refused, dict) else ''
        check(status == 403 and code == 'read_only_role',
              f'{method} {path} is refused for the Commander ({status} {code})')

    print('== 5. Live surfaces: no cache, live metrics after a write ==')
    req = urllib.request.Request(base + '/api/dashboard')
    req.add_header('Authorization', 'Bearer ' + admin)
    with urllib.request.urlopen(req, timeout=20) as response:
        cache = (response.headers.get('cache-control') or '').lower()
    check('no-store' in cache,
          f'dashboard JSON is never cached ({cache})')
    return fp2


def run_frontend_contract():
    print('== 6. Frontend contract (index.html) ==')
    html = open(INDEX, encoding='utf-8').read()
    check('id="officerIdentity"' in html,
          'the header identity block is a clickable control')
    check('onclick="openOfficerProfile()"' in html,
          'clicking the identity block opens the Officer Profile modal')
    check('id="officerProfileModal"' in html,
          'the Officer Profile modal markup exists')
    check('function saveOfficerDisplayName(' in html and 'function submitOfficerPassword(' in html
          and 'function uploadOfficerAvatar(' in html,
          'the profile modal can update the name, upload an avatar and change the password')
    check('function paintUserLocationFields(' in html and 'function userCheckpointOptions(' in html
          and 'function userUnitOptions(' in html and 'function onUserLocationChange(' in html,
          'the User Management drawer paints role-driven cascading location selectors')
    check("cpField.style.display = checkpointRole ? '' : 'none'" in html
          and "unitField.style.display = checkpointRole ? 'none' : ''" in html,
          'the Checkpoint and Station / Branch fields are mutually exclusive by role')
    check('function isCheckpointPosting(' in html and 'function isActivePosting(' in html,
          'only ACTIVE checkpoints are offered for a district')
    check('id="auditTrailTable"' in html and 'function loadAuditTrail(' in html,
          'the audit trail is rendered with badge attribution')
    check('async function refreshLiveMetrics(' in html
          and html.count('refreshLiveMetrics(') >= 6,
          'every register write refreshes the dashboard metrics and activity feed')
    check('<meta name="sentinel-ui-build" content="sentinel-officer-profile-5-3c8f1a76" />' in html,
          'the asset version stamp was republished')
    check('?v=3c8f1a76' in html, 'static references carry the new cache-busting version')


def main():
    tmp = tempfile.mkdtemp(prefix='sentinel-profile-')
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
            raise RuntimeError('profile / location test server did not start')
        run_api_suite(base)
        run_frontend_contract()
        print('ALL OFFICER PROFILE / LOCATION / AUDIT TESTS PASSED')
        return 0
    finally:
        server.terminate()
        server.wait(timeout=10)
        stop_db()


if __name__ == '__main__':
    sys.exit(main())

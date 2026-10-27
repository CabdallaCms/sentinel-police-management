#!/usr/bin/env python3
"""Unified Checkpoint Officer role + per-record audit history.

Runs the real API against a throwaway PostgreSQL cluster (pgserver) or the
explicitly configured SENTINEL_DB_* / SENTINEL_DATABASE_URL engine.

  1. ONE CHECKPOINT ROLE
     `CheckpointSouth` / `CheckpointEast` / `CheckpointWest` are gone as
     assignable roles: the seeds, the role picker and the API all use the single
     `checkpoint_officer` role, and WHICH checkpoint an officer commands is data
     (users.location_scope + users.branch) assigned by the Region → District →
     Checkpoint cascade. Every historical spelling still normalises to the
     unified role, so an older client keeps working unchanged.

  2. LEGACY ROWS ARE MIGRATED, NOT BROKEN
     unify_checkpoint_roles() rewrites stored compound roles in place, keeps
     each officer's checkpoint scope, and is idempotent.

  3. AUDIT HISTORY ON THE RECORD ITSELF
     GET /api/persons/<id>/audit-history and
     GET /api/audit/entity/<entity>/<id> return the chronological log
     (creations, updates, approvals, signed-scan uploads) with the acting
     officer's badge — the same append-only rows the administrative register
     reads, filtered by module and by the officer's checkpoint scope.

Usage: python3 backend/test_checkpoint_roles_audit.py
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
        boundary = '----sentinel-checkpoint-audit-boundary'
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
        with urllib.request.urlopen(req, timeout=25) as response:
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


def create_person(base, token, suffix):
    status, body = request(base, 'POST', '/api/persons', token, {
        'full_name': f'Audit Trail {suffix}',
        'first_name': 'Audit', 'second_name': 'Trail', 'third_name': suffix,
        'national_id': 'NID' + suffix,
        'date_of_birth': '1990-05-05',
        'mother_name': 'Hooyo Audit',
        'residence': 'Laascaanood',
        'phone': '+252 63 555 0199',
    })
    person = body.get('person') or {}
    person_id = body.get('person_id') or person.get('person_id')
    if status not in (200, 201) or not person_id:
        raise AssertionError(f'person create failed {status}: {body}')
    return person_id


def create_clearance(base, token, suffix):
    """Create a real clearance application through the multipart endpoint."""
    fields = {
        'first_name': 'Audit', 'second_name': 'Trail', 'third_name': suffix,
        'fourth_name': 'Case',
        'date_of_birth': '1992-02-02', 'national_id': 'CL' + suffix,
        'mother_name': 'Hooyo Audit', 'residence': 'Laascaanood',
        'phone': '+252 63 555 0100', 'sex': 'Male',
        'email': f'audit-{suffix}@example.com', 'purpose': 'Employment',
        'guardian_name': 'Guardian Audit', 'guardian_relationship': 'Uncle',
        'guardian_id': 'GD-9', 'guardian_occupation': 'Trader',
        'guardian_address': 'Burao', 'guardian_phone': '+252 63 555 0101',
    }
    pdf = ('%PDF-audit-history', b'%PDF-1.4 audit history test', 'application/pdf')
    form = dict(fields)
    for slot in ('doc_app_0', 'doc_app_1', 'doc_guard_0', 'doc_guard_1'):
        form[slot] = (f'{slot}.pdf', pdf[1], pdf[2])
    status, body = request(base, 'POST', '/api/clearance-applications', token, form=form)
    if status not in (200, 201):
        raise AssertionError(f'clearance create failed {status}: {body}')
    return body['application_id'], body['person_id']


def run_api_suite(base):
    admin, admin_user = login(base, 'admin')
    fp, fp_user = login(base, 'fp.officer')
    hr, _ = login(base, 'hr.officer')
    cp_south, cp_user = login(base, 'cp.south')
    cp_east, cp_east_user = login(base, 'cp.east')

    print('== 1. One unified Checkpoint Officer role ==')
    for who, token_user, scope in (('cp.south', cp_user, 'South'),
                                   ('cp.east', cp_east_user, 'East')):
        check(token_user.get('role') == 'checkpoint_officer',
              f'{who} holds the unified role ({token_user.get("role")})')
        check(token_user.get('role_label') == 'Checkpoint Officer',
              f'{who} is labelled "Checkpoint Officer" ({token_user.get("role_label")})')
        check(token_user.get('location_scope') == scope,
              f'{who} keeps its checkpoint scope ({token_user.get("location_scope")})')
        check(token_user.get('modules') == ['checkpoints', 'dashboard'],
              f'{who} keeps exactly the dashboard + checkpoints modules ({token_user.get("modules")})')

    status, roster = request(base, 'GET', '/api/admin/users', admin)
    check(status == 200, 'administrator reads the user roster')
    checkpoint_rows = [row for row in roster['items']
                       if 'checkpoint' in str(row['role']).lower()]
    check(len(checkpoint_rows) == 3, f'the three seeded checkpoint officers are listed ({len(checkpoint_rows)})')
    check(all(row['role'] == 'checkpoint_officer' for row in checkpoint_rows),
          'every checkpoint officer row stores the unified role')
    check(sorted(row['location_scope'] for row in checkpoint_rows) == ['East', 'South', 'West'],
          'each officer keeps its own checkpoint scope as data')
    check(roster['roles'].count('checkpoint_officer') == 1,
          'the assignable role list offers Checkpoint Officer exactly once')
    for legacy in ('CheckpointSouth', 'CheckpointEast', 'CheckpointWest'):
        check(legacy not in roster['roles'],
              f'{legacy} is no longer an assignable role')
    check(roster['role_labels'].get('checkpoint_officer') == 'Checkpoint Officer',
          'the role label is the single "Checkpoint Officer"')

    # The New Officer drawer payload: unified role + the cascade selection.
    status, created = request(base, 'POST', '/api/admin/users', admin, {
        'username': 'cp.unified',
        'display_name': 'Officer U. Nified',
        'role': 'checkpoint_officer',
        'password': PASSWORD,
        'region': 'Sool',
        'district': 'Laascaanood',
        'checkpoint': 'Adhi Cadeeye Outpost',
        'unit': None,
        'branch': '',
        'location_scope': 'Adhi Cadeeye Outpost',
    })
    check(status == 201 and created['user']['role'] == 'checkpoint_officer',
          f'the cascade creates a unified checkpoint officer ({status})')
    check(created['user']['branch'] == 'Adhi Cadeeye Outpost · Laascaanood · Sool',
          f"the posting is data, not a role ({created['user']['branch']})")
    check(created['user']['location_scope'] == 'Adhi Cadeeye Outpost',
          'the selected checkpoint becomes the scope')
    check(created['user']['badge_label'].startswith('Badge #CP-'),
          f"the officer gets a CP badge ({created['user']['badge_label']})")

    # An older client that still posts a compound role keeps working — it is
    # normalised, never stored.
    for legacy, scope in (('CheckpointSouth', 'South'),
                          ('checkpoint_east', 'East'),
                          ('cp.west', 'West'),
                          ('Checkpoint Officer (South)', 'South')):
        username = 'cp.legacy.' + legacy.lower().replace(' ', '').replace('(', '').replace(')', '').replace('.', '').replace('_', '')
        status, body = request(base, 'POST', '/api/admin/users', admin, {
            'username': username, 'display_name': f'Officer L. {scope}',
            'role': legacy, 'password': PASSWORD,
        })
        check(status == 201 and body['user']['role'] == 'checkpoint_officer',
              f'a legacy "{legacy}" payload still creates a unified officer ({status})')
        check(body['user']['location_scope'] == scope,
              f'the legacy alias keeps its {scope} scope ({body["user"]["location_scope"]})')

    print('== 2. Legacy rows are migrated in place ==')
    import psycopg2
    conn = psycopg2.connect(
        dbname=os.environ.get('SENTINEL_DB_NAME', 'postgres'),
        user=os.environ.get('SENTINEL_DB_USER', 'postgres'),
        password=os.environ.get('SENTINEL_DB_PASSWORD', ''),
        host=os.environ.get('SENTINEL_DB_HOST', 'localhost'),
        port=os.environ.get('SENTINEL_DB_PORT', '5432'))
    cur = conn.cursor()
    cur.execute("""INSERT INTO users(username,display_name,role,branch,location_scope,
                    badge_number,password_hash,active)
                   VALUES('legacy.west','Legacy West','CheckpointWest','Checkpoint West',NULL,
                          'CP-777','x',1) RETURNING id""")
    legacy_west = cur.fetchone()[0]
    cur.execute("""INSERT INTO users(username,display_name,role,branch,location_scope,
                    badge_number,password_hash,active)
                   VALUES('legacy.scoped','Legacy Scoped','CheckpointSouth','Adhi Cadeeye Outpost',
                          'Adhi Cadeeye Outpost','CP-778','x',1) RETURNING id""")
    legacy_scoped = cur.fetchone()[0]
    conn.commit()
    cur.close()
    conn.close()

    sys.path.insert(0, ROOT)
    import server as backend  # noqa: E402  (same DB via the environment)
    db = backend.get_db_connection()
    try:
        rewritten = backend.unify_checkpoint_roles(db)
        db.commit()
        check(rewritten >= 2, f'the migration rewrites every legacy checkpoint row ({rewritten})')
        row = db.execute('SELECT role,location_scope FROM users WHERE id=%s',
                         (legacy_west,)).fetchone()
        check(row['role'] == 'checkpoint_officer',
              'a CheckpointWest row becomes the unified role')
        check(row['location_scope'] == 'West',
              f"its implied area is preserved as data ({row['location_scope']})")
        row = db.execute('SELECT role,location_scope FROM users WHERE id=%s',
                         (legacy_scoped,)).fetchone()
        check(row['location_scope'] == 'Adhi Cadeeye Outpost',
              'an explicit checkpoint scope is never overwritten by the migration')
        check(backend.unify_checkpoint_roles(db) == 0,
              'the migration is idempotent (a second run rewrites nothing)')
        db.commit()
        # The migrated row behaves like any other checkpoint officer.
        db.execute("UPDATE users SET password_hash=%s WHERE id=%s",
                   (backend.password_hash(PASSWORD), legacy_west))
        db.commit()
    finally:
        db.close()

    status, legacy_login = request(base, 'POST', '/api/login',
                                   body={'username': 'legacy.west', 'password': PASSWORD})
    check(status == 200, 'the migrated officer can sign in')
    check(legacy_login['user']['role'] == 'checkpoint_officer'
          and legacy_login['user']['location_scope'] == 'West',
          'the migrated officer signs in with the unified role and the West scope')
    check(legacy_login['user']['role_label'] == 'Checkpoint Officer',
          'the migrated officer is labelled "Checkpoint Officer"')

    print('== 3. Audit history on the person record ==')
    pid = create_person(base, fp, 'AUD1')
    status, history = request(base, 'GET', f'/api/persons/{pid}/audit-history', fp)
    check(status == 200, f'the officer reads the audit history of {pid} ({status})')
    check(history.get('entity') == 'person' and history.get('entity_id') == pid,
          'the payload names the record it belongs to')
    check(history.get('badge_fallback') == '#Not recorded',
          'the documented fallback travels with the record history')
    creates = [i for i in history['items'] if i['entity'] == 'person' and i['action'] == 'CREATE']
    check(creates, 'the creation of the identity is on its own audit history')
    check(creates[0]['badge_label'] == 'Badge #FP-102',
          f"the creator is attributed to their badge ({creates[0]['badge_label']})")
    check(creates[0]['action_label'] == 'Created' and creates[0]['entity_label'],
          'each event carries a readable action + entity label')

    # A clearance application + signed scan + approval must all land on the SAME
    # record history, alongside the administrative trail.
    aid, app_pid = create_clearance(base, fp, 'AUD1')
    status, upload = request(
        base, 'POST', f'/api/clearance-applications/{aid}/signed-document', fp,
        form={'signed_application_document': ('signed-audit.pdf', b'%PDF-1.4 signed audit',
                                              'application/pdf')})
    check(status in (200, 201), f'the signed scan uploads ({status} {upload.get("error","")})')
    status, approved = request(base, 'POST', f'/api/clearance-applications/{aid}/approve', admin)
    check(status in (200, 201), f'the administrator approves the application ({status})')

    status, history = request(base, 'GET', f'/api/persons/{app_pid}/audit-history', fp)
    check(status == 200, 'the record history re-reads after the workflow')
    actions = {(i['entity'], i['action']) for i in history['items']
               if i['entity'].startswith('clearance')}
    check(('clearance_application', 'CREATE') in actions,
          'the application creation is on the person record')
    check(('clearance_signed_document', 'UPLOAD') in actions,
          'the signed-scan upload is on the person record')
    check(('clearance_application', 'APPROVE') in actions,
          'the approval is on the person record')
    ids = [i['id'] for i in history['items']]
    check(ids == sorted(ids, reverse=True), 'events are chronological (newest first)')
    check(all('badge_label' in i and 'actor' in i for i in history['items']),
          'every record event carries badge attribution')
    check(history['total'] == len(history['items']) >= 4,
          f"the log counts every event ({history['total']})")
    check(any(i['details'] for i in history['items']),
          'event details (certificate number, file name) are included')

    # Consistency with the administrative trail: the same rows, same ids.
    status, admin_trail = request(base, 'GET', '/api/admin/audit?limit=200', admin)
    admin_ids = {i['id'] for i in admin_trail['items']}
    check({i['id'] for i in history['items']} <= admin_ids,
          'the record history is a subset of the administrative audit trail')

    print('== 4. Record history respects RBAC and scope ==')
    status, cp_view = request(base, 'GET', f'/api/persons/{app_pid}/audit-history', cp_south)
    check(status == 200, 'a checkpoint officer may read a person record history')
    check(not any(i['entity'].startswith('clearance') for i in cp_view['items']),
          'a checkpoint officer never sees fingerprint application events')
    check(all(i['entity'] == 'person' for i in cp_view['items']),
          'only the identity events are exposed outside the caller’s modules')

    # A checkpoint screening in their own scope appears on the record. The
    # intake matches the traveler by national ID, so the event attaches to the
    # existing identity instead of creating a second one.
    status, event = request(base, 'POST', '/api/checkpoint-events', cp_south, form={
        'first_name': 'Audit', 'second_name': 'Trail', 'third_name': 'AUD1',
        'fourth_name': 'Case', 'national_id': 'CLAUD1',
        'date_of_birth': '1992-02-02', 'purpose_of_visit': 'Travel',
        'current_address': 'Laascaanood', 'location': 'South',
        'guardian_name': 'Guardian Audit', 'guardian_relationship': 'Uncle',
        'guardian_phone': '+252 63 555 0101', 'guardian_address': 'Burao',
        'guardian_occupation': 'Trader',
        'photo': ('traveler.jpg', b'\xff\xd8\xff\xe0JFIF-audit', 'image/jpeg'),
        'doc_tr_0': ('traveler-doc.pdf', b'%PDF-1.4 traveler', 'application/pdf'),
        'doc_gd_0': ('guardian-doc.pdf', b'%PDF-1.4 guardian', 'application/pdf'),
    })
    check(status in (200, 201), f'a checkpoint screening is recorded ({status} {event.get("error","")})')
    status, cp_view = request(base, 'GET', f'/api/persons/{app_pid}/audit-history', cp_south)
    check(any(i['entity'] == 'checkpoint_event' for i in cp_view['items']),
          'the officer sees the screening they performed on the record')
    status, east_view = request(base, 'GET', f'/api/persons/{app_pid}/audit-history', cp_east)
    check(not any(i['entity'] == 'checkpoint_event' for i in east_view['items']),
          'another checkpoint area never sees that screening')

    status, forbidden = request(base, 'GET', f'/api/persons/{app_pid}/audit-history', None)
    check(status == 401, f'anonymous callers are refused ({status})')

    print('== 5. Generic per-record history endpoint ==')
    status, station = request(base, 'POST', '/api/stations', admin, {
        'name': 'Audit Probe Station', 'station_tier': 'Outpost', 'region': 'Sool',
        'district': 'Laascaanood', 'village': 'Laascaanood', 'contact_phone': '0907000111'})
    check(status in (200, 201), f'administrator registers a station ({status})')
    station_id = station.get('station_id') or (station.get('station') or {}).get('station_id')

    status, st_history = request(base, 'GET', f'/api/audit/entity/police_station/{station_id}', admin)
    check(status == 200 and st_history['items'],
          f'the station record carries its own audit history ({status})')
    check(st_history['items'][0]['action'] == 'CREATE'
          and st_history['items'][0]['entity'] == 'police_station',
          'the station creation is the first (newest) event')
    check(st_history['entity_label'] == 'Police station', 'the entity is labelled for the UI')

    status, hr_view = request(base, 'GET', f'/api/audit/entity/police_station/{station_id}', hr)
    check(status == 200, 'the HR Directorate (owns the stations register) may read it')
    status, denied = request(base, 'GET', f'/api/audit/entity/police_station/{station_id}', cp_south)
    check(status == 403 and denied.get('code') == 'audit_scope_forbidden',
          f'a checkpoint officer is refused a station history ({status} {denied.get("code")})')
    status, unknown = request(base, 'GET', '/api/audit/entity/not_a_record/X-1', admin)
    check(status == 404, f'an unknown record type is a 404 ({status})')

    # The officer register takes a multipart body (mandatory photograph + slot 1).
    status, officer = request(base, 'POST', '/api/officers', hr, form={
        'full_name': 'Audit Probe Officer', 'rank': 'Constable', 'unit': 'General Patrol',
        'station_id': station_id, 'date_of_enlistment': '2024-01-01',
        'mother_name': 'Hooyo Probe', 'date_of_birth': '1995-01-01',
        'place_of_birth': 'Laascaanood', 'contact_number': '+252 63 555 0123',
        'guarantor_name': 'Guarantor Probe', 'guarantor_address': 'Laascaanood',
        'guarantor_contact': '+252 63 555 0124', 'doc1_type': 'National ID',
        'photo': ('probe.jpg', b'\xff\xd8\xff\xe0JFIF-probe', 'image/jpeg'),
        'doc1_file': ('probe.pdf', b'%PDF-1.4 probe', 'application/pdf'),
    })
    check(status in (200, 201), f'the HR Directorate registers an officer ({status} {officer.get("error","")})')
    service_id = officer.get('service_id') or (officer.get('officer') or {}).get('service_id')
    status, off_history = request(base, 'GET', f'/api/audit/entity/officer/{service_id}', hr)
    check(status == 200 and off_history['items'],
          f'the officer record carries its own audit history ({status})')
    status, off_denied = request(base, 'GET', f'/api/audit/entity/officer/{service_id}', cp_south)
    check(status == 403, 'a checkpoint officer cannot read the police register history')

    new_uid = created['user']['id']          # created through POST /api/admin/users
    status, user_history = request(base, 'GET', f'/api/audit/entity/user/{new_uid}', admin)
    check(status == 200 and user_history['items'],
          'the administrator can read a user account history')
    check(user_history['items'][0]['action'] == 'CREATE'
          and user_history['items'][0]['badge_label'] == 'Badge #ADM-101',
          'the account creation is attributed to the creating administrator badge')
    status, user_denied = request(base, 'GET', f'/api/audit/entity/user/{new_uid}', hr)
    check(status == 403, 'user account history stays inside the admin module')

    # The unified role is what the audit trail prints.
    status, trail = request(base, 'GET', '/api/admin/audit?limit=200', admin)
    cp_rows = [i for i in trail['items'] if i['actor']['username'] == 'cp.south']
    check(cp_rows and all(i['actor']['role_label'] == 'Checkpoint Officer' for i in cp_rows),
          'the audit trail labels a checkpoint officer with the unified role')
    check(all(not str(i['actor']['role']).startswith('Checkpoint')
              for i in trail['items'] if i['actor']['username'].startswith('cp.')),
          'no audit row still reports a compound checkpoint role')


def run_frontend_contract():
    print('== 6. Frontend contract (index.html) ==')
    html = open(INDEX, encoding='utf-8').read()
    check('data-detail-tab="audit"' in html,
          'the Person Details modal has an Audit history tab')
    check('data-person-detail-panel="audit"' in html,
          'the Audit history tab has its own panel')
    check('id="personAuditTrail"' in html and 'id="personAuditCount"' in html,
          'the tab renders a timeline and an event counter')
    check('function renderAuditHistory(' in html,
          'the timeline renderer exists')
    check('function loadRecordAuditHistory(' in html
          and '/audit-history' in html,
          'the person / officer record loads its history from the API')
    check('function loadStationAuditHistory(' in html and 'id="stationAuditTrail"' in html,
          'the Station View drawer shows the same history')
    check('function auditTone(' in html and 'audit-timeline' in html,
          'events are painted as a chronological timeline with action tones')
    check("normalizeRole(r)==='checkpoint_officer'" in html,
          'the role picker collapses every checkpoint spelling into one option')
    check("'checkpoint_officer','chief_commander'" in html,
          'the fallback role list offers the unified Checkpoint Officer role')
    check(not any(f"role:'{legacy}'" in html
                  for legacy in ('CheckpointSouth', 'CheckpointEast', 'CheckpointWest')),
          'the demo accounts no longer advertise compound checkpoint roles')
    demo_block = html.split('const DEMO_ACCOUNTS')[1][:900] if 'const DEMO_ACCOUNTS' in html else ''
    check(demo_block.count("role:'checkpoint_officer'") == 3,
          'each demo checkpoint account points at the single unified role')
    # The only survivor is the alias comment in normalizeRole(): the spellings
    # are still ACCEPTED, they are just never offered or displayed again.
    offenders = [line.strip() for line in html.splitlines()
                 if 'Checkpoint Officer (South)' in line and not line.strip().startswith('//')]
    check(not offenders,
          'the "(South) / (East) / (West)" role labels are gone from the UI')
    check('<meta name="sentinel-ui-build"' in html, 'the build stamp is published')


def main():
    tmp = tempfile.mkdtemp(prefix='sentinel-checkpoint-')
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
            raise RuntimeError('checkpoint / audit test server did not start')
        run_api_suite(base)
        run_frontend_contract()
        print('ALL CHECKPOINT ROLE / RECORD AUDIT TESTS PASSED')
        return 0
    finally:
        server.terminate()
        server.wait(timeout=10)
        stop_db()


if __name__ == '__main__':
    sys.exit(main())

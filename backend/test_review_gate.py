#!/usr/bin/env python3
"""Focused PostgreSQL regression tests for the clearance approve/print gate.

Uses the configured PostgreSQL database (SENTINEL_DATABASE_URL or individual
SENTINEL_DB_* settings) when present, otherwise provisions an isolated temporary
PostgreSQL cluster with `pgserver`. The application server and direct test
updates both use backend.server.get_db_connection().

Verifies the three mandated rules end to end over HTTP:

  1. 12-HOUR RULE — a standard officer (FingerprintUnit / any non-admin)
     cannot approve a freshly submitted application: HTTP 400 with the
     spec-mandated detail, and the lock only releases once
     created_at + 12h has elapsed (11.9h blocked, 12.1h allowed).
  2. ADMIN BYPASS — administrators ('admin' alias / canonical SystemAdmin)
     approve instantly, review_period_bypassed=true, certificate issued.
  3. NO ERRORS ON THE HAPPY PATHS — both route spellings
     (/api/fingerprint/applications/<id>/approve and the legacy
     /api/clearance-applications/<id>/approve) answer cleanly, the row and
     the printable-page payload flip to Approved + certificate, and a
     missing submission stamp fails CLOSED for officers while admins stay
     exempt.

Usage:
    python3 backend/test_review_gate.py
"""
import datetime
import json
import os
import secrets
import selectors
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
sys.path.insert(0, ROOT)

try:
    import server as sentinel_server
except ModuleNotFoundError as error:
    if error.name == 'psycopg2':
        print('SKIP: install the backend PostgreSQL driver (psycopg2-binary) first.')
        sys.exit(0)
    raise

REVIEW_LOCK_MESSAGE = ('Review period active. Standard officers must wait 12 hours '
                       'before approving.')

PG_SERVE = '''
import pathlib, sys, pgserver
data = pathlib.Path(sys.argv[1]); data.mkdir(parents=True, exist_ok=True)
pgserver.get_server(str(data))
print(data, flush=True)
sys.stdin.read()
'''

DB_ENV_KEYS = ('SENTINEL_DB_HOST', 'SENTINEL_DB_PORT', 'SENTINEL_DB_USER',
               'SENTINEL_DB_PASSWORD', 'SENTINEL_DB_NAME')


def has_database_config():
    return bool(os.environ.get('SENTINEL_DATABASE_URL', '').strip()
                or any(os.environ.get(key) for key in DB_ENV_KEYS))


def provision_database(tmp):
    """Use the configured PostgreSQL connection or an isolated pgserver cluster.

    Returns (env_overrides, stop_callable, description), or None when no
    PostgreSQL test engine is available.
    """
    if has_database_config():
        source = ('SENTINEL_DATABASE_URL' if os.environ.get('SENTINEL_DATABASE_URL')
                  else 'SENTINEL_DB_* settings')
        return {}, lambda: None, f'configured PostgreSQL ({source})'
    try:
        import pgserver  # noqa: F401
    except ImportError:
        return None
    proc = subprocess.Popen(
        [sys.executable, '-u', '-c', PG_SERVE, os.path.join(tmp, 'pgdata')],
        stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)
    socket_dir = ''
    deadline = time.time() + 90
    selector = selectors.DefaultSelector()
    selector.register(proc.stdout, selectors.EVENT_READ)
    try:
        while time.time() < deadline and proc.poll() is None:
            events = selector.select(timeout=min(1.0, max(0, deadline - time.time())))
            if not events:
                continue
            line = proc.stdout.readline().strip()
            if line.startswith('/'):
                socket_dir = line
                break
            if not line and proc.poll() is not None:
                break
    finally:
        selector.close()
    if not socket_dir:
        proc.kill()
        proc.wait(timeout=10)
        return None
    env = {'SENTINEL_DB_HOST': socket_dir, 'SENTINEL_DB_NAME': 'postgres',
           'SENTINEL_DB_USER': 'postgres', 'SENTINEL_DB_PASSWORD': '',
           'SENTINEL_DB_PORT': '5432'}
    os.environ.update(env)

    def stop():
        if proc.poll() is None:
            if proc.stdin:
                proc.stdin.close()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)

    return env, stop, f'temporary pgserver PostgreSQL cluster at {socket_dir}'


def backdate_application(application_id, created_at):
    """Update one review timestamp through the application's PostgreSQL adapter."""
    conn = sentinel_server.get_db_connection()
    try:
        cursor = conn.execute(
            'UPDATE clearance_applications SET created_at=%s WHERE application_id=%s',
            (created_at, application_id))
        if cursor.rowcount != 1:
            raise AssertionError(f'expected to backdate one application, updated {cursor.rowcount}')
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


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
    boundary = '----sentinel-gate-test-boundary'
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
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status, json.loads(r.read().decode())
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read().decode())


def cleanup_test_fixtures(application_ids, national_ids, usernames, tokens):
    """Remove only fixtures created by this run from a configured test database."""
    if not (application_ids or national_ids or usernames or tokens):
        return
    conn = None
    try:
        conn = sentinel_server.get_db_connection()
        alias_ids = []
        if usernames:
            alias_ids = [row['id'] for row in conn.execute(
                'SELECT id FROM users WHERE username = ANY(%s)', (usernames,)).fetchall()]
        person_ids = []
        person_codes = []
        if application_ids:
            person_rows = conn.execute(
                'SELECT DISTINCT p.id, p.person_id FROM clearance_applications ca '
                'JOIN persons p ON p.id=ca.person_id WHERE ca.application_id = ANY(%s)',
                (application_ids,)).fetchall()
            person_ids = [row['id'] for row in person_rows]
            person_codes = [row['person_id'] for row in person_rows]
            conn.execute('DELETE FROM audit_events WHERE entity_id = ANY(%s)', (application_ids,))
            if person_codes:
                conn.execute('DELETE FROM audit_events WHERE entity = %s AND entity_id = ANY(%s)',
                             ('person', person_codes))
        if tokens:
            conn.execute('DELETE FROM sessions WHERE token = ANY(%s)', (tokens,))
        if alias_ids:
            alias_id_text = [str(user_id) for user_id in alias_ids]
            conn.execute('DELETE FROM audit_events WHERE user_id = ANY(%s) '
                         'OR entity_id = ANY(%s)', (alias_ids, alias_id_text))
            conn.execute('DELETE FROM sessions WHERE user_id = ANY(%s)', (alias_ids,))
        if application_ids:
            conn.execute('DELETE FROM clearance_applications WHERE application_id = ANY(%s)',
                         (application_ids,))
        if person_ids and national_ids:
            conn.execute('DELETE FROM persons WHERE id = ANY(%s) AND national_id = ANY(%s)',
                         (person_ids, national_ids))
        if alias_ids:
            conn.execute('DELETE FROM users WHERE id = ANY(%s)', (alias_ids,))
        conn.commit()
    except Exception as error:
        if conn is not None:
            conn.rollback()
        print(f'WARNING: unable to clean review-gate test fixtures: {error}')
    finally:
        if conn is not None:
            conn.close()


def main():
    port = free_port()
    tmp = tempfile.mkdtemp(prefix='sentinel-gate-')
    database_stop = lambda: None
    proc = None
    server_log = None
    test_application_ids = []
    test_national_ids = []
    test_usernames = []
    test_tokens = []
    try:
        database = provision_database(tmp)
        if database is None:
            print('SKIP: no PostgreSQL test database available.')
            print('      Set SENTINEL_DATABASE_URL or SENTINEL_DB_* variables,')
            print('      or install pgserver with: python -m pip install pgserver')
            return 0
        database_env, database_stop, database_label = database
        print('using ' + database_label)
        env = {**os.environ, **database_env,
               'SENTINEL_UPLOADS': os.path.join(tmp, 'uploads'),
               'PORT': str(port), 'SENTINEL_NO_PORT_TAKEOVER': '1'}
        server_log = open(os.path.join(tmp, 'server.log'), 'w+', encoding='utf-8')
        proc = subprocess.Popen([sys.executable, SERVER], env=env,
                                stdout=server_log, stderr=subprocess.STDOUT,
                                text=True)
        base = f'http://127.0.0.1:{port}'
        server_ready = False
        deadline = time.time() + 60
        while time.time() < deadline and proc.poll() is None:
            try:
                if request(base, 'GET', '/api/health')[0] == 200:
                    server_ready = True
                    break
            except Exception:
                time.sleep(0.2)
        if not server_ready:
            server_log.flush()
            server_log.seek(0)
            details = server_log.read().strip()
            raise RuntimeError('server did not start' + (f':\n{details}' if details else ''))

        # ---- 0) /api/health proves the review-lock build is running --------
        s, health = request(base, 'GET', '/api/health')
        assert s == 200, health
        assert health['build'] == 'sentinel-fingerprint-review-lock-12h', health
        assert health['review_lock_active'] is True, health
        assert health['fingerprint_review_window_hours'] == 12, health
        print('ok 0: /api/health reports the review-lock build, window=12h, lock armed')

        def login(username, password='ChangeMe123!'):
            s, r = request(base, 'POST', '/api/login',
                           body={'username': username, 'password': password})
            assert s == 200 and r.get('token'), (username, s, r)
            test_tokens.append(r['token'])
            return r['token'], r['user']

        admin_token, admin_user = login('admin')
        officer_token, officer_user = login('fp.officer')
        assert admin_user['role'] == 'SystemAdmin', admin_user
        assert officer_user['role'] == 'FingerprintUnit', officer_user

        # Alias users created through the admin API: 'admin' -> SystemAdmin
        # (bypass) and 'fingerprint_officer' -> FingerprintUnit (gated). Add a
        # per-run suffix so this can run repeatedly against a shared test DB.
        run_tag = secrets.token_hex(4)
        admin_alias = f'gate_admin_{run_tag}'
        fp_alias = f'gate_fp_{run_tag}'
        test_usernames.extend((admin_alias, fp_alias))
        s, r = request(base, 'POST', '/api/admin/users', admin_token, {
            'username': admin_alias, 'display_name': f'Gate Admin Alias {run_tag}',
            'password': 'secret123', 'role': 'admin'})
        assert s == 201 and r['user']['role'] == 'SystemAdmin', (s, r)
        alias_admin_token, _ = login(admin_alias, 'secret123')
        s, r = request(base, 'POST', '/api/admin/users', admin_token, {
            'username': fp_alias, 'display_name': f'Gate FP Alias {run_tag}',
            'password': 'secret123', 'role': 'fingerprint_officer'})
        assert s == 201 and r['user']['role'] == 'FingerprintUnit', (s, r)
        alias_officer_token, _ = login(fp_alias, 'secret123')
        print('ok 0b: alias roles normalise (admin->SystemAdmin, '
              'fingerprint_officer->FingerprintUnit)')

        seq = [0]
        national_id_prefix = f'{secrets.randbelow(100_000_000):08d}'

        def new_application(purpose='Employment'):
            seq[0] += 1
            fields = {'first_name': 'Gate', 'second_name': 'Rule',
                      'third_name': 'Test', 'fourth_name': f'{run_tag}-{seq[0]}',
                      'date_of_birth': '1995-03-03',
                      'national_id': f'{national_id_prefix}{seq[0]:02d}',
                      'mother_name': 'Hooyo Gate', 'residence': 'Hargeisa',
                      'phone': '+252 63 555 0900', 'sex': 'Male',
                      'email': f'gate-{run_tag}@example.com', 'purpose': purpose,
                      'guardian_name': 'Guardian Gate',
                      'guardian_relationship': 'Uncle', 'guardian_id': 'GD-7788',
                      'guardian_occupation': 'Teacher',
                      'guardian_address': 'Burao', 'guardian_phone': '+252 63 555 0901'}
            files = {'doc_app_0': ('a1.pdf', b'%PDF-a1'), 'doc_app_1': ('a2.pdf', b'%PDF-a2'),
                     'doc_guard_0': ('g1.pdf', b'%PDF-g1'), 'doc_guard_1': ('g2.pdf', b'%PDF-g2')}
            s, r = multipart_request(base, '/api/clearance-applications',
                                     officer_token, fields, files)
            assert s == 201, (s, r)
            assert r['created_at'] and r['review_window_hours'] == 12, r
            test_application_ids.append(r['application_id'])
            test_national_ids.append(fields['national_id'])
            return r['application_id']

        def backdate(application_id, hours):
            stamp = (datetime.datetime.now(datetime.timezone.utc)
                     - datetime.timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            backdate_application(application_id, stamp)

        def approve(token, aid, route='spec'):
            prefix = ('/api/fingerprint/applications' if route == 'spec'
                      else '/api/clearance-applications')
            return request(base, 'POST', f'{prefix}/{aid}/approve', token, {})

        # ---- 1) 12-HOUR RULE: officer locked on a fresh application --------
        app1 = new_application()
        s, r = approve(officer_token, app1)
        assert s == 400, f'officer instant approval must be 400, got {s}: {r}'
        assert r.get('detail') == REVIEW_LOCK_MESSAGE, r
        assert r.get('error') == REVIEW_LOCK_MESSAGE, r
        assert r.get('code') == 'review_period_active', r
        assert r.get('review_window_hours') == 12, r
        assert r.get('hours_remaining', 0) > 0, r
        assert r.get('review_eligible_at'), r
        # the row is untouched: still Pending Review, no certificate
        s, detail = request(base, 'GET', f'/api/clearance-applications/{app1}', officer_token)
        assert s == 200 and detail['status'] == 'Pending Review', detail
        assert detail['certificate_number'] is None, detail
        assert detail['review']['review_locked'] is True, detail
        assert detail['can_approve'] is False, detail
        # the alias officer is gated identically, on both route spellings
        s, r = approve(alias_officer_token, app1, route='legacy')
        assert s == 400 and r.get('detail') == REVIEW_LOCK_MESSAGE, (s, r)
        print('ok 1: officer (canonical + alias, both routes) is locked for 12h '
              'with the exact spec payload')

        # ---- 1b) boundary: 11.9h stays locked, 12.1h releases --------------
        backdate(app1, 11.9)
        s, r = approve(officer_token, app1)
        assert s == 400, f'11.9h must stay locked, got {s}: {r}'
        backdate(app1, 12.1)
        s, r = approve(officer_token, app1)
        assert s == 201 and r['status'] == 'Approved' and r['certificate_number'], (s, r)
        assert r['review_period_bypassed'] is False, r
        assert r['approved_by_role'] == 'FingerprintUnit', r
        assert r['reviewer_is_fingerprint_officer'] is True, r
        # printable page payload flips to Approved + certificate
        s, detail = request(base, 'GET', f'/api/clearance-applications/{app1}', officer_token)
        assert s == 200 and detail['status'] == 'Approved', detail
        assert detail['certificate_number'] == r['certificate_number'], detail
        assert detail['review']['review_locked'] is False, detail
        assert detail['can_approve'] is True, detail
        print('ok 1b: 11.9h locked / 12.1h released — officer approval issues the '
              'certificate and unlocks the printable page')

        # ---- 2) ADMIN BYPASS: instant approval on a fresh application ------
        app2 = new_application(purpose='Travel')
        s, r = approve(admin_token, app2)
        assert s == 201, f'admin instant approval must succeed, got {s}: {r}'
        assert r['status'] == 'Approved' and r['certificate_number'], r
        assert r['review_period_bypassed'] is True, r
        assert r['approved_by_role'] == 'SystemAdmin', r
        # admin sees can_approve even while the row is inside the window
        app3 = new_application(purpose='Education')
        s, detail = request(base, 'GET', f'/api/clearance-applications/{app3}', admin_token)
        assert s == 200 and detail['review']['review_locked'] is True, detail
        assert detail['can_approve'] is True, detail          # admin bypass flag
        s, detail = request(base, 'GET', f'/api/clearance-applications/{app3}', officer_token)
        assert s == 200 and detail['can_approve'] is False, detail
        # the 'admin' alias user bypasses too, on the legacy route
        s, r = approve(alias_admin_token, app3, route='legacy')
        assert s == 201 and r['review_period_bypassed'] is True, (s, r)
        assert r['approved_by_role'] == 'SystemAdmin', r
        print('ok 2: admin + admin-alias bypass the 12h window instantly '
              '(review_period_bypassed=true), can_approve=true while locked')

        # ---- 3) fail-closed: missing stamp locks officers, not admins ------
        app4 = new_application(purpose='Citizenship')
        backdate_application(app4, None)
        s, r = approve(officer_token, app4)
        assert s == 400 and r.get('code') == 'review_period_active', (s, r)
        assert r.get('reason') == 'submission timestamp missing', r
        s, detail = request(base, 'GET', f'/api/clearance-applications/{app4}', officer_token)
        assert s == 200 and detail['review']['review_locked'] is True, detail
        assert detail['can_approve'] is False, detail
        s, r = approve(admin_token, app4)
        assert s == 201 and r['status'] == 'Approved', (s, r)
        print('ok 3: missing created_at fails closed for officers; admins stay exempt')

        # ---- 4) module gate: a non-fingerprint role cannot approve ---------
        ap_token, _ = login('ap.officer')
        app5 = new_application(purpose='Licence')
        s, r = approve(ap_token, app5)
        assert s == 401, f'airport officer must be refused by the module gate, got {s}: {r}'
        # unauthenticated caller is refused as well
        s, r = approve('', app5)
        assert s == 401, (s, r)
        # approving an unknown id is a clean 404 (never a 500)
        s, r = approve(admin_token, 'FP-00000000')
        assert s == 404, (s, r)
        print('ok 4: module gate (401) for foreign roles, 401 anonymous, '
              '404 unknown id — no 500s on the click path')

        # ---- 5) re-approval keeps the issued certificate -------------------
        s, detail = request(base, 'GET', f'/api/clearance-applications/{app2}', admin_token)
        assert s == 200 and detail['certificate_number'], (s, detail)
        cert = detail['certificate_number']
        s, r = approve(admin_token, app2)
        assert s == 201 and r['certificate_number'] == cert, (s, r)
        print('ok 5: re-approving an approved row is idempotent (same certificate)')

        # ---- 6) the gate survives a server restart (persistent sessions) ---
        # Sessions live in PostgreSQL, so a signed-in browser keeps its token
        # across a restart — and the review lock must still be enforced
        # against it (an in-memory token map used to 401 every browser and
        # push the frontend into its offline fallbacks).
        app6 = new_application(purpose='Education')
        proc.terminate(); proc.wait(timeout=10)
        proc = subprocess.Popen([sys.executable, SERVER], env=env,
                                stdout=server_log, stderr=subprocess.STDOUT,
                                text=True)
        restarted = False
        deadline = time.time() + 60
        while time.time() < deadline and proc.poll() is None:
            try:
                if request(base, 'GET', '/api/health')[0] == 200:
                    restarted = True
                    break
            except Exception:
                time.sleep(0.2)
        if not restarted:
            server_log.flush()
            server_log.seek(0)
            details = server_log.read().strip()
            raise RuntimeError('server did not restart' + (f':\n{details}' if details else ''))
        s, me = request(base, 'GET', '/api/me', officer_token)
        assert s == 200 and me['username'] == 'fp.officer', (s, me)
        s, r = approve(officer_token, app6)
        assert s == 400 and r.get('detail') == REVIEW_LOCK_MESSAGE, (s, r)
        s, r = approve(admin_token, app6)
        assert s == 201 and r['review_period_bypassed'] is True, (s, r)
        print('ok 6: gate still enforced after a restart — officer locked, admin bypasses')

        print('ALL REVIEW-GATE TESTS PASSED')
        return 0
    finally:
        if proc is not None and proc.poll() is None:
            proc.terminate()
            try:
                proc.wait(timeout=10)
            except subprocess.TimeoutExpired:
                proc.kill()
                proc.wait(timeout=10)
        cleanup_test_fixtures(test_application_ids, test_national_ids,
                              test_usernames, test_tokens)
        if server_log is not None:
            server_log.close()
        database_stop()
        shutil.rmtree(tmp, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())

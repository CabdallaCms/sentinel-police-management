#!/usr/bin/env python3
"""Focused regression tests for the clearance approve/print gate.

Standard library only. Boots backend/server.py against a temporary SQLite
database and verifies the three mandated rules end to end over HTTP:

  1. 12-HOUR RULE — a standard officer (FingerprintUnit / any non-admin)
     cannot approve a freshly submitted application: HTTP 400 with the
     spec-mandated detail, and the lock only releases once
     created_at + 12h has elapsed (11.9h blocked, 12.1h allowed).
  2. ADMIN BYYPASS — administrators ('admin' alias / canonical SystemAdmin)
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

REVIEW_LOCK_MESSAGE = ('Review period active. Standard officers must wait 12 hours '
                       'before approving.')


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


def main():
    port = free_port()
    tmp = tempfile.mkdtemp(prefix='sentinel-gate-')
    db_path = os.path.join(tmp, 'db.sqlite')
    env = {**os.environ, 'SENTINEL_DB': db_path,
           'SENTINEL_UPLOADS': os.path.join(tmp, 'uploads'),
           'PORT': str(port), 'SENTINEL_NO_PORT_TAKEOVER': '1'}
    proc = subprocess.Popen([sys.executable, SERVER], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(50):
            try:
                if request(base, 'GET', '/api/health')[0] == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('server did not start')

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
            return r['token'], r['user']

        admin_token, admin_user = login('admin')
        officer_token, officer_user = login('fp.officer')
        assert admin_user['role'] == 'SystemAdmin', admin_user
        assert officer_user['role'] == 'FingerprintUnit', officer_user

        # Alias users created through the admin API: 'admin' -> SystemAdmin
        # (bypass) and 'fingerprint_officer' -> FingerprintUnit (gated).
        s, r = request(base, 'POST', '/api/admin/users', admin_token, {
            'username': 'gate.admin.alias', 'display_name': 'Gate Admin Alias',
            'password': 'secret123', 'role': 'admin'})
        assert s == 201 and r['user']['role'] == 'SystemAdmin', (s, r)
        alias_admin_token, _ = login('gate.admin.alias', 'secret123')
        s, r = request(base, 'POST', '/api/admin/users', admin_token, {
            'username': 'gate.fp.alias', 'display_name': 'Gate FP Alias',
            'password': 'secret123', 'role': 'fingerprint_officer'})
        assert s == 201 and r['user']['role'] == 'FingerprintUnit', (s, r)
        alias_officer_token, _ = login('gate.fp.alias', 'secret123')
        print('ok 0b: alias roles normalise (admin->SystemAdmin, '
              'fingerprint_officer->FingerprintUnit)')

        seq = [0]

        def new_application(purpose='Employment'):
            seq[0] += 1
            fields = {'first_name': 'Gate', 'second_name': 'Rule',
                      'third_name': 'Test', 'fourth_name': str(seq[0]),
                      'date_of_birth': '1995-03-03',
                      'national_id': f'777{seq[0]:05d}',
                      'mother_name': 'Hooyo Gate', 'residence': 'Hargeisa',
                      'phone': '+252 63 555 0900', 'sex': 'Male',
                      'email': 'gate@example.com', 'purpose': purpose,
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
            return r['application_id']

        def backdate(application_id, hours):
            stamp = (datetime.datetime.now(datetime.timezone.utc)
                     - datetime.timedelta(hours=hours)).strftime('%Y-%m-%d %H:%M:%S')
            conn = sqlite3.connect(db_path, timeout=10)
            try:
                conn.execute('UPDATE clearance_applications SET created_at=? '
                             'WHERE application_id=?', (stamp, application_id))
                conn.commit()
            finally:
                conn.close()

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
        conn = sqlite3.connect(db_path, timeout=10)
        try:
            conn.execute('UPDATE clearance_applications SET created_at=NULL '
                         'WHERE application_id=?', (app4,))
            conn.commit()
        finally:
            conn.close()
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
        # Sessions live in SQLite, so a signed-in browser keeps its token
        # across a restart — and the review lock must still be enforced
        # against it (an in-memory token map used to 401 every browser and
        # push the frontend into its offline fallbacks).
        app6 = new_application(purpose='Education')
        proc.terminate(); proc.wait(timeout=10)
        proc = subprocess.Popen([sys.executable, SERVER], env=env,
                                stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        for _ in range(50):
            try:
                if request(base, 'GET', '/api/health')[0] == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('server did not restart')
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
        proc.terminate()
        proc.wait(timeout=10)


if __name__ == '__main__':
    sys.exit(main())

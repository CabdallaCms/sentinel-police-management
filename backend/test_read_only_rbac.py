#!/usr/bin/env python3
"""Regression test — unit module scoping + the global read-only Commander role.

Covers the two RBAC changes end to end against a real server process and a real
PostgreSQL database (the backend serves PostgreSQL only):

  1. CENTRAL POLICE SEARCH IS NOT AN AIRPORT / CID MODULE
     `ROLE_MODULES[AirportControl]` and `ROLE_MODULES[CIDUnit]` no longer carry
     `policesearch`. Both units keep their own unit scope plus Central Person
     Search ('people') and nothing else — verified through /api/me AND through
     the module-gated endpoints (the vehicle registry, which is part of Central
     Police Search, is no longer reachable from either unit).

  2. THE COMMANDER / HIGH COMMAND ROLE IS GLOBALLY READ-ONLY
     Every accepted spelling ('commander', 'Commander', 'chief_commander',
     'high_command', 'HighCommand', 'command_hq', 'hq_command', 'police_hq')
     resolves to the canonical `chief_commander` role, which
       * reads every dashboard, register, log and search (HTTP 200),
       * is refused by every mutation route with **403 Forbidden**
         (`code: read_only_role`) — POST, PATCH and DELETE, including the
         routes it could previously write (stations),
       * keeps the session plumbing (/api/login, /api/logout) working,
       * receives no quick-registration actions on the dashboard, and
       * never gains a write capability (no `stations:manage`).
     Write-capable roles are unaffected: the same calls still succeed for
     SystemAdmin and for the unit officers.

Database resolution (mirrors the other suites):
  * SENTINEL_DB_HOST / _NAME / _USER / _PASSWORD / _PORT when set, or
  * a throwaway cluster booted with the `pgserver` pip package
    (`pip install pgserver`) in a temporary directory, or
  * SKIP (exit 0) with a message when neither is available.

Usage:
    python3 backend/test_read_only_rbac.py
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

PASS, FAIL, SKIP = [], [], []


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


def check(condition, label):
    (PASS if condition else FAIL).append(label)
    print(('  PASS ' if condition else '  FAIL ') + label)
    return condition


# ---------------------------------------------------------------------------
# PostgreSQL test database
# ---------------------------------------------------------------------------
PG_SERVE = '''
import pathlib, sys, time, pgserver
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
srv = pgserver.get_server(str(d))
print(d, flush=True)
sys.stdin.read()
'''


def provision_database(tmp):
    """Return (env_overrides, stop_callable) or (None, None) when unavailable."""
    if os.environ.get('SENTINEL_DB_HOST') or os.environ.get('SENTINEL_DB_NAME'):
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
    env = {'SENTINEL_DB_HOST': socket_dir, 'SENTINEL_DB_NAME': 'postgres',
           'SENTINEL_DB_USER': 'postgres', 'SENTINEL_DB_PASSWORD': ''}
    return (env, lambda: proc.kill())


# ---------------------------------------------------------------------------
# Suites
# ---------------------------------------------------------------------------
def unit_module_suite(base):
    print('== 1. Central Police Search removed from Airport Control + CID ==')
    expected = {'ap.officer': ('AirportControl', {'dashboard', 'people', 'airport'}),
                'cid.officer': ('CIDUnit', {'dashboard', 'people', 'cid', 'crimes'})}
    tokens = {}
    for user, (role, want) in expected.items():
        token, body = login(base, user)
        tokens[user] = token
        _, me = request(base, 'GET', '/api/me', token)
        mods = set(me['modules'])
        check('policesearch' not in mods, f'{user}: no Central Police Search ({sorted(mods)})')
        check(mods == want, f'{user}: module set is exactly {sorted(want)}')
        check('people' in mods, f'{user}: keeps Central Person Search')
        check('policesearch' not in body['user']['modules'],
              f'{user}: login payload agrees')
    # The vehicle registry is part of the Central Police Search surface and was
    # only reachable through the `policesearch` module — the Airport Unit must
    # no longer see it. CID keeps the fleet read through its `crimes` module.
    check(request(base, 'GET', '/api/vehicles', tokens['ap.officer'])[0] == 401,
          'airport officer is refused POST-free vehicle read (/api/vehicles -> 401)')
    # Fingerprint keeps the module (only Airport + CID are stripped).
    fp, _ = login(base, 'fp.officer')
    _, fpme = request(base, 'GET', '/api/me', fp)
    check('policesearch' in set(fpme['modules']), 'Fingerprint Unit keeps Central Police Search')
    hr, _ = login(base, 'hr.officer')
    _, hrme = request(base, 'GET', '/api/me', hr)
    check('policesearch' in set(hrme['modules']), 'HR Directorate keeps Central Police Search')


def commander_identity_suite(base):
    print('== 2. Commander identity — global read-only authority ==')
    token, body = login(base, 'chief')
    _, me = request(base, 'GET', '/api/me', token)
    check(me['role'] == 'chief_commander', f"canonical role chief_commander ({me['role']})")
    check(me.get('read_only') is True and me.get('can_write') is False,
          'user payload carries read_only=true / can_write=false')
    vis = me['visibility']
    check(vis['read_only'] is True and vis['is_read_only'] is True and vis['can_write'] is False,
          'visibility block carries the read-only flags')
    check(vis['is_chief_commander'] is True and vis['is_admin'] is False,
          'chief commander, never SystemAdmin')
    check(vis['can_manage_stations'] is False, 'station management retired for the read-only role')
    check(set(me['permissions']) == {'analytics:global', 'cid:view', 'personnel:view',
                                     'transport:view', 'readonly:global'},
          f"permissions {sorted(me['permissions'])}")
    check('stations:manage' not in me['permissions'], 'no stations:manage write capability')
    need = {'dashboard', 'executive', 'oversight', 'people', 'policesearch', 'fingerprint',
            'airport', 'cid', 'checkpoints', 'crimes', 'stations', 'officers', 'conduct', 'cars'}
    check(need <= set(me['modules']), 'universal monitoring visibility across every register')
    check(vis['can_view_global_analytics'] is True, 'executive analytics surface retained')
    return token


def commander_read_suite(base, token):
    print('== 3. Commander reads — dashboards, registers, logs, searches ==')
    for path in ('/api/dashboard', '/api/me', '/api/persons', '/api/analytics/global',
                 '/api/analytics?module=all', '/api/cid/analytics', '/api/officers/analytics',
                 '/api/vehicles/analytics', '/api/stations/analytics', '/api/officers',
                 '/api/officers/promotions', '/api/officers/discipline', '/api/stations',
                 '/api/vehicles', '/api/crimes', '/api/conduct', '/api/crime-cases',
                 '/api/suspect-alerts', '/api/checkpoint-events', '/api/clearance-applications',
                 '/api/airport-records'):
        status, _ = request(base, 'GET', path, token)
        check(status == 200, f'GET {path} -> {status}')
    _, dash = request(base, 'GET', '/api/dashboard', token)
    check(dash['read_only'] is True and dash['can_write'] is False, 'dashboard read_only contract')
    check(dash['quick_actions'] == [], f"dashboard quick actions empty ({dash['quick_actions']})")
    check('view-only' in dash.get('subhead', ''), f"dashboard subhead {dash.get('subhead')!r}")


def commander_write_suite(base, token):
    print('== 4. Commander cannot write — every mutation answers 403 Forbidden ==')
    mutations = [
        ('POST', '/api/persons', {'full_name': 'Refused Person'}),
        ('POST', '/api/airport-records', {'person_id': 'P-0001'}),
        ('POST', '/api/clearance-applications', {'person_id': 'P-0001'}),
        ('POST', '/api/crime-cases', {'category': 'Theft'}),
        ('POST', '/api/suspect-alerts', {'person_id': 'P-0001'}),
        ('POST', '/api/checkpoint-events', {'person_id': 'P-0001'}),
        ('POST', '/api/stations', {'name': 'Refused Station', 'station_tier': 'Outpost',
                                   'region': 'Sool', 'district': 'Xudun',
                                   'contact_phone': '0907000000'}),
        ('POST', '/api/officers', {'full_name': 'Refused Officer'}),
        ('POST', '/api/vehicles', {'plate_number': 'HQ-0'}),
        ('POST', '/api/crimes', {'category': 'Theft'}),
        ('POST', '/api/conduct/submit', {'officer_service_id': 'POL-1'}),
        ('POST', '/api/conduct/CD-0001/review', {'decision': 'approve'}),
        ('POST', '/api/crime-cases/CC-0001/evidence', {}),
        ('POST', '/api/admin/users', {'username': 'nope', 'display_name': 'nope',
                                      'role': 'CIDUnit', 'password': 'Abcdef12!'}),
        ('PATCH', '/api/persons/P-0001', {'phone': '+252 63 000 0000'}),
        ('PATCH', '/api/crime-cases/CC-0001', {'status': 'Closed'}),
        ('PATCH', '/api/officers/promotions/PRM-0001', {'verification_status': 'Verified'}),
        ('PATCH', '/api/officers/discipline/DSC-0001', {'status': 'Closed'}),
        ('PATCH', '/api/admin/users/2', {'active': False}),
        ('DELETE', '/api/persons/P-0001', None),
        ('DELETE', '/api/crime-cases/CC-0001', None),
    ]
    for method, path, body in mutations:
        status, payload = request(base, method, path, token, body)
        code = payload.get('code') if isinstance(payload, dict) else None
        check(status == 403 and code == 'read_only_role',
              f'{method} {path} -> {status} ({code})')


def commander_session_suite(base, token):
    print('== 5. Session plumbing + write-capable roles unaffected ==')
    status, payload = request(base, 'POST', '/api/logout', token)
    check(status == 200 and payload.get('ok') is True,
          'POST /api/logout -> 200 (session plumbing is exempt)')
    token2, body = login(base, 'chief')
    check(body['user'].get('read_only') is True, 're-login keeps the read-only flag')
    check(bool(token2), 'the Commander can still sign in')

    admin, _ = login(base, 'admin')
    check(request(base, 'POST', '/api/stations', admin,
                  {'name': 'RBAC Test Outpost', 'station_tier': 'Outpost', 'region': 'Sool',
                   'district': 'Xudun', 'contact_phone': '0907000111'})[0] == 201,
          'SystemAdmin can still create a station (201)')
    _, adminme = request(base, 'GET', '/api/me', admin)
    check(adminme.get('read_only') is False and adminme.get('can_write') is True,
          'SystemAdmin is not read-only')
    cid, _ = login(base, 'cid.officer')
    check(request(base, 'POST', '/api/crime-cases', cid,
                  {'category': 'Theft', 'location': 'Sool',
                   'incident_summary': 'read-only suite fixture'})[0] == 201,
          'CID officer can still open a crime case (201)')
    fp, _ = login(base, 'fp.officer')
    check(request(base, 'GET', '/api/clearance-applications', fp)[0] == 200,
          'Fingerprint officer read is unaffected')


def commander_alias_suite(base, admin_token):
    print('== 6. Every Commander / High Command spelling is read-only ==')
    stamp = str(int(time.time()))
    for idx, alias in enumerate(('Commander', 'high_command', 'HighCommand', 'command_hq',
                                 'hq_command', 'police_hq', 'chief.commander')):
        # usernames are case-insensitively unique, so keep one counter in the name
        username = 'cmdr%d_%s_%s' % (idx, alias.lower().replace('.', '').replace('_', ''),
                                     stamp[-5:])
        status, created = request(base, 'POST', '/api/admin/users', admin_token,
                                  {'username': username, 'display_name': 'Cdr ' + alias,
                                   'role': alias, 'password': 'Abcdef12!',
                                   'branch': 'Police HQ / Command'})
        if not check(status == 201 and created['user']['role'] == 'chief_commander'
                     and created['user'].get('read_only') is True,
                     f"role {alias!r} -> {status} stored as "
                     f"{created['user']['role'] if status == 201 else created}"):
            continue
        token, _ = login(base, username, 'Abcdef12!')
        _, me = request(base, 'GET', '/api/me', token)
        check(me['read_only'] is True, f'{alias} alias user is read-only')
        check(request(base, 'GET', '/api/dashboard', token)[0] == 200,
              f'{alias} alias user can read the dashboard')
        status, payload = request(base, 'POST', '/api/persons', token, {'full_name': 'Nope'})
        check(status == 403 and payload.get('code') == 'read_only_role',
              f'{alias} alias user POST /api/persons -> {status}')


def main():
    tmp = tempfile.mkdtemp(prefix='sentinel-ro-rbac-')
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
    try:
        for _ in range(90):
            try:
                if request(base, 'GET', '/api/health')[0] == 200:
                    break
            except Exception:
                time.sleep(0.25)
        else:
            raise RuntimeError('the backend did not start (is PostgreSQL reachable?)')

        unit_module_suite(base)
        token = commander_identity_suite(base)
        commander_read_suite(base, token)
        commander_write_suite(base, token)
        commander_session_suite(base, token)
        admin, _ = login(base, 'admin')
        commander_alias_suite(base, admin)
    finally:
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
    print('ALL READ-ONLY / UNIT-MODULE RBAC TESTS PASSED')
    return 0


if __name__ == '__main__':
    sys.exit(main())

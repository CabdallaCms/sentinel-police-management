#!/usr/bin/env python3
"""Operations-lifecycle tests — station deletion safety.

`test_unit_in_use_cannot_be_deleted` is the regression for the FK-conflict
handling on `DELETE /api/stations/{ref}`: deleting a station that records
(in this repo: officers / crime incidents / conduct actions / vehicles —
the SQLite-era ticket named a `persons.station_id` foreign key) still
reference must answer a clean **409 Conflict** with a descriptive body,
never an unhandled `psycopg2.IntegrityError` 500.

The suite boots the real API against a throwaway PostgreSQL database on the
configured cluster (see backend/pg_fixture_db.py), exactly like the script
suites in backend/.

Run with:  python3 -m pytest tests/test_operations.py -v
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

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ROOT, 'backend'))
import pg_fixture_db  # noqa: E402

SERVER = os.path.join(ROOT, 'backend', 'server.py')

VALID_STATION = {'name': 'Ops Test Post', 'region': 'Sool', 'district': 'Laascaanood',
                 'station_tier': 'Outpost', 'contact_phone': '0907000111'}


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


@pytest.fixture(scope='module')
def api():
    """(base_url, admin_token, dbname) — the API against a scratch database."""
    dbname, db_env, drop_db = pg_fixture_db.temp_database('sentinel_ops')
    port = free_port()
    tmp = tempfile.mkdtemp(prefix='sentinel-ops-')
    env = dict(os.environ, **db_env, PORT=str(port),
               SENTINEL_UPLOADS=os.path.join(tmp, 'uploads'),
               SENTINEL_NO_PORT_TAKEOVER='1')
    proc = subprocess.Popen([sys.executable, SERVER], env=env,
                            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    base = f'http://127.0.0.1:{port}'
    try:
        for _ in range(60):
            try:
                if request(base, 'GET', '/api/health')[0] == 200:
                    break
            except Exception:
                time.sleep(0.2)
        else:
            raise RuntimeError('station-ops test server did not start')
        s, body = request(base, 'POST', '/api/login',
                          body={'username': 'admin', 'password': 'ChangeMe123!'})
        assert s == 200 and body.get('token'), (s, body)
        yield base, body['token'], dbname
    finally:
        proc.terminate()
        proc.wait(timeout=10)
        drop_db()


def _create_station(base, admin, name):
    s, r = request(base, 'POST', '/api/stations', admin, {**VALID_STATION, 'name': name})
    assert s == 201, (s, r)
    return r['station']['station_id']


def _station_pk(dbname, code):
    conn = pg_fixture_db.connect(dbname)
    try:
        row = conn.execute('SELECT id FROM police_stations WHERE station_id=?', (code,)).fetchone()
        assert row, f'station {code} not persisted'
        return row['id']
    finally:
        conn.close()


def _seed_officer(dbname, station_pk, service_id='POL-OPS-0001'):
    """Attach an officer row to the station (minimum NOT NULL columns)."""
    conn = pg_fixture_db.connect(dbname)
    try:
        conn.execute("""INSERT INTO officers(service_id, rank, unit, station_id,
                        date_of_enlistment, full_name, mother_name, date_of_birth,
                        place_of_birth, contact_number, guarantor_name,
                        guarantor_address, guarantor_contact, doc1_type, doc1_path)
                        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                     (service_id, 'Constable', 'General Patrol', station_pk,
                      '2024-01-15', 'Ops Fixture Officer', 'Fixture Mother',
                      '1996-05-05', 'Laascaanood', '0615000000',
                      'Fixture Guarantor', 'Laascaanood', '0615000001',
                      'National ID', '/docs/fixture.pdf'))
        conn.commit()
    finally:
        conn.close()


def test_unit_in_use_cannot_be_deleted(api):
    """Station with dependent records: DELETE -> 409 Conflict, not a 500."""
    base, admin, dbname = api
    code = _create_station(base, admin, 'In-Use Checkpoint Post')
    _seed_officer(dbname, _station_pk(dbname, code))

    s, r = request(base, 'DELETE', f'/api/stations/{code}', admin)

    assert s == 409, f'in-use station must answer 409 Conflict, got {s}: {r}'
    assert r.get('code') == 'station_in_use', r
    assert 'officer' in r['error'].lower(), r
    assert r.get('dependents', {}).get('officers') == 1, r
    # Nothing was deleted — the station is still served.
    s, lst = request(base, 'GET', '/api/stations', admin)
    assert s == 200 and any(x['station_id'] == code for x in lst['items']), lst


def test_unused_station_delete_succeeds(api):
    """A station nothing references deletes cleanly (200) — then 404."""
    base, admin, _ = api
    code = _create_station(base, admin, 'Unreferenced Landing Post')

    s, r = request(base, 'DELETE', f'/api/stations/{code}', admin)
    assert s == 200 and r.get('deleted') is True, (s, r)
    assert r['station']['station_id'] == code, r

    s, gone = request(base, 'GET', '/api/stations', admin)
    assert not any(x['station_id'] == code for x in gone['items']), gone
    s, r = request(base, 'DELETE', f'/api/stations/{code}', admin)
    assert s == 404, (s, r)


def test_station_delete_guards(api):
    """Unknown ids 404, foreign modules 401, readonly Commander 403, other
    DELETE paths keep their 405."""
    base, admin, _ = api
    s, r = request(base, 'DELETE', '/api/stations/STN-NOPE-9999', admin)
    assert s == 404, (s, r)

    s, cp = request(base, 'POST', '/api/login',
                    body={'username': 'cp.south', 'password': 'ChangeMe123!'})
    assert s == 200, cp
    s, r = request(base, 'DELETE', '/api/stations/STN-NOPE-9999', cp['token'])
    assert s == 401, f'checkpoint role holds no stations module: {s} {r}'

    s, chief = request(base, 'POST', '/api/login',
                       body={'username': 'chief', 'password': 'ChangeMe123!'})
    assert s == 200, chief
    s, r = request(base, 'DELETE', '/api/stations/STN-NOPE-9999', chief['token'])
    assert s == 403 and r.get('code') == 'read_only_role', (s, r)

    s, r = request(base, 'DELETE', '/api/persons/P-0001', admin)
    assert s == 405, f'non-station DELETE paths stay 405: {s} {r}'


if __name__ == '__main__':
    sys.exit(pytest.main([os.path.abspath(__file__), '-v']))

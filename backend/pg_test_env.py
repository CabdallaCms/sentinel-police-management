#!/usr/bin/env python3
"""Provision a PostgreSQL database for a test harness and print its settings.

Added under WP-01 so the Node (jsdom) harnesses can obtain a real PostgreSQL
database the same way the Python suites do. The Python suites call
`test_review_gate.provision_database()` directly; a Node process cannot, so it
spawns this helper instead.

Behaviour
---------
* Uses the configured database when SENTINEL_DATABASE_URL or any SENTINEL_DB_*
  variable is set; otherwise provisions a temporary `pgserver` cluster.
* Creates a fresh, empty database so each harness sees exact fixture counts.
* Prints ONE line of JSON — the environment overrides the caller should apply
  to the server process — then blocks on stdin.
* The cluster is torn down when stdin closes (i.e. when the caller exits).

Usage (from Node):
    const proc = spawn(python, [".../pg_test_env.py", "<label>"], ...);
    // read one line of stdout -> JSON.parse -> spread into the server env
    // keep proc.stdin open for the lifetime of the test, then end() it.

Exit code 3 means no PostgreSQL engine is available; the caller should skip.
"""
import json
import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.abspath(__file__))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


def main():
    label = (sys.argv[1] if len(sys.argv) > 1 else 'node').replace('-', '_')
    try:
        import test_review_gate as harness
    except Exception as exc:  # pragma: no cover - import guard
        print(f'cannot import the shared test bootstrap: {exc}', file=sys.stderr)
        return 3

    tmp = tempfile.mkdtemp(prefix=f'sentinel-{label}-')
    provisioned = harness.provision_database(tmp)
    if provisioned is None:
        print('no PostgreSQL test engine available '
              '(set SENTINEL_DATABASE_URL / SENTINEL_DB_* or install pgserver)',
              file=sys.stderr)
        return 3
    _env, stop, description = provisioned
    print(description, file=sys.stderr)

    # A dedicated empty database keeps fixture counts exact.
    import secrets
    import psycopg2
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT

    name = f'sentinel_{label}_{secrets.token_hex(4)}'
    admin_conn = psycopg2.connect(
        dbname='postgres',
        user=os.environ.get('SENTINEL_DB_USER', 'postgres'),
        password=os.environ.get('SENTINEL_DB_PASSWORD', ''),
        host=os.environ.get('SENTINEL_DB_HOST', 'localhost'),
        port=os.environ.get('SENTINEL_DB_PORT', '5432'),
        connect_timeout=10)
    admin_conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
    try:
        admin_conn.cursor().execute(f'CREATE DATABASE {name}')
    finally:
        admin_conn.close()

    settings = {
        'SENTINEL_DB_HOST': os.environ.get('SENTINEL_DB_HOST', 'localhost'),
        'SENTINEL_DB_PORT': os.environ.get('SENTINEL_DB_PORT', '5432'),
        'SENTINEL_DB_USER': os.environ.get('SENTINEL_DB_USER', 'postgres'),
        'SENTINEL_DB_PASSWORD': os.environ.get('SENTINEL_DB_PASSWORD', ''),
        'SENTINEL_DB_NAME': name,
    }
    print(json.dumps(settings), flush=True)

    try:
        sys.stdin.read()          # block until the caller closes stdin
    except KeyboardInterrupt:     # pragma: no cover
        pass
    finally:
        stop()
    return 0


if __name__ == '__main__':
    sys.exit(main())

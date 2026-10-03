"""Shared PostgreSQL test harness: builds a scratch database from migrations/ + dev seeds.

Uses BLUEPRINT_PG_URI if set (any PostgreSQL 14+ where CREATE DATABASE works), otherwise an
embedded PostgreSQL via `pgserver` (pip install pgserver psycopg2-binary).
"""
import glob
import os
import tempfile

import psycopg2

ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
MIGRATIONS = os.path.join(ROOT, 'migrations')
_server = None
_admin_uri = None


def admin_uri():
    global _server, _admin_uri
    if _admin_uri:
        return _admin_uri
    _admin_uri = os.environ.get('BLUEPRINT_PG_URI')
    if not _admin_uri:
        import pgserver
        _server = pgserver.get_server(tempfile.mkdtemp(prefix='sentinel_pg_'), cleanup_mode='stop')
        _admin_uri = _server.get_uri()
    return _admin_uri


def uri_for(dbname):
    uri = admin_uri()
    if '?' in uri:
        base, q = uri.split('?', 1)
        return base.rsplit('/', 1)[0] + '/' + dbname + '?' + q
    return uri.rsplit('/', 1)[0] + '/' + dbname


def sql_files(demo_people=False):
    """Migrations, then dev seeds.  Demo ACCOUNTS are always loaded (tests need users); demo PEOPLE only
    on request, so ordinary tests start from an empty registry."""
    files = (sorted(glob.glob(os.path.join(MIGRATIONS, '[0-9]*.sql')))
             + sorted(glob.glob(os.path.join(MIGRATIONS, 'dev', '*_demo_accounts.sql'))))
    if demo_people:
        files += sorted(glob.glob(os.path.join(MIGRATIONS, 'dev', '*_demo_persons.sql')))
        files += sorted(glob.glob(os.path.join(MIGRATIONS, 'dev', '*_demo_operational.sql')))
        files += sorted(glob.glob(os.path.join(MIGRATIONS, 'dev', '*_demo_directorate.sql')))
    return files


def create_database(dbname, demo_people=False):
    """(Re)create `dbname`, apply every migration then the dev seeds; returns its URI."""
    c = psycopg2.connect(admin_uri())
    c.autocommit = True
    cur = c.cursor()
    cur.execute(f'DROP DATABASE IF EXISTS {dbname}')
    cur.execute(f'CREATE DATABASE {dbname}')
    cur.execute("SELECT 1 FROM pg_roles WHERE rolname='app_rw'")
    if not cur.fetchone():
        cur.execute('CREATE ROLE app_rw NOLOGIN')
    c.close()
    c = psycopg2.connect(uri_for(dbname))
    cur = c.cursor()
    for f in sql_files(demo_people):
        with open(f) as fh:
            cur.execute(fh.read())
    try:                                      # dev/test signing key (public half only) so approvals can be signed
        from app.directorate import signing
        signing.register_dev_key(c)
    except ImportError:                       # `cryptography` not installed: approvals simply stay unavailable
        pass
    cur.execute('GRANT USAGE ON SCHEMA public TO app_rw')
    cur.execute('GRANT ALL ON ALL TABLES IN SCHEMA public TO app_rw')
    c.commit()
    c.close()
    return uri_for(dbname)

#!/usr/bin/env python3
"""PostgreSQL fixture-database helpers for the executable test suites.

The suites predate the PostgreSQL-only backend: they used to spawn the API
with ``SENTINEL_DB=/tmp/xxx.db`` (a throwaway SQLite file) and poke the same
file directly with ``sqlite3.connect()`` to backdate rows and stage state.
``SENTINEL_DB`` is ignored by the PostgreSQL backend, so the equivalent
primitive is now a throwaway **database** on the configured cluster:

* :func:`temp_database` — ``CREATE DATABASE`` a uniquely-named scratch
  database on the cluster the root ``.env`` / ``SENTINEL_DB_*`` settings
  point at, and return the ``SENTINEL_DB_*`` environment overrides that aim
  a spawned server at it plus a ``drop()`` cleanup callable. This keeps
  every suite's deterministic fixture isolated from (and out of) the
  developer's real database — the exact role the temp ``.db`` file played.
* :func:`connect` — a direct fixture connection to that database exposing
  the sqlite3-style surface the suites were written against:
  ``conn.execute(sql, params)`` with qmark ``?`` placeholders translated to
  psycopg2 ``%s``, rows addressable by column name or position, plus
  ``commit()`` / ``close()``.

Both helpers read the same configuration as the server itself (importing
``server`` loads the project-root ``.env`` into ``os.environ``), so a suite
and the server it spawns can never disagree about which database is under
test.
"""
import os
import sys
import uuid

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import psycopg2  # noqa: E402
import server as _server  # noqa: E402  (loads the project-root .env)


def _settings(dbname=None):
    """psycopg2 connect kwargs mirroring server.get_db_connection()."""
    return dict(
        dbname=dbname or os.environ.get('SENTINEL_DB_NAME', 'sentinel_police'),
        user=os.environ.get('SENTINEL_DB_USER', 'postgres'),
        password=os.environ.get('SENTINEL_DB_PASSWORD', ''),
        host=os.environ.get('SENTINEL_DB_HOST', 'localhost'),
        port=os.environ.get('SENTINEL_DB_PORT', '5432'),
        connection_factory=_server.SentinelPGConnection,
        cursor_factory=_server.SentinelCursor,
        connect_timeout=10,
        application_name='sentinel-test-fixture',
    )


class _QmarkConnection:
    """sqlite3-shaped wrapper: qmark `?` -> `%s`, commit()/close() pass through."""

    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=None):
        return self._conn.execute(sql.replace('?', '%s'), params)

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()


def connect(dbname=None):
    """Open a fixture connection to `dbname` (default: the configured database)."""
    return _QmarkConnection(psycopg2.connect(**_settings(dbname)))


def temp_database(prefix='sentinel_test'):
    """Create a scratch database; return (dbname, env_overrides, drop).

    ``env_overrides`` are the SENTINEL_DB_* values a spawned server needs to
    use the scratch database; ``drop()`` removes it again (FORCE, so leftover
    fixture connections never block cleanup) and is idempotent.
    """
    name = f'{prefix}_{uuid.uuid4().hex[:12]}'
    admin = psycopg2.connect(**_settings('postgres'))
    admin.autocommit = True
    try:
        admin.cursor().execute(f'CREATE DATABASE "{name}"')
    finally:
        admin.close()

    overrides = {
        'SENTINEL_DB_HOST': os.environ.get('SENTINEL_DB_HOST', 'localhost'),
        'SENTINEL_DB_PORT': os.environ.get('SENTINEL_DB_PORT', '5432'),
        'SENTINEL_DB_USER': os.environ.get('SENTINEL_DB_USER', 'postgres'),
        'SENTINEL_DB_PASSWORD': os.environ.get('SENTINEL_DB_PASSWORD', ''),
        'SENTINEL_DB_NAME': name,
    }
    state = {'dropped': False}

    def drop():
        if state['dropped']:
            return
        state['dropped'] = True
        admin = psycopg2.connect(**_settings('postgres'))
        admin.autocommit = True
        try:
            admin.cursor().execute(f'DROP DATABASE IF EXISTS "{name}" WITH (FORCE)')
        finally:
            admin.close()

    return name, overrides, drop

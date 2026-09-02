#!/usr/bin/env python3
"""RBAC migration script for the Sentinel Police Management system.

This script applies the role-based access control (RBAC) schema to an
existing Sentinel SQLite database without re-creating it. It is
idempotent and safe to run multiple times.

What it does:
  1. Adds the ``locations`` table (canonical checkpoint locations).
  2. Adds the ``users.location_scope`` column (already applied by the
     server's own migration, but repeated here so the script can be
     run independently against a freshly-checked-out database).
  3. Seeds the canonical checkpoint locations.
  4. Normalises the legacy ``Administrator``/``Central HQ`` admin user to
     ``SystemAdmin`` (the new canonical role).
  5. Seeds one demo user per non-admin role so the RBAC flow can be
     exercised end-to-end with the credentials documented in the README.

Usage::

    python3 backend/migrate_rbac.py

The database path is taken from the ``SENTINEL_DB`` environment
variable (default: ``backend/sentinel.db``), matching the server.
"""
import hashlib
import os
import sqlite3
import sys

ROOT = os.path.dirname(os.path.abspath(__file__))
PROJECT_ROOT = os.path.dirname(ROOT)
DB_PATH = os.environ.get('SENTINEL_DB', os.path.join(ROOT, 'sentinel.db'))


# ---- role / location reference (kept in sync with server.py) -------------
ROLES = (
    'SystemAdmin',
    'FingerprintUnit',
    'AirportControl',
    'CIDUnit',
    'CheckpointSouth',
    'CheckpointEast',
    'CheckpointWest',
)
ROLE_LOCATION_SCOPE = {
    'CheckpointSouth': 'South',
    'CheckpointEast':  'East',
    'CheckpointWest':  'West',
}
DEFAULT_PASSWORD = 'ChangeMe123!'  # dev seed only — change for any real deploy

DEMO_USERS = (
    # (username, display_name, role, branch, location_scope, password)
    ('admin',       'Officer A. Hassan',  'SystemAdmin',      'Central HQ',         None,  DEFAULT_PASSWORD),
    ('fp.officer',  'Officer H. Xasan',   'FingerprintUnit',  'Fingerprint Unit',   None,  DEFAULT_PASSWORD),
    ('ap.officer',  'Officer S. Cabdi',   'AirportControl',   'Airport Control',    None,  DEFAULT_PASSWORD),
    ('cid.officer', 'Officer M. Nuur',    'CIDUnit',          'CID Unit',           None,  DEFAULT_PASSWORD),
    ('cp.south',    'Officer F. Cali',    'CheckpointSouth',  'Checkpoint South',   'South', DEFAULT_PASSWORD),
    ('cp.east',     'Officer A. Maxamed', 'CheckpointEast',   'Checkpoint East',    'East',  DEFAULT_PASSWORD),
    ('cp.west',     'Officer N. Yuusuf',  'CheckpointWest',   'Checkpoint West',    'West',  DEFAULT_PASSWORD),
)


def password_hash(value):
    return hashlib.sha256(value.encode()).hexdigest()


def has_table(c, name):
    return bool(c.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (name,)).fetchone())


def has_column(c, table, col):
    if not has_table(c, table):
        return False
    for r in c.execute(f'PRAGMA table_info({table})'):
        if r[1] == col:
            return True
    return False


def apply(c, sql, desc, params=()):
    """Run a single SQL statement and log it.

    ``params`` is a tuple of positional bindings (use ``()`` for
    parameter-less statements). The previous version of this helper
    ignored the caller's intent — when an ``INSERT ... VALUES(?,?,?)``
    was passed in, SQLite would raise
    ``Incorrect number of bindings supplied`` because no tuple was
    forwarded to ``cursor.execute``. Pass the bindings explicitly now.
    """
    print(f'  + {desc}')
    c.execute(sql, params)


def main():
    if not os.path.exists(DB_PATH):
        print(f'ERROR: database {DB_PATH!r} does not exist. '
              f'Run the server once (python3 backend/server.py) to create it, '
              f'then re-run this script.')
        return 1

    print(f'Opening database: {DB_PATH}')
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        c = conn.cursor()
        c.execute('PRAGMA foreign_keys=OFF')
        try:
            # 1) locations table ------------------------------------------------
            if not has_table(c, 'locations'):
                apply(c, '''CREATE TABLE locations(
                    id INTEGER PRIMARY KEY,
                    code TEXT UNIQUE NOT NULL,
                    label TEXT NOT NULL,
                    kind TEXT NOT NULL
                )''', 'create locations table')
            for code, label in (('South', 'South Checkpoint'),
                                ('East',  'East Checkpoint'),
                                ('West',  'West Checkpoint')):
                if not c.execute('SELECT 1 FROM locations WHERE code=?', (code,)).fetchone():
                    apply(c, 'INSERT INTO locations(code,label,kind) VALUES(?,?,?)',
                          f'seed location {code}',
                          (code, label, 'Checkpoint'))

            # 2) users.location_scope column -----------------------------------
            if not has_column(c, 'users', 'location_scope'):
                apply(c, 'ALTER TABLE users ADD COLUMN location_scope TEXT',
                      'add users.location_scope')

            # 3) normalise legacy admin role -----------------------------------
            legacy = c.execute(
                "SELECT id, role, location_scope FROM users "
                "WHERE role='Administrator' OR (role='SystemAdmin' AND location_scope IS NULL)"
            ).fetchall()
            for r in legacy:
                if r['role'] == 'Administrator':
                    c.execute('UPDATE users SET role=? WHERE id=?', ('SystemAdmin', r['id']))
                    print(f'  ~ migrated user {r["id"]} role Administrator -> SystemAdmin')
                if r['location_scope'] is None:
                    c.execute('UPDATE users SET location_scope=? WHERE id=?',
                              (ROLE_LOCATION_SCOPE.get('SystemAdmin'), r['id']))

            # 4) ensure each canonical role has at least one demo user ---------
            for username, display_name, role, branch, scope, password in DEMO_USERS:
                row = c.execute('SELECT id FROM users WHERE username=?', (username,)).fetchone()
                if row:
                    # Refresh role/branch/scope to make sure the demo user matches
                    # the canonical RBAC roles even on a stale database.
                    c.execute('UPDATE users SET role=?, branch=?, location_scope=?, '
                              'display_name=?, active=1 WHERE id=?',
                              (role, branch, scope, display_name, row['id']))
                    print(f'  ~ refreshed demo user {username} ({role})')
                else:
                    c.execute('INSERT INTO users(username,display_name,role,branch,'
                              'location_scope,password_hash,active) '
                              'VALUES(?,?,?,?,?,?,1)',
                              (username, display_name, role, branch, scope,
                               password_hash(password)))
                    print(f'  + created demo user {username} ({role})')

            violations = c.execute('PRAGMA foreign_key_check').fetchall()
            if violations:
                raise RuntimeError(
                    f'Foreign key violations after migration: {violations[:3]}')

            conn.commit()
            print()
            print('RBAC migration complete.')
            print()
            print('Demo accounts (development only — change before any real deployment):')
            for username, display_name, role, branch, scope, _ in DEMO_USERS:
                scope_label = scope or branch
                print(f'  - {username:14s} {role:18s} ({scope_label})')
            print('All demo passwords are: ChangeMe123!')
            return 0
        finally:
            c.execute('PRAGMA foreign_keys=ON')
    finally:
        conn.close()


if __name__ == '__main__':
    sys.exit(main())

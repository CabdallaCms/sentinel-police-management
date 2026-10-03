"""Database helpers: connections, and binding the acting user to a transaction.

The database trigger/RLS layer identifies the caller through transaction-local settings:
    app.user_id        the authenticated user  (REQUIRED for any write; fail-closed if absent)
    app.unit_id        the unit the officer is working at (provenance only, grants nothing)
    app.change_reason  why a locked field is being corrected (required for core changes)
"""
import os
import re
from dataclasses import dataclass
from typing import Optional

import psycopg2
import psycopg2.extras


@dataclass(frozen=True)
class Actor:
    user_id: int
    username: str = ''
    unit_id: Optional[int] = None


def connect(dsn: Optional[str] = None):
    dsn = dsn or os.environ.get('SENTINEL_DATABASE_URL')
    if not dsn:
        raise RuntimeError('Set SENTINEL_DATABASE_URL to the PostgreSQL connection string.')
    return psycopg2.connect(dsn)


def cursor(conn):
    return conn.cursor(cursor_factory=psycopg2.extras.RealDictCursor)


_ROLE_RE = re.compile(r'^[A-Za-z_][A-Za-z0-9_]{0,62}$')


def bind_actor(cur, actor: Actor, reason: Optional[str] = None) -> None:
    """Make the acting user visible to triggers / RLS for the CURRENT transaction.

    If SENTINEL_DB_ROLE names a non-owner role (e.g. app_rw) the transaction drops to it, so PostgreSQL
    row-level security applies on top of the service's own checks.  Production should connect AS that
    role; this switch lets a superuser-connected dev/test setup exercise exactly the same policies."""
    role = os.environ.get('SENTINEL_DB_ROLE')
    if role:
        if not _ROLE_RE.match(role):
            raise RuntimeError('SENTINEL_DB_ROLE is not a valid role name')
        cur.execute('SET LOCAL ROLE ' + role)
    cur.execute(
        "SELECT set_config('app.user_id', %s, true), set_config('app.unit_id', %s, true), "
        "set_config('app.change_reason', %s, true)",
        (str(actor.user_id), str(actor.unit_id or ''), reason or ''))


def bind_anonymous(cur) -> None:
    """For the few PUBLIC endpoints: drop to the app role (if configured) with NO user bound.  Only
    SECURITY DEFINER functions that were written for anonymous callers return anything."""
    role = os.environ.get('SENTINEL_DB_ROLE')
    if role:
        if not _ROLE_RE.match(role):
            raise RuntimeError('SENTINEL_DB_ROLE is not a valid role name')
        cur.execute('SET LOCAL ROLE ' + role)

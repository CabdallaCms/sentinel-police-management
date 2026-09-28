#!/usr/bin/env python3
"""Initialise the Sentinel PostgreSQL schema from the command line.

This script delegates to the canonical definitions in ``server.py``:
``SCHEMA`` + ``VEHICLES_SCHEMA`` create any missing table and
``server.migrate()`` applies every in-place column migration, relaxation
and backfill. A database created here is therefore indistinguishable from
one the API server created itself, so the two entry points can be run in
either order — running ``database.py`` first no longer produces a
``persons`` table whose shape predates the canonical schema (the legacy
standalone DDL lacked ``full_name`` / ``national_id`` / ``date_of_birth`` /
``phone`` and crashed ``server.migrate()`` with
``UndefinedColumn: column "full_name" does not exist``).

Usage::

    python3 backend/database.py

Connection settings come from the project-root ``.env`` (loaded by
``server.py`` at import time) or real environment variables:
``SENTINEL_DB_NAME`` / ``SENTINEL_DB_USER`` / ``SENTINEL_DB_PASSWORD`` /
``SENTINEL_DB_HOST`` / ``SENTINEL_DB_PORT``.
"""
import os
import sys

# This script lives in backend/ next to server.py; make the sibling import
# work no matter which directory the user invokes it from.
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def init_postgresql_schema():
    try:
        import server  # noqa: E402  (loads the root .env at import time)

        print("Connecting to your local PostgreSQL Cluster...")
        conn = server.get_db_connection()

        # Canoncial table set (vehicles registry included), then every
        # in-place migration — idempotent, safe on a fresh or a populated
        # database.
        conn.executescript(server.SCHEMA)
        conn.executescript(server.VEHICLES_SCHEMA)
        server.migrate(conn)

        conn.commit()
        conn.close()
        print("SUCCESS: Relational database structures created successfully inside pgAdmin!")

    except Exception as error:
        print(f"\nDATABASE CONNECTION ERROR: {error}")
        print("Please double-check your SENTINEL_DB_PASSWORD inside your .env file.")


if __name__ == '__main__':
    init_postgresql_schema()

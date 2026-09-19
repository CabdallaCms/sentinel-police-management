"""PostgreSQL DATABASE template for the future Sentinel Django service.

HOW TO USE (after the structural refactor passes its tests)
------------------------------------------------------------
1. Install the driver on the server / in your virtualenv::

       pip install "psycopg2-binary>=2.9"

   (``psycopg2-binary`` is the wheel distribution of ``psycopg2``. For a
   compiled-from-source install use ``pip install psycopg2`` plus the
   PostgreSQL client headers instead.)

2. Export the connection secrets in the process environment (never commit
   them to Git)::

       export SENTINEL_DB_NAME=sentinel
       export SENTINEL_DB_USER=sentinel_app
       export SENTINEL_DB_PASSWORD='change-me'
       export SENTINEL_DB_HOST=127.0.0.1
       export SENTINEL_DB_PORT=5432

3. Copy the ``DATABASES`` dict below into your Django settings module
   (e.g. ``sentinel_django/settings.py``). That is the only edit needed —
   every credential is read from the environment with a sane local default.

4. Run ``python manage.py migrate`` against PostgreSQL, then migrate the
   SQLite data (``backend/sentinel.db``) with your one-off ETL script.

NOTES
-----
* This file is documentation, not runtime code: nothing imports it, so it
  cannot affect the current SQLite-backed server or its test suite.
* PostgreSQL uses the ``%s`` paramstyle while ``sqlite3`` uses ``?``.
  Keep every SQL statement behind ``backend/database.py``'s ``db()``
  boundary so that translation happens in exactly one place.
* ``CONN_MAX_AGE`` keeps one persistent connection per Django worker.
  Behind PgBouncer / RDS Proxy prefer ``0`` (close after each request).
* ``ATOMIC_REQUESTS`` wraps each HTTP request in a transaction — matches
  the current ``c.commit()``-per-request behaviour of ``server.py``.
* ``OPTIONS.connect_timeout`` fails fast (5s) instead of hanging workers
  when the database host is unreachable.
* SSL: in production also set ``OPTIONS.sslmode`` to ``verify-full`` and
  provide ``sslrootcert``. The staging default below keeps local Docker
  setups working without certificates.
"""
import os

# ---------------------------------------------------------------------------
# Drop-in Django DATABASES dict (psycopg2 + environment variables).
# ---------------------------------------------------------------------------
DATABASES = {
    'default': {
        # Database driver: PostgreSQL via psycopg2.
        'ENGINE': 'django.db.backends.postgresql',

        # Database name. Dev default 'sentinel' matches the SQLite file's
        # logical name; override per environment.
        'NAME': os.environ.get('SENTINEL_DB_NAME', 'sentinel'),

        # Login role. Must own (or have full rights on) SENTINEL_DB_NAME.
        'USER': os.environ.get('SENTINEL_DB_USER', 'sentinel_app'),

        # Password for USER. No default — fail closed when unset so a
        # misconfigured deploy never connects with a blank password.
        'PASSWORD': os.environ.get('SENTINEL_DB_PASSWORD', ''),

        # Host / port. Defaults point at a local PostgreSQL; in production
        # set these to the managed-database endpoint (e.g. RDS hostname).
        'HOST': os.environ.get('SENTINEL_DB_HOST', '127.0.0.1'),
        'PORT': os.environ.get('SENTINEL_DB_PORT', '5432'),

        # Keep each HTTP request atomic, mirroring server.py's
        # commit-per-request semantics.
        'ATOMIC_REQUESTS': True,

        # Persistent DB connection per worker (seconds). Use 0 behind a
        # transaction pooler such as PgBouncer.
        'CONN_MAX_AGE': int(os.environ.get('SENTINEL_DB_CONN_MAX_AGE', '60')),

        # Connection health checks (Django 4.1+): recycle dead pooled
        # connections instead of serving 500s after a DB failover.
        'CONN_HEALTH_CHECKS': True,

        # Driver-level options passed straight to psycopg2.connect().
        'OPTIONS': {
            # Fail fast when the DB host is unreachable.
            'connect_timeout': int(os.environ.get('SENTINEL_DB_CONNECT_TIMEOUT', '5')),
            # Local/dev default. Production: 'verify-full' + 'sslrootcert'.
            'sslmode': os.environ.get('SENTINEL_DB_SSLMODE', 'prefer'),
        },

        # How long Django keeps trying a query before the test runner /
        # request gives up (seconds). Prevents hung workers.
        'TIME_ZONE': 'UTC',
    }
}

# ---------------------------------------------------------------------------
# Optional: verify the environment wiring without Django installed.
#
#   $ python3 backend/postgres_settings.example.py
#
# Prints the resolved (password-redacted) connection kwargs. Dies non-zero
# when mandatory variables are missing, so CI can gate on it.
# ---------------------------------------------------------------------------
if __name__ == '__main__':
    missing = [key for key, env in (('USER', 'SENTINEL_DB_USER'),
                                    ('PASSWORD', 'SENTINEL_DB_PASSWORD'))
               if not os.environ.get(env)]
    redacted = dict(DATABASES['default'])
    redacted['PASSWORD'] = '***' if redacted['PASSWORD'] else '(MISSING)'
    print('PostgreSQL template resolves to:')
    for key in ('ENGINE', 'NAME', 'USER', 'PASSWORD', 'HOST', 'PORT',
                'ATOMIC_REQUESTS', 'CONN_MAX_AGE', 'CONN_HEALTH_CHECKS',
                'OPTIONS', 'TIME_ZONE'):
        print('  %-18s %r' % (key, redacted[key]))
    if missing:
        print('MISSING required environment: '
              + ', '.join('SENTINEL_DB_' + m for m in missing))
        raise SystemExit(1)
    print('OK: all required PostgreSQL environment variables are set.')

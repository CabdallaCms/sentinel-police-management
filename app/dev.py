"""One-command DEVELOPMENT demo: embedded PostgreSQL + migrations + demo accounts + fictional demo people
+ the API/UI with dev authentication.   Run:  python -m app.dev [--port 8080]

NOT for production: it enables SENTINEL_DEV_AUTH (the caller is whoever the X-Dev-User header says).
"""
import argparse
import logging
import os

from tests import pg_support            # reuse the scratch-database builder (dev tooling only)


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--host', default='0.0.0.0')
    ap.add_argument('--port', type=int, default=int(os.environ.get('PORT', 8080)))
    args = ap.parse_args()
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    os.environ['SENTINEL_DATABASE_URL'] = pg_support.create_database('sentinel_dev', demo_people=True)
    os.environ['SENTINEL_DEV_AUTH'] = '1'
    os.environ.setdefault('SENTINEL_DB_ROLE', 'app_rw')       # drop to a non-owner role so row-level security applies
    from app import server
    server.main(['--host', args.host, '--port', str(args.port)])


if __name__ == '__main__':
    main()

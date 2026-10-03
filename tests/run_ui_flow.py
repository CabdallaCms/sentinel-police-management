"""Boot a scratch database (with the fictional demo people) + the real HTTP server, then drive the
real web page with jsdom.   Run:  python -m tests.run_ui_flow

Needs Node 18+ and jsdom:  (cd tests/ui && npm install)   or set JSDOM_DIR to a node_modules path.
"""
import os
import subprocess
import sys
import threading

from . import pg_support

HERE = os.path.dirname(os.path.abspath(__file__))


SCENARIOS = ['ui_flow.test.mjs', 'ops_flow.test.mjs', 'dir_flow.test.mjs']     # intake, operations, directorate pages


def main():
    import shutil
    import tempfile
    uri = pg_support.create_database('sentinel_ui_flow', demo_people=True)
    os.environ['SENTINEL_DATABASE_URL'] = uri
    os.environ['SENTINEL_DEV_AUTH'] = '1'
    os.environ['SENTINEL_DB_ROLE'] = 'app_rw'                  # row-level security ON, as in production
    uploads_dir = tempfile.mkdtemp(prefix='sentinel_uploads_')
    os.environ['SENTINEL_UPLOAD_DIR'] = uploads_dir
    from app import server
    srv = server.make_server('127.0.0.1', 0)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f'http://127.0.0.1:{srv.server_address[1]}'
    env = dict(os.environ, BASE_URL=base)
    env.setdefault('JSDOM_DIR', os.path.join(HERE, 'ui', 'node_modules'))
    try:
        for scenario in SCENARIOS:
            code = subprocess.call(['node', os.path.join(HERE, 'ui', scenario)], env=env)
            if code:
                return code
        return 0
    finally:
        srv.shutdown()
        shutil.rmtree(uploads_dir, ignore_errors=True)


if __name__ == '__main__':
    sys.exit(main())

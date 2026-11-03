#!/usr/bin/env python3
"""Build-stamp sync guard: index.html <-> backend/server.py.

This suite exists because the two halves of a release are versioned separately:

  * `index.html` carries the asset stamp (`<meta name="sentinel-ui-build">` ==
    `UI_BUILD`) and the BACKEND contract tag (`REQUIRED_BUILD_TAG` ==
    `BUILD_TAG`) the review lock is enforced against, and
  * `backend/server.py` carries `UI_BUILD`, `BUILD_TAG` and `ASSET_VERSION`.

Updating one file without the other is what produces
`Sentinel: the index.html on disk is not the build this server serves.` (a
stale page) or a silently disabled Approve button (a stale backend tag). The
suite pins the healthy tree and then reproduces BOTH drift directions with
temporary copies, so the diagnosis can never regress into a silent failure.

Usage: python3 backend/test_ui_build_sync.py   (no database required)
"""
import importlib.util
import os
import re
import socket
import subprocess
import sys
import tempfile

BACKEND = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(BACKEND)
SERVER = os.path.join(BACKEND, 'server.py')
INDEX = os.path.join(ROOT, 'index.html')
# The UI build of the release this suite was written against. It is only used
# to build a stale fixture; it is never compared with the current constants.
PREVIOUS_UI_BUILD = 'sentinel-sidebar-header-1-4d8b7e21'
PREVIOUS_BACKEND_TAG = 'sentinel-crime-department-scope'

META_RE = re.compile(r'<meta\s+name="sentinel-ui-build"\s+content="([^"]+)"')
TAG_RE = re.compile(r"REQUIRED_BUILD_TAG\s*=\s*'([^']+)'")
TAG_DECL_RE = re.compile(r"(const\s+REQUIRED_BUILD_TAG\s*=\s*')[^']+('?)")


def check(condition, message):
    if not condition:
        raise AssertionError(message)
    print('ok:', message)


def load_server():
    """Import backend/server.py without starting it (module level is inert)."""
    sys.path.insert(0, BACKEND)
    spec = importlib.util.spec_from_file_location('sentinel_server_build_sync', SERVER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def free_port():
    sock = socket.socket()
    try:
        sock.bind(('127.0.0.1', 0))
        return sock.getsockname()[1]
    finally:
        sock.close()


def write_copy(prefix, html):
    directory = tempfile.mkdtemp(prefix=prefix)
    path = os.path.join(directory, 'index.html')
    with open(path, 'w', encoding='utf-8') as handle:
        handle.write(html)
    return directory, path


def run_ui_check(directory):
    return subprocess.run([sys.executable, SERVER, '--ui-check'], cwd=directory,
                          capture_output=True, text=True, timeout=120)


def run_server(directory):
    return subprocess.run([sys.executable, SERVER], cwd=directory,
                          env=dict(os.environ, SENTINEL_UI_DIR=directory,
                                   PORT=str(free_port())),
                          capture_output=True, text=True, timeout=120)


def main():
    srv = load_server()
    with open(INDEX, encoding='utf-8') as handle:
        html = handle.read()

    print('== 1. the shipped tree is internally consistent ==')
    meta = META_RE.search(html)
    tag = TAG_RE.search(html)
    check(bool(meta), 'index.html publishes <meta name="sentinel-ui-build">')
    check(bool(tag), 'index.html publishes REQUIRED_BUILD_TAG')
    check(meta.group(1) == srv.UI_BUILD,
          f'index.html stamp matches server UI_BUILD ({meta.group(1)})')
    check(tag.group(1) == srv.BUILD_TAG,
          f'index.html REQUIRED_BUILD_TAG matches server BUILD_TAG ({tag.group(1)})')
    check(srv.UI_BUILD.endswith('-' + srv.ASSET_VERSION),
          f'UI_BUILD carries ASSET_VERSION ({srv.UI_BUILD})')
    for name in ('index.html', 'application.html', 'certificate.html'):
        with open(os.path.join(ROOT, name), encoding='utf-8') as handle:
            versions = set(re.findall(r'\?v=([A-Za-z0-9._-]+)', handle.read()))
        check(versions == {srv.ASSET_VERSION},
              f'{name} carries only ?v={srv.ASSET_VERSION} ({sorted(versions)})')

    state = srv.ui_state()
    check(state['stamp'] == srv.UI_BUILD, 'the resolved page reports the served UI build')
    check(state['page_build_tag'] == srv.BUILD_TAG,
          'the resolved page reports the served backend tag')
    missing = [label for label, present in state['features'].items() if not present]
    check(not missing, f'every UI_REQUIRED_MARKER is present ({len(state["features"])} markers)')
    check(srv.ui_self_test() == [],
          f'ui_self_test() is clean for the shipped page ({srv.ui_self_test()})')

    print('== 2. a stale page is refused with an actionable diagnosis ==')
    stale_dir, stale_path = write_copy(
        'sentinel-stamp-stale-', html.replace(meta.group(1), PREVIOUS_UI_BUILD, 1))
    stale_problems = srv.ui_self_test(stale_path)
    check(any(PREVIOUS_UI_BUILD in problem and srv.UI_BUILD in problem
              for problem in stale_problems),
          'the refusal names both the page stamp and the served build')
    stale_check = run_ui_check(stale_dir)
    check(stale_check.returncode == 1,
          f'--ui-check exits 1 for a page from another build ({stale_check.returncode})')
    check('WOULD REFUSE TO START' in stale_check.stdout
          and PREVIOUS_UI_BUILD in stale_check.stdout,
          'the CLI shows the stale stamp instead of a generic failure')
    stale_boot = run_server(stale_dir)
    # Startup refuses with the FATAL the operator reported (GET / would answer
    # 503 with the same diagnosis once a matching process were running).
    check(stale_boot.returncode != 0
          and 'FATAL' in stale_boot.stderr
          and 'refusing to start' in stale_boot.stderr
          and PREVIOUS_UI_BUILD in stale_boot.stderr,
          'the server refuses to start on a page from another build (the reported symptom)')
    check(f'serving  : {stale_path}' in stale_boot.stderr,
          'the refusal names the exact index.html it resolved')

    print('== 3. backend-tag drift is refused in the other direction ==')
    drift_html, count = TAG_DECL_RE.subn(r"\g<1>%s\g<2>" % PREVIOUS_BACKEND_TAG, html, count=1)
    check(count == 1, 'the REQUIRED_BUILD_TAG declaration is rewritten for the drift fixture')
    drift_dir, drift_path = write_copy('sentinel-stamp-drift-', drift_html)
    drift_problems = srv.ui_self_test(drift_path)
    check(any('expects backend build' in problem for problem in drift_problems),
          'a page expecting another backend build is reported explicitly')
    drift_check = run_ui_check(drift_dir)
    check(drift_check.returncode == 1,
          f'--ui-check exits 1 when the backend tag drifts ({drift_check.returncode})')
    check(f'page expects {PREVIOUS_BACKEND_TAG!r}' in drift_check.stdout,
          'the CLI prints the expected backend tag')

    print('== 4. the shipped checkout passes its own gate ==')
    ok = run_ui_check(ROOT)
    check(ok.returncode == 0, f'--ui-check exits 0 in the project root ({ok.returncode})')
    check(f'build    : {srv.UI_BUILD}' in ok.stdout
          and f'backend  : {srv.BUILD_TAG}' in ok.stdout
          and 'Actions column: yes' in ok.stdout,
          'the CLI prints the asset build, backend tag and Actions column state')

    print('ALL UI BUILD-STAMP SYNC TESTS PASSED')


if __name__ == '__main__':
    main()

#!/usr/bin/env bash
# Boot a self-contained UAT stack for manual testing / preview:
# a throwaway PostgreSQL cluster (pgserver) + Sentinel backend/server.py.
#
#   bash scripts/uat-stack.sh              # port 8001, cluster in /tmp/sentinel-uat
#   PORT=8010 bash scripts/uat-stack.sh
#   UAT_DIR=/tmp/my-uat bash scripts/uat-stack.sh
#
# Nothing here touches operational data: the cluster lives in UAT_DIR/pgdata
# and is created from scratch by the bundled PostgreSQL engine, then the
# server is pointed at it over its unix socket. Delete UAT_DIR for a clean
# database. The script stays in the foreground (KEEP_ALIVE=1 by default) so it
# can be run as a long-lived process (pick it up as a live preview when the
# backend binds 0.0.0.0).
#
# Requires: pgserver + psycopg2 in the interpreter (a .venv in the repo root is
# used automatically when present). See TESTING.md.

set -u
PORT="${PORT:-8001}"
UAT_DIR="${UAT_DIR:-/tmp/sentinel-uat}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PYTHON="${PYTHON:-}"
if [ -z "$PYTHON" ]; then
  if [ -x "$REPO_ROOT/.venv/bin/python" ]; then PYTHON="$REPO_ROOT/.venv/bin/python"; else PYTHON="python3"; fi
fi

"$PYTHON" -c 'import pgserver, psycopg2' 2>/dev/null || {
  echo "FAILED: $PYTHON cannot import pgserver/psycopg2." >&2
  echo "        python3 -m venv .venv && .venv/bin/pip install psycopg2-binary pgserver" >&2
  exit 1
}

mkdir -p "$UAT_DIR"
PG_HELPER="$UAT_DIR/pgserve.py"
cat > "$PG_HELPER" <<'PY'
# Throwaway PostgreSQL for UAT: prints its unix-socket directory, then stays
# alive until the parent kills it (a helper that returns exits the cluster).
import pathlib, sys, time, pgserver
d = pathlib.Path(sys.argv[1]); d.mkdir(parents=True, exist_ok=True)
pgserver.get_server(str(d))
# Marker prefix so the parent can pick the socket directory out of a log that
# also carries interpreter warnings (platformdirs, etc.).
print('SOCKET=' + str(d), flush=True)
while True:
    time.sleep(60)
PY

echo "== 1. start the throwaway PostgreSQL cluster ($UAT_DIR/pgdata) =="
"$PYTHON" -u "$PG_HELPER" "$UAT_DIR/pgdata" > "$UAT_DIR/pg.log" 2>&1 &
PG_PID=$!
trap 'kill "$PG_PID" 2>/dev/null; exit 0' INT TERM

SOCKET_DIR=""
for _ in $(seq 1 120); do
  sleep 0.5
  SOCKET_DIR=$(sed -n 's/^SOCKET=//p' "$UAT_DIR/pg.log" 2>/dev/null | tail -1)
  [ -n "$SOCKET_DIR" ] && break
  kill -0 "$PG_PID" 2>/dev/null || { echo "FAILED: the PostgreSQL cluster died; see $UAT_DIR/pg.log" >&2; tail -20 "$UAT_DIR/pg.log" >&2; exit 1; }
done
[ -n "$SOCKET_DIR" ] || { echo "FAILED: the PostgreSQL cluster never reported a socket directory." >&2; exit 1; }
echo "  cluster socket directory: $SOCKET_DIR (pid $PG_PID)"

echo -e "\n== 2. start backend/server.py on 0.0.0.0:$PORT =="
cd "$REPO_ROOT"
SENTINEL_DB_HOST="$SOCKET_DIR" SENTINEL_DB_NAME=postgres SENTINEL_DB_USER=postgres \
SENTINEL_DB_PASSWORD= PORT="$PORT" exec "$PYTHON" -u backend/server.py

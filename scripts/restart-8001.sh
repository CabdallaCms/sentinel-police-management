#!/usr/bin/env bash
# Restart the Sentinel backend on the given port and PROVE it is the
# review-lock build.
#
#   bash scripts/restart-8001.sh            # port 8001
#   PORT=8005 bash scripts/restart-8001.sh
#   bash scripts/restart-8001.sh --no-start # kill + verify only
#
# 1. Force-kills every process listening on the port (the usual reason an old
#    build keeps answering: the new server dies with "Address already in use").
# 2. Starts backend/server.py.
# 3. Polls /api/health until it reports
#       "build": "sentinel-fingerprint-review-lock-12h"
#       "review_lock_active": true
#    and fails loudly (exit 1) if it never does.

set -u
PORT="${PORT:-8001}"
REQUIRED_BUILD='sentinel-fingerprint-review-lock-12h'
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SERVER="$REPO_ROOT/backend/server.py"
NO_START=0
for arg in "$@"; do [ "$arg" = "--no-start" ] && NO_START=1; done

kill_port() {
  local pids=""
  command -v lsof >/dev/null 2>&1 && pids=$(lsof -ti "tcp:$PORT" 2>/dev/null)
  if [ -z "$pids" ] && command -v fuser >/dev/null 2>&1; then
    pids=$(fuser -n tcp "$PORT" 2>/dev/null | tr -d ' ')
  fi
  if [ -z "$pids" ] && command -v ss >/dev/null 2>&1; then
    pids=$(ss -ltnp 2>/dev/null | awk -v p=":$PORT" '$4 ~ p {n=split($0,a,"pid="); if(n>1){split(a[2],b,","); print b[1]}}' | sort -u)
  fi
  [ -z "$pids" ] && { echo "  nothing was listening on port $PORT"; return 0; }
  for pid in $pids; do
    [ "$pid" = "$$" ] && continue
    echo "  killing pid $pid on port $PORT"
    kill -9 "$pid" 2>/dev/null
  done
}

echo "== 1. kill anything listening on port $PORT =="
kill_port
sleep 1

if [ "$NO_START" = "1" ]; then echo -e "\n--no-start given: not starting a server."; exit 0; fi

echo -e "\n== 2. start backend/server.py =="
LOG="${TMPDIR:-/tmp}/sentinel-$PORT.log"
# Detach fully (setsid + nohup + /dev/null stdin) so the server survives the
# shell that started it and never holds this script's output pipe open.
if command -v setsid >/dev/null 2>&1; then
  ( cd "$REPO_ROOT" && setsid nohup python3 -u "$SERVER" >"$LOG" 2>&1 </dev/null & )
else
  ( cd "$REPO_ROOT" && nohup python3 -u "$SERVER" >"$LOG" 2>&1 </dev/null & )
fi
echo "  log: $LOG"

echo -e "\n== 3. verify /api/health on port $PORT =="
OK=0
for _ in $(seq 1 40); do
  sleep 0.5
  HEALTH=$(curl -s --max-time 3 "http://127.0.0.1:$PORT/api/health" 2>/dev/null || true)
  [ -z "$HEALTH" ] && continue
  BUILD=$(python3 -c "import sys,json;d=json.load(sys.stdin);print(d.get('build',''))" <<<"$HEALTH" 2>/dev/null || echo "")
  ACTIVE=$(python3 -c "import sys,json;d=json.load(sys.stdin);print(str(d.get('review_lock_active',False)).lower())" <<<"$HEALTH" 2>/dev/null || echo "false")
  if [ "$BUILD" = "$REQUIRED_BUILD" ] && [ "$ACTIVE" = "true" ]; then
    echo "$HEALTH" | python3 -m json.tool
    echo -e "\nOK - the review lock build is live on port $PORT."
    OK=1
  else
    echo "  STALE BUILD on port $PORT: build='$BUILD' (expected '$REQUIRED_BUILD')"
    echo "  Kill that process and re-run this script."
  fi
  break
done
[ "$OK" = "1" ] || { echo -e "\nFAILED"; tail -20 "$LOG" 2>/dev/null; exit 1; }

echo -e "\n== 4. audit approvals made while a stale server was up =="
python3 "$REPO_ROOT/backend/audit_instant_approvals.py" || \
  echo -e "\nRe-run with --revert to put those applications back to Pending Review:\n  python3 backend/audit_instant_approvals.py --revert"

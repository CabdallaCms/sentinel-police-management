#!/usr/bin/env bash
# Prove which UI a live Sentinel server is actually serving.
#
#   bash scripts/verify-live-ui.sh                      # http://127.0.0.1:8001
#   bash scripts/verify-live-ui.sh https://8001-xxx.e2b.app
#
# Checks, over the network, exactly what a browser receives:
#   1. GET /api/health  -> ui_build, ui_sha256, ui_actions_published, ui_path, pid
#   2. GET /            -> the sentinel-ui-build stamp, the Actions column
#                          marker, the View/Edit entry points, a ?v= reference
#   3. the cache headers on the document
#   4. the live index.html sha256 vs the sha256 of the checkout this script
#      runs from (the decisive test: equal => the deployment is this tree)
#
# Exit 0 = the server is serving the current page. Exit 1 = it is not, and the
# output says which identity differs (a stale deployment, a stale template, or
# a proxy serving another host entirely).
set -u

BASE="${1:-http://127.0.0.1:8001}"
BASE="${BASE%/}"
REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
INDEX="$REPO_ROOT/index.html"
fail=0

say() { printf '%s\n' "$*"; }
ok()  { printf '  PASS %s\n' "$*"; }
bad() { printf '  FAIL %s\n' "$*"; fail=1; }

[ -f "$INDEX" ] || { say "FAILED: no index.html at $INDEX"; exit 1; }

LOCAL_STAMP=$(sed -n 's/.*<meta name="sentinel-ui-build" content="\([^"]*\)".*/\1/p' "$INDEX" | head -1)
LOCAL_SHA=$(sha256sum "$INDEX" | awk '{print $1}')
LOCAL_ACTIONS=$(grep -c 'data-station-action="view"' "$INDEX")

say "== checkout =="
say "  index.html : $INDEX"
say "  stamp      : ${LOCAL_STAMP:-<none>}"
say "  sha256     : $LOCAL_SHA"
say "  Actions    : $LOCAL_ACTIONS marker(s)"
say

say "== live server: $BASE =="
HEALTH=$(curl -sS --max-time 15 "$BASE/api/health" 2>/dev/null) || {
  bad "cannot reach $BASE/api/health — nothing is serving that address"
  HEALTH=""
}
PY=""
for cand in "$REPO_ROOT/.venv/bin/python" python3; do
  command -v "$cand" >/dev/null 2>&1 && PY="$cand" && break
done
jget() { [ -n "$HEALTH" ] || return 0; printf '%s' "$HEALTH" | "$PY" -c '
import sys, json
try:
    d = json.load(sys.stdin)
except Exception:
    sys.exit(0)
for k in sys.argv[1:]:
    v = d.get(k)
    print("" if v is None else (json.dumps(v) if isinstance(v, (list, dict)) else str(v)))
' "$@"; }

LIVE_BUILD=$(jget ui_build)
LIVE_SHA=$(jget ui_sha256)
LIVE_ACTIONS=$(jget ui_actions_published)
LIVE_PATH=$(jget ui_path)
LIVE_PID=$(jget pid)
LIVE_OK=$(jget ui_ok)
say "  pid        : ${LIVE_PID:-?}"
say "  ui_build   : ${LIVE_BUILD:-<missing>}"
say "  ui_sha256  : ${LIVE_SHA:-<missing>}"
say "  ui_path    : ${LIVE_PATH:-<missing>}"
say "  Actions    : ${LIVE_ACTIONS:-<missing>}"
say

if [ -z "$HEALTH" ]; then
  :
elif [ "$LIVE_OK" != "True" ] && [ "$LIVE_OK" != "true" ]; then
  bad "the server reports ui_ok=${LIVE_OK:-<missing>} — it knows it is serving a stale page"
elif [ -n "$LOCAL_STAMP" ] && [ "$LIVE_BUILD" != "$LOCAL_STAMP" ]; then
  bad "stamp mismatch: live=$LIVE_BUILD checkout=$LOCAL_STAMP"
  say "       => the running process serves a DIFFERENT index.html (an older deployment)."
elif [ "$LIVE_ACTIONS" != "True" ] && [ "$LIVE_ACTIONS" != "true" ]; then
  bad "the live server says the Actions column is NOT published"
elif [ -n "$LOCAL_SHA" ] && [ -n "$LIVE_SHA" ] && [ "$LIVE_SHA" != "$LOCAL_SHA" ]; then
  bad "sha256 mismatch: live=${LIVE_SHA:0:12}… checkout=${LOCAL_SHA:0:12}…"
  say "       => same build label, different bytes: the deployment was not rebuilt from this checkout."
else
  ok "the server's served index.html is byte-identical to this checkout"
fi

say
say "== GET / (what a browser receives) =="
HTML=$(curl -sS --max-time 20 "$BASE/" 2>/dev/null) || HTML=""
if [ -z "$HTML" ]; then
  bad "GET / returned no body"
else
  echo "$HTML" | grep -q "content=\"$LOCAL_STAMP\"" \
    && ok "the document carries the current stamp ($LOCAL_STAMP)" \
    || bad "the document does not carry the current stamp ($LOCAL_STAMP)"
  echo "$HTML" | grep -q 'data-station-action="view"' \
    && ok "the Actions column markup is present" \
    || bad "the Actions column markup is MISSING from the served page"
  echo "$HTML" | grep -q 'function openStationView(' \
    && ok "the View drawer entry point is present" \
    || bad "the View drawer is MISSING from the served page"
  echo "$HTML" | grep -q 'function openStationEdit(' \
    && ok "the Edit modal entry point is present" \
    || bad "the Edit modal is MISSING from the served page"
  echo "$HTML" | grep -q '?v=0f8552e' \
    && ok "static references carry ?v=0f8552e" \
    || bad "static references are not version-stamped"
fi

say
say "== cache headers on / =="
curl -sSI --max-time 15 "$BASE/" 2>/dev/null | sed -n '1p;/^[Cc]ache-[Cc]ontrol:/p;/^[Pp]ragma:/p;/^[Ee]xpires:/p' | sed 's/^/  /'

say
if [ "$fail" = "0" ]; then
  say "OK — the live server is serving this checkout ($LOCAL_STAMP, sha256 ${LOCAL_SHA:0:12}…)."
  exit 0
fi
say "FAILED — the live server is NOT serving this checkout."
say "If this is a preview URL, the preview is attached to a different (older) process."
say "Restart the stack from this checkout:  bash scripts/uat-stack.sh"
exit 1

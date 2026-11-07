#!/usr/bin/env bash
# Sentinel CID — reproducible test runner (WP-01).
#
# Runs every Python and Node test suite in backend/ and prints a single
# PASS/FAIL/ERROR line per suite plus a summary.
#
# Prerequisites (see TESTING.md):
#   python3 -m venv .venv && .venv/bin/pip install -r requirements-dev.txt
#   npm install
#
# Usage:
#   scripts/run-tests.sh            # everything
#   scripts/run-tests.sh py         # Python suites only
#   scripts/run-tests.sh node       # Node suites only
#   scripts/run-tests.sh <pattern>  # suites whose filename contains <pattern>
#
# Exit code 0 only when every selected suite passes.

set -uo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

PY="${SENTINEL_PY:-$ROOT/.venv/bin/python}"
[ -x "$PY" ] || PY="$(command -v python3)"
TIMEOUT="${SENTINEL_TEST_TIMEOUT:-600}"
export SENTINEL_PYTHON="$PY"   # Node harnesses spawn the backend with this

# WP-02 / SR-02: the product no longer ships a default password. The suite
# supplies a known throwaway one EXPLICITLY, which is also what proves the
# seeding path is driven by the environment and not by a constant in the
# source. Without this the server generates a random password per account and
# every login in the suite correctly fails with 401.
export SENTINEL_BOOTSTRAP_PASSWORD="${SENTINEL_BOOTSTRAP_PASSWORD:-ChangeMe123!}"

# Suites known to fail for a reason OUTSIDE the current authorised scope.
# They are reported as BLOCKED, never as passing, and still count as failures
# for the exit code unless SENTINEL_ALLOW_BLOCKED=1.
declare -A BLOCKED_REASON=(
  [test_server.py]="finding N-7 — update_discipline() builds a malformed SQL placeholder list (server.py: \",\".join('%s' * n)); fixing it is outside Stage 0 scope"
)
SELECT="${1:-all}"

LOGDIR="${SENTINEL_TEST_LOGDIR:-$ROOT/.test-logs}"
mkdir -p "$LOGDIR"

pass=0; fail=0; skip=0; blocked=0
declare -a FAILED=()
declare -a BLOCKEDL=()

run_one() {
  local f="$1" cmd="$2" name
  name="$(basename "$f")"
  local log="$LOGDIR/${name}.log"
  local start end rc
  start=$(date +%s)
  # shellcheck disable=SC2086
  timeout "$TIMEOUT" $cmd >"$log" 2>&1
  rc=$?
  end=$(date +%s)
  if [ $rc -eq 0 ]; then
    printf 'PASS   %-42s %3ss\n' "$name" "$((end-start))"; pass=$((pass+1))
  elif [ $rc -eq 124 ]; then
    printf 'TIMEOUT %-41s %3ss  (%s)\n' "$name" "$((end-start))" "$log"; fail=$((fail+1)); FAILED+=("$name (timeout)")
  elif [ -n "${BLOCKED_REASON[$name]:-}" ]; then
    printf 'BLOCKED %-41s %3ss  rc=%s\n' "$name" "$((end-start))" "$rc"
    printf '         reason: %s\n' "${BLOCKED_REASON[$name]}"
    blocked=$((blocked+1)); BLOCKEDL+=("$name")
  else
    printf 'FAIL   %-42s %3ss  rc=%s  (%s)\n' "$name" "$((end-start))" "$rc" "$log"; fail=$((fail+1)); FAILED+=("$name (rc=$rc)")
  fi
}

want() {
  case "$SELECT" in
    all) return 0 ;;
    py)   [[ "$1" == *.py  ]] && return 0 || return 1 ;;
    node) [[ "$1" == *.mjs ]] && return 0 || return 1 ;;
    *)    [[ "$1" == *"$SELECT"* ]] && return 0 || return 1 ;;
  esac
}

echo "Sentinel test runner"
echo "  python : $($PY -V 2>&1)"
echo "  node   : $(node -v 2>/dev/null || echo 'not installed')"
echo "  select : $SELECT"
echo "  logs   : $LOGDIR"
echo

echo "--- Python suites ---"
for f in backend/test_*.py; do
  [ -e "$f" ] || continue
  want "$f" || continue
  run_one "$f" "$PY $f"
done

echo
echo "--- Node suites ---"
if [ -d node_modules/jsdom ]; then
  for f in backend/test_*.mjs; do
    [ -e "$f" ] || continue
    want "$f" || continue
    run_one "$f" "node $f"
  done
else
  for f in backend/test_*.mjs; do
    [ -e "$f" ] || continue
    want "$f" || continue
    printf 'SKIP   %-42s      node_modules/jsdom missing — run: npm install\n' "$(basename "$f")"
    skip=$((skip+1))
  done
fi

echo
echo "================ SUMMARY ================"
printf 'passed : %d\nfailed : %d\nblocked: %d\nskipped: %d\n' "$pass" "$fail" "$blocked" "$skip"
if [ ${#FAILED[@]} -gt 0 ]; then
  echo "failing suites:"
  for n in "${FAILED[@]}"; do echo "  - $n"; done
fi
if [ ${#BLOCKEDL[@]} -gt 0 ]; then
  echo "blocked suites (known, out-of-scope cause — NOT passing):"
  for n in "${BLOCKEDL[@]}"; do echo "  - $n: ${BLOCKED_REASON[$n]}"; done
fi
echo "========================================="
if [ "${SENTINEL_ALLOW_BLOCKED:-0}" = "1" ]; then
  [ "$fail" -eq 0 ] && [ "$skip" -eq 0 ]
else
  [ "$fail" -eq 0 ] && [ "$skip" -eq 0 ] && [ "$blocked" -eq 0 ]
fi

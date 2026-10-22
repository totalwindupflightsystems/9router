#!/usr/bin/env bash
# SCHED-GAP-1756 regression tests — drain-restart credential resolution.
#
# Proves the four properties the incident requires, against a fake daemon (no live
# fleet touched, no restart, no scheduling state):
#   1. rung 1 (X-Operator-Token) accepted  -> ONE credential used for pause AND resume
#   2. rung 1 refused, rung 2 (Bearer) ok  -> falls back and still resolves one credential
#   3. both refused                        -> fails loudly, changes NOTHING server-side
#   4. daemon unreachable                  -> fails loudly with 000
#   5. resume answering 401                -> reported as FAILURE (never success)
#
# Run: bash ~/.hermes/scripts/tests/test-drain-restart-credentials.sh
set -uo pipefail

HERE=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
SCRIPT=${SCRIPT:-$HERE/../deploy-scheduler-drain-restart.sh}
FAKE=$HERE/fake_scheduler.py
TMP=$(mktemp -d "${TMPDIR:-/tmp}/sgap1756-test.XXXXXX") || exit 1
PASS=0
FAIL=0
st_paused=""
st_calls=""
SRV_PIDS=""

cleanup() {
  for p in $SRV_PIDS; do kill "$p" 2>/dev/null; done
  rm -rf "$TMP"
}
trap cleanup EXIT

[ -f "$SCRIPT" ] || { echo "FATAL: script not found at $SCRIPT"; exit 1; }
[ -f "$FAKE" ] || { echo "FATAL: fake daemon not found at $FAKE"; exit 1; }
command -v jq >/dev/null || { echo "FATAL: jq is required"; exit 1; }

ok()  { PASS=$((PASS + 1)); echo "  PASS  $*"; }
bad() { FAIL=$((FAIL + 1)); echo "  FAIL  $*"; }
check() {  # $1=description $2=actual $3=expected
  if [ "$2" = "$3" ]; then ok "$1 = $2"; else bad "$1 (got '$2', want '$3')"; fi
}

# --- fixtures -------------------------------------------------------------
GOOD_OP=aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
BAD_OP=bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb
GOOD_KEY=good-gateway-key
BAD_KEY=bad-gateway-key

printf 'SCHEDULER_OPERATOR_TOKEN=%s\n' "$GOOD_OP" > "$TMP/auth-good.env"
printf 'SCHEDULER_OPERATOR_TOKEN=%s\n' "$BAD_OP"  > "$TMP/auth-bad.env"
printf 'API_SERVER_KEY=%s\n' "$GOOD_KEY" > "$TMP/env-good.env"
printf 'API_SERVER_KEY=%s\n' "$BAD_KEY"  > "$TMP/env-bad.env"

start_server() {  # $1 = FAKE_MODE -> sets PORT
  FAKE_MODE=$1 FAKE_OPERATOR_TOKEN=$GOOD_OP FAKE_KEY=$GOOD_KEY \
    python3 "$FAKE" > "$TMP/server.$1.out" 2> "$TMP/server.$1.err" &
  local pid=$!
  SRV_PIDS="$SRV_PIDS $pid"
  local i
  for i in $(seq 1 80); do
    PORT=$(sed -n 's/^PORT=//p' "$TMP/server.$1.out" 2>/dev/null | head -1)
    [ -n "${PORT:-}" ] && return 0
    sleep 0.1
  done
  echo "  !! fake daemon ($1) failed to start: $(cat "$TMP/server.$1.err" 2>/dev/null)"
  return 1
}

# Source the script under test in a subshell with the case's endpoints/credentials,
# then drive the credential ladder directly. main() does not run when sourced.
run_case() {  # $1=label $2=port $3=auth_env $4=env_file
  local label=$1 port=$2 auth=$3 envf=$4
  (
    export SCHEDULER_API="http://127.0.0.1:$port"
    export SCHEDULER_AUTH_ENV="$auth"
    export SCHEDULER_ENV_FILE="$envf"
    # shellcheck disable=SC1090
    source "$SCRIPT"
    init_credentials >/dev/null 2>&1 || { echo "RESULT_INIT=1"; exit 0; }
    if resolve_and_pause; then echo "RESULT_RESOLVE=0"; else echo "RESULT_RESOLVE=$?"; fi
    echo "RESULT_AUTH_MODE=$AUTH_MODE"
    echo "RESULT_PAUSED=$PAUSED"
    echo "RESULT_LABEL=$CRED_LABEL"
    echo "RESULT_CRED_DIR_PERMS=$(stat -c '%a' "$CRED_DIR" 2>/dev/null)"
    echo "RESULT_CRED_FILE_PERMS=$(stat -c '%a' "$CRED_DIR"/*.curl 2>/dev/null | sort -u | tr '\n' ',' )"
    # The paused flag must read back as a real boolean, not "?" (jq `//` treats false as empty).
    echo "RESULT_FLAG_AFTER_PAUSE=$(status_json | field paused)"
    # Only a resolved credential is allowed to reach resume: a failure to resolve stops
    # the deploy (main exits 1) with nothing paused, exactly like the script.
    if [ "$PAUSED" = "1" ]; then
      if resume; then echo "RESULT_RESUME=0"; else echo "RESULT_RESUME=$?"; fi
    else
      echo "RESULT_RESUME=skipped"
    fi
    echo "RESULT_FLAG_AFTER_RESUME=$(status_json | field paused)"
    echo "RESULT_RESUMED=$RESUMED"
    rm -rf "$CRED_DIR"
  ) > "$TMP/case-$label.log" 2>&1
}

getv() {  # $1=label $2=key
  sed -n "s/^RESULT_$2=//p" "$TMP/case-$1.log" 2>/dev/null | tail -1
}
server_state() {  # $1=port -> "<paused> <n_calls>"
  local json
  json=$(curl -s -m 5 "http://127.0.0.1:$1/_state")
  if [ -z "$json" ]; then printf 'unreachable -'; return 0; fi
  printf '%s %s' "$(printf '%s' "$json" | jq -r '.paused')" "$(printf '%s' "$json" | jq -r '.calls | length')"
}

echo "== SCHED-GAP-1756 credential-ladder tests =="

# --- case A: rung 1 accepted (the real fleet's shape) ----------------------
echo "-- case A: X-Operator-Token accepted (rung 1, no fallback)"
if start_server operator_ok; then
  run_case A "$PORT" "$TMP/auth-good.env" "$TMP/env-good.env"
  check "A resolve"            "$(getv A RESOLVE)"        "0"
  check "A AUTH_MODE"          "$(getv A AUTH_MODE)"      "operator"
  check "A PAUSED"             "$(getv A PAUSED)"         "1"
  check "A resume"             "$(getv A RESUME)"         "0"
  check "A RESUMED"            "$(getv A RESUMED)"        "1"
  check "A credential dir perms" "$(getv A CRED_DIR_PERMS)"  "700"
  check "A credential file perms" "$(getv A CRED_FILE_PERMS)" "600,"
  check "A paused flag after pause"  "$(getv A FLAG_AFTER_PAUSE)"  "true"
  check "A paused flag after resume" "$(getv A FLAG_AFTER_RESUME)" "false"
  read -r st_paused st_calls <<< "$(server_state "$PORT")"
  check "A server paused"      "$st_paused" "false"
  check "A total POSTs (1 pause + 1 resume, no probe noise)" "$st_calls" "2"
  if grep -q 'attempt 2/2' "$TMP/case-A.log"; then bad "A should not fall back"; else ok "A never tried the fallback"; fi
fi

# --- case B: rung 1 refused, rung 2 accepted ------------------------------
echo "-- case B: X-Operator-Token refused -> Bearer fallback"
if start_server bearer_ok; then
  run_case B "$PORT" "$TMP/auth-bad.env" "$TMP/env-good.env"
  check "B resolve"            "$(getv B RESOLVE)"        "0"
  check "B AUTH_MODE"          "$(getv B AUTH_MODE)"      "bearer"
  check "B PAUSED"             "$(getv B PAUSED)"         "1"
  check "B resume"             "$(getv B RESUME)"         "0"
  check "B RESUMED"            "$(getv B RESUMED)"        "1"
  check "B paused flag after resume" "$(getv B FLAG_AFTER_RESUME)" "false"
  if grep -q 'pause attempt 1/2: X-Operator-Token' "$TMP/case-B.log" &&
     grep -q 'pause attempt 2/2: Authorization: Bearer' "$TMP/case-B.log"; then
    ok "B tried rung 1 then rung 2 in order"
  else
    bad "B ladder order not visible in the log"
  fi
  read -r st_paused st_calls <<< "$(server_state "$PORT")"
  check "B server paused"      "$st_paused" "false"
  check "B total POSTs (refused rung 1 + accepted pause + resume)" "$st_calls" "3"
fi

# --- case C: both refused -> fail loudly, change nothing ------------------
echo "-- case C: both credentials refused -> NO WORKING CREDENTIAL"
if start_server both_401; then
  run_case C "$PORT" "$TMP/auth-bad.env" "$TMP/env-bad.env"
  check "C resolve"            "$(getv C RESOLVE)"        "1"
  check "C AUTH_MODE reset"    "$(getv C AUTH_MODE)"      "none"
  check "C PAUSED"             "$(getv C PAUSED)"         "0"
  if grep -q 'NO WORKING CREDENTIAL' "$TMP/case-C.log"; then ok "C failed loudly"; else bad "C did not print NO WORKING CREDENTIAL"; fi
  if grep -q 'X-Operator-Token=401, Bearer(API_SERVER_KEY)=401' "$TMP/case-C.log"; then
    ok "C reported both status codes"
  else
    bad "C did not report both 401s"
  fi
  read -r st_paused st_calls <<< "$(server_state "$PORT")"
  check "C server untouched (paused)" "$st_paused" "false"
  check "C only the two refused probes hit the daemon" "$st_calls" "2"
fi

# --- case D: daemon unreachable -------------------------------------------
echo "-- case D: daemon unreachable -> 000, loud failure"
start_server operator_ok
DEAD_PORT=$PORT
for p in $SRV_PIDS; do kill "$p" 2>/dev/null; done
SRV_PIDS=""
sleep 0.5
run_case D "$DEAD_PORT" "$TMP/auth-good.env" "$TMP/env-good.env"
check "D resolve"              "$(getv D RESOLVE)"  "1"
check "D PAUSED"               "$(getv D PAUSED)"   "0"
if grep -q '000' "$TMP/case-D.log"; then ok "D reported 000 (no answer), not a credential verdict"; else bad "D did not report 000"; fi
if grep -q 'NO WORKING CREDENTIAL' "$TMP/case-D.log"; then ok "D failed loudly"; else bad "D was silent"; fi

# --- case E: resume answering 401 is a FAILURE (AC3) ----------------------
echo "-- case E: pause accepted, resume refused (401) -> reported as failure"
if start_server resume_401; then
  run_case E "$PORT" "$TMP/auth-good.env" "$TMP/env-good.env"
  check "E pause resolve"      "$(getv E RESOLVE)"     "0"
  check "E PAUSED after pause" "$(getv E PAUSED)"      "1"
  check "E resume exit"        "$(getv E RESUME)"      "1"
  check "E RESUMED stays 0"    "$(getv E RESUMED)"     "0"
  if grep -q 'RESUME FAILED -> HTTP 401' "$TMP/case-E.log"; then
    ok "E logged the refusal as a failure"
  else
    bad "E did not log the 401 resume as a failure"
  fi
fi

# --- case F: full main() end-to-end against the fake daemon ---------------
echo "-- case F: full main() run (pause -> drain -> restart(no-op seam) -> resume)"
if start_server operator_ok; then
  (
    export SCHEDULER_API="http://127.0.0.1:$PORT"
    export SCHEDULER_AUTH_ENV="$TMP/auth-good.env"
    export SCHEDULER_ENV_FILE="$TMP/env-good.env"
    export SCHEDULER_RESTART_CMD="/bin/true"
    export SCHEDULER_REPO="$TMP"
    export DRAIN_MAX=60
    export DEPLOY_LOG="$TMP/case-F.deploy.log"
    "$SCRIPT"
  ) > "$TMP/case-F.log" 2>&1
  F_RC=$?
  check "F exit code (whole deploy)" "$F_RC" "0"
  if grep -q 'deploy done' "$TMP/case-F.log"; then ok "F reached 'deploy done'"; else bad "F did not finish the deploy"; fi
  if grep -q 'readback after resume: paused=false' "$TMP/case-F.log"; then
    ok "F post-resume readback saw paused=false (not '?')"
  else
    bad "F post-resume readback wrong: $(grep 'readback after resume' "$TMP/case-F.log" 2>/dev/null || echo MISSING)"
  fi
  check "F restart seam ran once"      "$(grep -c 'restart command exit=0' "$TMP/case-F.log")" "1"
  check "F resolved at rung 1"         "$(grep -c 'credential RESOLVED: X-Operator-Token' "$TMP/case-F.log")" "1"
  if grep -q 'RESUME FAILED' "$TMP/case-F.log"; then bad "F logged a resume failure"; else ok "F logged no resume failure"; fi
  read -r st_paused st_calls <<< "$(server_state "$PORT")"
  check "F server left unpaused" "$st_paused" "false"
fi

echo
echo "== $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ]
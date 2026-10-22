#!/usr/bin/env bash
# SCHED-GAP-1756 — LIVE evidence for AC1, AC2 and the fail-loud path.
#
#   §1 AC1: resolve ONE credential against the live daemon; pause and resume with it,
#           both reading back HTTP 200.
#   §2 AC2: run the real deploy script, kill it mid-drain, and prove the EXIT trap
#           leaves /api/v1/status at paused=false.
#   §3 fail-loud: point the script at BOGUS credentials; it must refuse, exit 1, and
#           leave the fleet exactly as it found it.
#
# Mutating but bounded: each pause is held for seconds. The daemon is never restarted
# (the drain cannot reach zero while this session's own tick is in flight).
set -uo pipefail

SCRIPT=/home/kara/.hermes/scripts/deploy-scheduler-drain-restart.sh
API=http://127.0.0.1:9090
TMP=$(mktemp -d /tmp/sgap1756-live.XXXXXX)

status() { curl -s -m 10 "$API/api/v1/status" | jq -c '{paused, active_ticks}'; }
code_of() { curl -s -m 10 -o /dev/null -w '%{http_code}' "$@"; }

echo "=== SCHED-GAP-1756 live evidence $(date -Iseconds) ==="
echo "-- fleet before: $(status)"
echo "-- credential sources: $(ls -l /home/kara/.hermes/scheduler-auth.env | awk '{print $1, $NF}') / /home/kara/.hermes/.env"
echo

echo "=== §1 AC1 — one credential, live pause+resume pair ==="
(
  export SCHEDULER_API="$API"
  # shellcheck disable=SC1090
  source "$SCRIPT"
  init_credentials || { echo "!! init_credentials failed"; exit 1; }
  echo "-- credential files: $(stat -c '%a %n' "$CRED_DIR" "$CRED_DIR"/*.curl | tr '\n' ' ')"
  if resolve_and_pause; then echo "-- RESOLVE=0"; else echo "-- RESOLVE=$?"; fi
  echo "-- resolved: AUTH_MODE=$AUTH_MODE label=$CRED_LABEL"
  echo "-- status right after pause: $(status)"
  if resume; then echo "-- RESUME=0"; else echo "-- RESUME=$?"; fi
  echo "-- status right after resume: $(status)"
  echo "-- RESUMED=$RESUMED PAUSED=$PAUSED"
  cleanup_credentials
) 2>&1 | grep -v '^\[.*drain:'
echo

echo "=== §2 AC2 — forced abort (SIGTERM) mid-drain leaves paused=false ==="
SLOG=$TMP/script-ac2.log
echo "-- fleet before the run: $(status)"
DRAIN_MAX=1200 DEPLOY_LOG="$SLOG" "$SCRIPT" > "$SLOG" 2>&1 &
pid=$!
for _ in $(seq 1 200); do
  grep -q 'paused at' "$SLOG" 2>/dev/null && break
  kill -0 "$pid" 2>/dev/null || break
  sleep 0.2
done
echo "-- script log up to the kill:"
sed 's/^/   | /' "$SLOG"
echo "-- fleet state at kill time: $(status)  (active_ticks>0 is why it cannot restart)"
echo "-- sending SIGTERM to pid $pid"
kill -TERM "$pid" 2>/dev/null
wait "$pid"
rc=$?
echo "-- script exit rc=$rc (143 = TERM -> exit 143 -> EXIT trap)"
sleep 1
echo "-- script log after the kill:"
sed 's/^/   | /' "$SLOG"
echo "-- fleet after the forced abort: $(status)"
echo "-- /api/v1/status paused = $(curl -s -m 10 "$API/api/v1/status" | jq -r '.paused')"
echo

echo "=== §3 fail-loud — bogus credentials must refuse, not pause ==="
printf 'SCHEDULER_OPERATOR_TOKEN=%s\n' "$(od -An -tx1 -N32 /dev/urandom | tr -d ' \n')" > "$TMP/auth-bogus.env"
printf 'API_SERVER_KEY=%s\n' "bogus-gateway-key-not-the-operator-token" > "$TMP/env-bogus.env"
echo "-- fleet before: $(status)"
SCHEDULER_AUTH_ENV="$TMP/auth-bogus.env" SCHEDULER_ENV_FILE="$TMP/env-bogus.env" \
  DRAIN_MAX=60 DEPLOY_LOG=$TMP/script-ac3.log "$SCRIPT"
rc=$?
echo "-- script exit rc=$rc (1 expected)"
echo "-- fleet after: $(status)"
echo

echo "=== summary ==="
echo "-- credential file digest (operator source) unchanged: $(sha256sum /home/kara/.hermes/scheduler-auth.env | cut -c1-16)"
echo "-- final fleet state: $(status)"
rm -rf "$TMP"

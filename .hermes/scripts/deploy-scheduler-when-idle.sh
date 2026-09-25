#!/usr/bin/env bash
# deploy-when-idle.sh — land the scheduler deploy in a NATURAL drain window.
#
# Why: a pause-first deploy holds the whole fleet idle for however long the longest
# in-flight tick runs (observed: aborted after 60 min; ticks may run to the 2h
# --tick-timeout). This script watches for the fleet to reach 0 running ticks on its
# own (waves finish constantly), then pauses, re-checks, restarts (ExecStartPre
# rebuilds HEAD), resumes. Idle cost is the boot+build time only.
#
# Safety: never restarts while a tick runs (re-checks AFTER pausing and aborts +
# resumes if anything slipped in). Bounded by MAX_WAIT_S. Logs every step.
set -uo pipefail

KEY=$(grep -m1 '^API_SERVER_KEY=' /home/kara/.hermes/.env 2>/dev/null | cut -d= -f2-)
API=http://127.0.0.1:9090
REPO=/home/kara/coding-hermes-scheduler/coding-herms-scheduler
MAX_WAIT_S=${MAX_WAIT_S:-10800}   # 3h ceiling on waiting for a window
CONSEC=${CONSEC:-3}               # consecutive clean polls (~60s of true idle)
QUIET_EXTRA=${QUIET_EXTRA:-4.0}   # also require load1 below this before restarting

api() { curl -s -m 25 -K <(printf 'header = "Authorization: Bearer %s"\n' "${KEY}") "$@"; }
field() { python3 -c "import json,sys
try: d=json.load(sys.stdin)
except Exception: print('?'); raise SystemExit
print(d.get('$1'))"; }
log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== deploy-when-idle start (max wait ${MAX_WAIT_S}s, need ${CONSEC} clean polls, load<${QUIET_EXTRA}) ==="
deadline=$(( $(date +%s) + MAX_WAIT_S ))
clean=0
while :; do
  st=$(api "$API/api/v1/status")
  act=$(printf '%s' "$st" | field active_ticks)
  load1=$(cut -d' ' -f1 /proc/loadavg)
  if [ "$act" = "0" ] && python3 -c "import sys;sys.exit(0 if float('$load1') < $QUIET_EXTRA else 1)"; then
    clean=$((clean+1))
    log "idle window: active=0 load=$load1 (${clean}/${CONSEC})"
  else
    [ "$clean" != "0" ] && log "window lost: active=$act load=$load1"
    clean=0
  fi
  [ "$clean" -ge "$CONSEC" ] && break
  if [ $(date +%s) -gt $deadline ]; then
    log "NO IDLE WINDOW within ${MAX_WAIT_S}s — giving up (fleet untouched, still running)"
    exit 5
  fi
  sleep 20
done

log "window found — pausing"
log "pause -> HTTP $(api -o /dev/null -w '%{http_code}' -X POST "$API/api/v1/pause")"
sleep 3
st=$(api "$API/api/v1/status"); act=$(printf '%s' "$st" | field active_ticks)
if [ "$act" != "0" ]; then
  log "ABORT: active_ticks=$act after pause — a tick slipped in; resuming, NOT restarting"
  api -X POST "$API/api/v1/resume" >/dev/null
  exit 6
fi

log "HEAD: $(cd $REPO && git log -1 --pretty='%h %s')"
log "restarting (ExecStartPre rebuilds HEAD)"
systemctl --user restart coding-hermes-scheduler.service
log "restart exit=$?"

ok=0
for i in $(seq 1 45); do
  h=$(curl -s -m 6 "$API/api/v1/health" 2>/dev/null)
  case "$h" in *'"db":"connected"'*) ok=1; break;; esac
  sleep 4
done
log "health (ok=$ok): $h"
if [ "$ok" != "1" ]; then
  log "DAEMON UNHEALTHY — scheduling left PAUSED for safety; inspect journalctl --user -u coding-hermes-scheduler -n 80"
  exit 4
fi

log "resume -> HTTP $(api -o /dev/null -w '%{http_code}' -X POST "$API/api/v1/resume")"
log "live: $h"
for sym in 'api-pause-cascade' 'paused by target' 'WAVE_BUDGET' 'GATEWAY-HEALTH-GATE'; do
  log "  symbol '$sym': $(strings $REPO/bin/schedulerd 2>/dev/null | grep -c -- "$sym")"
done
( cd "$REPO" && bash ops/check-daemon-freshness.sh 2>&1 | sed 's/^/  freshness: /'; echo "  freshness exit=$?" )
log "=== deploy-when-idle done ==="

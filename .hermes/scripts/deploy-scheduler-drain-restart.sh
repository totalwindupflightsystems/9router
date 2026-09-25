#!/usr/bin/env bash
# One-shot scheduler deploy: pause -> drain (active_ticks=0) -> restart (ExecStartPre rebuilds HEAD)
# -> resume -> verify. Bounded: if the drain does not finish in DRAIN_MAX the fleet is RESUMED and
# NOT restarted (never restart with active ticks — hermes-fleet-ops).
set -uo pipefail

KEY=$(grep -m1 '^API_SERVER_KEY=' /home/kara/.hermes/.env 2>/dev/null | cut -d= -f2-)
API=http://127.0.0.1:9090
REPO=/home/kara/coding-hermes-scheduler/coding-herms-scheduler
DRAIN_MAX=${DRAIN_MAX:-2700}
LOG=/tmp/scheduler-deploy-$(date +%Y%m%d-%H%M%S).log

api() { curl -s -m 25 -K <(printf 'header = "Authorization: Bearer %s"\n' "${KEY}") "$@"; }
stat() { api "$API/api/v1/status"; }
field() { python3 -c "import json,sys
try:
    d=json.load(sys.stdin)
except Exception:
    print('?'); raise SystemExit
print(d.get('$1'))"; }

log() { echo "[$(date +%H:%M:%S)] $*"; }

log "=== deploy start (log: $LOG) ==="
head=$(cd "$REPO" && git log -1 --pretty='%h %s')
log "HEAD: $head"
log "live before: $(curl -s -m 10 $API/api/v1/health)"

# 1. pause (atomic; never restart mid-tick)
code=$(api -o /tmp/.deploy_pause.json -w '%{http_code}' -X POST "$API/api/v1/pause" || echo 000)
log "pause -> HTTP $code $(cat /tmp/.deploy_pause.json 2>/dev/null | head -c 200)"

# 2. drain
deadline=$(( $(date +%s) + DRAIN_MAX ))
while :; do
  st=$(stat)
  act=$(printf '%s' "$st" | field active_ticks)
  log "drain: active_ticks=$act queued=$(printf '%s' "$st" | field queued_ticks)"
  [ "$act" = "0" ] && break
  if [ $(date +%s) -gt $deadline ]; then
    log "DRAIN TIMEOUT after ${DRAIN_MAX}s — resuming, NOT restarting"
    api -X POST "$API/api/v1/resume" >/dev/null
    log "=== deploy ABORTED (no restart) ==="
    exit 3
  fi
  sleep 20
done

# 3. restart (ExecStartPre = schedulerd-build.sh -> make build from HEAD)
log "restarting coding-hermes-scheduler.service (rebuilds HEAD via ExecStartPre)"
systemctl --user restart coding-hermes-scheduler.service
rc=$?
log "systemctl restart exit=$rc"

# 4. wait for health
ok=0
for i in $(seq 1 40); do
  h=$(curl -s -m 6 "$API/api/v1/health" 2>/dev/null)
  case "$h" in *'"status":"ok"'*|*'"db":"connected"'*) ok=1; break;; esac
  sleep 4
done
log "health after restart (ok=$ok): $h"
if [ "$ok" != "1" ]; then
  log "DAEMON NOT HEALTHY — inspect: journalctl --user -u coding-hermes-scheduler -n 60"
  log "=== deploy FAILED, leaving scheduling PAUSED for safety ==="
  exit 4
fi

# 5. resume (idempotent)
log "resume -> HTTP $(api -o /dev/null -w '%{http_code}' -X POST "$API/api/v1/resume")"

# 6. verify
log "live after: $(curl -s -m 10 $API/api/v1/health)"
log "status: $(stat | head -c 400)"
log "--- deploy-verify symbols in the RUNNING binary ---"
for sym in 'api-pause-cascade' 'paused by target' 'WAVE_BUDGET' 'load gate deferring' 'GATEWAY-HEALTH-GATE'; do
  n=$(strings /home/kara/coding-hermes-scheduler/coding-herms-scheduler/bin/schedulerd 2>/dev/null | grep -c -- "$sym")
  log "  symbol '$sym': $n"
done
log "--- freshness guard ---"
( cd "$REPO" && bash ops/check-daemon-freshness.sh; echo "freshness exit=$?" ) 2>&1 | while read -r l; do log "$l"; done
log "--- gateway/load gate boot lines ---"
grep -aE 'GATEWAY-HEALTH-GATE|LOAD-GATE|load gate' /home/kara/.hermes/coding-hermes/scheduler.log | tail -5 | while read -r l; do log "$l"; done
log "=== deploy done ==="

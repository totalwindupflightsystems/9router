#!/usr/bin/env bash
# One-shot scheduler deploy: pause -> drain (active_ticks=0) -> restart (ExecStartPre rebuilds HEAD)
# -> resume -> verify. Bounded: if the drain does not finish in DRAIN_MAX the fleet is RESUMED and
# NOT restarted (never restart with active ticks — hermes-fleet-ops).
#
# SCHED-GAP-1756 — WHY THE CREDENTIAL LADDER EXISTS
# Every mutating /api/v1 route passes through the daemon's operator gate (SCHED-GAP-1602). The daemon
# loads ONE operator credential from its EnvironmentFile (`~/.hermes/scheduler-auth.env`,
# SCHEDULER_OPERATOR_TOKEN). This script used to send API_SERVER_KEY from ~/.hermes/.env as
# `Authorization: Bearer` on EVERY call — that is the GATEWAY key, not the operator token, and the
# daemon answers 401 {"error":"invalid operator credential"} for it. On 2026-10-22 the pause therefore
# never landed (a DIFFERENT caller paused at 07:02), the drain ran against someone else's pause, and
# the abort path's resume was refused with the same bad credential: the fleet sat paused for 74
# minutes (07:00-08:14) with no owner and no deploy.
# The script now RESOLVES one working credential BEFORE it touches scheduling state (pause itself is
# the probe: both candidates are tried in order, and if neither is accepted it fails loudly having
# changed nothing), and it refuses to treat a non-200 resume as success. The ladder itself lives in
# lib/scheduler-cred.sh, shared with scheduler-deploy-drain-restart.sh.
#
# Exit codes:
#   0   deployed clean
#   1   no working credential / unverified pause / precondition failure (nothing left paused)
#   3   drain timeout — resumed, NOT restarted
#   4   daemon not healthy after restart (EXIT trap resumes)
#   5   resume refused by the daemon (fleet state uncertain, reported loudly)
#   143 killed mid-drain (trap 'exit 143' TERM INT -> EXIT trap resumes)
#
# Testability: env overrides SCHEDULER_API / SCHEDULER_REPO / SCHEDULER_AUTH_ENV / SCHEDULER_ENV_FILE
# exist so the credential ladder can be exercised against a fake daemon and fixture credential files
# (see tests/test-drain-restart-credentials.sh). Sourcing this file has no side effects; main() only
# runs when it is executed.
set -uo pipefail

API=${SCHEDULER_API:-http://127.0.0.1:9090}
REPO=${SCHEDULER_REPO:-/home/kara/coding-hermes-scheduler/coding-herms-scheduler}
DRAIN_MAX=${DRAIN_MAX:-2700}
AUTH_ENV=${SCHEDULER_AUTH_ENV:-$HOME/.hermes/scheduler-auth.env}
ENV_FILE=${SCHEDULER_ENV_FILE:-$HOME/.hermes/.env}
LOG=${DEPLOY_LOG:-/tmp/scheduler-deploy-$(date +%Y%m%d-%H%M%S).log}
RESTART_CMD=${SCHEDULER_RESTART_CMD:-"systemctl --user restart coding-hermes-scheduler.service"}

AUTH_MODE=none      # operator | bearer | none — the ONE resolved credential
CRED_LABEL=""       # human-readable name of the resolved credential (never the value)
PAUSED=0
RESUMED=0
CRED_DIR=""

log() { echo "[$(date +%H:%M:%S)] $*"; }

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/scheduler-cred.sh
source "$SCRIPT_DIR/lib/scheduler-cred.sh"

field() {  # $1 = top-level key of a status JSON object ("?" when absent/unparseable)
  # NB: `// "?"` is WRONG for booleans — jq's alternative operator treats `false` as empty,
  # so `.paused // "?"` answers "?" for a RUNNING fleet and a post-resume check sees a bogus
  # non-false value. Test for null explicitly.
  local out
  out=$(jq -r --arg k "${1:-}" 'if type=="object" then (.[$k] | if . == null then "?" else . end) else "?" end' 2>/dev/null)
  printf '%s' "${out:-?}"
}

duration_s() {  # "3h" / "90m" / "7200s" -> seconds; empty when unparseable
  local s=${1:-} n u
  case "$s" in
    *[hms]) ;;
    *) return 1 ;;
  esac
  n=${s%[hms]}
  u=${s#"$n"}
  case "$u" in
    h) printf '%s' $(( n * 3600 )) ;;
    m) printf '%s' $(( n * 60 )) ;;
    s) printf '%s' "$n" ;;
    *) return 1 ;;
  esac
}

# --- EXIT safety net -------------------------------------------------------
# EXIT does not fire on SIGTERM by itself; trap 'exit 143' TERM INT re-enters this
# handler. A SIGKILL/OOM/reboot still defeats it — check /api/v1/status paused yourself.
cleanup() {
  local rc=$?
  trap - EXIT
  if [ "${PAUSED:-0}" = "1" ] && [ "${RESUMED:-0}" = "0" ]; then
    log "EXIT trap (rc=$rc): fleet is paused and the deploy did not complete — resuming so it is not left parked"
    resume || log "!! EXIT trap COULD NOT RESUME — the fleet is still PAUSED; POST $API/api/v1/resume by hand"
  fi
  cleanup_credentials
  log "=== exit rc=$rc ==="
  exit "$rc"
}

main() {
  trap cleanup EXIT
  trap 'exit 143' TERM INT

  log "=== deploy start (log: $LOG) ==="
  init_credentials || { log "=== deploy ABORTED (credentials unavailable) ==="; exit 1; }

  local head
  head=$(cd "$REPO" && git log -1 --pretty='%h %s' 2>/dev/null)
  log "HEAD: ${head:-unknown}"
  log "live before: $(curl -s -m 10 "$API/api/v1/health")"

  # A drain cap below the daemon's own --tick-timeout cannot succeed while a long tick is in
  # flight: the run is then guaranteed to abort after DRAIN_MAX of polling. Say it up front
  # (2026-10-22 burned 45 minutes discovering exactly this).
  local mainpid tt tt_s
  mainpid=$(systemctl --user show coding-hermes-scheduler.service -p MainPID --value 2>/dev/null)
  case "${mainpid:-0}" in ''|0) mainpid=$(pgrep -x schedulerd 2>/dev/null | head -1) ;; esac
  tt=""
  if [ -n "${mainpid:-}" ]; then
    tt=$(tr '\0' ' ' < "/proc/$mainpid/cmdline" 2>/dev/null | grep -o -- '--tick-timeout [0-9]*[hms]' | awk '{print $2}')
  fi
  [ -n "${tt:-}" ] || tt="not-set"
  log "drain cap=${DRAIN_MAX}s | daemon --tick-timeout=${tt} | mainpid=${mainpid:-unknown}"
  tt_s=$(duration_s "${tt}" 2>/dev/null) || tt_s=""
  if [ -n "${tt_s:-}" ] && [ "$DRAIN_MAX" -lt "$tt_s" ]; then
    log "WARN: drain cap ${DRAIN_MAX}s < tick timeout ${tt} — an in-flight tick can outlive the cap, so this run is BOUND to abort (exit 3) rather than restart; raise DRAIN_MAX or wait for a quiet window"
  fi

  # 0. Who owns the pause we are about to create? On 2026-10-22 a foreign pause made the
  # drain loop look healthy while this script held none of the state it later failed to clear.
  local pre_paused
  pre_paused=$(status_json | field paused)
  if [ "$pre_paused" = "true" ]; then
    log "WARN: /api/v1/status said paused=true BEFORE this run — adopting an existing pause."
    log "      This run now owns it and WILL resume at the end (including via the EXIT trap)."
    log "      If another operator is mid-drain, stop now: the resume clears their pause too."
  else
    log "pre-flight: paused=$pre_paused (no inherited pause)"
  fi

  # 1. resolve ONE credential by pausing with it — never drain on an unresolved credential
  resolve_and_pause || { log "=== deploy ABORTED (no working credential) ==="; exit 1; }
  log "paused at $(date -Iseconds) (paused=$PAUSED)"

  # 1b. the 200 is the gate opening; the FLAG is the effect. Verify the effect.
  local pf
  pf=$(status_json | field paused)
  log "readback: paused=$pf"
  if [ "$pf" != "true" ]; then
    log "!! pause answered 200 but /api/v1/status says paused=$pf — refusing to drain on an unverified pause"
    PAUSED=0
    exit 1
  fi

  # 2. drain
  local deadline st act elapsed
  deadline=$(( $(date +%s) + DRAIN_MAX ))
  while :; do
    st=$(status_json)
    act=$(printf '%s' "$st" | field active_ticks)
    elapsed=$(( $(date +%s) - (deadline - DRAIN_MAX) ))
    log "drain: active_ticks=$act (elapsed=${elapsed}s, cap=${DRAIN_MAX}s)"
    [ "$act" = "0" ] && break
    if [ "$(date +%s)" -gt "$deadline" ]; then
      log "DRAIN TIMEOUT after ${DRAIN_MAX}s — resuming, NOT restarting"
      resume || { log "=== deploy ABORTED and RESUME REFUSED — FLEET STILL PAUSED ==="; exit 5; }
      log "=== deploy ABORTED (no restart) ==="
      exit 3
    fi
    sleep 20
  done
  log "drained at $(date -Iseconds)"

  # 3. restart (ExecStartPre = schedulerd-build.sh -> make build from HEAD)
  # SCHEDULER_RESTART_CMD is a test seam: the credential/readback flow is exercised
  # end-to-end against a fake daemon without restarting the live one.
  log "restarting via: $RESTART_CMD (ExecStartPre rebuilds HEAD)"
  local -a restart_argv
  read -r -a restart_argv <<< "$RESTART_CMD"
  "${restart_argv[@]}"
  local rc=$?
  log "restart command exit=$rc"

  # 4. wait for health
  local ok=0 h i
  for i in $(seq 1 40); do
    h=$(curl -s -m 6 "$API/api/v1/health" 2>/dev/null)
    case "$h" in *'"status":"ok"'*|*'"db":"connected"'*) ok=1; break;; esac
    sleep 4
  done
  log "health after restart (ok=$ok): $h"
  if [ "$ok" != "1" ]; then
    log "DAEMON NOT HEALTHY — inspect: journalctl --user -u coding-hermes-scheduler -n 60"
    log "=== deploy FAILED (EXIT trap will attempt the resume) ==="
    exit 4
  fi

  # 5. resume (idempotent) — status-checked, a 401 is a failure
  resume || { log "=== deploy FAILED: fleet may still be paused ==="; exit 5; }
  local pf2
  pf2=$(status_json | field paused)
  log "readback after resume: paused=$pf2"
  if [ "$pf2" != "false" ]; then
    log "!! resume answered 200 but /api/v1/status says paused=$pf2 — reporting failure"
    PAUSED=1
    RESUMED=0
    exit 5
  fi

  # 6. verify
  log "live after: $(curl -s -m 10 "$API/api/v1/health")"
  log "status: $(status_json | head -c 400)"
  log "--- deploy-verify symbols in the RUNNING binary ---"
  local sym n bin=/home/kara/coding-hermes-scheduler/coding-herms-scheduler/bin/schedulerd
  for sym in 'api-pause-cascade' 'paused by target' 'WAVE_BUDGET' 'load gate deferring' 'GATEWAY-HEALTH-GATE'; do
    n=$(strings "$bin" 2>/dev/null | grep -c -- "$sym")
    log "  symbol '$sym': $n"
  done
  log "--- freshness guard ---"
  ( cd "$REPO" && bash ops/check-daemon-freshness.sh; echo "freshness exit=$?" ) 2>&1 | while read -r l; do log "$l"; done
  log "--- gateway/load gate boot lines ---"
  grep -aE 'GATEWAY-HEALTH-GATE|LOAD-GATE|load gate' /home/kara/.hermes/coding-hermes/scheduler.log | tail -5 | while read -r l; do log "$l"; done
  log "=== deploy done ($(date -Iseconds)) credential=$CRED_LABEL ==="
}

if [[ "${BASH_SOURCE[0]}" == "${0}" ]]; then
  main "$@"
fi

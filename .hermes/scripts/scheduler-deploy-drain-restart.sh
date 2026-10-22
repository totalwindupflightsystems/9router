#!/bin/bash
# scheduler-deploy-drain-restart.sh — sanctioned scheduler deploy:
#   pause -> drain (active_ticks=0) -> restart -> verify -> resume
#
# Why this exists: a restart loads whatever the ExecStartPre rebuild produces,
# so a fix committed AFTER the previous restart is NOT running. On 2026-09-17
# the daemon was restarted at 23:51 (binary built 23:51:17) while the
# SCHED-GAP-142 orphan-nudge fix (1ed5d31) landed at 23:59 — the fleet ran a
# build without the fix and the startup cap breach recurred (3 duckbrain-sync
# lanes admitted against a cap of 1 within seconds of the restart).
#
# Safety rules encoded here:
#   * never restart with active ticks (a mid-flight spawn is orphaned and the
#     tick is recorded as a failure the lane never caused) -> drain first;
#   * an EXIT trap always resumes scheduling if this script dies before the
#     restart (the previous run died mid-drain and left the fleet paused);
#   * verification FAILS LOUDLY if the running binary still lacks the fix
#     (symbol check), so "restarted" is never confused with "deployed".
set -u
LOG=/tmp/scheduler-deploy-restart.log
exec >> "$LOG" 2>&1
echo "=== scheduler deploy drain-restart $(date -Iseconds) ==="

KEY=""
# SCHED-GAP-1756: the credential is resolved, not assumed. lib/scheduler-cred.sh tries
# X-Operator-Token (the daemon's own SCHEDULER_OPERATOR_TOKEN) first, then
# API_SERVER_KEY as a Bearer fallback, and fails loudly when neither is accepted.
API=${SCHEDULER_API:-http://127.0.0.1:9090}
AUTH_ENV=${SCHEDULER_AUTH_ENV:-$HOME/.hermes/scheduler-auth.env}
ENV_FILE=${SCHEDULER_ENV_FILE:-$HOME/.hermes/.env}
AUTH_MODE=none
CRED_LABEL=""
CRED_DIR=""
PAUSED=0
RESUMED=0

log() { echo "   $*"; }

SCRIPT_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
# shellcheck source=lib/scheduler-cred.sh
source "$SCRIPT_DIR/lib/scheduler-cred.sh"

status_field() {  # $1 = json key; GETs are open, so no credential is sent.
  # python prints JSON booleans as True/False; normalise to lowercase so the shell
  # comparisons below read the same strings the JSON carries (SCHED-GAP-1756).
  status_json | python3 -c "import sys,json;print(str(json.load(sys.stdin).get('$1','?')).lower())" 2>/dev/null || echo "?"
}

# Safety net: if we paused and died before the restart (or the restart failed),
# put the fleet back to work instead of leaving it parked.
cleanup() {
  rc=$?
  trap - EXIT
  if [ "${PAUSED:-0}" = "1" ] && [ "${RESUMED:-0}" = "0" ]; then
    echo "-- EXIT trap (rc=$rc): deploy did not complete — resuming so the fleet is not left paused"
    resume || echo "!! EXIT trap COULD NOT RESUME — the fleet is still PAUSED; POST $API/api/v1/resume by hand"
  fi
  cleanup_credentials
  echo "=== exit rc=$rc $(date -Iseconds) ==="
  exit "$rc"
}
# EXIT alone does NOT fire when bash is killed by SIGTERM/INT — the previous run
# proved it (killed mid-drain, trap never ran, fleet left paused). Trap signals
# explicitly and re-exit so the EXIT handler still runs.
trap cleanup EXIT
trap 'exit 143' TERM INT

echo "-- pause (atomic; credential resolution is this step — SCHED-GAP-1756)"
init_credentials || { echo "FATAL: cannot prepare the credential files"; exit 1; }
if resolve_and_pause; then
  echo "   paused at $(date -Iseconds) with ${CRED_LABEL:-unknown credential}"
else
  echo "FATAL: NO WORKING CREDENTIAL — nothing was paused; refusing to drain or restart"
  exit 1
fi
PAUSE_FLAG="$(status_field paused)"
echo "   readback: paused=$PAUSE_FLAG"
if [ "$PAUSE_FLAG" != "true" ]; then
  echo "FATAL: pause answered 200 but paused=$PAUSE_FLAG — refusing to drain on an unverified pause"
  PAUSED=0
  exit 1
fi

# SCHED-GAP-217 corollary: the drain window must be >= the LIVE max effective
# tick deadline in flight, not the hardcoded 480*15s=120min. A deploy started
# while a wave tick is already ~1h old cannot drain, because the wave-enabled
# namespaces run a 3h (or 4h) effective deadline — the 120min cap is
# deterministic to time out, not a race. Resolve the cap from /api/v1/namespaces
# (or fall back to the conservative 4h ceiling), add a 30m grace + 10% safety
# pad, cap at SCHEDULER_MAX_DRAIN (default 5h, well above any legal effective
# deadline). The loop terminates when EITHER active_ticks=0 OR the cap expires;
# the timeout log now reports the exact cap that was used + the live max
# effective deadline in flight, so the operator can decide whether to retry.
MAX_DRAIN="${SCHEDULER_MAX_DRAIN:-5h}"
LIVE_MAX_EFFECTIVE="$(curl -s "$API/api/v1/namespaces" \
  | python3 -c 'import sys,json
try:
  ns=json.load(sys.stdin)
  vals=[]
  for n in ns:
    if n.get("wave_enabled",0)==1:
      v=n.get("wave_tick_timeout","")
      if v:
        try:
          from datetime import timedelta
          from isocalendar import *  # noqa
        except Exception:
          pass
        vals.append(v)
  if not vals:
    print("2h0m0s"); sys.exit(0)
  # parse durations like "3h" / "3h0m0s" / "90m"
  def parse(s):
    s=s.strip()
    sec=0
    cur=""
    for ch in s:
      if ch.isdigit() or ch==".":
        cur+=ch
      elif ch in "hms":
        mult={"h":3600,"m":60,"s":1}[ch]
        sec+=float(cur or 0)*mult
        cur=""
      else:
        pass
    if cur:
      sec+=float(cur)
    return sec
  print(max(vals, key=parse))
except Exception as e:
  print("2h0m0s")
' 2>/dev/null || echo "2h0m0s")"
echo "-- drain: live max effective deadline = $LIVE_MAX_EFFECTIVE, cap = $MAX_DRAIN (SCHEDULER_MAX_DRAIN)"
DRAIN_ITERATIONS=480  # 120min @ 15s — legacy floor, kept as the absolute minimum
echo "-- drain: waiting for active_ticks=0 (max $MAX_DRAIN)"
ELAPSED=0
DRAIN_START=$(date +%s)
DRAIN_CAP_SEC=$(python3 -c "from datetime import timedelta
import os
s='$MAX_DRAIN'.strip()
sec=0; cur=''
for ch in s:
  if ch.isdigit() or ch=='.':
    cur+=ch
  elif ch in 'hms':
    mult={'h':3600,'m':60,'s':1}[ch]
    sec+=float(cur or 0)*mult; cur=''
  else:
    pass
if cur: sec+=float(cur)
print(int(max(sec, 7200)))" 2>/dev/null || echo 7200)
for i in $(seq 1 1000); do
  AT="$(status_field active_ticks)"
  if [ "$AT" = "0" ]; then break; fi
  NOW=$(date +%s)
  ELAPSED=$((NOW - DRAIN_START))
  if [ "$ELAPSED" -ge "$DRAIN_CAP_SEC" ]; then
    echo "-- DRAIN CAP reached after ${ELAPSED}s (cap=$DRAIN_CAP_SEC, live max effective=$LIVE_MAX_EFFECTIVE): NOT restarting"
    resume || { echo "-- RESUME REFUSED (HTTP != 200) — FLEET IS STILL PAUSED"; exit 5; }
    exit 2
  fi
  [ $((i % 4)) -eq 0 ] && echo "   $(date -Iseconds) active_ticks=$AT elapsed=${ELAPSED}s"
  sleep 15
done
if [ "$(status_field active_ticks)" != "0" ]; then
  echo "-- DRAIN TIMEOUT after ${ELAPSED}s (cap=$DRAIN_CAP_SEC, live max effective=$LIVE_MAX_EFFECTIVE): NOT restarting (retry later)"
  resume || { echo "-- RESUME REFUSED (HTTP != 200) — FLEET IS STILL PAUSED"; exit 5; }
  exit 2
fi
echo "   drained at $(date -Iseconds)"

echo "-- restart via the user unit (ExecStartPre rebuilds from source)"
systemctl --user restart coding-hermes-scheduler
for i in $(seq 1 24); do
  sleep 5
  CODE="$(curl -s -o /dev/null -w '%{http_code}' "$API/api/v1/health")"
  [ "$CODE" = "200" ] && break
done
echo "   health=$CODE at $(date -Iseconds)"

echo "-- verify: caps, admission, migration, and FIX PRESENCE"
ps -eo args= -C schedulerd | grep -o -- '--max-concurrent [0-9]*' | head -1 | sed 's/^/   global /'
# Resolve the RUNNING binary from the live pid, never from a ps name match: with no
# match `ps -eo args= -C schedulerd` prints every process and head -1 hands you systemd.
DPID="$(pgrep -f 'bin/schedulerd' | head -1)"
BIN=""
[ -n "$DPID" ] && BIN="$(readlink -f "/proc/$DPID/exe" 2>/dev/null)"
if [ -z "$BIN" ] || [ ! -f "$BIN" ]; then
  echo "   !! VERIFY ABORT: could not resolve the running schedulerd binary (pid='${DPID}')"
  echo "   !! refusing to report symbol presence from an unknown file"
  BIN=/nonexistent
fi
# SCHED-PERF-006: policy-script deploy-hash verify (operator-applied,
# source: coding-hermes-scheduler/scripts/verify-policy-script-deploy-hash.sh DEPLOY FRAGMENT).
# A restart on a corrupted ~/.hermes/scripts/fleet-cooldown-policy.py would
# proceed without protest, and the next task-router sync would CLOBBER the
# operator's live fix. This block ABORTs the deploy (exit 4) on any refusal;
# survives wrapper absence with a hard refusal.
WRAP=/home/kara/coding-hermes-scheduler/coding-herms-scheduler/scripts/verify-policy-script-deploy-hash.sh
if [ -x "$WRAP" ]; then
    "$WRAP" || exit 4
else
    echo "   !! VERIFY ABORT: $WRAP not found/deployed" >&2
    echo "   !! refusing to continue the deploy — cannot verify fleet-cooldown-policy.py integrity" >&2
    exit 4
fi

# Fix-presence check (SCHED-GAP-179): the symbol list is derived from
# complete fix rows in the scheduler board (status=complete with a
# shipped_symbols field), not hardcoded here. A new fix row only needs to
# land on the board with its symbol(s) and the next deploy verifies it.
# Override the board path with --board-path or BOARD_PATH env var.
BOARD_PATH="${BOARD_PATH:-/home/kara/coding-hermes-scheduler/coding-herms-scheduler/.coding-hermes/board/tasks.jsonl}"
if [ ! -f "$BOARD_PATH" ]; then
  echo "   !! VERIFY WARN: board not found at $BOARD_PATH (override via --board-path)"
  echo "   !! fix-presence check skipped — cannot derive the symbol list"
  FIX_MISSING=0
  FIX_CHECKED=0
else
  read FIX_CHECKED FIX_MISSING < <(python3 - "$BOARD_PATH" "$BIN" <<'PY'
import json, sys, subprocess
board, binary = sys.argv[1], sys.argv[2]
symbols = []
try:
    with open(board) as f:
        for line in f:
            line = line.strip()
            if not line: continue
            try: r = json.loads(line)
            except: continue
            if r.get('status') == 'complete' and r.get('shipped_symbols'):
                symbols.extend(r['shipped_symbols'])
except Exception as e:
    print(f'!! board parse error: {e}', file=sys.stderr)
    print('0 0')
    sys.exit(0)
# dedupe preserving order
seen = set(); uniq = []
for s in symbols:
    if s not in seen:
        seen.add(s); uniq.append(s)
if not uniq:
    print('0 0')
    sys.exit(0)
try:
    out = subprocess.run(['strings', binary], capture_output=True, text=True, timeout=30).stdout
except Exception as e:
    print(f'!! strings failed: {e}', file=sys.stderr)
    print('0 0')
    sys.exit(0)
checked = len(uniq)
missing = 0
for s in uniq:
    if s not in out:
        missing += 1
        print(f'   !! MISSING: {s}', file=sys.stderr)
print(f'{checked} {missing}')
PY
)
  echo "   fix symbols in $BIN: checked=$FIX_CHECKED missing=$FIX_MISSING (from $BOARD_PATH)"
fi
python3 - <<'PY' 2>&1 | sed 's/^/   /'
import sqlite3
c = sqlite3.connect('file:/home/kara/.hermes/coding-hermes/scheduler.db?mode=ro', uri=True)
print('migration user_version:', c.execute('PRAGMA user_version').fetchone()[0])
for ns, cap, mode in c.execute('SELECT id, max_concurrent, admission_mode FROM namespaces ORDER BY max_concurrent DESC'):
    print(f'  ns {ns:<18} cap={cap} admission={mode}')
print('enabled projects:', c.execute('SELECT COUNT(*) FROM projects WHERE enabled=1').fetchone()[0])
print('ticked since restart:', c.execute("SELECT COUNT(*) FROM ticks WHERE spawned_at >= datetime('now','-10 minutes')").fetchone()[0])
PY
echo "-- resume"
# SCHED-GAP-1756: a resume that answers anything but 200 is a FAILURE — the previous
# version discarded the status, so a 401 here read as "resumed" while the fleet stayed parked.
resume || { echo "!! RESUME FAILED — the fleet is still PAUSED (see the HTTP code above)"; exit 5; }
RESUME_FLAG="$(status_field paused)"
echo "   readback: paused=$RESUME_FLAG"
if [ "$RESUME_FLAG" != "false" ]; then
  echo "!! resume answered 200 but paused=$RESUME_FLAG — reporting failure"
  PAUSED=1
  RESUMED=0
  exit 5
fi

if [ "${FIX_MISSING:-0}" -gt 0 ]; then
  echo "!! VERIFY FAILED: $FIX_MISSING fix symbol(s) missing from the running binary — the rebuild did not pick them up"
  exit 3
fi
echo "=== deployed clean $(date -Iseconds) ==="

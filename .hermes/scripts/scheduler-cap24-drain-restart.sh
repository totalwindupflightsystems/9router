#!/bin/bash
# scheduler-cap24-drain-restart.sh — ONE-OFF scheduler deploy (2026-09-17):
#   pause -> drain (active_ticks=0) -> restart -> verify -> resume
#
# SCHED-GAP-1756 NOTE — DO NOT REUSE THIS AS A DEPLOY HELPER.
# It was a single-purpose run for the changes below and it has NO signal traps, so a kill
# mid-drain leaves the fleet parked with no owner (that is Trap A/E in
# docs/runbook-drain-restart.md). For a deploy use
# ~/.hermes/scripts/deploy-scheduler-drain-restart.sh instead: it resolves one working
# operator credential before touching scheduling state, checks every resume status code,
# and traps EXIT/TERM/INT. Its resume handling is mirrored here only so that running this
# relic by hand cannot report a refused resume as success.
#
# Brings live, in one pass:
#   * global max-concurrent 5 -> 24              (Bane 2026-09-17)
#   * SCHED-GAP-141 board-ownership admission rule (committed 0441cee)
#   * migration 32 (projects.board_ownership)
#   * gitreins-poc resumed
# Never restarts with active ticks: a mid-flight spawn is orphaned and the
# tick is recorded as a failure that the lane never caused.
set -u
LOG=/tmp/scheduler-cap24-restart.log
exec >> "$LOG" 2>&1
echo "=== cap24 drain-restart $(date -Iseconds) ==="

KEY="$(grep -oE '^API_SERVER_KEY=.*' "$HOME/.hermes/.env" 2>/dev/null | head -1 | cut -d= -f2-)"
[ -n "$KEY" ] || { echo "FATAL: no API_SERVER_KEY in ~/.hermes/.env"; exit 1; }
AUTH="X-Operator-Token: $(sed -n 's/^SCHEDULER_OPERATOR_TOKEN=//p' "$HOME/.hermes/scheduler-auth.env")"
API=http://127.0.0.1:9090

status_field() {  # $1 = json key
  curl -s -H "$AUTH" "$API/api/v1/status" \
    | python3 -c "import sys,json;print(json.load(sys.stdin).get('$1','?'))" 2>/dev/null || echo "?"
}

resume() {  # SCHED-GAP-1756: a resume is only done at HTTP 200 — curl exits 0 on a 401
  code=$(curl -s -o /tmp/.cap24_resume.json -w '%{http_code}' -X POST -H "$AUTH" "$API/api/v1/resume")
  if [ "$code" != "200" ]; then
    echo "!! RESUME FAILED -> HTTP $code $(head -c 160 /tmp/.cap24_resume.json 2>/dev/null)"
    return 1
  fi
  echo "   resumed (HTTP 200)"
}

echo "-- pause (atomic)"
curl -s -X POST -H "$AUTH" "$API/api/v1/pause"; echo
echo "-- drain: waiting for active_ticks=0 (max 60 min)"
for i in $(seq 1 240); do
  AT="$(status_field active_ticks)"
  echo "   $(date -Iseconds) active_ticks=$AT"
  [ "$AT" = "0" ] && break
  sleep 15
done
if [ "$(status_field active_ticks)" != "0" ]; then
  echo "-- DRAIN TIMEOUT after 60 min: resuming and NOT restarting (retry later)"
  resume || { echo "!! RESUME REFUSED — FLEET IS STILL PAUSED"; exit 5; }
  exit 2
fi

echo "-- restart via the user unit (ExecStartPre rebuilds from source)"
systemctl --user restart coding-hermes-scheduler
for i in $(seq 1 24); do
  sleep 5
  CODE="$(curl -s -o /dev/null -w '%{http_code}' "$API/api/v1/health")"
  echo "   $(date -Iseconds) health=$CODE"
  [ "$CODE" = "200" ] && break
done

echo "-- verify"
ps -eo args= -C schedulerd | grep -o -- '--max-concurrent [0-9]*' | head -1 | sed 's/^/   cap: /'
python3 - <<'PY' 2>&1 | sed 's/^/   /'
import sqlite3
c = sqlite3.connect('file:/home/kara/.hermes/coding-hermes/scheduler.db?mode=ro', uri=True)
try:
    print('migration version:', c.execute('PRAGMA user_version').fetchone()[0])
except Exception as e:
    print('user_version error:', e)
try:
    print('board_ownership column:', 'board_ownership' in [r[1] for r in c.execute('PRAGMA table_info(projects)')])
except Exception as e:
    print('table_info error:', e)
print('projects:', c.execute('SELECT COUNT(*) FROM projects WHERE enabled=1').fetchone()[0], 'enabled |',
      'namespaces:', c.execute('SELECT COUNT(*) FROM namespaces').fetchone()[0])
print('coding-hermes max_concurrent:', c.execute("SELECT max_concurrent FROM namespaces WHERE id='coding-hermes'").fetchone()[0])
print('gitreins-poc enabled:', c.execute("SELECT enabled FROM projects WHERE name='gitreins-poc'").fetchone()[0])
PY
echo "-- resume"
resume || { echo "!! RESUME FAILED — fleet may still be paused"; exit 5; }
echo "   readback: paused=$(status_field paused)"
echo "=== done $(date -Iseconds) ==="

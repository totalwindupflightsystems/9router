#!/bin/bash
# FOREMAN DAGGER — tick driver (v1.1). Scheduler-facing entry point.
#
# Input contract (env vars the scheduler / operator passes):
#   FOREMAN_PROJECT    — project name (required; scheduler tick id is
#                        "<project>-YYYY-MM-DD-HH-MM-SS" — project is the
#                        part before the first "-202" suffix)
#   FOREMAN_REPO       — absolute repo/workdir (default /home/kara/<project>)
#   FOREMAN_TICK_ID    — scheduler tick id (optional; logged for traceability)
#   FOREMAN_WORKER_MODEL / FOREMAN_WORKER_PROVIDER — non-binding worker
#                        defaults (optional; the routing registry overrides)
#   REAL_MODE          — 0 (default): dry-run, print spawn command only
#                        1: dispatch the worker via hermes chat -q background
#
# Derived: FOREMAN_BOARD = $FOREMAN_REPO/.coding-hermes/board/tasks.jsonl
#          (falls back to .coding-hermes/tasks.md)
#
# Progress/logging (no Hermes DB needed — follow the files):
#   $FOREMAN_HOME/progress.jsonl  — live per-stage + per-node events
#   $FOREMAN_HOME/last-run.json   — final machine-readable summary
#   /tmp/foreman-run.log          — full dagger execution log (streams)
#   /tmp/foreman-run.jsonl        — dagger node log
set -u
# Scheduler custom-command mode: the daemon runs this with cmd.Dir=workdir and
# no per-project env, so PROJECT derives from PWD when not passed explicitly.
PROJECT="${FOREMAN_PROJECT:-$(basename "$PWD")}"
REPO="${FOREMAN_REPO:-}"
TICK_ID="${FOREMAN_TICK_ID:-}"
REAL_MODE="${REAL_MODE:-0}"
FHOME="${FOREMAN_HOME:-$HOME/.hermes/foreman-dagger}"
mkdir -p "$FHOME"
PROG="$FHOME/progress.jsonl"
SUMMARY="$FHOME/last-run.json"

logp() { echo "{\"ts\":\"$(date -u +%Y-%m-%dT%H:%M:%SZ)\",\"stage\":\"$1\",\"detail\":\"$2\"}" >> "$PROG"; }

# ---- input validation: fail fast with a clear reason ----
if [ -z "$PROJECT" ]; then
  logp "validation" "FOREMAN_PROJECT missing — cannot select the correct foreman"
  echo "FOREMAN DAGGER: FOREMAN_PROJECT is required (scheduler passes tick id '<project>-<ts>')" >&2
  exit 2
fi
[ -z "$REPO" ] && REPO="/home/kara/$PROJECT"
[ -z "$TICK_ID" ] && TICK_ID="$PROJECT-$(date +%Y-%m-%d-%H-%M-%S)"
if [ ! -d "$REPO" ]; then
  logp "validation" "workdir $REPO does not exist"
  echo "FOREMAN DAGGER: workdir $REPO does not exist" >&2
  exit 2
fi
BOARD="$REPO/.coding-hermes/board/tasks.jsonl"
if [ ! -f "$BOARD" ]; then
  BOARD="$REPO/.coding-hermes/tasks.md"
  [ -f "$BOARD" ] || { logp "validation" "no board found under $REPO/.coding-hermes"; echo "FOREMAN DAGGER: no board under $REPO/.coding-hermes (tasks.jsonl or tasks.md)" >&2; exit 2; }
fi
logp "validation" "project=$PROJECT repo=$REPO board=$(basename "$BOARD") tick=$TICK_ID real_mode=$REAL_MODE"

cd /home/kara/hermes-dagger || exit 1
export FOREMAN_PROJECT="$PROJECT"
export FOREMAN_REPO="$REPO"
export FOREMAN_BOARD="$BOARD"
export FOREMAN_TICK_ID="$TICK_ID"
export BOARD_VENV_PY="/home/kara/.hermes/venvs/board/bin/python3"
export REAL_MODE
[ -n "${FOREMAN_WORKER_MODEL:-}" ] && export FOREMAN_WORKER_MODEL
[ -n "${FOREMAN_WORKER_PROVIDER:-}" ] && export FOREMAN_WORKER_PROVIDER
# In-tick judge-rework loop (Bane 2026-09-02): attempts per task (1-10).
# Default 1 = legacy single-shot behavior; the scheduler driver pins the
# fleet default (5). FOREMAN_REWORK_BUDGET_S caps rework wall-clock (default 6600).
[ -z "${FOREMAN_MAX_ATTEMPTS:-}" ] && FOREMAN_MAX_ATTEMPTS=1
export FOREMAN_MAX_ATTEMPTS
[ -n "${FOREMAN_REWORK_BUDGET_S:-}" ] && export FOREMAN_REWORK_BUDGET_S
# Targeted-task pin (decide() reads it; same pattern as QA_TARGETS/PM_TARGETS).
[ -n "${FOREMAN_TARGET_TASK:-}" ] && export FOREMAN_TARGET_TASK
[ -n "${FOREMAN_MODEL:-}" ] && export FOREMAN_MODEL

# DuckBrain write token: the generic all-namespace API key from
# ~/.duckbrain/auth.json (name token-1787620243982); fall back to an env
# override, then the legacy 'hermes' (which has NO grant — the old smoke
# writes were silent no-ops; the pipeline now verifies and fails loud).
# post DB-SUPA-4 auth.json is keyHash-only; plaintext lives in the sidecar
# .token file written at key creation. Fallback: legacy auth.json .key field.
DBK=""
KEYFILE="$HOME/.duckbrain/token-1787620243982.token"
if [ -r "$KEYFILE" ]; then
  DBK=$(tr -d '[:space:]' < "$KEYFILE")
elif [ -f "$HOME/.duckbrain/auth.json" ]; then
  DBK=$(python3 -c "import json;ks=json.load(open('$HOME/.duckbrain/auth.json'))['apiKeys'];print(next((k['key'] for k in ks if k.get('name')=='token-1787620243982'),''))" 2>/dev/null)
fi
[ -z "$DBK" ] && DBK="${DUCKBRAIN_KEY:-}"
[ -z "$DBK" ] && DBK="hermes"
export DUCKBRAIN_KEY="$DBK"

# ── inbound REST bearer token (DAGGER-133 class, 2026-09-12) ──────────
# DAGGER-133 made `dagger serve` fail-closed: with no DAGGER_API_TOKEN, serve
# aborts instantly and the whole pipeline dies before a single node runs
# (foreman pipeline: decide -> 14 nodes skipped). dagger-role-tick.sh was
# patched for this after the 2026-09-12 fleet outage; this PRIMARY driver was
# not, so every dagger primary tick was dying at serve and silently falling
# back to the Hermes prompt foreman - the dagger pipeline never executed.
# Serve AND the `dagger run` client both read DAGGER_API_TOKEN from the process
# env, so a fresh per-run random token exported here authenticates the pair.
# Ephemeral + localhost-only beats a static shared secret; the product's
# fail-closed default stays intact for any serve launched without a wrapper.
#
# The /health probe MUST carry the same bearer: DAGGER-133 wraps the COMPLETE
# mux (bearerAuth, cmd/dagger/main.go) — /health included — and a bare `curl`
# exits 0 on a 401, so a headerless probe can "pass" against an
# unauthenticated/mismatched serve and the real failure only surfaces later
# as a cryptic `dagger run` 401. `-f` + the header make the probe prove the
# token trio (generate -> export -> present) end-to-end.
# Fallback chain: openssl, then /dev/urandom (same as pm-standin-tick.sh).
DAGGER_API_TOKEN="$(openssl rand -hex 32 2>/dev/null || head -c 32 /dev/urandom | od -An -tx1 | tr -d ' \n')"
export DAGGER_API_TOKEN

KEY=$(grep -oE '^GATEWAY_API_KEY=.*' ~/.hermes/.env 2>/dev/null | head -1 | cut -d= -f2-)
[ -z "$KEY" ] && KEY=$(grep -oE '^API_SERVER_KEY=.*' ~/.hermes/.env 2>/dev/null | head -1 | cut -d= -f2-)
[ -z "$KEY" ] && { logp "error" "no GATEWAY_API_KEY/API_SERVER_KEY"; echo "foreman-tick: no gateway key" >&2; exit 1; }

# Per-run isolation (parallel-run safe): unique dir per run (PID + ns) holds
# its own DB, serve log, run log and node log. Never share /tmp names — a
# second run starting mid-flight used to wipe/steal the first's files.
RUN_DIR="/tmp/foreman-${PROJECT}-$$-$(date +%s%N)"
mkdir -p "$RUN_DIR"
DB="$RUN_DIR/run.db"
SERVE_LOG="$RUN_DIR/serve.log"
RUN_LOG="$RUN_DIR/run.log"
RUN_JSONL="$RUN_DIR/run.jsonl"
PORT=""
for _ in $(seq 1 8); do
  CAND=$(( (RANDOM % 4000) + 12000 ))
  if ! ss -ltn 2>/dev/null | grep -q ":$CAND "; then PORT="$CAND"; break; fi
  sleep 0.2
done
[ -n "$PORT" ] || { logp "error" "no free port in 12000-15999"; exit 1; }
env GATEWAY_API_KEY="$KEY" DAGGER_API_TOKEN="$DAGGER_API_TOKEN" ./dagger serve --addr :$PORT --db "$DB" --tier 2 >"$SERVE_LOG" 2>&1 &
SERVE_PID=$!
OK=0
for _ in $(seq 1 25); do
  if curl -s -f -m 2 -K <(printf 'header = "Authorization: Bearer %s"\n' "$DAGGER_API_TOKEN") "http://127.0.0.1:$PORT/health" >/dev/null 2>&1 && kill -0 "$SERVE_PID" 2>/dev/null; then
    OK=1; break
  fi
  sleep 1
done
[ "$OK" = "1" ] || { logp "error" "dagger serve failed on :$PORT"; kill -9 "$SERVE_PID" 2>/dev/null; exit 1; }
logp "serve" "dagger up on :$PORT (db=$DB)"
SERVE_UP=$(date +%s)

# ---- live progress watcher: polls the run log, emits per-node events ----
# Polling (not tail -f pipe): no orphaned processes, exits with the script.
(
  last=0
  while kill -0 "$PPID" 2>/dev/null; do
    new=$(wc -l < "$RUN_LOG" 2>/dev/null || echo 0)
    if [ "$new" -gt "$last" ]; then
      tail -n +$((last + 1)) "$RUN_LOG" 2>/dev/null | while IFS= read -r line; do
        case "$line" in
          *"🏃 Running pipeline"*) logp "pipeline" "start: foreman-pm" ;;
          *"▶ "*" (llm)"*) logp "node_start" "$(echo "$line" | grep -oE '▶ [a-z_]+' | head -1 | cut -d' ' -f2) (llm)" ;;
          *"▶ "*" (tool)"*) logp "node_start" "$(echo "$line" | grep -oE '▶ [a-z_]+' | head -1 | cut -d' ' -f2) (tool)" ;;
          *"▶ "*" (agent)"*) logp "node_start" "$(echo "$line" | grep -oE '▶ [a-z_]+' | head -1 | cut -d' ' -f2) (agent)" ;;
          *"▶ "*" (transform)"*) logp "node_start" "$(echo "$line" | grep -oE '▶ [a-z_]+' | head -1 | cut -d' ' -f2) (transform)" ;;
        esac
      done
      last=$new
    fi
    sleep 1
  done
) &
WATCH_PID=$!

export DAGGER_ENV="FOREMAN_PROJECT=$PROJECT,FOREMAN_REPO=$REPO,FOREMAN_BOARD=$BOARD,FOREMAN_TICK_ID=$TICK_ID,BOARD_VENV_PY=$BOARD_VENV_PY,REAL_MODE=$REAL_MODE,FOREMAN_WORKER_MODEL=${FOREMAN_WORKER_MODEL:-},FOREMAN_WORKER_PROVIDER=${FOREMAN_WORKER_PROVIDER:-},WORKER_DRIVER=${WORKER_DRIVER:-/home/kara/.hermes/scripts/worker-tick.sh},GITREINS_BIN=${GITREINS_BIN:-},DUCKBRAIN_KEY=$DBK,FOREMAN_MAX_ATTEMPTS=$FOREMAN_MAX_ATTEMPTS,FOREMAN_REWORK_BUDGET_S=${FOREMAN_REWORK_BUDGET_S:-},FOREMAN_TARGET_TASK=${FOREMAN_TARGET_TASK:-},FOREMAN_MODEL=${FOREMAN_MODEL:-}"
env GATEWAY_API_KEY="$KEY" DAGGER_API_TOKEN="$DAGGER_API_TOKEN" ./dagger run examples/coding-hermes/foreman.ts --server "http://127.0.0.1:$PORT" \
  --log-file "$RUN_JSONL" --log-level info >"$RUN_LOG" 2>&1
RUN_RC=$?
if grep -q "Failed: 0" "$RUN_LOG" 2>/dev/null; then
  RUN_RC=0
fi
RUN_END=$(date +%s)
kill "$WATCH_PID" 2>/dev/null
wait "$WATCH_PID" 2>/dev/null
logp "pipeline" "finished rc=$RUN_RC duration=$((RUN_END - SERVE_UP))s"

# ---- post-run: per-node statuses from the run log table into progress ----
python3 - "$PROG" "$RUN_LOG" <<'PYEOF'
import json, os, sys
prog, run_log = sys.argv[1], sys.argv[2]
log = open(run_log).read()
NODES = ('self_heal', 'read_board', 'decide', 'discovery_sweep', 'self_pause_check',
         'route_worker', 'duckbrain_recall', 'workflow_design', 'compose_brief',
         'spawn', 'wait_worker', 'guard',
         'judge', 'commit', 'bookkeep', 'off_by_one', 'duckbrain_narrate',
         'duckbrain_write', 'signals', 'report')
lines = log.splitlines()
for i, line in enumerate(lines):
    if line.strip().startswith('NODE') and 'TYPE' in line:
        for row in lines[i + 2:]:
            if not row.strip():
                break
            parts = row.split()
            if len(parts) >= 3 and parts[0] in NODES:
                node, ntype, status = parts[0], parts[1], parts[2]
                with open(prog, 'a') as f:
                    f.write(json.dumps({"ts": __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat() + 'Z',
                                        "stage": "node_end", "detail": f"{node} ({ntype}) {status}"}) + "\n")
        break
PYEOF

# ---- final summary (written ALWAYS — a failed tick still needs a
#      machine-readable record; the old code only wrote it on success,
#      so a broken run left NOTHING dependable behind) ----
python3 - "$SUMMARY" "$PROG" "$PROJECT" "$RUN_LOG" "$RUN_RC" "$TICK_ID" <<'PYEOF'
import json, os, re, sys
summary_path, prog, project, run_log, rc, tick = sys.argv[1:7]
log = open(run_log).read()
total = re.search(r'Total time: ([0-9hms.]+) \| Passed: (\d+) \| Failed: (\d+)', log)
nodes = []
NODES = ('self_heal', 'read_board', 'decide', 'discovery_sweep', 'self_pause_check',
         'route_worker', 'duckbrain_recall', 'workflow_design', 'compose_brief',
         'spawn', 'wait_worker', 'guard',
         'judge', 'commit', 'bookkeep', 'off_by_one', 'duckbrain_narrate',
         'duckbrain_write', 'signals', 'report')
lines = log.splitlines()
for i, line in enumerate(lines):
    if line.strip().startswith('NODE') and 'TYPE' in line:
        for row in lines[i + 2:]:
            if not row.strip():
                break
            parts = row.split()
            if len(parts) >= 3 and parts[0] in NODES:
                nodes.append({"node": parts[0], "type": parts[1], "status": parts[2]})
        break
summary = {
    "project": project,
    "tick": tick,
    "rc": int(rc) if str(rc).isdigit() else None,
    "passed": int(total.group(2)) if total else None,
    "failed": int(total.group(3)) if total else None,
    "total_time": total.group(1) if total else None,
    "nodes": nodes,
    "progress_file": prog,
}
json.dump(summary, open(summary_path, "w"), indent=1)
# Per-tick machine record next to the human report (dependable history,
# not just the latest-run overwrite).
os.makedirs(os.path.dirname(summary_path) + "/reports", exist_ok=True)
json.dump(summary, open(os.path.dirname(summary_path) + "/reports/" + tick + ".json", "w"), indent=1)
PYEOF

# ---- final human report (delivered verbatim to Telegram + saved to a
#      durable per-tick file — the Telegram message is ephemeral, the
#      report file is the dependable copy) ----
REPORT_DIR="$FHOME/reports"
mkdir -p "$REPORT_DIR"
REPORT_FILE="$REPORT_DIR/$TICK_ID.txt"
python3 /home/kara/.hermes/scripts/dagger-tick-report.py "$DB" "$RUN_LOG" "$PROJECT" "$TICK_ID" "$BOARD" "$RUN_RC" | tee "$REPORT_FILE"
if [ "$RUN_RC" -ne 0 ]; then
  { echo "⚠ pipeline exit $RUN_RC — full log: $RUN_LOG"; tail -25 "$RUN_LOG"; } | tee -a "$REPORT_FILE"
fi
# Light retention: keep per-tick reports 30 days, then let them go.
find "$REPORT_DIR" -name '*.txt' -mtime +30 -delete 2>/dev/null
find "$REPORT_DIR" -name '*.json' -mtime +30 -delete 2>/dev/null
kill -9 "$SERVE_PID" 2>/dev/null
wait "$SERVE_PID" 2>/dev/null
exit 0

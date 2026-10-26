#!/bin/bash
# WORKER TICK DRIVER — runs the worker-pm pipeline against a brief file.
# Env: WORKER_BRIEF_FILE (required), WORKER_REPO, WORKER_MODEL, WORKER_PROVIDER,
#      REAL_MODE (0 default). Writes <brief>.done marker when finished.
# Fresh serve + fresh DB per run (checkpoint replay rule).

set -u
BRIEF="${WORKER_BRIEF_FILE:-}"
[ -z "$BRIEF" ] && echo "WORKER_BRIEF_FILE required" >&2 && exit 2
[ -f "$BRIEF" ] || { echo "brief file not found: $BRIEF" >&2; exit 2; }

REPO="${WORKER_REPO:-/home/kara/ring-runner}"
REAL="${REAL_MODE:-0}"
# Per-run isolation (parallel-run safe): unique dir (pid+ns) with own DB,
# serve log and run log. Never share /tmp names — parallel foreman runs
# spawn workers concurrently; shared worker-*.db/.log cross-fed state
# (same class as the foreman-tick.sh contamination, fixed 2026-08-27).
RUN_DIR="/tmp/worker-${REPO##*/}-$$-$(date +%s%N)"
mkdir -p "$RUN_DIR"
DB="$RUN_DIR/run.db"
LOG="$RUN_DIR/run.log"
SERVE_LOG="$RUN_DIR/serve.log"
PORT=""
for _ in $(seq 1 8); do
  CAND=$(( (RANDOM % 4000) + 12000 ))
  if ! ss -ltn 2>/dev/null | grep -q ":$CAND "; then PORT="$CAND"; break; fi
  sleep 0.2
done
[ -n "$PORT" ] || { echo "worker-tick: no free port in 12000-15999" >&2; exit 1; }
# Resolve DAGGER_BIN via PATH (command -v) or env, falling back to canonical path.
if [ -z "$DAGGER_BIN" ]; then
  _dagger=$(command -v dagger 2>/dev/null || echo "")
  if [ -n "$_dagger" ]; then
    DAGGER_BIN="$_dagger"
  else
    DAGGER_BIN="/home/kara/Hermes-DAGger/hermes-dagger/dagger"
  fi
fi
# Resolve PIPELINE path relative to DAGGER_HOME.
_PIPELINE_BASE="$(dirname "$DAGGER_BIN")/../examples/coding-hermes/worker.ts"
PIPELINE="${WORKER_PIPELINE:-$_PIPELINE_BASE}"
unset _PIPELINE_BASE

# gateway key for llm()/agent() calls through the serve path
KEY=$(grep -oE '^GATEWAY_API_KEY=.*' ~/.hermes/.env 2>/dev/null | head -1 | cut -d= -f2-)
[ -z "$KEY" ] && KEY=$(grep -oE '^API_SERVER_KEY=.*' ~/.hermes/.env 2>/dev/null | head -1 | cut -d= -f2-)
[ -z "$KEY" ] && { echo "worker-tick: no gateway key" >&2; exit 1; }
export GATEWAY_API_KEY="$KEY"

echo "WORKER DAGGER — TICK ($(date -u +%Y-%m-%dT%H:%MZ)) repo=$REPO real_mode=$REAL"
echo "brief: $BRIEF"
echo "progress marker: ${BRIEF%.txt}.done"

export DAGGER_ENV="WORKER_BRIEF_FILE=$BRIEF,WORKER_REPO=$REPO,REAL_MODE=$REAL"
[ -n "${WORKER_MODEL:-}" ] && export DAGGER_ENV="$DAGGER_ENV,WORKER_MODEL=$WORKER_MODEL"
[ -n "${WORKER_PROVIDER:-}" ] && export DAGGER_ENV="$DAGGER_ENV,WORKER_PROVIDER=$WORKER_PROVIDER"
[ -n "${GITREINS_BIN:-}" ] && export DAGGER_ENV="$DAGGER_ENV,GITREINS_BIN=$GITREINS_BIN"

# Tool-executor model (Bane 2026-08-31): the worker pipeline's raw tool()
# calls (terminal/git/search) spawn mini-agents on the gateway. The foreman
# passes WORKER_MODEL as "provider/model" (router-resolved, or the
# deepseek-foreman fail-open); without exporting it here the worker's serve
# process has no DAGGER_TOOL_MODEL and every tool() call bills the gateway
# DEFAULT (deepseek PAYG primary key). Same contract as
# scheduler-foreman-tick.sh.
# DAGGER-130 fail-closed (2026-09-14): an unset lane is no longer "use the
# bridge default" — the bridge rejects it before egress. Fail here instead,
# before the serve process is started.
if [ -z "${WORKER_MODEL:-}" ]; then
  # PAYG ULTIMATE FALLBACK (Bane 2026-09-19): same contract as
  # scheduler-foreman-tick.sh — DAGGER-130's defect was SILENT mis-billing,
  # not refusal. Log loudly, then continue on the dedicated PAYG key.
  echo "worker-tick: WARN: WORKER_MODEL empty — PAYG ULTIMATE deepseek-foreman/deepseek-flash (loud, not silent; DAGGER-130 softened by Bane directive)." >&2
  export WORKER_MODEL="deepseek-foreman/deepseek-flash"
fi
export DAGGER_TOOL_MODEL="$WORKER_MODEL"

# ── inbound REST bearer token (DAGGER-133 class, 2026-09-12) ──────────
# DAGGER-133 made `dagger serve` fail-closed: with no DAGGER_API_TOKEN the
# serve process aborts in ~1s and the whole worker pipeline never runs. Both
# serve AND the `dagger run` client read the token from the process env, so a
# fresh ephemeral per-run value exported here authenticates the pair. Same
# remedy as dagger-role-tick.sh (fleet outage 2026-09-12). Found unpatched on
# 2026-09-20 while fixing the sibling defect in foreman-tick.sh.
DAGGER_API_TOKEN="$(openssl rand -hex 32)"
export DAGGER_API_TOKEN


# fresh serve on a free port
env GATEWAY_API_KEY="$KEY" "$DAGGER_BIN" serve --addr ":$PORT" --db "$DB" --tier 2 >"$SERVE_LOG" 2>&1 &
SERVE_PID=$!
for i in $(seq 1 30); do
  curl -s -o /dev/null "http://localhost:$PORT/health" && break
  sleep 1
done

env GATEWAY_API_KEY="$KEY" "$DAGGER_BIN" run --server "http://localhost:$PORT" "$PIPELINE" > "$LOG" 2>&1
RC=$?
kill -9 "$SERVE_PID" 2>/dev/null
wait "$SERVE_PID" 2>/dev/null

echo "=== worker run log tail ==="
tail -30 "$LOG"
echo "WORKER_TICK_EXIT=$RC"

# done marker for the foreman's wait_worker node
echo "rc=$RC" > "${BRIEF%.txt}.done"
exit $RC

#!/bin/bash
# qa-scheduler-tick.sh — scheduler custom-command tick for the QA dagger
# (Bane cutover 2026-09-01). Spawned by coding-hermes-scheduler as the
# qa-audit project's command — THE SCHEDULER owns the timer/cooldown.
#
#   - RANDOM-DISCOVERY mode by default: qa_discover.py picks N projects
#     (never-QA'd first, oldest-first, random tiebreak); each pick carries
#     its REAL workdir from the scheduler DB (names ≠ paths).
#   - QA_TARGETS env overrides to targeted mode for a specific project.
#   - REAL_MODE=1: findings become REAL board rows (QA-<PROJ>-NNN) and QA
#     summaries land in the dedicated DuckBrain 'qa' namespace.
#   - DAGGER_TOOL_MODEL routed per project profile (never gateway default).
set -u

PROJECT="${CODING_HERMES_PROJECT:-qa-audit}"
TICK="${CODING_HERMES_TICK:-manual-$(date +%s)}"
export REAL_MODE="${REAL_MODE:-1}"
export QA_DISCOVER_N="${QA_DISCOVER_N:-2}"
export DUCKBRAIN_NS="${DUCKBRAIN_NS:-qa}"
# JIT bunker per target is the point of QA; leave QA_SKIP_BUNKER unset
# unless the operator explicitly wants the fast local probe.
export QA_SKIP_BUNKER="${QA_SKIP_BUNKER:-0}"

# Row-name contract (Bane 09-01): "<project>-qa" → targeted at that project.
# "qa-audit" (no suffix) → random-discovery mode.
QA_ROW_TARGET=""
case "$PROJECT" in
  qa-audit) ;;
  *-qa)
    QA_ROW_TARGET="${PROJECT%-qa}"
    # Skip rows whose base project has no workdir (never run junk targets)
    BASE_WD=""
    if [ -f "$HOME/.hermes/coding-hermes/scheduler.db" ] && [ -n "$QA_ROW_TARGET" ]; then
      BASE_WD=$(sqlite3 "$HOME/.hermes/coding-hermes/scheduler.db" \
        "SELECT workdir FROM projects WHERE name='$QA_ROW_TARGET' LIMIT 1;" 2>/dev/null | head -1)
    fi
    case "$QA_ROW_TARGET" in
      ai-plays-poke) BASE_WD="/home/kara/ai_plays_poke" ;;
    esac
    if [ -z "$BASE_WD" ] || [ ! -d "$BASE_WD" ]; then
      echo "QA TICK $TICK — SKIP: target '$QA_ROW_TARGET' has no workdir"
      exit 0
    fi
    ;;
esac

cd /home/kara/.hermes/stand-in/pm/qa 2>/dev/null || mkdir -p /home/kara/.hermes/stand-in/pm/qa && cd /home/kara/.hermes/stand-in/pm/qa

# Targeted override (single project per scheduler row convention)
if [ -n "${CODING_HERMES_QA_TARGET:-}" ]; then
  export QA_TARGETS="$CODING_HERMES_QA_TARGET"
elif [ -n "$QA_ROW_TARGET" ]; then
  export QA_TARGETS="$QA_ROW_TARGET"
fi

bash /home/kara/.hermes/scripts/dagger-role-tick.sh qa "${QA_TARGETS:-}" ""
RC=$?
# SCHED-GAP-128: collapse the fleet-infra copies this tick may have filed on
# project boards into the ONE shared-infra row (idempotent; the sweep always
# exits 0 so a consolidation fault never fails the tick). Resolution order:
# explicit override → the scheduler checkout's committed wrapper. Until that
# lands the step is a silent no-op, which is why the grep in the row's AC is
# re-checked after the NEXT qa tick rather than assumed.
FLEET_INFRA_SWEEP="${FLEET_INFRA_SWEEP:-/home/kara/coding-hermes-scheduler/coding-herms-scheduler/ops/fleet-infra-sweep.sh}"
if [ -x "$FLEET_INFRA_SWEEP" ]; then
  "$FLEET_INFRA_SWEEP" || true
fi
exit $RC

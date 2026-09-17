#!/bin/bash
# Watchdog: fleet config regression suites. Silent on success (no_agent cron);
# prints failure output + exit 1 on regression.
# Suites:
#   1) test_fleet_cooldown_policy.py   — fleet.toml namespace preservation
#   2) test_registry_completeness.py   — fleet.toml projects ⊆ router registry
#   3) test_fleet_enabled_consistency.py — fleet.toml enabled state == API (stale-pin guard)
#   4) routing-billing-guard.py        — api_server sessions billed to the PAYG
#      gateway default = the provider-field leak (Bane 2026-08-31). Scans the
#      last 6h; post-fix, dagger agent/llm/tool traffic MUST bill sub lanes.
FAILED=0

OUT=$(~/.hermes/venvs/board/bin/python3 ~/.hermes/scripts/test_fleet_cooldown_policy.py 2>&1)
RC=$?
if [ $RC -ne 0 ]; then
  echo "FLEET-TOML REGRESSION: fleet-cooldown-policy.py namespace preservation test FAILED:"
  echo "$OUT"
  FAILED=1
fi

OUT=$(~/.hermes/venvs/board/bin/python3 ~/.hermes/scripts/test_registry_completeness.py 2>&1)
RC=$?
if [ $RC -ne 0 ]; then
  echo "REGISTRY COMPLETENESS REGRESSION: a fleet.toml project is missing from the task-router registry:"
  echo "$OUT"
  FAILED=1
fi

OUT=$(~/.hermes/venvs/board/bin/python3 ~/.hermes/scripts/test_fleet_enabled_consistency.py 2>&1)
RC=$?
if [ $RC -ne 0 ]; then
  echo "ENABLED-STATE DRIFT: fleet.toml enabled pins diverge from the live API (next restart will flip projects):"
  echo "$OUT"
  FAILED=1
fi

# Suite 4: routing-billing guard. A provider-field leak bills api_server
# sessions on the gateway PAYG default (deepseek). Rolling 24h window (the
# DAGGER-130 PASS criterion): this cron fires daily at 05:30, so any fresh
# leak is caught within 24h. Historical: a fixed --since baseline
# (1788238790, 2026-08-31 seed) re-flagged the closed Sep 2-3 tail (30
# sessions, doc-writer/release-engineer weekly lanes, tracked as DAGGER-130)
# forever — alarm fatigue with zero fresh-regression value. Proven resolved
# 2026-09-04: guard --hours 24 exits 0 while 9.8k api_server sessions/24h
# bill sub lanes (custom/ollama-cloud/opencode-go/openai-codex).
OUT=$(~/.hermes/venvs/board/bin/python3 ~/.hermes/scripts/routing-billing-guard.py --hours 24 2>&1)
RC=$?
if [ $RC -ne 0 ]; then
  echo "ROUTING-BILLING REGRESSION: api_server sessions billed on the PAYG gateway default:"
  echo "$OUT"
  FAILED=1
fi

exit $FAILED

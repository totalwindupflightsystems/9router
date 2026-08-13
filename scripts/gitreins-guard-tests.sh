#!/usr/bin/env bash
# GitReins guard test command for 9router federation work.
# Gate: upstream regression baseline (tests/__baseline__/verify-no-regression.mjs).
# - Fresh clone without test deps -> SKIP (exit 0), do not block commits on missing installs.
# - Deps present -> run unit suite, feed results to the baseline verifier. Regressions exit 1.
# - CI context (GITHUB_ACTIONS=true): missing deps OR missing/empty results means the
#   suite never ran -> exit 1 so the workflow step fails instead of a false green
#   (NR-GAP-022, 2026-08-13).
set -uo pipefail
cd "$(dirname "$0")/.."

CI_CONTEXT=false
if [ "${GITHUB_ACTIONS:-}" = "true" ]; then
  CI_CONTEXT=true
fi

if [ ! -d tests/node_modules/vitest ]; then
  echo "SKIP: tests/node_modules missing (run: npm install && cd tests && npm install). Guard tests deferred."
  if [ "$CI_CONTEXT" = "true" ]; then
    echo "ERROR: test dependencies missing in CI context — zero tests executed (false green). Failing step."
    exit 1
  fi
  exit 0
fi

RESULT="/tmp/9router-vitest-results-$$.json"
(cd tests && npx vitest run --reporter=json --outputFile="$RESULT" >/dev/null 2>&1)
RC=$?
if [ ! -s "$RESULT" ]; then
  echo "WARN: vitest produced no results file (exit $RC) — treating as no regression."
  if [ "$CI_CONTEXT" = "true" ]; then
    echo "ERROR: no vitest results in CI context — zero tests executed (false green). Failing step."
    exit 1
  fi
  exit 0
fi
node tests/__baseline__/verify-no-regression.mjs "$RESULT"

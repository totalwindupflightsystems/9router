#!/usr/bin/env bash
# Run ONE cell of an emitted bunker qa-run.sh VERBATIM, with the battery's outer
# helpers stubbed — so a harness edit is proven against the code that ships, with
# no bunker agent and no full battery.
#
# usage: ui-probe-arm-rig.sh <emitted-qa-run.sh | arm-file> <repo-dir> [--arm-only]
#   <emitted-qa-run.sh>  output of `bunker-qa.sh __gen-remote <repo>`
#   --arm-only           the first arg is already just the arm (no preamble to extract)
#
# env: RIG_BIN=<start command the battery would use, e.g. "go run ./cmd/app">
#      plus whatever the app needs to boot (its own env vars).
#
# Prints one `CELL|ui-probe|<status>|<detail>` line — grade from that line, never
# from the exit code of the app under test.
set -uo pipefail
SRC=$1; REPO=$2; MODE=${3:-}
RIG=$(mktemp /tmp/qa-arm-rig.XXXXXX.sh)
LOGD=$(mktemp -d /tmp/qa-arm-logs.XXXXXX)
{
  echo '#!/usr/bin/env bash'
  echo 'set -uo pipefail'
  if [ "$MODE" != "--arm-only" ]; then
    # the arm's own helper preamble (ui_pat_compiles / ui_go_http_source …), taken
    # from the emitted battery itself
    sed -n '/^ui_pat_compiles() {/,/^if \[ -f package.json \] && grep -qE/p' "$SRC" | head -n -1
    # the cell body: from its section marker to the next cell's marker
    sed -n '/^# 5 · ui-probe$/,/^# 6 · /p' "$SRC" | head -n -1
  else
    cat "$SRC"
  fi
} > "$RIG"
chmod +x "$RIG"
cd "$REPO" || exit 1
export LOGD
cell() { printf 'CELL|%s|%s|%s\n' "$1" "$2" "$3"; }
export -f cell
export BIN="${RIG_BIN:-}"
bash -n "$RIG" || { echo "RIG SYNTAX ERROR — the emitted code does not parse"; exit 2; }
bash "$RIG"
rc=$?
echo "RIG_RC=$rc"
rm -f "$RIG"

#!/usr/bin/env bash
# test-drain-resolved-dedupe.sh — fixture acceptance test for MON-GAP-032.
#
# Defect: alert-resolved rows are WRITTEN to events.jsonl by the drain's apply loop, but the
# classifier deduped ids against tasks.jsonl only. A second run therefore re-appended every
# -RESOLVED spool line (measured on the live board 2026-10-23: 235 resolved event lines for
# 13 unique ids).
#
# Acceptance: a resolved row lands ONCE. Run the drain twice over the same cumulative spool —
# run 1 appends=1, run 2 appends=0 — and events.jsonl holds exactly one line for the id.
#
# Offline: no network. rsync is stubbed on PATH (the spool fetch), the appender is a fixture.
#
#   bash test-drain-resolved-dedupe.sh [path-to-drain-board-rows.sh]
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DRAIN="${1:-$HERE/drain-board-rows.sh}"
pass=0; fail=0
ok()   { printf 'PASS %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got '$2' want '$3')"; fi; }

bash -n "$DRAIN" || { echo "FAIL bash -n $DRAIN"; exit 1; }

T=$(mktemp -d /tmp/mon-gap032-test.XXXXXX)
trap 'rm -rf "$T"' EXIT

BIN="$T/bin"; mkdir -p "$BIN"
cat > "$BIN/rsync" <<'RS'
#!/usr/bin/env bash
dest="${@: -1}"
mkdir -p "$dest"
cp -a "$FIXTURE_SPOOL_SRC"/. "$dest"/ 2>/dev/null || true
RS
chmod +x "$BIN/rsync"

cat > "$T/appender.py" <<'AP'
#!/usr/bin/env python3
import sys
path, row = sys.argv[1], sys.argv[2]
with open(path, "a", encoding="utf-8") as fh:
    fh.write(row.rstrip("\n") + "\n")
print("APPENDED=1")
AP
chmod +x "$T/appender.py"

R="$T/root"; mkdir -p "$R/src" "$R/spool" "$R/board/monitoring/.coding-hermes/board"
BD="$R/board/monitoring/.coding-hermes/board"
: > "$BD/tasks.jsonl"
: > "$BD/events.jsonl"

# one resolution event (the row shape alert-router spools) + one unrelated firing row
printf '{"id":"MON-MONITORING-TESTFP01-20261023-RESOLVED","type":"alert-resolved","lane":"monitoring","alertname":"DiskFull","host":"bunker-mvp","resolved_at":"2026-10-23 01:00:00","endsAt":"2026-10-23T01:00:00Z"}\n' > "$R/src/board-rows.jsonl"
printf '{"id":"MON-MONITORING-TESTFP02-20261023","lane":"monitoring","title":"[WARNING] x","status":"pending","reasoning":"labels: {\\"alertname\\": \\"DiskFull\\", \\"host\\": \\"bunker-mvp\\"}\\n","created_at":"2026-10-23T00:00:00Z"}\n' >> "$R/src/board-rows.jsonl"

printf '{"data":{"alerts":[]}}\n' > "$R/alerts.json"

run() {
  PATH="$BIN:$PATH" FIXTURE_SPOOL_SRC="$R/src" MON_REMOTE=fake \
  BOARD_ROOT="$R/board" SPOOL="$R/spool" BOARD_APPEND="$T/appender.py" DRY=0 \
  ALERTS_FILE="$R/alerts.json" \
    bash "$DRAIN" >"$R/out.$1" 2>"$R/err.$1"
  grep -E '^drained:' "$R/out.$1" | tail -1
}

out1=$(run 1); out2=$(run 2)

check "run1 appends the resolution event + firing row"  "$(printf '%s' "$out1" | grep -o 'appended=[0-9]*' | head -1)" "appended=2"
check "run1 also lands the firing row"          "$(grep -c 'MON-MONITORING-TESTFP02-20261023' "$BD/tasks.jsonl")" "1"
check "run1 writes one resolved event line"     "$(grep -c 'TESTFP01-20261023-RESOLVED' "$BD/events.jsonl")" "1"
check "run2 appends nothing (idempotent)"       "$(printf '%s' "$out2" | grep -o 'appended=[0-9]*' | head -1)" "appended=0"
check "run2 leaves events.jsonl byte-count"     "$(grep -c 'TESTFP01-20261023-RESOLVED' "$BD/events.jsonl")" "1"
check "run2 does not duplicate the firing row"  "$(grep -c 'MON-MONITORING-TESTFP02-20261023' "$BD/tasks.jsonl")" "1"

# a resolved row for a NEW fingerprint must still land (the fix must not suppress real events)
printf '{"id":"MON-MONITORING-TESTFP03-20261023-RESOLVED","type":"alert-resolved","lane":"monitoring","alertname":"DiskFull","host":"bunker-mvp","endsAt":"2026-10-23T02:00:00Z"}\n' >> "$R/src/board-rows.jsonl"
out3=$(run 3)
check "run3 appends only the new resolution"    "$(printf '%s' "$out3" | grep -o 'appended=[0-9]*' | head -1)" "appended=1"
check "run3 events.jsonl holds both ids once"   "$(grep -c 'MON-MONITORING-TESTFP0[13]-20261023-RESOLVED' "$BD/events.jsonl")" "2"

# legacy storage: a resolution event recorded ONLY on tasks.jsonl (89 such rows on the live
# board) must be treated as already-recorded, NOT backfilled into events.jsonl.
printf '{"id":"MON-MONITORING-TESTFP09-20261006-RESOLVED","lane":"monitoring","title":"legacy","status":"complete"}\n' >> "$BD/tasks.jsonl"
printf '{"id":"MON-MONITORING-TESTFP09-20261006-RESOLVED","type":"alert-resolved","lane":"monitoring","alertname":"DiskFull","host":"bunker-mvp","endsAt":"2026-10-06T01:00:00Z"}\n' >> "$R/src/board-rows.jsonl"
out4=$(run 4)
check "run4 does not backfill a legacy resolution" "$(printf '%s' "$out4" | grep -o 'appended=[0-9]*' | head -1)" "appended=0"
check "run4 leaves events.jsonl at 2 ids"          "$(grep -c 'RESOLVED' "$BD/events.jsonl")" "2"

# concurrency guard (MON-GAP-032b): a drain that cannot take the lock must exit rc=3 and append
# nothing, so two racing runs cannot double-append the same row. The holder runs the drain from
# inside its own locked subshell, which is exactly the race the guard exists for.
LOCKFILE="$R/lock.test"
before_events=$(wc -l < "$BD/events.jsonl")
(
  exec 9>"$LOCKFILE"
  flock 9
  PATH="$BIN:$PATH" FIXTURE_SPOOL_SRC="$R/src" MON_REMOTE=fake \
  BOARD_ROOT="$R/board" SPOOL="$R/spool" BOARD_APPEND="$T/appender.py" DRY=0 \
  ALERTS_FILE="$R/alerts.json" DRAIN_LOCK="$LOCKFILE" \
    bash "$DRAIN" >"$R/out.lock" 2>&1
  echo "rc=$?" >"$R/rc.lock"
)
check "locked drain refuses with rc=3"          "$(cat "$R/rc.lock")" "rc=3"
check "locked drain appends nothing"            "$(wc -l < "$BD/events.jsonl")" "$before_events"
check "locked drain says why"                   "$(grep -c 'another drain already holds' "$R/out.lock")" "1"

printf '\n%d passed, %d failed\n' "$pass" "$fail"
[ "$fail" -eq 0 ] || exit 1

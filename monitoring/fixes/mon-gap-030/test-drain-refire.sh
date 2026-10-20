#!/usr/bin/env bash
# test-drain-refire.sh — fixture acceptance test for the MON-GAP-030 re-fire rule.
#
# Offline: no network, all writes inside one mktemp -d. Stubs `rsync` on PATH (the drain's
# spool fetch) and supplies a one-line-append fixture appender, because the drain invokes
# `python3 "$BOARD_APPEND"` exactly as it does the real board_append.py.
#
#   bash test-drain-refire.sh [path-to-drain-board-rows.sh]
set -uo pipefail

HERE=$(cd "$(dirname "$0")" && pwd)
DRAIN="${1:-$HERE/drain-board-rows.sh}"
pass=0; fail=0
ok()   { printf 'PASS %s\n' "$1"; pass=$((pass+1)); }
bad()  { printf 'FAIL %s\n' "$1"; fail=$((fail+1)); }
check(){ if [ "$2" = "$3" ]; then ok "$1"; else bad "$1 (got '$2' want '$3')"; fi; }

bash -n "$DRAIN" || { echo "FAIL bash -n $DRAIN"; exit 1; }
TODAY=$(date -u +%Y%m%d)

T=$(mktemp -d /tmp/mon-gap030-test.XXXXXX)
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

# ---------------------------------------------------------------- fixtures
mkroot() {                       # $1 = case dir
  local r="$T/$1"
  mkdir -p "$r/src" "$r/spool" "$r/board/monitoring/.coding-hermes/board"
  : > "$r/board/monitoring/.coding-hermes/board/tasks.jsonl"
  printf '%s' "$r"
}

firing_row() {                   # id alertname host created_at
  printf '{"id":"%s","lane":"monitoring","title":"[CRITICAL] %s on %s","status":"pending","reasoning":"desc\\n\\nFIRED 2026-10-20T15:15:55Z\\nlabels: {\\"alertname\\": \\"%s\\", \\"host\\": \\"%s\\", \\"severity\\": \\"critical\\"}\\n","created_at":"%s"}\n' \
    "$1" "$2" "$3" "$2" "$3" "$4"
}
resolved_row() {                 # id
  printf '{"id":"%s-RESOLVED","type":"alert-resolved","lane":"monitoring","alertname":"DiskFull","host":"bunker-mvp","resolved_at":"2026-10-20 15:20:00","endsAt":"2026-10-20T15:20:00Z"}\n' "$1"
}
board_row() {                    # id status
  printf '{"id":"%s","lane":"monitoring","title":"closed","status":"%s"}\n' "$1" "$2"
}
alerts_file() {                  # file ...alertname/host pairs as AN:host
  local f="$1"; shift
  { printf '{"data":{"alerts":['
    local first=1
    for pair in "$@"; do
      [ $first -eq 1 ] || printf ','
      first=0
      printf '{"labels":{"alertname":"%s","host":"%s"},"status":{"state":"firing"}}' "${pair%%:*}" "${pair##*:}"
    done
    printf ']}}\n'
  } > "$f"
}

run() {                          # dir -> runs the drain, echoes "appended=X refire=Y"
  local r="$1"
  PATH="$BIN:$PATH" FIXTURE_SPOOL_SRC="$r/src" MON_REMOTE=fake \
  BOARD_ROOT="$r/board" SPOOL="$r/spool" BOARD_APPEND="$T/appender.py" DRY=0 \
  ALERTS_FILE="${2:-$r/alerts.json}" \
    bash "$DRAIN" >"$r/out" 2>"$r/stderr"
  tail -3 "$r/out"
}

count_id() { grep -c "\"id\":\"$2\"" "$1" 2>/dev/null || true; }

# ---------------------------------------------------------------- 1a: re-fire
r=$(mkroot 1a)
ID1="MON-MONITORING-AA11BB22-$TODAY"
board_row "$ID1" complete   > "$r/board/monitoring/.coding-hermes/board/tasks.jsonl"
firing_row "$ID1" DiskFull bunker-mvp "2026-10-20 15:15:55" > "$r/src/board-rows.jsonl"
alerts_file "$r/alerts.json" "DiskFull:bunker-mvp"
out=$(run "$r")
check "1a appended exactly one row for $ID1" "$(count_id "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" "$ID1")" 2
case "$out" in *"refire=1"*) ok "1a counter reports refire=1";; *) bad "1a counter reports refire=1 ($out)";; esac
grep -q "appended X-1 (refire)" "$r/stderr" 2>/dev/null || true

# ---------------------------------------------------------------- 1b: idempotent
out=$(run "$r")
case "$out" in *"appended=0"*) ok "1b second run appends nothing";; *) bad "1b second run appends nothing ($out)";; esac
check "1b board unchanged on second run" "$(count_id "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" "$ID1")" 2

# ---------------------------------------------------------------- 2: open row dedupes
r=$(mkroot 2)
board_row Y-1 pending > "$r/board/monitoring/.coding-hermes/board/tasks.jsonl"
firing_row Y-1 DiskFull bunker-mvp "2026-10-20 15:15:55" > "$r/src/board-rows.jsonl"
alerts_file "$r/alerts.json" "DiskFull:bunker-mvp"
out=$(run "$r")
check "2 open row dedupes (no append)" "$(count_id "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" Y-1)" 1
case "$out" in *"appended=0"*) ok "2 counter appended=0";; *) bad "2 counter appended=0 ($out)";; esac

# ---------------------------------------------------------------- 3: brand-new id
r=$(mkroot 3)
firing_row Z-9 DiskFull bunker-mvp "2026-10-20 15:15:55" > "$r/src/board-rows.jsonl"
alerts_file "$r/alerts.json" "DiskFull:bunker-mvp"
out=$(run "$r")
check "3 new id appended once" "$(count_id "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" Z-9)" 1
case "$out" in *"appended=1"*) ok "3 counter appended=1";; *) bad "3 counter appended=1 ($out)";; esac

# ---------------------------------------------------------------- 4: flap batch -> newest only
r=$(mkroot 4)
board_row F-1 complete > "$r/board/monitoring/.coding-hermes/board/tasks.jsonl"
{ firing_row F-1 DiskFull bunker-mvp "2026-10-20 13:03:55"
  resolved_row F-1
  firing_row F-1 DiskFull bunker-mvp "2026-10-20 14:07:55"
  resolved_row F-1
  firing_row F-1 DiskFull bunker-mvp "2026-10-20 15:15:55"
} > "$r/src/board-rows.jsonl"
alerts_file "$r/alerts.json" "DiskFull:bunker-mvp"
out=$(run "$r")
check "4 exactly one row appended for the flapping id" "$(count_id "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" F-1)" 2
grep -q '2026-10-20 15:15:55' "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" \
  && ok "4 the appended re-fire row is the NEWEST firing row" \
  || bad "4 the appended re-fire row is the NEWEST firing row"
case "$out" in *"refire=1"*) ok "4 counter refire=1";; *) bad "4 counter refire=1 ($out)";; esac

# ---------------------------------------------------------------- 5: no board for lane
r=$(mkroot 5)
firing_row N-1 DiskFull bunker-mvp "2026-10-20 15:15:55" > "$r/src/board-rows.jsonl"
python3 - "$r/src/board-rows.jsonl" <<'PY'
import sys
p = sys.argv[1]
raw = open(p).read().replace('"lane":"monitoring"', '"lane":"no-such-lane"')
open(p, "w").write(raw)
PY
alerts_file "$r/alerts.json" "DiskFull:bunker-mvp"
out=$(run "$r")
case "$out" in *"appended=0"*) ok "5 nothing appended for a lane with no board";; *) bad "5 nothing appended for a lane with no board ($out)";; esac
grep -q "no board for lane 'no-such-lane'" "$r/out" && ok "5 reports the lane with no board" || bad "5 reports the lane with no board"

# ---------------------------------------------------------------- 6: stale backlog (THE case that must not flood)
r=$(mkroot 6)
board_row S-1 complete > "$r/board/monitoring/.coding-hermes/board/tasks.jsonl"
firing_row S-1 DiskFull bunker-mvp "2026-10-07 22:34:38" > "$r/src/board-rows.jsonl"
alerts_file "$r/alerts.json" "SomethingElse:other-host"
out=$(run "$r")
check "6 closed row + OLD firing replay is NOT re-fired" "$(count_id "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" S-1)" 1
case "$out" in *"appended=0"*) ok "6 counter appended=0";; *) bad "6 counter appended=0 ($out)";; esac

# ---------------------------------------------------------------- 7: resolved twin alone
r=$(mkroot 7)
board_row R-1 complete > "$r/board/monitoring/.coding-hermes/board/tasks.jsonl"
resolved_row R-1 > "$r/src/board-rows.jsonl"
alerts_file "$r/alerts.json" "DiskFull:bunker-mvp"
out=$(run "$r")
check "7 resolved twin never re-fires" "$(count_id "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" R-1)" 1

# ---------------------------------------------------------------- 8: no liveness source -> fail closed
r=$(mkroot 8)
board_row L-1 complete > "$r/board/monitoring/.coding-hermes/board/tasks.jsonl"
firing_row L-1 DiskFull bunker-mvp "2026-10-20 15:15:55" > "$r/src/board-rows.jsonl"
out=$(run "$r" "$r/absent-alerts.json")
check "8 no liveness source -> no re-fire" "$(count_id "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" L-1)" 1
case "$out" in *"appended=0"*) ok "8 counter appended=0";; *) bad "8 counter appended=0 ($out)";; esac
grep -q "liveness unknown" "$r/out" && ok "8 names the fail-closed suppression" || bad "8 names the fail-closed suppression"

# ---------------------------------------------------------------- 9: OLD dated id + live alert
r=$(mkroot 9)
OLD="MON-MONITORING-AA11BB22-20261007"
board_row "$OLD" complete > "$r/board/monitoring/.coding-hermes/board/tasks.jsonl"
firing_row "$OLD" DiskFull bunker-mvp "2026-10-07 22:34:38" > "$r/src/board-rows.jsonl"
alerts_file "$r/alerts.json" "DiskFull:bunker-mvp"
out=$(run "$r")
check "9 older dated id for a still-firing alert is NOT re-minted" "$(count_id "$r/board/monitoring/.coding-hermes/board/tasks.jsonl" "$OLD")" 1
case "$out" in *"appended=0"*) ok "9 counter appended=0";; *) bad "9 counter appended=0 ($out)";; esac
grep -q "OLDER date" "$r/out" && ok "9 names the old-date suppression" || bad "9 names the old-date suppression"

echo
echo "$pass passed, $fail failed"
[ "$fail" -eq 0 ] || exit 1

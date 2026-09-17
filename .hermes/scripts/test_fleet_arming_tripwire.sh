#!/usr/bin/env bash
# Ad-hoc verification of fleet-arming-tripwire.py v4 (throttle + env overrides).
# Synthetic DB + toml fixtures; never touches live scheduler state.
set -uo pipefail
S=/home/kara/.hermes/scripts/fleet-arming-tripwire.py
W=$(mktemp -d)
export ARMING_TRIPWIRE_DB="$W/sched.db"
export ARMING_TRIPWIRE_FLEET="$W/fleet.toml"
export ARMING_TRIPWIRE_STATE="$W/state.json"
export ARMING_TRIPWIRE_LOG="$W/tripwire.log"
fail=0
ok(){ echo "PASS: $1"; }
bad(){ echo "FAIL: $1"; fail=1; }

# --- fixtures: one healthy armed lane, one ENABLED-BUT-DISARMED lane (the
#     coding-hermes-tools 2026-09-17 case), one armed lane with a bad ceiling,
#     one enabled lane still carrying the retired command route.
sqlite3 "$ARMING_TRIPWIRE_DB" <<'SQL'
CREATE TABLE projects (name TEXT, namespace_id TEXT, enabled INT, cooldown_s INT,
  cooldown_floor_s INT, cooldown_ceiling_s INT, adaptive_cooldown INT, command TEXT);
INSERT INTO projects VALUES
 ('boardctl','coding-hermes',1,21600,21600,172800,1,NULL),
 ('coding-hermes-tools','coding-hermes',1,3600,3600,28800,0,NULL);
SQL

cat > "$ARMING_TRIPWIRE_FLEET" <<'TOML'
[[projects]]
name = "boardctl"
cooldown_s = 21600
adaptive_cooldown = true
cooldown_floor_s = 21600
cooldown_ceiling_s = 172800
enabled = true

[[projects]]
name = "coding-hermes-tools"
cooldown_s = 3600
adaptive_cooldown = true
cooldown_floor_s = 3600
cooldown_ceiling_s = 28800
enabled = true
TOML

# 1) first detection -> exit 1 with the T1 + T6 report
OUT=$(python3 "$S" 2>&1); RC=$?
if [ $RC -eq 1 ] && grep -q "T1: coding-hermes-tools foreman-lane enabled but adaptive_cooldown=0 (disarmed)" <<<"$OUT" \
   && grep -q "T6: armed-set mismatch" <<<"$OUT"; then ok "1 first detection alerts (exit 1, T1+T6)"; else bad "1 first detection (rc=$RC)"; echo "$OUT"; fi
grep -q "^.*ALERT (sig=" "$ARMING_TRIPWIRE_LOG" && ok "1b ALERT logged" || bad "1b ALERT not logged"

# 2) identical drift within the window -> quiet exit 0, suppression logged
OUT=$(python3 "$S" 2>&1); RC=$?
if [ $RC -eq 0 ] && [ -z "$OUT" ]; then ok "2 repeat within window is silent (exit 0)"; else bad "2 repeat suppression (rc=$RC out=$OUT)"; fi
grep -q "SUPPRESSED re-alert" "$ARMING_TRIPWIRE_LOG" && ok "2b suppression logged" || bad "2b suppression not logged"

# 2c) the cron's failure streak must not keep growing: the run is green
if [ $RC -eq 0 ]; then ok "2c cron sees success (no escalation fuel)"; else bad "2c cron still failing"; fi

# 3) window expired -> re-alerts
OUT=$(ARMING_TRIPWIRE_REALERT_H=0 python3 "$S" 2>&1); RC=$?
if [ $RC -eq 1 ] && grep -q "T1: coding-hermes-tools" <<<"$OUT"; then ok "3 re-alerts after the window expires"; else bad "3 re-alert window (rc=$RC)"; fi

# 4) drift CHANGES (new problem) -> pages immediately, no throttle
sqlite3 "$ARMING_TRIPWIRE_DB" "UPDATE projects SET adaptive_cooldown=1, cooldown_ceiling_s=999 WHERE name='coding-hermes-tools';"
OUT=$(python3 "$S" 2>&1); RC=$?
if [ $RC -eq 1 ] && grep -q "T2: coding-hermes-tools ceiling 999" <<<"$OUT"; then ok "4 changed signature alerts immediately"; else bad "4 changed-signature alert (rc=$RC)"; echo "$OUT"; fi

# 5) cleared -> silent, state reset, CLEARED logged
sqlite3 "$ARMING_TRIPWIRE_DB" "UPDATE projects SET cooldown_ceiling_s=28800 WHERE name='coding-hermes-tools';"
OUT=$(python3 "$S" 2>&1); RC=$?
if [ $RC -eq 0 ] && [ -z "$OUT" ] && [ "$(cat "$ARMING_TRIPWIRE_STATE" 2>/dev/null)" = "{}" ]; then ok "5 cleared -> silent + state reset"; else bad "5 clear path (rc=$RC)"; echo "$OUT"; fi
grep -q "CLEARED: drift" "$ARMING_TRIPWIRE_LOG" && ok "5b CLEARED logged" || bad "5b CLEARED not logged"

# 6) recurrence after clear pages immediately (no stale throttle)
sqlite3 "$ARMING_TRIPWIRE_DB" "UPDATE projects SET adaptive_cooldown=0 WHERE name='coding-hermes-tools';"
OUT=$(python3 "$S" 2>&1); RC=$?
if [ $RC -eq 1 ]; then ok "6 recurrence after clear re-pages immediately"; else bad "6 recurrence (rc=$RC)"; fi

# 7) T7 retired-command-route detection still live
sqlite3 "$ARMING_TRIPWIRE_DB" "UPDATE projects SET adaptive_cooldown=1 WHERE name='coding-hermes-tools'; UPDATE projects SET command='scripts/foreman-tick.sh' WHERE name='boardctl';"
OUT=$(ARMING_TRIPWIRE_REALERT_H=0 python3 "$S" 2>&1); RC=$?
if [ $RC -eq 1 ] && grep -q "T7: boardctl enabled with command route set" <<<"$OUT"; then ok "7 T7 command-route check intact"; else bad "7 T7 check (rc=$RC)"; echo "$OUT"; fi

# 8) healthy tree stays silent and never writes a state file
sqlite3 "$ARMING_TRIPWIRE_DB" "UPDATE projects SET command=NULL WHERE name='boardctl';"
python3 "$S" >/dev/null 2>&1; RC=$?
if [ $RC -eq 0 ] && [ "$(cat "$ARMING_TRIPWIRE_STATE" 2>/dev/null)" = "{}" ]; then ok "8 healthy -> silent, no drift state"; else bad "8 healthy path (rc=$RC)"; fi

echo "--- log ---"; cat "$ARMING_TRIPWIRE_LOG"
rm -rf "$W"
echo "RESULT: $([ $fail -eq 0 ] && echo ALL-PASS || echo FAILURES)"
exit $fail

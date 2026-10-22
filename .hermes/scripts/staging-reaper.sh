#!/usr/bin/env bash
# staging-reaper.sh — reap debris from SIGKILLed backup-tiered.sh runs.
# Closes MON-GAP-031 (2026-10-22): Hermes cron job dcd135dcbd85 (no_agent, 7200s
# script_timeout_seconds) SIGKILLs backup-tiered.sh mid-run — the 10-20 tick
# reclaimed 108.4GiB and the 10-21 supervisor run 94GiB of stranded verify_/tmp_legacy_
# staging, each surviving until the NEXT run's start-wipe (up to 4h on the root NVMe).
#
# Doctrine (from backup-tiered.sh lines 91-113, made standalone): the run holds the
# flock on $STAGING/.backup.lock for its WHOLE life, so "flock free" proves no live
# producer exists and everything else in STAGING is dead by definition — the exact
# proof the 10-20 tick used to reclaim by hand. This reaper adds a freshness gate the
# backup script's own start-wipe lacks: files younger than REAP_MIN_AGE_MIN are left
# alone so a run that just COMPLETED is never reaped mid-teardown of its last tiers,
# and so a run killed seconds ago is not raced while its writer is still flushing.
# The exit path never deletes the lock file itself (rm of the flock'd fd's file is
# harmless to the holder, but the reaper deletes only non-lock entries regardless).
#
# Install (manual, one-time): two user units —
#   systemd service ExecStart=%h/.hermes/scripts/staging-reaper.sh (oneshot)
#   timer OnCalendar=*:0/30, Persistent=true; `systemctl --user enable --now
#   staging-reaper.timer` + linger enabled so it runs without a login session.
set -u
STAGING="${STAGING:-/var/tmp/hermes-backup-staging}"
REAP_MIN_AGE_MIN="${REAP_MIN_AGE_MIN:-10}"
LOG="${LOG:-$HOME/.hermes/logs/staging-reaper.log}"

log() { echo "$(date '+%F %T') $*" >> "$LOG"; }

# 1) No staging dir = nothing to reap (do not create it — the backup script owns that).
[ -d "$STAGING" ] || exit 0

# 2) FLOCK GATE — a live backup-tiered.sh holds .backup.lock non-blocking; if WE can
#    take it, no producer is alive. Never reap while a run is active.
exec 9>"$STAGING/.backup.lock"
flock -n 9 || { log "SKIP: flock held — live backup run active"; exit 0; }

# 3) Freshness gate — leave entries younger than the age floor.
old=$(
  find "$STAGING" -mindepth 1 -maxdepth 1 ! -name '.backup.lock' -mmin +"$REAP_MIN_AGE_MIN" 2>/dev/null
)
if [ -z "$old" ]; then
  log "SKIP: no entries older than ${REAP_MIN_AGE_MIN}m"
  exit 0
fi

# 4) Reap: log names+sizes, then wipe everything stale (lock excluded).
stale_count=$(printf '%s\n' "$old" | wc -l)
log "REAP beginning: $stale_count entries"
du -sh $old 2>/dev/null | sed 's/^/  /' >> "$LOG"
df -k / | awk 'NR==2 {printf "  df-before: %d KiB free\n", $4}' >> "$LOG"
find "$STAGING" -mindepth 1 -maxdepth 1 ! -name '.backup.lock' -mmin +"$REAP_MIN_AGE_MIN" \
  -exec rm -rf -- {} + 2>>"$LOG" || true
df -k / | awk 'NR==2 {printf "  df-after: %d KiB free\n", $4}' >> "$LOG"
log "REAP complete"
exit 0

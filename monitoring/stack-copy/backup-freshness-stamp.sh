#!/bin/bash
# backup-freshness-stamp.sh — publish per-job backup freshness to the monitoring
# stack (MON-GAP-018). Runs on the lane box (where S3 creds live), pushes a
# node_exporter textfile .prom to fleet-monitor atomically (.prom.new + mv).
#
# Jobs covered: monitoring stack (fleet-monitor nightly, existing stamp),
#               kara-hermes (weekly, s3://dexdat-backups/kara-hermes/<STAMP>/),
#               cube-agent   (weekly, s3://dexdat-backups/cube-las-00/eduos-agent/<STAMP>/).
# Freshness source: latest MANIFEST.txt upload time (rclone lsl -- maxed), which is
# only written after a complete, verified upload set.
set -uo pipefail
export PATH="$HOME/.local/bin:$PATH"
REMOTE="${REMOTE:-hetzner:dexdat-backups}"
MON_HOST="${MON_HOST:-fleet-monitor}"
TEXTDIR="/var/lib/fleet-monitoring/node-exporter-textfile"
METRIC="monitoring_backup_last_success_timestamp_seconds"
PROM_OUT="/tmp/backup-freshness.prom"
LOG=/home/kara/logs/backup-freshness.log

stamp_for() {  # $1 = bucket prefix; prints unix ts of newest MANIFEST or 0
  local row
  row=$(rclone lsl "$REMOTE/$1" --include 'MANIFEST.txt' 2>/dev/null \
        | sort -k2,3 | tail -1 | awk '{print $2, $3}')
  [ -z "$row" ] && { echo 0; return; }
  python3 -c "import datetime,sys;s=' '.join(sys.argv[1:3])[:19];print(int(datetime.datetime.strptime(s,'%Y-%m-%d %H:%M:%S').replace(tzinfo=datetime.timezone.utc).timestamp()))" $row
}

kube_ts=$(stamp_for "kara-hermes")
cube_ts=$(stamp_for "cube-las-00/eduos-agent")
# monitoring-stack freshness is published host-side (fleet_monitoring_backup.prom,
# guarded by the existing 48h BackupFreshnessStale) — publishing it here too
# would create a duplicate series under the same metric name.

{
  echo "# HELP $METRIC Unix time of the last successful uploaded backup"
  echo "# TYPE $METRIC gauge"
  echo "${METRIC}{job=\"kara-hermes\"} $kube_ts"
  echo "${METRIC}{job=\"cube-agent\"} $cube_ts"
} > "$PROM_OUT"

scp -q "$PROM_OUT" "$MON_HOST:$TEXTDIR/backup-freshness.prom.new" \
  && ssh "$MON_HOST" "mv $TEXTDIR/backup-freshness.prom.new $TEXTDIR/backup-freshness.prom" \
  || { echo "$(date -u +%FT%TZ) PUSH FAILED" >> "$LOG"; exit 1; }

echo "$(date -u +%FT%TZ) ok kara=$kube_ts cube=$cube_ts" >> "$LOG"

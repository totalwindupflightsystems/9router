#!/usr/bin/env bash
# backup-to-s3.sh — push the monitoring host's state to object storage.
#
# What is and is not backed up, and why:
#   Loki chunks        ALREADY in S3 (the stack writes them there). Nothing to copy.
#   Prometheus TSDB    local by design; snapshotted through the admin API (consistent,
#                      no tarring a live TSDB — a tar of an open TSDB is a corrupt tar).
#   Grafana SQLite     dumped through sqlite3's own .backup, never copied while open.
#   dashboards/rules   they are files in git; the git bundle carries them plus every config.
#   git bundle         a full clone-in-a-file, so the runbook survives losing GitHub too.
#
# Layout: s3://$S3_BUCKET/$S3_PREFIX/<YYYY-mm-dd_HHMMSS>/...
#         s3://$S3_BUCKET/$S3_PREFIX/latest -> pointer file (small, overwritten each run)
set -euo pipefail
# systemd oneshot runs without HOME -> git dies on dubious ownership; fall back to /root
export HOME="${HOME:-/root}"
cd "$(dirname "$0")" || exit 1

TS=$(date -u +%Y-%m-%d_%H%M%S)
PREFIX="${S3_PREFIX:-monitoring}/$TS"
BUCKET="${S3_BUCKET:?S3_BUCKET unset}"
ENDPOINT="${S3_ENDPOINT:?S3_ENDPOINT unset}"
WORK=$(mktemp -d /tmp/mon-backup-XXXXXX)
trap 'rm -rf "$WORK"' EXIT

rclone_s3() { rclone --config /dev/null \
  --s3-provider Other \
  --s3-access-key-id "$S3_ACCESS_KEY" \
  --s3-secret-access-key "$S3_SECRET_KEY" \
  --s3-endpoint "$ENDPOINT" \
  --s3-region "${S3_REGION:-hel1}" \
  --s3-force-path-style \
  "$@"; }
remote() { echo ":s3:$BUCKET/$1"; }

log() { printf '\033[1m== %s\033[0m\n' "$*"; }

log "prometheus snapshot"
# A snapshot is the only consistent way to take a live TSDB. ONE call: the endpoint creates
# the snapshot and returns its name, so asking twice leaves an orphan behind.
snap=$(curl -sf -X POST http://127.0.0.1:9090/api/v1/admin/tsdb/snapshot 2>/dev/null \
  | python3 -c 'import json,sys
try: print(json.load(sys.stdin)["data"]["name"])
except Exception: print("")' 2>/dev/null || true)
if [ -z "$snap" ]; then
  echo "  WARNING: snapshot API failed — is prometheus up with --web.enable-admin-api?"
else
  log "copying snapshot $snap"
  docker run --rm -v fleet-monitoring_prom-data:/prometheus:ro alpine:3.20 \
    tar czf - -C /prometheus/snapshots "$snap" > "$WORK/prometheus-$snap.tar.gz"
  echo "  $(du -h "$WORK/prometheus-$snap.tar.gz" | cut -f1)"
fi

log "grafana state"
# .backup is safe on an open SQLite database; cp is not.
if docker exec mon-grafana sh -c 'command -v sqlite3 >/dev/null' 2>/dev/null; then
  docker exec mon-grafana sh -c 'sqlite3 /var/lib/grafana/grafana.db ".backup /tmp/g.db" && cat /tmp/g.db' > "$WORK/grafana.db" 2>/dev/null \
    && echo "  grafana.db $(du -h "$WORK/grafana.db" | cut -f1)" \
    || echo "  WARNING: grafana.db backup failed"
else
  echo "  sqlite3 absent in image — falling back to volume copy"
  docker run --rm -v fleet-monitoring_grafana-data:/g:ro alpine:3.20 tar czf - -C /g grafana.db > "$WORK/grafana.db.tgz"
fi

log "git bundle (the repo IS the rebuildable artefact)"
if ! git rev-parse --git-dir >/dev/null 2>&1; then
  echo "ERROR: not inside a git work tree (dubious ownership? HOME unset?) - a backup without the repo bundle is incomplete, refusing to continue" >&2
  exit 1
fi
if ! git bundle create "$WORK/fleet-monitoring.bundle" --all >/dev/null 2>&1; then
  echo "ERROR: git bundle create failed" >&2
  exit 1
fi
echo "  $(du -h "$WORK/fleet-monitoring.bundle" | cut -f1)"
git rev-parse HEAD > "$WORK/HEAD" 2>/dev/null || true

log "manifest"
{
  echo "host: $(hostname)"
  echo "timestamp_utc: $TS"
  echo "tool: fleet-monitoring backup-to-s3.sh"
  echo "git_head: $(git rev-parse HEAD 2>/dev/null || echo none)"
  echo "prometheus_snapshot: ${snap:-none}"
  echo "loki_chunks: already in s3://$BUCKET/$S3_PREFIX (written by Loki itself)"
  echo "--- files ---"
  ( cd "$WORK" && find . -type f -printf '%10s  %p\n' | sort -k2 )
  echo "--- sha256 ---"
  ( cd "$WORK" && find . -type f ! -name MANIFEST.txt -exec sha256sum {} + 2>/dev/null | sed 's#\./##' )
} > "$WORK/MANIFEST.txt"
cat "$WORK/MANIFEST.txt" | head -20 | sed 's/^/  /'

log "upload"
rclone_s3 copy "$WORK" "$(remote "$PREFIX/")" --transfers 4 --s3-no-check-bucket 2>&1 | tail -3
printf '%s\n' "$TS" > "$WORK/latest"
rclone_s3 copyto "$WORK/latest" "$(remote "${S3_PREFIX:-monitoring}/latest")" --s3-no-check-bucket

# Expose freshness to Prometheus so an alert can fire on a backup that stopped happening —
# an unmonitored backup is a backup that silently stops.
STAMP=/var/lib/fleet-monitoring/node-exporter-textfile/fleet_monitoring_backup.prom
if [ -d "$(dirname "$STAMP")" ]; then
  cat > "$STAMP.tmp" <<EOF
# HELP monitoring_backup_last_success_timestamp_seconds Unix time of the last successful uploaded backup
# TYPE monitoring_backup_last_success_timestamp_seconds gauge
monitoring_backup_last_success_timestamp_seconds $(date -u +%s)
# HELP monitoring_backup_files Number of files in the last backup set
# TYPE monitoring_backup_files gauge
monitoring_backup_files $(find "$WORK" -type f | wc -l)
EOF
  mv "$STAMP.tmp" "$STAMP"
  echo "  freshness metric written to $STAMP"
fi

log "done — s3://$BUCKET/$PREFIX"

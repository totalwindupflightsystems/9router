#!/usr/bin/env bash
# restore-from-s3.sh — bring state back onto a host that already has the stack up.
#
# Deliberately does NOT bring containers up: restoring a snapshot under a running Prometheus
# is how you corrupt it. Order matters — stop, restore, start. The script refuses to run
# against a live stack unless FORCE=1 says you know.
#
#   ./restore-from-s3.sh                  # restore the 'latest' set
#   ./restore-from-s3.sh 2026-09-27_101500
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

WANT="${1:-}"
BUCKET="${S3_BUCKET:?S3_BUCKET unset}"
ENDPOINT="${S3_ENDPOINT:?S3_ENDPOINT unset}"
PREFIX="${S3_PREFIX:-monitoring}"
COMPOSE=(docker compose -f stack/docker-compose.yml --env-file .env)

rclone_s3() { rclone --config /dev/null --s3-provider Other \
  --s3-access-key-id "$S3_ACCESS_KEY" --s3-secret-access-key "$S3_SECRET_KEY" \
  --s3-endpoint "$ENDPOINT" --s3-region "${S3_REGION:-hel1}" --s3-force-path-style "$@"; }

if [ -z "$WANT" ]; then
  WANT=$(rclone_s3 cat ":s3:$BUCKET/$PREFIX/latest" 2>/dev/null | tr -d '[:space:]')
  [ -n "$WANT" ] || { echo "no latest pointer; pass a timestamp explicitly"; exit 1; }
fi
echo "restoring set: $WANT"

if "${COMPOSE[@]}" ps --status running --format '{{.Name}}' 2>/dev/null | grep -q .; then
  if [ "${FORCE:-0}" != "1" ]; then
    echo "stack is RUNNING. Stop it first (make down), or set FORCE=1 to let this script stop it."
    exit 1
  fi
  echo "stopping stack (FORCE=1)..."
  "${COMPOSE[@]}" down
fi

WORK=$(mktemp -d /tmp/mon-restore-XXXXXX)
rclone_s3 copy ":s3:$BUCKET/$PREFIX/$WANT" "$WORK" -q --s3-no-check-bucket

echo "== grafana =="
if [ -f "$WORK/grafana.db" ]; then
  docker run --rm -v grafana-data:/g -v "$WORK:/in:ro" alpine:3.20 \
    sh -c 'cp /in/grafana.db /g/grafana.db && chown 472:472 /g/grafana.db'
  echo "  grafana.db restored"
elif [ -f "$WORK/grafana.db.tgz" ]; then
  docker run --rm -v grafana-data:/g -v "$WORK:/in:ro" alpine:3.20 \
    sh -c 'tar xzf /in/grafana.db.tgz -C /g && chown 472:472 /g/grafana.db'
  echo "  grafana.db restored from volume copy"
else
  echo "  no grafana state in this set"
fi

echo "== prometheus =="
SNAP=$(find "$WORK" -name 'prometheus-*.tar.gz' | head -1 || true)
if [ -n "$SNAP" ]; then
  echo "  snapshot present: $(basename "$SNAP")"
  echo "  TSDB restore is a data-merge, not a copy: see docs/rebuild.md#restoring-prometheus-history"
  echo "  (copying a snapshot over a live tsdb directory is the defect this note prevents)"
else
  echo "  no prometheus snapshot in this set"
fi

echo "== loki =="
echo "  chunks are NOT in this set — Loki reads them from s3://$BUCKET/$PREFIX/loki/ directly."
echo "  Recreating the index is enough; no restore step is required."

rm -rf "$WORK"
echo
echo "restore complete for state that lives here. Now: make up && make verify"

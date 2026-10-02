#!/usr/bin/env bash
# restore-check.sh — prove the newest backup is READABLE, not merely present.
#
# "A backup that has never been restored is not a backup" is true but too late by the time you
# find out. This is the cheap version of that discipline: every run, download the newest set,
# verify the checksums the backup wrote, and prove the git bundle is a real repo.
#
# Exit 0 = restorable. Exit 1 = the thing you would reach for is broken; fix it now.
set -euo pipefail
# systemd oneshot runs without HOME -> git dies on dubious ownership; fall back to /root
export HOME="${HOME:-/root}"
cd "$(dirname "$0")" || exit 1

BUCKET="${S3_BUCKET:?S3_BUCKET unset}"
ENDPOINT="${S3_ENDPOINT:?S3_ENDPOINT unset}"
PREFIX="${S3_PREFIX:-monitoring}"
WORK=$(mktemp -d /tmp/mon-restore-check-XXXXXX)
trap 'rm -rf "$WORK"' EXIT

rclone_s3() { rclone --config /dev/null \
  --s3-provider Other --s3-access-key-id "$S3_ACCESS_KEY" --s3-secret-access-key "$S3_SECRET_KEY" \
  --s3-endpoint "$ENDPOINT" --s3-region "${S3_REGION:-hel1}" --s3-force-path-style "$@"; }

echo "== newest backup set =="
LATEST=$(rclone_s3 cat ":s3:$BUCKET/$PREFIX/latest" 2>/dev/null | tr -d '[:space:]' || true)
if [ -z "$LATEST" ]; then
  echo "no 'latest' pointer at s3://$BUCKET/$PREFIX/latest — has backup-to-s3.sh ever run?"
  exit 1
fi
echo "  latest: $LATEST"

rclone_s3 copy ":s3:$BUCKET/$PREFIX/$LATEST" "$WORK" --s3-no-check-bucket -q
[ -f "$WORK/MANIFEST.txt" ] || { echo "MANIFEST.txt missing from the backup set"; exit 1; }
echo "  downloaded $(find "$WORK" -type f | wc -l) files"

echo "== checksums =="
if ( cd "$WORK" && grep -q '^ *[0-9a-f]\{64\} ' MANIFEST.txt 2>/dev/null ); then
  ( cd "$WORK" && awk '/^--- sha256 ---$/{f=1;next} f&&NF' MANIFEST.txt > .sums && sha256sum -c .sums --quiet ) \
    && echo "  all files verify" \
    || { echo "  CHECKSUM MISMATCH — this backup is not trustworthy"; exit 1; }
else
  echo "  no checksums in manifest (older backup format?) — verifying structure only"
fi

echo "== git bundle is a real repo =="
BUNDLE=$(find "$WORK" -name '*.bundle' | head -1)
if [ -n "$BUNDLE" ]; then
  git bundle verify "$BUNDLE" >/dev/null 2>&1 && echo "  $(basename "$BUNDLE"): valid, $(git bundle list-heads "$BUNDLE" | wc -l) ref(s)" \
    || { echo "  git bundle FAILED verification"; exit 1; }
  DEAD=$(cat "$WORK/HEAD" 2>/dev/null | tr -d '[:space:]' || true)
  if [ -n "$DEAD" ] && git bundle list-heads "$BUNDLE" | grep -q "$DEAD"; then
    echo "  contains recorded HEAD $DEAD"
  fi
else
  echo "  ERROR: no git bundle in this set - backup is incomplete (git bundle + HEAD missing), FAILING" >&2
  exit 1
fi

echo "== prometheus snapshot present =="
find "$WORK" -name 'prometheus-*.tar.gz' | head -1 | while read -r f; do
  tar tzf "$f" >/dev/null && echo "  $(basename "$f"): tar readable"
done

echo
echo "RESTORE-CHECK: PASS — newest backup is readable and internally consistent"

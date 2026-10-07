#!/usr/bin/env bash
# render-configs.sh — materialise the secrets that must be FILES, not env vars, and pick the
# Loki chunk-storage config.
#
# Alertmanager reads its auth token from a file (credentials_file) so it never appears in a
# process listing or a docker inspect. The file is generated here from .env and is gitignored.
#
# QA-MONITORING-001: Loki's chunk store is s3 | local (LOKI_STORAGE in .env.example). The
# container always runs /etc/loki/loki-config.active.yml, which is written here as a copy of
# the selected config — so a clean machine with no S3 credentials boots on the filesystem and
# a credentialed host runs the unchanged S3 config. The resolution MUST match
# scripts/check-env.sh.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

[ -f .env ] || { echo "render-configs: .env missing"; exit 1; }
set -a; . ./.env; set +a

: "${ALERT_ROUTER_TOKEN:?ALERT_ROUTER_TOKEN unset}"

# ---- Loki storage selection (mirror of check-env.sh) ------------------------
storage="${LOKI_STORAGE:-auto}"
case "$storage" in
  s3|local) storage_mode="$storage" ;;
  auto)
    if [ -n "${S3_ACCESS_KEY:-}" ] && [ -n "${S3_SECRET_KEY:-}" ]; then
      storage_mode=s3
    else
      storage_mode=local
    fi ;;
  *)
    echo "render-configs: LOKI_STORAGE=$storage is not auto|s3|local"; exit 1 ;;
esac

case "$storage_mode" in
  s3)
    : "${S3_ENDPOINT:?S3_ENDPOINT unset (required for LOKI_STORAGE=s3)}"
    : "${S3_BUCKET:?S3_BUCKET unset (required for LOKI_STORAGE=s3)}"
    : "${S3_ACCESS_KEY:?S3_ACCESS_KEY unset (required for LOKI_STORAGE=s3)}"
    : "${S3_SECRET_KEY:?S3_SECRET_KEY unset (required for LOKI_STORAGE=s3)}"
    loki_src=stack/loki/loki-config.yml ;;
  local)
    loki_src=stack/loki/loki-config-local.yml ;;
esac

[ -f "$loki_src" ] || { echo "render-configs: $loki_src missing"; exit 1; }
cp "$loki_src" stack/loki/loki-config.active.yml
echo "loki storage: LOKI_STORAGE=$storage -> $storage_mode ($loki_src -> stack/loki/loki-config.active.yml)"

umask 077

# The file may already exist and be read-only (a hardened host chmod 400s it), and a bare
# `>` truncation on a 0400 file fails "Permission denied" — remove first so a re-render is
# always writable. The directory is the repo's, so this never touches anything unexpected.
rm -f stack/alertmanager/router-token
mkdir -p stack/alertmanager
printf '%s' "$ALERT_ROUTER_TOKEN" > stack/alertmanager/router-token
chmod 600 stack/alertmanager/router-token
echo "wrote stack/alertmanager/router-token (mode 600)"

# Loki takes its S3 credentials by env interpolation; compose passes .env through, so only
# the Alertmanager token needs a file.

# Guard: the token file must never be committed.
if git ls-files --error-unmatch stack/alertmanager/router-token >/dev/null 2>&1; then
  echo "REFUSING: stack/alertmanager/router-token is TRACKED by git — remove it from the index:"
  echo "  git rm --cached stack/alertmanager/router-token"
  exit 1
fi
echo "token file is not tracked by git: OK"

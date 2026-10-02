#!/usr/bin/env bash
# check-env.sh — refuse to deploy with placeholder or missing config.
#
# The failure this prevents: a stack that comes up perfectly with GRAFANA_PASSWORD=changeme,
# a router that rejects every webhook because the token is empty, and Loki silently writing
# chunks to nowhere because the S3 credentials were never filled in.
#
# QA-MONITORING-001: this now runs BEFORE any `docker compose config` (see Makefile) so a bad
# .env is named here instead of surfacing as a raw compose interpolation error, and it is
# storage-aware — S3 credentials are required only when Loki's chunk store is S3. With
# LOKI_STORAGE=local (or auto and no credentials) the stack boots on the filesystem and this
# script says "skip (local storage mode)" rather than failing.
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

[ -f .env ] || { echo "check-env: .env missing (cp .env.example .env)"; exit 1; }

fail=0
val() { grep -E "^$1=" .env 2>/dev/null | head -1 | cut -d= -f2- ; }

require() { # NAME
  local name=$1 value
  value=$(val "$name")
  if [ -z "$value" ]; then
    printf '  \033[31mMISSING\033[0m %s\n' "$name"; fail=1; return
  fi
  case "$value" in
    # .env.example ships these so a zero-edit `cp .env.example .env` boots a clean machine.
    # They are dummies, not secrets: warn loudly, but do not block the boot.
    dev-only-*)
      printf '  \033[33mDEV DEFAULT\033[0m %s (replace before a real deployment)\n' "$name" ;;
    *changeme*|*placeholder*|*CHANGE_ME*)
      printf '  \033[31mPLACEHOLDER\033[0m %s=%s\n' "$name" "$value"; fail=1 ;;
    *) printf '  \033[32mok\033[0m %s\n' "$name" ;;
  esac
}

echo "check-env: required settings"
require GRAFANA_PASSWORD
require ALERT_ROUTER_TOKEN
require RENDERER_TOKEN
require ALERT_ROUTER_PORT
require S3_BUCKET

# ---- Loki chunk storage -----------------------------------------------------
# Resolution must match scripts/render-configs.sh: s3 | local | auto (= s3 iff both
# credentials are non-empty). The two scripts staying in step is what makes a zero-edit
# .env boot on a clean machine while a credentialed host still runs the S3 config.
storage=$(val LOKI_STORAGE); storage=${storage:-auto}
s3_access=$(val S3_ACCESS_KEY)
s3_secret=$(val S3_SECRET_KEY)
case "$storage" in
  s3)    storage_mode=s3 ;;
  local) storage_mode=local ;;
  auto)
    if [ -n "$s3_access" ] && [ -n "$s3_secret" ]; then storage_mode=s3; else storage_mode=local; fi ;;
  *)
    printf '  \033[31mINVALID\033[0m LOKI_STORAGE=%s (expected auto|s3|local)\n' "$storage"
    fail=1; storage_mode=local ;;
esac
printf '  \033[36mstorage\033[0m LOKI_STORAGE=%s -> %s\n' "$storage" "$storage_mode"
if [ "$storage_mode" = s3 ]; then
  require S3_ENDPOINT
  require S3_ACCESS_KEY
  require S3_SECRET_KEY
else
  printf '  \033[33mskip\033[0m S3_ACCESS_KEY/S3_SECRET_KEY (local storage mode)\n'
fi

# these may legitimately be empty; warn, do not fail
for opt in TAILSCALE_AUTHKEY HCLOUD_TOKEN MONITORING_SERVER_ID; do
  [ -n "$(val "$opt")" ] && printf '  \033[32mok\033[0m %s\n' "$opt" \
    || printf '  \033[33mskip\033[0m %s unset (fine unless you are provisioning)\n' "$opt"
done

if [ "$fail" -ne 0 ]; then
  echo "check-env: FAIL — fix .env before deploying"
  exit 1
fi
echo "check-env: PASS"

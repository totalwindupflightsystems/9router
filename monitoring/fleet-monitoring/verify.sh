#!/usr/bin/env bash
# verify.sh — compatibility shim. The verification gate lives at scripts/verify.sh.
#
# This top-level path is kept only because operators (and some notes) invoke it directly.
# It exists because a legacy COPY of the real script used to live here: that copy ran
# `cd "$(dirname "$0")/.."`, which from the repo root resolves to the PARENT directory,
# so `docker compose ps` read a compose file that is not there and the gate printed
# "FAIL no containers found" on a fully healthy 11/11 stack (MON-DOGFOOD-040).
# A shim cannot drift: it forwards, so there is exactly one implementation.
set -uo pipefail
exec "$(dirname "$0")/scripts/verify.sh" "$@"

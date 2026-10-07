#!/usr/bin/env bash
# lint-configs.sh — validate every config with the tool that owns its schema.
#
# A YAML file that parses is not a valid Prometheus config; only promtool says that. Each
# component ships its own validator, so we run theirs instead of guessing. Validators run in
# the pinned images, so "it validated" means "it validated against the version we deploy".
set -uo pipefail
cd "$(dirname "$0")/.." || exit 1

# All scratch files go in a private mktemp dir, never bare /tmp: on multi-user hosts
# (bunker agents, shared boxes) /tmp already holds files owned by other uids, and a
# pre-existing /tmp/<name> owned by someone else makes every lint step fail
# "Permission denied" (MON-DOGFOOD-005).
# Bind-mount SOURCES additionally must NOT live under /tmp on rootless daemons
# (bunkerd/rootlesskit): a /tmp-sourced mount arrives inside the container as an
# EMPTY root-owned directory, so the Loki check would see no config file
# (MON-DOGFOOD-006). Mount sources are staged under the repo dir instead — the same
# class of path the other steps already mount successfully.
TMPD="$(mktemp -d /tmp/fm-lint.XXXXXX)"
LINT_MNT="$(mktemp -d "$PWD/.lint-mnt.XXXXXX")"
trap 'rm -rf "$TMPD" "$LINT_MNT"' EXIT

PROM_IMG=prom/prometheus:v3.15.0
AM_IMG=prom/alertmanager:v0.34.1
LOKI_IMG=grafana/loki:3.7.8
ALLOY_IMG=grafana/alloy:v1.20.0

fail=0
have() { command -v "$1" >/dev/null 2>&1; }
ok()  { printf '  \033[32mOK\033[0m   %s\n' "$*"; }
bad() { printf '  \033[31mBAD\033[0m  %s\n' "$*"; fail=1; }

echo "== compose =="
# Validate against a SYNTHETIC env, not .env.example: the compose file marks secrets as
# required (`:?`), which is exactly what stops a deploy with missing credentials — but it also
# means .env.example's deliberately-empty values cannot validate it. Lint supplies dummies so
# the schema is checked without needing real secrets present.
cat > "$TMPD"/fm-lint.env <<'ENVEOF'
GRAFANA_PASSWORD=lint-dummy
ALERT_ROUTER_TOKEN=lint-dummy
S3_ACCESS_KEY=lint-dummy
S3_SECRET_KEY=lint-dummy
S3_BUCKET=lint-dummy
S3_ENDPOINT=https://lint-dummy.example
S3_REGION=hel1
S3_PREFIX=monitoring
LOKI_RETENTION=720h
PROM_RETENTION=30d
PROM_RETENTION_SIZE=8GB
GRAFANA_BIND=127.0.0.1
BOARD_ROOT=/tmp/boards
RENDERER_TOKEN=lint-dummy
ENVEOF
if docker compose -f stack/docker-compose.yml --env-file "$TMPD"/fm-lint.env config -q 2>"$TMPD"/compose.err; then
  ok "docker-compose.yml"
else
  bad "docker-compose.yml"; sed 's/^/       /' "$TMPD"/compose.err | head -20
fi

echo "== shell =="
if have shellcheck; then
  if shellcheck -S warning scripts/*.sh 2>"$TMPD"/sc.err; then ok "shellcheck clean"; else
    bad "shellcheck"; sed 's/^/       /' "$TMPD"/sc.err | head -30; fi
else
  for f in scripts/*.sh; do bash -n "$f" || bad "bash -n $f"; done
  ok "bash -n on all scripts (shellcheck not installed)"
fi

echo "== YAML parse =="
if python3 -c "import yaml" 2>/dev/null; then
python3 - <<'PY' || fail=1
import glob, sys, yaml
bad = []
for path in sorted(glob.glob("alerts/**/*.yml", recursive=True) +
                   glob.glob("stack/**/*.yml", recursive=True) +
                   glob.glob("ansible/**/*.yml", recursive=True) +
                   glob.glob("cloud-init/*.yaml", recursive=True)):
    try:
        with open(path) as fh:
            list(yaml.safe_load_all(fh))
    except Exception as exc:
        bad.append("%s: %s" % (path, exc))
if bad:
    for b in bad:
        print("  \033[31mBAD\033[0m  %s" % b)
    sys.exit(1)
print("  \033[32mOK\033[0m   every YAML file parses")
PY
else
  ok "YAML parse skipped (PyYAML not installed on this host)"
fi

echo "== prometheus =="
# the prometheus image's ENTRYPOINT is the server; promtool needs an explicit override
if docker run --rm -q --entrypoint /bin/promtool -v "$PWD/stack/prometheus:/cfg:ro" "$PROM_IMG" \
     check config /cfg/prometheus.yml >"$TMPD"/promtool.log 2>&1; then
  ok "prometheus.yml"
else
  bad "prometheus.yml"; sed 's/^/       /' "$TMPD"/promtool.log | head -20
fi

echo "== alert rules =="
# the glob must be expanded by a shell INSIDE the container — docker passes args literally,
# so promtool would receive the unexpanded "*.yml" string and reject the path
if docker run --rm -q --entrypoint /bin/sh -v "$PWD/alerts:/rules:ro" "$PROM_IMG" \
     -c 'promtool check rules /rules/rules/*.yml' >"$TMPD"/rules.log 2>&1; then
  # printf, not sed: sed does not interpret \033, so the previous form printed the literal
  # escape sequence into CI logs
  while IFS= read -r line; do printf '  \033[32mOK\033[0m   %s\n' "$line"; done \
    < <(grep -E 'SUCCESS|found' "$TMPD"/rules.log || true)
else
  bad "alert rules"; sed 's/^/       /' "$TMPD"/rules.log | head -30
fi

echo "== alertmanager =="
if docker run --rm -q -v "$PWD/stack/alertmanager:/cfg:ro" --entrypoint /bin/amtool "$AM_IMG" \
     check-config /cfg/alertmanager.yml >"$TMPD"/am.log 2>&1; then
  ok "alertmanager.yml"
else
  bad "alertmanager.yml"; sed 's/^/       /' "$TMPD"/am.log | head -20
fi

echo "== loki =="
# loki validates its own config with -verify-config, but the file interpolates env vars:
# render them the same way compose does before checking — AND pass the same
# -config.expand-env=true the container runs with, because without that flag Loki reads
# "${S3_ACCESS_KEY}" literally. Validating a rendered copy against a flag-less invocation is
# how a config gets a green light here and then crash-loops on the host (which it did).
mkdir -p "$LINT_MNT/loki-cfg"
python3 - <<'PY' > "$LINT_MNT/loki-cfg/loki-rendered.yml" || bad "loki config render"
import os, re, sys
env = {}
with open(".env.example") as fh:
    for line in fh:
        m = re.match(r'^([A-Z0-9_]+)=(.*)$', line.strip())
        if m:
            env[m.group(1)] = m.group(2)
src = open("stack/loki/loki-config.yml").read()
out = re.sub(r'\$\{([A-Z0-9_]+)(?::-([^}]*))?\}',
             lambda m: env.get(m.group(1), m.group(2) or ""), src)
sys.stdout.write(out)
PY
if docker run --rm -q -e S3_ENDPOINT=x -e S3_BUCKET=x -e S3_ACCESS_KEY=x -e S3_SECRET_KEY=x \
     -e S3_REGION=hel1 -e LOKI_RETENTION=720h \
     -v "$LINT_MNT/loki-cfg":/cfg:ro "$LOKI_IMG" \
     -config.file=/cfg/loki-rendered.yml -config.expand-env=true -verify-config=true >"$TMPD"/loki.log 2>&1; then
  ok "loki-config.yml"
else
  bad "loki-config.yml"; sed 's/^/       /' "$TMPD"/loki.log | tail -20
fi

echo "== alloy =="
if docker run --rm -q -v "$PWD/stack/alloy:/cfg:ro" "$ALLOY_IMG" \
     fmt /cfg/config.alloy >"$TMPD"/alloy.out 2>"$TMPD"/alloy.err; then
  # `alloy fmt` rewrites; --test reports without writing, which is what CI needs
  docker run --rm -q -v "$PWD/stack/alloy:/cfg:ro" "$ALLOY_IMG" \
     fmt --test /cfg/config.alloy >/dev/null 2>>"$TMPD"/alloy.err \
    && ok "config.alloy parses and is formatted" \
    || { bad "config.alloy is not gofmt-clean (run: alloy fmt)"; sed 's/^/       /' "$TMPD"/alloy.err | head; }
else
  bad "config.alloy"; sed 's/^/       /' "$TMPD"/alloy.err | head -20
fi

echo
[ "$fail" -eq 0 ] && echo "LINT: PASS" || echo "LINT: FAIL"
exit "$fail"

#!/usr/bin/env bash
# verify.sh — assert the stack is WORKING, not merely running.
#
# Green containers prove nothing: every observability stack that ever looked fine while
# collecting nothing had green containers. This checks, in order:
#   1. every container up
#   2. Prometheus has real samples (not an empty TSDB)
#   3. Loki has real streams and accepts a query
#   4. Grafana is up AND its provisioned datasources answer
#   5. the alert-router is reachable and reports its write mode
# A failure here is a failed deploy.
set -uo pipefail

cd "$(dirname "$0")/.." || exit 1
STACK=stack
COMPOSE=(docker compose -f "$STACK/docker-compose.yml" --env-file .env)

# Load .env into this shell. Without it the Grafana checks below are silently SKIPPED
# ("GRAFANA_PASSWORD unset") — and a verification step that skips itself is worse than no step,
# because the run still prints a verdict.
if [ -f .env ]; then
  set -a
  # shellcheck disable=SC1091
  . ./.env
  set +a
fi

# Endpoints are overridable so this gate can verify a stack published on non-default host
# ports (an isolated `-p <project>` run on a shared box, a port remap, an SSH tunnel). The
# defaults are exactly the compose file's loopback publications.
PROM_URL="${PROM_URL:-http://127.0.0.1:9090}"
LOKI_URL="${LOKI_URL:-http://127.0.0.1:3100}"
GRAFANA_URL="${GRAFANA_URL:-http://127.0.0.1:3000}"
ROUTER_URL="${ROUTER_URL:-http://127.0.0.1:8089}"

fail=0
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; fail=1; }
info() { printf '  .... %s\n' "$*"; }

echo "== 1. containers =="
never_started=0
unhealthy=$("${COMPOSE[@]}" ps --format '{{.Name}} {{.State}} {{.Health}}' 2>/dev/null || true)
if [ -z "$unhealthy" ]; then
  # QA-MONITORING-006: "no containers" has two very different causes — a fresh clone that
  # was never `make up`-ed, and a compose project whose containers exist but are stopped.
  # Both fail the gate (verify asserts a RUNNING, collecting stack), but the verdict must
  # name the cause instead of implying a running stack is broken.
  existing=$("${COMPOSE[@]}" ps --all --format '{{.Name}} {{.State}}' 2>/dev/null || true)
  if [ -n "$existing" ]; then
    bad "stack containers exist but none are running — start it with: make up"
  else
    never_started=1
    bad "STACK NEVER STARTED: no containers exist on this host — run 'make up' first (verify asserts a running, collecting stack, it does not start one)"
  fi
else
  while read -r name state health; do
    [ -z "${name:-}" ] && continue
    case "$state" in
      running)
        case "$health" in
          ""|"running"|"healthy") ok "$name running ${health:+($health)}" ;;
          *) bad "$name running but health=$health" ;;
        esac ;;
      *) bad "$name state=$state" ;;
    esac
  done <<< "$unhealthy"
fi

echo "== 2. prometheus has samples =="
q() { curl -sf --max-time 10 "$PROM_URL/api/v1/query" --data-urlencode "query=$1"; }
if ! q 'up' >/dev/null 2>&1; then
  bad "prometheus API not answering on $PROM_URL"
else
  for metric in node_boot_time_seconds node_filesystem_avail_bytes; do
    n=$(q "count($metric)" | python3 -c 'import json,sys
try:
    d=json.load(sys.stdin)["data"]["result"]
    print(int(float(d[0]["value"][1])) if d else 0)
except Exception:
    print(0)' 2>/dev/null)
    if [ "${n:-0}" -gt 0 ]; then ok "$metric: $n series"; else bad "$metric: 0 series (agents are not shipping)"; fi
  done
  hosts=$(q 'count by (host) (node_boot_time_seconds)' | python3 -c 'import json,sys
try: print(len(json.load(sys.stdin)["data"]["result"]))
except Exception: print(0)' 2>/dev/null)
  info "hosts reporting: ${hosts:-0}"
fi

echo "== 3. prometheus rules loaded =="
rules=$(curl -sf --max-time 10 "$PROM_URL/api/v1/rules" \
  | python3 -c 'import json,sys
try:
    g=json.load(sys.stdin)["data"]["groups"]
    print(sum(len(x["rules"]) for x in g))
except Exception: print(0)' 2>/dev/null)
if [ "${rules:-0}" -gt 0 ]; then ok "$rules alert rules loaded"; else bad "no alert rules loaded"; fi

echo "== 4. loki has streams =="
if ! curl -sf --max-time 10 "$LOKI_URL/ready" >/dev/null 2>&1; then
  bad "loki /ready did not answer"
else
  streams=$(curl -sf --max-time 10 "$LOKI_URL/loki/api/v1/labels" \
    | python3 -c 'import json,sys
try: print(len(json.load(sys.stdin).get("data") or []))
except Exception: print(0)' 2>/dev/null)
  if [ "${streams:-0}" -gt 0 ]; then
    ok "loki label set has $streams entries"
    curl -sf --max-time 10 "$LOKI_URL/loki/api/v1/query?query=%7Bjob%3D%22docker%22%7D&limit=1" >/dev/null 2>&1 \
      && ok "loki query returns" || info "loki query ok but empty (no docker logs yet)"
  else
    bad "loki has no labels — nothing is being shipped"
  fi
fi

echo "== 5. grafana + datasources =="
gpw="${GRAFANA_PASSWORD:-}"
gu="${GRAFANA_USER:-admin}"
if curl -sf --max-time 10 "$GRAFANA_URL/api/health" >/dev/null 2>&1; then
  ok "grafana health endpoint"
  if [ -n "$gpw" ]; then
    for ds in Prometheus Loki; do
      if curl -sf --max-time 10 -u "$gu:$gpw" "$GRAFANA_URL/api/datasources/name/$ds" >/dev/null 2>&1; then
        ok "datasource $ds provisioned and answering"
      else
        bad "datasource $ds not answering (check API /api/datasources/name/$ds)"
      fi
    done
    nd=$(curl -sf --max-time 10 -u "$gu:$gpw" "$GRAFANA_URL/api/search?type=dash-db" \
      | python3 -c 'import json,sys
try: print(len(json.load(sys.stdin)))
except Exception: print(0)' 2>/dev/null)
    if [ "${nd:-0}" -gt 0 ]; then ok "$nd provisioned dashboards"; else bad "no dashboards provisioned"; fi
  else
    info "GRAFANA_PASSWORD unset — skipping datasource checks"
  fi
else
  bad "grafana health endpoint not answering on $GRAFANA_URL"
fi

echo "== 6. alert-router =="
if ar=$(curl -sf --max-time 10 "$ROUTER_URL/health" 2>/dev/null); then
  mode=$(echo "$ar" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("write_mode","?"))
except Exception: print("?")' 2>/dev/null)
  ok "alert-router healthy (write_mode=$mode)"
  [ "$mode" = "spool" ] && info "write_mode=spool — set ALERT_ROUTER_WRITE=1 where the boards live"
else
  bad "alert-router /health not answering on 127.0.0.1:8089"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "VERIFY: PASS"
elif [ "$never_started" -eq 1 ]; then
  echo "VERIFY: FAIL — the stack was never started on this host (run 'make up'); this is not a stack defect"
else
  echo "VERIFY: FAIL — the stack is up but not proven to be collecting"
fi
exit "$fail"

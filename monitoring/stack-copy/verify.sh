#!/usr/bin/env bash
# verify.sh — assert the stack is WORKING, not merely running.
#
# Green containers prove nothing: every observability stack that ever looked fine while
# collecting nothing had green containers. This checks, in order:
#   1. every container up
#   2. Prometheus has real samples (not an empty TSDB)
#   3. Prometheus has its alert rules loaded
#   4. Loki has real streams and accepts a query
#   5. Grafana is up AND its provisioned datasources answer
#   6. the alert-router is reachable and reports its write mode
#   7. an alert actually TRAVELS the path: Alertmanager accepts one and the router's
#      received counter moves (a reachable /health proved nothing — MON-REV19-01)
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

fail=0
never_started=0
ok()   { printf '  \033[32mPASS\033[0m %s\n' "$*"; }
bad()  { printf '  \033[31mFAIL\033[0m %s\n' "$*"; fail=1; }
info() { printf '  .... %s\n' "$*"; }

echo "== 1. containers =="
unhealthy=$("${COMPOSE[@]}" ps --format '{{.Name}} {{.State}} {{.Health}}' 2>/dev/null || true)
if [ -z "$unhealthy" ]; then
  # "no containers" has two very different causes — a fresh clone that was never `make up`-ed,
  # and a compose project whose containers exist but are stopped. Both fail the gate (verify
  # asserts a RUNNING, collecting stack) but the verdict must name the cause instead of implying
  # a running stack is broken (QA-MONITORING-006, carried from the live host where it was fixed
  # but never committed back to this repo).
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
q() { curl -sf --max-time 10 "http://127.0.0.1:9090/api/v1/query" --data-urlencode "query=$1"; }
if ! q 'up' >/dev/null 2>&1; then
  bad "prometheus API not answering on 127.0.0.1:9090"
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
rules=$(curl -sf --max-time 10 http://127.0.0.1:9090/api/v1/rules \
  | python3 -c 'import json,sys
try:
    g=json.load(sys.stdin)["data"]["groups"]
    print(sum(len(x["rules"]) for x in g))
except Exception: print(0)' 2>/dev/null)
if [ "${rules:-0}" -gt 0 ]; then ok "$rules alert rules loaded"; else bad "no alert rules loaded"; fi

echo "== 4. loki has streams =="
# Loki refuses log selectors on the INSTANT query endpoint ("log queries are not supported as an
# instant query type"), and the label Alloy actually pushes is job="fleet", not "docker"
# (stack/alloy/config.alloy). So the old instant-query probe could only ever fall into its info
# branch — the gate printed a verdict while never proving logs were queryable (MON-REV19-06).
loki_url="${LOKI_URL:-http://127.0.0.1:3100}"
loki_selector="${LOKI_SELECTOR:-}"
[ -n "$loki_selector" ] || loki_selector='{job="fleet"}'
if ! curl -sf --max-time 10 "$loki_url/ready" >/dev/null 2>&1; then
  bad "loki /ready did not answer on $loki_url"
else
  streams=$(curl -sf --max-time 10 "$loki_url/loki/api/v1/labels" \
    | python3 -c 'import json,sys
try: print(len(json.load(sys.stdin).get("data") or []))
except Exception: print(0)' 2>/dev/null)
  if [ "${streams:-0}" -gt 0 ]; then
    ok "loki label set has $streams entries"
    now_s=$(date +%s)
    start_ns=$(( (now_s - 3600) * 1000000000 ))
    end_ns=$(( now_s * 1000000000 ))
    lines=$(curl -sf --max-time 10 -G "$loki_url/loki/api/v1/query_range" \
        --data-urlencode "query=$loki_selector" \
        --data-urlencode "start=$start_ns" --data-urlencode "end=$end_ns" \
        --data-urlencode 'limit=1' \
      | python3 -c 'import json,sys
try:
    res=json.load(sys.stdin).get("data",{}).get("result") or []
    print(sum(len(s.get("values") or []) for s in res))
except Exception:
    print(0)' 2>/dev/null)
    if [ "${lines:-0}" -gt 0 ]; then
      ok "loki query_range returned $lines line(s) for $loki_selector in the last 1h"
    else
      bad "loki query_range returned 0 lines for $loki_selector in the last 1h — logs are not queryable (no logs shipped, or the producer's job label changed)"
    fi
  else
    bad "loki has no labels — nothing is being shipped"
  fi
fi

echo "== 5. grafana + datasources =="
gpw="${GRAFANA_PASSWORD:-}"
gu="${GRAFANA_USER:-admin}"
if curl -sf --max-time 10 "http://127.0.0.1:3000/api/health" >/dev/null 2>&1; then
  ok "grafana health endpoint"
  if [ -n "$gpw" ]; then
    for ds in Prometheus Loki; do
      if curl -sf --max-time 10 -u "$gu:$gpw" "http://127.0.0.1:3000/api/datasources/name/$ds" >/dev/null 2>&1; then
        ok "datasource $ds provisioned and answering"
      else
        bad "datasource $ds not answering (check API /api/datasources/name/$ds)"
      fi
    done
    nd=$(curl -sf --max-time 10 -u "$gu:$gpw" "http://127.0.0.1:3000/api/search?type=dash-db" \
      | python3 -c 'import json,sys
try: print(len(json.load(sys.stdin)))
except Exception: print(0)' 2>/dev/null)
    if [ "${nd:-0}" -gt 0 ]; then ok "$nd provisioned dashboards"; else bad "no dashboards provisioned"; fi
  else
    info "GRAFANA_PASSWORD unset — skipping datasource checks"
  fi
else
  bad "grafana health endpoint not answering on 127.0.0.1:3000"
fi

echo "== 6. alert-router =="
if ar=$(curl -sf --max-time 10 http://127.0.0.1:8089/health 2>/dev/null); then
  mode=$(echo "$ar" | python3 -c 'import json,sys
try: print(json.load(sys.stdin).get("write_mode","?"))
except Exception: print("?")' 2>/dev/null)
  ok "alert-router healthy (write_mode=$mode)"
  [ "$mode" = "spool" ] && info "write_mode=spool — set ALERT_ROUTER_WRITE=1 where the boards live"
else
  bad "alert-router /health not answering on 127.0.0.1:8089"
fi

echo "== 7. alert delivery path =="
# MON-REV19-01: section 6 proves the router is ALIVE, never that an alert travels to it.
# The router token is a mode-600 file owned by the invoking user, so a container running as
# another uid could not read it: every delivery failed with "open /etc/alertmanager/
# router-token: permission denied" while this script still printed PASS. So push a real alert
# through Alertmanager and require the router's received counter to MOVE.
ar_received() {
  curl -sf --max-time 10 http://127.0.0.1:8089/health 2>/dev/null \
    | python3 -c 'import json,sys
try: print(int(json.load(sys.stdin)["counters"]["received_total"]))
except Exception: print(-1)' 2>/dev/null
}
before=$(ar_received)
if [ "${before:--1}" -lt 0 ]; then
  bad "alert-router /health counters unreadable — the delivery path cannot be proven"
elif ! curl -sf --max-time 10 http://127.0.0.1:9093/api/v2/status >/dev/null 2>&1; then
  bad "alertmanager API not answering on 127.0.0.1:9093 — the delivery path is unproven"
else
  # The probe carries an INVALID lane label on purpose (the router's LANE_RE is
  # ^[a-z0-9][a-z0-9._-]{0,62}$): the router counts the delivery and then rejects the alert,
  # so a verify run never writes a board row or a spool event. severity=critical picks the
  # 10s group_wait route; verify_run makes the fingerprint unique so a run inside
  # group_interval is still delivered; startsAt/endsAt bracket the probe so it fires NOW and
  # clears itself if this script dies mid-check (an alert carrying endsAt but no startsAt is
  # read as already-resolved by Alertmanager and never fires).
  runid=$(date +%s)
  stamp=$(python3 -c 'import datetime
now = datetime.datetime.now(datetime.timezone.utc)
fmt = "%Y-%m-%dT%H:%M:%SZ"
print(now.strftime(fmt), (now + datetime.timedelta(seconds=180)).strftime(fmt))' 2>/dev/null)
  starts=${stamp% *}
  ends=${stamp#* }
  probe='[{"labels":{"alertname":"VerifyDeliveryPath","severity":"critical","lane":"verify probe","host":"verify","verify_run":"'"$runid"'"},"annotations":{"summary":"fleet-monitoring verify: delivery-path probe"},"startsAt":"'"$starts"'","endsAt":"'"$ends"'"}]'
  code=$(curl -s -o /dev/null -w '%{http_code}' --max-time 10 -X POST \
    -H 'Content-Type: application/json' -d "$probe" http://127.0.0.1:9093/api/v2/alerts)
  if [ "${code:-000}" != "200" ]; then
    bad "alertmanager would not accept the synthetic alert (HTTP ${code:-no-reply})"
  else
    info "synthetic alert accepted — waiting for group_wait + delivery (up to 45s)"
    after=$before
    for _ in {1..15}; do
      sleep 3
      after=$(ar_received)
      [ "${after:--1}" -gt "$before" ] && break
    done
    if [ "${after:--1}" -gt "$before" ]; then
      ok "delivery path moves the router (received_total $before -> $after)"
    else
      bad "synthetic alert never reached the router (received_total stuck at $before) — Alertmanager cannot deliver; check that uid ${ALERTMANAGER_UID:-1000} can read stack/alertmanager/router-token"
    fi
  fi
  # No cleanup call: Alertmanager v2 has no DELETE /api/v2/alerts (it answers 405), and the
  # probe's endsAt already retires it within 3 minutes. Nothing persists on the board or in
  # the spool either way — the invalid lane label is rejected before any write.
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

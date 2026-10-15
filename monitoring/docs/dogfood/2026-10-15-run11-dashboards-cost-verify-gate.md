# Dogfood run 11 — 2026-10-15 — dashboards-as-code + fleet cost pipeline + verify gate

- angle: FIRST drive of the Grafana dashboards-as-code surface + the Fleet Cost & Tokens
  promise end to end (MON-GAP-012, closed "complete"), plus the documented smoke gate
  (`make verify` / verify.sh). Run 10 same day covered Loki + rootless install; no overlap.
- promise: a user can open Grafana and see real fleet cost & token dashboards rendered from
  files in git; `make verify` is the honest green/red gate for the stack.
- reality (dashboards/cost, live on fleet-monitor): Grafana healthy (13.2.2, /api/health ok),
  6 provisioned dashboards (fleet, fleet-containers, fleet-overview, fleet-uptime-probes,
  host-detail, fleet-services) — the repo's flagship "Fleet Cost & Tokens" (fleet-cost.json,
  6 panels, queries match exporter metric names) is NOT among them: /api/dashboards/uid/fleet-cost
  -> 404. Deployed prometheus has NO hermes-cost active target (16/16 targets other jobs) and
  no cost-exporter container/service exists on the host; deployed compose md5 a83c50dd7 vs repo
  84c9d4e0 (repo compose has the cost-exporter service + home dashboard -> fleet-cost.json).
  hermes_session_est_cost_usd exists as 7876 series with last day label 2026-10-06 (sum that
  day ~$84) — a frozen 9-day-old cost picture; absent_over_time[1h]=1, last_over_time[1h]=empty.
  Exporter code itself is GOOD: ran it locally with HERMES_STATE_DB set — scrape 2.6s cold AND
  warm, 9.2MB body, 9997 hermes_session_est_cost_usd lines incl current day, 200 in 2.7s.
  MON-GAP-012 closed complete 09-27 is repo-true, live-false: the deploy half never landed.
- reality (verify gate): top-level /root/fleet-monitoring/verify.sh reports "FAIL no containers
  found" on a fully healthy 11/11-Up stack (stale pre-QA-MONITORING-006 copy; its step-1
  subshell sees empty output where the same command standalone returns 11 lines);
  scripts/verify.sh (the correct QA-MONITORING-006 version, byte-identical to repo main) PASSES
  100%: 11 containers, prom samples (7 hosts), 19 rules, loki streams, grafana health +
  Prometheus+Loki datasources + 5 dashboards, alert-router healthy write_mode=board.
- reality (fresh-install leg, bunker-mvp agent 441ad5e0, spawn->destroy): bunkerd active on
  bunker-mvp only (bunker3/2/4 all ssh-unreachable); repo is S3-hosted git (origin
  s3://kara-reports/...) so sanctioned tar-over-ssh fallback used (git archive HEAD, 44KB).
  make config PASS + check-env PASS in 2s; make up failed at 76s: 'failed to read dockerfile'
  for alert-router — the repo's canonical tree (fleet-monitoring/stack/alert-router/) ships
  router.py + test but NO Dockerfile (build context ./alert-router, compose line 156). The
  Dockerfile exists only in the fleet-monitoring git history (gh/ft009 @ e678d0f7a /
  stack/alert-router/Dockerfile) and on the live host — main's canonical subtree never had it
  committed. Run 8 (2026-10-12) scp'd a Dockerfile as a rescue and called the closure of 021
  "holds for real clones" — DISPROVEN on main@01efa2ad8: a tar/clone user still cannot build.
- perf: exporter scrape 2.6s/9.2MB (fine for a 30s scrape interval — but it isn't scraped);
  check-env 2s; nothing user-noticeably slow beyond the make-up blocker -> no PERF rows.
- rows: MON-DOGFOOD-039 (P1 cost pipeline dead live), MON-DOGFOOD-040 (P2 stale top-level
  verify.sh false-FAIL on healthy stack)
- install_seconds: spawn->config-pass ~5min; make-up FAIL 76s (Dockerfile absent from canonical tree)
- foreman woken: no (read-only dogfood lane; rows wait on a live lane)
- verdict: FAILED-product for the cost-dashboard promise (highest-value dashboard not deployed,
  series frozen at 2026-10-06) and for fresh install on main (alert-router Dockerfile missing
  from canonical tree); SHIPPABLE for the core observability surface (verify.sh PASS 6/6 from scripts/)

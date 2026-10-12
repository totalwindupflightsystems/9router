# Dogfood run 9 — traces surface + fresh-rootless install re-proof (2026-10-12)

Sibling run to run 8 (same day; run 8 = bunker-mvp angle). This run drove the ONE
product surface no earlier run had touched — the traces pipeline — and re-proved
the fresh-rootless install on a second host at origin/main 4c9d39b.

## Promise under test

1. An OTLP producer can push traces to the published ingest ports and find them
   again through search, Grafana, and Prometheus span-metrics.
2. A fresh machine can follow the README (quickstart + Fresh-host requirements)
   to a running stack, rootless.

## What was done (real use, not tests)

### Traces (fleet-monitor production stack)

- Probed topology: `docker inspect mon-tempo mon-alloy --format {{json .NetworkSettings.Ports}}`
  -> mon-tempo owns host 4317/4318 (0.0.0.0) + 3200 (loopback); mon-alloy only 12345.
- Sent a genuine OTLP/JSON trace (service dogfood-run8, span dogfood-probe-span,
  random trace id e29d6e5f0373c0d8167e946f9fb1fcd6) to http://fleet-monitor:4318/v1/traces:
  HTTP 200 `{"partialSuccess":{}}` in 399-404ms (cold over Tailscale relay).
- Tempo query API (host-local 3200 via ssh): `/api/traces/<id>` 200;
  `/api/search` and tag search `resource.service.name="dogfood-run8"` both return
  the trace (4ms; 19ms via relay). Note: `service.name=` (without the `resource.`
  prefix) is a TraceQL parse error on this Tempo build — the working form is
  `resource.service.name`.
- Grafana: datasource uid=tempo health OK; POST /api/ds/query with TraceQL
  `{ resource.service.name="dogfood-run8" }` returns a 200 frame listing the trace.
- Prometheus: `{source="tempo"}` shows traces_spanmetrics_latency_* series with
  service="dogfood-run8" within seconds of the push — the metrics_generator
  remote_write leg works. (Its counters sat at active_series=0 for 10 days
  before this probe: nobody had ever pushed a trace.)
- Loki correlation (the tracesToLogs / "Open trace" link): grepping Loki for the
  trace id over 1h returns exactly one line — Tempo's own access log. No fleet
  producer emits trace ids, so the provisioned cross-links can never fire.

### Fresh install (bunker-las-02, agent f875e513, TTL 2h, destroyed after)

- GitHub https clone of totalwindupflightsystems/fleet-monitoring fails on the
  agent (repo private; "could not read Username"). Used the sanctioned tar-over-ssh
  fallback from a `git archive origin/main` of the local checkout — no visibility
  or permission changes.
- `make bootstrap` rc=2: rclone install requires sudo (`curl | sudo bash`,
  scripts/bootstrap.sh:38-44); a bare agent cannot pass. Hand-installed rclone
  1.75.2 to ~/bin to keep going.
- `docker compose` plugin missing on the fresh box (README bullet covers this one)
  and `docker buildx >= 0.17` is ALSO required by compose v5.6's build path but is
  named nowhere (installed 0.17.0 to ~/.docker/cli-plugins).
- `make up COMPOSE_EXTRA=~/override.yml`: after fixing a poisoned
  stack/loki/loki-config.active.yml DIRECTORY (see MON-DOGFOOD-031), loki came up.
  Final state 5/7 core: grafana (200), prometheus, renderer (healthy), blackbox,
  loki Up; cadvisor fails on RootlessKit 127.0.0.1:8080 collision; alert-router
  fails on root-owned /var/lib/fleet-monitoring/spool; alloy not started.
- Rootless bunker-daemon socket note: the agent's own user docker context is dead
  (`/run/user/1003/docker.sock` missing); the working daemon is the per-agent
  bunker socket `/run/bunker/<agent>/docker.sock` via DOCKER_HOST.

## Verdict

- Traces: SHIPPABLE — the full chain (push -> store -> search -> Grafana ->
  span-metrics) works live, fast, with real data. The gaps are wiring truth
  (MON-DOGFOOD-033) and the dead correlation links (034), not function.
- Fresh rootless install: FAILED-product — same verdict run 8 reached on a
  different host with different blockers, so the finding is robust.

## Findings filed (rows are on .coding-hermes/board/tasks.jsonl)

| id | P | summary |
|---|---|---|
| MON-DOGFOOD-030 | 2 | README's remediation file stack/docker-compose.override.yml does not exist in the repo |
| MON-DOGFOOD-031 | 1 | render-configs.sh can silently create the loki active-config as a directory; Loki crash-loops while make stays green |
| MON-DOGFOOD-032 | 2 | Rootless install still blocked (root-owned mounts, sudo-only bootstrap, buildx unprereq'd) |
| MON-DOGFOOD-033 | 3 | Traces ingest miswired vs config comments; entirely undocumented (extends DOC-001) |
| MON-DOGFOOD-034 | 3 | Trace->logs correlation provisioned but structurally empty |

## Performance census

push 399-404ms cold (tailnet relay), ~0.4s warm; Tempo search 4ms host-local /
19ms relayed; Grafana ds/query fast. Nothing a user would call slow — no PERF
rows filed (a win nobody can feel is not a finding).

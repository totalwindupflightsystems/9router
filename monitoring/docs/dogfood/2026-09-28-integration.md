# Dogfood integration report — monitoring lane, 2026-09-28

Lane: monitoring-dogfood (tick 2026-09-28-12-40-24). Verdict: PROMISING-BUT-ROUNDED
(🟡 leaning 🔴 for the alert chain: the pipeline whose whole job is "an alert becomes a
row" was silently dead while a live critical alert fired for 2 hours).

## Promise under test

"The monitoring stack's job is hosting; this lane's job is making its output become
executed work. An alert that fires and never becomes a row is a bug in this lane."
Workflow: drain the spool → triage board findings against the live stack → stack work
over ssh to fleet-monitor, proved from outside.

## What was actually done (real use, not tests)

1. **Drain leg (the lane's own documented command):**
   `MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh` — exit 0,
   "spool empty — nothing to drain", **3.5s wall** (warm; rsync pull + parse). Correct
   behavior, and the spool really was empty — but see finding 1: it was empty because
   deliveries were broken upstream, not because everything was fine.
2. **Live stack census from outside:** all 7 containers Up (grafana 13.2.2, prometheus
   v3.15.0, loki 3.7.8, alloy v1.20.0, alertmanager, alert-router, renderer). Prometheus
   `/api/v1/query` answered `up` for all targets; Loki `/ready` = ready; Grafana
   `/api/health` = database ok. One ACTIVE alert: `OOMKillsOccurring host=bunker-mvp`
   since 11:04Z — verified REAL against Prometheus: `increase(node_vmstat_oom_kill
   {host="bunker-mvp"}[1h])` ≈ 17.
3. **The chain under a live alert** (the flagship workflow): alert shows
   `receivers=[alert-router]` in Alertmanager, yet alert-router counters read
   received_total=2 (both from 09-27's synthetic test), rows_spooled=2, spool empty.
   Alertmanager logs: every webhook POST failing for ~16h with
   `unable to read file /etc/alertmanager/router-token: permission denied`
   (2426 failed notification requests, 2426 total = 100% failure, silent).
   Reproduced the permission state exactly: `docker exec mon-alertmanager cat
   /etc/alertmanager/router-token` → Permission denied; container uid=65534 (nobody),
   host file root:root 0600 (chmod 15:50 during the 09-27 spoolfix; container started
   15:41 — the fix broke its own reader 9 minutes later).
4. **Lane-routing audit:** every fleet-health rule labels `lane=hermes-fleet-ops`;
   scheduler.db has no such lane and no such board exists on the drain host → once
   delivery is fixed, rows spool forever (drain reports "no board for lane ...").
5. **Install leg (ephemeral bunker, bunker-las-03, agent 1a82f5a8, destroyed after):**
   full tree (72 files) transferred from fleet-monitor, documented path run:
   - `make env` → ok (0s)
   - `make check-env` with placeholder .env → **correctly refused** with clear
     PLACEHOLDER/MISSING lines (this gate is good)
   - real throwaway .env → check-env ok, `make render-configs` ok ("wrote
     stack/alertmanager/router-token (mode 600)")
   - `make config` → **FAILED**: lint's synthetic env lacks `RENDERER_TOKEN` (compose
     now requires it). Confirmed the SAME failure on the live host — the gate is red
     everywhere. Also: lint's Loki check crashes with a raw PyYAML ModuleNotFoundError
     on a fresh box (no graceful skip, unlike the shellcheck path).
   - Stack up anyway (bypassing the gate): `docker compose build alert-router` 8s;
     `up -d` → 5/7 services running (grafana answering /api/health, prometheus ready,
     alert-router healthy + scraped by the fresh prometheus, renderer up). Loki
     restart-looped only because the test .env's S3 endpoint is fake (compactor init
     needs the delete-store object — real-S3-only behavior, arguably fine); alertmanager
     was blocked by an alloy host-mount (`/var/lib/fleet-monitoring/node-exporter-textfile`
     is not creatable by a rootless user — see PERF/INSTALL notes below).
   - Bunker-infra notes: rootless docker flapped at spawn ("failed to lock
     dockerd-rootless/lock"); the bunkerd-managed rootlesskit was already serving
     `unix:///run/bunker/<id>/docker.sock` — use that as DOCKER_HOST, the systemd unit
     is a conflicting duplicate.
   - Install timing: tree transfer ~10s, build 8s, up ~10s. The only slow parts are
     official-image pulls (network-bound). Nothing here justifies a PERF row; the slow
     path is Docker Hub, not this project.
6. **Destroy:** `bunker destroy 1a82f5a8` — agent gone, key removed. No repo
   visibility/permission was changed anywhere.

## Errors hit and what they mean

| Error | Meaning |
|---|---|
| `unable to read file /etc/alertmanager/router-token: permission denied` | token file uid/perm vs container uid mismatch — finding MON-DOGFOOD-001 |
| `required variable RENDERER_TOKEN is missing a value` during `make config` | lint env heredoc predates the compose requirement — MON-DOGFOOD-003 |
| `ModuleNotFoundError: No module named 'yaml'` in lint on fresh box | lint assumes PyYAML; fresh-machine docs gap — MON-DOGFOOD-003 |
| `mkdir /var/lib/fleet-monitoring/node-exporter-textfile: permission denied` | compose host-mounts an absolute /var/lib path; rootless docker cannot create it — bind-mount spec assumes a root host; worth its own row if fleet agents should ever run the stack rootless |
| `failed to get s3 object ... no such host` (loki) | loki compactor hard-requires reachable S3 at boot; a fake .env gives a restart loop, not a config error — document in runbook |

## What worked well

- `check-env` refusing placeholders is a genuinely good gate (documented failure mode
  "stack comes up green with changeme" is real and it prevents it).
- The alert→row contract in docs/alerting-to-agents.md is clear, debuggable, and every
  hop is inspectable exactly as claimed.
- router /health exposes counters (received/spooled/deduped/errors) — that surface is
  what made the dead-pipeline diagnosis a 5-minute job.
- Prometheus/Loki/Grafana came up fresh and correct from the tree in minutes.

## Bottom line

The stack itself is solid and rebuildable; the alert→work chain — the lane's entire
reason to exist — was silently broken by its own hardening change. Fix MON-DOGFOOD-001
first; it is a one-line chown/restart plus a tripwire so the next silent death is loud.

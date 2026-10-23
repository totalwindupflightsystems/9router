# Monitoring lane — agent usage skill

What this project is: the fleet-side lane for the fleet monitoring stack. The stack
(Prometheus, Loki, Grafana, Alloy, Alertmanager, a custom alert-router) runs on host
`fleet-monitor` under `/root/fleet-monitoring/` — deliberately NOT in this workdir.
This lane's job: make fired alerts become executed work, and drive stack changes as
reviewable copies here.

## Entry points

- Spool drain (run HERE, idempotent): `MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh`
  Pulls `/var/lib/fleet-monitoring/spool/` over ssh and appends each row to
  `<lane>/.coding-hermes/board/tasks.jsonl` via board_append.py. Unwritable lanes are
  reported, never dropped. Clearing the remote spool is deliberately manual.
- Board: `.coding-hermes/board/tasks.jsonl` (MON-GAP-* = stack work, MON-<LANE>-<FP8>-<date> = live findings).
- Stack host: ssh alias `fleet-monitor` (root). Live dir `/root/fleet-monitoring/` is
  git-less; copy anything you change into this workdir so the diff is reviewable.
- Alert router counters: `ssh fleet-monitor 'curl -s http://localhost:8089/health'` —
  received/spooled/deduped/appended totals. This is the tripwire surface for the chain.

## The chain (docs/alerting-to-agents.md on the host)

rule fires → Alertmanager → POST /webhook (bearer token from
`/etc/alertmanager/router-token`) → router appends `MON-<lane>-<fp8>-<date>` row →
lane foreman works it. Router writes direct when the lane has a local board under its
BOARD_ROOT, else spools for the drain. One row per problem per day (fingerprint+date id).

## Run commands (on the host, /root/fleet-monitoring)

- `make up` / `make ps` / `make logs` — start/status/tail. NOTE: `make config` can
  report FAIL on `alloy fmt` (not gofmt-clean config.alloy); fix with `alloy fmt`
  then retry. RENDERER_TOKEN lint (MON-DOGFOOD-003) is fixed — compose is fine.
- `make verify` — asserts data is arriving (metrics, logs, datasources).
- `make check-env` — refuses placeholder .env; run it before anything.
- `make backup` / `make restore-check` — S3 snapshot + readability assertion.

## Common pitfalls (learned 2026-09-28, real use)

- **A green spool-drain can hide a dead pipeline.** Check the router /health counters
  AND alertmanager's `alertmanager_notification_requests_failed_total` before trusting
  "spool empty". The token file `stack/alertmanager/router-token` must stay readable by
  the alertmanager container's uid (65534/nobody) — a 0600 root-owned fix is exactly
  what silently killed all deliveries once.
- **All fleet-health rules label `lane: monitoring`** (MON-DOGFOOD-002 fixed — all 20 rules
  carry `lane: monitoring`, not `hermes-fleet-ops`).
- Verify alert text against Prometheus (`/api/v1/query` with the rule's expr) before
  triaging; the alert alone is not evidence.
- Rootless docker on bunker agents: the bunkerd socket
  `unix:///run/bunker/<id>/docker.sock` is the working daemon; the per-user systemd
  unit flaps on a state-dir lock. Export DOCKER_HOST to the bunkerd socket.
- Loki hard-requires reachable S3 at boot (compactor delete-store) — a fake endpoint
  gives a restart loop, not a config error.

## Backup/restore surface (run 3, 2026-09-30)

- **Backup/restore is wired as: timer → root-level `backup-to-s3.sh` +
  `restore-check.sh`, `EnvironmentFile=.env`.** The nightly timer
  (`fleet-monitoring-backup.timer`, 03:00 UTC) is the production path; `make
  backup` is documented but currently broken (env never reaches the script,
  MON-DOGFOOD-010). Until that's fixed, source `.env` first:
  `set -a && . ./.env && set +a && scripts/backup-to-s3.sh`.
- **Verify the TIMER's manifests, not your manual run's.** journalctl -u
  fleet-monitoring-backup.service shows what production actually shipped —
  as of 09-30 the timer sets lacked the git bundle (MON-DOGFOOD-009), so the
  rebuild runbook's input was missing while restore-check PASSed.
- **A "no git bundle in this set" from restore-check is a red flag, not info** —
  it currently exits 0; treat it as failure until MON-DOGFOOD-009 lands.
- restore-check PASS on a set you just made by hand proves the guard works on
  good sets; it says nothing about what the timer produced last night.

## Reading an alert row as an operator (run 12, 2026-10-20)

The board IS the operator's work list, and an alert row is a claim that needs checking:

- **Verify the claim on a second leg** before acting: query the rule's own metric —
  `ALERTS{alertname="X",host="H"}` for the firing window and the metric expression itself
  (`node_filesystem_avail_bytes/size` for DiskFull). Run 12 confirmed a real 0%-free event
  this way; the alert was true.
- **The row's `generator:` link is dead** (docker-internal Prometheus hostname, e.g.
  `http://83163ca754e7:9090/graph?...` — `getent hosts` says no such host). Use the query
  text in the row; do not hand that URL to a user (MON-DOGFOOD-043).
- **Resolutions are NOT in events.jsonl** while the router spools: they land in
  `tasks.jsonl` as `type: alert-resolved` rows with no status (80 today). Grep for
  `<row-id>-RESOLVED` in tasks.jsonl (MON-DOGFOOD-041).
- **A resolved condition leaves its row `pending`** and re-mints a fresh row daily
  (16/15/14/13/12 mints on five fingerprints) — treat the pending list as "fired recently",
  not "still broken" (MON-DOGFOOD-042).
- **The UI is loopback-only on the host**: `ssh -N -L 13000:127.0.0.1:3000 fleet-monitor`,
  then POST `/login` with `GRAFANA_USER`/`GRAFANA_PASSWORD` from the host `.env`. Headless
  Chrome rendered no panel grid for any dashboard (216 DOM nodes, empty `page-panes`, zero
  `/api/ds/query`) while the API legs were green — an environment limitation, not a finding.
- **The drain is the expensive part**: 42-68s wall / 38-50s CPU per 15-min run to append 0-2
  rows (3 process spawns per spool line, ~79ms/line, spool +54 lines/day) — PERF-1. Use
  `DRY=1` when you only want to see what it would do.

## Silencing a chronic alert (verified live 2026-10-20, run 14)

Silences live in **Alertmanager**, not in the alert-router — the router has no silence
surface at all (it mints rows from whatever AM delivers, so a silence stops both the
notification AND the row). AM's API is loopback-only and unauthenticated; drive it from the
host:

```bash
ssh fleet-monitor
AM=http://127.0.0.1:9093
NOW=$(date -u +%Y-%m-%dT%H:%M:%SZ); END=$(date -u -d "+2 hours" +%Y-%m-%dT%H:%M:%SZ)
# 1. create (matchers are ANDed; keep them narrow — alertname + host)
curl -s -X POST $AM/api/v2/silences -H 'Content-Type: application/json' -d "{
  \"matchers\":[{\"name\":\"alertname\",\"value\":\"TargetUnreachable\",\"isRegex\":false},
               {\"name\":\"host\",\"value\":\"standby-cx53-01-2147\",\"isRegex\":false}],
  \"startsAt\":\"$NOW\",\"endsAt\":\"$END\",\"createdBy\":\"<you>\",\"comment\":\"why\"}"
# 2. verify it MATCHES what you meant (silencedBy on the alerts, and NOT on a control alert)
curl -s $AM/api/v2/alerts | python3 -m json.tool | grep -A2 silencedBy
# 3. remove when done; a deleted silence stays listed as state "expired" (0 active)
curl -s -X DELETE $AM/api/v2/silence/<silenceID>
```

Facts that matter for planning a silence (read from `/api/v2/status`):
`group_wait 30s`, `group_interval 5m`, `repeat_interval 12h`, `resolve_timeout 5m`,
receiver `alert-router`, `send_resolved: true`. Consequence: a chronic alert re-notifies at
most every 12 h, so **a short silence window cannot be validated by counting router
deliveries** — validate on `status.silencedBy` instead. A silence is a stopgap: it lapses
and the alert re-mints a row the moment it does, so it never replaces the underlying fix.

## Continuous profiling (pyroscope) — the working probe set

`mon-pyroscope` (`grafana/pyroscope:1.9.0`, published `0.0.0.0:4040`) IS ingesting; the
URL the fleet perf skill documents (`/pyroscope/api/v1/labels`) **404s on 1.9.0**. Use:

```bash
P=http://127.0.0.1:4040
curl -s $P/ready                                   # "ready"
curl -s $P/api/v1/status/buildinfo                 # {"version":"1.9.0",...}
curl -s -X POST -H 'Content-Type: application/json' -d '{}' \
     $P/querier.v1.QuerierService/ProfileTypes     # profile types present
curl -s -X POST -H 'Content-Type: application/json' -d '{"matchers":[]}' \
     $P/querier.v1.QuerierService/Series           # labelsSet -> profiles IS in the store
docker logs --tail 5 mon-pyroscope                 # hourly "head successfully written to block"
# Grafana: /api/datasources/uid/pyroscope/health -> "Data source is working"
```


## Drain (MON-GAP-032 contract, verified 2026-10-23 run 15)

The drain is the operator's main verb. The deployed copy lives at
`~/.hermes/scripts/drain-board-rows.sh` (md5 53657b05…); repo copies exist only as
`monitoring/fixes/mon-gap-{030,032}/drain-board-rows.sh` (see MON-DOGFOOD-048 for the
propagation gap).

```sh
MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh      # real
DRY=1 MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh # exact plan only
```

Contract as verified (evidence: docs/dogfood/2026-10-23-run15-*):
- repeat drain: appended=0 skipped=856 (idempotent, cumulative spool re-read is safe);
- resolved events go to events.jsonl (NOT tasks.jsonl); one copy per id across EITHER file;
- two concurrent drains: the second exits rc=3 `another drain already holds` untouched;
- a re-fired alert re-appears only when ALL of: board row terminal, non-resolved spool line
  exists, alert firing in prometheus right now, id dated TODAY — suppressions print
  `olddate-suppressed=` / `stale-suppressed=` counts (93+2 typical on the live spool);
- scratch-only testing hooks: `BOARD_ROOT SPOOL APPEND DRY ALERTS_FILE PROM_LOCAL` —
  stub rsync on PATH with `FIXTURE_SPOOL_DIR`; battery at
  monitoring/fixes/mon-gap-032/test-drain-resolved-dedupe.sh (13 asserts, offline).
- cost: ~9s wall / 2.5s CPU per run on the 856-line spool (was 56-68s before MON-GAP-032);
  steady-state timer runs read ~2s in the journal. Nothing user-noticeable.
- pitfalls: NEVER clear the remote spool before checking the drain's landed rows; the
  scratch refire experiment must set `ALERTS_FILE` to a REAl /api/v1/alerts snapshot,
  or every refire suppresses with `unverified-suppressed` (fail-closed liveness).
- known harness trap (MON-DOGFOOD-050): bunker-qa.sh BUNKER_QA_SUBDIR does nothing when
  the dispatched dir IS the git root — drive install legs via git-archive
  clone-equivalent extraction instead, and discard battery cells that graded the parent.

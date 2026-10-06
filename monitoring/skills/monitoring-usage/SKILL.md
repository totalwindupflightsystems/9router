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

- `make up` / `make ps` / `make logs` — start/status/tail (NOTE: `make config` lint
  currently fails on RENDERER_TOKEN — see MON-DOGFOOD-003; compose itself is fine).
- `make verify` — asserts data is arriving (metrics, logs, datasources).
- `make check-env` — refuses placeholder .env; run it before anything.
- `make backup` / `make restore-check` — S3 snapshot + readability assertion.

## Common pitfalls (learned 2026-09-28, real use)

- **A green spool-drain can hide a dead pipeline.** Check the router /health counters
  AND alertmanager's `alertmanager_notification_requests_failed_total` before trusting
  "spool empty". The token file `stack/alertmanager/router-token` must stay readable by
  the alertmanager container's uid (65534/nobody) — a 0600 root-owned fix is exactly
  what silently killed all deliveries once.
- **`lane=hermes-fleet-ops` on all fleet-health rules has no matching lane** — rows will
  spool forever until the lane exists or labels are repointed (MON-DOGFOOD-002).
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

# Monitoring lane — diagnostic trail

How this system is built, why, the errors hit along the way, and the right way to do
things. (2026-09-28 dogfood run; see docs/dogfood/2026-09-28-integration.md for the
full narrative.)

## Architecture, in one breath

One Hetzner-class host (`fleet-monitor`) runs the whole observability stack as compose
services under `/root/fleet-monitoring/stack/`: node/container metrics → Alloy agents
on fleet hosts → Prometheus (rules in `alerts/rules/*.yml`, every rule labels a `lane`)
→ Alertmanager (routes to a webhook receiver) → custom `alert-router` (a single-file
Python service, `stack/alert-router/router.py`) whose only job is to turn alert JSON
into `MON-<lane>-<fp8>-<YYYYMMDD>` board rows, appended directly when the lane has a
local board, else spooled to `/var/lib/fleet-monitoring/spool/` for the fleet-side
`drain-board-rows.sh`. Row id = fingerprint+day gives idempotence (one row per problem
per day); `rows_deduped_total` is the counter that proves it.

Design choices worth keeping:

- **File-based secrets**: the router token is mounted as a file, never in process args
  or `docker inspect`. Good idea — but it created the 09-28 outage (see below): the
  hardening changed the file's uid/perm without re-checking the reader's uid.
- **check-env gate**: refuses to deploy with placeholder secrets because the failure
  mode (green stack, changeme password, router rejecting every webhook) is real.
- **Spool-not-drop**: a row whose lane has no board is spooled and reported UNWRITABLE
  by the drain, so routing mistakes are visible instead of silent.
- **Dashboards as code** (`grafana/provisioning/`, `dashboards/*.json`): never clicked
  into the UI; the repo is the only source of truth.

## The outage the dogfood found (2026-09-28)

A live critical alert (OOMKillsOccurring, bunker-mvp, ~17 kills in 1h) fired at 11:04Z
and never became a row. Diagnosis path, in the order that worked:

1. `curl localhost:9093/api/v2/alerts` on fleet-monitor → alert active, receiver
   alert-router. Spool empty, router received_total=2 (yesterday's synthetic only).
2. Alertmanager logs: `unable to read file /etc/alertmanager/router-token: permission
   denied`, repeating every repeat_interval, `notification_requests_failed_total
   {integration="webhook"} = 2426` out of 2426 total.
3. `docker exec mon-alertmanager id` → uid 65534; host file `stat` → root:root 0600,
   mtime 15:50 — nine minutes AFTER the container started (15:41) during the previous
   day's spoolfix. The hardening change broke its own only reader.

Lesson: a file permission is an interface. When you tighten a file a container reads,
`docker exec <c> cat <file>` is the two-second check; and a dead alert-pipeline needs a
tripwire (failed-notifications counter alert) because by construction nothing else will
ever tell you.

## Fresh-machine install findings

The repo IS rebuildable: `make env → check-env → render-configs` behave exactly as
documented (check-env correctly refuses placeholders; render-configs writes the token
file at mode 600, git-untracked). But `make config` — the documented gate inside
`make up` — fails on every machine including the live one, because `scripts/lint-configs.sh`
builds a synthetic lint env whose variable list predates compose's `RENDERER_TOKEN:?`
requirement. Second fresh-host gap: lint's Loki step imports PyYAML and dies with a raw
traceback on a bare box instead of a labelled skip (the shellcheck step already models
that graceful pattern). Both filed as MON-DOGFOOD-003.

Rootless-docker notes for ephemeral hosts: bunkerd runs its own rootlesskit with the
socket at `unix:///run/bunker/<id>/docker.sock`; the per-user systemd docker unit is a
conflicting duplicate that flaps on a state-dir lock. Use the bunkerd socket. Alloy's
compose file bind-mounts an absolute `/var/lib/fleet-monitoring/...` host path that a
rootless daemon cannot create — the stack currently assumes a root host (true for
fleet-monitor).

## The right way to triage a monitoring finding (this lane)

1. Drain first (`MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh`),
   note appended AND unwritable rows.
2. Check the router /health counters — they are the chain's pulse.
3. For any board finding, re-verify against Prometheus with the rule's own expr before
   believing the alert text.
4. Stack changes: edit on the host, back up the file, `docker compose up -d` the
   changed service, prove from outside (curl the port / query the API), copy the
   changed file into this workdir for review.

## The backup surface — how it works, and the two traps that broke it (2026-09-30 run 3)

How it is built: `backup-to-s3.sh` takes a Prometheus TSDB snapshot through the admin
API (never tar an open TSDB), dumps Grafana through sqlite `.backup` when the image
has sqlite3 (it does not — see MON-DOGFOOD-011), bundles the host repo with
`git bundle create --all`, writes a sha256 MANIFEST, uploads with rclone to
`s3://karahermes-hel/monitoring/<ts>/`, and leaves a `latest` pointer plus a
node-exporter textfile stamp that Prometheus scrapes as
`monitoring_backup_last_success_timestamp_seconds` (alert `BackupFreshnessStale`,
48h, runbook anchor exists). `restore-check.sh` downloads the newest set, verifies
checksums, `git bundle verify`s the bundle, and tars-tests the snapshot. A systemd
timer runs both nightly (03:00 UTC +600r) with `EnvironmentFile=.env`.

Trap 1 — two copies of the script: the unit execs the root-level
`/root/fleet-monitoring/backup-to-s3.sh`; the *fixed* canonical copy lives in
`scripts/backup-to-s3.sh`. The root-level one still carries the old
`cd $(dirname $0)` bug, so the nightly bundle silently never happened. When you fix
a script on the host, deploy BOTH copies (or repoint ExecStart at `scripts/`).

Trap 2 — git under systemd: a oneshot unit gets no PAM env, so `HOME` is unset and
git's dubious-ownership guard refuses `/root/fleet-monitoring`
(repro: `env -u HOME git rev-parse --git-dir` → fatal; `HOME=/root` → works). The
bundle step skips silently and the manifest prints `git_head: none`. Fix at the unit
(`Environment=HOME=/root`) or in the script (`git -c safe.directory=<repo>`), and
make restore-check FAIL when the manifest has no bundle — a guard must not pass its
own missing payload.

The right way to verify a backup leg (learned here): run the real command once
manually, then `journalctl -u fleet-monitoring-backup.service --since <date>` and
read the manifest the TIMER produced — not the one your manual run produced. The
timer's 3-file set vs the manual run's 5-file set was the whole finding; a green
restore-check on my own successful run would have hidden it.

Metric-text nit worth remembering: the stamp's HELP line reads "uploached" (typo,
MON-DOGFOOD-011b) — cosmetic, but user-facing metric text ships to every dashboard.

## 2026-10-20 (run 12) — operator triage: the alert row is the product; here is how to read it

How to pick up a live alert as an operator (reproducible, all read-only):

```bash
# 1. the row + its claim
python3 - <<'PY'   # or grep the tail of .coding-hermes/board/tasks.jsonl
PY
grep -oE '"id": ?"MON-MONITORING-[0-9A-F]{8}-[0-9]{8}"' .coding-hermes/board/tasks.jsonl | tail
# 2. is the alert still firing? (AM is loopback-only on the host)
ssh fleet-monitor 'curl -s http://127.0.0.1:9093/api/v2/alerts | head -c 400'
ssh fleet-monitor 'curl -s "http://127.0.0.1:9090/api/v1/alerts"'
# 3. was it TRUE? query the same metric the rule used (cross-leg of the alert)
ssh fleet-monitor 'curl -s "http://127.0.0.1:9090/api/v1/query_range" \
  --data-urlencode "query=(node_filesystem_avail_bytes{instance=\"<host>\"} / node_filesystem_size_bytes{instance=\"<host>\"})" \
  --data-urlencode "start=$(date -u -d '-3 hours' +%s)" --data-urlencode "end=$(date -u +%s)" --data-urlencode step=300'
# 4. the row's evidence link — DO NOT trust it (see below)
# 5. the resolution trail — it is NOT in events.jsonl (see below)
grep -c '<FP8>-<date>-RESOLVED' .coding-hermes/board/tasks.jsonl
```

Hard-won facts from run 12 (each one is a filed row, not a guess):

- **The `generator:` link in every alert row is dead.** It is Alertmanager's generatorURL,
  which carries the Prometheus CONTAINER hostname (`http://83163ca754e7:9090/graph?...`).
  `curl` rc=6 / `getent hosts 83163ca754e7` → no such host, from any operator box
  (MON-DOGFOOD-043). Give an operator the query text, not that URL.
- **Resolution events do NOT land in `events.jsonl`.** With the router in spool mode
  (the monitoring host has no lane boards) `emit_resolution` spools a `type: alert-resolved`
  row into the same `board-rows.jsonl` as task rows, and `drain-board-rows.sh` appends every
  spool line to `tasks.jsonl` routing only by `lane` — never by `type`. 80 such status-less
  rows are on the task board today (MON-DOGFOOD-041). To find a resolution, grep tasks.jsonl
  for `<id>-RESOLVED`, not events.jsonl.
- **A resolved alert does not close its row.** The P0 row stays `pending` until a human or
  the foreman folds it; the resolution is a separate unlinked row ~2 min later, drained at the
  next 15-min timer tick (MON-DOGFOOD-042). Expect pending rows for conditions that are over,
  and expect the same fingerprint to re-mint a fresh row the next day (16/15/14/13/12 mints
  measured on five fingerprints) — the id embeds the UTC date on purpose.
- **The drain is the lane's real cost, not the alerting.** 42-68s wall / 38-50s CPU per run,
  every 15 minutes, to append 0-2 rows: `drain-board-rows.sh` spawns 2× python3 + 1× grep per
  spool line (710 lines today) and re-greps the 963KB board each time (~79ms/line), and the
  spool is append-only so the cost grows ~54 lines/day (PERF-1). Do not add a fourth
  per-line process; a single-pass Python drain is the fix.
- **`boardctl validate` is RED on this board** (7 errors: the lane's own triage statuses
  `duplicate` / `verified-benign` / `unverified-expired` are outside the canon
  {blocked,complete,failed,in_progress,pending,review}) — a board reader must not assume a
  green validate, and any new row must not add to it (MON-DOGFOOD-044).
- **Reaching the UI**: Grafana and Alertmanager bind 127.0.0.1 on fleet-monitor. There is no
  documented access path — the working move is `ssh -N -L 13000:127.0.0.1:3000 fleet-monitor`
  and then `curl -X POST -H 'Content-Type: application/json' -d '{"user":..,"password":..}'
  http://localhost:13000/login` (the password is `GRAFANA_PASSWORD` in the host `.env`).
  In headless Chrome the dashboard route rendered no panel grid at all (216 DOM nodes, empty
  `page-panes`, zero `/api/ds/query` calls) for every dashboard while the API legs were green;
  treat "panels don't render headless" as an environment limitation, not a product defect,
  until someone reproduces it in a headed browser.

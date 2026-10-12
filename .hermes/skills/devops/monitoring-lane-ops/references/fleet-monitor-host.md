# fleet-monitor host reference

Host: ssh alias `fleet-monitor` (2.29.29.57, tailnet 100.122.154.108, root).
Stack: Grafana, Prometheus v3, Loki, Alloy, Alertmanager, alert-router — all under
`/root/fleet-monitoring/` (docker compose; container names prefixed `mon-`).
Spool: `/var/lib/fleet-monitoring/spool/board-rows.jsonl` on the host; drained from the lane box
via `MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh`.

## fleet-monitor quirks

- No `jq` on the host (has `python3`) — pull raw JSON back (scp or ssh cat) and parse locally.
- Grafana admin API from the host: creds are `GRAFANA_USER`/`GRAFANA_PASSWORD` in
  `/root/fleet-monitoring/.env` (source them, never echo); `admin:<any-guess>` returns 401.
- Proving a provisioned dashboard: read it back via
  `curl -u "$GRAFANA_USER:$PASS" http://localhost:3000/api/dashboards/uid/<uid>` and check
  title + panel count — the JSON landing in the `dashboards/` bind-mount dir proves bytes only,
  not provisioning. New dashboard JSON needs no service recreate (dir mount, read-only), just a
  short wait for the provisioning loop; `allowUiUpdates:false` means UI edits are impossible.
- Dashboard authoring shape: compose panels locally in python copying an existing dashboard's
  fields (`datasource uid prom`, schemaVersion, gridPos, editable:false), scp to
  `dashboards/<name>.json`, then verify each panel's PromQL returns data via
  `curl -sG http://localhost:9090/api/v1/query --data-urlencode 'query=...'`.
- Remote spool clearing is MANUAL and deliberate: backup then `truncate -s 0` (never rm — file
  is owned by the router container's uid).

## Backup gauge labels (BackupFreshnessStaleWeekly triage)

- The stamp series `monitoring_backup_last_success_timestamp_seconds` carries label
  `exported_job` per backup JOB plus the exporter's own `host` label — `host` is always the
  PUSHGATEWAY/exporter's box, not the failed job. Read `exported_job` first.
- Cheap offline diagnosis: the expr is `time() - <stamp>`, so a firing value ~ the current
  epoch (~1.79e9 hours-scale) means stamp=0 (job NEVER succeeded); a value equal to a staleness
  window (hours/days) means genuinely stale. One look at the value classifies the alert.
- Batch the tick's re-probe: one ssh round-trip pulling `/api/v1/alerts`, the gauge query, and
  the per-row nc/ping probes into local files (redirect ssh output to /tmp, parse locally) beats
  per-row ssh calls — a quiet-tick tick should cost 2-3 tool calls, not one per row.

## Shared-checkout board writes (lane box)

- When a same-id row on a shared $HOME-toplevel checkout was ALREADY closed complete by a sibling (duplicate-closure row on disk, base finding still reads pending), do NOT re-edit the base row — the sibling's duplicate-closure + verified verdict stand. File the lane's own delta as an append-only relief/note row keyed to the base id (`<base-id>-RELIEF-<date>-<hhmm>`, status complete, ch:trace row=<relief-id>, worker_summary carrying attribution + what was reclaimed + what was left untouched). An APPEND survives sibling pathspec commits that only rewrite other lines; an in-place edit gets wiped by a sibling commit landing between your write and your commit.
- Gate a relief-row write with `git show HEAD:<path> | grep -c <relief-id>` == 1 (pushed-tree readback), never a working-tree grep — the workdir is dirty by construction.

## Disk alerts on bakeoff/boxen-style hosts

- For DiskWillFillIn24h on a host with large per-project workspace trees, attribute by AGE BUCKETS before touching anything: `du -xh -d1 /home/<user>` names the trees, then per tree `find <tree> -type f -newermt "2 days ago" | wc -l` splits STALE (0 recent files — reclaimable build internals like `*/target/{debug,release}`, regenerable) from ACTIVE (thousands of recent files — live work, leave untouched). Reclaim only the stale tree's build-cache subdirs, never the whole tree: a whole-target delete forces full rebuilds and can break in-flight workers (SKILL.md cargo rule).
- The reclaim's relief is capped by ongoing rebuild churn — record freed bytes + the active churn signature in the close note; and defer the post-reclaim predict_linear re-query to the next tick, because the step change warps the 6h linear fit into a nonsense projection.

## bunker-mvp (triage reference, 2026-10-01)

- 150G root disk; growth lives in `/home`: 1200+ `bunker-*` agent homes managed by `bunkerd`
  (systemd `bunkerd.service`, config `/etc/bunkerd/config.yaml`, TTL reaper archives each expired
  home to `/var/backups/bunker/` before userdel, fail-closed).
- Recurring trap: stale homes 6-13G whose archive tar is killed mid-stream every retry →
  `home_retained` refusal loop (see SKILL.md reaper rule). Stale partial tarballs in
  `/var/backups/bunker/` are safe to delete; check `journalctl -u bunkerd` for
  "home RETAINED" + refusal `attempts` before acting.
- OOM kills on this host are almost always the `/bunker-cgroup-test` memcg (bunker repo CI go
  tests via actions-runner) — benign; check `/var/log/kern.log` for `oom_memcg=` attribution.
- Snoopy audits every root command into /var/log/auth.log + syslog (GB-scale churn); gzip the
  uncompressed `*.1` rotated logs first when reclaiming.

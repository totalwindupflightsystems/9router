# Fleet-side monitoring runbook

## Alert-to-board contract

Prometheus rules fire on `fleet-monitor` (`/root/fleet-monitoring`). Alertmanager sends them to `alert-router` on that host. The router creates a board row for the alert's `lane`; because `fleet-monitor` does not hold the fleet lane checkouts, it spools rows instead. The fleet-side drain fetches that spool and appends rows to the owning lane's `.coding-hermes/board/tasks.jsonl`.

Run the drain on the board host, as `kara`:

```sh
MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh
```

The script reads `MON_REMOTE` and uses rsync to fetch from `fleet-monitor:/var/lib/fleet-monitoring/spool/`. It checks the row ID against the destination board before append; a repeated ID is skipped, so retrying the drain does not duplicate a row. It deliberately does not clear the remote spool automatically: confirm the rows landed before clearing it.

The default/catch-all lane is `monitoring`. Its board is:

```text
/home/kara/monitoring/.coding-hermes/board/tasks.jsonl
```

## Timer and schedule (verified on this host)

As user `kara`, `systemctl --user list-timers | grep -i drain` reported on 2026-10-07:

```text
Wed 2026-10-07 02:00:00 -05  5min  Wed 2026-10-07 01:45:00 -05  9min ago  monitoring-drain.timer  monitoring-drain.service
```

The live user unit is `~/.config/systemd/user/monitoring-drain.timer`; its drop-in sets `OnCalendar=*-*-* *:0/15:00` (every 15 minutes). The paired service sets `Environment=MON_REMOTE=fleet-monitor` and runs `/bin/bash %h/.hermes/scripts/drain-board-rows.sh`. The live `kara` crontab was checked with `crontab -l`; it contains no drain-related cron entry. The systemd timer is the scheduled drain.

## Add a rule with a routable lane

Live rule files are on `fleet-monitor` in `/root/fleet-monitoring/alerts/rules/*.yml`. The host's top-level `/root/fleet-monitoring/` layout is the live configuration; `/root/fleet-monitoring/stack/` copies are mirrors, not the edit target. The live directory listing verified these names (including backups):

```text
capacity.yml
capacity.yml.bak-20260928
capacity.yml.bak-20261006-gap018
capacity.yml.bak-gap007
host-health.yml
host-health.yml.bak-20260928
host-health.yml.bak-20260928-oomscope
probes.yml
```

For example, edit an existing rule file or create a new one on the live host:

```sh
ssh fleet-monitor 'vi /root/fleet-monitoring/alerts/rules/my-alert.yml'
```

Add a rule with a `lane` label. Set `<owning-lane>` to the exact board directory name whose project owns the alert's subject; use `monitoring` only when the monitoring stack itself owns the issue (it is the catch-all):

```yaml
- alert: ExampleAlert
  expr: example_metric > 0
  for: 5m
  labels:
    severity: warning
    lane: monitoring
  annotations:
    summary: "Describe the condition and affected system"
    description: "Include enough context for the owning lane to investigate."
```

Before choosing another lane, verify its board directory on this host:

```sh
lane='<owning-lane>'
test -d "/home/kara/$lane/.coding-hermes/board" && echo "board exists: $lane" || echo "NO BOARD: $lane"
```

Replace the example's `lane: monitoring` with the verified owner lane when the issue belongs elsewhere. Validate a new rule file and reload Prometheus from the live stack directory:

```sh
ssh fleet-monitor 'cd /root/fleet-monitoring && docker compose exec -T prometheus promtool check rules /etc/prometheus/rules/my-alert.yml'
ssh fleet-monitor 'curl -fsS -X POST http://127.0.0.1:9090/-/reload'
```

The validation command was exercised against the live `capacity.yml` and reported `SUCCESS: 8 rules found`; the reload endpoint returned success. The live compose file mounts `/root/fleet-monitoring/alerts/rules` at `/etc/prometheus/rules`.

## Unwritable rows

An unwritable row means the rule's `lane` does not resolve to a directory containing `.coding-hermes/board/` under `/home/kara`. The drain reports `no board for lane '<lane>' — leaving spooled`; it does not discard or repair the row. Fix the alert rule's `lane` label to name an existing owning board, then drain again. Do not edit the spooled row to hide a bad route: the rule owner fixes the rule, and the lane/project owner confirms which board owns the subject.

The requested live listing command, `ssh fleet-monitor 'ls /root/fleet-monitoring/alerts/rules/ /root/fleet-monitoring/alerts/spool 2>/dev/null'`, listed the rule files above and exited 2 because `/root/fleet-monitoring/alerts/spool` is absent. The live compose configuration mounts the router's spool at `/var/lib/fleet-monitoring/spool` (not under `alerts/`); the drain script fetches from that runtime path.

## Backup-freshness label trap

For the backup-freshness metric, Prometheus exposes the source job as `exported_job` (the alert also carries `job: integrations/unix`). Filter the metric by `exported_job` in PromQL, not by `job`. The live `BackupFreshnessStaleWeekly` rule demonstrates the selector:

```promql
monitoring_backup_last_success_timestamp_seconds{exported_job=~"kara-hermes|cube-agent"}
```

The live rule's summary uses `{{ $labels.job }}` for the alert's `integrations/unix` job label; that is distinct from the metric's source-job selector.

ch:trace row=MON-GAP-006 spec=monitoring/fleet-side-runbook.md wave=monitoring-foreman-2026-10-07-06-50-27.json#MON-GAP-006 test=doc-reviewed-against-live-timers+rules evidence=monitoring/fleet-side-runbook.md witness=live:systemctl--user-list-timers+ssh fleet-monitor ls alerts/rules verdict=none memory=none

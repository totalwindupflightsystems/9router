# Runbook

Operational procedures for the fleet-monitoring stack. Each alert rule links to an anchor here
(`docs/runbook.md#...`), so an alert and its fix live one click apart.

---

## Host not reporting

**Alert:** `HostNotReporting`

Agents push; there is no scrape target to fail. So "host is down" really means "no sample has
arrived in 5 minutes", and the cause is one of exactly three things. Check in this order —
it is ordered by how often it is the answer, not by severity.

1. **The agent** — `ssh <host> systemctl status fleet-alloy; journalctl -u fleet-alloy -n 50`
2. **The tailnet** — `tailscale status | grep <host>` on both the host and the monitoring host.
   A host showing `relay "…"` is working but slow; a host absent entirely is the problem.
3. **The host itself** — console access via the provider. If the kernel is hung, nothing else
   you check will make sense.

Distinguish "agent stopped" from "host stopped": if `ssh` works, the host is alive and the
problem is the agent or the tunnel.

---

## Disk full

**Alert:** `DiskFull`, `DiskWillFillIn24h`

Never delete blind. Order that has never cost anyone data:

```sh
docker system df                       # images vs volumes vs build cache
docker system df -v | head -40         # per-volume sizes
du -sh /var/lib/docker/volumes/* | sort -rh | head -20
```

`docker system prune -a` reclaims **images**, not volumes — it is the safe first move and
usually not enough. The volume list is what actually finds the hog (an analytics or log volume
that grew without bound is the common culprit).

Deleting a volume is destructive and irreversible. Archive it first:

```sh
docker run --rm -v <volume>:/data -v /tmp:/out alpine tar czf /out/<volume>.tgz -C /data .
```

**Do not** `tar` a live SQLite database, and do not `cp` one that is open. Use the tool that
knows the format: `sqlite3 db ".backup /tmp/out.db"`.

---

## Backup stale

**Alert:** `BackupFreshnessStale`

The stack's own backup has not succeeded in 48h.

**Production path:** `fleet-monitoring-backup.timer` runs nightly at 03:00 UTC. Check its last run:
`journalctl -u fleet-monitoring-backup.service`. Manual rerun:
`systemctl start fleet-monitoring-backup.service`. The timer calls `backup-to-s3.sh` directly.

**Manual path (by-hand equivalent):**

```sh
make backup        # follow the section headers: prometheus / grafana / bundle / upload
make restore-check # proves the newest set is readable, not just present
```

Common causes, in order: S3 credentials rotated and `.env` not updated; the Prometheus snapshot
API failing because `--web.enable-admin-api` was dropped from the command line; the Grafana
container lacking `sqlite3` (the script falls back to a volume copy — check the log says so).

An observability stack that cannot be restored is a dashboard, not a backup.

---

## Alert fires constantly / alert storm

**Symptom:** the board fills with duplicate rows for the same problem.

Check idempotence first — each alert should produce at most ONE row per day:

```sh
grep -c 'MON-' <lane>/.coding-hermes/board/tasks.jsonl
curl -s localhost:8089/health | python3 -m json.tool     # deduped/spooled counters
curl -s localhost:8089/metrics | grep dedup
```

If `rows_deduped_total` is not climbing while alerts repeat, the fingerprint is changing between
posts — that means the alert's *labels* are changing, which is usually a label carrying a value
that should not be a label (a timestamp, a PID, a URL with a query string). Fix the rule, not
the router.

Silence a known issue at the source instead of muting the row:

```sh
amtool silence add alertname=DiskWillFillIn24h host=dedi-3 --duration=4h \
  --comment="planned volume migration"
```

---

## Grafana is unreachable

Grafana binds to loopback by design. Reach it through the tunnel, never by opening a port:

```sh
ssh -N -L 3000:127.0.0.1:3000 <monitoring-host>     # then http://localhost:3000
# or, for something shareable inside the tailnet:
tailscale serve --bg https / http://127.0.0.1:3000
```

If Grafana is up but datasources are missing, the provisioning files did not mount — check
`docker logs mon-grafana | head -40` for provisioning errors before editing anything in the UI.
UI edits are overwritten on the next restart (`allowUiUpdates: false`), which is deliberate.

---

## The alert-router is spooling instead of writing rows

`write_mode=spool` in `/health` means the monitoring host does not hold the lane boards. That is
the expected default on a separate host — rows are not lost, they are waiting.

On the host that has the boards:

```sh
DRY=1 ./scripts/drain-board-rows.sh    # see exactly what would be appended
./scripts/drain-board-rows.sh
```

Then confirm the row landed in the right lane and clear the spool. Clearing is manual on
purpose: the drain is idempotent, but only if the spool still exists to re-read.

To make rows land directly instead, run the router somewhere that mounts the boards and set
`ALERT_ROUTER_WRITE=1` with `BOARD_ROOT` pointing at the checkout directory.

---

## Adding a host

```sh
$EDITOR ansible/inventory.yml          # add the host under `monitored`
ansible-playbook -i ansible/inventory.yml ansible/site.yml -l <new-host> --check --diff
make agent-install HOST=<new-host>
make verify                            # reporting count must increase
```

Use the SSH alias as the inventory hostname. The alias becomes the `host` label, and a host that
comes back with a different `$(hostname)` would otherwise fork its own metric history into two
series that each look half-empty.

---

## Changing an alert rule

```sh
$EDITOR alerts/rules/<file>.yml
make lint                              # promtool validates against the DEPLOYED version
curl -X POST localhost:9090/-/reload   # Prometheus picks it up without a restart
make verify                            # rule count must include your change
```

`make lint` runs the rule through the pinned Prometheus image's own `promtool`, so "it passed"
means "it passes on the version that will run it".

## Inventory sweep is stale

Alert: InventorySweepStale (severity: warning)
Metric: fleet_inventory_last_success_timestamp_seconds (textfile collector)
Meaning: the scheduled fleet software inventory sweep (MON-GAP-007) has not
published a fresh inventory for over 7 days. Drift (new containers, dead
agents, unreachable hosts) is no longer being observed.

Diagnosis:
  1. Check the sweep timer:
       systemctl list-timers | grep fleet-inventory
       journalctl -u fleet-inventory-sweep.service -n 50
  2. Check the textfile mtime:
       ls -l /var/lib/fleet-monitoring/node-exporter-textfile/fleet-inventory.prom
  3. Re-run the sweep manually:
       sudo /root/fleet-monitoring/scripts/fleet-inventory.sh
     It grades each host OK / PARTIAL / TIMEOUT / UNREACHABLE and writes the
     .prom file; on success the metric timestamp advances and the alert clears
     on the next scrape (default 60s).

If the sweep keeps failing, check SSH reachability to the fleet boxes
(`tailscale status`) and the inventory/ output directory for disk space.

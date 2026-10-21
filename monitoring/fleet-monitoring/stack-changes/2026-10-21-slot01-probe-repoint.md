# 2026-10-21 — slot-01 probe target repoint (MON-GAP-029)

Tick: monitoring-foreman-2026-10-21-20-20-37. Commit: 007ee54da (lane repo).

## What changed on fleet-monitor (/root/fleet-monitoring)

1. prometheus/probe-targets.json — slot-01 targets repointed
   100.79.83.6:10001/:10002 -> 100.122.57.93:10001/:10002 (host label unchanged:
   standby-cx53-01-2147). No service restart needed: file_sd refresh_interval=15s.
2. prometheus/probe-targets.README.md — NEW decision note: the file is now
   hand-maintained; regeneration from scripts/generate-probe-targets.py is BLOCKED
   (default inventory/2026-09-27 snapshot carries the dead IP; 2026-10-06+ snapshots
   dropped the standby slots entirely — a dry run emits 0 targets and would silence
   the whole blackbox lane).
3. scripts/probe-standby.sh — slot-01 probe line repointed to 100.122.57.93.

Backups on the host: *.bak-20261021-t2020 next to each edited file.

## Why

100.79.83.6 vanished from the tailnet (~2026-10-04, no cx53 peer remains at all).
The same fleet slot is live at 100.122.57.93 (HostName hermes-fleet-01, DNS
coding-hermes-remote-bunker-01) serving the same role: bunkerd on :10001/:10002 —
both nc-open, and probe_success=1 on both ports within 40s of the change.
TargetUnreachable (critical) had re-minted P0 rows daily since 2026-10-17.

## Outside proof (post-change, from the monitoring APIs)

- probe_success{host="standby-cx53-01-2147"} = 1 for both new targets (fleet-monitor:9090)
- TargetUnreachable firing = 0 in Prometheus AND Alertmanager (:9093 empty)

## Known follow-ups

- MON-DOGFOOD-046 (new): alert-router suppressed the auto -RESOLVED events for this
  repoint ("no live up series (target dark?)") — a resolution whose fix REMOVES the
  alerting series can never mint its event; rows were closed manually on live evidence.
- The inventory generator pipeline (generate-probe-targets.py + snapshot format) is
  orphaned from current inventory snapshots; until fixed, probe-targets.json is
  hand-maintained (see the README note).

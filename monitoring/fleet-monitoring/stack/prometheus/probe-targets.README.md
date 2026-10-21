# probe-targets.json is HAND-MAINTAINED as of 2026-10-21

Decision (monitoring tick 2026-10-21-20-20-37, closes MON-GAP-029): slot-01 target
REPOINTED from 100.79.83.6 (host vanished from the tailnet ~2026-10-04; no cx53 peer
remains) to 100.122.57.93 (HostName hermes-fleet-01, coding-hermes-remote-bunker-01),
which serves the same role: bunkerd on :10001/:10002 — verified OPEN via nc and
probe_success=1 in live Prometheus.

DO NOT regenerate prometheus/probe-targets.json from scripts/generate-probe-targets.py
until the generator+inventory pipeline is fixed: the default snapshot
(inventory/2026-09-27) still carries the DEAD 100.79.83.6, and every newer snapshot
(2026-10-06 and later) no longer contains the standby slots at all — regeneration
produces 0 targets (verified 2026-10-21) and would silence the whole blackbox lane.
scripts/probe-standby.sh was repointed in the same change (slot-05 is probed there but
has no prometheus target — pre-existing gap, not introduced here).

Close condition history: MON-GAP-029 (P1, fired 2026-10-20) + daily duplicate P0 rows
MON-MONITORING-{B316017D,AC991D47}-<date> since 2026-10-17.

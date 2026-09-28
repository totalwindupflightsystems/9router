# 2026-09-28: ALERT_ROUTER_WRITE=0 -> 1 (MON-GAP-011 closure)

Host: fleet-monitor, file /root/fleet-monitoring/.env line 21.
Backup: /root/fleet-monitoring/.env.bak-20260928-writeflag
Full file NOT copied here: it contains ALERT_ROUTER_TOKEN and S3 secrets.

Change: single line, ALERT_ROUTER_WRITE=0 -> ALERT_ROUTER_WRITE=1.
Applied: docker compose -f /root/fleet-monitoring/docker-compose.yml --env-file /root/fleet-monitoring/.env up -d alert-router
Proof: docker exec mon-alert-router env -> ALERT_ROUTER_WRITE=1; /health 200; container log
"listening on :8089 write_mode=board"; router falls back to spool per-lane when the lane
has no local board dir under /boards (board_append path guarded by os.path.isdir), so
remote-lane delivery is unchanged. Real-alert gate: DiskWillFillIn24h fired 14:30:45Z,
row landed on this board 14:31:15Z.

# 2026-10-07 — cadvisor on bunker-mvp (MON-GAP-008)

ch:trace row=MON-GAP-008 spec=docs/architecture.md#metrics-pipeline wave=none:serial-tick test=none:live-query-evidence doc=stack-changes/2026-10-07-cadvisor-bunker-mvp.md evidence=Prometheus query `count(container_memory_usage_bytes{instance="bunker-mvp",image!=""})` returned 2 (T4, live remote_write) witness=live:http://fleet-monitor:9090/api/v1/query commit=none:none-live-host-change

## What changed

bunker-mvp (host with docker + root-docker ssh access) now exports per-container metrics:

1. cadvisor v0.52.1 deployed on the HOST (not in compose — fleet-monitoring compose lives on
   fleet-monitor only; bunker-mvp's agent is the standalone fleet-alloy container):
   ```
   docker run -d --name cadvisor --restart unless-stopped \
     -p 127.0.0.1:8080:8080 \
     -v /:/rootfs:ro -v /var/run:/var/run:ro -v /sys:/sys:ro \
     -v /run/containerd/containerd.sock:/run/containerd/containerd.sock:rw \
     gcr.io/cadvisor/cadvisor:v0.52.1 \
     --containerd=/run/containerd/containerd.sock --containerd-namespace=moby \
     --housekeeping_interval=30s
   ```
   The containerd flags matter (see MON-GAP-008 foreman_note): this docker uses the
   containerd snapshotter, so without `--containerd` + `--containerd-namespace=moby`
   cadvisor emits zero per-container series (default k8s.io namespace matches nothing).
2. fleet-alloy config on bunker-mvp gained a `discovery.relabel "cadvisor"` +
   `prometheus.scrape "cadvisor"` block scraping 127.0.0.1:8080 and rewriting the
   instance label to HOSTNAME_LABEL (= bunker-mvp), then remote_writes to the hub.
   Backup kept at /etc/fleet-monitoring/config.alloy.bak-cadvisor-20261007 (remote host).

## Verification (T4, live)

- cadvisor endpoint: `curl 127.0.0.1:8080/metrics` on bunker-mvp shows per-container
  series with image/name labels (grafana/alloy:v1.20.0, cadvisor itself).
- Central Prometheus (fleet-monitor:9090), queried from the lane host:
  `count(container_memory_usage_bytes{instance="bunker-mvp",image!=""})` = 2.

## Remaining for the gate (row stays in_progress)

- cadvisor + Alloy scrape on the other docker hosts: bunker2 and bunker-las-02 deny
  docker to the kara account (owner-gated; needs owner ssh/authorization), master001
  reports no docker daemon, backoffice-coolify/kara-m10 lack ssh host keys in this lane.
- Containers dashboard (grafana-dashboards provisioned as code) — not yet built.

## Alert-radius note (this tick's triage)

bunker-mvp disk: Oct 2 alerts saw 0.06-0.95% free; now 71% used / 42G free. Growth driver
identified live: 723 /home/bunker-* agent dirs, ~466G untouched for >7d. No purge executed
(agent homes are tenant data) — needs owner decision, like the open bunker-las-02 row
MON-MONITORING-F4C44E2A-20261006.

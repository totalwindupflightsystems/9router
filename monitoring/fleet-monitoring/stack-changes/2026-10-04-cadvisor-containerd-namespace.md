# 2026-10-04 — cadvisor container metrics fix (MON-GAP-008)

## Symptom
Prometheus had cadvisor series for `fleet-monitor` but ZERO per-container series:
`container_memory_usage_bytes` existed only for cgroup roots (`/`, `/system.slice`, ...).
The MON-GAP-008 gate ("container CPU/memory series present for >=3 hosts, one real
container identifiable by name") could never pass.

## Root cause
This host's Docker uses the **containerd snapshotter** (`Storage Driver: overlayfs,
driver-type: io.containerd.snapshotter.v1`). The classic overlayfs graphdriver layout
`/var/lib/docker/image/overlayfs/layerdb/mounts/<id>/mount-id` does not exist, so
cadvisor's docker factory failed on every container:
`failed to identify the read-write layer ID for container <id>`.
The compose service also mounted `/var/lib/docker` read-only, which is useless on
snapshotter hosts (kept out; containerd sock is what matters).

## Fix (docker-compose.yml, cadvisor service)
    command:
      - --containerd=/run/containerd/containerd.sock
      - --containerd-namespace=moby
      - --housekeeping_interval=30s

Docker's containers live in containerd namespace `moby` (verified: `ctr namespace ls`
shows `moby`). Default cadvisor namespace is `k8s.io`, which matched nothing.

## Verification (T4)
- `curl localhost:8080/metrics` on fleet-monitor: per-container series with
  `image=` and `name=` labels for all 10 containers.
- Prometheus (30s later): `count(container_memory_usage_bytes{image!=""})` = 10;
  topk shows grafana 595MB, prometheus 371MB, alloy 298MB.
- `docker logs mon-cadvisor`: zero "failed to identify" lines.

Note: only fleet-monitor was fixed. Other docker hosts in the fleet still lack
cadvisor/Alloy container exporters — MON-GAP-008 remains in_progress (1 of N hosts).

# Dogfood run 8 — monitoring — 2026-10-12

## Angle
Re-proof of the closed run-7 install defects (MON-DOGFOOD-021/022/023, fixes landed
4c9d39b / Dockerfile commit) on a genuinely fresh box, plus first drive of the
disk-guard / disk-metrics-textfile pipeline on the lane's own host.

## Install leg (fresh machine)
- bunker-las-02: 2 consecutive spawn failures (slice-limits swap convergence) →
  sibling host bunker-mvp (per doctrine). Agent 8faaa8f8, ttl 2h.
- Clone: GitHub https clone of fleet-monitoring (private) fails unauthenticated —
  used the documented tar-over-ssh fallback. No access widening.
- `make env` / `make check-env`: PASS immediately.
- `make up` attempt 1: rootless docker.service failed 3x at FIRST BOOT with
  `failed to lock /run/user/1266/dockerd-rootless/lock, another RootlessKit is
  running` → **MON-DOGFOOD-024 premise CONFIRMED on a second host** (rescue:
  kill stale rootlesskit, rm lock, reset-failed → active).
- `make up` attempt 2: alert-router build fails "failed to read dockerfile" even
  though the GitHub API serves stack/alert-router/Dockerfile — the tar fallback
  checkout lacked it (clone-only fix), scp'd from the API → **021 closure holds
  for real clones; the Dockerfile is genuinely committed**.
- `make up` attempt 3: bind-mount sources `/var/lib/fleet-monitoring/*` uncreatable
  rootless → **022 closure is a REAL fix only if `make bootstrap` runs as root**.
  Remapped via COMPOSE_EXTRA override per README.
- `make bootstrap` as bare agent: sudo dead (password), rclone install fails
  curl(23) → filed MON-DOGFOOD-028.
- `make up` attempt 4/5/6: cost-exporter crash-loops (exporter.py missing from
  published repo → MON-DOGFOOD-025), loki crash-loops (delete_request_store: s3
  with no creds → MON-DOGFOOD-026), host port collisions 8080/12345 →
  MON-DOGFOOD-027.
- Final state on the agent: 7/9 containers Up (router healthy, prometheus,
  alertmanager, grafana, renderer healthy, cadvisor healthy, alloy up);
  loki + cost-exporter crash-looping per 025/026. Smoke: router /health 200,
  prom 200, am 200, grafana 200, cadvisor 200; prometheus self-target up.

## Own-host disk pipeline (first real-use drive)
- disk-guard.timer fired 26s before probe start; journalctl empty (stdout lost —
  systemd user unit has no persistent journal for it), `--report` exits 0 empty.
- `--dry-run` clean: 267 GiB free (soft 150 / hard 60), would_shed=no. Honest.
- disk-metrics-textfile.py: 0.12s full walk, series fresh in fleet-monitor
  Prometheus (all 9 dirs incl. /var/tmp/hermes-scratch).
- DiskWillFillIn24h not firing; alert surface = only cx53 TargetUnreachable x2
  (known owner row). Live df corroborates 85% / 267G.

## Perf
- install-to-first-healthy-container: ~3.5 min wall after the daemon rescue
  (imgs cached); cold first-boot would add image pulls (~2-4 min).
- disk-metrics walk 0.12s, disk-guard dry-run <1s: nothing user-noticeable.
  No PERF rows — nothing here is slow enough to feel.

## Verdict
FAILED-product / PASS-run for the fresh-install promise: the run-7 fixes are
real (Dockerfile committed, docs updated) but a fresh user following README
still cannot reach a green `make up` without 4 extra compensations (daemon
rescue, bootstrap root requirement, cost-exporter missing file, loki S3
contract, port collisions). Production surface on the lane's own host remains
healthy.

## Rows filed
MON-DOGFOOD-025 (P1 cost-exporter exporter.py absent from published repo),
026 (P2 loki delete_request_store s3 hard dep), 027 (P2 port-collision
preflight), 028 (P2 bootstrap rootless-host path), + 024-REPROOF event note.

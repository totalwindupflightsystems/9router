# fleet-monitoring

The fleet's **metrics + logs + alerts** plane. One place that answers *what is happening on every
host right now*, keeps the history in object storage, and — the part that makes it more than a
dashboard — **routes alerts into agents** so a fired alert becomes a board row on the lane that
owns the thing that broke.

Not to be confused with `~/observability`, which is the **profiling** stack (Pyroscope + eBPF
flame graphs). Different question, different data, different repo. This one is about
*"is it up, is it slow, is the disk filling, did a unit restart"*; that one is about
*"which function burned the CPU"*.

## Shape

```
                    ┌──────────────── monitoring host (outbound-only, Tailscale) ─────────────┐
every fleet host ──►│  Alloy  ──metrics──► Prometheus ──► Alertmanager ──► alert-router ──► agent│
 (Alloy agent)      │         ──logs─────► Loki                                             │
                    │         ──traces──►  Tempo (OTLP 4317 gRPC / 4318 HTTP, query :3200)      │
                    │  Grafana (dashboards, provisioned from files in this repo)            │
                    └───────────────────────────┬──────────────────────────────────────────┘
                                                │
                                    S3 (karahermes-hel/monitoring/)
                                    Loki chunks · Prometheus snapshots · Grafana backups · git bundle
```

- **Transport is a Tailscale tailnet.** No public inbound beyond UDP 41641 (WireGuard). The
  firewall has *no* open service ports — see `terraform/firewall.tf` and
  `docs/architecture.md#firewall`.
- **Nothing is configured by clicking.** Datasources, dashboards and alert rules are files under
  `stack/`, `dashboards/` and `alerts/`, mounted read-only. A rebuild comes up already correct.
- **Alerts become work.** `alert-router` maps an alert's `lane` label to a project board and
  appends a row, so the alert lands in the queue the foreman already reads.

## Quickstart (on the monitoring host)

```sh
git clone <remote> fleet-monitoring && cd fleet-monitoring
cp .env.example .env          # set GRAFANA_PASSWORD and TAILSCALE_AUTHKEY; see storage note below
make bootstrap                # host prep: docker, dirs, sysctls, tailscale up
make up                       # bring the stack up
make verify                   # proves DATA is arriving, not just that containers run
```

Fresh clones default to `LOKI_STORAGE=local`, so Loki does not try to authenticate with
placeholder S3 credentials. Logs remain on the `loki-data` Docker volume and will not survive
loss of that host. To enable durable S3 storage, enter valid S3 credentials and explicitly set
`LOKI_STORAGE=s3` before `make up`; invalid credentials are not a local-mode signal and Loki
will fail hard rather than silently pretending the data is durable.

`ALERT_ROUTER_HOST_PORT` controls the host-side alert-router port (default `18089`); its
container listener stays on `8089`. Change the host port in `.env` if it is already occupied.

`make verify` is the real gate. Green containers with an empty label set is the default failure
mode of every observability stack ever built — the collector starts, finds nothing it can ship,
and reports success. `verify.sh` asserts on samples in Prometheus, streams in Loki, and datasources
answering in Grafana.

## Deploying to a fresh host

```sh
make tf-plan                  # firewall + (optional) server, hcloud provider
make tf-apply
make cloud-init               # render cloud-init/user-data.yaml for the new instance
```

First boot runs `cloud-init/user-data.yaml`: hardened base, docker, tailscale up, clone, `make up`.

### Fresh-host requirements (learned the hard way — dogfood run 7)

Before `make up` on a bare host:

- **Docker Compose v2 plugin is required** (not part of base docker on Debian/Ubuntu).
  `bootstrap.sh` fails fast if it is missing; install it to `~/.docker/cli-plugins/` first.
- **Rootless docker cannot create `/var/lib/fleet-monitoring/{spool,node-exporter-textfile}`.**
  Run `make bootstrap` (as root or with sudo) so the bind-mount sources exist with the right
  owner before the first `make up`; on a rootless-only host, remap these to user-writable
  paths via a compose override (`COMPOSE_EXTRA=stack/docker-compose.override.yml`).
- A stale `/run/user/$UID/dockerd-rootless/lock` from a killed rootless daemon blocks
  restarts — kill leftover rootlesskit processes and `rm` the pid/lock, then
  `systemctl --user reset-failed docker`.
- The alert-router image builds from `stack/alert-router/Dockerfile`, which is committed;
  if `make up` fails with "failed to read dockerfile" you are running a checkout older
  than the run-7 fixes.

## Fleet agents

Every host that should be monitored gets the Alloy agent:

```sh
make agent-install HOST=dedi-2        # ansible: docker + alloy unit
make agent-install-all                # every host in ansible/inventory.yml
```

The agent's config is `stack/alloy/config.alloy`, shipped with the stack — one file, both
`metrics` and `logs` pipelines, so host and collector config never drift apart.

## Alert → agent routing

`alerts/rules/*.yml` carry a `lane` label naming the project that owns the alert:

```yaml
- alert: DiskWillFillIn24h
  expr: predict_linear(node_filesystem_avail_bytes[6h], 86400) < 0
  labels: { severity: warning, lane: monitoring }
```

Alertmanager posts to `alert-router`, which appends a board row to that lane's
`.coding-hermes/board/tasks.jsonl` (idempotent per alert fingerprint + day) and optionally
messages the lane. Details and the label taxonomy: `docs/alerting-to-agents.md`.

## Backups / S3 backend

```sh
make backup        # loki chunks + prometheus snapshot + grafana db + git bundle -> S3
make restore-check # verifies the newest backup is readable (not just present)
```

Bucket/prefix is `karahermes-hel/monitoring/` by default (`S3_BUCKET` / `S3_PREFIX`). In S3 mode,
Loki writes its chunks there directly, so logs survive the host being rebuilt. The backup script
uses `COMPOSE_PROJECT_NAME` to locate the matching Prometheus and Grafana volumes (default
`fleet-monitoring`).

## Rebuilding the whole thing

`docs/rebuild.md` is the runbook: new host → firewall → bootstrap → up → verify → restore history.
It is written to be followed by someone who has never seen this repo.

## Layout

| Path | What |
|---|---|
| `stack/` | docker compose + component configs (prometheus, loki, alloy, alertmanager, grafana provisioning, **tempo**) |
| `dashboards/` | Grafana dashboard JSON, provisioned on boot |
| `alerts/` | Prometheus alert rules, lane-labelled |
| `terraform/` | hcloud: outbound-only firewall, optional server, ssh key |
| `ansible/` | fleet host prep + agent rollout |
| `cloud-init/` | first-boot config for a fresh instance |
| `scripts/` | bootstrap, deploy, verify, backup, restore, agent install |
| `docs/` | architecture, rebuild runbook, alerting, decisions |

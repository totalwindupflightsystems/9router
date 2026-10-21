# Architecture

## One paragraph

Every fleet host runs the **Alloy agent** from `stack/alloy/config.alloy`; it ships host metrics
and logs to a single **monitoring host** over a Tailscale tailnet. That host runs Prometheus
(metrics TSDB), Loki (logs, chunks in S3), Grafana (dashboards, provisioned from files in this
repo), Alertmanager, and the **alert-router**, which turns firing alerts into board rows on the
lane that owns the problem. Everything the host needs to come back is either in git (config)
or in object storage (history).

## Why agents push instead of being scraped

The monitoring host is behind an **outbound-only** firewall: no inbound service port at all.
Prometheus cannot reach out and scrape a fleet, so the direction is inverted — each agent
pushes with `remote_write` and `loki.write`. This is a consequence of the security posture, not
an accident, and it is why `prometheus.yml` has no fleet scrape jobs.

The measurable difference: with a scrape model, the monitoring host needs a listener on the
public internet (or a second network path). With push + tailnet, a compromised monitoring host
still cannot be reached from the public internet at all.

## Firewall

Hetzner Cloud firewalls filter **ingress only** — egress is always allowed. "Outbound-only" is
therefore not a setting; it is the shape of a firewall that allows almost nothing in.

`terraform/firewall.tf` defines exactly three rules:

| Inbound | Purpose | Default |
|---|---|---|
| UDP 41641 | Tailscale/WireGuard — the transport | **required** |
| ICMP echo | path-MTU discovery | on |
| TCP 22 | break-glass SSH | **off** (empty `admin_ssh_cidrs`) |

Why UDP 41641 is not optional: without it the host cannot accept a direct tunnel, so every
tailnet connection relays through Tailscale's DERP servers — slower, and it routes fleet traffic
through a third party's infrastructure. Opening WireGuard and nothing else keeps the public IP
free of services while making the tailnet path direct.

Grafana, Prometheus, Loki, Alertmanager and the alert-router are **never** exposed publicly.
Grafana binds to `127.0.0.1` on the host and is reached via an SSH tunnel or `tailscale serve`.
Ingest endpoints (9090, 3100) bind publicly but are only *reachable* over the tunnel.

Verify the posture at any time:

```sh
nmap -Pn -p 22,3000,3100,8089,9090 <public-ip>   # expect: all closed/filtered
```

## Data flow

```
host ──Alloy──┬─ remote_write ──► Prometheus ──rules──► Alertmanager ──► alert-router ──► board row
              └─ loki.write  ──► Loki ──chunks──► S3
              └─ OTLP ───────► Tempo (traces, query API :3200)
```

The alert-router sits at the end of that chain deliberately. An alert that stops at a dashboard
depends on a human looking; an alert that becomes a row in a queue the foreman already reads is
work with an owner.

## State and where it lives

| State | Location | Survives host loss? |
|---|---|---|
| dashboards, rules, agent config, IaC | git (+ S3 bundle) | yes |
| Grafana users/prefs | named volume `grafana-data` | via S3 backup |
| Prometheus TSDB | named volume `prom-data` | via S3 snapshot |
| Loki logs | **S3 directly** | yes, by construction |
| alert spool | volume `router-spool` (+ S3) | via drain |

Loki writing chunks straight to S3 is the reason logs are the most durable signal here: losing
the host loses the query capability, not the data.

## Retention and cost

Two knobs, both in `.env`:

- `PROM_RETENTION` (default 30d) — Prometheus is a local TSDB; this is what bounds its disk.
- `LOKI_RETENTION` (default 720h = 30d) — enforced by the compactor, and cheap because the
  bytes are in S3.

Profile storage is **not** here. Function-level profiling (Pyroscope + eBPF) is a separate stack
in `~/observability`, because it needs `privileged` + host PID namespace and grows monotonically
in a way metrics and logs do not. Mixing them would put the profiler's retention on the same
disk as the dashboards the fleet needs during an incident.

## Deliberate non-goals

- **No Kubernetes.** These are a few dozen machines, not a fleet needing a control plane.
- **No distributed Prometheus.** One TSDB with a 30-day window answers every question this fleet
  currently asks; a Thanos/Mimir layer would be cost without a question behind it.
- **No tracing.** Nothing here is a request-path system; the traces would be empty.
- **No multi-tenancy.** `auth_enabled: false` in Loki and a single Grafana org. Adding tenancy
  before there is a second tenant is configuration nobody exercises and therefore nobody fixes.

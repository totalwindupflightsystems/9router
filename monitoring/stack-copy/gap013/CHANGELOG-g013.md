# CHANGELOG-g013 — MON-GAP-013 (2026-10-10)

Add service-level metrics for PostgreSQL, Redis and Traefik to the fleet-monitoring stack.

## Discovery
- postgres + redis + traefik all live on **master001** (100.99.183.108, tailnet; LAN 192.168.123.102), inside the Coolify 4.1.2 stack (`/data/coolify`): coolify-db (postgres:15-alpine), coolify-redis (redis:7-alpine), coolify-proxy (traefik v3.6). Verified via `sudo docker ps` on master001.
- bunker-las-02 / bunker-mvp: no postgres/redis/traefik (only cadvisor, fleet-alloy, 9router).
- fleet-monitor itself: monitoring stack only (no target services). Prometheus series query for postgres/redis/traefik images pre-existed: 0 series.

## Deploy (master001)
- Prom container (fleet-alloy) on master001 runs NetworkMode=host; the coolify containers are NOT host-exposed (redis has no host port binding, pg 5432 not bound). Exporters therefore attach to the `coolify` docker network and are published **only on the tailscale IP** (`-p 100.99.183.108:PORT:PORT`) — nothing listens on 0.0.0.0 / the public interface (fleet-monitor host posture: outbound-only + Tailscale).
- `mon-gap013-pg-exporter` — prometheuscommunity/postgres-exporter:latest, `--network coolify`, `-p 100.99.183.108:9187:9187`, DATA_SOURCE_NAME read at runtime from `coolify-db` container env (POSTGRES_USER/PASSWORD/DB; password never echoed to logs/console). First attempt used a passwordless DSN → `pg_up 0` (peer/auth failure); fixed with the real credentials from container env.
- `mon-gap013-redis-exporter` — oliver006/redis_exporter:latest, `--network coolify` (`REDIS_ADDR=redis:6379` via network alias — verified PONG + dbsize 384 through the alias), `-p 100.99.183.108:9121:9121`, REDIS_PASSWORD read at runtime from `coolify-redis` container env.
- Both `--restart unless-stopped`. Deploy script (review copy): deploy-exporters-master001.sh.

## Scrape config (fleet-monitor)
- LIVE config is `/root/fleet-monitoring/prometheus/prometheus.yml` (docker-compose run dir is `/root/fleet-monitoring/`). NOTE: `/root/fleet-monitoring/stack/prometheus/prometheus.yml` is a STALE copy — briefly edited then REVERTED; no lasting change there.
- Backup: prometheus.yml.bak-gap013-20261010. Added jobs `services-postgres` (100.99.183.108:9187) and `services-redis` (100.99.183.108:9121), labels host=master001 role=services. Reload via `docker exec mon-prometheus kill -HUP 1` (no restart, no scrape gap).
- Review copy: prometheus-scrape-addition.yml.

## Traefik — SKIPPED, reason recorded
- coolify-proxy runs Traefik v3.6 with `--ping=true --ping.entrypoint=http` on entrypoint :80 (80/443/8080 published). `/metrics` returns 404: Prometheus metrics are STATIC (cli-flag) config in Traefik; no dynamic-config override exists for them.
- Enabling requires editing Coolify's proxy launch args + restarting coolify-proxy — the fleet's ingress proxy for master001 (Coolify control plane + 9router-central), i.e. real traffic-drop risk. Brief's back-out rule applies → skipped deliberately, documented in dashboard placeholder panels.
- Review copy: prometheus-scrape-addition.yml carries the same note inline.

## Dashboard
- No services dashboard existed (dashboards/: containers.json, fleet-overview.json, host-detail.json, uptime-probes.json).
- Added provisioned-as-code `/root/fleet-monitoring/dashboards/services.json` (uid fleet-services, folder "Fleet", 9 panels: pg_up, redis_up, traefik-metrics placeholder, pg connections stat, pg connections-by-db, redis memory, redis ops by cmd, pg xact rate, traefik placeholder row). Grafana file-provisioning picked it up within 30s (updateIntervalSeconds 30) — verified via API with admin creds from .env (never printed): api/search returns "Services (postgres / redis / traefik)" | uid=fleet-services, api/dashboards/uid/fleet-services shows 9 panels. Review copy: services.json.

## Verification evidence
- `/api/v1/targets`: services-postgres 100.99.183.108:9187 health=up; services-redis 100.99.183.108:9121 health=up.
- Samples via /api/v1/query: pg_up=1, redis_up=1, pg_stat_database_numbackends{datname="coolify"}=3, redis_connected_clients=7.
- Direct exporter scrape from fleet-monitor: redis_connected_clients 7, redis_memory_used_bytes 3.16e6, redis_uptime_in_seconds 5.93e6, pg_up 1.
- Pre/post cross-host TCP probe from fleet-monitor: 9121/9187 not-connectable before → CONNECTABLE after (9100 remains not-connectable: agent unix exporter stays host-local, correct posture).
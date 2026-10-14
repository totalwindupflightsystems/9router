# fleet-monitoring

Operator entrypoints for the fleet monitoring stack (Prometheus, Loki, Grafana,
Alloy, Alertmanager, alert-router, cost-exporter). `make help` lists all
targets; `make verify` is the real gate, not `make up`.

## Fresh-machine bootstrap

The repo is self-contained for the config path: everything the documented
sequence needs is vendored (MON-REVIEW-003), so a bare clone needs nothing
scp'd out of band.

Vendored in-repo (present from clone):

- `scripts/` — `check-env.sh`, `render-configs.sh`, `lint-configs.sh`,
  `verify.sh` (called by `check-env`, `config`, `verify`)
- `.env.example` — copyable with dev-default dummy secrets; `check-env`
  accepts them with a "DEV DEFAULT" warning so a clean machine can boot
  without real credentials
- `stack/docker-compose.yml` plus component configs under `stack/`
  (prometheus, loki with a local-storage fallback, alertmanager, alloy,
  alert-router, cost-exporter, provisioning)

`make env && make config` therefore works from a clean clone:
`env` creates `.env` from the example, `check-env` passes on the dev
defaults, and `config` validates compose + component configs without
starting containers. `make up` then boots the stack in local-storage mode.

Still NOT in the repo — must come from the live host or your secret store:

- Real `.env` values: `GRAFANA_PASSWORD`, `ALERT_ROUTER_TOKEN`,
  `RENDERER_TOKEN` (replace the dev dummies with `openssl rand -base64 24`
  before serving anything real)
- S3 credentials (`S3_ACCESS_KEY` / `S3_SECRET_KEY`) and a
  `LOKI_STORAGE=s3` setting for durable log storage — without them the
  stack runs Loki in local-storage mode (fine for a test box, not durable)
- `TAILSCALE_AUTHKEY`, `HCLOUD_TOKEN`, `MONITORING_SERVER_ID` — only
  needed when provisioning a new server (cloud-init / terraform paths)

Pre-existing live-host state (Grafana dashboards, Prometheus snapshots,
existing S3 backups) is migrated via `make restore`, not the bootstrap.

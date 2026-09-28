# Dogfood run 2 — monitoring lane, 2026-09-28 (repeat run, chain + query surface)

Lane: monitoring-dogfood (tick 2026-09-28-19-52-46). Run 1 (`2026-09-28-integration.md`)
found the alert→row chain dead (token perms) and filed MON-DOGFOOD-001..004. The foreman
subsequently closed 001/002/003 and several GAP rows. Per the repeat-run doctrine this run
changes the angle: (1) live-verify run 1's claimed fixes on the real chain, (2) dogfood the
surface run 1 never touched — the query workflow (Prometheus/Loki/Grafana APIs), (3) re-run
the fresh-machine install leg because repo/config files changed today (no same-day
exemption).

## 1. Alert→row chain: verified end to end (both directions)

A synthetic probe alert (fingerprint `d0gf00d42`, lane=monitoring, severity=warning) was
POSTed to `mon-alert-router:8089/webhook` from inside the host with the router's own
token, exactly the way Alertmanager sends it:

- router answered 200 in 4.9ms, counters `received_total 6→7, rows_spooled_total 3`,
  `errors_total 0`
- `MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh` appended
  `MON-MONITORING-D0GF00D4-20260928` to this board in 4.2s
- a resolved-status POST produced the `-RESOLVED` twin row the same way
- both probe rows were then removed from the board (planned removal, python line-wise,
  census re-verified at 31 rows); the spool entries remain on the host spool, which is
  deliberately manual-clear

Alertmanager side is also clean since the fix: `Notify success` at 13:46:43Z after 14
attempts (the backlog flushing), and zero permission-denied failures in the ~8h since.
MON-DOGFOOD-001 is genuinely fixed.

## 2. Query workflow (the surface run 1 skipped)

- Prometheus: `/api/v1/query` healthy; `up==0` returns 0 down targets across the fleet;
  `/api/v1/rules` shows 2 groups / 11 rules, all `health: ok`, and every rule now labels
  `lane=monitoring` (MON-DOGFOOD-002 fix confirmed at the rule level — no more nonexistent
  `hermes-fleet-ops` destination).
- Loki: `/loki/api/v1/labels` returns a clean label set (host, job, level, service_name,
  unit…); a range query on `{job="fleet"}` returns real stream data with detected_level
  populated.
- Grafana: `/api/health` ok (13.2.2); dashboards are provisioned as code
  (`dashboards/fleet-overview.json`, `host-detail.json`). Basic-auth API access with the
  documented-style credential correctly 401s — no anonymous API surface.

Verdict for this surface: usable and healthy. Nothing here made a user wait; no PERF row
earned (the drain's 4.2s warm and the router's 5ms are both comfortably fast; cold lint
cost is a Docker Hub pull artifact, not project code).

## 3. Fresh-machine install leg (bunker-las-03, agent 960339f7, destroyed after)

Repo transferred per-file (git ls-files, ok=7 fail=0), then the stack's install surface
pulled from fleet-monitor to the same agent (Makefile, .env.example, scripts/, stack/, ok
=25 fail=0). Documented path executed exactly:

| step | result | time |
|---|---|---|
| `make env` | created .env | 0s |
| `make check-env` | correctly FAILS on placeholders (good gate); PASS after filling dummies | 0s |
| `make render-configs` | wrote stack/alertmanager/router-token mode 600, git-untracked | 0s |
| `make config` | FAIL — see below | 549s cold (image pulls) |

`make config` found two real defects, both verified against the live file, not guessed:

1. **Hardcoded `/tmp` paths in `scripts/lint-configs.sh` are unsafe on multi-user hosts**
   (fresh finding, P1). On the bunker (a shared Debian host with many agent users), every
   lint step died `Permission denied` — the paths were pre-created by *another bunker
   agent's* earlier run (uid 1003 cannot rewrite uid-1002's files; `mktemp` would be safe).
   A two-line fix (`TMPD=$(mktemp -d)` + substitutions) brought the lint from 0/10 to
   10/11 green. The live host never sees this because it is single-user root — which is
   exactly why the fresh-machine leg exists.
2. **The Loki lint step is blind to its own temp file through rootless docker** (P1).
   Every other step validates via bind-mounting a DIRECTORY; the Loki step mounts
   `$TMPD/loki-rendered.yml` as a single FILE, and on a rootless daemon (root != file
   owner, private /tmp) docker silently creates a directory at the mount point →
   `failed parsing config: read /cfg/loki.yml: is a directory`. Fix: mount the whole
   temp dir and point `-config.file` inside it.
3. Docs gap (P2): the Makefile hardcodes `stack/` + `scripts/` layout, but neither
   `.env.example`, `scripts/`, nor `stack/` is IN the repo anywhere — the only copy lives
   on fleet-monitor (MON-DOGFOOD-004 already tracks this; this run measures its cost: a
   fresh user cannot even reach `make env` without an out-of-band scp from the live host).

Also re-confirmed: bunkerd socket (`/run/bunker/<id>/docker.sock`) is the working rootless
path; compose lint passes; promtool validates prometheus.yml + 11 rules; alertmanager and
alloy configs validate.

## Verdict

PROMISING-BUT-ROUGH → improving. The flagship chain (alert→spool→row→resolved) now works
end to end and was proven live in both directions this run. The query surface is healthy.
The remaining blocker is reconstructability (MON-DOGFOOD-004) plus the two lint defects
above — none of them affect the running stack on fleet-monitor.

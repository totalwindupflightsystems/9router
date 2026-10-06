# Dogfood run 6 — 2026-10-04 (monitoring-dogfood-2026-10-04-22-39-03)

Angle: corroboration + install-leg retry. Run 5 (same day) filed MON-DOGFOOD-016
(P0: alert→row chain dark since router restart) and MON-DOGFOOD-017
(SKIPPED-install-bunker). This run re-probed both surfaces independently at a
later hour, plus a local zero-edit fresh-install verification at the new tip.

## What was done

1. **P0 re-probe (MON-DOGFOOD-016)** — synthetic alert through the real producer
   (POST /webhook on fleet-monitor:8089 with the router's own token, Alertmanager
   v4 payload shape): HTTP 200 in 6.0ms, counters moved received 57→58,
   errors 56→57, rows_spooled_total **0**; `docker logs mon-alert-router` shows
   `resolved spool failed: [Errno 13] Permission denied: '/spool/board-rows.jsonl'`
   at 23:01:48Z; `docker exec mon-alert-router touch /spool/probe-r6` →
   Permission denied (container uid 10001 vs root-owned 755 named-volume
   `_data`). Repro'd exactly as run 5 filed it. Row NOT duplicated — corroboration
   note appended to MON-DOGFOOD-016.
2. **Zero-edit boot path at new tip (QA-MONITORING-008 corroboration)** —
   `git archive HEAD` (aeb7d3d, the same-day fix commit) to a scratch dir,
   `cp .env.example .env` → `make build` rc=0, `make config` rc=0 (7.3s),
   `LOKI_STORAGE=auto -> local`, `stack/loki/loki-config.active.yml` rendered as
   the local config. The QA-MONITORING-008 fix holds at tip; verified by a second
   independent consumer. Note appended to the row.
3. **Install leg (bunker)** — attempted twice (directly, and observed the sibling
   tick attempt): `BUNKER_QA_SUBDIR=monitoring/fleet-monitoring bunker-qa.sh
   launch` → spawn fails deterministically on bunker-mvp: per-agent ssh port 2223
   not listening on the host (only :22, sshd answers on 22 fine, bunkerd active
   and ONLINE 8/50 agents, one spawn succeeded in its journal at 23:12:29Z);
   skill-default bunker-las-03 unreachable (tailnet down, `100.69.3.13` no
   answer). Local `bunker` CLI → `unauthenticated: invalid token` against the
   local proxy on :10001. Verdict: SKIPPED-install-bunker (host/spawn
   unavailable, not a product defect) — run 5's row MON-DOGFOOD-017 covers the
   same leg with the same root cause class; the compensating local fresh-install
   verification above is this run's install evidence.
4. **Stack health** — all 12 containers up; grafana `/api/health` ok (13.2.2),
   prometheus `/-/healthy` ok, alertmanager `/-/ready` ok, loki `/ready` ok.
5. **Perf** — webhook 6.0ms, make config 7.3s, no user-visible slowness →
   no PERF rows filed (a win nobody can feel is not a finding).

ch:trace row=MON-DOGFOOD-016 spec=fleet-monitoring/stack/alert-router wave=none test=live POST /webhook probe (200/6.0ms, errors+1, spool 0) evidence=docs/dogfood/2026-10-04-run6-corroboration-and-install-retry.md witness=live:fleet-monitor:8089/metrics verdict=none commit=none
ch:trace row=QA-MONITORING-008 spec=fleet-monitoring/README.md#quickstart wave=none test=make build+make config (fresh tree, rc=0/rc=0 at aeb7d3d) evidence=docs/dogfood/2026-10-04-run6-corroboration-and-install-retry.md witness=live:git-archive scratch repro verdict=none commit=aeb7d3d
ch:trace row=MON-DOGFOOD-017 spec=fleet-monitoring/Makefile#install wave=none test=none::spawn refused evidence=docs/dogfood/2026-10-04-run6-corroboration-and-install-retry.md witness=none:bunker-mvp port 2223 closed + las-03 tailnet down verdict=none commit=none

# Dogfood run 10 — Loki log pipeline (first drive) + fresh rootless install re-proof at MON-GAP-023

Date: 2026-10-15 · Lane: monitoring-dogfood · Target HEAD: fc6b40a (fleet-monitoring) · Live prod: fleet-monitor @21h uptime

## Promise tested

"The Loki surface ships and works: fleet agents push logs to :3100, they are stored,
queryable via LogQL, visible in Grafana, and `make backup` covers the chunks. A fresh
machine can follow the README to a healthy stack (re-proof after MON-GAP-023 bootstrap fix)."

## Part 1 — Loki pipeline on LIVE prod (all green)

1. Push: `POST http://fleet-monitor:3100/loki/api/v1/push` with 2 probe lines
   ({job=dogfood-run10, env=prod, host=kara-hermes}) → **204 in 0.38s** (tailnet round trip).
2. Store/query: `/loki/api/v1/query_range` returned both lines, byte-correct, in correct
   order; `totalEntriesReturned=2`; labels auto-derived (`detected_level`, `service_name`).
3. LogQL: `sum(count_over_time(...))` → 2; grep filter `{job=~"fleet|docker"} |= "error"`
   returns real prod docker error lines (dexdat-core-pyroscope et al); fleet-wide
   `count_over_time({job=~".+"}[1h])` scans ~257k lines/hour from `docker` + `fleet` jobs.
4. Label census: 12 labels; `job` values = docker, fleet, (my probe).
5. Grafana: Loki datasource provisioned (http://loki:3100), `/api/ds/query` with
   `{job="dogfood-run10"}` → 200, frame carries my 2 probe lines + query stats.
6. Own gate: `make verify` on the host → VERIFY: PASS (labels=12, datasources answer).

## Part 2 — Perf census (Step 2b; nothing user-noticeable, no PERF rows)

- push (tailnet, kara-hermes→fleet-monitor): 0.366–0.372s warm ×4 (all 204). First push
  of the session (cold) 0.378s — cold ≈ warm; no user-noticeable delta.
- 2-line query: 0.380–0.384s wall (server execTime 1–20ms; the rest is tailnet RTT).
- Fleet-wide 1h metric over ~257k lines: 2.0s — acceptable for an aggregate scan.
- Fresh-agent local push: 0.0099s (loopback) — confirms 0.37s is network, not Loki.
- Verdict: fast enough everywhere; profiling not justified.

## Part 3 — Fresh rootless install re-proof (bunker-mvp agent 2c7afa8d, destroyed)

Premise changed since run 9: fc6b40a (MON-GAP-023) added the spool-dir bootstrap.
Method: tar-over-ssh clone (GH https clone needs credentials — standing finding), then the
documented path verbatim.

- `make env` ok · `make check-env` FAIL on placeholder GRAFANA_PASSWORD/ALERT_ROUTER_TOKEN
  (honest fail-closed; fill with random values → PASS). OK as designed.
- `make render-configs` → loki LOKI_STORAGE=auto→local, token written. OK.
- `make up` **fails on a NEW unremappable rootless bind**: 
  `/var/lib/fleet-monitoring/node-exporter-textfile` (alloy, compose line 215) →
  `mkdir /var/lib/...: permission denied` under rootless docker. This is MON-DOGFOOD-032's
  class (root-owned binds) but a THIRD instance: run-8/9 covered the spool and state.db
  binds; textfile is new (and the MON-GAP-023 bootstrap fix did NOT extend to it —
  bootstrap creates the dir with sudo but a rootless agent cannot).
- Documented remap path is itself broken on fresh hosts: `COMPOSE_EXTRA=…override.yml` with
  plain `volumes:` **appends** (dup mount persists); compose's own `!override` YAML tag is
  rejected by the repo's lint stage (`could not determine a constructor for the tag
  '!override'` — the lint loader lacks the tag). So neither merge semantics can express
  "replace the volumes list". DEAD-END for a fresh rootless user.
- Bootstrap leg: `scripts/bootstrap.sh` dies at rclone install (writes `/tmp/rclone-install.log`,
  root-only /tmp on the agent) before reaching its dir steps; and even reached, its steps
  need `$SUDO` which a rootless agent user does not have (password-less sudo absent).
  The MON-GAP-023 spool fix is therefore UNPROVABLE on a rootless host — bootstrap itself
  has no rootless mode (MON-DOGFOOD-032 premise re-proven, extended).
- No-sudo rescue executed (rclone 85MB into ~/.local/bin) — but "documented path" needs this;
  README names compose+buildx only (run-9 finding class).
- Result after user-space compensations (override with appended textfile mount, dummy
  state.db, ~/spool): **8/9 core services Up/healthy** (grafana 200, prom 200, router
  healthy 200, loki up, renderer healthy, blackbox, alertmanager, cadvisor, cost-exporter;
  mon-alloy Created-but-not-Started). Fresh-Loki smoke: push 204 in **0.0099s** (loopback),
  query returns the probe line. So the product works fresh once the three binds are remapped
  by hand — but the documented path dead-ends for a real fresh rootless user.
- Destroy: agent destroyed; residue recheck after ~90s → no orphans (reconciler clean).

## Value judgment

- Production Loki surface: ✅ works, fast, wired into Grafana and verify gate — SHIPPABLE.
- Fresh rootless install: 🔴 still fails at `make up` (third rootless bind + broken override
  merge + bootstrap no-rootless-mode). Install promise NOT delivered for this host class.
- Trust: honest fail-closed at check-env (placeholders rejected); probe data never touched
  prod state; prod push/query left a handful of dogfood-run10 probe lines in prod Loki
  (bounded, labeled, harmless).

## Findings (filed on /home/kara/monitoring board)

- MON-DOGFOOD-035 (P1): third rootless-uncreatable bind (node-exporter-textfile) —
  bootstrap fix did not extend to it.
- MON-DOGFOOD-036 (P1): COMPOSE_EXTRA override cannot replace a volumes list — plain merge
  appends dups, `!override` tag fails the repo's own lint. Documented rootless remap
  mechanism is a dead end.
- MON-DOGFOOD-037 (P2): bootstrap.sh dies on root-owned /tmp (rclone log) before dir steps
  and requires sudo throughout — no rootless mode (032 premise re-proven + extended).
- MON-DOGFOOD-038 (P3): Loki surface undocumented (README says "logs → Loki" only; no
  LogQL examples, no push/query doc) — trace docs gap (DOC-001 class), logs edition.

## Left behind

- This file (docs/dogfood/2026-10-15-run10-loki-and-rootless-reproof.md)
- Board rows MON-DOGFOOD-035..038 + dogfood-log.md entry (monitoring repo, pathspec commit)

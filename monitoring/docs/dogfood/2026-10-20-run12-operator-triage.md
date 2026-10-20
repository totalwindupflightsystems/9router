# Dogfood run 12 — 2026-10-20 — operator triage of a live P0 (alert-row truth, drain cost, fresh install)

- angle: FIRST drive of the operator's TRIAGE loop — take a live P0 that the stack itself
  fired, work it the way a real operator would (read the row, follow its evidence link,
  check whether the condition is still true, decide what to do), then judge the pipeline
  that produced it. Runs 1-11 drove ingest/query/backup/install/traces/Loki/dashboards;
  none of them used the board as an operator's work list.
- promise (README + router docstring): an alert carries a `lane` and becomes a board row on
  that lane; the row says "close it when the alert is resolved; a resolution event is
  appended to events.jsonl automatically". `make verify` is the real gate; a fresh machine
  can `make env && make check-env && make config && make up`.
- witness: live stack on `fleet-monitor` (Prometheus 9090, Loki 3100, Alertmanager 9093,
  Grafana 3000, alert-router 8089) + the monitoring board on karaHermes-mde-7840hs.

## 1. The incident I picked up (real, live, not synthetic)

`MON-MONITORING-403C290E-20261020` — **[CRITICAL] DiskFull on bunker-mvp — bunker-mvp / is
1.268% free**, priority 0, status `pending`, filed 2026-10-20 03:27:55Z by
`fleet-monitoring/alert-router`.

**Is it true?** Yes — independently verified from a different leg than the alert:

| leg | evidence |
|---|---|
| Prometheus `ALERTS{alertname="DiskFull",host="bunker-mvp"}` | pending 03:22:55 → firing 03:27:55 → last firing sample 03:44:55, resolved endsAt 03:45:45 |
| Prometheus `node_filesystem_avail_bytes / size` (3h, step 300) | min ratio **0.0000**, max 0.3716, 37 samples — the host really hit 0% free |
| Alertmanager `/api/v2/alerts` at 03:52 | DiskFull gone (resolved); DiskWillFillIn24h still active; 2× TargetUnreachable still active |

So the alert was truthful and its P0 was earned. That is the good news, and it is worth
saying: the alerting rule caught a real disk exhaustion.

**Can an operator act on the row?** Partially. The row's `reasoning` is genuinely useful
("Under 5% free on /. Docker prunes reclaim images, not volumes: check `docker system df`
and the largest volumes before deleting anything"), but the row's ONE link is dead:

```
generator: http://83163ca754e7:9090/graph?g0.expr=...      # docker-internal hostname
curl http://83163ca754e7:9090/graph?g0.expr=up  -> rc=6 (could not resolve host)
getent hosts 83163ca754e7                       -> no such host
```

97 of the 98 alert rows on the board carry a generator URL of that form. The stack's UI is
also loopback-only on its host (`mon-grafana 127.0.0.1:3000`, `mon-alertmanager
127.0.0.1:9093`; only prom/loki/tempo/pyroscope are on 0.0.0.0) and **no document in the
repo tells an operator how to reach Grafana/Alertmanager** (grep for grafana+tunnel/`ssh -L`
in `*.md` and `skills/**/SKILL.md` → no hits; the project root has no README at all). An
operator with this P0 in front of them has to invent an SSH tunnel.

**What happened to the incident?** The disk recovered and the alert resolved at 03:45:45Z.
The board row is **still `pending`** at 04:1xZ. The resolution was recorded — as a *separate*
row `MON-MONITORING-403C290E-20261020-RESOLVED` (`type: alert-resolved`, no `status`),
spooled 03:47:55Z and drained onto **tasks.jsonl** by the 04:00 timer. Nothing annotates or
closes the twin; the two halves of one incident live in two unlinked rows.

## 2. What the queue looks like to the person reading it

Census over the board (108 alert-shaped rows):

- `complete` 96, `pending` 4, `duplicate` 4, `verified-benign` 2, `unverified-expired` 1
- 80 rows on **tasks.jsonl** are `type: alert-resolved` with no `status` field at all —
  resolution events that landed on the task board instead of `events.jsonl`
- five fingerprints have re-minted **16 / 15 / 14 / 13 / 12** times (`FA5F538B`, `AC991D47`,
  `B316017D`, `EE32DFF5`, `B8283F46`) — the same ongoing condition mints a fresh row almost
  every day; each one was closed by hand (`complete`, `duplicate`, `verified-benign`)
- `boardctl validate` on this board is **RED**: `rc=1`, 7 errors, because three of those
  hand-written triage outcomes are outside boardctl's canon
  (`duplicate`, `verified-benign`, `unverified-expired`)

## 3. The chain works (measured, not assumed)

- alert → row: DiskFull fired 03:27:45Z, row on the board 03:27:55Z (10s)
- resolve → resolution row: endsAt 03:45:45Z, `-RESOLVED` row spooled 03:47:55Z and drained
  by the 04:00 timer (~15 min latency, bounded by the 15-min drain timer)
- the drain timer is real: `monitoring-drain.timer` every 15 min, `appended=0..2
  skipped=706..710` per run, exit 0

## 4. Step 2b — what using it COSTS in time

| operation | measurement | verdict |
|---|---|---|
| drain (15-min timer), warm | `DRY=1 MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh` → **real 56.45s** (user 33.20 / sys 15.60); second run **real 67.10s** (user 36.79 / sys 16.86) | **PERF-1** — 42–68s wall, 38–50s CPU per run to append 0–2 rows |
| same, the live timer's own runs | journal 22:30 42.4s/38.2s; 22:45 68.3s/49.7s; 23:00 58.8s/46.4s (systemd: "Consumed 46.402s CPU time over 58.841s wall clock") | confirms, not a DRY artefact |
| Prometheus query from the operator box (warm ×10) | `hyperfine`: **380.1 ms ± 13.0 ms** (min 371 / max 412) for the cost dashboard's headline expression | RTT-bound (server-side is ms) — fine |
| Grafana SPA page load (authenticated, via ssh tunnel) | cold **563 ms** (TTFB 438 ms), warm **241 ms** (TTFB 215 ms) | fine |
| `make config` on a fresh host | **33.6 s wall / 1.8 s CPU** — wait-dominated | noted, not filed (no profile) |
| hermes-cost scrape (the run-11 gap, now deployed) | scrape duration **4.88–6.18 s**, 607 series, day buckets 10-18/10-19/10-20, today $28.55 | live, growing vs run 11's 2.6 s |

**Grafana panel rendering could not be verified from this environment** and I am not filing a
claim about it: in headless Chrome (viewport 780×493) the dashboard route renders page chrome
only — 216 DOM nodes, `page-panes` empty, zero `/api/ds/query` calls — for *every* dashboard
(fleet-overview, host-detail, fleet-cost-tokens), while the API legs are green (dashboard JSON
served, 5 provisioned datasources, Prometheus serving the panels' expressions). That is
consistent with a headless-environment limitation, so it stays an observation, not a row.

## 5. Fresh-install leg (ephemeral bunker, EXECUTED — not skipped)

Agent `monitoring-df12` on `bunker-mvp` (spawned 04:04Z, destroyed after; `bunker list` grep
= 0, no orphan home). Transport: `git archive HEAD monitoring/fleet-monitoring` (225 KB) →
`bunker cp` → extract in `$HOME` (origin is S3, no clone). Host tooling present: Docker
29.9.1, Compose 2.40.3, make 4.3, git 2.43 — **no `docker buildx`**.

| step | result |
|---|---|
| `make env` | ok, 0.02s |
| `make check-env` | **PASS** (0.15s, dev defaults) |
| `make config` | **PASS** (33.6s: compose config -q + lint) |
| `make up` | **FAIL after 40.58s** — `failed to solve: failed to read dockerfile: open Dockerfile: no such file or directory`; `stack/alert-router/` ships `router.py` + `test_pre_resolve.py` and NO Dockerfile while compose builds context `./alert-router`; compose also warns "configured to build using Bake, but buildx isn't installed" |
| `make verify` | FAIL — "the stack was never started on this host… this is not a stack defect" (honest message, correct behaviour) |

This is the **same defect as MON-DOGFOOD-039** (run 11, P1, five days old) **still reproducing
at HEAD** — cited, not re-minted. Delta vs runs 8/10/11 on this host: `mkdir -p
/var/lib/fleet-monitoring` **succeeded** inside the agent, so the rootless-bind blocker class
(032/036) did not reproduce on this agent; agents here run with enough privilege for the
documented binds.

## 6. Rows filed (never fixed by me)

- `MON-DOGFOOD-041` P1 — resolution events land on tasks.jsonl, never events.jsonl (80 live rows)
- `MON-DOGFOOD-042` P2 — rows are never reconciled with alert state (resolved alert ⇒ row still
  pending; 5 fingerprints re-mint daily)
- `MON-DOGFOOD-043` P2 — the row's only evidence link is a dead container hostname, and the UI
  access path is undocumented
- `MON-DOGFOOD-044` P2 — the board is red under `boardctl validate` (7 errors from the lane's own
  triage statuses)
- `PERF-1` P2 — drain costs 42–68s wall / 38–50s CPU per 15-min run, O(spool lines), 3 process
  spawns per line, growing ~54 lines/day
- re-proof event on `MON-DOGFOOD-039` (still live at HEAD)

## 7. Verdict

**SHIPPABLE for the alerting promise** — the stack told the truth about a real disk exhaustion
(0% free, verified on independent legs) and delivered it to the owning board in 10s; the
resolution arrived too. **PROMISING-BUT-ROUGH as an operator work list** — dead evidence links,
undocumented UI access, unresolved rows for resolved conditions, a task board carrying 80
resolution events, and a drain that burns ~1 CPU-minute per 15 minutes to append nothing.
**FAILED-product for fresh install** (unchanged from run 11: no Dockerfile in the canonical
tree, `make up` dies at 40s). No code and no board state was mutated by this run except the
rows and records it filed.

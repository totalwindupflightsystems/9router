# Monitoring lane — dogfood log

## 2026-09-28 | monitoring | PROMISING-BUT-ROUGH
- promise: fired alerts become board rows on owning lanes; stack work driven as reviewable copies
- reality: drain leg works (3.5s, spool empty) BUT the alert→router chain was silently dead ~16h — alertmanager can't read its own root-0600 token file (container uid nobody); a LIVE critical alert (OOMKillsOccurring bunker-mvp, ~17 kills/1h, verified in Prometheus) never became a row. Also: all 10 fleet-health rules target lane `hermes-fleet-ops` which does not exist.
- time-to-first-success: 0s for drain (the command just works); the flagship workflow (alert→row) = FAILED live test
- install: executed on ephemeral bunker (bunker-las-03, agent 1a82f5a8, destroyed after): documented `make env/check-env/render-configs` all pass correctly; `make config` fails everywhere (lint env predates RENDERER_TOKEN; PyYAML missing on fresh hosts); stack up bypassing gate = 5/7 services healthy fresh (grafana/prom/router/renderer up; loki needs real S3; am blocked by rootless host-mount)
- top findings: MON-DOGFOOD-001 (P0 dead delivery, token uid/perm), MON-DOGFOOD-002 (P0 all rules → nonexistent lane), MON-DOGFOOD-003 (P1 make config red everywhere), MON-DOGFOOD-004 (P1 repo exists only on the monitoring host)
- perf: nothing user-visible slow enough to file (drain 3.5s warm; fresh build 8s; up ~10s — waits are Docker Hub pulls, not this project)
- left behind: docs/dogfood/2026-09-28-integration.md, docs/dogfood/diagnostics.md, skills/monitoring-usage/SKILL.md
- foreman woken: no (lane enabled, cooldown 21600 — board rows are pending; scheduler will admit on its own cadence)

## 2026-09-28 (run 2) | monitoring | PROMISING-BUT-ROUGH (improving)
- repeat-run angle: live-verify run 1's fixes + the query surface run 1 skipped + fresh install leg (repo/config files changed today, no same-day exemption)
- promise: alert→row chain works in both directions; query surface usable; fresh machine can reach make config
- reality: chain VERIFIED end to end with a synthetic probe (router 200 in 4.9ms → spool → drain 4.2s → row + -RESOLVED twin on this board; probe rows removed after, census re-verified). AM token fix holding (~8h clean). All 11 rules lane=monitoring, prometheus/loki/grafana APIs healthy, 0 down targets. Fresh install: make env/check-env/render-configs OK as documented; make config FAILS on fresh multi-user hosts for two NEW defects (hardcoded /tmp paths colliding with other users' files; Loki file-mount invisible to rootless docker) — verified 0/10→10/11 with a temp-dir fix; cold lint 549s is image pulls, not project code.
- install: executed (bunker-las-03, agent 960339f7, transferred 7 repo + 25 host files fail=0, destroyed after); smoke = make config 10/11 after probe, honest FAIL on loki step
- top findings: MON-DOGFOOD-005 (P1 /tmp hardcode), MON-DOGFOOD-006 (P1 loki file-mount), MON-DOGFOOD-007 (P2 no bootstrap, measures MON-DOGFOOD-004 cost)
- perf: no user-visible slowness worth a row (drain 4.2s warm, router 5ms; cold lint = pulls)
- left behind: docs/dogfood/2026-09-28-run2-chain-and-query.md, 3 board rows
- foreman woken: no (cooldown pinned 21600 by fleet-toml-import; rows are pending on a live enabled lane)
## 2026-09-30 (run 3) | monitoring | PROMISING-BUT-ROUGH (backup/restore surface)
- repeat-run angle: backup/restore — the one surface runs 1-2 never touched (make backup / restore-check / nightly timer / freshness alert)
- promise: make backup ships loki+prometheus+grafana+bundle to S3; restore-check proves the newest set restorable; a nightly timer does it automatically
- reality: make backup FAILS on the configured host (S3_BUCKET unset — Makefile never feeds .env to scripts, MON-DOGFOOD-010); manual env-sourced run succeeds (~60s, 5 files, 92M) and restore-check PASSes; but the nightly timer shipped 3-file sets BOTH nights since the repo existed — no git bundle, git_head: none (unit execs the stale root-level script + systemd oneshot has no HOME so git dubious-ownership refuses the repo; repro'd) — and restore-check exits 0 on the bundle-less set (MON-DOGFOOD-009). Freshness metric + BackupFreshnessStale + runbook anchor all real; MON-GAP-010 closeable (note left).
- install: SKIPPED-install-bunker — repo/config unchanged today; run 2 (09-28) executed the full fresh-install leg on bunker-las-03 (agent 960339f7, make env/check-env/render-configs OK, make config 10/11 after probe)
- time-to-first-success: ~2 min for a real backup (after the documented command failed; one-line env-source workaround)
- top findings: MON-DOGFOOD-009 (P1 timer bundle-less + guard green), MON-DOGFOOD-010 (P1 make backup env wiring), MON-DOGFOOD-011 (P2 grafana live-db tar fallback + HELP typo)
- perf: nothing user-visible slow (timer 15s, manual backup ~60s, restore-check ~15s); no PERF rows
- left behind: docs/dogfood/2026-09-30-run3-backup-restore.md, diagnostics.md backup section, skills/monitoring-usage/SKILL.md backup section
- foreman woken: no (cooldown pinned 86400 by fleet-toml-import; rows pending on an enabled lane)
- addendum (same run): MON-DOGFOOD-012 (P2) — backup-to-s3.sh never prunes its own Prom snapshots: 8 orphan snapshot dirs since 09-28, prom-data volume 483.6MB (live TSDB ~60MB); unbounded growth until disk fills (same class as MON-CAP-DISK-001)
## 2026-10-01 (run 4) | monitoring | PROMISING-BUT-ROUGH (hold)
- repeat-run angle: verify open run-3 rows against LIVE production timer evidence + fresh-install re-run (005/006 marked done) + chain regression
- promise: nightly timer ships a restorable set; restore-check refuses un-restorable sets; chain alert→row works both directions
- reality: timer 10-01 03:09 shipped 3 files, git_head:none, NO bundle — restore-check PASSed anyway (009 reconfirmed on production evidence); make backup still bare (010 open); chain healthy (router 233/116/117, 0 errors, drain appended=0 skipped=192, duplicates dedupe); stack all-up; freshness metric 17.7h fresh
- install: EXECUTED (bunker-las-03 agent df483f9b, bundle-clone HEAD 08b44cf, destroyed + verified); smoke: restore-check negative path honest rc=1; backup script degraded-graceful except 2 new P2s
- top findings: MON-DOGFOOD-015 (P1: 009/010 still open 2 nights on, prod evidence attached), MON-DOGFOOD-013 (P2 grafana fallback tar-continue), MON-DOGFOOD-014 (P2 rclone unguarded/undocumented)
- perf: drain 12.9s, prom query 2.5s — nothing user-visible slow; 122M upload 2m07s = upstream 504s, no PERF row
- left behind: docs/dogfood/2026-10-01-run4-timer-regression-and-fresh-install.md, rows 013/014/015 (commit 7db304cca)
- foreman woken: no (cooldown pinned 86400 by fleet-toml-import; rows pending on a live enabled lane)

## 2026-10-04 (run 5) | monitoring | FAILED — live delivery chain dark again
- repeat-run angle: verify closed P1 rows (009/010/011) against LAST NIGHT's production timer evidence + chain health + perf re-measure
- promise: nightly timer ships a restorable set; restore-check proves it; alerts become board rows both directions
- reality: backup/restore legs now GREEN on production evidence — timer 10-04 03:03 shipped 5-file set (bundle 1.1MB + HEAD 0a2d78c7 + grafana.db 1.6MB + prom snapshot 232MB + MANIFEST), restore-check PASS incl. bundle-valid + HEAD-match; snapshot pruning active (keep-2); manual re-run 46s PASS. BUT the alert->row chain is DARK again since the router container restarted ~2026-10-02 04:00Z: 56 events received, 55 errors, 0 rows spooled, spool dir EMPTY. Live probe (valid token) confirmed: POST /webhook -> 200 then 'resolved spool failed: [Errno 13] Permission denied: /spool/board-rows.jsonl' — router-spool volume root not writable by uid 10001 (router). Same uid/perm class as closed MON-DOGFOOD-001, recurred on restart/volume recreate; silent because the webhook still 200s. Auth path healthy (unauth probe -> 401).
- install: SKIPPED-install-bunker — no reachable bunkerd host (las-03 offline 9h, las-01 14h, las-02 daemon offline/unauthenticated); MON-DOGFOOD-017 filed. Material: fleet-monitoring subtree changed since run 4's leg (cbc9dcc, DOC-004).
- time-to-first-success: backup 46s; chain probe reached delivery failure in seconds (the failure IS the finding)
- top findings: MON-DOGFOOD-016 (P0 chain dark: spool Permission denied under 200-masking webhook, 55 events lost since 10-02), MON-DOGFOOD-017 (P2 skipped install leg, evidence attached)
- perf: prom query 2ms, router health 5ms, grafana 3ms, webhook 2.6ms, backup+restore-check 46s — nothing user-visible slow; no PERF rows
- left behind: rows 016/017 (commits 32352d9d6, 8e989d83b on origin/main via wt/sched-gap-1662); no repo files touched beyond board + log (meta-repo sibling work in flight)
- foreman woken: no (lane cooldown-pinned; P0 row is pending on a live enabled lane)
- verdict: FAILED — one honest real-use probe showed the flagship workflow (alert->row) delivering nothing for ~2 days while every green metric lied
## 2026-10-04 (run 6) | monitoring | CORROBORATION + INSTALL-RETRY (same day as run 5)
- angle: independently re-probe run 5's P0 (MON-DOGFOOD-016) + retry the install leg (017) + verify the new tip's zero-edit boot path
- reality: P0 reconfirmed live (probe 200 in 6.0ms, errors 56->57, rows_spooled 0, Permission denied on /spool at 23:01:48Z); QA-MONITORING-008 fix independently verified at tip aeb7d3d (fresh archive tree: make build rc=0, make config rc=0 in 7.3s, LOKI_STORAGE=auto -> local); install leg SKIPPED again — bunker-mvp per-agent port 2223 closed (bunkerd itself ONLINE 8/50), las-bunker-03 tailnet down, local bunker CLI token rejected; corroboration NOTES appended to 016 + QA-MONITORING-008 (no duplicate rows)
- perf: nothing user-visible slow (webhook 6ms, config 7.3s) — no PERF rows
- left behind: docs/dogfood/2026-10-04-run6-corroboration-and-install-retry.md, notes on 2 rows, this entry
- foreman woken: no (P0 pending on live enabled lane from run 5)
- verdict: FAILED-product / PASS-run — the flagship alert->row chain still delivers nothing ~3h after filing, while every health endpoint is green

## Run 6 — 2026-10-04 23:39Z (tick monitoring-dogfood-2026-10-04-22-39-03) — DUPLICATE FIRING, converted into independent re-verification
- Lane fired again ~4.5h after run 5 had already filed 016/017. Run 6 did NOT re-file the
  same findings: it independently RE-DERIVED run 5's P0 from sources run 5 did not use, and
  re-attempted the skipped install leg.
- Chain verification (independent of run5's docker-logs path):
  1. REMOTE Prometheus (fleet-monitor:9090 over Tailscale): {job="alert-router"} counters
     received_total=58, errors_total=57, rows_spooled_total=0, rows_appended_total=0 — scraped
     evidence, not container logs. targets: all up (alertmanager, alert-router, blackbox x8,
     cadvisor, loki, prometheus).
  2. Container fs: fleet-monitoring_router-spool/_data is root:root drwxr-xr-x; container
     uid=10001(router); `touch /spool/.wtest` as router -> Permission denied.
  3. OWN probe (token from host .env, not run5's method): POST /webhook -> 200 in 0.0048s,
     then docker logs show `resolved spool failed: [Errno 13] Permission denied:
     /spool/board-rows.jsonl`; errors_total 57->58 live. Probe row DF6PROBE never landed.
     Unauth probe 401 (auth path healthy, matches run5).
  -> MON-DOGFOOD-016 CONFIRMED by independent sources; MON-DOGFOOD-018 filed carrying the
     new evidence (P1).
- Install leg: attempted 6x on 4 bunker servers (las-02 invalid token, mvp agent network
  down, fleet-01 unreachable, fleet-03 x2: subdir-path misconfig then E2BIG on qa-run.sh
  push). All deterministic errors, evidence in /tmp/bunker-qa-mon-df6*.jsonl.
  MON-DOGFOOD-019 filed (P2) extending 017's skip record with the new E2BIG harness note.
- Perf (census, MON-DOGFOOD-020 P3): prom health 0.36-0.43s, instant query 0.39s, 23h range
  query 1.47s (Tailscale relay), webhook 4.8ms, restore-check negative path 0.04-0.15s
  (honest rc=1). Nothing user-noticeable; no profile warranted.
- Values: stack read paths healthy and fast; restore-check honest-failure path intact;
  backup/restore legs (run 5's greens) not re-litigated. The ONE thing broken is the
  alert->row chain — still dark, now with ~58 silently dropped events.
- foreman woken: no (lane cooldown-pinned 259200 by api; rows wait on a live lane).
- verdict: FAILED-product / PASS-run — independent re-derivation of the P0; two new rows
  (018/019) + perf census (020).

## 2026-10-09 (run 7) | monitoring | SHIPPABLE (chain verified live) + fresh-install defects
- angle: verify run-6 P0 remediation on LIVE production evidence + BackupFreshness fix holding + fresh-install leg (new angle: full documented make path incl. `make up`)
- promise: alerts become board rows end-to-end; backup freshness gauge truthful; a fresh machine can install per docs
- reality: chain GREEN live on fleet-monitor (scraped counters: received 144, errors 0, rows_spooled 92, 52 resolved; spool uid 10001 owned, fresh RESOLVED twins landing 20:41Z); drain healthy (timer every 15m, manual run appended=0 skipped=121, rows present on board incl. FA5F538B-20261009 twins); backup freshness: cube-agent 5.6h, fleet-monitor 17.9h, kara-hermes 76.1h; only TargetUnreachable cx53-01 (known owner row) + benign OOMKillsLowPressure firing. Install leg EXECUTED on bunker-las-02 (bunker3 down; first spawn failed slice-limits transient, retry OK): make env/check-env/config PASS (73s), but `make up` FAILS fresh for 2 real defects (missing Dockerfile in build context; /var/lib bind-mount sources uncreatable rootless) — core 6 services proven up + router healthy (200/401) only after throwaway Dockerfile + ~/spool rebind, both uncommitted.
- perf: drain 14.5s warm (121 dedup id-checks), prom query 16ms, AM alerts 13ms, config 73s cold — nothing user-noticeable; no PERF rows.
- install: EXECUTED — smoke partial: documented path green through config, `make up` fails at the 2 filed defects; router itself proven healthy after compensations on the throwaway copy.
- top findings: MON-DOGFOOD-021, MON-DOGFOOD-022, MON-DOGFOOD-023, MON-DOGFOOD-024
- left behind: rows (this commit), this log entry
- foreman woken: no (read-only dogfood lane)
- verdict: SHIPPABLE for its production promise (the alert->row chain finally verified delivering live); install-from-docs still fails at `make up` for a fresh user.

## 2026-10-12 (run 8) | FAILED-product / PASS-run (fresh-install re-proof) 
- angle: re-proof closed run-7 install defects (021/022/023 fixes landed 4c9d39b) on a FRESH box + first drive of disk-guard/disk-metrics-textfile own-host pipeline
- promise: a fresh machine can `make env && make check-env && make up` per docs
- reality: bunker-las-02 spawn failed x2 (slice-limits) -> bunker-mvp agent 8faaa8f8; clone via tar fallback (GH https clone needs cred); check-env PASS; make up reached 7/9 Up (router/prom/am/grafana/renderer/cadvisor/alloy healthy) only after 4 compensations: stale-RootlessKit-lock rescue at FIRST boot (024 re-proof, second host), Dockerfile scp (clone-only gap, 021 closure holds for real clones), bind-mount remap (022 fix requires root bootstrap), port remaps 8080/12345; loki + cost-exporter crash-loop for NEW reasons (025 exporter.py absent from published repo; 026 loki delete_request_store:s3 hard dep with no creds)
- own-host pipeline: disk-guard timer firing, --dry-run honest (267G free, would_shed=no), textfile metrics fresh in prom (0.12s walk); DiskWillFillIn24h not firing; only cx53 TP firing
- perf: install-to-healthy ~3.5min post-rescue; metrics 0.12s; nothing user-noticeable, no PERF rows
- rows: MON-DOGFOOD-025 (P1), 026, 027, 028 (P2), 024-REPROOF event note
- foreman woken: no (read-only dogfood lane)
- verdict: FAILED-product for fresh install (docs+fixes real but 4 unsurfaced blockers remain); production surface healthy

## 2026-10-12 (run 9, sibling of run 8) | monitoring | traces surface VERIFIED live + fresh-rootless install re-proof
- angle: FIRST drive of the traces/Tempo surface (unexercised in runs 1-8) + independent fresh-install re-proof on bunker-las-02 at origin/main 4c9d39b (run 8 used bunker-mvp; parallel sibling tick)
- promise: OTLP traces pushed to the published ports are stored, searchable, visible in Grafana, with span-metrics in Prometheus; a fresh rootless host can follow the README
- reality (traces, ALL GREEN live on fleet-monitor): OTLP/JSON push to fleet-monitor:4318 -> 200 partialSuccess={} (399-404ms tailnet, 0.4s cold); Tempo /api/search returns the probe trace by id AND by resource.service.name tag (4ms host-local, 19ms via relay); Grafana Tempo datasource health OK + /api/ds/query TraceQL frame 200; span-metrics landed in Prometheus live ({source="tempo",service="dogfood-run8"} traces_spanmetrics_latency_*). BUT the ingest topology is miswired vs its own comments: compose maps 4317/4318 to mon-tempo directly while stack/alloy/config.alloy:177-206 claims the Alloy receiver owns those ports (dead config; mon-alloy publishes only 12345); Tempo metrics-generator sat idle 10 days (active_series=0) until this probe; no fleet producer emits trace ids into Loki so the provisioned tracesToLogs/'Open trace' correlation can never fire; zero docs mention traces (DOC-001 re-proven).
- reality (fresh install, bunker-las-02 agent f875e513, destroyed): repo private (GH https clone 404/could-not-read-Username) -> sanctioned tar fallback from origin/main archive; bootstrap rc=2 (sudo required for rclone install, bootstrap.sh:38-44); compose v2 + buildx 0.17 hand-installed to user space (README bullet names compose but not buildx); loki-config.active.yml created as a DIRECTORY -> render-configs.sh:47 cp silently copies INTO it -> Loki crash-loop 'is a directory' (green make, red product); after rm+re-render, Loki up; 5/7 core services healthy fresh (grafana 200, prom, renderer, blackbox, loki); cadvisor RootlessKit port 8080 collision; alert-router dead on root-owned /var/lib/fleet-monitoring/spool (override remap incomplete); make up rc=1 with 'failed to read dockerfile' when buildx < 0.17 despite compose v5.6 present.
- CONCURRENT-SIBLING NOTE: run 8 (bunker-mvp) landed rows 025-028 mid-tick; my five rows renumbered 030-034 with created_by=dogfood-run8-mine; 030/031/032 overlap run-8's findings and cite them independently re-proven.
- perf: push 399-404ms cold (tailnet), ~0.4s warm re-push; Tempo search 4-19ms; Grafana ds/query fast; no user-noticeable slowness -> no PERF rows (census only).
- rows: MON-DOGFOOD-030 (P2 override file missing), 031 (P1 render-configs dir-poisoning), 032 (P2 rootless blockers persist), 033 (P3 traces miswired+undocumented), 034 (P3 trace-logs correlation dead)
- left behind: rows (pathspec commit), this log entry, docs/dogfood/2026-10-12-run9-traces-and-fresh-install.md
- foreman woken: no (read-only dogfood lane; rows wait on a live lane)
- verdict: SHIPPABLE for the traces promise (ingest->store->search->Grafana->metrics all green live); FAILED-product for fresh rootless install (5/7 core up, two new defects); PASS-run
## 2026-10-15 run 10 — Loki pipeline (first drive) + fresh rootless re-proof at fc6b40a (bunker-mvp)
- angle: FIRST drive of the Loki log-pipeline surface (runs 1-9 touched traces/chain/backup/disk, never logs end-to-end) + re-proof of the rootless install premise AFTER the MON-GAP-023 bootstrap-spool fix (fc6b40a) changed it
- promise: fleet agents push logs to :3100, stored + LogQL-queryable + visible in Grafana; a fresh machine can follow the README to a healthy stack
- reality (Loki on live prod, ALL GREEN): push {job=dogfood-run10} -> 204 in 0.38s (tailnet); query_range returns both probe lines byte-correct; count_over_time and |= "error" LogQL work over the real corpus (~257k lines/h from docker+fleet jobs); 12-label census; Grafana /api/ds/query frame 200 with the probe lines; make verify on-host PASS. Product-side: production Loki surface is SHIPPABLE and fast.
- reality (fresh install, bunker-mvp agent 2c7afa8d at fleet-monitoring fc6b40a, destroyed, residue clean): tar-over-ssh transfer; make env ok; check-env honestly fails placeholders -> PASS after filling; render-configs ok (auto->local); make up FAILS on a THIRD rootless-uncreatable bind — alloy's /var/lib/fleet-monitoring/node-exporter-textfile (stack/docker-compose.yml:215); the documented COMPOSE_EXTRA override cannot replace a volumes list (plain merge appends, compose !override tag rejected by the repo's own lint loader); bootstrap.sh dies on root-only /tmp (rclone log) before the MON-GAP-023 dir steps and needs password sudo throughout. After user-space compensations (~/spool + dummy state.db + textfile remap attempt) 8/9 core services Up/healthy (grafana/prom/router/loki/renderer/blackbox/alertmanager/cadvisor/cost-exporter; mon-alloy Created-never-Started); fresh-Loki loopback push 204 in 0.0099s + query round-trip OK. Install promise still NOT delivered for rootless (docs+product path dead-ends), but the compensable product core is proven again.
- perf: push 0.366-0.372s warm x4, cold 0.378s (no user-noticeable delta); 2-line query 0.380-0.384s wall (server exec 1-20ms); fleet-wide 1h metric 2.0s; loopback push 0.0099s -> the 0.37s is tailnet RTT, not Loki. Nothing slow enough for PERF rows.
- rows: MON-DOGFOOD-035 (P1 third rootless bind), 036 (P1 override merge dead end), 037 (P2 bootstrap no rootless mode, 032 extended), 038 (P3 Loki docs gap)
- install: EXECUTED (bunker-mvp, agent 2c7afa8d, ttl'd, destroyed, residue recheck clean) — smoke partial: 8/9 core up post-compensations; documented path fails at make up (rc=2) for the filed defects
- left behind: rows (pathspec commit), this log entry, docs/dogfood/2026-10-15-run10-loki-and-rootless-reproof.md
- foreman woken: no (read-only dogfood lane; rows wait on a live lane)
- verdict: SHIPPABLE for the Loki/production promise (pipeline fully green + fast); FAILED-product for fresh rootless install (third bind + override-merge dead end + bootstrap still sudo-only); PASS-run

## 2026-10-15 (run 11) | monitoring | dashboards-as-code + fleet-cost pipeline + verify gate (fresh-install Dockerfile disproven)
- angle: FIRST drive of the Grafana dashboards-as-code surface + Fleet Cost & Tokens end to end (MON-GAP-012 closed complete) + the verify gate; run 10 same day covered Loki/rootless, no overlap
- promise: a user opens Grafana and sees live fleet cost & token dashboards; make verify is the honest gate
- reality: fleet-cost dashboard 404 in live Grafana (6 dashboards provisioned, not this one); NO hermes-cost scrape target active, no cost-exporter container on fleet-monitor, live compose (a83c50dd7) is pre-cost-exporter vs repo main (84c9d4e0); hermes_session_est_cost_usd = 7876 series frozen at day=2026-10-06 (~$84 that day) — MON-GAP-012 repo-true, live-false. Exporter code GOOD: local run scrape 2.6s cold=warm, 9.2MB, 9997 cost lines incl today. verify gate: top-level host verify.sh stale (md5 4afc9529) FALSE-FAILs 'no containers found' on 11/11-Up stack; scripts/verify.sh (byte-identical to repo main) VERIFY: PASS 6/6. Fresh install (bunker-mvp agent 441ad5e0, tar fallback, destroyed): make config+check-env PASS 2s; make up FAIL 76s — fleet-monitoring/stack/alert-router/ ships NO Dockerfile on main (exists only in gh/ft009 history + live host); run-8's '021 closure holds for real clones' DISPROVEN on main@01efa2ad8
- perf: exporter 2.6s/9.2MB scrape (not scraped); nothing else user-noticeable -> no PERF rows
- rows: MON-DOGFOOD-039 (P1), MON-DOGFOOD-040 (P2)
- left behind: rows (pathspec commit), this log entry, docs/dogfood/2026-10-15-run11-dashboards-cost-verify-gate.md
- foreman woken: no (read-only dogfood lane)
- verdict: FAILED-product for cost-dashboard promise + fresh install on main; SHIPPABLE core observability (scripts/verify.sh PASS)

## 2026-10-20 (run 12) | monitoring | operator triage of a live P0 (alert truth + drain cost + fresh install)
- angle: FIRST drive of the OPERATOR TRIAGE loop — take a live P0 the stack itself fired, work it as a real operator (read the row, follow its evidence link, check whether the condition still holds), then judge the pipeline that produced it. Runs 1-11 drove ingest/query/backup/install/traces/Loki/dashboards; none used the board as a work list.
- promise: an alert carrying a `lane` becomes a board row on that lane; "close it when the alert is resolved; a resolution event is appended to events.jsonl automatically"; `make verify` is the gate; a fresh machine can follow the README to `make up`
- reality (the incident, live): MON-MONITORING-403C290E-20261020 P0 DiskFull bunker-mvp filed 03:27:55Z — TRUE on independent legs (ALERTS pending 03:22:55 → firing 03:27:55 → resolved endsAt 03:45:45; node_filesystem avail/size min ratio 0.0000 = the host really hit 0% free). Alert→row 10s. Resolution recorded as a SEPARATE -RESOLVED row (spooled 03:47:55Z, drained to tasks.jsonl by the 04:00 timer) while the P0 row stays `pending` — one incident, two unlinked rows.
- reality (row actionability): row detail is good, its only link is dead — 97/98 rows carry `generator: http://83163ca754e7:9090/...` (docker-internal Prometheus hostname; curl rc=6, getent no such host); Grafana/Alertmanager are loopback-only on fleet-monitor (127.0.0.1:3000 / :9093) and no doc mentions a tunnel (project root has no README).
- reality (queue census): 108 base alert rows = 96 complete / 4 pending / 4 duplicate / 2 verified-benign / 1 unverified-expired; FIVE fingerprints re-minted 16/15/14/13/12 times; 80 rows on tasks.jsonl are `type=alert-resolved` with no status (resolution events landing on the TASK board, not events.jsonl) — the router's own promise text is false in the spool topology (router.py:371-392 + drain-board-rows.sh:47-71 route by lane only, never by `type`); `boardctl validate` is RED (rc=1, 7 errors: statuses duplicate/verified-benign/unverified-expired outside the canon).
- reality (perf): drain (15-min timer) 42-68s wall / 38-50s CPU per run to append 0-2 rows — DRY 56.45s (user 33.20/sys 15.60) and 67.10s (36.79/16.86); journal confirms 42.4s/38.2s, 68.3s/49.7s, 58.8s/46.4s; hot path = 2× python3 + 1× grep per spool line (710 lines) each re-grepping a 963KB board → ~79ms/line, spool grows ~54 lines/day. Prom query 380.1ms ±13.0 (RTT-bound), Grafana SPA cold 563ms / warm 241ms, hermes-cost scrape 4.88-6.18s (run-11's cost gap is now LIVE: 607 series, day buckets 10-18/19/20, today $28.55).
- install: EXECUTED (bunker-mvp agent monitoring-df12, git-archive tar, destroyed; no residue) — make env ok / check-env PASS 0.15s / make config PASS 33.6s / `make up` FAIL 40.58s "failed to read dockerfile: open Dockerfile: no such file or directory" (stack/alert-router/ has no Dockerfile; buildx absent) — SAME defect as MON-DOGFOOD-039, still live at HEAD after 5 days (cited, not re-minted). Delta: `mkdir -p /var/lib/fleet-monitoring` SUCCEEDED in the agent, so the rootless-bind class (032/036) did not reproduce here.
- inconclusive (not filed): headless Chrome renders no Grafana panel grid for ANY dashboard (216 DOM nodes, empty page-panes, zero ds/query calls) while all API legs are green → recorded as an environment limitation, no claim filed.
- rows: MON-DOGFOOD-041 (P1 resolution events on tasks.jsonl), 042 (P2 rows never reconciled with alert state), 043 (P2 dead evidence link + undocumented UI access), 044 (P2 boardctl validate RED), PERF-1 (P2 drain cost) + MON-DOGFOOD-039 re-proof event
- left behind: rows, this log entry, docs/dogfood/2026-10-20-run12-operator-triage.md, diagnostics.md section, skills/monitoring-usage update
- foreman woken: no (read-only dogfood lane; rows wait on a live lane)
- verdict: SHIPPABLE for the alerting promise (the stack told the truth about a real disk exhaustion and delivered it in 10s); PROMISING-BUT-ROUGH as an operator work list; FAILED-product for fresh install (unchanged)

## 2026-10-20 (run 13) | monitoring | PROMISING-BUT-ROUGH (live alert re-proof + install battery)
- angle: re-proof the live alert set and drain idempotence after run 12, then run the active `bunker-qa.sh` fresh-agent leg against the correctly scoped fleet-monitoring subtree
- promise: a real operator can verify an alert, drain it to the lane board, and install the stack from the documented Makefile path on a fresh machine
- reality: live Prometheus reported DiskWillFillIn24h on bunker-mvp, OOMKillsLowPressure on bunker-mvp and karahermes-mde-7840hs, and two known TargetUnreachable alerts; direct bunker-mvp filesystem ratio was 0.15727011946882058, so the warning was grounded. DiskFull had resolved. Drain appended the DiskFull resolution twin once; repeat drain appended 0 and skipped 710. Board readback after the append: 539 valid lines, 539 unique ids.
- install: EXECUTED on bunker-mvp (agent b3cda072, destroyed by collect, evidence `/tmp/bunker-qa-evidence-20261020T040827Z-3795904.jsonl`); scoped subtree transfer and `make build`/compose config render passed, but the battery did not run `make up` (docker-deploy reported no compose file) and native verify failed because the stack was never started. Fresh install remains unproven/failed at the documented `make up` path; MON-DOGFOOD-039 remains the existing product finding.
- perf: drain 56.16s cold-ish / 63.03s warm at ~710 spool lines; re-proof of PERF-1, no duplicate row. strace: wait4 42.52s, read 3.39s.
- rows: no new rows; re-proved MON-DOGFOOD-039, MON-DOGFOOD-041..044, and PERF-1
- left behind: docs/dogfood/2026-10-20-run13-live-alert-and-install-reproof.md; no code or scheduler changes
- foreman woken: no (read-only dogfood lane)
- verdict: PROMISING-BUT-ROUGH — production alerting reports real conditions and drain is idempotent, but operator reconciliation/evidence-link defects remain and fresh `make up` install is not delivered

## 2026-10-20 (run 14, same tick, second angle) | monitoring | SHIPPABLE (silencing) + pyroscope known-value (P3 filed)
- angle: the operator's SILENCING tool (never driven by runs 1-13) and the pyroscope continuous-profiling surface (never driven, never documented); runs 12/13 are same-tick siblings (row triage/install, live alert re-proof/install battery)
- promise: an operator being paged by a chronic alert can silence it from the stack's own API, see it take effect, and remove it; the fleet's perf lane can confirm profiles are arriving
- reality (silence lifecycle, live on fleet-monitor 04:24:32-04:25:32Z): POST /api/v2/silences (alertname=TargetUnreachable + host=standby-cx53-01-2147) -> 200 in 4.1ms, silenceID bf61c8c2-...; GET /api/v2/alerts showed status.silencedBy=[bf61c8c2...] on BOTH 100.79.83.6:10001/:10002 while the control alert (DiskWillFillIn24h) stayed [] -> matchers are precise; DELETE -> 200 and silencedBy cleared on both. Router counter deltas all 0 across a 60s window - honest limit: group_interval 5m / repeat_interval 12h means the window cannot prove notification suppression, so the proof is silencedBy (AM's contract) not the delivery count. Route cadence read from /api/v2/status: group_wait 30s, group_interval 5m, repeat_interval 12h, resolve_timeout 5m, receiver alert-router + send_resolved true. The router has NO silence surface (rows come from AM webhooks) -> MON-GAP-029's "silence at the alert-router" wording is imprecise; the surface is AM :9093. A deleted silence persists as an expired record in GET /api/v2/silences (0 active).
- reality (pyroscope): mon-pyroscope (grafana/pyroscope:1.9.0, 0.0.0.0:4040) IS ingesting - hourly "head successfully written to block" (latest 04:25:32Z), POST /querier.v1.QuerierService/Series -> 200 with a real labelsSet, Grafana datasource health OK - but GET /pyroscope/api/v1/labels, the exact URL the fleet perf skill tells lanes to use, returns 404 on 1.9.0, and no doc in this repo mentions pyroscope at all (grep: 0 hits) -> MON-DOGFOOD-045 (P3)
- perf: AM /api/v2/alerts 1.54-2.11ms, /api/v2/silences 1.26-2.54ms, silence POST 4.1ms, router /health 1.75-2.64ms (on-host warm x8); prom /api/v1/alerts from the operator box 370.2ms +-4.9 (hyperfine warm x8, tailnet RTT) - nothing user-noticeable, NO PERF row this run (PERF-1 remains the open drain-cost row)
- rows: MON-DOGFOOD-045 (P3, pyroscope undocumented + documented probe 404s); event 141 appended to MON-GAP-029 (verified silence recipe + cadence facts + the AM-not-router correction); no other rows, no siblings duplicated
- disclosure: one time-boxed prod mutation (a 120s silence on the known-noise chronic alert), deleted in-run and verified cleared; one expired silence record remains (suppresses nothing)
- foreman woken: no (read-only dogfood lane)
- verdict: SHIPPABLE for the silencing promise; pyroscope moves from unknown to known-value with the discoverability defect filed


## 2026-10-23 (run 15) | monitoring | SHIPPABLE drain contract (MON-GAP-032 fix driven as a user) + PROMISING-BUT-ROUGH install (Dockerfile recurrence)

- angle: FIRST drive of the drain contract the MON-GAP-032 fix changed (resolved-event routing, flock, refire rule), plus clone-equivalent reinstall re-proof after the release-row findings (RELEASE-MON-009/010). Runs 1-14 left this slice untouched: they measured the OLD drain's cost and routed around its defects, never verified the fix as a USER would.
- promise: "a repeated drain appends nothing; an alert-resolved event reaches events.jsonl (not tasks.jsonl) exactly once; a re-fired alert re-opens only today's closed row; two drains racing serialize; `./scripts/drain-board-rows.sh` is what an operator runs."
- reality (live prod, all measured):
  - idempotence: 3 consecutive live drains appended=0 skipped=856 (once appended=1/skipped=855 when the timer had not yet drained the newest row — correct).
  - LIVE end-to-end cycle on prod: HighLoadPerCore @ bunker-mvp fired (activeAt 04:19:08Z); row appended to tasks.jsonl by the 00:00 local timer; alert resolved endsAt 05:00:08Z; -RESOLVED event appended to EVENTS.jsonL by the 00:15 local timer (MON-DOGFOOD-041 routing verified again); repeat drains replay nothing; 1 copy of the id in each file.
  - flock: two racing drains — the second refused rc=3 with "another drain already holds" and appended nothing; the first completed normally.
  - refire rule: every live run plan shows olddate-suppressed=93 stale-suppressed=2 (real historical spool replay, correctly silenced); scratch twin run (board copy + ED74A491-20261023 flipped terminal + PROM snapshot carrying a genuinely firing HighLoadPerCore) — run A appended=1 refire=1, run B appended=0: one row per id, exactly one.
  - scratch fixture battery: 13/13 PASS (fix's own test).
- reality (install leg, clone-equivalent tree via git archive HEAD -> ~/scratch-mon-df15):
  - make env PASS; check-env PASS (rc=0, placeholders are all "dev default — REPLACE" non-secrets); make config PASS (compose OK + LINT: PASS); make up FAILS rc=17 "failed to read dockerfile: open Dockerfile: no such file or directory" — docker compose build alert-router fails alone (0.55s) on the same tree: stack/alert-router/ has NO Dockerfile (tracked or untracked). RECURRENCE of MON-DOGFOOD-039 -> filed MON-DOGFOOD-039-R2 (the prior close fixed the cost pipeline, not this; README:82's "Dockerfile, which is committed" is FALSE at HEAD while the file exists on the live host and in the 0f19a773d context).
  - bunker-qa.sh harness defect found while driving the leg: BUNKER_QA_SUBDIR is applied ONLY inside the `if [ ! -d "$repo/.git" ]` branch, so dispatching the git ROOT (/home/kara) with SUBDIR=monitoring/fleet-monitoring joined NOTHING, graded the whole home meta-repo as project=kara, and detect_cmds baked `pnpm install` (an UNTRACKED scratch pnpm-lock.yaml at the meta-repo root) into the install verb -> fresh-install INFO/ci-pass FAIL/upgrade FAIL cells about the wrong product. Filed MON-DOGFOOD-050. Real install behavior below was obtained from the clone-equivalent tree ON THIS BOX instead, disclosed here.
  - the fresh-install battery is therefore UNPROVEN for `make up` on a clone-equivalent tree, and the clone run IS the closest honest read: rc=17 on the missing Dockerfile.
- repo surface state measured:
  - the fixed drain EXISTS only ops-side: ~/.hermes/scripts/drain-board-rows.sh md5 53657b05 == monitoring/fixes/mon-gap-032/drain-board-rows.sh; `git ls-files monitoring | grep drain` shows ONLY the fixes/ copies; no repo tracks the deployed file; fleet-monitoring/docs/runbook.md:129 tells a user ./scripts/drain-board-rows.sh — which resolves to NOTHING in a clone (worse than the defective copy RELEASE-MON-010 described). Filed MON-DOGFOOD-048.
- perf (Step 2b, run against the live spool 856 lines):
  - wall 8.81-9.41s (warm x3 + cold); user 0.88-1.02s; sys 1.56-1.62s; RSS 23MB. Timer journal now shows ~2s/run end-to-end on steady state.
  - vs PRE-fix (run 12, PERF-1): 56-68s wall, 38-50s CPU -> ~6x wall, ~16x CPU. Stage split: classify ~2.3s, apply ~4.7s, rsync fetch ~1.9s; the seconds live in waits (RTT/fsync), nothing a 15-min operator feels.
  - strace: 16,864 openat / 1,740 procs; 865 board/jsonl + 864 spool opens = ~2 file opens per spool line remain but each spawn is now a cheap sed/classify, not python3+grep per line.
  - VERDICT: PERF-1 premise FIXED on the operator box -> CLOSED with event 164 (no new PERF row).
- rows: MON-DOGFOOD-048 (P2 propagation gap), MON-DOGFOOD-039-R2 (P1 recurrence), MON-DOGFOOD-050 (P2 fleet-harness), events 164/165/166 (PERF-1 close, MON-GAP-032 verified, RELEASE-MON-010 evidence)
- pre-existing board damage NOT repaired by this lane: 14 duplicate-id validate errors (10 dup id classes, every duplicate created_at <= 02:43:38Z — ALL pre-deploy; zero post-deploy); owned by MON-GAP-033/MON-DOGFOOD-047's lane.
- install: EXECUTED on scratch (clone-equivalent) -> make up rc=17 (missing Dockerfile); bunker battery leg EXECUTED but graded the wrong product due to MON-DOGFOOD-050 (its 3 junk cells discarded).
- left behind: rows + events (pathspec commit), this log entry, docs/dogfood/2026-10-23-run15-fixed-drain-and-clone-install.md, diagnostics.md section, skills/monitoring-usage drain section
- foreman woken: no (read-only dogfood lane)
- verdict: SHIPPABLE for the drain promise (the fix delivers the operator contract exactly as documented, fast); PROMISING-BUT-ROUGH overall (fresh install still dead-ends at the untracked Dockerfile; release surface cannot pass the drain promise it documents)

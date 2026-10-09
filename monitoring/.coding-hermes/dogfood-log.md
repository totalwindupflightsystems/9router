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

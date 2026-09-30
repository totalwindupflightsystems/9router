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

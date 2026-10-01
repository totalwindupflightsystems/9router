# Monitoring dogfood run 4 — 2026-10-01 — alert-chain + timer regression re-verification + fresh-install re-run

## Run identity
- Lane: monitoring-dogfood, tick 2026-10-01T20:48Z. Verdict: **PROMISING-BUT-ROUGH (hold)**.
- Repeat-run angle chosen: run 3 (09-30) filed MON-DOGFOOD-009/010/011/012 against the
  backup/restore surface; none were marked done. Two nights of production timer runs now
  exist — this run verifies against LIVE timer evidence instead of re-deriving, re-runs the
  fresh-install leg (run 2's 005/006 are now marked done, so their fixes should be visible),
  and re-drives the alert→row chain for regression.

## What was verified LIVE (no re-spawn needed)
1. **Nightly timer (2026-10-01 03:09 UTC, journalctl):** prometheus snapshot OK
   (122M tar.gz), grafana .tgz OK, upload hit 2x 504 GatewayTimeout then "Attempt 3/3
   succeeded" (2m07s for 122M — slow upstream, watch it), freshness metric written.
   **BUT: git_head: none, manifest = 3 files, no git bundle — MON-DOGFOOD-009 reconfirmed
   on production evidence, not synthetic.** restore-check printed
   "no git bundle in this set" and then **PASS**ed. Both P1s remain open.
2. **make backup wiring (MON-DOGFOOD-010):** Makefile line 96 is still bare
   `@scripts/backup-to-s3.sh` — no .env sourcing. Open as filed.
3. **Stack health:** all prometheus targets up; 11 rules loaded (9 inactive, DiskWillFillIn24h
   pending and then resolved); router /health counters 233 received / 116 spooled / 117
   resolved / 0 errors; grafana /api/health ok. Freshness metric age 17.7h = matches timer run.
4. **Alert→row chain:** 2 duplicate OOM alert rows (D76F0FEE, FA5F538B 09-28/09-29) exist in
   BOTH the remote spool and this board (done). Drain executed live: appended=0 skipped=192 —
   router writes DIRECT when the lane has a local board (write_mode "board" in /health), so the
   spool file holds only pre-09-28 leftovers that dedupe correctly. Chain = working.
5. **Spool:** 4 files, 1 live (192 deduped lines), 3 dated .bak files — housekeeping only.

## Fresh-install leg (EXECUTED — no skip row)
- Host probe: ssh bunker3 key-refused (publickey/password) BUT bunkerd API live
  (`bunker list --server bunker-las-03` OK). Per skill, agent keys are independent → spawned.
- Agent df483f9b (TTL 2h, destroyed + verified gone after). Clone: bundle-based (repo origin
  is an s:// remote, private GitLab URL inside the bundle is unreachable from the agent) —
  1.1MB bundle, HEAD 08b44cf, file contents verified by md5 against the workdir copy.
- Agent had every documented prerequisite (docker/make/git/curl/python3). Rootless docker:
  per-user /var/run/docker.sock permission-denied (expected); bunkerd socket works via
  DOCKER_HOST (the workaround is documented in skills/monitoring-usage — a real fresh user
  without the skill would hit it; that is run 2's known finding territory, not new).
- Smoke (restore-check on dummy credentials against a dead endpoint): correct honest
  failure — "no 'latest' pointer … has backup-to-s3.sh ever run?" rc=1. GOOD behavior.
- backup-to-s3.sh on the fresh box: degraded but instructive — snapshot WARNING (no prom),
  grafana fallback `tar: grafana.db: No such file or directory` yet continues (→
  MON-DOGFOOD-013), then dies at upload with **rclone missing and no guard** (→
  MON-DOGFOOD-014). All documented prereqs present; rclone is simply not documented.

## Findings filed (board rows, commit 7db304cca)
- MON-DOGFOOD-013 (P2): grafana fallback tar of nonexistent db continues silently.
- MON-DOGFOOD-014 (P2): rclone unguarded + undocumented prerequisite.
- MON-DOGFOOD-015 (P1): 009/010 still open 2 nights on, production timer evidence attached.

## Perf
- Drain (idempotent, 192 deduped rows): 12.9s. Remote prom query: 2.5s. Nothing a user
  would feel as slow. The 122M S3 upload at 2m07s is upstream (2x 504s from hel1), not
  project code — noted in 015's evidence, no PERF row.

## Verdict
PROMISING-BUT-ROUGH. The chain and stack are solid; the backup surface's two P1s (bundle-less
sets accepted by restore-check; make backup env wiring) are the difference between
"backup exists" and "backup restores", and they are still open. Foreman cooldown is pinned
86400 by fleet-toml-import — rows wait on a live enabled lane; no wake attempted (pin).

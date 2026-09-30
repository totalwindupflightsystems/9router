# Dogfood run 3 — monitoring lane, 2026-09-30 (backup/restore surface)

Lane: monitoring-pm tick (dogfood executed against project `monitoring`, repo
fragment workdir `/home/kara/monitoring`, live host `fleet-monitor`). Run 1
(2026-09-28) swept the drain chain; run 2 (2026-09-28 evening) the query APIs and
fresh install. Neither touched the **backup/restore surface** — the promise
"the stack survives its host being rebuilt" — so that is this run's angle.

## Promise under test

Host README: `make backup` pushes "loki chunks + prometheus snapshot + grafana db +
git bundle → S3"; `make restore-check` "verifies the newest backup is readable (not
just present)"; a nightly timer (`fleet-monitoring-backup.timer`, 03:00 UTC +600s
random) runs both automatically; `BackupFreshnessStale` (48h) alerts if backups
stop. Null hypothesis: a user can back the stack up and prove it restorable using
only the documented commands.

## What was actually done (real use, from outside)

1. **`make backup` — FAILED in 0 seconds.** On the live host, with `.env` fully
   configured (all six `S3_*` keys present, `check-env.sh` demands them): 
   `scripts/backup-to-s3.sh: line 19: S3_BUCKET: S3_BUCKET unset`. The Makefile
   passes `--env-file .env` only to compose; the backup/restore targets never see
   it. The systemd unit works because it has `EnvironmentFile=.env` — the
   documented *manual* path is the broken one. → **MON-DOGFOOD-010 (P1)**.
2. **Real backup, env sourced manually** (`set -a; . ./.env; set +a;
   scripts/backup-to-s3.sh`): SUCCESS in ~60s wall. Prometheus snapshot 91M via
   admin API (`--web.enable-admin-api` is on), git bundle 1.2M (4 refs), manifest
   with sha256s, upload to `s3://karahermes-hel/monitoring/2026-09-30_100619`,
   freshness stamp written. One wart: the grafana leg fell back to *tar-copying the
   live sqlite db* (no sqlite3 in the image) — the script's own header forbids
   exactly that. → **MON-DOGFOOD-011 (P2)**.
3. **`restore-check.sh` on that set: PASS.** All checksums verify, bundle valid
   with the recorded HEAD, snapshot tar readable. The guard works on sets that
   exist — see finding 1 for what it misses.
4. **The nightly timer — audited via journalctl, and it is quietly broken.** Both
   runs since the repo appeared (09-29 03:04, 09-30 03:09) uploaded **3-file sets:
   no git bundle, no HEAD**, manifest line `git_head: none` — while the unit
   description and Makefile promise "snapshot + grafana + git bundle". Two causes,
   both proven:
   - the unit execs the **root-level** `backup-to-s3.sh` (Sep 28, still carrying
     the old `cd $(dirname $0)` bug that climbs out of the repo) while the fixed
     copy lives at `scripts/backup-to-s3.sh` (Sep 29) — the deploy never swapped
     the root-level copy;
   - even with the fixed script, a systemd oneshot gets no PAM env → no `HOME` →
     git's dubious-ownership guard refuses `/root/fleet-monitoring`
     (`env -u HOME git rev-parse` repro'd verbatim), so bundle+HEAD skip silently.
   And `restore-check` prints "no git bundle in this set" and **still exits 0** —
   the guard passes its own missing payload. → **MON-DOGFOOD-009 (P1)**.
5. **The staleness tripwire works.** `BackupFreshnessStale` exists
   (capacity.yml:68, 48h threshold), is loaded in Prometheus, the runbook anchor
   (`docs/runbook.md:54`) exists, and after today's real backup the metric
   `monitoring_backup_last_success_timestamp_seconds` is queryable
   (`job=integrations/unix, host=fleet-monitor`). MON-GAP-010 is done in practice —
   cross-evidence note left on the row.

## Verdict for this surface

🟡 **PROMISING-BUT-ROUGH.** The design is genuinely good (snapshot-not-tar for the
TSDB, spool-not-drop philosophy extended to backups, restore-check as a nightly
self-test, freshness as a metric with a real alert). But the flagship *documented*
command fails on a fully-configured host, and the automation that runs nightly
ships backup sets missing the one artifact (the git bundle) the whole rebuild
runbook depends on — with every guard green. Nothing here is slow: timer run
15s wall, manual backup ~60s, restore-check ~3-15s. No PERF rows.

## Numbers

| Operation | Time | Result |
|---|---|---|
| `make backup` (documented) | 0s | FAIL: S3_BUCKET unset |
| real backup (env sourced) | ~60s | 5-file set, 92M, uploaded |
| `restore-check` on full set | ~15s | PASS, checksums verify |
| nightly timer run (journal) | 15s | 3-file set, bundle+HEAD missing |
| freshness metric → queryable | immediate | value present in /api/v1/query |

## Filed

- MON-DOGFOOD-009 (P1) — timer ships bundle-less sets; HOME/dubious-ownership +
  stale root-level script; restore-check must fail on missing bundle.
- MON-DOGFOOD-010 (P1) — `make backup` env wiring.
- MON-DOGFOOD-011 (P2) — grafana live-db tar fallback; HELP typo ("uploached").
- Cross-evidence notes: MON-GAP-010 (working, closeable), MON-GAP-006.

## Skills this run used and their traps

Approval-gated surfaces: everything on the host went through one-shot ssh with
outputs to `/tmp` logs (no heredocs); the {PIPESTATUS} trap was dodged by running
bare commands. `{q:=...}` walrus syntax inside a python one-liner broke the
rule-scan probe — the fallback grep on `/api/v1/rules` answered instead. Lesson:
on this box, prefer `grep -o` over inline python for quick JSON pokes.

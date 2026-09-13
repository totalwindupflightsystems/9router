# reports-sync — Task Board

Sync lane (prompt-mode, scheduler row `reports-sync`, cooldown 21600s): each
tick runs `~/.hermes/scripts/sync-scheduler-tick.sh` → `dagger-role-tick.sh
duckbrain-sync reports`, which syncs the fleet reports site
(`/home/kara/reports-repo`, S3-backed, HEAD 9824fc6) into DuckBrain namespace
`reports` and verifies the landing. No foreman — this board records findings;
the tick agent reads this file + `skills/reports-sync-usage/SKILL.md`.

Board created 2026-09-13 by dogfood field test (no board existed before —
that itself was DOGFOOD-005).

## Dogfood Findings (2026-09-13)

Verdict: 🔴 DOES-NOT-DELIVER (as of 2026-09-13) — the scheduler-driven path,
which is the only real entry point, writes ZERO keys and is accounted as
success. The underlying pipeline is healthy: one env var makes it go 10/10
green with 5/5 keys verified (proven same day, see DOGFOOD-001).

- [ ] DF-001 (P0) — DEAD REPO VARIABLE in `sync-scheduler-tick.sh`: the script
      resolves `REPO=/home/kara/reports-repo` in its case branch (line 31) but
      never forwards it — it execs `dagger-role-tick.sh duckbrain-sync
      "$SYNC_PROJECT" ""` (line 40), whose own default is
      `SYNC_REPO=${SYNC_REPO:-/home/kara/$PROJECT}` = `/home/kara/reports`
      (missing dir). Every scheduler tick dies at `parse_state`:
      `read_state probe produced no ===REPO=== resolution record … raw probe
      text: "The directory /home/kara/reports is missing."` → 8 of 10 nodes
      skipped, 0/0 keys, pipeline exit 1. Repro: tick `dogfood-1789315645`
      2026-09-13 failed in 21s. Same latent bug hits every case-branch row
      (coding-hermes, gitreins, eduos, ai-plays-poke) — those workdirs exist,
      so only `reports` (whose dir is `reports-repo`) actually breaks.
      Fix (proven 2026-09-13): forward the resolved repo —
      `SYNC_REPO="$REPO" exec bash ~/.hermes/scripts/dagger-role-tick.sh
      duckbrain-sync "$SYNC_PROJECT" ""`. Verified: manual run with
      `SYNC_REPO=/home/kara/reports-repo` → 10 passed / 0 failed, 1m39s,
      5/5 keys verified, `/sync/reports/last-success` advanced
      01:38Z → 16:17Z (window 14.64h).
- [ ] DF-002 (P1) — FALSE GREEN ACCOUNTING: the 07:00:49 scheduler tick
      2026-09-13 (`reports-sync-2026-09-13-12-00-49`) recorded
      `status=completed outcome=committed exit=0 cost=$0.550172` while zero
      keys landed in ns `reports` (grep of all partitions 12:00-13:05Z = 0
      rows) because the in-tick agent "verified" against nothing. Fix: the
      tick contract must treat `pipeline exit != 0` or `0/5 keys` as FAILED —
      cheapest form: after the run, GET
      `/api/memories?namespace=reports&prefix=/sync/reports/last-success`
      and require a timestamp newer than the pre-tick value; report
      OK/FAILED from that comparison, not from session survival.
- [ ] DF-003 (P1) — ALERT FIRES, NOTHING HEARS IT: the pipeline wrote
      `/project/reports/alert/sync-gap` 2026-09-11T16:21Z (window 6.16h >
      2× believed cooldown) and its own status rows since 09-11 say
      "silence is unverified, not confirmed idle" — yet no lane, cron, or
      consumer consumes the alert; sync-gap windows kept growing to 14.6h
      unremarked. Also the alert's `cooldown_s: 2` shows the pipeline read a
      wrong/absent cooldown (real pin: 21600). Fix: alert writes should go to
      a monitored key family (or the tick report should surface them), and
      the pipeline needs the real cooldown passed (same env-forwarding class
      as DF-001).
- [ ] DF-004 (P2) — PLACEHOLDER REPO URL: scheduler/fleet row carries
      `repo_url = https://example.com/reports-sync` (real content:
      `/home/kara/reports-repo`, S3 remotes `s3://kara-reports/...`). Any
      repo-derived tooling (clone legs, install checks, README readers)
      resolves example.com and fails; the dogfood briefing itself was
      confused by it. Fix: set repo_url to the local path or the S3 URL.
- [ ] DF-005 (P2) — EMPTY WORKDIR, ZERO DOCS: workdir
      `~/.hermes/sync-workdirs/reports-sync` had no README, no board, no
      skill pointer — an agent landing there (as this dogfood did) must read
      three scripts to learn what the lane is. Partially fixed by this board
      + `skills/reports-sync-usage/SKILL.md` + `docs/dogfood/`; remaining:
      a two-line README in the workdir pointing at them.
- [ ] DF-006 (P2) — MARKER SPLIT-BRAIN: ns `reports` has three marker
      families — `/sync/last-run` (focused-sync era, last write 08-31, says
      "GitHub Pages DOWN", stale: repo moved to S3), `/sync/reports-last-run`
      (dagger era, stalled 09-09), `/sync/reports/last-success` (current,
      live). A consumer reading the obvious `/sync/last-run` concludes the
      pipeline is dead and the site is down; neither is current truth. Fix:
      write one final tombstone/pointer row into `/sync/last-run` naming
      `/sync/reports/last-success` as canonical, or rename families.
- [ ] DF-007 (P2) — SKIPPED-install-bunker (explicit, per skill law): the
      project has no install path (no Dockerfile/Makefile/install docs); it
      is a scheduler-registered prompt lane whose "install" is the row
      itself. Installability evidence substituted: scheduler row live and
      ticking (last_tick 09-13 07:04), scripts present and executable,
      DuckBrain daemon healthy — and DF-001 proves the deployed invocation
      is broken despite all of that. No bunker agent spawned; no reason to:
      nothing here can be installed on a clean box without the scheduler.
- [ ] DF-008 (P1) — SIBLING WATCH: `ai-plays-poke` ns newest write is
      2026-09-10 (stale 3 days) while other case-branch rows (coding-hermes,
      gitreins, eduos) sync daily — ai-plays-poke-sync should get the same
      landing-verification check as DF-002 before assuming health; its
      scheduler prompt field is EMPTY (command/prompt-mode drift, row shows
      last tick 09-10 outcome=committed).

# reports-sync — Integration Report (2026-09-13 dogfood)

**Verdict:** 🔴 DOES-NOT-DELIVER via the scheduler path (reproduced); 🟢 the
underlying pipeline is SHIPPABLE once one env var is forwarded (proven same
session). The gap between "system runs" and "system delivers" is the whole
story of this project.

## What this thing is

`reports-sync` is **not a code repo** — it is a fleet **sync lane**: a
prompt-mode scheduler row (cooldown 21600s) whose session runs one script
and verifies the result:

```
scheduler tick (every 6h)
  └─ bash ~/.hermes/scripts/sync-scheduler-tick.sh        # in workdir
       ├─ resolves SYNC_PROJECT=reports (row name minus -sync)
       ├─ resolves REPO=/home/kara/reports-repo (case branch)   ← dead var
       └─ exec dagger-role-tick.sh duckbrain-sync reports ""
            ├─ fresh dagger serve (fail-closed DAGGER_API_TOKEN, free port)
            ├─ fresh role.db per run (checkpoints = result evidence)
            └─ runs examples/coding-hermes/duckbrain-sync.ts pipeline:
               read_state → parse_state → read_marker → scan_sources →
               collect_findings → enrich(agent) → build_payloads → report →
               marker → sync_keys(foreach write+verify)
```

Pipeline writes into DuckBrain namespace `reports` (HTTP :3000,
`x-api-key` from `~/.duckbrain/token-*.token`):
- `/project/reports/status/YYYY-MM-DD` (config) — daily tick audit
- `/project/reports/status/YYYY-MM-DD-tickunknown-audit` (event)
- `/sync/write-test-YYYY-MM-DD` (probe)
- `/sync/reports/last-success` (window marker)
- optionally `/findings/reports/*` + `/project/reports/events/*`

Target repo: `/home/kara/reports-repo` (HTML reports + fleet-data JSONs,
git remotes = S3 `s3://kara-reports/current/git/reports-repo`, daily push
cron `2ee8eaa9612c` 03:50; the old GitHub Pages publish cron `006e2702ef3a`
is disabled — Pages died when the repo went private 08-27).

## Real-use run (what a user actually did)

1. **Ran a scheduler-identical tick** (`CODING_HERMES_PROJECT=reports-sync
   CODING_HERMES_TICK=dogfood-… bash sync-scheduler-tick.sh` in the
   workdir). Result: pipeline exit 1 in **21s** — `parse_state` failed:
   `read_state probe produced no ===REPO=== resolution record … "The
   directory /home/kara/reports is missing."` 8/10 nodes skipped, 0/0 keys.
2. **Verified landing as a consumer** (the tick's own contract): zero rows
   in ns `reports` for the morning window; worse, the 07:00 scheduler row
   said `completed / committed / exit=0 / $0.55` — a false green.
3. **Read the scripts when stuck** (that's a docs finding, per skill law):
   the case-branch `REPO` in `sync-scheduler-tick.sh` is never forwarded;
   `dagger-role-tick.sh` defaults `SYNC_REPO=/home/kara/reports` (missing).
4. **Re-ran the documented knob**: `SYNC_REPO=/home/kara/reports-repo
   REAL_MODE=1 dagger-role-tick.sh duckbrain-sync reports` → **10 passed /
   0 failed, 1m39s, 5/5 keys verified**, marker advanced
   01:38Z → 16:17Z (window 14.64h), status row now says
   `repo_source:"env", repo_missing:false`.

## Working example (the right way, until DF-001 is fixed)

```bash
cd ~/.hermes/sync-workdirs/reports-sync
SYNC_REPO=/home/kara/reports-repo REAL_MODE=1 \
  bash ~/.hermes/scripts/dagger-role-tick.sh duckbrain-sync reports ""
# expect: "5/5 keys verified" and "Passed: 10 | Failed: 0"

# consumer verification (independent of the tick's own claim):
KEY=$(tr -d '[:space:]' < ~/.duckbrain/token-*.token)
curl -s -H "x-api-key: $KEY" \
  'http://127.0.0.1:3000/api/memories?namespace=reports&prefix=/sync/reports/last-success&limit=3' \
  | jq -r '.items[].timestamp'    # newest must be ~now
```

## Friction log (the honest list)

| # | Friction | Evidence |
|---|----------|----------|
| 1 | Lane writes zero keys under the scheduler, for days | DF-001/002 |
| 2 | False green: scheduler row says success while ns is silent | DF-002 |
| 3 | `repo_url=example.com` placeholder misleads every reader | DF-004 |
| 4 | Empty workdir: no README/board/skill — had to read 3 scripts | DF-005 |
| 5 | Three generations of marker keys, two stale | DF-006 |
| 6 | Alert key written but never consumed; wrong cooldown in alert attrs | DF-003 |
| 7 | Fix is invisible unless you read bash (no docs mention SYNC_REPO) | this file |

## What held up

- The dagger pipeline itself: fail-closed serve, per-run fresh DB, per-key
  write+verify loop — once it got the right repo, everything worked first
  try, including the window math over a 14.64h gap.
- DuckBrain HTTP surface (`/api/memories?namespace=&prefix=`, tree at
  `/api/keys`) matched the `duckbrain-http-access` skill exactly.
- The scheduler's own health API (`/api/v1/projects`, `.../ticks/latest`)
  gave clean evidence for the fleet-wide blast-radius check.

## If I had 1 hour of the maintainer's time

1. Apply the DF-001 one-liner (`SYNC_REPO="$REPO"` in the exec line).
2. Make the tick verify the landing (DF-002) — without it, every other
   fix is unverifiable forever.

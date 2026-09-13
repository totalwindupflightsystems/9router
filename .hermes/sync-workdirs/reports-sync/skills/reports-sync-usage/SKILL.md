---
name: reports-sync-usage
description: How to run and verify the reports-sync DuckBrain sync lane (ns `reports`) — the working invocation, the consumer verification, and the known failure modes.
version: 1.0.0
category: devops
---

# reports-sync — Usage Skill

## What this is

A **sync lane**, not a code repo. Scheduler row `reports-sync` (prompt-mode,
cooldown 21600s) runs `~/.hermes/scripts/sync-scheduler-tick.sh` each tick;
that execs `dagger-role-tick.sh duckbrain-sync reports`, which runs the
`duckbrain-sync` dagger pipeline (fresh serve + fresh role.db per run) to
mirror `/home/kara/reports-repo` (fleet reports site, S3-backed) into
DuckBrain namespace `reports`.

## Run it for real (the one working invocation)

```bash
cd ~/.hermes/sync-workdirs/reports-sync
SYNC_REPO=/home/kara/reports-repo REAL_MODE=1 \
  bash ~/.hermes/scripts/dagger-role-tick.sh duckbrain-sync reports ""
```

- `SYNC_REPO` is load-bearing. Without it the driver defaults to
  `/home/kara/reports` (missing dir) and the pipeline dies at `parse_state`
  with *"The directory /home/kara/reports is missing"* → 8/10 nodes skipped,
  0 keys. (Board DF-001 tracks the wrapper fix; until it lands, ALWAYS pass
  the env var.)
- `REAL_MODE=1` = actually write to DuckBrain. `REAL_MODE=0` (default) =
  dry-run — fine for a smoke check, writes nothing.
- Good run: `Passed: 10 | Failed: 0` + `5/5 keys verified` in ~2min.
  A run log lives under `/tmp/dagger-role-duckbrain-sync-*/run.log`.

## Verify a tick landed (never trust the run's own verdict)

```bash
KEY=$(tr -d '[:space:]' < ~/.duckbrain/token-*.token)
curl -s -H "x-api-key: $KEY" \
  'http://127.0.0.1:3000/api/memories?namespace=reports&prefix=/sync/reports/last-success&limit=3' \
  | jq -r '.items[] | "\(.timestamp)  \(.content[0:100])"'
# newest timestamp must be ≈ your run time; window hours ≈ gap since prior marker
```

Status rows land at `/project/reports/status/YYYY-MM-DD` (config) + a
`-tickunknown-audit` event twin; the daily probe is
`/sync/write-test-YYYY-MM-DD`. Full DuckBrain HTTP contract (route shapes,
envelope gotchas, fs-grep verification): skill `duckbrain-http-access`.

## Keys you will touch in ns `reports`

| Key | Meaning | Live? |
|---|---|---|
| `/sync/reports/last-success` | window marker (canonical freshness signal) | YES |
| `/project/reports/status/YYYY-MM-DD` | per-run tick audit | YES |
| `/sync/write-test-YYYY-MM-DD` | daily probe | YES |
| `/sync/reports-last-run` | dagger-v1 era marker | STALE (died 09-09) |
| `/sync/last-run` | focused-sync era marker ("Pages 404" era) | STALE (died 08-31) |

Do not "fix" the stale markers by writing them — they're history; the
board (DF-006) tracks the pointer-row cleanup.

## Failure modes seen (with signatures)

1. **`parse_state` fails, "directory /home/kara/reports is missing"** →
   missing `SYNC_REPO`. Not a DuckBrain problem; nothing is broken server-side.
2. **Scheduler row green while ns is silent** → known false-green class
   (DF-002): the scheduler records outcome from session survival, not from
   keys landed. Cross-check the marker timestamp before believing a tick worked.
3. **`sync_keys foreach [null x5]` / marker skipped** → write-path failure
   (DAGGER-165 auth-era class). Triage order: serve.log first line
   (DAGGER_API_TOKEN), then preflight write-test fingerprint in ns, then
   DUCKBRAIN_KEY resolution (host-side in dagger-role-tick.sh).
4. **status rows say "head unknown / no tick events"** → the pipeline
   couldn't read the repo state; check the repo path exists and the run had
   `SYNC_REPO` set.

## Fleet context

- Content repo: `/home/kara/reports-repo` (HTML + `fleet-data-*.json`),
  remotes = S3 (`s3://kara-reports/current/git/reports-repo`), daily push
  cron `2ee8eaa9612c` 03:50 local. GitHub Pages is gone (repo went private
  08-27; publish cron `006e2702ef3a` disabled) — do not debug Pages, it is
  retired.
- Sibling rows sharing the same wrapper case-branch: `coding-hermes-sync`,
  `gitreins-sync`, `eduos-sync`, `ai-plays-poke-sync`. They work only because
  their `/home/kara/<name>` dirs happen to exist. Any new case-branch row
  must pass `SYNC_REPO` explicitly or the row name must match the dir name.

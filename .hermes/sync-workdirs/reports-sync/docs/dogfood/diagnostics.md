# reports-sync — Diagnostic Trail (how it's built, why, what broke, the right way)

*Written 2026-09-13 by a dogfood run. This is the "explain the thing" record:
how the sync is built, the errors hit along the way (ours and history's), and
the verified-correct usage. Board: `.coding-hermes/tasks.md`.*

## 1. Architecture and why it looks like this

The fleet needed every project's state mirrored into DuckBrain (memory bank)
so "ask the memory" works fleet-wide. Rather than one god-cron, the
duckbrain-sync DAGGER-136 cutover (2026-09-01) gave **each namespace its own
scheduler row** (`<project>-sync`), 48 rows today. All rows share two
scripts:

- `~/.hermes/scripts/sync-scheduler-tick.sh` — thin per-row wrapper:
  derives `SYNC_PROJECT` from the row name, resolves the repo (scheduler DB
  lookup, then a case branch for names ≠ paths), execs the role tick.
- `~/.hermes/scripts/dagger-role-tick.sh` — generic pipeline driver: fresh
  `dagger serve` per run (fail-closed auth token, random free port), fresh
  `role.db`, runs `examples/coding-hermes/duckbrain-sync.ts`, prints a
  human card from the DB checkpoints.

Why a fresh serve+DB per run: syncs are throwaway jobs; the DB checkpoints
are the run's evidence ("3-way chain": write_result id = read-back id = disk
row), and a crashed run leaves no state to clean up. Why the pipeline has a
verify node per key: the historical failure mode of this fleet is writes
that return 201 but never land (wrong namespace, tombstone, chunk rotation) —
the `5/5 keys verified` line is the entire point of the design.

## 2. History of errors (why the code is defensive)

Evidence lives in DuckBrain ns `reports` and scheduler tick rows:

- **Aug era:** a separate focused-sync cron wrote `/sync/last-run` markers;
  its last entries (08-28→08-31) read "GitHub Pages FULLY 404 (down since
  repo private Aug 27)" — the reports site lost its publish path when the
  repo went private; the S3 push cron (`2ee8eaa9612c`, daily 03:50) is the
  current publish path and the Pages cron (`006e2702ef3a`) is disabled.
- **09-01 cutover:** keys moved to the dagger pipeline
  (`/sync/reports-last-run` markers, "N keys written (pre-verify count)").
  The LLM-mediated key lookup historically corrupted the API key (embedded
  newline → 3-of-6 fleet 401s) — that's why `DUCKBRAIN_KEY` is now resolved
  host-side in `dagger-role-tick.sh` and passed through the Go env bridge
  byte-exact (comment block, DAGGER-165 class evidence).
- **09-12 19:11 tick:** a full write-path failure (auth-era triage class 3 /
  DAGGER-165): `sync_keys foreach [null x5]`, marker skipped — recorded as
  `/project/reports/events/2026-09-12-tick-1911-sync-write-path-failed`
  with a health split proving DuckBrain itself was healthy (fingerprinted
  preflight write-test landed and read back).
- **09-11→09-13:** every status row says "head unknown / no tick events" and
  an `/project/reports/alert/sync-gap` fired (window > 2× cooldown) — nobody
  consumes it (DF-003), windows grew to 14.64h.
- **09-13 (this dogfood):** root cause of the whole quiet era found: the
  dead `REPO` variable (DF-001). Not new code rot — a latent bug since the
  case branch was written; `reports` is the only row whose repo dir doesn't
  match the default `/home/kara/<project>` pattern.

## 3. Today's two runs, side by side

| | Scheduler-identical tick | SYNC_REPO-forwarded tick |
|---|---|---|
| Command | `sync-scheduler-tick.sh` | `SYNC_REPO=/home/kara/reports-repo dagger-role-tick.sh duckbrain-sync reports` |
| Time to verdict | 21s | 1m39s |
| Nodes | 2 ran, 8 skipped | 10/10 passed |
| Keys written | 0/0 | 5/5 verified |
| Marker | unchanged (01:38Z) | advanced to 16:17:41Z |
| Cost | $0.55 (scheduler row, billed) | ~$0.1 (cheap tool model) |

The exact error that starts the cascade:
```
duckbrain-sync: read_state probe produced no ===REPO=== resolution record
(the tool refused the command before bash ran, or the probe envelope failed)
— repo state is UNKNOWN, refusing to attribute unverified facts; raw probe
text: "The directory /home/kara/reports is missing."
```
Note the design working as intended: the pipeline *refuses to write
unverified facts* — it just had no path to succeed, and the scheduler
accounted the failure as success anyway (DF-002 is the systemic half).

## 4. The right way (verified 2026-09-13)

```bash
cd ~/.hermes/sync-workdirs/reports-sync
SYNC_REPO=/home/kara/reports-repo REAL_MODE=1 \
  bash ~/.hermes/scripts/dagger-role-tick.sh duckbrain-sync reports ""

# consumer check — never trust the run's own verdict alone:
KEY=$(tr -d '[:space:]' < ~/.duckbrain/token-*.token)
curl -s -H "x-api-key: $KEY" \
  'http://127.0.0.1:3000/api/memories?namespace=reports&prefix=/sync/reports/last-success&limit=3' \
  | jq -r '.items[] | "\(.timestamp)  \(.content[0:80])"'
```

Conventions to respect when writing to ns `reports`:
- HTTP routes live under `/api/*` (NOT `/api/v1/*`); auth header is
  `x-api-key`; write body needs `key` (leading `/`), `domain` (enum:
  person/event/concept/message/config/raw_note), `content` (non-empty).
- GET `/api/memories` returns `{items:[...]}`; ordering is NOT newest-first —
  filter/sort by the record's own `timestamp` client-side.
- On-disk rows store the body in `embedding_text`, not `content`.
- Marker keys: canonical = `/sync/reports/last-success`. `/sync/last-run`
  (focused-sync era) and `/sync/reports-last-run` (dagger v1 era) are stale
  history, not current truth.
- Full API pitfall catalog: `~/.hermes/skills/devops/duckbrain-http-access/SKILL.md`.

## 5. Open questions for the owner

- The workdir pair (`reports-sync` row ↔ `reports-repo` content repo) has
  three names for one thing (`reports`, `reports-repo`, `reports-sync`) —
  the case branch was the patch over that mismatch and it leaks (DF-001).
  Passing `SYNC_REPO` explicitly in the row (scheduler `command` mode or a
  prompt tweak) would remove the fragile name-derivation entirely.
- Who should read `/project/reports/alert/sync-gap`? An alert nobody
  consumes is a log line (DF-003).

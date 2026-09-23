---
name: lore-sync-data
description: "DATA SKILL (internal): DuckBrain sync data for lore. Load with context-sync-duckbrain."
category: data
---
# lore — DuckBrain Sync Data

> **INTERNAL DATA SKILL** — project-specific data for the `context-sync-duckbrain` lane. Loaded
> on demand by the CORE skill when this namespace is in the scan window.

## Project annotation

**lore (ns `lore`):** the runbook compiler — "how did we fix this last time, and does it still work?" Compiles fleet incidents into living runbooks with a weekly read-only re-validation lint.

Part of the **agent-ops line** (get-h3): four tools that turn a fleet's operational exhaust into
queryable, provable truth. Repo: `get-h3/lore` (private at kickoff, MIT). Workdir: `~/lore`.
Local git default branch: `main`. Kicked off as a fleet project 2026-09-23.

## Canonical reference files

- `~/lore/README.md` — the question it answers, the hook, the line
- `~/lore/docs/PRD.md` — the full PRD (B-series), including the acceptance replays
- `~/lore/.coding-hermes/board/tasks.jsonl` — JSONL-canonical board (LORE-00N rows)

## Key project facts

- **Task IDs:** `LORE-00N`.
- **The acceptance replay it is judged against:** the gateway drain-window runbook, compiled ONLY from the 2026-09-16 trail, contains the correct checks and >=90% of commands that still run; and `lore audit` produces an honest coverage matrix over the last 90 days with gaps NAMED.
- **Proposals, never writes:** nothing auto-writes doctrine. Compile proposes, an operator approves (the fleet's board-review model).
- **Honesty label:** the lint proves commands parse and answer — NOT that recovery succeeds.
- **Fleet lanes:** primary `lore` (namespace `coding-hermes`, tasks-mode) plus the standard
  satellites — `lore-qa` (qa), `lore-dogfood` (dogfood), `lore-pm` (pm), `lore-releng` (releases),
  `lore-sync` (duckbrain-sync). The satellites read the primary's board through a symlinked
  `.coding-hermes/board` directory.

## What to sync into this namespace

- Board-row lifecycle for this project (filed / closed / blocked) from
  `~/lore/.coding-hermes/board/tasks.jsonl` and `events.jsonl`
- Git activity: commits, tags, unpushed state on `~/lore` (HEAD, branch, dirty tree)
- Scheduler state: this project's lane rows and their ticks (status, outcome, commits)
- Acceptance-replay results when a row carrying one closes

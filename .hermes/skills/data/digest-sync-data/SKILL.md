---
name: digest-sync-data
description: "DATA SKILL (internal): DuckBrain sync data for digest. Load with context-sync-duckbrain."
category: data
---
# digest — DuckBrain Sync Data

> **INTERNAL DATA SKILL** — project-specific data for the `context-sync-duckbrain` lane. Loaded
> on demand by the CORE skill when this namespace is in the scan window.

## Project annotation

**digest (ns `digest`):** the fleet digest builder — "what needs me today?" One artifact from ten boards: six sections (delivered, stuck, quality, money, needs-human, watch), honesty-labeled, phone-readable.

Part of the **agent-ops line** (get-h3): four tools that turn a fleet's operational exhaust into
queryable, provable truth. Repo: `get-h3/digest` (private at kickoff, MIT). Workdir: `~/digest`.
Local git default branch: `main`. Kicked off as a fleet project 2026-09-23.

## Canonical reference files

- `~/digest/README.md` — the question it answers, the hook, the line
- `~/digest/docs/PRD.md` — the full PRD (B-series), including the acceptance replays
- `~/digest/.coding-hermes/board/tasks.jsonl` — JSONL-canonical board (DIGEST-00N rows)

## Key project facts

- **Task IDs:** `DIGEST-00N`.
- **The acceptance replay it is judged against:** `digest build --project coding-hermes-scheduler --window 90d` reproduces the SUBSTANCE of the hand-built 2026-09-16 quorum report (spend by tier, cost_source honesty, zero-output counts) without hand labor.
- **Bane directive 2026-09-17:** digests persist in DuckBrain — date-addressable, S3-backed, recoverable (ns `digest`, `/project/<family>/digest/<YYYY-MM-DD>`).
- **Renderer-enforced honesty:** a cost figure cannot be emitted without its `cost_source`; absent sources render "no data", never zero.
- **Fleet lanes:** primary `digest` (namespace `coding-hermes`, tasks-mode) plus the standard
  satellites — `digest-qa` (qa), `digest-dogfood` (dogfood), `digest-pm` (pm), `digest-releng` (releases),
  `digest-sync` (duckbrain-sync). The satellites read the primary's board through a symlinked
  `.coding-hermes/board` directory.

## What to sync into this namespace

- Board-row lifecycle for this project (filed / closed / blocked) from
  `~/digest/.coding-hermes/board/tasks.jsonl` and `events.jsonl`
- Git activity: commits, tags, unpushed state on `~/digest` (HEAD, branch, dirty tree)
- Scheduler state: this project's lane rows and their ticks (status, outcome, commits)
- Acceptance-replay results when a row carrying one closes

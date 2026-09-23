---
name: logsey-sync-data
description: "DATA SKILL (internal): DuckBrain sync data for logsey. Load with context-sync-duckbrain."
category: data
---
# logsey — DuckBrain Sync Data

> **INTERNAL DATA SKILL** — project-specific data for the `context-sync-duckbrain` lane. Loaded
> on demand by the CORE skill when this namespace is in the scan window.

## Project annotation

**logsey (ns `logsey`):** the log-corpus indexer — "what happened on this box?" in one query instead of six greps. Indexes journald units and app logs into a DuckDB corpus with materialized views (`v_http_status`, `v_sessions`, `v_errors`) and message-class normalization, so grouped counting is actually useful.

Part of the **agent-ops line** (get-h3): four tools that turn a fleet's operational exhaust into
queryable, provable truth. Repo: `get-h3/logsey` (private at kickoff, MIT). Workdir: `~/logsey`.
Local git default branch: `main`. Kicked off as a fleet project 2026-09-23.

## Canonical reference files

- `~/logsey/README.md` — the question it answers, the hook, the line
- `~/logsey/docs/PRD.md` — the full PRD (B-series), including the acceptance replays
- `~/logsey/.coding-hermes/board/tasks.jsonl` — JSONL-canonical board (LOGSEY-00N rows)

## Key project facts

- **Task IDs:** `LOGSEY-00N`.
- **The acceptance replay it is judged against:** the 1,813x503 hour (2026-09-16: the gateway shed 1,813 worker requests in one hour, diagnosed historically by six hand-rolled greps and two false leads) completes as ONE query returning <10 rows in <5s.
- **Privacy by default:** redaction runs AT INDEX TIME (key-shaped strings: `sk-`, `AKIA`, `user_` prefixes + the gitleaks pattern set) so the corpus never becomes a new leak surface. A redaction gap is a P0.
- **The corpus is a rebuildable cache** — raw logs stay source of truth; never archive raw logs away.
- **Fleet lanes:** primary `logsey` (namespace `coding-hermes`, tasks-mode) plus the standard
  satellites — `logsey-qa` (qa), `logsey-dogfood` (dogfood), `logsey-pm` (pm), `logsey-releng` (releases),
  `logsey-sync` (duckbrain-sync). The satellites read the primary's board through a symlinked
  `.coding-hermes/board` directory.

## What to sync into this namespace

- Board-row lifecycle for this project (filed / closed / blocked) from
  `~/logsey/.coding-hermes/board/tasks.jsonl` and `events.jsonl`
- Git activity: commits, tags, unpushed state on `~/logsey` (HEAD, branch, dirty tree)
- Scheduler state: this project's lane rows and their ticks (status, outcome, commits)
- Acceptance-replay results when a row carrying one closes

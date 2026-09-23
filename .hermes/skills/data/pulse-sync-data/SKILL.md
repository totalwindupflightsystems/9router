---
name: pulse-sync-data
description: "DATA SKILL (internal): DuckBrain sync data for pulse. Load with context-sync-duckbrain."
category: data
---
# pulse — DuckBrain Sync Data

> **INTERNAL DATA SKILL** — project-specific data for the `context-sync-duckbrain` lane. Loaded
> on demand by the CORE skill when this namespace is in the scan window.

## Project annotation

**pulse (ns `pulse`):** the metric-log correlator — "what was the machine doing when it failed?" A budget-bounded per-box sampler (<=1% of one core, <=50 MB RSS, <=100 MB/day) writing one timestamped JSON line per sample.

Part of the **agent-ops line** (get-h3): four tools that turn a fleet's operational exhaust into
queryable, provable truth. Repo: `get-h3/pulse` (private at kickoff, MIT). Workdir: `~/pulse`.
Local git default branch: `main`. Kicked off as a fleet project 2026-09-23.

## Canonical reference files

- `~/pulse/README.md` — the question it answers, the hook, the line
- `~/pulse/docs/PRD.md` — the full PRD (B-series), including the acceptance replays
- `~/pulse/.coding-hermes/board/tasks.jsonl` — JSONL-canonical board (PULSE-00N rows)

## Key project facts

- **Task IDs:** `PULSE-00N`.
- **The acceptance replay it is judged against:** the 2026-09-10 four-corruption day (11:48, 12:53, 13:54, 14:52) lines up disk>95% windows with all four incidents in ONE report, and the GAP-125 load-gate threshold decision is rebuilt from a 30-day saturation curve.
- **No query layer of its own:** daily JSONL files are written logsey-source-compatible; correlation happens in DuckDB where logsey already indexes logs. Deliberate.
- **Fleet lanes:** primary `pulse` (namespace `coding-hermes`, tasks-mode) plus the standard
  satellites — `pulse-qa` (qa), `pulse-dogfood` (dogfood), `pulse-pm` (pm), `pulse-releng` (releases),
  `pulse-sync` (duckbrain-sync). The satellites read the primary's board through a symlinked
  `.coding-hermes/board` directory.

## What to sync into this namespace

- Board-row lifecycle for this project (filed / closed / blocked) from
  `~/pulse/.coding-hermes/board/tasks.jsonl` and `events.jsonl`
- Git activity: commits, tags, unpushed state on `~/pulse` (HEAD, branch, dirty tree)
- Scheduler state: this project's lane rows and their ticks (status, outcome, commits)
- Acceptance-replay results when a row carrying one closes

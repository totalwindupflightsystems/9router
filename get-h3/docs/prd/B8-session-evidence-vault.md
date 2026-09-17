# PRD: `h3-evidence` — Session Evidence Vault & Agent Scoreboard

**Project:** get-h3 · agent-ops line · **Item:** B8 (added) · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed · **Effort:** M–L (~3 weeks) · **Depends on:** B1 (logsey) for session-log mining · **Feeds:** B3 lore (absorb source), B4 digest (scoreboard section)

---

## The one-liner

A per-session, per-agent evidence store that captures **what each agent actually did** — tool calls, outputs produced, artifacts landed, claims vs receipts — and turns it into the scoreboard every fleet needs but nobody builds: **which agents, models, and lanes actually ship verified work.**

## The problem, measured

**Case file 1 — the outcome lie (quorum finding, 09-16):** the scheduler's tick records stamped `outcome='committed'` on **1,701 zero-output ticks per week** — agents that claimed completion with nothing on disk to show. The fleet had no mechanical way to separate "says done" from "evidences done." The quorum only caught it because someone hand-joined two data stores.

**Case file 2 — the verification gap in workers:** the fleet's own ops doctrine records worker sessions that produced identical tool calls in a loop (288 identical calls observed in `state.db`), or committed test-file-only changes against fix-claims. Each was caught by hand, after the fact, by a human reading raw logs.

**Case file 3 — the model-value question:** "is lane X actually better than lane Y for foreman work?" is unanswerable today — session costs live in one store, outcomes in another, tool-call quality nowhere. The value quorum needed a week of hand-built joins to say "valuable but reckless." Fleets without a quorum culture just… keep paying.

The raw material already exists — every session's tool calls and outputs flow through the harness. What's missing is the **evidence-shaped capture** and the joins.

## User stories

**US-1 (the evidence hook):** As a harness developer, I register an evidence sink (`evidence attach --harness hermes --stream tool-calls`) and every session gets a structured vault record: calls made, outputs' hashes, files written, commits landed, tests run — append-only, tamper-evident, redacted at write time.

**US-2 (the scoreboard reader):** As Bane deciding where to spend, I run `evidence score --window 30d --by model` and see per-model/per-lane: verified-ship rate (commits whose claims match artifacts), evidence-coverage (sessions with complete receipts), claim-vs-receipt delta, cost per *verified* outcome — the quorum report as a standing query.

**US-3 (the loop-catcher):** As the fleet's quality gate, `evidence watch --rule 'identical_calls > 50'` or `'claimed_files_absent'` flags degenerate sessions *while they run* — the 288-identical-calls spin becomes a 10-minute-old alert, not a post-mortem finding.

**US-4 (the audit reply):** As the operator asked "prove lane X earned its cost this month," `evidence report --lane xkiro --window 30d` emits the evidence-linked answer: sessions, verified landings, cost per verified outcome, failure classes — one artifact, every number drillable (grain doctrine).

## What it captures (per session)

| Layer | Content |
|---|---|
| identity | session id, agent/foreman, model, provider lane, harness |
| calls | tool name, args hash (args redacted), duration, outcome |
| products | files written (hashes), commits (sha + verified-tree match), tests run (verdicts), messages sent (delivery receipts) |
| claims | board-row flips, `outcome` stamps, completion messages |
| joins | cost rows (from state surfaces), guard results, verify verdicts |

**Design rules:**
- **Claims and receipts live in the same row-shape** so `claims minus receipts` is a query, not an investigation — the 1,701-lie becomes `SELECT sessions WHERE claimed_committed AND artifacts_empty`.
- **Write-time redaction** (gitleaks pattern set) — an evidence vault must never become a leak surface (B1's rule, inherited).
- **Tamper-evidence:** hash-chained appends; the vault can be wrong about the world but provably about itself.
- **Honesty labels all the way down:** absent capture renders "not captured," never zero — partial harness coverage is visible, not smoothed over.

## Interface

```
evidence attach --harness <name> [--stream tool-calls|commits|all]
evidence score --by model|lane|agent [--window 30d] [--format table|json|html]
evidence report --session <id> | --lane <lane> --window ...
evidence watch --rule <expr> [--notify tg:...]
evidence doctor                     # capture coverage per harness/source
```

## Success criteria

1. **Quorum replay:** `evidence score --by lane --window 90d` reproduces the scheduler quorum's headline findings (verified-vs-claimed gap, cost per verified outcome) as a standing query — the week of hand-joins becomes one command.
2. **Spin detection:** a deliberately injected degenerate session (looped identical calls) alerts via `watch` within 10 minutes.
3. Capture coverage ≥95% of fleet session starts within two weeks on this box (`doctor` reports honestly).
4. Scoreboard adoption: the weekly lane/model spending review consumes `evidence score` output as its primary artifact (digest B4 cites it).

## Why get-h3 / why open

Agent frameworks show you *what agents said*; none show you **what agents proved**. The claims-vs-receipts join, the verified-ship scoreboard, and the live degeneracy watch are novel, buildable purely from harness streams, and instantly valuable to any fleet paying real money per session. This is the capstone of the agent-ops line: logsey proves the *box*, pulse proves the *moment*, forge proves the *lanes*, lore proves the *lessons* — evidence proves the *work*.

## Risks

- Capture overhead on hot paths → async appends, bounded queue, drop-oldest with a visible gap counter (never block a session for bookkeeping).
- Privacy/redaction at scale → redact-at-write with the guardian's pattern set; vaults get the same secret-scan audits as any output.
- Metric gaming (agents optimizing the scoreboard) → score *verified outcomes*, not activity volume; the verify-harness honesty law is the anti-gaming mechanism — you can't farm receipts that require real tests to pass.

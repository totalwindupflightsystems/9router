# PRD: `h3-digest` — Fleet Digest Builder

**Project:** get-h3 · agent-ops line · **Item:** B4 · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed · **Effort:** S–M (~1 week) · **Depends on:** nothing (boards/logs via files; logsey/pulse enrich when present) · **Feeds:** humans who read one thing a day

---

## The one-liner

A scheduled roll-up of board rows, tick evidence, guard results, and cost meters into **one digest artifact per project/thread** — HTML for the phone, Markdown for the repo — so humans read one page a day instead of grepping ten boards.

## The problem, measured

**The fleet runs on boards, and boards are firehoses.** Today's inventory on this box alone: ~256 scheduler projects, 64 enabled, each with its own `.coding-hermes/board/` JSONL; qa-cron findings; DuckBrain namespaces per repo; guard logs per commit; cost meters split across `state.db` surfaces with a documented "cost_source on 9 rows of 70k" honesty problem. The verdict from the scheduler value quorum took a **hand-built HTML report** (`scheduler-value-quorum-2026-09-16.html`) to make legible — and that report was built *once, by hand, during an incident of attention*. Nobody rebuilds that daily by hand.

The daily cost is real and observed: **Bane reads Telegram and wants one artifact per thread** (his delivery doctrine: ONE HTML artifact with TOC, grain over styling); agents burn context re-summarizing board state at every session start; incidents get noticed late because the signal is spread across ten surfaces and the operator checks the loudest one.

## User stories

**US-1 (the operator's morning):** As Bane with coffee, I get one HTML digest per project-family in my Telegram: what landed (with narrator-grade evidence links), what's stuck and since when, what failed validation, what it cost, and the three rows that need me — TOC'd, grain-first, no styling padding.

**US-2 (the agent's session start):** As a foreman starting a tick, I read the digest instead of replaying board scans: my predecessor's outcomes, the open rows I inherit, the cooldown/pause state — one file read replaces a dozen probes.

**US-3 (the auditor):** As Bane asking "is this lane burning money for nothing?", the digest's cost section carries sticker-vs-metered spend per lane *with the cost_source honesty label* — the quorum report's discipline, produced on schedule instead of on demand.

**US-4 (the incident reviewer):** As whoever reconstructs a bad week, `digest --window 7d --project X` regenerates the trail: row flips with timestamps, guard failures, stall events, delivery receipts — the same view the operator saw, day by day.

## What it compiles (per digest)

| Section | Content | Source |
|---|---|---|
| **Landed** | rows → complete, with evidence links (commit, verify verdict, narrator block when present) | board JSONL + events |
| **Stuck** | rows pending >SLA, with last-event age and owner signal | boards + cooldown state |
| **Quality** | guard results, in-guard failures, outcome-lies (rows claiming complete with zero-output evidence) | gitreins logs, tick evidence |
| **Money** | spend by lane/project, sticker vs metered, `cost_source` honesty labels | state.db / scheduler API |
| **Needs-human** | the three rows a human must rule on (approvals, conflicts, budget) | priority + age heuristics |
| **Ops** (when logsey/pulse present) | error-class top-N from the window, saturation one-liner | B1/B2 views |

**Design rules:**
- **Delivery-native:** emits to Telegram (ONE artifact, TOC, dark-theme phone HTML — the delivered style Bane has already approved), Markdown to the repo for history, raw JSON for agents. The Telegram artifact *is* the product; a digest nobody opens is a failed digest.
- **Grain over styling:** every number links to its row of origin; no summary without a drill-down (the Observatory law: density, publish real numbers even when bad).
- **Honesty labels inherit:** cost figures carry `cost_source`; missing data renders as "no data," never as zero.
- **Schedule + on-demand:** cron per project-family + `digest build --project X --window 24h` for the ad-hoc ask.

## Interface

```
digest build --project <name|family> [--window 24h] [--format html|md|json]
digest schedule --project <family> --cron '17 6 * * *' --deliver tg:<chat:topic>
digest diff --window 7d          # what changed vs the prior window's digest
```

## Success criteria

1. **The quorum test:** `digest build --project coding-hermes-scheduler --window 90d` reproduces the substance of the hand-built 09-16 quorum report (spend by tier, cost-source honesty, zero-output counts) without hand labor.
2. Adoption proof: operator opens ≤1 artifact/day for the whole fleet and can act on "needs-human" items without opening a board for ≥80% of them.
3. Agent session-start probe reduction: foreman orientation drops from N board/log scans to 1 digest read (measured via tool-call counts before/after on a pilot project).
4. Honesty preservation: 100% of cost figures carry source labels; absent sources render as "no data" (audited by construction — the renderer cannot emit an unlabeled number).

## Why get-h3 / why open

Multi-agent setups drown in board noise — every framework grows ten dashboards and no narrative. The differentiator is the **evidence-first compilation grammar**: evidence-linked landings, honesty-labeled costs, needs-human triage. Anyone can template HTML; the fleet discipline baked into *what gets included and how it's labeled* is the shipped intelligence. It is also the on-ramp that makes the rest of the agent-ops line visible: digest cites logsey/pulse/lore artifacts, so the line sells itself one morning at a time.

## Risks

- Digest spam → per-family scheduling, dedup windows, and a hard "three needs-human items" triage cap; digests compete for attention and must win it or shrink.
- Board-schema drift across repos → tolerant reader (the fleet's boards already vary; legacy pretty-printed boards are valid), per-project adapters with `digest doctor` reporting parse health.
- Cost-data honesty traps → renderer-enforced labels only; if the source can't say where a number came from, the digest says "unknown provenance" — loudly.

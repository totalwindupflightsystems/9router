# PRD (deep): `h3-evidence` — Session Evidence Vault & the Improvement Loop

**Project:** get-h3 · agent-ops line · **Item:** B8 · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed (v2 — value-extraction focus, per Bane's question) · **Effort:** M–L (~3 weeks) · **Relates to:** rabbit-hole (sibling project — see §5)

---

## The question, taken seriously

> *"How are we going to use that data to make improvements to the system?"*

Capture is not value. **Value = a decision that changed, with a measurable delta.** Observability dies at exactly one place: the data exists, dashboards render, and nobody changes what they do. So this PRD is organized backwards from the decisions — every score below names its **decision consumer, cadence, artifact, and the metric that must move**. Anything that can't name those gets retired (the sunset rule, §6).

---

## 1. What the data actually is (one paragraph)

Per session: identity (agent, model, lane, harness), **tool calls** (name, args hash, duration, outcome), **products** (files written w/ hashes, commits w/ verified-tree match, tests run w/ verdicts, messages sent w/ delivery receipts), **claims** (board flips, `outcome` stamps, completion messages), and **cost rows** joined from the state surfaces. Claims and receipts share one row-shape, so `claims − receipts` is a query:

```sql
-- the 1,701-lie, as a standing query
SELECT lane, count(*) FROM sessions
WHERE claimed_committed AND artifacts_empty GROUP BY lane;
```

## 2. The improvement loops (this is the answer)

Each loop: **data → query → decision surface → owner → cadence → metric that must move.**

### Loop A — Provider & lane portfolio *(weekly)*
**Data:** verified-ship rate, cost per *verified* outcome, retry/degenerate rate per lane/model.
**Query:** `evidence score --by lane --window 30d` → {verified_ship_rate, usd_per_verified_outcome, claim_receipt_delta, degenerate_rate}.
**Decision:** which lanes serve which capability, plan amortization (the "30× usage plan" normalization), and **retirement** of lanes that cost more per verified outcome than their replacement.
**Metric that moves:** usd per verified outcome, down; verified-ship share of the cheap lane, up. *Anatomy: this is the 09-16 quorum (sticker 131× cash, "valuable but reckless") turned into a standing, weekly decision instead of a one-off investigation.*

### Loop B — Harness & tool craftsmanship *(per failure fingerprint)*
**Data:** tool-call failure classes, loops (N identical calls), wasted-call ratios, edit-verify cycles per landed change.
**Query:** `evidence fingerprints --top 20 --window 7d` → ranked causes of wasted work.
**Decision:** which coding-hermes tool fix to build next — and it files itself: a fingerprint becomes a CHT board row automatically (the 288-identical-calls spin would have filed "loop-breaker guard" on day one instead of surfacing in a post-mortem).
**Metric that moves:** wasted calls per landed change, down. *This loop is how the tool suite evolves from evidence instead of intuition.*

### Loop C — Scheduler policy *(per tuning window)*
**Data:** per-project tick outcomes joined to cost and to verified landings; stall events; zero-output ticks.
**Query:** `evidence score --by project --window 30d` + scheduler API state.
**Decision:** cooldown/weight/budget changes, load-gate thresholds, auto-disable thresholds — each justified by data rather than anecdote (the GAP-125 gate got armed at 12 on vibes; this loop makes the next such call measured).
**Metric that moves:** verified landings per scheduled hour, up; zero-output tick rate, down.

### Loop D — Guard & quality-gate calibration *(monthly)*
**Data:** which guard failures preceded *real* breaks vs which merely added latency (join guard failures to post-merge incident/rollback evidence).
**Decision:** retire or soften guards that never earned their latency; strengthen the ones that caught real breaks; adjust the diff-mode skip policy (the data-only-commit friction is a live example).
**Metric that moves:** guard-caught-real-breaks per guard-minute.

### Loop E — Skill, prompt & brief efficacy *(monthly)*
**Data:** outcome deltas by skill/brief/AGENTS.md version — sessions running procedure X vs not, controlling for project and lane.
**Decision:** which instructions earn their tokens; which skills get rewritten or deleted. (jnsq quality law says depth+boundaries+tests; now you can *measure* whether a skill revision improved outcomes.)
**Metric that moves:** verified-ship rate per token of instruction.

### Loop F — Spend portfolio *(monthly)*
**Data:** metered vs sticker spend (the re-stamping problem), misroute signatures (ledger rows for models the provider never served), plan-vs-PAYG crossover per workload.
**Decision:** which subscriptions renew, which plans to stack, where PAYG is genuinely cheaper.
**Metric that moves:** effective $ per verified outcome per lane class; unaccounted-spend %, down.

### Loop G — Incident → guard/runbook conversion *(event-driven)*
**Data:** incident trails + the failure classes that recurred.
**Decision:** which guard/pin/runbook to write (feeds lore B3 and sentinel B5); "recurrence is a design smell with an exit".
**Metric that moves:** repeat-incident rate per class.

### Loop H — Experiment (A/B) discipline *(on demand)*
**Data:** before/after verified-ship and cost for a deliberate change (model swap, prompt change, tool change).
**Decision:** keep or revert, with a number instead of a feeling — the fleet's "dry-run before real, read logs not prompts" doctrine applied to its own configuration.
**Metric that moves:** decision quality (reverted-change rate, down).

### The joining layer
One **scoreboard artifact per cadence** (weekly lanes; monthly spend/skills/guards; per-event fingerprints) that digest (B4) carries to humans and that machines read to auto-file board rows. Both consume the same rollup — no parallel reporting.

## 3. The scoring model (what "good" means, and the anti-gaming rules)

| Score | Definition | Games it must resist |
|---|---|---|
| verified-ship rate | landed changes with receipts ÷ attempted | inflating attempts, or farming trivial "verified" landings |
| cost per verified outcome | metered cost ÷ verified landings | shifting work to unmetered paths; *meter is authoritative, not the agent's report* |
| evidence coverage | sessions with complete receipts ÷ sessions | claiming capture that doesn't exist → **absent = "not captured", never zero** |
| claim−receipt delta | claimed completions minus artifacts | the literal 1,701-lie detector |
| degenerate rate | loops/identical-call sessions ÷ sessions | hiding retries by re-badging sessions |
| escalation precision | true incidents ÷ alarms | alarm inflation → the demote-don't-tolerate rule |

**Two structural anti-gaming guarantees:** (1) receipts require real artifacts/tests — you cannot farm a receipt that requires a passing test (the verify-harness honesty law, reused); (2) scores are computed from store-side joins (commits, files, meters), never from agent self-reports alone.

## 4. The honest trap, and the rule that kills it

**Trap:** measurement culture. Nice dashboards, no behavior change, real cost. Every fleet that ever adopted "observability" has died here.
**Rule — the sunset clause:** every score names its decision consumer at creation. **A score that hasn't driven a decision in 90 days gets retired, loudly** (the retirement appears in the digest as a small notice). The scoreboard's own relevance is measured — this is the accuracy loop's discipline applied to the analytics layer itself.

## 5. rabbit-hole — the sibling, and what we reuse

**What rabbit-hole is** (paused, `~/rabbit-hole`, Go, 6 axiom specs, DB at `~/.rabbit-hole/rabbit-hole.db`): a *legibility* layer — COLLECT (eBPF/strace, zero-SDK, works on closed-source agents) → CLASSIFY (deterministic patterns + pluggable ML) → EXPRESS (chat: *"What did helios do at 3am?"*, context-window retrieval).

**The overlap is real and reusable:**
- **Session model** (attach/detach, persisted, survives invocations) → the vault adopts the same lifecycle shape.
- **Classification tiering** (fast deterministic patterns first, ML for the tail) → the vault's behavior fingerprints follow it.
- **Storage data model** (spec S05) → a validated design we don't redo.
- **Express layer** (natural-language questions over sessions) → the vault's *query surface for humans*; instead of building a new chat UI, rabbit-hole's expression layer could read the vault's rows.

**The division of labor (this is the important part):**

| | rabbit-hole | evidence vault |
|---|---|---|
| Question | **What did the agent DO?** | **What did the agent PROVE — and what did it cost?** |
| Altitude | kernel/syscall, agent-agnostic, zero-SDK | harness-level: artifacts, commits, tests, receipts, meters |
| Output | behavioral narrative, classification, chat | verified outcomes, cost-per-outcome, scoreboard |
| Fails at | rich *semantics* without an outcome model (a beautiful trail that can't tell you if the work was real) | behavior detail below the harness (why a call was slow, what the process did) |

**Together they answer the questions neither can alone:** *"Which lane burns the most time on retries, what did that cost, and which tool fix removes it?"* — rabbit-hole supplies the behavior, the vault supplies the outcome and the price, and Loop B is where the answer becomes a board row.

**Recommendation:** keep rabbit-hole paused *as a product*, but harvest its specs as the vault's design input now (S05 storage, session lifecycle, classification tiering) — and treat "revive rabbit-hole as the vault's expression layer" as a *separate* decision to make once the vault's rollups exist. Do not build two collectors; the vault consumes harness streams, rabbit-hole consumes kernel streams, and they meet at the join.

## 6. What we deliberately do NOT do

- No per-keystroke surveillance beyond what the harness already records (privacy boundary: aggregate-first, redact-at-write; content is not the product, outcomes are).
- No second reporting stack (digest/lore consume the same rollups).
- No scores without consumers (sunset clause).
- No self-reported metrics as truth (store-side joins only).

## 7. Success criteria

1. **Loop A:** within 30 days, one lane is **demoted or retired** with a published comparison (verified-ship vs cost-per-verified-outcome) — a decision the sticker-price-era view could not have justified.
2. **Loop B:** within 30 days, ≥2 tool fixes are shipped whose originating fingerprint was auto-filed as a board row, with before/after wasted-call evidence.
3. **Loop C:** one scheduler tuning change (cooldown/weight/gate) lands with its data justification attached — replacing the vibes-based version.
4. **Claim−receipt detector:** the standing query reproduces the quorum's zero-output finding on live data (no hand joins).
5. **Sunset clause works:** at least one score is retired by the rule within the first quarter (proving the meta-discipline isn't decorative).
6. **Join with behavior:** one question answered end-to-end from both channels (vault outcome + rabbit-hole behavior) on a real case.

## 8. Cost & shape

Effort **M–L (~3 weeks)**: capture hooks + joins (≈1w), scoring/rollups + scoreboard artifacts (≈1w), loops wiring (auto-filing to boards, digest sections, decision cadence docs) (≈1w). Ships as `h3ops evidence` (harness-side capture + store-side joins), no daemon beyond the existing harness; storage = append-only JSONL + DuckDB rollups, riding the same backup chain as the rest of the line.

**Sequencing:** nothing runs until LOGSEY-001 (repo/chain). Loop A/B/C are the highest-value first three; the rabbit-hole spec harvest is a reading task that can start immediately and costs no build time.

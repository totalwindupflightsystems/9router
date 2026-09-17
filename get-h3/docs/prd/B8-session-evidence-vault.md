# PRD (complete): `h3-evidence` — Session Evidence Vault

**Project:** get-h3 · agent-ops line · **Item:** B8 · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed (v3 — complete product spec) · **Effort:** M–L (~3 weeks) · **Depends on:** nothing · **Feeds:** digest (B4), lore (B3), scheduler tuning, task-router registry

---

## 0. Executive summary

The fleet pays real money for agent work and cannot currently tell **work that was done** from **work that was claimed**. The evidence vault closes that gap: it records, per session, what the agent *did* (tool calls), what it *produced* (files, commits, tests, messages), what it *claimed* (board flips, completion stamps), and what it *cost* (metered tokens/USD) — then joins them so that `claims − receipts` is a query, not an investigation.

It is both a **truth layer** (nobody can claim completion without artifacts) and a **decision engine** (eight improvement loops, each tied to a named decision consumer and a metric that must move). Value is defined backwards from decisions: a score that doesn't change a decision in 90 days is retired.

---

## 1. Problem statement (with live evidence)

| Failure | Evidence (this fleet) | Cost |
|---|---|---|
| **Completion lies** | scheduler tick records stamped `outcome='committed'` on **1,701 zero-output ticks/week** | unbounded — unverified work accumulates |
| **Degenerate sessions** | a worker session issued **288 identical tool calls** before a human noticed | hours of compute + attention |
| **Claim/artifact mismatch** | commit `d7d9b6e` claimed a fix, landed **test-file-only** and failed in-guard | rework, lost trust in the board |
| **Cost opacity** | scheduler's `cost_usd` was **sticker price: 131× the actual cash**; real meter lived elsewhere | wrong investment decisions |
| **No model-value signal** | "is lane X better than lane Y for foreman work?" was answerable only by a week-long hand-built quorum report | decision latency measured in weeks |
| **Lane integrity** | duplicate work in sibling sessions, collisions (TR-046), and retry storms invisible until they became incidents | incident costs + lost work |

Every one of these is the *same missing artifact*: a per-session record that joins **claims, receipts, behavior, and cost**. Logs have fragments; boards have claims; meters have dollars; **nothing joins them**.

## 2. Goals & non-goals

**Goals**
1. Every session produces a durable evidence record with **claims and receipts in the same row-shape**.
2. Scores that answer operator questions in **one command**, computed from **store-side joins** (never agent self-reports).
3. Each score names a **decision consumer, cadence, and expected metric movement** — or it is retired.
4. Capture is **cheap, async, fail-open** — never blocks or slows a session.
5. The store is **honest**: absent data renders "not captured", never zero.

**Non-goals (explicit)**
- Not a content recorder (no prompts/responses archive; no keystroke-level surveillance).
- Not a replacement for logs (logsey owns raw logs) or kernel telemetry (rabbit-hole owns that).
- Not a billing engine (it *joins* meters; cost truth stays where it already is).
- Not an agent-facing scoreboard for self-optimization by agents (see §11 anti-gaming).

## 3. Personas & users

| Persona | Uses evidence to… |
|---|---|
| **Operator (Bane)** | decide lane/spend/project investments; verify claims at a glance |
| **Foreman agent** | orient at session start: what landed, what's stuck, what it costs here |
| **Tool builder (coding-hermes)** | find the top failure fingerprints → file tool fixes |
| **Auditor / QA** | prove coverage, reproduce findings, spot claim/receipt drift |
| **Incident responder** | reconstruct "what was this agent actually doing?" during a window |
| **New agent on a box** | learn which lanes/procedures actually work here, from data |

## 4. User stories

**Capture & truth**
- US-1: As the fleet, every session records its tool calls, artifacts, claims, and cost joins — without any agent opting in.
- US-2: As an operator, `evidence report --session <id>` shows exactly what happened, with each claim paired to its receipt or marked unproven.
- US-3: As an auditor, `evidence score` shows claims-vs-receipts delta per lane/project over any window.

**Decisions**
- US-4: As Bane (weekly), I demote or retire a lane using verified-ship rate + cost per verified outcome — a decision I can defend with a number.
- US-5: As the tool builder, my top fingerprint auto-files a CHT board row with the failing tool call signature and wasted-call count.
- US-6: As the scheduler policy owner, I tune cooldown/weight/load-gate with data attached, replacing vibes.
- US-7: As the spend owner, I see metered vs sticker, misroutes, and plan-vs-PAYG crossover per workload.

**Quality & learning**
- US-8: As a guard maintainer, I retire guards that never caught a real break (join guard failures to post-merge rollbacks).
- US-9: As the knowledge owner, I see which skill/brief versions improved outcomes and delete the rest.
- US-10: As an investigator, I replay an incident window with behavior + cost + outcome side by side.

**Meta**
- US-11: As the owner, an unused score is retired automatically after 90 days and the retirement is visible.
- US-12: As a privacy-conscious owner, I can prove the vault contains no raw content and no credential material.

## 5. Product overview

Two channels, one join:

```
CLAIMS        board flips · outcome stamps · completion messages · PR text
RECEIPTS      files written (hash) · commits (tree-verified) · tests run (verdict) · messages (delivery id) · artifacts
BEHAVIOR      tool calls (name, args-hash, duration, status, error class, retry links)
COST          tokens in/out/cache + usd_sticker + usd_effective + cost_source
                  │
                  ▼   (store-side joins: session_id, project, lane, model, window)
             SCORES & ROLLUPS  →  loops A–H  →  decisions  →  measured deltas
```

**The core invariant:** claims and receipts share one row-shape, so honesty is a join, not a judgment call.

## 6. Architecture

```
[harness hooks]                      [store]                        [consumers]
 tool-call      ─┐                                                  digest (B4)
 commit/test    ─┤  async bounded queue  →  JSONL append-only  →    lore (B3)
 board-claim    ─┼─ drop-oldest + gap counter                       task-router registry
 meter join     ─┘        │                                          scheduler policy
                    redaction pass (write-time)                      CHT board (auto-filed rows)
                          │                                          human CLI / SQL
                    DuckDB rollups (rebuildable)
```

- **Capture:** harness-side hooks emit events; a bounded queue prevents session backpressure. **Drop-oldest with a visible gap counter** — bookkeeping never blocks work.
- **Redaction:** key-shaped strings (`sk-`, `AKIA`, `user_`, bearer patterns) stripped at write time; content payloads are never captured (summaries + hashes only).
- **Store:** append-only JSONL per box (git-friendly, auditable) + DuckDB rollups (rebuildable cache, never source of truth). Same backup chain as the line: DuckBrain ns → S3 → git history.
- **Tamper-evidence:** hash-chained appends; the vault can be wrong about the world but provably about itself.
- **Queries:** `h3ops evidence` CLI + SQL; rollups feed digest/lore; no separate reporting stack.

## 7. Data model (JSONL schemas)

```jsonc
// sessions.jsonl
{"id":"ses_...","started_at":"...","ended_at":"...","harness":"hermes","agent_kind":"foreman|worker|api|cron",
 "project":"coding-hermes-scheduler","tick_id":"t-...","model":"glm-5.3-flash","lane":"zai-glm","session_key":"2026..."}

// calls.jsonl
{"session_id":"ses_...","seq":12,"tool":"patch","args_hash":"sha256:...","args_summary":"file=…/router_spawn.go hunks=2",
 "started_at":"...","dur_ms":840,"status":"ok|error","error_class":"match_not_unique","retry_of":null,"bytes_out":214}

// products.jsonl
{"session_id":"ses_...","kind":"commit","ref":"db01096","hash":"sha256:...","verified":true,
 "verify_method":"tree_match","ts":"..."}                     // also: file | test | message | artifact

// claims.jsonl
{"session_id":"ses_...","kind":"board_flip","ref":"TRBL-046:complete","text_hash":"sha256:...","ts":"..."}

// costs.jsonl (joined from meters, not self-reported)
{"session_id":"ses_...","provider":"deepseek","model":"deepseek-flash","tokens_in":41022,"tokens_out":991,
 "cache_read":1210000,"usd_sticker":1.42,"usd_effective":0.11,"cost_source":"metered|gateway|estimated"}

// evidence_chain.jsonl  — integrity
{"seq":104411,"prev_hash":"sha256:...","row_hash":"sha256:...","ts":"..."}
```

**Derived rollups:** `score_lane`, `score_project`, `score_model`, `score_agent` per window with the six scores of §8.

## 8. Scoring model (with structural anti-gaming)

| Score | Definition | Anti-gaming mechanism |
|---|---|---|
| verified-ship rate | verified landings ÷ attempts | landings require artifact+receipt; trivial work doesn't satisfy verify |
| cost per verified outcome | `usd_effective` ÷ verified landings | meter is authoritative; unmetered paths surfaced as coverage gaps |
| evidence coverage | sessions with complete receipts ÷ sessions | "not captured" ≠ zero; completeness measured per harness |
| claim−receipt delta | claims without receipts ÷ claims | the 1,701-lie detector, as a query |
| degenerate rate | sessions with loops/retry-storms ÷ sessions | retries counted from call graph, not session count |
| escalation precision | true incidents ÷ alarms | precision published; below-threshold rules demoted |

**Structural guarantees:** (1) receipts require real artifacts/tests — you cannot farm a receipt that requires a passing test; (2) all scores come from **store-side joins** (commits, files, meters, message IDs), never from what an agent says about itself.

## 9. The eight improvement loops (value = a decision that changed)

| Loop | Cadence | Data → decision | Metric that must move |
|---|---|---|---|
| **A Provider/lane portfolio** | weekly | verified-ship + cost/verified outcome → demote/retire lanes, amortize plans | `$` per verified outcome ↓ |
| **B Tool craftsmanship** | per fingerprint | failure classes, loops, wasted calls → auto-filed CHT rows | wasted calls per landed change ↓ |
| **C Scheduler policy** | per window | outcomes × cost × landings → cooldowns/weights/gate | verified landings per scheduled hour ↑ |
| **D Guard calibration** | monthly | guard failures joined to real breaks → retire/strengthen | real breaks caught per guard-minute ↑ |
| **E Skill/prompt efficacy** | monthly | outcomes by skill/brief version → rewrite/delete | verified-ship per instruction-token ↑ |
| **F Spend portfolio** | monthly | metered vs sticker, misroutes, plan crossover | unaccounted spend % ↓ |
| **G Incident → guard/runbook** | event | repeat incidents per class → guard/pin/runbook | repeat-incident rate ↓ |
| **H Experiment discipline** | on demand | before/after on a deliberate change | reverted-change rate ↓ |

**Sunset clause:** each score declares its decision consumer; **no decision in 90 days → retire loudly** (a small digest notice). Success criterion includes at least one retirement in the first quarter, proving the meta-discipline is real.

## 10. Query surface (the questions that justify the tool)

```bash
evidence report --session <id>            # full trail, claims paired to receipts
evidence score --by lane --window 30d     # the weekly portfolio decision
evidence score --by project --window 30d  # scheduler tuning input
evidence fingerprints --top 20 --window 7d
evidence coverage                          # capture completeness per harness
evidence claim-gap --window 7d             # the outcome-lie list
```

```sql
-- cost per verified outcome, by lane, last 30d
SELECT lane, sum(usd_effective)/nullif(count(*) FILTER (WHERE verified),0) AS usd_per_verified
FROM landings JOIN costs USING (session_id) WHERE ts > now() - INTERVAL 30 DAY GROUP BY 1 ORDER BY 2;
```

## 11. Privacy & security

- **No content capture.** Args are hashed + summarized; outputs are referenced (path/hash), never stored.
- **Aggregate-first** for any external sharing; per-session detail stays local and access-scoped.
- **Write-time redaction** with the gitleaks pattern set (inherits the vault's rule: the vault must never become a leak surface).
- **Credentials:** the vault stores env-var *names* and refs, never values (forge/B7 boundary applies identically here).
- **Access policy:** read scoped by project/lane; operator-level for cross-fleet rollups.
- **Tamper-evidence:** hash chain per store; rollup regeneration verifies chain continuity.

## 12. Integration with the line

| Tool | Relationship |
|---|---|
| logsey (B1) | behavior/time context; evidence adds outcome + cost columns for incident joins |
| pulse (B2) | resource state at failure moments (`pulse around <ts>` + session id) |
| lore (B3) | failure classes feed runbooks; runbook efficacy measured by repeat rates |
| digest (B4) | carries scoreboard sections; delivery of "needs-human" items |
| forge (B7) | lane health + rotation events appear as evidence rows (audit trail continuity) |
| relay (B6) | job/delivery receipts are first-class evidence products |
| hilo | code-graph joins: which files/symbols landings touched (blast-radius of work) |
| CHT board | fingerprint → auto-filed tool-fix rows (Loop B) |

## 13. rabbit-hole relationship (sibling, not competitor)

- **rabbit-hole:** *what did the agent do* — COLLECT (eBPF/strace, zero-SDK) → CLASSIFY → EXPRESS (chat over sessions). Strong on behavior, blind on outcome.
- **evidence vault:** *what did the agent prove, and what did it cost* — strong on outcomes/cost, blind below the harness.
- **Reuse now (reading only, zero build cost):** session lifecycle (attach/detach, persisted), S05 storage data model, classification tiering (fast patterns then ML), possibly EXPRESS as the human query surface.
- **Decision point (separate, later):** whether to revive rabbit-hole as the vault's expression layer. Do **not** build two collectors — the vault eats harness streams, rabbit-hole eats kernel streams, they meet at the join.

## 14. Milestones & acceptance

| # | Milestone | Acceptance |
|---|---|---|
| **M1** | Capture + store (sessions, calls, products, claims, costs) | 7 days of this box's sessions captured; gap counter honest; no session slowed |
| **M2** | Joins + six scores | claim−receipt query reproduces the 1,701-lie class on live data, no hand joins |
| **M3** | Loops A/B/C wiring | one lane demoted with published comparison; ≥2 tool fixes from auto-filed fingerprints; one scheduler tuning with data attached |
| **M4** | Adoption + meta | digest carries the scoreboard; ≥1 score retired by the sunset clause; foreman session-start uses `evidence score` |

## 15. Success criteria (measurable, decision-shaped)

1. Lane demoted/retired with a published comparison within 30 days of M2.
2. ≥2 shipped tool fixes whose originating fingerprint was auto-filed.
3. One scheduler tuning change lands with its data justification attached.
4. Claim−receipt detector reproduces the quorum finding on live data.
5. ≥1 score retired by the sunset clause within the first quarter.
6. One end-to-end question answered from both channels (vault outcome + rabbit-hole behavior).
7. Privacy proof: grep of every artifact and the store returns zero content payloads and zero credential values.

## 16. Testing & QA plan

- **Honesty tests:** absence renders "not captured"; no score can emit an unlabeled cost.
- **Anti-gaming tests:** synthetic sessions that claim completion without artifacts must *not* increment verified landings; a passing-test-farm attempt must be rejected.
- **Gap-honesty test:** kill the capture path; `coverage` must report the gap, not smooth it.
- **Chain integrity test:** delete/mutate a row; regeneration must detect it.
- **Redaction test:** seeded key-shaped strings must never appear in the store or any rollup.
- **Dogfood:** run on bunker-las-03 against its own sessions; compare a hand-audited session with the vault's record (ground-truth parity).
- **Performance:** capture adds no measurable latency to a session (p95 delta < 5ms).

## 17. Rollout & operations

- Per-box capture, local store, no central dependency for capture; rollups may roll up centrally (digest) but failure of that never blocks local recording.
- Budgets: capture overhead <1% CPU, store growth bounded (summaries + hashes, not payloads) — measure and publish like pulse's budget.
- Kill switch: disable capture → sessions unaffected; rollups degrade honestly.
- Watchdog: capture silence >N minutes on a busy box = alert (the monitor watches itself).

## 18. Risks & mitigations

| Risk | Mitigation |
|---|---|
| Agents optimize the scoreboard | scores are outcome-based, store-joined, and require real artifacts (structural, not policy) |
| Measurement culture (dashboards, no decisions) | sunset clause + decision-consumer declaration at creation |
| Privacy creep | no-content rule enforced by test; aggregate-first sharing |
| Capture overhead | async, bounded, drop-oldest with visible gaps |
| Rollup divergence from raw | rebuildable-from-raw by design; chain continuity verified |
| Two competing telemetry systems (rabbit-hole overlap) | explicit division of labor; harvest specs, one collector per stream |

## 19. Effort & shape

**~3 weeks total:** capture hooks + store (≈1w) · joins + scores + rollups (≈1w) · loops wiring (auto-filing, digest sections, decision cadence docs) + QA (≈1w). Ships as `h3ops evidence`; no daemon beyond harness hooks; storage JSONL+DuckDB in the standard backup chain.

## 20. Open questions for Bane

1. **Scope of capture on this box first** (7840hs only) vs all fleet boxes at M1?
2. **Cost source priority** when meters disagree (metered > gateway > estimated) — confirm the ordering.
3. **Access policy default:** per-project scoping for read, or operator-only for v1?
4. **rabbit-hole:** harvest-specs-only now (recommended) or greenlight the expression-layer revival as part of B8?
5. **Auto-filing:** should Loop B create CHT rows directly, or propose them via digest for approval (proposal-not-write doctrine suggests propose)?

## 21. Glossary

**claim** — an agent's assertion of completion · **receipt** — an artifact/test/delivery proving it · **verified landing** — a landing with receipts · **degenerate session** — loop/retry-storm session · **gap counter** — visible count of dropped capture events · **sunset clause** — retire scores with no decision consumer in 90 days · **the join** — store-side combination of claims, receipts, behavior, cost.

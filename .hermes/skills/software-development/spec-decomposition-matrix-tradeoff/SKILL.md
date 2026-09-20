---
name: spec-decomposition-matrix-tradeoff
description: Use when turning vague intent into an exhaustive design matrix — cascading questions, break-checks, explicit tradeoffs — before PRD or build.
version: 1.1.0
license: MIT
metadata:
  hermes:
    tags: [design, decomposition, tradeoff, cascade, pre-spec, interrogation, design-matrix]
    related_skills:
      - coding-hermes-spec-lifecycle
      - coding-hermes-quorum
      - coding-hermes-prd-to-contracts
      - engineering-prd-writing
      - prd-authoring
  forge_name: 問い尽くし (Toitsukushi — "asking until nothing is left to ask")
  stage: pre-spec
  audience: autonomous-agent
---

# 問い尽くし — Spec Decomposition Matrix & Tradeoff

> **Name.** 問い尽くし (toi-tsukushi): *toi* 問い, "question"; *tsukushi* 尽くし, "exhaust, use up
> completely, leave nothing remaining." A matrix is done when the questions have been *used
> up* — not when you are tired of asking them.

You sit between a vague idea and a PRD that an autonomous fleet can execute. You do not
write code. You do not write a checklist. You run a **depth-first interrogation engine**
against the project until no answer generates a new unknown, and you leave behind a design
substrate: every implicit decision made explicit, every alternative compared, every tradeoff
named, every genuine priority question escalated to the human as ONE comparative question
with options and costs attached.

**The failure you exist to prevent.** An agent is handed a shallow prompt and starts writing
one function at a time. It invents the storage format, invents the auth model, invents the
error taxonomy, invents the directory layout, invents the retry semantics — each locally
reasonable, mutually incompatible. Five thousand lines are then deleted. This is not a style
problem. It is the mechanism by which shallow design becomes expensive.

**Shallow design is not a smaller version of this skill. It is a different output.**

---

## 1. The law — four mechanics and two governors

Everything in this skill is one of four mechanics, held in check by two governors. If you
skip a mechanic, the artifact is defective. If you skip a governor, the artifact is
irrelevant.

### Mechanic 1 — Cascade

Every answered question generates the next ring. The canonical shape:

```
seed answer
  → ≥5 derived questions across ≥5 distinct classes
    → each answered (by you, with evidence)
      → ≥5 more
        → … until a full ring produces no new unknowns
```

Questions in questions in questions. A flat checklist asks "which database?" once. The
cascade asks what the data *means*, who owns it, what a half-written record looks like, what
rejects it, what the retention horizon is, whether the query pattern even needs a database —
and then asks whether the whole branch should exist.

### Mechanic 2 — Break-check

After every proposed decision: **what does this break?** Not as a motto — as a recorded
field. Every decision row carries `breaks:`, and `breaks: none` is only legal as
`breaks: none — checked against <explicit list>`. A break-check that modifies nothing is a
break-check that was not run.

### Mechanic 3 — Tradeoff, not verdict

Never output "use Postgres." Output: the real candidate set, what each costs, what each
breaks, which axis actually separates the survivors, what would reverse the choice later,
and — when the separating axis is a *priority judgment* rather than a technical fact — one
comparative question for the human, with options attached.

### Mechanic 4 — Recursion to core

After every branching ring, climb back:

> Does this still serve what the user actually needs? Why does the user need it? **If this
> entire branch vanished, which job fails?**

If the answer is "elegance," "completeness," or "future maybe" — prune it or demote it, and
record that you did. Unconstrained question machines produce beautiful irrelevant documents.

### Governor 1 — Self-interrogation (the human is not the queried party)

**You ask yourself the million questions.** You seed from the human — intent, priorities,
hard constraints, non-negotiables — then reason independently, research prior art, probe the
system, and answer your own questions with evidence.

The human receives **only**:

- seeds you genuinely cannot derive (bounded to ≤5 per run, asked up front, batched);
- priority tradeoffs with real costs on both sides;
- the final artifact.

A run that hands the human a questionnaire has failed its core requirement, no matter how
thorough the questions are. "The AI is asking itself" is the whole design.

### Governor 2 — The budget (a cascade is not bottomless)

An unbounded interrogation loop on a low-stakes domain is the mirror-image failure of the
shallow matrix. Rings are bounded by stakes.

**Precedence — read this once, it resolves every case:** *the fixed point terminates the
cascade; floors and ceilings bound the effort.* In order:

1. **The fixed point is the stop condition.** A cascade ends when a full ring produces no new
   unknowns (§3.4). That is the only legitimate termination.
2. **The ceiling is a hard maximum** — ring 8 per domain absent an owner instruction. Hitting
   the ceiling writes `depth-ceiling-reached` as a register row naming every remaining
   load-bearing unknown, and hands off. An honestly truncated cascade beats a fabricated
   complete one.
3. **A floor is a minimum of EFFORT, never an instruction to fabricate questions.** If the
   fixed point arrives below the floor, the floor is satisfied by recording
   `fixed-point-below-floor: ring N` **with the reason the ring closed** — not by generating
   questions that answer themselves. A floor never authorizes padding.
4. **`NOT-REACHED` with a named reason and owner** satisfies the coverage requirement for a
   domain the run did not open at all. It does not satisfy a floor for a domain the run
   *did* open.

Then, the bounds themselves:

- **Ring floor:** every domain reaches ring 3, **or** reaches its fixed point earlier and
  records `fixed-point-below-floor` with the reason, **or** is recorded `NOT-REACHED` with a
  named reason and owner. Data, identity, concurrency, security, and deployment carry a
  ring-5 floor under the same rule.
- **Thin-domain exemption:** a domain whose triage score is ≤6 is expected to close at ring 2.
  When it does, record `fixed-point-below-floor: ring 2 (thin domain, score N)` — the reason
  is the score, and that is a legal close. The ring-3 floor above applies to domains with
  score ≥7; it is never a reason to keep interrogating a domain that already reached its
  fixed point.
- **Ring ceiling:** ring 8 per domain, absent an owner instruction. Ring 5 on a thin domain
  that already closed at ring 2 is a budget violation, not diligence.
- **Domain triage:** score each domain `blast_radius × uncertainty × irreversibility` (each
  1–3, integers, justified in one clause). Score ≥18 → ring 5 floor. Score ≤6 → the domain is
  thin: ring 2 is expected, record the score, and do not descend it further on principle.

---

## 2. The run — S0 through S9

Run these in order. Each stage's output feeds the next; the register accumulates across all.

**S0 — Intake lock.** Write down, verbatim: the owner's words, the named outcome, what is
explicitly out of scope, and the hard constraints. Do not paraphrase the owner into your own
vocabulary; their words are the seed of every core-recursion check. If the seed is empty,
hostile, or self-contradictory, see §10.

**S1 — Core statement.** One paragraph, produced and then *frozen*:

```
The user is <who>. They need <what> because <why>. Today they <current state>.
If we succeed, <observable change>. If we fail, <observable harm>.
This is explicitly NOT <the adjacent thing it will be confused with>.
```

The core statement is the anchor for every recursion check and every `core_link` field. If
you cannot write it, you have not understood the request — that is the first escalation
(§6), and it is worth more than any battery below.

**S2 — Domain sweep.** Walk the full grid in §4. For each domain, set a ring floor from the
triage score, mark what you already know, and mark what is `NOT-REACHED` with a reason and
an owner. No domain is silently absent.

**S3 — Cascade per domain.** Run the grammar in §3, domain by domain, in triage order
(highest score first — if the budget runs out, it runs out on the cheap domains).

**S4 — Break-check pass.** Walk the accumulated decisions against each other per §5.

**S5 — Tradeoff ledger.** Convert every contested choice into a ledger row with a named
hinge (§6).

**S6 — Escalation set.** Apply the escalation criteria. Produce the minimal set of
comparative questions. Everything else is decided and recorded.

**S7 — Assemble the artifact.** §7.

**S8 — Self-gate.** Run the DONE-vs-SHALLOW check (§8). A failing gate sends you back to
S3, not forward to handoff.

**S9 — Hand off.** Emit the handoff contract (§7.5) and the consumption contract for the
downstream spec/PRD stage.

### DONE vs SHALLOW

The matrix is **DONE** when all hold:

- every domain is answered or `NOT-REACHED` with a reason and owner;
- every load-bearing decision carries ≥2 candidates and a non-empty `breaks` with its
  checked-against list;
- every cascade recorded its terminating ring, and termination is by fixed point (§3.4);
- every escalation is comparative, options-attached, and one-line answerable;
- every unresolved item has an owner, a deadline or trigger, and a containment default;
- the artifact contains at least one evidence handle that could only exist because you
  looked at *this* project (§8, anti-gaming).

It is **SHALLOW** — regardless of length — if any of the shallow tells in §8 is present.

---

## 3. The cascade grammar

### 3.1 Answer type → next question type

Identify what kind of answer you just wrote, then ask its row. This table is the **classifier**
— it tells you which probes a given answer owes. The actual *generators* are §3.2 (universal
expansion, the default first ring), §3.3 (the five-class rule), and §4's domain batteries
(the per-domain question sets). Use all three together: §4 supplies domain-specific probes,
§3.2 the generic ten, §3.3 the class-coverage floor, and this table picks the right subset
for the answer in front of you.

| Answer type | Questions it forces |
|---|---|
| **Choice** ("we will use X") | What were the credible alternatives? Why does this one win on the hinge axis? What does it worsen? What evidence supports it? What does switching later cost — migration, contract breaks, data, retraining? Which interface preserves a swap path? Who chose differently and what happened to them? |
| **Format / schema** | Who writes it? Who reads it? What does a half-written or mixed-version instance look like on disk and on the wire? What rejects it, with what error? How does it evolve — additive, versioned, migrated? Which copy is canonical when two exist? How is migration tested? |
| **Number** (limit, timeout, size, rate) | What does the number bound? How was it derived — measured or guessed? Who enforces it: client, server, driver, kernel, or human? What happens at 80%, 100%, and beyond? How is the actual value measured? What is it at 10×? |
| **Agent / process / service** | What identity does it use, what credentials does it hold? What may it do that others may not? What does broken look like from outside? Who supervises it, how fast is restart, what happens to in-flight work? What is its blast radius when it misbehaves? Can retries duplicate work? |
| **Dependency / library / driver** | Which version, and what pins it? Which license — does it restrict the product? Maintenance signal: release cadence, issue response, bus factor, last commit? Vendored, mirrored, or fetched at build? **Does it actually support the capability you need, or do you assume it does?** What is the swap path if it dies, and is that path tested? |
| **Tool / hardware driver** | Does it expose the required capability — and did the documentation say so, or did you probe? If probed: with what, and what was the transcript? If the capability is absent, what degrades, and is it a degradation or a stop? Who keeps it working across OS and driver updates? |
| **Human step** | Who performs it, by role? What is the SLA? What happens when they are absent, slow, mistaken, or overloaded? Is it approval, input, or gate? Can it be partially automated, and what is the residual? How is it audited? |
| **State transition** | What initiates it? What guards it? Is it atomic? What happens if interrupted mid-way? Can it repeat safely? Who observes it? How is an illegal state prevented — or repaired once it exists? |
| **External contract** | Who controls it? How is change announced and scheduled? What are its limits and failure semantics? How is compatibility tested? What happens when it lies, is slow, or disappears? |
| **Assumption** | What evidence supports it? What observation would falsify it? When will that observation exist? Which decisions depend on it? What is the containment plan if it turns out false? |
| **Negative answer** ("we don't need that") | Is it truly unnecessary, or merely postponed? What future condition activates it? Which design choice today makes adding it later expensive? What evidence supports the omission? |
| **"We'll figure it out later"** | **Rejected.** Convert it: what exactly is unknown, why is it not answerable now, who owns it, what evidence closes it, by when, what does it block, and what reversible default contains the uncertainty meanwhile? |

### 3.2 Universal expansion — the default first ring

For each answer, these ten are the default probes. Select the ones that expose new design
information; do not ask all ten mechanically.

1. **Meaning** — what does this mean in observable terms?
2. **Dependency** — what depends on it, and what does it depend on?
3. **Failure** — how can it be absent, late, partial, stale, duplicated, malformed, or wrong?
4. **Enforcement** — who or what keeps it true?
5. **Proof** — how will we verify it?
6. **Alternative** — what else could satisfy the same need?
7. **Reversal** — what would switching later cost?
8. **Core** — which user need makes this necessary?
9. **Breakage** — what does adopting it break?
10. **Boundary** — at what scale, time, trust boundary, or lifecycle stage does it stop being true?

### 3.3 The five-class rule

Every **load-bearing** answer (one that other decisions rest on) must spawn **at least five**
derived questions across **distinct classes**. Same class five times is one question wearing
a hat.

- **D — data:** what shape, whose data, what does it mean, who owns it, how does it evolve.
- **F — failure:** how does this break, how do you notice, what does recovery look like.
- **O — ops:** who runs it, what happens at 3am, how is it upgraded, who is paged.
- **C — cost:** money, time, complexity, maintenance, and all four at 10×.
- **A — alternatives:** what else could work, why not, what would change the verdict.

Add **S — security**, **U — user experience**, **X — compatibility**, and **P — proof**
questions whenever the domain touches them. Security questions are never optional on
identity, tenancy, secrets, or network boundaries.

### 3.4 Termination — the fixed point, and how to make it checkable

A cascade terminates when one full ring produces **no new unknowns**.

**Define the ring once, so the termination test means something.** A **ring** is: *every
question opened in the previous ring has, in this ring, either been answered or explicitly
resolved to a recorded unknown, a decision, or a deferral.* A ring is not "one branch
descended" — it is the full pass over the previous ring's output set. If a domain has four
open branches, the next ring closes all four before the ring is complete. This makes the
termination test a set operation on a known input, not a judgment call.

Terminating because you are tired, because you hit a page count, or because the answer "seems
obvious" is not termination — it is truncation.

"Seems like no new unknowns" is a vibe. Make it mechanical:

1. **Assign every question a stable id** (`<domain>-q<ring>-<n>`).
2. **Compute a normalized signature** per question: `(subject, decision-class, affected
   boundary)`, lowercased, stop-words removed, sorted. A question already in the register
   with the same signature is a **duplicate or an alias**, not a new unknown — link it,
   never re-ask it. The three axes are closed sets you must pin down before the run:
   - **`subject`** — the noun being decided. Extract it as the head noun of the question (the
     thing the question is *about*). Build the vocabulary in the order the run produces it:
     common nouns first (file, record, request, user, device — whatever the seed names), then
     extend the list as §4.5's data dictionary and §4.6's store inventory land. **Ordering
     rule, so the signature test is not circular:** a question asked before §4.5 completes
     signs off the seed's own nouns, not off the data dictionary — and when §4.5 later renames
     or splits a subject, re-sign only the questions that used the old noun, recording the
     re-sign as a `possible-alias` link rather than a silent rewrite. Never block a cascade
     waiting for §4.5; sign with what you have and re-sign on change.
     Maintain a domain-local synonym map so "record"/"entry"/"row" collapse to one subject;
     when you cannot tell whether two subjects are the same, **do not collapse them** — link
     them as `possible-alias` and let the reviewer decide. False merges lose unknowns
     silently; false splits merely cost a redundant question.
   - **`decision-class`** — a closed set, use §3.3's letters: `D F O C A S U X P` (data,
     failure, ops, cost, alternatives, security, user-experience, compatibility, proof).
   - **`affected boundary`** — which domain(s) or layer(s) the answer touches, from the §4
     grid (e.g. `4.6 storage`, `4.21 security`, `4.18 protocols`). Reuse the §4 numbering;
     never invent a boundary name.
3. **Track ring sets.** Ring N's output set minus the register's existing signature set =
   `new_normalized_unknowns`.
4. **Terminate when `new_normalized_unknowns == ∅`** for a full ring.
5. **Resolving an item to an owned unknown counts as closing it for the ring** — the unknown
   is a new register row, but it is not an *open question* carried into the next ring. Only a
   newly-asked question with a signature not yet in the register is a new unknown.
6. **Record the terminating ring number in the register.** Ring depth is evidence of how hard
   you interrogated; a "done" claim with no ring recorded fails the gate.

### 3.5 Worked cascade — data & storage (the shape to imitate)

Seed: *"an edge device records readings about once a second; a small web app shows the last
hour and monthly totals."*

**Ring 1.**
`Q (data, BEFORE-BUILD): What is a reading, and what does it mean to the user?`
`A:` reading = `(device, timestamp, value, unit, quality_flag)`. Meaning: *"was this thing
behaving normally during the window I care about."* → `breaks: none — checked against scope
(no alerting in v1) and UI (chart only)`.
Derived, five distinct classes:

- **D1** — Are timestamps from the device clock or the receiver? Device clocks drift and lose
  power; who is authoritative?
- **F2** — What does a gap mean: sensor asleep, network down, device dead? Are gaps
  first-class?
- **O3** — How long is data retained, and who deletes it?
- **C4** — At 10× devices, what is the write rate and row count per month?
- **A5** — Alternatives to a database at all: append-only files per device-day, object
  storage, columnar store.

**Ring 2** (descend D1, the heaviest).
`Q (choice, BEFORE-BUILD): Who owns time?`
`A:` receiver stamps `received_at`; device `recorded_at` kept as-is, never trusted for
ordering. → `breaks: UI chart ordering if record and receive differ; the sync job that
compares devices; retention policy keyed on date` → **the break-check forces a second
decision**: all ordering and partitioning keys use `received_at`; `recorded_at` is
display-only.
Derived:

- **D1a** — Do you ever correct `received_at` (backfill), and if so what re-orders?
- **F2a** — Readings arriving after a long offline period: accept, reject, or quarantine?
- **O3a** — Timezone and DST: stored UTC, rendered local — which local?
- **C4a** — Does clock skew break the monthly rollup?
- **A5a** — Alternatives: NTP on the device (needs network and config at every site),
  monotonic sequence numbers from the device (needs firmware control), accept-and-flag skew.

`A on A5a:` device firmware is third-party and not updatable in this phase → sequence numbers
unavailable → **a probe was required**, and the probe (a raw field read over the device's
protocol) showed no sequence field, only a timestamp. `Evidence handle: probe transcript.`

**Ring 3** (descend A5 from ring 1 — storage shape).
`Q (choice, BEFORE-BUILD): Where does it live?`
Candidates: **(i)** relational table with an index on `(device, received_at)`; **(ii)** one
append-only file per device-day, indexed by a manifest; **(iii)** columnar/analytics store;
**(iv)** both — relational for recent, object storage for archive.

Compare without false precision: (i) is the least new machinery and the only one answering
"last hour" and "monthly totals" with the same query engine; it needs a retention job; at 10×
it needs partitioning. (ii) is cheapest to write and most expensive to read — monthly totals
require scanning; there are no transactions around the manifest; corruption in one file is
recoverable, but the manifest is now a custom store you maintain. (iii) buys monthly totals,
loses cheap point-writes, and adds a second system to operate. (iv) is right when retention
is long and recent access is hot; it costs a copy job plus a consistency question — *which
one is canonical?*

→ **Decision: (i),** with partitioning keyed on month and a retention job; (iv) is recorded
as the re-evaluation trigger condition.

`breaks:` the "no new machinery" assumption — partitioning implies a migration when the
partition key changes; asks the deploy pipeline for a scheduled job (nothing in the pipeline
runs scheduled work yet) → **new decision opened: scheduler ownership for maintenance jobs.**

Derived:

- **D1b** — Index set and why: `(device, received_at)` for the chart, `(received_at)` for
  retention sweeps, `(device, month)` for rollups. What does each cost on write?
- **F2b** — Disk fills: reject writes, drop oldest, or alert? Who decides?
- **O3b** — Backup: is a dump enough, or does restore need the retention job too?
- **C4b** — Storage cost per device-month, extrapolated to 10×.
- **A5b** — What would switch you to (ii) or (iv): retention horizon, read pattern, cost
  curve — and is any of it instrumented?

**Core recursion check** (mandatory after this branch). Does hourly-granularity storage serve
*why* the user needs this — "was my device behaving normally in the window I care about"?
Re-derive: the user's actual question is **comparative, not archival** — they want *currently
abnormal*, plus a chart. That downgrades long retention and upgrades a rollup path.
Consequence: the retention default drops from "forever" to "13 months, with monthly
aggregates kept indefinitely," which changes the storage decision's cost profile and closes
the partitioning-vs-archive question for v1. **The check changed a decision — that is what it
is for.** Recorded as `core-check-1`, with the delta it caused.

**Ring 4.** Derived questions resolve into known territory (index costs measured once;
retention job scheduled; gap semantics decided — gaps are first-class: row absent = gap,
rendered as gap). One new unknown survives: *what does the user see when data arrives late
but within the displayed window?* → recorded unknown, owner: UI domain, deadline: before ship.

**Termination.** Ring 4 produced one new unknown; ring 5 produced none. Closes at **ring 5**.
Register rows produced: 9. Escalations produced: **none** — every fork had a technical
winner. That is a valid outcome; escalating here would have been noise.

> **Read the shape, not the content.** The content above is an illustration. Copying it into
> a different project is the anti-gaming failure in §8.

### 3.6 Worked cascade — identity & permissions

Seed: *"a small internal tool; a handful of people; some should only see their own stuff."*

**Ring 1.** `Q (user model, BEFORE-BUILD): Who are the user classes, and what does each need
that the others must not have?`
`A:` (i) operator — sees everything, changes config; (ii) member — sees and creates their own
records; (iii) observer — read-only across everything, creates nothing. → `breaks: none yet,
but this implies three distinct authorization surfaces, which the API design does not have.`
Derived:

- **D1** — What is the account identifier: email, username, or an opaque id — and what
  happens when one person has two of them?
- **F2** — What happens when a member's access is revoked *while* their request is in
  flight, or while a permission decision is cached?
- **O3** — Who assigns and who revokes a role, and is there an audit trail for the change?
- **C4** — At 10× users and 100× records, does a per-request permission check cost anything?
- **A5** — Alternatives: per-object ownership column, role table, policy engine, or
  nothing-but-convention (which is a decision too — record it).

**Ring 2** (descend F2 — the failure class that usually ships broken).
`A:` revocation must take effect on the *next request*; therefore permission decisions may
not be cached beyond a single request unless the cache is invalidated on revocation.
→ `breaks: the performance assumption behind Q C4 (a per-request check), and the caching
layer if one is added later` → **break-check forces a second decision:** no permission data
in a shared cache; if one is introduced, tenancy and revocation epoch go in the key.
Derived:

- **S1** — Is the authorization check enforced at the entry point, the service, or the data
  layer — and if it is only at the entry point, what happens to internal callers?
- **F2a** — What does the response look like for a revoked user mid-session: 401, 403, or a
  silent empty result? (A silent empty result is indistinguishable from "no data" and hides
  the revocation.)
- **O3a** — Who can read the audit log, and is it tamper-evident?
- **C4a** — Does the check run per row or per query, and what does that cost at 100k rows?
- **A5a** — Alternatives: enforce at the data layer only (safe, harder to reason about),
  enforce in both (safe, duplicated logic), or a policy engine (flexible, a new dependency).

**Core recursion check.** The seed said "a handful of people." Re-derive *why* they need
isolation: is this confidentiality (a real requirement) or tidiness (a preference)? The seed
does not say. That is not a technical question the run can answer — it is a
`kind: seed-vs-derivation` gap about *stakes*. Record it, and escalate only the part that is
genuinely a priority judgment: *does a leaked record between colleagues constitute real harm,
or merely inconvenience?* That single answer sets the enforcement tier, and everything else
follows from it. Recorded as `core-check-2` with the delta.

**Ring 3** (descend A5). `A:` enforce at the data layer (row-level scoping in the query),
because the entry point is one code path today but will not be after the first background
job is added — and a background job bypassing the entry point is the classic breach.
→ `breaks: the "no new machinery" assumption (queries now carry a scope), plus the test
strategy (every query test needs a negative case)` → opens **D: the test matrix must include
an access-denied case per query.**
Derived: **S1a** — how does the scope get attached to a query, and can a developer forget it
silently? **F2b** — what happens on a query with no scope: fail closed or return everything?
**O3b** — who reviews the query layer for missing scopes? **C4b** — cost of the scope
predicate at 100k rows. **A5b** — what would make a policy engine worth it (number of roles,
number of resources)?

**Termination.** Ring 3 resolved both branches into owned unknowns (the stakes question, the
test-matrix item) and one decision; ring 4 produced no new signatures. Closes at **ring 4**.
Escalations produced: **1** (the stakes judgment — it is a priority, not a fact). Register
rows: 11.

### 3.7 Worked cascade — integration & driver capability

Seed: *"the service should print receipts to the thermal printer the shop already owns."*

**Ring 1.** `Q (integration, BEFORE-BUILD): What is the integration point — and does the
driver actually expose the capability we need?`
`A:` the shop's printer has a vendor driver. The service will call it. → `breaks: nothing yet,
but this is an assumption, not a fact.` Derived:

- **D1** — What is the wire format the printer accepts: a vendor SDK, a raw byte protocol
  over USB/serial, ESC/POS, or a spooler queue? Which one are we actually targeting?
- **F2** — What happens when the printer is off, out of paper, or mid-job? Does the print
  block the request?
- **O3** — Who restarts the print service at 3am, and is the failure visible?
- **C4** — Print latency, and what it does to request latency at 10× volume.
- **A5** — Alternatives: direct driver call, an adapter/bridge in front of the driver, a
  sidecar print agent, or spooling to the OS queue.

**Ring 2** (descend A5, and probe D1 — the driver capability is the load-bearing unknown).
`A:` the driver is a closed vendor SDK with no documented support for the duplicate-copy
feature the shop asked for. **This was probed, not assumed** — a two-line script against the
SDK raised `UnsupportedOperation`; transcript retained.
→ `breaks: the seed's requirement, and the integration plan built on the SDK` → **the break
forces a decision: an adapter/bridge that speaks the printer's raw protocol directly,
bypassing the SDK.** Rationale: the SDK may gain the feature later and is worth keeping
reachable; the bridge interface is stable (a print job), and the swap is plausible.
→ `breaks: adds a component to operate, and a protocol to test` → opens **O: who owns the
bridge process, and what restarts it.**
Derived:

- **F2a** — What does the bridge do when the raw write partially succeeds (half a receipt)?
- **S1a** — Does the bridge run as the service user, and can it reach the printer device?
- **X1a** — What is the protocol version, and what happens on a firmware update?
- **C4a** — The cost of the extra process, and of testing two paths instead of one.
- **A5a** — What would send us back to the SDK (feature shipped), and is that monitored?

**Core recursion check.** The seed's actual goal is *"the shop can hand a customer a
receipt,"* not *"we integrate the vendor SDK."* A half-printed receipt is worse than a
failed print, because the customer leaves with a wrong document. That re-ranks F2a from a
minor failure to a BEFORE-BUILD invariant: **a job either prints completely or not at all.**
The bridge must buffer and commit atomically at the protocol level, or mark the job failed
and alert. Recorded as `core-check-3` with the delta — it changed the failure handling from
"best effort" to "all-or-nothing."

**Termination.** Ring 3 resolved into owned unknowns (firmware-update policy, bridge
ownership) and no new signatures. Closes at **ring 3** — below the ring-5 floor for a
deployment-adjacent domain, recorded as **`fixed-point-below-floor: ring 3`**, with the
reason: the integration surface is one peripheral on one machine, blast radius bounded, and
the remaining questions are operational rather than architectural. Ring depth is evidence,
not a quota.

---

## 4. The domain grid

Every domain below gets: a triage score, a ring floor from the score, a **battery** (run it,
answer it), and a **required output** (what the answers must produce). Domains marked ⊕
carry a ring-5 floor unconditionally.

Capture per domain, in one record: answers, decisions (with ids), unknowns, break-check
results, the terminating ring, and the required output. A domain with a heading and no
answers is a shallow tell.

**Name the outputs, or the validator can't see them.** Several domains require a table, a
matrix, or a runbook. Those are artifacts in their own right and they carry ids, or the §7.6
cross-reference check is blind to them:

| Output kind | Id form | Lives in |
|---|---|---|
| data dictionary row | `DD-\d{3}` | domain file (§4.5) |
| schema/DDL sketch | `SC-\d{3}` | domain file (§4.6) |
| index entry | `IX-\d{3}` | domain file (§4.6) |
| interface contract | `IF-\d{3}` | domain file (§4.8) |
| pattern decision | `PT-\d{3}` | domain file (§4.31) |
| candidate/library | `LB-\d{3}` | `10-research.md` (§4.32) |
| integration seam | `IN-\d{3}` | domain file (§4.33) |
| failure entry | `FM-\d{3}` | domain file (§4.42) |
| runbook | `RB-\d{3}` | domain file (§4.42) |
| alert entry | `AL-\d{3}` | domain file (§4.17) |
| invariant | `IV-\d{3}` | `15-invariant-test-map.md` |
| required-output row, any domain | `<domain>-out-\d{2}` | the domain's own file |

A decision, ledger row, or unknown that references one of these names it by id. A table with
prose rows only is not an output — give its rows ids at creation, not retroactively.

### 4.1 Product & people
Who is this for, and who is it *not* for? Who pays, who operates, who is harmed when it
fails? Is this a product, a tool, a library, a service, or an internal script — and what
changes if the answer is different? Sketch the smallest thing that proves the idea.
**Required output:** the core statement (§2 S1) plus a named audience and an explicit
non-audience.

### 4.2 User model ⊕
Who is the user? What do they need? **Why** do they need it — what are they doing today
instead, and what does that cost them? How many distinct user classes exist, and what does
each need that the others must not have? What is each class's job-to-be-done in their own
words? What would make the user abandon this? Who is the *second* user nobody designed for?
**Required output:** a user-class table (class / need / why / what the others must not have /
success signal / abandonment trigger).

### 4.3 User management & identity
If there are users, someone must manage them. Accounts: how are they created, named,
uniqued, and deleted? Identity: what is the login identifier, and what happens when a person
has two? **Permissions:** what roles exist, who assigns them, who revokes them, and does
revocation take effect immediately (and if not, what is the window)? Sessions: lifetime,
refresh, concurrent-session policy, and forced logout. **Password/login reset:** the flow,
the channel, the token lifetime, the rate limit, what happens when the reset email is
compromised. **Social/OIDC login:** which providers, which is canonical, what happens when a
provider changes its claims or goes down, what links two logins to one account. MFA: offered
or required, which factors, and the recovery path. Invites, deactivation, offboarding, data
ownership on offboarding. Tenancy: is one customer's data ever in the same table, file, or
cache key as another's? Audit of permission changes.
**Required output:** an identity model (identifiers, credential types) and an authorization
matrix (role × resource × action) with the revocation window stated in seconds.

### 4.4 Requirements & explicit non-goals
Numbered requirements, each testable. Then the **non-goals** — what this explicitly will not
do in v1, named so nobody assumes it. Every non-goal is a decision with a reason, not an
omission. What is the acceptance bar for "works as expected" (§4.34)?
**Required output:** `R1..RN` with the non-goals list annotated with reasons.

### 4.5 Data — inventory, meaning, lifecycle ⊕
**Not "which database" — what data do you have, and what does it MEAN?** Enumerate every
data item: name, source, shape, type, units, valid range, nullability, cardinality, owner,
sensitivity. For each, the semantic question: what does a value *mean* to the user, and what
would make it meaningless? Which data is **canonical** and which is derived — and if two
copies disagree, which wins? Lifecycle: creation, mutation, deletion, archival, and who may
do each. Provenance: where did this value come from, and can you prove it later? Encoding:
text vs binary, character set, number precision (floats for money is a decision — record it),
time representation and timezone. Versioning: can the shape change without breaking readers?
Retention and deletion: how long, enforced by what, and is deletion actually deletion
(backups, caches, derived copies)? Privacy: which fields are personal, regulated, or
sensitive, and what is the lawful basis? Migration: how does existing data move, and can it
be rolled back?
**Required output:** a data dictionary — item / type / meaning / canonical-or-derived /
owner / sensitivity / retention — plus the canonical-source rule.

### 4.6 Storage & schema ⊕
Reason **from** §4.5 to a store; never from fashion to a store. Is it relational, document,
key-value, columnar, files, object store, or several at once — and why does the *meaning* of
the data demand that? If SQL: table structure (columns, types, constraints, nullability,
defaults, foreign keys), and **the indexes that will be needed and why** — one line per
index naming the query it serves and its write cost. If not SQL, what enforces integrity, and
what replaces the join? If both: which is canonical, and how do they stay consistent?
Transactions and isolation level: what must be atomic, and what anomaly is tolerable?
Partitioning/sharding: key, and what breaks when the key changes? Capacity: row/byte growth
per month at 1× and 10×. Backup and restore: what is backed up, how often, where, and has a
restore been rehearsed — *a backup that has never been restored is a hypothesis*. Schema
change: how is a migration applied, tested, and rolled back, and can old and new code run
simultaneously?
**Required output:** a DDL-equivalent schema sketch (or its non-relational equivalent), an
index table with the query each serves, and the migration/rollback procedure.

### 4.7 Cache — and whether you need one at all
**First question: is a cache needed?** What measurement shows the current path is too slow or
too expensive? If nothing measures it, the answer is no — record the decision and move on.
Local or shared? A local (in-process) cache is trivial and dies with the process; a shared
cache adds a network hop, a consistency problem, and a second system to operate. Which
**technology**, and why that one over the obvious alternatives — for a shared cache the
real candidates are a key-value store like Redis, an embedded engine like SQLite, the
database's own materialized views, or nothing at all; each has a different persistence
story, a different data model, and a different operational cost. **What data type lives in
it** — does the store's data model even fit your shape (a key-value store is not a queue; a
sorted-set is not a document; a TTL'd string is not a relational table)? If the chosen
technology is a store with its own persistence, is that persistence a source of truth or a
derived copy, and what happens on an unclean restart? Key design: what is the key, what is
the namespace, is tenancy in the key? How is it **filled** (lazy on read, eager on write,
warmed at boot), **invalidated** (on write — which write paths know about it? — on time, on
version stamp), and **cleared** (per key, per namespace, wholesale)? What is the TTL, and what
is the worst case when it is wrong? What happens when the cache is cold, unreachable, or
lies? Is the cache also a **store** — and if so, is there a script that can rebuild it from
the source of truth, is that script tested, and is it included in the deliverable?
Monitoring: hit rate, eviction rate, and staleness alarms.

**Required output:** the cache decision (yes/no with the measurement), plus key/TTL/
invalidation table and the rebuild script's location if the cache is durable.

### 4.8 Interfaces — inputs, outputs, contracts
Every input: source, format, validation, required vs optional, defaults, limits, and what a
malformed input does. Every output: shape, stability guarantee, and who consumes it. The
contract: is it versioned, is it additive-only, and how are breaking changes announced?
Error taxonomy: the classes of failure, their codes, their retryability, and what the caller
is expected to do. Idempotency: is the operation safe to repeat, and what key makes it so?
Pagination, filtering, sorting, and their limits. Rate limits and quota — enforced where, and
what the client sees. Timeouts: what is the client's timeout, what is the server's, and what
happens in the gap. **Required output:** an interface inventory with a per-interface contract
(shape, limits, errors, idempotency, version).

### 4.9 Filesystem, repo layout & where things live
One repo or many, and what forces the split (deploy unit, access control, release cadence,
language boundary)? Directory conventions: what goes where, and what is the rule a newcomer
can apply without asking? Naming: files, packages, artifacts, branches, tags. What is
**generated** vs **committed** — and is generated output ever checked in (why)? Where do
artifacts live: build output, binary, container, package registry, release bundle. Where does
**state** live — and is anything durable inside the working tree that should not be? What is
gitignored and why? Where do secrets live, and what is never in the repo? License file,
contributing file, changelog, CI config — present or explicitly not?
**Required output:** a repo tree sketch with a one-line rule for each top-level directory,
plus the generated-vs-committed list.

### 4.10 Build pipeline
Toolchain and versions — pinned how, updated how? Lockfile: present, committed, and enforced
in CI? Reproducibility: does the same commit produce the same artifact, and can you prove it
(two builds, hash compare)? Hermeticity: does the build reach the network, and if so, for
what, and can it be cached or vendored? Caching: what is cached, keyed on what, and how is
the cache invalidated correctly (a cache keyed on the wrong thing is a correctness bug).
Cross-compilation and target platforms. Build time at cold and warm, and what dominates it.
Artifact registry: where artifacts go, how they are named and versioned, and who can publish.
The local dev loop: how does a developer get from clone to running in one command?
**Required output:** the build graph (inputs → steps → artifacts) with the version-pinning
mechanism and the reproducibility proof.

### 4.11 Deploy pipeline ⊕
Environments: names, purpose, who can deploy to each, and how they differ. Promotion: how
code moves from dev to staging to production, and who approves. Rollback: the exact procedure,
how long it takes, and whether it has been tested. Migrations: expand-contract vs big-bang,
and the mixed-version window. Secrets: where they live, how they reach the process, how they
rotate, and what happens during rotation. Configuration: sources, precedence order, hot
reload, and per-environment divergence. Feature flags: which system, who owns the flag, and
what removes it. Deployment strategies: rolling, blue-green, canary — and how failure is
detected mid-deploy. Infrastructure as code: what is declarative, what is clicked by hand,
and what reconciles drift. Release cadence and versioning scheme. Post-deploy verification:
what proves the deploy worked, and what is the automatic rollback trigger?
**Required output:** an environment table (name / purpose / access / config delta) plus the
rollback procedure and the migration plan.

### 4.12 Runbox & runtime ⊕
What actually runs this — one process, a supervised set, containers, a scheduler, a serverless
platform, a cron job, a desktop app? Process model: forking, threading, worker pools, or
single-threaded; and why. Containers vs native: image build, base image, entrypoint, user,
filesystem layers, and image size. Resource limits: CPU, memory, file descriptors, disk, and
what happens when each is hit. Scheduling: what decides placement, and what happens on
contention. Sandboxing: what is allowed to touch what. Lifecycle: start, ready, healthy,
shutdown, and what happens to in-flight work on shutdown. Restart semantics: supervised,
exponential backoff, crash-loop protection. "Logs of last resort": if the app itself is
broken, where do you look, and is that path independent of the app? Timezone and clock.
Ports and sockets. What runs at boot, and what happens after an unclean shutdown?
**Required output:** a runtime spec (process model, limits, restart policy, shutdown
sequence) and the boot/restart story.

### 4.13 Logging
What is logged, at which levels, with which fields, and to where? Is there a **schema** for
log lines (or is it free text nobody can query)? Correlation: does a request have an id that
follows it across services? PII: what must never be logged, and how is that enforced rather
than hoped? Retention and rotation: size, age, compression, and where. Sampling and volume
control. Debug level in production: on, off, or toggleable — and if toggleable, by whom.
**Required output:** a log schema (field / type / example) and the redaction rule.

### 4.14 Metrics
Which numbers tell you the system is healthy, and what is the threshold for each? Rate,
error, duration — plus the domain-specific ones (queue depth, cache hit rate, lag, pool
saturation). Cardinality: what labels exist, and what stops label explosion? Where do metrics
live, how long are they kept, and who queries them? Every alerting threshold traces to a
metric — an alert with no metric is superstition. **Required output:** a metrics table
(name / type / labels / threshold / who acts).

### 4.15 Tracing
Is distributed tracing needed at all — and if the system is one process, is it worth the
overhead? If yes: what is a trace, what is a span, what is propagated, and at what sampling
rate? Where do traces go, and what is the retention? What question does a trace answer that
logs and metrics cannot? **Required output:** the tracing decision with its justification (a
"no" with a reason is a valid output).

### 4.16 Errors & exception taxonomy
Enumerate failure classes: expected-and-handled, expected-and-surfaced, unexpected-and-
contained, unexpected-and-fatal. For each: how it is represented internally, how it appears
externally, and what the caller should do. Retryability: which errors are safe to retry, with
what backoff, and what makes retry idempotent. The error envelope: code, message, detail,
correlation id — and the rule for what never appears in a user-facing message. Where errors
are caught, where they are allowed to propagate, and where they must never be swallowed. What
a "silent" failure costs, and how it is made loud. **Required output:** an error-class table
(class / internal repr / external repr / retry policy / who is paged).

### 4.17 Alerts, on-call & the human signal
Which conditions wake a human, who is that human, and what do they do first? What is the
escalation path when they do not respond? Which alerts are informational, and how are they
kept out of the waking path? Every alert: its trigger, its runbook, and its "what to do if
the runbook is wrong." Alert desensitization: how do you keep people from ignoring alerts
(this is a design problem, not a discipline problem)? **Required output:** an alert table
(condition / threshold / severity / responder / first action).

### 4.18 Services & protocols
Is this synchronous, asynchronous, or both — and which operations can tolerate which?
REST, RPC, message queue, stream, or file drop — and why, given the interaction's actual
shape? The wire schema: format, versioning, evolution rules, and what happens when an old
client meets a new server. Retries and idempotency keys. Backpressure: what happens when the
consumer is slower than the producer — buffer, drop, or block, and who decides? Timeouts and
deadlines: propagated or local? Service discovery and address resolution. Health and
readiness endpoints. Compatibility policy across versions.
**Required output:** a protocol table (interaction / sync-or-async / transport / schema /
timeout / retry / error contract).

### 4.19 State & persistence boundaries ⊕
Where does truth live, and where does a copy live? What is in memory that would be lost on
restart, and does that matter? Session state: where, how long, and what happens when the
store holding it goes down. Which components are stateless and can be replaced arbitrarily?
What is the single source of truth for each entity, and can you name it in one sentence per
entity? **Required output:** a state inventory (state / where it lives / survives restart? /
source of truth).

### 4.20 Concurrency & coordination ⊕
Where does concurrency exist — threads, processes, async tasks, multiple instances, multiple
users? What protects each shared resource: lock, queue, transaction, atomic operation, CRDT,
or nothing (and if nothing, why is it safe)? Race classes: lost update, read-modify-write,
check-then-act, double-submit, thundering herd, deadlock, livelock. Ordering: what must be
processed in order, and what breaks when it is not? Delivery: at-most-once, at-least-once, or
exactly-once — and the honest answer is usually at-least-once plus idempotency; say which you
are doing. Clock assumptions: does correctness depend on synchronized time (and does it break
under skew or NTP jumps)? **Required output:** a shared-resource table (resource / protection
/ race classes considered / ordering guarantee / idempotency key).

### 4.21 Security, secrets & tenancy ⊕
Identity: how does each actor — user, service, job, agent — prove who it is? Authentication:
method, strength, and where credentials are stored. Authorization: where it is enforced
(entry point, service, data layer — and enforced in more than one place is a decision to
justify), and what a bypass looks like. **Secrets management:** where secrets live, how they
reach the process, how they are rotated, who can read them, and what happens when one leaks —
which is *not* "nothing," because rotation beats deletion. Crypto: what is encrypted, at rest
and in transit, with which algorithms, and where the keys live. Tenancy: how one tenant's data
is prevented from appearing in another's response, log, cache key, or error message. Supply
chain: dependency provenance, lockfiles, and whether builds are reproducible. Audit: what
security-relevant events are recorded, and can they be tampered with? Threat model: who
attacks this, with what, and what is the scariest realistic outcome? **Never record an actual
secret value in the artifact — reference the secret's location, never its content.**
**Required output:** an authn/authz model, a secrets inventory (name / location / rotation /
consumer), and the threat model's top three risks with mitigations.

### 4.22 Virtualization & isolation
Containers, VMs, sandboxes, emulation — which, and why does the isolation requirement demand
it? What is being isolated from what: tenants, customers, users, jobs, agents, untrusted code?
Resource contention between neighbors: CPU, memory, disk I/O, network. Nested isolation: what
runs inside what, and what the inner layer can see of the outer. Escape surface: what breaks
isolation, and how is it prevented? Performance cost of the isolation layer, and whether that
cost is acceptable. **Required output:** the isolation topology and its escape-surface
analysis.

### 4.23 OS & platform
Which OS (or which set), and why? Distribution and version, and the upgrade policy. Kernel
features relied on (namespaces, cgroups, epoll/kqueue/IOCP, io_uring) and their availability.
Filesystem choice and its consequences (case sensitivity, atomicity of rename, fsync
semantics, maximum path length). Signals and process semantics. Locale, encoding, and
timezone handling at the OS level. Packaging and distribution method. Platform-specific code
paths and how they are tested. **Required output:** a platform matrix (OS / version /
features relied on / how tested).

### 4.24 Language & runtime selection
Which language, and why *this* one for *this* problem (concurrency model, memory model,
type system, ecosystem)? What does it constrain? Ecosystem health for the specific
libraries you need. Competence of the people or agents who will maintain it — a language
nobody on the team uses is a liability, however elegant. Runtime performance envelope:
startup time, memory floor, and whether that matters here. Interop: what must it talk to, and
how. Compile/interpret tradeoffs. **Required output:** a selection rationale naming the
constraints and the runner-up language with the reason it lost.

### 4.25 UI / UX
Screens and their purpose, one line each. **States:** empty, loading, partial, error,
permission-denied, offline, and too-much-data — the states nobody designs are where the
product feels broken. Navigation and information architecture. Accessibility: keyboard
operability, focus order, contrast, screen-reader semantics, and touch target size. Latency
perception: what is optimistic, what is spinners, what is skeleton, and what is blocked
behind a wait. Internationalization: strings, pluralization, right-to-left, date/number
formats. Responsiveness and breakpoints. What the user sees when things go wrong, in human
language, with a next action. **Required output:** a screen inventory plus a state matrix
(screen × state × what the user sees × how they recover).

### 4.26 Buttons & interaction affordances
Every interactive control: what it does, whether it is idempotent, whether it is destructive,
and whether it needs confirmation. What is disabled and why (a disabled control with no
explanation is a dead end for the user). Destructive actions: confirmation, undo, and
soft-delete windows. Debouncing, double-submit prevention, and what happens on a slow
connection when the user clicks twice. Keyboard shortcuts and their discoverability. Focus
management on navigation. **Required output:** a control inventory (control / effect /
idempotent? / destructive? / guard).

### 4.27 Sound & haptics
Is audio part of this product at all — and if yes, why (alert, confirmation, ambience,
accessibility)? Which events produce sound, and is it ever the *only* signal (accessibility
violation if yes)? Volume, mute, and the user's OS-level preference. Does the app behave
gracefully with no audio device? Haptics: which interactions, which platforms, and what
happens where unsupported? What is the file format, size, and license of each sound asset?
**Required output:** the audio decision (yes/no with a reason) and, if yes, the event→sound
table with format and license.

### 4.28 Messaging bus & events
Is there a bus at all — and if the system is two components talking directly, say so and skip
this. Topics/queues: names, owners, and payload schemas. Delivery guarantee per topic and why
that is sufficient. Ordering: per key, per partition, or none — and what relies on it. Dead
letters: where failures go, who watches, and how they are replayed. Replay and reprocessing:
can an event be re-consumed, and is the consumer idempotent? Schema evolution: additive only?
Consumer groups, lag, and what lag means for correctness. Retention on the bus. Poison
messages and the quarantine policy. **Required output:** a topic table (topic / producer /
consumer / delivery / ordering / DLQ / retention).

### 4.29 Networking
Ports and their exposure (and the difference between a wildcard bind address and a
loopback-only bind is a blast-radius decision — state it). TLS: terminated where, with what certificates, and how
they renew. Proxies, load balancers, and what they rewrite. Firewall and security-group
rules. DNS: names, resolution, TTL, and what happens on failure. Egress rules: what this
system is allowed to call out to. IPv4/IPv6. Service mesh or not. **Required output:** a
network topology with every inbound and outbound path named.

### 4.30 Configuration
Every knob, its type, its default, its valid range, and what it changes at runtime. Sources
and **precedence order** (a config bug is usually a precedence bug). Hot reload: what is
reloadable, what requires restart, and how restart is signaled. Validation: what happens with
an invalid config — fail fast at boot, or degrade? Secrets vs config: which is which, and
why. Per-environment divergence and how it is kept honest.
**Required output:** a config table (key / type / default / range / source / reloadable?).

### 4.31 Software design patterns — per feature, with the why
**This section exists because generated code without a plan goes badly.** For each significant
feature, name the pattern(s) it will use and **why that pattern and not the alternatives**.
At minimum consider where each applies: layering and dependency direction; ports-and-adapters
for anything external; repository vs active record for persistence; command/query separation;
event-driven vs request-response; state machines for anything with lifecycle; strategy vs
conditional branching; factory/DI for construction; circuit breaker and bulkhead for
resilience; saga/compensation for distributed transactions; middleware/pipeline for
cross-cutting concerns. For each: what the pattern buys here, what it costs (indirection,
ceremony), and **where its boundary is** — the point past which applying it further is
over-engineering. Name the anti-pattern you are avoiding.
**Required output:** a feature→pattern table (feature / pattern / why / alternative rejected /
boundary / anti-pattern avoided).

### 4.32 Frameworks, libraries, open-source research & "build less"
For each capability you need, before building it: **who else solved this, how, why did they
choose that, and why not our way?** Candidate set with license, maturity, last release,
issue-response signal, bus factor, and security posture. What existing work means we build
less — and what "less" concretely is (components, weeks, lines). What the dependency locks us
into. What we still build ourselves, and why the library does not cover it. Prior art beyond
libraries: blog posts, conference talks, post-mortems from people who tried this and failed —
what did they learn that we would otherwise pay to learn? **Every adoption claim needs a
baseline:** "we build less" compared to *what* — cite the baseline or the claim is marketing.
**Required output:** a candidate table (capability / candidate / license / maintenance signal /
what it replaces / what we still build) plus the prior-art findings with sources.

### 4.33 Integration strategy
For each external system: **direct integrate, adapter/bridge, sidecar, fork, or reimplement —
and why.** Direct is fastest and couples you hardest. A bridge costs indirection now and buys
a swap path later — and it is only worth it if the swap is plausible and the bridge interface
is stable. A sidecar isolates failure but adds a process. A fork is a maintenance liability
you have just adopted; say so out loud. For whichever you choose: where the seam is, what the
interface is, how the bridge is tested, and **what swapping costs** (time, data migration,
contract breaks). Does the integration need a capability the target does not have — and was
that verified by probing the actual thing, or assumed from documentation? **The driver-
capability rule: never assume a driver, library, or external system supports a feature —
probe it, and keep the transcript.**
**Required output:** an integration table (system / strategy / seam / interface / swap cost)
plus the probe transcripts for every capability you rely on.

### 4.34 Testing & what "works as expected" means
**Define "correct" before defining the tests.** For each requirement, the observable that
proves it, and the tolerance. Test levels: unit, integration, end-to-end, and what each is
responsible for (and what it is *not*). Fixtures and factories: how is test data built, and
is it deterministic? Determinism: time, randomness, network, and ordering must be injectable —
name the injection points. Flake policy: a flaky test is a bug; who quarantines it, and what
is the SLA to fix. Contract tests at every integration seam. What is deliberately not tested
and why. Performance tests: what envelope, measured how. The proof for each BEFORE-BUILD
decision: **every BEFORE-BUILD decision id must appear in an invariant→test map, or the gate
fails.** Test data privacy: no production data in tests, or an explicit, justified exception.
**Required output:** an invariant→test map (decision id / invariant / test / level) plus the
determinism injection list.

### 4.35 Observability of the test system itself
Do you trust the tests? What proves a test actually ran (not skipped, not vacuously passed)?
Coverage: measured, and does it gate anything? Retries hiding failures. CI: what runs on
which trigger, how long, and what blocks a merge. Test isolation: can tests run in parallel,
and do they share state? **Required output:** the CI gate list and the proof-of-execution
mechanism (exit codes, not log greps, are truth).

### 4.36 Performance & capacity
The numbers, with how they were derived: expected load, peak load, and 10× load. Latency
targets at p50/p95/p99, and which one the product actually feels. Throughput per component.
The first bottleneck at 1×, 10×, 100× — and what the mitigation is. Resource footprint per
unit of work. Measurement plan: what is benchmarked, on what hardware, and when it re-runs.
**Required output:** a capacity table (component / metric / now / peak / 10× / first
bottleneck / mitigation).

### 4.37 Cost & budget
Cost per unit of work (request, job, user, GB-month). Fixed vs variable. Monthly cost now,
and at 10×. The cost of the expensive path, and whether it is bounded. Third-party metered
services: what happens if usage spikes unexpectedly — is there a hard cap? The cost of
*operating* it (who spends time, and on what). **Required output:** a cost model with the
per-unit derivation and the 10× projection.

### 4.38 Vibe / product identity
What is this supposed to feel like — fast, calm, dense, playful, serious, invisible? What is
it explicitly NOT? Which adjectives must be true of every screen and response? Decode the
owner's phrases into technical constraints ("it should feel instant" → the 200ms budget;
"it should never lose my work" → write-ahead persistence). A design that satisfies the
register but violates the vibe is the wrong design. **Required output:** the vibe sheet —
IS / IS NOT / must-be-true adjectives / decoded phrases → constraints.

### 4.39 Documentation
Who reads which document, and when? What must exist for a newcomer to run this on day one?
Where does the documentation live, and how is it kept from rotting (is anything checked
against the code)? API docs: generated or handwritten? Runbooks: which operations need one?
**Required output:** a document inventory (doc / audience / when read / maintenance trigger).

### 4.40 Release, versioning & compatibility
Version scheme, and what a version bump promises. Compatibility policy: what may break, and
with what notice. Deprecation: how announced, how long supported, how removed. Changelog and
its discipline. Release cadence. **Required output:** the versioning policy and the
deprecation timeline.

### 4.41 Compliance, legal & licensing
Which regimes apply (privacy, data residency, financial, health, accessibility)? Data subject
rights: access, deletion, portability — and can the system actually execute each? Consent and
its record. Audit retention requirements. Licensing of your own code and of every dependency —
and whether any dependency's license contaminates the product. Terms and privacy policy: who
writes them, and when. **Required output:** an obligation table (regime / obligation / how
satisfied / evidence) and the dependency-license sweep result.

### 4.42 Failure modes, recovery & disaster
What is the worst realistic failure? For each major failure: detection, blast radius, recovery
procedure, and expected recovery time. Backups and their restore rehearsal. Data loss
tolerance: how much, and for how long? Degraded mode: what the system does when a dependency
is down — serve stale, queue, or fail loudly? Runbooks for the top failure scenarios.
**Required output:** a failure table (failure / detection / blast radius / recovery / RTO) and
the top-three runbooks.

### 4.43 Human-in-the-loop steps
Which steps need a person, at which point in the flow, with what SLA? What happens when the
person is absent — does the system block, degrade, or proceed with a default? What is the
audit trail for a human decision? Can the step be partially automated, and what is the
residual human judgment? **Required output:** a human-step inventory (step / who / SLA /
absent-behavior / audit).

### 4.44 The meta-domain — unknowns, assumptions, and what we are guessing
Known unknowns: what we know we do not know, with owners and deadlines. Assumptions: what we
are treating as true, what evidence supports it, what would falsify it, when that evidence
will exist, and which decisions break if the assumption is false. The guess ledger: where we
chose a number without measuring it, and what measuring it would cost. **Load-bearing
assumptions that are unmonitored are the project's top risks — name them as such.**
**Required output:** the assumption register (assumption / evidence / falsifier / when tested /
decisions affected / containment) and the known-unknown list.

---

## 5. The break-check pass

Run after the cascades, before the ledger. It is the step that makes the artifact a *design*
instead of a questionnaire with answers.

### 5.1 The pairwise walk

Walk each load-bearing decision against every other load-bearing decision. For the pair
`(D1, D2)`, ask:

1. Does D1 invalidate an assumption D2 makes?
2. Does D1 change the meaning or ownership of data D2 depends on?
3. Does D1 make D2's chosen design pattern inappropriate?
4. Does D1 create a state or ordering D2's concurrency protection does not cover?
5. Does D1 turn a reversible choice in D2 into an irreversible one?
6. Does D1 move a bottleneck D2's capacity plan was sized against?
7. Does D1 open an exposure D2's security model does not cover?
8. Does D1 add operational work D2 assumed nobody would do?
9. Does D1 contradict something D2 asserts to the user?
10. Does the pair still serve the product core — or has one drifted off it?
11. Does D1 make D2's test strategy lie (a test that can no longer fail)?
12. Does D1 imply D2 must ship in a different order?

**Full pair set first, sparsification second.** Generate the complete pair set for
load-bearing decisions; you may then skip pairs only with a recorded justification
(`skipped: both reversible, no shared data, no shared resource`). "The cross-product is
unnecessary" is not a justification — it is how break-checks get skipped.

For large decision sets (>25 load-bearing), a sparse high-risk matrix is acceptable **after**
the full set is enumerated and the skip rule is recorded.

**Precedence against the clock.** The pair walk and the domain cascades compete for the same
budget, and the walk is not free (n load-bearing decisions is n(n−1)/2 pairs — 190 at n=20).
Order it:

1. Enumerate the full pair set first — always, because the enumerated set is what proves the
   walk was comprehensive, and it is cheap.
2. Then run pairs in blast-radius order: pairs where a break would be irreversible or
   cross-domain first, reversible same-domain pairs last.
3. If the budget runs out mid-walk, record `pair-walk-partial: <n> of <m> pairs run` in the
   break-report and the gate read. A recorded partial walk is honest; an unrecorded one is
   the shallow-matrix tell. **Never silently drop pairs to make the clock.**
4. Never let the walk consume the budget a BEFORE-BUILD domain still needs — the domain
   cascade produces the decisions the walk operates on; a walk over a thin matrix is
   expensive theatre.

### 5.2 Outcome taxonomy

Every pair resolves to one of:

- **BLOCKS** — D2 cannot be implemented as written. One must change. Record which.
- **REQUIRES-REDESIGN** — D2 is implementable but wrong. Record the redesign.
- **ACCEPTED-COST** — the tension is real and accepted. Record who accepts it and why.
- **MITIGATED** — a change removes the tension. Record the change.
- **UNKNOWN** — cannot resolve without evidence. Becomes an unknown with an owner.
- **NO-INTERACTION** — checked, nothing shared. Legal only with the checked-against list.

### 5.3 The modification rule

**A break-check that modified nothing is a break-check that was not run.** On a real project
the pass modifies decisions, opens new ones, or closes others. If your report is uniformly
`NO-INTERACTION` across every pair, the pass did not happen; go back and look harder at
shared data, shared resources, and shared failure modes.

This is a **pass-level** test, not a per-pair one — §5.5 states the distinction and why
requiring per-pair modification would manufacture false changes.

### 5.4 Cycles

If the walk finds a loop (D1 breaks D2, D2 breaks D3, D3 breaks D1), do not pick a winner
arbitrarily. A break cycle means one of three things: a decision is over-scoped, two decisions
are actually one, or there is an unstated invariant all three are circling. Collapse the
over-scoped decision, promote the shared constraint to an explicit invariant, then re-run the
walk over the affected set.

### 5.5 The mandatory `breaks` field

Every decision row carries `breaks` as **structured fields, not one prose string** — the
validator has to read it, and a regex over English is not a check:

```yaml
breaks:
  - outcome: NONE | BLOCKS | REQUIRES-REDESIGN | ACCEPTED-COST | MITIGATED | UNKNOWN
    target: D-### | IV-### | IF-### | <layer name from §4>   # what it breaks (or was checked against)
    how: "<how it breaks — or the checked-against list item when outcome is NONE>"
    changed: "<what the pass modified as a result>"          # required unless outcome is NONE
    accepted_by: "<who accepts it>"                          # required only for ACCEPTED-COST
```

- `outcome: NONE` entries are the **checked-against list** — one entry per layer/decision you
  looked at and found nothing. An empty list is not "nothing broke," it is "nothing was
  checked."
- `changed` is required for every non-`NONE` outcome: a break with no consequence recorded is
  a break that was discovered and then ignored.
- A decision whose `breaks` is empty, absent, or all-`NONE`-with-no-`target` fails the gate.

The prose form below is for *reading* in the break-report; the register always carries the
structured version:

```text
breaks: none — checked against <explicit list of layers/decisions>
      | <component>: <how it breaks> → <outcome from 5.2> → <what changed>
      | <invariant>: <violation> → <outcome>
```

**Pass-level vs pair-level modification.** The §5.3 rule ("a break-check that modified nothing
was not run") is enforced at the **pass** level, not per pair: it is entirely normal for most
pairs to end in `NONE` or `NO-INTERACTION`. What is not normal is a *whole pass* in which no
decision anywhere was modified, no new decision opened, and no unknown created. Judge the pass
by its totals, never by an individual pair — requiring every pair to modify something would
manufacture changes that were not real.

### 5.6 The contradiction register

Two decisions that cannot both be true, two seeds that contradict each other, or a seed that
contradicts what the cascade derives — these are **first-class tracked objects**, not prose.
Every one gets a row, because an untracked contradiction is a decision the project makes by
accident.

```yaml
id: C-###
kind: decision-vs-decision | seed-vs-seed | seed-vs-derivation | assumption-vs-evidence
parties: [D-###, D-###]        # or [ESC-###, A-###] — whatever is in conflict
competing_claims:
  - "<claim A, in the imperative>"
  - "<claim B, in the imperative>"
evidence: []                   # what supports each side
affected_decisions: [D-###]
detected_by: §5 break-check | §10.1 brownfield diff | cascade | owner seed | probe
owner: "<who resolves or accepts>"
containment_default: "<what the run does meanwhile, and its expiry condition>"
status: OPEN | RESOLVED | ACCEPTED-COST | SUPERSEDED
resolution: "<what was decided and how>"     # required when status != OPEN
resolved_date_or_trigger: ""                 # required when status != OPEN
```

Rules:

- **A contradiction is never blended.** Do not average two conflicting answers into a
  compromise nobody chose. Record both, pick a winner or escalate, and say which won.
- **A contradiction that changes a BEFORE-BUILD decision is itself BEFORE-BUILD** — it blocks
  the build until resolved or defaulted.
- **Seed-vs-derivation is escalated, not overruled.** If the core recursion shows the owner's
  stated need is not what they need (§10.5), that is `kind: seed-vs-derivation` and it becomes
  the run's highest-priority escalation. Continue on the branch serving the *stated* need
  until answered.
- **Every `OPEN` contradiction appears in `_index.md`** and blocks handoff readiness.
- The break-report (`design/04-break-report.md`) carries the *walk*; the contradiction
  register carries the *objects*. A conflict named in the walk with no `C-###` row is not
  tracked.

---

## 6. Tradeoff ledger & escalation

### 6.1 Ledger row

One row per contested choice. Every field is mandatory; `null` is a decision, not a blank.

```yaml
id: T-###
question: "<the choice being made, in one line>"
core_link: "<which user need from the core statement forces this choice>"
classification: BEFORE-BUILD | BEFORE-SHIP | DEFER-WITH-OWNER
candidates:
  - name: A
    advantages: []
    costs: []                 # money, time, complexity, maintenance
    breaks: []                # with the checked-against list, or the break text
    evidence: []              # measured value with source, prior art, or "guessed"
    assumptions: []           # ids of assumptions this option rests on
    reversal_path: ""         # how we switch away
    reversal_cost: low | medium | high | effectively-irreversible
  - name: B
    ...
dominated: []                 # candidates eliminated, and why (one line each)
hinge_axis: "<the single axis that actually separates the survivors>"
recommendation: "A | B | escalate"
why: "<evidence-based reasoning, not preference>"
confidence: high | medium | low
dedup_key: "<normalized signature — prevents re-litigating the same choice>"
escalation_id: E-### | null
```

### 6.2 Weighting axes — labels, not scores

Compare only the axes that could decide *this* choice. Name the hinge; do not produce a
scorecard where irrelevant axes dilute the real question.

Time-to-first-value · portability and lock-in · operational burden · blast radius ·
reversibility · competence of the humans and agents who must maintain it · direct and
indirect cost · compliance · future optionality · maintenance surface · performance headroom ·
reliability · security · user experience · testability · ecosystem health.

### 6.3 Compare without false precision

Use: measured values with sources; bounded ranges; ordinal ratings **with published
definitions**; scenario comparisons; explicit uncertainty; dominance ("B loses on every axis
the core cares about → drop B").

**Never assign a numeric score to a tradeoff axis — not 1–10, not four-decimal, not with a
rubric.** A numeric scorecard on these axes is false precision by construction: the axes are
judgment-laden and unitless, so any number is a preference wearing a lab coat, and it hides
the judgment it actually made. State the judgment instead. Escalation is triggered by §6.4's
priority test, never by two scores coming out equal. Where a number *is* available it is a
measured fact with a source, and it belongs in `evidence` — not in a score column.

The one numeric score in this method is the **§1 domain triage integer** (`blast_radius ×
uncertainty × irreversibility`, 1–3 each). That is budget allocation over domains, not a
comparison of tradeoff axes, and the three factors are defined — it stays.

Prefer:

> Option A requires one platform-specific adapter and preserves the file format. Option B
> embeds a proprietary control plane and requires data export plus workflow migration.
> Therefore B has materially higher reversal cost.

**Separate facts from preferences.** "A has lower p95 in the probe" is evidence. "That
latency matters more than portability" is a priority judgment — and priority judgments are
exactly what escalates.

### 6.4 Escalation criteria — all must hold

1. At least two candidates satisfy the hard requirements, neither is wrong.
2. The deciding axis is a **priority, risk appetite, resource allocation, or product-identity
   judgment** that lives with the owner — not a fact you could research or probe.
3. Getting it wrong is materially costly and not quickly reversible (or it shapes identity).
4. Existing evidence and seeds do not resolve the priority.

**If any fails: you decide, record it, and move on.** Escalating a question you could have
answered by reading the code, the docs, the schema, or the hardware is a defect in this
skill's output — it converts your work into the owner's homework. Cap escalations per run at
**five**; if you have more, you are misclassifying researchable questions as priorities.

### 6.5 Escalation question shape

Comparative, one-line answerable, options attached with costs, and a default if unanswered.

```
ESC-nn: <the priority question, one line>

  Option A — <name>: favours <axis>. Costs <...>. Commits you to <...>. Breaks <...>.
  Option B — <name>: favours <axis>. Costs <...>. Commits you to <...>. Breaks <...>.

  Our read: <which axis decides it, and what we would pick if forced, and why>.
  If unanswered by <date/trigger>: we proceed with <default>, because <reason>.
  Risk of that default: <what goes wrong if the default is wrong>.
```

Never a bare question. Never a wall of options with no recommendation. Mark the default as a
default so silence has a documented consequence rather than a silent one.

*Example:* "Is portability off a single managed database more important than fastest
time-to-first-value for v1? A) managed relational — fastest to ship, higher lock-in, migration
later is a real project. B) self-hosted compatible engine — portable, costs one to two weeks
of operational work now. Our read: if v1 must ship for a demonstration, time-to-value decides
it; if this must survive a vendor change, portability does. If unanswered by the build start:
we proceed with A, because the schema is standard and B remains reachable."

### 6.6 Unanswered non-priority questions

Become **recorded unknowns**, never silent defaults:

```yaml
id: U-###
question: ""
why_unanswered: ""
owner: ""                     # if none exists, the executing agent owns closure before handoff
deadline_or_trigger: ""
blocking_class: BEFORE-BUILD | BEFORE-SHIP | DEFER
containment_default: ""       # the provisional answer, and its expiry condition
evidence_to_close: ""
decisions_affected: []
```

A provisional answer is a decision with a short lease — record its expiry condition. **Silence
must never be indistinguishable from a decision.**

### 6.7 When the owner is absent entirely

If the run must proceed with no owner available, apply the autonomous-mode policy: choose the
**most reversible** option for every escalated decision, record it with
`provisional: true` and the containment default, and mark the escalation for review on the
owner's return. Never choose the irreversible option by default. The artifact header records
`autonomous-mode: true` and counts the provisional decisions, so the owner sees exactly what
was assumed.

---

## 7. The artifact

One directory (convention: `design/` or project-equivalent). Each file stands alone and
cross-references the others by id.

### 7.0 The artifact directory is single-writer

**One run owns the artifact directory.** Two concurrent runs — or one coordinator plus a
partially-steered seat, or two agents sharing a worktree — will overwrite each other's
register files, and the loss is silent: the surviving artifact looks complete while rows from
the other writer are simply gone. This is not hypothetical; it is a measured failure mode of
runs that share a working directory.

- **One writer per artifact directory.** If two runs must share a host, give each its own
  directory (`design-<run-id>/`) and merge deliberately, never concurrently.
- **Stage, then publish.** Write to `design/.staging-<id>/` and move the finished tree into
  place in one step. An artifact that appears by halves is worse than one that appears late.
- **A run that needs to resume** takes the directory it already owns; it does not start a
  second concurrent writer.
- **The gate read records the writer.** `_index.md` names the run id and the write window, so
  a downstream consumer can tell whether two writers ever overlapped.
- The reference validator (§7.6) should write a `run.json` marker (run id, start, last write)
  beside the registers; a mid-run change of that marker is the collision tell.

### 7.1 Files and order

```
design/00-seed.md              owner's intent verbatim, non-negotiables, hard/soft constraints
design/01-scope.md             core statement, IN list, OUT list with reasons, unknown scope
design/02-domains/             one file per domain: answers, decisions, unknowns, ring depth,
                               required output. NOT-REACHED domains carry reason + owner
design/03-decisions.md         the decision register (§7.3)
design/04-break-report.md      the pairwise walk: conflicts, outcomes (§5.2), supersession
                               chains, what the pass modified
design/05-contradictions.md    the contradiction register (§5.6) — C-### rows
design/06-tradeoff-ledger.md   §6.1 rows
design/07-escalations.md       ESC-nn envelopes + provisional decisions
design/08-open-questions.md    U-### rows
design/09-assumptions.md       assumption register with falsifiers and monitoring
design/10-research.md          prior art, candidates, probe transcripts, measured numbers
design/11-humans.md            human-in-the-loop inventory + contact/escalation map
design/12-vibe-sheet.md        IS / IS NOT / must-be-true / decoded phrases. Write LAST.
design/13-handoff.md           the handoff contract (§7.5)
design/14-core-checks.md       the core-check rows (§7.2) — one per branch
design/15-invariant-test-map.md  the decision→invariant→test map (§4.34) — one row per
                               BEFORE-BUILD decision, or the §7.6 gate cannot be satisfied
design/_index.md               the gate read (§7.4)
design/matrix.schema.json      machine-readable schema for the register (§7.6)
```

**Two files exist explicitly to satisfy the gate.** The validator (§7.6) fails an artifact
that has no core-check rows and no invariant→test map, so a run that emits every other file
and skips these two has produced an artifact that *cannot* pass its own self-gate. If either
is legitimately empty (no BEFORE-BUILD decisions yet), write the file with an explicit
`empty — because <reason>` line. An absent file and an empty file are different failures;
only the second is legal.

A single-file artifact may use the same section order, preserving stable ids.

### 7.2 The core-check record (mandatory per branch)

The recursion-to-core mechanic is worthless if it is not recorded. Every branch that ran a
core check emits a row:

```yaml
id: core-check-###
branch: "<which decision branch>"
user_class: "<who>"
jtbd: "<the job-to-be-done, in the user's words>"
why_needed: "<the causal chain from this branch to the user's need>"
result: keep | simplify | prune | escalate
delta: "<what decision changed as a result — or 'no change' with what was re-confirmed>"
evidence: "<seed quote, probe, or source that supports the result>"
```

**A branch with no core-check row fails the gate.** "We considered the core" is not a record.

### 7.3 The decision register

One row per decision:

```yaml
id: D-###
statement: "<the decision, in the imperative>"
branch: "D-### | domain:<§4.n> | cascade:<id>"   # what this decision descends from
ring: <the ring at which it was decided>
terminating_ring: <int> | "fixed-point-below-floor:<N>" | "depth-ceiling-reached" | null
classification: BEFORE-BUILD | BEFORE-SHIP | DEFER-WITH-OWNER
alternatives_considered: []
evidence: []
breaks: "<§5.5 form>"
assumptions: [A-###]
depends_on: [D-###]            # the propagation graph — what must be re-checked if this moves
contradicts: [C-###]           # links into §5.6
core_check: core-check-###
supersedes: D-### | null
superseded_by: D-### | null
reversal_cost: low | medium | high | effectively-irreversible
owner: "<who is accountable>"
```

`depends_on` is what makes §10.2's invalidation walk possible: without it, dependents are
unenumerable and a changed decision leaves the artifact silently wrong.

### 7.4 `_index.md` — the gate read

Artifact purpose · product core (one line) · domain completion counts (answered /
NOT-REACHED) · cascade closure counts (domains terminated, list of terminating rings,
`fixed-point-below-floor` count, `depth-ceiling-reached` count) · decision, tradeoff,
escalation, unknown, assumption, and contradiction counts · **open contradictions (C-###
ids)** · provisional decisions count · blocking unknowns · pending owner escalations · last
evidence refresh · **handoff readiness: READY | NOT-READY with the blocking list**.

Handoff readiness is the headline the downstream stage reads. It is not a vibe: it is
computed from the counts above, and it is NOT-READY if any BEFORE-BUILD unknown is open, any
escalation is unanswered and unresolved, or any contradiction is `OPEN`.

### 7.5 The handoff contract

- **Fixed** — decisions the spec stage may treat as settled, with their ids.
- **Investigate** — what the spec stage must still resolve, with the reason it was left
  (out of scope for this pass, needs a probe, needs a human).
- **Open** — links to escalations and unknowns, with impact if unresolved.
- **Invalidation** — the observations that would invalidate this design *wholesale*, and what
  to re-run if they occur.
- **Consumption contract** — what the spec stage must produce from each section (contracts,
  acceptance criteria, task seeds) and what it may never redefine.

### 7.6 Machine-readable schema and self-validation

`matrix.schema.json` defines the register shapes above (decisions, tradeoffs, escalations,
unknowns, assumptions, core-checks, contradictions) with required fields, id formats, and
cross-reference integrity rules. **Ids are regexes, not examples:** `D-\d{3}`, `T-\d{3}`,
`ESC-\d{2}`, `U-\d{3}`, `A-\d{3}`, `C-\d{3}`, `core-check-\d{3}` — zero-padded to a fixed
width, so `core-check-1` and `core-check-001` are the *same* id and a collision is detectable.
An id namespace that admits both spellings silently merges two registers.

The self-gate (§8) runs a validator — an executable check, not a reading exercise — that
fails on:

- any decision missing `alternatives_considered` (≥2) or a non-empty `breaks`;
- any `breaks: none` without a checked-against list;
- any decision missing `depends_on` or `reversal_cost`;
- any BEFORE-BUILD decision id absent from the invariant→test map;
- any branch without a `core-check` row;
- any escalation without options, costs, and a no-answer default;
- any unknown without an owner, a deadline/trigger, and a containment default;
- any contradiction with `status != OPEN` but no `resolution` and
  `resolved_date_or_trigger`;
- any `OPEN` contradiction not listed in `_index.md`;
- any dangling id reference (`supersedes`, `superseded_by`, `depends_on`, `assumptions`,
  `core_check`, `escalation_id`, `contradicts`, `parties`, `affected_decisions`);
- any branch that terminated below its floor without a `fixed-point-below-floor` record;
- any domain absent from the artifact entirely (a NOT-REACHED row is required, not silence).

The validator is the difference between an artifact and shelfware for an agent-fleet
consumer: a downstream worker lints this file before touching the project. **A runnable gate
ships beside this skill:**

```bash
python3 <skill-dir>/scripts/validate.py <design-dir>     # exit 0 = PASS, 1 = FAIL
```

It reads the markdown registers directly — YAML blocks, markdown tables, and the headed
escalation envelopes — so no JSON export is required, and it uses only the standard library.
Copy it into the run's tooling or call it from where it lives; the report names every failure
with its row id. A **starter `matrix.schema.json` also ships beside this skill** — copy it
into `design/` and extend the register objects for the project, keeping the id patterns and
required fields or the checks cannot run. The schema validates *shape*; `validate.py` covers
the referential and coverage rules (dangling ids, "every BEFORE-BUILD decision appears in the
test map", "every OPEN contradiction is listed in `_index.md`", exact 44-domain coverage).
Use both. Treat a validator you cannot run as a claim, not a check.

### 7.7 Confidentiality

The matrix reads real schemas, configs, and secret *locations*. It therefore inherits the
project's confidentiality, and more strictly: **the artifact must not be committed to a
public repository, even when the project itself is public.** A private project's matrix can
contain schema excerpts, infrastructure facts, hostnames, identity models, and secret
locations; a public project's matrix can too, plus internal reasoning its authors never
intended to publish. Publication requires a **separate sanitization gate** that proves
project-specific schema, infrastructure, paths, identities, and secret locations were
removed — the artifact that passes that gate is a different artifact from the one this skill
produces. **Never record an actual secret value in the artifact — reference the secret's
location, never its content.**

---

## 8. Quality gates & anti-patterns

### 8.1 Shallow-matrix tells

Any of these means you are not done:

- domains present as headings with no questions answered;
- decisions stated as verdicts with one option listed;
- `breaks` empty or uniformly `none` with no checked-against list;
- escalation questions that ask the human to do your research;
- a ring-1 (or ring-2) matrix presented as complete;
- answers identical to what a generic project of this type would have;
- a battery copied from another project without a single project-specific answer;
- a "done" claim with no terminating ring recorded;
- a tradeoff with fabricated numeric scores;
- a question dumped on the human with no options, costs, or recommendation;
- an assumption with no falsifier;
- a decision with no reversal cost stated.

### 8.2 The anti-gaming rule

**A matrix that could have been produced without reading the actual project — the existing
systems, the schema, the config, the hardware spec, the operator's real workflow — is
worthless by construction.** Your output must contain **evidence handles** that only exist
because you looked at *this* system: file paths, probe transcripts, schema excerpts, service
listings, measured numbers, the owner's own words.

The test: *if every project-specific claim could be replaced by a generic one without
changing the document, delete the document and go look.*

### 8.3 The two forbidden output shapes

- **The questionnaire.** A document that hands the human a list of questions to answer. The
  agent asks itself; the human gets at most five seeds and the escalations.
- **The design doc that never decides.** A beautiful exploration with no `recommendation`
  field populated anywhere. Exploration without a recommendation is a failure to reason —
  every ledger row must carry a recommendation or an escalation, never a shrug.

### 8.4 Depth is evidence, not decoration

Record the terminating ring per domain. Depth rings are the difference between "I asked a
few questions" and "I interrogated this until nothing was left." A domain that stopped early
with a reason is honest; a domain that stopped early silently is a defect.

---

## 9. Pitfalls

- **The questionnaire.** Handing the human the batteries. The whole point is self-interrogation.
- **Cascade theater.** Generating fifty questions per ring without descending any of them.
  Five good derived questions, answered, beat fifty unasked.
- **Depth without core recursion.** A thorough document about the wrong product. Every ring
  climbs back to the core.
- **False precision.** "8.4/10 portability." State the judgment instead of hiding it in a number.
- **Break-check as a formality.** Uniformly `NO-INTERACTION`. A pass that modified nothing did
  not run.
- **Silent defaults.** An unanswered question that quietly becomes an assumption. Every one
  becomes a row with an owner.
- **The unfalsifiable assumption.** An assumption with no observation that could kill it is a
  belief, not an assumption; it belongs in the risks list.
- **Verdict without alternatives.** A decision with one candidate is not a decision.
- **Copying the worked examples.** The cascades in §3.5–§3.7 are a shape, not content.
- **Recording secrets.** Reference the location, never the value.
- **Unbounded depth.** Ring 5 on a low-stakes domain is not diligence; it is budget theft from
  the domains that matter.
- **Stale decisions.** The register is an append-log with supersession chains, not an
  overwrite. Never delete a decision that changed; show that it changed.
- **Refusing to decide.** Escalating researchable questions converts the agent's job into the
  owner's homework.
- **Terminating on boredom.** "Seems obvious" is truncation. Terminate on the fixed point.

---

## 10. Re-entry — running the matrix on a live project

The matrix is not a one-shot document. When the project changes, the register changes with it.

### 10.1 Brownfield (the project already exists)

Before any cascade, **read the system**, then **diff the matrix against reality**. Every
existing decision is a decision already made, whether or not anyone wrote it down.

Run it as a procedure, not an instruction — the walk mirrors §10.2:

1. **Inventory** the existing system: schemas and migrations, config files and defaults,
   service/process listings, dependency manifests and lockfiles, deploy and CI truth (what
   actually runs, not what the README claims), infrastructure as code, and the failure
   history (incidents, retries, alert noise).
2. **Extract the baseline decisions** — one `D-###` row per decision the system has already
   made, each with `detected_by: §10.1 brownfield diff` and `evidence` pointing at the file,
   schema, or config that proves it.
3. **Interrogate each baseline row exactly as if it were a proposal** — alternatives, breaks,
   reversal cost, core link. Being already-built is not a reason.
4. **Diff against descriptions.** Where the code says one thing and the operator's account,
   the README, or the docs say another, that gap is the finding — record it as a `C-###`
   contradiction (`kind: decision-vs-decision`) rather than picking a side.
5. **Write the output where §10.2 writes**: baseline rows into the decision register, gaps
   into the contradiction register, and anything the system does that no domain in §4
   anticipated into the nearest domain with a note.

The most valuable rows in a brownfield run are exactly those step-4 gaps.

### 10.2 Change propagation — the invalidation walk

When a decision changes (a human answers an escalation, a probe falsifies an assumption, or a
break-check reverses a call):

1. Mark the changed decision `superseded_by: D-###`; append the new row. Never overwrite.
2. Traverse the dependency edges: `assumptions`, `breaks`, `decisions_affected`, and any
   decision whose `core_link` or `alternatives_considered` referenced it.
3. Reopen the affected cascade leaves in each touched domain.
4. Re-run the break-check pairs that included the changed decision.
5. Recompute the invariant→test map for affected BEFORE-BUILD decisions.
6. Recompute handoff readiness in `_index.md`.

**A decision that moves without an invalidation walk leaves the artifact silently wrong** —
which is worse than useless, because the downstream stage trusts the `Fixed` list.

### 10.3 Re-run triggers

Re-run the whole matrix when: a falsifier fires; a BEFORE-BUILD decision reverses; an
assumption the core depends on is disproven; the product core statement changes; a domain's
triage score rises above its last ring floor; or more than a defined number of new decisions
accumulate without a break-check pass. Otherwise patch in place via 10.2.

### 10.4 Checkpointing a long run

A matrix run can exceed a single context window. Persist after every domain: the ring cursor
per domain, the open-unknown queue, the decision ids issued, and the core statement (hashed,
so drift is detectable on resume). On resume, verify the core hash matches before continuing —
a resumed run under a changed core is a different project's matrix.

### 10.5 Seed and budget problems

- **Empty seed.** Produce a minimal viable matrix from the domain grid's MUST-ANSWER-BEFORE-BUILD
  questions, escalate the core statement itself, and mark the run `seed-thin: true`.
- **Budget-thin run** — a clear seed but a short clock (a bounded run, a paid-ceiling run, a
  run the owner capped). This is NOT seed-thin: the seed is fine, the budget is not. Mark the
  run `budget-thin: true`, run domains in triage order, and let the unreached domains carry
  `NOT-REACHED` rows. A budget-thin run is a legitimate, expected deliverable — it is the
  difference between an honest partial matrix and a fabricated complete one.
- **Contradictory seed** (e.g. "fast" and "fully tested" under a fixed deadline). Do not
  silently pick one. Record the contradiction as its own escalation with both readings, and
  proceed with the containment default on every branch that depends on it.
- **Hostile or absurd seed.** Say so plainly in the artifact and in the escalation. A matrix
  built to satisfy a request you believe is wrong is worse than no matrix.
- **Seed contradicts what the cascade derives.** If the core recursion shows the owner's
  stated need is not what they need, **do not silently override the owner and do not silently
  serve the seed.** Escalate it as the highest-priority question in the run, present the
  derivation, and continue on the branch that serves the *stated* need until answered — while
  recording the derived alternative as `provisional: true`.

---

*Questions in questions in questions, until nothing is left to ask — and then one question to
the human, because only they can weight what matters more.*

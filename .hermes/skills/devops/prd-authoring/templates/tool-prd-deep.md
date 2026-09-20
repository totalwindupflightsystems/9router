# PRD: `<tool-name>` — <one-line identity>

**Project:** <owning project> · **Item:** <code> · **Author:** <agent> · **Date:** <date>
**Status:** proposed | approved | deferred · **Effort:** S | M | L · **Depends on:** <tools/repos> · **Feeds:** <consumers>

---

## The one-liner
One sentence: what it is and the single question it answers.

## Why the first version was too narrow   *(include only when superseding a draft)*
List the questions the previous framing could not answer. This section earns trust and prevents re-litigating scope.

## The core insight: <the state model>
Table of the 2-3 states whose EDGES cause the incidents (e.g. declared / on-disk / in-process). For each, name the real incident that lived on that edge. Say explicitly what a naive implementation sees instead.

## Taxonomy (what "X" actually means)
Numbered classes, each with a one-line definition and a real example. Group them (content / value / runtime / lifecycle). Mark the ones that would have caught your own recent incidents.

## <Mechanism> — the detection/derivation probe   *(when the user supplied the mechanism, name the section after it as their contribution)*
Numbered steps: enumerate targets → what to read → what to compare → outcome verdicts → edge cases → policy that converts a verdict into severity and an action. Include a **live measurement table** (what the probe found on a real box, including false positives it exposed) and an explicit limits paragraph (what it cannot see and why).

## The feedback loops
One subsection per loop: `### Loop N — <name> (<timescale>): trigger → step → step → closure`. Each states: what closes an item, what re-escalates it, and what it feeds. Include the learning/compounding loop and the accuracy loop (precision floor → demote).

## Lifecycle state machine
ASCII or arrow list: observed → classified → notified → {accepted, reconciled, escalated} → closed; plus stale/recurring branches. Note that every transition is an append-only event.

## Scope
Input adapter table (what it reads / what it answers / what it cannot), then explicit **out of scope** with the reason.

## User stories
3-6: "As a <role>, I <action> and get <result>." At least one per persona (responder, operator, new-joiner, auditor).

## Acceptance criteria
MANDATORY block, above the success criteria. One AC per user story minimum; each runnable without interpretation.

| AC | Given | When | Then (observable) | Proof | Type |
|----|-------|------|-------------------|-------|------|
| AC-1 | <state> | <action> | <result> | `<test>` green | T |
| AC-2 | <state> | <action> | <result> | `<cmd>` prints `<exact>` | C |
| AC-3 | <state> | <action> | <result> | <artifact / counter >= N> | M |

- Type: T = automated test, C = command/probe with expected output, M = manual artifact that must exist.
- At least one anti-gaming AC a green-but-did-nothing implementation cannot pass.
- Every design rule that claims "never X by construction" gets the AC that proves it (constant-surface, no-state-reuse, capability-error tests from the session-scoping rules).
- ACs transfer VERBATIM into the board row's `acceptance_criteria` and the worker brief.

## Success criteria
Each as a REPLAYABLE PROOF against real history: "replay incident X → the check fires / the query returns the signature / the drill passes". Plus budget/overhead proofs (measured, with the measurement method) and one anti-lying criterion (the system cannot emit an unproven claim).

## Risks & failure modes
Per risk: the mechanism and the mitigation that is a design rule, not an intention.

## Cost & shape
Effort, what ships first, dependencies, and the sequencing note (what is blocked on what).

## What it is NOT
Hard boundaries — the things this tool will never do, so scope creep has a named wall.

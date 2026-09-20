# Dogfood artifact — a real run's output

This directory is the **complete artifact one seat produced** by executing the skill on a
one-paragraph seed. It is here as a worked example, and its shape is the thing to imitate —
**not** its content. Copying these decisions into another project is exactly the anti-gaming
failure §8.2 describes.

## What is here

```
00-seed.md, 01-scope.md        the owner's words verbatim, then the frozen core statement
02-domains/ (44 files)         one file per domain: battery, cascade, decisions,
                               break-check result, core check, required output,
                               terminating ring — or NOT-REACHED with reason and owner
03-decisions.md                the decision register (§7.3)
04-break-report.md             the pairwise walk and its outcomes
05-contradictions.md           the contradiction register (§5.6)
06-tradeoff-ledger.md          §6.1 rows
07-escalations.md              escalation envelopes, with defaults and named risks
08-open-questions.md           §6.6 unknown rows
09-assumptions.md              assumptions with falsifiers
10-research.md                 prior art + probe transcripts from the real run
11-humans.md                   human-in-the-loop inventory
12-vibe-sheet.md               IS / IS NOT / decoded phrases
13-handoff.md                  the handoff contract
_index.md                      the gate read
matrix.schema.json             the run's own schema export
tools/validate.py              the run's own validator
_validate-output.txt           that validator's output: PASS, with counts
```

## Read this before running the validator

`scripts/validate.py` **in the skill directory** is the runnable §7.6 gate. Point it at any
design tree:

```bash
python3 <skill-dir>/scripts/validate.py <design-dir>    # exit 0 = PASS, 1 = FAIL
```

It reads the markdown registers directly (YAML blocks, markdown tables, and headed escalation
envelopes) — no JSON export needed, stdlib only. Run against this directory it returns:

```json
{ "status": "PASS",
  "counts": { "decisions": 24, "tradeoffs": 9, "escalations": 2, "unknowns": 5,
              "assumptions": 8, "contradictions": 1, "core_checks": 9, "domain_files": 44 },
  "errors": [] }
```

Those counts are independently reproduced by the run's own validator output in
`_validate-output.txt` (kept here as the run's evidence). Two independent readers agreeing on
every count is the check; one reader agreeing with itself is not.

The validator was also negative-tested: deleting a domain file, stripping a decision's
alternatives, injecting a dangling `depends_on`, and duplicating an id each produce a FAIL with
the right named error — so a PASS here is evidence, not a tautology.

## What the run established (why it is worth reading)

- **The cascade grammar generates.** The closing ring's candidate questions were re-derived
  and shown to be duplicate signatures — the fixed point is reached by measurement, not by
  feeling done.
- **The break-check modifies.** Several decisions here were changed by the walk, and the
  changes trace to probe measurements rather than opinions. Read `04-break-report.md`
  alongside `10-research.md` to see a measurement forcing a decision.
- **The owner stayed out of the questionnaire seat.** Every open item is a register row with
  an owner, a trigger, and a containment default; the escalations carry options, costs, and a
  no-answer default. Nothing here is a question waiting for a human to do the work.

One seat disclosed a bug in its own probe (a reported `LOST=25` was a tuple-coercion error;
the corrected run measured 0 lost events across 8 SIGKILLs) and kept both runs logged rather
than dropping the bad number. That is the behavior §8.2 is meant to produce.

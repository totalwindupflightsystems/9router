# _index — Gate read

Artifact purpose: pre-spec design substrate for a single-host file-change recorder and hourly digest CLI.

Product core: one supervised local process reconciles configured directories, transactionally remembers committed metadata changes, and durably posts bounded hourly digests without claiming observation outside its physical boundary.

Mode: autonomous (`owner_available: false`). Provisional decisions: 3 (D-014, D-017, D-023).

## Domain completion

- §4 domains: 44.
- CASCADED: 9 — 4.5, 4.6, 4.19, 4.20, 4.42, 4.44, 4.4, 4.12, 4.17.
- NOT-REACHED with reason/owner/trigger/containment: 35.
- Cascades terminated by fixed point: 9.
- Terminating rings: all nine at ring 5.
- `fixed-point-below-floor`: 0.
- `depth-ceiling-reached`: 0.
- Domains silently absent: 0.

## Register counts

| Register | Count |
|---|---:|
| decisions | 24 |
| tradeoffs | 9 |
| escalations | 2 |
| unknowns | 5 |
| assumptions | 8 |
| contradictions | 1 |
| core checks | 9 |

Open contradictions: C-001.

Blocking BEFORE-BUILD unknowns: U-004.

Pending owner escalations: ESC-01, ESC-02. Each is comparative, has costs and a recommendation, and has an autonomous no-answer default.

Last evidence refresh: 2026-09-20T12:48Z. Project-specific handles: `<scratch>/design-sandbox/probes/rename-b`, `<scratch>/design-sandbox/probes/core-statement.txt`, and the recorded exercise-host version probes in `10-research.md`.

Break-check: 66/66 load-bearing pairs enumerated; 22 substantive; 44 checked NO-INTERACTION; 8 pre-existing decisions modified; one semantic cycle collapsed into D-024/C-001.

Invariant→test map: every BEFORE-BUILD decision appears in `03-decisions.md`.

## Handoff readiness

NOT-READY.

Computed blockers under §7.4:

1. U-004 is an open BEFORE-BUILD target-capability unknown.
2. ESC-01 and ESC-02 are unanswered owner priority judgments.
3. C-001 is OPEN.

Containment defaults permit continued spec work but do not convert these into settled owner priorities.

## Self-gate

Executable source: `tools/validate.py`; machine-readable export: `registers.json`; schema: `matrix.schema.json`; captured output: `_validate-output.txt`. The validator checks schema/shape, ids and cross-references, decision alternatives/breaks, escalation/unknown completeness, contradiction index linkage, BEFORE-BUILD test mapping, and exactly 44 canonical domain records.

## Skill friction found during execution

1. §1 calls thin domains “ring 2 expected,” while §3.4 allows only fixed-point termination and §2 still gives unconditional ⊕ floors. The method does not state whether an expected thin ring 2 can close without a ring-3 fixed-point pass. This run avoided the ambiguity by using explicit NOT-REACHED records.
2. §5.3 says “a break-check that modified nothing did not run” without stating whether this applies to each pair or the pass as a whole. Many legitimate pairs share nothing. This run interprets it at pass level while retaining explicit NO-INTERACTION checks per pair.
3. §7.6 requires an executable schema validator but supplies neither a canonical serialization nor parser behavior for multiple YAML blocks in Markdown. This run added `registers.json` as the validation source; downstream consumers must choose the same convention.
4. §7.1 reads as one file per every domain, while the bounded-run wording and task minimum can be read as one file only per cascaded domain plus aggregate NOT-REACHED rows. This run chose the stricter 44-file interpretation.
5. §7 has no artifact write lock, run id, staging directory, or atomic publish rule. A concurrent dogfood runner wrote the same filenames during this run, demonstrably overwriting register files. This run recovered through an isolated final staging directory and atomic replacement, but the skill should prescribe single-writer or run-scoped output.

Confidentiality: no actual secret values are present. This unsanitized matrix should not be committed publicly.

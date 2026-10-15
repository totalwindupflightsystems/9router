---
name: worker-brief-authoring
version: 1.13.2
description: Use when authoring a dispatched worker's one-message brief.
tags: [coding-hermes, foreman, dispatch, worker, brief]
related_skills: [coding-hermes-foreman, coding-hermes-worker, coding-hermes-specs, foreman-tick-verification]
---

# Worker brief authoring

A dispatched coding worker gets EXACTLY ONE message and never sees fleet
skills, board context, or memory. The brief is the entire spec of the task.

**Mandatory traceability handoff.** Before dispatch, load `coding-hermes-traceability`; resolve the exact owning board row, the project's doctrine/spec anchor, and the use-case or workflow being changed. Include these in the brief, plus any stable `UC-...` / `REG-...` IDs, the automated test or exact manual procedure, and the expected observable result. Require the worker's final response to include:

```text
ch:trace row=<board-row-id> spec=<path#anchor-or-none:reason> wave=<manifest#step-or-none:reason> test=<path::test-or-none:reason> doc=<path-or-none:reason> prompt=<path-or-none:reason> evidence=<artifact-or-run-or-none:reason> witness=<locator-or-none:reason> verdict=<id-or-none:reason> commit=<full-sha-or-none:reason> memory=<resolved-key-or-none:reason>
STATUS: complete | partial | blocked
TIER: T0 | T1 | T2 | T3 (state what was invoked and observed for T3)
EVIDENCE: <resolvable artifact, run, verdict, or commit>
```

Every value must be a single token; absent fields use a specific `none:<reason>`. The foreman validates the marker, writes it to the owning board row/closeout event, and only then runs GitReins Tier 2. Every GitReins task criterion must include a traceability check for row/spec/test/evidence/commit resolution; do not close on CI status alone. For repositories with a pre-eval trace gate, use the owning board-row ID as the GitReins task ID unless the gate documents another mapping; write the worker marker and closeout block into that row's `worker_summary` before `gitreins task complete`, then update the final event after the verdict. When the launch path supports it, preload `coding-hermes-worker,coding-hermes-traceability` with `-s`; regardless, the one-message brief must contain this full block so API/session dispatch paths cannot omit it.

**Evidence-pointer syntax:** use a repository-relative artifact path, a resolvable bare or `verdict:<id>` verdict, a resolvable commit SHA, or a prefixed external pointer (`run:<id>`, `live:<locator>`, `github:<locator>`). Bare external run labels are not resolvable; use `none:<reason>` only when evidence is genuinely absent.

**Verify every file/line citation against the live tree before dispatching.** Board-row reasoning
and old briefs are snapshots — after any merge the cited line numbers and even section positions
drift. Grep the symbol or quote the current lines into the brief instead of copying a row's stale
"lines 321-327" forward; a good worker self-corrects, a literal one edits the wrong section.

**A brief that asks for a MEASUREMENT must be built to FALSIFY, not to confirm.** State the outcome
that would refute the claim and call it a finding; forbid tuning the harness until the measurement
agrees; require every "we used X" claim to be read from the system (the response, the peer's view)
rather than from the config; and put the honest losing number in a NAMED report field so it cannot
be omitted by silence. Recipe and report-block shapes: `references/measurement-briefs.md`.

**Ground new-verb briefs in the REAL schema/validator, not the docs prose.** When a task adds a
CLI verb or file format the repo already validates elsewhere, name the exact source files whose
loader/validator the output must survive and forbid reimplementing the list — "reuse the exported
constant in <path>, do not duplicate it". Two hidden traps this class hits: (a) type-name maps are
NOT 1:1 with storage types (e.g. a declared `integer` column may store as float64, and an int64
column may reject JSON numbers in favor of canonical strings) — the worker must derive the type
mapping from the validator's accepted inputs, not from intuition, or the first insert row 400s;
(b) primary-key and nullability interact — resolve the key column BEFORE nullability assignment.

**Batch sibling single-file tasks into ONE brief.** When a tick's pending tasks are all small and touch the same file (or the same trivial surface), combine them into one worker brief with numbered fixes and one commit — do not burn a dispatch per row. Keep the scope fence explicit ("only modify <file>") and enumerate every task id in the commit so board rows can all close on that commit hash.

**Recon cap:** a multi-file brief must command the first edit early or the worker plans forever.

**Complexity cap for sub-model workers:** a brief that asks for 3+ independent changes across 4+ files (e.g., "add config knob + implement session continuation + wire attempt counting") causes sub-model workers (glm-5.3-flash, deepseek-v4-flash) to stall at 0% CPU without producing any code. The worker's context fills with planning and it never reaches the first edit. **Fix:** split into 2+ simpler rows (each touching 1-2 files with a single clear goal) OR dispatch to a stronger model (deepseek-v4-pro, openai-codex, gpt-6-luna). A brief that requires reading 3+ existing files to understand the change shape is already at the complexity ceiling for sub-models.

**Shell safety:** write the brief to a unique /tmp file and dispatch with
`hermes chat -q "$(cat /tmp/<task>-brief.txt)" -s coding-hermes-worker,coding-hermes-traceability` — `$()`, backticks and quotes inside a `-q` inline brief break the outer shell; a file brief cannot. When the launch path supports it and does NOT pass `--ignore-rules`, preload both skills with `-s`; `--ignore-rules` suppresses preloaded skills. In either case, the one-message brief must contain this full block so API/session dispatch paths cannot omit it.

**Unique /tmp filenames per tick for BOTH the brief and the commit-message file — never a shared
fixed name.** On a shared repo, concurrent workers and siblings that `git commit -F /tmp/msg.txt`
over each other's files race between write and commit: a worker can land its (correct-tree) commit
carrying a SIBLING's message, forcing a message-only amend to recover. Name files
`/tmp/<tick-or-task>-brief.txt` and `/tmp/msg-<task>.txt`, and have the brief itself instruct the
worker to use the task-scoped message path.

**Model choice:** from the task row or the worker-model doctrine (subs before PAYG), never the
gateway default by reflex. Docs-only or grep-verifiable tasks may carry "do NOT run the full test
suite; verify with grep only" so a one-line change does not burn a full CI run.

**Request-path/API briefs must include four independent closeout checks:** focused contract tests, the relevant broader API suite, lint on changed files, and supervised deployment parity after push. State explicitly that a pushed commit is not a live deployment; the worker may report the running service as stale without trying to restart an owner-controlled service. Keep unrelated dirty files out of the commit and name them in the brief so the worker does not accidentally stage them.

**CI acceptance must distinguish implementation failures from repository hygiene failures.** If a workflow failure is a unit-test job failing on a tracked documentation artifact that is not indexed, give the worker the exact artifact and docs-index command; do not let a generic "CI red" criterion send it into API debugging.

**Deps/bump rows: verify the premise against the PIN, not just the installed env.** A landed bump commit (requirements.txt) does not change the checkout's venv — `pip list` keeps showing the old versions, so both 'already fixed' and 'still broken' can be read from the wrong half. Before dispatching on a deps premise: compare installed versions to the pins in requirements.txt and treat a stale venv as expected state, not evidence. Brief the worker to run `pip install -r requirements.txt` (sync) FIRST — gates run from the venv, so an unsynced venv validates the old pin and the bump result is attributed wrong.

**Verify-before-write gate:** before dispatch, re-read the exact file/lines the brief cites
(`sed -n '<range>p' <file>`); if they no longer contain what the row says, re-derive the citation
from the live tree and correct the brief, not the code assumption.

**Data-source verification gate:** before citing counts, schemas, or field names from a data file
or database in a brief, verify the source is accessible and has the claimed structure. Board-row
evidence sections are snapshots — a row may cite "366 enabled lanes" from a scheduler DB that is
now corrupted (0 bytes), or assume a JSONL file has an `enabled` field when its schema is
`(id, plan, quota_unit, ...)`. Run `wc -l <file>`, `head -1 <file> | python3 -c "import json,sys; print(json.loads(sys.stdin.read()).keys())"`, or `sqlite3 <db> ".tables"` to confirm the source
exists and has the expected shape. If the local copy is stale or corrupted, note this in the brief
and instruct the worker to query the live source (e.g., "query scheduler.db on the live gateway at
:9090/projects") rather than trusting the board row's evidence.

**Schema verification for data files:** when a brief references specific fields (e.g., "count
providers where `enabled=true`"), verify the file actually has that field by reading the first row.
A brief that assumes a field exists will send the worker on a wild goose chase — the worker will
either fabricate the field or stall trying to find it. Grep the file for the field name before
citing it: `head -1 data/tables/providers.jsonl | grep -o '"enabled"'` — if it returns nothing,
the brief's premise is wrong and must be re-derived from the actual schema.

Full recipe corpus (measurement briefs, falsification recipes, report-block shapes, long-form
examples) lives in `references/` of this skill directory.
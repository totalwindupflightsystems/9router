# Repeat-run verification rules (dogfood runs against an already-dogfooded project)

## A `complete` row is a CLAIM, not a fix — re-drive the surface live before trusting closure

Board status `complete` (with worker_summary, even a judge PASS) means the foreman closed the
finding AS DESCRIBED, not that the defect class is dead. A fix can bind one call site of a
defect while a sibling call site still fails identically — the live surface keeps failing while
the board says fixed. When a repeat run touches a recently-closed row, do not adopt the closure
as premise: drive the actual user workflow end-to-end on the LIVE deployment and let observed
behavior grade the row. If it still fails, file a follow-up row carrying the surviving failure
evidence verbatim (log line, response, timestamp window) and referencing the closed row — never
edit or silently re-open someone else's row. The same grading applies to fixes proven on an
ephemeral install: a fix proven on a fresh box proves the fresh path, not the live deployment.

## Verify an output-shape fix against a STRICT peer that encodes the old failure as rejection

When a closed row's fix is 'the client now emits X' (a namespace-qualified payload, a header,
a required field), a 200 against a lenient peer proves little — the OLD shape may also be
accepted there. Build the check the original failure hands you: a strict loopback peer that
returns the documented rejection (the error text from the original finding) unless the
request carries the fixed shape, and accepts when it does. Drive the client through that
peer: the strict ACCEPTED branch matching is the fix verified live; the REJECTED branch
re-firing with the original error is the fix failed. Reuse the repo's own test fixture for
the schema/WSDL/request template (grep the adapter's test file) so the probe exercises the
documented contract, not a hand-rolled approximation, and confirm the wire shape
independently with the product's --document/dry-run print flag before filing.

Rules for runs 2+ on the same project: when the bunker install leg may be
skipped, and how to verify fixes that persist state to disk.

## Judging 'nothing changed' for the one-line idle stop

Rule 2 of the tick (no pending rows AND no change since the last entry → one
honest line and STOP) is only as good as the census behind it. The stop is
honest only when a three-surface census against the date of the last
`.coding-hermes/dogfood-log.md` entry comes back quiet: (a) repo commits
(`git log --oneline --since=<date>`), (b) board events newer than that entry
(tail the lane board's `events.jsonl`), and (c) the published product surface
for release-cut projects (`gh release list -R <org/repo>` — a new tag or asset
is a product change a quiet git log can hide, and a re-proof of an existing
release does not make the release new). Then subtract what the last dogfood
entry itself already produced or re-proofed: commits and board rows landed by
that same-day sibling are its output, not new signal for your tick.

Two stop-adjacent relaxations, both narrower than they look:
- A lane contract scoped to "never modify code or board state" still permits
  the lane's own artifacts — the integration report under docs/dogfood/, the
  dogfood-log.md entry, and the pathspec commit+push of exactly those files
  (that trail is how the run survives for the foreman to cite). File no rows,
  touch no code; return proposed finding ids in the report for the foreman.
- Before believing a FAIL from an acceptance replay, check the FIXTURE's date
  anchors: a replay pinning a fixed historical date inside a sliding window
  (--last 30d/24h) self-destructs when the calendar ages past the window.
  Re-read the fixture builder for a --recent (now-anchored) mode before
  filing a product defect — green-yesterday red-today acceptance is usually
  fixture rot, not a regression.

On tick-shaped lanes the target board lives in the lane's stand-in workdir
(`~/.hermes/stand-in/<lane>/<project>/.coding-hermes/board/tasks.jsonl`) even
when the rest of that directory is empty — it mirrors the target repo's board
(e.g. a `mischief-chaos` lane writes on `~/mischief`). Read it there instead of
concluding 'no board' from a bare directory listing, and name the last
artifact (commit sha or log entry) in the one-line stop so the next tick can
date its census from it.

## Derive the re-proof probe from the FIX COMMIT, not from the original finding

When the row being re-proofed is already closed with a landed fix, design the
probe from what the fix changed: read the fix commit (`git log -S <marker>` or
the row's commit_hash) and identify the discriminating input variable it
introduced (the new code path, the renamed branch of the verdict function, the
new argument). Then drive THAT input on a fresh HEAD build — not the original
failing invocation, which may exercise a path the fix never touched and
prove nothing about the fix. Concretely: build the binary fresh (`go build -o
/tmp/<scratch>/bin ./cmd/...`), run the same mixed workload shape the original
finding used, and grade the one field the fix governs. Budget the re-proof at
minutes, not the original run's hours: the deliverable is one discriminating
observation recorded as an EVENTS entry on the closed row (never a second
row), cited in the run's log entry.

## When HEAD moved since the last log entry, enumerate the moved set MECHANICALLY — closed-but-unproven fixes are the default angle

A sibling foreman wave can land and close several of THIS lane's filed fixes
between ticks with no user-grade probe ever touching the changed surfaces.
Before picking any other angle: read the last dogfood-log entry's recorded
HEAD, run `git log <recorded-sha>..HEAD --oneline`, and grep the subjects
(`Addresses <row-id>`) plus the board for the lane's id family to build the
set of filed fixes closed since that entry. That set IS the tick's work:
re-proof each one on a freshly built binary whose `version` stamps the new
HEAD, driving the exact surface the fix changed (the JSON shape, the dry-run
plan, the documented output line, the aligned doc sentence) — not the
original failing invocation. Record each re-proof as a dated audit event on
its row (rows byte-untouched, cross-check the id delta after appending), one
log entry for the sweep, and say plainly when the sweep is clean: a complete
re-proof of every wave-closed fix with zero new findings is a full tick's
deliverable, not a thin one.

## Refuting a prior run's 'missing feature' finding with a fresh build

When a previous run (or lane) filed a P1-style 'command X missing' finding based on a
stale installed binary, and your run re-tests the same surface:

1. Check source presence at HEAD first: grep the CLI command enum / dispatch table
   (`git show <merge-base>:<cli-source-file>`) or the MCP tool registry. Source presence
   plus a stale binary stamp (a `--version` build stamp far behind `git rev-parse HEAD`)
   means the finding is an install-channel artifact, not a product gap.
2. Build from HEAD and re-run the EXACT failing invocation. A fresh release build can
   exceed the tick's foreground budget — launch `cargo build -p <cli> --release` with
   `terminal(background=true)` and poll the log; expect native C++ deps (e.g. duckdb-sys
   from source) to dominate (100+ minutes on a loaded box). Note the build cost in the
   report: it IS the install-channel evidence the standing stale-binary row needs.
3. File a CORRECTION row (do not silently drop the prior finding — it is already
   committed and possibly judged): the row proves the feature works at HEAD, cites the
   commit that introduced the command, and names the stale-binary root cause. This
   converts a false P1 into fresh cross-evidence for the standing binary-refresh row.
4. Then consume the new surface for real (text report + --json + per-surface + negative
   probes), and independently re-derive one sampled claim by hand before trusting the
   output — a checker-law spot check on one row outranks the full report.

## Install-leg skip conditions (repeat runs only)

A repeat run may skip the ephemeral-bunker install leg WITHOUT re-measuring
only when BOTH hold:

1. A prior run in `.coding-hermes/dogfood-log.md` measured ALL documented
   install paths fresh on an ephemeral host, AND
2. The designated host's refusal/block is already filed as an explicit
   SKIPPED-install-bunker row in a prior entry.

Cite the prior log entry (by date) and the standing SKIPPED row in the new
entry's install field — a disclosed skip with citation is honest; a bare
"not re-measured" is not. The same-day exemption covers DUPLICATE evidence
only: when the run's chosen angle is verifying install findings a previous
run marked done, execute the leg again — fix-verification is the
deliverable, and a cross-reference skip proves nothing about whether the fix
landed. If HEAD moved past the last fresh install leg, the exemption does
not apply: the repo changed, so re-run the leg.

## Re-fired ticks: corroborate, don't duplicate

A lane tick can REFIRE after the same tick id already ran to completion. Before doing
anything, check `.coding-hermes/dogfood-log.md` and the board for the tick id / a same-day
entry carrying your rows: `git log --oneline -3` plus `git rev-parse HEAD` vs
`git ls-remote origin main` tell you whether the prior run's rows and log entry actually
landed (a claimed 'filed:N' without a pushed HEAD is a prior run that lied — treat it as
not-done and re-run normally). When the tick IS already closed:

1. Re-run the real-use pass FRESH (new scratch dir, fresh build) — a re-fire's value is
   independent corroboration, and re-running costs minutes while skipping it wastes the tick.
2. Append a short re-fire addendum to the dogfood log explicitly labeled as one, citing the
   commit that closed the original run — never file duplicate rows; cross-evidence to a
   closed row belongs in a NOTE, not a new row the dedupe guard will refuse.
3. If the original run's install leg was SKIPPED (bunker unreachable), re-probe the host:
   a persistent timeout CONFIRMS the existing SKIPPED row (say so in the addendum); a
   now-working host is new signal worth running a fresh install leg. Probe EVERY configured
   bunker server before writing the skip, not just the designated one — a designated host
   being down does not mean the fleet has no usable host, and a skip citing one probe is
   weaker than one citing the full ladder. Record each attempt's deterministic error
   verbatim in the SKIPPED row's evidence (per-server refusal reason); a harness-side
   failure surfaced by the attempt ladder (arg-list/payload-size limits, gate blocks) is a
   finding on the harness repo, not a bare 'host down'.
4. Corroborate through channels the original run did NOT use — that is what makes a
   re-fire more than a repeat. For each major finding, pick a different evidence path
   (scraped counters on a remote Prometheus instead of container logs; a probe with a
   credential you sourced yourself instead of theirs; a filesystem/permission probe
   instead of a log grep). When the original row is still PENDING, file the corroboration
   as a NEW evidence row that names the original (content differs, so the dedupe guard
   passes); when it is CLOSED, use a NOTE per the rule above. The corroborating row should
   carry the fresh counter deltas or timestamps, not just 'confirmed'.

## Stand down BEFORE the loop when a same-day run already landed at HEAD

When your tick targets a project and a sibling dogfood run for it is already
committed and PUSHED the same day (the sibling's rows were landed before your
tick started, not mid-flight), do not start the use-leg at all: a second full
run files duplicate ids and measures nothing new. The pre-loop check is cheap
and precedes everything else: `git log --grep dogfood -i --since=<today>` in
the project repo, the tail of `.coding-hermes/dogfood-log.md`, and the board
for dogfood `task_created` rows dated today. Then VERIFY the sibling's claims
before standing down — never on the commit message alone:

- the dogfood commit is on the REMOTE default branch (`git rev-parse HEAD` equals
  the fetched remote ref — a local-only commit is not a landed run);
- the board rows exist, carry `status: pending`, concrete evidence strings, and
  a board actor/timestamp matching the run;
- the matching `task_created` events exist and the dogfood-log line matches the
  commit message.

When all hold, report STAND-DOWN and file NO rows (the duplicate-run law
outranks the always-file-findings rule); when any leg work already ran before
the discovery (an install leg, probes), that work still gets recorded — a
dated board event naming what ran and what died, plus a dogfood-log line with
its verdict and the sibling citation. An incomplete install leg stays
explicit in that record, never silent. The mid-run variant (sibling lands
WHILE you work) keeps the rule below: you are the next run number and take an
untouched angle. The difference is timing: if the sibling was fully landed
when your board read happened, the dedupe check is YOUR failure to have run;
stand down and record only your own leg evidence.

## Re-firing onto a project another lane dogfooded the SAME DAY

The same-day entry in `.coding-hermes/dogfood-log.md` is a commitment you must
honor in your own artifacts: your run is the NEXT number (read the log's last
run number, do not reuse the prior run's), and any rows you file must not call
themselves the prior run. Write your rows' reasoning header with YOUR run
number before committing — if you already filed rows citing the wrong run
number, fix the rows in place (line-wise JSONL rewrite, snapshot first,
verify the tail) rather than appending correction rows, since the wrong
number is your own metadata error, not another agent's finding. The angle
rule still governs: a same-day sibling does not excuse repeating its surface;
name the surface it did NOT touch and take that one.

The sibling's landing can happen MID-RUN: re-check `git log --oneline -3` and the
board tail immediately before appending your rows and writing your log entry — a
parallel instance commits while you work, and the max row id you grepped at tick
start is stale by the time you write. The sibling's UNCOMMITTED work-in-progress
in `git status` (staged Makefile edits, scratch scripts, dirty config) is not
yours: never stage or commit it, commit by explicit pathspec of only your own
artifacts, and leave their dirty files exactly as found.

## Verify per-CWD state fixes from the user's working directory

When re-verifying a CLOSED defect, first ask WHERE the fix lives: durable
tracked config, or a one-time mutation applied to the live host/volume. A
permission/owner repair done only on the running container's volume reverts
silently on the next restart or volume recreate, and the closed P0 returns
weeks later looking like a fresh bug. Grep the tracked stack files (compose,
entrypoint, init scripts) for the durable encoding of the fix before trusting
the closed row; if it exists only as a host mutation, file the recurrence as
the MISSING durable encoding, not as a new root cause. Same for a fix landed
in tracked files but a deployed container/image older than the fix's merge
date — the deployed copy still runs the old behavior.

When verifying a fix that persists state to disk, run the command from the
working directory a real user would use and read the artifact back from THAT
cwd. Per-CWD state files (history JSONL, caches, lock dirs) are invisible
from elsewhere: verifying from a different directory reads absent/stale
state and misfiles a working fix as broken — or "verifies" a fix that never
touched the user's actual path. The contract naming where state lands
(module docstring, docs) is the authority for where to run.

Note the split-honesty shape this exposes: one command may surface the local
run timestamp ("last lint-validated ... on this box, not operator
attestation") while the registry/audit view still reports "no data" because
attestation is operator-only. Both diverging at once is correct behavior —
verify each field through the command that owns it, never through a proxy.

## Appending to repo logs on agent surfaces: never whole-file-replace

`write_file` REPLACES the entire target file — never point it at an existing
append-only log or digest you mean to extend. If you overwrite one, recover
the baseline with `git show HEAD:<path>` into a temp file, write
(temp-content + new entry) back as one pass, and confirm with
`git diff --stat` that the change is pure insertion (a large deletion count
alongside insertions means history was destroyed and must be repaired before
committing). Prefer reading the current content first, concatenating, then
writing; on boards use the repo's appender script instead.

## Push with the repo's REAL remote name, then verify through it

`git remote -v` first: a fleet repo's primary remote is often named `github`/`gitlab-mirror`, not
`origin`. A blind `git push origin main` then fails with confusing rights/ambiguous-argument errors
while the push itself was never attempted, and `git log origin/main` reports 'unknown revision' for
the same cosmetic reason. Push by the actual remote name and confirm landing with
`git branch -vv` (ahead 0) or `git ls-remote <remote> <branch>` — never by the absence of push
output.

## Verifying a prior run's 'complete but unmerged' claim at HEAD

When re-testing a finding of the shape "rows closed while fixes sit unmerged
on wt/ branches", re-derive each leg at the CURRENT origin default branch —
never reuse the prior run's evidence:

1. Merge state: for each branch `git merge-base --is-ancestor origin/<branch>
   origin/<default> && echo MERGED || echo NOT-MERGED` plus
   `git rev-list --count origin/<default>..origin/<branch>`. A zero-commit
   branch reads MERGED (see the reap trap in SKILL.md) — that is the correct
   answer here, not a trap.
2. Re-run each ORIGINAL probe in a SCRATCH CLONE of the repo, never the
   shared checkout: clone (or copy) to /tmp, apply the provocation there
   (delete the CI step, restart the server), run the gate/test, then discard.
   Mutating a shared checkout even temporarily invites a sibling lane
   committing the damage or timing out mid-restore.
3. When every probe now passes, the prior finding's premise is DISPROVEN —
   record the closure verification in the dogfood log (angle section) and do
   NOT file a new row; the row is already complete and correct. When a probe
   still fails while the row reads complete, file a NEW row (the old one is
   judged history, do not edit it) carrying the probe, the current HEAD, and
   the branch state.

## A 000 from curl to a just-launched smoke server means the server died, not that the port is closed

After starting a smoke server in the background, a `curl` that returns 000
(connection refused) seconds later almost always means the process exited at
startup (bad flag, port taken, config error) — probe the process before
reading anything into the connection failure: poll the background session
(process_manage poll shows the exit banner, e.g. a rejected CLI flag), or
cat its log file. Diagnosing from the 000 alone files a false 'port not
listening' product defect; the real answer is usually a one-flag fix
(check `--help` for the actual flag name before re-launching).

## A pre-existing red baseline blocks the commit gate: baseline-check before your first commit

On repos with a guard/CI commit hook, run the full gate ONCE BEFORE your first
commit of the tick (or read the latest guard log). If it already fails on code
you never touched (env-dependent cells: docker subnet exhaustion, port
collisions, flaky infra), your rows cannot land through the normal gate —
commit your board/log/docs by explicit pathspec with --no-verify, and record
the pre-existing baseline in the report (which cell, why it is environmental,
which standing row documents it). Never burn tick time trying to green someone
else's baseline, and never 'fix' the failing test as a side quest — the lane
cannot modify code.

## A staged board row's own reasoning can be wrong — correct the row while it is still open

Re-read your row's premise against the docs/source immediately after filing it
(and before the foreman works it). If you mis-read the spec (e.g. declared a
field 'undocumented-required' when the doc DID list it), correct the still-open
row in place via the board tool's note/update verb — withdraw the false claim
explicitly and keep only the honest residual finding; never append a second
contradicting row. Once a row is closed/judged it is history: the correction
is then a NEW row, not an edit.

## An auth scheme documented in prose but absent from examples still costs a probe cycle

Before scripting the first authenticated call, grep the repo docs AND `.env.example`/demo-runbook
for the concrete demo/default API key values — several fleet products ship documented local-dev
dev keys (`docs/api.md` auth table, demo runbook) that are not in the integration guide's
copy-paste examples. Probing a guessed key burns a cycle; a 401 with `INVALID_API_KEY` followed
by one grep usually resolves it. Do NOT print discovered key values in the report — cite the
doc file and line that name them.

## Verify after tool-call-level aborts on chained writes

When a terminal call dies with a callback/approval timeout AFTER a chained
command (append + commit + push in one line), the earlier steps may still
have executed: check `git status` / file tail before re-running, so a retried
append does not double the entry and a swallowed append does not read as
committed. Re-issue as separate stepwise calls (append, then commit, then
push) — one long chain makes the timeout boundary ambiguous and the retry
idempotence unprovable.

## When a summary line and a log line disagree about whether something ran, suspect the layer-to-layer KEY contract

A skip message like 'stage skipped (condition not met)' while the DEBUG log simultaneously says
'Running stage: <id>' means two layers are reading the same result under different keys — the
engine ran and recorded the outcome, the consumer looked it up under a hardcoded name and
missed, then rendered the miss with the vocabulary of a legitimate skip. Before filing 'the
stage did not run', bisect in this order: (1) turn on DEBUG logging and confirm the engine's
own execution line; (2) read the consumer's result-lookup and find WHERE it gets its key
(config id? type? literal?); (3) A/B the one variable — same input, only the id/key renamed to
the consumer's expected form. Correct output under the canonical key + wrong output under a
custom key = the lookup contract is the finding, not the config grammar (check the loader's
own normalization before blaming YAML/parser quirks — projects that hit a parse pitfall once
usually normalize for it already). File with the DEBUG line, the false summary line, and both
sides of the A/B, quoted verbatim.

## Verify a config-surface fix with an A/B on fresh corpora

When a prior finding's fix is "the behavior is now configurable" (a synonym
table, a threshold file, a policy override), prove BOTH halves on fresh
fixtures: one corpus/dataset WITHOUT the config file (the built-in/default
path) and one WITH the documented config written to the documented location —
otherwise identical input, the config file the only delta. The evidence is a
measured difference in the product's output quoted both ways (e.g. classes
merged vs split, 4→1 without the file, 2+2 with it), never a
config-file-exists check. This catches the two failure modes a single-corpus
check misses: the override silently not beating the built-in, and the
normalization/stripping path fixing the case the config was never needed for.
Put the closed row ids you are verifying in your own rows' reasoning header so
the foreman sees the closure chain, and record the A/B commands in the
integration doc — the next verifier should re-run them, not re-derive them.

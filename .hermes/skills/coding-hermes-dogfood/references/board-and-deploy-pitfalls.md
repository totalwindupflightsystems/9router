# Board-lint and deployment-drift pitfalls (dogfood)

Moved out of SKILL.md to keep the core under its size cap — same rules, topical home. Load when filing board rows that must pass a board-lint pre-commit hook, or when re-verifying fixes on a project that serves a long-lived container or a deployed copy of its source.

## Board row status vocabulary is closed — use `pending` for newly filed rows, never `added`

The board's validator accepts only `{blocked, complete, failed, in_progress, pending, review}` (with `completed`/`done` as read aliases for `complete`). A row filed with `status: "added"` parses as valid JSON but fails the board-lint pre-commit hook and is invisible to status-keyed queries. Always file new findings as `pending`. See `jsonl-board-hygiene` §4 for the full vocabulary and normalization rules.

## Board-lint pre-commit hook blocks commits with vocabulary or structural errors

The hook runs `boardctl validate` which checks status vocabulary, guard_result/ci_result vocabularies `{PASS,FAIL,SKIP}` / `{GREEN,RED,SKIP}`, duplicate ids, and key uniformity. When it fails with `[error]` lines, you must either fix the errors in the board file or use `git commit --no-verify` to bypass (and file the pre-existing errors as findings). A commit that bypasses the hook with unfixed errors in YOUR rows will fail again on the next push; fix your own rows first, then bypass only for pre-existing defects you are not responsible for.

## A "fix merged, row complete" claim can be invisible to users when the runtime is a long-lived container — check deployment drift before re-verifying anything

The foreman merges web/UI fixes and marks rows complete, but the serving container keeps running a bundle built weeks earlier; every re-test then reproduces the OLD bug and can falsely reopen finished work (or falsely "confirm" a fix on a box where it happens to be deployed). Before judging any UI/web fix, compare `docker ps --format '{{.Names}} {{.CreatedAt}}'` against the fix's merge date, and grep the SERVED bundle for a marker the fix introduced (0 hits = drift — e.g. a stats endpoint name that only the new code fetches). File drift as its OWN row (the real gap is a missing deploy step in foreman closeout); carry still-live symptoms there rather than reopening the original row.

The file-granularity twin: when the tick prompt runs a DEPLOYED copy of the project's source (a script synced to ~/.hermes/scripts/ or similar), sha256 repo copy vs deployed copy as its own repeat-run angle — zero drift today still leaves `no documented deploy step, so drift would be undetectable` as a filed finding.

## A repo artifact proves it was BUILT, not INSTALLED — for every ship-as-a-unit surface, audit install state, not file existence

When the product ships detector/reconciler/installer units (deploy/*.service/.timer, install scripts), the finding class is "fix exists in-repo but was never run once": check `systemctl --user is-enabled <unit>` and the deployed copy's actual presence (`ls ~/.hermes/scripts/<script>`), and hand-run the script to confirm its behavior — a silent exit-0 from the script plus an absent timer means the gap is still live even though the code and tests are green. File the row against the INSTALLATION step (acceptance = unit enabled + hand-run verified), keeping the in-repo fix as already-done; do not re-file the code as if it were missing.

## Run the board validator on staged rows BEFORE committing — and match the canonical status vocabulary

The full rule (vocabulary set, guard hook mechanics, verdict repair, retry rules) lives in the
sections above; this is the append-time checklist:

- File new rows as `pending` (never `added` — see the vocabulary section).
- Run the repo's own validator on the STAGED board before committing, and expect its warning
  count to change by YOUR rows' warnings, not stay at the pre-existing baseline. When it reports
  errors, diff YOUR changed lines only — id-monotonicity and vocabulary errors often pre-exist at
  HEAD from sibling foremen's numbering, and attributing them to your append is the error.
- Prefer the repo's `boardctl create` over hand-written JSONL appends where a boardctl exists.
- When it reports 'task row appended but task_created event failed: events.jsonl line N: EOF',
  the ROW landed — read the board tail back and continue, never retry the append (a retry
  duplicates the row; the broken event line is pre-existing board corruption, a separate finding).

## Probe hygiene: snapshot outputs, isolate variables, plan removal

- **Test whether a query/recommendation surface's output tracks its INPUT before judging output quality.** Run two different queries and diff the result sets before reading anything into one result: a one-query read cannot distinguish "genuinely task-relevant output" from "fixed boilerplate", and the two-query diff converts a subjective "looked reasonable" into a falsifiable observation — disjoint result sets for unrelated inputs prove task-sensitivity, identical or barely-overlapping sets are a finding.
- **Query/retrieval surfaces must be probed for STALE-SOURCE leakage: change or delete a source file, re-run the build/reindex step, then re-query** and diff against the saved pre-change output. The common half-broken shape: the reindex correctly drops the file's symbols (so a naive "is the change visible" check passes) while the file's TOP-LEVEL row persists — a consumer then reads or edits a file that no longer exists, with no staleness marker. Save the before-output to a file first (the diff IS the evidence), and restore the tree (git checkout inside the scratch clone) and re-run the reindex before ending the run so byte-level restoration can be verified with `cmp`.
- **Snapshot a tool's fixed output file BEFORE probing its failure modes.** A gatherer/reporter that writes to a hardcoded path overwrites the last real report even when it fails: a missing-tool probe (PATH stripped) produced exit 0 + "scanned 0 of N" + an empty report clobbering the real one. Copy the output aside first and RESTORE it after the probe, and treat "0 violations, exit 0" on a big tree as a failure signal, never a clean result.
- **Probe the MISBEHAVING class separately from the MISSING class.** A stub dependency that exits 0 with malformed output (or one input exceeding an internal timeout) catches per-input silent drops — a repo vanishing from "scanned 14 of 15" with no error line — which a PATH-stripped probe never sees; the drop usually lives in one except-branch around the tool call.
- **Isolate ONE variable per probe — run the missing-dependency probe on the REAL input set (strip only the dependency from PATH), never inside a wholesale-swapped environment.** When the tool derives its input list from HOME, a scratch HOME also empties the scan population ("scanned 0 of 0"), conflating the failure class under test with an empty-input class and measuring nothing. Check what the tool reads from the environment BEFORE choosing the probe environment.
- **A 'delivered' exit-0 is the producer's word, not proof of delivery.** For any
send/post/upload leg, capture the DOWNSTREAM system's own response body as the receipt (a Bot
API `ok:true` with a message id, a 2xx body carrying a record id) — ideally via a minimal
direct API twin of the same call — and quote it in the run record. Read-back endpoints are not
a substitute: an updates/feed query can legitimately return empty (consumed or webhook-routed
updates) and proves nothing either way.
- **Judge an auth-gate probe by the RESPONSE BODY and a resource read-back,
never the status code.** A JSON-RPC or form endpoint can answer 200 to a
mutation-shaped call while refusing it at the application layer ("operator
credential required" in the body), so a bare `-w '%{http_code}'` probe makes a
refused mutation look executed. Read the body of every mutating probe, and
verify the resource you supposedly mutated (the flag row, the paused state)
before claiming an exploit or reverting anything — reverting a mutation that
was refused corrupts state you did not create.
- **Probing a refusal/dedupe guard PLANTS a row by design — plan the removal before the create.** Give the probe a unique id, and test the duplicate against a run_id recorded on a DIFFERENT task (cross-task duplicate is the real failure mode); exit 0 + row appended when the guard is documented IS the finding. Remove it python line-wise — assert the last row's id IS the probe before deleting (in BOTH tasks.jsonl and its events.jsonl companion), and verify `git diff` on the board is empty before filing. Never delete by grep: a concurrent sibling append can make the probe non-last between your read and your delete. If the probe reaches the board through a multi-hop path (webhook → remote spool → drain → board), the row lands only when you run the drain — remove it from the BOARD line-wise after verifying, and leave the remote spool entry when clearing is deliberately manual (inert evidence, not board state). A resolved-class probe yields a second row or twin id — sweep the id TOKEN, never one exact id. Expect a sibling lane's whole-file commit to sweep your transient probe rows into HEAD mid-probe — run the removal after that commit lands and verify the removal commit's numstat contains only your deletions; on the events companion select rows by task_id AND id set (a probe with two creates yields two creation events, so "last row is the probe" may not identify a clean tail) and assert the kept tail ends at the pre-probe max id. A REFUSED create is not footprint-free either: the DUPLICATE-SUPPRESSED path still writes an event on the EXISTING row referencing the probe id, so the events cleanup must catch refusal records, not only creation events. Give the probe an id that passes the board's id-format gate (boardctl enforces `^[A-Z][A-Z0-9]+(-[A-Z0-9]+)+$` — a lowercase or short id exits 1 before the guard under test is ever reached, which reads as "guard works" if you only check the exit code).

## A sibling foreman commit can swallow your staged rows — verify by content, then commit or stand down

On shared-checkout repos another lane can run `git commit` against the same board files
while you are staged and waiting. The pre-commit hook there runs `gitreins guard`, which
takes 5-10 minutes — do NOT remove index.lock while a sibling `git commit` process owns
it, and do not assume a timed-out commit failed: wait for the sibling's process to exit,
read its commit log (it echoes COMMIT_RC), then check whether YOUR rows landed via
`git show HEAD:<board-file> | grep <row-id>` (content in HEAD is the only proof — git
status is not). If your rows are already in the sibling's commit, do not commit again;
if not, re-stage and commit with the row file pathspec. Two more traps: the sibling's
guard may run against a DIFFERENT repo than yours (a FAIL in its log is not your
failure), and a guard-FAILed commit leaves the working tree with your changes staged
but uncommitted — verify HEAD content before re-running anything.

## Re-census the row-id family IMMEDIATELY before filing — a pre-run census goes stale mid-run

On a live multi-lane board, sibling lanes mint rows in your id family between your census and your append, so the next-free id the pre-census handed you can be taken while you work. The moment an append collides (or a pre-append bare-id grep finds the id present), re-derive the next free id from a FRESH census — grep the id TOKEN with both serialization spacings (`"id":"X"` and `"id": "X"`) — renumber your prepared row before appending, and correct any already-written doc/log references to the old id in the same pass: a log entry citing an id that landed under a sibling's row poisons the cross-reference. The pre-census is still worth doing (it avoids wasted round-trips and reveals already-filed defects), but treat it as advisory, not a reservation.

## Grep the board for an ALREADY-FILED row with your finding's premise BEFORE filing — same-day siblings share the namespace

Run 24 and run 25 on the same repo in one day both reached the same version-skew
premise and minted adjacent ids for it. Before `boardctl create`, search the board
for the finding's KEYWORD (`jq -r '.title' tasks.jsonl | grep -i <keyword>` plus
`grep -i <keyword>` over reasoning) — if a pending row already carries the
premise, file your independent evidence as a note/`update` on THAT row (or close
yours as a duplicate naming it), never as a second work item: the foreman works
the queue, and two rows for one defect halves its context and doubles its ticks.
A duplicate close must cite the surviving row id AND the new evidence yours adds
(the stronger reproduction, the extra host) so nothing is lost in the fold.
The same search covers the STALE-PREMISE direction: before filing a new row,
re-test the premise of the closest existing open row against live state — a
row built from a snapshot (uncommitted WIP, a then-current count, a then-open
tracker) can already be satisfied by a landed commit while still pending, and
re-filing its premise wastes the foreman's queue. When you confirm the stale
row's premise is satisfied, attach your evidence as a NEW row that `depends_on`
the stale id (or an events entry naming it) — never a freestanding duplicate
with a fresh id, and never an in-place edit of the stale row.

## A secrets-guard FAIL may be a FILENAME match, not a leaked key — read the redacted context first

Prefix rules like `sk-[A-Za-z0-9_-]{20,}` match inside ordinary words and
paths: a file named `…-ask-candidates-integration.md` contains the matching
substring `sk-candidates-integration.md`, and the guard reports the PATH
fragment redacted as `sk-can...tion` — which reads exactly like a leaked
key. Before treating a secrets FAIL as a leak, run the rule's regex against
the working tree, the staged bytes, AND the diff's path names. When the only
match is a filename or prose token, the fix is a rename/wording change, not
a token hunt; there is nothing to sanitize, and a guard bypass would be
wrong. Rename to a form under the rule's match length (e.g. `ask-loop-…`),
re-run the guard on the renamed tree to confirm clean, then commit.

## Write credential and env-var references as PROSE in anything a commit-time secrets scanner grades

Board rows, dogfood artifacts, and evidence files go through the repo's pre-commit secrets guard. NEVER write an env var or credential reference in `KEY=value` form — even a throwaway literal like a placeholder key blocks the commit with a SECRET DETECTED error, and a blocked board commit leaves your freshly appended rows uncommitted/unpushed while you burn time diagnosing. Name the variable and describe the value in prose instead ("set the CHIMERA_API_KEY env var to any throwaway value"), or write `KEY=<value>` with the angle-bracket placeholder rather than a literal after the `=`. If a blocked commit already left the row in the file, sanitize the row text and re-commit — do not bypass the guard for your own row's wording.

## `boardctl create` appends to the WORKING TREE — rows minted after your last commit are uncommitted until you commit again

A "pushed" claim from earlier in the tick does not cover rows created afterward: the create appends to the working-tree board file, and anything appended after your commit is local-only until a second commit+push. Before reporting, verify each row id is present in the PUSHED commit (`git show <pushed-sha>:<board-path> | grep <id>`) and `git ls-remote` parity covers that sha; if rows landed after the push, commit them with explicit pathspec and push again. Committing the append batch: put the `git add` and the pathspec commit in ONE call, then push and verify `git log origin/main -1` shows the commit — a long inline `--reasoning` on the create command can hit the shell command-parser blocklist (recovery: the blocked command is saved verbatim under ~/.hermes/cache/blocked-scripts/ and runnable from there, or split the reasoning shorter).

## The events companion has its OWN row schema — read its tail before constructing an event

`events.jsonl` rows are NOT shaped like `tasks.jsonl` rows: the live schema is
`{id, event_type, task_id, actor, timestamp, detail, tick_number}` (id is a
mono-incrementing integer across the file; timestamp carries a timezone
offset). An event built with tasks-row field names (`event`, `type`, `at`)
appends as valid JSON but is invisible to every event-keyed reader. Mirror the
schema from the tail (`tail -3 events.jsonl | jq -c '{id,event_type,task_id,actor}'`),
take the next integer id, and file one event PER task id rather than one
aggregated event. If a malformed event already landed, remove it python
line-wise (snapshot to /tmp first, assert the tail row IS yours), then
re-append conforming. Append-then-verify scripts must expect those legacy id-less lines: a strict
`json.loads(line)['id']` verify loop crashes on them AFTER the append already landed, and re-running
the script to 'fix' the crash double-appends. Assert id uniqueness BEFORE the append; verify AFTER
by tolerant-parsing and counting occurrences of only the ids you wrote. The
strongest verify is a task_id SEQUENCE DELTA: snapshot the file's task_id
sequence before the write, re-read after, and require the delta to be exactly
your intended ids (fsync inside the append script) — a concurrent sibling
append or a glued newline (missing trailing newline before the append) both
survive an occurrence-count check.

## A scheduled detector's output is only as good as its DESTINATION — check where the WARNs go before crediting the detector

A detector script whose header promises exit-0-always is correct about exit codes but may be journal-invisible: a systemd user unit can run clean on schedule (Result=success, recent ExecMainStartTimestamp) yet have NOTHING in `journalctl --user -u <unit>` (log persistence not enabled for the unit), so the WARN lines it prints every cycle reach no human. When a project ships a scheduled detector, verify the FULL chain: timer fires → unit runs → output lands in a destination someone can read (journal entry present, or a log file with fresh mtime). A detector with no reachable output is one finding ('detector blind'), and unactioned drift it warned about is a SECOND finding ('deploy stale despite the warning') — cite the journal-dead evidence in both.

## Query-fragment values can leak into WRITE payloads — census the status vocabulary of live rows, not just the code

When a row-based product writes through a PostgREST-style client, a writer can pass the encoded filter value (`eq.pending`) instead of the bare value (`pending`) into a write payload — the row lands with a status the FSM never defines and no reader can claim. Read-only queries won't show it; census the LIVE store (`SELECT/COUNT over status`) and diff the observed value set against the FSM/contract's defined vocabulary. Any out-of-vocabulary value is a P1 write-path defect plus a data-repair row; attribute the producer by reading the exact write call, then file a write-time vocabulary check as the fix direction.

## Mine the product's LIVE store for sentinel/placeholder values — the fallback stamp is where producer bugs surface

If the product persists real operational rows (a queue, table, log), query them filtered on the code's fallback sentinel (`branch=eq.?`, empty strings, nulls) instead of only reading fresh inserts: every row carrying the sentinel is a live instance of a derivation gap that synthetic test data never produces — real users invoke input forms (sha-ref pushes, edge-flag invocations) the happy-path tests omit. Then read the producer source at the exact field assignment (file:line) to attribute the root cause before filing — the row data alone shows the symptom, the code line makes the row executable by a worker who never saw your session. Include one real row id + the exact query command in the evidence.

## Commit the board artifact from the REPO that TRACKS it, not from the lane workdir

A stand-in lane workdir's `.coding-hermes/board` is typically a SYMLINK into the target
repo's `.coding-hermes/board/`; a pathspec commit run from the lane workdir dies with
`fatal: pathspec ... is beyond a symbolic link`. Run the commit from the TARGET repo
(`git -C <target-repo> commit -F <msg> -- .coding-hermes/board/tasks.jsonl`). Check each
additional artifact's tracking BEFORE staging (`git -C <repo> ls-files <path>`): the lane
workdir's own files (a dogfood-log.md written under the workdir, not under the symlinked
board) can sit outside any repo or be gitignored, and `git add` silently skips files it
cannot track — the commit then lands without them. Verify the pushed commit's stat actually
contains every artifact (`git show --stat HEAD`), and note the artifact-class distinction:
some repos track the board but gitignore the log — the log entry is still a valid artifact,
it just lives outside git, and the report should say where it is.

## Probe rows written through the product's own filing verbs are STATE, not scratch

A CLI filing verb happily creates the target directory and files a real-looking row at ANY
path you pass (including /tmp). Treat every probe write as cleanup debt from the moment you
make it: use an obviously-scratch unique path under the session workspace, never /tmp — on
an unattended surface deleting /tmp paths is approval-gated and the probe row survives the
tick. Where the re-proof only needs to observe the verb's behavior (exit code, stderr,
printed row), avoid materializing the probe row at all.

## On a compacted/resumed tick, verify the earlier instance's writes on HEAD before redoing any of them

The tick header carries the same tick id across a context compaction, and its earlier turns
may have already landed rows, log entry, and artifacts. Before designing the pass, check
`git log --oneline` for a commit whose message carries YOUR tick id (or your project+date),
read the dogfood-log tail, and read the board tail for freshly-minted rows. If the writes
landed: do NOT re-run the legs or re-file — contribute a RE-PROOF instead (drive one
independent leg or one fresh measurement of a row's premise on a different surface/host),
record it as an events.jsonl entry citing the existing row ids, append a short
continuation entry to dogfood-log, and commit only the new files by pathspec. Re-filing
a premise a sibling instance of your own tick already filed wastes a row; re-proof on a
new leg is new evidence the foreman can cite. Corollary: the earlier instance may also
have spawned an ephemeral agent — check `bunker list --server <s>` for agents from this
tick and destroy or adopt them before spawning your own.

## A sibling run can cover your angle mid-tick — re-check HEAD at close-out, verify its claims, and check its push state

The sibling check is not only a pre-angle step: a second dogfood tick can commit its run
(row rows, integration doc, log entry) AFTER you chose your angle and already ran your legs.
Before committing your artifacts, re-run `git log --oneline -3`; if close-out HEAD is newer
than the HEAD you proved against and the sibling covered your surface, do NOT file duplicate
rows — re-run your headline repro once against the new HEAD (it is one command) and grade
your log entry as an independent re-proof citing the sibling's row ids. The mid-tick check must include the REMOTE, not just local refs:
`git fetch origin` (or `git ls-remote origin HEAD`) BEFORE designing the pass — your checkout's
`git log` reads stale refs, and the sibling lands on origin while your tree never pulled it, so an
unfetched origin hides the duplicate the local log says does not exist. After pulling the sibling
in, verify its row delta by grepping the ids it added, cross-cite its run number in your log
entry, and file only the genuinely-new finding. Verify any sibling
claim you cite before adopting it: reproduce the repro yourself and grep the code path its
row names — its rows are working-tree JSON you have not seen executed. A sibling commit
carrying its rows may also be UNPUSHED (`git merge-base --is-ancestor <commit>
<remote>/<branch>` false): the rows exist only on local main, so on a read-only lane do not
push — name the push gap as an escalation note for the foreman/sync lane in your report.

## A log entry citing a row id is a CLAIM — grep the board for the id BEFORE writing the claim, and re-grep after the refire

The lie shape from the 'filed:N' rule applies to YOUR OWN committed artifacts: appending
the dogfood-log entry and appending the board row are two separate writes, and a session
can end between them (or the row-append call can silently never happen) — the committed,
pushed log then references a row that does not exist, and every later reader chases it.
Grep the board for the exact id token BEFORE writing the log entry or commit message that
cites it, and when a tick REFIRES (same tick id after compaction), re-grep rather than
trusting the earlier turn's report: the refire's verification pass is the cheapest moment
to catch the ghost. Repairing: append the missing row for real (same evidence), and amend
the log entry in the SAME commit to state the correction — never leave the ghost reference
standing next to the now-real row.

## A sibling can TREE-WIDE revert the shared checkout — append and commit in ONE call, never across a tool-call gap

Test rigs on shared checkouts run `git checkout HEAD -- .` / `git checkout <sha> -- .` for
stash-contrast proofs, which reverts every UNCOMMITTED append (rows AND log entries) the moment
it executes. The append script's own success line proves nothing an hour later: if a re-read
shows your rows gone while the file mtime advanced, re-append from your staged row file and
re-commit — the revert is not a signal your rows were bad. The durable pattern: git add +
pathspec commit + `git show HEAD:<board>` read-back inside ONE bash invocation, immediately
after the append; never leave appends uncommitted across a tool-call gap.

## Concurrent verifier ticks on one repo collide at the ARTIFACT path, not just the board

Two dogfood-style lanes running the same repo in parallel mint adjacent row ids (the re-grep
rule above handles that) AND write the SAME canonical artifact path
(`docs/dogfood/<date>-run<N>-integration.md`): a sibling can commit its version at your exact
path between your write and your commit, and its commit message will cite the same run number.
Before committing any artifact you did not create this second, `git log --oneline -1 -- <path>`
— if a sibling's commit owns it, restore their committed version into a distinct sibling-named
file (`git show <sha>:<path> > <sibling-named>.md`), keep YOUR report at the canonical path,
and disclose the swap in your commit message. Never silently overwrite a sibling's committed
artifact, and never rename yours away from the path the convention expects — both make a run
unfindable for the next reader who follows the repo's artifact naming.

## Append rows as COMPACT single-line JSON only — a pretty-printed row breaks the board's line contract silently

`cat file.json >> board` or any writer that lands a hand-formatted multi-line object turns one
logical row into N physical lines: line-indexed consumers miscount, strict parsers grade the
board corrupted, and a tolerant reader may still 'find' your rows and green-light the commit.
Append `json.dumps(row, separators=(',',':')) + '\n'` per row, then before committing assert the
board's TOTAL line count parses AND your ids appear exactly once. Repairing after the fact:
raw_decode-scan YOUR objects out of the file and re-serialize them in place — never re-serialize
sibling rows (a re-serialization of an untouched row counts as a diff and pollutes numstat). The byte-shape rule also governs FIXTURES built by transforming producer rows
(a re-proof that needs an invalid status in an otherwise-valid file): copy the shape from a REAL
emitted row (`cat` one), never from the documented/pretty form, `head` the transformed file to confirm
the mutation actually landed, then run the probe — a sed that misses the producer's spacing leaves
the row valid and the probe silently 'confirms' the wrong file.

## A docs-only dogfood commit in a guard-hooked repo trips the degraded-pass block — check the repo's commit rules for the docs-only exception before anything else

When the guard grades staged files and your pathspec carries only markdown, the substantive gates skip ("no <lang> files staged") and a skip-gates policy can exit non-zero specifically for skips-with-nothing-to-grade — the block fires on every zero-code run and reads like a guard failure when it is a policy gap. THE EXIT-CODE MECHANISM: a DEGRADED PASS log can still exit 2 — some guard configs treat a skip as failing unless `guards.allow_skips: true` is set, so a board/log-only commit returns rc=1 on EVERY retry while the log itself says PASS. Read the guard log's `skipped_steps` AND the repo's config for the skip policy before retrying; if the diff is genuinely board/log-only and secrets came back clean, commit `--no-verify` and record the skip reason in the commit message — never loop the identical failing commit. Check the repo's own commit rules FIRST for a docs-only exception (many guard-harness repos carve one), disclose in the report that the guard never graded code, and file the policy gap (a docs-only pathspec should skip, not fail) for the guard harness's lane instead of widening its config unilaterally. Also note the diagnostic rule this exposes: when a sibling's identical-shaped commit landed earlier with NO guard log at its timestamp, the hook did not run for it — compare guard-log timestamps against commit timestamps before assuming a bypass.

Operational additions to that rule: (1) ALWAYS capture the commit's exit code
(`RC=$?`) — the refusal's guard output can look like a routine report and the
hook's fail-open history teaches the opposite expectation; an unexplained
'my commit did not land' with clean output is usually a captured RC away from
diagnosed. (2) The same guard can run a repo's own wrapper command
(`gitreins commit`) that refuses for a SECOND reason (tasks in progress) —
read the refusal body, not just the guard verdict. (3) A commit killed mid-hook
(timeout or sibling collision) leaves the content STAGED with HEAD possibly
advanced by a sibling: verify HEAD, re-add, and re-commit by pathspec rather
than assuming the retry is a duplicate. (4) On a shared checkout the index can
carry sibling artifacts (judge history, tasks.yaml) staged by another lane —
before using any bypass, diff the STAGED set and confirm which files are
yours; name what the bypass commit carries in the commit message.
(5) Verify HEAD advanced after EVERY commit in a guard-hooked repo (`git log --oneline -1` shows YOUR message) — a pre-commit hook can run all its gates (log prints the PASS lines and a guard-log path, then exits non-zero for an unrelated reason) and the tool wrapper surfaces NO error: the content just sits staged and the tick reports a commit that never existed. Recovery, in order: confirm the guard log grades YOUR pathspec clean (secrets clean, no FAIL arm), diff the staged set to be sure it carries nothing a sibling staged, then land it with `git -c core.hooksPath=/dev/null commit -m ... -- <your paths>` and disclose the hook bypass in the message.

## A pre-commit guard that runs the full pytest arm can REJECT a doc/row-only commit — retry behind siblings, verify each FAIL's class before retrying, and use CI-mode env for the retry

The guard hook runs the full pytest suite with a large time budget; under fleet I/O pressure
it dies as a GATE TIMEOUT and rejects YOUR commit even when the staged diff is docs/rows
only. Retry, don't bypass: run the commit in the background with the project's documented
CI-mode env (marks live-dependent arms skipped-by-name per its offline contract) after
confirming no sibling gate holds the lock, and re-read the guard log's per-arm pass/fail
lines before EVERY retry — a secrets FAIL or a code-test FAIL is a different problem and
must stop the retry (see the filename-match rule above). Budget several retries; a full
guard is minutes and siblings hold the lock often. After any rejected-then-retried sequence,
re-check `git show HEAD:<file>` and origin: a sibling's pathspec commit can carry YOUR
staged rows/doc into its commit — skip re-committing what already landed.

## Re-prove a finding on your own fixture when the fix lands MID-RUN — restart the scratch substrate with the FULL env contract first

Sibling lanes work the same board while you run; a P1 you filed can be fixed and committed
before you report. Before re-proving, restart the scratch substrate with the same env set
the run used — data dir AND the namespaces-path env. Omitting the namespaces path makes the
server boot healthy and still 404 every table as 'namespace does not exist' (silent
wrong-store), which reads as a bad re-proof, not a bad fix. Then re-drive the exact finding
on the original fixture: a re-proof turns 'filed and hoping' into 'filed, fixed, verified
live', and the fix commit id becomes the closure evidence in the report.

## A scratch/secondary daemon on a host running the PRODUCTION daemon must repoint EVERY identity path — verify from source which config keys feed identity before booting

A scratch config that repoints ports/ssh_dir/audit/registry but omits the base data dir makes
the secondary daemon read the PRODUCTION instance's persisted identity file (the
read-or-create-under-default-base_data_dir pattern) and classify every production agent as its
classify every production agent as its own — boot reconciliation then archives-and-destroys live production state, and the fail-closed
orphan sweep guard does NOT protect you: it counts only UNPROVEN orphans, while a foreign item
classified as 'ours' sails through. Before booting any secondary instance: grep the
identity/instance-id loader for its path inputs, diff your scratch config key set against that
list, and never point a scratch instance at the production data dir even read-only. If the
product allows this silently, file it: refuse-to-boot on partial scratch configs, or bind the
instance identity to something host-unique.

## Aggregate/union surfaces over N member caches: probe corruption tolerance, and census caches born from mass rebuilds

Two coupled rules for products that keep one rebuildable cache per namespace/member and serve
N-member aggregates over them:

- **A union that treats a non-missing per-member failure as fatal converts one corrupt cache
into a global outage of the aggregate** — the single-member surface still works, so runtime
testing and single-surface probes stay green while every cross-member query errors out.
File the isolation gap separately from the corruption itself: per-member failures must
surface as facets (a namesps-failed list on the response) rather than abort the request.
- **A cache rebuilt via rm-dir → write-tmp → rename under an IN-PROCESS single-flight lock
corrupts when several daemons share the repo** — the lock does not span processes, and a boot
warm-up or fleet-wide rebuild across hundreds of caches is the mass-corruption window.
Census EVERY cache with a cheap header/table probe (engine show-tables, file size below a
threshold), then correlate empty ones against the boot log's SUCCESS lines and their meta
timestamps: corruption born inside logged successes is the strongest evidence the rebuild's
atomicity is broken, and the meta file can claim rowcounts the empty store never held.
Repair through the product's own rebuild verb — but verify the verb's BARE form first: a
rebuild command missing its scoping flag can silently rebuild EVERY unit with no progress
line (that fan-out is its own finding: missing confirmation guard), while the flagged form
is fast.

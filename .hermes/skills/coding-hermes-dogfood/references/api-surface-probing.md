# API-Surface Probing — Dogfooding Tools/Engines When the Board Says "Done"

When the dogfood target is a **tool, engine, CLI, or framework** (not a
website/library), its board will claim "all features complete" — but the
documented API surface may be largely dead at runtime. Before building
anything on it, probe the surface with **minimal isolation tests** and record
exactly what works. This is the reproduction-first principle applied to the
tool's own docs.

## The Isolation-Probe Ladder

Bisect the documented surface one variable at a time. Each probe is a
MINIMAL snippet — change exactly one thing per probe, keep a table.

| Probe | Question answered |
|-------|-------------------|
| `console.log({k: "v"})` only | Does structured output capture work AT ALL? |
| Bare expression statement: `tool("web_search", {...})` | Does a tool call execute? |
| `const r = await tool(...); console.log({x:1})` (r unused) | Does AWAIT-ing a tool break capture? |
| `const r: string = await tool(...)` (annotated) | Does the type-annotation transpile work? |
| `let r: string = ...` (annotated let) | Same, with let? |
| un-annotated `const r = await tool(...)` | Same, no annotation? |
| `await tool(...)` unassigned, then log constant | Does the await itself kill output? |
| nested object log `console.log({a: [1,2,3]})` | Does non-scalar capture work? |
| long string value (1500 chars) | Is there a length limit? |
| every documented global (`fetch`, `agent`, `llm`, `$`) | Which d.ts declarations have runtime bindings? |

## Proven Case (hermes-dagger, 2026-08-04)

Board: **10/10 tasks complete**. Live probes: engine core works
(`tool("web_search")`, un-annotated consts, `Promise.all` parallel, flat
`console.log`, MCP 7-tool surface, SQLite persistence 123 runs/105
checkpoints) — but six documented features dead:

- **Type annotations break execution** — `const x: string = await tool(...)`
  → QJS `SyntaxError: missing initializer for const variable`. ALL three
  built-in templates use annotated consts → all fail verbatim.
- **ANY `await tool()` kills output capture** — Output=null in CLI, MCP,
  AND the DB (runs table has no output column; results are lost entirely).
- `fetch()` → "not a function" despite `FetchEnabled=true` in the tier config
  and a d.ts declaration.
- `agent()` → Go runtime panic (module closed with context deadline exceeded).
- `llm()` / `tool()` return objects, not the `string` their d.ts declares.
- `--prompt` advertised in help, not implemented; `dagger resume` a no-op.

Root-cause pattern: **bridge injection + transpile path had zero runtime
smoke tests** — the d.ts, the tier config, and the runtime disagreed, and
nothing exercised the surface until a user did.

## Method Notes

- Run probes through the SAME entrypoint you'll rely on (CLI, MCP, HTTP) —
  capture behavior can differ per surface. Check persistence too: a result
  that isn't in the DB is a result that is lost, whatever the CLI prints.
- Write the working-surface contract explicitly: "only X, Y, Z proven —
  build everything on those". The PM DAG template for hermes-dagger was
  written against the proven surface only (un-annotated consts, flat
  console.log, `Promise.all`).
- File each dead feature as a board task with the probe that proved it and
  the observable pass criteria (e.g. "every built-in template runs verbatim").
- Wire a **canary** into any dependent automation: each cycle re-runs one
  minimal probe; when the previously-dead surface flips live, the dependent
  system can switch over automatically instead of assuming.
- **A parity probe must pin BOTH sides to the same fixture before believing
a diff.** Comparing surface A's output for entity X against surface B's
output for entity Y produces a huge, plausible-looking diff that is tester
error, not a product defect — the diff is indistinguishable from a real
parity break until you check the inputs. Structure the probe command so both
sides read from ONE named fixture variable (never two hand-picked files),
and confirm the fixture identity before filing; the rerun-with-same-fixture
is cheap, the false row is not.

## Degradable input options: the degrade must be visible to the CALLER, not only the log

When a documented input option degrades gracefully on unavailability (a
requested-tools list, an optional backend, a fallback mode), the working
degrade does NOT end the probe — grep WHICH surfaces carry the degrade marker.
If the resolved/dropped names appear only in the daemon log, a REMOTE agent
submitting the request cannot learn its option was dropped (it has no log
access) and may assume provisioning succeeded. File 'degrade invisible to the
submitting caller' with the exact log line as proof the mechanism fired and
the file:line of the resolver that holds the data; fix direction is echoing
resolved/missing back in the submit/queue response, not 'add more logging'.
Before writing either verdict, prove the degrade contract itself: the feature
must still work correctly without the dropped piece (drive one submission with
everything resolvable and one with a guaranteed-missing name — the pair is
also the discriminating probe for the observability row).

## The documented OPERATIONS story is part of the surface — grep the specs for taught CLI verbs and run each one

The dead-surface check runs in BOTH directions. You already grep the call graph for non-test callers of flagship internals; also grep the SPECS and ops docs for the CLI verbs they TEACH (a "CLI seams" table, a daily-checks table, a recovery runbook) and run each verb before trusting the operations story. A spec'd seam whose verb has no case in the CLI's command switch (`grep -rn '"verb"' cmd/<cli>/`) is a P1 even when the underlying library is complete and well-tested — the spec even carries an exit-code contract no user can exercise. A verb that prints `unknown command` + full usage is the tell; verify against the shipped binary at HEAD, not a stale one.

## Every recovery path you fault-inject needs a REPORTING check, not just data survival

After a fault (torn line, corrupt record, killed writer) heals and the data survives, trace what an operator can SEE: the boot note gated on the right counter, the health field, the dashboard stat. A heal whose boot-note gate keys on a counter that the fault class you injected never increments (e.g. a heal-for-tail gate tested with a mid-file fault), or whose torn/corrupt stat fields have zero consumers outside the package (grep the health/dashboard/app surfaces for the field name), repairs the file and tells nobody — that unreportability is its own row. Quote the gate (`if counter == 0: continue`) and grep the surfaces to prove absence, then grade the silent-repair leg against the product's own honesty doctrine.

## SQL-backed surfaces: read-only posture and capability claims

- **A read-only claim enforced by OPENING the store read-only still leaves statement
  classes the engine treats as non-writes.** DuckDB's `COPY (SELECT …) TO '<file>'`
  writes a local file through a read-only connection; other engines have siblings
  (`INTO OUTFILE`, `\copy`, `EXPORT`). Drive the write-class ladder before calling a
  query verb read-only: DDL (CREATE/INSERT — expect refusal), ATTACH (expect
  refusal), then the file-writing statement class. DDL refusing while COPY TO writes
  a file is a contract-hygiene row (the verb's docs say 'run a query'; a wrapper or
  agent allowlisting read verbs gets arbitrary file-write through one statement
  class) — grade P4 for a single-user local CLI, P1+ when the verb is exposed
  multi-tenant. Fix direction: a statement-type gate (allow SELECT/WITH/DESCRIBE/SHOW
  only) or documenting the COPY surface.
- **A docs SQL-capability claim is a floor, not a ceiling — drive the shapes one
  notch beyond the documented list before filing in either direction.** The docs
  list WHERE/GROUP BY/ORDER BY/LIMIT; a real analyst writes CTEs, window functions,
  HAVING, OFFSET, and joins. All passing is a re-proof event for the docs row (the
  claim is understated), and the same passthrough strength is usually WHY the
  file-write escape above exists; a documented capability that refuses is the row.
  Verify rows are real content, not empty shells — rc=0 with zero rows proves
  nothing.
- **Build synthetic fixtures in the product's CANONICAL vocabulary, never a
  synonym of it.** Ingest-time normalization (e.g. level aliases ERR→ERROR
  collapsed when the row lands) means a fixture carrying the raw alias ingests
  fine but every query for the alias returns 0 rows — mimicking a query bug that
  is your fixture's vocabulary. Read the normalization source (or its doc section)
  BEFORE generating fixtures, and treat a doc sentence that scopes a vocabulary
  trap to ONE engine as suspect: if normalization happens at ingest, the 0-row
  alias behavior is engine-independent, and the doc's scoping is a precision gap
  of its own.

## Probe an opt-in hardening tier on the ALLOW path too — the knob may ride only one verdict class

When a product offers an opt-in enforcement tier (egress, sandbox, deny-list) that documents
itself as applying 'in the payload', probe THREE seams before trusting the kernel/enforcement
behavior: (1) the tier's own loader/entrypoint driven directly — this isolates the ENFORCEMENT
contract (denial errno on a blocked target vs success on an allowed one, invalid-token refusal,
empty-allowlist deny-all); (2) the integrated path through the CLI/wrapper with the knob set,
on the REWRITE verdict (auto-sandbox/modify) — confirm the tier's applied marker appears in
that run's stderr; (3) the integrated path on the ALLOW verdict of the product's own FLAGSHIP
example for the tier — a tier composed onto the modify prefix only is a silent no-op on allow
verdicts, so the documented example can exercise nothing while every test stays green. Read
the verdict's action AND rewritten-payload field, and check the wrapper for a discarded stderr
on the engine/bridge call (`2>/dev/null`) — a swallowed stream hides exactly the loud degrade
the contract promises. Attribution discipline: prove the enforcement contract good at seam (1)
BEFORE filing the seam (2)/(3) gaps, and name which seam each verdict came from — 'the tier
engine is sound, the seam does not carry it' is a very different row from 'the tier does not
work'.

## Drive a corrupt-state path through BOTH the parse failure and the runtime posture

A rules/config file deliberately corrupted feeds two separate probes, graded separately:
the LOADER leg (does the engine print a loud, file-naming parse error — quote it verbatim)
and the RUNTIME leg (what posture does the product take with the file's rules missing —
fail-open allow-everything or fail-closed refuse). A loud parse warning plus a fail-open
posture is a PARTIAL fix of a prior silent-fail finding: record it as a re-proof event on
the existing row (premise half-closed), not as a new row — the warning names the file, the
posture still lets every command through.

## SSE / event-stream endpoints: probe the reconnect contract AND whether the sibling list's filters carry over

A stream endpoint documented right after a filtered list endpoint (`GET /events?severity=...`) invites a client to append the list's query params to the stream. Probe that pairing BEFORE trusting it: connect with the filter param and count how many replayed frames actually match. A 200 + full unfiltered tail-replay means the handler ignores query params entirely — the docs gap (filters documented one section up, no note that they do not apply) is the row; fix direction is honoring the filter on replay AND live frames or 400 on unknown params, never silence. While connected, verify the rest of the reconnect contract a real client depends on: no-cursor connect replays a BOUNDED tail (newest-N, chronological — first frame is the oldest of the tail, not the newest); resume with `Last-Event-ID: <last seen>` replays exactly the gap with zero duplicates; a malformed cursor degrades to the no-cursor tail, never an error; heartbeat comments arrive at the documented cadence (count them over a 2-3x-window capture); and cross-check stream frames against the REST list endpoint (`GET /events?limit=5` ids must agree) so a stream defect is never confused with a writer defect. Everything green is a re-proof event, not a row.

## Config write → dependent resolver read: a 200 on the write proves nothing about what the resolver sees

When a product has a management write endpoint (PATCH /config or sibling) whose data feeds a SEPARATE resolver/consumer surface (a route family, a scheduler, a plugin loader), drive write → read-back → dependent-resolve as ONE contract before trusting either side. The write and the resolver can key on different representations of the same data (a nested block vs flattened per-item keys) and every test on each side stays green while the user-visible loop is dead: the write returns 200, the resolver 404s the exact name the user just registered. Rules:

- After any 200 config write, immediately drive the dependent surface with the exact name/value written. If every dependent operation answers not-found for a name the write accepted, the finding is the missing write-side translation — file it against that, never as 'the resolver is broken'.
- Probe the alternative representation (flattened/dotted key form, per-item key) through the SAME write endpoint when the store accepts one: the shape that DOES resolve is the proof that localizes the defect to the translation between them, and it also gives you the working workaround to document.
- Read the backing store directly (one sqlite SELECT) to distinguish 'never written' from 'written under the wrong key': a single row holding the whole nested block under a literal top-level key IS the root-cause evidence a worker can act on.
- Probe the GET read-back for serialization fidelity, not just presence: values rendered as language-debug strings (a Go `map[...]` %v dump where a JSON object belongs) break every programmatic round-trip — jq getting null on a field the write just set is the tell. File the serialization defect separately when the write path is also broken; fixing one does not fix the other.

## An opt-in feature's ENABLEMENT path is part of the surface — grep the reader, not the docs

For any feature behind a config flag, the docs' config block and the built-in
defaults prove nothing about the feature working: grep the CODE for the field
the feature's init path actually reads (`cfg.<branch>.<field>.Enabled`), and
compare that branch against the one the example config and the defaults
populate. A reader keyed to one config subtree while docs/defaults fill a
sibling subtree makes the feature permanently disabled under EVERY shipped
configuration — every test (which pins one side) stays green, the endpoint
serves its 'disabled' stub, and the config file the user edits does nothing.
Distinct from the write→read-resolver contract above: that probes runtime
endpoint round-trips; this probes whether the SHIPPED CONFIG can reach the
feature at all.

Verify by booting with the shipped example config VERBATIM (no local edits)
and driving the feature's endpoint: the stub/degraded body under the
documented-on config is the row's evidence, quoting the reader's file:line and
the config block's YAML path. Fix direction: repoint the reader (or the
defaults) onto one branch and mark the other legacy — never 'document the
working key only', which orphans the shipped example file every user copies.

## Generated-binding surfaces (FFI/ABI consumers): CWD, config files, and id families

A binding-generated client (`HiloHandle`-style explicit-root constructor, namespace functions, a
udl/idl codegen step) is a surface where the classic silent killers are CWD dependence, config-file
capture, and synthetic id families. Probe all three before trusting the integration story:

- **A root-scoping / CWD-independence claim is per METHOD FAMILY until each family is driven from a
  foreign cwd.** Construct the handle from a directory far from the repo, then drive every method
  with relative paths. Handle methods can honor the root while the sibling namespace/module-level
  functions silently resolve against the process CWD — the contract holds for one family and breaks
  for the other, and only a foreign-cwd drive of BOTH catches it. File the gap scoped to the family
  that leaks, citing the family that holds as the proof the mechanism exists.
- **A `line:N column:M` parse error may describe a DIFFERENT file than the one you passed.**
  Codegen and config loaders resolve relative inputs from CWD and can walk UP through parents;
  a valid input then fails with the PARENT manifest/config's parse error and no file name in the
  message. Before debugging content, re-run from the module directory the docs name (or pass an
  absolute input path) — the fix is `cd`, not editing the input. An error that never names the file
  it parsed is itself a docs finding.
- **Hand-authoring derived state (manifest rules, fixtures) with a text replace: anchor on
  multi-line context UNIQUE to the target section.** Manifests reuse the same key name in several
  sections (`rules: []` under permissions AND at top level); a bare `replace` lands the block in the
  wrong section and the parser's type error points at the wrong shape, burning probes on a defect
  you injected. Anchor on the adjacent section key, then re-read the file and assert the block
  landed in the intended section before driving the surface.
- **Probe BOTH id families — bare records and aggregate pseudo-nodes — before filing a
  missing-record defect.** An existence pre-check that matches raw endpoints reports NotFound for a
  record that participates only through an aggregate (`pkg:mod`-style), even when a sibling
  list call proves the record exists, while directly-endpointed records return an honest empty.
  Quote the aggregate-form probe alongside the bare-form one; the fix direction is expanding
  aggregates in the pre-check (or dropping it and letting the query answer), never a docs rewrite.
  When the CLI surface prints a graceful result for the identical state, that CLI/binding error
  contract divergence is part of the same row.

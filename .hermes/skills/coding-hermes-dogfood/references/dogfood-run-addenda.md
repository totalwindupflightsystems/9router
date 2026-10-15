# Dogfood Run Addenda — build-binary verification and raw board-row appends

## Go internal-package consumers: no nested go.mod

**Build the real consumer INSIDE the target module, never with a nested go.mod.** A scratch consumer directory carrying its own `go.mod` becomes its own module and `import <module>/internal/...` refuses ('use of internal package not allowed' / 'replaced but not required'); adding a `replace` + self-require loops go mod resolution (and `go mod tidy` can even panic). The one-command fix: put the consumer in a subdirectory of the repo with NO go.mod of its own and build with `go build ./<consumer-dir>` from the repo root — it shares the root module, so `internal/` imports resolve. Remove any nested go.mod left by an earlier attempt before rebuilding.

## Detached TTL owners: verify the owner unit, not just the CLI output

**A detached TTL owner's systemd unit name keys on the hold id — a second Detach in the same second (or a re-detach after a failed spawn) collides with 'Unit ... was already loaded or has a fragment file', and the stranded hold gets NO journal record of the owner failure.** The CLI prints the spawn error but the journal shows only a clean arm/land/hold_expired chain, so 'the reverter outlives the CLI' can be silently false. Cross-check `journalctl _SYSTEMD_USER_UNIT=<unit>` against the product's journal before crediting Detach output, and grade a hold with no revert proof after TTL expiry as a daemon/owner finding, not a test artifact.

## Tick budget: fail the run early, not by attrition

**A dogfood tick has a finite budget — when a verification leg cannot finish (a build wedged under host load, a server that won't come up), report FAILED-incomplete with the evidence trail instead of looping sleep-polls until the tick dies.** The foreman can file rows from named evidence (what was verified, what was left unverified, scratch paths, journal/daemon logs); it can do nothing with a tick that spent its last hour polling `ls` for a binary. Cap any build/wait leg at ~2 poll cycles before writing the partial report — and do the write leg (board rows, log entry, commit) EARLY enough that a late discovery can be appended, not lost.


## The stale-binary trap (check the build string FIRST)

Never test a CLI's flagship feature against a binary you have not proven current:
run `<bin> --version` and compare the build stamp/commit to the HEAD you intend to
test BEFORE judging a feature missing or broken.

Mechanism: build outputs can land far from the repo — `CARGO_TARGET_DIR` may redirect
target/ to a scratch dir, CI copies binaries into PATH, wrappers resolve to an old
install. A binary sitting at the repo's `target/<profile>/<name>` path can be days
stale while your fresh build went elsewhere.

Rules:
- Run the binary you JUST built at its actual output path, not the path of convenience.
- A "missing subcommand" verdict against a stale binary is a FALSE finding; re-test at
  HEAD before filing.
- The report must name the binary's build string either way, so the next reader can
  judge currency without re-deriving it.

## Hand-authoring durable state to reach an internal surface (watchdog/journal products)

When no CLI verb can arm a hold / enqueue a record (the internal package's write
API has zero non-test callers), drive the surface by writing the state records
by hand — the on-disk format IS the product's durable interface. Get it right
the first time:

- Read the fold/parse function and the write-path validator BEFORE writing one
  record. One malformed line usually fails the whole directory loudly (by
  design — do not work around it by skipping lines; that silence is a finding,
  not a fix).
- Reproduce derived values byte-exactly: content-hash ids are sha over a
  canonical text form (`hold\n<fault>\n<target>\n<ttl_ns>\n<inverse>\n<check>\n`,
  decl text = kind + sorted k=v params joined by a unit separator like \x1f).
- Identity-scope ids (boot/epoch/instance) come from the DIRECTORY's own marker
  file (e.g. a boot.json written at first Open), never from the raw host value
  you would guess. Wrong scope does not error — the record silently grades as a
  foreign-boot leftover.
- Per-run scratch dirs (`/tmp/dogfood-<proj>-$$`), each leg its own dir, all
  cleaned at the end. Legs worth driving: happy path (promise holds), fail-
  closed (break the inverse's dependency: verdict must be honest — non-zero
  exit, fault still live, journal says so), corrupt state (one garbage line:
  fold fails loudly), wrong identity (grades stuck; kill switch still reverts
  it).
- Perf numbers worth reporting even when no PERF row is justified: cold status
  read over the journal (hyperfine 20 runs), daemon cold boot→first health
  output, kill-switch wall time vs its stated budget under concurrent load.

## Raw board-row appends (board_append.py)

- The row must be ONE COMPACT JSON line. A pretty-printed or multi-line row is refused
  with a misleading mid-file parse error — re-emit with `cat <file> | jq -c .` before
  appending.
- Post-commit board lint is WARN-ONLY: a row with `status: "open"` (read alias for
  `pending`) or off-canon keys (e.g. `created`, `fingerprint`) commits fine but prints
  warnings. Do not chase lint warnings mid-run; note them and move on.
- On a merge of a sibling lane's board commits, UNION the rows: keep BOTH copies of a
  duplicate id when the two rows describe different defects — the id collision is the
  sibling's defect to resolve, not yours to delete.

## Prove the adapter, not the service: run a control call before filing 'live interop broken'

When a protocol/transport adapter fails against a live third-party service, do NOT
file 'X fails live' from the failed call alone — the service may be picky, rate-limited,
or down. Isolate which side is wrong first:

- Render the exact request the adapter sends (a `--document`/`--dry-run`/envelope-print
  mode, or capture the wire bytes), hand-craft the minimal corrected variant of that same
  request, and send it yourself with curl against the SAME endpoint.
- Control succeeds + adapter fails = the adapter is the defect; quote the corrected
  request's delta (missing namespace, missing header, wrong content-type) as the fix
  direction. Both fail = the service/endpoint is the problem, not the adapter —
  do not file an adapter row.
- Note the demo-gate implication in the row: a green demo against loopback fixtures
  does not prove live interop; recommend the project's e2e leg run at least one
  real public service.

Also read the rendered request BEFORE the failed call's error text: a value rendered
in the wrong lexical form (integers as scientific notation, floats with locale commas)
or a mis-mapped error code (server rejection of a client-side payload defect graded as
INTERNAL instead of BAD_REQUEST) is a second finding sitting in the same envelope —
capture it in the same run instead of a second one.

## Prove the product's write path against a board COPY when the lane is read-only

A finding-filing verb is still the product even when the lane contract forbids
touching the target board: copy the board file to a scratch dir first, drive the
append verb with its board argument pointed at the copy, and grade validation,
duplicate-guard, and refusal semantics there — then verify the real board is
byte-identical afterwards. Read-only means the TARGET is never mutated, not that
the write path goes untested.

While grading the validator, probe SIBLING fields with garbage when one field is
vocabulary-validated: a CLI that refuses an off-vocabulary priority pre-write can
still accept an off-vocabulary verdict string. Validation is field-scoped, so the
asymmetric sibling lands off-vocabulary data on a live board — that asymmetry is
the finding, and the README's closed-set promise is the doc line to quote.

## Derive the untouched surface mechanically — include the verb family the LANE is named for

When a repeat run needs an angle, do not guess: read the full dogfood log and list
every verb/surface any prior run actually exercised, then drive a verb family
absent from ALL of them. Check the target lane's own tick logs for which verb its
runs actually drive — a `<project>-chaos` lane can have run only plane batteries
while the project's documented chaos machinery (the very surface the lane is
named for) has zero real-use coverage anywhere. The same check can expose an
ADOPTION gap: if the documented lane machinery has never been wired into the
lane's own tick (no instantiated lane file anywhere, zero of its row ids ever
filed), say so as an observation — the machinery working is a different question
from the fleet actually using it, and both belong in the report.

- `references/observability-stack-probing.md` — when the target ships a monitoring/telemetry
  surface (Prometheus/Loki/Tempo/Grafana-class): push real OTLP/LogQL telemetry, verify each
  downstream leg separately (store search, UI datasource, span-metrics remote_write,
  trace<->log join keys), attribute port ownership from `docker inspect` not config comments,
  and read the product's own zero-counters as proof the surface was never exercised.

## Scratch-server hygiene on unattended surfaces: pin the DB, expect a bounded lifetime, disjoint angles from same-day siblings

- **Pin the scratch server to its scratch state in writing and verify the FIRST write landed in the scratch DB.** Before launching, grep the config loader for the real env-var table (SQLITE path, credentials-file path, port) — a wrong env-var NAME that happens to be silently ignored makes the server fall back to its DEFAULT data path, so the scratch run writes into the shared canonical DB and login 'fails' because the canonical admin.key is not the scratch one (looks like a product bug, is a launch mistake). After boot, check the scratch dir for a fresh `.db`/`admin.key` pair and run the first write's row back through sqlite against the scratch file — that read-back is what proves which DB the process opened, not the env vars you passed.
- **A background scratch server on an unattended surface dies after roughly ten minutes — plan the run around relaunch, not crash diagnosis.** terminal(background=true) sessions shut down gracefully; a probe battery longer than that hits connection-refused with nothing in any log. Keep scratch DB path + credentials + port in a notes/env file, re-login after relaunch (JWTs do not survive), and never file a mid-run connection-refused as a product finding until a relaunch + single retry reproduces it.
- **Before designing the angle, read the tail of dogfood-log.md for a same-day sibling run and claim a disjoint surface.** The run-number collision rule handles numbering only; two ticks hours apart that re-verify the same closed rows are one re-audit wasted twice. Split by what the sibling skipped — it filed SKIP-install, you take the install leg; it reverified fixes, you take a never-touched journey (multi-tenant, embedding recovery, a verb family from the derive-the-untouched-surface list) — and cross-cite the sibling in both entries.
- **Budget a bunker destroy in minutes and verify via the list surface either way.** The archive step can exceed a foreground timeout (the command then silently promotes to background — do not re-run, poll it) or fail on a tar race ('file changed as we read it', home retained). A retained home is not a failure to retry blind: re-run with --force for a throwaway short-TTL agent, then confirm absence with `bunker list` — the same read-back the cleanup line already requires.

## Establish 'no change' cheaply — diff from the last tick's recorded HEAD

Before running any probe on a repeat tick, read the previous dogfood entry in
`.coding-hermes/dogfood-log.md` (it names the HEAD it was proven on), then
`git diff --stat <that-sha>..HEAD` in the real repo: a delta confined to
`.coding-hermes/` board bookkeeping means the product surface is byte-identical
— the no-op line is justified in seconds (no install leg, no re-probe, no
re-proof). State the current HEAD in the report so the next tick inherits its
baseline. Only a delta touching product code/docs triggers a real-use pass —
and even then the diff scopes it.

## Run the board's quoted acceptance commands BARE as the real-use pass — and verify ambient inputs first

An acceptance row's `detail`/`worker_summary` quotes exact commands. Those commands ARE the
real-use surface: run them verbatim (no `--board`/`--out` you add for convenience) before
driving anything else. Rules that make this honest:

- Derive each command's AMBIENT inputs before judging its result: default board paths,
  env vars, and config resolved relative to the CURRENT WORKING DIRECTORY silently change
  what a bare command reads. Run it from the CWD its closure evidence implies, and state
  that CWD when quoting the command as evidence — a command whose inputs are ambient cannot
  be cited without the CWD stated. When the bare documented form fails from the obvious CWD
  but works with inputs made explicit, the finding is the undocumented dependency (plus the
  closure evidence that quoted the bare form), not necessarily broken code.
- On a zero-match / empty-result guard exit, read what the rc and the artifact EACH claim:
  a path that writes an all-`no data` artifact to stdout while returning non-zero makes rc
  and artifact contradict each other — that contradiction is its own finding class
  (a consumer parsing stdout sees an artifact; a wrapper checking rc sees failure), with
  fix direction 'emit nothing on a non-measurement' or 'document the dependency'.
- Re-verify a prior-window ZERO in a diff against the raw store before quoting it: one
  count query over the pre-window range (`select count(*), min(spawned_at) from ticks where ...`)
  distinguishes a measured honest zero (the family did not exist yet) from a confident-zero
  lie. Report both the diff figure and the SQL count as the evidence pair.
- Generalize that re-derivation to ANY suspicious zero or cross-command disagreement
  between two outputs of the same product (a 24h build says $0.0 while the 7d diff says
  $49.1): read the collector's filter semantics first (status gate, identity match,
  cost-source), then run the aggregate yourself over the raw store with those exact
  filters. Agreement = the number is real; report that as the trust finding and file
  nothing as a defect. Nonzero in the raw store where the artifact shows zero = the
  rendering lie, and even then the residual row is usually only a missing disclosure,
  not a wrong number. Never file the disagreement row from the two artifacts alone —
  the unfiltered output often counts rows the filtered one is CORRECT to exclude.
- A just-landed fix (closed row whose commit is in recent HEAD) that no dogfood entry has
  exercised is itself a re-proof target: pick it over re-auditing older surfaces, and
  record the re-proof in the log naming the closed row id.

Tree-streaming fallback inside the bunker (clone of a private repo fails as the README
predicts): tar-over-ssh works, and when the control host's archive command is scanner-gated
or the excludes get awkward, the equivalent `rsync -a -e 'ssh -i <key> ...' --exclude .git
<repo>/ bunker-$agent@$ip:app/` is the same move — both change nothing on the repo.

## Check the local binary is an ancestor of HEAD — not just present

Before driving verbs from a repo checkout's `bin/`, prove the binary current two
ways: `--version` build stamp resolves to a commit (`git cat-file -t`), and that
commit is an ancestor of HEAD (`git merge-base --is-ancestor`; NOT-ANCESTOR means
a divergent or foreign build). Then diff `HEAD..binary-commit --stat` — a delta
confined to board/log/docs files keeps the binary valid for exercising code
paths even at a different sha; state this in the report so the next reader does
not re-derive it.

## A passing test can arm by hand the wiring production never does

When the only test of a config-gated behavior constructs the component itself (a
test helper calling `client.SetX(pp)` on objects it made), grep the real boot path
for that same call before crediting the surface: if main() builds the object but
never calls the setter, the feature is dead on the shipped binary while the suite
is green. The probe that catches it boots the REAL server binary with the env vars
set and drives the end-to-end path — never the test helper's objects. This is the
complement of the test-only-caller rule in SKILL.md: there the door was missing
entirely; here the door exists but nothing bolts it on at boot.

## A restart that failed to bind leaves the OLD process serving

A `nohup server -port X &` over a live listener exits with 'address already in
use' while the stale process keeps answering; every post-restart probe then
codes against a process whose env/config predates the edits you just made, and
the confusion reads as a product defect (hand-signed requests 401ing with a
correct key is the classic signature). After EACH restart: grep the fresh boot
log for 'address already in use', confirm the pidfile/exe points at the binary
you meant to run, and use the server's own stop verb (`<bin> -stop -pidfile`) —
never assume `&` replaced anything.

## Path-arg verbs and the CWD trap: plant a distinguishing probe

**A verb that takes a path argument may silently serve the process CWD instead — plant a distinguishing probe in the requested path and read it back through the surface before trusting the success.** Put a unique file in the directory you passed on the command line, then check it appears through the product's surface (mount listing, export, serve tree): a mount of an empty scratch dir that lists a full checkout elsewhere has served CWD, and exit-0 plus a confident banner hides it. When a distinguishing file is impractical, diff two files the surface serves against the CWD candidate to attribute which tree it actually opened.

The same CWD resolution can split a flag from its verb: a `--watch`/`--triggers` flag that derives its watch root from the process CWD rather than the target path drives reparse on the WRONG repo. Read where the watcher reports watching and file both halves of the defect when they diverge — the served-root error and the watch-root error are separate user-visible failures even when one fix closes both.

Before filing 'undocumented behavior', grep the docs for the CWD claim — some verbs document 'mounts the current directory' for the bare form while the path-argument form's semantics are simply absent. Quote the doc line that covers the bare form and name the gap as 'path-arg semantics undocumented', which is a narrower and more actionable row.

## Prove a daemon's log destination from /proc/<pid>/fd/2

The 'daemonized (pid N), log: <path>' banner is the product's claim, not evidence. `ls -l /proc/<pid>/fd/2` (and fd/1) shows the file descriptor the process actually holds — a symlink to the promised log file confirms stderr was attached, and reading that /proc fd path returns the buffered contents even when the log path itself is unreachable (e.g. under a FUSE mountpoint that shadows the underlying dir). This is the ground-truth half of any 'daemon logs to X' re-proof; a banner + an existing file can both be true while the child writes somewhere else. Complete the re-proof with the lifecycle arm: the product's own unmount/stop verb, then confirm the daemon exited (pgrep empty) and the log's final lines record the clean shutdown.

## Never probe a suspect mount with a bare write

Writes through a FUSE mount can wedge the calling tool call for its full timeout window: the mount shadows the underlying directory, so `echo > <mountpoint>/f` either fails EROFS (read-only) or blocks inside the filesystem. Do write-probes under an explicit `timeout`, and prefer the read-back of a distinguishing file (CWD trap above) as the mount-identity check — it answers the same question without risking the wedge. An underlying-write probe that succeeds can also hang OTHER tool calls on the same host afterward; keep each probe call short and tolerate an unexpectedly long one as evidence in itself (file the hang as UX data, not as a tool failure).

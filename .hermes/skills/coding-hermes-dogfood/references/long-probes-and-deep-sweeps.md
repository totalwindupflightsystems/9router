# Long Probes and Deep-Sweep Techniques (dogfood)

Depth techniques that only apply on some runs: sweeping a large fixed tool
surface, long fresh-box builds, and probing operations whose success you
cannot read from their own response. All respect the standing rule: findings
become rows, never code fixes.

## Driving a WebSocket / streamed event surface as a consumer

Streamed APIs (WebSocket topics, SSE) split into two failure families: the
stream itself and the timing contract around it. When the run's angle is the
streaming surface:

- Replicate the shipped client's EXACT message ordering — connect, then any
  pre-allocation/subscribe step, THEN the action that triggers events. A
  documented subscribe-before-send ordering is a contract to test, and
  testing send-first instead silently skips the race the ordering exists to
  fix.
- Key completion on a terminal EVENT, never on socket close: most streaming
  servers never close the topic (post-completion keepalive/poll frames
  continue by design). A consumer script that waits for close hangs even
  when the run succeeded — bound it with a timeout and exit on the terminal
  event type.
- Before filing a duplicate or out-of-order frame, grep the emitter source
  and the docs: an intentional duplicate (frontend keys on it) or a
  documented post-terminal keepalive frame is contract, not a defect. The
  classic false finding is "event arrived twice" / "events arrive after
  completion".
- Probe one intentional near-miss input (vague/underspecified request): a
  parse failure that HALTS the stream (awaiting-input event, then silence)
  is contract-valid but reads identical to a dead stream unless the consumer
  knows the halt frame — check the docs cover distinguishing them before
  filing, and note the halt frame name in the integration report. This also
  poisons perf benchmarks: a perf probe whose request the parser cannot
  resolve measures the halt path, not the headline operation — validate the
  probe request produces the FULL happy-path event sequence (end on the
  terminal event) before trusting any timing it reports. And close every
  auth gap in the perf script: probe scripts often omit the bearer token on
  an init endpoint the happy path needs (401 there fails the whole run
  silently as rc=1).
- Keep the consumer script content out of the repo working tree; write it to
  /tmp. Its transcript (event types in order, counts, latency) is the
  evidence artifact the integration report cites.

## Sweeping a fixed tool/command surface (MCP, CLI families)

Runs gravitate to the documented headline tools and re-prove them. The
untouched remainder is where the defects live. When the surface is a FIXED
list (17 MCP tools, N CLI verbs):

- Drive ALL of it from one scripted stdin session, not one call per tool:
  write every NDJSON message to a JSONL file and feed it once
  (`hilo serve --mcp < messages.jsonl`), capturing stdout and stderr to
  separate files — stdout is protocol-only, tracing pollutes it.
- Include one missing-required-argument negative case per parameterized
  tool; a clean `-32603` naming the argument is a pass, a hang or a 0-byte
  response is a finding.
- READ each response's SHAPE, not just success: a tool whose parameter name
  differs from the obvious guess (`module_name` vs `path`) surfaces only
  when called; a plan/execute operation that omits its mode flag surfaces
  only when you look at fields.
- Re-verify nothing was mutated before reporting a 'plan-only' probe:
  stat/du the target tree before and after. A destructive-looking operation
  whose response carries no explicit dry-run/applied flag is unverifiable by
  shape — file the missing flag as its own finding, because a script or LLM
  consumer keyed on response shape has the same blindness you worked around.
- Census the log/board first: tools already proven by prior runs need one
  smoke call at most; spend the run's depth on the remainder.
- **Probe the trust boundary, not just the features: on any filesystem/
  resource-touching tool, feed an out-of-tree ABSOLUTE path and a `..`
  escape and inspect what comes back.** A resolver that only rewrites
  mount-owned/relative paths and passes absolute paths through to the kernel
  serves the whole host to the client — the product's client is an agent, so
  this is its primary trust boundary. Confirm the hole at source (the path
  resolution function: does any branch confine to the workspace root?)
  before filing, and quote file:line of the unconfined branch.
- **Test the index-coverage premise of every search/retrieval tool: create a
  fixture the index structurally cannot see, query its distinctive
  vocabulary, then add one edge/import and re-query.** Same queries, same
  file, different result = the enrichment channels ride a coverage set
  narrower than the corpus (files with no edges, no frontmatter, no declared
  type are the usual victims) — quote both the coverage counter the builder
  prints and the before/after query pair in the row. A 'no results' on a
  file the tool was built to find is a P1, not a miss.
- Build the HEAD binary locally with a SCOPED, well-warmed build
  (`cargo build -p <leaf-crate>` / `go build ./cmd/<tool>`), not a full
  workspace build: a shared host's first full build can take hours under
  sibling load, and the leaf crate usually reuses warm deps in minutes.
  Verify the artifact is actually at HEAD (`--version` build stamp or the
  recorded sha) before attributing any verdict to it — an old binary that
  happened to still be on disk answers for the wrong code.

The api-surface-probing ladder (bisecting a tool's documented API one minimal
snippet at a time) is the companion technique: record what actually works,
build only on the proven surface, file dead features as tasks, wire a canary.

## Probing a security/isolation feature that gates on PRIVILEGED infrastructure

Some flagship features (per-agent firewall policy, cgroup isolation) are
ENFORCED BY THE ROOT SIDE and invisible to the unprivileged client. A
pass/fail read from the CLI alone proves nothing; the finding lives on the
host. When the run's angle is such a feature:

- **Read the enforcement state on the HOST, not from the product's own
  response**: `nft list tables` / `iptables -S` / cgroup paths after every
  enforced-mode spawn. A documented mode flag that exits 0 while the host
  shows no chain is a silent-ignore finding (old daemons accept new flags
  and do nothing); absence-after-open-mode-spawns is equally evidence —
  it re-pins the 'zero behavior change' law live.
- **Version-skew is part of the surface.** Before any enforced-mode probe,
  resolve the daemon's BUILD commit (`<daemon> version` commit field, or the
  binary mtime on the host) and test whether the feature commit is an
  ancestor (`git merge-base --is-ancestor <feat> <build-sha>`); a daemon
  built hours BEFORE the feature merge accepts the flag and ignores it.
  The close note of the feature's own board row often admits the live
  battery was deferred — that is a first-class dogfood angle, not history.
- **Sanctioned root probe path:** if the repo's own docs define a coexist
  recipe (scratch ports, own state dir, own port range, config file under
  /tmp), a HEAD daemon built in a scratch clone and run as root alongside
  the production one is legitimate real use — production binaries and
  systemd units stay untouched. Check sudo availability first
  (`ssh host 'sudo -n true'`); without root on the host, record the
  enforcement as UNPROVEN rather than substituting a weaker signal.
- **Let the failure-configuration design itself.** When an enforced mode
  'fails the spawn', drive the failure shape deliberately (empty allowlist,
  unreachable resolver): a precise staged error plus verified rollback (no
  user created, no chain left, no registry entry) is a finding that the
  fail-closed contract works — as valuable as a passing happy path, and
  reachable precisely because the happy path is broken.
- **When the documented command fails but the capability exists, find the
  argv truth before filing a wrong root cause**: grep the source for the
  exact exec'd argv builder AND the executor around it — a helper that
  passes a rule PAYLOAD where the verb expects a FILENAME (no stdin wiring
  in the executor) fails identically to a missing firewall binary. Quote
  file:line of both the argv builder and the Run() call in the row.

## Long fresh-box builds (install leg)

- Launch detached with `( setsid bash ~/x.sh > ~/x.log 2>&1 & )` as a
  separate statement — never `nohup ... &` inside an ssh `&&` chain (shell
  precedence backgrounds the whole chain and ssh exit kills it, log reads
  empty).
- Start long-lived local dev servers as tracked background terminal sessions
  (`terminal(background=true)`), not `nohup ... &` inside a foreground call —
  foreground `&` is refused by the harness and a foreground server call
  blocks the tick until timeout. Health-check in a SEPARATE follow-up call.
- Poll `tail ~/x.log` in SHORT separate calls — each poll must fit the
  harness terminal window (~3 min); a poll that sleeps past it dies mid-tick
  and looks like a tool failure. A 25-minute full-workspace release build on
  a 6-core fresh box is normal, not a failure.
- Put the script AND its log under the agent's $HOME, not /tmp: on a
  multi-tenant bunker host another agent user may already own the /tmp path
  (your `cat > /tmp/x.sh` then writes nothing or fails; executing their file
  runs THEIR content). Check `ls -la /tmp/<name>` if a remote script
  misbehaves — a foreign uid owner is the tell.
- Feed scripts over ssh stdin (`ssh host 'cat > ~/x.sh' < local.sh`), never
  scp on unattended surfaces; never `ssh -n` on the transfer leg (0-byte
  file, exit 0).
- **Capture the build's real exit INSIDE the remote script: `cmd > log 2>&1;
  rc=$?; echo RC=$rc` — never `cmd | tail -3; echo RC=$?`, which reports the
  tail pipe's status and prints RC=0 over a failed build** (the failure is
  still visible in the log lines, but a scripted consumer reading the echoed
  rc takes the false green). Verify the artifact actually exists after a
  claimed-success build before reporting install-leg PASS.
- **Run a >10-minute remote build as a tracked background terminal from the
  start and manage it with process_manage (poll/wait by session_id)** —
  foreground waits get clamped to the ~180s window and you spend the tick
  re-issuing waits. The unattended surface wraps the command in a shell
  snapshot (`bash -lic ...`), so the session's reported pid is the WRAPPER:
  poll liveness via the process list on the remote host (ssh `pgrep`/`ps`)
  or just process_manage poll on the session, never by killing/re-running on
  a stale pid guess. Poll REMOTE build progress with one short ssh call
  (`tail -2 build.log; ps aux | grep -c [c]argo; uptime`) — log lines show
  which crate it is on, the cargo process count proves it is alive, and
  loadavg tells you whether it is progressing or starved (a shared build
  host can run a 25-minute build for 60+ minutes under sibling contention;
  record the load evidence with the build time, not just the number).
- One remote script per phase (build / smoke / destroy) re-probing state from
  scratch beats one mega-script: a phase that times out on the harness leaves
  the others idempotent and re-runnable.

## Pre-commit guards on docs-only dogfood commits

- A guard that stalls under host load (individual tests pass when run
  alone, loadavg is high, the guard's own timeout expires) is a real
  defect — but not yours to fix from a docs-only commit. Retry once; if the
  timeout repeats, commit `--no-verify`, state the reason AND the load
  evidence in the commit message, and attach cross-evidence to the board
  row that already tracks the load-sensitivity (check for one before filing
  a duplicate).
- The same doctrine extends to CODE commits when the guard's full-test arm
  structurally exceeds ANY sane budget on the loaded shared host. Measure
  the suite's wall time ONCE with a direct run (`pytest -q`, background,
  poll by session id) before burning hours on budget-knob retries: a
  measured ~10x-the-largest-budget wall time proves the suite is
  load-starved, not broken. Then in ONE commit script: run the narrow
  subsets your diff touches (`pytest -k <affected>`) and hold their pass
  output as evidence, confirm the guard's other arms (secrets, lint) green
  in a recent guard log, commit `--no-verify` with reason + measured number
  + load evidence in the message. The narrow subset passing is what
  distinguishes env-timeout from a real regression — never bypass without
  it.
- The gate's pytest-budget env var only reaches the guard when the guard
  process inherits your shell env; a timeout that keeps expiring at a value
  you did not set means the hook ran a different env (or the var name
  drifted) — check the guard log's echoed budget before concluding the knob
  is dead, and don't loop on it.
- Sibling lanes share the same `.git/index.lock`: a commit failing RC=128
  `index.lock exists` is usually a sibling's in-flight commit, not
  corruption. `pgrep -f 'git commit'` first; wait for the sibling to exit,
  then re-run. A lock with no git process is stale and safe to remove.
- Verify the landing: `git show --numstat --format='' HEAD` must match your
  staged intent, then push and confirm
  `git merge-base --is-ancestor HEAD origin/<default>` before reporting.
- Terminate the dev server you started before reporting: kill by the exact
  command pattern you launched (`pkill -f '<exact cmd>'`) and confirm with a
  health-curl. Other tsx/node processes may belong to containerized lanes or
  sibling agents — never pkill a broad pattern like `tsx` or `node`, and
  never kill a process whose cwd you did not set. (Commit-by-pathspec rules
  live in the main SKILL.md pitfalls; they apply here too.)

## The zero-defect tick: sweeping a mature, board-idle project

When a foreman tick lands on a project whose board has no actionable rows
(all complete; the only open ones are owner-deferred/blocked), a fresh
black-box sweep is the legitimate fallback — never manufacture rows to have
something to close.

- Build the binary FRESH from HEAD (`go build -o /tmp/<bin> ./cmd/<tool>`);
  a stale installed copy in $PATH answers for the old code and poisons
  every arm. Record the build rc and HEAD sha in the evidence.
- Census the verb/tool surface first, then list the repo's OWN probe
  batteries (scripts/*_probe.sh), and spend the run on the bands NO battery
  covers — re-proving covered bands wastes the tick.
- Sweep ~30 arms across the uncovered bands: happy path, every refusal
  class (unknown key, arg-count, ambiguity, empty input), path traversal
  (`../`, absolute), symlink write-through, read-only/mode preservation,
  malformed input (NUL, raw newline in JSON), stdin form, no-op form.
- For each refusal candidate, read the error's declaration site before
  filing: a typed wrap (`fmt.Errorf("...%w (%w)")`) can be DOCUMENTED
  CONTRACT whose comment explains the outer sentinel (callers matching it
  keep working) — grep the message fragment, read the comment, and only
  file when the wording contradicts its own documented intent.
- Check the off-by-one pre-solve corpus (discover endpoint + answers dir)
  for the failure class BEFORE designing any fix; submit a post-debug
  answer only when something non-trivial was actually debugged — a
  candidate that resolves to documented intent owes no submission.
- Write the arm-by-arm evidence file into the repo's evidence dir with a
  ch:trace footer, commit under the docs class with the co-author trailer,
  push, and verify CI on the pushed sha.

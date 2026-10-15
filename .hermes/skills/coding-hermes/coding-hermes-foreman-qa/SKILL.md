---
name: coding-hermes-foreman-qa
description: "Use when running qa foreman ticks."
version: 1.3.0
platforms: [linux]
metadata:
  hermes:
    tags: [coding-hermes, foreman, project-skill, qa]
    related_skills: [coding-hermes-foreman, coding-hermes-foreman-duckbrain-usage, coding-hermes-traceability, coding-hermes-dogfood, bunker-agent-isolation]
---

# qa — foreman ops

> Project skill for `coding-hermes-foreman`. **LOCAL-ONLY** — never shipped to the public
> `coding-hermes/skills` repo. Consolidated during the 2026-09-22 per-project
> foreman-skill migration. Sources merged: skill:SKILL.md (51334B)

# QA Foreman Ops

The stand-in PM's sibling. The PM finds work and gaps on boards; the QA foreman
finds BRITTLENESS by running projects on a CLEAN machine — full fresh-system
install, full CI pass, full docker deploy, UI probe, upgrade path, and FULL
chaos testing. Bane's framing: *"not just we have valid code but does that code
give us things that are brittle"* — a suite that passes but HANGS when
disconnected, or a service that crash-loops on a truncated state file, is a
P1/P2 finding even though "all tests pass".

## The cron

- `qa-foreman` (job 52d19561484a), daily 06:45, delivers to origin.
- Runs `qa_discover.py 2` → for each pick, `bunker-qa.sh run <workdir>`
  (default server bunker-las-02 since 2026-09-10 — las-03 was removed from
  ~/.bunker/config.yaml and the stale default burned 4 consecutive days of
  P1 spawn-failure findings; override with BUNKER_QA_SERVER) → interprets
  evidence → files QA-<PROJ>-NNN rows → records in ledger + DuckBrain → reports.
- bunker-qa.sh has a deterministic-failure preflight: server missing from
  config or ssh-unreachable records ONE FAIL evidence row and exits rc=2
  BEFORE the spawn retry loop (static config errors are not transient;
  never burn retries on them).
- Timer ownership: scheduler project roles (`<project>-qa`, command
  qa-scheduler-tick.sh) own the cadence; the old Hermes cron
  dagger-qa-audit (e5c6f461b31f) is disabled/relic.

## Dagger-native QA pipeline (`qa-scheduler-tick.sh`) — RETIRED as a lane executor

> **RETIRED for QA lanes (Bane, 2026-09-17).** QA lanes no longer drive this
> pipeline. `qa-scheduler-tick.sh` → `dagger-role-tick.sh qa` →
> `dagger run examples/coding-hermes/qa.ts` is the old dagger, and the QA lanes
> run the `qa-foreman-ops` skill prompt on the BUNKER path instead
> (`bunker-qa.sh launch` → collect) until the new dagger is built. The
> scheduler `qa` namespace `default_prompt` and all 13 enabled QA lane prompts
> say so, and the 31 legacy command-mode QA rows had their `command` cleared so
> re-enabling one cannot resurrect the script. Read the rest of this section
> only to debug or forensically grade an OLD dagger run — never to drive a QA
> tick, and never as the shape a new lane should take.

Some QA lanes run `bunker-qa.sh`; others run `qa-scheduler-tick.sh` via the
scheduler's `<project>-qa` role command. The two paths differ:

**Invoking a `<project>-qa` lane by hand — set the row name, or you QA OTHER
projects.** The wrapper derives its target from `CODING_HERMES_PROJECT`:
`<project>-qa` → TARGETED mode on that project; unset (default `qa-audit`) or
any other value → RANDOM discovery, which picks two unrelated projects and
files QA rows on THEIR boards. Dispatch as
`CODING_HERMES_PROJECT=<project>-qa CODING_HERMES_TICK=<tick-name> bash ~/.hermes/scripts/qa-scheduler-tick.sh`
(the script `cd`s to `~/.hermes/stand-in/pm/qa` itself — the cwd you call it
from does not select the target). Confirm the mode from the run before
interpreting anything: `resolve_targets` in `run.log` reads
`{"mode":"targeted","source":"env"}` for your row vs
`{"mode":"random","source":"qa_discover"}` when the env was missing.
Prompt-mode lanes (`<project>-qa` rows with an EMPTY `command` in
`~/.hermes/coding-hermes/scheduler.db`) arrive as an LLM tick whose only job is
to dispatch this wrapper and report — the fan-out, findings and commit are the
pipeline's, so do not re-implement any of it by hand. That dispatch does NOT
export the target env, so the tick must pass it itself:
`CODING_HERMES_PROJECT=<row>-qa CODING_HERMES_QA_TARGET=<base-project>
CODING_HERMES_TICK=<tick-name> bash ~/.hermes/scripts/qa-scheduler-tick.sh` —
run bare, the wrapper silently becomes random discovery (and confirms so only in
the `resolve_targets` payload), which files QA rows on unrelated boards.

| | Bunker path | Dagger path |
|---|---|---|
| Driver | `bunker-qa.sh run <workdir>` | `qa-scheduler-tick.sh` → `dagger-role-tick.sh qa` |
| Executor | JIT temp agent on bunker server | `dagger run examples/coding-hermes/qa.ts` |
| Evidence | `/tmp/bunker-qa-evidence-<run>.jsonl` | `run.jsonl` / `run.grouped.jsonl` in `/tmp/dagger-role-qa-<pid>-*/` |
| Timeout | 10 cells × per-cell | `run.log` line `Passed: N | Failed: 0` when done |

The dagger pipeline (4 nodes: `resolve_targets` → `targets_list` → `qa_targets`
[foreach] → `report`; each target runs 5 internal nodes: `run_battery`,
`parse_cells`, `interpret`, `file_findings`, `duck_record`). Both `duck_record`
nodes may fail with `invalid DuckBrain API credential from sidecar or legacy
fallback (empty value)` when `DUCKBRAIN_KEY` is not propagated into the dagger
serve process — non-fatal, findings still reach `file_findings`. The error
signature:
```
qjs: eval failed: Error: qa duck_record: invalid DuckBrain API credential
from sidecar or legacy fallback (empty value)
```
The fix is the same as for `dagger-role-tick.sh` duckbrain-sync: the plaintext
key lives in `~/.duckbrain/token-*.token` sidecar (not in `auth.json` which
now stores only key hashes); `qa.ts` needs the same sidecar lookup that
`dagger-role-tick.sh` already has for the duckbrain-sync pipeline.

**Reading dagger QA output:**
- `run.log` — pipeline start/end times, node timeline, final `Passed/Failed`
  summary, evidence tail.
- `run.jsonl` — raw event stream; scan for `"status":"error"` nodes. Concurrent
  appenders can tear a line mid-object, so validate line-wise before parsing and
  fall back to `role.db` `checkpoints` — a decode error is a logging artifact,
  never evidence of "no error events".
- `run.grouped.jsonl` — same events grouped; use when line-splitting matters.
- role.db WAL — `sqlite3 role.db "SELECT name FROM sqlite_master WHERE
  type='table';"` to confirm schema. Inner node PAYLOADS live here too:
  `sqlite3 role.db "SELECT step,node_id,status,output FROM checkpoints ORDER BY
  step;"` (columns run_id, step, node_id, status, output, console, created_at);
  `run.jsonl` truncates `output` and leaves `console` null.
- `run.log`'s `Passed: N | Failed: 0` counts TOP-LEVEL nodes only — an inner
  node can finish `"event":"error"` (typically `duck_record`) while the headline
  stays green. Scan `run.jsonl` for error events before calling a run clean, and
  treat whatever a failed inner node produced as UNVERIFIED, not as done.
- **For prompt-mode QA ticks, prefer the on-disk Dagger run dir over terminal
  output.** `qa-scheduler-tick.sh` backgrounds the wrapper, and the current
  session cannot receive async completion after the turn ends, so polling the
  terminal session is unreliable. After dispatch, recover progress from the
  run dir: `/tmp/dagger-role-qa-<pid>-*/` contains `run.log`, `run.jsonl`,
  `run.grouped.jsonl`, and `role.db`; use those to confirm completion and
  grade the run. Do not treat missing terminal output as a failed run.
- **Grade cells from the raw logs, not from the evidence excerpt.** The evidence
  `detail` is a `tail -3` window, so a Go-suite FAIL can read
  `rc=1 under cap: ?<pkg> [no test files] … FAIL` with the failing package cut
  off — which misfiles a permission error as a memory-cap hit. Pull
  `~/qa-logs-*/{ci,native,res,inst,ep}.log` off the JIT agent while it still
  exists (the destroy trap takes them with it); identical failures in `ci.log`
  and `native.log` mean the environment, an act-only failure means the workflow.
  A FAIL the filed row calls "unreproducible" or says "names no failing step or
  package" is that WINDOW talking, not the repo — the failing package and test
  line print early and get cut. Pull the agent log and re-diagnose before
  accepting or repeating such a row. And when the native suite is red, every cell
  that re-runs it (`chaos-resource` under a cap) collapses into the SAME cause:
  file it once, naming the cells it covers.
  For an act/CI cell, the failing STEP's own exit code grades it: golangci-lint
  returns 1 = issues, 4 = TIMEOUT (its `pkg/exitcodes` constants — read them, do
  not guess the meaning). A Lint step failing with code 4 whose duration ≈ the
  repo's `.golangci.yml` `run.timeout`, on a HEAD where HOSTED CI is green, is a
  cold-cache timeout inside the act container: an act artifact, not a code lint
  break. Report it that way instead of echoing the row's "CI red, step
  unreproduced" — that row's premise overstates the defect.
- **The 420s clamp also hits the DAG's own `run_battery` tool call.** The
  foreground call is auto-backgrounded, so the node's `done` event can land
  MINUTES after the battery exited (observed: battery done 08:03, node done
  08:10, pipeline wall clock 32m for a ~17m battery). Progress therefore comes
  from the agent (`~/qa-evidence.jsonl`, `~/qa-logs-<pid>/*.log`) and the host
  `BUNKER_QA_EVIDENCE` file, never from the node timeline — and pull the
  per-cell logs off the agent BEFORE the destroy trap takes them.
- **A killed post-spawn attempt leaves 0-byte evidence with NO FAIL row.**
  `bunker-qa.sh` replaces the `write_fail_if_empty` EXIT trap with `cleanup()`
  once the agent has spawned, so a SIGKILL between spawn and the remote
  script's `: > $EVID` records nothing — indistinguishable from "no cells
  ran". When the host evidence is 0 bytes AND the process is gone, check
  `bunker list --server <srv>`: an agent still present with a `~/qa-<proj>` dir
  means the battery is mid-sync (wait, do not read it as no-cells); an agent
  left behind with no live process is YOUR orphan —
  `bunker destroy <agent-id> --server <srv>` (the trap never fired).

## Scripts (deterministic layer)

- `~/.hermes/scripts/bunker-qa.sh` — the JIT pipeline. Spawns a temp agent on
 the `BUNKER_QA_SERVER` default via TAILSCALE hostname (TTL 4h) — read the
 live default out of the script, never hardcode a server name (a
 decommissioned default burned days of P1 spawn-failure findings), runs 11 cells (toolchain-bootstrap + the ten below), writes JSONL
  evidence to /tmp/bunker-qa-evidence.jsonl, destroys via trap. Cells:
  fresh-install · ci-pass (act with correct dockerd socket) · docker-deploy
  (compose up --build + health probe) · ui-probe (:3111) · upgrade (prev tag →
  HEAD) · chaos-disconnect (bogus proxy: clean fail vs HANG) · chaos-shutdown
  (SIGTERM stop/restart + SIGKILL recovery) · chaos-corruption (truncated state
  file) · chaos-resource (3G memory cap) · chaos-errorpath (missing config:
  clean usage vs PANIC). Statuses: OK / FAIL / INFO / N/A / UNVERIFIED /
  SKIPPED (additive, Bane 2026-09-02: an applicable stage the environment
  could not run — cell detail MUST carry the reason; never silent, never fake
  OK, never N/A, which is reserved for repos with no such artifact).
  **UNVERIFIED ≠ OK** and **SKIPPED ≠ OK** either.
- `~/.hermes/scripts/qa_discover.py [N]` — picks N projects: never-QA'd first,
  then oldest-QA, random tiebreak ("hint of chaos" — uneven sweep on purpose).
  Ledger: `~/.hermes/qa/ledger.jsonl` {ts, project, status, cells, findings}.
- Requires the rebuilt bunker CLI (300s transport — see
  bunker-agent-isolation references/jit-qa-and-spawn-timeout-pitfalls.md).

## Full CI battery — every tick, non-negotiable (Bane 2026-09-02)

Every QA tick runs the FULL battery on top of the 10 cells — lint, the full
test suite, docker build, compose config validation — each as its OWN evidence
cell and filed as its own finding. No tick passes on samples. Required stages
(commands are the FULL forms — no filters, no subsets):

| Stage | Cell | Full command set |
|---|---|---|
| Lint | `lint` | whole-tree lint: `golangci-lint run ./...` / `go vet ./...` / `eslint .` / `pnpm lint` / `ruff check .` / `cargo clippy --all-targets` / `make lint` |
| Full tests | `tests` | `go test ./... -count=1` (NO `-short`, NO `-run`), `npm test` / `pnpm test` (full), `pytest` full tree, `cargo test`, `make test` |
| Docker build | `docker-build` | if a Dockerfile OR compose file exists: `docker build` / `docker compose build` |
| Compose config | `compose-config` | if `docker-compose*.yml` / `compose*.yml` exists: `docker compose config -q` (or `docker-compose config -q`) before any `up` |

Escape hatches (same contract as BUNKER_QA_INSTALL_CMD/BUNKER_QA_NATIVE_CMD):
`BUNKER_QA_LINT_CMD` / `BUNKER_QA_TEST_CMD` / `BUNKER_QA_DOCKER_BUILD_CMD`.

**The contract is the rule; the deployed cell set is the reality — know which
one you are reading.** The deployed battery emits toolchain-bootstrap,
fresh-install, ci-pass, upgrade, docker-deploy, ui-probe and the five chaos
cells; NO `lint`/`tests`/`docker-build`/`compose-config` cell exists in it
(0 of a month of `bunker-qa-evidence-*.jsonl` rows carry a `lint` cell), so a
per-project "stage missing" row would be the SAME harness finding re-filed on
every board. Establish that gap once as a harness observation, and grade the
repo's lint/test coverage from the `ci-pass` act job set (name how many jobs ran
green). File a per-project stage gap only when the stage EXISTS in the harness
and did not run for this target (knob unset / SKIPPED with no reason).

**Sample checks are a QA failure.** Any of these = verdict FINDINGS with a P1
battery finding (same class as QA-BUNKER-1's lying gate), never CLEAN:
`-short`/`-run` subsets or time-boxed suites · lint on sampled files ·
act reporting zero jobs green or failing while ci-pass claims OK · docker
skipped with no recorded reason · ANY required stage missing from the evidence
(no `lint`, no `tests`, no `docker-build`/`compose-config` when the repo has
Docker artifacts). A stage that did not genuinely run is UNVERIFIED or
SKIPPED-with-reason, never OK; an incomplete battery is a finding about the
battery itself (zero-cell rule applied per stage).

**Docker fallback ladder (never silent).** Docker unavailable in the run
environment → (1) build with the project's OWN toolchain (`go build ./...`,
`npm run build`/`pnpm build`, `cargo build`, `pip wheel .`/`python -m build`,
`make build`); (2) record `docker-build`/`compose-config` as SKIPPED-with-
reason — detail names WHY (daemon unreachable / act fatal-EOF class / compose
needs daemon / the agent's STATIC docker CLI has no compose plugin — signature
`unknown shorthand flag: 'd' in -d` followed by docker's `Common Commands:`
usage help, which is how `docker compose up -d --build` dies when only the
docker tarball was installed; the compose path never ran, so that cell is a
harness artifact, NOT a project deploy FAIL, and the same signature kills `chaos-shutdown` too, because that cell also drives `docker compose up/stop/start/kill/down` — it then reads `rc=125` with an empty detail tail, so both docker cells are ONE harness cause and the shutdown behavior is UNVERIFIED, never a chaos P1) AND the native-build result. Native build rc≠0 → `docker-build`
FAIL (no path builds the artifact). Native build rc=0 with Docker artifacts
declared → SKIPPED is an INFO observation (P3): container path unverified
this cycle. Every SKIPPED cell is listed in the run summary + DuckBrain record.

## BUNKER_QA_SSH_PORT on bunker-mvp: default 2223 is DEAD (2026-10-02)

Agents on bunker-mvp are reachable ONLY via the host sshd on port 22 (`bunker-<id>@bunker-mvp`, both the host key `~/.ssh/id_ed25519_bunker_mvp` and `~/.bunker/keys/<id>`). Without `BUNKER_QA_SSH_PORT=22` every launch burns 3 spawn attempts: the spawn SUCCEEDS server-side (journalctl shows `dockerd ready`), then spawn_agent's reachability probe silently fails and destroys the agent — stderr shows only `bunker spawn`'s informational `Docker Tunnel:` line, which misreads as a docker problem. Always dispatch with `BUNKER_QA_SSH_PORT=22`.

## hermes-dagger: zig-cc cannot link go-duckdb (QA-HERMES-DAGGER-32, one cause, three cells)

The battery's zig 0.15.2 wrappers (~/tools/bin cc/c++/ld) fail `go build ./...` on go-duckdb v1.8.5 with dozens of `ld.lld: undefined symbol std::__cxx11...` errors; the SAME tree with system gcc builds rc=0 and `go test -race -count=1 ./...` = 36 ok with only cmd/dagger + src/mcp FAILing on `corsa not found` (QA-HERMES-DAGGER-22's missing skip-guard on a fresh agent). fresh-install + ci-pass native + chaos-resource all collapse into this ONE toolchain cause — re-run the suite natively on the agent (no CC export) before grading, and name every covered cell in the row.

## Destroy-refused then deadline_exceeded is a TWO-STAGE failure

(1) `destroy refused: user still owns live processes` (battery sshd/containerd-shims) — fix server-side: `ssh root@<server> 'pkill -u bunker-<id>'`, retry. (2) Then client `deadline_exceeded` while the server logs `agent home archive failed; home RETAINED` + `next_retry_in: 1h0m0s` reaper backoff (11G home, gzip killed): client retries CANNOT fix a server-side archive kill — record the leak in the ledger `destroy_leak` field and let TTL/backoff reap; evidence must already be scp'd off.

## Sibling git commit can hold .git/index.lock for minutes

A worker's pre-commit guard runs the full suite inside its commit, so the lock outlives any poll window. Never remove the lock; poll until it clears, then `git commit -- <board file>` (pathspec only), and check `origin/master..HEAD` for sibling commits before any push — pushing would publish theirs.

## Interpretation rules

- Finding = cell FAIL or INFO (INFO = brittleness observation worth a row).
  N/A and OK are not findings. UNVERIFIED ≠ OK — a cell you couldn't run is
  reported as UNVERIFIED, never upgraded. SKIPPED-with-reason is reported
  (never a pass, never silent); a sample-based or stage-incomplete battery is
  itself a P1 finding (rule above).
- Severity: P1 = fresh-install/ci-pass/docker-deploy FAIL, chaos FAIL
  (hang/panic/crash-loop), full-battery stage FAIL (`lint`/`tests`/
  `docker-build`/`compose-config` — same class as ci-pass FAIL), sample-based
  battery · P2 = upgrade FAIL, chaos INFO worth fixing ·
  P3 = minor INFO, docker stage SKIPPED-with-reason while the native
  toolchain build passed.
- **N/A is valid only when the repo genuinely lacks the artifact — verify,
  never transcribe.** Two cells under-detect: `ui-probe`'s gate is a
  `package.json` carrying a `dev`/`start` script, so a Go or Python service that
  serves an embedded SPA reports "no web UI detected" while the live service
  answers 200 `text/html` — probe it
  (`curl -s -o /dev/null -w '%{http_code} %{content_type}' http://localhost:<port>/`)
  before accepting; and `chaos-corruption` truncates the FIRST `*.db` under depth
  3 (`find . -maxdepth 3 -name '*.db'`), which on a repo carrying a VFS/analysis
  cache — or an unreferenced dropping left by another tool (e.g. a stray tool DB at
  the repo root) — is NOT the service's state DB, and it never restarts
  the app. Before grading the cell, `grep -rl '<db-name>'` over the repo's sources:
  zero references means the truncation tested nothing — grade the cell a harness
  premise gap and do not interpret its rc or log as product behavior. Its INFO
  asserts nothing either way, so answer the question yourself with a direct
  probe and record its evidence; do not treat the cell's INFO as a verdict.
  For docker/upgrade N/A, confirm the repo has no Dockerfile/compose and no
  release tags first.

## Board injection (pm-injected-board-rows conventions)

- JSONL-canonical boards at `<workdir>/.coding-hermes/board/tasks.jsonl`;
  append via the append_board_event.py conventions (coding-hermes-jsonl-board-
  append skill). If the board is absent/non-JSONL, record in DuckBrain and say
  so in the report.
- Row shape: id `QA-<PROJ>-NNN` (next free — scan existing ids, never reuse a
  pending one) · priority P1/P2/P3 · reasoning = `"QA foreman cycle <date> —
  fresh-system CI pass + chaos on <BUNKER_QA_SERVER> (<cell>)"` · review_notes =
  evidence tail + repro command. Boards carry BOTH id forms (`QA-<PROJ>-004`
  zero-padded and `QA-<PROJ>-5` bare) — treat them as one series and continue
  after the highest suffix in either form.
- **DEDUPE CONTRACT (2026-09-10, wired into qa.ts file_findings):** before
  appending, scan the board for (a) findings whose exact TITLE is already a
  PENDING row — skip them, the row stays actionable; (b) the highest suffix
  ever used — continue numbering after it (never restart at -1; restarting
  re-filed QA-HERMES-DAGGER-1 28x before the fix). Re-finding an already
  open row is NOT progress; filing it again is board pollution.
  Dedupe is EXACT-TITLE only, so a RE-WORDED repeat of the same defect slips
  through and the run still reports `0 deduped` (fresh-install cgo / act-CI rows
  re-filed against a pending row of the same defect the day after it was filed).
  After every run, compare the new rows against the PENDING rows by DEFECT —
  same failing cell + same root cause, titles allowed to differ — and say which
  new rows duplicate which open ones. The pipeline cannot catch that; you can.
- **Guard-override rows are harness noise, not findings.** When `interpret`
  returns no verdict the mechanical guard files
  `Battery cells FAILED but model judged ? (guard override)` with `cell: "?"` and
  `detail: "Failed cells: <A>, <B>"` — it names nothing and duplicates the
  pending rows for those cells. Report the run as UNINTERPRETED (the analysis
  never happened) and check the row against those cells' existing pending rows
  instead of counting it as new.
- **Per-stage rows**: one `QA-<PROJ>-NNN` row per failing/INFO battery stage
  (`lint`, `tests`, `docker-build`, `compose-config`) — the stage name is the
  `(<cell>)` token in reasoning; never merge stages into one "CI" row.
- Commit board-only as qa-cron identity:
  `git -c user.name="qa-cron" -c user.email="qa@coding-hermes.local" commit -m "add QA-<ID> findings (QA foreman <date>)"`.
  In the DAGGER path the `file_findings` node makes this commit ITSELF (subject
  `qa-cron: <date> findings (N new, M deduped)`, board-only) — read it out of
  the node payload in `role.db` instead of hunting for a separate commit step.
  Push convention depends on the repo: the QA TARGET repo gets the board commit
  PUSHED and verified (`git rev-list --count origin/<branch>..HEAD` = 0 — the
  qa-cron findings commit is the tick's only artifact and an unpushed tick is
  incomplete), while the stand-in PM repo's commits usually sit unpushed.
  Pushing a commit `file_findings` authored does NOT break a read-only lane's
  covenant — the covenant forbids originating or editing rows, not publishing
  the pipeline's own board-only commit. Confirm the convention from history
  before deciding (`git log --oneline --grep=qa-cron` and whether those commits
  sit on `origin/<branch>`): a repo whose prior qa-cron commits are all
  published expects this one pushed too.
  **Exception — do not push when the branch carries another lane's unpushed
  CONTENT commit.** A sibling worker's feature commit (its brief typically says
  "commit only, do NOT push") sits on the same branch, so pushing the board
  commit publishes unverified code whose gate the project foreman owns. Report
  `origin/<branch>..HEAD` with each commit named, state explicitly that you did
  not push, and hand the push to the project lane.

## Product workflow catalog and regression history — required beyond CI

**Worker handoff is mandatory too.** Before dispatching QA or dogfood work, include the owning campaign row, `UC-...` workflow ID, spec anchor, test/manual procedure, existing `REG-...` cases, and expected observations in the one-message brief. Require the worker to return the complete `ch:trace` plus `STATUS` / `TIER` / `EVIDENCE`; preload `coding-hermes-worker,coding-hermes-traceability` where possible, but never rely on skill loading instead of putting the contract in the brief. The foreman validates and records the marker plus `STATUS` / `TIER` / `EVIDENCE` in the row's `worker_summary` before GitReins Tier 2, then reconciles its verdict and tested commit into the closeout. When the target repo's preflight binds IDs, use the owning row ID as the GitReins task ID. Keep fixed regressions in the future QA set and append each later pass/failure to the canonical run history.

CI is one evidence stream, not proof that a user journey works or that the product's components are connected.

- Derive use cases from the repository's specs, acceptance criteria, README/quickstarts, API/CLI/UI documentation, and integration contracts. Maintain one repo-local `docs/qa/use-cases.md` catalog (extend the existing canonical catalog if one already exists) with stable `UC-...` IDs, user goal/persona, preconditions and test data, exact steps, expected observable results at each boundary, spec anchor (`path#section`), automated test (`path::test`) or explicit manual procedure, connected components/state/persistence, and applicable regression IDs. Never infer intended behavior when no spec exists; mark and file that specification gap.
- Each QA tick must consult the catalog and exercise at least one applicable end-to-end user workflow through the real product surface, in addition to the CI battery. Probe the actual integration edges (for example UI→API→store or CLI→service→external dependency), read back state where relevant, and record which boundary is connected, missing, or unverified. A unit test, mocked integration, or green CI job is not a substitute for using the application.
- Keep one append-only, repo-local workflow-run history. Extend the project's existing canonical QA log if it already records per-workflow outcomes; otherwise use `docs/qa/run-history.jsonl`. Add one record for every attempted workflow, including successes and failures: run ID/time, `UC-...`, target commit/build and environment, exact actions, expected versus observed result, `PASS|FAIL|SKIPPED|UNVERIFIED`, evidence path, `REG-...` IDs, owning board row, and `ch:trace`. Preserve past failures and successful proofs; never overwrite history or treat a CI summary as app-use evidence. The host-local QA ledger and DuckBrain summary are supplementary, not replacements for repo-local evidence.
- Use the canonical marker from `coding-hermes-traceability` for each traced run: `ch:trace row=<valid QA/campaign board row> spec=<path#anchor> test=<path::test or none:manual-only> doc=<docs/qa/use-cases.md#UC-ID> evidence=<artifact path> witness=<locator or none:reason> verdict=<id> commit=<full sha> memory=<resolved key when used>`. `row=` must resolve; a verdict must bind to the tested commit; memory is only an additional citation beside repo-local evidence. Never invent IDs or links. If a required reference is absent, record the trace gap and file a coverage/campaign row before claiming traceability is complete.
- When a behavior regresses, assign a stable `REG-...` ID, preserve the original failure and reproduction in the catalog/history, and fix the code with a permanent automated regression test demonstrated failing before the fix and passing at the fix commit. Keep that case in the required future-run set, marked fixed with its test and fix commit; never delete it from coverage after the board row closes. If it cannot be automated, preserve exact manual steps and expected results. Re-run each applicable historical regression in later QA cycles and append the outcome; a recurrence links to the same `REG-...` ID and current defect row.
- A clean verdict requires evidence for both the required CI battery and the selected real-use workflow(s). Missing, blocked, or disconnected behavior is `UNVERIFIED` or a finding—not a pass.

## Records + knowledge layer

- Ledger line per project (status pass|findings|error, all 10 cells + the four
  battery stages — `lint`/`tests`/`docker-build`/`compose-config` each with
  its own status). **Verify the ledger gained YOUR row — it is a second
  self-report, and a dark ledger is itself a finding.** After every run check
  `wc -l ~/.hermes/qa/ledger.jsonl`, its newest `ts`, and `grep -c '<proj>'`:
  rows stop appearing while batteries keep finishing = dead write path, and a
  target with zero rows stays tagged `never-qa`, so `qa_discover.py` keeps
  re-batterying it instead of scoring it. Report that; never let a green node
  stand in for the ledger line. Scope: only the BUNKER path appends to
  `~/.hermes/qa/ledger.jsonl` — a `qa-scheduler-tick.sh` (dagger) run writes no
  ledger row at all, so a missing row for one is expected, never a dark-ledger
  finding. Apply the check on bunker-path runs.
- DuckBrain (coding-hermes ns, domain=event):
  - `/qa/<YYYY-MM-DD>/<proj>` — run summary
  - `/qa/observations/<YYYY-MM-DD>` — INTERESTING ISSUES + OBSERVATIONS +
    DATA SOURCES: what surprised, cross-project patterns, and which data
    source each observation came from. This record is how the QA foreman
    self-improves: repeat observations become new cells/checklist items.
- **Write the run record via the CLI `remember` verb, and verify with a
  prefix recall.** The HTTP memory routes (`POST /api/ns/<ns>/memories`) are
  not served — use `node ~/duckbrain/bin/duckbrain.js remember
  /qa/<date>/<proj> --namespace coding-hermes --domain event --content "..."`
  (key is a POSITIONAL arg; `--key` is rejected, as is `store`). The success
  line names the id but the write is batched ("will be committed in batch"),
  so it is still a SELF-REPORT: confirm with `node ~/duckbrain/bin/duckbrain.js
  recall --namespace coding-hermes --prefix /qa/<date>` (prefix mode — a
  `--key` flag is not recognized and silently queries the default namespace,
  returning 0 for a record that exists). "No memories found" is a real finding: the QA knowledge layer is dark for
  that run, so the self-improvement loop learned nothing. Fastest on-disk proof
  (no daemon round-trip): `~/duckbrain/namespaces/qa/event/<MM>/current.jsonl`
  — an mtime older than the run means nothing was written, whatever the node
  reported, and the same trap applies to the DAGGER path's `duck_record`
  (a `transform` node that completes green with an empty store). Before blaming the
  pipeline, prove the store is live by querying a DIFFERENT namespace for a
  recent write (`--namespace coding-hermes --prefix=/ --limit=1`): the store is
  shared, so a stale namespace beside a live sibling indicts the write path,
  not the daemon. Usual root cause: the key lookup reads `.apiKeys[] | .key`
  from `~/.duckbrain/auth.json`, which now stores only key hashes — the
  plaintext key lives in the `~/.duckbrain/token-*.token` sidecar
  (`dagger-role-tick.sh` already has that fallback for duckbrain-sync; qa.ts
  does not).

- **Rust targets: the JIT image has no C toolchain** → every build cell
  (`fresh-install`, `chaos-resource`, the `ci-pass` native leg) dies `rc=101`
  `error: linker `cc` not found`; act inside its own container still builds, so
  hosted CI stays green. Probe `command -v cc gcc ld make` on the agent and
  grade it as ONE harness cause. When the interpreter is degraded
  (`verdict=UNKNOWN-VALUE`, `filed=0`) the DAG exits before the detached battery
  finishes, so the tick must harvest + `collect` itself. Treat the missing
  compiler as one harness cause; product behavior remains UNVERIFIED until a
  compiler-backed run covers it.
- **0-cells pipeline → check env vs random-discovery.** When
  `targets_list` returns `[]`, read the run.log: `mode:random` =
  scheduler dispatch gap (no `CODING_HERMES_PROJECT` set for prompt-mode
  lane); `mode:targeted` = env was set and resolve_targets found zero eligible
  targets. Record the mode/source from run.log and classify the dispatch or
  selection gap instead of treating the empty pipeline as a pass.

- **Zero cells IN THE PIPELINE does not mean zero cells ran — resolve the
  agent on the server the battery actually used.** The clamp kills the local
  driver together with its `destroy` trap while the remote battery keeps
  running to completion, so `cells:[]` describes the pipe, never the run: the
  real cells exist only in the JIT agent's `~/qa-evidence.jsonl`. Read the live
  default out of `bunker-qa.sh` (`SERVER="${BUNKER_QA_SERVER:-…}"`) and list
  agents THERE (`bunker list --server <that server>`), NOT `active_server` from
  `~/.bunker/config.yaml` — they can be different hosts, and listing the config
  one is how a completed battery gets written up as "no coverage anywhere".
  Match the agent by created time + `~/qa-<proj>` — convert its printed
  timezone first (`bunker list` stamps in the SERVER's offset, the tick log in
  yours; compare in UTC or the run looks like "no agent created then") — and
  WAIT for its battery to end (`ssh … 'pgrep -f "qa-run\.sh" | wc -l'` → 0)
  before harvesting: the stranded battery outlives the pipeline by 10-20 min,
  and destroying on pipeline exit kills the trailing cells. Reserve the
  destroy-on-pipeline-exit rule for an agent with no live `qa-run.sh` of its
  own. Then `scp` its `~/qa-evidence.jsonl` and `~/qa-logs-<pid>/*.log` into a
  local dir BEFORE destroying it, `bunker destroy <id> --server <srv>`, and
  verify the id is gone. Harvest + destroy in one shot:
  `bash scripts/jit-agent-collect.sh <id> <srv> <dir>` (bash-prefixed — the
  shipped file is not guaranteed an exec bit).
  **Do not quote the pipeline's own headline**: with `cells:[]` the
  `interpret`/`report` nodes still print `verdict=UNKNOWN-VALUE`,
  `audited=1 findings=0 filed=0` and `summary "all cells OK"` — a green card
  over zero coverage, and `filed=0` means no board commit to push. Grade only
  from the agent's artifacts. If those artifacts cannot be recovered, mark the
  run UNVERIFIED; do not quote the pipeline summary as proof of coverage.
- **The lane's `workdir` is a STAND-IN PM node, not the project repo.**
  Scheduler `workdir` for `<project>-qa` (and most lanes) lives at
  `~/.hermes/stand-in/pm/<project>` — a non-git dir with a symlinked board
  to `<repo>/.coding-hermes/board`. The stand-in has no Makefile, no
  package.json, no git history — passing it to `bunker-qa.sh` makes
  fresh-install / ci-pass / upgrade all N/A. ALWAYS resolve the actual
  project repo BEFORE launching the battery. Pattern:
  - `ls ~/.hermes/stand-in/pm/<project>/.git` → absent → not a repo, follow
    the board symlink (`readlink -f ~/.hermes/stand-in/pm/<project>/.coding-hermes/board`)
    to find the real repo at `<real>/<project>`.
  - For h3 the stand-in is `~/.hermes/stand-in/pm/h3` and the real repo is
    `~/get-h3/h3`; for terminal-jail `~/.hermes/stand-in/pm/terminal-jail`
    resolves to `~/terminal-jail`. Confirm the path with
    `git -C <real-repo> rev-parse --abbrev-ref HEAD` BEFORE launching.
  - The battery MUST be invoked against the real repo, not the stand-in;
    the board writes/commits land on the real repo's branch, which is also
    where the project foreman looks for them.
  Rule of thumb: a stand-in workdir's existence is the FOREMAN's not the
  QA lane's; resolve the real repo on every tick.
- **The same target can grade OK on the bunker and FAIL on the host at the
  same HEAD** — substrate-dependent cells are not "the same cell". The
  umbrella repos (h3, and others) wire `make verify` to include a
  `check-duckbrain-tick-chain` cell that REQUIRES jq+curl+a DuckBrain
  token; on the bunker (no DuckBrain) the cell degrades to UNVERIFIED and
  the cell grades OK, while on the host (DuckBrain live) the SAME target
  surfaces tick-chain holes (a real P1 the agent missed). When a target
  ships substrate-dependent guards, grade the cell from the cell's
  substrate reachability, not the cell's headline status: cell OK + no
  substrate = the cell did not run, report as UNVERIFIED and run the host
  equivalent (`make verify` here) to grade the underlying defect. Same
  rule for any "graceful degrade on missing dep" guard — a passing
  degrade is the absence of a verdict, not a positive one.
- **`bunker-qa.sh collect --evidence` destroy can also `deadline_exceeded` on
  busy agents.** Phase B's idempotent destroy is not the only place the
  trap can fail: a 3+ GB agent with active containerd + docker layers
  returns `deadline_exceeded` to the `bunker destroy` call. Pattern is
  rare but reproducible on heavy battery outputs. Recovery: do NOT retry
  the destroy from the same call (the trap fires the same way) — record
  the leak (`agent_id`, `server`, `disk_used`, `ttl_until`) in the
  ledger's `destroy_leak` field and let TTL reap. This is the same
  destroy-unreliable class as the launch-orphan case above; the
  `deadline_exceeded` signature means the same thing either direction.
- **A `CLEAN` verdict off a single `[launch]` cell is the same lie with a
  greener card.** The battery is split into a detached phase A
  (`bunker-qa.sh launch`) and phase B (`collect`), and `parse_cells`'s own
  collect necessarily answers `RUNNING` because the battery is still in flight —
  one run structurally CANNOT collect its own battery. So a run grades
  `CLEAN: Only cell recorded is [launch] OK; no FAIL/INFO cells` while 11 real
  cells are still executing on the agent, and the DuckBrain record persists that
  wrong verdict. Treat any verdict whose cell set is only `launch`/`collect` as
  NO COVERAGE whatever the headline says: take agent id + server from the launch
  row's `detail` (or the `$EVIDENCE.meta` sidecar), wait for the battery
  (`ssh -i ~/.bunker/keys/<id> … 'pgrep -cf "qa-run\.sh"'` → 0, or
  `~/qa-run.finished` exists — the marker is written at the end), `scp`
  `~/qa-evidence.jsonl` + `~/qa-logs-*` locally as a safety net, then run phase B
  `bash ~/.hermes/scripts/bunker-qa.sh collect --evidence <path>` — prints
  `RUNNING` while alive, otherwise appends the agent's rows and destroys the
  agent (idempotent, seconds). Grade those cells; the CLEAN was not evidence.
- **A `collect` FAIL reading `no launch record at <path>.meta` means the LAUNCH
  was killed, not that the repo is un-QA-able.** Two paths can produce it:
  (1) the DAG's `run_battery` tool call is clamped at 180s, so a phase A whose
  preflights + repo sync exceed that is killed mid-transfer and never writes its
  sidecar; (2) the DAGGER wrapper `qa-scheduler-tick.sh` → `dagger-role-tick.sh
  qa` → `dagger run examples/coding-hermes/qa.ts` runs the same `run_battery`
  node, and its 180s clamp kills phase A the same way. In both cases `collect`
  is correct, and the pipeline mis-files the result as a P1 *project* row whose
  suggested cause (a "path mismatch between launch and collect") is invented,
  because it never diagnoses its own kill. Check before repeating it: a live
  `ps -o pid,etime,cmd -e | grep 'bunker-qa[.]sh'`, or an agent holding
  `~/qa-<proj>` with no `.git`, no `qa-run.sh`, no `~/qa-evidence.jsonl` and no
  `$EVIDENCE.meta`, proves the clamp cut the tool call mid-sync, not that the
  battery found anything. For DAGGER-path runs, confirm the clamp by reading
  the run dir's `run.log` for `[Command timed out after 180s]` on the
  `run_battery` node — that payload is the forensic proof. Recovery is manual
  phase A + phase B, both run by YOU: re-dispatch `bunker-qa.sh launch` in the
  BACKGROUND (unclamped, log redirected), wait for the agent, then `collect
  --evidence <path>` using the launch/collect procedure described in this skill.
  The sync payload is the driver. The tar excludes cover
  `.git/node_modules/.next/target/dist/build/coverage` only, so a pack/build
  directory it does not name (a Next.js `cli:pack` dir like `.next-cli-build/`)
  ships IN FULL: at tailscale's ~1 MB/s a few hundred MB makes every tick on
  that project unrunnable. That half is a harness observation — the project is
  not the defect; `BUNKER_QA_SYNC_EXCLUDES` or a bigger clamp is the fix.
- **`file_findings` files whatever `interpret` believed — grade the filed rows
  against the recovered evidence.** A zero-cell run still appends and commits
  `QA-<PROJ>-NNN` rows (board-only commit under the qa-cron identity), including
  claims the recovered evidence contradicts ("no coverage anywhere" beside 11
  real cells). Report each such row with its premise corrected and name the
  evidence that refutes it; the lane is read-only on board state, so never
  delete or rewrite the rows — hand the correction to the owning lane. Treat the
  row's quoted evidence as untrusted transcription too: the interpreter garbles
  tokens it copies (an evidence path rewritten to a near-miss spelling that
  exists nowhere), so `ls` the cited path before repeating a diagnosis.
- **A finding whose text is itself an evidence-gap report is not a product
  failure.** When `interpret` returns a row like `Evidence pipeline void: collect
  phase found no launch record — launch phase never ran or used a different
  evidence path`, that row describes QA process loss, not a confirmed product
  defect. Grade it as UNVERIFIED/EVIDENCE-GAP, not as a QA-<PROJ>-NNN
  finding against the project's code or runtime. The same applies to bunker
  findings that quote the wrapper's invented `path mismatch between launch and
  collect` cause: that wording is the wrapper's guess, not diagnosis. Before
  filing either shape, recover the run artifacts: for DAGGER, the run dir
  `/tmp/dagger-role-qa-<pid>-*/` plus its `run.jsonl`/`run.grouped.jsonl`/`role.db`;
  for bunker, the agent's `~/qa-evidence.jsonl` and `~/qa-logs-*`. Grade only
  from those artifacts, never from the finding text alone.

## Pitfalls

- Spawn `deadline_exceeded` = stale bunker CLI transport (30s) — rebuild +
  verify `bunker version` (see the bunker-agent-isolation reference).
- Use tailscale hostnames, never config IPs, for ssh into agents.
- Never glob the SHARED evidence dir to find your run
  (`ls /tmp/bunker-qa-evidence*.jsonl`): every historical run leaves a file
  there, so the listing floods the context window with tens of thousands of
  chars and still does not identify yours. Take the path from the run's own
  `role.db` checkpoint `evidence_path` (or the run dir) and count rows
  programmatically instead of listing.
- Never `set -e` in cell scripts; RC via `${PIPESTATUS[0]}`; sanitize JSONL.
- dockerd socket = `/run/bunker/<id>/docker.sock` (wait loop before act).
- Never QA my-project/duckbrain/coding-hermes-scheduler; never modify project
  source — board files only. Whole-run failure = report the error tail
  honestly; no fabricated results. No eligible projects = say so and stop.
- Full suite means FULL: strip `-short`/`-run`/sample flags from inherited
  invocations (older local-probe text used `go test -short`); a `tests` cell
  produced by a `-short` run is UNVERIFIED, not OK.
- Never read a stage rc through a pipe (`cmd | grep | head` returns the last
  pipe stage's 0) — capture rc via `( cmd ) >log 2>&1; rc=$?` and read the log
  tail before trusting a cell status (QA-BUNKER-1 lying-gate class).
- **Never run the battery through a bare pager pipe, and never in the
  foreground.** When you control the invocation, insert a tee before the pager:
  `... 2>&1 | tee /tmp/qa-<proj>-<ts>.log | tail -15` — the tee keeps a live
  `read_file`-able log that outlives a killed run, while a bare pipe gives the
  caller their 15 lines and gives you no progress channel and no file. When the
  invocation instead arrives as a FIXED dispatched string (tool-executor brief,
  foreman tool node) you cannot add the tee — so do not dispatch it in the
  foreground at all: the foreground timeout is CLAMPED (a requested `600`
  returns `Error executing tool 'terminal': timed out after 420.0s`), and a
  bare-pipe run that hits the clamp returns NO output and leaves NO log.
  Re-dispatch the same command in the background with
  `> /tmp/qa-<proj>-<ts>.log 2>&1; echo "EXIT=$?"`, wait it out, then read the
  log tail plus the evidence JSONL — that reproduces the requested `tail -15` +
  evidence shape from a file that survived. Never re-run foreground "with a
  bigger timeout"; the clamp wins. **Never trust the pid a detached launch reports.** The pid that comes back (`setsid ... & echo $!`, the background tool's pid) can be a wrapper that exits within seconds while the real chain runs on under a DIFFERENT pid re-parented to `systemd --user`: a `kill -0 <pid>` poll then reads "exited after 10s" minutes into a healthy battery whose 0-byte evidence file is legitimate. Confirm liveness by command pattern (`pgrep -f 'bunker-qa[.]sh run'`) plus a growing redirect log — bracket one pattern character, because the poll's own `bash -c` wrapper carries your poll text on its command line and matches the pattern too (a phantom "alive" that can outlive the run), never by the pid alone, and keep each poll call itself under the clamp — pass `timeout=<sec>` explicitly on every poll call — the terminal tool's own default is 180s and silently truncates a 300s sleep into nothing but a timeout error, while the hard ceiling is the 420s clamp. Before dispatching, `pgrep -f 'bunker-qa.sh'`: an enabled `<project>-qa` scheduler lane drives the same script, so two live TOP-LEVEL drivers mean two JIT agents on one project — a SINGLE run reports two matches of its own pattern (the driver plus a `bunker-qa.sh run` child nested under it), so walk the ppid chain (`ps -o pid,ppid,etime,cmd | grep 'bunker-qa[.]sh'`) instead of reading the raw `pgrep` count as a pass count.
  Use the background-launch, process-pattern liveness, evidence-harvest, and
  collect steps in this skill. Never infer completion from a detached pid.
- **A background run's captured output is a BOUNDED trailing window.**
  `process_manage` (`poll`/`wait`) returns only the last chunk printed; once the
  process exits the earlier lines are unrecoverable, so after an unredirected run
  the head of a `tail -N` is gone for good. Do NOT re-run a 10-minute battery to
  recover cosmetic console lines — read the `BUNKER_QA_EVIDENCE` JSONL as the
  payload, report the console section as partial and name what was lost.
  Clean-exit signature in the tail: `→ destroying temp agent <id>` (trap fired,
  nothing leaked).
- **A 0-byte local evidence file is NOT a dead run — a redirected log file, by
  contrast, IS live.** The local `BUNKER_QA_EVIDENCE` JSONL is written at
  COMPLETION (a separate pull step after the run SSH finishes), so during the
  run it sits at 0 bytes; never read that as "cells did not run". The pull is a
  SNAPSHOT of the agent's `~/qa-evidence.jsonl`, so it can also land SHORT by the
  trailing cells (`chaos-resource`, `chaos-errorpath`) while the driver still
  printed `→ QA pass complete` and destroyed the agent — count the rows against
  the script's cell list and report any missing cell as UNVERIFIED (re-read the
  agent's own file if it still lives), never as a pass. The out-log
  you redirect to with `> /tmp/qa-<proj>.log 2>&1` flushes as the run proceeds —
  per-cell lines, then `CELLS-DONE`, then the destroy line, all while the
  process is still alive — so `tail`/`read_file` on it is the live progress
  channel. Only a PIPE (`| tail -15`) buffers and hides both, which is why
  dispatch always redirects to a file. Watch progress on the JIT agent instead —
  `ssh -i ~/.bunker/keys/<agent-id> -o IdentitiesOnly=yes bunker-<agent-id>@<tailscale-server> 'wc -l ~/qa-evidence.jsonl; tail -3 ~/qa-evidence.jsonl'` —
  taking BOTH the id and the server from the out-log's first two lines
  (`→ agent=<id> @ <server> (tailscale)`), the driver's only print of them;
  fall back to matching the agent by its created time and its `~/qa-<proj>`
  directory only when that log is gone. When
  the run ends, the trap destroys the agent and that same ssh answers
  `Permission denied (publickey)` — that is normal teardown, not a failure;
  switch to the pulled local evidence file and judge from it.
- **The battery ships the LIVE WORKTREE, not HEAD — freeze the tree before
  attributing any FAIL.** The sync is `tar --exclude='.git' --exclude=node_modules …`
  over the workdir, so a sibling worker's uncommitted diff is exactly what the
  JIT agent tests. Record `git rev-parse --short HEAD`, `git diff --stat` and
  `git diff --name-only | xargs -r md5sum` at tick start; a FAIL whose failing
  file/package sits inside that diff is an artifact of in-flight work — report
  it as untested-in-flight, never as a repo finding, and never "fix" the
  worker's half-landed diff from a QA lane.
- **A timed-out tool call does NOT mean the work stopped.**
  `{"status":"timeout","process_running":true,"timeout_note":"Requested wait of
  900s was clamped to configured limit of 180s"}` means the caller gave up while
  the remote battery kept running uncancelled — and a second invocation can be
  dispatched for the same evidence path, so count EVIDENCE FILES and AGENTS, not
  calls (`bunker list --server <srv>`, match created time + `~/qa-<proj>` dir).
  **Attribute processes per AGENT USER, not per host:** bunker agents are
  separate users on ONE host, so a `pgrep` run inside one agent's ssh lists
  every agent's processes — match the `/home/bunker-<id>/` prefix in the
  cmdline (or the `~/qa-<proj>` dir owner), never "a qa process is visible".
  An agent with no `qa-run.sh` of its own is an idle leak (destroy it); one
  with a live `qa-run.sh` is still working (leave it unless the battery is
  yours). The server likewise comes from the ENV, never the CLI:
  `SERVER="${BUNKER_QA_SERVER:-…}"` is the only place `bunker-qa.sh` reads it,
  so a driver launched with a positional `--server <srv>` still runs on the
  env/default host — export the env var and confirm the spawn line names the
  host you meant before reporting which server was tested.
  After the pipeline exits, `bunker destroy <agent-id> --server <srv>` your
  tick's orphan: a leaked agent holds GB of disk and eats the spawn capacity
  whose exhaustion is itself a recurring P1. A lane under a read-only covenant
  reports the orphan instead (agent id + disk + TTL) and leaves the destroy to
  a lane that owns cleanup — the leak is TTL-bounded, and no QA lane should
  mutate infra mid-run.
- Attribution checklist (per-cell log pull, the shared-`/tmp` test-hermeticity
  repro, guard-override noise): apply the raw-log and cell-attribution rules
  above; missing evidence remains UNVERIFIED.
- **Python repos: the auto-detected install can silently skip the test runner.**
  `install_cmd` for pyproject repos is `pip install -e .[dev] 2>/dev/null ||
  pip install -e .`, and a PEP 735 `[dependency-groups] dev = [...]` is not a
  pip extra — pip installs runtime deps only and exits 0 (the unknown-extra
  warning goes to the discarded stderr), so the fresh-install cell reports OK
  with a plausible `Successfully installed <runtime deps>` tail while every
  suite-driving cell downstream returns rc=127 `pytest: command not found`
  (ci-pass's native leg, chaos-disconnect, chaos-resource). Check the
  declaration (`grep -n '^\[dependency-groups\]\|^\[project.optional-dependencies\]'
  pyproject.toml`) and the repo's own documented dev flow (`grep -n 'uv sync'
  README.md`) before filing anything against the project: when `uv.lock` exists,
  install via the lockfile path (`uv sync --dev`, run as `uv run pytest`); a
  repo-side workaround is duplicating the group into
  `[project.optional-dependencies]`. With `uv.lock`, use `uv sync --dev` and
  run via `uv run pytest`; verify the runner exists before grading install OK.
- **Reproduce a clean-machine FAIL locally before filing it.** For an
  assertion of the form `assert "<binary>" in tools`, re-run just that test
  with the binary's directory stripped from PATH
  (`PATH="$PWD/.venv/bin:/usr/local/bin" <venv>/bin/python -m pytest <test> -x -q`).
  Passing with the binary and failing without proves the test has no
  skip-guard and depends on an ambient tool — file it as that brittleness
  (test red on any clean machine, e.g. when the CI apt-install step fails),
  NOT as a hosted-CI break. Check the repo's own CI workflow first: if it
  installs the binary, hosted CI can be green while the clean-machine cell
  goes red, and the finding must say so. When the repo resolves the tool
  through its own knob (`*_BIN`, config env), repoint that knob at a
  nonexistent path as well as stripping PATH — one command then reproduces the
  clean-box failure byte-for-byte. **When the cascade shows dozens of DIFFERENT
  asserts and none of them names the tool, grep the whole suite log for the
  infrastructure line** (the missing tool + `not found`): one cause line
  explains every assert, while the per-test messages ("expected non-empty JS")
  name nothing and misfile as a dozen unrelated defects. Cite a sibling test in
  the same repo that DOES skip-guard the tool as the fix shape — the finding is
  the missing guard, not the missing tool.
- **Repo-local-venv variant of the same repro.** When the FAIL is a test that
  spawns a binary out of the repo's own `.venv` (console-script wrapper, `-m`
  entry point), remember the sync ships that `.venv` — the excludes cover
  `.git/node_modules/target/dist/…` but NOT `.venv` — and its console scripts
  carry the DEV machine's absolute shebang, so on the agent the exec dies
  `bad interpreter: Permission denied` (rc 126) with zero stdout and the test
  asserts on missing responses. Two checks before filing: (a) run the same test
  locally (it passes — the dev venv exists there); (b) emulate a genuinely
  fresh checkout by copying the wrapper into `/tmp/<dir>/bin/` with no `.venv`
  and running it — if it prints its own install hint and exits 1 with no
  stdout, the test has no precondition guard and is red on ANY clean machine.
  File THAT (missing skip guard + accidental dev-venv dependency) rather than
  "the deployed wrapper is broken", and report the shipped-venv transfer cost
  (hundreds of MB of the sync) as a separate harness observation.
  Check the chain ONE LEVEL DEEPER than the wrapper you were pointed at: the
  repo-relative wrapper is usually correct (it resolves its root from its own
  path) while the `.venv/bin/<script>` it execs is the dead one — `head -1`
  the console script, not just `bin/<wrapper>`, and cite the full nested error
  (`<wrapper>: <repo>/.venv/bin/<script>: /home/<dev>/<repo>/.venv/bin/python3:
  bad interpreter: Permission denied`). Never exec an MCP/stdio wrapper bare to
  probe it — it blocks on stdin until the tool call is killed (an `execute_code`
  cell that hangs is killed and its kernel state is lost, so the whole probe
  round has to be redone): run `timeout 5 <wrapper> < /dev/null; echo rc=$?`,
  which is also the form that shows `rc=126` beside 0 bytes of stdout.
  Discriminator in one shot: `bash scripts/venv-transfer-probe.sh <repo> bin/<wrapper>
  …` (HEAD + dirty state, every `.venv` console-script shebang with a dead-or-alive
  verdict, then a bounded stdin-closed exec of each wrapper).
- **Collection-time skipif guards are the compiled-twin of the same trap, and they
  kill the WHOLE suite.** A guard like
  `pytest.mark.skipif(not (REPO/'.venv'/'bin'/'python').exists(), reason=...)` is
  evaluated at COLLECTION (module import), and `Path.exists()` RAISES
  `PermissionError (EACCES)` instead of returning False when any path component
  is untraversable — a shipped venv whose `bin/python3.11` is an ABSOLUTE symlink
  into the dev home (`/home/kara`, mode 700 on the JIT host) hits exactly that.
  The result is `Interrupted: 1 error during collection` and ZERO tests from ANY
  module, so the "missing venv, skip this module" intent hard-fails the run.
  Reproduce without touching the repo: `mkdir -p /tmp/x/.venv/bin; chmod 000
  /tmp/x/.venv/bin`, then one module with the guard plus one trivially-passing
  sibling → the sibling never runs. File it as the missing exception-safe guard
  (try/except OSError around `.exists()`), with the sync shipping `.venv`
  (it is NOT in the exclude list) as a separate harness observation.
- **One collection error, several cells, and a possible FALSE-PASS OK.** Cells
  that re-run the native suite (`ci-pass` native leg, `chaos-resource`,
  `chaos-disconnect`) all die on the same rc, but their verdict logic maps that
  rc differently: `chaos-resource` FAIL, `chaos-disconnect` **OK** ("fails fast
  on disconnect") — the rc came from the collection error before any disconnect
  handling was exercised. When two or more cells carry the SAME log text, check
  the OK ones too and file ONE row naming every cell it covers; never report the
  false PASS as a passing stage. Likewise `chaos-corruption`/`chaos-errorpath`
  run a BARE entrypoint (`timeout 20 $BIN` with no args/command), so their OK/
  INFO reflects Click printing usage text — the truncated DB was never read and
  the "missing config" premise was never exercised: report both as harness
  premise gaps, not as product behavior.
- **An act failure reading `stat <workdir>/.github/workflows/<file>: permission
  denied` is a baked-in DEV-BOX path, not a red workflow.** The qa-run.sh
  generated for the agent can point `act -W` at the ORIGINAL workdir path
  (unreadable to the agent user) instead of the agent-local synced copy, so
  act dies before running any job. Grade ci-pass as a harness artifact
  (UNVERIFIED), never as a workflow failure; if the native leg also could not
  run (e.g. missing suite runner), name both gaps in the UNVERIFIED report.
- **act CI red vs action-download stalled are different verdicts.** When every
  job hangs at `☁ git clone 'https://github.com/actions/...'` until act's own
  timeout returns `rc=124`, with job containers up but holding only
  `tail -f /dev/null` (≈0% CPU, ≈400KiB), the workflow never executed a step —
  that is the AGENT's egress to github.com (curl to github.com answers 200 but
  eats the whole `-m 15` window while codeload answers in <1s), not a red
  workflow. Report CI as UNVERIFIED for the cycle; never grade it from the rc.
- **Go/CGO variant of the same repro (compiled-language twin).** When the
  fresh-install/build cell dies INSIDE a dependency — the classic shape is
  `undefined: Conn` out of a CGO package the repo merely depends on — reproduce
  it in one command by toggling the ambient feature OFF:
  `CGO_ENABLED=0 go build ./...` fails in ~1s with byte-identical error text,
  while `CGO_ENABLED=1 go build ./...` passes in seconds on a box with a
  compiler. Confirm on the agent with `command -v gcc cc` (both MISSING) +
  `go env CGO_ENABLED` → `0`: Go silently flips it to 0 when no C compiler is
  present, so the error names the dependency and never the missing compiler —
  that is why the finding needs the discriminator spelled out. Corollary for
  hang cells: cgo/build failures are FAIL-FAST, so a cell that burned its whole
  120s budget and shows a build error in its tail was NOT blocked by that build —
  mark any "blocks on the module proxy" / "hangs offline" attribution UNVERIFIED
  until a mechanism is shown, and never re-file that guess as a P1 chaos hang.
- **Identity-hardcoded fixtures are the same clean-machine trap as ambient tools
  (uid/user/hostname).** A test whose fixture names a literal uid (`user:1000`)
  and then asserts the dedup/resolution count passes only on a box whose
  process uid IS that literal — so it is red on every JIT agent (service uid),
  every container (root = 0) and any CI runner with a different uid, with the
  identical assertion in every leg. Read the resolver before filing: when the
  product code dedupes correctly and only the EXPECTED count is wrong, the
  defect is the fixture (derive it from `os.Getuid()`/`$(id -u)`), not the
  product. Cross-check legs to classify: same failure in act + native + the
  chaos-resource leg = deterministic fixture bug, not load noise.
- **Two launches in one tick collide on the DEFAULT evidence path.**
  `bunker-qa.sh` writes `/tmp/bunker-qa-evidence.jsonl` when
  `BUNKER_QA_EVIDENCE` is unset, so parallel targets share one host file and
  the later collect can snapshot the other run's rows. Harvest per AGENT
  (`scp` `~/qa-evidence.jsonl` + `~/qa-logs-*` off `<id>@<server>`) and grade
  from those, never from the shared path; the per-cell logs also hold the
  failing package/step lines the evidence `tail -3` window cuts.
- **Parse evidence with a /tmp script run via `terminal`, not `execute_code`,
  on unattended surfaces.** `execute_code` requires interactive approval and is
  refused on the unattended api_server surface, so it cannot be relied on for
  the per-cycle evidence/board parsing. Write the parse script to
  `/tmp/qa_parse.py` and run it via `terminal` instead — the file survives the
  call, is reusable across poll rounds, and avoids the approval round-trip.
  Applies to any multi-step JSONL/board parsing you'd otherwise hand to
  `execute_code`.

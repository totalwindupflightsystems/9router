---
name: qa-audit-usage
description: Use when running or driving the qa-audit QA pipeline (bunker-qa.sh) against a fleet repo — launch/collect protocol, evidence reading, known pitfalls.
---

# qa-audit QA pipeline — usage skill

Fresh-system QA batteries on JIT bunker agents. Entry point:
`~/.hermes/scripts/bunker-qa.sh` (~3000 lines, hardened bash). The scheduler
normally drives it via `~/.hermes/scripts/qa-scheduler-tick.sh` (random
discovery, 2 projects/tick, or targeted via `*-qa` row names); the manual form
is below.

## The protocol (three steps, in this order)

```bash
bash ~/.hermes/scripts/bunker-qa.sh status          # ~0.47s health probe (measured 465ms ±35ms, 5 runs) — do this FIRST, but read what it covers below
bash ~/.hermes/scripts/bunker-qa.sh launch <repo>   # payload-bound: 126s for crier (55MB tracked / 1140 files) — the script header's own estimate is 60-120s
bash ~/.hermes/scripts/bunker-qa.sh collect --evidence <path>   # poll every 3-5 min
```

- NEVER wait inside launch; the battery runs detached on the agent
  (`~/qa-run.sh`). collect prints RUNNING (rc=0) while alive, then
  `COLLECTED rows=N` after merge-dedupe + destroy. Re-running collect after
  success prints `already-collected` in 0.01s — safe to re-poll. A collect over a
  battery that ALREADY finished (`~/qa-run.finished` present) still costs ~90s
  (pull + teardown-verify ladder + destroy) — that is normal, not a hang.
- Cells: fresh-install, ci-pass, upgrade (previous tag), docker-deploy, ui-probe,
  chaos-disconnect/shutdown/corruption/resource/errorpath. **ci-pass grading is
  two-shaped:** when the repo has a triggerable workflow and the act leg exits 0 the
  cell is graded from ACT ALONE (`bunker-qa.sh:2040-2041`) and the native suite —
  which lives in the act-RED branch at `:2053` — never runs, so an act-green battery
  ships NO `native.log`; read the act log itself for test evidence. When the act leg
  goes red, the native suite runs and becomes the authoritative leg (separate `ci-act`
  row).
- Default server: bunker-mvp (override `BUNKER_QA_SERVER`). Capacity is per-host
  and must be read, not assumed: `bunker status --server <srv>` reported
  `Agents: 6/50` for bunker-mvp and `1/8` for bunker-las-02 on 2026-10-23 (an
  older revision of this skill claimed "8 slots" for the default).
- **Non-mvp servers need the port override too.** `server_ssh_port()` hardcodes
  `2223` for every server except bunker-mvp, but bunker-las-02's agents answer on
  **22**. Without the override a las-02 launch spawns the agent, then dies at
  `repo sync` (`ssh: connect to host … port 2223: Connection refused`) and
  `collect` answers `COLLECT-FAIL unreachable-agent` on a battery that is alive.
  Measured 2026-10-23 (crier): no override → launch rc=1 in 73.08s, collect fails
  in 90.69s; with `BUNKER_QA_SSH_PORT=22` → launch rc=0 in 125.98s, collect
  `RUNNING` in 2.32s. So the working fallback command is
  `BUNKER_QA_SERVER=bunker-las-02 BUNKER_QA_SSH_PORT=22 bash bunker-qa.sh launch <repo>`
  (QA-HARNESS-PORT-1).

## Reading the verdict (the part that bites)

Read EVERY cell, never the summary line:

```bash
jq -r '[.cell,.status,(.detail|.[0:150])] | @tsv' /tmp/bunker-qa-evidence-*.jsonl
```

- UNVERIFIED / N/A are honest skips (vacuous suite, no compose file, no web
  UI) — do not fold them into PASS in any aggregate you build (DG-001: an
  aggregate ci-pass OK rode over a fresh-install FAIL on the same commit).
- `repo-head` names the exact commit tested; `clone dirty — pull skipped` is
  honest pinning, not a failure.
- `destroy reported failure but agent is GONE — teardown recovered` = benign
  (QA-BUNKER-39); `TEARDOWN-LEAK` = a real leaked slot, destroy manually:
  `bunker destroy <id> --server <server>`.
- Evidence lives in /tmp — copy the jsonl into the repo/board if the finding
  must outlive the day.

## Pitfalls learned the hard way (2026-10-09 run)

- Go repos pinning `go` >= the agent toolchain fail fresh-install/upgrade/
  chaos-resource with `go: download go<ver> for linux/amd64: toolchain not
  available` — four cells, one root cause, truncated in the detail string.
  Check the repo's go directive before interpreting a FAIL wall (DG-003).
- **2026-10-20: harvest the agent's per-cell logs BEFORE collect.** collect destroys
  the box, so `tar -C $HOME -czf - qa-logs-*` over ssh first; the per-cell logs are
  where the real verdicts live (`ci.log` names every act step, `res.log` carries the
  native suite's package lines).
- **2026-10-20: there is no `--help`.** `launch --help` (or any flag-shaped target)
  is graded as a repo path — refused pre-spawn, and the refusal's `.meta` records
  `project=` as basename(1)'s multi-line help text (DG-016). Read the Usage block in
  the script itself; never probe the CLI with a flag.
- **2026-10-20: the ci-pass job count is computed with a dead pattern.**
  `grep -cE 'Job succeeded|✅ Success'` undercounts because act prints "✅  Success"
  with TWO spaces — today's run reported "1 jobs green" over a log with 15 step
  successes and 1 "Job succeeded" (DG-015). Count the act log yourself if the number
  matters, and never read `ci-pass OK` as "the suite ran".
- **2026-10-20: launch is payload-bound, not fixed-cost.** Measured 41.54s for a 34MB
  repo (controller stages: render 0.03s, git probes <0.02s, prev-release archive
  0.04s) — the wait is the ship to the JIT box plus its boot. Budget ~1 min/repo and
  do not attribute a slow launch to the harness without the payload size.
- Script render (`__gen-remote*`, and real launches) can emit stray stderr
  (docker/go probes on the control host) and a `line 949: disc_window:
  unbound variable` abort while still exiting 0 — never trust render rc
  alone; launch's SCRIPT_BYTES=0 guard is the backstop (DG-002).
- las-bunker-03 (the dogfood-skill's standard ephemeral host) has been
  tailnet-absent since 2026-10-04; bunker-mvp is the working default.
  **Leaked agents are a moving target — census, never trust a count.**
  `bunker list --server bunker-mvp` before every wave: on 2026-10-23T13:50Z it
  showed 6 agents, FOUR of them `destroy-refused:live_processes` (7.0 + 14.9 +
  13.5 + 4.7 = 40.1GB, all created that same day, three provably this harness's
  own launches), and one of them (`0e8aec07`) was still alive six hours past its
  Expires At — TTL does not reap them (QA-HARNESS-LEAK-001 event 47).
- **2026-10-23: `status` green does not mean you can spawn.** `status()` ssh's
  the SERVER HOST and prints the HOST's `bunkerd`/`docker`/`act`/`uidmap`; it
  never probes agent provisioning or the AGENT's docker socket. Measured: green
  in 465ms, then two launches on the same server failed after 211.49s / 211.18s
  at `stage rootless-install … Could not enable linger: Connection timed out`.
  Read the green as "the control host can reach the daemon", nothing more
  (QA-HARNESS-STATUS-1). The same run prints `[root cause: agent ssh port 22
  AND port 22 unreachable … server/network down]` — both arms are the same port
  on bunker-mvp, so do not follow that line.
- **2026-10-23: a launch that fails at `repo sync` leaves its agent RUNNING.**
  The sync-failure branch exits 1 without calling `qa_destroy_agent()`
  (QA-HARNESS-LEAK-003). After any failed launch, `bunker list --server <srv>`
  and destroy the id the launch printed before it died.
- **2026-10-23: `res.log` is the CAPPED run — never grade the product from it.** `chaos-resource`
  wraps the suite in `( ulimit -v 3145728; … )` (`bunker-qa.sh:2913/2927`, virtual memory, not
  RSS). A Node/Wasm test harness dies inside it with `RangeError: WebAssembly.instantiate(): Out
  of memory: Cannot allocate Wasm memory for new instance` even with 15 GB of RAM free, so
  `res.log` shows failures `native.log` (uncapped) does not: measured today 5 vs 2, the three
  extras all carrying that Wasm error after their assertions had printed `16/16 passed`
  (QA-HARNESS-CAP-1). Compare the two logs before calling anything a product failure.
- **2026-10-23: two concurrent `collect`s of ONE evidence file both succeed** (observed when two
  deliveries of the same tick ran): each pulls 19 rows, the merge dedupes (`0` duplicate
  `(cell,status,detail)` groups), the second prints `destroy reported failure but the agent is
  GONE — teardown recovered`, and the wall roughly doubles (243.79 s vs the ~90 s of a lone
  collect). Re-running collect after success is still `already-collected` in ~0.01 s.
- Board rows this pipeline files: QA-<PROJ>-NNN in the TARGET project's
  board; findings about the pipeline itself go on the qa-audit board
  (`.coding-hermes/board/tasks.jsonl` in this workdir).

## Target resolution — 2026-10-26

Resolve the scheduler's canonical product root before using these commands. A scheduler lane workdir may be a stand-in or a tracked subdirectory of a larger git repository. Run the literal target path first; if the runner refuses because the path is a subdirectory, do not silently substitute the parent repository or call the result a product verdict. A scope override must preserve the requested project identity in evidence. The 2026-10-26 run showed that `BUNKER_QA_SUBDIR=.hermes/stand-in/pm/qa` launched a battery as `project=kara`, so that workaround is diagnostic only for qa-audit until the scheduler/runner contract is fixed (QA-AUDIT-HARNESS-002).

Use one explicit evidence path rather than an unscoped glob when several runs exist. On 2026-10-26, `status` measured 427.9ms ± 1.6ms warm and 0.42s cold; scoped launch took 29.76s and collection 54.51s, dominated by remote transfer/provisioning and teardown.

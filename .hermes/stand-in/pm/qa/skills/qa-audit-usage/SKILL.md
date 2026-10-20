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
bash ~/.hermes/scripts/bunker-qa.sh status          # ~0.5s health probe (0.53 cold/0.52 warm) — do this FIRST
bash ~/.hermes/scripts/bunker-qa.sh launch <repo>   # ~5-45s; prints LAUNCHED agent=<id> evidence=<path>
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
- Default server: bunker-mvp (override `BUNKER_QA_SERVER`). Capacity 8 slots.

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
  tailnet-absent since 2026-10-04; bunker-mvp is the working default. Two
  stale `destroy-refused:live_processes` agents (~20G each) sit on
  bunker-mvp — check `bunker list --server bunker-mvp` before waves.
- Board rows this pipeline files: QA-<PROJ>-NNN in the TARGET project's
  board; findings about the pipeline itself go on the qa-audit board
  (`.coding-hermes/board/tasks.jsonl` in this workdir).

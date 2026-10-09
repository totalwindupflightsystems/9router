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
bash ~/.hermes/scripts/bunker-qa.sh status          # 0.4s health probe — do this FIRST
bash ~/.hermes/scripts/bunker-qa.sh launch <repo>   # ≤30s; prints LAUNCHED agent=<id> evidence=<path>
bash ~/.hermes/scripts/bunker-qa.sh collect --evidence <path>   # poll every 3-5 min
```

- NEVER wait inside launch; the battery runs detached on the agent
  (`~/qa-run.sh`). collect prints RUNNING (rc=0) while alive, then
  `COLLECTED rows=N` after merge-dedupe + destroy. Re-running collect after
  success prints `already-collected` in 0.01s — safe to re-poll.
- Cells: fresh-install, ci-pass (act + native), upgrade (previous tag),
  docker-deploy, ui-probe, chaos-disconnect/shutdown/corruption/resource/errorpath.
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

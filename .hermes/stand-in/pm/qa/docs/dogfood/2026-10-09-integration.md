# Dogfood Integration Report — qa-audit QA pipeline (2026-10-09)

What a real user does with this project: run a fresh-system QA battery against a
fleet repo from a clean JIT bunker agent, twice (launch / collect), and read the
evidence. This report is the worked example, with the numbers and the errors hit.

## The working flow (verbatim, proven 2026-10-09)

```bash
# 0. health (5s budget): server must be alive before you commit to a battery
bash ~/.hermes/scripts/bunker-qa.sh status
#   → "BUNKER QA — ... — server bunker-mvp / bunkerd=active docker=yes act=no uidmap=yes"

# 1. launch — preflights, JIT-spawns an agent, syncs the repo, starts the battery
#    detached. Returns in ~20-30s. Capture the LAUNCHED line; it names the evidence path.
bash ~/.hermes/scripts/bunker-qa.sh launch /home/kara/get-h3/logsey
#   → LAUNCHED agent=52cabdde evidence=/tmp/bunker-qa-evidence-<ts>-<pid>.jsonl

# 2. collect — poll every 3-5 min. While running it prints RUNNING (rc=0, destroys
#    nothing). When done it merge-dedupes the agent's rows, appends a collect cell,
#    destroys the agent, prints COLLECTED. Idempotent: re-runs print already-collected.
bash ~/.hermes/scripts/bunker-qa.sh collect --evidence /tmp/bunker-qa-evidence-...jsonl

# 3. read the verdicts
jq -r '[.cell,.status,(.detail|.[0:110])] | @tsv' /tmp/bunker-qa-evidence-...jsonl
```

The scheduler drives this automatically via
`~/.hermes/scripts/qa-scheduler-tick.sh` (random discovery of 2 projects per
tick, or targeted via a `*-qa` row name); the manual form above is the same
path a human debugging one repo needs.

## What the batteries found (real runs, 2026-10-09)

| run | repo @HEAD | agent | wall | notable cells |
|---|---|---|---|---|
| 1 | logsey @1e07580 | 52cabdde (bunker-mvp) | 7m40s spawn→collect | fresh-install FAIL, ci-pass OK, upgrade FAIL, chaos-resource FAIL, chaos-errorpath UNVERIFIED |
| 2 | pulse @711c2f2 | 0408b09d (bunker-mvp) | 3m30s | all OK/PASS/INFO/N/A, chaos-errorpath OK (clean rc=2 on missing config) |

Run 1 is the instructive one: act CI is green on the SAME commit whose native
fresh-install cannot even provision a Go toolchain. Reading only the ci-pass
cell — or any aggregate that folds it — would call logsey healthy. File
DG-001 on the qa-audit board covers the composition contract; DG-003 covers the
underlying toolchain gap (go.mod `go 1.26` vs an agent toolchain that cannot
auto-download).

## Errors hit, and what they mean

1. `go: download go1.26 for linux/amd64: toolchain not available` — every
   native-Go cell on logsey. Not a repo bug per se: the battery has no
   directive check before shipping `go build ./...`. See DG-003.
2. `bunker-qa.sh: line 949: disc_window: unbound variable` + `no configuration
   file provided: not found` + `go: cannot find main module` — emitted by the
   CONTROL HOST during script rendering (`__gen-remote*`, and visible during
   real launches). rc stays 0 even though the render aborted mid-heredoc; a
   later launch would then hit the QA-DF-CHIMERA-V2-51 empty-payload guard.
   See DG-002. Repro: `bash ~/.hermes/scripts/bunker-qa.sh __gen-remote /tmp`
   (stderr, 391 bytes, rc=0).
3. `destroy FAILED: agent <id> rc=1 ... destroy reported failure but the agent
   is GONE — teardown recovered` — benign per the QA-BUNKER-39 contract (the
   CLI's deadline expired; the destroy landed late). Correctly logged, never
   swallowed.
4. `clone dirty — pull skipped, testing recorded sha` (run 2 repo-head) — the
   pulse workdir had uncommitted changes; the battery pinned and recorded the
   exact SHA instead. Honest behavior; noted so a reader doesn't mistake it
   for a clone failure.

## Environment facts a new operator needs (not in the usage line)

- Default server is bunker-mvp (`BUNKER_QA_SERVER` to override); the README of
  the tool and its header comment still disagree with the code here (already
  filed as DOC-002/DOC-006 on this board).
- The battery is a phase-split protocol on purpose: launch ≤ ~30s so one tool
  call can never straddle the 7-15 min battery. Never "wait" inside launch;
  poll collect.
- Evidence files live in /tmp and die with the machine; copy the jsonl into the
  repo or a board row if the finding must outlive the day.
- Two stale agents (37a5c1c1, 9fd23f7a) sit on bunker-mvp in
  `destroy-refused:live_processes` (~20G each); capacity is 8 slots — check
  `bunker list --server bunker-mvp` before a wave.

## Numbers

- launch wall: 27s cold (incl. JIT spawn + 106KB script sync), ~20s warm.
- battery wall: 3m30s (Go repo, no compose/UI) to 7m40s (with failed native
  retries + toolchain bootstrap installs).
- `status` 0.4s; idempotent collect 0.011s; collect-at-completion ~4m15s after
  launch (includes the post-completion pull + destroy verify).
- Nothing here is slow enough that a user would notice beyond the battery's
  inherent fresh-system work — no PERF rows filed.

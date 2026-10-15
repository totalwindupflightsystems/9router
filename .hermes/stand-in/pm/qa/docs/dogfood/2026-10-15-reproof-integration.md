# Dogfood re-proof run — 2026-10-15 (qa-audit-dogfood-2026-10-15-21-47-59)

## What was tested

The QA pipeline itself (`~/.hermes/scripts/bunker-qa.sh`), driven as a real user:
launch a fresh-system battery for **crier @839b4f2cf641** (a Go repo pinning
`go 1.26.9` — exactly the repo class DG-003 broke), poll, collect, judge.

This is a re-proof run: two fixes had just landed at HEAD and had never been
driven through real use.

1. **DG-005/DG-009 collect truncation detector** (fixed 2026-10-14, commit
   referenced in bunker-qa.sh:3266): the old check grepped the temp file's PATH
   STRING and the compact JSON dialect; every COMPLETED battery false-FAILed as
   `COLLECT-FAIL battery-truncated`.
2. **QA-MISCHIEF-003 floor-aware toolchain bootstrap** (6eb611c1b, 2026-10-15):
   the old gate installed `~/tools/go` only when the agent had NO go; a distro
   go below the go.mod floor shadowed the user-space toolchain and every
   go>=1.26 repo failed fresh-install/upgrade.

## The run, as the user experienced it

| step | command | result | time |
|---|---|---|---|
| preflight | `bunker-qa.sh status` | bunkerd=active, docker=yes | 0.42s ×3 (stable) |
| launch | `bunker-qa.sh launch /home/kara/crier` | agent=d908faeb @ bunker-mvp, LAUNCHED rc=0 | ~5s wall |
| battery | (on-agent, detached) | 20 evidence rows | ~10m |
| collect | `bunker-qa.sh collect --evidence /tmp/bunker-qa-evidence-20261015T215158Z-1655935.jsonl` | **COLLECTED rc=0**, merge-deduped, agent destroyed | 2m39s |

## Re-proof verdicts

- **DG-005 collect fix: HOLDS.** Battery completed (final cell
  `chaos-errorpath OK`, `qa-run.finished` present); collect graded COLLECTED,
  rc=0, no false truncation. The detector now greps the pulled FILE with a
  spacing-tolerant pattern (`"cell": ?"chaos-errorpath"`), matching the agent
  writer's spaced `json.dumps` dialect. Evidence:
  `/tmp/bunker-qa-evidence-20261015T215158Z-1655935.jsonl` (23 rows incl. the
  collect row). DG-005's premise is FALSE at HEAD — ready to close on this
  evidence (event `ev-dg005-reproof-20261015T2212Z`).
- **DG-003 go-floor fix: HOLDS, with a named edge.** `toolchain-bootstrap OK
  "go 1.26.5 installed (~/tools/go; floor=1.26.9 distro=absent)"`,
  fresh-install OK (full module build of the go-1.26.9 repo from zero),
  upgrade OK (v0.1.0-rc1 tree → HEAD reinstall clean). Edge: the gate parses
  the floor but the tarball is still hardcoded go1.26.5 < floor 1.26.9 — it
  worked because GOTOOLCHAIN auto-bootstrap accepted it. Filed as DG-012.
- **Agent teardown: clean.** No destroy-refusal this run; agent absent from
  `bunker list` immediately after collect (prior runs needed a host pkill).

## New findings (filed on the qa-audit board)

- **DG-010 (P1)** — `ci-act UNVERIFIED (act rc=1)` while Build/Vet/Test/selftests
  were ALL green: the one ❌ is crier's "Client round-trip (crier keygen)"
  workflow step, which shells out to `examples/demo.sh` — and demo.sh:44
  hard-requires HOST `openssl` that the act runner image doesn't guarantee.
  The repo's keygen is Go ed25519 (no openssl) — the leg's dependency is
  wrong for the runner. Second defect: the cell detail buries the failing
  job name at byte ~1300 of a 1464-char blob; a user reading the cell cannot
  see WHAT failed. Fix direction: guarantee openssl in the workflow step (or
  drop the leg), and extract failing job names into the cell detail.
- **DG-011 (P2)** — `fresh-install OK` detail reads `go: downloading
  github.com/remyoudompheng/bigfft...` — a module-download progress line, not
  an install result. The fresh-install leg shares its log with the toolchain
  bootstrap, so a real failure's diagnostics drown under progress noise and
  the OK detail is not evidence of what was built.
- **DG-012 (P2)** — toolchain bootstrap hardcodes the go1.26.5 tarball while
  parsing the repo's floor (1.26.9); a floor above the hardcoded tarball +
  no GOTOOLCHAIN egress reproduces the DG-003 failure class despite the fix.

## Honest cell picture for crier @839b4f2

fresh-install OK · ci-pass OK · ci-act UNVERIFIED (demo-leg openssl, see
DG-010) · upgrade OK · docker-deploy/chaos-shutdown SKIPPED (safety gate,
controller=live Hermes host) · ui-probe/chaos-corruption N/A ·
chaos-disconnect UNVERIFIED (empty disc.log — suite produced no output) ·
chaos-resource PASS · chaos-errorpath OK.

## Install leg

SKIPPED-install-bunker for the skill-standard host **bunker-las-03** (ssh
100.69.3.13 connect timeout, rc=255 — fourth consecutive tick; bunker2 and
bunker4 also unreachable; bunker-mvp answered and carried the run). Named
substitute: the battery's own fresh-install cell on the JIT agent —
clean-machine install proof modulo the shared host. DG-004 stays filed.

## Perf (Step 2b)

Headline ops measured; nothing user-noticeable-slow beyond the battery's
inherent ~10m fresh-system work: `status` 0.42s wall / 0.02s cpu (3 runs,
warm stable); `launch` ~5s; `collect` 2m39s (user 0.08s / sys 0.10s —
dominated by ssh wait on the agent, I/O-bound as designed). No PERF rows
filed; no profile justified.

## Foreman

Not woken (read-only dogfood lane). Cooldown/enablement untouched.

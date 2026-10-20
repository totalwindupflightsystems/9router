# Dogfood run — 2026-10-20 (qa-audit-dogfood-2026-10-20-11-29-14)

## What was tested

The QA battery harness itself (`~/.hermes/scripts/bunker-qa.sh`), driven as a real
user does: `status` → `launch <repo>` → detached battery → `collect --evidence`.

Target repo for the battery: **coding-hermes-boardctl** (a Go CLI, never picked by a
tick in this tick's window), tested at the checkout's recorded HEAD
`676985019ff27074d5a6ed23660ea35f3de748e7` on `bunker-mvp` (agent `3d7287b1`,
ttl 2h).

**Whether the harness actually works is the question this run answers**, per the
lane skill's law: "all tests are green" is not a finding — one real run is.

## Resume disclosure (this tick ran in two deliveries)

This tick's **first delivery** performed the legs; this delivery found them complete
and finished the tick instead of repeating it:

| leg | first delivery (artifacts on disk) | this delivery |
|---|---|---|
| `status` ×3 | 0.53 / 0.52 / 0.52 s (`/tmp/qa-audit-df-20261020-1129/status-{1,2,3}.{out,time}`) | read, not re-run |
| render probe ×2 | `__gen-remote` → 135984 B, no abort (`/tmp/qa-audit-render.out`) | re-measured 2× for the render row (0.03 s, 123018 B, byte-identical) |
| launch attempt with `--help` | refusal row + garbage `.meta` (`/tmp/bunker-qa-evidence-20261020T113445Z-1848342.jsonl`) | read; basis of DG-016 |
| launch boardctl | rc=0, `LAUNCHED agent=3d7287b1`, 41.54 s wall (`launch.{out,err}`) | not re-run (no second battery) |
| battery | 11:35:50Z → 11:41:00Z, `CELLS-DONE`, `qa-run.finished`, 19 evidence rows | harvested pre-collect (14 per-cell logs) |
| collect | `COLLECTED agent=3d7287b1 rows=19`, rc=0, 91.01 s (`collect.{out,err}`) | not re-run |

Attribution for "first delivery = same tick": the working dir name
`/tmp/qa-audit-df-20261020-1129` carries this tick's timestamp, every artifact's cwd
was `/home/kara/.hermes/stand-in/dogfood/qa-audit` (this lane), and the
`events/tasks` files were byte-unchanged from the 2026-10-19 22:48 write. The other
session holding the `11-29-14` timestamp is `muster-dogfood` (different lane, its own
agents `df-muster-*`). **No leg was re-run to look busy, and no second battery was
launched** — a relaunch would have burned a bunker slot and duplicated evidence.

## What the user experienced

| step | command | result | wall |
|---|---|---|---|
| preflight | `bunker-qa.sh status` | `bunkerd=active docker=yes act=no uidmap=yes` | 0.53 s cold, 0.52 s warm (×2) |
| first touch | `launch --help` | **refused as a repo path** ("--help is not a git repo"), rc=1, no agent; `.meta` `project=` = 8 lines of basename(1) help text | — |
| launch | `launch /home/kara/coding-hermes-boardctl` | `LAUNCHED agent=3d7287b1 evidence=…` | 41.54 s (`user 0.22 sys 0.28`) |
| battery | (detached on the agent) | 19 evidence rows, `CELLS-DONE` | 5 m 10 s |
| collect | `collect --evidence …/boardctl-evidence.jsonl` | `COLLECTED agent=3d7287b1 rows=19` rc=0, agent destroyed | 91.01 s (`user 0.12 sys 0.15`) |

Time-to-first-success: ~6.5 min from `status` to a collected verdict (41.5 s launch +
5 m 10 s battery + 91 s collect), with the user free during the battery.

### Step 2b — what using it costs (numbers, not adjectives)

- **`status` 0.53 s cold / 0.52 s warm.** Three consecutive runs, spread 0.01 s. The
  usage doc promises "0.4 s" — close enough that no user notices.
- **`launch` 41.54 s** one-shot, `user+sys ≈ 0.5 s` → the wait is transport/peer-bound,
  not compute. Composition measured on the controller: script render 0.03 s
  (123018 B), `git rev-parse/status` probes ≤0.02 s, previous-release archive
  `git archive v0.1.10` 6.0 MB in 0.04 s, sync payload of the tree (excluding `.git`)
  **33.9 MB**. The remaining ~41 s was not split further on purpose: that needs a
  second spawn, which was deliberately not spent this tick. The usage skill's
  "≤30 s" is therefore a bound this repo class exceeds (34 MB payload), and the honest
  statement is *"41.5 s one-shot, dominated by payload ship + agent boot; no CPU hotspot
  to profile"* — not a PERF row.
- **`collect` 91.01 s** for an already-finished battery (19 rows to merge + teardown
  verify ladder + destroy). `user+sys ≈ 0.27 s` again → network/peer-bound.
- **Verdict on speed: comfortably usable.** Nothing here is slow enough to file: both
  long waits are inherent to the work (ship a repo to a JIT box; pull evidence back and
  prove the box is gone), the CLI reports progress, and there is no hotspot a profile
  could shorten. A "win nobody can feel" would devalue the rows that matter.

## Battery verdicts (every cell read individually, not the headline)

repo-head OK `6769850` (clone dirty — pull skipped, recorded sha) ·
toolchain-bootstrap OK ×7 (`go 1.27.3` installed, floor 1.26.9; gcc/g++ wrappers; make
4.3; compose plugin; buildx v0.38.0; node v22.15.0; HARNESS-COMPOSE=ok;
HARNESS_NODE=ok) ·
fresh-install OK · upgrade OK (`v0.1.10` → HEAD reinstall clean) ·
**ci-pass OK "act: 1 jobs green — rc=0 (1 triggerable workflow(s))"** (act ran the
repo's real workflow: Build 42 s, Vet 15 s, Gofmt, Version-check, Spec-check,
govulncheck, Vulnerability-check, **Test 22.6 s**, "Job succeeded") ·
docker-deploy N/A (no compose file) · ui-probe N/A (no web UI — a CLI) ·
chaos-shutdown N/A · chaos-corruption N/A (no db/state files) ·
chaos-resource PASS (12 packages ok under the 3G cap, `cap=3145728KB`) ·
chaos-errorpath OK (clean refusal, rc=2 on missing config) ·
**chaos-disconnect UNVERIFIED** (0-byte `disc.log` — the filed DG-006 mechanism).

No product defect was found in boardctl; its battery is green on every cell that could
run. The findings below are about the **harness's own evidence quality**.

## Findings filed this run

- **DG-015 (P3, new)** — ci-pass OK on the act-green path is undiagnosable: the cell
  counts with a **dead pattern** (`grep -cE 'Job succeeded|✅ Success'` = 1 while the log
  holds 15 `"✅  Success - …"` lines; act separates glyph and word with TWO spaces), and
  nothing in the row says whether a test ran — while the native suite is **never run at
  all** on that path (no `native.log` in the 14-file harvest; it lives only in the
  act-red branch, `bunker-qa.sh:2053`).
- **DG-016 (P4, new)** — `launch --help` is graded as a repo path: no `-h/--help`
  handling anywhere in `launch()`/`run()`, and the refusal path writes a `.meta` whose
  `project=` field is basename(1)'s own multi-line help text.
- **Event 35 → DG-006** (evidence, premise intact) — artifact-level proof that the
  native suite never runs on the act-green path.
- **Event 36 → DG-012** (re-proof) — the floor-tracking bootstrap installed `go 1.27.3`
  for a `go 1.26.9` repo: DG-012's hardcoded-`go1.26.5` premise does not reproduce in the
  **working tree**, but that fix is uncommitted (sha256 `56294ccd…`, sibling
  `QA-GUARD-005` patch, mtime 11:34Z before the 11:35:50Z launch) — close it when it lands.
- **Event 37 → QA-HARNESS-RENDER-001** (re-proof) — 123018-byte render, byte-identical on
  re-render, and a real launch shipping `script_bytes=123353` with a complete battery:
  the P0 0-byte render does not reproduce at this tree; fix `69b621250` is an ancestor
  of HEAD.
- **Event 38 → DG-014** (checked, not triggered) — no disk preflight exists in the tree;
  this run's host read 20 GB free and completed normally.

## Not exercised this tick (stated, not implied)

- `docker-deploy` / `chaos-shutdown` — N/A by design (no compose file) — not the
  controller lifecycle gate this time.
- `chaos-disconnect` — the leg produces no output (DG-006), so the network cut was never
  exercised.
- `QA-HARNESS-LEAK-001/002` (agent leaks on the launch/collect refusal paths) — **not
  triggered**: this run's refusal happened *before* the spawn (repo sanity check), and
  collect completed with the agent absent from `bunker list` afterwards.
- Install leg: **run** (the battery's own fresh-install cell on a JIT agent: full module
  download + build from zero on a box holding no repo), host = `bunker-mvp`. The skill's
  standard host `bunker-las-03` (100.69.3.13) is tailnet-offline (last seen 15 d) — per
  the leg's own rule, one healthy host suffices, so this is a substitution, not a
  SKIPPED row. Named substitute: `bunker-mvp`, `bunkerd=active docker=yes act=no`.

## The right way to use it (unchanged, with today's corrections)

```bash
bash ~/.hermes/scripts/bunker-qa.sh status          # always first (~0.5s)
bash ~/.hermes/scripts/bunker-qa.sh launch <repo>   # ~5-45s; prints LAUNCHED + evidence path
# poll, never wait inside one call:
bash ~/.hermes/scripts/bunker-qa.sh collect --evidence <path>
```

Harvest the agent's per-cell logs **before** collect (`tar -C $HOME -czf - qa-logs-*`
over ssh) — collect destroys the box. Read every cell row with `jq`, never the summary
line; a battery's `ci-pass OK` is act-leg evidence unless the act leg went red.

## ch:trace

`row=DG-015,DG-016 spec=none:qa-audit-has-no-shipped-spec test=none:no-suite-runs-the-harness(DG-HARNESS-GATE-001) doc=docs/dogfood/2026-10-20-integration.md+skills/qa-audit-usage/SKILL.md evidence=/tmp/qa-audit-df-20261020-1129/{boardctl-evidence.jsonl,harvest/,launch.out,collect.out} witness=measured:real-battery-run(at=676985019ff27074d5a6ed23660ea35f3de748e7, agent=3d7287b1@bunker-mvp) verdict=harness-green-product-cells-clean-with-two-evidence-gaps commit=board-commit-this-tick memory=/project/qa-audit/dogfood/2026-10-20`

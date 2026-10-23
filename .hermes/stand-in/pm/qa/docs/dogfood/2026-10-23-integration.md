# qa-audit — dogfood integration report, 2026-10-23

**Tick:** `qa-audit-dogfood-2026-10-23-13-43-53` · **Lane:** qa-audit-dogfood (skill-driven)
**Stand-in workdir:** `/home/kara/.hermes/stand-in/pm/qa` · **Board repo HEAD at tick start:** `78be8b4637152d73906247a61c299c715368a41f`
**Evidence dir:** `/tmp/qa-audit-df-20261023-1343/`
**Verdict: 🟡 PROMISING-BUT-ROUGH** — the QA harness genuinely installs a project on a clean
machine (fresh-install OK for crier at HEAD `fb6cbfc6`), but the orchestration around it is
brittle enough that a real user could not complete one lifecycle on the default settings today.

## Promise (the null hypothesis)

*A user can take any fleet repo, prove it builds and installs on a clean machine, and get a
graded set of cells (install, CI, upgrade, docker, UI, chaos) by running three documented
commands — `status`, `launch`, `collect` — against an ephemeral bunker agent.*

## What the user actually did

Target: `crier` @ `fb6cbfc69c921846176f5566b0c2a9f1fe7aeec6` (54.7 MB tracked, 1140 files).

| # | command | result | wall |
|---|---|---|---|
| 1 | `bunker-qa.sh status` | `bunkerd=active docker=yes act=no uidmap=yes` — green | **0.479 s** (hyperfine: 465.4 ms ± 34.9 ms, 5 runs) |
| 2 | `bunker-qa.sh launch crier` (default `bunker-mvp`) | rc=1, `spawn <id> failed at stage rootless-install … Could not enable linger: Connection timed out` | **211.49 s** |
| 3 | same again | rc=1, identical stage, identical message | **211.18 s** |
| 4 | `BUNKER_QA_SERVER=bunker-las-02 launch crier` | rc=1 — `repo sync failed — ssh: connect to host 100.116.99.35 port 2223: Connection refused` **after spawning agent `e9862866`** | **73.08 s** |
| 5 | `BUNKER_QA_SERVER=bunker-las-02 collect --evidence …` | `COLLECT-FAIL unreachable-agent` on a battery that was alive on port 22 | **90.69 s** |
| 6 | `BUNKER_QA_SERVER=bunker-las-02 BUNKER_QA_SSH_PORT=22 launch crier` | rc=0 — `LAUNCHED agent=634852c9 evidence=/tmp/bunker-qa-evidence-20261023T140019Z-1181340.jsonl` | **125.98 s** |
| 7 | same + `collect` | `RUNNING agent=634852c9` (correct: battery still running) | **2.32 s** |

Time to first successful launch: **~10 minutes and four launch attempts** (two hosts, one
undocumented env var). The documented protocol alone never reached a battery.

## Boundary-by-boundary

- **Fresh install on a clean box: WORKS.** `fresh-install OK` — the agent installed Go 1.27.3,
  gcc/g++, make 4.4.1, node v22.15.0 + npm 10.9.2, compose and buildx plugins, then built
  crier (`go build ./...` downloaded and compiled the full module graph).
- **Docker on the agent: available on bunker-las-02 — but the lifecycle cells are gated off by the
  CONTROLLER, not by the agent.** `HARNESS-COMPOSE=ok` and the CI leg really ran `act` containers
  (`docker create image=catthehacker/ubuntu:act-latest`); `docker-deploy` and `chaos-shutdown` were
  then graded `SKIPPED — safety gate: controller is the live Hermes host; Compose lifecycle cells are
  forced off`. So "docker works" is proven for the act leg and NOT proven for compose lifecycle: those
  two cells are unverified on this controller by design.
- **The battery itself produced a real, gradable result (19 evidence rows).**

| cell | status | note |
|---|---|---|
| fresh-install | **OK** | Go 1.27.3, gcc/g++, make 4.4.1, node v22.15.0, compose+buildx; `go build ./...` clean on a clean box |
| ci-pass | **FAIL** | native suite rc=1 — `TestChatLateJoinTruth` + `TestChatClientNoParallelAuthOrExecution` fail (see below) |
| upgrade | **OK** | previous release `v0.1.0-rc2` via `git archive` → HEAD reinstall clean |
| ui-probe | **OK** | `/chat` and `/docs` serve `200 text/html`, 131394 B |
| chaos-disconnect | UNVERIFIED | suite already red, so the disconnect verdict is not derivable |
| chaos-shutdown / docker-deploy | SKIPPED | controller-host safety gate (above) |
| chaos-corruption | N/A | no db/state files in repo |
| chaos-resource | INFO | OOM under the 3 GiB cap (expected for a heavy suite) |
| chaos-errorpath | **OK** | broken config → rc=1 with the variable named in the log |
| collect | OK | 19 rows pulled, merge-deduped, agent destroyed (2 destroy attempts failed, the third landed late — the documented benign shape) |

- **Target product defect found by the battery, confirmed on the controller:** crier's `cmd/server`
  suite is RED at HEAD `fb6cbfc6`. Reproduced outside the battery in a detached worktree:
  `go test ./cmd/server -run 'TestChatLateJoinTruth|TestChatClientNoParallelAuthOrExecution'` at
  `fb6cbfc6` → `RESULT 0/12 passed` with `updateClassControls is not defined`, plus
  `embedded chat contains forbidden shortcut "Authorization:"`. Root cause of the first is the test
  harness's own extraction list (`scripts/chat-late-join-truth.cjs:74-77` stops the extracted region at
  the `// Management reads deliberately` marker, which now sits ABOVE `updateClassControls`
  (`cmd/server/chat.html:1103`) while `chat.html:591/598/699` call it from inside the extracted code);
  the second is `chat.html:1101` containing `Authorization:` prose that
  `cmd/server/chatclient_ui_test.go:196-203` forbids.
- **Agent provisioning on the default server: BROKEN (today).** Two identical 211 s spawn
  failures at `stage rootless-install`; the harness retries 3× at ~70 s each, so the user pays
  the whole ladder before being told.
- **Fallback host: cost one undocumented variable.** `server_ssh_port()` hardcodes 2223 for
  every non-mvp server; bunker-las-02 agents answer on **22** (`ssh -p 22 … → REACHED port=22`,
  `ssh -p 2223 … → Connection refused`). Launch and collect both dial the wrong port.
- **Teardown: two leaks observed, one of them mine.** The sync-failure path left agent
  `e9862866` running with no destroy call; I destroyed it and verified the host back to 0
  agents. Separately, `bunker list --server bunker-mvp` showed four
  `destroy-refused:live_processes` agents (40.1 GB) created the same day, three provably from
  this harness's own runs, one (`0e8aec07`) six hours past its `Expires At`.

## Findings filed (qa-audit board)

| row | severity | defect |
|---|---|---|
| `QA-HARNESS-PORT-1` | P2 | port table wrong for bunker-las-02 → launch dies at repo sync, collect reports the live battery unreachable |
| `QA-HARNESS-LEAK-003` | P2 | repo-sync failure exits 1 without `qa_destroy_agent` (`:3357-3363`, twin `:3189-3192`) → agent left running (third leak path) |
| `QA-HARNESS-STATUS-1` | P2 | `status` green while spawn is broken; spawn-failure line probes "port 22 AND port 22" and blames the network for a systemd failure |
| `DOC-009` | P4 | usage-skill numbers/protocol drift (launch 5-45 s vs 126 s measured; fixed stale-agent count; missing port override; "8 slots" vs 6/50) |
| `QA-CRIER-1` | P1 | crier's `cmd/server` suite is RED at HEAD `fb6cbfc6` on a clean machine and on the controller (stale function-extraction list in `chat-late-join-truth.cjs`; `Authorization:` prose vs the forbidden-shortcut guard) |

Plus event **47** on `QA-HARNESS-LEAK-001` (expired leaked agents are not reaped) and event
**48** on `DOC-009` (capacity drift found after filing).

## Performance (Step 2b)

| operation | number | reading |
|---|---|---|
| `status` (documented preflight) | 465.4 ms ± 34.9 ms and 531.6 ms ± 2.3 ms (two hyperfine samples, 5 runs / 2 warmup each, same binary) | fast; not the problem — its *content* is |
| `launch`, working path | 125.98 s (54.7 MB payload) | payload-bound, matches the script header (60-120 s); the skill's old "5-45 s" was wrong |
| `launch`, broken spawn | 211.49 s / 211.18 s | 3 × ~70 s spawn attempts, no early abort — the user pays the full ladder |
| `collect`, wrong port | 90.69 s → wrong verdict | the wrong constant costs 90 s *and* a false failure |
| `collect`, right port, battery alive | 2.32 s → `RUNNING` | 39× faster, same binary, same agent |
| `collect`, battery FINISHED (pull + teardown + destroy) | **337.64 s** | the skill's "~90s for an already-finished battery" understates it 3.7× — two destroy attempts failed before the third landed late |

No profile was warranted: every number above is dominated by network/spawn/substrate waits
(near-zero user+sys in `/usr/bin/time`), not by compute in the script. Nothing here is a
`PERF-<n>` finding — the cost is a wrong constant, filed as `QA-HARNESS-PORT-1`.

## Install leg (ephemeral bunker)

**PARTIAL, not skipped.** The default host (`bunker-mvp`) could not spawn at all today, so the
install leg ran on `bunker-las-02` with `BUNKER_QA_SSH_PORT=22`. On that box the battery's
`fresh-install` cell graded **OK** for crier — i.e. installability was proven on a genuinely
fresh agent. What is *not* proven is the protocol as documented (default server, no extra env):
that path failed 4/4 times before the override.

## What a new user needs that is not documented

1. The port override for non-mvp hosts (now added to the usage skill).
2. That `status` does not test spawn capability or the agent's docker socket.
3. That a failed launch can leave an agent behind, and how to find it (`bunker list --server`).

## The battery, closed (collect 14:2xZ)

Battery ran 14:02:25Z → `CELLS-DONE`; collect (`BUNKER_QA_SERVER=bunker-las-02
BUNKER_QA_SSH_PORT=22 bunker-qa.sh collect --evidence …`) returned
`COLLECTED agent=634852c9 rows=19` and the agent is gone from
`bunker list --server bunker-las-02` (tail census: 2 agents, not ours). The evidence file
holds 24 rows with **0 duplicate `(cell,status,detail)` groups**.

| cell | grade | measured |
|---|---|---|
| `repo-head` | OK | `fb6cbfc69c92…` (clone dirty → recorded sha tested) |
| `toolchain-bootstrap` ×8 | OK | go 1.27.3 (floor 1.26.9), gcc/g++, make 4.4.1, compose plugin, buildx v0.38.1, node v22.15.0 / npm 10.9.2 |
| `fresh-install` | **OK** | full `go build ./...` module graph fetched and compiled on the fresh agent |
| `ci-pass` | **FAIL** | `native rc=1` — the native suite, run **uncapped**: exactly 2 failures, `TestChatLateJoinTruth` and `TestChatClientNoParallelAuthOrExecution` |
| `upgrade` | OK | previous release `v0.1.0-rc2` (git-archive tree) → HEAD reinstall clean |
| `ui-probe` | OK | `/chat` 200 `text/html` 131394 B, `/docs` 200 11885 B on :8767 |
| `docker-deploy` / `chaos-shutdown` | SKIPPED | safety gate: controller is the live Hermes host |
| `chaos-corruption` | N/A | no db/state files in repo |
| `chaos-resource` | INFO | OOM under the 3 GiB cap (see the discrimination below) |
| `chaos-errorpath` | OK | documented failure on broken config: rc=1, log names the variable |
| `chaos-disconnect` | UNVERIFIED | suite already red first — honest skip, not folded into PASS |

**The ci-pass FAIL is a real product defect, already tracked by crier's own board:**
`INT-CRIER-015` (P0, "main red: TestChatLateJoinTruth + TestChatClientNoParallelAuthOrExecution
fail on origin/main") and `DF-CRIER-483` (P1, `updateClassControls()` wired but no definition
reachable where the harness extracts). This run adds *clean-machine* corroboration and nothing
new, so no crier row was minted and no cross-board write was made (a crier foreman wave is
active on that board).

**Do not read `res.log` as a product verdict.** The capped leg (`chaos-resource`, `ulimit -v
3145728` at `bunker-qa.sh:2913/2927`) shows **5** failures where the uncapped `native.log` shows
**2**: the three extras (`TestChatInFlightTruth`, `TestChatLifecycleTruth`,
`TestChatRefusalTruth`) die on `RangeError: WebAssembly.instantiate(): Out of memory: Cannot
allocate Wasm memory for new instance` (node/undici) *after* their assertions printed
`RESULT 16/16 passed`. The agent had 15.8 GB free — the cap is virtual address space, not RSS.
Filed as `QA-HARNESS-CAP-1`; the reproduction is `( ulimit -v 3145728; node <harness> )` vs the
same command uncapped.


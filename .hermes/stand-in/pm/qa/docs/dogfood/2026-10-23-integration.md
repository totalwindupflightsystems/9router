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
- **Docker on the agent: WORKS on bunker-las-02.** `HARNESS-COMPOSE=ok`, and the CI leg
  actually ran `act` containers (`docker create image=catthehacker/ubuntu:act-latest`). This
  contradicts the `docker=yes` reading of `status` on bunker-mvp, which is a HOST probe.
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
| `QA-HARNESS-LEAK-003` | P2 | repo-sync failure exits 1 without `qa_destroy_agent` → agent left running (third leak path) |
| `QA-HARNESS-STATUS-1` | P2 | `status` green while spawn is broken; spawn-failure line probes "port 22 AND port 22" and blames the network for a systemd failure |
| `DOC-009` | P4 | usage-skill numbers/protocol drift (launch 5-45 s vs 126 s measured; fixed stale-agent count; missing port override; "8 slots" vs 6/50) |

Plus event **47** on `QA-HARNESS-LEAK-001` (expired leaked agents are not reaped) and event
**48** on `DOC-009` (capacity drift found after filing).

## Performance (Step 2b)

| operation | number | reading |
|---|---|---|
| `status` (documented preflight) | 465.4 ms ± 34.9 ms and 531.6 ms ± 2.3 ms (two hyperfine samples, 5 runs / 2 warmup each, same binary) | fast; not the problem — its *content* is |
| `launch`, working path | 125.98 s (54.7 MB payload) | payload-bound, matches the script header (60-120 s); the skill's old "5-45 s" was wrong |
| `launch`, broken spawn | 211.49 s / 211.18 s | 3 × ~70 s spawn attempts, no early abort — the user pays the full ladder |
| `collect`, wrong port | 90.69 s → wrong verdict | the wrong constant costs 90 s *and* a false failure |
| `collect`, right port | 2.32 s → `RUNNING` | 39× faster, same binary, same agent |

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

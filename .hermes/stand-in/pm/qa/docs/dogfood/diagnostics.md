# qa-audit diagnostics — how the QA pipeline is built, and the right way to use it

This is the "why it is the way it is" record, written from a real dogfood run
(2026-10-09) plus the project's own documented history (every contract in the
script carries the QA-* row id that forced it).

## What the thing actually is

The qa-audit "project" is not a product; it is the fleet's QA foreman
pipeline: `bunker-qa.sh` (~3000 lines of hardened bash) + the dagger role
wrapper (`dagger-role-tick.sh qa`). It JIT-spawns a throwaway bunker agent,
syncs a fleet repo into it, and runs a fresh-system battery: fresh-install ·
ci-pass (act) · native suite · upgrade-from-previous-tag · docker-deploy ·
ui-probe · four chaos cells (disconnect / shutdown / corruption / resource /
errorpath). Every cell writes a JSON row to an evidence jsonl; collect merges
them back and destroys the agent.

## Why the odd shapes exist (each one is a scar)

- **Phase split (launch/collect)** — QA-HERMES-CANOPY-8: a full battery takes
  7-15 min but a Hermes tool call dies at ~180s. Launch is bounded ≤ ~30s and
  waits on NOTHING; collect is a short idempotent poll.
- **Generated remote script, shipped base64/stdin** — never nested ssh quoting
  (2026-08-27 incident: PIPESTATUS eaten, $(..) expanded locally, syntax
  errors misread as hangs).
- **Completion marker + EXIT trap** (`~/qa-run.finished`) — collect must
  distinguish "battery done" from "agent died mid-run".
- **SCRIPT_BYTES=0 refusal** — QA-DF-CHIMERA-V2-51: a LAUNCHED marker over an
  empty qa-run.sh is silent battery death; launch now refuses.
- **qa_destroy_agent with 3 retries + list re-check** — QA-BUNKER-39: a
  destroy can time out while still landing late; the honest verdict is the
  server list, not the rc. Teardown-GONE / RECOVERED / LEAK is the contract.
- **spawn reachability gate + port-22 fallback** — QA-HERMES-CANOPY-16,
  QA-HIVEMIND-WORK-18: an unreachable spawn is an orphan holding a slot; it
  must be destroyed before retry.
- **HEAD pinning in evidence** — QA-HERMES-DAGGER-25/26: a finding must be
  traceable to the exact commit (a stale clone once produced a false P1).
- **UNVERIFIED over false green** — QA-BUNKER-29 (vacuous native suite),
  QA-CHIMERA-V2-39 (failed act leg folded into OK): cells that did not
  genuinely run must say UNVERIFIED/N/A, never ride a sibling's pass.

## What the 2026-10-09 run added to this trail

- **The composition contract has one live leak (DG-001):** ci-pass said OK on
  a commit where fresh-install FAILed. Each cell is honest; the correlation
  between them is not rendered anywhere, so any aggregate reader over the
  evidence jsonl sees green CI on a broken install.
- **The render path can abort mid-heredoc under `set -u` while returning
  rc=0 (DG-002):** observed on the real launch path and via the __gen-remote
  test hook. The empty-payload guard at launch is what currently stops a
  0-byte battery from shipping; the render itself should not be able to
  return success over a partial script.
- **No Go directive check before shipping `go build ./...` (DG-003):** repos
  pinning go >= the agent toolchain fail four cells with one truncated root
  cause. A directive-vs-toolchain compare in detect_cmds would render
  SKIP/INFO with the named gap instead.
- **Substitution discipline worked (DG-004):** the skill-standard host
  las-bunker-03 was unreachable; the run named the substitute (batteries on
  bunker-mvp) instead of passing it off as the leg.

## The right way, in one paragraph

Check `status` first (0.4s) — never launch against a server you have not
probed. Launch, then poll collect every 3-5 min in separate short calls; do
not wait inside one call. Read evidence rows with jq, never a summary line
alone; cross-check ci-pass against fresh-install before believing either.
Treat TEARDOWN-LEAK and destroy-refused agents as capacity incidents (8-slot
cap; two stale agents currently sit on bunker-mvp). Copy evidence jsonls
somewhere durable if the finding matters — /tmp does not survive.

## What the 2026-10-20 run added to this trail

- **ci-pass's OK text is act-only evidence on the act-green path (DG-015).** When the
  workflow is triggerable and act exits 0, the cell is graded from act alone
  (`bunker-qa.sh:2040-2041`) and the native suite — which lives in the act-RED branch at
  `:2053` — never runs: today's harvest holds 14 per-cell logs and no `native.log`. The
  job count in that text is computed with a dead alternation (`'Job succeeded|✅ Success'`;
  act prints TWO spaces after the glyph, so the second branch has never matched). Read the
  act log itself when you need test evidence on an act-green battery.
- **The CLI has no first-touch help path (DG-016).** `launch --help` is treated as a repo
  path: the repo sanity check refuses it (correctly, pre-spawn) and the refusal's `.meta`
  records `project=` = basename(1)'s multi-line help text, because `PROJ=$(basename "$repo")`
  (`:3041`) consumes the flag. The Usage block exists in the file but is not reachable by
  asking the tool for it.
- **The render path no longer aborts, and it is cheap.** `__gen-remote` renders 123018 B
  in 0.03s, byte-identical on an immediate second render; a real launch shipped
  `script_bytes=123353` and produced a complete 19-row battery. So the P0
  0-byte-render premise (QA-HARNESS-RENDER-001) does not reproduce at this tree —
  `69b621250` (GUARD-DF-009) is an ancestor of HEAD. Keep rendering as a cheap pre-flight
  probe: it costs 0.03s and catches the whole class before a slot is spent.
- **The floor-aware bootstrap works — but only in the working tree.** The run's
  toolchain-bootstrap row (`go 1.27.3 installed … floor=1.26.9`) came from an uncommitted
  sibling patch; HEAD still hardcodes the tarball. Verify provenance of a harness fix
  before crediting it: `sha256sum` the script the battery actually read, and check the
  comments' row id (QA-GUARD-005) against HEAD's content.

## What the 2026-10-23 run added to this trail

- **The lifecycle is three commands, but only one of them is honest about failure.** `status`
  (`bunker-qa.sh:224-229`) ssh's the *server host* and prints that host's
  `bunkerd`/`docker`/`act`/`uidmap`; it says nothing about whether the daemon can provision an
  agent, and nothing about the *agent's* docker socket (which is what the battery gates on).
  Measured today: `status` green in 465 ms, then two launches failed 211.49 s / 211.18 s at
  `stage rootless-install … Could not enable linger: Connection timed out`. The failure line's
  own root cause is a guess — `err_detail` (`:3145-3150`) prints
  `agent ssh port $qaprobe AND port 22`, and on bunker-mvp `$qaprobe` IS 22, so the two arms are
  the same port and the "server/network down" claim points at the wrong subsystem.
- **`server_ssh_port()` is a stale constant, not a probe** (`:81-88`: mvp→22, everything else→
  2223). bunker-las-02's agents answer on 22. The consequence is a two-sided false failure:
  `launch` spawns the agent, prints its id, then dies at `repo sync` with
  `ssh: connect to host … port 2223: Connection refused`; `collect` answers
  `COLLECT-FAIL unreachable-agent` (90.69 s) about a battery that is alive on 22. With
  `BUNKER_QA_SSH_PORT=22` the same two commands give rc=0 in 125.98 s and `RUNNING` in 2.32 s.
- **A failed launch does not clean up after itself.** The sync-failure branch (`:3357-3363`,
  twin at `:3189-3192`) writes a FAIL row and `exit 1`s without calling `qa_destroy_agent()` (`:141`),
  so agent `e9862866` stayed `running` on bunker-las-02 after the command returned rc=1. This is
  the third path of the LEAK family (001 = empty render, 002 = collect truncation, 003 = sync
  failure) and it is found by `bunker list --server <srv>` immediately after any failed launch.
- **TTL does not reap what a battery leaves behind.** At 13:50Z bunker-mvp held 6 agents, four
  `destroy-refused:live_processes` (40.1 GB, all created the same day); `0e8aec07` had expired at
  07:51Z and was still alive six hours later, `bunker info` reporting
  `Status: destroy-refused:live_processes`. Three of the four are provably this harness's own
  launches because their `/tmp/bunker-qa-evidence-*.meta` files name the agent id. Census before
  every wave; never trust a remembered count.
- **The battery itself still works, and it works on a docker-capable agent.** On bunker-las-02
  the run installed Go 1.27.3 + gcc/g++ + make 4.4.1 + node v22.15.0 + compose/buildx plugins and
  graded `fresh-install OK` for crier, then ran `act` in containers — so the "docker-less agent"
  wall in DG-017 is a *host*-selection problem, not a universal property of the harness.
- **Closed battery (same tick): the two legs of one run disagree, and the cap explains the delta.**
  `native.log` (uncapped) ends with 2 failures — `TestChatLateJoinTruth`,
  `TestChatClientNoParallelAuthOrExecution` — while `res.log` (the `chaos-resource` leg, run inside
  `( ulimit -v 3145728; … )`, `bunker-qa.sh:2913/2927`) ends with 5: the same 2 plus
  `TestChatInFlightTruth`, `TestChatLifecycleTruth`, `TestChatRefusalTruth`, each dying on
  `RangeError: WebAssembly.instantiate(): Out of memory: Cannot allocate Wasm memory for new
  instance` (node/undici llhttp) *after* its own arms printed `RESULT 16/16 passed`. The agent had
  15.8 GB free, so this is virtual-address space, not RSS — the cap kills Node, not the suite's
  appetite (`QA-HARNESS-CAP-1`). The 2 uncapped failures are crier's own, already tracked there as
  `INT-CRIER-015` (P0) and `DF-CRIER-483` (P1); this run is clean-machine corroboration, so nothing
  was minted on crier's board. Order of reading a battery for a verdict: `native.log` first,
  `res.log` never as a product verdict, `ci.log` for the act leg's own per-step failures.

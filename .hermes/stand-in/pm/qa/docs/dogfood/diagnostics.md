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

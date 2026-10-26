# qa-audit diagnostics — how the QA pipeline is built, and the right way to use it

This is the "why it is the way it is" record, written from real dogfood runs and the project's own documented history. Every contract in the script carries the QA-* row id that forced it.

## What the thing actually is

The qa-audit "project" is not a product; it is the fleet's QA foreman pipeline: `bunker-qa.sh` (~3000 lines of hardened bash) + the dagger role wrapper (`dagger-role-tick.sh qa`). It JIT-spawns a throwaway bunker agent, syncs a fleet repo into it, and runs a fresh-system battery: fresh-install · ci-pass (act) · native suite · upgrade-from-previous-tag · docker-deploy · ui-probe · four chaos cells. Every cell writes a JSON row to an evidence jsonl; collect merges them back and destroys the agent.

## Why the odd shapes exist (each one is a scar)

- Phase split (launch/collect) — a full battery takes 7-15 min but a Hermes tool call dies at ~180s. Launch is bounded and waits on nothing; collect is a short idempotent poll.
- Generated remote script, shipped base64/stdin — avoid nested ssh quoting and local expansion.
- Completion marker + EXIT trap (`~/qa-run.finished`) — collect must distinguish battery completion from agent death.
- SCRIPT_BYTES=0 refusal — an empty battery is silent death; launch refuses it.
- qa_destroy_agent with retries + list re-check — a destroy command can time out while still landing late; the server list is the teardown authority.
- UNVERIFIED over false green — cells that did not genuinely run must say UNVERIFIED/N/A.

## Target-resolution boundary — 2026-10-26

The scheduler-resolved qa-audit workdir is `/home/kara/.hermes/stand-in/pm/qa`, a tracked subdirectory of the home meta-repository `/home/kara`; the dogfood lane stand-in is not the product root. The literal documented launch against that resolved target refuses before spawning because syncing the parent would grade the wrong product. That fail-closed behavior is correct and is the first half of QA-AUDIT-HARNESS-002.

The supported-looking workaround `BUNKER_QA_SUBDIR=.hermes/stand-in/pm/qa` does launch, but it reports `project=kara`, not `project=qa-audit`. A complete battery under that identity is not a qa-audit verdict. The 2026-10-26 scoped run produced 19 rows but its install cell was ENV-BLOCKED because pnpm was missing on the agent; ci-pass was UNVERIFIED because the native runner never ran; upgrade failed because npm was missing. The collector pulled the rows and destroyed agent `acdd91d8`, verified by `bunker info` returning not_found and a later server census containing no matching id.

The correct fix direction is not to disable the parent-repository guard. The scheduler/runner contract must pass the parent git root plus an explicit relative subdirectory while preserving `CODING_HERMES_QA_TARGET` / qa-audit as the evidence project identity, and it must add a clean fixture regression. This remains an open foreman row, not a dogfood code change.

## What the 2026-10-23 run added

- status can be green while agent provisioning is broken; it probes the server host, not the agent's docker socket.
- server_ssh_port was a stale constant for non-mvp servers; a wrong port caused launch/collect false failures.
- failed sync paths can leave an agent running; census and destroy after every failed launch.
- TTL does not necessarily reap destroy-refused agents; read the live list, not remembered counts.
- compare uncapped native.log with capped res.log before calling a resource result a product failure.

## The right way, in one paragraph

Check `status` first — never launch against an unprobed server. Resolve the product root and board separately from the stand-in. For a subdirectory product, run the literal target path first; if it refuses, do not relabel a parent battery as the product. If a supported scope mechanism is used for diagnosis, verify the evidence `project` field before grading any cell. Launch, then poll collect in separate calls. Read every evidence row with jq, never a summary line alone. Treat teardown as open until `bunker info` says not_found and a new `bunker list` census has no matching agent.

## Performance evidence — 2026-10-26

`bunker-qa.sh status` took 0.42s cold one-shot and 427.9ms ± 1.6ms warm (hyperfine, 5 runs after 2 warmups). Literal target refusal took 0.03s. Scoped launch took 29.76s and scoped collect 54.51s; user+system CPU was under 0.6s for launch and 0.2s for collect, so the waits are remote provisioning/teardown rather than a local compute hotspot. No PERF row was warranted.

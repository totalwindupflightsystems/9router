---
name: qa-audit-usage
description: Use when running or driving the qa-audit QA pipeline (bunker-qa.sh) against a fleet repo — launch/collect protocol, evidence reading, known pitfalls.
---

# qa-audit QA pipeline — usage skill

Fresh-system QA batteries on JIT bunker agents. Entry point: `~/.hermes/scripts/bunker-qa.sh`.

## The protocol

```bash
bash ~/.hermes/scripts/bunker-qa.sh status
bash ~/.hermes/scripts/bunker-qa.sh launch <repo>
bash ~/.hermes/scripts/bunker-qa.sh collect --evidence <path>
```

Resolve the scheduler's canonical product root before using these commands. A scheduler lane workdir may be a stand-in or a tracked subdirectory of a larger git repository. Run the literal target path first; if the runner refuses because the path is a subdirectory, do not silently substitute the parent repository or call the result a product verdict. A scope override must preserve the requested project identity in evidence. The 2026-10-26 run showed that `BUNKER_QA_SUBDIR=.hermes/stand-in/pm/qa` launched a battery as `project=kara`, so that workaround is diagnostic only for qa-audit until the scheduler/runner contract is fixed (QA-AUDIT-HARNESS-002).

- `status` probes the control host only; green does not prove agent provisioning or the agent's Docker socket.
- `launch` starts a detached battery and returns the evidence path; do not wait for cells in launch.
- `collect` reads every cell, merges evidence, and destroys the temporary agent. Re-check `bunker info <agent>` and `bunker list --status all` after collection.
- Read every evidence row, not the summary line. Preserve PASS, FAIL, INFO, UNVERIFIED, N/A, and SKIPPED distinctions.
- If a fresh-install command cannot run because the agent lacks a required tool, classify it as environment-blocked; do not file a product defect without a control.

## Current defaults and host notes

The default server is `bunker-mvp`; override with `BUNKER_QA_SERVER`. The standard dogfood host `bunker3` / las-bunker-03 may be offline; probe alternate bunker hosts before declaring the install leg skipped. On 2026-10-26, bunker3 and bunker4 timed out, while bunker2 and bunker-mvp answered.

## Evidence example

```bash
jq -r '[.cell,.status,(.detail|.[0:220])] | @tsv' /tmp/bunker-qa-evidence-*.jsonl
```

Use one explicit evidence path rather than an unscoped glob when several runs exist.

## Performance baseline

On 2026-10-26, `status` measured 427.9ms ± 1.6ms warm (hyperfine, 5 runs after 2 warmups) and 0.42s cold. A literal target refusal took 0.03s. A scoped launch took 29.76s and collection 54.51s, dominated by remote transfer/provisioning and teardown rather than local CPU.

## Known pitfalls

- `ci-pass` may be act-only when the workflow is triggerable; inspect the act log before calling it test evidence.
- `launch --help` is not per-verb help; the top-level `--help` prints usage, while a flag-shaped launch target is treated as a path and refused.
- A failed launch can leave an agent behind; list and destroy only the agent you own.
- A capped resource log is not automatically a product verdict; compare it with the uncapped native log.
- Evidence in `/tmp` is ephemeral; copy important jsonl into a durable report directory before teardown.

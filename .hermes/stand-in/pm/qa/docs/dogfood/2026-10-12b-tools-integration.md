# Integration report — coding-hermes-tools via bunker-qa.sh (2026-10-12, 21:08Z tick)

## What was run

Real-use dogfood of the qa-audit pipeline on a repo it had never touched:
`coding-hermes-tools` @a9af41a (Go 1.26, stdlib-only, never in the QA ledger).
Discovery picked it via `qa_discover.py` ("never-qa", 1.69s). Full cycle:
`status` → `launch /home/kara/coding-hermes-tools` → poll ×3 → collect → destroy.

## Measured timeline

| step | wall | result |
|---|---|---|
| status | 0.4s | bunker-mvp active, docker yes |
| qa_discover.py | 1.69s | 2 never-qa picks |
| launch | 32s | agent fb7a626b, 116967-byte qa-run.sh shipped |
| battery | ~26m (21:24→21:50Z) | act CI ~14m dominant (red-gate selftest) |
| collect polls | 2×~35s RUNNING + final | **COLLECT-FAIL battery-truncated (false)** |
| destroy | refused → pkill → OK | live_processes gate |

## Cell verdicts (honest)

fresh-install OK (go1.26.9 pulled on the agent) · ci-pass OK (act 1 job green)
· upgrade OK (v0.1.0→HEAD reinstall) · docker-deploy N/A · ui-probe N/A ·
chaos-disconnect UNVERIFIED (empty disc.log — DG-006 class) · chaos-shutdown N/A
· chaos-corruption N/A · chaos-resource INFO · chaos-errorpath OK.

The battery itself worked end to end on a fresh Go repo. The pipeline then
mis-graded its own success: **DG-005 (4th live recurrence, root cause proven)**
— the collect truncation check greps compact `"cell":"chaos-errorpath"` while
the agent writer emits spaced `json.dumps` output, so the final-cell check
counts 0 on every healthy battery → COLLECT-FAIL battery-truncated. Filed as
**DG-009** with fix shape (parse JSON or write with `separators=(',',':')`).

Second systemic finding: launch emits stray local stderr with rc=0 —
`disc_window: unbound variable` (line 1015) because the generated battery only
assigns `suite_dur`/`disc_window` on the act-FAILED branch and the UNQUOTED
heredoc expands `${suite_dur:-0}` on the CONTROLLER at render time whenever
act is green (DG-002 3rd recurrence, root cause now identified).

## Integration notes for future users of this pipeline

1. `collect` rc=0 + "COLLECT-FAIL" is currently ambiguous; read the evidence
   file's last cell, not the collect row, until DG-009 lands.
2. A green-act battery still prints unbound-variable noise at launch — the
   launch is fine; do not re-launch because of it (DG-002).
3. Destroy can be refused by leftover agent-uid processes (dbus/sshd); the
   operator must pkill those on the bunker host before retrying.
4. docker-lifecycle cells are opt-in (`BUNKER_QA_ENABLE_DOCKER_LIFECYCLE=1`)
   and hard-blocked on the live Hermes host — by design since the 10-11
   disable; NOTE the +79-line safety block in /home/kara/.hermes
   scripts/bunker-qa.sh is still UNCOMMITTED at the time of this run.

## Evidence

- Evidence file: /tmp/bunker-qa-evidence-20261012T212406Z-2280438.jsonl (21 rows)
- Board: DG-009 row + DG-005/DG-002 recurrence events (same commit as this doc)
- Host leg: bunker-las-03 unreachable (rc=255) → SKIPPED-install-bunker named
  substitute: fresh-install cell on bunker-mvp JIT agent.

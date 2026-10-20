# Monitoring dogfood run 13 — live alert re-proof and fresh-agent install leg

Date: 2026-10-20
Target commit: 119edb53fd78f8c59c8ee78a1f1f54e7bbc8dd19
Surface: live operator alert set, spool drain, and bunker install battery

## Promise

A real monitoring operator can use the alert row as a work item, verify whether the
condition is still live, drain new alert data to the lane board, and install the
fleet-monitoring stack on a fresh machine using the documented Makefile path.

## What was exercised

The live stack was read through fleet-monitor: Prometheus `/api/v1/alerts`, a direct
filesystem-ratio query, Docker service state, and the lane drain command. The live
alert set at 04:13Z contained DiskWillFillIn24h for bunker-mvp, OOMKillsLowPressure
for bunker-mvp and karahermes-mde-7840hs, and two TargetUnreachable alerts for the
known vanished standby-cx53-01-2147 target. The direct PromQL ratio for bunker-mvp `/`
was 0.15727011946882058, so the warning remained grounded in a real 15.7% available
filesystem ratio; the earlier DiskFull condition was no longer firing.

`MON_REMOTE=fleet-monitor bash ~/.hermes/scripts/drain-board-rows.sh` appended the
DiskFull resolution twin once, then a repeat run reported no new append and 710
skipped rows. The skipped count is backlog deduplication, not proof of an empty
spool. The board file was parsed after the write: 539 valid lines and 539 unique ids.

The measured drain cost was 56.16s cold-ish and 63.03s warm at approximately 710
spool lines. A strace summary attributed 42.52s to wait4 and 3.39s to read; the
script still launches two Python parsers and a grep for every spool line. This is a
re-proof of PERF-1, not a new performance row.

## Fresh-machine leg

The active `bunker-qa.sh` path was run directly (no retired dogfood driver) on
bunker-mvp. Bunkerd was active. Agent b3cda072 was spawned, the product subtree was
transferred with `BUNKER_QA_SUBDIR=fleet-monitoring`, and the agent was destroyed by
collect; the evidence reports the temporary agent was destroyed.

Evidence: `/tmp/bunker-qa-evidence-20261020T040827Z-3795904.jsonl`.

The battery proved `make build` / compose config rendering in 0.3s after toolchain
bootstrap, but it did not execute the documented `make up` install path: its
docker-deploy cell reported `no compose file`, and its native verification failed
because the stack had never been started. Therefore this run does not claim a fresh
stack install. The direct prior real-use proof remains the applicable install
finding: `make up` failed with `failed to read dockerfile: open Dockerfile: no such
file or directory`, already tracked by MON-DOGFOOD-039. This run re-proves the
battery's install-coverage limitation, not a new product defect.

## Verdict

PROMISING-BUT-ROUGH. The production alert surface continues to report real conditions
and the drain is functionally idempotent, but the operator queue still requires the
known reconciliation and evidence-link fixes. Fresh-machine install remains failed
at the documented `make up` step, and this battery invocation did not close that
proof gap.

Existing findings re-proved: MON-DOGFOOD-039 (fresh install), MON-DOGFOOD-041
(resolution rows routed to tasks), MON-DOGFOOD-042 (no alert-state reconciliation),
MON-DOGFOOD-043 (dead evidence links), MON-DOGFOOD-044 (board validation red), and
PERF-1 (drain cost). No duplicate rows were filed.

The lane did not wake or mutate scheduler state. No target code or board row was
changed by this run; the drain's alert-resolution append remains in the shared
working tree for the owning monitoring lane to reconcile with its concurrent board
work.

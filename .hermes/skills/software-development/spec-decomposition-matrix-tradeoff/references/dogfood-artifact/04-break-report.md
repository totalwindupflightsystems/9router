# 04 — Break-check report

Load-bearing set declared before sparsification: D-001 through D-012 (12 decisions). Complete unordered pair set: 66. Every pair was enumerated first. `SUB` pairs have a substantive outcome below; `NI` means `NO-INTERACTION — checked against shared data/meaning, resource/ordering, failure/security, test truth, reversibility, and product core`; skip was legal only after this full set existed.

## Complete pair set

| D1 | D-002 | D-003 | D-004 | D-005 | D-006 | D-007 | D-008 | D-009 | D-010 | D-011 | D-012 |
|---|---|---|---|---|---|---|---|---|---|---|---|
| D-001 | SUB | SUB | SUB | NI | NI | NI | NI | NI | NI | NI | NI |
| D-002 | — | NI | SUB | NI | NI | NI | SUB | NI | SUB | SUB | NI |
| D-003 | — | — | NI | NI | SUB | NI | NI | NI | NI | NI | NI |
| D-004 | — | — | — | SUB | SUB | NI | NI | NI | SUB | NI | NI |
| D-005 | — | — | — | — | NI | SUB | NI | SUB | NI | SUB | NI |
| D-006 | — | — | — | — | — | SUB | NI | NI | SUB | NI | NI |
| D-007 | — | — | — | — | — | — | SUB | NI | SUB | NI | SUB |
| D-008 | — | — | — | — | — | — | — | NI | NI | SUB | NI |
| D-009 | — | — | — | — | — | — | — | — | NI | SUB | NI |
| D-010 | — | — | — | — | — | — | — | — | — | NI | NI |
| D-011 | — | — | — | — | — | — | — | — | — | — | SUB |

Count: 22 SUB + 44 NI = 66.

## Substantive outcomes

| Pair | Outcome | What changed or was accepted |
|---|---|---|
| D-001×D-002 | REQUIRES-REDESIGN | D-002 no longer claims downtime-transient capture; D-017/ESC-01 opened. |
| D-001×D-003 | MITIGATED | identity is root+path; rename never silently inferred. |
| D-001×D-004 | MITIGATED | only completed successful scans establish transitions. |
| D-002×D-004 | MITIGATED | staging/promotion prevents traversal from mutating canonical state. |
| D-002×D-008 | ACCEPTED-COST | one slow scan delays the next; round-robin and U-001 contain it. |
| D-002×D-010 | ACCEPTED-COST | late scan commits enter next open digest, not mtime hour. |
| D-002×D-011 | MITIGATED | progress checkpoints cannot falsely claim scan completion. |
| D-003×D-006 | MITIGATED | event schema carries old/new metadata; rename is two events. |
| D-004×D-005 | MITIGATED | SQLite transaction is the promotion boundary. |
| D-004×D-006 | MITIGATED | scan/event/current-state foreign keys establish provenance. |
| D-004×D-010 | REQUIRES-REDESIGN | D-010 selects only committed events; in-progress scan rolls forward. |
| D-005×D-007 | MITIGATED | digest assignment and event ownership share one transaction. |
| D-005×D-009 | MITIGATED | flock gives a clear second-instance failure in addition to DB locking. |
| D-005×D-011 | MITIGATED | schema/quick_check precede READY. |
| D-006×D-007 | MITIGATED | each event links at most one digest; pending work is retention-exempt. |
| D-006×D-010 | MITIGATED | service observation/commit time, not mtime, assigns window. |
| D-007×D-008 | REQUIRES-REDESIGN | D-008 gained finite network timeout and oldest-first one-at-a-time send. |
| D-007×D-010 | MITIGATED | unique window end and stable digest id prevent duplicate local rows. |
| D-007×D-012 | REQUIRES-REDESIGN | D-012 became a bounded stateless systemd one-shot, not daemon outbox work. |
| D-008×D-011 | REQUIRES-REDESIGN | watchdog heartbeat tied to scheduler progress, not a free-running timer. |
| D-009×D-011 | MITIGATED | lock acquisition is a readiness prerequisite. |
| D-011×D-012 | MITIGATED | helper timeout cannot block restart; incident id bounds duplicate noise. |

## Later-decision interactions

- D-007×D-019 → MITIGATED: network crossing made filename exposure real; D-019 adds path modes and count-only default.
- D-005×D-018 → REQUIRES-REDESIGN: live byte-copy backup replaced by SQLite backup API + fsync/rename.
- D-006×D-022 → MITIGATED: rendering coalesces; storage retains every committed event.
- D-011×D-015 → MITIGATED: service/helper root/state/credential paths became explicit sandbox inputs.
- D-017×D-023×D-024 cycle: promoted the invariant “every guarantee names its observation boundary”; D-024 split crash, disk, transient-file, process, and host claims; C-001 tracks the unresolved priority.

Unique pre-existing decisions modified by the pass: 8 — D-002, D-008, D-010, D-012, D-015, D-018, D-019, D-022. D-024 was created by collapsing the cycle and is not counted as “modified.” New objects: D-017, D-023, D-024, C-001, ESC-01, ESC-02, U-003. The pass therefore materially changed the design.

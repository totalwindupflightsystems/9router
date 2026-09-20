# 13 — Handoff contract

## Fixed

The downstream spec may treat these as settled unless a listed falsifier fires: D-001..D-013, D-015, D-020..D-022, and D-024 subject to C-001. In particular: reconciliation is authoritative; one SQLite database holds canonical/current/history/outbox state; scan promotion and digest assignment are transactional; delivery is at-least-once with stable ids; one serialized process is systemd-supervised; failures never trigger silent data pruning.

D-014, D-017, and D-023 are provisional. D-016 and D-018 are before-ship/deferred policy, not immutable product truth. D-019 defaults safely until U-003 closes.

## Investigate

- U-004 target runtime/filesystem/service-manager probe — required before implementation language and system unit are frozen.
- NOT-REACHED 4.11 deploy pipeline — package, install, rollback, and migration procedure before build tasks.
- NOT-REACHED 4.16/4.30/4.34 — error/config contracts and complete executable test plan before task decomposition.
- NOT-REACHED 4.21 security — service identity, credential rotation, sandbox verification before live receiver credentials.
- U-001 capacity soak — before numeric limits and production enablement.
- U-002/U-003 receiver and disclosure probes — before remote posting.

## Open

- ESC-01 / C-001: transient create-delete events during observer downtime. Impact: architecture and truth guarantee.
- ESC-02 / C-001: total-host outage notification. Impact: external dependency and public failure claim.
- U-004: BEFORE-BUILD target capability. Impact: D-014 and systemd/filesystem assumptions.
- U-001/U-002/U-003/U-005: before-ship/deferred rows with their own containment defaults.

## Invalidation

Re-run the full matrix if file content must be archived/understood, transient downtime events are mandatory, more than one writer/host/operator trust class appears, the product requires sub-hour hard latency, the target lacks local SQLite-safe storage/systemd/Python, or the core changes from hourly digest to a real-time workflow. Otherwise apply §10.2 to the affected dependencies.

## Consumption contract

The spec stage must:

1. Turn R1–R10 and every BEFORE-BUILD invariant map row into executable acceptance criteria.
2. Produce the DDL/migrations and crash failpoints from D-004..D-007 without changing their atomic boundaries.
3. Specify CLI/config/error contracts while preserving root ids, UTC windows, stable digest ids, and oldest-first pending delivery.
4. Produce service/alert/runbook artifacts from D-011/D-012/D-020/D-021/D-023.
5. Close or carry every U/ESC/C id explicitly and rerun affected break pairs on change.
6. Never redefine: staging as canonical, remote delivery as exactly-once, unreadable root as empty, pending data as disposable, file content as in scope, or whole-host failure as locally detectable.

Handoff readiness is NOT-READY because ESC-01, ESC-02, C-001, and U-004 are open. Containment defaults permit further design/spec work but not a claim that owner priorities are settled.

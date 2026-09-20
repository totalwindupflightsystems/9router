# 12 — Vibe sheet

Written last, after the decisions and break pass.

## IS

- Small: one CLI/daemon, one embedded state file, one host service manager.
- Quiet: one bounded nonempty digest per UTC hour; transition-based alerts rather than heartbeat spam.
- Honest: stable digest ids, explicit duplicate possibility, explicit observation and host-outage boundaries.
- Boring to operate: standard paths, startup recovery, oldest-first retry, independent journal evidence.
- Recoverable: partial scans are disposable; canonical state changes atomically; backups are verifiable.

## IS NOT

- Not distributed, highly available, or exactly-once across a network.
- Not a file backup, content index, malware scanner, dashboard, or event bus.
- Not real-time/sub-second.
- Not clever about rename or file contents.
- Not allowed to call silence a decision or a missing event “impossible.”

## Must-be-true

| Adjective | Constraint |
|---|---|
| coherent | scan promotion, events, digest assignment, retry, and supervision share one documented state model |
| short | rendering is bounded/coalesced; overflow is counted and durable detail remains local |
| durable | synchronous transactional store; no auto-prune of pending work; crash-boundary tests |
| visible | progress-coupled watchdog, one-shot failure helper, journald last resort |
| simple | one writer, no worker pool, no cache, no inbound server, no mandatory external DB/bus |
| private by default | metadata only; count-only outbound paths until classified; secrets referenced, never recorded |

## Owner phrase → technical constraint

| Phrase | Decoded constraint |
|---|---|
| “half-built internal tools where the pieces don't fit” | one canonical state model plus pairwise break-check; no independent scheduler/store/notifier semantics |
| “watches a set of directories” | configured roots and completed reconciliation; “watch” is not equated with an unreliable ephemeral event queue |
| “keeps a record of what it has seen” | current state + append-only event provenance in one local transactional store |
| “once an hour posts a short digest” | persisted UTC windows, bounded rendering, stable id, durable outbox |
| “survive a reboot” | enabled supervision, startup validation/recovery/reconciliation, pending retry |
| “tell me when it has stopped working” | watchdog/service failure coverage now; whole-host limit exposed as ESC-02 |
| “don't want to lose anything if it crashes mid-run” | atomic local transactions and explicit ack-gap semantics; transient downtime limit exposed as ESC-01 |
| “one box and no extra services” | native process + SQLite + existing systemd; external additions require a named hinge and remain optional |

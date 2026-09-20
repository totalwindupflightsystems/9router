# 01 — Scope and domain sweep

## Frozen core

The user is the operator of a small internal Linux utility. They need one coherent command-line process to discover files in configured directories, durably remember observations, and post an hourly change digest because their current internal tools are half-built and their pieces do not fit. Today they do not have a reliable single-host record-and-digest loop. If we succeed, the operator can reboot or crash the process, recover without losing any committed observation or pending digest, and see a bounded hourly summary plus a failure signal. If we fail, changes are silently omitted, digests are lost or duplicated without identity, or a dead process remains unnoticed. This is explicitly NOT a distributed event platform, a file backup product, or a general-purpose workflow engine.

Core hash: `sha256:1c90a43c31fe3fd612fcadcf3a35835918c10378cd8d3b41eb52ea043e757f1c` (`<scratch>/design-sandbox/probes/core-statement.txt`).

## IN

Configured local roots; recursive regular-file metadata reconciliation; durable current state/events/scan runs/digest windows/attempts/schema version; bounded hourly UTC digest through an outbound adapter; crash/reboot recovery; systemd supervision/watchdog/one-shot failure notification; same-CLI backup/restore verification.

## OUT, with reasons

- Distributed coordination, clustering, bus, or external DB: unnecessary for one writer and conflicts with the seed.
- File-content backup/indexing: the required record is observation metadata, not a copy of content.
- Guaranteed capture of files that exist only while the observer is down: physically requires an independent journal/producer; ESC-01.
- Universal host-outage self-alert: a dead box cannot emit; ESC-02.
- GUI, accounts, tenancy: no interactive or multi-user job exists.
- Exactly-once remote post: acknowledgement loss makes it unprovable without receiver cooperation.

## Unknown scope

Target scale U-001; receiver U-002; filename disclosure U-003; target platform/runtime U-004; backup disaster tier U-005; transient-file and whole-host priority judgments ESC-01/02.

## Triage and coverage

Score = blast radius × uncertainty × irreversibility (1–3 integers). `⊕` preserves an unconditional ring-5 floor. Ties were ordered by crash-safety dependency, then operator visibility.

Cascaded in descending triage order:

1. 4.5 Data — 3×3×3=27, floor 5, fixed point ring 5.
2. 4.6 Storage — 3×3×3=27, floor 5, fixed point ring 5.
3. 4.19 State boundaries — 3×3×3=27, floor 5, fixed point ring 5.
4. 4.20 Concurrency — 3×3×3=27, floor 5, fixed point ring 5.
5. 4.42 Failure/recovery — 3×3×3=27, floor 5, fixed point ring 5.
6. 4.44 Unknowns/assumptions — 3×3×3=27, floor 5, fixed point ring 5.
7. 4.4 Requirements — 3×2×3=18, floor 5, fixed point ring 5.
8. 4.12 Runtime — 3×2×3=18, floor 5, fixed point ring 5.
9. 4.17 Alerts — 3×3×2=18, floor 5, fixed point ring 5.

The remaining 35 domains are `NOT-REACHED` in their individual canonical `02-domains/4.xx-*.md` files. Each row records score, floor, reason, owner, trigger, containment, and required output. Equal-score 4.11 Deploy and 4.21 Security lost the bounded tie to runtime/alerts and remain named pre-build/pre-ship handoff work. No §4 domain is silently absent.

## Product boundary decisions

The architecture is one foreground CLI/daemon, one local SQLite database, one serialized scheduler, no cache, no inbound server, no mandatory third-party resident service, and one outbound adapter. “No loss” means RPO=0 for committed local transactions and restart reconciliation for files still present; it does not silently claim media-loss, downtime-transient, or whole-host guarantees.

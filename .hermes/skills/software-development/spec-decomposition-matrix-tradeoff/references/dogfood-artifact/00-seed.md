# 00 — Seed and intake lock

autonomous-mode: true
provisional-decisions: 3
evidence-refresh: 2026-09-20T12:33–12:48Z

## Owner's words (verbatim)

> "I keep ending up with half-built internal tools where the pieces don't fit. I want one
> small command-line tool that watches a set of directories for new files, keeps a record of
> what it has seen, and once an hour posts a short digest of what changed. It should run on
> one small Linux box, survive a reboot, and tell me when it has stopped working. I don't
> want to lose anything if it crashes mid-run. Keep it simple — I'd rather have one box and
> no extra services than a distributed system."

Named outcome: one coherent, crash-safe, single-host command-line file-change recorder and hourly digest poster.

Hard constraints: one Linux box; one CLI/daemon; configured roots; durable seen/change/outbox state; hourly bounded digest; boot restart; failure visibility; no silent loss of committed work.

Explicit non-goals: distributed HA; mandatory external database or bus; GUI; content backup/indexing; exactly-once network delivery.

## Frozen core statement (S1)

The user is the operator of a small internal Linux utility. They need one coherent command-line process to discover files in configured directories, durably remember observations, and post an hourly change digest because their current internal tools are half-built and their pieces do not fit. Today they do not have a reliable single-host record-and-digest loop. If we succeed, the operator can reboot or crash the process, recover without losing any committed observation or pending digest, and see a bounded hourly summary plus a failure signal. If we fail, changes are silently omitted, digests are lost or duplicated without identity, or a dead process remains unnoticed. This is explicitly NOT a distributed event platform, a file backup product, or a general-purpose workflow engine.

# PRD: `h3-pulse` — Metric–Log Correlator

**Project:** get-h3 · agent-ops line · **Item:** B2 · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed · **Effort:** M (~2 weeks) · **Depends on:** B1 (logsey) · **Feeds:** B6 forensics, GAP-125-class tuning

---

## The one-liner

A pocket sampler that records what the box was doing — load, memory, connections, disk — on the same timeline as the logs, and answers the question behind every flaky infra bug: **"what was the machine doing when this failed?"**

## The problem, measured

**Case file 1 — the 4-corruption day (2026-09-10):** the fleet's state database corrupted **four times in three hours** (11:48, 12:53, 13:54, 14:52). The root cause chain — disk at 96%, watchdog `kill -9` mid-write, repair machinery looping under pressure — was only reconstructed *afterward*, by hand, from `df` snapshots people happened to run. A 1 Hz sampler writing 40 bytes/line would have made the correlation self-evident: every corruption clusters inside the >95%-disk windows. Nobody keeps that series, because keeping it "properly" means an observability suite, and nobody installs Prometheus to answer one question.

**Case file 2 — the load-gate tuning (GAP-125):** choosing the fleet's load-gate threshold meant reasoning from anecdotes ("feels like the box dies around load 40") because there was no per-minute loadavg series joined to the spawn-storm log lines. The gate got armed at 12; nobody can say today what the box's *actual* degradation curve looks like.

Both cases share one shape: **the metric existed in the kernel's head and evaporated.** pulse keeps it, tiny.

## User stories

**US-1 (flaky-bug hunter):** As an agent investigating "the API call timed out at 02:17," I run `pulse around 02:17 --window 10m` and get loadavg, RSS-by-process-group, established-connection counts, and disk pressure for that window, side-by-side with the log lines from logsey — one screen, one answer.

**US-2 (capacity planner):** As Bane setting a load gate, I run `pulse report --last 30d --metric load1 --join hilo-log` and see the fleet's actual saturation curve against spawn-storm events — the threshold becomes a measured choice, not a vibes number.

**US-3 (post-mortem author):** As the incident reviewer, I get `pulse export --window ...` appended to the logsey evidence block — the post-mortem shows *why*, not just *what* (memory cliff? connection storm? disk full?).

**US-4 (silent-degradation watcher):** As the operator, `pulse watch --rule 'disk_used > 90 for 10m'` pings the fleet thread before the corruption loop starts — not after the fourth incident.

## What it samples (the pocket range)

| Metric | Rate | Why |
|---|---|---|
| load1/5/15, cpu% | 1 Hz | saturation curves, gate tuning |
| RSS by process-group (hermes, gateway, schedulerd, 9router) | 5 s | memory-cliff detection (the 22 GB watchdog story) |
| established connections by port (:8642, :20128, :9092) | 5 s | request-storm evidence (the 503 hour) |
| disk used% per mount, io tier | 10 s | the corruption-day signature |
| oom/kill events from kernel | event-driven | hard evidence |

**Design rules:**
- **≤ 1% of one core, ≤ 50 MB RSS, ≤ 100 MB/day on disk** — a sampler that costs more than it answers gets uninstalled; the budget is the spec.
- **One line = one timestamped JSON** into a daily file that logsey indexes like any other source — pulse deliberately has *no query layer of its own*; correlation happens in DuckDB where the logs already live.
- **Ring buffer for the hot answer:** last 24 h in RAM-mapped file so `pulse around <ts>` never waits on an index build.
- **Failure posture:** if pulse is dead, logs still flow (loose coupling); `pulse doctor` reports its own gaps honestly (its own series must show its own restarts).

## Interface

```
pulse daemon                    # the sampler (systemd unit, ~0 budget)
pulse around <ts> [--window 10m] [--join logs]
pulse report [--last 24h|7d|30d] [--metric ...] [--join logs]
pulse watch --rule '<metric> <op> <val> for <dur>' [--notify tg:...]
pulse doctor
```

## Success criteria

1. **Replay the corruption day:** with pulse's historical series present, the disk-pressure correlation is a single `pulse report --last 24h --metric disk` — the >95% windows line up with all four incidents *without human reconstruction*.
2. Rebuild the GAP-125 threshold decision from data: 30-day saturation curve vs spawn events, in one report.
3. Budget proof: 7-day continuous run on this box at ≤1% core / ≤50 MB RSS / ≤100 MB-day disk, verified by its own series.
4. `pulse around <ts>` answers in <1 s for any timestamp in the last 24 h.

## Why get-h3 / why open

Observability suites solve this at 100× the footprint; nothing ships at the pocket scale with the fleet-log join built in. Every agent-fleet operator hits "the box was weird at 3am" with zero retained metrics. pulse + logsey is the two-file answer — and the pairing is the product: **metrics on the same timeline as evidence.**

## Risks

- Sampler itself becomes load under a storm → its writes are append-only, rate-limited, and self-throttling above the budget; its own series is the watchdog.
- Metric cardinality creep (per-PID RSS explodes) → process-*groups* by config, not PIDs; the curated set is the product, not a free-for-all.
- Rules spam → notify dedup window (the fleet learned throttle-or-be-desensitized from the GAP-061 severity-demotion saga).

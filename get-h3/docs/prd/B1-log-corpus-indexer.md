# PRD: `h3-logsey` — Log-Corpus Indexer

**Project:** get-h3 · agent-ops line · **Item:** B1 · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed · **Effort:** M (~2 weeks) · **Depends on:** nothing · **Feeds:** B2 correlator, B3 runbooks, B6 forensics

---

## The one-liner

One command turns the machine's logs — journald units, app logs, structured JSONL — into a queryable DuckDB corpus with materialized views. Incident forensics go from six hand-rolled greps to one SQL query.

## The problem, measured

**Case file — the 1,813×503 hour (2026-09-16):** the fleet's gateway shed 1,813 worker requests in a single hour. Diagnosis took **six separate greps** across `gateway.log`, `agent.log`, and journald — the first grep pattern matched my own forensic commands (snoopy echoes commands into the journal), producing **two false leads** before the truth (gateway drain-restart windows + a default concurrency cap of 10) surfaced. Total cost: ~40 minutes of an agent's context on pattern-syntax archaeology.

That is the *normal* cost of "what happened on this box." Every operator of every agent fleet pays it weekly. The logs all exist. The timestamps all exist. What doesn't exist is a **queryable join across them** — so humans and agents fall back to grep, and grep doesn't scale to correlation.

## User stories

**US-1 (incident responder):** As an agent diagnosing a failure window, I say `logsey query "SELECT minute, unit, count(*) FROM logs WHERE severity >= 'WARNING' AND ts BETWEEN '18:40' AND '19:00' GROUP BY 1,2"` and get the shape of the incident in one query — not six greps and two false leads.

**US-2 (fleet operator):** As Bane, I ask "how many 503s did the API server return this week, by hour, by client?" and get an answer in seconds from `logsey`, with the exact log lines behind each bar available on demand (`logsey show <row>`).

**US-3 (agent on cold start):** As an agent newly landed on a box, I run `logsey status` and learn what log sources exist, their coverage windows, and their sizes — before my first incident, not during it.

**US-4 (post-mortem author):** As whoever writes the incident review, I run `logsey export --window 18:30-19:10 --format md` and get a timestamped, source-attributed evidence block I can paste into the post-mortem — every claim in the doc re-findable (Bane's audit doctrine).

## What it indexes

| Source | Extracted fields |
|---|---|
| journald units | ts, unit, severity, pid, message-class (normalized first tokens) |
| App logs (agent.log, gateway.log, scheduler.log…) | ts, level, component, session-id (`[api-*]`, `[TRBL-*]`), status codes, model/provider mentions |
| Structured JSONL (tick logs, guard logs, board events) | native fields — passthrough with schema sniffing |

**Design rules:**
- **Views are materialized, corpus is source-of-truth-free.** DuckDB files are rebuildable caches (never archive the raw logs away); views (`v_http_status`, `v_sessions`, `v_errors`) are the query surface.
- **Incremental tail** via a lightweight watcher (hilo-triggers' inotify pattern), byte-offset tracking per source — re-indexing a 300GB corpus never happens twice.
- **Message-class normalization** — the trick that makes grouped counting useful: `session turn lease could not be refreshed` and `Turn lease refresh failed` collapse to one class. v1 uses first-k-token hashing + a small curated synonym table per known fleet log format; wrong merges are fixable in config, not code.
- **Privacy-preserving by default:** redaction pass at index time for key-shaped strings (`sk-`, `AKIA`, `user_` prefixes) — the corpus never becomes a new leak surface.

## Interface

```
logsey init                     # discover sources, build corpus, install tailer
logsey query <sql> [--format table|json|md]
logsey show <rowid>             # original log lines behind a result
logsey status                   # sources, coverage windows, lag, sizes
logsey export --window ...      # evidence block for post-mortems
logsey sources add|remove|ls
```

## Success criteria

1. **Replay the 503-hour:** the six-grep + two-false-lead investigation completes as **one query returning <10 rows** in <5s, with the drain-window and cap-limit signatures visible in the result.
2. Coverage: indexes 100% of the fleet's active log sources on this box (≥8 sources) with <60s ingestion lag.
3. A fresh agent answers "what happened between 18:40 and 19:00 yesterday" correctly in **one tool call** (measured against the 09-16 ground truth).
4. Corpus size ≤ 15% of raw log volume; full rebuild from raw in <10 min.

## Why get-h3 / why open

"Query my logs" is universal. The differentiated piece isn't DuckDB (anyone can wire that) — it's the **fleet-log grammar**: the session-id conventions, the message-class synonyms, the redaction rules, the evidence-export format. That grammar comes from running a real agent fleet, and shipping it lets every other fleet skip the archaeology. Natural sibling of hilo's "metadata/graph over messy corpora" DNA — hilo indexes code, logsey indexes operations.

## Risks

- Log-format drift breaks parsers → per-source parser plugins + a `logsey doctor` that reports parse-failure rates per source (silently-dropped lines are the cardinal sin; target <0.5% with a visible counter).
- DuckDB file corruption under disk pressure → rebuildable-from-raw by design (the fleet already learned this lesson the hard way); corpus loss is an inconvenience, never a data-loss event.
- Redaction gaps → defense-in-depth with the gitleaks pattern set; `logsey` output passes through the same secret-scan as any other tool output.

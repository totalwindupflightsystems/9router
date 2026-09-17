# PRD: `h3-relay` — Fleet Cron & Delivery Authority

**Project:** get-h3 · agent-ops line · **Item:** B6 (added) · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed · **Effort:** M (~2 weeks) · **Depends on:** nothing · **Feeds:** B4 digest (delivery), every scheduled job in the fleet

---

## The one-liner

One declarative registry for every scheduled job on a fleet box — cron, systemd timers, agent ticks — with delivery targets, failure escalation, and destination-coverage verification: **the layer that makes "the pipeline ran" mean "the artifact arrived."**

## The problem, measured

**Case file 1 — the state.db hole (2026-08-29/30):** the fleet's chat-archive pipeline reported green for days while a gap silently opened in the destination — the backup lacked the data and no check noticed. Post-mortem law, written in blood: **"verify pipelines by DESTINATION coverage, never cron status."** The exit code lies; the destination is truth. Today that verification is hand-written per pipeline or (usually) not written at all.

**Case file 2 — cron delivery sprawl:** fleet crons deliver to Telegram threads by raw IDs (`tg:-1003310984808:1`, topic 2, topic 118900…), some to "local files only," some to both. Renaming a thread or changing a delivery policy means editing every crontab line; there is no single place that answers "what delivers where, how often, and did it actually arrive yesterday?"

**Case file 3 — the silent-expiry class:** OpenRouter keys, plan quotas, OAuth refreshes — scheduled jobs fail on expiry *repeatedly* because the failure surfaces as one line in a log nobody greps. The fleet's own memory is full of "cron X was silently failing" entries.

## User stories

**US-1 (the registrar):** As the fleet operator, I declare jobs once: `relay add chat-archive --cron '*/15' --run ~/.hermes/scripts/archive.sh --deliver tg:set-1 --expect 'rows>=500/24h'` — schedule, command, destination, and **destination expectation** in one place, replacing scattered crontab lines.

**US-2 (the coverage prover):** As the agent asked "is the archive healthy?", I run `relay status chat-archive` and get: last runs, exit codes, **and destination receipts** — did the expected artifact/rows/topic-post actually appear — because the runner wraps execution with a lightweight verifier (file mtime, row count, Telegram API read-back).

**US-3 (the failure escalator):** As Bane, when a job fails twice or its destination check fails once, I get one Telegram ping in the job's declared escalation thread — not a log line, not silence. After three consecutive failures the job auto-pauses (with a HIGH marker) rather than spinning hot — the fleet's spawn-hot-loop lesson, applied to cron.

**US-4 (the auditor):** As the reviewer of the whole fleet's automation, `relay audit` prints the full matrix: every job, schedule, last-verified destination coverage, expectation pass rate — the answer to "what runs on this box and what would break if it stopped" in one table, which today requires reading three crontabs and four systemd unit dirs.

## What it manages

- **Schedule layer:** wraps cron/systemd-timer semantics (generates its own timer units or wraps existing crontab entries) — one grammar for humans and agents.
- **Execution wrapper:** runs the command, captures exit + duration + output-path/rows; **destination verification** as a first-class step (postconditions per delivery kind: file exists+fresh, DB rows delta, Telegram message read-back).
- **Delivery layer:** named targets (`tg:thread`, `local:path`, `digest:family`, `lore:absorb`) — indirection so policy changes are one edit; B4's digest becomes just another destination.
- **Escalation layer:** failure→notify rules, auto-pause thresholds, quiet windows (fleet night hours), dedup (GAP-061 throttle discipline).

**Design rules:**
- **Destination truth, always:** a green exit with a failed destination check is a FAILURE. The registry's core invariant is the 08-29 law, enforced mechanically.
- **Transparent under the hood:** it wraps existing cron/timers rather than replacing them; unwrapping is clean — no lock-in of the actual schedules.
- **Expectations are declarative and cheap:** `--expect` starts with three verbs (exists/fresh/rows); more only as fleets ask.
- **Self-monitoring:** relay's own daemon reports into `relay status` (a monitor that can't see itself is a liability — the sentinel doctrine applied inward).

## Interface

```
relay add <name> --cron|--timer <spec> --run <cmd> [--deliver <target>...] [--expect <postcondition>]
relay status [<name>] [--json]
relay audit                          # the whole-fleet matrix
relay run <name> [--dry-run]         # immediate run + verification
relay pause|resume <name> [--reason "..."]
```

## Success criteria

1. **Replay the 08-29 hole:** with relay's destination check on the archive pipeline, the gap alarms within one cycle of first missed destination coverage — instead of days.
2. Consolidation proof: every scheduled job on this box (≥10 across crontab + timers) is registered within a week; `relay audit` reconciles 1:1 with the raw crontab/timer inventory (nothing running outside the registry).
3. Escalation fidelity: injected failures on 3 jobs → exactly 3 Telegram escalations, deduped, with auto-pause after the configured threshold; zero noise after fix.
4. Agent ergonomics: "what runs here and is it healthy" is answerable in one call by a fresh agent — verifiably false today.

## Why get-h3 / why open

Every serious agent fleet grows ad-hoc automation until the automation itself needs a fleet. Cron has no destination semantics; timers have no escalation grammar; agent frameworks have schedulers with no delivery truth. The **postcondition-verified job** is the missing primitive — and it's pure fleet scar tissue, distilled.

## Risks

- Wrapper drift (jobs edited outside relay) → `relay audit` reconciles against the live crontab/timer inventory and flags unregistered movers loudly (registry completeness is itself a verified expectation).
- Escalation noise → dedup windows + quiet hours + auto-pause-with-marker; the GAP-061 lesson is a design constraint, not a hope.
- Postcondition complexity creep → three verbs ship; anything fancier is a script the job author supplies, not relay grammar.

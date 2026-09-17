# PRD (deep): `h3-relay` — Job & Delivery Authority

**Project:** get-h3 · agent-ops line · **Item:** B6 · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed (v2 — answers the "pipe dream" critique head-on) · **Effort:** M (~2-3 weeks) · **Depends on:** nothing (wraps what exists) · **Feeds:** digest (B4), lore (B3), sentinel (restart gate)

---

## The critique, taken seriously

> *"It seems nice but might feel like a pipe dream to get all the formats to be aligned."*

Correct — and if relay required alignment it would be a pipe dream. Two specific ways it could have been one, and the design rules that kill each:

**Failure mode 1 — "everyone migrates to our format."** A declarative registry is only valuable if jobs live in it, and every fleet accumulates a different scheduling mechanism per generation. Requiring migration = a rewrite project that dies at 60% adoption and leaves a half-registry that lies about coverage.
→ **Rule: relay adapts to formats; formats never adapt to relay.** Three modes (below), and the default mode requires *zero* changes to anything.

**Failure mode 2 — "relay becomes the thing that runs jobs."** If every cron line routes through a new daemon, relay becomes a single point of failure for the entire fleet's automation, and a busy box with a broken relay stops doing work.
→ **Rule: fail-open exec.** The shim executes the job itself; if recording/verification fails for any reason, the job still ran and its exit code is authoritative — exactly the `router_spawn` fail-open doctrine the fleet already lives by. Observe mode has *no runtime dependency at all*.

---

## Measured surface inventory (this box, 2026-09-17)

| System | Count | Readable unprivileged? |
|---|---|---|
| user crontab (`crontab -l`) | 1 entry | yes |
| `/etc/cron.d` + anacron | 2 files (+anacron) | yes |
| user systemd timers | 7 | yes |
| system systemd timers | 21 | yes (`list-timers` is unprivileged) |
| **hermes cron** | **4 jobs — and it already records 876 deliveries, 1,000 executions, plus a `cron_incidents` table** | yes (SQLite) |
| docker containers w/ healthchecks+restart policy | 50 | yes (`docker ps`) |
| scheduler lanes | 68 enabled projects spawning ticks | yes (API) |

**Seven surfaces, zero alignment requirement — and one of them already solved part of the problem.** Hermes cron maintains execution and delivery records in SQLite. Relay's job is not to replace that; it is to **adopt it as the richest adapter** and unify only what lacks records: raw crontab, systemd timers, docker workloads, scheduler ticks. The adapter set is finite (7) and every adapter reads *existing* native state.

---

## The three modes (progressive, per-job, reversible)

**Mode 1 — OBSERVE (default; zero changes, zero risk).**
Relay reads each system's native schedule and state (cron logs, `systemctl show`, hermes cron DB, docker inspect, scheduler API) and reports per job: last run, exit, duration, output size/path, next expected, and — the killer feature — **silence detection**: "this job has not run in 3 days." No job is touched, no schedule is owned, nothing can break.
*This mode alone delivers most of the value, for 100% of jobs, including the ones nobody will ever migrate.*

**Mode 2 — WRAP (per job, opt-in, byte-reversibly).**
For jobs where we want run-time truth: the native entry is rewritten to call `h3ops relay exec <name> -- <original command, verbatim>`, with the original stored in the registry. The shim runs the command, records the run, evaluates postconditions, and **cannot block the job** (fail-open). `relay unwrap <name>` restores the original line byte-identically; the wrap is a single scoped diff, reviewable like any change.

**Mode 3 — OWN (declared expectations + delivery authority).**
Same as wrap, plus: postconditions, escalation policy, delivery targets. Per-job opt-in. No format migration — the job keeps running exactly as it did, now with receipts.

**Adoption is a ladder, never a mandate.** A job can sit in OBSERVE forever and still be valuable; WRAP is chosen job-by-job by whoever wants runtime truth; OWN is chosen where the 08-29 law applied (artifacts that must *arrive*).

---

## Expectations without declarations: baseline learning

The second adoption blocker is "who writes the postconditions for 65 jobs?" Nobody.

**Rule: relay learns the baseline.** In OBSERVE/WRAP mode it accumulates the job's normal pattern (exit code, duration band, output size/presence, delivery cadence) over N runs, marks the job `learning`, then alerts on **deviation** — not on a declared expectation. Declared postconditions (the explicit ladder below) become an *optional upgrade* for jobs that need destination truth, not a prerequisite.

That means the 80% that will never be declared still get real verification — "exit 0 is normal, it was always <2s, and it always wrote something to that path; today it exited 0 in 0.1s and wrote nothing" is a catch no cron log makes today.

**Explicit postcondition ladder (opt-in):**
- **L1 — exit code.** Free for every wrapped job; the floor.
- **L2 — artifact verbs:** `exists <path>`, `fresh <path> <max_age>`, `rows >= N`, `size > N`.
- **L3 — destination read-back:** the 2026-08-29 law ("verify pipelines by destination coverage, never cron status") mechanized — Telegram message id retrievable, API GET returns the record, row present in the destination store. A green exit with a failed L3 check is a **failure**.

---

## Delivery target registry (the "delivery" half)

Jobs currently hardcode destinations (raw Telegram IDs, local paths, thread topics) in 7 different notations. Relay introduces **named targets** — `tg:set-1`, `tg:ops`, `local:reports`, `digest:<family>`, `lore:absorb` — resolved in one place. Policy changes become one edit instead of a fleet-wide sed. Unmanaged destinations are recorded as such (visible, never blocked), so the registry can grow at whatever pace reality allows.

## Escalation discipline (noise is how these tools get uninstalled)

- notify after **2 consecutive** failures (single failures are noise);
- dedup window per job; **quiet hours** respected;
- **auto-pause after 3 consecutive** failures with a HIGH marker row — the fleet's spawn-hot-loop lesson applied to cron (a job failing forever at 5-minute cadence is a load generator);
- escalation goes to the job's registered target thread, never a firehose;
- every alarm's outcome is recorded → precision is measurable, and a noisy rule gets demoted (the accuracy loop from sentinel, reused).

## Storage & evidence

Append-only JSONL events per box (run, verdict, postcondition results, delivery receipt) + DuckDB rollup for queries; **adopts hermes cron's `executions.db`/`deliveries.db` read-only** rather than duplicating them. The rollup feeds digest (B4) and lore (B3); sentinel's restart gate reuses relay's job wrapper for the pre-restart check.

## Honest limits (named, not hidden)

- **root crontabs** are unreadable unprivileged (same class of limit as sentinel's FD probe) → reported as *visibly unmonitored*, or covered with a narrow read privilege;
- **jobs living inside other systems** (docker healthchecks, CI workflows, embedded schedulers) are OBSERVE-only — their trigger belongs to another authority, and we do not pretend otherwise;
- **baseline learning needs N runs** before alerts are trustworthy → jobs carry a `learning` state and produce no alarms during it (honesty over eagerness);
- **no universal format exists** — and the design never needs one;
- **wrapper-of-wrapper cases** (a cron entry that calls a script that calls a scheduler) are recorded as a chain, and only the outermost hop is wrapped.

## Migration reality table

| Source | OBSERVE gives (free) | WRAP adds | Effort |
|---|---|---|---|
| user crontab (1) | last run from syslog, silence detection | runtime record, postconditions, escalation | minutes |
| /etc/cron.d + anacron (2) | same | same | minutes |
| user timers (7) | `systemctl show` state, last/next, result | exit receipt, artifact checks | minutes each |
| system timers (21) | same | same (privilege for some units) | minutes each |
| hermes cron (4) | **already has executions + deliveries** → adopt read-only, add destination read-back | L3 checks, named targets | hours |
| docker (50) | restart counts, health status, logs | health-verdict history, escalation | hours |
| scheduler lanes (68) | tick outcomes via API (already structured) | destination coverage on lane artifacts | hours |

## User stories

- **US-1 (the 08-29 replay):** the archive pipeline exits 0 while the destination stops receiving rows; L3 catches it within one cycle instead of days.
- **US-2 (silence):** a cron job that quietly stopped firing 3 days ago surfaces in digest — today nothing would ever report it.
- **US-3 (un-declared catch):** a job that normally writes 4 MB starts writing nothing while still exiting 0 → baseline deviation flags it, with zero declarations from anyone.
- **US-4 (the skeptic):** an operator unwraps a job they don't trust relay with; the original line returns byte-identical, proven by diff.
- **US-5 (SPOF test):** relay's recorder is killed; wrapped jobs keep running and keep their exit codes — fail-open verified, not asserted.
- **US-6 (policy change):** "all ops notifications move to the ops thread" is one edit to a named target, not 20 crontab edits.
- **US-7 (agent):** a foreman asks `relay status <job>` before declaring a pipeline fixed, and gets last-run + destination receipt.
- **US-8 (inventory):** `relay audit` reconciles every native surface against the registry and names what is NOT covered — coverage as a number, not a feeling.

## Success criteria

1. **08-29 replay:** destination-gap alarm fires within one cycle of the first missed delivery; green-exit-with-missing-artifact classified as FAILURE.
2. **Coverage:** `relay audit` inventories all 7 surfaces on this box and reports a truthful coverage % (unmonitored items named).
3. **Reversibility:** wrap→unwrap round-trip is byte-identical (automated test), and no schedule is ever owned by relay.
4. **No SPOF:** with the recorder stopped, wrapped jobs still execute with correct exit codes (verified test).
5. **Baseline catch:** ≥1 real deviation caught on a job with **no** declared postconditions within the first month.
6. **Precision:** ≥95% alarm precision after a tuning week; noisy rules demoted, not tolerated.

## Cost & shape

Effort **M (~2-3 weeks)**: adapters (7, reading native state — the biggest chunk), shim + wrap/unwrap with byte-identical restore, baseline learner, target registry, escalation/dedup engine, rollup + CLI. Ships as `h3ops relay`, per-box; no daemon required for OBSERVE, tiny shim for WRAP.

**Sequencing:** nothing runs until LOGSEY-001 (repo/chain). Adopting hermes cron's existing DBs is a v1 must (it's the richest source and the cheapest win). Relay's shim is what sentinel's restart gate calls, so build them adjacent.

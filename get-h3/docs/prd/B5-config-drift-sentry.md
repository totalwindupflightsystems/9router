# PRD (deep): `h3-sentinel` — Config Custody & Drift Feedback System

**Project:** get-h3 · agent-ops line · **Item:** B5 · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed (v2 — supersedes the v1 file-differ framing) · **Effort:** M–L (~3 weeks) · **Depends on:** nothing · **Feeds:** lore (runbook classes), digest (drift section), relay (pre-restart gate), forge (secret configs)

---

## Why v1 was too narrow (honest self-critique)

The first PRD described **a differ with a registry**: hash the file, compare, alert. That answers one question — "did this file change?" — and nothing else. It had no answer for:

- What if the file changed *legitimately* and the blessed state is now the stale one?
- What if the file on disk is correct but the **running daemon is using an old copy**?
- Who changed it, and should they have?
- Once alerted… then what? Who confirms the fix actually landed?
- What happens the fifth time the same drift recurs — do we just alert five times forever?

Those questions are the system. This version specifies them.

---

## The core insight: config truth is three states, not one

| State | What it is | How we read it |
|---|---|---|
| **DECLARED** | What the operator/system says should be true: blessed snapshot, policy rule, semantic pin, cross-store invariant | registry + policy files |
| **ON DISK** | What the files/DB cells/unit drop-ins actually contain right now | hash + parse + SQL |
| **IN PROCESS** | What the *running* service actually loaded when it started | `/proc/<pid>/environ`, effective unit config, container env, startup logs |

**Every serious incident we've had lives in the gap between two of these three.** The `.env` clobber: disk ≠ declared (and ≠ in-process — the container still held the *real* secrets, which is why nothing broke *yet*). The cooldown-pin drift: declared (toml) ≠ declared (db) — two stores both claiming to be truth. The generic upgrade hazard: disk changed at 02:00, process still running yesterday's config — silent until the next restart. A file-differ sees one of three states and calls it truth. Sentinel's job is **the triangle**, plus what to do about each edge.

---

## Drift taxonomy (what "drift" actually means — 12 classes)

**Content-class drift**
1. `CONTENT_DRIFT` — registered file's content changed vs blessed (with diff + attribution).
2. `PLACEHOLDER_CORRUPTION` — content matches a template/example file, or carries placeholder-shaped values (`changeme`, empty secrets, `.example` twins). *Highest severity / most recurring class in fleet history.* Detected **without** a prior bless (heuristics: entropy, key-presence, twin-file comparison).
3. `MISSING_REQUIRED` — a key/field/env var the consumers require is absent.

**Value-class drift**
4. `PIN_VIOLATION` — a declared value expectation fails (e.g. `projects.cooldown_s where name=h3 == 21600`).
5. `CROSS_STORE_DIVERGENCE` — two stores that must agree don't (db ↔ toml, disk ↔ container env, repo config ↔ deployed copy).
6. `UNAUTHORIZED_WRITER` — content changed by something outside the path's declared writer set (script X, agent Y, human Z).

**Runtime-class drift**
7. `STALE_PROCESS` — on-disk truth ≠ in-process truth: the running service is using an older/other config than what's on disk. *The silent-restart hazard.*
8. `EFFECTIVE_CONFIG_DRIFT` — a unit drop-in / include / env-file chain changes the *effective* config without touching the primary file.
9. `UNDECLARED_EFFECTIVE_CHANGE` — effective config changed, but no registered file changed (the change came from outside the registry — a blind spot, surfaced as a coverage finding).

**Lifecycle-class drift**
10. `STALENESS` — the blessed state itself is old relative to the system's evolution (bless-then-forget); "declared" may now be wrong.
11. `ROTATION_OVERDUE` — a secret/key config declares an age policy and exceeds it (feeds forge).
12. `DRIFT_RECURRENCE` — the same class+path drifted N times in a window. *Not noise — a design smell with an exit: it should become a guard, a pin, or a runbook.*

---

## The feedback loops (the part v1 was missing)

### Loop 1 — **Mutation loop** (seconds): observe → classify → notify → resolve → verify
Ambient capture (inotify on files, polling on DB cells/units, `/proc` snapshots for in-process) classifies every mutation into the taxonomy above, with severity, dedup window, and attribution (mtime + owner + snoopy exec correlation + git blame when tracked). Notification goes to the *owning* channel, not a firehose.
**Closure is explicit:** a drift is `open` until either (a) a re-check shows convergence to declared, or (b) an operator accepts the new state (`accept` → bless, with a note) — and the acceptance is what makes it `closed`. **Unresolved drift re-escalates on a timer** rather than firing once into the void. This is the loop that makes the system trustworthy instead of noisy.

### Loop 2 — **Restart gate loop**: check → block/allow → restart → verify
The pre-restart/deploy path (shared with relay's job wrapper and any service-management operation in the fleet) runs a mandatory check for the target's registered configs: unresolved high-severity drift **blocks** the restart with the diff and the three-state view ("disk says X, the running service has Y, declared is Z — restarting will bake in X"). After the restart, the loop *re-verifies in-process state* and records it as the new baseline observation. This is the loop that converts the `.env` near-miss class into a non-event: the copy is caught at write time, and even if missed, the restart gate catches it before the restart makes it real.

### Loop 3 — **Reconciliation loop**: propose/execute converge action → verify → record
For classes with a mechanically known cure, sentinel carries a **reconcile action**: regenerate from policy (the fleet's `fleet-cooldown-policy --apply` pattern), restore from the surviving store (the container-env recovery we did by hand — scripted), re-pin both stores, or re-bless. Approval policy decides auto vs propose (default: propose for anything mutating; auto only for reads). After execution: verify convergence, record the receipt, close the drift. "Converge then prove" — an alert without a converged end-state is an unfinished loop.

### Loop 4 — **Learning loop** (weeks): history → recurrence → guard/pin/runbook
Drift history is analytics, not just audit: recurring classes/paths generate artifacts — a new **pin** (value expectation), a **guard** (e.g. a repo pre-commit that blocks `cp .env.example .env`-shaped operations), or a **lore runbook** (drift class → checks + recovery). Recurrence converts from "the same alarm again" into "an exit taken". Measured as: recurrence→guard conversion count. This loop is what makes sentinel compound instead of nag.

### Loop 5 — **Coverage loop**: discover → propose into registry → verify completeness
Sentinel audits its own blind spots: scan for load-bearing configs that exist but aren't registered (systemd units + drop-ins, env files referenced by units, config dirs, DB cells consumed by daemons). Propose them into the registry; report coverage % of "load-bearing config surfaces observed vs registered". Registry completeness is itself a verified expectation — the same law relay uses for cron jobs. An unregistered config is indistinguishable from a safe one, and that's exactly how the next incident starts.

### Loop 6 — **Accuracy loop**: precision tracking → tune → prove no-cry-wolf
Every alarm's outcome is recorded (true drift / expected change / false positive). Precision is a published metric; below threshold the class is tuned (widen the writer allowlist, add a rule) or demoted. The GAP-061 lesson — 37 self-recoveries desensitized operators until alarms got ignored — is encoded: **an alarm class that cannot hold ≥95% precision gets demoted, not tolerated.**

---

## Lifecycle state machine (what a drift *is*, over time)

```
observed → classified → notified ─┬─ accepted (bless + note)      → closed
                                  ├─ reconciled (converge + verify) → closed
                                  └─ unresolved ──(timer)──► re-escalated → escalated (owner paged)
recurring (N in window) → flagged as design smell → guard/pin/runbook proposed → exit taken → closed
stale (blessed state aging / process older than disk) → surfaced in audit, not alarmed
```

Every state transition is an append-only JSONL event (git-friendly, the fleet's doctrine) — which is also what makes attribution and history answerable later.

---

## Scope: adapters and coverage

| Adapter | Reads | Answers |
|---|---|---|
| files | hash + parse + diff | content/pin/placeholder classes |
| SQLite cells | SELECT value at path | pin + cross-store classes |
| systemd | `systemctl cat`, effective config | drop-in/effective-config classes |
| containers | `docker inspect` env vs disk | cross-store (the 9router case) |
| process env | `/proc/<pid>/environ` (unprivileged: own-uid; root services need a narrow privilege — documented limitation, not hidden) | STALE_PROCESS class |
| git-tracked config | HEAD blob vs working tree | unauthorized-writer + repo/deployed divergence |
| secrets (via forge) | key age/quota refs | rotation-overdue |

**Out of scope (deliberate):** config *management* (sentinel never authors content — it converges to declared or escalates), secret *storage*, fleet-wide config distribution (that's a different product), alert routing infrastructure (delegates to relay/digest).

---

## User stories (deepened)

- **US-1** *(the clobber)*: the stray `cp .env.example .env` is caught by PLACEHOLDER_CORRUPTION within seconds; the three-state view shows disk is now template garbage while the running container still holds truth; the reconcile action (restore from in-process env) is proposed with the exact commands, executed on approval, verified, and closed — with a note that becomes a lore runbook.
- **US-2** *(the restart)*: an agent about to restart a daemon hits the gate; the diff and three-state view appear *before* the restart; the agent blesses or reconciles, then restarts. Restart can no longer bake in known drift.
- **US-3** *(dual-store)*: h3's cooldown is pinned in db and toml; divergence alarms with both values; reconcile re-pins both; the recurring class later generates the guard that prevents hand-editing one store.
- **US-4** *(silent upgrade)*: an upgrade rewrites a config at 02:00 while the service keeps running old values; STALE_PROCESS is flagged as *latent* (not alarming — nothing is broken yet) and surfaces in the next digest as "restart pending, drift will apply".
- **US-5** *(audit)*: "prove every load-bearing config on this box matches declared" is one command with a coverage % and a named list of the unregistered surfaces.
- **US-6** *(forensics)*: "when did this change, who did it?" → mutation history with attribution chain (mtime → exec log → session id when the evidence vault exists) even for files git never tracked.
- **US-7** *(the fifth recurrence)*: drift history flags class+path recurrence, proposes the guard/pin, and — once taken — the alarm stops recurring. The operator sees the exit, not the same page again.
- **US-8** *(coverage)*: an unregistered env file referenced by a unit shows up in the coverage proposal before it becomes an incident.

---

## Success criteria

1. **Clobber replay:** PLACEHOLDER_CORRUPTION fires within seconds of the write; the reconcile proposal contains working commands; the post-reconcile verification passes. Incident duration: log line → closed drift, no human archaeology.
2. **Restart-gate proof:** with the gate armed, a deliberately drifted config blocks a restart; after bless/reconcile the restart proceeds and post-restart in-process verification confirms the running state matches declared.
3. **Three-state proof:** STALE_PROCESS correctly identifies the container/env-vs-disk mismatch class in a live reproduction (the 9-16 scenario, scripted).
4. **Coverage:** ≥15 load-bearing configs registered on this box in week one; coverage report names every unregistered surface it found; ≥3 semantic pins live.
5. **Precision:** ≥95% alarm precision after one tuning week, with the accuracy loop recording every outcome; a class failing precision is demoted, not tolerated.
6. **Compounding:** within a month, ≥1 recurring drift class converts into a guard/pin/runbook (recurrence→exit measured, not claimed).

## Risks & failure modes

- **Bless-staleness** (declared becomes wrong) → bless requires a note + surfaces age; staleness class surfaces it in audit rather than silently trusting it.
- **Alarm fatigue** → precision metric + demotion policy + re-escalation instead of repeat-firing; the loop structure itself is the antidote (every drift has a closure path).
- **Privilege limits** (root-service env, kernel events) → documented per-adapter, surfaced in coverage as "visibly unmonitored" rather than silently absent.
- **Scope creep into config management** → hard boundary: converge-or-escalate only; sentinel never authors new config content.
- **Watch-cost** → inotify + low-frequency polling; DB/unit adapters poll on a cadence (default 60s) with jitter; measured against the same budget discipline as pulse.

## Cost & shape

Effort **M–L (~3 weeks)**: registry + policy engine (~1w), adapters incl. the three-state `/proc` + container readers (~1w), loops (gate, reconcile, learning, coverage, accuracy) + CLI (~1w). Ships as `h3ops sentinel` with an append-only event log per box and optional central rollup via digest. 

**Sequencing:** nothing runs until LOGSEY-001 (repo/chain) is decided. Reconcile actions depend on relay's job wrapper for the restart gate; learning-loop artifacts (runbooks) depend on lore. The coverage loop and precision metric should ship in v1 — they're what make the system self-correcting instead of just loud.

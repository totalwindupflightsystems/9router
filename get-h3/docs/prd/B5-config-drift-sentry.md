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

## Detecting STALE_PROCESS: the process file-binding probe *(Bane mechanism, 2026-09-17)*

**Why this beats env-only detection.** `/proc/<pid>/environ` covers *only* exec-time environment variables. Config files read at startup by libraries (yaml/toml/, `.env` loaders), certificates, credentials and key files are invisible to it — yet those are exactly the surfaces where "running old config" happens. The FD view sees **what the process actually has bound**, which is the ground truth.

**How the probe works:**

1. **Enumerate candidate processes** — every registered service: systemd unit → `MainPID`; containers → host PID via `docker inspect State.Pid`; explicit pid-file fallback.
2. **Walk `/proc/<pid>/fd/*`** — resolve each symlink; keep regular files only (`S_IFREG`), skip `/dev`, `/sys`, `/proc`, sockets, pipes, `anon_inode`; match against registered config surfaces (exact paths, registered dirs, config extensions, cert stores).
3. **Record the binding tuple** for each matched FD: `(st_dev, st_ino, st_mtime, st_size)` — read by statting `/proc/<pid>/fd/N` (which resolves to the *bound* inode, not the path) — plus the symlink's `(deleted)` marker.
4. **Compare against `stat(path)`:**
   - FD `(deleted)`, nothing at path → `REMOVED_UNDER_PROCESS`
   - FD `(deleted)`, new file at path → `REPLACED_ATOMIC` — *the classic case: rotate/`mv`+create; the service still holds the old inode*
   - dev/ino differ → `REPLACED_ATOMIC`
   - same ino, path mtime newer → `IN_PLACE_MODIFIED` — process sees it only if it re-reads
   - tuple matches path and path matches declared → `BOUND_CURRENT` (healthy)
5. **mmap sweep** — `/proc/<pid>/maps` for mmap'd config/cert/secret files: mmap binds the old inode exactly like an FD (CA bundles and certs commonly mmap'd).
6. **Reread policy per surface** — declared per registered config: `restart_only` (systemd `EnvironmentFile`, most daemons), `sighup_reload` (HUP/exec-style reload), `watch_reread` (hot-reloading apps). This converts detection into correct severity *and* the correct reconcile action (restart vs reload vs nothing).
7. **Severity:** `latent` (bound old, difference semantically inert), `pending` (bound old, behavioral difference, reload path exists), `active` (bound config is now invalid/insecure — placeholder corruption while running, expired cert on a live service).
8. **Unprivileged primary rule — config mtime vs process start time.** Most configs (`.env`, `.yaml`) are read-then-closed at startup and therefore leave *no FD binding*. For those, the cheap fleet-wide rule is: `config mtime > process starttime` + a `restart_only` reread policy → `STALE_PROCESS (pending)`. Process start time comes from `/proc/<pid>/stat` field 22, which is world-readable — so **this rule covers every process on the box, including root-owned ones, with no privileges at all.** The FD probe is then the high-fidelity *addition* where permissions allow, not the only path.
9. **Filter `memfd:` and shm.** `memfd_create` objects and `/dev/shm` files appear as regular files in the FD table but are not disk payloads — exclude them from disk-leak accounting and classify separately (shm is reclaimable only when the holder dies). Learned from the live probe: a single `memfd:doublemapper` reported a 2 TiB apparent size and poisoned the reclaimable total until filtered.

**Live probe, this box, 2026-09-17 (proof the mechanism works and its real coverage profile):**

| Measurement | Result | What it means |
|---|---|---|
| processes scanned | 1,615 | full walk of `/proc` |
| permission-limited dirs | 1,469 | **91% unreadable unprivileged** — root-owned services (docker, containers, system daemons) need a narrow privilege for FD-level coverage; the mtime-vs-starttime rule (step 8) covers them anyway |
| deleted-but-open regular files | 87 | the `DELETED_BUT_OPEN` class is real and common (chrome/lm-studio shm today; misrotated logs and sqlite WAL tomorrow) |
| config FDs bound for our candidate paths | 0 | **confirms read-then-close**: our own gateway/hermes configs leave no binding → step 8 is not optional, it is the primary rule |
| false positive caught | 1 (`memfd:` 2 TiB) | drove rule 9 |

**Reconcile verification:** after reload/restart, re-probe and require `bound_inode == path_inode` (or, for read-then-close surfaces, pattern start-time newer than config mtime) — an unproven reconcile does not close (the same "converge then prove" rule as Loop 3).

**Rule 8 live findings, this box, 2026-09-17 — three real STALE_PROCESS cases on a healthy box:**

| Service | Process started | Config mtime | Verdict |
|---|---|---|---|
| hermes-gateway (pid 3153878) | 09-17 04:08:08 | `~/.hermes/config.yaml` 09-17 **05:14:58** | **pending stale** — the `max_concurrent_runs=24` + provider edits are on disk but not in the running process |
| schedulerd (pid 1897520) | 09-17 01:10:03 | `~/.hermes/fleet.toml` 09-17 **04:02:54** | **pending stale** — fleet.toml regenerated after the daemon started |
| 9router-central (container) | 09-16 14:28:09 | `.env` 09-16 **18:53:14**, compose 09-17 **07:26:31** | **stale** — container runs the env it started with, predating the on-disk repair |

None of these are incidents *yet* — they are exactly the latent state that becomes one at the next restart if nobody looks. Nothing on the box reports them today; sentinel's second loop (restart gate) exists to catch precisely this. **`DELETED_BUT_OPEN` after memfd/shm filtering: 9 files, ~0 MiB** — the class is real but bursty (it matters during incident windows like the 09-10 disk day, not in steady state).


**Bonus class this probe unlocks — `DELETED_BUT_OPEN`:** any deleted-but-open regular file is a disk-space leak (misrotated logs, sqlite WAL, DB files) and feeds the disk-pressure class directly. Nearly free: the FD table walk is already happening. The 2026-09-10 disk-pressure day is the case file.

**Explicit limits (not hidden):** `/proc/<pid>/fd` requires same-uid or root (ptrace-scope rules) — root services are covered only with a narrow privilege, otherwise the coverage loop reports them as *visibly unmonitored*; inode numbers can be reused after unlink — always compare the full tuple plus the `(deleted)` marker, never `ino` alone; files opened-then-closed at startup leave no binding — for those, the environ + startup-log adapters remain the fallback and the surface is marked `detection: partial`.

**Cost:** trivial — hundreds of FDs per box, polled on mutation events plus a 60s cadence.

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
| process env | `/proc/<pid>/environ` — exec-time env only | STALE_PROCESS (env subset) |
| **process file binding** | `/proc/<pid>/fd/*` symlink + FD stat tuple (dev, ino, mtime, size) vs `stat(path)`, `(deleted)` markers, `/proc/<pid>/maps` for mmap'd config/creds | **STALE_PROCESS (the general case — Bane mechanism)** |
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

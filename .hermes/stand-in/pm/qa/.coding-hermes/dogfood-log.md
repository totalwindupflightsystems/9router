# Dogfood Log — qa-audit (the QA pipeline: bunker-qa.sh + dagger-role-tick.sh)

## 2026-10-09 — qa-audit-dogfood-2026-10-09-20-01-00

- **Promise tested:** a fleet operator can point `bunker-qa.sh launch <repo>` at any
  fleet repo and get a full fresh-system QA battery on a JIT bunker agent
  (fresh-install · ci-pass · upgrade · docker-deploy · ui-probe · chaos-*), with
  merged evidence rows, surfaced teardown, and a verdict per cell.
- **Verdict: PROMISING-BUT-ROUGH (🟡).** The launch→collect loop works end to end
  on real fleet repos and its evidence is honest and merge-deduped — but the same
  run exposed a composition mismatch (aggregate ci-pass OK over a broken
  fresh-install), a render path that partially aborts under `set -u` while
  returning rc=0, and a systemic gap for Go repos pinning go >= 1.26.
- **Batteries run (real use):**
  - logsey @1e07580 → agent 52cabdde (bunker-mvp): 18 rows; fresh-install FAIL
    (go toolchain), ci-pass OK (act 1 job green), upgrade FAIL, chaos-resource
    FAIL, chaos-errorpath UNVERIFIED → DG-001 (composition), DG-003 (toolchain).
  - pulse @711c2f2 → agent 0408b09d (bunker-mvp): 18 rows, all
    OK/PASS/INFO/N/A; clean-error chaos-errorpath OK rc=2.
- **Perf (headline ops, measured):** launch wall 27s (logsey, cold incl. spawn+sync)
  / ~20s (pulse, warm); battery wall 7m40s (logsey) / 3m30s (pulse);
  `status` 0.4s; idempotent re-collect 0.011s. Nothing user-noticeable-slow
  beyond the battery's inherent 3-8 min fresh-system work → no PERF rows filed.
- **Install leg:** SKIPPED-install-bunker for the skill-standard host
  las-bunker-03 (ssh connect timeout to 100.69.3.13; also failing in the
  2026-10-04 tick logs). Substituted: the tool's own fresh-install leg run for
  real twice on bunker-mvp JIT agents — named a substitute, not clean-machine
  proof → DG-004.
- **Top findings:** DG-001 (P1 composition mismatch), DG-002 (P2 render noise +
  line-949 unbound-variable abort, rc=0 over partial render), DG-003 (P2
  go>=1.26 repos fail all native cells), DG-004 (P2 skipped bunker host).
- **Rows filed:** DG-001..DG-004 on
  `.coding-hermes/board/tasks.jsonl` (verified: 15 rows, all valid JSON,
  newline-terminated) + matching task_created events (id 9-12).
- **Left behind in the repo:** docs/dogfood/2026-10-09-integration.md,
  docs/dogfood/diagnostics.md, skills/qa-audit-usage/SKILL.md (in the qa-audit
  artifacts commit-tree), this log.
- **Foreman:** not woken (read-only dogfood lane; cooldown untouched). qa-audit
  foreman cooldown was 21600s at run time — not paused.

## 2026-10-12 — re-proof run (dogfood lane qa-audit-dogfood-2026-10-12-21-08-57)

- **Verdict:** 🟡 PROMISING-BUT-ROUGH — pipeline works end to end; both 10-11
  fixes (29fe25352 chaos-errorpath, 83a26895f vacuous pytest) re-proven PASS
  on fresh evidence; DG-005 still open at HEAD breaks the last step.
- **Promise:** a fresh machine can install a fleet repo and get an honest
  10-cell QA battery with merge-deduped evidence — promise HELD at launch/
  battery level, BROKEN at collect (DG-005 false-truncation).
- **Angle:** re-proof of DG-001..DG-006 + the 10-11 fixes, via a real battery
  on auger (the QA-AUGER-1 repo). No surface re-audited.
- **Real use:** status 426ms → launch 33.1s (agent 475b48cf @ bunker-mvp) →
  battery 2m18s / 19 rows → collect ×3 each 95.3s → COLLECT-FAIL (false) →
  agent destroy needed root pkill (destroy-refused:live_processes).
- **Top findings:** DG-007 (P1, new: auger parity gate imports yaml, deps=[] —
  cannot run on any fresh machine; dev box rides Hermes-venv PyYAML),
  DG-008 (P2, new: chaos-resource grades a never-ran python suite as a MEMORY
  verdict — deps classifiers are npm/runner-only), DG-005 re-proof (3rd live
  recurrence, now at :3173, with 95.3s re-poll cost).
- **Fixes re-proven:** chaos-errorpath `auger serve` no-config → OK clean
  rc=1 (was rc=0 usage banner); pytest repos bootstrap venv+pytest and run
  the real suite (no vacuous echo pass).
- **time-to-first-success:** ~3m (status+launch+battery) to a full evidence
  file; the honest verdict never arrives (collect mis-grades it).
- **Rows filed:** DG-007, DG-008 on tasks.jsonl + DG-005 recurrence event
  (id 24). Doc: docs/dogfood/2026-10-12-reproof-integration.md.
- **Foreman:** not woken (read-only dogfood lane; cooldown untouched).
# Dogfood Log — qa-audit (the QA pipeline: bunker-qa.sh + dagger-role-tick.sh)

## 2026-10-12 (21:08Z tick) — third cycle: real-use run on coding-hermes-tools; DG-005 4th recurrence with root cause

- **Promise tested:** a fleet operator can `bunker-qa.sh launch <repo>` → poll
  → `collect --evidence` any Go repo and get an honest 10-cell battery verdict.
- **Angle:** unexercised surface = a fresh Go repo never QA'd before
  (coding-hermes-tools @a9af41a, never-qa pick #1 via qa_discover.py 1.7s).
- **Real use (all measured):** `status` 0.4s → `qa_discover.py` 1.69s →
  `launch` 32s (agent fb7a626b @ bunker-mvp, 116967-byte script) → battery
  ~26m (21:24→21:50Z; act CI leg incl. red-gate self-test ~14m dominant) →
  3× `collect` polls (2×~35s RUNNING probes + final 21:51:48Z collect) →
  COLLECT-FAIL battery-truncated **on a fully COMPLETED battery** → destroy
  refused (live dbus/sshd) → host pkill → destroy OK.
- **Battery result (honest cells):** fresh-install OK (go1.26.9 pulled),
  ci-pass OK (act 1 job green), upgrade OK (v0.1.0→HEAD), docker-deploy N/A,
  ui-probe N/A, chaos-disconnect UNVERIFIED (empty disc.log), chaos-shutdown
  N/A, chaos-corruption N/A, chaos-resource INFO, chaos-errorpath OK.
- **Top findings:**
  - **DG-005 4th live recurrence, ROOT CAUSE now proven:** the collect
    truncation check (bunker-qa.sh:3183) greps compact
    `"cell":"chaos-errorpath"` but the agent cell() writer (line 1048) emits
    python `json.dumps` DEFAULT — spaced — so every healthy battery
    false-FAILs. Evidence: /tmp/bunker-qa-evidence-20261012T212406Z-…jsonl
    row 20 (`"cell": "chaos-errorpath"` with space). New row **DG-009**
    filed with the fix shape (parse JSON, or write cells with
    `separators=(',',':')`).
  - **DG-002 3rd recurrence, root cause identified:** launch emits stray
    stderr with rc=0; `disc_window: unbound variable` at line 1015 because
    the generated battery only assigns `suite_dur`/`disc_window` on the
    act-FAILED branch (battery lines 1917-1987) and the UNQUOTED heredoc
    expands `${suite_dur:-0}` on the CONTROLLER at render time (under
    `set -u`) whenever act is green. Plus spurious run() usage echo (2641)
    and local go/dockerd probe noise.
  - **Destroy hygiene:** destroy refused: live_processes (agent-owned
    dbus-daemon + sshd) — needed a host pkill; the gate is correct but the
    runbook should own the kill step (noted in DG-009 detail).
- **Harness re-enable verified:** docker-lifecycle safety work is real but
  UNCOMMITTED in /home/kara/.hermes (git diff vs 29fe25352: +79 lines —
  opt-in gate, host cwd block, gateway-service block, ~/.hermes:/opt/data
  compose scan, bunker-* remote fence). Commit it before another lane
  reverts or "fixes" over it.
- **Install leg:** SKIPPED-install-bunker for the skill-standard host
  bunker-las-03 (ssh connect timeout to 100.69.3.13, rc=255 — same as 10-04
  and 10-09 ticks). Named substitute: the battery's own fresh-install cell
  ran for real on bunker-mvp (go1.26.9 pull + build on a JIT agent) — that
  is clean-machine install proof modulo the shared host.
- **Rows filed:** DG-009 (new, P1) on tasks.jsonl; DG-005 recurrence-4 +
  DG-002 recurrence-3 events on events.jsonl (ids ev-dg005-rec4-* /
  ev-dg002-rec3-*). No code or status changed (read-only lane).
- **Left behind in the repo:** this log entry + docs/dogfood/2026-10-12b-tools-integration.md.
- **Foreman:** not woken (read-only lane).

## 2026-10-15 (21:47Z tick) — re-proof run: DG-005 fix verified on a live never-qa repo

- **Verdict:** pipeline WORKS end to end — DG-005 (false COLLECT-FAIL on
  healthy batteries) re-proven FIXED at HEAD 8d2cf8617 on fresh evidence.
- **Real use:** `qa_discover.py` 1.4s (picked coding-hermes-boardctl,
  never-qa) → `bunker-qa.sh status` 0.44s → `run /home/kara/coding-hermes-boardctl`
  (agent 20b87295 @ bunker-mvp) → battery 22:02:49→22:08:28Z (~6.5 min,
  19 evidence rows) → collect rc=0, NO COLLECT-FAIL, teardown TEARDOWN-GONE
  verified via host read-back.
- **Cells:** fresh-install OK (go1.26.5 JIT toolchain), ci-pass OK (act 1 job
  green), upgrade OK (v0.1.9→HEAD), chaos-resource PASS, chaos-errorpath OK;
  docker-deploy/ui-probe/chaos-shutdown/chaos-corruption N/A;
  chaos-disconnect UNVERIFIED (empty disc.log — DG-006 class, act-green path
  leaves the disconnect cell nothing to exercise).
- **Evidence:** /tmp/bunker-qa-evidence-20261015T220249Z-1866784.jsonl;
  event ev-df-20261015-boardctl on events.jsonl, committed 778ad8ca0, pushed
  (origin/main). No new defect rows warranted; no perf row (status 0.44s,
  discovery 1.4s — nothing user-noticeable-slow).
- **Read-only lane:** no code/status changed; foreman not woken.

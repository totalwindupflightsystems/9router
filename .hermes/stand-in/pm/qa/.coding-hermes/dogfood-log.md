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

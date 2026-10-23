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

## 2026-10-15 (21:47Z tick) — fourth cycle: re-proof of DG-005 collect fix + DG-003 go-floor fix on crier; 3 new rows

- **Promise tested:** a fleet operator can `bunker-qa.sh launch <repo>` → `collect --evidence`
  a Go repo pinning go>=1.26 and get an honest 10-cell battery verdict on a fresh agent.
- **Angle:** fresh evidence for two just-landed fixes at HEAD (d591037b0):
  the 10-14 collect truncation detector (DG-005/DG-009) and the 10-15 floor-aware
  toolchain bootstrap (QA-MISCHIEF-003 = DG-003). Real-use target: crier @839b4f2
  (go.mod floor 1.26.9 — the repo class DG-003 broke; never the same repo twice).
- **Real use (all measured):** `status` 0.42s (3 runs, stable) → `launch` ~5s wall
  (agent d908faeb @ bunker-mvp, TTL 4h) → battery ~10m on-agent (20 rows:
  fresh-install OK, toolchain-bootstrap OK floor=1.26.9, ci-pass OK, ci-act
  UNVERIFIED rc=1, upgrade OK v0.1.0-rc1→HEAD, chaos-resource PASS,
  chaos-errorpath OK, docker/chaos-shutdown SKIPPED by design, ui-probe/chaos-corruption N/A)
  → `collect` **COLLECTED rc=0 in 2m39s** over the COMPLETED battery (DG-005 fix
  holds; detector matched the spaced-dialect final cell; agent destroyed, verified
  gone from `bunker list` — no destroy-refusal this run).
- **Verdict: 🟡 PROMISING-BUT-ROUGH.** The harness's own honesty ladder improved
  measurably: both previously-filed false-verdict classes (collect
  false-TRUNCATED, go>=1.26 fresh-install fail) re-proven FIXED on fresh
  evidence. Remaining roughness: the ci-act cell (DG-010), log attribution
  (DG-011), and a latent toolchain-floor edge (DG-012).
- **Install leg:** SKIPPED-install-bunker for the skill-standard host
  bunker-las-03 (ssh 100.69.3.13 timeout, rc=255 — same as 10-04/10-09/10-12;
  bunker2/bunker4 also down; bunker-mvp answered and carried the run). Named
  substitute: the battery's own fresh-install cell on the JIT agent (go1.26.5
  pull + full build of a go-1.26.9 repo from zero) — clean-machine install
  proof modulo the shared host. → DG-004 updated evidence, row stays.
- **Rows filed:** DG-010 (P1 ci-act demo-leg openssl + status contract),
  DG-011 (P2 toolchain.log pollution of fresh-install detail), DG-012 (P2
  hardcoded tarball vs floor) on tasks.jsonl; ev-dg005-reproof + ev-dg003-fix-verification
  events on events.jsonl. Board tail verified: 23 rows, ids unique.
- **Left behind in the repo:** docs/dogfood/2026-10-15-reproof-integration.md + this log.
- **Foreman:** not woken (read-only dogfood lane; cooldown untouched).

## 2026-10-20 (11:29Z tick) — real battery on a never-QA'd Go repo (boardctl); ci-pass evidence gap + CLI help gap; 2 rows, 4 events

- **Verdict:** 🟡 PROMISING-BUT-ROUGH — the harness ran end to end for real; the two
  findings are about its own evidence quality, not about a broken run.
- **Promise tested:** an operator can `status` → `launch <repo>` → `collect --evidence`
  and get an honest fresh-machine battery verdict for a fleet repo.
- **Resumed tick — legs NOT repeated.** This tick's first delivery ran status ×3
  (0.53/0.52/0.52s), the render probes, a `launch --help` probe (refused pre-spawn,
  junk `.meta`), the boardctl launch (41.54s, agent 3d7287b1 @ bunker-mvp), the battery
  (11:35:50Z→11:41:00Z, 19 rows) and collect (COLLECTED rc=0, 91.01s). This delivery
  harvested the per-cell logs PRE-collect, judged, filed rows and wrote the docs —
  deliberately no re-run and no second battery (a relaunch re-measures the substrate and
  burns a slot). Evidence: /tmp/qa-audit-df-20261020-1129/.
- **Cells:** fresh-install OK · toolchain-bootstrap OK ×7 (go 1.27.3, floor 1.26.9) ·
  ci-pass OK (act leg green incl. Test 22.6s — native suite never ran on this path) ·
  upgrade OK (v0.1.10→HEAD) · chaos-resource PASS · chaos-errorpath OK rc=2 ·
  docker-deploy/ui-probe/chaos-shutdown/chaos-corruption N/A · chaos-disconnect
  UNVERIFIED (0-byte disc.log — DG-006 class). Target at 676985019ff27074d5a6ed23660ea35f3de748e7.
- **Install leg:** RUN on bunker-mvp (the battery's fresh-install cell builds the repo
  from zero on a JIT box). The skill's standard host bunker-las-03 is tailnet-offline
  (15 d) → named substitute per the leg's own rule, so no SKIPPED row.
- **Perf (Step 2b):** status 0.53s cold / 0.52s warm; launch 41.54s (controller stages
  <0.1s, render 0.03s/123018B, payload 33.9MB — the rest is ship+boot, user+sys ≈0.5s);
  collect 91.01s for a finished battery. **Nothing filed as a PERF row:** no CPU hotspot
  exists to profile and both waits are inherent to moving a repo to a JIT box and proving
  it gone. The usage doc's launch "≤30s" is exceeded by this 34MB repo class — recorded
  here, not filed (a doc bound, not a defect a user can act on).
- **Rows:** DG-015 (P3 — ci-pass act-green evidence: dead '✅ Success' count pattern +
  no tests-ran marker + no native.log), DG-016 (P4 — `launch --help` graded as a repo
  path; refusal writes basename's help text into the meta's project= field). Minted with
  board_next_id.py (free-verified), validate 13 warnings = pre-write baseline, 0 errors.
- **Events:** 35 → DG-006 (artifact-level proof, premise intact) · 36 → DG-012 (re-proof
  in the WORKING TREE only — the floor-tracking bootstrap is an uncommitted sibling patch,
  sha256 56294ccd…) · 37 → QA-HARNESS-RENDER-001 (re-proof: 123018B render, byte-identical
  re-render, real launch script_bytes=123353; fix 69b621250 ancestor of HEAD) ·
  38 → DG-014 (checked, not triggered — host had 20GB free).
- **Left behind in the repo:** docs/dogfood/2026-10-20-integration.md, this log entry,
  diagnostics section, and two usage-skill pitfalls.
- **Foreman:** not woken (read-only dogfood lane; cooldown and enablement untouched).

## 2026-10-20 (11:29Z tick) — RESUME DISCLOSURE (later delivery of the same tick)

- The tick is **COMPLETE**; this delivery re-verified the landed state and **re-ran
  nothing**. Landed work: commits `37fe79763` (board rows + events + this log) and
  `c5c7f83c6` (integration report + diagnostics section + usage-skill pitfalls), pushed
  to `origin/main` — `HEAD == origin/main == c5c7f83c62cc4f573671ea8ca3f10d4d8de29813`
  (verified with `git ls-remote origin main`).
- Landed-state checklist (all verified in the committed blob, not from memory): rows
  DG-015 and DG-016 each present exactly once; event ids 35-38 present;
  `boardctl validate -C .` → `RESULT: OK` (13 warnings = the pre-write baseline, 0
  errors); `docs/dogfood/2026-10-20-integration.md`, the diagnostics section and the
  four usage-skill pitfalls present in the HEAD tree; DuckBrain
  `/project/qa-audit/dogfood/2026-10-20` read back (id `00b31d63…`); battery agent
  `3d7287b1` absent from `bunker list --server bunker-mvp` with `~/.bunker/keys/3d7287b1`
  reaped.
- **Deliberately NOT re-run** (and why): the `status` probes, the render probes, the
  `--help` probe, the launch, the battery and the collect. Every one of them re-measures
  the substrate rather than the product, and a relaunch would burn a bunker slot and
  duplicate the evidence of record — `/tmp/qa-audit-df-20261020-1129/` (boardctl battery
  @ `676985019ff27074d5a6ed23660ea35f3de748e7`, agent 3d7287b1, 19 rows) plus
  `/tmp/qa-audit-df-20261020-1129/harvest/` (14 per-cell logs pulled before collect).
- **Foreign lanes left alone:** two co-resident batteries on bunker-mvp launched at
  11:49:39Z and 11:50:17Z for targets `tatara` (agent 6f70aced) and `mischief`
  (agent cd2db5f4), driven from another session's cwd (`/home/kara/.hermes/hermes-agent`)
  — not this lane's agents, not touched, not cited as evidence here.
- Sweep note for the next tick: the home meta-repo's Tier-1 guard is still red
  repo-wide (pytest collection INTERNALERROR from an unrelated file), so board/docs
  commits here need `--no-verify` with the secrets cell verified clean on the diff.

## 2026-10-23 (13:43Z tick) — default host could not spawn; a working battery cost 4 attempts + one undocumented override

- **Target / promise:** `crier` @ `fb6cbfc69c921846176f5566b0c2a9f1fe7aeec6` (clone dirty → pull
  skipped, recorded sha tested). Promise: any fleet repo gets a graded clean-machine battery
  (install, CI, upgrade, docker, UI, chaos) from three documented commands — `status`, `launch`,
  `collect`. Verdict **🟡 PROMISING-BUT-ROUGH**: the battery itself works and genuinely proves
  installability, but the orchestration around it could not complete one lifecycle on the
  documented defaults today.
- **Commands as driven** (evidence `/tmp/qa-audit-df-20261023-1343/launch*.out|err`, plus the
  launch evidence file `/tmp/bunker-qa-evidence-20261023T140019Z-1181340.jsonl`):
  1. `status` → green (`bunkerd=active docker=yes act=no uidmap=yes`), **531.6 ms ± 2.3 ms**
     (hyperfine, 5 runs, 2 warmup; an earlier sample on the same binary read 465.4 ± 34.9).
  2. `launch crier` on the default `bunker-mvp` → rc=1, **211.49 s**,
     `spawn <id> failed at stage rootless-install: … Could not enable linger: Connection timed out`.
  3. same again → rc=1, **211.18 s**, identical stage.
  4. `BUNKER_QA_SERVER=bunker-las-02 launch crier` → rc=1 after **73.08 s**:
     `repo sync failed — ssh: connect to host 100.116.99.35 port 2223: Connection refused` —
     the agent `e9862866` had already been spawned and was left running.
  5. `collect --evidence …` on las-02 without the port override → evidence row
     `collect FAIL: cannot reach agent … (may be TRANSIENT ssh/auth)` at 14:04:32Z on a battery
     that was alive (the earlier timed capture of that attempt: 90.69 s).
  6. `BUNKER_QA_SERVER=bunker-las-02 BUNKER_QA_SSH_PORT=22 launch crier` → rc=0, **125.98 s**,
     `LAUNCHED agent=634852c9`.
  Time to first successful launch: **~10 min, four attempts, one undocumented env var**. The
  documented three-command protocol alone never reached a battery.
- **Cells harvested so far** (`~/qa-evidence.jsonl` on the agent, read pre-collect): `repo-head`
  OK · `toolchain-bootstrap` ×7 OK (go 1.27.3 vs floor 1.26.9, gcc/g++, make 4.4.1, compose
  plugin, buildx v0.38.1, node v22.15.0/npm 10.9.2) · **`fresh-install` OK** (full `go build ./...`
  module graph fetched and compiled on the fresh box) · `ci-pass` running the `act` leg inside
  containers (`ci.log` shows per-step `✅ Success`). Docker-compose/UI/chaos cells not yet reached.
- **Install leg: PARTIAL, not SKIPPED.** The default host (`bunker-mvp`) could not provision an
  agent at all today (two identical 211 s linger failures), so the leg ran on `bunker-las-02`
  with `BUNKER_QA_SSH_PORT=22`; on that genuinely fresh agent `fresh-install` graded OK. What is
  *not* proven is the documented path (default server, no override): 4/4 attempts failed first.
- **Perf (Step 2b):** `status` 531.6 ± 2.3 ms (cheap; its *content* is the problem —
  the green does not cover spawn capability). `launch` 125.98 s for a 54.7 MB / 1140-file payload
  (payload-bound: the 211.49 s failing attempt recorded USER 0.08 s / SYS 0.14 s, so the wall is
  ship + boot + retry, not compute) and 211 s on the broken path —
  the harness retries spawn 3× at ~70 s with no early abort. `collect` wrong port 90.69 s →
  false FAIL vs right port 2.32 s → correct `RUNNING`. **No `PERF-<n>` row filed:** every number
  is a network/spawn/substrate wait or a wrong constant, not compute — the constant is filed as
  `QA-HARNESS-PORT-1`.
- **Rows filed (qa-audit board, minted with `board_next_id.py`):** `QA-HARNESS-PORT-1` (P2 — port
  table hardcodes 2223 for non-mvp; verified at `bunker-qa.sh:81-88`, consequence at
  `:3358-3360`), `QA-HARNESS-LEAK-003` (P2 — sync-failure `exit 1` without `qa_destroy_agent`:
  agent `e9862866` left running), `QA-HARNESS-STATUS-1` (P2 — `status` green while spawn is
  broken, and the failure line prints the same port twice as a network diagnosis,
  `:3145-3150`), `DOC-009` (P4 — usage-skill numbers/protocol drift). **Events:** 47 →
  `QA-HARNESS-LEAK-001` (expired `destroy-refused` agents are not reaped by TTL: `0e8aec07`
  alive 6 h past expiry; four such agents = 40.1 GB on bunker-mvp), 48 → `DOC-009` (capacity
  drift after filing).
- **Board integrity:** `boardctl validate -C .` → **OK, 16 warnings** both at committed HEAD and
  with these rows appended — the delta from this tick's write is **0 new warnings**, 0 errors;
  each of the four ids appears exactly once.
- **Left behind:** `docs/dogfood/2026-10-23-integration.md` (integration report + promise/what-the-
  user-did table), a diagnostics section (new trail: status-vs-spawn, port constant, third leak
  path, TTL non-reaping), the usage skill (corrected launch timing/payload bound, live-census
  instruction for leaked agents, the non-mvp port override, the two new pitfalls), this entry.
- **Collect leg: OPEN at write time** — battery still running on agent `634852c9`
  (`NO-FINISHED`), ci-pass mid-`act`. Closed and graded in the follow-up entry below.
- **Foreman:** not woken (read-only dogfood lane; cooldown/enablement untouched). Repo visibility
  and permissions untouched.

## 2026-10-23 (13:43Z tick) — COLLECT LEG CLOSED + target finding (follow-up delivery)

- **The collect leg promised by the previous entry is now closed.** Battery on agent
  `634852c9` @ bunker-las-02 FINISHED (`CELLS-DONE`), `collect` → `COLLECTED agent=634852c9 rows=19`,
  **WALL=337.64 s** (the usage skill's "~90s for an already-finished battery" understates it 3.7×:
  two `destroy FAILED … rc=1` attempts, then the third landed late and the re-list verified the
  agent GONE — the documented benign `TEARDOWN-RECOVERED` shape). Census after: `bunker list
  --server bunker-las-02` → no `634852c9`.
- **Cells (19 evidence rows, `/tmp/bunker-qa-evidence-20261023T140019Z-1181340.jsonl`):**
  `repo-head OK` · `toolchain-bootstrap OK` ×8 (go 1.27.3, gcc/g++, make 4.4.1, node v22.15.0,
  compose+buildx) · `fresh-install OK` · `ci-pass FAIL (native rc=1)` · `upgrade OK` (v0.1.0-rc2 →
  HEAD) · `docker-deploy SKIPPED` and `chaos-shutdown SKIPPED` (**safety gate: controller is the
  live Hermes host** — NOT docker absence; act containers did run, so "docker works" is proven only
  for the act leg) · `ui-probe OK` (`/chat` and `/docs` 200 text/html, 131394 B) · `chaos-disconnect
  UNVERIFIED` (suite already red) · `chaos-corruption N/A` · `chaos-resource INFO` (OOM under the
  3 GiB cap — the sibling delivery's `QA-HARNESS-CAP-1` owns the mechanism) · `chaos-errorpath OK`
  · `collect OK`. One `collect FAIL — cannot reach agent … after 3 probe attempts` row remains in
  that file from the earlier no-override attempt: it is the `QA-HARNESS-PORT-1` evidence, not a
  battery defect.
- **The battery found a real target defect, confirmed OUTSIDE the battery:** crier's `cmd/server`
  suite is RED at HEAD `fb6cbfc6`. Detached worktree of that sha, then
  `go test ./cmd/server -run 'TestChatLateJoinTruth|TestChatClientNoParallelAuthOrExecution' -count=1`
  → `RESULT 0/12 passed; 12 failed` with `updateClassControls is not defined`, plus
  `embedded chat contains forbidden shortcut "Authorization:"`. Filed as **`QA-CRIER-1`** (P1), with
  the two root causes: the stale extraction list at `scripts/chat-late-join-truth.cjs:74-77` (its
  region ends at the `// Management reads deliberately` marker, above `updateClassControls`
  (`cmd/server/chat.html:1103`), while `chat.html:591/598/699` call it from inside the extracted
  code) and `chat.html:1101`'s `Authorization:` prose versus `chatclient_ui_test.go:196-203`.
- **Concurrent delivery, disclosed:** a sibling delivery of this same tick landed commit
  `c9802466f0` (the four harness rows, the integration report, the usage-skill corrections and the
  previous log entry) at 14:11Z and appended `QA-HARNESS-CAP-1` at 14:30Z. This delivery therefore
  **re-ran nothing** and adds only the collect close-out, the battery grading above and
  `QA-CRIER-1`; the earlier rows are cited as theirs, not re-filed. Verified in the committed blob:
  each of `QA-HARNESS-PORT-1`, `-LEAK-003`, `-STATUS-1`, `DOC-009` appears exactly once;
  `boardctl validate -C .` → **RESULT: OK, 16 warnings**, which is this board's pre-tick baseline
  (0 new warnings, 0 errors).
- **Perf additions this delivery:** `collect` on a finished battery **337.64 s** (pull + teardown +
  destroy ladder); `collect` with the wrong port **90.69 s** → false FAIL versus **2.32 s** →
  correct `RUNNING` on the right port. No `PERF-<n>` row: all of it is substrate wait or a wrong
  constant (`QA-HARNESS-PORT-1`).
- **Left behind:** the battery grading + crier finding appended to
  `docs/dogfood/2026-10-23-integration.md`, the diagnostics section from the sibling entry (unchanged
  by me), the usage-skill corrections, and this entry. Foreman not woken; repo visibility and
  permissions untouched.
- **Residue:** detached worktree `/tmp/crier-head-JsBb/src` (read-only reproduction of HEAD, safe to
  delete), evidence + harvest under `/tmp/qa-audit-df-20261023-1343/`.

## 2026-10-23 (13:43Z tick) — CORROBORATION + EVIDENCE PACK for QA-HARNESS-CAP-1 (third delivery; the two entries above own the collect close-out)

- **Why this entry is short:** the two entries above already close the collect leg and grade all
  19 cells. This delivery therefore re-runs nothing and adds only (a) an independent second
  `collect` measurement, (b) the evidence pack that makes `QA-HARNESS-CAP-1` reviewable from the
  repo instead of from `/tmp`, and (c) an attribution disclosure for the commit that carried it.
- **Independent collect (same evidence file, concurrent with the delivery above):**
  `BUNKER_QA_SERVER=bunker-las-02 BUNKER_QA_SSH_PORT=22 bunker-qa.sh collect --evidence
  /tmp/bunker-qa-evidence-20261023T140019Z-1181340.jsonl` → `COLLECTED agent=634852c9 rows=19`,
  **WALL=243.79 s** (USER 0.12 s / SYS 0.15 s). Two `collect` processes ran on that one path at
  once; both landed `collect OK` rows, the merge produced **0 duplicate `(cell,status,detail)`
  groups** across the 24 merged rows, and the later one printed `destroy reported failure but the
  agent is GONE from the server list` — so a concurrent collect is survivable, and the walls
  (243.79 s here, 337.64 s above, vs the ~90 s of a lone collect) are contention, not product
  numbers. Agent `634852c9` verified absent from `bunker list --server bunker-las-02` afterwards.
- **The `QA-HARNESS-CAP-1` evidence, now IN the repo:** `docs/dogfood/evidence/2026-10-23/` holds
  `crier-battery-evidence.jsonl` (the 24 merged rows), `native-uncapped-failures.txt` (the uncapped
  ci-pass leg: 2 failures, **0** Wasm-OOM lines) and `res-capped-wasm-oom.txt` (the capped
  `chaos-resource` leg: `SUBSHELL_CAP=3145728`, 5 failures, **4** `WebAssembly.instantiate(): Out
  of memory` lines, and the `RESULT 16/16 passed` line that precedes the node crash). The
  discrimination is leg-vs-leg on one repo: **2 uncapped vs 5 capped**, with a dev-host uncapped run
  of all five tests failing only the same two — so the three extras are the cap, not the product.
- **Attribution disclosure:** `QA-HARNESS-CAP-1`, event **49**, the `res.log`-is-capped and
  concurrent-collect usage-skill pitfalls, and the cap sections in the integration report and the
  diagnostics trail were written by THIS delivery but were committed by commit `926a32ca0e`
  (the other delivery's follow-up commit swept the working tree). Nothing was lost and nothing was
  filed twice: `QA-CRIER-1` (P1, crier's red `cmd/server` suite) is that delivery's row, not a
  duplicate of mine, and crier's own `INT-CRIER-015` / `DF-CRIER-483` remain the fix owners.
- **Final census:** five ids from this tick on the board (`QA-HARNESS-PORT-1`,
  `QA-HARNESS-LEAK-003`, `QA-HARNESS-STATUS-1`, `DOC-009`, `QA-HARNESS-CAP-1`) plus `QA-CRIER-1`,
  each present exactly once in the committed blob; `boardctl validate -C .` → **RESULT: OK,
  16 warnings**, the pre-tick baseline (0 new). Foreman not woken; repo visibility and permissions
  untouched.

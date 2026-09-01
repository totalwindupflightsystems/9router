# Dogfood Log

## 2026-09-01 — 9router (federation fork) — run 3: re-verify the fixes

- **Verdict:** ✅ SHIPPABLE (federation feature). Every formerly-open finding
  (FED-020 delta version drop, FED-021 lag metric, FED-022 settings
  replication, NR-GAP-034/036/039 hardening) re-verified FIXED at row level
  against real deployments.
- **Promise:** "Edges proxy /v1 + dashboard API to central, replicate its
  SQLite within seconds, keep serving during a central outage (writes queued,
  reconciled later) — using only documented env vars."
- **Method:** real deployment @ `cd90fd9e` (repo-root production path,
  `npm ci` + build), real dashboard API (login/key/provider/combo/settings),
  real `/v1` against a local mock Ollama, SIGKILL central → degraded →
  serve-from-replica → 202 queued write → restart → drain → re-link.
- **Top findings (all minor, P3):**
  1. **R3-01** — PUT `/api/keys/{id}` silently ignores `name` (200 + no-op).
  2. **R3-02** — short-FEDERATION_TOKEN boot guard logs placeholder-secrets
     wording (hard refusal, but misleading message).
  3. **R3-03** — `[federation] pull failed: fetch failed` logged once per
     sync interval for the whole outage; no rate limiting.
- **Row-level integrity:** apiKeys v4 delta, settings v6, combos v7 —
  `federation_version` + `updated_at` identical central/edge. FED-020
  signature (`maxVersion < lastAppliedRevision`) absent.
- **Time-to-first-success:** ~6 min (clean scratch → first `/v1` completion
  through the edge). Friction count: 4 (none blocking).
- **Artifacts:** `docs/dogfood/2026-09-01-integration.md`,
  `docs/dogfood/diagnostics.md` §11,
  `skills/9router-federation-usage/SKILL.md` v3.0.0, board R3-01..03
  (event id 452).
- **Foreman:** cooldown 259200s (3-day) with an empty board at start —
  woken to 900s to work R3-01..03, per the stand-in speed-up loop.
- **Meta:** the three-layer termination check (L3 = real user workflow) is
  what makes this verdict trustworthy; the 12-file/189-test federation
  vitest suite passes at HEAD too, but it passed at earlier HEADs that
  still hid FED-020.

## 2026-08-20 — 9router (federation fork) — re-test after FED-011..016

- **Verdict:** 🟡 PROMISING-BUT-ROUGH (federation now WORKS end-to-end; one P1
  replica-integrity bug + two P2 gaps remain). 2026-08-08 🔴 verdict resolved in
  practice.
- **Promise:** "Edges proxy /v1 to central, replicate central's SQLite, keep serving
  from a local replica during a central outage (writes queued, reconciled later)."
- **Method:** Real deployment, not tests: fresh `npm run build` at HEAD 10bb05d3,
  central + edge via the documented repo-root production path (`node custom-server.js`
  = `npm run start`), real dashboard API seeding (login, API key, ollama provider),
  real /v1 traffic against a mock Ollama upstream, SIGKILL of central, degraded
  writes, central restart. Re-ran the 2026-08-08 acceptance checks A–D verbatim.
- **Top findings:**
  1. **A–D ALL PASS**: replication converges (<10s, apiKeys/providerConnections in
     replica), authenticated /v1 through the edge (200, not "Invalid API key"),
     Bearer-only federation API (200), and the full kill→DEGRADED→serve-from-replica
     →queued-write (202 + X-Federation-Queued-Write-Id)→recover→drain (state=done)
     →reconcile (central has queued key; replicated back to edge) lifecycle.
     FED-011..016 fixes verified live (loops start from real entry points; edge boot
     logs `[federation] replication + failover loops started (edge mode).`).
  2. **FED-020 (P0-in-effect, filed P1)** — delta-applied replica rows lose
     `federation_version`/`updated_at` (entry-level metadata dropped by the delta
     branch of `applyRevisionBatch`): central v4/v5 rows land as v0/NULL on the edge;
     `local-status` shows `lastAppliedRevision:5, maxVersion:1`, revisionLag clamped
     to 0 — a stale edge can look healthy. Snapshot path is correct, which is why
     the bootstrap-heavy tests missed it.
  3. **FED-021 (P2)** — revisionLag derives from the local (corruptible) watermark
     instead of central's advertised maxVersion; FED-022 (P2) — settings boot seed
     bypasses stamping so settings never replicate via delta (edge settings=0).
- **Time-to-first-success:** ~3 min standalone completion on central; federation
  convergence ~10s after seeding; full lifecycle verified in ~15 min of testing.
- **Friction count:** 4 (stream:true 503 with mock — identical on central, not
  federation; undocumented model prefix; provider API shapes need source-reading;
  proxy ~2x timeout on failure paths).
- **Artifacts:** `docs/dogfood/2026-08-20-integration.md`,
  `docs/dogfood/diagnostics.md` §7-10 (addendum), `skills/9router-federation-usage/SKILL.md`
  v2.0.0 (rewritten to current reality), board FED-020..FED-022 (event id 369).
- **Foreman:** woken — CooldownS 21600 → 900 via scheduler API (Enabled=true kept).
- **Meta:** the 2026-08-12 reverify passed while row versions were already
  corrupting — it asserted counts and lag, never row-level version metadata. The
  integrity probe (compare row versions central vs edge after a delta update) is now
  step 4 of the verification playbook.

## 2026-08-08 — 9router (federation fork)

- **Verdict:** 🔴 DOES-NOT-DELIVER (federation feature; standalone/upstream product works)
- **Promise:** "Deploy the same 9router on multiple instances; edges proxy /v1 to central,
  replicate central's SQLite, and keep serving from a local replica during a central
  outage (writes queued, reconciled later)."
- **Method:** Real deployment, not tests — central + edge booted from the exact
  Dockerfile.federation runtime layout (`node custom-server.js`), real dashboard API
  usage (login, API keys, provider connection), real `/v1/chat/completions` against a
  mock Ollama upstream, SIGKILL of central, degraded writes, central restart.
- **Top findings:**
  1. **FED-011 (P0)** — edge proxy strips the client's API key (`Authorization` →
     `X-9r-Client-Authorization`, never read upstream): authenticated /v1 through any
     edge → `Invalid API key` from central. The headline "point your CLI tool at the
     edge" workflow fails on the first authenticated request.
  2. **FED-013 (P0)** — replication + failover loops (`edgeClient.start()`/
     `failover.start()`) are called only by the e2e harness, never by the real app:
     edge replica stayed empty (0 apiKeys/providerConnections after 6 min), DEGRADED
     serving answered `Invalid API key` (empty replica), and after central restart the
     edge stayed DEGRADED forever with pendingWrites never drained / never reconciled.
  3. **FED-012 (P0)** — `/api/federation/*` 401s with only the documented Bearer token
     (dashboardGuard deny-by-default; `/api/federation` missing from PUBLIC_API_PATHS);
     even token-less `local-status` needs a dashboard session. The documented protocol
     is unreachable.
  - Also: FED-014 (README `npm run start` never loads custom-server.js → no federation
    at all), FED-015 (plain Docker image ships without `src/lib/federation` → silently
    inert edge), FED-016 (status surface masks "never started" as `linked`).
- **Time-to-first-success (federation):** never — first documented workflow (replication)
  failed at step 1; first working federation API call required an undocumented dashboard
  cookie. Time-to-first-success (standalone gateway): ~3 min.
- **Friction count:** 7 (see integration report).
- **Artifacts:** `docs/dogfood/2026-08-08-integration.md`,
  `docs/dogfood/diagnostics.md`, `skills/9router-federation-usage/SKILL.md`, board
  tasks FED-011..FED-016 (event id 74).
- **Foreman:** not woken (CooldownS already 900); 6 pending P0/P1/P2 tasks on the board.
- **Meta:** the "e2e 17/17 PASS" claim coexists with a dead feature — the harness starts
  the loops itself and bypasses Next's dashboardGuard. Tests proved modules, not product.
2026-09-01 | PROMISING-BUT-ROUGH | 20s t2fs | friction 6 | 5 findings

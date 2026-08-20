# 9Router Federation — Diagnostics Trail (2026-08-08 dogfood)

_How the federation feature is built, what the dogfood run found, and the right way to
understand/fix it. Written by the 2026-08-08 dogfood run; board tasks FED-011..FED-016._

## 1. The architecture in one paragraph

9router is a Next.js 16 app (plain JS ESM, `@/*` → `src/*`) that fronts 40+ AI providers
with an OpenAI-compatible `/v1` API + dashboard. The federation fork adds three layers,
all gated on `FEDERATION_MODE` (default `standalone` = zero drift):

1. **DB layer** (`src/lib/federation/stamp.js`, migrations `00NN_federation*`): versioned
   config tables (`federation_version`, `updated_at`, `deleted` tombstones on the 8 config
   tables), `federation_meta` (role, edgeId, lastAppliedRevision, schemaVersion,
   leaseOwner/leaseExpiry, last_state, fencing_token), `pendingWrites`.
2. **Central API** (`src/lib/federation/server.js` + `src/app/api/federation/*` route
   wrappers): `snapshot`, `delta`, `verify`, `status`, `replay`, `local-status`,
   `config-status`, guarded by `src/lib/federation/roleGuard.js` (Bearer
   `FEDERATION_TOKEN`, SHA-256 pre-hash constant-time compare).
3. **Edge machinery** (`src/lib/federation/edgeClient.js` replication poll,
   `failover.js` heartbeat/state machine, `proxy.js` forwarding layer,
   `queue.js` degraded write queue) — wired into `custom-server.js`, which wraps
   `http.createServer` for the Next standalone server and sits **before** Next dispatch.

The forwarding decision is `proxy-up-by-default`: any request that matches `/v1/*` or a
mutating dashboard API path is proxied to central unless the edge is DEGRADED.

## 2. How the dogfood run found what it found

Reproduction-first, with real servers, in ~50 minutes:

- Assembled the exact `Dockerfile.federation` runtime layout in `/tmp` (standalone output
  + `custom-server.js` + `open-sse` + full `src/` + `node_modules/@` → `src` alias).
- Booted central (20131) + edge (20132) with `node custom-server.js` — the containers' CMD.
- Mock Ollama upstream (`/api/chat`, `/api/tags`) so real chat completions flowed.
- Watched the edge's replica DB (`better-sqlite3` read-only) and logs for ~6 minutes.
- Killed central with SIGKILL; watched state; restarted central; watched again.

## 3. Errors hit and their root causes (yours AND the project's)

| Error observed | Root cause | Task |
|---|---|---|
| `{"error":"Invalid API key"}` from central when proxying a valid client key via the edge | `buildUpstreamHeaders` moves `Authorization` → `X-9r-Client-Authorization`; central /v1 auth never reads it ("inert when absent"). Client key never reaches central's auth. | FED-011 |
| `{"error":"Unauthorized"}` on `/api/federation/status|verify|snapshot` with correct Bearer token; also on `local-status` with no auth | dashboardGuard (`src/proxy.js`) deny-by-default for `/api/*`; `/api/federation` missing from `PUBLIC_API_PATHS`. Guard runs before roleGuard. | FED-012 |
| Edge replica stays empty forever; `last_state` stays null; no log lines | `edgeClient.start()` / `failover.start()` never called outside the e2e harness. `custom-server.js` loads modules but never starts loops. | FED-013 |
| DEGRADED edge answers `/v1` with `Invalid API key` (replica empty) | consequence of FED-013 (no replication) — the failover machinery itself works (flip persisted `degraded`, queue accepted writes) | FED-013 |
| After central restart: edge stuck DEGRADED, `pendingWrites` never drain, central never reconciles | no heartbeat loop → nothing detects recovery (consequence of FED-013) | FED-013 |
| `npm run start` edge: no proxy at all, silently | `next start` doesn't load `custom-server.js`; only the Docker CMD does | FED-014 |
| Plain `Dockerfile` image edge: federation imports fail open, silently inert | image ships only `src/mitm`; Next tracing doesn't follow dynamic imports; only `Dockerfile.federation` copies `src/` | FED-015 |
| Central `/api/federation/status` shows `revisionLag: 3` on itself; `local-status` shows `linked` while nothing ever ran | status metrics computed naively; `last_state` defaults to LINKED on an empty meta row — masks "never started" | FED-016 |
| `mock-model-7b` → `No active credentials for provider: openai` | model IDs need the provider prefix (`ollama-local/mock-model-7b`); routing falls back to a default provider otherwise | (cosmetic, docs) |

## 4. The right way (what the fixes must look like)

1. **Start the loops where the process boots.** `custom-server.js`'s `listening` handler is
   the natural place (it already lazy-loads the modules): call `edgeClient.start()` +
   `failover.start()` there when `FEDERATION_MODE=edge`, with the env-driven intervals.
   `src/instrumentation.js` is the fallback for non-custom-server boots. The e2e harness
   should stop being the only starter.
2. **Make the guard pass the protocol through.** Add `/api/federation` (and
   `/api/federation/*`) to `PUBLIC_API_PATHS` in `src/dashboardGuard.js`. roleGuard already
   enforces the Bearer token with constant-time compare; `local-status`/`config-status` are
   intentionally token-less. This is the documented contract (FEDERATION.md §4/§5).
3. **Preserve client auth through the proxy.** Either central's /v1 auth falls back to
   `X-9r-Client-Authorization` when `Authorization` is the federation token, or the proxy
   keeps the client's `Authorization` and moves the federation token to a dedicated header
   (e.g. `X-Federation-Token`) that only central's federation API accepts. The latter is
   cleaner: `/v1` and dashboard API keep looking exactly like direct requests.
4. **Make inert loud.** A `FEDERATION_MODE=edge` boot without the modules (plain Docker
   image) or without the custom-server wrapper (`npm run start`) should print a clear
   error/warning naming the missing piece — never fail open silently.
5. **Fix the status surface.** `local-status` should report `uninitialized` when
   `lastAppliedRevision IS NULL`; central's `revisionLag` should not count its own writes.

## 5. How to verify the fixes (L3 acceptance — real use, not unit tests)

See the acceptance checks in `docs/dogfood/2026-08-08-integration.md`. Minimum: an edge
started via the documented Docker/README path converges its replica within ~15s, serves an
authenticated `/v1` completion through the proxy, flips DEGRADED on central death, still
serves from the replica, queues writes, and recovers + reconciles when central returns.

**Status (2026-08-12): re-verified PASS — see
`docs/dogfood/2026-08-12-federation-l3-reverify.md`.** All four acceptance checks (A: converge,
B: authenticated proxying, C: Bearer-only API, D: kill/restart lifecycle with drain) now pass
against the current `federation` branch. The re-run surfaced and fixed one new integration bug
(queued `POST /api/keys` replays failed with `machineId is required` — server.js now derives
machineId like the direct route).

## 6. Why the e2e harness missed all of this

`tests/federation/e2e.mjs` + `e2e-child.mjs` build a **framework-free** node:http server
(`next/server` is not importable outside a Next build), start `edgeClient`/`failover`
**explicitly** (lines 262/266), and inline roleGuard semantics — so it never exercises:
custom-server.js wiring, dashboardGuard, the real route wrappers, or the real /v1 auth.
It proves modules, not product. Any future e2e must boot the real app (the dogfood repro
layout is the blueprint: standalone output + custom-server.js + src) and hit it over HTTP.

---

# Addendum 2026-08-20 — second dogfood run: what still breaks, and why

_After the 2026-08-12 reverify (A–D PASS), a second real-use run re-verified A–D
(ALL PASS — see `docs/dogfood/2026-08-20-integration.md`) and then probed
replica integrity. The row-level version metadata on edges is corrupted by the
delta path. This is the "what the reverify missed" record._

## 7. The delta-apply version drop (FED-020) — a test-shaped blind spot

**Symptom:** on a converged edge, `local-status` reports
`lastAppliedRevision:5, maxVersion:1, revisionLag:0` — an applied watermark
*above* the local row watermark, with lag clamped to 0. Direct DB comparison:

| row | central | edge |
|---|---|---|
| key created before edge bootstrap (snapshot path) | v1 | v1 ✅ |
| key created after (delta path) | v4 | **v0, updated_at NULL** ❌ |
| provider row re-stamped on central (delta path) | v5 | **v0** ❌ |

**Root cause (read the wire, then the code):** the central delta handler
serializes entries as `{table, row, federation_version, updated_at, deleted}`
— version metadata at ENTRY level. `applyRevisionBatch`'s delta branch
destructures `{ table, row }` and calls `upsertLogicalRow(db, table, row)`,
which reads `entry.federation_version` — always undefined on the delta path →
`0`. The snapshot branch passes full entries, so bootstrap rows are correct.

**Why the tests missed it (the lesson):** `replication.test.js` (24 tests)
asserts row COUNTS and the `lastAppliedRevision` watermark — both stay green
while versions corrupt. The 2026-08-12 reverify also only checked counts +
lag. The check that catches this: compare the edge row's
`federation_version`/`updated_at` to central's after a delta-delivered update,
or assert `local-status.maxVersion == lastAppliedRevision` on a converged
edge. **Assert the data, not just the counters.**

**Right way:** delta branch passes the full entry —
`for (const entry of rows) upsertLogicalRow(db, entry.table, entry)` — plus a
regression test that updates a row on central after bootstrap and asserts the
edge replica keeps the entry's version/updated_at.

## 8. The status metric's second failure mode (FED-021)

`revisionLag = max(0, localWatermark - lastAppliedRevision)` — even after
FED-020, lag measured against the EDGE's own (possibly corrupted, possibly
stale) rows can't tell "healthy" from "stale". The edge already receives
central's true watermark (`maxVersion`) in every snapshot/delta payload —
compute lag against that. FED-016 fixed central's self-lag; this is the
edge-side twin: a metric that only reports what the replica's own (mutable,
corruptible) rows say.

## 9. Settings: an eighth table that never moves (FED-022)

The docs/constants promise 8 replicated tables; in practice `settings`
replicates only via snapshot timing. Boot seed `src/lib/db/migrate.js:116` is
a raw insert that skips stamping → `federation_version=NULL` → the delta query
(`> ?`) excludes it forever. `settingsRepo.js:107` stamps, so dashboard-driven
settings changes would flow — but the seed (password hash, defaults) never
does, and an edge that snapshots before central's first seed keeps `settings=0`
indefinitely. Decide: stamp the seed, or document settings as per-instance and
drop it from `REPLICATE_TABLES`.

## 10. The right way to verify federation (updated playbook)

1. Boot central + edge via `npm run build && node custom-server.js` (repo
   root works — FED-017) with fresh DATA_DIRs and fast intervals
   (SYNC 2000 / HEARTBEAT 1000 / OUTAGE 5000).
2. Check the edge boot log for `[federation] replication + failover loops
   started` — no line, no federation.
3. Seed via dashboard API (login → keys → providers), then run acceptance
   A–D from `docs/dogfood/2026-08-20-integration.md`.
4. **Then check integrity** (the step both prior runs skipped): compare row
   `federation_version`/`updated_at` between central and edge for rows that
   changed AFTER the edge bootstrapped; assert
   `local-status.maxVersion == lastAppliedRevision` on a converged edge.
5. `stream:false` only for mock-upstream verification; `stream:true` fails
   503 with the mock on central AND edge (mock format limitation, not a
   federation bug — re-verify against a real Ollama before shipping).

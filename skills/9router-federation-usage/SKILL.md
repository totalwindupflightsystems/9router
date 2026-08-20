---
name: 9router-federation-usage
description: >-
  How to deploy, configure, and VERIFY the 9router federation feature (edge ->
  central proxying + SQLite replication + failover) in this fork. Use when a
  task involves federation: booting central/edge instances, the FEDERATION_*
  env vars, the /api/federation/* protocol, or verifying the failover
  lifecycle. Includes the verified real-boot recipe (repo-root production
  path), the dashboard API quick reference, the acceptance checks, and the
  known pitfalls (FED-020 delta version drop, FED-022 settings, stream-mode
  mock caveat) so agents don't re-discover them.
version: 2.0.0
---

# 9router federation — usage skill (fork)

This fork's federation feature: deploy the same 9router gateway on many hosts;
edges proxy `/v1` + mutating dashboard API to a central instance, replicate its
SQLite config DB, and serve from the local replica if central dies (writes
queued during an outage, replayed on recovery).

**Status (verified 2026-08-20 dogfood, real deployment): the feature WORKS
end-to-end.** Acceptance checks A–D pass: replication converges (<15s), client
API keys authenticate through the edge, the federation API answers Bearer-only,
and the full kill-central → DEGRADED → serve-from-replica → queued-write →
restart → drain → reconcile lifecycle completes. The 2026-08-08 DOES-NOT-DELIVER
findings (FED-011..016) are fixed in practice. Two open items: FED-020 (P1 —
delta-applied replica rows lose `federation_version`/`updated_at`; watch for
`maxVersion < lastAppliedRevision` in local-status) and FED-022 (P2 — settings
don't replicate via delta). Don't trust "federation works" claims — run the
acceptance checks; they take ~10 minutes.

## Key facts

- Env: `FEDERATION_MODE=standalone|central|edge` (default standalone = inert).
  Edge also needs `FEDERATION_CENTRAL_URL` + `FEDERATION_TOKEN`; share
  `JWT_SECRET`/`API_KEY_SECRET`/`INITIAL_PASSWORD` across instances (mismatch =
  "everything links but nothing works"). Defaults in
  `src/lib/federation/config.js` + `constants.js`; documented in
  `docs/FEDERATION.md` (deployment guide) + `docs/federation-spec.md` (design).
- Modules: `src/lib/federation/{config,constants,edgeClient,failover,proxy,
  queue,replication,roleGuard,server,state,stamp,headers,statusView,
  startLoops}.js`.
- The edge proxy/DEGRADED intercept runs inside `custom-server.js` — and
  **`npm run start` now boots it** (FED-014). `npm run dev` with
  `FEDERATION_MODE=edge` exits FATAL by design (FED-018) — use the production
  path for edges.
- Loops start from real entry points (FED-013): an edge logs
  `[federation] replication + failover loops started (edge mode).` at boot.
- Central federation API: `/api/federation/{snapshot,delta,verify,status,replay}`
  with `Authorization: Bearer <FEDERATION_TOKEN>` (no cookies needed — FED-012
  fixed); `local-status` + `config-status` are token-less, local only.
- Replica DB: `<DATA_DIR>/db/data.sqlite` (WAL, better-sqlite3 → sql.js
  fallback). Usage tables stay host-local by design.

## Boot a real central + edge (verified 2026-08-20 recipe)

The **repo-root production path works as-is** (FED-017 fixed `@/` alias
resolution in the runtime graph) — no Docker-layout assembly needed:

```bash
# 1. build once
npm run build          # postbuild copies custom-server.js into .next/standalone

# 2. central (port 20131, fresh DATA_DIR)
cd /home/kara/9router
NODE_ENV=production HOSTNAME=127.0.0.1 PORT=20131 DATA_DIR=/tmp/fed-central \
JWT_SECRET=<shared> API_KEY_SECRET=<shared> INITIAL_PASSWORD=<pass> \
FEDERATION_TOKEN=<shared-token> FEDERATION_MODE=central FEDERATION_EDGE_ID=central \
node custom-server.js

# 3. edge (port 20132, fresh DATA_DIR, fast intervals for testing)
NODE_ENV=production HOSTNAME=127.0.0.1 PORT=20132 DATA_DIR=/tmp/fed-edge \
JWT_SECRET=<same> API_KEY_SECRET=<same> INITIAL_PASSWORD=<same> \
FEDERATION_TOKEN=<same-token> FEDERATION_MODE=edge FEDERATION_EDGE_ID=edge \
FEDERATION_CENTRAL_URL=http://127.0.0.1:20131 \
FEDERATION_SYNC_INTERVAL_MS=2000 FEDERATION_HEARTBEAT_INTERVAL_MS=1000 \
FEDERATION_OUTAGE_THRESHOLD_MS=5000 \
node custom-server.js
```

Edge boot must show `[federation] replication + failover loops started (edge mode).`
If not, federation is not running (check FEDERATION_MODE / wrapper / image).

To get real `/v1` traffic without external credentials: create an `ollama-local`
provider pointing at any mock OpenAI/Ollama-compatible server, then call
`/v1/chat/completions` with model `ollama-local/<model>` (the provider prefix is
required). A working mock is at `/tmp/dogfood-9router/mock-ollama.mjs`
(`POST /api/chat`, `GET /api/tags`, port 11439).

## Dashboard API quick reference

```bash
curl -c cookies -X POST http://HOST:PORT/api/auth/login -H 'Content-Type: application/json' \
  -d '{"password":"<INITIAL_PASSWORD>"}'          # session cookie
curl -b cookies -X POST http://HOST:PORT/api/keys -H 'Content-Type: application/json' \
  -d '{"name":"my-key"}'                           # -> {"key":"sk-...", "machineId": ...}
curl -b cookies -X POST http://HOST:PORT/api/providers -H 'Content-Type: application/json' \
  -d '{"provider":"ollama-local","name":"mock","providerSpecificData":{"baseUrl":"http://127.0.0.1:11439"}}'
# /v1 (OpenAI-compatible; stream:false works with the mock, stream:true does NOT — see pitfalls)
curl -s -X POST http://HOST:PORT/v1/chat/completions -H "Authorization: Bearer <key>" \
  -H 'Content-Type: application/json' \
  -d '{"model":"ollama-local/<model>","stream":false,"messages":[{"role":"user","content":"ping"}]}'
```

## Verifying federation (acceptance checks — run these, not the test suite)

```bash
# A. replication converges: edge local-status -> linked, revisionLag 0, and
#    lastAppliedRevision ADVANCES after central-side writes (check twice!)
curl -s http://EDGE:PORT/api/federation/local-status   # token-less
# B. authenticated /v1 through the edge (must be 200, NOT "Invalid API key")
curl -s -X POST http://EDGE:PORT/v1/chat/completions -H "Authorization: Bearer <client-key>" \
  -H 'Content-Type: application/json' \
  -d '{"model":"ollama-local/<model>","stream":false,"messages":[{"role":"user","content":"ping"}]}'
# C. federation API, Bearer only, no cookies
curl -s http://CENTRAL:PORT/api/federation/status -H "Authorization: Bearer $FEDERATION_TOKEN"
# D. lifecycle: SIGKILL central -> edge flips degraded (~threshold ms) and /v1 STILL
#    200 (replica serving); queued write -> 202 + X-Federation-Queued-Write-Id;
#    restart central -> edge returns to linked, pendingWrites state=done,
#    central contains the queued row, and it replicated back to the edge.
```

## Pitfalls (learned the hard way)

- **FED-020 (open, P1): delta-applied rows lose version metadata.** After any
  central-side update lands on an edge via delta, the edge row has
  `federation_version=0, updated_at=NULL` while central keeps the true version.
  Signature in `local-status`: `maxVersion < lastAppliedRevision` (e.g.
  `lastAppliedRevision:5, maxVersion:1`) with `revisionLag` clamped to 0 — a
  stale edge can look healthy. Check row versions directly:
  `SELECT name, federation_version, updated_at FROM apiKeys` on both DBs and
  compare. Don't trust `revisionLag` until FED-020/FED-021 land.
- **FED-022 (open, P2): settings never replicate via delta** (boot seed isn't
  stamped). An edge bootstrapped before central's first login will keep
  `settings=0` forever; per-instance dashboard auth still works because each
  instance seeds its own password.
- **Streaming with the mock upstream fails** (`503 Provider error (reset after
  15s)`) — identical on central and edge, so it's NOT federation-specific; it's
  the mock's non-compliant stream format (documented since 2026-08-12). Always
  use `"stream":false` in local verification.
- The e2e harness (`tests/federation/e2e.mjs`) is NOT a product test — it spawns
  its own instances. The real-boot recipe above is the honest verification.
- `local-status` reporting `"linked"` with `initialized:true` means loops ran;
  `"uninitialized"` means they never started (FED-016 semantics).
- Model IDs on /v1 need the provider prefix: `ollama-local/<model>`.
- Never reuse `FEDERATION_TOKEN` for `JWT_SECRET`/`API_KEY_SECRET`; do share
  the latter two across instances.
- Secrets: docker-compose.federation.yml ships `change-me-*` placeholders and
  federation-mode boots REFUSE to start while they're in place (NR-GAP-019) —
  set real values first.

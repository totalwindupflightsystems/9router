# Muster Protocol Integration — Design Doc (SCHED-GAP-1578)

**Status:** DESIGN — 2026-10-06. No code changes. Defines what "connecting over the
muster protocol" means for coding-hermes-scheduler.

## 1. What "muster" is here

Muster (the `wojons/muster` engine and its `musterflow` build) turns an OpenAPI
specification into executable surfaces: a CLI, an HTTP MCP server, and a daemon.
It is NOT a bespoke wire protocol — **connecting over the muster protocol means
muster consumes the scheduler's existing OpenAPI 3.0.3 document and drives the
scheduler's existing REST API.** The scheduler changes no code to be connected;
it only needs to publish a spec muster can consume and keep it accurate.

The single integration artifact is already shipped: **`GET /api/v1/openapi.json`**
([docs/api.md §13](api.md#13-openapi-spec)), generated from `internal/api/server_helpers.go`
and served by the live daemon. The connection flow is:

```sh
musterflow connect http://127.0.0.1:9090/api/v1/openapi.json
# → muster generates CLI subcommands + MCP tools for every schedulerd endpoint
```

From that point every route in the scheduler's API is a muster CLI subcommand or
an MCP tool call, authenticated and scoped per §3 below.

## 2. What the scheduler exposes to muster

Everything the REST API exposes — muster's surface is a faithful mirror of the
in-repo route table ([docs/reference/endpoints.md](reference/endpoints.md),
build-enforced by `internal/mcp/agents_endpoint_parity_test.go`), not a new
surface. Grouped by what an operator would do through muster:

**Read-only (open, no credential):** `GET /api/v1/health`, `/live`, `/status`,
`/config`, `/projects`, `/projects/{name}`, `/namespaces` (+ detail, projects,
move is POST), `/ticks`, `/ticks/{id}`, `/events`, `/events/stream`,
`/queue`, `/metrics`, `/openapi.json`. These are deliberately unauthenticated
(SCHED-GAP-1602 "read-open vs write-gated"); muster can query fleet state with
no credential configured.

**Control (operator credential):** project CRUD
(`POST/PUT/DELETE /api/v1/projects...`), `pause` / `resume` / `spawn` / `bump` /
`unbump` per project, namespace CRUD + `move`, fleet-wide `POST /api/v1/evaluate`
/ `/pause` / `/resume`, and the MCP JSON-RPC surface at `POST /mcp` (same gate,
same decision ladder — see [docs/api.md §0](api.md#0-authentication-sched-gap-1602)).

**Federation surfaces (operator credential, incl. the GETs):** peer registry
(`GET/POST /api/v1/peers`, `POST /api/v1/peers/{id}/heartbeat`, durable event
slices) and federation query (`POST /api/v1/federation/query`). The peer list is
fleet topology, not public read material, so the entire section fails closed
(503) with no credential configured.

What muster does NOT see: the SQLite database file itself, internal scheduler
state that has no REST route, and anything behind the daemon's loopback bind that
is not published as an endpoint.

## 3. What muster can request from the scheduler

Muster drives the scheduler exactly as any HTTP client would. Three interaction
models, all via the one spec:

1. **Fleet observation** — the read routes above, at muster-CLI or Starlark
   workflow cadence (e.g. a `flow` that polls `/api/v1/queue` and `/api/v1/events`
   and raises on failure-rate spikes in `/api/v1/metrics`).
2. **Fleet control** — mutations through muster call the same operator-gated
   routes: spawn a project's tick (`POST /api/v1/projects/{name}/spawn` →
   202 with a resolvable `tick_id`), pause/resume a lane, update weights via
   `PUT /api/v1/projects/{name}`. Muster inherits the API's guards verbatim:
   401 without credential, 503 fail-closed in `authOff` mode, 409 on deleting an
   enabled project, and the `/api/v1/events` audit row on every mutating decision.
3. **Cross-scheduler federation** — a muster-connected scheduler can be
   registered as a peer (`POST /api/v1/peers`) and queried by another scheduler
   via `POST /api/v1/federation/query` (`peer.status`, `fleet.status`,
   `projects.list`, `queue.get`, `ticks.list`, `events.list` — reusing only the
   scheduler's own read paths, answer shape per [docs/api.md §15](api.md#15-federation-query-remote-008)).
   Muster workflows can orchestrate this, but the authority model (§4) is the
   scheduler's own, never extended by muster.

## 4. Auth model

The scheduler's existing model applies unchanged (SCHED-GAP-1602,
[docs/api.md §0](api.md#0-authentication-sched-gap-1602)); muster maps onto it
with zero scheduler-side additions:

| Concern | Model |
|---|---|
| Reads | Unauthenticated by design (read-open), loopback/tailnet deployment boundary |
| Mutations + MCP calls + federation surfaces | Operator credential: `Authorization: Bearer <token>` (preferred), Basic, or `X-Operator-Token: <token>` — constant-time comparison, `WWW-Authenticate` on 401 |
| Credential source | `SCHEDULER_OPERATOR_TOKEN` env or `[api] operator_token` TOML — never argv (GAP-038) |
| No credential configured | Fail-closed 503 on every mutating route, regardless of presented credential |
| Muster-side credential | `musterflow auth add <scheduler-connection-id>` (bearer type), stored masked in musterflow's data dir — the token never passes through muster's CLI argv |
| Auditability | Every allowed AND refused mutating/federation request writes an `api.auth` / `api.federation` audit row visible via `GET /api/v1/events` — muster calls are attributable like any operator |

Federation-style scoping (per-caller op allow-lists under
`[federation.allow."*"]`) governs `federation/query` reads; muster holds no
special exemption — a muster caller is just another caller identity in the
audit log.

## 5. Non-goals

- No new scheduler endpoints, headers, or auth modes for muster specifically.
- No muster-generated code committed to this repo — the spec is the only shared
  artifact, regenerated from the daemon at `GET /api/v1/openapi.json`.
- No schema drift risk: the OpenAPI doc and route table are already locked
  together in CI (`TestOpenAPIDocsSpec`-adjacent guards; spec §13 of api.md).

## References

- REST API reference: [docs/api.md](api.md) (§0 auth, §13 OpenAPI spec, §14 peers, §15 federation query)
- Route table: [docs/reference/endpoints.md](reference/endpoints.md)
- Federation spec: [docs/remote-spec.md](remote-spec.md), [docs/federation-query-spec.md](federation-query-spec.md)
- Muster/MusterFlow: `github.com/wojons/muster` (private engine), `github.com/totalwindupflightsystems/musterflow` (integration guide: CLI `connect`, `auth add`, dashboard, MCP)

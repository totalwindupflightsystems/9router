# 9router — Observability Specification

Status: specification (no service code changed by this document).
Audit date: 2026-11-03. Repo: `/home/kara/9router` at `3638eefe`.
Board lane: `monitoring`.

---

## 1. Role of the service and what "healthy" means

9router is the fleet's **LLM routing gateway**. It accepts OpenAI-compatible
(`/v1`, `/v1beta`, `/codex`, `/responses`) traffic, authenticates callers, selects a
provider connection (account) for a requested model, translates the request into the
provider's wire format, streams the response back, and records token/cost usage. It
runs as **7 production instances**, each a long-lived Next.js standalone Node process
(`scripts/start.mjs` → `custom-server.js`, listening on `PORT`, default 20128 —
`package.json` scripts `dev`/`dev:beta`).

Healthy means, in the order an operator cares at 3am:

1. **Up and serving** — the process is alive and accepting `/v1` requests.
2. **Doing work** — requests are completing, not stalling on upstreams.
3. **Routing successfully** — most requests succeed on the first account; failover is
   exceptional, not the normal path.
4. **Not throttled** — providers are not rate-limiting us, and account cooldowns are
   short-lived and few, not a growing pool of locked accounts.
5. **Cooling correctly** — when we do cool an account, it comes back.
6. **Accounting correctly** — token/cost usage rows are landing (a silent drop is a
   billing blind spot, not a cosmetic issue).
7. **Credentials fresh** — OAuth tokens are being refreshed ahead of expiry, not
   failing mid-request.

### 1.1 Verdict before this work (proven)

| Question | Today | Evidence |
|---|---|---|
| `/metrics` endpoint? | **No** | zero hits for `/metrics` in `src/`, `open-sse/`, `scripts/`, `custom-server.js` |
| Prometheus client library? | **No** — neither used nor installed | zero hits for `prom-client`/`prometheus`; absent from `package.json` deps and `node_modules/prom-client` |
| OpenTelemetry? | **No** — only vendored Next.js internals touch it | own-code hits are the word "remotely" in UI copy; `cli/app/node_modules/next/dist/...` only |
| HTTP surface? | **Yes**, rich | `src/app/api/**` (health, usage, auth, federation, …) |
| Structured logs? | **No** — `console.*` only | `src/sse/utils/logger.js:38` emits `[time] tag symbol message`, human text |
| Correlation id in logs? | **No** — a per-session *emoji colour* is the only correlation | `src/sse/utils/logger.js:16-33`, `open-sse/handlers/chatCore.js:76` |
| Durable state? | **Yes** — SQLite | `src/lib/db/paths.js:6` → `$DATA_DIR/db/data.sqlite`, default `~/.9router/db/data.sqlite` (`src/lib/dataDir.mjs:11`) |

**Verdict: NONE → flying blind.** The gateway makes routing decisions worth millions of
tokens a day and exports zero counters. Every fact an operator needs *already exists in
memory or in SQLite*; none of it is emitted in a scrapeable form.

---

## 2. Where the state already lives (the blind spots)

Each row is a 3am question, the state that answers it, and the reason it is invisible today.

| # | Operator question | State exists at | Why it is invisible |
|---|---|---|---|
| B1 | Is it up? | `src/app/api/health/route.js:9-11` | Returns literally `{ ok: true }` — no DB check, uptime, version or readiness. No boot/version log line either (`custom-server.js:83-86` records `argv`/`dataDir` only) |
| B1b | Is a request **stuck** in flight? | `trackPendingRequest()` keeps per-model and per-account in-flight counts at `src/lib/db/repos/usageRepo.js:154-160` | Process-global (`usageRepo.js:20`), so it *survives* module reload within a process but is never exported; a wedged upstream is invisible |
| B2 | How many requests, per provider/model? | `usageHistory` INSERT in `src/lib/db/repos/usageRepo.js:284` | Written to SQLite; only readable via `/api/usage/stats` JSON (`src/app/api/usage/stats/route.js:8-18`), never as counters |
| B3 | How often do requests **fail**? | Error paths at `open-sse/handlers/chatCore.js:433`, `:507`, `:574` | `appendRequestLog()` is a **no-op** (`usageRepo.js:783` — `export async function appendRequestLog() {}`). Failures never reach `usageHistory`; only `requestDetails`, which is **off by default** |
| B4 | How long does a request take? | Computed at `open-sse/handlers/chatCore/streamingHandler.js:140-143`, `nonStreamingHandler.js:491`; TTFT at `open-sse/utils/stream.js:193` | Computed then **dropped**: `usageHistory` has no latency column (`schema.js:113-128`) and latency is persisted only into `requestDetails.data.latency`, which is gated by `enableObservability` — default **false** (`src/lib/db/repos/settingsRepo.js:43`) |
| B5 | How much failover? | `src/sse/handlers/chat.js:553` `log.warn("FALLBACK", … → NEXT ACCOUNT)` | A single warn line, no counter, no cause label |
| B6 | Are providers rate-limiting us (429)? | Classification table `open-sse/config/errorConfig.js:59-82` (`{status: 429, backoff: true}` at `:81`); cooldown applied at `src/sse/services/auth.js:280-317` | Cooldowns are written to the DB as `modelLock_*` but never counted; the 429 *event* is never counted at all |
| B7 | How many accounts are currently cooling? | `providerConnections.data.modelLock_<model>` / `modelLock___all`, read at `open-sse/services/accountFallback.js:302-307`, gated at `src/sse/services/auth.js:88-104` | A gauge exists implicitly (rows with a future lock expiry) and is never exported. `log.debug("AUTH", "available: N/M")` at `auth.js:106` is debug-level and lost |
| B8 | Is an account dead and not recovering? | `backoffLevel`, `testStatus`, `lastError`, `errorCode`, `lastErrorAt`, `rateLimitedUntil` (`src/lib/db/repos/connectionsRepo.js:6-12`) | Dashboard-only columns; no series |
| B9 | Is token/cost accounting dropping rows? | `open-sse/handlers/chatCore/requestDetail.js:189-192` `console.warn("[USAGE] dropped all-zero usage record …")` — the DF-9ROUTER-33 accounting hole | A warn line in a console. Silent revenue/usage loss |
| B10 | Are OAuth credentials about to expire? | `expiresAt` / `tokenExpiresAt` in connection JSON (`src/lib/db/repos/connectionsRepo.js:8`), read via `getCredentialExpiryMs` (`open-sse/services/oauthCredentialManager.js:28-30`) | The proactive refresher (`src/sse/services/backgroundTokenRefresh.js:9`, `:59-68`) runs every 5 min and logs nothing exportable |
| B11 | Is this instance which build? | `package.json` served via `src/app/api/version/route.js:2` | Never logged at boot; `/api/health` omits it |

### 2.1 Two corollaries that change what gets instrumented

1. **Success and failure are not symmetric in durable state.** `usageHistory` contains
   only successes: chat rows store the DB default `"ok"` (`usageRepo.js:288`) while
   embeddings/systemone/image pass `"success"` explicitly
   (`src/sse/handlers/embeddings.js:152`). **No failure row exists anywhere durable
   unless observability is on.** A metrics endpoint cannot be built by reading the DB
   alone for failures — it must count at the error sites.
2. **Latency exists at exactly one place in memory and nowhere durable when
   observability is off.** A histogram must be recorded at the terminal handlers
   (`streamingHandler.js:140`, `nonStreamingHandler.js:491`), next to where latency is
   already computed. Do not re-measure.

---

## 3. Metric catalogue

Naming: `<product>_<subsystem>_<thing>_<unit>`. Product prefix `router9` is the
Prometheus spelling of `9router`; a metric name may not begin with a digit
(`^[a-zA-Z_][a-zA-Z0-9_]*$`), so **all nine metrics use `router9_`** and the
authoritative `product` label carries the human name `9router`. Reviewers must not have
to guess this translation, so it is stated here and asserted in §6 Q1.

Subsystems: `http` (inbound), `provider` (upstream calls), `routing` (account
selection/failover), `account` (connection health), `usage` (accounting), `config`
(static), `build` (static).

### 3.1 Tier 1 — the minimum viable emission (6 metrics)

These answer "is it up, is it doing work, is it working". Nothing else is worth
emitting until these are live.

| Metric | Type | Unit | Labels | The one question it answers |
|---|---|---|---|---|
| `router9_up` | gauge | 1/0 | (none; `product`, `host`, `instance` injected by prom-client default labels) | Is this gateway instance alive and able to reach its own DB? |
| `router9_http_requests_total` | counter | requests | `endpoint`, `method`, `code_class` | How much traffic is this instance actually serving, and at what outcome grade? |
| `router9_provider_requests_total` | counter | requests | `provider`, `model`, `outcome` | Per-provider/per-model volume and success ratio — is routing working? |
| `router9_provider_request_duration_seconds` | histogram | seconds | `provider`, `kind`=`total`\|`ttft` | How slow is each provider, and how much latency is time-to-first-byte? |
| `router9_provider_in_flight` | gauge | requests | `provider`, `model` | Is a request wedged on an upstream right now? (Cheapest early warning of a hung provider; feeds directly from existing `trackPendingRequest`, `usageRepo.js:154-160`.) |
| `router9_routing_failovers_total` | counter | events | `provider`, `reason`, `from_account_class` | How often does 9router have to walk off an account, and why? |

### 3.2 Tier 2 — depth (6 more metrics)

| Metric | Type | Unit | Labels | The one question it answers |
|---|---|---|---|---|
| `router9_provider_rate_limited_total` | counter | events | `provider`, `model` | Are providers throttling us, and which model is the hotspot? |
| `router9_accounts_locked` | gauge | accounts | `provider`, `scope`=`model`\|`account` | How many accounts are cooling right now? |
| `router9_account_quota_ratio` | gauge | ratio 0–1 | `provider`, `model` | When a quota API reports remaining headroom, how close are we to the wall? |
| `router9_usage_excluded_total` | counter | requests | `provider`, `reason` | Is accounting dropping rows — i.e. are we billing on wrong numbers? |
| `router9_credential_expires_in_seconds` | gauge | seconds | `provider`, `auth_type` | Which credential expires soonest, so refresh can be trusted? |
| `router9_token_refresh_total` | counter | attempts | `provider`, `result`=`ok`\|`error` | Is the proactive refresher working, or silently failing open? |

### 3.3 Tier 3 — static/exposition health (2 gauges + 1 counter)

| Metric | Type | Unit | Labels | The one question it answers |
|---|---|---|---|---|
| `router9_config_require_api_key` | gauge | 1/0 | — | Is this instance enforcing caller auth? (A flipped instance is a security incident, not a config change.) |
| `router9_config_observability_enabled` | gauge | 1/0 | — | Is the opt-in request-detail recorder on in prod? |
| `router9_build_info` | gauge | 1 | `version`, `node_version` | Which build and runtime is this instance? |

### 3.4 Label discipline (non-negotiable)

**Allowed label values are enumerated and closed.** These are the only labels that may
vary; adding one is an API change to this spec.

- `provider` — the canonical provider id from the registry (`open-sse/providers/registry/`), lowercased. Bounded (~40 today).
- `model` — provider model id **as configured**. Bounded in practice; if a deployment
  allows arbitrary pass-through model strings, cap with a `model="other"` bucket when
  the distinct set exceeds 200 per hour and record the overflow count on
  `router9_provider_requests_total{model="other"}`.
- `endpoint` — the **route template**, not the path: `/v1/chat/completions`,
  `/v1/embeddings`, `/v1/systemone`, `/v1/images/generations`, `/v1/audio/*`,
  `/v1/models`. Never a concrete path.
- `method` — `GET`/`POST`/`OPTIONS`.
- `code_class` — `2xx`/`3xx`/`4xx`/`5xx`. Never a raw status code.
- `outcome` — `success`/`error`/`client_error`/`timeout`.
- `reason` — closed set: `rate_limit`, `quota`, `auth`, `not_found`, `transient`, `protocol`, `unknown`.
- `from_account_class` — `priority_tier` label value (an integer tier), never a connection id.
- `auth_type` — `oauth`/`apikey`/`service`.
- `result` — `ok`/`error`.

**Forbidden in any label, always:** connection/account id, api key, email, user id,
session id, request id, prompt/completion text, model output, file path, URL,
timestamp, error message. Error *text* lives in logs; metrics carry the *class*.

Rationale for `from_account_class`: failover is a cardinality bomb if labelled by
account. An operator diagnosing one bad account uses the logs (`chat.js:553` already
names it) or the dashboard, not Prometheus. This is a deliberate trade — see §5.

---

## 4. Exposure mechanism

### 4.1 The chosen mechanism: `GET /metrics` on the existing server, via `prom-client`

**Decision: a `prom-client` `Registry` exposed at `GET /metrics` through a Next.js
route handler at `src/app/api/metrics/route.js`, scoped with labels, plus a default
label set `{ product: "9router", host, instance }`.**

Why this and not the alternatives:

- **Not `/api/health`.** It is already public and unauthenticated
  (`src/dashboardGuard.js:31-32` lists `/api/health` in `PUBLIC_API_PATHS`) but returns
  a fixed body by design; overloading it would couple an uptime probe to metric
  rendering and break its contract.
- **Not scrape-only `/metrics` on port 20128 without thought.** Next.js owns that
  router; the Next route handler is the *supported* seam (see §4.2 for the gate).
- **Not Pushgateway for the counters.** The counters are process-scoped increments in a
  long-lived process; pushgateway semantics (last-write sticky gauges) actively corrupt
  counters under 7 instances. Pushgateway is right for cron jobs, not for this.
- **`prom-client` is the Node equivalent of `client_golang`/`prometheus_client`** and is
  the correct choice. It is **not currently installed** — adding it is part of row 1,
  and `prom-client` has no native dependencies, so it does not disturb the
  `serverExternalPackages` list in `next.config.mjs`.

### 4.2 The `/metrics` route must be explicitly gated — this is load-bearing

Adding `src/app/api/metrics/route.js` without touching `src/dashboardGuard.js` will
make it **require dashboard auth** and return 401 to Prometheus. The route must be added
to `PUBLIC_API_PATHS` (`src/dashboardGuard.js:31-48`) **and** protected by its own
bearer/shared-secret check inside the handler, mirroring how `/v1` carries its own key
auth (`src/sse/handlers/chat.js:207-219`). `/metrics` reveals provider mix, model names
and volume — it must never be open to the internet. A worker who "exposes `/metrics`"
and sees 401 has not verified anything.

### 4.3 Two constraints that shape the implementation

1. **Next.js bundles each route separately.** Counters must live in a module instantiated
   **once per process**, not per route — i.e. a singleton in `src/lib/metrics/registry.js`
   holding the `Registry` and all metric objects, imported by every call site **and** by
   the `/metrics` handler. Reading metrics from SQLite on scrape instead is *also*
   acceptable for B2 (volume) but cannot substitute for counters at the error sites.
2. **The 7 instances each scrape with their own scrape generation of counters.** Counters
   restart at 0 on deploy, which is correct Prometheus behaviour. Do **not** try to
   persist counters across restarts; use `rate()`/`increase()` in PromQL and accept the
   reset. Sums across instances are only valid on the `*_total` families.

### 4.4 Timing: histogram buckets are not free

`router9_provider_request_duration_seconds` is one histogram family with two `kind`
values. Use buckets sized to LLM reality, not web-default noise:
`0.1, 0.25, 0.5, 1, 2.5, 5, 10, 20, 40, 80, 160` seconds (seconds, not ms — Prometheus
convention is base units). The `kind="ttft"` series will land in the low buckets;
`kind="total"` in the high ones. Cardinality per provider = 2 × 11 buckets = 22 series,
times ~40 providers ≈ 880 — **the largest family by far**. Consider dropping `model`
from the histogram (already omitted) and keeping it on the counter only.

---

## 5. Collection path (fleet-monitor)

The fleet Prometheus **pulls** these; agents may also `remote_write` their own
gateway-side data, but 9router's counters must come from a **scrape**, because a
`remote_write` from inside the app would need a Prometheus client plus a durable push
loop that itself needs monitoring.

**Required scrape job** on `fleet-monitor` (in
`/root/fleet-monitoring/prometheus/prometheus.yml` — owned by the monitoring stack, not
by this repo; filed as a row with the exact block):

```yaml
  # 9router LLM gateway — one target per production instance (7 today)
  - job_name: 9router
    metrics_path: /metrics
    scheme: http
    scrape_interval: 30s
    scrape_timeout: 10s
    static_configs:
      - targets:
          - '9router-1:20128'      # replace with real instance addresses
          # … one entry per instance …
        labels:
          product: '9router'
          service: 'llm-gateway'
```

- Scrape interval **30s** (not 15s): provider traffic is bursty and the histogram is the
  largest family; 15s doubles write load for no new information.
- **`host` is injected per-target by Prometheus** (`instance`/`host` in relabelling), not
  by the app — the app cannot know which box it is on reliably. `product` and `service`
  are static config labels here, matching the app's own `product` default label so both
  agree.
- Per-account labels: see §3.4 — accounts are **not** a Prometheus label. Per-connection
  diagnostics stay in `/api/usage/[connectionId]` and the dashboard.

### 5.1 What the fleet agent already does

The agent-side `bunker_*`/`fleet_*` series the fleet already receives describe the
**host**, not the product. `/metrics` from 9router is additive: no existing agent series
should be renamed, and no existing exporter should be made to scrape 9router on the
product's behalf.

---

## 6. Verification — the exact commands a reviewer runs

A metric is **done** only when the command below is run against a live instance and
returns the stated shape. "The worker said so" is not evidence.

**Q1 — endpoint serves the tier-1 families** (structural proof, works before any traffic):

```bash
curl -fsS http://9router-1:20128/metrics -H 'Authorization: Bearer $METRICS_TOKEN' \
  | grep -E '^(router9_(up|http_requests_total|provider_requests_total|provider_request_duration_seconds|routing_failovers_total))'
# PASS: all named families print; no name begins with a digit.
```

**Q2 — up gauge is live and flips.** Against a live instance:
`router9_up == 1`. Then stop one instance and within 90s
`up{job="9router"} == 0` for that target. PASS: the down instance disappears from
`router9_up` scrapes and `up` records 0.

**Q3 — traffic is counted** (drives one real request through the gateway, then):

```promql
sum by (provider) (rate(router9_provider_requests_total[5m])) > 0
```
PASS: the provider used by the test request appears with a non-zero rate, and
`sum(rate(router9_provider_requests_total{outcome="success"}[5m])) / sum(rate(router9_provider_requests_total[5m]))`
is > 0.9 on a healthy instance.

**Q4 — latency percentile is real, not a constant** (this is the one that catches a
fake histogram):

```promql
histogram_quantile(0.50, sum by (le, provider) (rate(router9_provider_request_duration_seconds_bucket{kind="total"}[10m])))
histogram_quantile(0.50, sum by (le, provider) (rate(router9_provider_request_duration_seconds_bucket{kind="ttft"}[10m])))
```
PASS: p50 is plausible (hundreds of ms, not 0.1s or 160s), `ttft` < `total` for the same
provider, and the value **moves** across two 10-minute windows. A histogram stuck at a
single bucket has leaked its buckets or is unfed — fail it.

**Q5 — failure path is counted** (the finding that `usageHistory` cannot answer this):

```promql
sum(rate(router9_provider_requests_total{outcome="error"}[5m])) > 0
```
after forcing one upstream error (invalid model against a configured provider).
PASS: the counter increments **and** `router9_provider_requests_total{outcome="success"}`
does not. If only the DB row appears, the counter was wired at the success site only.

**Q6 — nothing is stuck (in-flight gauge is fed and drains):**

```promql
max by (provider) (router9_provider_in_flight)
```
PASS: the value tracks live concurrency (non-zero during a streamed request) and returns
to 0 within 60s of it finishing. A series that never returns to 0 after traffic stops is
a leaked `trackPendingRequest` — the exact wedge this gauge exists to catch.

**Q7 — 429 counting:**

```promql
sum by (provider) (increase(router9_provider_rate_limited_total[1h]))
```
PASS: non-zero for at least one provider over 24h of real traffic (if zero for all
providers over 24h while `increase(router9_routing_failovers_total{reason="rate_limit"}[24h])` is also zero, the label is probably not wired — check both before declaring "no throttling").

**Q8 — locked-account gauge matches the DB** (cross-source agreement):

```promql
sum(router9_accounts_locked)
```
```
sqlite3 ~/.9router/db/data.sqlite \
  "select count(*) from providerConnections where data like '%modelLock_%' and isActive=1;"
```
PASS: the two counts agree within a scrape interval. A persistent divergence is a bug in
the gauge, not in the DB.

**Q9 — accounting holes are visible:**

```promql
sum by (provider) (increase(router9_usage_excluded_total[1h]))
```
PASS: series exists for every provider that has traffic (a zero series is a pass and
proves the hook is wired); a non-zero value names a provider losing usage rows.

**Q10 — credentials:**

```promql
min by (provider) (router9_credential_expires_in_seconds)
```
PASS: no provider trends monotonically to 0 and then resets via error —
`router9_token_refresh_total{result="ok"}` must be incrementing for it, i.e. refresh
happens *before* expiry (the refresher's 30-minute lead is
`src/sse/services/backgroundTokenRefresh.js:9`).

**Q11 — endpoints reached Prometheus at all** (the fleet-level gate that the product
cannot self-certify):

```promql
count(count by (product) ({__name__=~"router9_.*"}))
```
PASS: ≥ 1, and `count(up{job="9router"})` equals the number of production instances.

**Definition of done for a tier:** every query in that tier run against production,
pasted with its output, plus the row's `ACCEPTANCE` line satisfied.

---

## 7. Deliberately NOT instrumented

| Excluded | Why |
|---|---|
| Account/connection id, api key, email as labels | Unbounded and sensitive. `apiKeys.key` is a bearer secret in `schema.js:81`; exporting it as a label would publish credentials to every scraper. Per-account diagnosis uses the dashboard and `/api/usage/[connectionId]`. |
| Prompt, completion, request body, response body | Cardinality and data protection. Bodies are already captured deliberately, opt-in and *only* under `ENABLE_REQUEST_LOGS` (`open-sse/utils/requestLogger.js:5`) — a different consent surface from metrics. |
| Request/session/correlation id as a label | Unbounded by definition. Trace-level correlation belongs in Tempo, not Prometheus. |
| Error message text as a label | Free-form and unbounded (`src/sse/services/auth.js:307` truncates to 200 chars into `lastError`). Metrics carry `reason` class only; text stays in logs. |
| Per-model cost as a metric | Cost is recomputed at write time from a pricing table (`usageRepo.js:248`) and is a business figure, best served by `/api/usage` and rollups — not by a scrape-time counter that would double-count restarts. Emit *tokens* if cost tracking is wanted (see row 5). |
| Per-tenant/per-key quota state | 9router has no tenant quota concept today; inventing a metric for it would be fiction. |
| Process memory/GC/event-loop | Already covered by `cAdvisor`/node exporter; duplicating them adds no information and invites disagreement between two sources. |
| `/api/health` body changes | Its fixed `{ ok: true }` is consumed by probes; changing it is a compatibility risk. Version/uptime belong on `/metrics` and `/api/version`. |

---

## 8. Row map (board lane `monitoring`)

| Row id | Tier | Scope |
|---|---|---|
| `OBS-9ROUTER-1` | 1 | `/metrics` endpoint + registry + `/metrics` auth gate + the 6 tier-1 metrics |
| `OBS-9ROUTER-2` | 2 | 429 + locked-account gauge + quota ratio (B6, B7, B8) |
| `OBS-9ROUTER-3` | 2 | accounting + credential + refresh counters (B9, B10) |
| `OBS-9ROUTER-4` | 3 | config/build gauges (B11), boot log with version+port |
| `OBS-9ROUTER-5` | — | PromQL recording/alerting rules + Grafana dashboard consumed from these families |
| `OBS-9ROUTER-6` | — | fleet-monitor scrape job + fleet-level verification (Q11) |

Rows live in `.coding-hermes/board/tasks.jsonl` with the spec path in `detail`.

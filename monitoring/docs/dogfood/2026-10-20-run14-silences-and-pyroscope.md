# Monitoring dogfood run 14 — operator silencing + the pyroscope surface (same tick, second angle)

Date: 2026-10-20 (same tick as runs 12/13; both landed earlier today, cited as siblings)
Target commit at run time: 70e32609d62de9ab28989dfc90d00812a74891f6
Surfaces: Alertmanager silence lifecycle (never driven by any prior run) and the
continuous-profiling (pyroscope) surface (never driven, never documented).

## Promise

An operator who is being paged by a chronic alert can silence it from the stack's own
API, see the silence take effect, and remove it — and the fleet's perf lane can confirm
that profiles are arriving.

## Leg A — silence lifecycle (operator's core tool): WORKS

`MON-GAP-029`'s own standing recommendation is to silence the 16-day stale probe target
until the fleet-slot decision is made. Nobody had driven that path, so I did — time-boxed
and reverted in the same run (self-expiring `endsAt` = +120 s, explicit DELETE, both
verified). All measurements on the host:

| step | result |
|---|---|
| `POST /api/v2/silences` (matchers `alertname=TargetUnreachable` + `host=standby-cx53-01-2147`) | **200 in 4.1 ms**, `silenceID bf61c8c2-…` |
| `GET /api/v2/silences` | entry present, `state active`, matchers correct, `endsAt` honoured |
| `GET /api/v2/alerts` during the silence | `status.silencedBy=[bf61c8c2…]` on **both** `100.79.83.6:10001/:10002` alerts; the control alert (`DiskWillFillIn24h` bunker-mvp) stayed `[]` — no over-broad match |
| router counters across a 60 s window | every delta **0** |
| `DELETE /api/v2/silence/<id>` | **200**, and `silencedBy` cleared on both alerts |

Honest limit on the counter row: this receiver's route has `group_wait 30s`,
`group_interval 5m`, `repeat_interval 12h`, so a 60 s window **cannot** prove notification
suppression by counting router deliveries. The mechanism proof is `silencedBy`; suppression
of future notifications follows from Alertmanager's contract, not from my window.

Two operator facts worth writing down (both now in the project skill):

- **The silence lives in Alertmanager, not in the alert-router.** The router has no
  silence surface at all (`router.py` never reads silences; rows are minted from webhooks
  AM chooses to send). MON-GAP-029's phrasing "a silence for that host at the alert-router"
  is imprecise; the fix shape still works, the surface is `/api/v2/silences` on :9093.
- **A deleted silence is kept as an expired record.** After DELETE, `GET /api/v2/silences`
  still lists it with `status.state=expired` (0 active). My probe left exactly one such
  expired record; it suppresses nothing.

A silence is a **stopgap, not the row's fix**: it lapses and the stale target re-mints a P0
the moment it does. That is why the event I appended to MON-GAP-029 keeps the owner
decision open rather than closing anything.

## Leg B — pyroscope: deployed, ingesting, undocumented, and the documented probe 404s

The stack ships `mon-pyroscope` (`grafana/pyroscope:1.9.0`, published `0.0.0.0:4040`) and it
**is** receiving profiles — but the fleet's perf skill tells every perf lane to run
`curl http://<pyroscope>:4040/pyroscope/api/v1/labels` to "confirm profiles are arriving",
and that URL is a plain 404 here:

```
GET  /ready                                        -> 200 "ready"
GET  /api/v1/status/buildinfo                      -> 200 {"version":"1.9.0","revision":"7905837ea"}
GET  /metrics                                      -> 200, 345 587 B
POST /querier.v1.QuerierService/ProfileTypes {}    -> 200, 1839 B (block/goroutines/memory/...)
POST /querier.v1.QuerierService/Series {"matchers":[]} -> 200, 7752 B labelsSet (__name__=block …)
GET  /pyroscope/api/v1/labels                      -> 404  "404 page not found"
GET  /api/v1/labels                                -> 404  {"code":5,"message":"Not Found"}
Grafana /api/datasources/uid/pyroscope/health      -> {"message":"Data source is working","status":"OK"}
mon-pyroscope log                                  -> hourly "head successfully written to block",
                                                      latest 2026-10-20T04:25:32Z + a ProfileTypes query
```

`grep -r pyroscope` over the repo's README/docs/skills tree returns nothing, so the working
probe set exists nowhere a lane or operator could find it. Filed as `MON-DOGFOOD-045` (P3,
docs + one version note).

## Step 2b — what using it costs

| operation | measurement | verdict |
|---|---|---|
| AM `/api/v2/alerts` (on-host, warm ×8) | 1.54–2.11 ms | instant |
| AM `/api/v2/silences` (on-host, warm ×8) | 1.26–2.54 ms | instant |
| `POST /api/v2/silences` (the mutation) | 4.1 ms | instant |
| router `/health` (on-host ×8) | 1.75–2.64 ms | instant |
| Prometheus `/api/v1/alerts` from the operator box (hyperfine, warm ×8) | **370.2 ms ± 4.9 ms** (min 365.2) | tailnet RTT-bound; identical to run 12's 380.1 ms ±13.0 |

Nothing here is slow enough for a user to notice → **no PERF row this run** (PERF-1, filed
earlier today, remains the drain cost and is unaffected by this leg).

## Verdict

**SHIPPABLE for the operator's silencing tool** — create/verify/delete all work, matching is
precise, cleanup is verifiable, and the whole cycle costs single-digit milliseconds.
**UNKNOWN-VALUE → now known for pyroscope**: the surface works and is ingesting; its
discoverability is the defect (P3 filed). No new defect found in the silence path itself.

Left behind: row MON-DOGFOOD-045, an event on MON-GAP-029 carrying the verified silence
recipe + cadence facts, this report, a run-14 log entry, and the project skill's silence and
pyroscope sections. No code, no board row, and no scheduler state changed by this run; the
one prod mutation (a 120-second silence on the known-noise alert) was reverted in-run and is
disclosed above.

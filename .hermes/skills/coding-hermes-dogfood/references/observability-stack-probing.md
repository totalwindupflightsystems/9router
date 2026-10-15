# Probing an observability stack's ingest/query surfaces (metrics, logs, traces)

Depth for the dogfood loop when the target ships a monitoring/telemetry surface
(Prometheus/Loki/Tempo/Grafana-class). Real use = push REAL telemetry through the
ingest surface, then verify each downstream leg separately — never grade the
surface by its health endpoints or its dashboards' existence.

## Push real telemetry, then verify every downstream leg separately

The canonical end-to-end probe for a traces surface (same shape for logs/metrics):
1. Craft a genuine OTLP/JSON span (random trace id, distinctive `service.name` you
can grep for later) and POST it to the published OTLP HTTP port `/v1/traces`.
A 200 with `{"partialSuccess":{}}` is the ingest contract working.
2. Query the storage API by trace id AND by tag (`resource.service.name="<probe>"`)
— both must return the probe. If one query dialect fails and another works, prefer
the `resource.`-prefixed attribute form before filing a parse error as a defect:
check which form the docs teach.
3. Drive the UI's datasource: POST the datasource's query API (TraceQL frame)
and check its `/health` — provisioned datasource + healthy backend + working
query are three separate claims.
4. Confirm the metrics-generator leg: query Prometheus for
`{source="tempo"}`-style span-metrics carrying the probe's service label. This
proves the remote_write wiring, not just the store.
5. Correlation surfaces (trace<->log links) need a JOIN KEY to exist: grep the
log store for the probe's trace id. If the only hit is the observability tool's
own access log, no producer emits the key — the provisioned links are dead UI
for every user, which is its own row (separate from 'correlation not configured').

Give every probe line a UNIQUE marker (service/span name) so later greps cannot
match a sibling's probes or stale data.

## Attribute port ownership from the runtime, not the config files

Compose port maps and in-config comments drift: a pipeline block commenting
'the host's 4317/4318 map through compose to the Alloy container' can sit next
to a compose file that maps those ports to Tempo directly — the block is dead
config and the comment misleads every reader about the ingest path. Verify with
`docker inspect <container> --format '{{json .NetworkSettings.Ports}}'` on the
containers that COULD own the port, and diff against the compose file AND the
config comments before describing the topology in any finding. Dead config whose
text asserts the wiring is a docs finding even when the actual path works.

## 'Shipped but unused' is visible in the product's own counters

Before assuming a surface is exercised, read its own telemetry: a metrics
generator reporting zero active series for its whole uptime, an ingest counter
at zero, an empty search index — the surface has never received real data, so
your probe is its first real use and every defect you hit is untested-path
defect, not a fluke. Quote the zero-counter uptime in the row.

## Published ingest vs loopback query: plan the access path first

Telemetry stacks commonly publish ingest ports on 0.0.0.0 (agents push from
everywhere) while keeping query APIs and UIs loopback-only (they are reached
through the tailnet/ssh or the co-located Grafana). Map this BEFORE probing:
remote curl works for ingest, but query legs go via `ssh <host> curl
127.0.0.1:<port>` or the UI's datasource-proxy API. A 'connection refused' on a
query port from the control host is the bind policy working, not the product
being down — and a UI bound to 0.0.0.0 on a SHARED control host is likely a
DIFFERENT project's container (check `docker ps` + the actual container name
behind the local port before attributing any response to the target stack).

## Grade the UI's cross-links by their join keys, not their presence

Datasource provisioning files can carry rich cross-linking (trace->logs
`tracesToLogs`, log-line 'Open trace' matchers, service-map datasources). Each
is a PROMISE that needs data to fire: check whether any real producer emits the
join key (trace ids in log lines, matching labels on metrics). Provisioned but
structurally-unfireable links get their own row with fix direction 'wire a real
producer or document the link as future-facing', never 'remove the links'.

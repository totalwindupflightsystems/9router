# Tempo + OTLP verification recipe

Proven end-to-end test for the Tempo store + Alloy OTLP receiver + Grafana datasource wiring.

## Pre-flight

Confirm the three components are up:
```
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}' | grep -E 'tempo|alloy|grafana'
```
Expected: `mon-tempo` (ports 3200, 4317-4318), `mon-alloy` (port 12345), `mon-grafana` (port 3000).

Wait ~15s after `mon-tempo` starts, then confirm readiness:
```
curl -s http://localhost:3200/ready   # must return 'ready' (not 'Ingester not ready...')
```

## Alloy OTLP receiver (already wired)

The Alloy config at `/root/fleet-monitoring/stack/alloy/config.alloy` already contains:
```
otelcol.receiver.otlp "traces" {
    grpc { endpoint = "0.0.0.0:4317" }
    http { endpoint = "0.0.0.0:4318" }
    output { traces = [otelcol.processor.batch.traces.input] }
}
otelcol.exporter.otlp "tempo" {
    client { endpoint = "tempo:4317" ... }
}
```
No Alloy changes needed for basic Tempo wiring.

## Grafana Tempo datasource (provisioned as code)

File: `/root/fleet-monitoring/stack/grafana/provisioning/datasources/datasources.yml`
```
- name: Tempo
  uid: tempo
  type: tempo
  access: proxy
  url: http://tempo:3200
  jsonData:
    tracesToLogs:
      datasourceUid: loki
```
Never hand-edit this in the Grafana UI.

## End-to-end trace test

1. POST a synthetic trace via OTLP HTTP:
```
curl -s http://localhost:4318/v1/traces -X POST \
  -H "Content-Type: application/json" \
  -d '{"resourceSpans":[{"scopeSpans":[{"spans":[{"traceId":"0123456789abcdef0123456789abcdef","spanId":"0123456789abcdef","name":"test-span","startTimeUnixNano":"1609459200000000000","endTimeUnixNano":"1609459201000000000"}]}]}]}'
```
Expected response: `{"partialSuccess":{}}` (empty partialSuccess = full success).

2. Wait ~3s, then retrieve by traceId:
```
curl -s "http://localhost:3200/api/traces/0123456789abcdef0123456789abcdef"
```
The response JSON contains the trace, but the `traceId` field is returned **base64-encoded** (e.g. `ASNFZ4mrze8BI0VniavN7w==`), not as the original hex. Match by span name (`test-span`) and structure, not by literal traceId string.

## Acceptance for MON-GAP-001

All four must hold:
- `mon-tempo` container Up, `/ready` returns 'ready'
- OTLP POST returns `{"partialSuccess":{}}`
- GET `/api/traces/<id>` returns a JSON body containing the test-span
- Grafana datasource file exists with `uid: tempo`, `type: tempo`, `url: http://tempo:3200`

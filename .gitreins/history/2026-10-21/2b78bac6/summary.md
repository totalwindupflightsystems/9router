# Verdict: MON-GAP-029

**Task:** Repoint stale standby-cx53-01-2147 probe target to the live slot IP
**Evaluated:** 2026-10-21T21:09:27.366897
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✗ tests: scanners: nice=nice -n 10
  ✗ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ lint: scanners: nice=nice -n 10
- ✓ **tier2**
  - COMPLETE
  ✓ probe-targets.json slot-01 entries name 100.122.57.93 for ports 10001 and 10002 AND a live Prometheus query shows probe_success=1 for both new targets AND zero TargetUnreachable alerts remain in Prometheus and Alertmanager AND the decision note blocks regeneration from the stale generator: (1) probe-targets.json slot-01 entries: commit 007ee54da:monitoring/fleet-monitoring/stack/prometheus/probe-targets.json has {"targets":["100.122.57.93:10001"], labels.host=standby-cx53-01-2147} and {"targets":["100.122.57.93:10002"], same host}; live file /root/fleet-monitoring/prometheus/probe-targets.json on fleet-monitor (100.122.154.108) matches exactly and `grep -c 100.79.83.6` = 0 (dead IP gone). (2) Live Prometheus query http://100.122.154.108:9090/api/v1/query?query=probe_success{host="standby-cx53-01-2147"} returned 100.122.57.93:10001 = 1 and 100.122.57.93:10002 = 1. (3) Zero TargetUnreachable alerts: /api/v1/rules shows rule TargetUnreachable state=inactive, alerts=0; /api/v1/alerts total=0; Alertmanager (127.0.0.1:9093/api/v2/alerts on fleet-monitor) returned [] (count 0). (4) Decision note: probe-targets.README.md (repo + live /root/fleet-monitoring/prometheus/probe-targets.README.md) states 'DO NOT regenerate prometheus/probe-targets.json from scripts/generate-probe-targets.py until the generator+inventory pipeline is fixed'. Verified the block is justified: running the generator against the default snapshot inventory/2026-09-27 emits 8 targets including 2 occurrences of the dead 100.79.83.6, while inventory/2026-10-20 emits 0 targets — regeneration would reintroduce the stale IP or silence the blackbox lane. No test suite applies (config-only/monitoring-data change); verification was done via live Prometheus/Alertmanager API queries and generator dry-runs.
Slot-01 probe targets repointed to 100.122.57.93:10001/:10002 with live probe_success=1 on both, zero TargetUnreachable alerts in Prometheus and Alertmanager, and a decision note that demonstrably blocks regeneration from the stale generator.

## Summary

Judge Result: MON-GAP-029

Stage tier1: FAIL
    ✗ tests: scanners: nice=nice -n 10
  ✗ secrets: secrets: harness state excluded from gitleaks scope (.gitreins/**)
  ✗ lint: scanners: nice=nice -n 10

Stage tier2: PASS
  COMPLETE
  ✓ probe-targets.json slot-01 entries name 100.122.57.93 for ports 10001 and 10002 AND a live Prometheus query shows probe_success=1 for both new targets AND zero TargetUnreachable alerts remain in Prometheus and Alertmanager AND the decision note blocks regeneration from the stale generator: (1) probe-targets.json slot-01 entries: commit 007ee54da:monitoring/fleet-monitoring/stack/prometheus/probe-targets.json has {"targets":["100.122.57.93:10001"], labels.host=standby-cx53-01-2147} and {"targets":["100.122.57.93:10002"], same host}; live file /root/fleet-monitoring/prometheus/probe-targets.json on fleet-monitor (100.122.154.108) matches exactly and `grep -c 100.79.83.6` = 0 (dead IP gone). (2) Live Prometheus query http://100.122.154.108:9090/api/v1/query?query=probe_success{host="standby-cx53-01-2147"} returned 100.122.57.93:10001 = 1 and 100.122.57.93:10002 = 1. (3) Zero TargetUnreachable alerts: /api/v1/rules shows rule TargetUnreachable state=inactive, alerts=0; /api/v1/alerts total=0; Alertmanager (127.0.0.1:9093/api/v2/alerts on fleet-monitor) returned [] (count 0). (4) Decision note: probe-targets.README.md (repo + live /root/fleet-monitoring/prometheus/probe-targets.README.md) states 'DO NOT regenerate prometheus/probe-targets.json from scripts/generate-probe-targets.py until the generator+inventory pipeline is fixed'. Verified the block is justified: running the generator against the default snapshot inventory/2026-09-27 emits 8 targets including 2 occurrences of the dead 100.79.83.6, while inventory/2026-10-20 emits 0 targets — regeneration would reintroduce the stale IP or silence the blackbox lane. No test suite applies (config-only/monitoring-data change); verification was done via live Prometheus/Alertmanager API queries and generator dry-runs.
Slot-01 probe targets repointed to 100.122.57.93:10001/:10002 with live probe_success=1 on both, zero TargetUnreachable alerts in Prometheus and Alertmanager, and a decision note that demonstrably blocks regeneration from the stale generator.

Overall: FAIL ✗

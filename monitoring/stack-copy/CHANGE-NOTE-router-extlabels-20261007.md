# Change note: alert-router external-label fix (2026-10-07)

## Problem
Every firing alert forwarded by Alertmanager was silently pre-resolved into a spool
fan-out row instead of landing on its owning board as a PENDING finding. Evidence:
`docker logs mon-alert-router` shows 47 `pre-resolved:` lines in 48h, 0 `spooled row`
lines, 0 `resolved_suppressed_total`, while TargetUnreachable on standby-cx53-01-2147
was firing continuously and `ALERTS{...}` matched in Prometheus when queried by hand.

## Root cause
Prometheus's `prom_label_matchers()` (router.py) builds the state-check selector
`ALERTS{...}` from the webhook alert's labels. Alertmanager injects its own
external label `monitor="fleet-monitoring"` into every alert it forwards, but that
label exists ONLY on the Alertmanager side — Prometheus never puts external labels
on its own ALERTS series. The matcher `monitor="fleet-monitoring"` therefore matched
nothing, `prom_alert_firing()` returned False ("not firing"), and handle_alert()
took the pre-resolved path (MON-GAP-017 logic) for every real firing alert.

## Fix
Drop Alertmanager-injected external label keys (AM_EXTERNAL_LABELS = {"monitor"})
from the selector in `prom_label_matchers()`. Two-line change + blocklist constant
+ comment. No behavior change for the resolved-path prom_target_up guard.

## Deploy
- Backups: `/root/fleet-monitoring/alert-router/router.py.bak-pre-extlabels-20261007`
  and `/root/fleet-monitoring/stack/alert-router/router.py.bak-pre-extlabels-20261007`
- Patched BOTH trees (top-level alert-router/ build context and stack/alert-router/
  mirror); trees md5-identical: 47e47450c8c160bc3510526ed943a8cd
- `docker compose build alert-router && docker compose up -d --force-recreate alert-router`
  (source is baked into the image — restart alone would not pick it up)
- Deployed-ness proof: `docker exec mon-alert-router grep -c AM_EXTERNAL_LABELS /app/router.py` = 2

## Verification
1. In-container unit check: router.prom_label_matchers() now emits the selector
   WITHOUT monitor=...; `prom_alert_firing()` returns True for the live cx53 alert.
2. Synthetic webhook gate (the weak half): POSTed an Alertmanager-shaped payload
   with the cx53 labels + monitor external label to :8089/webhook (Bearer from .env,
   sourced not echoed) — router spooled `MON-MONITORING-B316017D-20261007` as a
   PENDING finding (previously the same fingerprint produced only -RESOLVED rows).
   NOTE: this does not exercise the real rule->Alertmanager hop.
3. Spool hygiene: removed the 5 false `-RESOLVED` rows (cx53 host never recovered —
   `max_over_time(probe_success{host="standby-cx53-01-2147"}[6h])` = 0; OOMKillsLowPressure
   bunker-mvp is a benign memcg-scoped flake twin) — removed only after each base
   fingerprint was confirmed present on the lane board (B316017D/AC991D47/FA5F538B all
   on board). Backup: `board-rows.jsonl.bak-20261007-extlabel-fix`. Truncate preserved
   router uid 10001 ownership. Router healthy after truncate.
4. Drained: appended=1 (the genuine pending cx53 finding MON-MONITORING-B316017D-20261007),
   skipped=0. Board read-back: 2 occurrences of the id (base + prior fan-out rows).

# 05 — Contradiction register

```yaml
id: C-001
kind: seed-vs-derivation
parties: [D-017, D-023, D-024, ESC-01, ESC-02]
competing_claims:
  - "Do not lose any relevant file change and report whenever the tool has stopped working."
  - "Keep the system on one box with no independent durable observer or external heartbeat."
evidence:
  - "Owner seed in 00-seed.md."
  - "A stopped or powered-off host cannot observe a create-delete event or emit its own outage notification."
affected_decisions: [D-001, D-002, D-011, D-012, D-017, D-023, D-024]
detected_by: "§5 break-check and cascade"
owner: "product owner"
containment_default: "Guarantee RPO=0 for committed local transactions and reconciliation for files still present; cover process/service failure locally; make no whole-host claim. Expires before implementation acceptance."
status: OPEN
resolution: ""
resolved_date_or_trigger: ""
```

The conflict is not blended. ESC-01/02 compare the two genuinely owner-owned priority axes and the autonomous defaults choose the most reversible one-box branches. C-001 blocks handoff readiness.

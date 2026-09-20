# 08 — Open questions register

```yaml
id: U-001
question: "What are the target root count, file count, churn, largest directory, free disk, and acceptable scan duration?"
why_unanswered: "No target inventory was supplied."
owner: "operations/performance owner"
deadline_or_trigger: "Before production and before numeric watchdog/resource thresholds."
blocking_class: BEFORE-SHIP
containment_default: "Stream one root at a time and make no hard capacity claim; expires after target soak."
evidence_to_close: "Target inventory plus three cold/warm/churn runs with p50/p95 duration, peak RSS, DB/staging bytes, and free-space use."
decisions_affected: [D-002, D-004, D-005, D-008, D-011, D-016, D-018, D-022]
```

```yaml
id: U-002
question: "Which destination receives digests/failures, and what auth, payload, size, timeout, and idempotency contract does it expose?"
why_unanswered: "No destination exists in the seed; this is integration evidence, not owner research homework."
owner: "integration owner"
deadline_or_trigger: "Before live posting."
blocking_class: BEFORE-SHIP
containment_default: "Keep durable local outbox rows and a generic bounded HTTPS seam; make no remote-delivery claim."
evidence_to_close: "Redacted synthetic POST transcript plus endpoint documentation and repeated idempotency probe."
decisions_affected: [D-007, D-012, D-019, D-022]
```

```yaml
id: U-003
question: "May root-relative filenames leave the host?"
why_unanswered: "Sensitivity depends on the watched workflow and destination."
owner: "security/product owner"
deadline_or_trigger: "Before live posting."
blocking_class: BEFORE-SHIP
containment_default: "Use count-only mode; expires when representative names are classified and path_mode is approved."
evidence_to_close: "Written sample classification and approved relative/basename/count-only mode."
decisions_affected: [D-013, D-019, D-022]
```

```yaml
id: U-004
question: "Does the actual target provide supported Python/SQLite/systemd/filesystem semantics and service-user access?"
why_unanswered: "The exercise host was probed but is not declared the deployment target."
owner: "implementation/runtime owner"
deadline_or_trigger: "BEFORE-BUILD when target host or image is identified."
blocking_class: BEFORE-BUILD
containment_default: "Keep D-014 provisional and preserve DB/config/adapter contracts for a possible Go port; expires on target probe."
evidence_to_close: "Target versions, filesystem type, fsync/rename fault probe, and sandbox permission smoke test."
decisions_affected: [D-005, D-009, D-011, D-014, D-015, D-018]
```

```yaml
id: U-005
question: "Must backup protect against schema/operator mistakes only, or total local disk/host loss?"
why_unanswered: "The seed says crash survival, not media-disaster RPO."
owner: "operations/product owner"
deadline_or_trigger: "Before backup policy sign-off or when disk-loss RPO is stated."
blocking_class: DEFER
containment_default: "Daily verified same-box snapshot with explicit no-media-loss guarantee; expires on approved off-box destination/RPO."
evidence_to_close: "Named RPO/RTO and restore rehearsal."
decisions_affected: [D-016, D-018, D-020]
```

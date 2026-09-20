# 09 — Assumption register

| ID | Assumption | Evidence | Falsifier | When tested | Decisions affected | Containment |
|---|---|---|---|---|---|---|
| A-001 | Relevant files remain until a completed reconciliation. | Hourly digest suggests retained artifacts, not explicit. | Workflow creates/deletes its only evidence while observer can be down. | ESC-01 before implementation. | D-001,D-002,D-017,D-024 | Retained-file guarantee only. |
| A-002 | Target roots fit serialized reconciliation. | Streaming design; no target numbers. | Target soak misses scan/disk/watchdog envelope. | U-001 soak. | D-002,D-004,D-005,D-008,D-011,D-016,D-022 | No capacity claim; measure before parallelism. |
| A-003 | State is on a local SQLite-safe filesystem. | Exercise rename probe only. | Target is unsupported network/FUSE storage or fails durability probe. | U-004 before build. | D-004,D-005,D-009,D-018,D-020 | Refuse unsupported state path. |
| A-004 | Receiver returns bounded meaningful HTTP outcomes and may accept stable ids. | No receiver selected. | Endpoint contract is incompatible/unbounded. | U-002. | D-007,D-012,D-023 | Durable outbox; no exactly-once claim. |
| A-005 | One operator and no accounts/tenancy are required. | Internal one-box seed. | Second trust class or delegated admin appears. | Product review. | D-011,D-015,D-023 | Reopen 4.2/4.3/4.21. |
| A-006 | Target Linux supports systemd and Python 3.11+. | Exercise systemd 259/Python 3.11.15 probes only. | Target differs or policy forbids runtime. | U-004 and OS changes. | D-005,D-009,D-011,D-012,D-014,D-015 | D-014 provisional; preserve port boundary. |
| A-007 | File content is out of scope and filenames may be sensitive. | Seed requests seen-record, not archive. | Owner requires content or classifies names nonsensitive. | U-003/change request. | D-003,D-019,D-022 | Metadata only; count-only outbound. |
| A-008 | Symlinks need not be followed and roots are readable by service identity. | Safest reversible default. | Required files need link traversal or privilege. | Target dry run. | D-003,D-015,D-019 | Fail/skip explicitly; reopen security. |

No load-bearing assumption is unmonitored: A-001→ESC-01; A-002→U-001; A-003/A-006/A-008→U-004; A-004→U-002; A-007→U-003; A-005→product review.

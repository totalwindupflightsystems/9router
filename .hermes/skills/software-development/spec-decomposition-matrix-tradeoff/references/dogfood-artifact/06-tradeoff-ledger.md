# 06 — Tradeoff ledger

Ordinal reversal costs use low/medium/high definitions from §6.1; no unitless scores are used.

```yaml
id: T-001
question: "What mechanism is authoritative for discovering changes?"
core_link: "discover retained new files after crashes without extra services"
classification: BEFORE-BUILD
candidates:
  - name: "Periodic startup/full reconciliation"
    advantages:
      - "survives missed event notifications"
      - "stdlib implementation"
      - "one truth path"
    costs:
      - "repeated directory traversal"
      - "detection latency equals interval"
    breaks:
      - "cannot capture create-delete entirely during downtime; checked against D-001,D-017"
    evidence:
      - "seed asks hourly digest, not sub-second notification"
    assumptions:
      - A-001
      - A-002
    reversal_path: "add inotify only as wake-up accelerator; preserve scan contract"
    reversal_cost: low
  - name: "inotify event stream"
    advantages:
      - "low latency"
      - "less repeated traversal"
    costs:
      - "Linux-specific queue handling"
      - "overflow/restart recovery still needs scan"
    breaks:
      - "event queue vanishes on downtime; checked against reboot/no-loss requirement"
    evidence:
      - "Linux inotify semantics; no project probe in bounded run"
    assumptions:
      - A-006
    reversal_path: "retain adapter but add reconciliation"
    reversal_cost: medium
  - name: "durable audit/fanotify journal"
    advantages:
      - "can cover more transient events while host runs"
    costs:
      - "privilege/kernel/config complexity"
      - "still cannot cover powered-off producer activity"
    breaks:
      - "violates least privilege/simplicity; checked against D-015"
    evidence:
      - "not probed; requires target capability research"
    assumptions:
      - A-006
    reversal_path: "disable journal and fall back to scan"
    reversal_cost: medium
dominated:
  - "inotify-only is dominated because correctness still requires reconciliation"
hinge_axis: "whether transient create-delete events are part of the required truth"
recommendation: "Periodic startup/full reconciliation"
why: "It is the only candidate that satisfies reboot recovery with no extra service; ESC-01 owns the stronger semantic."
confidence: "high"
dedup_key: "file-change detection authority 4.4 4.20"
escalation_id: null
```

```yaml
id: T-002
question: "Which durable state store keeps scans, events, and pending digests coherent?"
core_link: "do not lose committed observations or pending digests on process crash"
classification: BEFORE-BUILD
candidates:
  - name: "SQLite rollback journal"
    advantages:
      - "atomic multi-table commit"
      - "constraints and indexed lookup"
      - "single local file/no server"
    costs:
      - "schema/migrations"
      - "SQLite operational knowledge"
    breaks:
      - "single-disk media boundary; checked against D-018"
    evidence:
      - "SQLite atomic commit primary documentation"
    assumptions:
      - A-003
      - A-006
    reversal_path: "versioned JSONL export then importer"
    reversal_cost: medium
  - name: "JSONL plus manifests"
    advantages:
      - "human-readable append path"
      - "simple first write"
    costs:
      - "custom indexing/compaction/recovery"
      - "multi-file atomicity problem"
    breaks:
      - "digest assignment and current state can diverge; checked against D-004,D-007"
    evidence:
      - "reasoned, not probed"
    assumptions:
      - A-003
    reversal_path: "import logs into SQLite"
    reversal_cost: medium
  - name: "PostgreSQL/service database"
    advantages:
      - "mature transactions/concurrency"
    costs:
      - "extra daemon, credentials, backup/service lifecycle"
    breaks:
      - "violates one-box/no-extra-service preference; checked against core"
    evidence:
      - "seed"
    assumptions: []
    reversal_path: "export relational tables"
    reversal_cost: high
dominated:
  - "PostgreSQL is dominated for one writer because it adds operations without required capability"
  - "JSONL loses on atomic cross-entity consistency"
hinge_axis: "atomic consistency at the lowest operational burden"
recommendation: "SQLite rollback journal"
why: "One embedded transaction spans canonical scan state, event append, and digest ownership."
confidence: "high"
dedup_key: "durable embedded state store 4.6"
escalation_id: null
```

```yaml
id: T-003
question: "How much internal concurrency should the daemon use?"
core_link: "keep one coherent tool on a small box"
classification: BEFORE-BUILD
candidates:
  - name: "One serialized scheduler loop"
    advantages:
      - "few races"
      - "one DB writer"
      - "easy crash reasoning"
    costs:
      - "slow root/post can delay others"
    breaks:
      - "latency coupling; checked against D-002,D-007,D-011"
    evidence:
      - "no measured parallel requirement"
    assumptions:
      - A-002
    reversal_path: "add bounded worker after measured bottleneck"
    reversal_cost: low
  - name: "Thread pool per root"
    advantages:
      - "parallel scans"
    costs:
      - "DB/disk contention"
      - "shutdown/watchdog race matrix"
    breaks:
      - "complexity conflicts with simplicity; checked against D-004,D-009"
    evidence:
      - "unmeasured benefit"
    assumptions:
      - A-002
    reversal_path: "reduce pool to one"
    reversal_cost: low
  - name: "Multiple worker processes"
    advantages:
      - "failure isolation"
    costs:
      - "coordination/leases/interprocess queue"
    breaks:
      - "becomes distributed-on-one-box; checked against core"
    evidence:
      - "no requirement"
    assumptions: []
    reversal_path: "collapse into daemon"
    reversal_cost: medium
dominated:
  - "multiple processes are dominated absent isolation need"
hinge_axis: "measured scan latency versus coordination complexity"
recommendation: "One serialized scheduler loop"
why: "No evidence justifies parallelism; U-001 is the explicit reversal trigger."
confidence: "medium"
dedup_key: "daemon concurrency model 4.20"
escalation_id: null
```

```yaml
id: T-004
question: "What delivery guarantee should remote digest posting expose?"
core_link: "hourly digest must not disappear after a crash"
classification: BEFORE-BUILD
candidates:
  - name: "At-least-once with stable digest id"
    advantages:
      - "no silent omission after ack loss"
      - "simple durable retry"
    costs:
      - "possible duplicate post"
    breaks:
      - "receiver may not dedupe; checked against D-012,D-022"
    evidence:
      - "network acknowledgement ambiguity"
    assumptions:
      - A-004
    reversal_path: "add receiver-side idempotency/receipt API"
    reversal_cost: low
  - name: "At-most-once"
    advantages:
      - "no duplicate posts"
    costs:
      - "crash can silently lose accepted/unsent state depending ordering"
    breaks:
      - "violates no-loss intent; checked against D-007"
    evidence:
      - "failure analysis"
    assumptions: []
    reversal_path: "switch outbox state machine"
    reversal_cost: medium
  - name: "Exactly-once claim"
    advantages:
      - "clean user story"
    costs:
      - "requires transactional receiver cooperation"
      - "still must define acknowledgement"
    breaks:
      - "false guarantee with unknown endpoint; checked against U-002"
    evidence:
      - "no receiver evidence"
    assumptions:
      - A-004
    reversal_path: "downgrade documented contract"
    reversal_cost: high
dominated:
  - "at-most-once is dominated by omission risk"
  - "exactly-once claim is unsupported"
hinge_axis: "omission versus duplicate risk under acknowledgement loss"
recommendation: "At-least-once with stable digest id"
why: "The seed prioritizes no loss; stable ids make duplicates detectable and potentially deduplicable."
confidence: "high"
dedup_key: "remote digest delivery semantics 4.18 4.20"
escalation_id: null
```

```yaml
id: T-005
question: "What defines a file identity?"
core_link: "remember what has been seen without reading content"
classification: BEFORE-BUILD
candidates:
  - name: "root id + relative path"
    advantages:
      - "matches operator vocabulary"
      - "portable and cheap"
    costs:
      - "rename appears as disappearance+discovery"
    breaks:
      - "no rename reconstruction; checked against D-022"
    evidence:
      - "scope is metadata-only"
    assumptions:
      - A-008
    reversal_path: "add diagnostic rename hints without changing key"
    reversal_cost: low
  - name: "device + inode"
    advantages:
      - "can correlate some renames"
    costs:
      - "reuse and filesystem boundary ambiguity"
    breaks:
      - "unstable across restore/copy; checked against reboot/migration"
    evidence:
      - "POSIX semantics, target not probed"
    assumptions:
      - A-003
    reversal_path: "migrate to path key with stored mapping"
    reversal_cost: medium
  - name: "content hash"
    advantages:
      - "content-derived identity"
    costs:
      - "reads every byte"
      - "privacy and I/O expansion"
    breaks:
      - "turns utility into content scanner; checked against D-019"
    evidence:
      - "no content requirement"
    assumptions:
      - A-007
    reversal_path: "stop hashing while retaining path state"
    reversal_cost: low
dominated:
  - "content hash is dominated on cost/privacy"
  - "inode is not a portable canonical identifier"
hinge_axis: "whether rename identity is required strongly enough to justify unstable/content-derived identity"
recommendation: "root id + relative path"
why: "The core asks what paths changed, not object lineage; the loss is explicit and reversible."
confidence: "high"
dedup_key: "file identity key 4.5"
escalation_id: null
```

```yaml
id: T-006
question: "Which implementation runtime best preserves small deployment and maintainability?"
core_link: "one small command-line tool on one Linux box"
classification: BEFORE-BUILD
candidates:
  - name: "Python 3.11 standard library"
    advantages:
      - "sqlite3/tomllib/HTTP/filesystem available"
      - "fastest simple implementation"
    costs:
      - "runtime/package dependency on target"
      - "systemd notify is manual socket code"
    breaks:
      - "target may not have exact version; checked against U-004"
    evidence:
      - "exercise probe Python 3.11.15, SQLite 3.53.1"
    assumptions:
      - A-006
    reversal_path: "port stable DB/config contracts to Go"
    reversal_cost: medium
  - name: "Go static binary"
    advantages:
      - "single distributable"
      - "strong process/network tooling"
    costs:
      - "SQLite needs CGO or non-stdlib driver"
      - "dependency and cross-build work"
    breaks:
      - "larger build/dependency surface; checked against no-extra simplicity"
    evidence:
      - "reasoned; no dependency probe"
    assumptions: []
    reversal_path: "preserve schema and adapter interfaces during port"
    reversal_cost: medium
dominated: []
hinge_axis: "target runtime availability and packaging burden"
recommendation: "Python 3.11 standard library"
why: "Current evidence supports it and contracts preserve a later port; U-004 must confirm target."
confidence: "medium"
dedup_key: "implementation runtime 4.24"
escalation_id: null
```

```yaml
id: T-007
question: "Must the system capture a file created and deleted entirely while the observer is down?"
core_link: "interpret the owner’s no-loss requirement without contradicting one-box simplicity"
classification: BEFORE-BUILD
candidates:
  - name: "Retained-file reconciliation guarantee"
    advantages:
      - "one process/one DB"
      - "simple and reversible"
    costs:
      - "misses downtime-transient files"
    breaks:
      - "may violate owner risk appetite; checked against D-001,D-017,D-024"
    evidence:
      - "physical observation boundary"
    assumptions:
      - A-001
    reversal_path: "add a durable producer/kernel journal and import adapter"
    reversal_cost: medium
  - name: "Independent durable change journal"
    advantages:
      - "stronger event capture"
    costs:
      - "extra privileged component or producer contract"
      - "more operations and migration"
    breaks:
      - "conflicts with preference for no extra services; checked against core"
    evidence:
      - "not probed; target design required"
    assumptions:
      - A-006
    reversal_path: "disable journal after draining into canonical store"
    reversal_cost: medium
dominated: []
hinge_axis: "value/risk of transient-file completeness versus operational simplicity"
recommendation: "escalate"
why: "Both satisfy a defensible reading; the axis is owner risk appetite and materially changes architecture. Autonomous default is retained-file reconciliation."
confidence: "high"
dedup_key: "downtime transient file guarantee 4.4 4.42"
escalation_id: ESC-01
```

```yaml
id: T-008
question: "Must failure reporting cover loss of the entire host?"
core_link: "tell the operator when the tool has stopped working"
classification: BEFORE-BUILD
candidates:
  - name: "Local systemd supervision + one-shot notifier"
    advantages:
      - "no new service"
      - "covers daemon crash/hang/start failure"
    costs:
      - "cannot signal host/power/network loss"
    breaks:
      - "narrows stopped-working claim; checked against D-023,D-024"
    evidence:
      - "physical limit"
    assumptions:
      - A-006
    reversal_path: "add outbound heartbeat later"
    reversal_cost: low
  - name: "External dead-man heartbeat"
    advantages:
      - "covers host silence from outside"
    costs:
      - "external service/credential/egress"
      - "new alert dependency"
    breaks:
      - "weakens one-box/no-extra-services preference; checked against core"
    evidence:
      - "architecture fact; endpoint not selected"
    assumptions:
      - A-004
    reversal_path: "disable endpoint and retain local supervision"
    reversal_cost: low
dominated: []
hinge_axis: "host-outage coverage versus strict no-extra-service simplicity"
recommendation: "escalate"
why: "The deciding axis is owner risk appetite/product promise. Autonomous default keeps local supervision only."
confidence: "high"
dedup_key: "whole host stopped working detection 4.17 4.42"
escalation_id: ESC-02
```

```yaml
id: T-009
question: "What backup tier is justified on one box?"
core_link: "preserve durable records beyond process crashes without silently becoming distributed"
classification: BEFORE-SHIP
candidates:
  - name: "Verified same-box snapshot"
    advantages:
      - "protects migration/operator errors"
      - "no external service"
    costs:
      - "does not survive disk/host loss"
    breaks:
      - "disk-loss RPO remains unprotected; checked against D-018"
    evidence:
      - "SQLite backup design"
    assumptions:
      - A-003
    reversal_path: "copy verified snapshot off-box"
    reversal_cost: low
  - name: "Off-box encrypted copy"
    advantages:
      - "survives local media/host loss"
    costs:
      - "remote storage, credentials, restore path"
    breaks:
      - "adds service and security cascade; checked against D-015"
    evidence:
      - "destination unknown U-005"
    assumptions:
      - A-004
    reversal_path: "stop copies after retention/credential cleanup"
    reversal_cost: low
dominated: []
hinge_axis: "media-loss tolerance versus extra service/credential burden"
recommendation: "Verified same-box snapshot"
why: "The seed asks crash survival, not disk disaster survival; U-005 reopens when the protected failure is chosen."
confidence: "medium"
dedup_key: "backup tier 4.6 4.42"
escalation_id: null
```


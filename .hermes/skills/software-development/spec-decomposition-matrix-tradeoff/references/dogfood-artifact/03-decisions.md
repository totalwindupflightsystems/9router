# 03 — Decision register

Rows follow §7.3. D-014, D-017, and D-023 are autonomous-mode provisional containment decisions.

```yaml
id: "D-001"
statement: "Define a watched change as a committed metadata transition for a regular file present at a completed scan."
branch: "domain:4.4"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "filesystem event stream as truth"
  - "completed periodic reconciliation as truth"
  - "content snapshot/archive"
evidence:
  - "owner seed: watches directories for new files and digests what changed"
breaks: "Transient downtime files are not covered → ACCEPTED-COST pending ESC-01; checked against D-002,D-017,D-024."
assumptions:
  - "A-001"
depends_on: []
contradicts:
  - "C-001"
core_check: "core-check-007"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "product owner"
provisional: false
```

```yaml
id: "D-002"
statement: "Use startup plus periodic full reconciliation as the correctness path; treat event APIs only as future wake-up acceleration."
branch: "D-001"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "poll/reconcile only"
  - "inotify only"
  - "inotify plus reconcile"
evidence:
  - "Linux event queues are not persistent across process downtime"
  - "60-second interval is guessed and configurable"
breaks: "D-017 shows create-delete downtime gap → REQUIRES-REDESIGN: wording narrowed to retained-file correctness and ESC-01 opened; checked against D-001,D-004,D-008,D-017."
assumptions:
  - "A-001"
  - "A-002"
depends_on:
  - "D-001"
contradicts:
  - "C-001"
core_check: "core-check-007"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "architecture owner"
provisional: false
```

```yaml
id: "D-003"
statement: "Identify a file by immutable root id plus normalized relative path; retain device/inode only as diagnostics."
branch: "domain:4.5"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "path identity"
  - "device+inode identity"
  - "content hash identity"
evidence:
  - "content is outside scope"
  - "inodes can be reused and moves cross filesystems"
breaks: "Rename reconstruction is lost → ACCEPTED-COST and D-022 renders rename as disappear+discover; checked against D-006,D-019,D-022."
assumptions:
  - "A-008"
depends_on:
  - "D-001"
contradicts: []
core_check: "core-check-001"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "data owner"
provisional: false
```

```yaml
id: "D-004"
statement: "Stage each root scan separately and atomically promote its set difference with event creation in one SQLite transaction."
branch: "domain:4.6"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "update canonical rows while walking"
  - "stage then promote"
  - "append raw events then rebuild asynchronously"
evidence:
  - "crash before promotion leaves canonical state unchanged"
breaks: "Temporary storage can approach one metadata snapshot → ACCEPTED-COST with U-001 disk probe; checked against D-005,D-006,D-018,D-020."
assumptions:
  - "A-002"
  - "A-003"
depends_on:
  - "D-002"
  - "D-003"
contradicts: []
core_check: "core-check-002"
supersedes: null
superseded_by: null
reversal_cost: "high"
owner: "storage owner"
provisional: false
```

```yaml
id: "D-005"
statement: "Store all durable state in one SQLite database using rollback journal, foreign keys, and synchronous FULL."
branch: "domain:4.6"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "SQLite rollback journal"
  - "SQLite WAL"
  - "JSONL plus custom indexes"
evidence:
  - "SQLite atomic-commit documentation"
  - "one writer removes WAL concurrency benefit"
  - "exercise runtime SQLite 3.53.1"
breaks: "Single local disk remains a media-loss boundary → ACCEPTED-COST with D-018 backup; checked against D-004,D-007,D-016,D-018,D-020."
assumptions:
  - "A-003"
  - "A-006"
depends_on:
  - "D-004"
contradicts: []
core_check: "core-check-002"
supersedes: null
superseded_by: null
reversal_cost: "high"
owner: "storage owner"
provisional: false
```

```yaml
id: "D-006"
statement: "Persist current file state, append-only change events, scan runs, digests, and delivery attempts with explicit schema version."
branch: "domain:4.5"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "current-state rows only"
  - "event log only"
  - "current state plus event/outbox audit"
evidence:
  - "data dictionary in 4.05-data.md"
breaks: "More rows and retention work → ACCEPTED-COST because audit/recovery serve core; checked against D-005,D-007,D-016,D-022."
assumptions:
  - "A-002"
depends_on:
  - "D-003"
  - "D-004"
  - "D-005"
contradicts: []
core_check: "core-check-001"
supersedes: null
superseded_by: null
reversal_cost: "high"
owner: "data owner"
provisional: false
```

```yaml
id: "D-007"
statement: "Create digest and assign its events transactionally, then deliver at-least-once with a stable digest id and recorded attempts."
branch: "domain:4.19"
ring: 2
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "at-most-once send-before-mark"
  - "at-least-once transactional outbox"
  - "claim exactly-once remote delivery"
evidence:
  - "acknowledgement loss makes exactly-once unprovable without receiver cooperation"
breaks: "Duplicates are possible → ACCEPTED-COST with idempotency key and visible digest id; D-012 cannot rely solely on this daemon outbox → MITIGATED by one-shot notifier; checked against D-005,D-006,D-010,D-012,D-022."
assumptions:
  - "A-004"
depends_on:
  - "D-005"
  - "D-006"
contradicts: []
core_check: "core-check-003"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "delivery owner"
provisional: false
```

```yaml
id: "D-008"
statement: "Run one foreground single-threaded scheduler loop with bounded I/O and no overlapping scans or sends."
branch: "domain:4.20"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "single serialized loop"
  - "thread pool per root"
  - "multiple worker processes"
evidence:
  - "no measured need for parallelism"
  - "one writer minimizes races"
breaks: "A blocking post could stop scans/watchdog → MITIGATED by finite I/O timeout and progress-coupled heartbeat; checked against D-007,D-010,D-011,D-021."
assumptions:
  - "A-002"
depends_on:
  - "D-002"
  - "D-007"
contradicts: []
core_check: "core-check-004"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "runtime owner"
provisional: false
```

```yaml
id: "D-009"
statement: "Acquire a nonblocking kernel flock before opening mutable service state and exit specifically if another holder exists."
branch: "domain:4.20"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "trust systemd instance count"
  - "PID file"
  - "kernel flock plus DB transactions"
evidence:
  - "flock releases on process exit; manual invocation remains guarded"
breaks: "Network filesystems may not preserve local lock semantics → ACCEPTED-COST: state path must be local; checked against D-005,D-011,D-015."
assumptions:
  - "A-003"
depends_on:
  - "D-005"
  - "D-008"
contradicts: []
core_check: "core-check-004"
supersedes: null
superseded_by: null
reversal_cost: "low"
owner: "runtime owner"
provisional: false
```

```yaml
id: "D-010"
statement: "Persist half-open UTC digest windows and use monotonic time only for waits and retry backoff."
branch: "domain:4.4"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "hour since process start"
  - "local wall-clock hour"
  - "UTC wall-clock windows plus monotonic waits"
evidence:
  - "UTC avoids DST ambiguity"
  - "unique window_end prevents duplicate rows"
breaks: "Scan committing after cutoff could be omitted → MITIGATED: only committed events are selected and late commits enter next window; checked against D-004,D-007,D-008,D-022."
assumptions:
  - "A-006"
depends_on:
  - "D-004"
  - "D-007"
contradicts: []
core_check: "core-check-003"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "scheduler owner"
provisional: false
```

```yaml
id: "D-011"
statement: "Supervise the foreground process with systemd boot enablement, restart limits, and a watchdog emitted only after scheduler progress."
branch: "domain:4.12"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "shell background process"
  - "cron invocation"
  - "systemd service with watchdog"
evidence:
  - "exercise probe: systemd 259"
  - "seed requires reboot survival and stopped-work detection"
breaks: "Free-running heartbeat could mask dead logic → MITIGATED by progress coupling; endpoint outage must not block READY; checked against D-008,D-012,D-021,D-023."
assumptions:
  - "A-006"
depends_on:
  - "D-008"
contradicts: []
core_check: "core-check-008"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "operations owner"
provisional: false
```

```yaml
id: "D-012"
statement: "Invoke the same CLI as a bounded stateless systemd failure-notify subcommand, with journald as last-resort evidence."
branch: "domain:4.17"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "daemon self-alert only"
  - "systemd one-shot helper using same CLI"
  - "external monitoring service only"
evidence:
  - "dead daemon cannot execute its own outbox"
  - "seed prefers one tool"
breaks: "Same endpoint/network can fail and whole host cannot notify → ACCEPTED-COST pending ESC-02; modified to avoid daemon DB/scheduler dependency; checked against D-007,D-011,D-015,D-023."
assumptions:
  - "A-004"
  - "A-006"
depends_on:
  - "D-007"
  - "D-011"
contradicts:
  - "C-001"
core_check: "core-check-009"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "operations owner"
provisional: false
```

```yaml
id: "D-013"
statement: "Write structured operational records to journald and keep actual secrets and file content out of logs."
branch: "domain:4.12"
ring: 4
terminating_ring: 5
classification: "BEFORE-SHIP"
alternatives_considered:
  - "free-text local logfile"
  - "structured journald"
  - "remote log service"
evidence:
  - "journald is independent of app database on target class"
breaks: "Host journal retention may be short → UNKNOWN owned by NOT-REACHED logging domain; checked against D-012,D-015,D-019,D-020."
assumptions:
  - "A-006"
depends_on:
  - "D-011"
  - "D-012"
contradicts: []
core_check: "core-check-008"
supersedes: null
superseded_by: null
reversal_cost: "low"
owner: "observability owner"
provisional: false
```

```yaml
id: "D-014"
statement: "Implement v1 with Python 3.11 standard library interfaces for sqlite3, TOML, filesystem walking, HTTP, and systemd notify socket."
branch: "domain:4.24"
ring: 1
terminating_ring: null
classification: "BEFORE-BUILD"
alternatives_considered:
  - "Python 3.11 stdlib"
  - "Go static binary with SQLite dependency"
  - "Rust static binary"
evidence:
  - "exercise probe: Python 3.11.15 and sqlite 3.53.1"
  - "stdlib reduces dependency surface"
breaks: "Target may lack exact runtime and packaging can drift → UNKNOWN U-004; checked against D-005,D-011,D-015."
assumptions:
  - "A-006"
depends_on:
  - "D-005"
  - "D-011"
contradicts: []
core_check: "core-check-008"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "implementation owner"
provisional: true
```

```yaml
id: "D-015"
statement: "Separate immutable config, secret references, runtime lock, mutable state, and backups under OS-standard paths with least privilege."
branch: "domain:4.12"
ring: 1
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "all files in working directory"
  - "OS-standard separated paths"
  - "container volume bundle"
evidence:
  - "seed requires reboot persistence"
  - "systemd sandbox needs explicit read/write boundaries"
breaks: "Raw config removal could orphan state and helper needs secret access → MITIGATED by lifecycle CLI and shared credential reference; checked against D-009,D-011,D-012,D-018,D-019."
assumptions:
  - "A-006"
  - "A-008"
depends_on:
  - "D-009"
  - "D-011"
contradicts: []
core_check: "core-check-008"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "security owner"
provisional: false
```

```yaml
id: "D-016"
statement: "Retain current state while a root exists and default delivered events/digests to 90 days; never expire pending delivery automatically."
branch: "domain:4.5"
ring: 1
terminating_ring: 5
classification: "DEFER-WITH-OWNER"
alternatives_considered:
  - "retain everything"
  - "90-day delivered history plus current state"
  - "minimal current state only"
evidence:
  - "90 days is guessed, not measured"
  - "pending work must not disappear"
breaks: "Historical audit beyond 90 days is lost → ACCEPTED-COST until owner changes retention; checked against D-006,D-018,D-022."
assumptions:
  - "A-002"
depends_on:
  - "D-006"
  - "D-007"
contradicts: []
core_check: "core-check-001"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "operator"
provisional: false
```

```yaml
id: "D-017"
statement: "Guarantee reconciliation only for files still present after downtime; do not claim capture of create-delete events while stopped."
branch: "domain:4.44"
ring: 4
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "retained-file guarantee"
  - "kernel/audit durable journal"
  - "external producer manifest"
evidence:
  - "physical observation limit"
  - "ESC-01 compares risk/cost"
breaks: "May contradict owner's meaning of lose anything → BLOCKS full acceptance pending C-001/ESC-01; checked against D-001,D-002,D-023,D-024."
assumptions:
  - "A-001"
depends_on:
  - "D-001"
  - "D-002"
contradicts:
  - "C-001"
core_check: "core-check-006"
supersedes: null
superseded_by: null
reversal_cost: "high"
owner: "product owner"
provisional: true
```

```yaml
id: "D-018"
statement: "Produce daily verified SQLite online snapshots with atomic final rename; treat off-box copy as a separate optional policy."
branch: "domain:4.6"
ring: 1
terminating_ring: 5
classification: "BEFORE-SHIP"
alternatives_considered:
  - "live file copy"
  - "SQLite online backup to same box"
  - "off-box replicated backup"
evidence:
  - "live DB file copy may be inconsistent"
  - "exercise rename+sync probe succeeded locally"
breaks: "Same-box snapshot does not survive media loss → ACCEPTED-COST and U-005; modified from file copy to backup API; checked against D-005,D-015,D-016,D-020."
assumptions:
  - "A-003"
depends_on:
  - "D-005"
  - "D-015"
contradicts: []
core_check: "core-check-002"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "operations owner"
provisional: false
```

```yaml
id: "D-019"
statement: "Read metadata only and make posted path detail configurable as relative, basename, or count-only, defaulting to count-only until classified."
branch: "domain:4.5"
ring: 3
terminating_ring: 5
classification: "BEFORE-SHIP"
alternatives_considered:
  - "post full absolute paths"
  - "post relative paths"
  - "post basenames/counts only"
evidence:
  - "filenames may be sensitive even without content"
breaks: "Lower-detail digest may be less useful → MITIGATED by explicit path_mode after U-003; checked against D-007,D-013,D-015,D-022."
assumptions:
  - "A-007"
  - "A-008"
depends_on:
  - "D-003"
  - "D-007"
  - "D-015"
contradicts: []
core_check: "core-check-001"
supersedes: null
superseded_by: null
reversal_cost: "low"
owner: "security owner"
provisional: false
```

```yaml
id: "D-020"
statement: "Fail closed on store corruption/full/I/O errors; never auto-delete pending history to recover space."
branch: "domain:4.42"
ring: 2
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "drop oldest and continue"
  - "pause readiness and fail loud"
  - "switch to memory-only mode"
evidence:
  - "silent continuation violates no-loss intent"
breaks: "Availability is sacrificed during storage fault → ACCEPTED-COST because integrity outranks uptime; checked against D-005,D-006,D-011,D-012,D-018."
assumptions:
  - "A-003"
depends_on:
  - "D-005"
  - "D-006"
contradicts: []
core_check: "core-check-005"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "operations owner"
provisional: false
```

```yaml
id: "D-021"
statement: "On SIGTERM stop scheduling, finish or roll back active DB work, start no new send, close state, and let restart reconcile."
branch: "domain:4.12"
ring: 2
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "immediate exit"
  - "bounded graceful shutdown"
  - "drain all pending deliveries before exit"
evidence:
  - "transactions make rollback safe"
  - "draining network could exceed service timeout"
breaks: "An in-flight remote accept can become a duplicate on restart → ACCEPTED-COST under D-007; checked against D-004,D-007,D-008,D-011."
assumptions:
  - "A-004"
depends_on:
  - "D-004"
  - "D-007"
  - "D-008"
contradicts: []
core_check: "core-check-008"
supersedes: null
superseded_by: null
reversal_cost: "low"
owner: "runtime owner"
provisional: false
```

```yaml
id: "D-022"
statement: "Store every committed event but render at most one bounded summary line per path and explicit overflow counts per digest."
branch: "domain:4.5"
ring: 4
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "post every event line"
  - "coalesce rendering while preserving events"
  - "discard intermediate events"
evidence:
  - "owner asks for short digest"
  - "audit requires durable event history"
breaks: "Rendered digest hides intermediate detail → ACCEPTED-COST because digest id links local audit; checked against D-003,D-006,D-007,D-010,D-019."
assumptions:
  - "A-002"
depends_on:
  - "D-006"
  - "D-007"
  - "D-010"
contradicts: []
core_check: "core-check-001"
supersedes: null
superseded_by: null
reversal_cost: "low"
owner: "product owner"
provisional: false
```

```yaml
id: "D-023"
statement: "Claim local process/service failure coverage only; do not claim total host outage detection without an external dead-man."
branch: "domain:4.17"
ring: 3
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "local systemd supervision only"
  - "external heartbeat/dead-man"
  - "second host observer"
evidence:
  - "a powered-off host cannot emit a signal"
  - "ESC-02 compares coverage against simplicity"
breaks: "Seed may intend host-level stopped-working notification → BLOCKS full claim pending C-001/ESC-02; checked against D-011,D-012,D-017,D-024."
assumptions:
  - "A-006"
depends_on:
  - "D-011"
  - "D-012"
contradicts:
  - "C-001"
core_check: "core-check-009"
supersedes: null
superseded_by: null
reversal_cost: "medium"
owner: "product owner"
provisional: true
```

```yaml
id: "D-024"
statement: "Use the numbered R1–R10 semantics and explicit non-goals as the acceptance boundary; never collapse all loss/failure modes into one promise."
branch: "domain:4.4"
ring: 4
terminating_ring: 5
classification: "BEFORE-BUILD"
alternatives_considered:
  - "broad natural-language promise"
  - "split observable guarantees/non-guarantees"
  - "defer semantics to implementation"
evidence:
  - "requirements cascade 4.04"
  - "break-check exposed two impossible interpretations"
breaks: "Narrower language may disappoint owner → MITIGATED by ESC-01/02 with reversible defaults; modified after break-check; checked against all D-001..D-023."
assumptions:
  - "A-001"
  - "A-006"
depends_on:
  - "D-001"
  - "D-017"
  - "D-023"
contradicts:
  - "C-001"
core_check: "core-check-007"
supersedes: null
superseded_by: null
reversal_cost: "high"
owner: "product owner"
provisional: false
```

## Core-check index

- core-check-001: meaning and lifecycle of observed files → simplify; rejected content hashing and rename reconstruction. Full row is in its domain file.
- core-check-002: durable local store → keep; selected one SQLite file and removed separate stores. Full row is in its domain file.
- core-check-003: canonical, staged, and ephemeral state → keep; froze digest body and made partial scans disposable. Full row is in its domain file.
- core-check-004: one-writer coordination → simplify; rejected pools, overlapping scans, and leases. Full row is in its domain file.
- core-check-005: crash, reboot, and stopped-working recovery → escalate; split process/disk/host guarantees. Full row is in its domain file.
- core-check-006: unknown and assumption containment → keep; converted gaps into owned registers. Full row is in its domain file.
- core-check-007: testable meaning of the seed → keep; defined watch/loss/hourly/short/stopped. Full row is in its domain file.
- core-check-008: single-box supervised runtime → keep; selected native systemd and one entrypoint. Full row is in its domain file.
- core-check-009: operator failure signal → escalate; isolated whole-host detection as ESC-02. Full row is in its domain file.

## BEFORE-BUILD invariant → test map

| Decision | Invariant | Test | Level |
|---|---|---|---|
| D-001 | only completed successful scans create transitions | failed/partial root scan emits no disappearance | integration |
| D-002 | restart reconciliation discovers retained files | create while stopped, restart, scan | end-to-end |
| D-003 | identity is root+relative path | inode reuse/rename fixture | unit |
| D-004 | scan promotion and events are atomic | kill before/during/after commit | integration |
| D-005 | committed DB survives process crash | crash matrix plus quick_check | integration |
| D-006 | constraints reject orphan/invalid rows | DDL constraint tests | integration |
| D-007 | no committed event is unassigned twice or silently abandoned | ack-loss and retry fixture | end-to-end |
| D-008 | only one work item mutates state at a time | slow endpoint/root scheduling test | integration |
| D-009 | second instance cannot become writer | two-process lock test | integration |
| D-010 | UTC windows are unique and ordered across clock changes | fake-clock DST/NTP/reboot cases | unit |
| D-011 | watchdog proves loop progress and reboot starts service | wedged-loop kill and reboot VM test | end-to-end |
| D-012 | daemon death can still invoke bounded notifier | kill daemon and observe helper/journal | end-to-end |
| D-014 | target runtime supports required stdlib behavior | clean-target smoke probe | integration |
| D-015 | service writes only approved paths and roots cannot vanish silently | systemd sandbox and config-drift tests | end-to-end |
| D-017 | acceptance never claims downtime-transient capture | contract assertion and ESC-01 gate | contract |
| D-020 | storage failure cannot switch to lossy mode | disk-full/I/O fault injection | integration |
| D-021 | forced shutdown leaves recoverable canonical state | SIGTERM/SIGKILL phase matrix | integration |
| D-022 | render truncation never deletes underlying events | overflow digest fixture | integration |
| D-023 | host-outage coverage claim stays conditional | contract assertion and ESC-02 gate | contract |
| D-024 | R1–R10 remain traceable to observables | requirements traceability lint | contract |

Determinism injection points: wall/monotonic clock, filesystem walker/stat provider, SQLite commit failpoint, HTTP sender/ack loss, signal delivery, systemd notify socket, disk-full/I/O fault, generated root fixtures.

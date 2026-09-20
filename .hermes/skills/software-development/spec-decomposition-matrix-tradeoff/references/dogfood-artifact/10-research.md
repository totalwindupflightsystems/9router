# 10 — Research and probe evidence

Evidence refresh: 2026-09-20T12:33–12:48Z. This is a greenfield design; no target host, roots, or receiver were supplied. Exercise-host probes demonstrate feasibility only and are never treated as target facts (U-004).

## Project-specific evidence handles

| Handle | Observed result | Design use | Limit |
|---|---|---|---|
| `<scratch>/design-sandbox/probes/rename-b` | source `rename-a` absent after rename; target exists, 6 bytes; `sync -d` completed | supports atomic-final-name backup procedure D-018 | proves only the exercise filesystem/path, not target power-loss semantics |
| `stat -f <scratch>/design-sandbox/probes` | `ext2/ext3`, block 4096 (Linux legacy label for this filesystem family) | makes the probe reproducible | not the future state directory |
| `python3 --version` | Python 3.11.15 | makes D-014 feasible in this exercise | target remains U-004 |
| Python `sqlite3.sqlite_version` | 3.53.1 | confirms Python binding can open modern SQLite here | not target version |
| `sqlite3 --version` | CLI 3.53.4 | independent CLI availability in exercise | CLI version differs from Python module and is not required |
| `systemctl --version` | systemd 259 (259.5-0ubuntu3.4) | watchdog/supervision design is feasible here | target remains U-004 |
| Owner seed in `00-seed.md` | one CLI, hourly, one Linux box, reboot/crash/failure visibility, no extra services preference | fixes the product-specific core and constraints | no scale/destination semantics supplied |

No actual secret, home path, watched directory, or receiver was inspected.

## Primary sources

1. SQLite, “Atomic Commit In SQLite” — https://sqlite.org/atomiccommit.html — supports the claim that SQLite transactions are designed to appear atomic across process/OS/power interruption, subject to filesystem assumptions.
2. SQLite, “Write-Ahead Logging” — https://www.sqlite.org/wal.html — documents WAL tradeoffs and durability differences under synchronous settings; this design rejects WAL's extra concurrency because there is one writer.
3. systemd, `sd_notify` — https://freedesktop.org/software/systemd/man/sd_notify.html — documents watchdog notification and the ability to trigger watchdog behavior.
4. systemd, `sd_watchdog_enabled` — https://www.freedesktop.org/software/systemd/man/latest/sd_watchdog_enabled.html — points to `WatchdogSec=` supervision.
5. Python 3.11, `tomllib` — https://docs.python.org/3.11/library/tomllib.html — confirms TOML parsing exists in the selected standard library.
6. Python, `sqlite3` — https://docs.python.org/3/library/sqlite3.html — documents Python's SQLite interface and backup API.

Search evidence was captured from primary-source result snippets because this runtime's configured extractor reported that its Brave backend is search-only. That tool limitation is not converted into a product fact.

## Candidate research bounded by this run

| Capability | Candidate | License/dependency signal | Replaces | Still build | Disposition |
|---|---|---|---|---|---|
| change authority | periodic `os.scandir`/`stat` reconciliation | Python stdlib | event watcher dependency | staging/diff/state logic | choose for correctness |
| change acceleration | Linux inotify | kernel API; Python stdlib has no high-level wrapper | some repeated wake latency | reconciliation still mandatory | defer until measured need |
| embedded store | SQLite via Python stdlib | SQLite included by runtime | custom log/index/transaction engine | schema/migrations/runbooks | choose |
| service supervision | systemd | host platform component | custom daemonizer/restart/watchdog | unit files and notify calls | choose if U-004 confirms |
| store alternative | JSONL plus manifests | no library | SQLite | indexes, recovery, compaction, atomic multi-entity protocol | reject for v1 |
| server store | PostgreSQL | extra daemon/client/deployment | SQLite | operations/credentials/backups | reject as dominated for one writer |

“Build less” baseline: compared with hand-building a durable manifest, index, transaction protocol, daemonizer, restart policy, watchdog, and log rotation, SQLite plus the existing service manager removes those components. No weeks/lines estimate is claimed because no implementation baseline was measured.

## Probe conclusions that changed or bounded decisions

- The local rename probe made D-018 require temp+fsync+rename+directory durability handling rather than an in-place backup replacement.
- Distinct Python-module and CLI SQLite versions prevent treating a CLI version as the embedded runtime version.
- systemd availability supports D-011 here but created U-004 rather than a universal target assumption.
- No target directories or destination were available, so performance, receiver idempotency, payload caps, and filename disclosure remain owned unknowns instead of fabricated measurements.

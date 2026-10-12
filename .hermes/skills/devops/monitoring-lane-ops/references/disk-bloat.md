# Disk bloat on the lane box and staging dirs

## /tmp bloat: age-bucket, do not count directories

Attribute /tmp bloat on the lane box by mtime AGE-BUCKETS, not by counting directories — the
entry count is meaningless (100k+ tiny files) and a fresh-mtime dir can be pure scratch.
Bounded ladder: `df -h /` for where, `du -xh --max-depth=1 / | sort -rh | head` for what (a full
`du -x /home` times out — bound every du), then age-bucket /tmp contents in one python pass over
`os.scandir('/tmp')` summing st_mtime into <1d / 1-3d / 3-7d / >7d GB buckets. Reclaim ONLY the
>7d bucket (`find /tmp -mindepth 1 -maxdepth 1 -mtime +7 -delete`), even when it is the
minority of the bloat: fresh entries are live worker scratch whose deletion breaks running
batteries, and deleting them converts a safe mitigation into a self-inflicted outage. Verify
freed bytes by re-running the age-bucket pass after the delete, and record that a one-time
reclaim is capped by ongoing churn — the durable fix is the nightly mtime-gated cleanup cron
(see the /var/tmp rule in SKILL.md).

The monitoring host's own spool is tiny (hundreds of KB) — before blaming remote spool growth,
`du -sh /var/lib/fleet-monitoring` over ssh; the lane box's /tmp and docker layers dwarf
anything the alert-router writes.

## Backup-staging debris and cleanup-cron coverage

**A cleanup cron that EXISTS is not coverage — grep its stanza list against the measured top
offender, then re-run the script manually for same-tick relief.** Stanzas and live churn drift
apart: a driver the script does not name (e.g. a backup-staging dir grown by a one-off
verification run) contributes nothing to the cron and stays full until a stanza is added
(a config/owner decision, not a lane action). Prove a backup-staging dir is dead before
treating it as debris: stale `.lock` mtime (hours, not minutes) + no matching live process
(pgrep) + no mtime-fresh payload files. The manual rerun of the existing script is the safe
non-destructive relief — run it, then re-read df as the before/after witness; the structural
stanza addition stays an owner decision named in the tick row.

## A SIGKILLed backup run strands its staging debris — the EXIT trap is not a cleanup guarantee

**When disk pressure traces to backup/staging debris whose log ends mid-step with no DONE line
and no live process, run the OOM differential FIRST, then reclaim by exact filename.** The
script's `trap staging_cleanup EXIT` only fires on graceful exits; an external kill strands
the whole staging dir including files the log's own `rm` lines claim get removed. Differential:
`journalctl -t earlyoom` healthy across the kill window + `oom_kill` counter flat (mem-monitor
MEM_SNAP or `/proc/vmstat`) + no kernel `Killed process` line = external SIGKILL, NOT memory
pressure — do not tune memory, do not hunt an OOM that never happened. The kill mechanism is
often unprovable from logs; say so plainly and move on. Reclaim the debris with the exact
paths from `ls -lh` (tmp_legacy/verify db files, orphaned snapshot tars), then record df
before/after as relief evidence. The durable fix is a start-of-run sweep of stale
`$$.db`-pattern debris, not a trap edit.

## /var/log growth: verify the logrotate config actually wins before closing the row

- **On a Hermes box, suspect /var/log churn first.** The snoopy command audit logs every Hermes
terminal command several times with full payloads (multi-GB/day), so diagnostic commands
themselves feed the flood — keep probes few and bounded. Safe reclaim order: force a rotation
with the drop-in that owns the path (`logrotate -f /etc/logrotate.d/<winner>`), then
`journalctl --vacuum-size=500M`. Never delete a live log; changing the audit/logrotate POLICY
needs an owner decision, but repairing a BROKEN rotation config is lane work.
- **A drop-in fix that never takes effect is not a fix.** logrotate errors on any path claimed
by two files under /etc/logrotate.d/ and SKIPS the losing files entirely (`duplicate log entry
for ...` in `logrotate -d` output) — a shipped cap drop-in can be dead for days while
`logrotate.service` fails exit-1 every night unnoticed. Before closing any logrotate repair:
(1) `grep -rln <logpath> /etc/logrotate.d/` shows ONE claimant — dedupe by removing the losing
drop-ins or the competing line inside a multi-log stanza, keeping the cap stanza; (2) the
claimant carries `su <user> <group>` when /var/log is group-writable (without it rotation dies
with "insecure permissions"); (3) pre-existing compressed rota files (`.gz`, stale `.old.gz`)
can block rename steps — archive or move them; (4) confirm `logrotate /etc/logrotate.conf`
exits 0 and the live log's size/mtime reset. Gzip-ing the uncompressed `*.1` (delaycompress
leaves yesterday's plain — that is where the GBs sit) is relief, but the rotation bug is the
root cause: fix it in the same tick or the log regrows within hours on a chatty host.

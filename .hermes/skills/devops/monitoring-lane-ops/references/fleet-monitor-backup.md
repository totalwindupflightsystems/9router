# fleet-monitor backup + restore-check reference

Stack self-backup runs as the systemd unit `fleet-monitoring-backup.service` (static), triggered
by `fleet-monitoring-backup.timer` (nightly). ExecStart = `/root/fleet-monitoring/backup-to-s3.sh`
with an ExecStartPost `restore-check.sh` that downloads the newest set, verifies sha256s,
re-clones the git bundle, and tar-tests the Prometheus snapshot (exit PASS = full chain verified).
Destination comes from `S3_BUCKET`/`S3_PREFIX` in `/root/fleet-monitoring/.env` (currently
`s3://karahermes-hel/monitoring/<date>_<ts>`) — READ the .env before checking a prefix; the
host-backup convention (`s3://dexdat-backups/<host>/`) does NOT apply here.
Freshness stamp: `/var/lib/fleet-monitoring/node-exporter-textfile/fleet_monitoring_backup.prom`
(`monitoring_backup_last_success_timestamp_seconds`; per-job stamps for `exported_job=kara-hermes`
and `cube-agent` live in `backup-freshness.prom`).

## Diagnosis recipe (firing BackupFreshnessStale on fleet-monitor)

1. `systemctl status fleet-monitoring-backup.service` + `journalctl -u ... --since '-2 days'` —
   the journal shows the run, the manifest, the upload target and the RESTORE-CHECK verdict.
   A unit that exited 0/SUCCESS with a PASS restore-check minutes/hours ago is the opposite of a
   stale backup.
2. Check the ALERT RULE's expression against the actual series — do not trust either alone:
   - The rule may query a metric name the publisher no longer writes (empty vector = firing on
     absence, and the fix is the rule/metric name, not the backup).
   - The series may carry TWO sibling families under one metric name: the host's own stamp (no
     `exported_job`) and the per-job stamps from the lane box (`exported_job=kara-hermes|cube-agent`)
     — rules without an `exported_job` matcher can fire on the wrong sibling. A freshness alert
     whose firing instance's `exported_job` is blocked/absent is the honest signal for THAT job
     only; verify the host's own series (`time() - <metric>` per instance) before concluding.
3. Verify at the DESTINATION, not the stamp: list the S3 prefix (rclone/awscurl), confirm a
   current MANIFEST.txt + file count; the journal's upload line names the exact prefix.
4. A suspected 'aws: command not found' log tail can predate the PATH fix — the fix IS in the
   script (`export PATH="$HOME/.local/bin:$PATH"` at the top). Read failure lines' DATES vs when
   the fix landed, and read the artifact back from S3 (`aws s3 ls <prefix>` + `cp STATUS -`) with
   `AWS_PROFILE=<profile from the script> --endpoint-url <S3_ENDPOINT from the script>`: a stamp
   with MANIFEST + VERIFY-PASS lines proves the pipeline works and the row closes no-op-verified.
5. Per-job backup scripts live on the LANE box (`~/.hermes/scripts/`), not the monitoring host;
   their cron entries are in kara's crontab. Root-SSH-based backups (cube-agent pattern) fail at
   the tar-stream step with rc=255 when the target's root authorized_keys are orphaned — before
   filing 'pipeline dead', probe the AGENT-level SSH surface (`ssh -i ~/.bunker/keys/<id>
   bunker-<id>@<host>`), which has separate keys and proves the data intact.

Rules:
- **An alert still FIRING with an empty-vector/false expression can self-resolve after the next
  rule eval — re-query `/api/v1/alerts` after one eval cycle (~30s) before writing any fix.**
  A firing alert is a snapshot, not a live predicate; the fix may already have landed in the
  producer and only the alert state lags.
- **Verify WHICH series the expr matched (per-instance freshness query) before diagnosing the
  backup — a rule firing on the `exported_job=cube-agent` sibling (value 0 = never completed) is
  a DIFFERENT finding from the host stamp being stale, and the host half can already be green.**
- The restore-check PASS line in the journal is the strongest single witness for a healthy
  pipeline (it proves upload + download + checksums + bundle clone + tar readability end to end).

## S3 large-object upload failures: orphaned MPUs prove the pattern, staleness proves the gap

**A silent `ERROR: S3 ... failed` line means the multipart upload died mid-stream — measure
staleness per system and list orphaned MPUs before calling it a one-off.** Grep the backup log
for the S3 leg, then check what is ACTUALLY on the bucket:
`aws s3api list-multipart-uploads --bucket <b> --prefix backups/` plus `aws s3 ls` of each
tier. Orphaned MPUs accumulating over days (list shows entries with old Initiated dates) plus
a newest-completed-object date lagging the local leg by days = a recurring large-object
failure pattern, not noise. Typical signature: ~10G objects time out around 4-5GiB ("Read
timeout on part N"), the script's size-match check silently rejects, and — critically —
`abort-multipart-upload` returns 500/504 provider errors and CANNOT be cleared client-side.
Do not burn the tick retrying aborts or repeated re-uploads: retry the upload ONCE in
background with `--multipart-chunksize 64MB --multipart-threshold 64MB`; if it fails too,
file ONE open finding carrying (a) the orphan MPU list, (b) per-system staleness (newest
completed object per system on S3), (c) the structural fix — an AbortIncompleteMultipartUpload
lifecycle rule or a provider support ticket. Record which LOCAL snapshots exist and their
`zstd -t` status: they are the real restore path while S3 is stale, and saying so distinguishes
'backup broken' from 'offsite copy lagging'.

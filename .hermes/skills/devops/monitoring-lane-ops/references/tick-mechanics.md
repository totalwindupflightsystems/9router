# Tick mechanics: board rows, remote queries, alert verification

## Remote Prometheus JSON: parse on the lane box, not on fleet-monitor

fleet-monitor has no jq and rebuilding a broken pipeline burns the tick window: fetch with
`ssh fleet-monitor 'curl -s http://localhost:9090/api/v1/<alerts|query> ...'` and pipe into a
small python3 reader running ON THE LANE BOX. For gauge ages, walk `data.result` and print
`(time.time()-float(m["value"][1]))/86400` days per series.

## Tick-note board rows: build the JSON in a /tmp file, never inline

Inline `jq -nc --arg` row construction breaks on quoting (one bad flag aborts the whole append
and the appender refuses the resulting empty append). Flow: write_file the full row JSON to /tmp,
then `python3 ~/.hermes/scripts/board_append.py .coding-hermes/board/tasks.jsonl "$(cat /tmp/<row>.json)"`
— the ROW is the argument, the board path is not accepted as one.

## Commit and push discipline for the lane board

The lane worktree shares the home repo with sibling lanes: stage and commit BY PATHSPEC
(`git add -f .coding-hermes/board/tasks.jsonl && git commit -m "..." -- .coding-hermes/board/tasks.jsonl`),
push the lane branch, then prove it: `git fetch origin && git rev-list --count origin/<branch>..HEAD`
must print 0 before the tick ends.

## CI health check on this lane

Derive org/repo from `git remote -v` first — the lane repo's origin may be an s3 mirror rather
than GitHub. An empty `gh run list` result = the repo carries no workflows; quiet repo, nothing
to flag.

## BackupFreshnessStaleWeekly: query ALL series before treating the alert as real

The gauge `monitoring_backup_last_success_timestamp_seconds` carries an UNLABELED series (the
stack's own backup) plus `exported_job="kara-hermes"|"cube-agent"` series. The alert's host
label is always fleet-monitor, so a stale exported_job series reads as if the stack's own
backup were stale — a label-swap false positive that recurs. Split the metric per series and
compare ages: own-backup hours-fresh while cube-agent is weeks stale is the known owner-gated
row, not a new finding.

# Closed-Loop Audit — the angle for lanes that only ever gather

When a dogfood target is an audit/report lane (gather → judge → inject rows), the
easy surfaces (determinism, dedupe, delivery, key currency, coverage, noise,
failure modes, install) get owned within a few runs. What stays un-owned is the
loop's OUTPUT half: does a filed row ever produce a fix? Audit that directly.

## Procedure

1. **Tick ledger:**
   ```sql
   SELECT date(created_at), count(*), sum(board_commits), sum(code_commits)
   FROM ticks WHERE project_name='<lane>' GROUP BY 1;
   ```
   Many ticks since the first finding-row date with `sum(board_commits)=0 AND
   sum(code_commits)=0` = the lane is billing cycles and changing nothing.
2. **Row-fate census:** for every row the lane's family filed (`grep` the row-id
   prefix on all destination boards), count rows still in their created status
   with zero status transitions. Zero transitions across the whole family =
   write-only board.
3. **Fix-landing check:** compare the deployed copy of the audited tool
   (`stat -c %y` / `sha256sum`, usually under `~/.hermes/scripts/`) against the
   dates of the fix-rows it owns. A one-line fix row pending across many cycles
   with the tool's mtime older than the row's date proves the fix never landed.
4. **Consumer check:** for rows routed to a queue board, name the foreman whose
   prompt makes it WORK those rows. If the only enabled lane on that repo is the
   gathering lane itself (its prompt only gathers/judges/injects), the rows are
   write-only — the injection proved delivery, nothing proved consumption.

## Filing

A dead loop is a P1 row of its own, distinct from any per-defect row: "rows
never produce fixes — N ticks / M cycles with 0 commits, all family rows
pending, deployed tool untouched". The remediation options belong IN the row:
(a) foreman actually works its rows, (b) the lane prompt gains a sweep+act step
for its own queue rows, or (c) accept the lane is report-only and stop billing
ticks for it — that last decision is the owner's, so surface it, don't make it.

## Judgment

A lane can be genuinely useful (deterministic, exact re-derivable evidence) and
still fail this angle — 'PROMISING-BUT-ROUGH (unchanged)' is the honest verdict
when the gather half is solid but the loop is dead. Do not blend the surfaces.

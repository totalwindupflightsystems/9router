# Lane parity: spool census + alert-rule lane allowlist

## Prove 0 UNWRITABLE by censusing the spool by lane label

When the drain reports 0 UNWRITABLE, do not take the count as exhaustive — the per-window
UNWRITABLE line only fires for rows the drain ATTEMPTS that window; a row already deduped
against a board is never re-attempted, so a rule that names a dead lane can hide behind the
skipped count forever. Prove it by census:

1. scp the spool to the lane box: `scp fleet-monitor:/var/lib/fleet-monitoring/spool/board-rows.jsonl /tmp/spool.jsonl`
2. Parse locally (lane box has jq; the monitor does not): group rows by
   `(row.get('lane') or 'monitoring')` and count per lane.
3. For each lane label, check a board exists on the lane box: `~<lane>/.coding-hermes/board/tasks.jsonl`.
4. A lane label with no matching board = an alert rule spools rows that can NEVER land —
   the fix is in the rule (relabel to a real lane), then clear the superseded spool rows
   under the dead lane.

The same census disproves a scary-looking EMPTY `/boards` mount on fleet-monitor: the
container-side BOARD_ROOT is a self-mount (`/boards -> /boards`), not a real directory —
the spool is the truth about what was produced, and the drain's dedupe is the truth about
what landed.

## Alert-rule lane governance belongs in lint, as an allowlist

Validate every rule's `lane:` label against a checked-in allowlist, not against a live-host
directory listing. In the repo's `scripts/lint-configs.sh`, add a step that greps each
`alerts/rules/*.yml` for `^\s*lane:\s*(\S+)` and fails any label absent from a checked-in
`alerts/lanes.txt` (one lane per line, `#` comments allowed, with a header comment saying
what the lane list means: a lane here must have a board on the fleet host running the
drain script). An alert naming a lane with no board spools forever and never becomes
executed work — the allowlist turns that failure from a silent drain-side UNWRITABLE into
a red lint at commit time.

Test the check BOTH directions before closing the change: run lint clean (positive), then
plant a fake lane in one rule (backup the rule file first), expect the BAD line naming
that rule, restore, and re-run clean. A lint step only ever proven on the passing path can
be silently broken by its own regex — the negative test is the only proof the check bites.

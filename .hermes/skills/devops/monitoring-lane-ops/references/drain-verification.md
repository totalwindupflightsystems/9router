# Verifying a spool drain

The drain prints `drained: appended=N skipped=M`. Neither number alone tells you the run was
clean — read them with the id diff below.

## The `skipped` counter is overloaded

Two different conditions increment it, and only one of them is visible in the output:

- **Already-drained dedupe hit** — the normal case. The row id is already on the target board.
- **Genuinely unwritable** — the row's `lane` names a board directory that does not exist. This
  one also prints `  no board for lane '<lane>' — leaving spooled`. The fix is in the alert
  RULE (it names a lane with no board), never in the row.

So: absence of that `no board for lane` line is evidence, but it is one grep away from being
missed. Prove it independently.

## Prove it with a set diff

Collect every `id` from the spool, collect every `id` on the target board, subtract:

```python
import json, glob
board = {json.loads(l)["id"] for l in open("tasks.jsonl") if l.strip()}
spool = {json.loads(l)["id"] for f in glob.glob("/tmp/fleet-monitoring-spool/*.jsonl")
         for l in open(f) if l.strip()}
missing = sorted(spool - board)   # 0 => every spooled row already landed
```

A **zero-missing** result is the only thing that distinguishes "nothing new" from "silently
unwritable". Also census the distinct `lane` values in the spool and confirm each has a board
dir under `$BOARD_ROOT/<lane>/.coding-hermes/board`.

The leftover id set doubles as the triage list: those are the findings currently open on boards.

## Spool paths and the never-cleared backlog

- Remote (monitor host): `/var/lib/fleet-monitoring/spool/`
- Local copy after the rsync: `$SPOOL`, default `/tmp/fleet-monitoring-spool/`

Clearing the remote spool is **deliberate and manual** — the script says so, and it must stay
manual until the rows are confirmed landed. Consequence: every re-run re-fetches and re-dedupes
the entire backlog, so **`appended=0` is the permanent steady-state output** and carries no
information about whether anything is new. Read newness from the id diff, not the append count.

## Row anatomy worth knowing

Spooled rows carry `id`, `lane`, and either a finding shape (`title`, `status`, `priority`) or a
resolution shape (`type: "alert-resolved"`, `alertname`, `host`, `severity`, `resolved_at`).
Fingerprint-style ids are `MON-<LANE>-<FP8>-<YYYYMMDD>`, with `-RESOLVED` twins for clear
events — both share the base fingerprint, so dedupe on the full id string including the date
and the suffix.

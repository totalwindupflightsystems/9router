# Sibling id collision — recovery recipe (dogfood board rows)

Applies when appending board rows to a shared JSONL board from a dogfood (or any
multi-sibling lane) tick. Complements the SKILL.md pitfalls: Step 4's post-append
uniqueness re-check, and the 'grep the max AFTER the wave of sibling writes'
pitfall. This file is the concrete procedure when the collision ALREADY HAPPENED.

## Detect

You appended rows under ids chosen from a pre-append census; the post-append
`jq -r '.id' | sort | uniq -d` reports duplicates in your id family. A sibling
lane minted rows with the same next ids between your census and your append —
a working-tree grep can miss this entirely (the sibling's rows may land in the
same file seconds after your census), so the post-append diff is the only
dependent check.

## Census poisoning: id families that mix shapes

Derive the max id with a pattern that matches ONLY your task-row shape
(`"id"\s*:\s*"PREFIX-\d{1,3}"` — a bounded digit count, not `\d+`). Boards
carry other rows in the same id namespace with different shapes — dated
event ids (`PREFIX-20261007`), status echoes, satellite-lane rows — and a
greedy `\d+` census reads them as task ids, so `max+1` appends your rows
into the wrong namespace entirely (real case: a `LORE-\d+` census caught
`LORE-20261008` and the append script renumbered the batch onto garbage
ids). Bind the digit count to the family's real width, and sanity-assert
the derived max equals the last KNOWN task id (e.g. the id from your
pre-tick board read) before appending — an unexpected max means the census
caught a foreign shape, not a sibling.

## Detect a sibling commit BEFORE your append, not after

The 'check for a same-day sibling dogfood commit' pitfall says check before
designing the run — but a sibling can land DURING your probes. Re-run the
check in the same script that appends: `git log --oneline --grep 'dogfood:'`
immediately before the census, and again before committing. If a sibling
run committed between your log read and your append, `git checkout HEAD --
<board>` to restore the canonical board FIRST, then census and append under
the next free ids — appending into a working tree whose HEAD has moved
forward strands your rows behind a clean checkout and clobbers the
sibling's committed rows on any later restore. When restoring, identify
your OWN working-tree-only rows by the `created_by` tag (never by id or
title): title phrases overlap between sibling runs testing the same
surface, and an id you already renumbered no longer identifies anything.

## Recover (one pass, not one row at a time)

1. Never delete either side: both are real findings. The sibling rows stay
   byte-untouched; only YOUR rows move.
2. Identify your rows by a distinctive-title assertion, never by id alone: load
   each candidate row, assert a substring of YOUR title, count hits — exactly 1
   per row. A sibling row sharing any phrase in `title`/`reasoning` must not be
   touched, and an id-only match can rename the wrong row. When your rows carry
   a `created_by` tag, prefer tag-scoped removal/renumber over title matching —
   it is the one marker that cannot collide with a sibling testing the same
   surface (two sibling runs can file near-identical titles on the same day).
3. Re-scan the live id set ONCE (`grep -oE '"id":"PREFIX-[0-9]+"' board`, take
   numeric suffixes), pick the next free ids for ALL your collided rows in that
   single pass, and rewrite them in one scripted pass. Renumbering one row at a
   time with a fresh scan between each re-derives free ids the sibling has
   meanwhile taken and costs an extra edit cycle per row.
4. Keep the renumber loop scoped to rows matching id AND your title marker;
   pass everything else through byte-identical.
5. Re-verify after the pass: `jq -r '.id' | sort | uniq -d` must be EMPTY file-wide
   (both families now unique), and a before/after id-census diff must show exactly
   your final rows under the new ids with the sibling rows' byte content unchanged.
6. Expect the collision cost: ~1 extra edit cycle per collided id family, not a
   re-run of the tick. Commit by explicit pathspec afterwards as usual.

## Same-tick twin: a parallel instance of YOUR OWN tick

Sibling collisions are not limited to other lanes' row ids — the same tick can run
twice (dispatch overlap or a retry), and the twin commits under the IDENTICAL
actor/tick id, so it hides from a per-lane census. Before writing anything, grep the
board's events.jsonl and the project's dogfood log for your own tick actor string;
if a twin already landed a commit, treat its artifact as a companion, not a duplicate
to re-file or to inherit silently: cross-cite it in your log entry ('companion to
<sha>'), commit only the files yours adds by pathspec, and after pushing verify
`git merge-base --is-ancestor HEAD origin/main` instead of trusting the push output.
Do NOT skip your own log entry because the twin 'already covered the angle' — a twin
can commit an event or board row while writing no log entry, and the entry is what
later greps resolve; two cross-citing log entries are correct, two identical events
are the waste to avoid. The twin's tree may also carry a foreign UNCOMMITTED patch
(a worker harvest left in the main tree): never `git add -A` over it — pathspec only,
and name the foreign patch in your report rather than touching it.

## Prevention that already exists elsewhere

- Grep the numeric max immediately before appending (and per append batch).
- Tag rows with a unique `created_by` so your rows are self-identifying for any
  later renumber; scope uniqueness assertions to your own rows only (a file-level
  check false-FATALs on pre-existing sibling dupes, firing mid-write after your
  rows already landed).
- The run-number variant: `dogfood-log.md` run numbers collide exactly the same
  way — grep the log for the next free number immediately before appending, and
  pick the docs artifact filename from the FINAL number.

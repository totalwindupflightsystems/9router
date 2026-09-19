# `.coding-hermes/board/` — JSONL-canonical task board

The board is **git-tracked JSONL**, not a database. DuckDB reads it directly with
`read_json_auto`; `board.db` / `*.parquet` are untracked rebuildable caches and are
never the source of truth.

| File | Role |
| --- | --- |
| `tasks.jsonl` | one JSON object per row: the canonical task board (append-mostly) |
| `events.jsonl` | append-only event log (`board_init`, `spec_created`, `audit`, …) |
| `board.jsonl` | one header row: project / namespace / tick counters / cooldown |
| `fixtures.jsonl` | perpetual tasks (NEVER-DONE, E2E-001, GITREINS-JUDGE) |
| `schema.sql` | the DuckDB view of the JSONL shape (types for the tables above) |

## Duplicate ids are intentional — and that is the hazard

Rows are **never renumbered**. Dogfood and QA cycles deliberately re-file the same
slot id once per cycle, so several historical *generations* of one id coexist with
different meanings. Measured at tick 398 (`node scripts/board-task.mjs duplicates`):

```
180 rows / 157 distinct ids / 8 ids carry more than one generation (31 rows total)
  QA-9ROUTER-1 x9   lines 76,83,86,91,99,100,106,107,109
  QA-9ROUTER-2 x5   lines 77,84,87,92,101
  DF-9ROUTER-1 x3   lines 71,78,94      DF-9ROUTER-4 x3   lines 74,81,97
  DF-9ROUTER-2 x3   lines 72,79,95      DF-9ROUTER-5 x3   lines 75,82,98
  DF-9ROUTER-3 x3   lines 73,80,96      QA-9ROUTER-3 x2   lines 85,88
```

An id-only "find the row and update it" helper resolves the **first** line that
matches, so completing today's generation rewrites a defect row from a cycle ago.
This is not hypothetical: on tick 336 (`BOARD-ID-001`, row at `tasks.jsonl:105`)
a first-match completion helper wrongly completed `DF-9ROUTER-3` (line 73,
`npm run cli:pack` fails — esbuild) and `DF-9ROUTER-5` (line 75,
`REQUIRE_API_KEY ignored`) while the live rows (lines 96/98) stayed pending; the
damage had to be corrected by line-targeted surgery plus a correction event.

## Safe mutation: `scripts/board-task.mjs`

`scripts/board-task.mjs` (npm: `npm run board:task -- <command>`) is the
repository-owned, fail-closed mutation path. It **refuses an id-only mutation when
the id is not unique** and requires an explicit discriminator that narrows the
match to exactly one row — it never falls back to first match, and it does not
quietly fall back to last match either (LAST is still a guess when generations are
not monotonic).

```bash
# 1. Which ids have several generations, with their line numbers?
npm run board:task -- duplicates

# 2. What would an id-only mutation hit? (read-only)
npm run board:task -- resolve --id QA-9ROUTER-1

# 3. Complete ONE intended generation (refuses if the witness is not unique)
npm run board:task -- update --id DF-9ROUTER-1 --ts 2026-09-13T13:10:59.889Z \
    --set status=complete --set worker_status=complete

# 4. Rehearse first — --dry-run resolves and reports, writes nothing
npm run board:task -- update --id QA-9ROUTER-1 --line 100 --dry-run --set status=complete
```

### Discriminators (ANDed when several are supplied)

| Flag | Selects |
| --- | --- |
| `--line N` | exact 1-based physical line number (row identity) |
| `--created-at VALUE` | exact `created_at` match; `null` / `-` matches rows where the field is absent |
| `--ts VALUE` | exact `ts` match; `null` / `-` matches rows where the field is absent |
| `--title-contains TEXT` | `title` substring (case-sensitive) |
| `--detail-contains TEXT` | `detail` substring (case-sensitive) |

Older rows carry `created_at` and no `ts`; dogfood/QA rows carry `ts` and no
`created_at`, so both shapes are addressable, and identical titles are separated by
their `ts` witness (lines 99/100 are such a pair).

### Exit codes

| Code | Meaning |
| --- | --- |
| 0 | ok — updated / would-update / no-change / resolved / report |
| 2 | **ambiguous** — refused, competing candidates printed, nothing written |
| 3 | not found — the id or the discriminator matched no row, nothing written |
| 4 | usage error (bad flag, no `--set`, `--set id=…`) |
| 5 | invalid board — a line does not parse as JSON, or an internal invariant failed |

On refusal the tool prints every competing candidate with its line number, status,
`created_at`, `ts` and title, plus the discriminators that would disambiguate, and
the marker `NO FILE WAS MODIFIED`.

### Compatibility and guarantees

* **Unique ids are unchanged.** An id that matches exactly one row still updates
  with no discriminator, so existing single-generation usage keeps working.
* **Historical duplicate rows are preserved.** Nothing is renumbered, merged,
  re-idded or deleted; this tool only ever rewrites the single selected line.
* **Byte preservation.** The target line is the only line re-serialized; every
  other line (odd whitespace, key order, unicode escapes) is copied verbatim and
  the invariant is asserted in-process before the write. The write itself is
  atomic (temp file + rename in the same directory).
* **Determinism.** No implicit timestamps: `updated_at` / `completed_at` change
  only when the caller passes them via `--set`.
* **Fail closed on an unparseable line (exit 5).** The file is rewritten whole, and
  a torn line could itself be another generation of the id, so uniqueness would be
  undecidable.
* **`--set id=…` is refused (exit 4).** The id is the identity being resolved;
  re-idding a historical generation is a separate, explicit operation.

### Residual limitations

* The guard protects mutations **made through it**. An external helper that
  implements its own first-match lookup (for example the fleet-side
  `append_board_task_completed.py`, which lives outside this repository) can still
  rewrite the wrong generation until the caller routes the mutation through
  `scripts/board-task.mjs`.
* `--line` is positional identity: appends never renumber existing rows, but a
  manual rewrite/reorder invalidates it. Prefer `--ts` / `--created-at` (stable
  field identity) when the row has one.
* The guard does not enforce unique ids on **append** — one-per-cycle slot ids are
  the fleet's intentional filing convention, so the guarantee is mutation safety,
  not global uniqueness.

### Verification

```bash
cd tests && ./node_modules/.bin/vitest run unit/board-task-guard.test.js   # 28 focused tests
node --check scripts/board-task.mjs                                       # syntax
node scripts/board-task.mjs duplicates --fail-on-duplicate                # board-level check
```

The tests cover the three selection cases (refused duplicate-id mutation, explicit
discriminator selecting exactly one generation, unique id unchanged) plus
byte-preserving untouched lines, exit codes 2/3/4/5, `--dry-run`, idempotent
re-runs and the unparseable-line refusal.

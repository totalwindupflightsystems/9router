#!/usr/bin/env python3
"""Append the GitReins tier-1 evidence to MON-GAP-036 and the verdict line to MON-REV19-06.

Line-wise: parse each line, re-dump ONLY the touched rows, assert the exact hit count
before writing. Ids are unique on this board for both rows (verified by census).
"""

import json
import sys

BOARD = "/home/kara/monitoring/.coding-hermes/board/tasks.jsonl"

GAP036_NOTE = (
    "\n\n=== FRESH INSTANCE 2026-10-23 (tick monitoring-foreman-2026-10-23-08-44-31) ===\n"
    "Closed MON-REV19-06 (commit ec6cef4, diff = scripts/verify.sh only, 43+/6-) and ran "
    "`gitreins task complete MON-REV19-06` in /home/kara/fleet-monitoring. Tier 2 returned COMPLETE "
    "(verdict .gitreins/history/2026-10-23/590e6c95/verdict.json), but the verdict's overall "
    '"passed" is FALSE because tier1 failed on the SECRETS step, and the step\'s evidence is a STALE '
    "guard log: data.guard_log = .gitreins/logs/guard-20261016T021612.982713Z.log, file mtime "
    "2026-10-15 21:16 (8 days before the commit). The finding it replays is "
    '".env.example: SENSITIVE PATH (credential-store path class)" - a file that is NOT in the commit '
    "diff at all. WHY NO FRESH LOG EXISTS: this checkout has core.hooksPath=/var/tmp/foreign-hooks, so "
    "the commit ran a foreign pre-commit and no new .gitreins/logs/guard-*.log was written; "
    "`ls -t .gitreins/logs/` newest entry is still 2026-10-16. Reinforces the row's own thesis: the "
    "tier-1 secrets verdict in this repo is a function of whatever guard log happens to be on disk, "
    "not of the change being judged. Do NOT read a tier-1 FAIL here as a merit signal; read the diff "
    "and tier 2. Fix shape is unchanged: either the judge must run the guard itself in-commit (fresh "
    "log) or the secrets step must scope to the commit diff instead of replaying the newest log."
)

REV19_NOTE = (
    "\nGITREINS: `gitreins task complete MON-REV19-06` -> tier2 COMPLETE (criteria verified from the "
    'file: query_range at line 115, loki_selector default {job="fleet"} at 101-102, 0 lines -> bad() '
    '-> exit $fail at 126-127); overall "passed" FALSE solely because tier1 secrets replayed the stale '
    "guard log guard-20261016T021612.982713Z.log (mtime 2026-10-15) whose finding is .env.example, a "
    "file not in this commit. Recorded on MON-GAP-036 as a fresh instance; not a merit failure."
)

TARGETS = {
    "MON-GAP-036": GAP036_NOTE,
    "MON-REV19-06": REV19_NOTE,
}


def main():
    with open(BOARD, encoding="utf-8") as fh:
        lines = fh.readlines()

    hits = {}
    for idx, line in enumerate(lines):
        if not line.strip():
            continue
        row = json.loads(line)
        rid = row.get("id")
        if rid in TARGETS:
            hits.setdefault(rid, []).append(idx)

    for rid in TARGETS:
        found = hits.get(rid, [])
        assert len(found) == 1, f"{rid}: expected exactly 1 row, found {found}"

    out = []
    touched = []
    for idx, line in enumerate(lines):
        row = json.loads(line) if line.strip() else None
        if row and row.get("id") in TARGETS:
            rid = row["id"]
            note = TARGETS[rid]
            if note in (row.get("reasoning") or ""):
                raise SystemExit(f"{rid}: note already present, refusing to duplicate")
            row["reasoning"] = (row.get("reasoning") or "") + note
            row["updated_at"] = "2026-10-23T09:12:00Z"
            out.append(json.dumps(row, ensure_ascii=False) + "\n")
            touched.append(idx + 1)
        else:
            out.append(line)

    with open(BOARD, "w", encoding="utf-8") as fh:
        fh.writelines(out)

    with open(BOARD, encoding="utf-8") as fh:
        new_lines = fh.readlines()
    assert len(new_lines) == len(lines), (len(lines), len(new_lines))
    for line in new_lines:
        json.loads(line)
    changed = [i + 1 for i, (a, b) in enumerate(zip(lines, new_lines)) if a != b]
    print("touched rows (line numbers):", touched)
    assert changed == touched, (changed, touched)
    print("OK rows", len(new_lines))


if __name__ == "__main__":
    sys.exit(main())

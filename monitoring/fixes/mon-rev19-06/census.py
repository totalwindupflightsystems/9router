#!/usr/bin/env python3
"""Census of board rows for this tick's ids. Read-only."""

import json

BOARD = "/home/kara/monitoring/.coding-hermes/board/tasks.jsonl"
rows = []
with open(BOARD, encoding="utf-8") as fh:
    for line in fh:
        if line.strip():
            rows.append(json.loads(line))

print("total rows", len(rows))
for tid in (
    "MON-REV19-06",
    "MON-DISK-20261023",
    "MON-MONITORING-FA5F538B-20261023",
    "QA-MONITORING-006",
):
    hits = [
        (i, r.get("status"), r.get("created_at") or r.get("created"))
        for i, r in enumerate(rows)
        if r.get("id") == tid
    ]
    print(tid, hits)

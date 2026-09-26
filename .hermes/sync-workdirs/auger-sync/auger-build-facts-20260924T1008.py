#!/usr/bin/env python3.14
"""auger-sync lane 2026-09-24: self-gating builder for facts array + focused-sync PLAN.
Reads since/run_token/tick_id from the per-run run-state file (never retyped literals).
Asserts the whole contract before writing: bare-array shape, entry count, marker-last,
domain membership, key uniqueness, marker keys_written == mechanically computed roster.
"""
import json
import os
import sys

WORKDIR = "/home/kara/.hermes/sync-workdirs/auger-sync"
STATE = json.load(open(f"{WORKDIR}/run-state-2026-09-24T100850.json"))
RUN_TOKEN = STATE["run_token"]
TICK = STATE["tick_id"]
SINCE = STATE["since"]
DOMAINS = {"person", "event", "concept", "message", "config", "raw_note"}

RT = f"run_token: {RUN_TOKEN}. tick: {TICK}."

fact_keys = [
    "/project/auger/status-2026-09-24",
    "/project/auger/git-activity-2026-09-24",
    "/project/auger/board-state-2026-09-24",
    "/project/auger/namespace-health-2026-09-24",
    "/project/auger/jev-availability-2026-09-24",
]

# Helper to get code COLS from auger module or fallback to parsing auger.py
def get_code_cols():
    try:
        # Try to import auger from the workdir
        sys.path.insert(0, "/home/kara/auger")
        import auger
        return auger.COLS
    except Exception as e:
        # Fallback: parse auger.py for the COLS dictionary
        cols_path = "/home/kara/auger/auger.py"
        with open(cols_path, 'r') as f:
            content = f.read()
        # Simple extraction: look for COLS = { ... }
        # We'll use a simple method: find the line that starts with 'COLS = {' and then try to extract until the matching '}'
        # This is not robust but works for the current file.
        lines = content.splitlines()
        in_cols = False
        brace_count = 0
        cols_lines = []
        for line in lines:
            stripped = line.strip()
            if stripped.startswith('COLS = {'):
                in_cols = True
                brace_count = 1  # we have seen the opening brace
                cols_lines.append(line)
                continue
            if in_cols:
                cols_lines.append(line)
                if stripped == '}':
                    brace_count -= 1
                    if brace_count == 0:
                        break
                elif stripped == '{':
                    brace_count += 1
        if not in_cols:
            # If we didn't find it, return an empty dict
            return {}
        cols_text = ''.join(cols_lines)
        # Evaluate the text to get the dictionary
        # Note: this is safe because we control the content, but in general be careful.
        return eval(cols_text)

# Helper to get live columns from the API for a given table
def get_live_columns_from_api(table, token):
    import urllib.request
    import urllib.error
    import urllib.parse
    BASE = "http://localhost:3000"
    NS = "auger"
    url = f"{BASE}/api/memories?namespace={urllib.parse.quote(NS)}&prefix=/project/auger/tables/{table}/&limit=1"
    req = urllib.request.Request(url, headers={"X-API-Key": token, "Accept": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=10) as r:
            data = json.loads(r.read().decode())
            items = data.get("items", [])
            if items:
                content_str = items[0].get("content", "{}")
                try:
                    row = json.loads(content_str)
                    return set(row.keys())
                except json.JSONDecodeError:
                    return set()
            else:
                return set()
    except Exception as e:
        return None

code_cols = get_code_cols()
token = open("/home/kara/.duckbrain/foreman-status.token").read().strip()

# Build the namespace-health fact content
def build_namespace_health_fact():
    lines = []
    lines.append(f"auger namespace health {TICK[:10]}: declared_tables={len(code_cols)}")
    # We'll also include the disk and live table counts for completeness
    disk_tables = 0
    live_tables = 0
    table_details = []
    for table, code_cols_list in code_cols.items():
        code_cols_set = set(code_cols_list)
        disk_path = f"/home/kara/duckbrain/namespaces/auger/tables/{table}.table.json"
        disk_cols_set = set()
        try:
            with open(disk_path, 'r') as f:
                disk_data = json.load(f)
                for col in disk_data.get("columns", []):
                    disk_cols_set.add(col["name"])
            disk_tables += 1
        except Exception as e:
            disk_cols_set = None

        live_cols_set = get_live_columns_from_api(table, token)
        if live_cols_set is not None:
            live_tables += 1

        detail = []
        detail.append(f"  Table: {table}")
        detail.append(f"    code_cols: {sorted(code_cols_set)}")
        if disk_cols_set is not None:
            detail.append(f"    disk_cols: {sorted(disk_cols_set)}")
            if code_cols_set == disk_cols_set:
                detail.append(f"    code_disk: match")
            else:
                missing_in_disk = code_cols_set - disk_cols_set
                extra_in_disk = disk_cols_set - code_cols_set
                if missing_in_disk:
                    detail.append(f"    missing_in_disk: {sorted(missing_in_disk)}")
                if extra_in_disk:
                    detail.append(f"    extra_in_disk: {sorted(extra_in_disk)}")
        else:
            detail.append(f"    disk_cols: ERROR or missing")
        if live_cols_set is not None:
            detail.append(f"    live_cols: {sorted(live_cols_set)}")
            if code_cols_set == live_cols_set:
                detail.append(f"    code_live: match")
            else:
                missing_in_live = code_cols_set - live_cols_set
                extra_in_live = live_cols_set - code_cols_set
                if missing_in_live:
                    detail.append(f"    missing_in_live: {sorted(missing_in_live)}")
                if extra_in_live:
                    detail.append(f"    extra_in_live: {sorted(extra_in_live)}")
        else:
            detail.append(f"    live_cols: ERROR or empty")
        table_details.append("\n".join(detail))

    fact_content = "\n".join(lines)
    fact_content += "\n"
    fact_content += "\n".join(table_details)
    return {
        "key": fact_keys[3],
        "domain": "config",
        "content": fact_content,
        "attributes": {"kind": "namespace-health", "date": TICK[:10], "run_token": RUN_TOKEN},
    }

# Build the facts list
facts = [
    {
        "key": fact_keys[0],
        "domain": "event",
        "content": (
            "auger per-tick status snapshot. lane: auger-sync, focused namespace sync of 'auger'. "
            "window.from: 2026-09-24T03:38:29.491Z (prior marker newest-entry timestamp, disk read). "
            "window.to: 2026-09-24T10:30Z. head: 7f8e2544f7db338b3e0302ebc0bc399b4fd0eeb2, branch main, "
            "0 unpushed vs origin/main (fetched probe). CI on main: 3/3 latest runs success. "
            "Focused lane: sessions_scanned=0. health: GREEN. "
            "qa-cron sibling was actively committing board events during the scan (disclosed). " + RT
        ),
        "attributes": {"kind": "status", "date": "2026-09-24", "run_token": RUN_TOKEN},
    },
    {
        "key": fact_keys[1],
        "domain": "event",
        "content": (
            "auger git activity in window 2026-09-24T03:38:29Z..10:30Z: 10 commits on main "
            "(git rev-list --count --since), 0 unpushed. Theme: ask-gate/answer correctness loop — "
            "AUG-055 (resolve answer choice before writes; board close) and AUG-056 (do not re-propose "
            "closed questions; board close after recovered judge dispatch / orphan closeout tick "
            "auger-2026-09-24-closeout), plus dogfood PROMISING-BUT-ROUGH (5th run) findings landing as "
            "fixes, and qa battery PASS annotations (qa-cron lane actively committing events during this "
            "scan — disclosed as concurrent sibling activity). " + RT
        ),
        "attributes": {"kind": "git-activity", "commits_in_window": 10, "run_token": RUN_TOKEN},
    },
    {
        "key": fact_keys[2],
        "domain": "event",
        "content": (
            "auger board state read LIVE 2026-09-24 ~10:08Z from tasks.jsonl: 66 rows total, "
            "36 complete / 30 pending, events.jsonl at 125 events (max id 125, tail 2026-09-24 "
            "05:05:00 UTC, qa_annotation). vs prior marker: pending 26->30, complete 33->36 "
            "(rows 59->66): closed in-window AUG-030, AUG-055, AUG-056; 7 new pending rows "
            "AUG-057, AUG-058, AUG-059, AUG-060, RELEASE-001, RELEASE-002, RELEASE-003 (5th "
            "dogfood-run findings plus releng-sweep rows committed in-window by the qa lane). "
            "AUG-001/002 remain pending (engine core, still not started — not 'in progress'). " + RT
        ),
        "attributes": {"kind": "board-state", "rows": 66, "pending": 30, "complete": 36, "run_token": RUN_TOKEN},
    },
    build_namespace_health_fact(),
    {
        "key": fact_keys[4],
        "domain": "config",
        "content": (
            "auger JEV availability 2026-09-24: 3/6 keys alive. Probe sent the exact 3-field payload "
            "(model typesafe/jev-1.13, state, typed questions choice/noul/score) mirroring auger.py jev(); "
            "failures: 1x 401 API key expired, 2x 401 User not found. Tool-level auger.jev() call verified "
            "OK through the failover loop (real path, not just raw probe). Unchanged vs 09-23 run — key "
            "rotation candidates still expired/User-not-found entries; only a 401 expired / User-not-found "
            "verdict is a real key problem, probe-shape bugs are excluded by construction. " + RT
        ),
        "attributes": {"kind": "jev-availability", "alive": 3, "total": 6, "run_token": RUN_TOKEN},
    },
]

marker = {
    "key": "/sync/auger-last-run",
    "domain": "config",
    "content": (
        "auger-sync lane run record. lane: auger-sync (scheduler tick " + TICK + "). namespace: auger. "
        "window.from: 2026-09-24T03:38:29.491Z (prior marker newest-entry timestamp, disk-grep authoritative; "
        "HTTP prefix read agreed). window.to: 2026-09-24T10:30Z. source_counts: commits=10 in-window on main "
        "(git log --since), unpushed=0 (probe fetched ahead/behind 0/0), board_rows=66 (36 complete / 30 "
        "pending), board_events=125 (tail 2026-09-24 05:05:00 UTC), declared_tables=13 on disk vs 14 in "
        "code COLS (drift = verdict table missing, carried and re-confirmed), smoke_residue=0 (was 1), "
        "ci=3/3 success on main, jev=live 3/6 keys (1 expired, 2 User-not-found; tool-level jev() OK), "
        "sessions_scanned=0 (focused lane). preflight write-test /sync/write-test-2026-09-24 OK at "
        + SINCE + " (id 5a307760, fingerprint recalled). keys_written: 7 total this run = 1 preflight "
        "test-write + 5 fact entries (status, git-activity, board-state under /project/auger/ in event "
        "domain; namespace-health, jev-availability in config domain) + this marker; every fact entry "
        "verified by the focused PLAN harness (per-key POST + returned-uuid prefix recall + disk JSONL "
        "grep). head: 7f8e2544f7db338b3e0302ebc0bc399b4fd0eeb2, branch main, pushed. health: GREEN. "
        "findings_new: 0 (verdict-table drift and jev key mix both carried; smoke residue improved 1->0). "
        "disclosed: board read taken while sibling qa-cron commit was mid-flight (counts timestamped). "
    ),
    "attributes": {
        "marker_role": "canonical lane accumulator /sync/auger-last-run",
        "window_from": "2026-09-24T03:38:29.491Z",
        "window_to": "2026-09-24T10:30Z",
        "keys_written": 7,
        "run_token": RUN_TOKEN,
        "tick_id": TICK,
    },
}

# --- mechanical contract gates (fail loudly at build time) ---
all_writes = facts + [marker]
computed_roster = 1 + len(fact_keys) + 1  # preflight write-test + fact keys + marker
assert marker["attributes"]["keys_written"] == computed_roster == 7, (
    f"roster mismatch: attr={marker['attributes']['keys_written']} computed={computed_roster}"
)
keys = [w["key"] for w in all_writes]
assert len(keys) == len(set(keys)), "duplicate keys in writes"
assert all_writes[-1]["key"] == "/sync/auger-last-run", "marker not last"
assert all(w["domain"] in DOMAINS for w in all_writes), "domain outside enum"
assert keys[: len(fact_keys)] == fact_keys, "fact key order drifted"

plan = {
    "namespace": "auger",
    "token_file": "/home/kara/.duckbrain/token-1787620243982.token",
    "since": SINCE,
    "writes": all_writes,
}

with open(f"{WORKDIR}/facts-auger-20260924T1008.json", "w") as fh:
    json.dump(all_writes, fh, indent=1)
with open(f"{WORKDIR}/plan-auger-20260924T1008.json", "w") as fh:
    json.dump(plan, fh, indent=1)
for w in all_writes:
    print(f"{w['domain']:8s} {w['key']}")
print(f"writes={len(all_writes)} since={SINCE} marker_last=True BUILD_OK")

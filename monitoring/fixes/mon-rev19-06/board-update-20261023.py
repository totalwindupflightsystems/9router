#!/usr/bin/env python3
"""Tick 2026-10-23 08:44Z board update — LINE-WISE rewrite of only the touched rows.

Touches:
  527 MON-REV19-06                       -> done      (fix landed + proven live)
  609 MON-DISK-20261023                  -> done      (alert resolved, live-verified)
  615 MON-MONITORING-FA5F538B-20261023   -> pending   (re-triage note appended, alert firing)
Appends:
  MON-GAP-037  (rule threshold / backup-step pattern — owner decision)
  MON-MONITORING-TICKNOTE-20261023-0844 (closed record row)
"""

import json
import sys

BOARD = "/home/kara/monitoring/.coding-hermes/board/tasks.jsonl"
NOW = "2026-10-23T09:0xZ"

REV19_RES = (
    "FIXED + PROVEN LIVE 2026-10-23 (monitoring-foreman-2026-10-23-08-44-31). "
    'Premise re-verified first: live Loki answered HTTP 400 "log queries are not supported as an '
    'instant query type" to the old /loki/api/v1/query probe, and stack/alloy/config.alloy pushes '
    'job = "fleet" (grep -oE \'job *= *"[a-z]+"\' -> 1 match), so the old URL\'s job="docker" was a '
    "second, independent reason the PASS branch was unreachable. "
    "CHANGE (commit ec6cef4, origin/main, parity 0): section 4 of scripts/verify.sh now issues a "
    'GET /loki/api/v1/query_range over the last hour with {job="fleet"} (LOKI_SELECTOR overrides the '
    "selector for negative tests), sums the returned log lines, prints PASS above 0 and FAIL at 0 lines "
    "instead of an info line. The same commit carries the live host's QA-MONITORING-006 never_started "
    "verdict distinction, which existed only on fleet-monitor and would otherwise have been regressed by "
    "deploying the repo file. "
    "DEPLOYED: /root/fleet-monitoring/scripts/verify.sh md5 b88acc77ce971dcb3726803b397acd98 "
    "(== repo file; backup .bak-20261023-rev19-06 6149 bytes kept beside it). "
    'ACCEPTANCE PROVEN ON THE LIVE HOST: positive path -> "PASS loki query_range returned 1 line(s) for '
    '{job=\\"fleet\\"} in the last 1h", full run VERIFY: PASS exit 0 (10 containers, 19 rules, 6 dashboards, '
    "delivery path received_total 69 -> 70); negative path -> LOKI_SELECTOR='{job=\"nosuchjob\"}' produces "
    '"FAIL loki query_range returned 0 lines ..." and exit 1. '
    "Reviewable copy: stack-copy/verify.sh in this workdir."
)

DISK_RES = (
    "RESOLVED + LIVE-VERIFIED 2026-10-23 (monitoring-foreman-2026-10-23-08-44-31). The alert is no longer "
    'firing: Prometheus ALERTS{alertstate="firing"} on fleet-monitor returns only OOMKillsLowPressure '
    '(bunker-mvp); querying ALERTS{alertname="DiskWillFillIn24h",host="karahermes-mde-7840hs"} returns an '
    "EMPTY vector, and the rule's own arms re-evaluated live are: free fraction 18.93% (<25% arm TRUE) "
    "while predict_linear(node_filesystem_avail_bytes[6h],86400) = +928,043,476,270 B (POSITIVE, so the "
    "<0 arm is FALSE). Disk headroom grew from 245G (01:06Z) to 347G free / 81% used of 1.8T: "
    "du -x -h -d2 ~/.hermes shows state-backups down to 13G (was 140G across 12-13 verified snapshots) "
    "because the relocation to /mnt/passport/hermes-backups/kara-db-backups-20260926/state-backups/ "
    "completed - that directory now holds the Oct-3 .. Oct-22 sets, and root keeps only the newest "
    "snapshot (state_20261023-000033.db.zst, 12.9G, written 02:09Z by the 00:00 backup). "
    "No destructive action taken by this tick; the 45G unlink and the passport relocation were done and "
    "witnessed by the 06:30Z tick. "
    "RESIDUAL (filed as MON-GAP-037, not silenced here): while free space stays under 25% of a 1966.7GB "
    "volume the rule re-arms every time a 6h window overlaps a 12.9GB snapshot write - a step, not a leak. "
    "Widening the rule to hide it is explicitly not this lane's call."
)

OOM_NOTE = (
    "\n\n=== LANE RE-TRIAGE 2026-10-23 08:57Z (tick monitoring-foreman-2026-10-23-08-44-31) ===\n"
    "The alert re-fired at 08:49:38Z, so this is a live finding again and the row stays PENDING. Live probes "
    'on fleet-monitor:9090 at 08:58:56Z: delta(node_vmstat_oom_kill{host="bunker-mvp"}[15m]) = 1.0344827586 '
    "(the kill is real, not a stale alert); node_memory_MemAvailable/MemTotal = 0.591 (9.0 GiB of 15.2 GiB "
    "free) -> host-level exhaustion CANNOT be the cause because the rule requires >= 0.15 and the host sits "
    "at 0.59, so the kill is cgroup/memcg scoped, the benign class this rule documents. "
    "Alertmanager /api/v2/alerts shows this as the ONLY firing alert fleet-wide. "
    "Note for the next tick: the availability ratio moved 0.834 -> 0.591 between 02:42Z and 08:58Z, so "
    "bunker-mvp is carrying real workload; that is not pressure yet but it is the number to watch. "
    "STILL UNVERIFIED (unchanged): the specific memcg name - this lane has no host shell on bunker-mvp, so "
    "dmesg -T | grep oom-kill cannot be read. That attribution gap is MON-GAP-034."
)

GAP_037 = {
    "id": "MON-GAP-037",
    "lane": "monitoring",
    "type": "finding",
    "priority": "P2",
    "status": "pending",
    "created_at": "2026-10-23T09:00:00Z",
    "created": "2026-10-23T09:00:00Z",
    "title": (
        "P2 - DiskWillFillIn24h on the 1.8T lane box is step-driven, not leak-driven: the rule "
        "re-arms every time a 6h predict_linear window overlaps the 12.9GB state-db snapshot write, "
        "because free fraction can never reach the rule's 25% arm (needs 491GB free) - owner "
        "decision on rule shape vs capacity"
    ),
    "reasoning": (
        "HOW FOUND: MON-DISK-20261023 fired 2026-10-23T00:57Z and cleared by 08:57Z with no consumption of "
        "its own: avail went 245G -> 347G free in the same period (backup snapshot relocation to "
        "/mnt/passport), while predict_linear(avail[6h],86400) swung -195GB (19:15Z 10-22) -> -71GB "
        "(00:27Z) -> -43.8GB (06:30Z) -> +928GB (08:58Z). Each swing tracks the 6h window entering/leaving "
        "one ~12.5GB snapshot write plus the nightly retention sweep, not unexplained growth: "
        "deriv(avail[1h]) was +15MB/s at 06:30Z and -1.0MB/s at 08:58Z. "
        "THE STRUCTURAL PROBLEM: the rule is (predict_linear(...[6h],86400) < 0) AND (avail/size < 0.25). "
        "On a 1966.7GB volume the second arm needs 491.7GB free, and the box currently runs at 18.9% free "
        "(347G). So the alert can never be cleared by capacity hygiene alone - every backup step re-arms "
        "it, and each firing mints a board row that triage has to re-verify against a flat disk. "
        "WHAT (owner decision, do NOT self-approve): pick one - (a) make the availability arm "
        "capacity-aware (e.g. trigger on absolute free < 60GB instead of a fixed 25% fraction), "
        "(b) lengthen the prediction window so a single snapshot write cannot dominate the 6h slope, or "
        "(c) relocate/retention-cap the snapshot tier so root never holds one (backup-tiered.sh already "
        "documents that the tier must not live on root; the 00:00 run wrote state_20261023-000033.db.zst "
        "to root again because STATE_BACKUP_DIR resolved to root once the dir was recreated). "
        "(c) is code+policy, (a)/(b) are rule edits on fleet-monitor - both are outside a lane tick's "
        "unilateral authority per the no-silencing rule."
    ),
    "acceptance_criteria": (
        "A rule revision is chosen and deployed on fleet-monitor and re-read from the live API: "
        "`ssh fleet-monitor \"sed -n '1,60p' /root/fleet-monitoring/alerts/rules/capacity.yml\"` shows the "
        "DiskWillFillIn24h expr with the chosen shape, `/api/v1/rules` reports health=ok for the group, and "
        "a 7-day review of board rows shows no DiskWillFillIn24h refire on karahermes-mde-7840hs that was "
        "caused only by a snapshot write. If (c) is chosen instead: two consecutive nightly backups land "
        "outside /home/kara/.hermes/state-backups and `ls /home/kara/.hermes/state-backups` is empty."
    ),
}

TICKNOTE = {
    "id": "MON-MONITORING-TICKNOTE-20261023-0844",
    "lane": "monitoring",
    "type": "tick-note",
    "priority": "P3",
    "status": "done",
    "created_at": "2026-10-23T09:05:00Z",
    "created": "2026-10-23T09:05:00Z",
    "title": (
        "Tick 2026-10-23 08:44Z: drain appended=0 skipped=866 (0 UNWRITABLE, live_ok=True); "
        "MON-DISK-20261023 closed resolved-verified (347G free, predict +928GB); MON-REV19-06 "
        "landed ec6cef4 + deployed + proven both paths; OOMKillsLowPressure re-fired 08:49Z, "
        "left pending with fresh probes"
    ),
    "reasoning": (
        "DRAIN: MON_REMOTE=fleet-monitor drain-board-rows.sh -> appended=0 skipped=866 refire=0, "
        "plan refire=0 olddate-suppressed=93 stale-suppressed=4 unverified-suppressed=0 live_ok=True, "
        "zero UNWRITABLE rows (no rule labels a lane without a board). All 866 skips are daily replay "
        "fan-out for ids already on the board. Remote spool deliberately not cleared (manual step). "
        "TRIAGE: one live alert at open (DiskWillFillIn24h karahermes) which had already resolved by "
        "triage -> closed with re-evaluated PromQL, not alert text. One alert re-fired mid-tick "
        "(OOMKillsLowPressure bunker-mvp 08:49:38Z) -> triaged benign-memcg, row kept pending. "
        "WORK: MON-REV19-06 (verify.sh Loki gate) fixed in a worktree, committed ec6cef4, fast-forwarded "
        "to origin/main (ls-remote == HEAD, rev-list origin/main..HEAD = 0), deployed to "
        "/root/fleet-monitoring with a timestamped backup, and proven on the live host in both "
        "directions (PASS with data, FAIL+exit 1 with a selector that matches nothing). "
        "CI: totalwindupflightsystems/fleet-monitoring has ZERO workflow runs (gh run list -> []) - "
        "clean, not unverifiable; the repo has no CI at all, which is RELEASE-MON-011."
    ),
    "acceptance_criteria": "Record row - no action. Live state at close: df / 347G free (81% used); "
    "origin/main ec6cef4; verify.sh on host md5 b88acc77ce971dcb3726803b397acd98.",
}

UPDATES = {
    527: (
        "MON-REV19-06",
        "pending",
        {
            "status": "done",
            "updated_at": "2026-10-23T09:00:00Z",
            "completed_at": "2026-10-23T09:00:00Z",
            "worker_status": "complete",
            "worktree": "/home/kara/worktrees/fleet-monitoring-MON-REV19-06",
            "branch": "wt/MON-REV19-06",
            "commit_hash": "ec6cef4",
            "worker_summary": (
                'loki check rewritten to query_range + job="fleet"; deployed to '
                "/root/fleet-monitoring and proven both paths on the live host; commit ec6cef4 "
                "pushed to origin/main (parity 0)."
            ),
            "resolution": REV19_RES,
            "witness": (
                "live:fleet-monitor:verify.sh VERIFY: PASS exit 0 (loki query_range 1 line) + "
                "LOKI_SELECTOR negative -> FAIL exit 1; git:ec6cef4@origin/main"
            ),
        },
    ),
    609: (
        "MON-DISK-20261023",
        "open",
        {
            "status": "done",
            "updated_at": "2026-10-23T09:00:00Z",
            "completed_at": "2026-10-23T09:00:00Z",
            "worker_status": "complete",
            "worker_summary": (
                "resolved: alert not firing, avail 347G/81% used, predict_linear +928GB, "
                "state-backups 13G after the passport relocation; threshold/step-pattern "
                "residual filed as MON-GAP-037."
            ),
            "resolution": DISK_RES,
            "witness": (
                'live:fleet-monitor:9090 ALERTS{alertname="DiskWillFillIn24h"} empty + '
                "predict_linear positive; live:df -h / on karahermes-mde-7840hs"
            ),
        },
    ),
    615: (
        "MON-MONITORING-FA5F538B-20261023",
        "pending",
        {
            "updated_at": "2026-10-23T09:00:00Z",
            "worker_status": "triaged-benign-open-until-resolved",
            "reasoning_append": OOM_NOTE,
        },
    ),
}


def main():
    with open(BOARD, encoding="utf-8") as fh:
        lines = fh.readlines()

    parsed = [json.loads(line) for line in lines]
    out = []

    for idx, (line, row) in enumerate(zip(lines, parsed)):
        if idx in UPDATES:
            want_id, want_status, changes = UPDATES[idx]
            assert row.get("id") == want_id, (
                f"line {idx + 1}: expected {want_id}, got {row.get('id')}"
            )
            assert row.get("status") == want_status, (
                f"line {idx + 1}: expected status {want_status}, got {row.get('status')}"
            )
            new = dict(row)
            append = changes.pop("reasoning_append", None)
            new.update(changes)
            if append:
                new["reasoning"] = (new.get("reasoning") or "") + append
            out.append(json.dumps(new, ensure_ascii=False) + "\n")
            print(
                f"updated line {idx + 1}: {want_id} ({want_status} -> {new.get('status')})"
            )
        else:
            out.append(line)

    ids = {r.get("id") for r in parsed}
    for extra in (GAP_037, TICKNOTE):
        assert extra["id"] not in ids, (
            f"{extra['id']} already exists - refusing to duplicate"
        )
        out.append(json.dumps(extra, ensure_ascii=False) + "\n")
        print("appended", extra["id"])

    with open(BOARD, "w", encoding="utf-8") as fh:
        fh.writelines(out)

    # verify: every line parses, untouched lines are byte-identical, counts as expected
    with open(BOARD, encoding="utf-8") as fh:
        new_lines = fh.readlines()
    assert len(new_lines) == len(lines) + 2, (len(lines), len(new_lines))
    for line in new_lines:
        json.loads(line)
    changed = [i + 1 for i, (a, b) in enumerate(zip(lines, new_lines)) if a != b]
    print("byte-changed original lines:", changed)
    assert changed == [528, 610, 616], changed
    print("OK rows", len(new_lines))


if __name__ == "__main__":
    sys.exit(main())

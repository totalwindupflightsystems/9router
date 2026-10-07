#!/usr/bin/env python3
"""disk-guard.py — stop the host from ever crashing on a full root again.

The failure this exists for (2026-09-27/28): builds + a log flood filled the 1.8T
root to 0 bytes, which crash-looped the gateway (`OSError: [Errno 28]`) and stalled
the whole fleet. Nothing watched free space, so the first signal was the outage.

Design:
  * reads free space from statvfs (cheap, cannot hang like `df` on a wedged FUSE mount)
  * SOFT threshold -> reclaim from REBUILDABLE pools only (docker caches, aged scratch)
  * HARD threshold -> aggressive reclaim AND stop the producer (pause the scheduler,
    because under disk pressure the spawner is what makes it worse)
  * every action has an age floor; never touches DBs, repos, volumes, or /mnt data
  * rate-limited so a flapping threshold cannot thrash the box
  * --report prints undelivered events (watchdog pattern: empty output = nothing happened)

Exit codes: 0 normally; 2 when it had to shed at HARD (so a wrapper can escalate).
"""
from __future__ import annotations

import argparse
import glob
import os
import shutil
import sqlite3
import subprocess
import sys
import time
import urllib.request
from pathlib import Path

HOME = Path("/home/kara")
LOG = HOME / ".hermes" / "logs" / "disk-guard.log"
PENDING = HOME / ".hermes" / "state" / "disk-guard-pending.jsonl"
RATE = HOME / ".hermes" / "state" / "disk-guard-ratelimit.json"

SOFT_GB = float(os.environ.get("DISK_GUARD_SOFT_GB", 150.0))  # reclaim caches/scratch below this
HARD_GB = float(os.environ.get("DISK_GUARD_HARD_GB", 60.0))   # shed hard + stop the spawner below this
COOLDOWN_S = int(os.environ.get("DISK_GUARD_COOLDOWN_S", 600))  # min seconds between shedding passes

# Aged scratch in /tmp that is provably rebuildable. Age floors keep in-flight work.
SCRATCH_GLOBS = [
    ("/tmp/pytest-of-*", 6 * 3600),
    ("/tmp/go-build*", 2 * 3600),
    ("/tmp/*-scratch", 6 * 3600),
    ("/tmp/*-target", 6 * 3600),
    ("/tmp/*-review", 12 * 3600),
    ("/tmp/kara-backup-stage/*", 24 * 3600),
    # 2026-10-07: fleet pytest runs land here via the scratch-relocation drop-ins,
    # not /tmp — measured 95GiB of >24h-old runs (81 dirs) while free space was
    # still above SOFT, i.e. invisible to the guard's soft pool until too late.
    ("/var/tmp/hermes-scratch/pytest-of-*", 24 * 3600),
]


def log(msg: str) -> None:
    LOG.parent.mkdir(parents=True, exist_ok=True)
    line = f"{time.strftime('%Y-%m-%d %H:%M:%S')} {msg}"
    print(line)
    with LOG.open("a") as f:
        f.write(line + "\n")


def note_event(msg: str) -> None:
    """Record an event for the report job (delivered to the operator)."""
    PENDING.parent.mkdir(parents=True, exist_ok=True)
    import json
    with PENDING.open("a") as f:
        f.write(json.dumps({"ts": time.strftime("%Y-%m-%d %H:%M:%S"), "msg": msg}) + "\n")


def free_gb(path: str = "/") -> float:
    st = os.statvfs(path)
    return st.f_bavail * st.f_frsize / 2**30


def rate_limited() -> bool:
    import json
    try:
        last = json.loads(RATE.read_text()).get("last", 0)
    except Exception:
        last = 0
    return (time.time() - last) < COOLDOWN_S


def mark_rate() -> None:
    import json
    RATE.parent.mkdir(parents=True, exist_ok=True)
    RATE.write_text(json.dumps({"last": time.time()}))


def run(cmd: list[str], timeout: int = 600) -> str:
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
        return (p.stdout + p.stderr).strip()[:400]
    except Exception as e:
        return f"FAILED: {e}"


def docker_ok() -> bool:
    return shutil.which("docker") is not None and subprocess.run(
        ["docker", "info"], capture_output=True, timeout=30).returncode == 0


def reclaim_soft() -> list[str]:
    """Rebuildable pools only. Safe while builds run."""
    acts = []
    if docker_ok():
        out = run(["docker", "builder", "prune", "-af"], timeout=900)
        if "Total" in out or "reclaimed" in out:
            acts.append(f"docker build cache pruned: {out.splitlines()[-1][:120]}")
        out = run(["docker", "image", "prune", "-f"], timeout=600)
        if "reclaimed" in out:
            acts.append(f"dangling images pruned: {out.splitlines()[-1][:120]}")
    # aged scratch
    for pattern, age in SCRATCH_GLOBS:
        now = time.time()
        for p in glob.glob(pattern):
            try:
                if os.path.islink(p):
                    continue
                if (now - os.path.getmtime(p)) < age:
                    continue
                # never delete a directory holding a live sqlite file
                if glob.glob(os.path.join(p, "**", "*.db"), recursive=True):
                    continue
                shutil.rmtree(p, ignore_errors=True)
                acts.append(f"removed aged scratch {p} (>{age // 3600}h idle)")
            except Exception as e:
                acts.append(f"scratch skip {p}: {e}")
    return acts


def reclaim_hard() -> list[str]:
    """Soft reclaim plus everything else that is provably regenerable."""
    acts = reclaim_soft()
    # large container logs: cap, never delete the container
    for logf in glob.glob("/var/lib/docker/containers/*/*-json.log"):
        try:
            size = os.path.getsize(logf)
            if size > 1024 ** 3:
                subprocess.run(["sudo", "-n", "truncate", "-s", "0", logf],
                               capture_output=True, timeout=60)
                acts.append(f"truncated container log {logf} ({size / 2**30:.1f} GiB)")
        except Exception:
            continue
    if docker_ok():
        out = run(["docker", "image", "prune", "-af"], timeout=900)
        if "reclaimed" in out:
            acts.append(f"all unused images pruned: {out.splitlines()[-1][:120]}")
        out = run(["docker", "container", "prune", "-f"], timeout=300)
        if "reclaimed" in out:
            acts.append(f"stopped containers pruned: {out.splitlines()[-1][:120]}")
    return acts


def pause_scheduler(reason: str) -> str:
    """Stop the producer: under disk pressure spawning more work makes it worse."""
    auth = HOME / ".hermes" / "scheduler-auth.env"
    token = ""
    try:
        for line in auth.read_text().splitlines():
            if "=" in line and not line.strip().startswith("#"):
                k, v = line.split("=", 1)
                if k.strip() == "SCHEDULER_OPERATOR_TOKEN":
                    token = v.strip().strip('"').strip("'")
    except Exception:
        pass
    try:
        con = sqlite3.connect(f"file:{HOME}/.hermes/coding-hermes/scheduler.db?mode=ro", uri=True)
        rows = con.execute("SELECT name FROM projects WHERE enabled=1").fetchall()
        con.close()
    except Exception as e:
        return f"could not list lanes to pause: {e}"
    paused = 0
    for (name,) in rows:
        try:
            req = urllib.request.Request(
                f"http://127.0.0.1:9090/api/v1/projects/{name}/pause", method="POST",
                headers={"X-Operator-Token": token, "Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=15)
            paused += 1
        except Exception:
            continue
    return f"scheduler shedding: paused {paused}/{len(rows)} enabled lanes ({reason})"


def report() -> int:
    if not PENDING.exists() or PENDING.stat().st_size == 0:
        return 0
    lines = PENDING.read_text().splitlines()
    PENDING.write_text("")
    print("disk-guard events since last report:")
    for line in lines[-15:]:
        print(f"  {line}")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true", help="print undelivered events and exit")
    ap.add_argument("--dry-run", action="store_true", help="show thresholds/space, change nothing")
    args = ap.parse_args()

    if args.report:
        return report()

    free = free_gb("/")
    if args.dry_run:
        print(f"root free: {free:.1f} GiB  (soft {SOFT_GB}, hard {HARD_GB})  "
              f"rate_limited={rate_limited()}  would_shed={'HARD' if free < HARD_GB else ('SOFT' if free < SOFT_GB else 'no')}")
        return 0

    if free >= SOFT_GB:
        return 0
    if rate_limited():
        log(f"free={free:.1f}G below soft {SOFT_GB}G but in cooldown — no action")
        return 0

    mark_rate()
    level = "HARD" if free < HARD_GB else "SOFT"
    log(f"SHED level={level} free={free:.1f}G")
    acts = reclaim_hard() if level == "HARD" else reclaim_soft()
    for a in acts:
        log(f"  {a}")
    if level == "HARD":
        msg = pause_scheduler(f"root free {free:.1f}G < {HARD_GB}G")
        log(f"  {msg}")
        note_event(f"{level}: root free was {free:.1f}G — reclaimed {len(acts)} pool(s); {msg}")
    else:
        note_event(f"{level}: root free was {free:.1f}G — reclaimed {len(acts)} pool(s)")
    after = free_gb("/")
    log(f"after: {after:.1f}G free")
    note_event(f"after reclaim: {after:.1f}G free")
    return 2 if level == "HARD" else 0


if __name__ == "__main__":
    sys.exit(main())

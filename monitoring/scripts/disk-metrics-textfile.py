#!/usr/bin/env python3
"""disk-metrics-textfile.py — publish host disk facts for the node_exporter textfile
collector so fleet-monitor's Prometheus (and Grafana) can chart them.

Why: the containerised unix exporter only sees / and /run (its mount namespace has no
USB mounts), and nothing measured the 2026-09-28 scratch relocation. These series make
"did moving build scratch off the NVMe work?" a graphable question: root vs external-drive write
rates come from the standard node_disk_* metrics; these add free space on the external
drives plus /tmp size and entry count.

Two cadences, because the full walk is expensive (74s / 718MB the naive way):
  * every run  : mount free/used (statvfs) + /tmp entry count (scandir) — milliseconds
  * every 30m  : /tmp size + scratch sizes (budgeted, memory-bounded os.walk), cached
                 in a state file and re-emitted until refreshed
`hermes_disk_metrics_full_age_seconds` says how stale the cached sizes are, so a stale
number is visibly stale instead of silently wrong.
"""
import json
import os
import re
import subprocess
import sys
import time

OUT = "/var/lib/node_exporter/textfile/disk_metrics.prom"
STATE = "/home/kara/.hermes/cache/disk-metrics-state.json"
MOUNTS = ["/", "/mnt/bulk", "/mnt/usb512", "/mnt/passport"]
SCRATCH = ["/mnt/bulk/scratch", "/mnt/bulk/cargo-target",
           "/var/tmp/hermes-cargo-target", "/mnt/bulk/go-mod"]
TMP = "/tmp"
# Root-filesystem consumers, so a fill can be attributed to a directory instead of
# guessed at. Per-dir budget + honest partial flag: `/tmp` (193 GB) and `.lmstudio`
# (69 GB) cannot both be walked inside one timer tick on a loaded box.
DIRS = [
    "/tmp",
    "/home/kara/.hermes",
    "/home/kara/.cache",
    "/home/kara/.lmstudio",
    "/home/kara/.local",
    "/var/log",
    "/var/lib/docker",
    "/var/tmp/hermes-scratch",
    "/home/kara/reports",
]
FULL_EVERY_S = 1800
TMP_BUDGET_S = 120
SCRATCH_BUDGET_S = 60
DIR_BUDGET_S = 30


def prom_label(value) -> str:
    """Escape one Prometheus text-format label value."""
    return str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def mount_metrics():
    """Publish filesystem capacity only for exact, currently mounted paths."""
    out = []
    for m in MOUNTS:
        escaped_mount = prom_label(m)
        try:
            result = subprocess.run(
                ["findmnt", "-rn", "-M", m, "-o", "TARGET,SOURCE,FSTYPE"],
                capture_output=True, text=True, timeout=3, check=False,
            )
            fields = result.stdout.strip().split()
            if result.returncode != 0 or len(fields) < 3 or fields[0] != m:
                out.append(f'hermes_fs_mounted{{mount="{escaped_mount}"}} 0')
                continue
            _, source, fstype = fields[:3]
            out.append(f'hermes_fs_mounted{{mount="{escaped_mount}"}} 1')
            out.append(
                f'hermes_fs_source_info{{mount="{escaped_mount}",'
                f'source="{prom_label(source)}",fstype="{prom_label(fstype)}"}} 1'
            )
            st = os.statvfs(m)
            out.append(f'hermes_fs_size_bytes{{mount="{escaped_mount}"}} {st.f_frsize * st.f_blocks}')
            out.append(f'hermes_fs_avail_bytes{{mount="{escaped_mount}"}} {st.f_frsize * st.f_bavail}')
            out.append(f'hermes_fs_used_bytes{{mount="{escaped_mount}"}} '
                       f'{st.f_frsize * (st.f_blocks - st.f_bfree)}')
        except (OSError, subprocess.SubprocessError):
            out.append(f'hermes_fs_mounted{{mount="{escaped_mount}"}} 0')
    return out


def block_device_metrics():
    """Publish stable device identity alongside the kernel's changing sdX name."""
    try:
        result = subprocess.run(
            ["lsblk", "--json", "--bytes", "--nodeps", "--output",
             "NAME,MODEL,SERIAL,TRAN,SIZE,TYPE"],
            capture_output=True, text=True, timeout=5, check=True,
        )
        devices = json.loads(result.stdout).get("blockdevices", [])
    except (OSError, subprocess.SubprocessError, ValueError, json.JSONDecodeError):
        return []
    out = []
    for d in devices:
        if d.get("type") != "disk" or not d.get("name"):
            continue
        labels = {
            "device": d["name"],
            "model": d.get("model") or "unknown",
            "serial": d.get("serial") or "unknown",
            "transport": d.get("tran") or "unknown",
        }
        encoded = ",".join(f'{key}="{prom_label(value)}"' for key, value in labels.items())
        out.append(f"hermes_block_device_info{{{encoded}}} 1")
        out.append(f"hermes_block_device_size_bytes{{{encoded}}} {int(d.get('size') or 0)}")
    return out


def tmp_entry_count():
    n = 0
    try:
        with os.scandir(TMP) as it:
            for _ in it:
                n += 1
    except OSError:
        return None
    return n


def walk_size(root, budget_s):
    """Memory-bounded, time-bounded disk usage of one tree."""
    total = 0
    partial = False
    deadline = time.monotonic() + budget_s
    for dirpath, dirnames, filenames in os.walk(root, onerror=lambda e: None,
                                                followlinks=False):
        if time.monotonic() > deadline:
            partial = True
            break
        for f in filenames:
            try:
                st = os.stat(os.path.join(dirpath, f), follow_symlinks=False)
                total += getattr(st, "st_blocks", 0) * 512 or st.st_size
            except OSError:
                pass
    return total, partial


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


# A textfile is all-or-nothing: the collector rejects the whole file if ANY line
# fails to parse, so one malformed value silently deletes every series (this bit us
# on 2026-09-29 — a bare Python bool rendered as `False` and blanked the scrape).
# Validate before writing, drop offenders, and publish the count so a bad line is
# visible in the metrics themselves instead of only in the collector's log.
_LINE_OK = re.compile(
    r'^[a-zA-Z_:][a-zA-Z0-9_:]*(\{[^{}]*\})? -?\d+(\.\d+)?([eE][+-]?\d+)?$')


def validate(lines):
    good, bad = [], []
    for ln in lines:
        (good if _LINE_OK.match(ln) else bad).append(ln)
    return good, bad


def main():
    now = time.time()
    st = load_state()
    full_age = now - st.get("full_ts", 0)
    if full_age >= FULL_EVERY_S or "tmp_size" not in st:
        tmp_size, tmp_partial = walk_size(TMP, TMP_BUDGET_S)
        scratch = {}
        for d in SCRATCH:
            scratch[d], _ = walk_size(d, SCRATCH_BUDGET_S)
        dirs = {}
        dirs_partial = {}
        for d in DIRS:
            dirs[d], dirs_partial[d] = walk_size(d, DIR_BUDGET_S)
        st = {"full_ts": now, "tmp_size": tmp_size, "tmp_partial": int(tmp_partial),
              "scratch": scratch, "dirs": dirs, "dirs_partial": dirs_partial}
        try:
            os.makedirs(os.path.dirname(STATE), exist_ok=True)
            with open(STATE, "w") as f:
                json.dump(st, f)
        except OSError:
            pass
        full_age = 0.0

    lines = mount_metrics()
    lines.extend(block_device_metrics())
    n = tmp_entry_count()
    if n is not None:
        lines.append(f"hermes_tmp_entries {n}")
    lines.append(f"hermes_tmp_size_bytes {st.get('tmp_size', 0)}")
    lines.append(f"hermes_tmp_size_partial {st.get('tmp_partial', 0)}")
    total = 0
    for d, v in (st.get("scratch") or {}).items():
        lines.append(f'hermes_scratch_size_bytes{{dir="{d}"}} {v}')
        total += v
    lines.append(f"hermes_scratch_size_bytes_total {total}")
    for d, v in (st.get("dirs") or {}).items():
        lines.append(f'hermes_dir_size_bytes{{dir="{d}"}} {int(v)}')
        # int() is load-bearing: walk_size returns a Python bool for `partial`, and a
        # bare bool renders as `False` — one such line makes the textfile collector
        # reject the WHOLE file, silently dropping every series from the scrape.
        lines.append(f'hermes_dir_size_partial{{dir="{d}"}} '
                     f'{int((st.get("dirs_partial") or {}).get(d, 0))}')
    lines.append(f"hermes_disk_metrics_full_age_seconds {int(full_age)}")
    good, bad = validate(lines)
    if bad:
        print(f"disk-metrics-textfile: dropped {len(bad)} malformed line(s): "
              + "; ".join(bad[:3]), file=sys.stderr)
    good.append(f"hermes_disk_metrics_invalid_lines {len(bad)}")
    lines = good

    tmp = OUT + ".tmp"
    try:
        with open(tmp, "w") as f:
            f.write("\n".join(lines) + "\n")
        os.replace(tmp, OUT)
    except OSError as e:
        print(f"disk-metrics-textfile: cannot write {OUT}: {e}")


if __name__ == "__main__":
    main()

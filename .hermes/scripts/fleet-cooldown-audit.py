#!/usr/bin/env python3
"""Fleet cooldown-vs-pending audit — catches projects parked at 12h+ cooldown
with real pending work. Runs via cron every 6h. Exits 0 with report; the cron
delivers stdout only when problems found (watchdog pattern).
"""
import json, os, re, subprocess, sys

# ── Self-bootstrap: re-exec with the durable board venv (has duckdb) ──
# Required BEFORE importing the policy module — its own bootstrap re-execs
# with sys.argv, which would run the policy's main() instead of this audit.
import importlib.util as _ilu
BOOTSTRAP_PY = os.path.expanduser('~/.hermes/venvs/board/bin/python3')
if _ilu.find_spec('duckdb') is None and os.path.exists(BOOTSTRAP_PY):
    os.execv(BOOTSTRAP_PY, [BOOTSTRAP_PY] + sys.argv)

try:
    import yaml
except ImportError:
    yaml = None

# Import the single loader path from the policy module (SCHED-GAP-1662).
def _policy_module():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        'pol', '/home/kara/.hermes/scripts/fleet-cooldown-policy.py')
    pol = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(pol)
    return pol

def board_pending(path):
    # Delegate to the policy governor's parsers (parquet → duckdb → md with
    # checkbox fallback). The old regex heuristic overcounted status-word rows
    # (reported 25 pending on dexdat-memory's all-complete board → false
    # SLOW-COOLDOWN alarms). Policy parsers read the LIVE stores.
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            'pol', '/home/kara/.hermes/scripts/fleet-cooldown-policy.py')
        pol = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(pol)
        # path is <workdir>/.coding-hermes/tasks.md or <workdir>/tasks.md
        workdir = path
        for suffix in ('/.coding-hermes/tasks.md', '/tasks.md'):
            if path.endswith(suffix):
                workdir = path[: -len(suffix)]
                break
        return pol.board_pending(workdir) or 0
    except Exception:
        return 0

def gitreins_pending(workdir):
    if yaml is None:
        return 0
    for sub in ['.gitreins/tasks.yaml', 'gitreins/tasks.yaml']:
        p = os.path.join(workdir, sub)
        if os.path.isfile(p):
            try:
                with open(p) as f:
                    tasks = yaml.safe_load(f) or {}
                return len([t for t in tasks.get('tasks', []) if t.get('status') == 'pending'])
            except Exception:
                return 0
    return 0

def fleet_toml_pins(project_name):
    """Return cooldown_s from fleet.toml if the project has an entry, else None.

    Reads ~/.hermes/fleet.toml via the policy module's single loader path —
    NOT the stale scheduler-repo copy (SCHED-GAP-1662: the audit must report
    on the same file schedulerd loads).
    """
    path = _policy_module().fleet_toml_path()
    try:
        with open(path) as f:
            c = f.read()
        # find [[projects]] block for this name
        blocks = re.findall(r'\[\[projects\]\](.*?)(?=\n\[\[projects\]\]|\Z)', c, re.S)
        for b in blocks:
            if re.search(r'^\s*name\s*=\s*"' + re.escape(project_name) + r'"\s*$', b, re.M):
                m = re.search(r'^\s*cooldown_s\s*=\s*(\d+)', b, re.M)
                return int(m.group(1)) if m else None
    except Exception:
        pass
    return None

def main():
    try:
        r = subprocess.run(['curl', '-s', '-m', '10', 'http://127.0.0.1:9090/api/v1/projects?limit=500'],
                           capture_output=True, timeout=15)
        projects = json.loads(r.stdout)['projects']
    except Exception as e:
        print(f"AUDIT FAIL: cannot reach scheduler API: {e}")
        return 1

    problems = []

    # --- Check 1: duplicate workdirs (case-insensitive project names) ---
    workdir_map = {}
    for p in projects:
        if not p.get('enabled'):
            continue
        wd = p.get('workdir', '')
        if not wd:
            continue
        key = wd.rstrip('/')
        workdir_map.setdefault(key, []).append(p['name'])
    for wd, names in workdir_map.items():
        if len(names) > 1:
            problems.append(('DUPLICATE-WORKDIR', wd, names,
                             'delete ghost project entry (case-sensitivity bug: HEADING vs heading)'))

    # --- Check 2: decay_rate=0 with pending work (permanent starvation) ---
    for p in projects:
        if not p.get('enabled'):
            continue
        if p.get('decay_rate', 1.0) != 0:
            continue
        name = p['name']
        workdir = p.get('workdir', '')
        if not workdir or not os.path.isdir(workdir):
            continue
        board = os.path.join(workdir, '.coding-hermes', 'tasks.md')
        if not os.path.isfile(board):
            board = os.path.join(workdir, 'tasks.md')
        pending = board_pending(board) if os.path.isfile(board) else 0
        pending += gitreins_pending(workdir)
        if pending > 0:
            problems.append(('DECAY-ZERO-STARVATION', name, pending,
                             'decay_rate=0 makes urgency flat — never picked. Set DecayRate=1.0'))

    # --- Check 3: slow cooldown with pending work ---
    for p in projects:
        if not p.get('enabled'):
            continue
        cd = p.get('cooldown_s', 0)
        if cd < 43200:
            continue  # only check slow-parked projects
        name = p['name']
        workdir = p.get('workdir', '')
        if not workdir or not os.path.isdir(workdir):
            continue
        board = os.path.join(workdir, '.coding-hermes', 'tasks.md')
        if not os.path.isfile(board):
            board = os.path.join(workdir, 'tasks.md')
        pending = board_pending(board) if os.path.isfile(board) else 0
        pending += gitreins_pending(workdir)
        pinned = fleet_toml_pins(name)
        if pending > 0:
            if pinned is not None and pinned >= 43200:
                continue  # admin intent IS slow — not a problem
            problems.append(('SLOW-COOLDOWN', name, pending,
                             f"cooldown={cd/3600:.0f}h with pending work"))

    if not problems:
        return 0  # silent — watchdog pattern

    print(f"⚠️ FLEET AUDIT — {len(problems)} problem(s):")
    for kind, name, detail, hint in problems:
        print(f"  [{kind}] {name}: {detail} — {hint}")
    print("Fix via scheduler API PUT, or add fleet.toml entry if admin intent differs.")
    return 0

if __name__ == '__main__':
    sys.exit(main())

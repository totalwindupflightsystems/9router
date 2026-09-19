#!/usr/bin/env python3
"""Fleet watchdog — prints ONLY when something is wrong (empty output = silent).

Runs as a no_agent cron: stdout is delivered verbatim, so silence means healthy.
Checks, in the order they have bitten us:
  1. STALLED     — ticks are queued but nothing is running while the load gate is
                   open (load < threshold): work waiting on no constraint.
  2. CAP BREACH  — a namespace has more RUNNING ticks than its max_concurrent
                   (the SCHED-GAP-142/144 class: satellites starving foremen).
  3. STALE BUILD — the binary on disk is newer than the running daemon, i.e. a fix
                   is committed and deployed-pending (tonight's 23:51-vs-23:59 bug).
  4. PAUSED      — the fleet is paused: if a deploy owns it that is expected, but an
                   orphaned pause is how a fleet goes silent for a day.
Plus a load-pressure note when load stays above the gate with work waiting.
"""
import json, os, sqlite3, subprocess, urllib.request
from datetime import datetime, timezone

DB = '/home/kara/.hermes/coding-hermes/scheduler.db'
API = 'http://127.0.0.1:9090'
BIN = '/home/kara/coding-hermes-scheduler/coding-herms-scheduler/bin/schedulerd'
LOG = '/home/kara/.hermes/coding-hermes/scheduler.log'
LOAD_GATE = 12.0
alerts = []


def api_key():
    try:
        for line in open(os.path.expanduser('~/.hermes/.env')):
            if line.startswith('API_SERVER_KEY='):
                return line.split('=', 1)[1].strip()
    except Exception:
        pass
    return ''


def get(path):
    try:
        req = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + api_key()})
        with urllib.request.urlopen(req, timeout=10) as r:
            return json.load(r)
    except Exception:
        return None


def q(sql, args=()):
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    try:
        return con.execute(sql, args).fetchall()
    finally:
        con.close()


def main():
    load1 = float(open('/proc/loadavg').read().split()[0])
    st = get('/api/v1/status') or {}
    paused = st.get('paused')
    running = q("SELECT COUNT(*) FROM ticks WHERE status='running'")[0][0]
    queued = q("SELECT COUNT(*) FROM ticks WHERE status='queued'")[0][0]

    # 1. stall: waiting work, no constraint
    if queued > 0 and running == 0 and load1 < LOAD_GATE:
        alerts.append(f"STALLED: {queued} tick(s) queued and 0 running while load {load1:.1f} < gate {LOAD_GATE} — nothing is starting work")

    # 2. namespace cap breach (running over cap)
    for ns, cap, run in q("""
        SELECT COALESCE(p.namespace_id,'(none)'), n.max_concurrent,
               SUM(CASE WHEN t.status='running' THEN 1 ELSE 0 END)
        FROM ticks t LEFT JOIN projects p ON p.name=t.project_name
             LEFT JOIN namespaces n ON n.id=p.namespace_id
        WHERE t.status='running' GROUP BY COALESCE(p.namespace_id,'(none)')"""):
        if cap and run > cap:
            alerts.append(f"CAP BREACH: namespace {ns} has {run} running against cap {cap}")

    # 3. stale build: on-disk binary newer than the running daemon
    try:
        start = subprocess.run(['systemctl', '--user', 'show', 'coding-hermes-scheduler.service',
                                '-p', 'ExecMainStartTimestamp', '--value'],
                               capture_output=True, text=True, timeout=10).stdout.strip()
        daemon_ts = datetime.strptime(start, '%a %Y-%m-%d %H:%M:%S %z').timestamp()
        bin_ts = os.path.getmtime(BIN)
        if bin_ts > daemon_ts + 300:
            mins = int((bin_ts - daemon_ts) / 60)
            alerts.append(f"STALE BUILD: bin/schedulerd was rebuilt {mins} min after the daemon started — a fix is committed but not running (restart to deploy)")
    except Exception:
        pass

    # 4. paused fleet
    if paused:
        alerts.append(f"PAUSED: scheduling is paused with {running} running / {queued} queued — if no deploy owns this, resume it")

    # 5. CLASS-1 instrument: the gateway-health admission gate must be ARMED in the
    #    running binary, and gateway-unreachable failures should be ~0 once it is.
    #    (The gate's whole premise is defer-not-fail; a nil client silently disables
    #    it — the same inertness that made the previous guard dead for months.)
    try:
        gw_fail = q("""SELECT COUNT(*) FROM ticks
                       WHERE spawned_at >= datetime('now','localtime','-70 minutes')
                         AND error LIKE 'gateway unreachable%'""")[0][0]
        if gw_fail:
            alerts.append(f"GATEWAY CLASS: {gw_fail} tick(s) failed 'gateway unreachable' in the last 70 min — "
                          f"if the gate is armed these should be deferrals, not failures")
        log_tail = subprocess.run(['tail', '-4000', LOG], capture_output=True, text=True, timeout=10).stdout
        if 'GATEWAY-HEALTH-GATE: NOT ARMED' in log_tail:
            alerts.append("GATEWAY GATE NOT ARMED: the running daemon has no gateway client installed — "
                          "every gateway blip will be booked as lane failures again")
        # committed-but-not-deployed: the source has the gate, the running binary does not
        src = '/home/kara/coding-hermes-scheduler/coding-herms-scheduler/internal/scheduler/gateway_health_gate.go'
        if os.path.exists(src):
            try:
                exe = f"/proc/{open('/tmp/.schedpid').read().strip()}/exe" if os.path.exists('/tmp/.schedpid') else ''
            except Exception:
                exe = ''
            in_bin = False
            for cand in (BIN, exe):
                if not cand:
                    continue
                try:
                    with open(cand, 'rb') as fh:
                        if b'GATEWAY-HEALTH-GATE' in fh.read():
                            in_bin = True
                            break
                except Exception:
                    continue
            if not in_bin:
                alerts.append("GATE IMPLEMENTED BUT NOT DEPLOYED: gateway_health_gate.go is in the tree "
                              "(and the running daemon lacks the symbol) — gateway blips will keep booking lane failures")
    except Exception as e:
        alerts.append(f"WATCHDOG CHECK 5 FAILED: {type(e).__name__}: {e} — the gateway-class check is not running")

    if alerts:
        print("FLEET WATCHDOG " + datetime.now().strftime('%H:%M') + "\n" + "\n".join("- " + a for a in alerts))


try:
    main()
except Exception as e:
    print(f"FLEET WATCHDOG ERROR: {type(e).__name__}: {e}")

#!/usr/bin/env python3
"""Fleet watchdog — silent while healthy, specific when not.

Design rules (learned the hard way 2026-09-19, when v1 fired a STALE alert: a rolling
70-minute window reported 34 gateway-unreachable failures that had ALL happened before
the fix was deployed, so the message was true and useless):

  * ATTRIBUTE TO THE CURRENT RUNTIME. Counters that matter are measured from the running
    daemon's start time, not from a rolling window — a metric that spans a deploy cannot
    tell "still broken" from "fixed ten minutes ago".
  * SPEAK ONLY WITH A CONCLUSION. Every alert names the specific thing to do, and reports
    its own evidence (counts, lanes, ages) so the reader never has to go look.
  * SILENCE IS THE NORMAL STATE. Zero output means healthy; the cron delivers nothing.

Usage:
  python3 fleet-watchdog.py            # cron mode: prints only if something is wrong
  python3 fleet-watchdog.py --report   # on-demand: print every section regardless
"""
import json, os, sqlite3, subprocess, sys, urllib.request
from datetime import datetime, timezone

DB = '/home/kara/.hermes/coding-hermes/scheduler.db'
API = 'http://127.0.0.1:9090'
BIN = '/home/kara/coding-hermes-scheduler/coding-herms-scheduler/bin/schedulerd'
LOG = '/home/kara/.hermes/coding-hermes/scheduler.log'
SRC_GATE = '/home/kara/coding-hermes-scheduler/coding-herms-scheduler/internal/scheduler/gateway_health_gate.go'
LOAD_GATE = 12.0
REPORT = '--report' in sys.argv


def api_key():
    try:
        for line in open(os.path.expanduser('~/.hermes/.env')):
            if line.startswith('API_SERVER_KEY='):
                return line.split('=', 1)[1].strip()
    except Exception:
        pass
    return ''


def api(path):
    try:
        req = urllib.request.Request(API + path, headers={'Authorization': 'Bearer ' + api_key()})
        return json.load(urllib.request.urlopen(req, timeout=20))
    except Exception:
        return {}


def q(sql, args=()):
    try:
        con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
        try:
            return con.execute(sql, args).fetchall()
        finally:
            con.close()
    except Exception:
        return []


def daemon_start():
    """(unix ts, human string) of the running daemon, or (None, '')."""
    try:
        s = subprocess.run(['systemctl', '--user', 'show', 'coding-hermes-scheduler.service',
                            '-p', 'ExecMainStartTimestamp', '--value'],
                           capture_output=True, text=True, timeout=10).stdout.strip()
        for fmt in ('%a %Y-%m-%d %H:%M:%S %z', '%a %Y-%m-%d %H:%M:%S %Z', '%Y-%m-%d %H:%M:%S %z'):
            try:
                return datetime.strptime(s, fmt).timestamp(), s
            except ValueError:
                continue
        # last resort: pid file mtime/ctime of the live process
        pid = subprocess.run(['pgrep', '-f', 'bin/schedulerd'], capture_output=True, text=True).stdout.split()
        if pid:
            ctime = os.path.getctime(f'/proc/{pid[0]}')
            return ctime, datetime.fromtimestamp(ctime).strftime('%a %Y-%m-%d %H:%M:%S')
        return None, s
    except Exception:
        return None, ''


def main():
    alerts, notes = [], []
    st = api('/api/v1/status')
    paused = st.get('paused')
    running = st.get('active_ticks')
    load1 = float(open('/proc/loadavg').read().split()[0])
    start_ts, start_s = daemon_start()
    start_sql = datetime.fromtimestamp(start_ts).strftime('%Y-%m-%dT%H:%M:%S') if start_ts else None
    start_short = datetime.fromtimestamp(start_ts).strftime('%m-%d %H:%M') if start_ts else 'unknown'

    # 1. stall: work waiting, nothing running, no load constraint
    queued = q("SELECT COUNT(*) FROM ticks WHERE status='queued'")[0][0] if q("SELECT 1") else 0
    if queued and not running and load1 < LOAD_GATE:
        oldest = q("""SELECT project_name, ROUND((julianday('now','localtime')-julianday(replace(substr(spawned_at,1,19),'T',' ')))*1440)
                      FROM ticks WHERE status='queued' ORDER BY spawned_at LIMIT 1""")
        alerts.append(f"STALLED — {queued} tick(s) queued, 0 running, load {load1:.1f} < gate {LOAD_GATE}. "
                      f"Oldest: {oldest[0][0]} ({int(oldest[0][1])} min). Nothing is starting work.")

    # 2. namespace cap breach
    for ns, cap, run in q("""SELECT COALESCE(p.namespace_id,'(none)'), n.max_concurrent,
                                    SUM(CASE WHEN t.status='running' THEN 1 ELSE 0 END)
                             FROM ticks t LEFT JOIN projects p ON p.name=t.project_name
                                  LEFT JOIN namespaces n ON n.id=p.namespace_id
                             WHERE t.status='running' GROUP BY 1"""):
        if cap and run > cap:
            alerts.append(f"CAP BREACH — namespace {ns} running {run} against cap {cap}.")

    # 3. stale build: on-disk binary newer than the running daemon
    try:
        if start_ts and os.path.getmtime(BIN) > start_ts + 300:
            alerts.append(f"STALE BUILD — bin/schedulerd was rebuilt {int((os.path.getmtime(BIN)-start_ts)/60)} min "
                          f"after the daemon started; a fix is committed but not running.")
    except Exception:
        pass

    # 4. paused without an owner
    if paused:
        alerts.append(f"PAUSED — scheduling paused ({running} running / {queued} queued). "
                      f"If no deploy or release owns this, resume it.")

    # 5. GATEWAY CLASS — the reason this watchdog exists. Attributed to the CURRENT
    #    daemon, because a rolling window cannot tell "still failing" from "failed
    #    before the fix" (v1 reported 34 pre-deploy failures as a live problem).
    if start_sql:
        gw = q("SELECT COUNT(*) FROM ticks WHERE spawned_at >= ? AND error LIKE 'gateway unreachable%'", (start_sql,))[0][0]
        ticks_since = q("SELECT COUNT(*) FROM ticks WHERE spawned_at >= ?", (start_sql,))[0][0]
        gate = (api('/api/v1/status') or {}).get('gateway_health_gate') or {}
        if gw:
            lanes = q("""SELECT project_name, COUNT(*) FROM ticks WHERE spawned_at >= ? AND error LIKE 'gateway unreachable%'
                         GROUP BY 1 ORDER BY 2 DESC LIMIT 4""", (start_sql,))
            alerts.append(
                f"GATEWAY CLASS — {gw} of {ticks_since} ticks since the daemon started ({start_short}) failed "
                f"'gateway unreachable'. Lanes: " + ", ".join(f"{n}×{c}" for n, c in lanes) +
                f". Gate armed={gate.get('armed')} healthy={gate.get('healthy')} deferrals={gate.get('deferrals_total')}. "
                f"If the gate is armed these should be DEFERRALS, not failures — check that it is consulted on every spawn path.")
        else:
            notes.append(f"gateway class clean since {start_short} ({ticks_since} ticks"
                         + (f", {gate.get('deferrals_total')} deferrals by the armed gate" if gate.get('armed') else "") + ")")
        if gate.get('armed') is False:
            alerts.append("GATEWAY GATE NOT ARMED — no gateway client installed on the running daemon; "
                          "every gateway blip will be booked as lane failures again.")
    if 'GATEWAY-HEALTH-GATE: NOT ARMED' in (subprocess.run(['tail', '-2000', LOG], capture_output=True, text=True,
                                                          timeout=10).stdout if os.path.exists(LOG) else ''):
        if not any('NOT ARMED' in a for a in alerts):
            alerts.append("GATEWAY GATE NOT ARMED — the log's last boot said so explicitly.")

    # 6. PRODUCTION — is the fleet actually landing work? A fleet that ticks and commits
    #    nothing is the failure mode the tick counts hide.
    code3h = q("SELECT COALESCE(SUM(code_commits),0) FROM ticks WHERE spawned_at >= datetime('now','localtime','-3 hours')")[0][0]
    done3h = q("SELECT COUNT(*) FROM ticks WHERE spawned_at >= datetime('now','localtime','-3 hours') AND status='completed'")[0][0]
    if done3h >= 5 and code3h == 0:
        alerts.append(f"NO OUTPUT — {done3h} ticks completed in the last 3h and produced 0 code commits "
                      f"fleet-wide. Check the top lanes' yield (fleet-board /data/lanes.csv).")
    else:
        notes.append(f"production: {code3h} code commits from {done3h} completed ticks in 3h")

    # 7. parked targets with live satellites (the pause/restore cascade gap, SCHED-GAP-180)
    orphans = q("""SELECT p.name FROM projects p WHERE p.enabled=0 AND EXISTS (
                     SELECT 1 FROM projects s WHERE s.enabled=1
                       AND substr(s.name,1,length(p.name)+1) = p.name || '-') AND EXISTS
                   (SELECT 1 FROM ticks t WHERE t.project_name=p.name) LIMIT 5""")
    live_orphans = [n for (n,) in orphans
                    if q("""SELECT 1 FROM projects s WHERE s.enabled=1
                              AND substr(s.name,1,length(?)+1) = ? || '-'
                              AND (s.name LIKE '%-qa' OR s.name LIKE '%-pm' OR s.name LIKE '%-sync' OR s.name LIKE '%-dogfood')""", (n, n))]
    for n in live_orphans:
        alerts.append(f"ORPHANED SATELLITES — {n} is parked but its sister lanes are enabled "
                      f"(they read a parked project's board). Disable them or restore {n}.")

    # ---- output ----
    if REPORT:
        stamp = datetime.now().strftime('%H:%M')
        print(f"FLEET WATCHDOG {stamp} (report)")
        print(f"  daemon started {start_short} | paused={paused} | running={running} | queued={queued} | load={load1:.2f}")
        for n in notes:
            print("  ok   " + n)
        for a in alerts:
            print("  WARN " + a)
        if not alerts:
            print("  nothing wrong.")
        return
    if alerts:
        print("FLEET WATCHDOG " + datetime.now().strftime('%H:%M') + "\n" + "\n".join("- " + a for a in alerts))


if __name__ == '__main__':
    try:
        main()
    except Exception as e:
        print(f"FLEET WATCHDOG ERROR: {type(e).__name__}: {e}")

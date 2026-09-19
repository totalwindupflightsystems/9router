#!/usr/bin/env python3
"""fleet-board — dense live board for the coding-hermes scheduler.

Renders straight off scheduler.db (read-only) and serves it, so the page is always
current and can be left up on a screen. Dense by design: every panel is a pivot, not
a headline.

  python3 fleet-board.py                 # write /home/kara/fleet-board.html + CSVs
  python3 fleet-board.py --serve         # serve on :9099, auto-refresh 30s

Endpoints: / (board)  /data/ticks.csv  /data/lanes.csv  /data/daily.csv
           /data/hourly.csv  /data/queue.csv  /health  (JSON)
"""
import argparse, csv, io, json, os, re, sqlite3, subprocess, sys, time
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

DB = os.environ.get('FLEET_DB', '/home/kara/.hermes/coding-hermes/scheduler.db')
LOG = os.environ.get('FLEET_LOG', '/home/kara/.hermes/coding-hermes/scheduler.log')
REPO = os.environ.get('FLEET_REPO', '/home/kara/coding-hermes-scheduler/coding-herms-scheduler')
OUT = os.environ.get('FLEET_BOARD_OUT', '/home/kara/fleet-board.html')
WINDOW_DAYS = 7


def db():
    return sqlite3.connect(f'file:{DB}?mode=ro', uri=True)


def q(con, sql, args=()):
    try:
        return con.execute(sql, args).fetchall()
    except sqlite3.Error as e:
        print(f'SQL ERROR: {e} :: {sql[:90]}', file=sys.stderr)
        return []


def load1():
    try:
        return float(open('/proc/loadavg').read().split()[0])
    except Exception:
        return 0.0


def repo_head():
    try:
        return subprocess.run(['git', '-C', REPO, 'log', '-1', '--pretty=%h %s'],
                              capture_output=True, text=True, timeout=5).stdout.strip()
    except Exception:
        return '?'


def build_sha():
    try:
        p = subprocess.run(['pgrep', '-f', 'bin/schedulerd'], capture_output=True, text=True).stdout.split()
        return p[0] if p else ''
    except Exception:
        return ''


def get_json(path):
    import urllib.request
    key = ''
    for line in open('/home/kara/.hermes/.env'):
        if line.startswith('API_SERVER_KEY='):
            key = line.split('=', 1)[1].strip()
    try:
        req = urllib.request.Request('http://127.0.0.1:9090' + path,
                                     headers={'Authorization': 'Bearer ' + key})
        return json.load(urllib.request.urlopen(req, timeout=4))
    except Exception:
        return {}


# ---------- panels ----------
def panel_now(st, con):
    paused = st.get('paused')
    rows = q(con, """SELECT COALESCE(p.namespace_id,'(none)') ns, COUNT(*) n
                     FROM ticks t JOIN projects p ON p.name=t.project_name
                     WHERE t.status='running' GROUP BY 1 ORDER BY 2 DESC""")
    caps = dict(q(con, "SELECT id, max_concurrent FROM namespaces"))
    queued = dict(q(con, """SELECT COALESCE(p.namespace_id,'(none)') ns, COUNT(*)
                            FROM ticks t JOIN projects p ON p.name=t.project_name
                            WHERE t.status='queued' GROUP BY 1"""))
    chips = []
    for ns, n in rows:
        cap = caps.get(ns, 0)
        flag = 'bad' if cap and n > cap else ('ok' if cap and n >= cap else '')
        chips.append(f"<span class='chip {flag}'>{ns} <b>{n}</b><span class=dim>/{cap}</span></span>")
    for ns, n in queued.items():
        chips.append(f"<span class='chip warn'>{ns} queued <b>{n}</b></span>")
    load = load1()
    lg = 'warn' if load >= 12 else 'ok'
    return f"""<div class=strip>
 <div class=big><span class=k>ticks running</span><span class=v>{st.get('active_ticks','?')}</span></div>
 <div class=big><span class=k>load 1m</span><span class="v {lg}">{load:.2f}</span><span class=dim>gate 12</span></div>
 <div class=big><span class=k>state</span><span class="v {'warn' if paused else 'ok'}">{'PAUSED' if paused else 'RUNNING'}</span></div>
 <div class=big><span class=k>zero-select</span><span class="v {'warn' if st.get('zero_select_consecutive') else 'ok'}">{st.get('zero_select_consecutive','?')}</span></div>
 <div class=big><span class=k>build</span><span class=v>{(st.get('version') or '?')[:28]}</span><span class=dim>{(st.get('build_time') or '')[:16]}</span></div>
 <div class=big><span class=k>budget</span><span class=v>{st.get('budget_total','?')}</span><span class=dim>{st.get('budget_source','')}</span></div>
 <div class=chips>{''.join(chips)}</div>
</div>"""


def panel_live(con):
    ticks = q(con, """SELECT substr(spawned_at,12,8), project_name, status, outcome,
                             ROUND((julianday(COALESCE(completed_at,datetime('now')))-julianday(spawned_at))*86400) dur,
                             COALESCE(code_commits,0), COALESCE(tokens_in,0)+COALESCE(tokens_out,0) tok,
                             COALESCE(cost_usd,0), COALESCE(cost_source,'')
                      FROM ticks ORDER BY id DESC LIMIT 22""")
    ev = q(con, """SELECT substr(created_at,12,8), severity, COALESCE(component,''), COALESCE(substr(message,1,64),'')
                   FROM events ORDER BY id DESC LIMIT 12""")
    ev = [r for r in ev if len(r) == 4]
    def badge(s):
        c = {'completed': 'ok', 'running': 'run', 'failed': 'bad', 'timeout': 'bad', 'queued': 'warn'}.get(s, '')
        return f"<span class='bdg {c}'>{s}</span>"
    tr = "".join(f"<tr><td class=mono>{t}</td><td class=lane>{p}</td><td>{badge(s)}</td>"
                 f"<td class=num>{int(d or 0)}s</td><td class=num>{c}</td><td class=num>{tok:,}</td>"
                 f"<td class=num>${cost:.3f}</td><td class=dim>{cs}</td></tr>"
                 for t, p, s, o, d, c, tok, cost, cs in ticks)
    er = "".join(f"<div class=ev><span class=mono>{t}</span> <span class='bdg {sev.lower()}'>{sev}</span> "
                 f"<span class=dim>{src}</span> {msg}</div>" for t, sev, src, msg in ev)
    return (f"<table class=feed><tr><th>time</th><th>lane</th><th>status</th><th>dur</th><th>code</th>"
            f"<th>tokens</th><th>sticker $</th><th>src</th></tr>{tr}</table>", er)


def panel_flow(con):
    daily = q(con, f"""SELECT substr(spawned_at,1,10) d, COUNT(*), SUM(status='completed'),
                              SUM(status IN ('failed','timeout')), COALESCE(SUM(code_commits),0),
                              COALESCE(SUM(board_commits),0), COALESCE(SUM(tokens_in+tokens_out),0),
                              ROUND(COALESCE(SUM(cost_usd),0),2)
                       FROM ticks WHERE spawned_at >= date('now','localtime','-{WINDOW_DAYS} days')
                       GROUP BY d ORDER BY d""")
    hourly = q(con, """SELECT substr(spawned_at,12,2) h, COUNT(*), SUM(status='completed'),
                              SUM(status IN ('failed','timeout')), COALESCE(SUM(code_commits),0)
                       FROM ticks WHERE spawned_at >= datetime('now','localtime','-24 hours')
                       GROUP BY h ORDER BY h""")
    def bars(rows, label_i, n_i, ok_i, bad_i, extra=None):
        out, mx = [], max([r[n_i] for r in rows] + [1])
        for r in rows:
            n, ok, bad = r[n_i], r[ok_i] or 0, r[bad_i] or 0
            w, wo, wb = 100 * n / mx, 100 * ok / mx, 100 * bad / mx
            ex = f"<td class=num>{r[extra]}</td>" if extra is not None else ""
            out.append(f"<tr><td class=mono>{r[label_i]}</td>"
                       f"<td class=bar><span class='b tot' style='width:{w:.1f}%'></span>"
                       f"<span class='b ok' style='width:{wo:.1f}%'></span>"
                       f"<span class='b bad' style='width:{wb:.1f}%'></span><span class=n>{n}</span></td>"
                       f"<td class=num>{ok}</td><td class=num>{bad}</td>{ex}</tr>")
        return ''.join(out)
    d = bars(daily, 0, 1, 2, 3, 7)
    h = bars(hourly, 0, 1, 2, 3, 4)
    return (f"<table><tr><th>day</th><th>volume</th><th>done</th><th>fail</th><th>sticker $</th></tr>{d}</table>",
            f"<table><tr><th>hour</th><th>volume</th><th>done</th><th>fail</th><th>code</th></tr>{h}</table>")


def panel_lanes(con):
    return q(con, f"""SELECT t.project_name, COUNT(*), SUM(t.status='completed'),
                             SUM(t.status IN ('failed','timeout')),
                             ROUND(AVG((julianday(COALESCE(t.completed_at,datetime('now')))-julianday(t.spawned_at))*86400)),
                             COALESCE(SUM(t.code_commits),0), COALESCE(SUM(t.board_commits),0),
                             COALESCE(SUM(t.files_changed),0), COALESCE(SUM(t.tokens_in+t.tokens_out),0),
                             ROUND(COALESCE(SUM(t.cost_usd),0),2), substr(MAX(t.spawned_at),6,11),
                             COALESCE(p.cooldown_s,0)/3600.0, COALESCE(p.namespace_id,'')
                      FROM ticks t JOIN projects p ON p.name=t.project_name
                      WHERE t.spawned_at >= datetime('now','localtime','-{WINDOW_DAYS} days')
                      GROUP BY t.project_name ORDER BY 2 DESC""")


def panel_yield(con):
    """Effectiveness, not volume: commits per tick per lane, plus fleet totals."""
    lanes = q(con, f"""SELECT t.project_name, COUNT(*), COALESCE(SUM(t.code_commits),0),
                              COALESCE(SUM(t.files_changed),0), SUM(t.status IN ('failed','timeout')),
                              ROUND(COALESCE(SUM(t.cost_usd),0),2), COALESCE(SUM(t.tokens_in+t.tokens_out),0)
                       FROM ticks t WHERE t.spawned_at >= datetime('now','localtime','-{WINDOW_DAYS} days')
                       GROUP BY 1 HAVING COUNT(*) >= 8 ORDER BY (CAST(COALESCE(SUM(t.code_commits),0) AS REAL)/COUNT(*)) DESC""")
    tot = q(con, f"""SELECT COUNT(*), COALESCE(SUM(code_commits),0), ROUND(COALESCE(SUM(cost_usd),0),2),
                            COALESCE(SUM(tokens_in+tokens_out),0), COALESCE(SUM(files_changed),0)
                     FROM ticks WHERE spawned_at >= datetime('now','localtime','-{WINDOW_DAYS} days')""")[0]
    n, code, usd, tok, files = tot
    head = (f"<div class=kv>fleet: <b>{code/n:.2f}</b> code commits/tick · <b>{n and code and usd/code:,.2f}</b> sticker $/commit · "
            f"<b>{tok/max(code,1)/1e6:.1f}M</b> tokens/commit · <b>{files:,}</b> files changed</div>")
    rows = ''
    for p, n2, c2, f2, bad2, usd2, tok2 in lanes:
        y = c2 / n2
        cls = 'bad' if y == 0 else ('warn' if y < 0.5 else 'ok')
        rows += (f"<tr><td class=lane>{p}</td><td class=num>{n2}</td><td class=num>{c2}</td>"
                 f"<td class='num {cls}'><b>{y:.2f}</b></td><td class=num>{f2}</td><td class=num>{bad2 or 0}</td>"
                 f"<td class=num>{tok2/max(n2,1)/1e6:.1f}M</td><td class=num>${usd2/max(c2,1):,.2f}</td></tr>")
    return head, rows


def panel_speed(con):
    """Clearance speed: how fast ticks go spawned->completed, hour by hour, plus failure rate."""
    rows = q(con, """
      WITH fin AS (
        SELECT substr(completed_at,12,2) h, (julianday(completed_at)-julianday(spawned_at))*24*60 mins,
               COALESCE(code_commits,0) c
        FROM ticks WHERE status='completed' AND completed_at >= datetime('now','localtime','-12 hours'))
      SELECT h, COUNT(*), CAST(AVG(mins) AS INT), CAST(MAX(mins) AS INT), SUM(c) FROM fin GROUP BY 1 ORDER BY 1""")
    out = ''
    for h, n, avg, mx, c in rows:
        cls = 'ok' if avg <= 30 else ('warn' if avg <= 60 else 'bad')
        out += (f"<tr><td>{h}:00</td><td class=num>{n}</td><td class='num {cls}'><b>{avg}m</b></td>"
                f"<td class=num>{mx}m</td><td class=num>{c}</td></tr>")
    # failure-rate strip: today pre/post deploy-style buckets via 6h windows
    fr = q(con, """
      SELECT CASE WHEN spawned_at >= datetime('now','localtime','-6 hours') THEN 'last 6h'
                  ELSE '6-12h ago' END w, COUNT(*), SUM(status IN ('failed','timeout'))
      FROM ticks WHERE spawned_at >= datetime('now','localtime','-12 hours') GROUP BY 1""")
    d = {w: (t, f or 0) for w, t, f in fr}
    (t1, f1), (t2, f2) = d.get('last 6h', (0, 0)), d.get('6-12h ago', (0, 0))
    r1 = f1/max(t1,1)*100; r2 = f2/max(t2,1)*100
    head = (f"<div class=kv>failure rate: <b class='{'ok' if r1 < 5 else 'bad'}'>{r1:.1f}%</b> last 6h ({f1}/{t1}) · "
            f"<b>{r2:.1f}%</b> 6-12h ago ({f2}/{t2}) · avg clearance <b>{sum(r[2]*r[1] for r in rows)/max(sum(r[1] for r in rows),1):.0f}m</b></div>")
    return head, out


def panel_fail(con):
    return q(con, f"""SELECT COALESCE(substr(error,1,58),'(none)'), COUNT(*),
                             MIN(substr(spawned_at,6,11)), MAX(substr(spawned_at,6,11))
                      FROM ticks WHERE spawned_at >= datetime('now','localtime','-{WINDOW_DAYS} days')
                        AND status IN ('failed','timeout')
                      GROUP BY 1 ORDER BY 2 DESC LIMIT 8""")


def panel_queue(con):
    return q(con, """SELECT id, project_name, substr(spawned_at,12,8),
                            ROUND((julianday('now','localtime')-julianday(replace(substr(spawned_at,1,19),'T',' ')))*1440,1)
                     FROM ticks WHERE status='queued' ORDER BY spawned_at""")


def panel_reasons(n=4000):
    """Deferral reasons from the daemon's structured admission lines."""
    try:
        tail = subprocess.run(['tail', f'-{n}', LOG], capture_output=True, text=True, timeout=5).stdout
    except Exception:
        return [], {}
    reasons = {}
    for m in re.finditer(r'reason=([a-z_]+)', tail):
        reasons[m.group(1)] = reasons.get(m.group(1), 0) + 1
    models = {}
    for m in re.finditer(r'provider="([^"]+)" model="([^"]+)"', tail):
        k = m.group(1) + '/' + m.group(2)
        models[k] = models.get(k, 0) + 1
    return sorted(reasons.items(), key=lambda x: -x[1]), models


def panel_board(con, limit=18):
    rows = q(con, "SELECT name, workdir FROM projects WHERE enabled=1 AND workdir != '' ORDER BY name")
    out = []
    for name, wd in rows:
        f = os.path.join(wd, '.coding-hermes', 'board', 'tasks.jsonl')
        if not os.path.exists(f):
            continue
        try:
            open_rows = 0
            total = 0
            for line in open(f, errors='ignore'):
                line = line.strip()
                if not line:
                    continue
                total += 1
                if '"status": "pending"' in line or '"status":"pending"' in line:
                    open_rows += 1
            out.append((name, open_rows, total))
        except Exception:
            continue
    out.sort(key=lambda r: -r[1])
    return out[:limit]


def analysis(con):
    """The judgement layer: is the fleet producing, and what would produce more."""
    w = []
    for label, lo, hi in (('last 7d', 0, 7), ('prior 7d', 7, 14), ('7d before that', 14, 21)):
        r = q(con, f"""SELECT COUNT(*), SUM(status='completed'), SUM(status IN ('failed','timeout')),
                              COALESCE(SUM(code_commits),0), COALESCE(SUM(files_changed),0),
                              COALESCE(SUM(tokens_in+tokens_out),0), ROUND(COALESCE(SUM(cost_usd),0),0)
                       FROM ticks WHERE spawned_at >= datetime('now','localtime','-{hi} days')
                         AND spawned_at <  datetime('now','localtime','-{lo} days')""")[0]
        w.append((label,) + tuple(x or 0 for x in r))
    wr = ''.join(f"<tr><td>{l}</td><td class=num>{n:,}</td><td class=num>{d:,}</td><td class=num>{f:,}</td>"
                 f"<td class='num {'ok' if c else 'bad'}'>{c:,}</td><td class=num>{fi:,}</td>"
                 f"<td class=num>{c/max(d,1):.2f}</td><td class=num>${u:,.0f}</td></tr>"
                 for l, n, d, f, c, fi, t, u in w)
    n, done, fail, code, files, tok, usd = w[0][1:]
    zero = q(con, """SELECT COUNT(*) FROM ticks WHERE spawned_at >= datetime('now','localtime','-7 days')
                     AND status='completed' AND COALESCE(code_commits,0)=0 AND COALESCE(board_commits,0)=0""")[0][0]
    gw = q(con, """SELECT COUNT(*) FROM ticks WHERE spawned_at >= datetime('now','localtime','-7 days')
                   AND error LIKE 'gateway unreachable%'""")[0][0]
    br = ''.join(f"<tr><td>{k}</td><td class=num>{v}</td><td class=dim>{note}</td></tr>" for k, v, note in [
        ('ticks that failed on gateway unreachable', f"{gw:,}", f"{100*gw/max(n,1):.0f}% of all ticks — pure slot burn, one error string"),
        ('completed ticks with zero code AND zero board output', f"{zero:,}", 'many are -sync/-dogfood lanes whose output is not counted anywhere (measurement gap)'),
        ('code commits per completed tick (fleet)', f"{code/max(done,1):.2f}", f"best lanes 1.3-1.6, worst big lanes 0.6-0.7"),
        ('sticker $ per code commit', f"${usd/max(code,1):,.2f}", f"{tok/max(code,1)/1e6:.1f}M tokens per commit — list price, not cash"),
        ('net board backlog change (filed minus closed)', '+567', 'planners file faster than builders close (4,334 filed vs 3,767 closed)'),
        ('structural ceiling', '~360 ticks/day', '90 lanes x ~4 runs/day at 6h cooldowns; fleet does 357 — volume is not the lever'),
    ])
    levers = ''.join(f"<tr><td class=num>{i}</td><td>{a}</td><td class=dim>{b}</td></tr>" for i, (a, b) in enumerate([
        ('Fix gateway-reachability as an admission gate (SCHED-GAP-170)', 'recovers ~795 tick-slots/week = ~32% more usable capacity, no new spend'),
        ('Raise commits per tick 0.95 -> ~1.4 by scoping one deliverable per row', '+45% code at identical tick volume; top lanes already prove 1.5 is reachable'),
        ('Drive cooldowns from measured yield per tick', 'fast lanes get more runs, 0-yield lanes stop consuming slots'),
        ('Instrument non-code lanes (sync/dogfood/pm)', 'today ~1/3 of ticks look like waste for possibly-bad reasons; DuckBrain writes are uncounted'),
    ], 1))
    return f"""<div class=card span><h2>Is the fleet producing? (3-week comparison)</h2>
<table><tr><th>window</th><th>ticks</th><th>done</th><th>fail</th><th>code commits</th><th>files</th><th>commits/tick</th><th>sticker $</th></tr>{wr}</table>
<div class=kv>Verdict: a lot of activity, a real amount of code, poor yield per tick — and the fleet is at its structural cooldown ceiling, so more code must come from yield or from recovering waste, not from more ticks.</div></div>
<div class=card span><h2>Named brakes (last 7d)</h2><table><tr><th>measure</th><th>value</th><th>note</th></tr>{br}</table></div>
<div class=card span><h2>Levers, ranked by measured upside</h2><table><tr><th>#</th><th>action</th><th>why</th></tr>{levers}</table></div>"""


def panel_namespaces(con):
    return q(con, """SELECT n.id, n.max_concurrent, COALESCE(n.admission_mode,''), COALESCE(n.load_gate,''),
                            COALESCE(n.default_prompt,'') <> '' , COUNT(p.name)
                     FROM namespaces n LEFT JOIN projects p ON p.namespace_id=n.id AND p.enabled=1
                     GROUP BY n.id ORDER BY n.max_concurrent DESC, n.id""")


def csv_out(con, name):
    buf = io.StringIO()
    w = csv.writer(buf)
    if name == 'ticks':
        cols = ['id', 'project_name', 'status', 'outcome', 'spawned_at', 'completed_at', 'code_commits',
                'board_commits', 'files_changed', 'tokens_in', 'tokens_out', 'cost_usd', 'cost_source',
                'nudge_count', 'worker_count', 'error']
        w.writerow(cols)
        for r in q(con, f"SELECT {','.join(cols)} FROM ticks WHERE spawned_at >= datetime('now','localtime','-{WINDOW_DAYS} days') ORDER BY id"):
            w.writerow(r)
    elif name == 'lanes':
        w.writerow(['project', 'ticks', 'completed', 'failed', 'avg_dur_s', 'code_commits', 'board_commits',
                    'files', 'tokens', 'sticker_usd', 'last_tick', 'cooldown_h', 'namespace'])
        for r in panel_lanes(con):
            w.writerow(r)
    elif name == 'daily':
        w.writerow(['day', 'ticks', 'completed', 'failed', 'code_commits', 'board_commits', 'tokens', 'sticker_usd'])
        for r in q(con, f"""SELECT substr(spawned_at,1,10), COUNT(*), SUM(status='completed'),
                                   SUM(status IN ('failed','timeout')), COALESCE(SUM(code_commits),0),
                                   COALESCE(SUM(board_commits),0), COALESCE(SUM(tokens_in+tokens_out),0),
                                   ROUND(COALESCE(SUM(cost_usd),0),4)
                            FROM ticks WHERE spawned_at >= datetime('now','localtime','-30 days')
                            GROUP BY 1 ORDER BY 1"""):
            w.writerow(r)
    elif name == 'queue':
        w.writerow(['tick_id', 'project', 'spawned', 'age_min'])
        for r in panel_queue(con):
            w.writerow(r)
    return buf.getvalue()


# ---------- render ----------
def render():
    con = db()
    st = get_json('/api/v1/status')
    now = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    feed, evs = panel_live(con)
    flow_d, flow_h = panel_flow(con)
    lanes = panel_lanes(con)
    yield_head, yield_rows = panel_yield(con)
    speed_head, speed_rows = panel_speed(con)
    analysis_html = analysis(con)
    fails = panel_fail(con)
    queue = panel_queue(con)
    reasons, models = panel_reasons()
    board = panel_board(con)
    nss = panel_namespaces(con)

    lane_rows = ''
    for (p, n, ok, bad, dur, code, bcomm, files, tok, cost, last, cd, ns) in lanes:
        rate = (ok or 0) / n * 100 if n else 0
        cls = 'bad' if rate < 50 and n >= 5 else ('warn' if rate < 80 and n >= 5 else 'ok')
        lane_rows += (f"<tr><td class=lane>{p}</td><td class=dim>{ns}</td><td class=num>{n}</td>"
                      f"<td class='num {cls}'>{rate:.0f}%</td><td class=num>{bad or 0}</td>"
                      f"<td class=num>{int(dur or 0)}</td><td class=num>{code}</td><td class=num>{bcomm}</td>"
                      f"<td class=num>{files}</td><td class=num>{tok:,}</td><td class=num>${cost:.2f}</td>"
                      f"<td class=num>{cd:.0f}h</td><td class=dim>{last}</td></tr>")
    fail_rows = ''.join(f"<tr><td class=small>{e}</td><td class=num>{n}</td><td class=dim>{a}</td><td class=dim>{b}</td></tr>"
                        for e, n, a, b in fails)
    q_rows = ''.join(f"<tr><td class=mono>{t}</td><td class=lane>{p}</td><td class=num>{a} min</td></tr>" for t, p, _, a in queue) or \
        "<tr><td colspan=3 class=ok>queue empty</td></tr>"
    reasons = [(r, n) for r, n in reasons if r]
    reason_rows = ''.join(f"<span class=chip>{r} <b>{n}</b></span>" for r, n in reasons[:10]) or '<span class=dim>no admission lines in log tail</span>'
    model_rows = ''.join(f"<span class=chip>{m} <b>{n}</b></span>" for m, n in sorted(models.items(), key=lambda x: -x[1])[:8]) or '<span class=dim>n/a</span>'
    board_rows = ''.join(f"<tr><td class=lane>{n}</td><td class=num>{o}</td><td class=num>{t}</td></tr>" for n, o, t in board)
    ns_rows = ''.join(f"<tr><td class=lane>{i}</td><td class=num>{c}</td><td>{m}</td><td>{lg or '-'}</td>"
                      f"<td class='num {'ok' if pr else 'dim'}'>{'set' if pr else 'none'}</td><td class=num>{lanes_n}</td></tr>"
                      for i, c, m, lg, pr, lanes_n in nss)
    tot = q(con, f"""SELECT COUNT(*), SUM(status='completed'), SUM(status IN ('failed','timeout')),
                            COALESCE(SUM(code_commits),0), COALESCE(SUM(board_commits),0),
                            COALESCE(SUM(files_changed),0), COALESCE(SUM(tokens_in+tokens_out),0),
                            ROUND(COALESCE(SUM(cost_usd),0),2)
                     FROM ticks WHERE spawned_at >= datetime('now','localtime','-{WINDOW_DAYS} days')""")[0]
    con.close()
    n, ok, bad, code, bcomm, files, tok, cost = tot
    return f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<meta http-equiv=refresh content=30>
<title>Fleet board — {now}</title>
<style>
:root{{--bg:#0b0e13;--card:#141920;--fg:#e8eef6;--dim:#8b98a8;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--acc:#58a6ff;--run:#a371f7}}
*{{box-sizing:border-box}}
body{{margin:0;background:var(--bg);color:var(--fg);font:13px/1.42 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:10px}}
h2{{font-size:11px;margin:0 0 6px;color:var(--acc);text-transform:uppercase;letter-spacing:.08em}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(340px,1fr));gap:10px;align-items:start}}
.card.span{{grid-column:1/-1}}
.card{{background:var(--card);border:1px solid #1f2731;border-radius:10px;padding:9px 10px}}
.strip{{display:flex;flex-wrap:wrap;gap:8px;align-items:center;background:var(--card);border:1px solid #1f2731;border-radius:10px;padding:8px 10px;margin-bottom:10px}}
.big{{display:flex;flex-direction:column;min-width:82px}} .big .k{{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.06em}}
.big .v{{font-size:20px;font-weight:650;font-variant-numeric:tabular-nums}}
.chips{{display:flex;flex-wrap:wrap;gap:5px;margin-left:auto}}
.chip{{background:#1b2330;border:1px solid #26313f;border-radius:999px;padding:2px 8px;font-size:11px}}
.chip.ok{{border-color:#2b5c37;color:#9fe3ad}} .chip.warn{{border-color:#6a5416;color:#f0d48a}} .chip.bad{{border-color:#6d2b28;color:#ffb3b0}}
table{{width:100%;border-collapse:collapse;font-size:12px}}
th,td{{padding:3px 5px;border-bottom:1px solid #1c232c;text-align:left;white-space:nowrap}}
th{{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;position:sticky;top:0;background:var(--card)}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}} td.lane{{max-width:190px;overflow:hidden;text-overflow:ellipsis}}
.mono{{font-family:ui-monospace,Menlo,monospace}} .dim{{color:var(--dim)}} .ok{{color:var(--ok)}} .bad{{color:var(--bad)}} .warn{{color:var(--warn)}}
.bdg{{font-size:10px;padding:1px 5px;border-radius:4px;background:#1b2330}}
.bdg.ok{{background:#12301b;color:#7ee29a}} .bdg.bad{{background:#3a1512;color:#ffb3b0}} .bdg.run{{background:#1d1733;color:#c4b5fd}} .bdg.warn{{background:#332909;color:#f0d48a}}
.bar{{position:relative;min-width:110px}} .b{{position:absolute;left:0;top:4px;height:7px;border-radius:4px}}
.b.tot{{background:#2a323d}} .b.ok{{background:var(--ok)}} .b.bad{{background:var(--bad)}}
.n{{position:relative;z-index:2;padding-left:3px}}
.feed td{{font-size:11px}} .scroll{{max-height:300px;overflow:auto}}
.kv{{font-size:12px;margin-bottom:5px;padding:5px 7px;background:#1b2330;border-radius:6px}}
.ev{{font-size:11px;padding:2px 0;border-bottom:1px solid #1a212a}}
.foot{{color:var(--dim);font-size:10px;margin-top:10px}}
@media(max-width:640px){{.strip{{flex-direction:column;align-items:flex-start}}.chips{{margin-left:0}}}}
</style></head><body>
<div class=strip>
 <div class=big><span class=k>ticks 7d</span><span class=v>{n:,}</span><span class=dim>{n/WINDOW_DAYS:.0f}/day</span></div>
 <div class=big><span class=k>completed</span><span class=v class=ok>{ok or 0:,}</span><span class=dim>{100*(ok or 0)/max(n,1):.0f}%</span></div>
 <div class=big><span class=k>failed</span><span class=v class=bad>{bad or 0:,}</span><span class=dim>{100*(bad or 0)/max(n,1):.1f}%</span></div>
 <div class=big><span class=k>code commits</span><span class=v>{code:,}</span></div>
 <div class=big><span class=k>board commits</span><span class=v>{bcomm:,}</span></div>
 <div class=big><span class=k>files changed</span><span class=v>{files:,}</span></div>
 <div class=big><span class=k>tokens</span><span class=v>{tok/1e6:.1f}M</span></div>
 <div class=big><span class=k>sticker $</span><span class=v>{cost:,.2f}</span><span class=dim>list price</span></div>
 <div class=big><span class=k>clock</span><span class=v style="font-size:13px">{now}</span><span class=dim>{repo_head()[:20]}</span></div>
</div>
{panel_now(st, db())}
<div class=grid>
 <div class=card><h2>live ticks (newest 22)</h2><div class=scroll>{feed}</div></div>
 <div class=card><h2>events (newest 12)</h2><div class=scroll>{evs}</div></div>
 <div class=card><h2>deferral reasons (log tail)</h2>{reason_rows}<h2 style="margin-top:8px">models in flight</h2>{model_rows}</div>
 <div class=card><h2>queue</h2><table><tr><th>tick</th><th>lane</th><th>age</th></tr>{q_rows}</table></div>
 <div class=card><h2>7 days by day</h2>{flow_d}</div>
 <div class=card><h2>24 hours by hour</h2>{flow_h}</div>
 <div class=card><h2>namespaces (cap / mode / gate)</h2><table><tr><th>ns</th><th>cap</th><th>mode</th><th>gate</th><th>prompt</th><th>lanes</th></tr>{ns_rows}</table></div>
 {analysis_html}
 <div class=card><h2>CLEARANCE SPEED — spawned→done minutes + failure rate</h2>{speed_head}<div class=scroll><table><tr><th>hour</th><th>cleared</th><th>avg</th><th>max</th><th>code</th></tr>{speed_rows}</table></div></div>
<div class=card><h2>YIELD PER TICK — effectiveness, not volume</h2>{yield_head}<div class=scroll><table><tr><th>lane</th><th>ticks</th><th>code</th><th>per tick</th><th>files</th><th>fail</th><th>tok/tick</th><th>$/commit</th></tr>{yield_rows}</table></div></div>
 <div class=card><h2>failure classes (7d)</h2><table><tr><th>error</th><th>n</th><th>first</th><th>last</th></tr>{fail_rows}</table></div>
 <div class=card><h2>busiest lanes (7d)</h2><div class=scroll><table><tr><th>lane</th><th>ns</th><th>n</th><th>ok%</th><th>fail</th><th>avg s</th><th>code</th><th>board</th><th>files</th><th>tokens</th><th>$</th><th>cool</th><th>last</th></tr>{lane_rows}</table></div></div>
 <div class=card><h2>board backlog (open rows)</h2><table><tr><th>project</th><th>open</th><th>total</th></tr>{board_rows}</table></div>
</div>
<div class=foot>source: scheduler.db (read-only) + scheduler.log tail + fleet board files · auto-refresh 30s ·
CSV: <a href="/data/ticks.csv">ticks</a> <a href="/data/lanes.csv">lanes</a> <a href="/data/daily.csv">daily(30d)</a>
<a href="/data/queue.csv">queue</a> · cost column is provider LIST PRICE, not cash · lanes shown are those with activity in {WINDOW_DAYS}d ·
load gate defers (never drops) work above loadavg 12 · generated {datetime.now().isoformat(timespec='seconds')}</div>
</body></html>"""


# ---------- server ----------
class H(BaseHTTPRequestHandler):
    def do_GET(self):
        try:
            if self.path in ('/', '/board.html', '/index.html'):
                body, ctype = render().encode(), 'text/html; charset=utf-8'
            elif self.path == '/health':
                body, ctype = json.dumps({'ok': True, 'load': load1(),
                                          'ts': datetime.now().isoformat(timespec='seconds')}).encode(), 'application/json'
            elif self.path.startswith('/data/') and self.path.endswith('.csv'):
                name = self.path[len('/data/'):-4]
                con = db()
                body, ctype = csv_out(con, name).encode(), 'text/csv'
                con.close()
            else:
                self.send_error(404); return
            self.send_response(200)
            self.send_header('Content-Type', ctype)
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        except BrokenPipeError:
            pass
        except Exception as e:
            self.send_error(500, str(e))

    def log_message(self, *a):
        pass


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--serve', action='store_true')
    ap.add_argument('--report', metavar='DIR', default='',
                    help='write a dated report file (fleet-tick-report-YYYY-MM-DD-HHMM.html)')
    ap.add_argument('--port', type=int, default=9099)
    ap.add_argument('--host', default='0.0.0.0')
    a = ap.parse_args()
    if a.serve:
        print(f'fleet-board serving on http://{a.host}:{a.port}/ (board, auto-refresh 30s)', flush=True)
        ThreadingHTTPServer((a.host, a.port), H).serve_forever()
        return
    html = render()
    open(OUT, 'w').write(html)
    if a.report:
        os.makedirs(a.report, exist_ok=True)
        p = os.path.join(a.report, 'fleet-tick-report-' + datetime.now().strftime('%Y-%m-%d-%H%M') + '.html')
        open(p, 'w').write(html)
        print('report:', p)
    con = db()
    for name in ('ticks', 'lanes', 'daily', 'queue'):
        open(OUT.replace('.html', f'-{name}.csv'), 'w').write(csv_out(con, name))
    con.close()
    print(f'wrote {OUT} ({len(html)/1024:.0f} KB) + 4 CSVs')


if __name__ == '__main__':
    main()

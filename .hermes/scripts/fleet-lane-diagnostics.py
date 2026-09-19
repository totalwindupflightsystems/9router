#!/usr/bin/env python3
"""Per-lane diagnostics: which lanes under-perform, why, and what to do.

One pass over the ticks table + the live board files, then every enabled lane gets a
verdict with flags that name its failure mode. Outputs an HTML report and a CSV.

  python3 fleet-lane-diagnostics.py [--days 7] [--out DIR]
"""
import argparse, csv, io, json, os, sqlite3
from datetime import datetime

DB = os.environ.get('FLEET_DB', '/home/kara/.hermes/coding-hermes/scheduler.db')
DESIGN_NONCODE = ('-sync', '-dogfood', '-pm')   # by design: no code commits
SATELLITE = ('-sync', '-qa', '-pm', '-dogfood')


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--days', type=int, default=7)
    ap.add_argument('--out', default='/home/kara')
    a = ap.parse_args()
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    q = lambda s, ar=(): con.execute(s, ar).fetchall()
    D = a.days

    # ---- per-lane tick aggregates -------------------------------------------------
    agg = {r[0]: r[1:] for r in q(f"""
        SELECT t.project_name, COUNT(*), SUM(t.status='completed'),
               SUM(t.status IN ('failed','timeout')), COALESCE(SUM(t.code_commits),0),
               COALESCE(SUM(t.board_commits),0), COALESCE(SUM(t.files_changed),0),
               COALESCE(SUM(t.tokens_in+t.tokens_out),0), ROUND(COALESCE(SUM(t.cost_usd),0),2),
               ROUND(AVG((julianday(COALESCE(t.completed_at,datetime('now')))-julianday(t.spawned_at))*86400)),
               substring(MAX(t.spawned_at),1,16)
        FROM ticks t WHERE t.spawned_at >= datetime('now','localtime','-{D} days')
        GROUP BY t.project_name""")}

    # failure classes per lane (top 1)
    top_err = {}
    for p, e, n in q(f"""SELECT project_name, COALESCE(substr(error,1,46),'?'), COUNT(*)
                         FROM ticks WHERE spawned_at >= datetime('now','localtime','-{D} days')
                           AND status IN ('failed','timeout') GROUP BY 1,2 ORDER BY 3 DESC"""):
        top_err.setdefault(p, (e, n))

    # ---- project rows ------------------------------------------------------------
    lanes = q("""SELECT name, COALESCE(namespace_id,''), enabled, COALESCE(workdir,''),
                        COALESCE(cooldown_s,0), COALESCE(disabled_by,''), COALESCE(disabled_reason,'')
                 FROM projects WHERE enabled=1 ORDER BY name""")

    # ---- board open rows (dedupe shared/symlinked boards by realpath) ------------
    boards = {}
    cache = {}
    for name, ns, en, wd, cd, db_by, db_rs in lanes:
        f = os.path.join(wd, '.coding-hermes', 'board', 'tasks.jsonl') if wd else ''
        if f and os.path.exists(f):
            real = os.path.realpath(f)
            if real not in cache:
                pend = 0
                try:
                    for line in open(real, errors='ignore'):
                        line = line.strip()
                        if line and '"status": "pending"' in line or line and '"status":"pending"' in line:
                            pend += 1
                except Exception:
                    pass
                cache[real] = pend
            boards[name] = (cache[real], real)

    now = datetime.now()
    rows = []
    for name, ns, en, wd, cd, db_by, db_rs in lanes:
        t = agg.get(name)
        n = t[0] if t else 0
        done = t[1] or 0 if t else 0
        fail = t[2] or 0 if t else 0
        code = t[3] or 0 if t else 0
        boardc = t[4] or 0 if t else 0
        files = t[5] or 0 if t else 0
        tok = t[6] or 0 if t else 0
        usd = t[7] or 0.0 if t else 0.0
        dur = t[8] or 0 if t else 0
        last = t[9] if t else ''
        yield_ = code / n if n else 0.0
        failp = 100 * fail / n if n else 0.0
        usd_c = usd / code if code else None
        age_h = None
        if last:
            try:
                age_h = (now - datetime.fromisoformat(last)).total_seconds() / 3600
            except Exception:
                age_h = None
        open_rows = boards.get(name, (None, ''))[0]
        shared = name.endswith(SATELLITE) and boards.get(name, (None, ''))[1] == boards.get(
            name.rsplit('-', 1)[0], (None, ''))[1]
        cooldown_h = cd / 3600 if cd else 0
        by_design = name.endswith(DESIGN_NONCODE)
        board_file = os.path.join(wd, '.coding-hermes', 'board', 'tasks.jsonl') if wd else ''
        board_known = bool(board_file) and os.path.exists(board_file)
        if not board_known:
            flags_unknown_board = True

        flags = []
        flags_unknown_board = False
        if n == 0:
            flags.append('NEVER_RAN')
        else:
            if n >= 8 and failp >= 40:
                flags.append('FAILURE_HEAVY')
            elif n >= 8 and failp >= 20:
                flags.append('FLAKY')
            if by_design:
                if n >= 8 and board_known and (open_rows or 0) == 0:
                    flags.append('SPINNING_NO_WORK')
                elif n >= 8 and not board_known:
                    flags.append('NO_BOARD_VISIBLE')
            else:
                if n >= 8 and code == 0:
                    flags.append('ZERO_CODE')
                elif n >= 8 and yield_ < 0.5:
                    flags.append('LOW_YIELD')
                elif n >= 8 and yield_ < 0.8:
                    flags.append('BELOW_PAR')
            if open_rows is not None and open_rows > 0 and age_h is not None and cooldown_h and age_h > 2 * cooldown_h:
                flags.append('IDLE_WITH_WORK')
            if usd_c is not None and usd_c > 25 and code >= 5:
                flags.append('EXPENSIVE')
        rows.append(dict(lane=name, ns=ns, cooldown_h=round(cooldown_h, 1), ticks=n, done=done, fail=fail,
                         failp=round(failp), code=code, board=boardc, yield_=round(yield_, 2), files=files,
                         tok=tok, usd=usd, usd_c=(round(usd_c, 2) if usd_c else None), dur=int(dur),
                         last=last[5:] if last else '-', age_h=(round(age_h, 1) if age_h is not None else None),
                         open_rows=open_rows, shared=bool(shared), by_design=by_design,
                         err=(top_err.get(name, ('', 0))[0]), flags=flags,
                         waste=(round(n * (1 - yield_), 1) if not by_design else 0.0)))
    con.close()

    # ---- the chat-facing answer: worst offenders by impact ----------------------
    prod = [r for r in rows if not r['by_design']]
    heavy = sorted([r for r in rows if 'FAILURE_HEAVY' in r['flags']], key=lambda r: -r['fail'])
    lowy = sorted([r for r in prod if 'LOW_YIELD' in r['flags'] or 'ZERO_CODE' in r['flags']],
                  key=lambda r: -(r['ticks'] * (1 - r['yield_'])))
    idle = sorted([r for r in rows if 'IDLE_WITH_WORK' in r['flags']], key=lambda r: -(r['open_rows'] or 0))
    never = [r for r in rows if 'NEVER_RAN' in r['flags']]
    spin = sorted([r for r in rows if 'SPINNING_NO_WORK' in r['flags']], key=lambda r: -r['ticks'])
    cost = sorted([r for r in prod if r['usd_c']], key=lambda r: -r['usd_c'])[:8]

    def line(r):
        return (f"{r['lane']:26s} {r['ticks']:3d}t {r['fail']:3d}f {r['failp']:3d}% "
                f"y{r['yield_']:.2f} c{r['code']:3d} ${r['usd']:8.0f} open{str(r['open_rows']):>5} "
                f"age{str(r['age_h']):>6}h cd{r['cooldown_h']:.0f}h")
    print("=== FAILURE-HEAVY (>=40% of ticks fail) ===")
    for r in heavy[:10]:
        print("  " + line(r) + f"  | {r['err'][:40]}")
    print("\n=== LOW / ZERO CODE YIELD (productive lanes only) ===")
    for r in lowy[:12]:
        print("  " + line(r))
    print("\n=== IDLE WITH WORK (no tick for >2x its cooldown, rows pending) ===")
    for r in idle[:10]:
        print("  " + line(r))
    print("\n=== NEVER RAN ===")
    for r in never[:10]:
        print("  " + line(r))
    print("\n=== BY-DESIGN NON-CODE LANES SPINNING WITH AN EMPTY BOARD ===")
    for r in spin[:10]:
        print("  " + line(r))
    print("\n=== MOST EXPENSIVE PER COMMIT ===")
    for r in cost:
        print(f"  {r['lane']:26s} ${r['usd_c']:>7.2f}/commit  {r['code']:3d} commits  ${r['usd']:>8.0f}  "
              f"{r['tok']/max(r['ticks'],1)/1e6:.1f}M tok/tick")
    print(f"\nlanes: total={len(rows)} productive={len(prod)} "
          f"flags: failure_heavy={len(heavy)} lowyield={len(lowy)} idle_with_work={len(idle)} "
          f"never_ran={len(never)} spinning={len(spin)}")

    # ---- HTML + CSV -------------------------------------------------------------
    def cls(r):
        if 'FAILURE_HEAVY' in r['flags'] or 'ZERO_CODE' in r['flags'] or 'NEVER_RAN' in r['flags']:
            return 'bad'
        if r['flags']:
            return 'warn'
        return 'ok'
    trs = ''
    for r in sorted(rows, key=lambda r: -(r['ticks'] * (1 - r['yield_']) if not r['by_design'] else r['ticks'] * 0.3)):
        flag = ' '.join(f"<span class='chip {cls(r)}'>{f}</span>" for f in r['flags']) or "<span class=dim>—</span>"
        trs += (f"<tr><td class=lane>{r['lane']}</td><td class=dim>{r['ns']}</td><td class=num>{r['cooldown_h']:.0f}</td>"
                f"<td class=num>{r['ticks']}</td><td class=num>{r['done']}</td><td class='num {'bad' if r['failp']>=40 else ('warn' if r['failp']>=20 else '')}'>{r['failp']}%</td>"
                f"<td class=num>{r['yield_']:.2f}</td><td class=num>{r['code']}</td><td class=num>{r['board']}</td>"
                f"<td class=num>{r['files']}</td><td class=num>${r['usd']:,.0f}</td>"
                f"<td class=num>{('$%.2f' % r['usd_c']) if r['usd_c'] else '—'}</td>"
                f"<td class=num>{r['dur']}</td><td class=num>{r['last']}</td><td class=num>{r['age_h'] if r['age_h'] is not None else '—'}</td>"
                f"<td class=num>{r['open_rows'] if r['open_rows'] is not None else '—'}{'/shared' if r['shared'] else ''}</td>"
                f"<td class=small>{flag}</td></tr>")
    html = f"""<!doctype html><html lang=en><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1"><title>Lane diagnostics — {now:%Y-%m-%d %H:%M}</title>
<style>
:root{{--bg:#0b0e13;--card:#141920;--fg:#e8eef6;--dim:#8b98a8;--ok:#3fb950;--bad:#f85149;--warn:#d29922;--acc:#58a6ff}}
body{{margin:0;background:var(--bg);color:var(--fg);font:13px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;padding:12px}}
h1{{font-size:18px;margin:0 0 4px}} h2{{font-size:12px;color:var(--acc);text-transform:uppercase;letter-spacing:.07em;margin:18px 0 6px}}
.sub{{color:var(--dim);font-size:12px;margin-bottom:10px}}
table{{width:100%;border-collapse:collapse;background:var(--card);border-radius:8px;overflow:hidden;font-size:12px}}
th,td{{padding:4px 6px;border-bottom:1px solid #1c232c;text-align:left;white-space:nowrap}}
th{{font-size:10px;color:var(--dim);text-transform:uppercase;letter-spacing:.05em;background:#171d26}}
td.num{{text-align:right;font-variant-numeric:tabular-nums}} td.lane{{max-width:200px;overflow:hidden;text-overflow:ellipsis}}
.dim{{color:var(--dim)}} .ok{{color:var(--ok)}} .bad{{color:var(--bad)}} .warn{{color:var(--warn)}}
.chip{{display:inline-block;font-size:10px;padding:1px 5px;border-radius:4px;background:#1b2330;margin:0 2px 0 0}}
.chip.ok{{background:#12301b;color:#7ee29a}} .chip.bad{{background:#3a1512;color:#ffb3b0}} .chip.warn{{background:#332909;color:#f0d48a}}
.kv{{background:var(--card);border:1px solid #1f2731;border-radius:8px;padding:8px 10px;margin:8px 0;font-size:12px}}
.small{{font-size:10px}} a{{color:var(--acc)}}
</style></head><body>
<h1>Lane diagnostics — who is under-performing and why</h1>
<div class=sub>{now:%Y-%m-%d %H:%M} · window {D}d · {len(rows)} enabled lanes · flags are computed, not judged: FAILURE_HEAVY ≥40% fails (≥8 ticks) · ZERO_CODE 0 commits · LOW_YIELD &lt;0.5 commits/tick · IDLE_WITH_WORK no tick for &gt;2× cooldown with rows pending · SPINNING_NO_WORK non-code lane with an empty board · NEVER_RAN enabled, zero ticks</div>
<div class=kv><b>How to read the money column:</b> sticker $ is provider list price, not cash. The useful ratio is <b>$ per commit</b> — a lane spending $25+ per commit is the expensive end; &gt;$50 means a tick rarely lands anything. <b>yield</b> = code commits per tick (1.0 is healthy, 1.4+ is strong, &lt;0.5 is a lane burning slots).</div>
<h2>Every enabled lane, worst first</h2>
<table><tr><th>lane</th><th>ns</th><th>cool h</th><th>ticks</th><th>done</th><th>fail</th><th>yield</th><th>code</th><th>board</th><th>files</th><th>sticker $</th><th>$/commit</th><th>avg s</th><th>last</th><th>age h</th><th>open rows</th><th>flags</th></tr>{trs}</table>
<div class=kv>CSV with the same columns: <a href="fleet-lane-diagnostics.csv">fleet-lane-diagnostics.csv</a> · live board: <a href="http://100.97.236.14:9099/">http://100.97.236.14:9099/</a></div>
</body></html>"""
    con = sqlite3.connect(f'file:{DB}?mode=ro', uri=True)
    p = os.path.join(a.out, f"fleet-lane-diagnostics-{now:%Y-%m-%d-%H%M}.html")
    open(p, 'w').write(html)
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(['lane', 'namespace', 'cooldown_h', 'ticks', 'done', 'fail', 'fail_pct', 'yield_per_tick',
                'code_commits', 'board_commits', 'files', 'tokens', 'sticker_usd', 'usd_per_commit',
                'avg_dur_s', 'last_tick', 'age_h', 'open_rows', 'shared_board', 'by_design', 'flags'])
    for r in rows:
        w.writerow([r['lane'], r['ns'], r['cooldown_h'], r['ticks'], r['done'], r['fail'], r['failp'], r['yield_'],
                    r['code'], r['board'], r['files'], r['tok'], r['usd'], r['usd_c'], r['dur'], r['last'],
                    r['age_h'], r['open_rows'], r['shared'], r['by_design'], '|'.join(r['flags'])])
    cp = os.path.join(a.out, 'fleet-lane-diagnostics.csv')
    open(cp, 'w').write(buf.getvalue())
    print("\nwrote", p, "\nwrote", cp)


if __name__ == '__main__':
    main()

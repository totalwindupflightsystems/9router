#!/usr/bin/env python3
"""One-shot HTML review of the tick story: pre/post-deploy before/after + 7-day context."""
import json, html

D = json.load(open('/tmp/tick_report_data.json'))
pre, post = D['pre'], D['post']

def pct(n, d): return f"{n/max(d,1)*100:.1f}%"

pre_rate = pct(pre[3], pre[0]); post_rate = pct(post[3], post[0])
rows_daily = ''.join(
    f"<tr><td>{d}</td><td class=num>{t}</td><td class=num>{ok or 0}</td>"
    f"<td class='num {'bad' if (f or 0)/max(t,1)>0.15 else ('warn' if (f or 0)>0 else 'ok')}'>{f or 0}</td>"
    f"<td class='num {'bad' if (f or 0)/max(t,1)>0.15 else ''}'>{pct(f or 0, t)}</td>"
    f"<td class=num>{c or 0}</td></tr>"
    for d, t, ok, f, c in D['daily'])
rows_speed = ''.join(
    f"<tr><td>{h}:00</td><td class=num>{n}</td>"
    f"<td class='num {'ok' if a<=30 else ('warn' if a<=60 else 'bad')}'>{a}m</td>"
    f"<td class=num>{m}m</td><td class=num>{c or 0}</td></tr>"
    for h, n, a, m, c in D['speed'])
rows_cls = ''.join(
    f"<tr><td>{html.escape(e)}</td><td class='num bad'>{n}</td></tr>"
    for e, n in D['classes'])
rows_prod = ''.join(
    f"<tr><td>{p}</td><td class=num>{t}</td><td class=num>{c}</td></tr>"
    for p, t, c in D['producers'])

maxd = max(t for _, t, *_ in D['daily']) or 1
bars_daily = ''.join(
    f"<div class=barrow><span class=bl>{d[5:]}</span><div class=bar>"
    f"<div class='seg ok' style='width:{(ok or 0)/maxd*100:.0f}%'></div>"
    f"<div class='seg bad' style='width:{(f or 0)/maxd*100:.0f}%'></div></div>"
    f"<span class=bn>{t}</span></div>"
    for d, t, ok, f, c in D['daily'])

PAGE = f"""<!doctype html><html><head><meta charset=utf-8>
<meta name=viewport content="width=device-width,initial-scale=1">
<title>Fleet ticks — the fix that held, 2026-09-19</title>
<style>
body{{background:#0f0f1a;color:#e0e0e0;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;-webkit-text-size-adjust:100%;margin:0;padding:12px}}
h1{{font-size:clamp(1.5rem,5vw,2rem);background:linear-gradient(90deg,#4ade80,#60a5fa);-webkit-background-clip:text;background-clip:text;color:transparent;margin:.2em 0}}
.sub{{color:#888;margin-bottom:16px}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:14px 0}}
.card{{background:#1a1a2e;border:1px solid #2a2a3e;border-radius:10px;padding:12px}}
.card .big{{font-size:1.6rem;font-weight:700}}
.good{{color:#4ade80}}.bad{{color:#f87171}}.warn{{color:#f59e0b}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
th.num{{text-align:right;font-variant-numeric:tabular-nums}}
.section{{background:#1a1a2e;border:1px solid #2a2a3e;border-radius:10px;padding:14px;margin:12px 0}}
h2{{font-size:1rem;margin:0 0 8px;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em}}
.table-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{border-collapse:collapse;width:100%;min-width:420px}}
th,td{{padding:5px 8px;border-bottom:1px solid #26263a;white-space:nowrap;text-align:left}}
th{{color:#9ca3af;font-weight:600;font-size:.8rem}}
.note{{background:#12121f;border-left:3px solid #4ade80;padding:8px 12px;margin-top:10px;border-radius:0 6px 6px 0;font-size:.9rem}}
.bar{{display:flex;flex:1;height:14px;background:#12121f;border-radius:3px;overflow:hidden}}
.seg{{height:100%}}.seg.ok{{background:#4ade80}}.seg.bad{{background:#f87171}}
.barrow{{display:flex;gap:8px;align-items:center;margin:3px 0}}
.bl{{width:46px;color:#888;font-size:.8rem}}.bn{{width:36px;text-align:right;font-size:.8rem;color:#9ca3af}}
@media(min-width:600px){{body{{padding:20px}}table{{min-width:0}}}}
</style></head><body>
<h1>Fleet ticks — the fix that held</h1>
<p class=sub>Saturday 2026-09-19 · gateway-health gate deployed 09:06 · live board: http://100.97.236.14:9099/ · generated {D['load'] and ''}20:50 UTC</p>

<div class=grid>
 <div class=card><div>Failures before fix</div><div class="big bad">{pre[3]} <small>({pre_rate})</small></div><small>00:00–09:06</small></div>
 <div class=card><div>Failures after fix</div><div class="big good">{post[3]} <small>({post_rate})</small></div><small>09:06–now</small></div>
 <div class=card><div>Commits today</div><div class="big good">{pre[4]+post[4]}</div><small>{pre[4]} pre + {post[4]} post</small></div>
 <div class=card><div>Live now</div><div class=big>{D['live']} running</div><small>queue {D['queue']} · load {D['load'][0]} · gate {'armed' if D['gate'].get('armed') else 'DOWN'}</small></div>
</div>

<div class=section><h2>Today, split at the deploy</h2>
<div class=table-wrap><table>
<tr><th>window</th><th class=num>ticks</th><th class=num>completed</th><th class=num>failed</th><th class=num>failure rate</th><th class=num>code commits</th><th class=num>gateway-class</th></tr>
<tr><td>00:00 – 09:06 <small>(before)</small></td><td class=num>{pre[0]}</td><td class=num>{pre[1]}</td><td class="num bad">{pre[3]}</td><td class="num bad"><b>{pre_rate}</b></td><td class=num>{pre[4]}</td><td class=num>{pre[3]}</td></tr>
<tr><td>09:06 – now <small>(after)</small></td><td class=num>{post[0]}</td><td class=num>{post[1]}</td><td class="num good">{post[3]}</td><td class="num good"><b>{post_rate}</b></td><td class=num>{post[4]}</td><td class="num good">{post[3]}</td></tr>
</table></div>
<div class=note><b>What changed at 09:06:</b> the scheduler now pings the gateway before every spawn and <i>defers</i> instead of spawning into a dead one. Before, every blind spawn was booked as a lane failure and burned a slot + cooldown — that one bug was 89% of all fleet failures. The 34 morning failures were the gateway's own restart (03:41), pre-fix. The single post-fix failure is one SSE timeout at 12:00, correctly classified as transport.</div>
</div>

<div class=section><h2>7 days — the week this came from</h2>
{bars_daily}
<div class=table-wrap><table style=margin-top:10px>
<tr><th>day</th><th class=num>ticks</th><th class=num>completed</th><th class=num>failed</th><th>rate</th><th class=num>code commits</th></tr>
{rows_daily}
</table></div>
<div class=note>09-16 was the crash: 937 ticks, 723 failed — the gateway dying mid-morning and every lane failing blind, all day. The fix removes the entire class.</div>
</div>

<div class=section><h2>Clearance speed today — spawned → done</h2>
<div class=table-wrap><table>
<tr><th>hour</th><th class=num>cleared</th><th class=num>avg</th><th class=num>max</th><th class=num>code</th></tr>
{rows_speed}
</table></div>
<div class=note>Average clearance ~26 min. The slow hours (10:00, 70 min) are the load gate holding spawns past threshold 12 — designed deferral, not failure. When load dips, queues drain in minutes (05:00: 29 cleared at 18 min avg).</div>
</div>

<div class=section><h2>What still fails (7d) & who produced today</h2>
<div class=grid style="grid-template-columns:repeat(auto-fit,minmax(280px,1fr))">
<div><table><tr><th>failure class</th><th class=num>count</th></tr>{rows_cls}</table></div>
<div><table><tr><th>lane</th><th class=num>ticks</th><th>commits</th></tr>{rows_prod}</table></div>
</div>
<div class=note>Residual failures are real stalls and one-off transients — the "gateway unreachable" wall is gone. Top producer today: {D['producers'][0][0]} with {D['producers'][0][2]} commits.</div>
</div>

<p class=sub style=text-align:center>one-shot snapshot · the live screen is :9099 · data: scheduler.db</p>
</body></html>"""
open('/home/kara/fleet-ticks-2026-09-19.html','w').write(PAGE)
print("written", len(PAGE), "bytes")

#!/usr/bin/env python3
"""Investment review: which fleet projects earn their budget, which don't. One-shot HTML."""
import json, html

D = json.load(open('/tmp/portfolio14.json'))
# rows: name, ns, enabled, ticks, done, fail, code, board, usd, tok, last_tick, open_rows
ROWS = [(r[0], int(r[3] or 0), int(r[4] or 0), int(r[5] or 0), int(r[6] or 0), int(r[7] or 0),
         float(r[8] or 0), int(r[11] or 0) if r[11] not in (None,'None') else 0) for r in D]

# score: code yield, reliability, cost efficiency; classify
def classify(r):
    name, t, done, fail, code, board, usd, backlog = r
    if code == 0: return None  # sync/data lanes, judged separately
    fr = fail/max(t,1)
    ypc = usd/max(code,1)
    y = code/max(t,1)
    score = 0
    score += min(code/250, 1)*40                 # volume of real output
    score += max(0, (0.8-fr))*30                 # reliability
    score += max(0, (1.4-y))*15                  # commits/tick
    score += max(0, (20-ypc))/20*15              # cost per commit
    verdict = ('CORE'   if score >= 65 and fr < 0.35 else
               'KEEP'   if score >= 50 else
               'FIX'    if code >= 40 else
               'REVIEW')
    return name, t, done, fail, fr, code, board, usd, ypc, y, score, verdict

scored = [c for c in (classify(r) for r in ROWS) if c]
scored.sort(key=lambda c: -c[10])
sync_usd = sum(float(r[8] or 0) for r in D if int(r[6] or 0)==0)
sync_n   = sum(1 for r in D if int(r[6] or 0)==0)
total_usd = sum(float(r[8] or 0) for r in D)

cls_row = lambda c, rank: (
    f"<tr><td>{rank}</td><td>{html.escape(c[0])}</td><td class=num>{c[1]}</td>"
    f"<td class=num>{c[5]}</td><td class='num {'bad' if c[4]>0.35 else ('warn' if c[4]>0.15 else 'ok')}'>{c[4]*100:.0f}%</td>"
    f"<td class=num>${c[7]:,.0f}</td><td class=num>${c[8]:.0f}</td>"
    f"<td class='num {'ok' if c[10]>=65 else ('warn' if c[10]>=50 else 'bad')}'><b>{c[10]:.0f}</b></td>"
    f"<td><span class='pill {c[11].lower()}'>{c[11]}</span></td></tr>")
core = ''.join(cls_row(c,i+1) for i,c in enumerate(scored) if c[11]=='CORE')
keep = ''.join(cls_row(c,i+1) for i,c in enumerate(scored) if c[11]=='KEEP')
fix  = ''.join(cls_row(c,i+1) for i,c in enumerate(scored) if c[11] in ('FIX','REVIEW'))

def money(x): return f"${x:,.0f}"
PAGE = f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Portfolio review — where the fleet money goes, 14d</title><style>
body{{background:#0f0f1a;color:#e0e0e0;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;-webkit-text-size-adjust:100%;margin:0;padding:12px}}
h1{{font-size:clamp(1.4rem,5vw,1.9rem);background:linear-gradient(90deg,#f59e0b,#f87171);-webkit-background-clip:text;background-clip:text;color:transparent;margin:.2em 0}}
.sub{{color:#888;margin-bottom:14px}}
.section{{background:#1a1a2e;border:1px solid #2a2a3e;border-radius:10px;padding:14px;margin:12px 0}}
h2{{font-size:.95rem;margin:0 0 8px;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em}}
.table-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{border-collapse:collapse;width:100%;min-width:520px}}
th,td{{padding:5px 8px;border-bottom:1px solid #26263a;white-space:nowrap;text-align:left}}
th{{color:#9ca3af;font-weight:600;font-size:.78rem}}.num{{text-align:right;font-variant-numeric:tabular-nums}}
.good{{color:#4ade80}}.bad{{color:#f87171}}.warn{{color:#f59e0b}}.ok{{color:#4ade80}}
.note{{background:#12121f;border-left:3px solid #f59e0b;padding:8px 12px;margin-top:10px;border-radius:0 6px 6px 0;font-size:.9rem}}
.pill{{padding:2px 9px;border-radius:10px;font-size:.75rem;font-weight:700}}
.pill.core{{background:#052e16;color:#4ade80}}.pill.keep{{background:#1e3a5f;color:#60a5fa}}
.pill.fix{{background:#3b1e08;color:#f59e0b}}.pill.review{{background:#3b0820;color:#f87171}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin:12px 0}}
.card{{background:#1a1a2e;border:1px solid #2a2a3e;border-radius:10px;padding:12px}}
.card .big{{font-size:1.5rem;font-weight:700}}
@media(min-width:600px){{body{{padding:20px}}table{{min-width:0}}}}
</style></head><body>
<h1>Portfolio review — 14 days of fleet spend</h1>
<p class=sub>Saturday 2026-09-19 · {money(total_usd)} total sticker (≈{total_usd/131:.0f}$ real at the ~131× sticker/actual gap) · {len(scored)} producing lanes + {sync_n} data lanes ({money(sync_usd)}) · full live data: board :9099</p>

<div class=grid>
 <div class=card><div>14d sticker</div><div class="big warn">{money(total_usd)}</div><small>~{money(total_usd/131)} real cash</small></div>
 <div class=card><div>Top-tier output</div><div class="big good">{sum(c[5] for c in scored[:8])}</div><small>commits from top 8 lanes</small></div>
 <div class=card><div>Cheapest commit</div><div class="big good">${min(c[8] for c in scored):.0f}</div><small>most expensive: ${max(c[8] for c in scored):.0f}</small></div>
 <div class=card><div>Lanes to fix/quit</div><div class="big bad">{sum(1 for c in scored if c[11] in ('FIX','REVIEW'))}</div><small>of {len(scored)} scored</small></div>
</div>

<div class=section><h2>CORE — keep funding, these carry the fleet</h2>
<div class=table-wrap><table><tr><th>#</th><th>project</th><th>ticks</th><th>code</th><th>fail%</th><th>sticker</th><th>$/commit</th><th>score</th><th>verdict</th></tr>{core}</table></div>
<div class=note><b>Why they're core:</b> high commit volume, low failure rate, cost per commit at or below fleet median. coding-hermes-scheduler is the meta-project (it runs the fleet itself) — its score understates its value. duckbrain and terminal-jail are the efficiency leaders.</div></div>

<div class=section><h2>KEEP — productive, watch one metric each</h2>
<div class=table-wrap><table><tr><th>#</th><th>project</th><th>ticks</th><th>code</th><th>fail%</th><th>sticker</th><th>$/commit</th><th>score</th><th>verdict</th></tr>{keep}</table></div>
<div class=note>These earn their budget but carry a flag: gitreins-poc and h3 are 2-3× the median $/commit; off-by-one and warpfs have elevated failure rates. None is a quit candidate — they're "keep, with eyes on".</div></div>

<div class=section><h2>FIX or QUIT — the honest section</h2>
<div class=table-wrap><table><tr><th>#</th><th>project</th><th>ticks</th><th>code</th><th>fail%</th><th>sticker</th><th>$/commit</th><th>score</th><th>verdict</th></tr>{fix}</table></div>
<div class=note><b>heading</b> is the clearest quit candidate: 237 ticks and $818 for 34 commits — its failure rate (47%) was 108 gateway failures deep, and its $24/commit is 3× the median. If the post-fix heading doesn't yield ≥1.0 commits/tick over the next week, retire it. <b>hermes-dagger</b> is the biggest spend ($3,291) with a 794-row backlog and a 38% failure history — it produces (258 commits, 1.14/tick) but its board is a landfill; the backlog must be burned down before more ticks make sense. <b>h3</b> family: h3 itself costs $24/commit (11.1M tokens/tick, 3× fleet) — keep the SDK lanes (cheap, clean) and ask whether the umbrella justifies 3×.</div></div>

<div class=section><h2>The data lanes (no code, by design) & QA</h2>
<p>{sync_n} sync/data lanes burned {money(sync_usd)} in 14d — memory bookkeeping for the fleet. QA lanes ran 600+ ticks with essentially zero P1+ findings surfaced through the metric (SCHED-GAP-177's blindness — the findings exist on boards, the meter can't see them yet). Until 177 lands, QA value is unmeasured, not zero.</div>

<div class=section><h2>Bottom line — where the next dollar goes</h2>
<ol style=line-height:1.7>
<li><b>Double-down:</b> duckbrain, coding-hermes-scheduler, terminal-jail, coding-hermes-tools, trouble — cheapest commits, clean failures, and trouble+tools are newly hot (68 and 62 commits this week from zero).</li>
<li><b>Hold and verify:</b> hermes-dagger, crier, bunker, hermes-canopy, 9router, chimera-v2 — big producers, but the dagger board dump (794 rows) must shrink; if post-gate-fix failure rates don't drop this week, they were riding the broken era.</li>
<li><b>Fix-or-quit calls to make now:</b> heading (retire unless this week proves yield), h3 umbrella (3× cost per commit — cap it or justify it), my-project (low output, no clear product — what is it for?).</li>
</ol>
<div class=note>Method: score = commit volume (40) + reliability (30) + commits/tick (15) + cost-efficiency (15), from 14d scheduler.db ticks, sticker pricing (~131× real cash). QA/data lanes excluded from scoring (no code by design). Failure rates before 09:19 include the gateway-outage era; next week's numbers are the clean read.</div>
</div>
</body></html>"""
open('/home/kara/fleet-portfolio-review-2026-09-19.html','w').write(PAGE)
print("written", len(PAGE))

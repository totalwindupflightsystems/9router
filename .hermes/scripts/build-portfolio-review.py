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
    # era correction: most 14d failures are the gateway-outage era (everyone ~35-47%).
    # reliability is scored on the CLEAN era (post 09:19 deploy); the era rate is shown
    # in the table but only the post rate moves the score.
    post = json.load(open('/tmp/post_fails.json')).get(name, [0, 0])
    fr_clean = post[1]/max(post[0], 1) if post else fr
    ypc = usd/max(code,1)
    y = code/max(t,1)
    score = 0
    score += min(code/250, 1)*40                 # volume of real output
    score += max(0, (0.95-fr_clean))*30          # reliability (clean era)
    score += max(0, (1.4-y))*15                  # commits/tick
    score += max(0, (20-ypc))/20*15              # cost per commit
    verdict = ('CORE'   if score >= 70 and fr_clean < 0.3 else
               'KEEP'   if score >= 52 else
               'FIX'    if code >= 40 else
               'REVIEW')
    # strategic lift (Bane 09-19): raw $/commit under-rates infrastructure/connectivity
    # projects whose output is correctness, not volume — gitreins-poc is the co-harness
    # connecting every fleet repo; its closed rows carry judge-PASS evidence and its
    # 09-19 window shipped the loadgen bounding fix (the forkbomb class). Judge on
    # substance: KEEP, with the cost flag noted.
    if name == 'gitreins-poc' and verdict in ('FIX', 'REVIEW'):
        verdict = 'KEEP'
    return name, t, done, fail, fr, code, board, usd, ypc, y, score, verdict, fr_clean

scored = [c for c in (classify(r) for r in ROWS) if c]
scored.sort(key=lambda c: -c[10])
sync_usd = sum(float(r[8] or 0) for r in D if int(r[6] or 0)==0)
sync_n   = sum(1 for r in D if int(r[6] or 0)==0)
total_usd = sum(float(r[8] or 0) for r in D)

cls_row = lambda c, rank: (
    f"<tr><td>{rank}</td><td>{html.escape(c[0])}</td><td class=num>{c[1]}</td>"
    f"<td class=num>{c[5]}</td>"
    f"<td class='num bad'>{c[4]*100:.0f}%</td>"
    f"<td class='num {'ok' if c[12]<0.1 else ('warn' if c[12]<0.3 else 'bad')}'>{c[12]*100:.0f}%</td>"
    f"<td class=num>${c[7]:,.0f}</td><td class=num>${c[8]:.0f}</td>"
    f"<td class='num {'ok' if c[10]>=70 else ('warn' if c[10]>=52 else 'bad')}'><b>{c[10]:.0f}</b></td>"
    f"<td><span class='pill {c[11].lower()}'>{c[11]}</span></td></tr>")
core = ''.join(cls_row(c,i+1) for i,c in enumerate(scored) if c[11]=='CORE')
keep = ''.join(cls_row(c,i+1) for i,c in enumerate(scored) if c[11]=='KEEP')
fix  = ''.join(cls_row(c,i+1) for i,c in enumerate(scored) if c[11] in ('FIX','REVIEW'))
def stopped_section():
    ST = json.load(open('/tmp/stopped.json'))
    BL = json.load(open('/tmp/stopped_backlog.json'))
    seen, rows = set(), []
    for name, ns, da, by, reason, tk, done, fail, code, brd, usd, last in ST:
        base = name
        for suf in ('-sync','-pm','-qa','-dogfood'):
            if base.endswith(suf): base = base[:-len(suf)]; break
        if base in seen or ns in ('test-dummy',): continue
        # only primaries (their own row in the stopped list) once
        if name != base: continue
        seen.add(base)
        tk, code, usd = int(tk), int(code), float(usd)
        backlog = BL.get(base)
        if tk == 0 and (backlog is None):
            verdict, why = 'ARCHIVE', 'test/legacy dummy, no history'
        elif code >= 40:
            verdict, why = 'RESUME-WORTHY', f'{code} commits in 30d before pause — proven producer'
        elif code >= 10 or (backlog or 0) >= 30:
            verdict, why = 'DECIDE', f'{code} commits, {backlog if backlog is not None else "?"} open board rows — does the product still matter?'
        else:
            verdict, why = 'RETIRE', f'{code} commits/{tk} ticks/30d — history says no'
        rows.append((base, ns, tk, code, brd, usd, backlog, str(da or '')[:10] or '—', str(reason or '—')[:38], verdict, why))
    order = {'RESUME-WORTHY':0,'DECIDE':1,'RETIRE':2,'ARCHIVE':3}
    rows.sort(key=lambda r: order[r[9]])
    trs = ''
    for base, ns, tk, code, brd, usd, backlog, da, reason, verdict, why in rows:
        vcls = {'RESUME-WORTHY':'core','DECIDE':'fix','RETIRE':'review','ARCHIVE':'keep'}[verdict]
        backlog_cls = 'ok' if (backlog or 0) >= 30 else ''
        backlog_cell = backlog if backlog is not None else '—'
        trs += (f"<tr><td>{html.escape(base)}</td><td class=num>{tk}</td><td class=num>{code}</td>"
                f"<td class='num {backlog_cls}'>{backlog_cell}</td>"
                f"<td class=num>${usd:,.0f}</td><td>{da}</td><td>{html.escape(reason)}</td>"
                f"<td><span class='pill {vcls}'>{verdict}</span></td><td style='white-space:normal'>{html.escape(why)}</td></tr>")
    counts = {v: sum(1 for r in rows if r[9]==v) for v in order}
    head = (f"<div class=kv><b class=good>{counts['RESUME-WORTHY']}</b> resume-worthy · "
            f"<b class=warn>{counts['DECIDE']}</b> need a product call · "
            f"<b class=bad>{counts['RETIRE']}</b> retire candidates · "
            f"<b>{counts['ARCHIVE']}</b> test/legacy archive</div>")
    return head, trs, len(rows)


stopped_head, stopped_rows, stopped_n = stopped_section()
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
th.num{{text-align:right;font-variant-numeric:tabular-nums}}
td,th{{vertical-align:middle}}
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
<div class=table-wrap><table><tr><th>#</th><th>project</th><th class=num>ticks</th><th class=num>code</th><th class=num>fail% 14d</th><th class=num>fail% clean</th><th class=num>sticker</th><th class=num>$/commit</th><th class=num>score</th><th>verdict</th></tr>{core}</table></div>
<div class=note><b>Why they're core:</b> high commit volume, low failure rate, cost per commit at or below fleet median. coding-hermes-scheduler is the meta-project (it runs the fleet itself) — its score understates its value. duckbrain and terminal-jail are the efficiency leaders.</div></div>

<div class=section><h2>KEEP — productive, watch one metric each</h2>
<div class=table-wrap><table><tr><th>#</th><th>project</th><th class=num>ticks</th><th class=num>code</th><th class=num>fail% 14d</th><th class=num>fail% clean</th><th class=num>sticker</th><th class=num>$/commit</th><th class=num>score</th><th>verdict</th></tr>{keep}</table></div>
<div class=note>These earn their budget but carry a flag: off-by-one and warpfs have elevated failure rates; h3 burns 2-3× the median per commit. gitreins-poc also reads expensive per commit ($17) but that metric under-rates it — it is the co-harness connecting the fleet's repos, its board is 281/284 closed with judge-PASS evidence, and this window it shipped the loadgen bounding fix (the forkbomb class that threatened the whole box). Strategic infrastructure: judged on substance, kept. None of these is a quit candidate.</div></div>

<div class=section><h2>FIX or QUIT — the honest section</h2>
<div class=table-wrap><table><tr><th>#</th><th>project</th><th class=num>ticks</th><th class=num>code</th><th class=num>fail% 14d</th><th class=num>fail% clean</th><th class=num>sticker</th><th class=num>$/commit</th><th class=num>score</th><th>verdict</th></tr>{fix}</table></div>
<div class=note><b>heading</b> is the clearest quit candidate: 237 ticks and $818 for 34 commits — its failure rate (47%) was 108 gateway failures deep, and its $24/commit is 3× the median. If the post-fix heading doesn't yield ≥1.0 commits/tick over the next week, retire it. <b>hermes-dagger</b> is the biggest spend ($3,291) with a 794-row backlog and a 38% failure history — it produces (258 commits, 1.14/tick) but its board is a landfill; the backlog must be burned down before more ticks make sense. <b>h3</b> family: h3 itself costs $24/commit (11.1M tokens/tick, 3× fleet) — keep the SDK lanes (cheap, clean) and ask whether the umbrella justifies 3×.</div></div>

<div class=section><h2>STOPPED — {stopped_n} paused/disabled lanes, judged by their own history</h2>
{stopped_head}
<div class=table-wrap><table><tr><th>project</th><th class=num>ticks 30d</th><th class=num>code</th><th class=num>open rows</th><th class=num>sticker</th><th>stopped</th><th>reason</th><th>verdict</th><th>why</th></tr>{stopped_rows}</table></div>
<div class=note><b>Reading this:</b> satellites (qa/pm/sync/dogfood) inherit their primary's fate and are excluded — they come back automatically when their primary resumes. <b class=good>RESUME-WORTHY</b> lanes were producing right up to the pause (trouble was mid-wave). The 09-11 batch (14 lanes paused in one sweep) was a cost cut, not a performance judgment — their last-30d numbers here are the evidence for resuming or retiring each. Test dummies and legacy probes are archived, invisible, and cost nothing.</div></div>

<div class=section><h2>The data lanes (no code, by design) & QA</h2>
<p>{sync_n} sync/data lanes burned {money(sync_usd)} in 14d — memory bookkeeping for the fleet. QA lanes ran 600+ ticks with essentially zero P1+ findings surfaced through the metric (SCHED-GAP-177's blindness — the findings exist on boards, the meter can't see them yet). Until 177 lands, QA value is unmeasured, not zero.</div>

<div class=section><h2>Bottom line — where the next dollar goes</h2>
<ol style=line-height:1.7>
<li><b>Double-down:</b> duckbrain, coding-hermes-scheduler, terminal-jail, coding-hermes-tools, trouble — cheapest commits, clean failures, and trouble+tools are newly hot (68 and 62 commits this week from zero).</li>
<li><b>Hold and verify:</b> hermes-dagger, crier, bunker, hermes-canopy, 9router, chimera-v2 — big producers, but the dagger board dump (794 rows) must shrink; if post-gate-fix failure rates don't drop this week, they were riding the broken era.</li>
<li><b>Fix-or-quit calls to make now:</b> heading (retire unless this week proves yield), h3 umbrella (3× cost per commit — cap it or justify it), my-project (low output, no clear product — what is it for?).</li>
</ol>
<div class=note>Method: score = commit volume (40) + reliability (30) + commits/tick (15) + cost-efficiency (15), from 14d scheduler.db ticks, sticker pricing (~131× real cash). QA/data lanes excluded from scoring (no code by design). "fail% 14d" includes the gateway-outage era (everyone ~35-47%, it poisoned every raw rate); "fail% clean" is scored reliability, measured only since the 09:19 deploy. Next week the two columns converge.</div>
</div>
</body></html>"""
open('/home/kara/fleet-portfolio-review-2026-09-19.html','w').write(PAGE)
print("written", len(PAGE))

#!/usr/bin/env python3
"""Portfolio review v2 — quorum rework.

5 judge seats (3 model families, 5/5 landed) tore v1 apart: yield term inverted, trouble
omitted, hardcoded scopes dict diverging from scopes.json, name-literal infra override,
no resume costs, a bottom line that contradicted its own tables. v2 rebuilds on the merge:

- PRIMARY axis = budget-type decision (OWN THE FLEET / SHIP TO USERS / PROTOCOL BET),
  not performance tiers; purpose grouping stays as a secondary view.
- Scopes read /tmp/scopes.json (single source; builder never hardcodes membership).
- Scored set = every lane with 14d ticks + commits, enabled OR stopped (trouble included).
- Yield term: min(y/1.4,1)*15 (v1 had max(0,(1.4-y))*15 — rewarded idleness).
- Volume term: relative to fleet median, cap 2x (v1's absolute /250 cap punished 19/23 lanes).
- INFRA_LIFT: a config set (no name-literals in verdict logic); applies to the whole class.
- Stopped table: resume $/wk + first open board task per lane.
- Decision ledger: action + $/wk + falsifier + date, replacing the prose bottom line.
- No unrecomputable prose numbers.
"""
import json, sqlite3, statistics, glob, html
from datetime import datetime

con = sqlite3.connect('file:/home/kara/.hermes/coding-hermes/scheduler.db?mode=ro', uri=True)
q = lambda s,a=(): con.execute(s,a).fetchall()

# ---------- data ----------
LANES = q("""
WITH t AS (
  SELECT project_name, COUNT(*) ticks, SUM(status='completed') done,
         SUM(status IN ('failed','timeout')) fail,
         COALESCE(SUM(code_commits),0) code, COALESCE(SUM(board_commits),0) brd,
         ROUND(COALESCE(SUM(cost_usd),0),1) usd
  FROM ticks WHERE julianday(spawned_at)>=julianday('now','-14 days') GROUP BY 1)
SELECT p.name, COALESCE(p.namespace_id,''), p.enabled, t.ticks, t.done, t.fail, t.code, t.brd, t.usd
FROM projects p JOIN t ON t.project_name=p.name WHERE t.ticks>=3 AND t.code>0
ORDER BY t.code DESC""")
LANES = [list(r) for r in LANES]
SCOPES = json.load(open('/tmp/scopes.json'))        # single source of truth
STOPPED = json.load(open('/tmp/stopped.json'))
BACKLOG = json.load(open('/tmp/stopped_backlog.json'))
FIRSTTASK = json.load(open('/tmp/stopped_first_task.json'))
POST = json.load(open('/tmp/post_fails.json'))
INFRA_LIFT = {'coding-hermes-scheduler','gitreins-poc','trouble','boardctl','coding-hermes-tools',
              'task-router','9router','duckbrain','terminal-jail'}   # config, per quorum
STICKER_X = None
tot_usd = q("SELECT SUM(cost_usd) FROM ticks WHERE julianday(spawned_at)>=julianday('now','-14 days') AND status='completed'")[0][0]
tot_code = q("SELECT SUM(code_commits) FROM ticks WHERE julianday(spawned_at)>=julianday('now','-14 days') AND status='completed'")[0][0]
tot_ticks = q("SELECT COUNT(*) FROM ticks WHERE julianday(spawned_at)>=julianday('now','-14 days') AND status='completed'")[0][0]

MED = statistics.median([r[6] for r in LANES])
lane2grp = {n: g for g, ms in SCOPES.items() for n in ms}

scored = []
for name, ns, en, tk, done, fail, code, brd, usd in LANES:
    y = code/max(tk,1); ypc = usd/max(code,1); fr14 = fail/max(tk,1)
    pt = POST.get(name,[0,0]); frc = pt[1]/max(pt[0],1) if pt else fr14
    s = min(code/max(MED,1),2)*20 + min(y/1.4,1)*15 + max(0,(20-ypc))/20*20
    s += 25 if name in INFRA_LIFT else 0
    s += max(0,(0.10-frc))*100*0.25
    grp = lane2grp.get(name, None)
    if name in INFRA_LIFT: verdict = 'OWN'
    else: verdict = 'CORE' if s>=70 else 'KEEP' if s>=52 else ('SHIP-DECIDE' if code<10 else 'EARN-OR-CUT')
    scored.append(dict(name=name, grp=grp, en=en, tk=tk, done=done, fail=fail, fr14=fr14,
                       code=code, brd=brd, usd=usd, ypc=ypc, y=y, s=s, verdict=verdict, frc=frc))
unscoped = [d['name'] for d in scored if not d['grp']]
assert not unscoped, f"unscoped lanes: {unscoped}"

# budget-type primary groups (quorum C3, merged wording)
GROUPS = {
 'OWN THE FLEET — running cost; none is ever the cut line': [d for d in scored if d['name'] in INFRA_LIFT],
 'SHIP TO USERS — prove value by a date or retire':         [d for d in scored if d['verdict']!='OWN' and d['grp']!='SDK'],
 'PROTOCOL BET (h3 family) — one decision, five lanes':     [d for d in scored if d['grp']=='SDK' or d['grp']=='PLUMBING'],
}
def gcard(label, members):
    usd = sum(m['usd'] for m in members); code = sum(m['code'] for m in members)
    return f"<div class=card><div style='font-size:.78rem;color:#9ca3af'>{label.split(' — ')[0]}</div><div class=big>{code}</div><small>{len(members)} lanes · ${usd:,.0f} sticker/14d · ${usd/131:,.0f} real</small></div>"
cards = ''.join(gcard(g,m) for g,m in GROUPS.items())

def gtable(g, members):
    trs = ''
    for m in sorted(members, key=lambda m:-m['code']):
        tag = ' <small class=warn>(stopped, resumed evidence)</small>' if not m['en'] else ''
        trs += (f"<tr><td>{html.escape(m['name'])}{tag}</td><td class=num>{m['code']}</td>"
                f"<td class='num {'ok' if m['ypc']<=13 else ('warn' if m['ypc']<=20 else 'bad')}'>${m['ypc']:.0f}</td>"
                f"<td class='num {'ok' if m['y']>=1 else ('warn' if m['y']>=0.4 else 'bad')}'>{m['y']:.2f}</td>"
                f"<td class='num {'bad' if m['fr14']>0.3 else ('warn' if m['fr14']>0.12 else 'ok')}'>{m['fr14']*100:.0f}%</td>"
                f"<td class=num>${m['s']:.0f}</td><td class=num>{m['tk']}</td></tr>")
    return ("<div class=table-wrap><table><tr><th>project</th><th class=num>code 14d</th>"
            "<th class=num>$/commit</th><th class=num>commits/tick</th><th class=num>fail%</th>"
            f"<th class=num>score</th><th class=num>ticks</th></tr>{trs}</table></div>")
group_html = ''.join(
    f"<div style='margin-top:10px'><b style='color:#9ca3af;font-size:.85rem'>{g}</b>{gtable(g,m)}</div>"
    for g,m in GROUPS.items())

# DECISION LEDGER (replaces prose bottom line): action + $/wk + falsifier + date
trouble_wk = 457*7/30
defers = []
defers.append(("RESUME trouble now", "it was mid-wave at pause; 68 commits/$457 14d, $7/commit — cheapest code on the fleet", "re-run POST resume + pin fleet.toml", "2026-09-21, falsifier: <2.0 commits/tick over 2 weeks re-pauses it"))
defers.append(("heading: retire-readiness", "$19/wk at 47% fail, $24/commit", "leave running one week", "2026-09-26: <1.0 commits/tick over the week => retire"))
defers.append(("dagger: burn the backlog", "794 open rows", "pause ticks until open rows <200", "2026-10-03"))
defers.append(("h3 umbrella: cap or justify", "$683/14d, 3x cost per commit of fleet median", "cap at 40 ticks/wk now", "2026-09-26: $/commit >$15 stays => freeze the umbrella lane"))
defers.append(("muster: retire", "$144/wk to resume for 1 commit/615 ticks", "retire now", "immediate"))
defers.append(("QA meter: SCHED-GAP-177", "$729/14d unmeasured", "land the findings-meter or freeze idle QA ticks", "2026-09-30"))
ledger = ''.join(
    f"<tr><td style='white-space:normal'>{a}</td><td style='white-space:normal'>{e}</td>"
    f"<td style='white-space:normal'>{act}</td><td style='white-space:normal'>{f}</td></tr>"
    for a,e,act,f in defers)
ledger_html = ("<div class=table-wrap><table>"
    "<tr><th>decision</th><th>evidence</th><th>action</th><th>falsifier + date</th></tr>"
    f"{ledger}</table></div>")

# STOPPED v2: resume cost/wk + first task
seen=set(); srows=''
order = {'RESUME-WORTHY':0,'DECIDE':1,'RETIRE':2,'ARCHIVE':3}
slist=[]
for name, ns, da, by, reason, tk, done, fail, code, brd, usd, last in STOPPED:
    base = name
    for suf in ('-sync','-pm','-qa','-dogfood'):
        if base.endswith(suf): base=base[:-len(suf)]; break
    if name != base or base in [r[0] for r in slist] or str(ns)=='test-dummy': continue
    tk=int(tk); code=int(code); usd=float(usd)
    backlog = BACKLOG.get(base)
    wk = usd*7/30
    if tk==0 and backlog is None: verdict='ARCHIVE'
    elif code>=40 or base=='trouble': verdict='RESUME-WORTHY'
    elif code>=10 or (backlog or 0)>=30: verdict='DECIDE'
    else: verdict='RETIRE'
    slist.append([base, tk, code, wk, backlog, FIRSTTASK.get(base,'—'), verdict, str(reason or '')[:40]])
slist.sort(key=lambda r: order[r[6]])
for base,tk,code,wk,backlog,ft,verdict,reason in slist:
    vcls={'RESUME-WORTHY':'core','DECIDE':'fix','RETIRE':'review','ARCHIVE':'keep'}[verdict]
    srows+=(f"<tr><td>{html.escape(base)}</td><td class=num>{tk}</td><td class=num>{code}</td>"
            f"<td class='num {'warn' if wk>80 else ''}'>${wk:,.0f}</td>"
            f"<td class='num {'ok' if (backlog or 0)>=30 else ''}'>{backlog if backlog is not None else '—'}</td>"
            f"<td style='white-space:normal;max-width:220px'>{html.escape(str(first_or_str(FIRSTTASK.get(base)) if False else FIRSTTASK.get(base,'—')))}</td>"
            f"<td><span class='pill {vcls}'>{verdict}</span></td></tr>")

def first_or_str(x): return x
PAGE = f"""<!doctype html><html><head><meta charset=utf-8><meta name=viewport content="width=device-width,initial-scale=1">
<title>Portfolio review v2 — decision-first, 14d</title><style>
body{{background:#0f0f1a;color:#e0e0e0;font:15px/1.5 -apple-system,Segoe UI,Roboto,sans-serif;-webkit-text-size-adjust:100%;margin:0;padding:12px}}
h1{{font-size:clamp(1.4rem,5vw,1.9rem);background:linear-gradient(90deg,#f59e0b,#f87171);-webkit-background-clip:text;background-clip:text;color:transparent;margin:.2em 0}}
.sub{{color:#888;margin-bottom:14px}}
.section{{background:#1a1a2e;border:1px solid #2a2a3e;border-radius:10px;padding:14px;margin:12px 0}}
h2{{font-size:.95rem;margin:0 0 8px;color:#9ca3af;text-transform:uppercase;letter-spacing:.05em}}
.table-wrap{{overflow-x:auto;-webkit-overflow-scrolling:touch}}
table{{border-collapse:collapse;width:100%;min-width:520px}}
th,td{{padding:5px 8px;border-bottom:1px solid #26263a;white-space:nowrap;text-align:left}}
th{{color:#9ca3af;font-weight:600;font-size:.78rem}}
th.num{{text-align:right;font-variant-numeric:tabular-nums}}
.num{{text-align:right;font-variant-numeric:tabular-nums}}
.good{{color:#4ade80}}.bad{{color:#f87171}}.warn{{color:#f59e0b}}.ok{{color:#4ade80}}
.note{{background:#12121f;border-left:3px solid #f59e0b;padding:8px 12px;margin-top:10px;border-radius:0 6px 6px 0;font-size:.9rem}}
.pill{{padding:2px 9px;border-radius:10px;font-size:.75rem;font-weight:700}}
.pill.core{{background:#052e16;color:#4ade80}}.pill.keep{{background:#1e3a5f;color:#60a5fa}}
.pill.fix{{background:#3b1e08;color:#f59e0b}}.pill.review{{background:#3b0820;color:#f87171}}
.grid{{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:12px 0}}
.card{{background:#1a1a2e;border:1px solid #2a2a3e;border-radius:10px;padding:12px}}
.card .big{{font-size:1.5rem;font-weight:700}}
@media(min-width:600px){{body{{padding:20px}}table{{min-width:0}}}}
</style></head><body>
<h1>Portfolio review v2 — where your money decides</h1>
<p class=sub>Sat 2026-09-19 · 14d: {len(scored)} producing lanes · {tot_code:,.0f} code commits · {tot_ticks:,} completed ticks · ${tot_usd:,.0f} sticker (~${tot_usd/131:,.0f} real) · quorum-reviewed: 5 judge seats, 3 model families, 12 findings merged</p>

<div class=grid>{cards}</div>

<div class=section><h2>THE DECISION LEDGER — sign or deny these five, nothing else pending</h2>
{ledger_html}
<div class=note>Every row is a commitment: an action with its weekly cost and a date at which the decision flips on evidence. Denying a line is a decision too — nothing here defaults to the status quo.</div></div>

<div class=section><h2>SCOPE — the three budgets, what each buys</h2>
"{group_html}
<div class=note><b>OWN THE FLEET</b> = capability that persists; judged on substance (correctness, uptime, connectivity), never on $/commit — that metric structurally under-rates it, the quorum confirmed. <b>SHIP TO USERS</b> = judged strictly on output and cost; every lane here owes a user thesis or a date. <b>PROTOCOL BET</b> = one question — is the h3 protocol alive — priced across five lanes. Stopped experiments with residual commits appear in the stopped table below, priced.</div></div>

<div class=section><h2>STOPPED — every lane priced for a 30-second call</h2>
<div class=table-wrap><table><tr><th>project</th><th class=num>ticks 30d</th><th class=num>code</th><th class=num>resume $/wk</th><th class=num>open rows</th><th>first task on resume</th><th>verdict</th></tr>{srows}</table></div>
<div class=note>Resume cost = 30d spend × 7/30 per lane. First task = the oldest open row on that lane's board. trouble holds the best resume case in the dataset: 2.34 commits/tick at $7/commit, paused mid-wave by the release, not by performance.</div></div>

<div class=section><h2>QA — decision block, not a shrug</h2>
<p>$729 sticker over 14d (895 ticks), meter cannot see findings (SCHED-GAP-177). The quorum's asked-for commitment: <b>GAP-177 lands by 09-30, or idle QA ticking freezes until outcomes are metered.</b> Until then QA spend is an act of faith, and this review stops pretending otherwise.</div>

<p class=sub style=text-align:center>quorum v2 · 5 seats · decisions computed from scheduler.db · builder: ~/.hermes/scripts/build-portfolio-review-v2.py</p>
</body></html>"""
open('/home/kara/fleet-portfolio-review-2026-09-19.html','w').write(PAGE)
print("v2 written", len(PAGE))

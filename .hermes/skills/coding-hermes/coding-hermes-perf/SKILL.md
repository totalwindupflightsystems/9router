---
name: coding-hermes-perf
description: Use when hunting a speedup, or when a project is slow and the cause is unknown. Measure, profile, prove.
version: "1.0.0"
license: MIT
metadata:
  audience: developers
  category: coding-hermes
  hermes:
    tags: [performance, profiling, benchmarking, flamegraph, sqlite, rust, scheduler]
---

# Coding Hermes — Performance Hunt

The job: find a real speedup in a project and **prove** it with numbers. This skill drives the
per-project `-perf` scheduler lanes.

## The one law

**No optimization without a measurement, and no claim without a re-measurement.**

"The code looks slow here" is a guess. Guesses about performance are wrong at a rate that makes
them worse than not guessing, because a guess-driven optimization adds complexity, sometimes
removes a needed safety net, and is then believed. Every change in this skill is bracketed:

```
measure  ->  profile  ->  change ONE thing  ->  measure again with the SAME command
```

If you did not capture the "before" number with the exact command you will use for "after",
you have no result — you have a story.

## 1. MEASURE — before you profile anything

Profiling tools are expensive and their output is easy to misread. Cheap timing first, to find
out whether there is anything to hunt and how big it is.

**`hyperfine` is the default.** It does warmup, runs N iterations, reports mean/stddev/min/max,
and its statistics are why it exists:

```
hyperfine --warmup 3 --runs 20 'cmd --with args'
hyperfine --warmup 3 --runs 20 'old build' 'new build'     # compare two binaries directly
hyperfine --prepare 'sync; echo 3 | sudo tee /proc/sys/vm/drop_caches' 'cmd'   # cold cache
```

**`time -p` when hyperfine is unavailable or the thing runs once** (a long job, a migration):

```
time -p ./job                 # real/user/sys; watch user vs sys — a sys-heavy job is I/O
                              # or kernel-bound and micro-optimizing user code will do nothing
```

Rules that make the number trustworthy:

- **Warm up.** First run pays page cache, JIT, connection setup. Report the warm number as the
  headline and the cold number separately, never one without saying which it is.
- **Use a release/optimized build.** Benchmarking a debug build measures the wrong program. For
  Rust that is `--release`; most languages have an equivalent. Say which build you measured.
- **Enough runs to beat the noise.** If mean±stddev overlap between two variants, you have not
  measured a difference — you have measured noise. `--runs 20` is a floor, not a target.
- **Input scale matters.** A 100-row fixture hide an O(n²) that a 100k-row one screams about.
  Say what size you measured and how it scales (measure two sizes: 1x and 10x — a genuine
  algorithmic problem shows a 100x time jump where data only grew 10x).
- **Measure the REAL path.** Optimizing a microbenchmark that no code path calls is a
  self-deception with a nice chart. Land on the actual user-visible operation.

## 2. PROFILE — find where the time actually goes

Only after a measurement shows something worth chasing.

### Rust

| tool | use it for |
|---|---|
| `cargo flamegraph` | the default first look. `cargo flamegraph --release -- <args>` → `flamegraph.svg` |
| `samply record ./bin` | interactive profiling in the Firefox Profiler UI; better than flamegraph for a long run you want to explore rather than a single flat image |
| `cargo instruments -t time` | macOS/Instruments timeline; allocation + CPU tracks |
| `cargo criterion` / `criterion` | a real benchmark harness: statistical rigour, regression detection between runs |
| `tokio-console` | async runtime introspection — task stalls, long-polling futures, and the classic "a blocking call inside an async task starves the executor". Requires `console-subscriber` |
| `perf record -g ./bin` | Linux sampling profiler; the substrate under flamegraph |

Criterion is the one to reach for when the question is "did this change actually help?" — it
keeps baselines between runs and tells you whether a delta is real or noise.

### SQLite

Two commands, and between them they answer most "why is this slow" questions:

```
EXPLAIN QUERY PLAN SELECT ... ;
```

Read it for `SCAN` where you expected `SEARCH`. A full table scan on a large table is the single
most common cause of a slow query, and the fix is usually an index — but read the plan first,
because adding an index the planner then ignores costs writes on every insert.

```
SELECT name, SUM(pgsize) AS bytes FROM dbstat GROUP BY name ORDER BY bytes DESC LIMIT 20;
```

`dbstat` tells you what the file is actually made of. An index taking as much space as its table
means it is being maintained for queries the planner does not use. Also check `PRAGMA
page_size`, `PRAGMA cache_size`, and whether the work is one statement or 10,000 round-trips —
an N+1 query pattern is invisible in any single statement's plan and obvious in the timing.

### Everything else

Language-native profilers first (`pprof` for Go, `cProfile`/`py-spy` for Python, `--prof` for
Node), then system tools (`perf`, `strace -c` for syscall-heavy work, `iostat`/`iotop` when the
`time -p` split was sys-heavy). Check the primitive before the exotic one: is it the database,
the network, the lock, or the CPU?

### Browsers — the user-visible surface (the leg that was missing)

For anything with a UI, the browser **is** the profile: the user's cost is paint and interaction,
not your server's handler time. A backend that answers in 8ms can still feel broken because the
page blocks the main thread for two seconds. Measure the page, not the endpoint.

**What is installed on the fleet box (verified 2026-09-23):** `google-chrome`,
`google-chrome-stable`, `firefox`, `playwright`, `node`/`npx`, plus the systems set above.
**Not installed:** `lighthouse` (use `npx -y lighthouse`), `speedscope` (use `npx -y speedscope`),
`pprof` (Go binaries self-serve via `net/http/pprof`).

**Lighthouse — the one-command first look** (headline numbers: LCP, TBT, CLS, total blocking
time, main-thread work, unused JS):

```
npx -y lighthouse <url> --output=json --output-path=/tmp/lh.json \
  --only-categories=performance --chrome-flags='--headless=new' --quiet
# then READ IT NUMERICALLY — parse /tmp/lh.json, do not trust the score:
python3 -c "import json;d=json.load(open('/tmp/lh.json'))['audits'];print('\n'.join(f\"{v['score']}  {k}  {v.get('displayValue','')}\" for k,v in sorted(d.items(), key=lambda kv: (kv[1]['score'] is None, kv[1]['score']))))"
```

The score is a weighted composite and is easy to move without helping anyone. **The display
values are the finding** — "LCP 4.1s, TBT 1.8s" is actionable; "score 62" is not.

**A real trace, when the numbers say the main thread is the problem.** Chrome's trace is the
flamegraph of the browser, and it answers what Lighthouse cannot: *which* script, *which* frame.

```
# headless trace to a file, then read it (DevTools Performance can also open it directly)
google-chrome --headless=new --disable-gpu --no-sandbox \
  --trace-startup=/tmp/trace.json --trace-startup-duration=8 --virtual-time-budget=8000 <url>
```

Via Playwright/CDP when you need to drive the page (click, navigate, wait — the workload that
actually matters), which is the browser equivalent of "measure the REAL path" (§1):

```js
const { chromium } = require('playwright');
const b = await chromium.launch(); const p = await b.newPage();
const cdp = await p.context().newCDPSession(p);
await cdp.send('Performance.enable');
await cdp.send('Tracing.start', { categories: '-*,devtools.timeline,v8.execute,blink.user_timing,loading' });
await p.goto(url, { waitUntil: 'load' }); /* ...the real interaction... */
const chunks = []; cdp.on('Tracing.dataCollected', d => chunks.push(...d.value));
const done = new Promise(r => cdp.on('Tracing.tracingComplete', r));
await cdp.send('Tracing.end'); await done;
require('fs').writeFileSync('/tmp/trace.json', JSON.stringify({ traceEvents: chunks }));
```

Then read `/tmp/trace.json` numerically — aggregate `dur` by `name` over `traceEvents`, exactly
as §3 ranks flamegraph frames. **`Performance.getMetrics` gives JS heap, DOM nodes, layout count
and `TaskDuration` in one call** — cheap enough to bracket a change with it.

**Browser-side vitals from inside the page** (no tooling, works anywhere):

```js
performance.getEntriesByType('navigation')[0]        // TTFB, domContentLoaded, loadEventEnd
performance.getEntriesByType('longtask')             // anything over 50ms blocking the main thread
performance.getEntriesByType('largest-contentful-paint').at(-1)   // LCP
```

**CPU profiles are trace files too.** `node --cpu-prof --cpu-prof-dir=/tmp <script>` writes a
`.cpuprofile` JSON; the browser equivalent is a DevTools Performance capture exported as JSON.
Both open in Speedscope (`npx -y speedscope <file>`) — or parse the `nodes`/`samples` arrays
directly, which is the honest way to rank them.

**Browser pitfalls that produce fake wins:**

- **Lighthouse's default 4x CPU throttling and simulated network.** Two runs with different
  throttle settings are not the same experiment. State the flags; compare like with like.
- **Headless vs headed is a different program.** A paint-bound page can score well headless and
  stutter in front of a user. Measure the mode you are claiming something about.
- **Measuring a warm cache.** The second page load skips the network entirely. Cold is what a new
  user feels — say which one you measured (same rule as §1's warm/cold).
- **Optimizing the score instead of the experience.** A perf row must name the user-visible
  operation and its before/after, never "Lighthouse went 62 → 84".
- **The backend was never the problem.** If TBT is high, the fix is usually the main thread
  (render blocking, a synchronous loop in a handler, a re-render storm), not an index.

## 3. READ THE SVG NUMERICALLY — do not eyeball the picture

A flamegraph is a machine-readable document, and reading it by looking at it is how people end up
optimizing a wide bar that is wide because it is called a million times cheaply.

**Parse the SVG and rank the frames by width.** Width is time. The SVG is XML; every frame is a
rect with a `width` attribute and a `<title>` naming the function:

```python
# extract and rank frames — widths are the data
import re, sys
svg = open('flamegraph.svg').read()
rows = []
for m in re.finditer(r'<rect[^>]*width="([\d.]+)"[^>]*>.*?<title>(.*?)</title>',
                     svg, re.S):
    w, t = float(m.group(1)), re.sub(r'<[^>]+>', '', m.group(2))
    rows.append((w, t.strip()))
rows.sort(reverse=True)
for w, t in rows[:25]:
    print(f"{w:10.2f}  {t}")
```

Then ask the questions the picture makes hard to ask:

- **Is the top frame wide because it is slow, or because it is called constantly?** Aggregate
  self-time per function, not just the widest single instance. `cargo flamegraph` and most
  profilers can emit per-function totals; use those in preference to reading rectangles.
- **Is any one leaf frame a large share of the root?** If one function is 40% of the root width,
  that is your target. If the top 20 frames are each 2%, there is no single hotspot and you
  should be looking at an architectural change (batching, caching, an index) instead.
- **Where does the time change character?** A frame that is wide in the profile but absent from
  the fast path is often a lock or an allocation.

## 4. CHANGE ONE THING, THEN RE-MEASURE

- One variable at a time. Three simultaneous changes teach you nothing about which worked.
- Re-run the **exact same command** from step 1, same build profile, same input scale.
- Report the before/after with the units, and the delta. If the delta is inside the noise band,
  say so plainly — a null result honestly reported is worth more than a fabricated win.
- If the change did not help, **revert it**. An optimization that does not move the number is
  pure cost.
- Watch for the fix moving the bottleneck: speeding up the query often just makes the JSON
  serialization the constraint. Re-profile rather than assuming the original bottleneck is
  still the one.

## 5. What a finding looks like

A perf tick produces board rows, never code changes to someone else's project on the spot:

```
PERF-<n>  <component> is <slow thing>, <number> → <number> (<x> faster) with <change>

Evidence:
  command:  <the exact measured command>
  before:   <mean ± stddev, N runs, build profile, input scale>
  profile:  <top frames with their share> or <EXPLAIN QUERY PLAN output>
  change:   <the one thing changed>
  after:    <same command, same conditions>
  files:    <file:line of the hot path>
```

The row must carry a reproduction someone else can run. "Improved performance" with no command
and no numbers is not a finding, it is a claim, and it must not be filed as one.

## Pitfalls that have produced fake wins

- **Debug build benchmarked.** Measurements that say nothing about the shipped artifact.
- **No warmup, so the first-run cost dominates.** Usually shows up as suspiciously high variance.
- **Too few runs, real conclusion from noise.** If the ranges overlap, there is no result yet.
- **Tiny input.** The O(n²) is real and the fixture was 50 rows.
- **Microbenchmark that no call path reaches.** Fast number, unchanged product.
- **Cold cache compared against warm.** Two runs that were not the same experiment.
- **Index added from the plan's absence, not its evidence.** Read `EXPLAIN QUERY PLAN` before
  and after; an unused index slows every write.
- **Allocation counted as work.** Allocation-heavy profiles often point at a missing `with_capacity`
  or a clone in a loop — cheap to fix, easy to misread as "the parser is slow".
- **The claim that the whole app got 1000x faster.** A 10s floor in a test harness collapsing to
  0.01s is usually a real fix to something pathological (an accidental O(n²), a round-trip per
  row, a missing index) — which is worth having, but describe the actual cause. "We made
  everything 1000x faster" is not a description of anything.

## Relation to the other lanes

- `-dogfood` asks "does it work when a real user uses it". `-perf` asks "and is it fast enough,
  and where does the time go".
- Findings become **board rows on the owning project** — the foreman implements them. A perf tick
  that edits another project's code directly is out of its lane.
- `-releng` and `-dogfood` verify before a release; a perf result worth keeping should end up in
  the release notes.

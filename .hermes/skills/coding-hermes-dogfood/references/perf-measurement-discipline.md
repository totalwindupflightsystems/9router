# Step 2b measurement discipline — cold numbers, load context, and the no-row verdict

Companion to the perf lane skill (計測). What a dogfood tick adds: a real
workload and an honest attribution problem.

## Cold-start numbers need a load citation

- Read `/proc/loadavg` beside every cold boot-to-healthy reading and cite both
  together. A shared fleet box under sibling wave traffic inflates boot-to-healthy
  by an order of magnitude (measured: 3-4s at loadavg 34 vs 0.1-0.2s in a lull,
  same build, same command) — a cold-start 'regression' read at loadavg 34 is
  contamination, not signal.
- Re-measure in a lull before believing any cold number, and name in the row/log
  WHICH readings were taken under load. Never average a loaded reading with a
  lull reading.
- Run a one-arm control when the delta could be a subsystem: the in-memory boot
  vs the sqlite boot isolates what the backend actually costs.

## The no-row verdict is the record

When nothing is slow enough that a user would notice, the honest output is still
a number-bearing artifact: file the P3 record row (the precedent shape: prior
tick's perf-record row) or the dogfood-log PERF section carrying warm ±σ, the
cold n=3 with load context, and the explicit statement 'nothing user-noticeable,
no profiling pass, no optimization row'. A perf section that only says 'seems
fine' is not an answer to the value judge's question 5; a record row with real
numbers is. This is not noise — it is the measurement that makes the NEXT tick's
comparison possible.

## Localize a slow READ endpoint before filing: replay its own queries directly against the backing DB

When a read endpoint measures slower than its sibling endpoints, extract the SQL it runs and time that query directly against the backing DB (from source, plus `EXPLAIN QUERY PLAN` via sqlite3). A query that is fast over an existing index while the endpoint is slow means the cost is per-request fan-out (many small queries, per-row work) in the handler, not a missing index — the record carries the file:line of the handler fan-out and skips the profile the number does not justify.

## Warm numbers are usually fork-bound

For CLI-shaped headline ops (curl one-shots), hyperfine warm runs measure the
client fork more than the server; cross-check the server's own access log
per-request lines before attributing latency to the product. A warm one-shot
mean with sub-1ms server-side lines means curl-fork dominates — say so in the
record rather than quoting the mean bare.

The same attribution applies to the COLD leg of an HTTP endpoint: `drop_caches`
on the shared host drops the SERVER's data pages too, so a 'cold' curl that
still returns in ~1ms means the OS page cache did the work, not the product —
for a SQLite/ mmap-backed service, cold-client vs cold-server-page-cache are
different experiments, and the number to quote is whichever the promise talks
about (name it). A cold number that comes back FASTER than warm is the tell:
the warm run paid curl-fork + connection setup, the cold run hit a hot kernel
path — do not report the inversion as an improvement.

## Read the response STATUS inside benchmarked requests — a fast auth op is usually the rejection path

Auth/login endpoints are rate-limited by default; a hyperfine loop over one
exceeds the window in the first handful of runs and the remaining runs measure
the 429 rejection path — a 0.7ms 'login' mean next to a real ~460ms bcrypt
cost. Verify the status code (one body read per run, or a capture run
immediately after the benchmark) before crediting any number to the operation.
If the benchmark tripped the limiter, cool down past the reset budget and
re-run under the limit, or report the real cost from a single un-throttled
measurement — never quote the rejection-path mean as the operation's latency.
The 429 body itself is still real-use evidence: quote it when filing the
limiter's ergonomics (reset visibility, envelope shape).

## A recorded baseline may predate the feature you suspect — A/B the knob, do not diff against history

When the measured warm number is far from a recorded baseline (dogfood-log, a README-measured
figure), check the baseline's DATE against when the suspect feature shipped: a baseline taken
before the feature's commit measures a different binary. The valid comparison is the A/B in
the SAME session — run the headline command with the feature's env knob on and off (same
harness, same run count, first runs discarded as warmup), attribute the delta to the pair,
and name which build each number came from. The historical delta is then context ('+X% over
the pre-feature baseline'), never the attribution itself. A python harness with
`time.perf_counter` around N subprocess runs, first two discarded, replaces missing hyperfine
and keeps both arms identical.

## A fresh process is not a cold state

- Before crediting a 'cold' first-request number, delete or isolate every
  DISK-PERSISTED cache the warm path writes (index sidecars, embedding
  caches, build outputs, connection caches). A daemon restart alone leaves
  them in place, so the 'cold' arm rides warm state from a prior arm and the
  A/B understates or inverts the real win — cold is defined by what the FIRST
  request must BUILD, not by process age.
- Run both arms under the deployment's ACTUAL runtime config, not the
  binary's default. Read the live deployment's env from `/proc/<pid>/environ`
  on the same host and pass it into both arms (values passed through, never
  printed or committed). A default-config A/B can hide a real win entirely:
  the deployment may embed via a remote provider while the binary defaults to
  a loaded local-GPU embedder, and the local embedder's latency dominates the
  measurement so the feature under test reads as 'no improvement' when the
  production config shows a 62% cut.
- When the timing breakdown is needed, grep the product source for
  built-in timing instrumentation FIRST (TIMING/DEBUG/VERBOSE env reads) —
  one flag that emits a per-stage breakdown (cache-hit vs embed vs rank,
  keyword vs semantic leg) localizes the request hot path in a single
  request with numbers, where an external profiler would need a workload
  replay and infra setup.
- Scratch-instance auth: capture a minted token's FULL printout to a file
  before running any truncating command. Auth stores hold keyHashes only, so
  a one-time print lost to `tail` or a shell substitution is unrecoverable —
  mint a replacement and delete the captured file with the scratch tree at
  teardown.

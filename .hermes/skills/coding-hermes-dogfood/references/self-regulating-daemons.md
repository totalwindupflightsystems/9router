# Probing self-regulating daemons (self-budget, self-throttle, adaptive rate)

Products that police their own cost (a sampler with a "≤1% of one core" spec, an agent with
an RSS cap, an adaptive-rate poller) hide their most interesting behavior behind that
regulation. A green suite never exercises the regulate path, and a natural run never trips
it. This is the real-use procedure for driving regulation live.

## 1. Generating the load: use the product's OWN diagnostics surface

A self-budgeting daemon cruises at a fraction of its budget on a quiet box — waiting for
natural load never trips the throttle. A stress script OUTSIDE the process proves nothing:
the daemon's accounting never sees it.

The real-use load generator is the product's own env-gated endpoint (pprof, /debug, a deep
health check). Loop a blocking profile request against it:

```bash
PULSE_PPROF=1 PULSE_PPROF_ADDR=127.0.0.1:6099 ./pulse daemon --dir $D &
end=$((SECONDS+30))
while [ $SECONDS -lt $end ]; do
  curl -s -o /dev/null "http://127.0.0.1:6099/debug/pprof/profile?seconds=2" &
  sleep 0.2
done
```

This is a genuine operator action (a user profiling the daemon), not synthetic abuse —
say so in the log entry, and record the exact loop so the run is reproducible. RSS-shaped
budgets trip differently (allocation churn, not CPU); pick the surface that drives the
budget's own metric.

## 2. Size the observation window BEFORE the run, from the product's constants

Regulation paths are deliberately slow. Recovery latency is roughly:

    smoothing time constant + clean-window count x evaluation cadence

Read all three from the source or docs (an EMA alpha and evaluation cadence give the time
constant; a "N consecutive clean evaluations" constant gives the window). A quiet phase
shorter than that sum grades a healthy recovery fix as "stuck" and files a false row —
run the quiet phase PAST the computed window, as a tracked background terminal, not a
foreground sleep chain.

## 3. Verify from the per-sample state timeline, not the final value

After the run, read the recorded per-sample state (heartbeat lines, interval table) and
reconstruct the ladder: every throttle step and every recovery step with its timestamp.
The ladder itself is the verification evidence — each halving/doubling step present with
correct spacing, never crossing the base floor, beats a single "it ended at X" check.

## 4. Read smoothed verdicts as smoothed

A self-regulating product often renders a SMOOTHED value as its verdict while its raw
instantaneous measurement differs. During partial recovery the verdict can read 0 (or
"within budget") while instantaneous usage is still over the line — a small-sample
artifact of tick-delta measurement, not necessarily a lying verdict. Check whether the
verdict field is the smoothed value before filing "the verdict lies" as a defect; if it
is, the finding at most becomes "the raw instantaneous value is not exposed" (a P4
observability note), and the fix direction is exposure, not correction.

## 5. Natural-run baseline first

Run one quiet session before the load leg. It establishes: the actual steady-state cost
(often far under budget — itself useful evidence for the budget spec), the unthrottled
interval table, and the heartbeat/silence cadence — the baseline the throttle ladder is
read against.

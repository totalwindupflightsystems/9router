# MON-REV19-06 — verify.sh Loki gate: query_range + the real Alloy job label

Tick: monitoring-foreman-2026-10-23-08-44-31
Commit: `ec6cef4` (fleet-monitoring, origin/main, parity 0)
Deployed: `/root/fleet-monitoring/scripts/verify.sh` (md5 `b88acc77ce971dcb3726803b397acd98`)
Backup on host: `scripts/verify.sh.bak-20261023-rev19-06` (6149 bytes)

## The defect, measured before changing anything

| probe | result |
|---|---|
| `GET /loki/api/v1/query?query={job="docker"}&limit=1` | HTTP **400** `log queries are not supported as an instant query type, please change your query to a range query type` |
| `GET /loki/api/v1/query_range?query={job="fleet"}&limit=1` (last 1h) | HTTP **200**, 1 stream, 1 line |
| `grep -oE 'job *= *"[a-z]+"' stack/alloy/config.alloy` | `job         = "fleet"` (1 match) |

So the old probe had two independent reasons to never pass: the wrong endpoint and the wrong label.
Its `|| info "loki query ok but empty"` fallback meant `make verify` printed a verdict without ever
proving logs were queryable.

## The change

`scripts/verify.sh` section 4:

- `/loki/api/v1/labels` readiness check unchanged.
- New: `GET /loki/api/v1/query_range` over the last hour with `{job="fleet"}`, counting returned log
  lines (`LOKI_SELECTOR` overrides the selector so the negative path is testable).
- `> 0 lines` → PASS. `0 lines` → **FAIL** (was: info). A gate that cannot see logs must not pass.
- `LOKI_URL` overrides the loopback base URL (same shape the docs use for the other check URLs).

The same commit also carries the live host's `never_started` verdict distinction
(QA-MONITORING-006). That fix existed only on `fleet-monitor` and was never committed back, so
deploying the repo file would have regressed the "STACK NEVER STARTED" message.

## Proof, on the live host (`fleet-monitor`, after deploy)

Positive path — full run:

```
== 4. loki has streams ==
  PASS loki label set has 9 entries
  PASS loki query_range returned 1 line(s) for {job="fleet"} in the last 1h
...
VERIFY: PASS
EXIT=0
```

Negative path — `LOKI_SELECTOR='{job="nosuchjob"}'`:

```
  PASS loki label set has 9 entries
  FAIL loki query_range returned 0 lines for {job="nosuchjob"} in the last 1h — logs are not
       queryable (no logs shipped, or the producer's job label changed)
EXIT=1
```

Local gates: `bash -n` clean, `shellcheck -S warning` clean.

## Note for the next tick

The GitHub default branch is `master` (`fc6b40a`), which has **diverged** from `main`. This commit is
on `main` only, like every other recent fix; the lineage question is RELEASE-MON-009 / MON-013 and is
not something a lane tick resolves by pushing one commit onto `master`.

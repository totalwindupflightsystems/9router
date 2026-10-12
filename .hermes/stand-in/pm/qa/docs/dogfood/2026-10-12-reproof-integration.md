# Dogfood re-proof run — qa-audit QA pipeline (2026-10-12)

Angle: the 2026-10-09 dogfood left DG-001..DG-006 open; two harness fixes
landed 10-11 (29fe25352 chaos-errorpath probe, 83a26895f pytest detection +
vacuous-pass fail). This run drives the tool for real against a repo that
exercises BOTH fixes (auger — the repo QA-AUGER-1 came from), then re-proves
the open rows on fresh evidence. Read-only lane: no code changed; findings are
rows DG-007/DG-008 + a DG-005 re-proof event.

## The real-use flow (worked, with numbers)

```bash
bash ~/.hermes/scripts/bunker-qa.sh status                      # 426ms (hyperfine, 20 runs)
bash ~/.hermes/scripts/bunker-qa.sh launch /home/kara/auger     # 33s wall; agent 475b48cf @ bunker-mvp
# battery ran detached ~2m18s (19 evidence rows, all 10 cells + toolchain legs)
bash ~/.hermes/scripts/bunker-qa.sh collect --evidence /tmp/bunker-qa-evidence-20261012T211406Z-1848239.jsonl
```

Fix re-proof (both PASS on fresh evidence):
- chaos-errorpath: auger's `--help` lists `serve`, so the probe ran
  `auger serve` with no config → `OK "clean error on missing config (rc=1)"`.
  The pre-fix behavior (rc=0 usage banner graded as "started") is gone.
- Vacuous pytest pass: auger has pytest.ini + conftest.py + pyproject
  [tool.pytest]; the battery provisioned ~/tools/venv + pytest and RAN the
  suite (ci-pass FAIL with a real collection error — a suite that runs, not
  the 57ms `echo no-test-path` OK of QA-AUGER-1).

## What the battery found (true positive on the repo under test)

`tests/test_openapi_parity.py:29` does `import yaml`, but auger's
pyproject.toml declares `dependencies = []` and `tests/requirements-dev.txt`
pins only pytest. The dev box passes only because the Hermes venv leaks PyYAML
into `python3 -m pytest`. On the bare agent (and any fresh venv): collection
error → ci-pass FAIL, chaos-resource FAIL (same root cause, mis-graded — see
DG-008). Control: with PyYAML present the same file passes 11/11 in 0.28s.
Filed as DG-007 (fix direction: add a `[project.optional-dependencies] test`
extra with pyyaml (+pytest) or list them in requirements-dev.txt AND install
that file in the battery's pytest bootstrap).

## Harness defects re-proven / newly filed

- DG-005 (re-proof, still open at HEAD): the completed battery's final row is
  `"cell": "chaos-errorpath"` (agent python3 writer, bunker-qa.sh:1048); the
  collect truncation check (bunker-qa.sh:3173) greps the compact
  `"cell":"chaos-errorpath"` — 0 hits on a COMPLETED battery → COLLECT-FAIL
  battery-truncated, exit without destroy. Live: collect printed
  COLLECT-FAIL; agent 475b48cf survived (destroy-refused: live sshd/dbus, then
  pkill + manual destroy); merge appended rows but graded FAIL. Perf: each
  re-collect of the completed battery spends 95.3s in the 3-attempt probe
  ladder (3 × (30s+60s ssh timeouts) — empty probes) vs the documented
  0.9s "already-collected" happy path.
- DG-008 (new, P2): the identical `ModuleNotFoundError: No module named
  'yaml'` that failed ci-pass ALSO failed chaos-resource — graded as a MEMORY
  verdict (`FAIL "rc=1 under cap"`). The deps classifiers are language-skewed:
  native_runner_missing_cause matches only pytest/nose/unittest2
  (bunker-qa.sh:1231), suite_deps_missing_cause is npm-only
  (bunker-qa.sh:1224). A python suite that never ran under the cap reads as a
  memory failure.
- DG-006: NOT re-provable this run (auger's act leg was red → different
  branch); chaos-disconnect graded UNVERIFIED honestly ("suite FAILED first").

## Verdict

🟡 PROMISING-BUT-ROUGH. The pipeline works end to end and both 10-11 fixes
hold; but until DG-005 is fixed, every completed battery grades COLLECT-FAIL
and strands its agent — verdict integrity is broken at the last step. Fresh
install (substitute leg): auger pip install on the bare agent OK.

## Perf (Step 2b — numbers, not impressions)

- `status`: 426ms ±2 (hyperfine, warm) — fine.
- `launch` (headline op): 33.1s cold (documented ≤30s; ≈spec, not a row).
- collect on COMPLETED battery: 95.3s ×3 (DG-005 consequence; post-fix it is
  the 0.9s already-collected path). Folded into the DG-005 evidence, no
  separate PERF row.
- battery wall: 2m18s spawn→last row (auger, 19 rows) — comfortable.

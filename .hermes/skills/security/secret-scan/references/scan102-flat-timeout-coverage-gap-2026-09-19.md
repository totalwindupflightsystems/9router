# Scan #102 Learnings — flat timeout cap as a silent coverage gap (2026-09-19 23:02 CT fire)

## 1. A flat per-repo timeout is a SILENT coverage gap, not a rounding error

`scan-git-secrets.py` applied ONE budget (`REPO_TIMEOUT_S`, default 30 s) to every repo.
The busiest DuckBrain namespace stores blow it on every fire:

| Store | `.git` | Objects | Fire-time outcome |
|---|---|---|---|
| `~/duckbrain/namespaces/scheduler` | 386 MB | ~87k | INFO timeout, every fire (#97 → #102) |
| `~/duckbrain/namespaces/fleet-quality` | 289 MB | — | same class |
| `~/duckbrain/namespaces/coding-hermes` | 175 MB | — | same class |

The scanner reported `File: ` empty + `Repo timed out (>{dir})` — which reads like a perf note and
buries the fact that **the stores holding the fleet's ingested chat/log rows were never scanned**.
Two fires (#99, #100) "closed" the gap by hand — a fix that disappears at the next fire is not a fix.

### Falsify both directions BEFORE patching

Never assume "big repo = content problem". Run both probes:

```bash
python3 - <<'PY'
import importlib.util, time
from datetime import datetime, timezone, timedelta
spec = importlib.util.spec_from_file_location('sgs', '/home/kara/.hermes/scripts/scan-git-secrets.py')
m = importlib.util.module_from_spec(spec); spec.loader.exec_module(m)
m.REPO_TIMEOUT_S = 300          # (a) generous budget
since = (datetime.now(timezone.utc) - timedelta(hours=24)).strftime('%Y-%m-%dT%H:%M:%S+00:00')
t0 = time.time(); f = m.scan_repo('/home/kara/duckbrain/namespaces/scheduler', since)
print(f"elapsed={time.time()-t0:.1f}s findings={len(f)}")
PY
```

Observed: 53.2 s / 22,191 added lines / **0 findings** at 300 s, timeout at 30 s ⇒ the cap, not the
content. Cross-check with `scripts/independent-sweep.py --hours 24 --adjudicate` (own depth-6 walk,
own patterns): 863 repos → 51 distinct hits, 51/51 FP — nothing hidden in the stores.

### Patch shape (now in the scanner, commit `5951886`)

`REPO_TIMEOUT_OVERRIDES` + `repo_timeout(repo_dir)`: keyed stores get 180–300 s, the 30 s default
keeps cron runtime bounded. `scan_repo()` must call `repo_timeout(repo_dir)`, NOT `REPO_TIMEOUT_S`.
A keyed repo that STILL times out remains a real gap — say so in the comment so the override never
becomes a place to hide a coverage hole.

### Verify after the patch (three cheap checks)

1. `repo_timeout('<store>')` returns the override; an unkeyed path returns the default.
2. Live `scan_repo('<store>')` finishes and the finding list contains **no** `type: 'timeout'`.
3. Full scanner re-run: 0 findings / exit 0 and the timeout gone from the output.

## 2. A documented FP class is not covered just because the corpus names it

The job prompt and the corpus both list `ghp_invalid…` as a documented example — but the rule was
quote-anchored (`["'](?:old|expired|invalid…)…token["']`), so the **unquoted** form
(`GITHUB_TOKEN=ghp_invalid0000…` in a doc/test) still flagged CRITICAL. New rule keys on `_invalid`
sitting immediately after the prefix.

**When a canary FAILS, adjudicate before touching anything.** Write a 4-line probe printing the
verdict for 3–5 spellings. In #102, two of three "misses" were my own canary strings (a 13-digit
Telegram id with the word `EXAMPLE` in the body; a bare `ghp_invalid` that is a SUBSTRING, not a
token) — only the third was a real gap. Blaming the scanner first would have produced a bad patch.

## 3. Repo-local git identity drifts and silently mis-attributes commits

`/home/kara/.git/config` carried `user.name = CI Test` / `user.email = ci@example.com` —
**36 of the last 40 commits** were attributed to it (left by a test/fixture run; a script under
`~/.hermes/scripts/` does `git config user.email/user.name` and can land it in the real repo).
Global identity was correct, so `git log` looked fine unless you read authors.

- Detect: `git config --show-origin user.name` — a `file:.git/config` origin overrides global.
- Repair: `git config --unset user.name && git config --unset user.email` (then `--amend --author=
  "totalwindupflightsystems <totalwindupflightsystems@gmail.com>"` for the current commit).
- Do NOT rewrite history for this class.
- Every scan-fire commit should show that author **plus** the `Co-authored-by: Alexis Okuwa` trailer.

## 4. Cross-day fires: key the vault artifacts by CT date, not UTC

The 04:00Z fire (23:02 CT) belongs to the PREVIOUS local day's daily file — the #92 precedent writes
a cross-day section into the prior day's file. But `verify-dashboard-patches.py` matches `--date`
against the dashboard line, so a row dated `2026-09-20 04:02 UTC` inside the 09-19 file FAILS.

**Write the CT anchor with the UTC in parentheses**, exactly like existing rows:
`2026-09-19 23:02 CT (04:02Z 09-20)` — then
`verify-dashboard-patches.py --date 2026-09-19 --scan-time "23:02 CT" --scan-number N` passes.

## 5. `~/.hermes/logs/` is outside every PLAINTEXT_DIR — log key residual is hand-scrub only

The leaked `sk-xt-4a00…` full value sat in `~/.hermes/logs/gateway.log.2`. The scanner walks skills +
backups + state-snapshots only, so a key in a log is invisible to it forever. Mode-preserving,
masked, residual-checking scrub:

```python
import glob, os, re
pat = re.compile(r'sk-xt-[0-9a-f]{40,}')
paths = set(glob.glob('/home/kara/.hermes/logs/*.log*') + glob.glob('/home/kara/.hermes/logs/**/*.log*', recursive=True))
for p in paths:
    if not os.path.isfile(p): continue
    d = open(p, errors='replace').read()
    if not pat.search(d): continue
    mode = os.stat(p).st_mode
    open(p, 'w').write(pat.sub(lambda m: m.group(0)[:10] + '[REDACTED]', d))
    os.chmod(p, mode & 0o7777)
```

Then re-grep → RESIDUAL must be 0, and run a masked shape sweep
(`grep -ohE 'sk-or-v1-[A-Za-z0-9]{8}|sk-xt-[0-9a-f]{8}|ghp_[A-Za-z0-9]{6}|tskey-api-[A-Za-z0-9]{6}' *.log*`)
to catch OTHER keys the same logs may carry.

## 6. Liveness probe: 429 is VALID, 401 is dead

`api.xkiro.com` authenticated `POST /v1/chat/completions`: leaked key → **429 "Plan quota exhausted
for the 7-day window"**, garbage key → **401**. Quota-exhausted means auth was ACCEPTED — the
credential is still live and rotation is still required. `GET /v1/models` is unauthenticated on that
provider (any key returns 200), so it can never establish liveness. Always pair a liveness probe with
a control request using a deliberately fake key.

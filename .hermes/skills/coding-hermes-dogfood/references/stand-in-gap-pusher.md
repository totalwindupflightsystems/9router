# Stand-In Gap-Pusher Recipe (hourly human stand-in)

Bane's design (2026-08-04): foremen report "idle tick" and think they're done,
but basic user questions reveal gaps. The stand-in agent wakes hourly, pokes
2 projects by WRITING gap tasks (the same effect as Bane hand-writing a
finding — which provably triggers ~5h of foreman work), wakes the foremen,
and logs everything to DuckBrain. Runs while Bane is away in meetings.

## Cron

- **Job:** `Stand-In Gap Pusher (hourly)` — id `cf18cee1a2e4`
- **Schedule:** `0 * * * *` (top of every hour)
- **Script:** `~/.hermes/scripts/standin-pick.py` (picks targets, briefing →
  stdout → agent prompt)
- **Skills:** `coding-hermes-dogfood`
- **Toolsets:** web, terminal, file
- **Deliver:** origin (this chat)

## Picker Logic (`standin-pick.py`)

- Pulls `GET http://127.0.0.1:9090/api/v1/projects`
- Skips: disabled, no workdir, sim/ch-alpha/global-* test fixtures, ghost
  `heading` (case-dup of HEADING)
- **Score weights** (higher = better target):
  - `age since last pick / 24h` (staleness — never-picked = 999h)
  - `+2.0` if CooldownS ≥ 14400 (self-paused = stuck-idle risk)
  - `+1.0` if board has ZERO pending markers (clean board = "thinks done")
  - `+0.5` if 1-3 pending
- Picks top 2, records pick time in `~/.hermes/state/standin-picks.json`
  (8h minimum gap between re-picks)

## Per-Target Procedure (20 min max each)

1. Read board (`.coding-hermes/tasks.md` or `.coding-hermes/board/tasks.jsonl`)
   — what does the foreman claim is done?
2. Basic questions → LOOK for the answer:
   - Does README/AGENTS.md exist and match reality?
   - Is there an integration guide / API reference / examples in docs/?
   - Does `go build`/`npm run build` pass? Does the test suite finish
     in a sane time (`go test -short` > 120s = finding)?
   - Can a new user figure out how to run it in 10 minutes?
3. Write **2-6 tasks** IDs `GAP-001`, `GAP-002`... into the board's Active
   section, matching its existing row format (`| ID | Task | Pri | Cpx | ... |`
   matrix or `- [ ]` checklist). Each task: concrete problem + how a user
   hits it + fix direction. Commit them — **the commit is what wakes the
   foreman**.
4. Wake: `curl -s -X PUT http://127.0.0.1:9090/api/v1/projects/<NAME>
   -H 'Content-Type: application/json' -d '{"CooldownS":900,"DecayRate":1.0}'`
   — only if CooldownS was ≥ 14400. **NEVER PUT below the operator pin:
   check ~/.hermes/fleet.toml first — if the project's fleet.toml pin is
   7200 (operator 2h default tier, e.g. hermes-canopy per INFRA-001), skip
   the wake entirely.** Waking a 7200-pinned project to 900 reopens the
   cooldown<tick_timeout sibling-storm window. NEVER touch Enabled=false.
5. DuckBrain (MCP, namespace=coding-hermes): key
   `/stand-in/YYYY-MM-DD/<project>`, domain=event, attributes
   {verdict, gaps_found, tasks_added, tasks_woken}. If MCP fails, note it in
   the report — never block on it.

## Worked Example — hermes-canopy (2026-08-04)

Board claimed "Phase 4-7 COMPLETE, all BE/FE/INT/TEST ✅" (35.7% coverage).
2-minute probes found:

| Probe | Result | Task |
|---|---|---|
| `find docs -iname '*integrat*'` | nothing | GAP-001: write docs/INTEGRATION.md |
| `find docs -iname '*api*'` | nothing | GAP-002: generate docs/API.md from specs |
| `go test -short ./...` (120s timeout) | hung | GAP-003: suite too slow, recursive-CTE test suspect |

Committed `9b71507` ("stand-in: gap push"), foreman at CooldownS=900,
DuckBrain `/stand-in/2026-08-04/hermes-canopy`. Total elapsed ~10 min.

**Pattern:** green tests + complete board ≠ done. Missing docs/integration
guides/usability are invisible to the foreman's own audit — they only surface
when someone (or something) asks the basic questions and writes the answer as
tasks.

## Rules Recap

- NEVER fix code — findings become tasks, foremen fix. The stand-in is the
  poke, not the worker.
- NEVER re-enable disabled projects (human intent).
- If a target is mid-tick (check `/api/v1/ticks`), skip conflicting board
  writes, just log observations.
- Time-box: ~20 min/project, ~40 min total per wake.

## Related

- `references/closed-loop-audit.md` — the deeper dogfood variant of this idea: when a
  lane has filed rows for many cycles, audit whether ANY row ever produced a fix
  (tick ledger commits, row-fate census, deployed-tool mtime vs fix-row dates,
  queue-board consumer check). A write-only board is a P1 finding of its own.
- `references/api-surface-probing.md` — isolation-probe ladder for tool/engine targets.

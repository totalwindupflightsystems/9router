---
name: coding-hermes-map
description: THE router for the coding-hermes fleet — complete skill inventory with WHEN-to-load logic. Load this + coding-hermes-foreman at tick start; pull other skills lazily per phase. Never preload the whole toolbox.
version: 2.1.1
author: Bane + Hermes
platforms: [linux]
metadata:
  hermes:
    tags: [coding-hermes, map, router, navigation, cost]
---

# Coding Hermes — Skill Map v2 (ROUTER)

**Doctrine (Bane 2026-08-23):** a tick starts with ONLY this map + `coding-hermes-foreman`.
Every other skill is pulled on demand with `skill_view` at the moment its phase starts.
Preloading 17 skills costs ~166K tokens per API call across the fleet — the map exists so
you never do that again.

**How to use this map:** read the phase you are in, load the skills that phase lists,
do the work, and only keep them loaded while the phase runs. When a phase ends, you may
stop re-reading its skills (they stay in your context but you stop consulting them).

---

## Tick flow — what to load, when

| Phase | When | Load (skill_view) |
|---|---|---|
| **Start** | Every tick | `coding-hermes-foreman` (core loop) + THIS map. Nothing else. |
| **Self-heal** | Before any git work | `coding-hermes-self-heal` if repo state is dirty/unknown |
| **Board read** | First action after start | `coding-hermes-board` (board semantics; JSONL vs DuckDB) |
| **Task pick** | Board has actionable rows | `coding-hermes-model-router` (task→model/provider) + `coding-hermes-worker-model` (worker capability routing) |
| **Idle verdict** | Board empty / only fixtures | `coding-hermes-discovery` (gap scan) then `coding-hermes-never-done` (perpetual audit). Do NOT load work-phase skills. |
| **Work dispatch** | Task needs code | `worker-brief-authoring` (one-message brief + trace handoff) + `coding-hermes-worker` and `coding-hermes-traceability` (preload both unless `--ignore-rules` is used; that flag suppresses skills, so the one-message brief must carry the full marker contract) + the project's `coding-hermes-foreman-<project>` skill. Every brief names the owner row, spec/use-case, test/manual procedure, expected evidence, and required `ch:trace`; add a Tier2 criterion to verify it. For repos with a pre-eval trace gate, use its documented task-ID mapping and persist the marker plus closeout block in the required board field before judging. ≥2 eligible independent rows → wave with worktrees (foreman skill §Parallel Ticks: middle-out partition test + hygiene + merge checklist) |
| **Debugging** | Error during work | `systematic-debugging`, then `off-by-one` (pre-solve lab) BEFORE designing fixes |
| **GitHub/CI** | Before push, CI checks | `github-pr-workflow`, `github-repo-management` |
| **Verify/commit** | Before every commit | `gitreins` (guard battery) — never skip |
| **Claim completion** | About to write "done", close a row, or commit a close-out footer | `coding-hermes-traceability` — validate the worker's marker against the owning row/spec/test/evidence and preserve QA/dogfood regression IDs. T3 (invoked and observed) is the minimum for "done"; T0–T2 alone never close a row; every claim carries a witness or explicit `none:<reason>`. Require `STATUS: / TIER: / EVIDENCE:` and a Tier2 criterion before closing. |
| **Judge cap / INCOMPLETE verdict** | Tier 2 verdict INCOMPLETE with `Cap exceeded: Input token budget (...)` | DISCOVER FIRST: pre-solve slug `gitreins-tier2-input-token-cap-exceeded` (corpus answer: raise the cap a rung) + skill `gitreins-cap-sizing`. Do NOT re-derive this from first principles — it costs a wasted diagnosis. Check EVERY location the knob is defined (`defaults:`, `evaluator:`, and the combined `evaluator.cap` string) |
| **Judge runs longer than the tool window** | `gitreins task complete <id>` killed mid-Tier-2 (big Go/JS suite: state flips, NO verdict.json) | Do NOT re-run it foreground: `gitreins task complete <id> --force --skip-tier2` (fast flip) then `gitreins judge --async <id>`, poll `gitreins judge --status <job-id>` on later calls. `coding-hermes-foreman` → `references/gitreins-judge-async-for-long-tiers.md` |
| **Cron context** | Running as cron | `coding-hermes-cron` (cron pitfalls) |
| **Impact analysis** | Need dependency graph | `hilo-usage` |
| **Fleet memory** | Need cross-session context | `duckbrain` / `duckbrain-memory` / `duckbrain-http-access` |
| **Reports/delivery** | Client-facing output | `client-demo-delivery`, `live-demo-delivery`, `reporting-delivery` |
| **Board maintenance** | Appending events/rows (use the board appender) | `coding-hermes-board` + `jsonl-foreman-board-reading` + `coding-hermes-jsonl-board-append` |
| **Board surgical edit** | Closing/updating a row in a tracked JSONL (status, commit_hash, worker_summary, etc.) | `git-tracked-jsonl-editing` (mandatory — full-file `json.loads`→`json.dumps` re-serializes untouched rows and churns the file; proven across the fleet 20+ times, see the skill's references) + the project's `coding-hermes-foreman-<project>` skill (project-specific board style: tasks.jsonl separators, events.jsonl detail-as-string vs detail-as-object, board.jsonl compact vs pretty-printed — every project has at least one non-default quirk the generic skill cannot infer) |

## Heavy docker multiarch builds → bunker-las-03 (fleet-wide rule, 2026-08-31)
ANY heavy docker build (a `--platform linux/amd64,linux/arm64 --push` buildx run, or any docker build whose arm64 leg runs under qemu) goes on **bunker-las-03** (`bunker3` ssh alias, 100.69.3.13 — the fleet CI box), NEVER the primary host: qemu-aarch64 emulation pegs cores for hours (rethinkdb 2026-08-31: 4+ cores until killed; kobayashi-maru same day: load 56). The box is provisioned (docker group, qemu binfmt 31 arches, buildx `rt-ci-001` docker-container builder, ghcr login via stdin). Build form: `ssh bunker3 'cd <repo> && git pull -q && docker buildx build --builder rt-ci-001 --platform linux/amd64,linux/arm64 --push ...'`. Setup + retry-loop enforcement: devops/bunker-deployment refs/multiarch-ci-build-box.md + refs/multiarch-builds-on-ci-box.md. Enforcement when a local build appears anyway: kill the client, then `docker buildx rm <builder>` on the primary so re-dispatches fail in ~1s.

## Project foreman-ops skills (load the one matching your project)

**Canonical name: `coding-hermes-foreman-<project>`** (fleet migration in progress). The legacy
`coding-hermes/<project>-foreman-ops` name still resolves for projects not yet migrated — try the
canonical name first, fall back to legacy. These skills are **LOCAL-ONLY** (fleet disk; never
shipped to the public repo) and carry project-specific boards, gates, pitfalls, and the
project's DuckBrain namespace.

DuckBrain read/write mechanics for every tick: `coding-hermes-foreman-duckbrain-usage`.
(`skill_view('coding-hermes/coding-hermes-foreman-<project>')` when your tick's project matches.)

9router · ai-plays-poke · asce · bunker · chimera · crier · dexdat-core · dexdat-memory ·
duckbrain · escalation-doctrine · h3-shim · h3-sdk-go · h3-sdk-python · h3-sdk-typescript ·
h3-umbrella · heading · helios · helix · hermes-canopy · hermes-dagger · hermes4friends-infra ·
imhotep · inference-estimator · kobayashi-maru · mafia-ai-benchmark · muster · musterflow ·
coding-hermes-tools · my-project · off-by-one · rabbit-hole · ring-runner · speclang
totalstack · uhlp · warpfs · wojons-mythos · coding-hermes-scheduler (the scheduler itself)

## Complete coding-hermes inventory (all verified existing)

**Orchestrator / core**
- `coding-hermes-foreman` — full SDLC tick loop. EVERY tick.
- `coding-hermes-map` — this router. EVERY tick.
- `coding-hermes-bankai` / `bankai-mode` — full-auto fleet mode (Bane-driven, not ticks)
- `coding-hermes-project-ops` / `coding-hermes-project-bootstrap` — project lifecycle
- `coding-hermes-worker` — worker spawn rules
- `coding-hermes-worker-model` — worker model selection
- `coding-hermes-model-router` — task decomposition + model routing
- `coding-hermes-supervisor` — fleet-level maintenance cron
- `coding-hermes-north-star` — management plane

**Board & data**
- `coding-hermes-board` — workboard semantics (DuckDB + JSONL)
- `coding-hermes-jsonl-board-append` — appender usage
- `jsonl-foreman-board-reading` — reading JSONL boards
- `git-tracked-jsonl-editing` — **mandatory before any row-update/commit to a tracked JSONL**; full-file rewrites churn (mixing key orders, escaping, separators, nested `detail`); byte-preserve untouched lines via per-line round-trip
- `coding-hermes-idle-tick-audit` — idle-tick audit pattern
- `foreman-tick-verification` — verify tick rows/commits
- `pm-injected-board-rows` — stand-in PM row injection
- `coding-hermes-contradictory-tests` — resolving contradictory tests
- `coding-hermes-ledger-analysis` — stand-in PM ledger
- `coding-hermes-project-check-in` — fleet check-in
- `coding-hermes-board-external-injection` — cross-project board coordination
- `fleet-gap-verification` — gap proposals from PM digest
- `docs-board-gap-remediation` — docs-vs-reality board triage
- `scheduler-db-audit` — scheduler DB value/cost audit
- `coding-hermes-testing` — front-to-back testing battery

**Idle & discovery**
- `coding-hermes-discovery` — finds work when board is empty
- `coding-hermes-never-done` — perpetual audit loop (FAT — 97.8K, trim in progress)
- `never-done` — legacy alias (same loop)

**Cron & scheduling**
- `coding-hermes-cron` — canonical cron shape for the fleet
- `coding-hermes-cron-schema` — shared cron schema
- `coding-hermes-scheduler` / `coding-hermes-foreman-coding-hermes-scheduler` — scheduler project itself
- `coding-hermes-broker` — weight-budget scheduling model
- `coding-hermes-foreman-coding-hermes-scheduler` — scheduler ticks
- `fleet-scheduler-http-api` — scheduler HTTP API queries
- `coding-hermes-self-heal` — pre-tick repo hygiene (load when repo state uncertain)
- `sibling-tick-collision-recovery` — collision handling
- `foreman-pipeline-unblocking` — deadlock breaking
- `worker-interruption-recovery` — dead worker resume
- `delegation-orphan-recovery` — orphaned commits
- `concurrent-agent-collision` — zero-write stop on collisions

**Skills/shipping**
- `coding-hermes-skills-shipping` — sync fleet skills to public repo
- `coding-hermes-skill-publishing` — publish to public repo
- `coding-hermes-dogfood` — value discovery via real use
- `coding-hermes-config` — fleet config handling
- `coding-hermes-goimports-local-prefixes-pitfall` — gofmt pitfall

**Delivery**
- `client-demo-delivery`, `live-demo-delivery`, `fleet-report-publishing`, `reporting-delivery`,
  `client-deliverable-reports`, `client-deliverable-html-reports`

**Common non-coding-hermes skills the ticks pull**
- `systematic-debugging` (debug phases) · `trust-but-verify` (verification) ·
  `reality-validation` (claims) · `github-pr-workflow` / `github-repo-management` (git/GitHub) ·
  `claude-design` / `popular-web-designs` (UI work) · `hilo-usage` (graph analysis) ·
  `gitreins` (guard battery) · `off-by-one` (pre-solve lab) · `duckbrain-memory` /
  `duckbrain-http-access` (memory) · `hermes-dagger` / `dagger-development` (DAG work)

---

## Two-tier architecture (Bane 2026-08-23): CORE skills + DATA skills

Every coding-hermes skill is one of two tiers:

**CORE skill** — general, public-ready, ≤50K. Ships to the public
`coding-hermes/skills` repo so anyone can clone and use it without knowing our
system. Rules:
- Generic workflow, triggers, pitfalls that apply to ANY user of the skill
- A project hint is allowed at most at 10–100 tokens (e.g. "scheduler projects
  may pin cooldowns in fleet.toml") — NOT every project needs the scheduler's
  details, and no project section belongs in a shared core skill
- Zero internal paths, names, or project lore (shipping sanitizes: no real
  names, /home/kara→~, private names→<project>, see coding-hermes-skills-shipping)

**DATA skill** — project-specific detail, internal-only, never shipped (or
shipped as an empty stub). Rules:
- Named `data/<project>-<topic>` or lives as the project's `coding-hermes-foreman-<project>` skill
- Loaded ON DEMAND: the core skill (or the map) points to it; the agent calls
  it only when working on that project/topic
- **If a data skill exceeds ~50K, split it by project first, then by topic**:
  `data/imhotep-ns-sync`, `data/imhotep-gitlab`, … — every agent finds exactly
  what it needs and never loads another project's bullshit

**Routing chain:** map → core skill → (only if needed) data skill. The map's
phase table lists both: `skill` = core load, `data:<name>` = on-demand detail.

Fat skills (98-99K) get split so the map routes to ONLY the needed part:
1. SKILL.md stays ≤50K: trigger, quick workflow, key pitfalls, **pointer to references/**
2. Detail corpora (tick logs, per-tick learnings, full pitfall lists) move to `references/<topic>.md`
3. The map entry for that skill gains a "load `references/<topic>` when <sub-task>" line

**NO CROSS-PROJECT POLLUTION (Bane 2026-08-23):** shared skills must never carry
project-specific sections. A general skill (duckbrain-memory, coding-hermes-board, etc.)
that contains another project's conventions (e.g. imhotep ×37 in duckbrain-memory) wastes
tokens on every load and confuses the agent with foreign context. Rules:
- Project-specific content → that project's `coding-hermes-foreman-<project>` skill or its own `references/`
- Shared skill keeps generic content only + a one-line pointer ("imhotep ns sync: see coding-hermes-foreman-imhotep")
- Audit heuristic: grep a shared skill for other project names; ANY hit with a content
  section (not a passing example) = move it out
- Examples that TEACH a pattern (model routing by project type) are OK if kept to 1-2 lines

Do NOT trim alone — a trimmed skill that lost detail fails Bane's "don't lose anything" rule.
Always: move, never delete; verify the reference loads; keep the map pointer updated.

## Verification

- After any map edit: every skill name referenced MUST exist (`find ~/.hermes/skills -name SKILL.md -path "*<name>*"`)
- A tick using this map loads ≤3 skills in its first 5 calls (map + foreman + board)
- **Map freshness (existence is not coverage).** `skill-health.py` (3-day cron) now flags every fleet-named
  skill whose `SKILL.md` is *newer than this map* and is not routed here. A skill nobody routes to is
  invisible to a tick — exactly how `coding-hermes-traceability` stayed unrouted while it was made
  load-bearing. When the flag fires: add a phase row or a pointer line, or the skill does not exist in practice.
  Any agent that adds, renames or retires a fleet skill MUST route it here in the same change (Axiom does this in
  AGENTS.md for `axiom-capability-surface`: the surface skill is updated by whoever widens the surface).

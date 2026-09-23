---
name: coding-hermes-fleet-topology
description: "Use when aligning the fleet planet/moon topology."
version: 1.0.0
platforms: [linux]
metadata:
  hermes:
    tags: [coding-hermes, fleet, topology, lanes, scheduler, alignment]
    related_skills: [coding-hermes-map, coding-hermes-foreman, coding-hermes-supervisor]
---

# Coding Hermes Fleet Topology — planets, moons, debris

**The model (Bane's):** Hermes is the **sun**. Each project is a **planet**. Each planet
carries one **moon per satellite lane**. Cron jobs are loose **debris** — asteroids and
comets that pass through, not part of the orbit.

```
SUN      Hermes (the runtime, the skills, the gateway)
PLANET   an enabled base project row          e.g. auger
MOON     a satellite lane on that planet      e.g. auger-qa, auger-dogfood, auger-sync
DEBRIS   cron jobs / one-off rows             e.g. secret-scan, CVE-scanner
```

**The invariant: every enabled planet carries exactly ONE moon of each type.**
A complete fleet is a clean rectangle, not ragged numbers. Five moon types today:
`-qa`, `-dogfood`, `-pm`, `-releng`, `-sync`.

The satellite lane *scripts* on disk (`qa-scheduler-tick.sh`, `dogfood-scheduler-tick.sh`,
`dagger-role-tick.sh`, `sync-scheduler-tick.sh`) are the **RETIRED dagger path**. The live
lanes are **skill-driven sessions** — the scheduler spawns them from the `projects.prompt`
column, and each prompt names the skill to load and says *"NOT via a driver script"*.
Never reason about a lane from a script on disk; read the row.

## Where the truth lives

| Fact | Source |
|---|---|
| Which lanes exist / are enabled | `~/.hermes/coding-hermes/scheduler.db` → `projects` (name, enabled) |
| What a lane DOES | `projects.prompt` — the live instruction, per lane |
| Which skill it loads | named in that prompt |
| Lane config (cooldown, weight, ns, deliver) | the row's columns |
| `projects.command` | **empty by design** for skill-driven lanes — never judge a lane by it |

## Row-name contract

- planet: `<project>`
- moon: `<project>-<lane>` (e.g. `auger-qa`)
- **Service rows are NOT planets** and own no moons: `qa-audit` (fleet random-discovery QA),
  `release-engineer` (the release lane), `dogfooding`, `stand-in`. A `0/5` for these is correct,
  not a gap.
- **Orphan moons are legitimate**: a `-sync` lane whose planet is not enabled is a *namespace*
  sync (e.g. `coding-hermes-sync`, `reports-sync`, `eduos-sync`). Don't "fix" those by inventing
  a planet.

## Lane → skill map

| Moon | Loads | Per-planet lower level |
|---|---|---|
| base | `coding-hermes-foreman` | `coding-hermes-foreman-<project>` |
| `-qa` | `qa-foreman-ops` | (none yet — see Gap 3) |
| `-dogfood` | `coding-hermes-dogfood` | (none yet) |
| `-pm` | `coding-hermes-project-manager` | (none yet) |
| `-releng` | `coding-hermes-releng` | (none yet) |
| `-sync` | `context-sync-duckbrain` | `<project>-sync-data` + `<project>-namespace` |
| any DuckBrain-touching moon | `coding-hermes-foreman-duckbrain-usage` (shared contract) | — |

## The audit + resolve tool

```bash
P=~/.hermes/skills/coding-hermes/coding-hermes-fleet-topology/scripts/fleet-topology-audit.py
python3 $P                # human report: gaps, orphans, skill wiring
python3 $P --json         # machine-readable (what the warden cron consumes)
python3 $P --apply --dry  # show the exact row payloads that would be created
python3 $P --apply        # CREATE the missing moons (clones an enabled same-lane sibling)
```

It checks four things:
1. **Moon completeness** — planets missing a lane (or with a disabled one).
2. **Orphan moons** — lanes whose planet is not enabled (informational; expected for namespaces).
3. **Skill wiring** — does each moon's live prompt actually name its skill? A moon whose prompt
   never names the skill it is supposed to follow is a **silent** misalignment: the lane runs on
   the model's guess instead of the procedure.
4. **Moon runnability** — does the moon's stand-in workdir exist, with its `.coding-hermes/board`
   symlinked to the PLANET's board? Resolve the target from the planet's OWN `workdir` (names ≠
   paths — `coding-hermes-scheduler` lives at the nested `coding-hermes-scheduler/coding-herms-scheduler`,)
   not from `/home/kara/<name>`. `--apply` provisions both.

### Fixing a gap: resume, don't recreate

A "missing" moon is often a **disabled existing row** (a planet pause pauses its moons: 
`disabled_reason: "paused by target <planet>"`). Recreating it hits `409 project already exists`.
The script checks for an existing row first and calls `POST /projects/{name}/resume` instead —
which also preserves that row's own workdir (some rows legitimately deviate, e.g. `duckbrain-qa`
lives at `stand-in/qa/duckbrain` because `pm` took `stand-in/pm/duckbrain`).

### API contract gotchas (learned live)

- **`enabled` must be a JSON BOOL.** SQLite stores it as `0/1`; POSTing the int returns
  `400: cannot unmarshal number into Go struct field projectAlias.enabled of type bool`. Same for
  `adaptive_cooldown` and `no_global_fallback`.
- **ONE enabled project per workdir** (409, case-insensitive). The lane workdir templates are NOT
  what their names suggest: `qa` → `stand-in/pm/<p>` while `pm` → `stand-in/pm-lane/<p>`; `releng` →
  `stand-in/releng-lane/<p>`. If the canonical dir is taken, fall back to a lane-scoped one.
- **Always surface the HTTP body on error.** A bare "HTTP 400" hides the validation message; the
  script now reads `HTTPError.read()` and prints it.
- `fleet.toml` is written ONLY by `fleet-cooldown-policy.py` — never hand-edit it. After creating
  or resuming lanes, check drift (DB-enabled set vs toml set, both directions + the enabled flag)
  and `--verify` the canonical pins; regenerate with `--apply` if they disagree.

`--apply` is safe and idempotent: it clones an **existing enabled sibling of the same lane**
(so cooldown/weight/namespace/deliver/prompt shape all match the fleet's proven form), retargets
the project name in `repo_url`, `workdir` and `prompt`, and POSTs to `/api/v1/projects`.
It never edits an existing row. Re-run the audit afterwards — `gaps == []` is the proof.

## The resolving loop (why a static alerter is not enough)

The fleet has static watchdogs (arming tripwire, skill-health) that **alert** but do not **act**.
Alignment drift needs a loop that *resolves*: audit → create/fix → verify → report. That is the
**Fleet Topology Warden** cron (agent-backed, `no_agent=False`): it runs the audit, applies the
fix for any gap, re-audits to prove `gaps == []`, and reports what it changed.

A no-agent cron can only print the gap. An agent cron closes it.

## Pitfalls (learned the hard way)

- **Never infer a lane's behaviour from a script on disk.** The dagger scripts are retired; the
  prompts explicitly forbid them. Read `projects.prompt`.
- **`projects.command` is empty for skill-driven lanes** — an empty command is NOT "unwired".
- **Ragged counts are the symptom, not the census.** If qa=16 and dogfood=17 against 21 planets,
  that difference IS the gap report.
- **A lane with an empty prompt is broken**, not defaulted — scheduler rows with `prompt=''` have
  nothing to run.
- **Don't create a moon for a service row** and **don't invent planets for orphan namespace syncs**.
- Retarget prompts by substituting the project token, but verify the rendered prompt in `--dry`
  before applying — the template's grammar is per-lane.

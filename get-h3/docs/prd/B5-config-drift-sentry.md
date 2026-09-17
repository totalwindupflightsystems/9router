# PRD: `h3-sentinel` — Config-Drift Sentry

**Project:** get-h3 · agent-ops line · **Item:** B5 (added) · **Author:** Kara-agent · **Date:** 2026-09-17
**Status:** proposed · **Effort:** M (~2 weeks) · **Depends on:** nothing · **Feeds:** B4 digest (drift section), B3 runbooks

---

## The one-liner

A registry of every config file that *matters* on a fleet box — with provenance, expected-drift rules, and tripwires — that catches the moment a config diverges from what the operator last blessed, **before** the next restart turns drift into an outage.

## The problem, measured

**Case file 1 — the `.env` wipe (2026-09-16):** 9router's repo `.env` was overwritten by its `.env.example` twin (byte-identical size, same mtime — a stray `cp`). All four federation secrets became placeholders *on disk* while the running container kept the real ones. Discovery was pure luck (a 401 during unrelated wiring). **One restart would have broken central↔edge auth fleet-wide, silently, with no error pointing at the cause.** The repair — pulling secrets back out of the running container — was hand-crafted, unreproducible, and is now only recorded in a chat log.

**Case file 2 — the cooldown-pin drift (SCHED-GAP-121):** an operator set a 900s cooldown in the live DB; the policy regenerator kept rewriting 7200 from `fleet.toml`. Two stores, one truth-shaped lie — the pin silently reverted on every restart until the dual-store `--verify` tripwire was hand-built. Cost: weeks of a project running at 8× its intended cooldown with nobody able to say why.

**Case file 3 — the sibling revert:** a shared `.gitreins/config.yaml` evaluator pin was silently reverted by a sibling foreman's merge; the wrong model served until noticed days later. Config changes have **no ownership trail** in git — the log says a merge touched the file, not that a *semantic pin* was undone.

The pattern: fleet boxes carry dozens of load-bearing configs (env files, TOML, YAML, unit drop-ins), mutations come from agents, siblings, upgrades, and stray `cp`s, and **the failure only surfaces at restart — the worst possible moment.**

## User stories

**US-1 (the operator's blessing):** As Bane, after fixing the `.env` mess I run `sentinel bless /home/kara/9router/.env --class secrets` — the file's current content-hash is registered. Any later change without a fresh bless is *drift*, reported with a unified diff at next check-in.

**US-2 (the restart insurance):** As the agent about to `systemctl restart` a daemon, I run `sentinel check --unit 9router-central` first: it diffs every registered config feeding that unit against blessed state and blocks/warns *before* the restart bakes the drift in.

**US-3 (the semantic-pin guardian):** As the fleet, I declare pins beyond raw hashes: `sentinel pin scheduler.db projects.cooldown_s --where name=h3 --expect 21600` — value-level, store-level expectations (the SCHED-GAP-121 tripwire generalized to any SQLite/TOML pair), verified on schedule.

**US-4 (the archaeologist):** As the responder asking "who changed this and when?", `sentinel history /home/kara/9router/.env` shows every observed mutation with timestamp, mtime evidence, and the diff — even when git isn't watching the file (env files never are).

## What it registers

| Class | Examples | Check |
|---|---|---|
| secret-env | 9router/.env, gateway env files | hash + required-keys-present + placeholder-detector (`.env.example`-twin detection: entropy + `changeme`-class values) |
| daemon-toml/yaml | fleet.toml, schedulerd.toml, .gitreins configs | hash + semantic pins (declared values at declared paths) |
| dual-store pairs | DB column ↔ toml key | value agreement per pin (both directions) |
| unit drop-ins | systemd overrides | hash + effective-unit diff (`systemctl cat`) |

**Design rules:**
- **Blessing is explicit; observation is ambient.** File watching (inotify) records mutations continuously; drift is only *declared* against blessed state. No blessing = monitor-only, so adoption is zero-risk.
- **Placeholders are their own alarm class:** the `.env.example` clobber is detectable *without* a prior bless (placeholder heuristics) because it's the highest-severity, most-recurring failure in fleet history.
- **Restart-coupled checks:** a tiny exec shim (or documented pre-restart hook) makes "check before you restart" the path of least resistance for agents.
- **Provenance is the product:** every observed change is appended (JSONL, git-friendly) — the fleet's append-only doctrine applied to config.

## Interface

```
sentinel register <path|--unit name> --class <class>
sentinel bless <path> [--note "..."]
sentinel check [<path>|--unit name|--all] [--json]
sentinel pin <store.path> --expect <value>     # semantic, value-level pins
sentinel history <path>
sentinel daemon                                 # inotify watcher + scheduled pin checks
```

## Success criteria

1. **Replay the `.env` clobber:** with sentinel live, the `cp .env.example .env` fires a placeholder-class alarm within seconds of the write — hours before any restart could have baked it in.
2. **Replay SCHED-GAP-121:** the value-pin check reports `db=900 toml=7200 MISMATCH` on every scheduled run until reconciled — the tripwire exists without hand-building it per case.
3. Fleet coverage: ≥15 load-bearing configs registered on this box within a week of install, with ≥3 live-class pins.
4. Zero false alarms after the first tuning week (drift alarm precision ≥95% — the GAP-061 desensitization lesson: alarms that cry wolf get uninstalled).

## Why get-h3 / why open

Every multi-agent fleet has this wound: configs mutated by many hands, failures deferred to restart time. Existing tools (etcd, consul, chef) solve fleet-scale config *management*; nothing solves single-box config *custody* for heterogeneous files + DBs + units with provenance. The placeholder-detector heuristic and the dual-store pin pattern are fleet scar tissue — shipping them is the value.

## Risks

- Hash churn from legitimate writers (installers, schedulers) → per-path "expected writers" allowlist; noisy paths get observation-only mode instead of alarms.
- Bless-staleness (blessed state itself becomes wrong) → bless requires `--note` and surfaces age; blessing is a moment of accountability, not a fire-and-forget.
- Scope creep toward full config management → hard line: sentinel never *writes* configs, only witnesses them.

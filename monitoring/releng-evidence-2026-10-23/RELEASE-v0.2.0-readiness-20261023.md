# fleet-monitoring v0.2.0 — release readiness record (tick monitoring-releng-2026-10-23-03-42-40)

Decision: **NO-CUT** — the version is decided and the gate is green, but two P1 code-level
blockers make the tagged tree a regression versus what is already shipped/deployed.
Standing releng authority covers the cut itself (patch/minor); the blockers are technical.
Cut row: **RELEASE-MON-015**. Blockers: **RELEASE-MON-009**, **RELEASE-MON-010**.

## Target resolution

| Item | Value | How |
|---|---|---|
| Lane workdir | `/home/kara/.hermes/stand-in/releng-lane/monitoring` | board symlink only, NOT a git repo |
| Release target repo | `/home/kara/fleet-monitoring` | `git rev-parse --show-toplevel` → standalone checkout |
| Remote | `https://github.com/totalwindupflightsystems/fleet-monitoring.git` (private) | `git remote -v` |
| Default branch (GitHub) | `master` @ fc6b40af4 (2026-10-14T20:01:07Z) | `gh repo view --json defaultBranchRef` |
| Active branch | `main` @ be7b1f8 (after this tick's landing) | `git ls-remote origin refs/heads/main` |
| Last release | tag `v0.1.0` → af05dee (2026-09-28), Release object present, assets [] | `git ls-remote --tags origin` + `gh release view v0.1.0` |

## Semver decision

`v0.1.0..origin/main` = **24 commits**: 3 `feat`, 11 `fix`, 4 `docs`, 3 `merge`, 2 `chore`,
1 non-conventional (MON-GAP-009 blackbox probe stack). BREAKING markers: 0.

feat present, no breaking → **MINOR → v0.2.0**. (Earlier sweeps' `v0.1.1`/`v0.1.2`
proposals were bucket errors: a feature addition is not a patch.)

```
$ git log --oneline v0.1.0..origin/main | sed -E 's/^[0-9a-f]+ //' \
    | grep -oE '^[a-zA-Z]+(\([^)]*\))?!?:' | sed 's/(.*)//' | sort | uniq -c | sort -rn
     11 fix:
      4 docs:
      3 merge:
      3 feat:
      2 chore:
```

## Readiness criteria (four, all checkable)

| # | Criterion | Verdict | Evidence |
|---|---|---|---|
| 1 | Gates green on the exact sha | **GREEN (local only)** | No `.github/workflows` exists → `gh run list` = `[]` for the repo's whole life. Substitute: `make test` (Makefile:132 tier1 = terraform fmt/validate, compose config, shellcheck, yamllint, prometheus/alertmanager/loki/alloy config, alert-router self-test) **RC=0, "0 check(s) failed"** at 17e8bc1 and again at be7b1f8 in worktree `/home/kara/fm-wt-releng-v020`. Logs: `gate-17e8bc1.log`, `gate-be7b1f8.log`. |
| 2 | Changelog written | **FAIL** | `CHANGELOG.md` newest heading `## 0.1.0 — 2026-09-29`; 24 commits unrecorded, no `Unreleased`. Not promoted this tick: a version heading is a claim, not a receipt, and no tag will exist. |
| 3 | No open P0/blocker | **FAIL** | RELEASE-MON-009 (P1), RELEASE-MON-010 (P1), plus open MON-DOGFOOD-041 (P1, same drain class) and QA-MONITORING-007 (P3, upgrade cell cannot exercise a release). |
| 4 | Version staged | **PASS by construction** | No version constant in the tree (only docker/OS strings match `0.1.0`); tag and newest CHANGELOG heading are the only stamps that must agree. |

## Release surface — three layers (verified live)

| Layer | State | Command |
|---|---|---|
| Annotated tag | ✔ `v0.1.0` on origin = 8c809ca → af05dee | `git ls-remote --tags origin` |
| Release object | ✔ draft:false, assets [], body "Release of fleet-monitoring v0.1.0 (tag af05dee, first cut)." | `gh release view v0.1.0` |
| Build artifacts | n/a by precedent — compose/ops repo, no registry artifact | RELEASE-MON-015 reasoning |

## Blockers (both live in the tree that would be tagged)

**RELEASE-MON-009 — divergent lineages.** `merge-base(master,main)` = 4c9d39b; 12 commits
each way. main lacks master's `scripts/bootstrap.sh` MON-GAP-023 fix
(`SPOOL_HOST_DIR` + `chown 10001:10001`; main's bootstrap has a bare `mkdir -p`, so a fresh
host's alert-router fails its first spool write with EACCES), `stack/cost-exporter/*`,
`stack/grafana/provisioning/dashboards/bunker.json`, `verify.sh` MON_BASE_URL. master lacks
main's REV19 alert-path verification, `tempo/`, the compose override, and the capacity lane
fix. Tagging either branch ships the other's regressions.

**RELEASE-MON-010 — the shipped drain is the defective one.**
`scripts/drain-board-rows.sh` (75 lines, on main and on the host, md5
e7f3eb40bd542c49a22a229b8844f60a) does `rm -f "$SPOOL"/*RESOLVED*` (line 25) and always
appends to `<lane>/.coding-hermes/board/tasks.jsonl` (line 56), while
`stack/alert-router/router.py:13,381` promises resolutions land in `events.jsonl`. The fix
(374-line script with `rtype == alert-resolved` routing at :336-337, dedupe against
events.jsonl ∪ tasks.jsonl at :216-231) exists only in `~/.hermes/scripts/`. `grep -c
alert-resolved` on the repo copy = 0.

## Landed this tick (mechanical prep, verified before merge)

Merged `ft/qa-monitoring-009-reconcile` (3f0e5ba) into main in the isolated worktree
`/home/kara/fm-wt-releng-v020` → **be7b1f8**, pushed to origin/main (ls-remote == local
HEAD), primary checkout fast-forwarded.

Proof of correctness: the branch's `alerts/rules/capacity.yml` is byte-identical to
`fleet-monitor:/root/fleet-monitoring/alerts/rules/capacity.yml` except one annotation line
(`capacity-live-vs-qa-branch.diff` = 1 line). Before the merge, main labelled all 5 capacity
rules `lane: hermes-fleet-ops` — a lane with NO board (MON-DOGFOOD-002) — and was 49 lines
behind production (`capacity-live-vs-main-before-merge.diff`). README-020 was closed as
"fixed" on 2026-10-09 but this file was never synced: a 14-day false closure. After
be7b1f8: 19/19 rules label `lane: monitoring`, matching host-health.yml and probes.yml
which already matched the host.

## Board-row discipline (changelog → commits → rows)

Every user-facing change in the delta names a board row: `feat(monitoring): MON-GAP-007 —
scheduled fleet inventory sweep`, `feat: reconcile QA-MONITORING-009 — port alert-router
live-state check`, `feat(containers): cadvisor on fleet-monitor (MON-GAP-008 step 1)`, and the
one non-conventional subject `MON-GAP-009: blackbox_exporter + 8 inventory-derived probe
targets …`. All four ids are present exactly once on `.coding-hermes/board/tasks.jsonl`
(`grep -c "\"<id>\""` = 1 each). No unnamed user-facing change → no finding of that class.

Version stamps: the tree carries none (`grep -rnE '^VERSION|APP_VERSION'` across Makefile,
.env.example, stack/docker-compose.yml, README.md = 0 hits; the only `0.1.0` matches are
docker/OS version strings under `scripts/raw/`). Tag and newest CHANGELOG heading are the
only stamps that must agree.

## Path to the cut (next tick owning RELEASE-MON-015)

1. RELEASE-MON-009 — reconcile master→main, name each conflict resolution.
2. RELEASE-MON-010 — fix/retire the shipped drain, prove with a mixed-spool test.
3. Prep commit: `## 0.2.0 — <date>` + fresh `Unreleased`, entries from the 24-commit census.
4. `make test` RC=0 on the prep sha (clean tree; never cut from the primary checkout — it
   carries live-collected residue: .env.example, coverage.json, inventory.json,
   scripts/backup-to-s3.sh modified; .gitreins/, scripts/raw/, stack/cost-exporter/ untracked).
5. Annotated tag `v0.2.0` (does not exist locally or on origin — verified; never force-move).
6. `gh release create v0.2.0 --notes-file <categorized notes>` (assets: none, per precedent).
7. Verify `gh release view v0.2.0` + local gate on the tagged sha. Rollback tag: `v0.1.0`.

## Board hygiene

`boardctl validate` FAIL **14 errors / 1052 warnings** before this tick's writes;
**14 errors / 1060 warnings** after (8 new warnings are the `lane` key on the 8 added rows —
the same key shape neighbouring rows carry). Baseline error count unchanged; the pre-existing
errors are tracked by MON-DOGFOOD-044. Rows closed: RELEASE-MON-003/005/006/007/008
(superseded by 015), REL-MON-007-PROGRESS-20261007 (unblock item landed at be7b1f8).

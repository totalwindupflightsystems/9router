---
name: releases
description: Cut releases via the release-engineer scheduler spawn lane.
version: 1.1.0
author: hermes
license: MIT
metadata:
  hermes:
    tags: [release, semver, scheduler, ci, gh]
    related_skills: [git-release]
---

# Releases — Release Engineering Lane

## When to Use

Use when a `release-engineer` scheduler tick is spawned (manual release request),
or when asked to decide and cut a release from git/CI/dogfood evidence. Not for
routine scheduled work — this lane is manual-trigger only.

Decide and cut software releases (semver minor vs bugfix, occasionally major) from
evidence: git history since the last tag, CI run history, gitreins verdicts, and
dogfood results. Triggered as a scheduler tick (never scheduled — manual only).

## 1. Trigger

This lane runs as the scheduler project `release-engineer` in namespace `releases`:

- **Manual spawn:** `curl -s -X POST http://localhost:9090/api/v1/projects/release-engineer/spawn`
  → 202 `{"status":"spawned","tick_id":...}`. Bypasses cooldown (SpawnNow).
  409 = a tick for this project is already running — report the 409 and wait.
- **Chat request:** Bane says "cut a release for <project>" in chat → same manual
  spawn, with the target project identified in the triggering message thread.
- The 604800s (7d) cooldown is only a natural-cadence backstop; never wait on it —
  spawns are always manual.

If the triggering message thread does not name a target project/repo, STOP and reply
in the delivery thread asking which project to release. Do not guess a repo.

## 2. Evidence Gathering

First, find the last release tag and the target repo:

```bash
# Target repo = the one named in the trigger thread. If the tick workdir IS the
# repo (check `git -C <repo> remote -v`), you may use it directly.
git -C <repo> fetch --tags --quiet
git -C <repo> tag --sort=-v:refname | head -5          # newest tags first
LAST_TAG=$(git -C <repo> tag --sort=-v:refname | head -1)   # verify it's a real release (vX.Y.Z), not an ad-hoc tag
```

Then gather, in order:

1. **Git history since last tag** — categorize by conventional-commit prefixes:
   ```bash
   git -C <repo> log --oneline --no-decorate <LAST_TAG>..HEAD
   git -C <repo> log --oneline --no-decorate <LAST_TAG>..HEAD | grep -cE '^[0-9a-f]+ (feat|fix|perf)'
   ```
2. **CI history** — org/repo comes from `git remote -v` (the on-disk folder name may
   not match the GitHub org):
   ```bash
   ORG_REPO=$(git -C <repo> remote get-url origin | sed -E 's#.*github.com[:/]([^/]+/[^/]+)(\.git)?$#\1#')
   gh run list --repo "$ORG_REPO" --limit 20 --json status,conclusion,displayTitle,headBranch,headSha,createdAt
   # For each of the last N commits in <LAST_TAG>..HEAD, confirm the CI run on that SHA concluded success.
   ```
3. **Gitreins verdicts** — look for verdict.json / gitreins task records for the
   commits being released (`find <repo> -name 'verdict.json'` or `gitreins task list`
   in repos that use it). Only-green verdicts release cleanly.
4. **Dogfood results** — the project's dogfood lane output (duckbrain-sync or the
   pm/dogfood stand-in reports) that exercised the commits since the last tag.

### Semver decision matrix

| Evidence since last tag | Bump |
|---|---|
| only `fix`/`chore`/`docs`/`refactor`/`test` commits | **patch** (vX.Y.(Z+1)) |
| ≥1 `feat` (or `perf` that changes behavior) | **minor** (vX.(Y+1).0) |
| `BREAKING CHANGE:` footer, `!` after type, or 0.x→1.x milestone | **major** — PROPOSE ONLY, require explicit Bane confirmation before tagging |
| red CI on any commit in range / failing gitreins verdict | **no release** — report and stop (unless explicit override, §5) |

## 3. Artifact Detection & Build

Check the repo for its own release tooling FIRST (authoritative — Bane doctrine:
projects should ship a release script and release docs anyway):

1. `scripts/release*`, `release.sh`, `Makefile` targets (`make release`, `make tag`,
   `make build`) — read the release docs/README section about releasing and USE the
   project's own tooling.
2. `.goreleaser.yml` / `.goreleaser.yaml` → `goreleaser release` (Go binaries).
3. `Dockerfile` + registry configured (env: registry creds present, e.g.
   `ghcr.io`/docker login) → `docker build` + `docker push` a version tag. Only push
   if a registry is actually configured — never invent one.
4. `package.json` → `npm run build`/`npm publish`; `pyproject.toml` → `python -m
   build` / upload.

Never invent build steps not evidenced in the repo. If no tooling exists and the
artifact is a Go binary, cross-compile static binaries per the repo's build docs
(`CGO_ENABLED=0 go build` per GOOS/GOARCH) and attach them to the release.

## 4. Cut & Verify

```bash
# Tag from the repo's default branch HEAD, only after evidence passes.
git -C <repo> tag -a "v<NEW_VERSION>" -m "Release v<NEW_VERSION>"            # NEVER -f / force-move an existing tag
git -C <repo> push origin "v<NEW_VERSION>"

# Release notes: categorized (reference the git-release skill for note format —
# New Features / Bug Fixes / Other Changes sections, PR links where available).
gh release create "v<NEW_VERSION>" --repo "$ORG_REPO" --title "v<NEW_VERSION>" \
  --notes-file <notes-file> [--attach <built-artifacts...>]
```

Verify afterwards:
```bash
gh release view "v<NEW_VERSION>" --repo "$ORG_REPO"        # exists, notes, assets present
gh run list --repo "$ORG_REPO" --branch "v<NEW_VERSION>"   # tag CI green
# or: gh run list --repo "$ORG_REPO" --limit 5 --json status,conclusion,headSha — the run on the tag SHA
```

### Release-surface completeness — a tag without a Release object is NOT a release

Before reporting ANY release as shipped (including doc sweeps and board
audits, not just cuts), run the 4-layer check. A failing layer is an OPEN
release-surface defect (file a RELEASE-* row with the layer number), never
a "shipped" verdict:

```bash
git -C <repo> tag -l 'v*'                                        # L1: local tags
git -C <repo> ls-remote --tags origin                            # L1b: tags on the remote
gh release list --repo "$ORG_REPO"                              # L2: Release objects exist
curl -s -o /dev/null -w '%{http_code}' "https://api.github.com/repos/$ORG_REPO/releases/tags/vX.Y.Z"   # L2b: 404 = NO object
curl -s "https://api.github.com/repos/$ORG_REPO/releases/tags/vX.Y.Z" | jq '.assets[].name'            # L3: artifacts present
```

- L1 passes + L2b 404 = the v0.1.0 trap (observed off-by-one 2026-09-22:
  tag on the remote for a day, zero Release objects, zero artifacts, while
  the board recorded the tag as the release). Backfill with `gh release
  create vX.Y.Z --repo "$ORG_REPO" --title ... --notes-file ...` carrying
  real notes and, when the repo has a buildable artifact, assets built from
  the exact tag tree (temp worktree of the tag, the repo's own build recipe,
  ldflags version stamp, `--version` smoke, SHA256SUMS).
- A tag that sits on a chore commit N commits behind HEAD is not
  release-prepared. Prefer a fresh cut from HEAD through the repo's own
  tooling (its release target / script, CHANGELOG section as tag message) so
  the marker lands on a release-prepared commit; backfill the old tag's
  Release object too if consumers may already reference it.
- The shipped verdict requires ALL of: tag (L1b) + Release object (L2) +
  assets (L3) + CI green on the tag SHA. Anything less: report exactly which
  layers are missing, with command output.

## 5. Safety Rules

- **Never release on red CI** without an explicit Bane override naming the failure.
- **Never force-move / overwrite an existing tag** (`git tag -f`, `git push --force
  --tags`) — that rewrites history for anyone holding the old tag.
- **Never cut a major** (or 0.x→1.0) without explicit confirmation.
- If the repo's own release docs/tooling conflict with this skill, the repo wins.
- A tick that cannot decide (missing evidence, ambiguous range) reports the open
  question instead of guessing.

## 6. Reporting

Report to the delivery thread in markdown:

| Section | Contents |
|---|---|
| Target | repo (org/repo), range `<LAST_TAG>..HEAD` |
| Commits | count by category (feat / fix / chore / docs / breaking) |
| CI | verdict per recent run: green count, any failures with run id |
| Dogfood/gitreins | relevant verdicts or results |
| Decision | bump chosen + why (decision matrix row), version `vX.Y.Z` |
| Artifacts | what was built/pushed (or "none — no build tooling found") |
| Release | `gh release view` confirmation + URL |

Keep it tight: a decision table + the release URL is the deliverable.

## 7. Pitfalls

- **A tag is not a release.** L1 can pass green while the Release object
  never existed: off-by-one v0.1.0 sat on the remote for a day with `gh
  release list` empty and `releases/tags/v0.1.0` returning 404 — and the
  project's own board recorded the tag as shipped (2026-09-22). Run the §4
  release-surface completeness check before any shipped verdict.
- **Stale dedicated clone**: the release-engineer workdir clone can lag origin/main by
  100+ commits (observed 150). ALWAYS `git fetch origin` and compare `git rev-list
  --count HEAD..origin/main` before computing the range — the true release range is
  `vX..origin/main`, not `vX..HEAD`. If local main has diverged by board-only commits,
  check out origin/main on a temp branch (never merge/rebase the shared clone); pin the
  tag at origin/main HEAD SHA.
- **Tag-push workflow trigger can silently drop**: pushing a lone tag ref may fire no
  Release workflow run at all (observed 2026-09-16 on coding-hermes/scheduler v1.3.0 —
  two pushes, zero runs, workflow active, perms admin, tag byte-identical in form to
  the tag that triggered v1.2.0's run). Verify a run appears within ~5 min of the push;
  if not, delete/re-push the tag once, then fall back to replicating the repo's release
  workflow steps locally (same GOOS/GOARCH matrix, same ldflags, version smoke test,
  SHA256SUMS) and `gh release create vX.Y.Z --target <commit-sha> --notes-file ...`.
  Never skip the version smoke — a silent -X no-op ships a binary reporting the wrong
  version.

- **409 on spawn** means a release-engineer tick is already running (project
  max_concurrent=1 in the releases namespace). Don't spawn again — report the 409.
- **fleet.toml mirror**: namespace + project live in `/home/kara/.hermes/fleet.toml`
  (re-applied on daemon restart). API changes to the lane should be mirrored there
  or a restart will re-pin old values. The file is auto-regenerated by siblings —
  read it fresh before editing.
- **gh org/repo derivation**: derive from `git remote -v`, never the folder name
  (workdirs differ from GitHub orgs across the fleet).
- **deliver is create-only** in the scheduler API: `ProjectUpdates` has no
  `deliver` field — set it in the POST body or recreate the project.
- **Workdir guard**: two ENABLED projects cannot share a workdir (split-tick
  protection). The release-engineer workdir is a dedicated clone
  (`~/.hermes/release-engineer/repo`), NOT the foreman's board dir.
- Tag ordering: `git tag --sort=-v:refname` sorts semver correctly; plain
  `--sort=-creatordate` can surface backports/old tags first — confirm the "last
  release" is actually the newest vX.Y.Z.

# fleet-monitoring v0.1.0 — release record (tick monitoring-releng-2026-09-29-02-47-35)

Board authorization: RELEASE-MON-002 (explicit gates) + RELEASE-MON-001 (artifact layer).
Cut executed 2026-09-29 02:47–03:12Z. No forge/CI exists (git remote -v empty, verified
on both repo and host) — the repo's own doctrine IS the release surface: annotated tag +
backup-to-s3.sh artifact bundle + restore-check. Used the repo's own tooling, no gh.

## Semver decision
13 commits since inception, all conventional: 4 feat / 7 fix / 2 docs (categorized via
`git log --oneline | awk '{print $2}' | sort | uniq -c`). Every feat is named by board
rows. First cut → v0.1.0. No BREAKING CHANGE tokens.

## Gates (measured, in order)
| Gate | Result | Evidence |
|---|---|---|
| Untracked files | CLEARED | scripts/probe-endpoints.sh committed (shellcheck rc=0) |
| Repo↔host parity | FIXED then VERIFIED | host-health.yml synced from live (OOM kill-scope split MON-GAP-015, lane=monitoring labels); 9/10 other files byte-equal pre-tag |
| Backup scripts | FIXED | repo scripts/backup-to-s3.sh + restore-check.sh were the BROKEN variant (pre-cbc9dcc: wrong volume names prom-data:/prom, cwd climbs out of repo); absorbed host top-level fix (fleet-monitoring_prom-data:/prometheus, cd /..) |
| .bak hygiene | CLEANED | tracked .bak snapshots removed (git rm) |
| make lint | PASS rc=0 | promtool 6 rules, compose OK, shellcheck clean, YAML parse OK, terraform valid — at tagged sha af05dee |
| Tree clean | CLEAN | git status empty at tag |
| Annotated tag | v0.1.0 | 8c809ca → af05dee5953fc0a830f257abafe25e414c740ed9; re-pointed once pre-publication (1b7afd6→8c809ca) while absorbing the backup fix; tag never left the box, no consumer existed — not a force-move of a consumed tag |
| Artifact | PRODUCED | s3://karahermes-hel/monitoring/2026-09-29_030454/ — prometheus-20260929T030454Z-05d5c8a975e8f802.tar.gz (45MB, sha256 37a478d9…), grafana.db.tgz (060f50b4…), fleet-monitoring.bundle (f828f7a3…), MANIFEST.txt, latest pointer |
| restore-check.sh | PASS rc=0 | checksums verify, bundle valid, snapshot tar readable (run on fleet-monitor, live creds) |
| S3 bundle carries the release | PROVEN | clone from the S3-uploaded bundle resolves tag v0.1.0 → af05dee |
| Live stack verify.sh | PASS 6/6 | 10 hosts, 11 rules, loki 9 labels, grafana 2 datasources + 2 dashboards, alert-router write_mode=board |

## Tag propagation
Host repo /root/fleet-monitoring has its own 2-commit history (init + cbc9dcc) and cannot
fast-forward (checked-out master). v0.1.0 fetched into the host repo by ref (no working-tree
change) so the NIGHTLY 03:00Z backup bundle carries the tag from here on. Reconciliation of
the two trees filed as MON-GAP-016.

## CI / gitreins / dogfood
No forge → no CI runs, no gh, no gitreins verdicts on this repo. The repo's own gates
(make lint, scripts/verify.sh, restore-check.sh) substitute, per the releng skill's
forge-detection rule. QA-MONITORING-001 (no secretless first boot) and MON-DOGFOOD-005/006/007
remain open but are NOT release gates for v0.1.0 (no consumer path exists yet).

## Rollback
Previous artifact set: s3://karahermes-hel/monitoring/2026-09-29_030438/ (pre-tag bundle,
HEAD cbc9dcc); restore via scripts/restore-from-s3.sh. Tag rollback: none needed (no
consumers, no forge).

## Open items filed
- MON-GAP-016 (P2): host repo legacy-layout reconciliation — make host a clean clone of the
  repo so repo==host==artifact by construction.
- Bane decision needed: no git remote exists. If this repo should be public/pushed, the
  three-layer release surface completes (tag + Release object + artifact); until then the
  S3 bundle is the only distribution path.

# Verdict: QA-HARNESS-SCOPE-20261004

**Task:** bunker-qa.sh mis-scopes non-git-repo project dirs (subdir of git repo syncs whole parent)
**Evaluated:** 2026-10-04T18:59:53.736619
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✗ tests: scanners: nice=nice -n 10
  ✗ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
- ✗ **tier2**
  - INCOMPLETE
  ✗ bunker-qa.sh launch/run refuses a repo dir whose git toplevel differs from the dir with a product-mismatch error + FAIL evidence cell, unless BUNKER_QA_SUBDIR names the real product subdir, in which case sync is scoped to it; bash -n clean; commit reachable from origin main: The criterion requires BOTH launch and run to refuse. Only launch() was fixed. launch() (lines 2398-2545) has the fix at 2437-2449: BUNKER_QA_SUBDIR scoping (repo="$repo/${BUNKER_QA_SUBDIR%/}"; PROJ=basename) plus subdir refusal with product-mismatch message + FAIL evidence cell — live test `bunker-qa.sh launch /home/kara/monitoring` printed 'ERROR: /home/kara/monitoring is a SUBDIRECTORY of git repo /home/kara ... grade the wrong product' and wrote a FAIL cell. run() (lines 2275-2397) was NOT modified: `grep -c BUNKER_QA_SUBDIR` in run() = 0 (launch() = 5); its repo check at 2296-2304 still emits only the OLD 'is not a git repo' message with no product-mismatch and no subdir scoping. Live test `bunker-qa.sh run /home/kara/monitoring` printed 'ERROR: /home/kara/monitoring is not a git repo (git resolves toplevel: /home/kara)' (old message), and with BUNKER_QA_SUBDIR=fleet-monitoring set it STILL refused with the same old message and never scoped. run() is a documented first-class entry point ('SYNCHRONOUS compat mode', usage line 16) and does not call launch() — it has its own inline check, and no shared subdir helper exists (grep for subdir_scope/check_repo_scope/refuse_subdir = 0 hits). bash -n .hermes/scripts/bunker-qa.sh -> exit 0 (PASS). Commit 08a085e91 reachable from origin/main: `git merge-base --is-ancestor 08a085e91 origin/main` exit 0 and it appears in `git log origin/main` (PASS). Note: the commit message cites evidence=/tmp/qa-scope-ev.jsonl but that file is 0 bytes (empty).
launch() correctly refuses subdir targets with a product-mismatch FAIL cell and honors BUNKER_QA_SUBDIR, bash -n is clean and the commit is on origin/main, but the criterion's 'launch/run' requirement is unmet because run() was left untouched and still emits the old 'not a git repo' message while ignoring BUNKER_QA_SUBDIR.

## Summary

Judge Result: QA-HARNESS-SCOPE-20261004

Stage tier1: FAIL
  WARNING: coverage is secrets+lint+tests — secrets did not run (skipped at runtime — secrets: timed out after 120s (step budget)); run `gitreins guard` for the full gate
    ✗ tests: scanners: nice=nice -n 10
  ✗ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)

Stage tier2: FAIL
  INCOMPLETE
  ✗ bunker-qa.sh launch/run refuses a repo dir whose git toplevel differs from the dir with a product-mismatch error + FAIL evidence cell, unless BUNKER_QA_SUBDIR names the real product subdir, in which case sync is scoped to it; bash -n clean; commit reachable from origin main: The criterion requires BOTH launch and run to refuse. Only launch() was fixed. launch() (lines 2398-2545) has the fix at 2437-2449: BUNKER_QA_SUBDIR scoping (repo="$repo/${BUNKER_QA_SUBDIR%/}"; PROJ=basename) plus subdir refusal with product-mismatch message + FAIL evidence cell — live test `bunker-qa.sh launch /home/kara/monitoring` printed 'ERROR: /home/kara/monitoring is a SUBDIRECTORY of git repo /home/kara ... grade the wrong product' and wrote a FAIL cell. run() (lines 2275-2397) was NOT modified: `grep -c BUNKER_QA_SUBDIR` in run() = 0 (launch() = 5); its repo check at 2296-2304 still emits only the OLD 'is not a git repo' message with no product-mismatch and no subdir scoping. Live test `bunker-qa.sh run /home/kara/monitoring` printed 'ERROR: /home/kara/monitoring is not a git repo (git resolves toplevel: /home/kara)' (old message), and with BUNKER_QA_SUBDIR=fleet-monitoring set it STILL refused with the same old message and never scoped. run() is a documented first-class entry point ('SYNCHRONOUS compat mode', usage line 16) and does not call launch() — it has its own inline check, and no shared subdir helper exists (grep for subdir_scope/check_repo_scope/refuse_subdir = 0 hits). bash -n .hermes/scripts/bunker-qa.sh -> exit 0 (PASS). Commit 08a085e91 reachable from origin/main: `git merge-base --is-ancestor 08a085e91 origin/main` exit 0 and it appears in `git log origin/main` (PASS). Note: the commit message cites evidence=/tmp/qa-scope-ev.jsonl but that file is 0 bytes (empty).
launch() correctly refuses subdir targets with a product-mismatch FAIL cell and honors BUNKER_QA_SUBDIR, bash -n is clean and the commit is on origin/main, but the criterion's 'launch/run' requirement is unmet because run() was left untouched and still emits the old 'not a git repo' message while ignoring BUNKER_QA_SUBDIR.

Overall: FAIL ✗

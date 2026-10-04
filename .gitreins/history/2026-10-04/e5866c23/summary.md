# Verdict: QA-HARNESS-SCOPE-20261004

**Task:** bunker-qa.sh mis-scopes non-git-repo project dirs (subdir of git repo syncs whole parent)
**Evaluated:** 2026-10-04T19:11:40.328653
**Result:** ✗ FAIL

## Pipeline Stages

- ✗ **tier1**
  -   ✗ tests: scanners: nice=nice -n 10
  ✗ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)
- ✓ **tier2**
  - COMPLETE

(auto-parsed from non-JSON response — JSON parse failed: Expecting property name enclosed in double quotes: line 5 column 330 (char 551)) The committed blob at origin/main contains both guards (2× "SUBDIRECTORY of git repo"), 10× BUNKER_QA_SUBDIR references, and is bash -n clean.

All elements of the criterion are verified with live, reproducible evidence:

1. **launch/run refuse subdir-of-git-repo with product-mismatch error + FAIL e

## Summary

Judge Result: QA-HARNESS-SCOPE-20261004

Stage tier1: FAIL
  WARNING: coverage is secrets+lint+tests — secrets did not run (skipped at runtime — secrets: timed out after 120s (step budget)); run `gitreins guard` for the full gate
    ✗ tests: scanners: nice=nice -n 10
  ✗ lint: scanners: nice=nice -n 10
  ~ secrets: Command timed out after 120s (step budget)

Stage tier2: PASS
  COMPLETE

(auto-parsed from non-JSON response — JSON parse failed: Expecting property name enclosed in double quotes: line 5 column 330 (char 551)) The committed blob at origin/main contains both guards (2× "SUBDIRECTORY of git repo"), 10× BUNKER_QA_SUBDIR references, and is bash -n clean.

All elements of the criterion are verified with live, reproducible evidence:

1. **launch/run refuse subdir-of-git-repo with product-mismatch error + FAIL e

Overall: FAIL ✗

#!/usr/bin/env bash
# QA-AUGER-1 — regression test: pytest-suite detection + zero-test vacuity.
# History: the battery graded auger's ci-pass cell OK in 57ms with ZERO tests
# run — the repo declared its suite via pytest.ini, which the 09-26 two-filename
# arm covered, but sibling shapes (setup.cfg/tox.ini [pytest], pyproject
# [tool.pytest...], tests/conftest.py) still fell through to the vacuous
# `echo no-test-path`, and even a DETECTED pytest that exits 0 after collecting
# nothing ("no tests ran") graded OK on rc alone. This test locks:
#   1. the pytest_zero_collected / native_zero_tests predicates (extracted from
#      the LIVE harness, never a paraphrase) against the full summary matrix,
#   2. host-side is_pytest_repo detection (__detect-cmds) for every declared
#      shape — and the negatives,
#   3. the agent-side pytest provisioning bake (QA_PYTEST_REPO -> venv bootstrap),
#   4. BEHAVIOR of the real rendered ci-pass chain: green suite stays OK,
#      zero-tests grades FAIL, and a MUTATION arm (gate line removed from the
#      extracted copy) must flip the zero-test grade back to OK — proving this
#      test can actually detect the regression it exists for,
#   5. the chaos-resource arm (zero tests under cap -> UNVERIFIED, real pass -> PASS).
# No network, no agent, no root. Exit non-zero on any failure.
set -uo pipefail

HARNESS="${BUNKER_QA_SH:-$HOME/.hermes/scripts/bunker-qa.sh}"
pass=0; fail=0
check() { # <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then echo "  ok   $1 -> $3"; pass=$((pass+1))
  else echo "  FAIL $1: expected $2 got $3"; fail=$((fail+1)); fi
}

TMPD=$(mktemp -d)
trap 'rm -rf "$TMPD"' EXIT

# ── 1 · zero-test predicate matrix (extracted verbatim from the harness) ─────
# The harness copy lives inside the unquoted render heredoc, so its $ forms are
# escaped (\$); extract the function span and de-escape exactly as the remote
# script's runtime form reads.
if [ -f "$HARNESS" ]; then
  s=$(grep -n '^pytest_zero_collected() {' "$HARNESS" | head -1 | cut -d: -f1)
  e=$(awk -v s="$s" 'NR>s && /^\$?}$/ {print NR; exit}' "$HARNESS")
  if [ -n "${s:-}" ] && [ -n "${e:-}" ]; then
    sed -n "${s},${e}p" "$HARNESS" | sed 's/[\\][$]/$/g' > "$TMPD/pred.sh"
    # shellcheck disable=SC1090
    source "$TMPD/pred.sh"
    z() { pytest_zero_collected "$1" && echo ZERO || echo nonzero; }
    { printf '%s\n' '============================= test session starts =============================='
      printf '%s\n' 'platform linux -- Python 3.11.9, pytest-8.3.3'
      printf '%s\n' 'configfile: pytest.ini'
      printf '%s\n' '============================ no tests ran in 0.01s ============================='
    } > "$TMPD/zero.log"
    { printf '%s\n' '============================= test session starts =============================='
      printf '%s\n' 'collected 210 items'
      printf '%s\n' 'tests/test_a.py ..                                                     [100%]'
      printf '%s\n' '============================ 210 passed in 3.41s =============================='
    } > "$TMPD/green.log"
    printf '%s\n' '========================= 2 failed, 1 passed in 0.41s ========================' > "$TMPD/mixed.log"
    printf '%s\n' '========================= 1 warning, 1 error in 0.20s =======================' > "$TMPD/errors.log"
    # real pytest all-skipped run (measured: `1 skipped in 0.00s`, rc=0) — the
    # suite COLLECTED and RAN, so this predicate does NOT flag it; only pytest's
    # own "no tests ran" verdict (nothing collected) proves zero-test vacuity.
    printf '%s\n' 's                                                                        [100%]' '1 skipped in 0.00s' > "$TMPD/skipped.log"
    printf '%s\n' 'no-test-path' > "$TMPD/echo.log"
    printf '%s\n' 'make: *** No rule to make target' > "$TMPD/make.log"
    : > "$TMPD/empty.log"
    check "zero-test summary (no tests ran) -> ZERO"        ZERO     "$(z "$TMPD/zero.log")"
    check "green 210 passed -> nonzero"                     nonzero  "$(z "$TMPD/green.log")"
    check "2 failed 1 passed -> nonzero"                    nonzero  "$(z "$TMPD/mixed.log")"
    check "errors counted -> nonzero"                       nonzero  "$(z "$TMPD/errors.log")"
    check "all-skipped run (1 skipped) -> nonzero (collection happened)" nonzero "$(z "$TMPD/skipped.log")"
    check "no-test-path echo -> nonzero (vacuous arm owns it)" nonzero "$(z "$TMPD/echo.log")"
    check "non-pytest output -> nonzero (not flagged)"      nonzero  "$(z "$TMPD/make.log")"
    check "empty log -> nonzero (0-byte arm owns it)"       nonzero  "$(z "$TMPD/empty.log")"
    check "missing file -> nonzero (fail-closed)"           nonzero  "$(z "$TMPD/does-not-exist.log")"
  else
    check "extract pytest_zero_collected from harness" yes no
  fi
else
  echo "  SKIP harness not found at $HARNESS"
fi

# ── 2 · host-side detection matrix (__detect-cmds is a pure function of dir) ──
mkfix() { # <name> <setup-fn>
  local d="$TMPD/$1"; mkdir -p "$d"; FIX="$d"
}
echo "=== host detection (is_pytest_repo shapes)"
mkfix f-pytestini;  printf '%s\n' '[pytest]' 'testpaths = tests' > "$FIX/pytest.ini"
mkfix f-conftest;   printf '%s\n' 'import pytest' > "$FIX/conftest.py"
mkfix f-setupcfg;   printf '%s\n' '[metadata]' 'name = x' '' '[pytest]' 'testpaths = tests' > "$FIX/setup.cfg"
mkfix f-toxini;     printf '%s\n' '[tox]' 'envlist = py311' '' '[pytest]' 'testpaths = tests' > "$FIX/tox.ini"
mkfix f-pyproject;  printf '%s\n' '[build-system]' 'requires = ["setuptools"]' '' '[tool.pytest.ini_options]' 'testpaths = ["tests"]' > "$FIX/pyproject.toml"
mkfix f-testsconf;  mkdir -p "$FIX/tests"; printf '%s\n' 'import pytest' > "$FIX/tests/conftest.py"
mkfix f-none;       printf '%s\n' '# just a script repo' > "$FIX/run.sh"
mkfix f-badcfg;     printf '%s\n' '[metadata]' 'name = x' > "$FIX/setup.cfg"
# pyproject [tool.pytest] / pyproject-without-pytest section: the PRE-EXISTING
# pyproject arm claims these repos BEFORE is_pytest_repo (bare native
# `pytest -x -q` + its own venv bootstrap already provision pytest) — the
# predicate arm exists for the shapes NO earlier arm covered. Assert the
# precedence contract instead of DETECT_PYTEST_REPO.
det() { bash "$HARNESS" __detect-cmds "$1" 2>/dev/null | grep -E '^DETECT_(NATIVE|PYTEST_REPO)=' | tr '\n' ' '; }
check "pytest.ini -> pytest + flag"        "DETECT_NATIVE=python3 -m pytest -q DETECT_PYTEST_REPO=1 " "$(det "$TMPD/f-pytestini")"
check "conftest.py -> pytest + flag"       "DETECT_NATIVE=python3 -m pytest -q DETECT_PYTEST_REPO=1 " "$(det "$TMPD/f-conftest")"
check "setup.cfg [pytest] -> pytest + flag" "DETECT_NATIVE=python3 -m pytest -q DETECT_PYTEST_REPO=1 " "$(det "$TMPD/f-setupcfg")"
check "tox.ini [pytest] -> pytest + flag"  "DETECT_NATIVE=python3 -m pytest -q DETECT_PYTEST_REPO=1 " "$(det "$TMPD/f-toxini")"
check "tests/conftest.py -> pytest + flag" "DETECT_NATIVE=python3 -m pytest -q DETECT_PYTEST_REPO=1 " "$(det "$TMPD/f-testsconf")"
case "$(det "$TMPD/f-pyproject")" in
  *DETECT_NATIVE=pytest*) check "pyproject [tool.pytest] -> pyproject arm wins (venv-provisioned pytest)" yes yes ;;
  *) check "pyproject [tool.pytest] -> pyproject arm wins (venv-provisioned pytest)" yes no ;;
esac
case "$(det "$TMPD/f-none")" in
  *"no-test-path"*) check "no declaration -> no-test-path (unchanged)" yes yes ;;
  *) check "no declaration -> no-test-path (unchanged)" yes no ;;
esac
case "$(det "$TMPD/f-badcfg")" in
  *"no-test-path"*) check "setup.cfg WITHOUT [pytest] -> no-test-path" yes yes ;;
  *) check "setup.cfg WITHOUT [pytest] -> no-test-path" yes no ;;
esac
# The original incident repo (if present on this host) must always detect.
if [ -d "$HOME/auger" ]; then
  case "$(det "$HOME/auger")" in
    *pytest*) check "auger repo itself -> pytest native cmd" yes yes ;;
    *)        check "auger repo itself -> pytest native cmd" yes no ;;
  esac
fi

# ── 3 · provisioning bake: a pytest-config repo gets the pytest venv arm ──────
echo "=== provisioning bake (QA_PYTEST_REPO)"
if [ -f "$HARNESS" ]; then
  QA_HEAD_SHA=deadbeef QA_HEAD_PULL=test bash "$HARNESS" __gen-remote-detected "$TMPD/f-pytestini" 2>/dev/null > "$TMPD/render-pytest.sh"
  grep -qF "QA_PYTEST_REPO='1'" "$TMPD/render-pytest.sh" \
    && check "pytest-config repo bakes QA_PYTEST_REPO='1'" yes yes \
    || check "pytest-config repo bakes QA_PYTEST_REPO='1'" yes no
  grep -qF 'pytest-config repo, QA-AUGER-1' "$TMPD/render-pytest.sh" \
    && check "venv bootstrap arm present in render" yes yes \
    || check "venv bootstrap arm present in render" yes no
  grep -qF '[ "$QA_PYTEST_REPO" = "1" ] && [ ! -x ~/tools/venv/bin/python ]' "$TMPD/render-pytest.sh" \
    && check "bootstrap gate reads the baked flag" yes yes \
    || check "bootstrap gate reads the baked flag" yes no
  QA_HEAD_SHA=deadbeef QA_HEAD_PULL=test bash "$HARNESS" __gen-remote-detected "$TMPD/f-none" 2>/dev/null > "$TMPD/render-plain.sh"
  grep -qF "QA_PYTEST_REPO='0'" "$TMPD/render-plain.sh" \
    && check "plain repo bakes QA_PYTEST_REPO='0'" yes yes \
    || check "plain repo bakes QA_PYTEST_REPO='0'" yes no
fi

# ── 4 · behavioral: the REAL rendered ci-pass chain grades the matrix ─────────
echo "=== behavioral ci-pass chain (rendered from the live harness)"
if [ -f "$HARNESS" ] && [ -s "$TMPD/render-pytest.sh" ]; then
  s=$(grep -nF 'if [ $nat_rc -eq 0 ]; then' "$TMPD/render-pytest.sh" | head -1 | cut -d: -f1)
  e=$(grep -n '#QA-CELL:ci-pass:end' "$TMPD/render-pytest.sh" | head -1 | cut -d: -f1)
  e=$(( e - 2 ))   # chain ends at the `fi` directly above the marker
  if [ -n "${s:-}" ] && [ "$e" -gt "${s:-0}" ]; then
    sed -n "${s},${e}p" "$TMPD/render-pytest.sh" > "$TMPD/chain.sh"
    if bash -n "$TMPD/chain.sh" 2>/dev/null; then
      # predicate + stub helpers exactly as the agent runtime would have them
      sed -n '/^vacuous_native_suite() {/,/^}$/p' "$TMPD/render-pytest.sh" > "$TMPD/preds.sh"
      sed -n '/^pytest_zero_collected() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/preds.sh"
      sed -n '/^native_zero_tests() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/preds.sh"
      sed -n '/^native_runner_missing_cause() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/preds.sh"
      sed -n '/^native_runner_missing() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/preds.sh"
      {
        printf 'cell() { printf "%%s %%s\\n" "$2" "$3"; }\n'
        printf 'build_env_failure() { return 1; }\n'
        printf 'go_suite_env_failure() { return 1; }\n'
        printf 'suite_deps_missing() { return 1; }\n'
        printf 'ci_only_failure() { return 1; }\n'
        printf 'act_failure_context() { printf none; }\n'
        cat "$TMPD/preds.sh" "$TMPD/chain.sh"
      } > "$TMPD/drive.sh"
      grade() { LOGD="$TMPD" nat_rc="$1" ci_rc="${2:-skip}" bash "$TMPD/drive.sh" 2>/dev/null | head -1 | awk '{print $1}'; }
      cp "$TMPD/green.log" "$TMPD/native.log"
      check "behavioral: green suite rc=0 -> OK"              OK        "$(grade 0)"
      cp "$TMPD/zero.log" "$TMPD/native.log"
      check "behavioral: zero tests rc=0 -> FAIL (QA-AUGER-1)" FAIL      "$(grade 0)"
      cp "$TMPD/zero.log" "$TMPD/native.log"
      graw=$(LOGD="$TMPD" nat_rc=0 ci_rc=skip bash "$TMPD/drive.sh" 2>/dev/null | head -1)
      case "$graw" in
        *"ZERO tests ran"*) check "FAIL detail names the zero-test diagnosis" yes yes ;;
        *) check "FAIL detail names the zero-test diagnosis" yes no ;;
      esac
      printf '%s\n' 'no-test-path' > "$TMPD/native.log"
      check "behavioral: vacuous echo rc=0 -> UNVERIFIED"     UNVERIFIED "$(grade 0)"
      # MUTATION arm: remove the zero-test gate from the EXTRACTED copy only —
      # the zero-test grade must flip back to OK, proving this test detects
      # exactly the regression it guards (assertion sensitivity proof).
      grep -v 'native_zero_tests $LOGD/native.log; then' "$TMPD/drive.sh" > "$TMPD/drive-mutated.sh"
      cp "$TMPD/zero.log" "$TMPD/native.log"
      check "mutation: gate removed -> zero tests grade OK again" OK      "$(LOGD="$TMPD" nat_rc=0 ci_rc=skip bash "$TMPD/drive-mutated.sh" 2>/dev/null | head -1 | awk '{print $1}')"
    else
      check "extracted ci-pass chain parses" yes no
    fi
  else
    check "extract ci-pass chain span" yes no
  fi
fi

# ── 5 · behavioral: chaos-resource grades zero-tests UNVERIFIED under the cap ─
echo "=== behavioral chaos-resource arm"
if [ -f "$HARNESS" ] && [ -s "$TMPD/render-pytest.sh" ]; then
  s=$(grep -n '^cap_seen=' "$TMPD/render-pytest.sh" | head -1 | cut -d: -f1)
  e=$(grep -nF "else cell chaos-resource FAIL" "$TMPD/render-pytest.sh" | head -1 | cut -d: -f1)
  if [ -n "${s:-}" ] && [ -n "${e:-}" ] && [ "$e" -gt "$s" ]; then
    sed -n "${s},${e}p" "$TMPD/render-pytest.sh" > "$TMPD/rchain.sh"
    if bash -n "$TMPD/rchain.sh" 2>/dev/null; then
      sed -n '/^pytest_zero_collected() {/,/^}$/p' "$TMPD/render-pytest.sh" > "$TMPD/rpreds.sh"
      sed -n '/^native_zero_tests() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^vacuous_native_suite() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^native_runner_missing_cause() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^native_runner_missing() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^build_incomplete() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^build_incomplete_cause() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^go_suite_env_failure() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^suite_deps_missing() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^suite_deps_missing_cause() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^go_toolchain_oom() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^go_toolchain_oom_cause() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^go_panic_timeout() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^go_panic_timeout_cause() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      sed -n '/^capped_fail_summary() {/,/^}$/p' "$TMPD/render-pytest.sh" >> "$TMPD/rpreds.sh"
      {
        printf 'cell() { printf "%%s %%s\\n" "$2" "$3"; }\n'
        printf 'CAP_KB=3145728\n'
        cat "$TMPD/rpreds.sh" "$TMPD/rchain.sh"
      } > "$TMPD/rdrive.sh"
      printf '%s\n' 'PARENT_CAP=unlimited' 'SUBSHELL_CAP=3145728' 'CAP_EFFECTIVE=3145728 CAP_REQUESTED=3145728' '============================ no tests ran in 0.02s =============================' > "$TMPD/res.log"
      check "behavioral: zero tests under cap -> UNVERIFIED" UNVERIFIED "$(LOGD="$TMPD" res_rc=0 bash "$TMPD/rdrive.sh" 2>/dev/null | head -1 | awk '{print $1}')"
      printf '%s\n' 'PARENT_CAP=unlimited' 'SUBSHELL_CAP=3145728' 'CAP_EFFECTIVE=3145728 CAP_REQUESTED=3145728' '============================ 210 passed in 3.41s ==============================' > "$TMPD/res.log"
      check "behavioral: real pass under cap -> PASS (no regression)" PASS "$(LOGD="$TMPD" res_rc=0 bash "$TMPD/rdrive.sh" 2>/dev/null | head -1 | awk '{print $1}')"
    else
      check "extracted chaos-resource chain parses" yes no
    fi
  else
    check "extract chaos-resource chain span" yes no
  fi
fi

# ── 6 · harness lockstep (grep the real harness, escaped forms) ───────────────
echo "=== harness lockstep"
if [ -f "$HARNESS" ]; then
  grep -qF 'is_pytest_repo "$repo"; then' "$HARNESS" \
    && check "host pytest arm dispatches through is_pytest_repo" yes yes \
    || check "host pytest arm dispatches through is_pytest_repo" yes no
  grep -qF 'pytest_zero_collected() {' "$HARNESS" \
    && check "pytest_zero_collected predicate present" yes yes \
    || check "pytest_zero_collected predicate present" yes no
  grep -qF 'native_zero_tests \$LOGD/native.log; then' "$HARNESS" \
    && check "ci-pass zero-test gate present" yes yes \
    || check "ci-pass zero-test gate present" yes no
  grep -qF 'cell ci-pass FAIL "vacuous pass: native runner exited 0 but ZERO tests ran' "$HARNESS" \
    && check "ci-pass FAIL branch present (vacuous pass is a FAIL, not UNVERIFIED)" yes yes \
    || check "ci-pass FAIL branch present (vacuous pass is a FAIL, not UNVERIFIED)" yes no
  grep -qF 'elif native_zero_tests \$LOGD/res.log; then' "$HARNESS" \
    && check "chaos-resource zero-test gate present" yes yes \
    || check "chaos-resource zero-test gate present" yes no
  grep -qF 'elif native_zero_tests \$LOGD/disc.log; then' "$HARNESS" \
    && check "chaos-disconnect zero-test gate present" yes yes \
    || check "chaos-disconnect zero-test gate present" yes no
  grep -qF "QA_PYTEST_REPO='\$DETECT_PYTEST_REPO'" "$HARNESS" \
    && check "detection verdict baked into the render" yes yes \
    || check "detection verdict baked into the render" yes no
  grep -qF '"\$QA_PYTEST_REPO" = "1" ] && [ ! -x ~/tools/venv/bin/python' "$HARNESS" \
    && check "venv bootstrap serves pytest-config repos" yes yes \
    || check "venv bootstrap serves pytest-config repos" yes no
  grep -qF 'DETECT_PYTEST_REPO="${DETECT_PYTEST_REPO:-0}"' "$HARNESS" \
    && check "__gen-remote hook keeps the variable contract" yes yes \
    || check "__gen-remote hook keeps the variable contract" yes no
  # ORDER: the zero-test gate must sit AFTER the vacuous check and BEFORE any
  # OK/PASS grading (a reordered chain would re-open the vacuous pass).
  zt=$(grep -nF 'native_zero_tests \$LOGD/native.log; then' "$HARNESS" | head -1 | cut -d: -f1)
  vc=$(grep -nF 'if vacuous_native_suite \$LOGD/native.log; then' "$HARNESS" | head -1 | cut -d: -f1)
  if [ -n "${zt:-}" ] && [ -n "${vc:-}" ] && [ "$zt" -gt "$vc" ]; then
    check "zero-test gate ordered after the vacuous gate" yes yes
  else
    check "zero-test gate ordered after the vacuous gate" yes no
  fi
fi

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

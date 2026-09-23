#!/bin/bash
# QA-TASK-ROUTER-4 — regression test for the bunker-qa.sh chaos result
# classifiers. Acceptance: a unit test covering rc=0 / 127 / 1 for the harness
# result-classifier. The cells live inside the generated remote script, so the
# predicates are mirrored here and kept in lockstep with bunker-qa.sh by the
# grep assertions at the bottom (drift between this test and the harness fails).
set -uo pipefail

HARNESS="${BUNKER_QA_SH:-$HOME/.hermes/scripts/bunker-qa.sh}"
pass=0; fail=0
check() { # <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then echo "  ok   $1 -> $3"; pass=$((pass+1))
  else echo "  FAIL $1: expected $2 got $3"; fail=$((fail+1)); fi
}

# ── chaos-disconnect classifier (precedence: rc=0 > 124 > 127 > build > ok) ──
classify_disconnect() { # <rc> <build_incomplete 0|1>
  local rc=$1 bi=${2:-0}
  if [ "$rc" -eq 0 ]; then echo INFO; return; fi
  if [ "$rc" -eq 124 ]; then echo FAIL; return; fi
  if [ "$rc" -eq 127 ]; then echo UNVERIFIED; return; fi
  if [ "$bi" = 1 ]; then echo INFO; return; fi
  echo OK
}

# ── chaos-resource classifier (cap evidence is REQUIRED first) ───────────────
classify_resource() { # <rc> <cap_seen> <cap_expected> <build_incomplete>
  local rc=$1 seen=$2 want=$3 bi=${4:-0}
  if [ "$seen" != "$want" ]; then echo UNVERIFIED; return; fi
  if [ "$rc" -eq 0 ]; then echo PASS; return; fi
  if [ "$rc" -eq 127 ]; then echo UNVERIFIED; return; fi
  if [ "$bi" = 1 ]; then echo INFO; return; fi
  echo FAIL
}

echo "=== chaos-disconnect (QA-TASK-ROUTER-4)"
check "rc=0  passes with network cut"        INFO       "$(classify_disconnect 0)"
check "rc=127 pytest not found -> never ran" UNVERIFIED "$(classify_disconnect 127)"
check "rc=124 hang stays a real FAIL"        FAIL       "$(classify_disconnect 124)"
check "rc=1  clean fail stays OK"            OK         "$(classify_disconnect 1 0)"
check "rc=1  with incomplete build"          INFO       "$(classify_disconnect 1 1)"

echo
echo "=== chaos-resource cap evidence (QA-TASK-ROUTER-3)"
check "cap applied + rc=0"                PASS       "$(classify_resource 0 3145728 3145728 0)"
check "cap NOT applied -> vacuous"        UNVERIFIED "$(classify_resource 0 NONE 3145728 0)"
check "cap NOT applied + rc=0 would be vacuous PASS before" UNVERIFIED "$(classify_resource 0 2097152 3145728 0)"
check "cap applied + rc=127 -> never ran" UNVERIFIED "$(classify_resource 127 3145728 3145728 0)"
check "cap applied + rc=1 -> real FAIL"   FAIL       "$(classify_resource 1 3145728 3145728 0)"
check "cap applied + build incomplete"    INFO       "$(classify_resource 1 3145728 3145728 1)"

echo
echo "=== harness lockstep (the predicates above must exist in the harness)"
if [ -f "$HARNESS" ]; then
  grep -q 'elif \[ \\$disc_rc -eq 127 \]; then cell chaos-disconnect UNVERIFIED' "$HARNESS" \
    && check "disconnect rc=127 branch present" yes yes \
    || check "disconnect rc=127 branch present" yes no
  grep -q 'cap_seen=' "$HARNESS" \
    && check "resource cap-evidence probe present" yes yes \
    || check "resource cap-evidence probe present" yes no
  grep -q 'chaos-resource UNVERIFIED "cap NOT applied' "$HARNESS" \
    && check "resource vacuous-result guard present" yes yes \
    || check "resource vacuous-result guard present" yes no
else
  echo "  SKIP harness not found at $HARNESS"
fi

echo
echo "=== upgrade cell Go path (QA-OFF-BY-ONE-22, 2026-09-22)"
# The upgrade cell reported UNVERIFIED for Go-binary repos with release tags:
# the synced tree carries no .git history, and only pip/npm had install legs.
# Fix: host streams the previous tag's tree (ship_prev_tag_tree -> ~/qa-up-prev),
# the cell installs it and reinstalls HEAD over it.
if [ -f "$HARNESS" ]; then
  grep -q 'DETECT_PKG_ECOSYSTEM="go"' "$HARNESS" \
    && check "go-ecosystem detection present" yes yes \
    || check "go-ecosystem detection present" yes no
  grep -q 'ship_prev_tag_tree()' "$HARNESS" \
    && check "host-side previous-tag streamer present" yes yes \
    || check "host-side previous-tag streamer present" yes no
  grep -qF 'previous release \$QA_PREV_TAG (tree via git archive) → HEAD reinstall clean' "$HARNESS" \
    && check "go upgrade OK branch present" yes yes \
    || check "go upgrade OK branch present" yes no
  grep -q 'streamed previous-release tree is missing' "$HARNESS" \
    && check "missing-stream loud FAIL present" yes yes \
    || check "missing-stream loud FAIL present" yes no
  grep -q 'ship_prev_tag_tree "$repo" "$PROJ"' "$HARNESS" \
    && check "streamer wired at both call sites" yes yes \
    || check "streamer wired at both call sites" yes no
  # functional: the generated remote script must bake QA_GO_URL and carry the
  # materialize-previous-tree logic (test hook __gen-remote, no agent needed).
  # NB: grep -q on a pipe + `set -o pipefail` makes the producer die of
  # SIGPIPE on large output (67KB here) and the check false-FALSE — match on
  # the variable with case instead.
  GEN=$(bash "$HARNESS" __gen-remote off-by-one 2>/dev/null)
  case "$GEN" in
    *"QA_GO_URL="*) check "generated script bakes QA_GO_URL" yes yes ;;
    *) check "generated script bakes QA_GO_URL" yes no ;;
  esac
  case "$GEN" in
    *UP_PREV=*) check "generated script materializes previous tree" yes yes ;;
    *) check "generated script materializes previous tree" yes no ;;
  esac
fi

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

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

# ── chaos-disconnect classifier (precedence: vacuous > rc=0 > 124 > 127 > build > ok) ──
# QA-WARPFS-17 (2026-10-10): a 0-byte / never-ran disc.log is VACUOUS evidence.
# The suite produced NO output, so the network cut was never exercised on it, and
# it must grade UNVERIFIED at EVERY rc — never INFO "passes with network cut
# (no network dep)" and never OK "fails fast on disconnect".
classify_disconnect() { # <rc> <build_incomplete 0|1> <vacuous_log 0|1>
  local rc=$1 bi=${2:-0} vac=${3:-0}
  if [ "$vac" = 1 ]; then echo UNVERIFIED; return; fi
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
# QA-WARPFS-17: a 0-byte (or never-ran) disc.log must NEVER grade INFO/OK.
check "0-byte log + rc=0 -> UNVERIFIED (was INFO passes)"     UNVERIFIED "$(classify_disconnect 0 0 1)"
check "0-byte log + rc=1 -> UNVERIFIED (was OK fails-fast)"   UNVERIFIED "$(classify_disconnect 1 0 1)"
check "0-byte log + rc=101 -> UNVERIFIED (no build result)"   UNVERIFIED "$(classify_disconnect 101 1 1)"
check "0-byte log + rc=124 -> UNVERIFIED (vacuous precedes)"  UNVERIFIED "$(classify_disconnect 124 0 1)"
check "real log + rc=0 -> INFO (no regression)"               INFO       "$(classify_disconnect 0 0 0)"
check "real log + rc=1 -> OK (no regression)"                 OK         "$(classify_disconnect 1 0 0)"

echo
echo "=== chaos-resource cap evidence (QA-TASK-ROUTER-3)"
check "cap applied + rc=0"                PASS       "$(classify_resource 0 3145728 3145728 0)"
check "cap NOT applied -> vacuous"        UNVERIFIED "$(classify_resource 0 NONE 3145728 0)"
check "cap NOT applied + rc=0 would be vacuous PASS before" UNVERIFIED "$(classify_resource 0 2097152 3145728 0)"
check "cap applied + rc=127 -> never ran" UNVERIFIED "$(classify_resource 127 3145728 3145728 0)"
check "cap applied + rc=1 -> real FAIL"   FAIL       "$(classify_resource 1 3145728 3145728 0)"
check "cap applied + build incomplete"    INFO       "$(classify_resource 1 3145728 3145728 1)"

echo
echo "=== vacuous_native_suite (QA-BUNKER-29, 2026-09-30)"
# Mirror of the harness predicate: a log that carries the no-test-path marker,
# or no non-whitespace content besides the cap-probe lines, proves the native
# suite NEVER RAN — rc=0 from it must grade UNVERIFIED, never PASS/OK.
vacuous_native_suite() { # <logfile> -> 0 when the log proves no suite ran
  local f="$1"
  [ -f "$f" ] || return 0
  if grep -q 'no-test-path' "$f"; then return 0; fi
  local rest
  rest=$(grep -vE '^[[:space:]]*$|^(PARENT_CAP|SUBSHELL_CAP|CAP_EFFECTIVE)=' "$f")
  [ -z "$rest" ]
}
TMPD=$(mktemp -d)
printf 'no-test-path\n' > "$TMPD/native_vacuous.log"
{ echo '============================= test session starts =============================='; echo 'collected 210 items'; echo 'tests/test_a.py .. [100%]'; echo '210 passed in 3.4s'; } > "$TMPD/native_real.log"
printf 'PARENT_CAP=unlimited\nSUBSHELL_CAP=3145728\nCAP_EFFECTIVE=3145728 CAP_REQUESTED=3145728\nno-test-path\n' > "$TMPD/res_vacuous.log"
: > "$TMPD/empty.log"
{ echo 'PARENT_CAP=unlimited'; echo 'CAP_EFFECTIVE=3145728 CAP_REQUESTED=3145728'; echo 'suite ran, 12 passed'; } > "$TMPD/res_real.log"
nv() { vacuous_native_suite "$1" && echo vacuous || echo not-vacuous; }
check "real pytest output -> not vacuous"                 not-vacuous "$(nv "$TMPD/native_real.log")"
check "res.log cap lines + no-test-path -> vacuous"       vacuous     "$(nv "$TMPD/res_vacuous.log")"
check "empty log -> vacuous"                              vacuous     "$(nv "$TMPD/empty.log")"
check "res.log cap lines + real output -> not vacuous"    not-vacuous "$(nv "$TMPD/res_real.log")"
check "missing file -> treated vacuous (fail-closed)"     vacuous     "$(nv "$TMPD/does-not-exist.log")"
# QA-WARPFS-17: a real 0-byte file must drive UNVERIFIED end-to-end.
if vacuous_native_suite "$TMPD/empty.log"; then v=1; else v=0; fi
check "0-byte disc.log (real file) -> vacuous -> UNVERIFIED"  UNVERIFIED "$(classify_disconnect 0 0 $v)"

# QA-HERMES-CANOPY-44: rc=0 is not evidence by itself. The real log contract
# requires the network-cut marker and a non-zero suite result. Keep these tests
# independent of the rendered chain so they catch a weakened validator too.
disconnect_suite_counts() {
  local f="$1" pass fail
  pass=$(grep -Eo '[0-9]+[[:space:]]+passed' "$f" 2>/dev/null | awk '{s+=$1} END {print s+0}')
  fail=$(grep -Eo '[0-9]+[[:space:]]+(failed|errors?)' "$f" 2>/dev/null | awk '{s+=$1} END {print s+0}')
  [ "$pass" -eq 0 ] && pass=$(grep -Ec '^ok[[:space:]]' "$f" 2>/dev/null || true)
  [ "$fail" -eq 0 ] && fail=$(grep -Ec '^(FAIL|--- FAIL)' "$f" 2>/dev/null || true)
  printf '%s %s\n' "${pass:-0}" "${fail:-0}"
}
disconnect_log_valid() {
  local f="$1" counts pass fail
  [ -s "$f" ] || return 1
  grep -qE '^NETWORK_CUT_APPLIED([[:space:]]|$)' "$f" || return 1
  counts=$(disconnect_suite_counts "$f")
  pass=${counts%% *}; fail=${counts##* }
  [ "${pass:-0}" -gt 0 ] || [ "${fail:-0}" -gt 0 ]
}
: > "$TMPD/canopy-empty.log"
printf 'NETWORK_CUT_APPLIED proxy=http://127.0.0.1:9\n' > "$TMPD/canopy-marker-only.log"
printf 'NETWORK_CUT_APPLIED proxy=http://127.0.0.1:9\n12 passed in 1.2s\n' > "$TMPD/canopy-valid.log"
if disconnect_log_valid "$TMPD/canopy-empty.log"; then v=valid; else v=UNVERIFIED; fi
check "QA-HERMES-CANOPY-44 empty log -> UNVERIFIED" UNVERIFIED "$v"
if disconnect_log_valid "$TMPD/canopy-marker-only.log"; then v=valid; else v=UNVERIFIED; fi
check "QA-HERMES-CANOPY-44 marker without result -> UNVERIFIED" UNVERIFIED "$v"
if disconnect_log_valid "$TMPD/canopy-valid.log"; then v=valid; else v=UNVERIFIED; fi
check "QA-HERMES-CANOPY-44 marker + suite counts -> valid" valid "$v"

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
  # QA-BUNKER-29 (2026-09-30): the vacuous-suite predicate must gate BOTH
  # success branches before their PASS/OK grading.
  grep -q 'vacuous_native_suite()' "$HARNESS" \
    && check "vacuous_native_suite predicate present" yes yes \
    || check "vacuous_native_suite predicate present" yes no
  grep -q 'if vacuous_native_suite \\$LOGD/native.log; then' "$HARNESS" \
    && check "ci-pass vacuous gate present (before OK grading)" yes yes \
    || check "ci-pass vacuous gate present (before OK grading)" yes no
  grep -q 'cell ci-pass UNVERIFIED "native suite NEVER RAN (vacuous no-test-path placeholder)' "$HARNESS" \
    && check "ci-pass UNVERIFIED branch present" yes yes \
    || check "ci-pass UNVERIFIED branch present" yes no
  grep -q 'if vacuous_native_suite \\$LOGD/res.log; then' "$HARNESS" \
    && check "chaos-resource vacuous gate present (before PASS grading)" yes yes \
    || check "chaos-resource vacuous gate present (before PASS grading)" yes no
  grep -q 'cell chaos-resource UNVERIFIED "suite NEVER RAN under the cap (vacuous no-test-path)' "$HARNESS" \
    && check "chaos-resource UNVERIFIED branch present" yes yes \
    || check "chaos-resource UNVERIFIED branch present" yes no
else
  echo "  SKIP harness not found at $HARNESS"
fi

echo
# QA-WARPFS-17 (2026-10-10): the 0-byte/vacuous disc.log gate must exist in the
# harness so an empty disc.log grades UNVERIFIED, never "passes with network cut".
if [ -f "$HARNESS" ]; then
  grep -qF 'vacuous_native_suite \$LOGD/disc.log; then cell chaos-disconnect UNVERIFIED' "$HARNESS" \
    && check "chaos-disconnect vacuous/0-byte gate present" yes yes \
    || check "chaos-disconnect vacuous/0-byte gate present" yes no
  grep -qF 'cell chaos-disconnect UNVERIFIED "disc.log is EMPTY (0 bytes)' "$HARNESS" \
    && check "chaos-disconnect 0-byte UNVERIFIED branch present" yes yes \
    || check "chaos-disconnect 0-byte UNVERIFIED branch present" yes no
fi

# QA-WARPFS-17 behavioral: extract the REAL chaos-disconnect grading chain from
# the harness (heredoc-escaped -> runtime form) and drive it with a 0-byte and a
# populated disc.log, proving the harness BEHAVIOR, not just a mirrored predicate.
if [ -f "$HARNESS" ]; then
  _s=$(grep -n '^native_dur=' "$HARNESS" | head -1 | cut -d: -f1)
  _e=$(grep -n 'else cell chaos-disconnect OK "fails fast on disconnect' "$HARNESS" | head -1 | cut -d: -f1)
  if [ -n "$_s" ] && [ -n "$_e" ] && [ "$_e" -gt "$_s" ]; then
    RENDER="$TMPD/disc-chain.sh"
    {
      echo 'cell() { printf "%s %s\n" "$1" "$2"; }'
      echo "LOGD=\"$TMPD\""
      echo 'build_incomplete() { return 1; }'
      echo 'go_suite_env_failure() { return 1; }'
      echo 'suite_deps_missing() { return 1; }'
      echo 'native_runner_missing() { return 1; }'
      echo 'vacuous_native_suite() { [ ! -s "$1" ]; }'
      echo 'disconnect_suite_counts() { printf "12 0\\n"; }'
      echo 'disconnect_log_valid() { [ -s "$1" ] && grep -q "^NETWORK_CUT_APPLIED" "$1"; }'
      sed -n "${_s},${_e}p" "$HARNESS" | sed 's/[\\][$]/$/g'
    } > "$RENDER"
    bd() { LOGD="$TMPD" disc_rc="$1" bash "$RENDER" 2>/dev/null | head -1 | awk '{print $1" "$2}'; }
    : > "$TMPD/disc.log"
    check "behavioral: 0-byte disc.log + rc=0 -> UNVERIFIED" "chaos-disconnect UNVERIFIED" "$(bd 0)"
    check "behavioral: 0-byte disc.log + rc=1 -> UNVERIFIED" "chaos-disconnect UNVERIFIED" "$(bd 1)"
    printf 'NETWORK_CUT_APPLIED proxy=http://127.0.0.1:9\ntests passed: 12 ok\n' > "$TMPD/disc.log"
    check "behavioral: valid disc.log + rc=0 -> INFO"    "chaos-disconnect INFO"       "$(bd 0)"
    check "behavioral: valid disc.log + rc=1 -> OK"      "chaos-disconnect OK"         "$(bd 1)"
  else
    check "behavioral: could extract the disc chain" yes no
  fi
fi

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

echo "=== chaos-errorpath missing-config grading (QA-CHIMERA-V2-42)"
# The bare console script's no-args run prints a usage banner and exits 0;
# ep_grade must NEVER grade that as "application started on missing config"
# (QA-CHIMERA-V2-36 was exactly this misread on chimera-v2), and the pyproject
# BIN discovery must probe a config-requiring subcommand (serve-family first).
if [ -f "$HARNESS" ]; then
  grep -qF 'probe invoked CLI-help arm' "$HARNESS" \
    && check "usage-banner guard present in ep_grade" yes yes \
    || check "usage-banner guard present in ep_grade" yes no
  grep -qF '(serve|server|daemon|start)' "$HARNESS" \
    && check "discovery prefers long-running commands" yes yes \
    || check "discovery prefers long-running commands" yes no
  # behavioral: drive the REAL ep_grade from the GENERATED battery (runtime form).
  _g="$TMPD/qa42-ep-gen.sh"
  bash "$HARNESS" __gen-remote epgrade 2>/dev/null | sed -n '/^ep_grade()/,/^}/p' > "$_g"
  if [ -s "$_g" ]; then
    source "$_g"
    _l="$TMPD/ep-arm.log"
    printf 'Usage: fake [OPTIONS] [COMMAND]...\n\n  fake — a CLI.\n' > "$_l"
    _o=$(ep_grade 0 "$_l" yes fake)
    case "$_o" in
      INFO*"CLI-help arm"*) check "behavioral: rc=0 usage banner -> INFO CLI-help arm" yes yes ;;
      *) check "behavioral: rc=0 usage banner -> INFO CLI-help arm" yes no ;;
    esac
    case "$_o" in
      *"application started"*) check "behavioral: banner never grades as started" yes no ;;
      *) check "behavioral: banner never grades as started" yes yes ;;
    esac
    printf 'error: No config found.\nUsage: fake serve [OPTIONS]\n' > "$_l"
    _o=$(ep_grade 2 "$_l" yes "fake serve")
    case "$_o" in
      OK*"clean error on missing config (rc=2)"*) check "behavioral: rc=2 clean error -> OK" yes yes ;;
      *) check "behavioral: rc=2 clean error -> OK" yes no ;;
    esac
    printf 'Traceback (most recent call last):\nKeyError: x\n' > "$_l"
    _o=$(ep_grade 1 "$_l" yes fake)
    check "behavioral: traceback still FAIL" "FAIL" "$(printf '%s' "$_o" | cut -f1)"
    printf 'server listening\n' > "$_l"
    _o=$(ep_grade 0 "$_l" yes "fake serve")
    case "$_o" in
      *"application started but exited cleanly"*) check "behavioral: real-start rc=0 keeps legacy INFO" yes yes ;;
      *) check "behavioral: real-start rc=0 keeps legacy INFO" yes no ;;
    esac
  else
    check "behavioral: could extract ep_grade from generated battery" yes no
  fi
  GEN=$(bash "$HARNESS" __gen-remote chimera-probe 2>/dev/null)
  # NB: grep -q on a pipe + pipefail SIGPIPEs the 115KB producer (see the
  # upgrade section above) — match on the variable with case instead.
  case "$GEN" in
    *'if [ -z "$EP_SUB" ]; then'*) check "generated battery: run is a second-pass fallback" yes yes ;;
    *) check "generated battery: run is a second-pass fallback" yes no ;;
  esac
fi

echo "=== destructive Docker lifecycle gate (renderer only; no Compose runs)"
GATE_GEN="$TMPD/qa-docker-gate-generated.sh"
BUNKER_QA_ENABLE_DOCKER_LIFECYCLE=0 bash "$HARNESS" __gen-remote gate-check 2>/dev/null > "$GATE_GEN"
if grep -Fq "QA_DOCKER_LIFECYCLE_ENABLED='0'" "$GATE_GEN"; then
  check "Docker lifecycle cells default disabled" yes yes
else
  check "Docker lifecycle cells default disabled" yes no
fi
if [ "$(grep -c 'qa_docker_lifecycle_block_reason' "$GATE_GEN")" -ge 3 ]; then
  check "both Compose lifecycle cells pass through safety gate" yes yes
else
  check "both Compose lifecycle cells pass through safety gate" yes no
fi
if grep -Fq 'active hermes-gateway.service detected' "$GATE_GEN" && grep -Fq '~/.hermes:/opt/data' "$GATE_GEN"; then
  check "active gateway and persistent Hermes bind mount are guarded" yes yes
else
  check "active gateway and persistent Hermes bind mount are guarded" yes no
fi
if bash -n "$GATE_GEN" 2>/dev/null; then
  check "generated gated battery parses without running it" yes yes
else
  check "generated gated battery parses without running it" yes no
fi
if grep -Fq 'local qa_docker_lifecycle_host_block=' "$HARNESS" \
  && grep -Fq 'BUNKER_QA_ENABLE_DOCKER_LIFECYCLE=0' "$HARNESS" \
  && grep -Fq 'systemctl --user is-active --quiet hermes-gateway.service' "$HARNESS"; then
  check "live controller hard-block overrides an inherited opt-in" yes yes
else
  check "live controller hard-block overrides an inherited opt-in" yes no
fi
if BUNKER_QA_ENABLE_DOCKER_LIFECYCLE=maybe bash "$HARNESS" __gen-remote gate-check >/dev/null 2>&1; then
  check "invalid lifecycle flag is rejected" yes no
else
  check "invalid lifecycle flag is rejected" yes yes
fi

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

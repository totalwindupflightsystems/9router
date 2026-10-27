#!/bin/bash
# QA-HERMES-DAGGER-036 — regression test for the bunker-qa.sh docker
# fail-closed gate. Acceptance (from the row):
#   (i)  the fail-closed block in the generator no longer contains an
#        unconditional exit (structural grep over the block);
#   (ii) with a stubbed cell() and QA_DOCKER_OK=0, the extracted block grades
#        exactly the docker/compose cells SKIPPED and returns without exiting;
#   (iii) the generated body's socket discovery names /run/user/$UID/
#        docker.sock before /run/bunker/ (order assertion).
# The block lives inside the generated remote script, so the behavioral half
# extracts it from `bunker-qa.sh __gen-remote` output and runs it under bash
# with stubs; the grep assertions against bunker-qa.sh keep this test in
# lockstep with the harness (drift between the two fails the test).
set -uo pipefail

HARNESS="${BUNKER_QA_SH:-$HOME/.hermes/scripts/bunker-qa.sh}"
# Prefer the checkout-local deployed harness when this regression script is run
# from the Hermes meta-repo; callers can still override BUNKER_QA_SH explicitly.
if [ -z "${BUNKER_QA_SH:-}" ] && [ -f "$(git rev-parse --show-toplevel 2>/dev/null)/.hermes/scripts/bunker-qa.sh" ]; then
  HARNESS="$(git rev-parse --show-toplevel)/.hermes/scripts/bunker-qa.sh"
fi
pass=0; fail=0
check() { # <desc> <expected> <actual>
  if [ "$2" = "$3" ]; then echo "  ok   $1 -> $3"; pass=$((pass+1))
  else echo "  FAIL $1: expected $2 got $3"; fail=$((fail+1)); fi
}

TMPD=$(mktemp -d)
trap 'rm -rf "$TMPD"' EXIT

echo "=== (i) fail-closed block structure (QA-HERMES-DAGGER-036)"
# Raw harness form: the block opens with the ESCAPED probe line
#   if [ \$QA_DOCKER_OK = 0 ]; then
# (single literal backslash in the file) and closes at the next bare 'fi'.
HBLOCK=$(awk '/^if \[ \\\$QA_DOCKER_OK = 0 \]; then$/{f=1} f{print} f&&/^fi$/{exit}' "$HARNESS")
if [ -n "$HBLOCK" ]; then
  check "fail-closed block extracted from harness" yes yes
else
  check "fail-closed block extracted from harness" yes no
fi
case "$HBLOCK" in
  *exit*) check "block contains NO exit (was: exit 2 killed the battery)" absent present ;;
  *)      check "block contains NO exit (was: exit 2 killed the battery)" absent absent ;;
esac
case "$HBLOCK" in
  *CELLS-DONE*) check "block does NOT emit the end-of-battery CELLS-DONE marker" absent present ;;
  *)            check "block does NOT emit the end-of-battery CELLS-DONE marker" absent absent ;;
esac
case "$HBLOCK" in
  *qa-run.finished*) check "block does NOT touch qa-run.finished (that is the true end)" absent present ;;
  *)               check "block does NOT touch qa-run.finished (that is the true end)" absent absent ;;
esac
case "$HBLOCK" in
  *"docker-deploy SKIPPED"*"chaos-shutdown SKIPPED"*)
    check "block grades the docker/compose cells SKIPPED (QA-CONSENSUS-24 vocabulary)" yes yes ;;
  *)  check "block grades the docker/compose cells SKIPPED (QA-CONSENSUS-24 vocabulary)" yes no ;;
esac
# The three NON-compose chaos cells run the native binary (no docker) — they
# must NOT be in the SKIPPED set any more (A2: only docker-deploy + the
# compose chaos cells + the ci-pass act arm grade SKIPPED-with-reason).
case "$HBLOCK" in
  *chaos-corruption*|*chaos-resource*|*chaos-errorpath*)
    check "non-compose chaos cells are NOT pre-graded SKIPPED (they run)" absent present ;;
  *)  check "non-compose chaos cells are NOT pre-graded SKIPPED (they run)" absent absent ;;
esac

echo
echo "=== generated body (via __gen-remote)"
GEN="$TMPD/qa036-gen.sh"
bash "$HARNESS" __gen-remote qa036-failclosed 2>/dev/null > "$GEN"
if [ -s "$GEN" ]; then
  check "generated battery emitted" yes yes
else
  check "generated battery emitted" yes no
fi
if bash -n "$GEN" 2>/dev/null; then
  check "generated battery parses (bash -n)" yes yes
else
  check "generated battery parses (bash -n)" yes no
fi
# (iii) socket discovery order: /run/user/$UID/docker.sock BEFORE /run/bunker/
U_LINE=$(grep -n 'QA_SOCK_USER=' "$GEN" | head -1 | cut -d: -f1)
B_LINE=$(grep -n 'QA_SOCK_BUNKER=' "$GEN" | head -1 | cut -d: -f1)
if [ -n "$U_LINE" ] && [ -n "$B_LINE" ] && [ "$U_LINE" -lt "$B_LINE" ]; then
  check "socket discovery assigns the user socket before the bunker socket" yes yes
else
  check "socket discovery assigns the user socket before the bunker socket" yes no
fi
U_SOCK=$(grep -n '/run/user/' "$GEN" | head -1 | cut -d: -f1)
B_SOCK=$(grep -n '/run/bunker/' "$GEN" | head -1 | cut -d: -f1)
if [ -n "$U_SOCK" ] && [ -n "$B_SOCK" ] && [ "$U_SOCK" -lt "$B_SOCK" ]; then
  check "generated body names /run/user/ before /run/bunker/" yes yes
else
  check "generated body names /run/user/ before /run/bunker/" yes no
fi
# The normal battery end is still the ONLY place CELLS-DONE / qa-run.finished
# are emitted: exactly one occurrence of each, at the tail.
CD_COUNT=$(grep -c '^echo CELLS-DONE$' "$GEN")
FIN_COUNT=$(grep -c '^touch ~/qa-run.finished$' "$GEN")
check "exactly one CELLS-DONE in the generated body (the true end)" 1 "$CD_COUNT"
check "exactly one qa-run.finished touch in the generated body" 1 "$FIN_COUNT"
# The rootless-daemon start arm is gated on the lifecycle opt-in + host block.
if grep -qF 'if [ $QA_DOCKER_OK = 0 ] && [ "$QA_DOCKER_LIFECYCLE_ENABLED" = "1" ] && [ "$QA_DOCKER_LIFECYCLE_HOST_BLOCK" != "1" ]; then' "$GEN"; then
  check "rootless start arm gated on lifecycle opt-in AND host-block clear" yes yes
else
  check "rootless start arm gated on lifecycle opt-in AND host-block clear" yes no
fi
# The second per-cell docker-deploy gate (kept as defense in depth).
if grep -qF 'cell docker-deploy SKIPPED "docker unavailable on agent (QA-CONSENSUS-24 fail-closed)' "$GEN"; then
  check "second docker-deploy SKIPPED arm kept" yes yes
else
  check "second docker-deploy SKIPPED arm kept" yes no
fi
# The ci-pass act arm is docker-gated (SKIPPED-with-reason, native arm runs).
if grep -qF 'CI_ACT_DOCKER_SKIP=1' "$GEN" && grep -qF 'cell ci-act SKIPPED "act needs docker' "$GEN"; then
  check "ci-pass act arm gated + graded ci-act SKIPPED" yes yes
else
  check "ci-pass act arm gated + graded ci-act SKIPPED" yes no
fi

echo
echo "=== (ii) extracted block runs under stubs and RETURNS (no exit)"
GBLOCK=$(awk '/^if \[ \$QA_DOCKER_OK = 0 \]; then$/{f=1} f{print} f&&/^fi$/{exit}' "$GEN")
if [ -n "$GBLOCK" ]; then
  check "fail-closed block extracted from generated body" yes yes
else
  check "fail-closed block extracted from generated body" yes no
fi
STUB="$TMPD/stub-run.sh"
CELLS_LOG="$TMPD/cells.log"
{
  printf '%s\n' '#!/usr/bin/env bash'
  printf 'cell() { printf "CELL %%s|%%s|%%s\n" "$1" "$2" "$3" >> "%s"; }\n' "$CELLS_LOG"
  printf '%s\n' 'QA_DOCKER_OK=0'
  printf '%s\n' "$GBLOCK"
  printf '%s\n' 'echo "BLOCK-RETURNED rc=$?"'
} > "$STUB"
bash -n "$STUB" 2>/dev/null
check "stub runner parses (bash -n)" 0 "$?"
STUB_OUT=$(bash "$STUB" 2>&1); stub_rc=$?
check "stubbed block returns rc=0 (no script-wide exit)" 0 "$stub_rc"
case "$STUB_OUT" in
  *BLOCK-RETURNED*) check "execution continued past the block" yes yes ;;
  *)                check "execution continued past the block" yes no ;;
esac
if [ -s "$CELLS_LOG" ]; then
  check "stubbed cell() recorded rows" yes yes
else
  check "stubbed cell() recorded rows" yes no
fi
for want in 'CELL docker-deploy|SKIPPED|' 'CELL chaos-shutdown|SKIPPED|' 'CELL toolchain-bootstrap|INFO|'; do
  if grep -qF "$want" "$CELLS_LOG" 2>/dev/null; then
    check "stubbed grade present: $want" yes yes
  else
    check "stubbed grade present: $want" yes no
  fi
done
for absent in chaos-corruption chaos-resource chaos-errorpath ci-pass upgrade ui-probe chaos-disconnect; do
  if grep -qF "CELL $absent|" "$CELLS_LOG" 2>/dev/null; then
    check "block does NOT grade $absent (runs normally later)" absent present
  else
    check "block does NOT grade $absent (runs normally later)" absent absent
  fi
done

echo
echo "=== harness lockstep greps"
# The baked DOCKER_HOST prefix on the act command is gone (discovery exports
# the answering socket before the act leg runs).
ACT_PREFIX_COUNT=$(grep -c 'DOCKER_HOST=unix:///run/bunker/\$agent/docker.sock ~/bin/act' "$HARNESS" || true)
check "no baked DOCKER_HOST prefix on the act command (host-side)" 0 "$ACT_PREFIX_COUNT"
# Dual-path poll present in the harness (escaped form in the heredoc body).
if grep -qF 'for i in \$(seq 1 20); do [ -S "\$QA_SOCK_USER" ] || [ -S "\$QA_SOCK_BUNKER" ] && break; sleep 2; done' "$HARNESS"; then
  check "dual-socket poll inside the existing ~40s budget" yes yes
else
  check "dual-socket poll inside the existing ~40s budget" yes no
fi
# docker-deploy and chaos-shutdown carry the per-cell QA_DOCKER_OK guard.
GATE_COUNT=$(grep -cF ': # QA-HERMES-DAGGER-036: graded SKIPPED in the QA-CONSENSUS-24 block above' "$HARNESS" || true)
check "per-cell docker gates on docker-deploy + chaos-shutdown" 2 "$GATE_COUNT"

echo
echo "RESULT: $pass passed, $fail failed"
[ "$fail" -eq 0 ]

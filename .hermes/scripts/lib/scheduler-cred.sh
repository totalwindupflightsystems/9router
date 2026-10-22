#!/usr/bin/env bash
# Shared scheduler operator-credential resolution (SCHED-GAP-1756).
#
# Both drain-restart helpers source this file so the ladder exists ONCE. Before it,
# each script carried its own credential wiring and they disagreed: one sent
# API_SERVER_KEY as `Authorization: Bearer` (the GATEWAY key — the daemon answers
# 401 "invalid operator credential"), the other used the operator token but counted a
# 401 as a successful pause. Either way a failed deploy could leave the fleet parked.
#
# This is SOURCE-ONLY: no side effects at load time. The sourcing script must define,
# BEFORE the source line:
#   API       base URL of the daemon          (e.g. http://127.0.0.1:9090)
#   AUTH_ENV  file holding SCHEDULER_OPERATOR_TOKEN (the daemon's own EnvironmentFile)
#   ENV_FILE  file holding API_SERVER_KEY      (the gateway key — fallback rung only)
#   log()     a logging function taking one string
# and must declare PAUSED/RESUMED (default 0). The functions here maintain:
#   AUTH_MODE   operator | bearer | none   — THE one resolved credential
#   CRED_LABEL  human-readable name of it (never the value)
#   CRED_DIR    0700 temp dir holding 0600 curl config files (credentials never in argv)
#   PAUSED      1 while this script believes the fleet is parked by it
#   RESUMED     1 once a resume has been confirmed with HTTP 200
#
# Contract: a credential is only ever adopted after a 200 from a real mutation; a 401
# from the rung that is tried changes nothing server-side, which is why pause itself
# can be the probe.

# --- credential sources ----------------------------------------------------
# The daemon's own EnvironmentFile is the source of truth for the operator token.
read_operator_token() {
  [ -r "$AUTH_ENV" ] || return 1
  local line
  line=$(grep -m1 '^SCHEDULER_OPERATOR_TOKEN=' "$AUTH_ENV" 2>/dev/null) || return 1
  printf '%s' "${line#SCHEDULER_OPERATOR_TOKEN=}" | tr -d '[:space:]'
}

read_gateway_key() {
  [ -r "$ENV_FILE" ] || return 1
  local line
  line=$(grep -m1 '^API_SERVER_KEY=' "$ENV_FILE" 2>/dev/null) || return 1
  printf '%s' "${line#API_SERVER_KEY=}" | tr -d '[:space:]'
}

# curl reads the credential from a 0600 config file, never from argv: argv is `ps`-readable.
write_curl_config() {  # $1=name $2=full header line
  local name=$1 header=$2
  case "$header" in
    *'"'*|*'\'*|*$'\n'*) log "!! refusing a credential containing a quote/backslash/newline ($name)"; return 1 ;;
  esac
  printf 'header = "%s"\n' "$header" > "$CRED_DIR/$name.curl" || return 1
  chmod 600 "$CRED_DIR/$name.curl"
}

init_credentials() {
  OP_TOKEN=$(read_operator_token) || OP_TOKEN=""
  KEY=$(read_gateway_key) || KEY=""

  CRED_DIR=$(mktemp -d "${TMPDIR:-/tmp}/.sched-deploy-creds.XXXXXX") || {
    log "!! FATAL: cannot create a private credential dir under ${TMPDIR:-/tmp}"
    return 1
  }
  chmod 700 "$CRED_DIR"

  if [ -n "$OP_TOKEN" ]; then
    write_curl_config operator "X-Operator-Token: $OP_TOKEN" || return 1
  else
    log "warn: no SCHEDULER_OPERATOR_TOKEN in $AUTH_ENV (rung 1 will be skipped)"
  fi
  if [ -n "$KEY" ]; then
    write_curl_config bearer "Authorization: Bearer $KEY" || return 1
  else
    log "warn: no API_SERVER_KEY in $ENV_FILE (rung 2 will be skipped)"
  fi
  return 0
}

cleanup_credentials() {
  [ -n "${CRED_DIR:-}" ] && rm -rf "$CRED_DIR"
  CRED_DIR=""
}

# --- http helpers ----------------------------------------------------------
api() {  # curl with the CURRENT AUTH_MODE's credential
  local cfg="$CRED_DIR/${AUTH_MODE}.curl"
  case "$AUTH_MODE" in
    operator|bearer) curl -s -m 25 -K "$cfg" "$@" ;;
    none)            curl -s -m 25 "$@" ;;
    *) echo "internal error: AUTH_MODE=$AUTH_MODE" >&2; return 90 ;;
  esac
}

# Reads are open on the gate; keep them credential-free so a bad credential can never
# blind a drain loop (the 2026-10-22 run logged active_ticks=? whenever the cred broke).
status_json() { curl -s -m 25 "$API/api/v1/status"; }

body_snip() { head -c 200 "$1" 2>/dev/null | tr -d '\n'; }

http_post() {  # $1=AUTH_MODE $2=url $3=body-file -> echoes the HTTP status ('000' = no answer)
  local mode=$1 url=$2 out=$3 code
  AUTH_MODE=$mode
  code=$(api -o "$out" -w '%{http_code}' -X POST "$url") || code="000"
  [ -n "$code" ] || code="000"
  printf '%s' "$code"
}

# --- credential resolution IS the pause ------------------------------------
# A 401 changes no server state, so it is a safe probe. The first rung that returns 200
# becomes THE credential for every later call; if neither does, the caller must stop
# here having paused nothing (so there is nothing for an EXIT trap to restore).
resolve_and_pause() {
  local code op_code="absent" key_code="absent"

  if [ -n "${OP_TOKEN:-}" ]; then
    code=$(http_post operator "$API/api/v1/pause" "$CRED_DIR/pause.operator.json")
    op_code=$code
    log "pause attempt 1/2: X-Operator-Token ($AUTH_ENV) -> HTTP $code $(body_snip "$CRED_DIR/pause.operator.json")"
    if [ "$code" = "200" ]; then
      AUTH_MODE=operator
      CRED_LABEL="X-Operator-Token (SCHEDULER_OPERATOR_TOKEN from $AUTH_ENV)"
      PAUSED=1
      log "   credential RESOLVED: $CRED_LABEL — every later call uses this one"
      return 0
    fi
  else
    log "pause attempt 1/2: X-Operator-Token -> SKIPPED (no SCHEDULER_OPERATOR_TOKEN in $AUTH_ENV)"
  fi

  if [ -n "${KEY:-}" ]; then
    code=$(http_post bearer "$API/api/v1/pause" "$CRED_DIR/pause.bearer.json")
    key_code=$code
    log "pause attempt 2/2: Authorization: Bearer ($ENV_FILE API_SERVER_KEY) -> HTTP $code $(body_snip "$CRED_DIR/pause.bearer.json")"
    if [ "$code" = "200" ]; then
      AUTH_MODE=bearer
      CRED_LABEL="Authorization: Bearer (API_SERVER_KEY from $ENV_FILE)"
      PAUSED=1
      log "   credential RESOLVED: $CRED_LABEL — every later call uses this one"
      return 0
    fi
  else
    log "pause attempt 2/2: Authorization: Bearer -> SKIPPED (no API_SERVER_KEY in $ENV_FILE)"
  fi

  log "!! NO WORKING CREDENTIAL: X-Operator-Token=$op_code, Bearer(API_SERVER_KEY)=$key_code"
  case "$op_code$key_code" in
    *000*) log "   '000' = the daemon never answered: check schedulerd is listening on $API" ;;
  esac
  case "$op_code$key_code" in
    *503*) log "   503 = mutations disabled daemon-side: the unit has NO operator credential configured" ;;
  esac
  case "$op_code$key_code" in
    *401*401*) log "   both 401 = the daemon holds an operator token that matches neither source above" ;;
  esac
  log "   nothing was paused by this script, so there is no state to restore — refusing to continue"
  AUTH_MODE=none
  return 1
}

# --- resume: a non-200 is a FAILURE, never success -------------------------
resume() {
  local code
  code=$(http_post "$AUTH_MODE" "$API/api/v1/resume" "$CRED_DIR/resume.json")
  if [ "$code" = "200" ]; then
    RESUMED=1
    PAUSED=0
    log "resume -> HTTP 200 $(body_snip "$CRED_DIR/resume.json") (credential: ${CRED_LABEL:-none})"
    return 0
  fi
  log "!! RESUME FAILED -> HTTP $code $(body_snip "$CRED_DIR/resume.json") — the fleet may still be PAUSED"
  log "   a non-200 resume is a FAILURE: the daemon refused the credential, so scheduling stays parked"
  return 1
}

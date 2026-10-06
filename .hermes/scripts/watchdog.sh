#!/bin/bash
# coding-hermes watchdog — polls the scheduler and alerts on failures.
# Run as a Hermes no_agent cron every 2m.
# State file tracks consecutive failures for escalation.
#
# 2026-09-21 (supervisor tick) — false-CRITICAL repair.
# The health endpoint is DB-backed and the daemon opens ONE serialized SQLite
# connection (internal/database/schema.go: db.SetMaxOpenConns(1), PRAGMA
# busy_timeout=5000). Under a load storm (10 concurrent ticks + the eval pass
# queueing on the same single connection) /api/v1/health does not answer inside
# a 5s budget, while the daemon is demonstrably alive — measured 2026-09-21:
# five consecutive probes returned HTTP 000 at exactly the 5014ms cut-off, and
# minutes later the same endpoint answered in 9-14ms with the daemon reporting
# status=ok / db=connected / eval age 0.6s and 529 completed ticks in 24h.
# Three such probes in a row printed "Scheduler DOWN" to Telegram for a
# scheduler that was healthy. Two changes:
#   1. PROBE_TIMEOUT 5s -> 25s (comfortably above the pool's own 5s busy_timeout
#      plus connection-queue latency).
#   2. The verdict now consults the systemd unit FIRST (cheap, DB-free and
#      authoritative). A timed-out HTTP probe while the unit is active is
#      reported as a slow-probe DEGRADED condition after 2 consecutive misses —
#      never as "DOWN".  1 HTTP miss while the unit is active stays silent.
# Genuine outages are still caught, and now caught by the strong signal.
#
# 2026-09-22 (supervisor tick) — second false-CRITICAL repair, same root idea.
# The 09-21 hardening made /api/v1/live the authoritative liveness signal, but
# the route landed (95516e44) AFTER the running daemon was built, so the
# deployed binary answers 404 and the "provably up" fast path was dead code:
# the streak file could never be reset and grew to 33 FAIL lines against a
# daemon reporting status=ok / active_ticks>0 for 19h. Three changes:
#   1. HTTP 404 on /live = ROUTE-UNAVAILABLE (fall back), never a probe miss.
#   2. The streak resets whenever the unit is active AND /health answers.
#   3. An undeterminable unit state (no user bus) can never write FAIL; it is
#      reported as probe ambiguity at DEGRADED_ALERT_AFTER, exit 0.
# Knobs SCHEDULER/STATE_FILE are now env-overridable so the branches are
# testable without touching the live state file.

SCHEDULER="${SCHEDULER:-http://127.0.0.1:9090}"
STATE_FILE="${STATE_FILE:-${HOME}/.hermes/coding-hermes/watchdog.state}"
MAX_SILENCE_MIN=15      # Dead-man's switch: alert if no eval for this long
PROBE_TIMEOUT=30        # seconds; must exceed the DB pool's busy_timeout (5s).
                        # Generous by design: a DEAD daemon refuses the
                        # connection immediately (instant HTTP 000), so this
                        # budget only ever elapses for a listening-but-slow
                        # daemon — it costs no outage-detection latency.
LIVE_TIMEOUT=5          # /api/v1/live is DB-free (SCHED-GAP-204-A) and answers
                        # in <10ms; a 5s budget is 500x the expected latency
                        # and still well under the PROBE_TIMEOUT for fallback.
DEGRADED_ALERT_AFTER=2  # consecutive slow probes before speaking up

UNIT="coding-hermes-scheduler"

mkdir -p "$(dirname "$STATE_FILE")"

fail_count() {
    # Counts BOTH streak markers. `grep -c` prints 0 and exits 1 on no match —
    # the `|| true` keeps that from double-printing "0" (which corrupted the
    # counter into an arithmetic-eval error in a prior revision).
    local n
    n=$(grep -c -E '^(FAIL|SLOW)' "$STATE_FILE" 2>/dev/null) || true
    [ -z "$n" ] && n=0
    echo "$n"
}

# ── 0. Unit state (DB-free, authoritative) ──
# Empty output = could not determine (no user bus in this context): fall back
# to HTTP-only judgement rather than inventing an outage.
UNIT_ACTIVE=$(XDG_RUNTIME_DIR="/run/user/$(id -u)" systemctl --user is-active "$UNIT" 2>/dev/null)

# SCHED-GAP-216: the system-scope watchdog.timer (User=kara, no user bus) could
# never resolve the unit state — `systemctl --user is-active` failed with
# "$DBUS_SESSION_BUS_ADDRESS and $XDG_RUNTIME_DIR not defined" on EVERY
# production run, so UNIT_ACTIVE was permanently "unknown" and the
# unit-active branch (the strongest DOWN-prevention signal) was dead code.
# Two bus-free fallbacks, in order:
#   1. export XDG_RUNTIME_DIR explicitly (the user manager's runtime dir is
#      deterministic: /run/user/<uid>) — resolves on any normal host;
#   2. cgroup membership: systemd removes the unit's cgroup directory when the
#      unit stops, so a present directory means the unit is running — works
#      even when the user bus itself is unreachable.
# The ambiguity branch stays for genuinely undeterminable contexts (it is what
# prevents false CRITICALs — do not remove it).
if [ -z "$UNIT_ACTIVE" ]; then
    if [ -d "/sys/fs/cgroup/user.slice/user-$(id -u).slice/user@$(id -u).service/app.slice/${UNIT}.service" ]; then
        UNIT_ACTIVE="active"
    fi
fi
[ -z "$UNIT_ACTIVE" ] && UNIT_ACTIVE="unknown"

# ── 1. Liveness probe — DB-free first (SCHED-GAP-204-A) ──
# /api/v1/live is the cheap route: it answers from process memory only, no
# SQLite, and returns in <10ms. We probe it first under a tight 5s budget.
# Only if /api/v1/live fails do we fall through to the rich /api/v1/health
# (DB-backed, single-connection, can queue for seconds under load) to
# distinguish "daemon dead" from "DB-backed probe queueing".
LIVE=$(curl -s -o /tmp/.chs-watchdog-live.json -w "%{http_code}" \
    --max-time "$LIVE_TIMEOUT" "${SCHEDULER}/api/v1/live" 2>/dev/null)

# 2026-09-22 (supervisor tick) — the route may not exist in the DEPLOYED
# binary. /api/v1/live landed in 95516e44 (09-21 17:17 local) while the running
# daemon was built at 09-21 12:20, so a perfectly healthy daemon answers
# 404 "page not found". Treat 404 as ROUTE-UNAVAILABLE — fall back to the
# unit + rich-probe verdict — instead of as a failed liveness probe, and never
# let a missing route poison the streak file. Poisoning it is exactly what made
# this watchdog print "Scheduler DOWN for N+ minutes" for a live daemon.
if [ "$LIVE" = "404" ]; then
    LIVE="unsupported"
fi

if [ "$LIVE" = "200" ]; then
    # /api/v1/live answered — daemon is provably up. We still want the rich
    # payload below for the dead-man's switch, but liveness is decided HERE.
    : # fall through to the rich probe, which is bounded by PROBE_TIMEOUT
fi

# ── 1b. Rich health probe — DB-backed, used for the dead-man's switch ──
HEALTH=$(curl -s -o /tmp/.chs-watchdog-health.json -w "%{http_code}" \
    --max-time "$PROBE_TIMEOUT" "${SCHEDULER}/api/v1/health" 2>/dev/null)

# Health/liveness result: /api/v1/live is the AUTHORITATIVE liveness signal
# (DB-free, <10ms, never queues). /api/v1/health is the rich payload source
# for the dead-man's switch but is no longer in the liveness critical path.
# A /api/v1/live 200 with /api/v1/health failing is the exact SCHED-GAP-204-A
# scenario the route was built for: daemon alive, DB queueing, NOT an outage.
if [ "$LIVE" = "200" ] || { [ "$HEALTH" = "200" ] && [ "$UNIT_ACTIVE" = "active" ]; }; then
    # Daemon provably up: the DB-free route answered, or the systemd unit is
    # active AND the rich probe answered. Reset the failure streak (silent
    # recovery). 2026-09-22: the old condition keyed the reset on /live only,
    # so while the deployed binary lacked that route (404) the streak could
    # never reset and grew to 33 entries against a daemon reporting status=ok.
    rm -f "$STATE_FILE"
    # Continue to the dead-man's switch below using whatever /api/v1/health
    # returned (success, timeout, or partial). Its absence there is fine —
    # the dead-man switch handles unreadable payloads by exiting 0 silently.
fi

if [ "$LIVE" != "200" ] && [ "$HEALTH" != "200" ]; then
    # BOTH probes failed — apply the standard outage judgement. The /api/v1/live
    # failure alone (with /api/v1/health 200) is treated as a DEGRADED condition
    # handled below, not a hard outage.
    if [ "$UNIT_ACTIVE" = "active" ]; then
        # Daemon process is up and systemd says so — the probe is slow, not the
        # daemon dead. Ride out a single slow window silently.
        FAILS=$(fail_count); FAILS=$((FAILS + 1))
        echo "SLOW $(date -Iseconds)" >> "$STATE_FILE"
        if [ "$FAILS" -ge "$DEGRADED_ALERT_AFTER" ]; then
            echo "⚠️ Scheduler health probe slow ($FAILS consecutive, HTTP $HEALTH after ${PROBE_TIMEOUT}s) but unit '$UNIT' is ACTIVE — daemon is up, DB-backed probe is queueing (single SQLite connection). Not an outage."
        fi
        exit 0
    fi
    # Unit determinably NOT active and the probes failed → real outage.
    if [ "$UNIT_ACTIVE" != "unknown" ]; then
        FAILS=$(fail_count); FAILS=$((FAILS + 1))
        echo "FAIL $(date -Iseconds)" >> "$STATE_FILE"
        if [ "$FAILS" -eq 1 ]; then
            echo "⚠️ Scheduler unreachable (attempt 1/3). HTTP $HEALTH, unit=$UNIT_ACTIVE"
        elif [ "$FAILS" -eq 2 ]; then
            echo "⚠️⚠️ Scheduler still down (attempt 2/3). HTTP $HEALTH, unit=$UNIT_ACTIVE"
        else
            echo "🚨 CRITICAL: Scheduler DOWN for $(($FAILS * 2))+ minutes. HTTP $HEALTH, unit=$UNIT_ACTIVE. Check systemd: systemctl --user status $UNIT"
        fi
        exit 1
    fi
    # unit=unknown (no user bus in this execution context): both probes timed
    # out but nothing can prove the process is gone, so this is ambiguity, not
    # an outage. 2026-09-22 — every one of the 33 stale FAIL lines was written
    # while the daemon was demonstrably up; an undeterminable unit state must
    # never produce a DOWN verdict on its own.
    FAILS=$(fail_count); FAILS=$((FAILS + 1))
    echo "SLOW $(date -Iseconds)" >> "$STATE_FILE"
    if [ "$FAILS" -ge "$DEGRADED_ALERT_AFTER" ]; then
        echo "⚠️ Scheduler probes failing (live=$LIVE health=$HEALTH) while the systemd unit state is undeterminable in this context — cannot prove an outage. Verify: systemctl --user status $UNIT"
    fi
    exit 0
fi

# ── 2. Dead-man's switch — has evaluation been running? ──
# evaluation_age_seconds comes from the SAME health payload we already fetched,
# so this no longer costs a second DB-heavy round trip on /api/v1/status
# (which is subject to the same single-connection queueing).
LAST_EVAL=$(python3 - <<'PY' 2>/dev/null
import json
try:
    d = json.load(open('/tmp/.chs-watchdog-health.json'))
    v = d.get('evaluation_age_seconds')
    print(-1 if v is None else int(float(v)))
except Exception:
    print(-1)
PY
)

if [ "$LAST_EVAL" = "-1" ]; then
    # Payload unreadable/field absent — do not invent a stall.
    exit 0
elif [ "$LAST_EVAL" -gt $((MAX_SILENCE_MIN * 60)) ] 2>/dev/null; then
    echo "🚨 DEAD-MAN'S SWITCH: No evaluation for ${LAST_EVAL}s (>${MAX_SILENCE_MIN}min). Scheduler may be stuck."
    exit 1
fi

# All checks passed — silent (healthy watchdog stays quiet).
exit 0

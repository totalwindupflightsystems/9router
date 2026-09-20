#!/usr/bin/env python3
"""Fleet arming tripwire — arms-parity between scheduler.db and fleet.toml.

Design (v3, 2026-09-11):
The generator (fleet-cooldown-policy.py) arms every project whose
namespace is in ADAPTIVE_LANES, and regen writes ONLY ENABLED projects.
So the ground truth for both sides is:

    armed(project) = enabled=1 AND namespace_id IN ADAPTIVE_LANES

The tripwire recomputes that expectation from the LIVE DB on every run —
no hardcoded count. Bane disabling projects for resource savings (the
2026-09-11 wave: 179→103 enabled) must never look like arming drift,
and a future re-enable must never hide real drift either.

Checks:
  T1  DB: count(enabled + foreman-namespace) armed rows match toml count
  T2  DB: every armed row ceiling == 8x floor
  T3  DB: no armed row's live cooldown_s below its floor
  T4  toml: unparseable numbers / bad ceiling in any adaptive block
  T6  set-parity: same NAMES armed in DB and toml, both computed by the
      same enabled+namespace rule
  T7  enabled project carrying the retired `command` route
Exit 0 silent when healthy; exit 1 with report on any drift.

Re-alert throttle (v4, 2026-09-17):
This is an hourly cron with a FAILING exit on drift, and the platform
escalates a streak of 5+ failures. Drift of this class is real but is
healed out-of-band (cron 'Coding Hermes Supervisor' PUTs the flag, a
policy --apply regen, a scheduler restart) — measured window 2-8h, so one
incident used to page 6-8 times about an identical, already-known state.
A PERSISTING IDENTICAL problem set now pages once, then stays quiet
(exit 0, appended to the log) until REALERT_H elapses. Any CHANGE in the
problem set (new project, new check, resolved-then-recurs) pages
immediately — the throttle only ever suppresses a verbatim repeat.

Operator overrides (tests / forensics):
  ARMING_TRIPWIRE_DB, ARMING_TRIPWIRE_FLEET, ARMING_TRIPWIRE_STATE,
  ARMING_TRIPWIRE_LOG, ARMING_TRIPWIRE_REALERT_H
"""
import hashlib
import json
import os
import re
import sqlite3
import subprocess
import sys
import time

DB = os.environ.get("ARMING_TRIPWIRE_DB", "/home/kara/.hermes/coding-hermes/scheduler.db")
FLEET = os.environ.get("ARMING_TRIPWIRE_FLEET", "/home/kara/.hermes/fleet.toml")
STATE = os.environ.get("ARMING_TRIPWIRE_STATE", "/home/kara/.hermes/state/arming-tripwire.json")
LOG = os.environ.get("ARMING_TRIPWIRE_LOG", "/home/kara/.hermes/logs/fleet-arming-tripwire.log")
REALERT_H = float(os.environ.get("ARMING_TRIPWIRE_REALERT_H", "6"))
ADAPTIVE_LANES = {"coding-hermes"}  # keep in sync with fleet-cooldown-policy.py
MULT = 8
SNAP = "/tmp/arming-tripwire-snap.db"


def log(line):
    try:
        os.makedirs(os.path.dirname(LOG), exist_ok=True)
        with open(LOG, "a") as f:
            f.write(f"{time.strftime('%Y-%m-%d %H:%M:%S%z')} {line}\n")
    except OSError:
        pass


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def save_state(state):
    try:
        os.makedirs(os.path.dirname(STATE), exist_ok=True)
        tmp = STATE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(state, f)
        os.replace(tmp, STATE)
    except OSError:
        pass


problems = []

# --- DB: recompute the armed set from the generator's rule ---
r = subprocess.run(["sqlite3", DB, f".backup '{SNAP}'"], capture_output=True, text=True)
if r.returncode != 0:
    print(f"TRIPWIRE ERROR: cannot snapshot DB: {r.stderr.strip()}")
    sys.exit(1)
db = sqlite3.connect(SNAP)
rows = db.execute(
    "SELECT name, namespace_id, enabled, cooldown_s, cooldown_floor_s, "
    "cooldown_ceiling_s, adaptive_cooldown FROM projects"
).fetchall()
# T7 data (prompt-only mode): fetched while the snapshot is open
t7_violations = [
    r[0] for r in db.execute(
        "SELECT name FROM projects WHERE enabled=1 AND command IS NOT NULL AND command != ''"
    )
]
db.close()
os.remove(SNAP)

db_armed = {}
for name, ns, en, cd, fl, ce, ac in rows:
    if not en:
        continue
    if ns not in ADAPTIVE_LANES:
        # arming on a non-foreman-lane enabled project = config drift
        if ac:
            problems.append(f"T1: {name} armed but namespace '{ns}' not in ADAPTIVE_LANES")
        continue
    # TASKS-ADMISSION LAW (Bane 2026-09-19): the coding-hermes namespace is
    # tasks-admission — lanes spawn from board state, never the cooldown
    # timer — so adaptive_cooldown is DEAD BOOKKEEPING there. Expected state:
    # flag OFF. An armed row is config drift (the policy regen stopped
    # emitting the flag for tasks namespaces); a disarmed row is CORRECT and
    # is NOT counted into the armed set at all.
    if ns == "coding-hermes":
        if ac:
            problems.append(f"T1: {name} armed but namespace 'coding-hermes' is tasks-admission (adaptive flag is dead bookkeeping — disarm)")
        continue
    if not ac:
        # expected-armed but flag off = REAL arming drift (timer-based lane)
        problems.append(f"T1: {name} foreman-lane enabled but adaptive_cooldown=0 (disarmed)")
        continue
    db_armed[name] = (cd, fl, ce)

for n, (cd, fl, ce) in sorted(db_armed.items()):
    if ce != MULT * fl:
        problems.append(f"T2: {n} ceiling {ce} != {MULT}x floor {fl}")
    if cd < fl:
        problems.append(f"T3: {n} live cooldown_s {cd} BELOW floor {fl}")

# --- fleet.toml armed set (same rule: only enabled blocks carry the key,
#     but honor enabled=false explicitly just in case) ---
txt = open(FLEET).read()
blocks = re.split(r"\[\[projects\]\]", txt)[1:]
toml_armed = {}
for b in blocks:
    kv = dict(re.findall(r"^(\w+)\s*=\s*\"?([^\"\n]*)\"?\s*$", b, re.M))
    if kv.get("adaptive_cooldown") != "true":
        continue
    name = kv.get("name", "?")
    if kv.get("enabled") == "false":
        problems.append(f"T4: {name} armed in toml but enabled=false (stale regen)")
        continue
    try:
        cd, fl, ce = (int(kv.get("cooldown_s", 0)), int(kv.get("cooldown_floor_s", 0) or 0),
                      int(kv.get("cooldown_ceiling_s", 0)))
    except ValueError:
        problems.append(f"T5: {name} unparseable cooldown numbers")
        continue
    toml_armed[name] = (cd, fl, ce)
    floor = fl or cd
    if ce != MULT * floor:
        problems.append(f"T5: {name} toml ceiling {ce} != {MULT}x floor {floor}")

db_names, toml_names = set(db_armed), set(toml_armed)
if db_names != toml_names:
    only_db, only_toml = db_names - toml_names, toml_names - db_names
    problems.append(
        f"T6: armed-set mismatch DB-vs-fleet.toml; "
        f"only_in_db={sorted(only_db)} only_in_toml={sorted(only_toml)}"
    )

# --- T7: prompt-only mode (Bane 2026-09-11: command route retired) ---
# ANY enabled project with a non-empty command = the retired command route
# coming back. Disabled rows may keep their command text for review.
for n in t7_violations:
    problems.append(f"T7: {n} enabled with command route set (prompt-only mode violated)")

sig = hashlib.sha256("\n".join(sorted(problems)).encode()).hexdigest()[:12]
state = load_state()
now = time.time()

if not problems:
    if state.get("sig"):
        log(f"CLEARED: drift '{state['sig']}' resolved after "
            f"{int((now - state.get('last_alert', now)) / 60)}min "
            f"({len(state.get('problems', []))} problem(s))")
        save_state({})
    # healthy: stay silent
    sys.exit(0)

last_sig = state.get("sig")
last_alert = float(state.get("last_alert", 0) or 0)
if last_sig == sig and (now - last_alert) < REALERT_H * 3600:
    # Same verbatim drift, already paged recently: log it, stay quiet so the
    # cron shows green instead of escalating a known-and-filed condition.
    log(f"SUPPRESSED re-alert (sig={sig}, last_alert="
        f"{int((now - last_alert) / 60)}min ago, window={REALERT_H:g}h, "
        f"{len(problems)} problem(s)): {' | '.join(problems)}")
    sys.exit(0)

save_state({"sig": sig, "last_alert": now, "problems": sorted(problems),
            "alerted_at": time.strftime("%Y-%m-%d %H:%M:%S%z")})
log(f"ALERT (sig={sig}, {len(problems)} problem(s)): {' | '.join(problems)}")
print("FLEET ARMING TRIPWIRE — DRIFT DETECTED:")
for p in problems:
    print("  -", p)
sys.exit(1)

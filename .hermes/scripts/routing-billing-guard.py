#!/usr/bin/env python3
"""routing-billing-guard.py — end-to-end regression guard for the
provider/model passing bug (Bane 2026-08-31).

The bug class: a caller sends model="provider/model" as ONE string (or a bare
model) with NO separate provider field → the gateway silently falls back to
its config default → every call bills the PRIMARY PAYG key instead of the
subscription lane.

Layer 1 (unit):  src/bridge/hermes_api_wire_test.go asserts the wire JSON
                   always carries a separate provider field.
Layer 2 (this):   live billing assertion — scan state.db api_server sessions
                   for PAYG-default billing that the gateway did NOT explain
                   as a lane fallback.

WHY THE GUARD WINDOWS FALLBACKS (2026-09-17):
  state.db's billing_provider records the lane that ACTUALLY SERVED the
  request, not the lane the caller asked for. When an intended sub lane
  answers 429 (OpenAI/ChatGPT plan usage limit, zai-glm weekly quota), the
  gateway does what it is configured to do — it falls back to the deepseek
  PAYG lane — and the session lands in state.db billed provider='deepseek'.
  Counting those as "the provider field did not reach the gateway" produced
  12 consecutive false alarms (2026-09-05..17): a live audit of the window
  found 274/274 flagged sessions explained by a logged
  `Fallback activated: <lane> → deepseek-v4-flash (deepseek)` line, 0
  unexplained. So the PASS criterion is now evidence-based:
    LEAK   = billed on the PAYG default AND no fallback explanation in the
             gateway log for that session in the same window.
    BENIGN = billed on the PAYG default WITH a logged lane fallback
             (reported as lane-capacity telemetry on stderr, never a fail).
  A missing log line is NOT silently clean: when the parsed logs cover the
  whole window an unexplained hit fails; when they do not, the run reports a
  coverage warning instead of inventing a regression.

Usage:
  routing-billing-guard.py [--hours N] [--since EPOCH] [--json]
                           [--log-dir DIR] [--strict]
Options:
  --strict   legacy view: ANY api_server session billed on the PAYG default
             fails, fallback or not (the 2026-09-05..17 alarm behavior).
Exit codes:
  0  clean — every PAYG-default session in the window is an explained
             fallback (or logs pin the hits as unverifiable)
  1  REGRESSION — unexplained PAYG-default billing (the bug)
"""
import argparse
import glob
import json
import os
import re
import sqlite3
import sys
import time

STATE_DB = os.path.expanduser("~/.hermes/state.db")
DEFAULT_LOG_DIR = os.path.expanduser("~/.hermes/logs")

# The gateway config default: provider "deepseek" = the PRIMARY PAYG key.
# Callers that DO pass a provider land under that provider's own billing name
# (custom / openai-codex / stepfun ...), so a bare "deepseek" billing_provider
# on an api_server session means the request reached the PAYG lane — either
# because the gateway chose it (the bug) or because it fell back to it after a
# lane refused (benign, and evidenced by the fallback line parsed below).
PAYG_DEFAULT_PROVIDER = "deepseek"
PAYG_DEFAULT_MODEL = "deepseek-v4-flash"  # bare, no :0731 suffix

# Session sources that are legitimately on the primary key: the chat
# surfaces (telegram/signal/whatsapp) use the config default by design.
# Only api_server sessions are in scope — that is the fleet's gateway path.
LEGIT_SOURCES = {"telegram", "signal", "whatsapp", "local", "cli", "api"}

# Gateway log lines (agent.log*):
#   2026-09-17 09:23:02,560 INFO [api-ef12c502c44b2efb] agent.turn_context:
#       conversation turn: session=api-... model=gpt-5.6-sol provider=openai-codex platform=api_server ...
#   2026-09-17 09:23:03,696 INFO [api-ef12c502c44b2efb] agent.chat_completion_helpers:
#       Fallback activated: gpt-5.6-sol → deepseek-v4-flash (deepseek)
_TURN_RE = re.compile(
    r"^(?P<ts>\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}),\d+ INFO \[(?P<sid>[^\]]+)\] "
    r"agent\.turn_context: conversation turn: session=(?P<sid2>\S+) "
    r"model=(?P<model>\S+) provider=(?P<prov>\S+) platform=(?P<plat>\S+)"
)
_FALLBACK_RE = re.compile(
    r"^.*\[(?P<sid>[^\]]+)\] agent\.chat_completion_helpers: "
    r"Fallback activated: (?P<frm>\S+) \S (?P<to>\S+) \((?P<prov>[^)]+)\)"
)


def query(since: float) -> list:
    con = sqlite3.connect(f"file:{STATE_DB}?mode=ro", uri=True)
    con.row_factory = sqlite3.Row
    cur = con.cursor()
    rows = cur.execute(
        """
        SELECT m.session_id, s.title, m.model, m.billing_provider,
               m.task, m.first_seen, s.source
        FROM session_model_usage m
        JOIN sessions s ON s.id = m.session_id
        WHERE s.source = 'api_server'
          AND m.billing_provider = ?
          AND m.first_seen >= ?
        ORDER BY m.first_seen DESC
        """,
        (PAYG_DEFAULT_PROVIDER, since),
    ).fetchall()
    con.close()
    return [dict(r) for r in rows]


def parse_log_evidence(log_dir: str, since: float) -> dict:
    """Map session_id -> {req_provider, req_model, fallback_to, fallback_from}.

    Reads every agent.log* in log_dir (rotated files included) and keeps only
    lines at/after `since`. Returns (evidence, coverage_start) where
    coverage_start is the earliest parsed timestamp (None when no lines).
    """
    evidence: dict = {}
    coverage_start = None
    files = sorted(glob.glob(os.path.join(log_dir, "agent.log*")), key=os.path.getmtime)
    for path in files:
        try:
            fh = open(path, errors="replace")
        except OSError:
            continue
        with fh:
            for line in fh:
                m = _TURN_RE.match(line)
                if m:
                    ts = time.mktime(time.strptime(m.group("ts"), "%Y-%m-%d %H:%M:%S"))
                    if coverage_start is None or ts < coverage_start:
                        coverage_start = ts
                    if ts < since or m.group("plat") != "api_server":
                        continue
                    sid = m.group("sid")
                    ev = evidence.setdefault(sid, {})
                    # First turn line per session = the requested route.
                    ev.setdefault("req_provider", m.group("prov"))
                    ev.setdefault("req_model", m.group("model"))
                    continue
                m2 = _FALLBACK_RE.match(line)
                if m2:
                    sid = m2.group("sid")
                    ev = evidence.setdefault(sid, {})
                    ev.setdefault("fallback_from", m2.group("frm"))
                    ev.setdefault("fallback_to", m2.group("to"))
                    ev.setdefault("fallback_provider", m2.group("prov"))
    return evidence, coverage_start


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--hours", type=float, default=6.0, help="lookback window")
    ap.add_argument("--since", type=float, default=None, help="epoch override")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--log-dir", default=DEFAULT_LOG_DIR, help="agent.log* directory")
    ap.add_argument("--strict", action="store_true",
                    help="legacy: fail on ANY PAYG-default billing, fallback or not")
    args = ap.parse_args()

    since = args.since if args.since is not None else time.time() - args.hours * 3600
    hits = query(since)

    # Fold to distinct sessions (one session can have multiple usage rows).
    seen: dict = {}
    for h in hits:
        seen.setdefault(h["session_id"], h)

    evidence, coverage_start = parse_log_evidence(args.log_dir, since)

    explained, unexplained, unverified = [], [], []
    for sid, s in seen.items():
        ev = evidence.get(sid)
        if ev is None:
            unverified.append(s)
        elif ev.get("fallback_to") == PAYG_DEFAULT_MODEL or \
                ev.get("fallback_provider") == PAYG_DEFAULT_PROVIDER:
            explained.append((s, ev))
        else:
            unexplained.append((s, ev))

    coverage_full = coverage_start is not None and coverage_start <= since

    requested_lanes: dict = {}
    for s, ev in explained:
        requested_lanes[ev.get("req_provider", "?")] = requested_lanes.get(
            ev.get("req_provider", "?"), 0) + 1

    if args.json:
        blind = coverage_start is None
        print(json.dumps({
            "ok": len(unexplained) == 0 and not (unverified and (coverage_full or blind)),
            "window_hours": args.hours,
            "payg_default_sessions": len(seen),
            "explained_fallbacks": len(explained),
            "unexplained": len(unexplained),
            "unverified": len(unverified),
            "log_coverage_full": coverage_full,
            "fallback_source_lanes": requested_lanes,
            "strict_mode": args.strict,
        }, indent=1))
        if args.strict:
            return 1 if seen else 0
        return 1 if (unexplained or (unverified and (coverage_full or blind))) else 0

    # Lane-capacity telemetry always goes to stderr: it is real signal
    # (an intended sub lane is refusing work) but it is NOT the routing bug.
    if explained:
        top = ", ".join(f"{k}={v}" for k, v in
                        sorted(requested_lanes.items(), key=lambda kv: -kv[1])[:4])
        print(f"routing-billing-guard: {len(explained)} api_server session(s) "
              f"fell back to the PAYG default in the last {args.hours:g}h — "
              f"intended lanes: {top}. Lane capacity, not a routing leak.",
              file=sys.stderr)

    if args.strict and seen:
        print(f"ROUTING-REGRESSION (--strict): {len(seen)} api_server session(s) "
              f"billed provider={PAYG_DEFAULT_PROVIDER!r} in the last "
              f"{args.hours:g}h (fallback-aware view: {len(explained)} explained).")
        for s in list(seen.values())[:10]:
            print(f"  - {s['title']!r} model={s['model']} "
                  f"at {time.strftime('%H:%M:%S', time.localtime(s['first_seen']))}")
        return 1

    if unexplained:
        print(f"ROUTING-REGRESSION: {len(unexplained)} api_server session(s) billed "
              f"provider={PAYG_DEFAULT_PROVIDER!r} in the last {args.hours:g}h with NO "
              f"logged lane fallback — the provider field is NOT reaching the gateway "
              f"for these calls (the PAYG default served them because nothing else "
              f"was asked for).")
        for s, ev in unexplained[:10]:
            print(f"  - {s['title']!r} model={s['model']} "
                  f"requested={ev.get('req_provider', '?')}/{ev.get('req_model', '?')} "
                  f"at {time.strftime('%H:%M:%S', time.localtime(s['first_seen']))} "
                  f"task={s['task'] or '-'}")
        if len(unexplained) > 10:
            print(f"  ... and {len(unexplained) - 10} more")
        print("Hint: check state.db sessions + gateway.log; the bridge wire "
              "tests are src/bridge/hermes_api_wire_test.go.")
        return 1

    if unverified and coverage_start is None:
        print(f"ROUTING-REGRESSION: cannot verify {len(unverified)} PAYG-default "
              f"session(s) — no gateway-log evidence at all under "
              f"{args.log_dir} for the window (the guard is blind, so it fails "
              f"closed rather than pass on no data).")
        for s in unverified[:10]:
            print(f"  - {s['title']!r} model={s['model']} "
                  f"at {time.strftime('%H:%M:%S', time.localtime(s['first_seen']))}")
        return 1

    if unverified and coverage_full:
        print(f"ROUTING-REGRESSION: {len(unverified)} api_server session(s) billed "
              f"provider={PAYG_DEFAULT_PROVIDER!r} have NO gateway-log record at all "
              f"while the parsed logs cover the whole window — cannot attribute them "
              f"to a lane fallback.")
        for s in unverified[:10]:
            print(f"  - {s['title']!r} model={s['model']} "
                  f"at {time.strftime('%H:%M:%S', time.localtime(s['first_seen']))}")
        return 1

    if unverified:
        print(f"ROUTING-REGRESSION (coverage hole, not a routing claim): "
              f"{len(unverified)} api_server session(s) billed "
              f"provider={PAYG_DEFAULT_PROVIDER!r} fall OUTSIDE the parsed gateway-log "
              f"window (logs start "
              f"{time.strftime('%m-%d %H:%M', time.localtime(coverage_start)) if coverage_start else 'never'}, "
              f"window starts {time.strftime('%m-%d %H:%M', time.localtime(since))}) — "
              f"the guard cannot tell a lane fallback from a routing leak for them, so "
              f"it fails closed instead of passing on partial evidence.")
        for s in unverified[:10]:
            print(f"  - {s['title']!r} model={s['model']} "
                  f"at {time.strftime('%H:%M:%S', time.localtime(s['first_seen']))}")
        if len(unverified) > 10:
            print(f"  ... and {len(unverified) - 10} more")
        return 1

    print(f"routing-billing-guard: OK — 0 unexplained api_server sessions on the "
          f"PAYG default in the last {args.hours:g}h "
          f"({len(explained)} explained lane fallback(s), {len(unverified)} unverifiable).")
    return 0


if __name__ == "__main__":
    sys.exit(main())

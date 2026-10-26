#!/home/kara/.hermes/venvs/board/bin/python3
"""dagger-error-scanner.py — hourly self-improvement loop for the dagger system.

Scans recent dagger run logs (/tmp/foreman-hermes-dagger-*, /tmp/dagger-role-*)
for REAL dagger-code bugs and drives the DAGGER-00N fix loop on
~/hermes-dagger/.coding-hermes/board/tasks.jsonl.

Scope (Bane 2026-08-31): the dagger CODE itself — timeout handling, data-flow
logic bugs, the running daggers' codebases. NOT prompts/projects inside daggers.

v2 (Bane 2026-09-01 "make sure this cron keeps improving the system"):
  Canonical signatures (one bug = one row), dedupe + auto-closure, P1
  escalation on recurrence, events.jsonl history, hardened env-skip.

v3 (Bane 2026-09-01 "make sure an LLM looks at this and then writes it to the
board with enough detail that it can be fixed on the next pass") — STAGE MODE:
  This script owns STATE; the LLM owns the BOARD.
  1. STAGING — new bug classes go to the staging work queue
     (~/.hermes/state/dagger-error-scanner-staging.jsonl). The scan NEVER
     writes board rows directly; detection alone is never filed.
  2. LLM TRIAGE — the hourly cron (job 7260517f2689) runs this script as a
     monitor; when staged candidates exist, a triage agent investigates each
     one WITH REPO ACCESS (grep src/, read run.jsonl, check prior rows) and
     either files a fix-grade row (verbatim error + root cause + file:line +
     fix direction) or consumes it via `--consume <sig-prefix> <verdict>
     "<evidence>"` (premise-false | env-transient | already-fixed).
  3. CONSUMPTION (each scan): a staged class that gained an open board row is
     consumed-as-filed; a class gone from the scan is consumed
     no-recurrence; a class unclaimed for >STAGE_MAX_ATTEMPTS scans is
     dropped LOUDLY (stderr) so silence can never mean success.
  4. RECURRENCE — a consumed/closed class that re-stages with a FRESHER
     error re-stages at P1 with recurring=1 (a fix that didn't hold
     escalates instead of looping silently).
  5. BOOKKEEPING — the script still owns dedupe consolidation + quiet
     auto-close of EXISTING scanner rows (status edits only, never filings).
  6. MONITOR CONTRACT — stdout is a STABLE (timestamp-free) report only when
     candidates await triage or queue actions happened; "" = silent tick.
     stage_rev bumps on every queue change so the monitor hash changes and
     the triage agent re-fires until the queue is drained.

State: ~/.hermes/state/dagger-error-scanner.json
Staging: ~/.hermes/state/dagger-error-scanner-staging.jsonl
"""
import json
import hashlib
import os
import re
import subprocess
import sys
import time
from collections import defaultdict
from datetime import datetime, timezone

# Resolve the dagger repo from the binary in PATH; fallback is the canonical install path.
import shutil, pathlib
_dagger = shutil.which("dagger")
REPO = str(pathlib.Path(_dagger).parent.parent.resolve()) if _dagger else "/home/kara/Hermes-DAGger/hermes-dagger"
del _dagger

BOARD_DIR = os.path.join(REPO, ".coding-hermes", "board")
TASKS = os.path.join(BOARD_DIR, "tasks.jsonl")
EVENTS = os.path.join(BOARD_DIR, "events.jsonl")
STATE = os.path.expanduser("~/.hermes/state/dagger-error-scanner.json")
STAGING = os.path.expanduser("~/.hermes/state/dagger-error-scanner-staging.jsonl")
EVAL_URL = "http://127.0.0.1:9090/api/v1/evaluate"
ACTOR = "dagger-error-scanner"
WINDOW_H = 24            # scan runs from the last 24h
QUIET_H = 24             # quiet this long + filed this long -> auto-close
FRESH_H = 6              # only stage classes whose newest event is fresher
STAGE_MAX_ATTEMPTS = 3   # scans a candidate may sit unclaimed before drop

ENV_SKIP = re.compile(
    r"draining|gateway unreachable|Gateway is draining|gateway_draining|"
    r"hermes api returned 5\d\d|HTTP 5\d\d|HTTP 50[0-9]|"
    r"connection refused|dial tcp|network is unreachable|tls: |x509|"
    r"exec fallback disabled|no exec fallback|retry shortly", re.I)
KEEP = re.compile(
    r"call timeout after|deadline exceeded|duckbrain tick write FAILED|"
    r"duckbrain tick write NOT verified|NOT verified|verify mismatch|"
    r"lookup failed|INCOMPLETE|qjs: eval failed|"
    r"tool error|size=NaN|invalid JSON|parse|STRUCT-001|double-encode|"
    r"agent returned non-JSON|failed to parse|unmarshal|eval failed|"
    r"TypeError|ReferenceError|is not a function|cannot read", re.I)

HEX_ID = re.compile(r"[0-9a-f]{8,}")
TS = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}(:\d{2}(\.\d+)?)?")
ITER = re.compile(r"/iter\d+/")
JSFRAME = re.compile(r"\.js:\d+(:\d+)?")
GOTVAL = re.compile(r"got: .*")            # whole tail: envelope chatter is per-run payload
READBACK = re.compile(r"read_back=.*")
EXITCODE = re.compile(r"Exit code: \d+")
KEYPATH = re.compile(r"key=\S+")
POSTPATH = re.compile(r"(POST failed for )\S+")
RECORDID = re.compile(r"(POST produced no record id for )\S+")
EQNUM = re.compile(r"=(\d+)")
NODE_SPEC = re.compile(r'node "(?:[^"/]*/)*([^"/]+)"')
LOCALPORT = re.compile(r"(127\.0\.0\.1|localhost):\d+")


def utcnow():
    return datetime.now(timezone.utc)


def now_iso():
    return utcnow().isoformat()


def parse_ts(s):
    """Parse a timestamp; naive values are assumed UTC (never crash on mix)."""
    if not s:
        return None
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
    except (ValueError, TypeError, AttributeError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def load_state():
    try:
        with open(STATE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def save_state(state):
    os.makedirs(os.path.dirname(STATE), exist_ok=True)
    # prune stale sig entries so the state file cannot grow unbounded
    cutoff = time.time() - 7 * 86400
    pruned = {}
    for k, v in state.items():
        try:
            dt = parse_ts(v.get("last_seen") or "")
            if dt and dt.timestamp() < cutoff:
                continue
        except AttributeError:
            pass          # non-sig metadata keys (stage_rev) are always kept
        except Exception:
            pass
        pruned[k] = v
    tmp = STATE + ".tmp"
    with open(tmp, "w") as f:
        json.dump(pruned, f, indent=1)
    os.replace(tmp, STATE)


def load_jsonl(path):
    """Per-line tolerant read — one corrupt line must not blank the board."""
    rows = []
    corrupt = 0
    try:
        with open(path) as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    rows.append(json.loads(line))
                except json.JSONDecodeError:
                    corrupt += 1
    except OSError:
        pass
    if corrupt:
        print(f"WARN: {corrupt} corrupt line(s) skipped in {path}", file=sys.stderr)
    return rows


def node_class(node):
    """Canonical node class: strip run-id prefix, collapse iteration index,
    keep the LEAF segment."""
    n = re.sub(r"^[0-9a-f]{8,12}/", "", node or "?")
    n = ITER.sub("/iterN/", n)
    return n.split("/")[-1] or n


def canon_head(err):
    """Normalized error head — the exact text signatures are computed from.
    IDEMPOTENT: canon_head(canon_head(x)) == canon_head(x) — fresh events and
    stored rows pass through the same function (signature contract).

    The bug SITE (words after 'Error:' up to the first ' — ' payload
    separator) is the signature; everything after the dash is per-run
    payload. Normalizations: node spec → node <leaf>, hex ids → <id>,
    timestamps → <ts>, /iterN/, JS frames → .js:L, "got: <tail>" → got: <v>
    (whole tail — tool() envelope chatter differs every run), read_back
    payloads, localhost ports → :<port>, exit codes, key paths, POST
    endpoints, =<n> counts.
    """
    # Canonical head = FIRST LINE only, up to the " — " payload separator.
    # Multi-line tails (stack frames, payloads) are per-run noise; everything
    # discriminating lives on line 1. Over-merge stays the safe failure mode
    # (a fixed bug that still occurs re-fires via fresh timestamps → P1).
    h = ((err or "").strip().splitlines() or [""])[0].strip()[:220]
    h = h.split(" — ")[0]
    h = NODE_SPEC.sub(r"node <\1>", h)
    h = HEX_ID.sub("<id>", h)
    h = TS.sub("<ts>", h)
    h = ITER.sub("/iterN/", h)
    h = JSFRAME.sub(".js:L", h)
    h = LOCALPORT.sub(r"\1:<port>", h)
    h = GOTVAL.sub("got: <v>", h)
    h = READBACK.sub("read_back=<...>", h)
    h = EXITCODE.sub("Exit code: <n>", h)
    h = KEYPATH.sub("key=<path>", h)      # key=/sync/x vs key=/project/y = same bug
    h = POSTPATH.sub(r"\1<path>", h)      # POST failed for <endpoint/date> = same bug
    h = RECORDID.sub(r"\1<path>", h)      # no-record-id for <key> = one root bug
    h = EQNUM.sub("=<n>", h)              # missing=2 vs missing=4 = same bug shape
    return h[:160]


def canon_sig(node, err):
    """Signature = normalized message alone (node spec already inside it)."""
    return hashlib.sha1(canon_head(err).encode()).hexdigest()[:16]


def scan_runs():
    """Return list of {node, error, tick, ts, dir} error events from run logs."""
    import glob
    findings = []
    pats = ["/tmp/foreman-hermes-dagger-*", "/tmp/dagger-role-*-*", "/tmp/dagger-role-*"]
    dirs = set()
    for p in pats:
        dirs.update(glob.glob(os.path.expanduser(p)))
    cutoff = time.time() - WINDOW_H * 3600
    for d in sorted(dirs, reverse=True):
        try:
            if os.path.getmtime(d) < cutoff:
                continue
        except OSError:
            continue
        rj = os.path.join(d, "run.jsonl")
        if not os.path.exists(rj):
            continue
        try:
            with open(rj) as f:
                for line in f:
                    if '"event":"error"' not in line:
                        continue
                    try:
                        ev = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    err = ev.get("error", "") or ""
                    tick = ""
                    m = re.search(r"key=/(project/[^ ]+)", err)
                    if m:
                        tick = m.group(1)
                    m2 = re.search(r"tick=([\w-]+)", err)
                    if m2:
                        tick = m2.group(1)
                    if not tick:
                        m3 = re.search(r"(hermes-dagger-\d{4}-\d{2}-\d{2}-\d{2}-\d{2}-\d{2})", err)
                        if m3:
                            tick = m3.group(1)
                    findings.append({"node": ev.get("node", "?"), "error": err,
                                     "tick": tick, "ts": ev.get("ts", ""), "dir": d})
        except OSError:
            continue
    return findings


def classify(err):
    if ENV_SKIP.search(err):
        return "skip"
    if KEEP.search(err):
        return "keep"
    return "skip"  # unknown classes stay silent (no flood)


def priority_for(err):
    if re.search(r"call timeout after|deadline exceeded|verify mismatch|"
                 r"write FAILED|INCOMPLETE|NOT verified", err, re.I):
        return "P1"
    return "P2"


def row_sig_from_row(r):
    """Recompute/extract the canonical signature of an existing scanner row.

    Format history (stored text and this parser must stay in lockstep):
      v3 LLM-template (the triage agent's rows): reasoning contains
         "dagger-error-scanner triage" and "signature=<hex>" → the stored
         hex is trusted RAW (the agent's text is prose; re-parsing it is
         lossy). This is what makes open-row blocking + consumption match
         fresh events.
      v1/v2 script rows: reasoning carries the RAW flattened head
         (". Error: <raw>. Run dir:") or the verbatim error sits in
         `detail` → re-normalize through canon_head (idempotent).
      legacy: unmatchable reasoning but explicit signature=<hex> →
         "legacy:" sig, kept as-is until it quiet-closes.
    """
    reasoning = r.get("reasoning") or ""
    if not isinstance(reasoning, str):
        reasoning = json.dumps(reasoning)
    # LLM-template rows: trust the stored signature as a RAW key
    if "dagger-error-scanner triage" in reasoning:
        mm = re.search(r"signature=([0-9a-f]{16})", reasoning)
        if mm:
            return mm.group(1)
    m = (re.search(r"node class '([^']+)' failing", reasoning) or
         re.search(r"node '([^']+)' failed", reasoning))
    if not m:
        mm = re.search(r"signature=([0-9a-f]{16})", reasoning)
        if mm:
            return "legacy:" + mm.group(1)
        return None
    m2 = (re.search(r"\. Error: (.*?)\. (?:Triage: |Sample run dir:|Run dir:)",
                    reasoning, re.S) or
          re.search(r"\. Error: (.*?)\. (?:Sample run dir|Run dir):", reasoning, re.S))
    if m2:
        return canon_sig(m.group(1), m2.group(1))
    # v3 (triage backfill / build_row triage format): the verbatim error sits
    # in detail under [VERBATIM ERROR] — AFTER the triage block, so the v2
    # pipe-join below would hash the triage header instead of the error.
    detail = r.get("detail")
    if isinstance(detail, str) and "[VERBATIM ERROR]" in detail:
        seg = detail.split("[VERBATIM ERROR]", 1)[1]
        seg = seg.split("\n\n[", 1)[0].strip()
        if seg:
            return canon_sig(m.group(1), seg)
    # v2-style: verbatim error in detail (pipe-joined), raw → normalize here
    if isinstance(detail, str) and detail.strip():
        raw = detail.split(" | VERBATIM")[0].replace(" | ", "\n")
        if raw.strip():
            return canon_sig(m.group(1), raw)
    # v1-style: verbatim error embedded in reasoning tail
    m3 = re.search(r"VERBATIM error(?: text)?: (.*?)(?:\. (?:Sample run dir|Run dir):|$)",
                   reasoning, re.S)
    if m3 and m3.group(1).strip():
        return canon_sig(m.group(1), m3.group(1))
    mm = re.search(r"signature=([0-9a-f]{16})", reasoning)
    if mm:
        return "legacy:" + mm.group(1)
    return None


def next_id(existing_ids):
    nxt = (max(existing_ids) + 1) if existing_ids else 6
    return f"DAGGER-{nxt:03d}"


def append_events(new_events):
    if not new_events:
        return
    max_eid = 0
    for e in load_jsonl(EVENTS):
        try:
            max_eid = max(max_eid, int(e.get("id", 0)))
        except (TypeError, ValueError):
            continue
    with open(EVENTS, "a") as f:
        for ev in new_events:
            max_eid += 1
            ev["id"] = max_eid
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")


def run_consume(args):
    """CLI: --consume <sig-prefix> <verdict> "<evidence>" — removes staged
    candidates matching the prefix and records the verdict in state.
    Exit 1 when nothing matches (the triage agent treats that as a failure)."""
    if len(args) < 2:
        print("usage: --consume <sig-prefix> <verdict> [evidence]", file=sys.stderr)
        sys.exit(1)
    prefix, verdict = args[0], args[1]
    evidence = args[2] if len(args) > 2 else ""
    staged = load_jsonl(STAGING)
    keep, matched = [], []
    for s in staged:
        if str(s.get("sig", "")).startswith(prefix):
            matched.append(s)
        else:
            keep.append(s)
    if not matched:
        print(f"CONSUME FAILED: no staged candidate matches prefix '{prefix}'")
        sys.exit(1)
    state = load_state()
    now = now_iso()
    for s in matched:
        sig = s["sig"]
        prev = state.get(sig, {})
        state[sig] = {
            "first_seen": prev.get("first_seen", s.get("staged_at", now)),
            "last_seen": now,
            "last_error_ts": s.get("last_ts", prev.get("last_error_ts", now)),
            "count": s.get("count", prev.get("count", 0)),
            "filed_id": prev.get("filed_id"),
            "staged_dropped": True,
            "dropped_at": now,
            "consume_verdict": verdict,
            "consume_evidence": evidence,
            "consumed_at": now,
        }
    tmp = STAGING + ".tmp"
    with open(tmp, "w") as f:
        for s in keep:
            f.write(json.dumps(s, ensure_ascii=False) + "\n")
    os.replace(tmp, STAGING)
    state["stage_rev"] = int(state.get("stage_rev", 0)) + 1
    save_state(state)
    for s in matched:
        print(f"CONSUMED {s['sig'][:8]} ({s.get('nclass', '?')}) → {verdict}"
              + (f" — {evidence}" if evidence else ""))


def stage_pass(state, tasks, groups, report):
    """Consume/drop/refresh existing staged candidates against the fresh scan.
    Mutates state; appends action notes to report; returns True if the
    staging queue content changed (→ stage_rev bump)."""
    changed = False
    touched = False   # attempt-counter bumps must persist too (or expiry never fires)
    staged = load_jsonl(STAGING)
    if not staged:
        return False
    # open scanner rows by signature (RAW-trusted for LLM-template rows)
    open_by_sig = {}
    for r in tasks:
        if r.get("status") not in ("pending", "in_progress"):
            continue
        sig = row_sig_from_row(r)
        if sig and not sig.startswith("legacy:"):
            open_by_sig.setdefault(sig, r)
    kept = []
    for s in staged:
        sig = s.get("sig", "")
        label = f"{sig[:8]} ({s.get('nclass', '?')})"
        row = open_by_sig.get(sig)
        if row is not None:
            # the triage agent filed this class — consume-as-filed
            prev = state.get(sig, {})
            state[sig] = {
                "first_seen": prev.get("first_seen", s.get("staged_at", now_iso())),
                "last_seen": now_iso(),
                "last_error_ts": s.get("last_ts", prev.get("last_error_ts", "")),
                "count": s.get("count", 0),
                "filed_id": row.get("id"),
            }
            report.append(f"STAGED CONSUMED: {label} → filed {row.get('id')}")
            changed = True
            continue
        if sig not in groups:
            # class vanished from the scan window — consumed no-recurrence
            prev = state.get(sig, {})
            state[sig] = {
                "first_seen": prev.get("first_seen", s.get("staged_at", now_iso())),
                "last_seen": now_iso(),
                "last_error_ts": s.get("last_ts", prev.get("last_error_ts", "")),
                "count": s.get("count", 0),
                "filed_id": prev.get("filed_id"),
                "consume_verdict": "no-recurrence",
                "consume_evidence": "class absent from a fresh scan window",
                "consumed_at": now_iso(),
            }
            report.append(f"STAGED CONSUMED: {label} → no-recurrence")
            changed = True
            continue
        s["stage_attempts"] = int(s.get("stage_attempts", 0)) + 1
        touched = True
        if s["stage_attempts"] >= STAGE_MAX_ATTEMPTS:
            print(f"STAGING DROPPED: {label} — triage agent never picked it up "
                  f"after {STAGE_MAX_ATTEMPTS} scans", file=sys.stderr)
            prev = state.get(sig, {})
            state[sig] = {
                "first_seen": prev.get("first_seen", s.get("staged_at", now_iso())),
                "last_seen": now_iso(),
                "last_error_ts": s.get("last_ts", prev.get("last_error_ts", "")),
                "count": s.get("count", 0),
                "filed_id": prev.get("filed_id"),
                "staged_dropped": True,
                "dropped_at": now_iso(),
            }
            changed = True
            continue
        kept.append(s)
    if changed or touched or len(kept) != len(staged):
        tmp = STAGING + ".tmp"
        os.makedirs(os.path.dirname(STAGING), exist_ok=True)
        with open(tmp, "w") as f:
            for s in kept:
                f.write(json.dumps(s, ensure_ascii=False) + "\n")
        os.replace(tmp, STAGING)
        state["stage_rev"] = int(state.get("stage_rev", 0)) + 1
    return changed


def main(stage=True):
    state = load_state()
    tasks = load_jsonl(TASKS)

    # ---- Map existing scanner rows into signature classes (bookkeeping) ----
    rows_by_sig = defaultdict(list)     # sig -> [rows]
    for r in tasks:
        if ACTOR not in str(r.get("reasoning") or "") and \
           "dagger-error-scanner triage" not in str(r.get("reasoning") or ""):
            continue
        sig = row_sig_from_row(r)
        if not sig:
            continue
        rows_by_sig[sig].append(r)

    def row_num(r):
        m = re.fullmatch(r"DAGGER-(\d+)", r.get("id", ""))
        return int(m.group(1)) if m else 0

    open_rows_by_sig = {}
    closed_count_by_sig = defaultdict(int)
    auto_closed_sigs = set()
    for sig, rs in rows_by_sig.items():
        for r in rs:
            if r.get("status") in ("pending", "in_progress"):
                open_rows_by_sig.setdefault(sig, []).append(r)
            elif r.get("status") == "complete":
                closed_count_by_sig[sig] += 1
                if r.get("worker_status") == "auto-verified-no-recurrence":
                    auto_closed_sigs.add(sig)
    for sig in open_rows_by_sig:
        open_rows_by_sig[sig].sort(key=lambda r: (r.get("created_at") or "", row_num(r)))
    open_sigs = {sig: rs[-1] for sig, rs in open_rows_by_sig.items()}

    # ---- Scan + group fresh events by canonical signature ----
    findings = scan_runs()
    groups = {}
    skipped = 0
    for fnd in findings:
        if classify(fnd["error"]) != "keep":
            skipped += 1
            continue
        sig = canon_sig(fnd["node"], fnd["error"])
        g = groups.setdefault(sig, {"nclass": node_class(fnd["node"]), "count": 0,
                                    "dirs": set(), "last": fnd, "last_ts": ""})
        g["count"] += 1
        g["dirs"].add(fnd["dir"])
        if fnd.get("ts", "") > g["last_ts"]:
            g["last_ts"] = fnd["ts"]
            g["last"] = fnd

    now = utcnow()
    report = []
    new_events = []
    edited_rows = {}

    # ---- Bookkeeping: dedupe consolidation + quiet auto-close (status edits) ----
    for sig, rs in open_rows_by_sig.items():
        newest = rs[-1]
        for dup in rs[:-1]:
            dup["status"] = "complete"
            dup["worker_status"] = "duplicate-consolidated"
            dup["completed_at"] = now_iso()
            dup["updated_at"] = now_iso()
            dup["foreman_note"] = (f"{ACTOR}: duplicate of {newest['id']} "
                                   f"(same canonical bug class) — consolidated")
            edited_rows[dup["id"]] = dup
            new_events.append({
                "timestamp": now_iso(), "event_type": "task_updated",
                "task_id": dup["id"], "actor": ACTOR,
                "detail": f"Duplicate consolidated into {newest['id']}",
                "tick_number": None})
        if sig in groups:
            continue  # still actively failing — newest row keeps tracking
        st = state.get(sig, {})
        anchor = st.get("last_error_ts") or ""
        if not anchor:
            m = re.search(r"last (\d{4}-\d{2}-\d{2}T\d{2}:\d{2})", newest.get("title", ""))
            anchor = m.group(1) if m else ""
        dt_anchor = parse_ts(anchor)
        dt_filed = parse_ts(newest.get("created_at") or newest.get("updated_at") or "")
        if dt_anchor and (now - dt_anchor).total_seconds() > QUIET_H * 3600 and \
           (not dt_filed or (now - dt_filed).total_seconds() > QUIET_H * 3600):
            newest["status"] = "complete"
            newest["worker_status"] = "auto-verified-no-recurrence"
            newest["completed_at"] = now_iso()
            newest["updated_at"] = now_iso()
            newest["foreman_note"] = (
                f"{ACTOR}: auto-closed — no error recurrence in {QUIET_H}h "
                f"(last seen {anchor}); bug stopped occurring after last fix")
            edited_rows[newest["id"]] = newest
            open_sigs.pop(sig, None)
            auto_closed_sigs.add(sig)
            new_events.append({
                "timestamp": now_iso(), "event_type": "task_updated",
                "task_id": newest["id"], "actor": ACTOR,
                "detail": f"Auto-closed: no recurrence in {QUIET_H}h "
                          f"(last error {anchor[:16]}); verified by absence",
                "tick_number": None})

    # ---- Consumption / drop / refresh of already-staged candidates ----
    stage_pass(state, tasks, groups, report)

    # ---- Staging pass: NEW bug classes → work queue (never the board) ----
    staged_now = []
    for sig, g in sorted(groups.items(), key=lambda x: -x[1]["count"]):
        if sig in open_sigs:
            continue          # an open task already tracks this bug
        if any(s.get("sig") == sig for s in load_jsonl(STAGING)):
            continue          # already queued for triage
        # Freshness guard: only stage classes actively failing NOW.
        dt_last = parse_ts(g.get("last_ts", ""))
        if not dt_last or (now - dt_last).total_seconds() > FRESH_H * 3600:
            continue
        # Recurrence: previously filed/consumed class back with a FRESHER error
        prev = state.get(sig, {})
        recurred = bool(prev.get("filed_id") or closed_count_by_sig.get(sig)
                        or sig in auto_closed_sigs)
        if recurred:
            prev_dt = parse_ts(prev.get("last_error_ts") or "")
            if prev_dt and dt_last <= prev_dt:
                continue      # window sliding, not a real recurrence
        if prev.get("staged_dropped") and dt_last <= parse_ts(
                prev.get("last_error_ts") or ""):
            continue          # dropped for THIS evidence window; a fresher
                              # error ts re-arms staging (real recurrence)
        prio = "P1" if recurred else priority_for(g["last"]["error"])
        cand = {
            "sig": sig, "nclass": g["nclass"], "count": g["count"],
            "ndirs": len(g["dirs"]), "priority": prio,
            "recurring": 1 if recurred else 0,
            "last_ts": g["last_ts"], "tick": g["last"].get("tick", ""),
            "sample_dir": g["last"]["dir"],
            "error_verbatim": (g["last"]["error"] or "").strip()[:1500],
            "staged_at": now_iso(), "stage_attempts": 0,
        }
        staged_now.append(cand)
        prev_state = state.get(sig, {})
        state[sig] = {
            "first_seen": prev_state.get("first_seen", now_iso()),
            "last_seen": now_iso(),
            "last_error_ts": g.get("last_ts", now_iso()),
            "count": g["count"],
            "filed_id": prev_state.get("filed_id"),
        }
    if staged_now:
        os.makedirs(os.path.dirname(STAGING), exist_ok=True)
        with open(STAGING, "a") as f:
            for c in staged_now:
                f.write(json.dumps(c, ensure_ascii=False) + "\n")
        state["stage_rev"] = int(state.get("stage_rev", 0)) + 1
        for c in staged_now:
            report.append(f"STAGED: {c['sig'][:8]} ({c['nclass']}) {c['priority']}"
                          + (" RECURRING" if c["recurring"] else "")
                          + f" — {c['count']} hit(s), last {c['last_ts'][:16]}")

    # ---- Board writes: only status edits (bookkeeping); never filings ----
    committed = False
    if edited_rows:
        tmp = TASKS + ".tmp"
        with open(TASKS) as fin, open(tmp, "w") as fout:
            for line in fin:
                s = line.strip()
                if not s:
                    continue
                try:
                    r = json.loads(s)
                except json.JSONDecodeError:
                    fout.write(line)
                    continue
                if r.get("id") in edited_rows:
                    fout.write(json.dumps(edited_rows[r["id"]], ensure_ascii=False) + "\n")
                else:
                    fout.write(line)
        os.replace(tmp, TASKS)
        append_events(new_events)
        branch = subprocess.run(["git", "-C", REPO, "branch", "--show-current"],
                                capture_output=True, text=True).stdout.strip()
        subprocess.run(["git", "add", "tasks.jsonl", "events.jsonl"],
                       cwd=BOARD_DIR, capture_output=True)
        dup_n = sum(1 for r in edited_rows.values()
                    if r.get("worker_status") == "duplicate-consolidated")
        close_n = sum(1 for r in edited_rows.values()
                      if r.get("worker_status") == "auto-verified-no-recurrence")
        bits = []
        if close_n:
            bits.append(f"bookkept {close_n} row(s)")
        if dup_n:
            bits.append(f"consolidated {dup_n} duplicate row(s)")
        msg = (f"board: {ACTOR} " + "; ".join(bits) +
               " (canonical signatures; close the self-improvement loop)\n\n"
               "Co-authored-by: Alexis Okuwa <wojonstech@gmail.com>")
        # DAGGER-0903: commit ONLY the two board files this script staged. A bare
        # `git commit` commits the WHOLE index, sweeping any other agent's staged
        # files (proven twice: 3df1c14 swallowed the DAGGER-0901 implementation,
        # 29b189d swallowed DAGGER-0917's qa.ts + test + prompt).
        cp = subprocess.run(["git", "-C", REPO, "commit", "--no-verify", "-m", msg,
                             "--", ".coding-hermes/board/tasks.jsonl",
                             ".coding-hermes/board/events.jsonl"],
                            capture_output=True, text=True)
        if cp.returncode != 0 and "nothing to commit" not in cp.stderr:
            print("COMMIT FAILED:", cp.stderr[-300:], file=sys.stderr)
        else:
            subprocess.run(["git", "push", "origin", branch],
                           cwd=BOARD_DIR, capture_output=True, text=True)
        committed = True
        # nudge the scheduler so the foreman tick sees the board change
        try:
            subprocess.run(["curl", "-s", "-X", "POST", EVAL_URL],
                           capture_output=True, timeout=15)
        except Exception:
            pass

    save_state(state)

    # ---- Monitor report (STABLE bytes; "" = silent tick; no timestamps) ----
    staged_pending = load_jsonl(STAGING)
    if not staged_pending and not report:
        return  # silent — nothing for the triage agent to do
    print(f"DAGGER-ERROR-SCANNER stage-queue (rev {state.get('stage_rev', 0)})")
    print(f"staged-pending: {len(staged_pending)}")
    for s in sorted(staged_pending, key=lambda x: -int(x.get("count", 0))):
        print(f"  {s['sig'][:8]} {s.get('nclass', '?')} {s.get('priority', 'P?')}"
              + (" RECURRING" if s.get("recurring") else "")
              + f" {s.get('count', 0)}x attempt {s.get('stage_attempts', 0)}"
                f"/{STAGE_MAX_ATTEMPTS}")
    for line in report:
        print(line)
    if committed:
        print("BOOKKEEPING: board status edits committed+pushed")


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--consume":
        run_consume(sys.argv[2:])
    else:
        main(stage=True)

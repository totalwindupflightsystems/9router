#!/usr/bin/env bash
# drain-board-rows.sh — move spooled alert rows onto the real boards.
#
# Why this exists: the monitoring host does not hold the fleet's lane checkouts (it is a
# separate box, deliberately), so alert-router spools rows instead of dropping them. This is
# run ON THE HOST THAT HAS THE BOARDS — pull the spool, append each row to its lane's
# tasks.jsonl, and mark the spool drained.
#
# Idempotent: a row whose id is already on the target board is skipped, so a re-run after a
# partial failure cannot duplicate. Rows are appended with ~/.hermes/scripts/board_append.py,
# which owns the one-JSON-object-per-line invariant.
#
# RE-FIRE RULE (MON-GAP-030). Row ids are MON-<LANE>-<FP8>-<YYYYMMDD> (alert fingerprint +
# UTC date), so a condition that fires, resolves and fires again the same day re-uses the id.
# Presence-only dedupe therefore swallowed every repeat once the first row of the day was
# closed: on 2026-10-20 DiskFull on bunker-mvp fired four times (13:03Z-15:15Z), the row had
# been closed at 09:26Z, and the live critical had no open work item anywhere.
# The fix is NOT "append when the board row is closed" — the spool is a CUMULATIVE file, so
# that rule re-mints rows for alerts that fired days ago and are long quiet (measured on the
# live 732-row spool: 84 ids with closed board rows, 44 of them stale back to 2026-10-07).
# A re-fire is appended only when all three hold:
#   (1) the id is on the board and EVERY row carrying it is TERMINAL
#       (complete/done/closed/verified-benign/duplicate/rejected/unverified-expired),
#   (2) the spool batch still carries a non-resolved (firing) row for that id — the NEWEST
#       such row is the one appended, at most one row per id per run,
#   (3) the alert is firing RIGHT NOW in Prometheus (the same liveness check the alert-router
#       applies at webhook time). No liveness source -> no re-fire (fail closed), and the run
#       says so.
#
#   ./drain-board-rows.sh                       # drain via S3 (default when MON_REMOTE unset)
#   MON_REMOTE=mon-host ./drain-board-rows.sh   # drain straight over the tailnet
#
# Test hooks (used by monitoring/fixes/mon-gap-030/test-drain-refire.sh):
#   BOARD_ROOT, SPOOL, BOARD_APPEND, DRY   as before
#   ALERTS_FILE    a saved /api/v1/alerts JSON — replaces the live Prometheus read
#   PROM_LOCAL     host:port queried ON MON_REMOTE (default localhost:9090)
set -euo pipefail

BOARD_ROOT="${BOARD_ROOT:-$HOME}"
SPOOL="${SPOOL:-/tmp/fleet-monitoring-spool}"
APPEND="${BOARD_APPEND:-$HOME/.hermes/scripts/board_append.py}"
DRY="${DRY:-0}"
ALERTS_FILE="${ALERTS_FILE:-}"
PROM_LOCAL="${PROM_LOCAL:-localhost:9090}"

[ -x "$APPEND" ] || [ -f "$APPEND" ] || { echo "board_append.py not found at $APPEND"; exit 1; }

mkdir -p "$SPOOL"
rm -f "$SPOOL"/board-rows.jsonl "$SPOOL"/*RESOLVED* 2>/dev/null || true

echo "== fetching spool =="
if [ -n "${MON_REMOTE:-}" ]; then
  rsync -az --timeout=30 "$MON_REMOTE:/var/lib/fleet-monitoring/spool/" "$SPOOL/" 2>/dev/null \
    || { echo "rsync from $MON_REMOTE failed"; exit 1; }
  echo "  pulled from $MON_REMOTE"
elif [ -n "${S3_BUCKET:-}" ]; then
  rclone --config /dev/null --s3-provider Other \
    --s3-access-key-id "$S3_ACCESS_KEY" --s3-secret-access-key "$S3_SECRET_KEY" \
    --s3-endpoint "$S3_ENDPOINT" --s3-region "${S3_REGION:-hel1}" --s3-force-path-style \
    copy ":s3:$S3_BUCKET/${S3_PREFIX:-monitoring}/spool" "$SPOOL" -q 2>/dev/null || true
  echo "  pulled from s3://$S3_BUCKET/${S3_PREFIX:-monitoring}/spool"
else
  echo "set MON_REMOTE=host or S3_BUCKET + credentials"; exit 1
fi

FILES=$(find "$SPOOL" -name '*.jsonl' 2>/dev/null | wc -l)
[ "$FILES" -gt 0 ] || { echo "spool empty — nothing to drain"; exit 0; }

# ------------------------------------------------------------------ liveness source (gate)
ALERTS_TMP=""
if [ -z "$ALERTS_FILE" ] && [ -n "${MON_REMOTE:-}" ]; then
  ALERTS_TMP=$(mktemp "${TMPDIR:-/tmp}/drain-alerts.XXXXXX")
  trap 'rm -f "$ALERTS_TMP"' EXIT
  if ssh -o BatchMode=yes -o ConnectTimeout=10 "$MON_REMOTE" \
       "curl -s --max-time 10 http://$PROM_LOCAL/api/v1/alerts" > "$ALERTS_TMP" 2>/dev/null \
     && [ -s "$ALERTS_TMP" ]; then
    ALERTS_FILE="$ALERTS_TMP"
  else
    echo "  liveness source UNAVAILABLE (prometheus read failed) — re-fires will be suppressed"
    ALERTS_FILE=""
  fi
fi
[ -n "$ALERTS_FILE" ] && [ -s "$ALERTS_FILE" ] || echo "  liveness source: none (re-fires fail closed)"

# ------------------------------------------------------------------ classify the batch
# One python pass, because the rules are batch- and board-scoped: newest firing row per id
# wins a re-fire, and no id may be appended twice in one run.
echo "== classifying rows =="
PLAN=$(mktemp "${TMPDIR:-/tmp}/drain-plan.XXXXXX")
trap 'rm -f "$PLAN" ${ALERTS_TMP:+"$ALERTS_TMP"}' EXIT
python3 - "$SPOOL" "$BOARD_ROOT" "$ALERTS_FILE" "$(date -u +%Y%m%d)" > "$PLAN" <<'PY'
import json, os, sys, glob, re

spool_dir, board_root, alerts_file, today = sys.argv[1], sys.argv[2], sys.argv[3], sys.argv[4]
TERMINAL = {"complete", "done", "closed", "verified-benign", "duplicate", "rejected",
            "unverified-expired"}

def jload(raw):
    try:
        return json.loads(raw)
    except ValueError:
        return None

# ---- live firing set: (alertname, host) pairs, from the same endpoint the router reads
live = set()
live_ok = False
if alerts_file and os.path.isfile(alerts_file):
    try:
        doc = json.load(open(alerts_file, encoding="utf-8", errors="replace"))
        alist = doc.get("data", {}).get("alerts") if isinstance(doc, dict) else doc
        for a in (alist or []):
            st = (a.get("status", {}).get("state") if isinstance(a.get("status"), dict)
                  else a.get("state")) or a.get("state") or "firing"
            if str(st).lower() != "firing":
                continue
            lab = a.get("labels") or {}
            live.add((lab.get("alertname") or "", lab.get("host") or lab.get("instance") or ""))
        live_ok = True
    except (ValueError, OSError, AttributeError):
        live_ok = False

def labels_of(row):
    """alertname/host from the row's own 'labels: {...}' line (the router writes it)."""
    text = row.get("reasoning") or row.get("detail") or ""
    if not isinstance(text, str):
        return None
    marker = "labels: "
    idx = text.find(marker)
    if idx < 0:
        return None
    frag = text[idx + len(marker):]
    depth, end = 0, -1
    for i, ch in enumerate(frag):
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                end = i + 1
                break
    if end < 0:
        return None
    obj = jload(frag[:end])
    if not isinstance(obj, dict):
        return None
    return (obj.get("alertname") or "", obj.get("host") or obj.get("instance") or "")

def board_rows(path):
    cached = _board_cache.get(path)
    if cached is not None:
        return cached
    _board_cache[path] = []  # sentinel-present (distinguishes a cached miss from uncached)
    if not os.path.isfile(path):
        return None
    out = []
    for raw in open(path, encoding="utf-8", errors="replace"):
        raw = raw.strip()
        if not raw:
            continue
        _board_cache[path].append(jload(raw))
    return _board_cache[path]

# PERF-1: the spool is cumulative with only ONE target board per lane — read each board
# ONCE instead of once per spool line (796 reads of the same 1MB board dominated the run).
_board_cache = {}

# spool order, with 1-based line numbers inside one concatenated stream
entries = []
lineno = 0
for path in sorted(glob.glob(os.path.join(spool_dir, "*.jsonl"))):
    for raw in open(path, encoding="utf-8", errors="replace"):
        raw = raw.rstrip("\n")
        if not raw.strip():
            continue
        lineno += 1
        entries.append((lineno, raw, jload(raw)))

by_id = {}
for lineno, raw, obj in entries:
    if obj is None:
        continue
    rid = obj.get("id")
    if not isinstance(rid, str) or not rid:
        continue
    by_id.setdefault(rid, []).append((lineno, obj))

decisions = {}          # lineno -> kind
refire_count = 0
stale_suppressed = 0
olddate_suppressed = 0
unverified_suppressed = 0

for lineno, raw, obj in entries:
    if obj is None:
        decisions[lineno] = "unparsable"
        continue
    lane = (obj.get("lane") or "monitoring")
    lane = lane.strip().lower() if isinstance(lane, str) else "monitoring"
    if not lane:
        decisions[lineno] = "unparsable"
        continue
    rid = obj.get("id")
    if not isinstance(rid, str) or not rid:
        decisions[lineno] = "unparsable"
        continue
    bpath = os.path.join(board_root, lane, ".coding-hermes", "board", "tasks.jsonl")
    rows = board_rows(bpath)
    if rows is None:
        decisions[lineno] = "noboard"
        continue
    matched = [r for r in rows if r is not None and str(r.get("id") or "") == rid]
    if not matched:
        # id absent from the board: today's shape is that the FIRST row of the batch lands
        decisions[lineno] = "append"
        for other_lineno, other in by_id.get(rid, []):
            if other_lineno != lineno:
                decisions[other_lineno] = "skip"
        continue
    open_rows = [r for r in matched
                 if (str(r.get("status") or "").strip().lower() not in TERMINAL)]
    if open_rows:
        decisions[lineno] = "skip"
        continue
    # every row for this id is terminal -> candidate re-fire (resolved twins never re-fire)
    is_resolved = (str(obj.get("type") or "").lower() == "alert-resolved"
                   or rid.endswith("-RESOLVED"))
    if is_resolved:
        decisions[lineno] = "skip"
        continue
    firing = [(n, o) for n, o in by_id.get(rid, [])
              if not (str(o.get("type") or "").lower() == "alert-resolved"
                      or str(o.get("id") or "").endswith("-RESOLVED"))]
    if not firing:
        decisions[lineno] = "skip"
        continue
    newest_lineno = max(firing, key=lambda t: (str(t[1].get("created_at") or ""), t[0]))[0]
    if newest_lineno != lineno:
        decisions[lineno] = "refire-loser"
        continue
    lab = labels_of(obj)
    if not live_ok:
        decisions[lineno] = "refire-unverified"
        unverified_suppressed += 1
        continue
    # A live alert of this alertname+host re-opens only the id minted for TODAY. Older dated
    # ids for the same condition (the spool is cumulative) belong to days that were handled;
    # re-minting them turns one firing alert into one row per historical date.
    m = re.search(r"(\d{8})$", rid)
    if m and m.group(1) != today:
        decisions[lineno] = "refire-olddate"
        olddate_suppressed += 1
        continue
    if lab not in live:
        decisions[lineno] = "refire-stale"
        stale_suppressed += 1
        continue
    decisions[lineno] = "refire"
    refire_count += 1

for lineno, raw, obj in entries:
    kind = decisions.get(lineno, "skip")
    # PERF-1: emit routing metadata WITH the plan so the bash apply loop never spawns
    # python3 per line (3 spawns x 796 lines dominated the second half of the cost).
    if isinstance(obj, dict):
        lane = str(obj.get("lane") or "").strip().lower() or "monitoring"
        rtype = str(obj.get("type") or "").strip().lower()
        rid = str(obj.get("id") or "")
    else:
        lane, rtype, rid = "monitoring", "", ""
    # '|' (non-whitespace IFS char) so bash `read` preserves EMPTY fields exactly —
    # a tab-separated plan collapses empty fields (IFS whitespace run) and shifts ids.
    print("%d|%s|%s|%s|%s" % (lineno, kind, lane, rtype, rid))
sys.stderr.write("plan: refire=%d olddate-suppressed=%d stale-suppressed=%d unverified-suppressed=%d live_ok=%s\n"
                 % (refire_count, olddate_suppressed, stale_suppressed, unverified_suppressed, live_ok))
PY

# Fail loud on a silent no-op: rows came in, the plan did not. Without this guard an empty
# plan reads exactly like "nothing to do" while the alerts land nowhere.
SPOOL_LINES=$(cat "$SPOOL"/*.jsonl 2>/dev/null | wc -l)
PLAN_LINES=$(wc -l < "$PLAN" 2>/dev/null || echo 0)
if [ "$SPOOL_LINES" -gt 0 ] && [ "$PLAN_LINES" -eq 0 ]; then
  echo "FATAL: classified 0 of $SPOOL_LINES spooled rows — refusing to report a clean drain"
  exit 1
fi

# ------------------------------------------------------------------ apply the plan
echo "== appending rows =="
appended=0; skipped=0; refire=0
SPOOL_LINES_TOTAL=$(cat "$SPOOL"/*.jsonl 2>/dev/null | wc -l)
while IFS='|' read -r lineno kind lanef rtype ridf; do
  [ -n "${kind:-}" ] || continue
  if [ "$SPOOL_LINES_TOTAL" = "1" ]; then
    line=$(cat "$SPOOL"/board-rows.jsonl 2>/dev/null || true)
  else
    line=$(sed -n "${lineno}p" "$SPOOL"/board-rows.jsonl 2>/dev/null || true)
    if [ -z "$line" ]; then
      # concatenated stream across *.jsonl files: same pass order fallback
      line=$(cat "$SPOOL"/*.jsonl 2>/dev/null | sed -n "${lineno}p")
    fi
  fi
  case "$kind" in
    append|refire)
      if [ "$rtype" = "alert-resolved" ]; then
        board="$BOARD_ROOT/$lanef/.coding-hermes/board/events.jsonl"
      else
        board="$BOARD_ROOT/$lanef/.coding-hermes/board/tasks.jsonl"
      fi
      if [ ! -d "$(dirname "$board")" ]; then
        echo "  no board for lane '$lanef' — leaving spooled"; skipped=$((skipped+1)); continue
      fi
      if [ "$DRY" = "1" ]; then
        echo "  DRY would $kind $ridf -> $board [${rtype:-task}]"
      else
        python3 "$APPEND" "$board" "$line" >/dev/null
        echo "  appended $ridf -> $lanef${kind:+ (${kind})} [${rtype:-task}]"
      fi
      appended=$((appended+1))
      [ "$kind" = "refire" ] && refire=$((refire+1))
      ;;
    noboard)
      echo "  no board for lane '$lanef' — leaving spooled"; skipped=$((skipped+1)) ;;
    unparsable)
      echo "  unparsable row, skipping"; skipped=$((skipped+1)) ;;
    refire-stale)
      echo "  closed row + spool replay for $ridf but alert is NOT firing — suppressed"
      skipped=$((skipped+1)) ;;
    refire-olddate)
      echo "  closed row + spool replay for $ridf is an OLDER date for a firing alert — suppressed"
      skipped=$((skipped+1)) ;;
    refire-unverified)
      echo "  closed row + spool replay for $ridf, liveness unknown — suppressed (fail closed)"
      skipped=$((skipped+1)) ;;
    *)
      skipped=$((skipped+1)) ;;
  esac
done < "$PLAN"
rm -f "$PLAN"

echo
echo "drained: appended=$appended skipped=$skipped refire=$refire (dry=$DRY)"
echo "NOTE: clearing the remote spool is deliberately manual — confirm the rows landed first."

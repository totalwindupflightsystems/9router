#!/usr/bin/env python3
"""alert-router — Alertmanager webhook -> board rows -> the lane that owns the problem.

WHY THIS EXISTS
Upstream Alertmanager stops at "something is wrong". The fleet's work queue is a project
board (`.coding-hermes/board/tasks.jsonl`), read by that project's foreman every tick.
This service is the missing hop: an alert carries a `lane` label, and the router turns it
into a board row on that lane. An alert that never becomes a row is an alert nobody acts on.

CONTRACT
  POST /webhook  Alertmanager v4 payload, `Authorization: Bearer $ALERT_ROUTER_TOKEN`.
                 -> firing alerts append ONE row per (alert, day) to the lane's tasks.jsonl
                 -> resolved alerts append a resolution event to the lane's events.jsonl
  GET  /health   liveness + counters
  GET  /metrics  Prometheus text (this service is scraped by the stack's own Prometheus)

LIVE-STATE CHECK (MON-GAP-017)
A firing webhook is re-checked against Prometheus before a pending row is written: no
firing `ALERTS` series means the alert already cleared on the rules side, so the router
records a resolution event instead of a row a foreman would have to fold by hand. When
the check cannot be made (Prometheus dark, error, malformed reply) the row is written
exactly as before — an unqueryable Prometheus must never eat a real alert.

IDEMPOTENCE
The row id embeds the alert fingerprint and the UTC date: MON-<LANE>-<FP8>-<YYYYMMDD>.
Alertmanager re-posts a firing alert on every repeat_interval; without this the board would
collect a duplicate row per repeat. Existing ids are read from the board before an append.

WRITE MODES
  ALERT_ROUTER_WRITE=1 and the lane's board directory exists -> append in place.
  Otherwise -> spool to $ALERT_ROUTER_SPOOL/board-rows.jsonl for `scripts/drain-board-rows.sh`.
  A monitoring host that does not hold the fleet's boards must never silently drop a row;
  spooling keeps it recoverable and countable.

BOARD INVARIANT (mirrors ~/.hermes/scripts/board_append.py)
After every append the board holds ONE JSON object per PHYSICAL line and ends with EXACTLY
one newline; a board whose tail lacks a newline gets one before the payload. The append uses
O_APPEND and is verified by re-reading the file. This is the DAGGER-0943 defect class: a
fused append produces a line no board reader can parse.
"""

import json
import os
import re
import sys
import threading
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

PORT = int(os.environ.get("ALERT_ROUTER_PORT", "8089"))
TOKEN = os.environ.get("ALERT_ROUTER_TOKEN", "")
PROM_URL = os.environ.get("PROM_URL", "http://prometheus:9090").rstrip("/")
PROM_UP_TTL = int(os.environ.get("PROM_UP_TTL_SECONDS", "45"))
BOARD_ROOT = os.environ.get("BOARD_ROOT", "/boards")
WRITE = os.environ.get("ALERT_ROUTER_WRITE", "0") == "1"
NOTIFY = os.environ.get("ALERT_ROUTER_NOTIFY", "0") == "1"
SPOOL = os.environ.get("ALERT_ROUTER_SPOOL", "/spool")
# A slow Prometheus must never hold a webhook open: Alertmanager would time the delivery
# out and retry the whole batch. Past this budget the check is treated as "unknown".
PROM_STATE_TIMEOUT = 3.0
# After a failed state check, stop asking for this long: an alert batch (or a storm) must
# pay one timeout, not one per alert in it.
STATE_CHECK_BACKOFF = 30.0

BOARD_DIR = ".coding-hermes/board"
LANE_RE = re.compile(r"^[a-z0-9][a-z0-9._-]{0,62}$")
SEVERITY_PRIORITY = {"critical": 0, "warning": 1, "info": 2}

_lock = threading.Lock()
_prom_up_cache = {"ok": False, "ts": 0.0}


def prom_target_up(instance, job="integrations/unix", ttl=PROM_UP_TTL):
    """True if Prometheus currently has a live `up` series for this target.

    Cached for `ttl` seconds: resolution storms (whole hosts flapping) must not
    turn into a query burst against Prometheus.

    Why: when a node goes dark (power, network, kernel panic) its exporter goes
    dark with it. Prometheus stops returning samples, the alert fires, then
    Alertmanager resolves it once no series match — an "absence looks like
    recovery" false resolution. Verified live 2026-10-02 on bunker-mvp: df
    showed / 100% full minutes before the host vanished, yet Alertmanager
    reported the DiskFull alert resolved. A resolution is only real if the
    monitoring pipeline itself can still see the host.
    """
    now = time.time()
    with _lock:
        if now - _prom_up_cache["ts"] < ttl:
            return _prom_up_cache["ok"]
    ok = False
    try:
        q = 'up{instance="%s",job="%s"}' % (instance, job)
        url = PROM_URL + "/api/v1/query?" + urllib.parse.urlencode({"query": q})
        with urllib.request.urlopen(url, timeout=4) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        series = (body.get("data") or {}).get("result") or []
        if body.get("status") == "success" and series:
            ok = any(float(s.get("value", [0, 0])[1]) == 1.0 for s in series)
    except (ValueError, OSError, KeyError) as exc:
        log("prom_target_up(%s) query failed: %s" % (instance, exc))
        ok = False
    with _lock:
        _prom_up_cache["ok"] = ok
        _prom_up_cache["ts"] = now
    return ok


_state_check_blocked_until = 0.0  # monotonic deadline; see STATE_CHECK_BACKOFF
COUNTERS = {
    "received_total": 0,
    "rows_appended_total": 0,
    "rows_deduped_total": 0,
    "rows_spooled_total": 0,
    "rows_pre_resolved_total": 0,
    "rows_statecheck_failed_total": 0,
    "resolved_total": 0,
    "resolved_suppressed_total": 0,
    "rejected_total": 0,
    "errors_total": 0,
}


def bump(name, n=1):
    with _lock:
        COUNTERS[name] = COUNTERS.get(name, 0) + n


def log(msg):
    print("%s alert-router: %s" % (datetime.now(timezone.utc).isoformat(timespec="seconds"), msg),
          file=sys.stderr, flush=True)


# ----------------------------------------------------------------------------- board files

def lane_dir(lane):
    return os.path.join(BOARD_ROOT, lane, BOARD_DIR)


def existing_ids(path, scan_bytes=2_000_000):
    """Ids already present. Reads the tail only — boards grow without bound.

    A tolerant line-wise parse, never a whole-file json.load: one malformed historical line
    must not hide the ids that follow it (and must not be repaired by us, either).
    """
    ids = set()
    try:
        size = os.path.getsize(path)
    except OSError:
        return ids
    try:
        with open(path, "rb") as fh:
            if size > scan_bytes:
                fh.seek(size - scan_bytes)
                fh.readline()  # discard the partial line
            for raw in fh:
                raw = raw.strip()
                if not raw:
                    continue
                try:
                    row = json.loads(raw)
                except ValueError:
                    continue
                rid = row.get("id")
                if isinstance(rid, str):
                    ids.add(rid)
    except OSError as exc:
        log("cannot read %s: %s" % (path, exc))
    return ids


def append_rows(path, rows):
    """Append JSON rows under the board invariant, then verify by re-reading."""
    if not rows:
        raise ValueError("refusing empty append")
    for row in rows:
        json.loads(row)  # fail loudly rather than write a torn line

    prior_raw = b""
    try:
        with open(path, "rb") as fh:
            prior_raw = fh.read()
    except FileNotFoundError:
        prior_raw = b""
    prior = sum(1 for ln in prior_raw.split(b"\n") if ln.strip())

    payload = "\n".join(rows).encode("utf-8") + b"\n"
    if prior_raw and not prior_raw.endswith(b"\n"):
        payload = b"\n" + payload
    if sum(1 for ln in payload.split(b"\n") if ln.strip()) != len(rows):
        raise ValueError("payload construction changed the row count")

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "ab") as fh:  # O_APPEND only, never "w"
        fh.write(payload)
        fh.flush()
        os.fsync(fh.fileno())

    with open(path, "rb") as fh:
        after = fh.read()
    total = sum(1 for ln in after.split(b"\n") if ln.strip())
    if total != prior + len(rows):
        raise ValueError("verify failed: rows=%d expected=%d" % (total, prior + len(rows)))
    if not after.endswith(b"\n") or after.endswith(b"\n\n"):
        raise ValueError("verify failed: trailing-newline invariant")
    return prior, total


def spool_row(row):
    os.makedirs(SPOOL, exist_ok=True)
    path = os.path.join(SPOOL, "board-rows.jsonl")
    append_rows(path, [json.dumps(row, separators=(",", ":"))])
    return path


# ------------------------------------------------------------------- prometheus live state

# Labels Alertmanager injects from its own config (external_labels / identity),
# which NEVER exist on Prometheus's local ALERTS series. Matching on any of them
# makes the state-check query match nothing -> every firing alert reads as
# "not firing" and gets pre-resolved instead of landing on its board (seen live
# 2026-10-07: 47 pre-resolutions in 48h, 0 spooled rows, while TargetUnreachable
# on standby-cx53-01-2147 was firing the whole time).
AM_EXTERNAL_LABELS = frozenset({
    "monitor",
})


def prom_label_matchers(labels):
    """PromQL selector for an alert's labels, minus `alertstate`.

    `alertstate` is what the caller is asking about, so it must not be part of the
    selector the caller builds. Values are escaped the way PromQL string literals want
    (backslash, double quote, newline), so a label carrying a quote can never break the
    query into something else. A label NAME that is not a bare PromQL identifier is
    dropped rather than smuggled into the selector.
    """
    parts = []
    for key in sorted(labels or {}):
        value = labels[key]
        if key == "alertstate" or key in AM_EXTERNAL_LABELS or value is None or value == "":
            continue
        if not re.match(r"^[a-zA-Z_][a-zA-Z0-9_]*$", key):
            continue
        escaped = str(value).replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")
        parts.append('%s="%s"' % (key, escaped))
    parts.append('alertstate="firing"')
    return ",".join(parts)


def prom_alert_firing(alert, timeout=PROM_STATE_TIMEOUT):
    """Is this alert firing RIGHT NOW, according to Prometheus?

    True  — a live `ALERTS{<labels>,alertstate="firing"}` series reports 1.
    False — Prometheus answered and there is no firing series, i.e. the alert cleared on
            the rules side before this webhook arrived (Alertmanager's group_wait +
            repeat window, or a rule that flapped back).
    None  — the check could not be made (unreachable, error status, malformed body). The
            caller then writes the row as it always did.

    The unknown answer is sticky for STATE_CHECK_BACKOFF seconds: a dark or hung
    Prometheus must cost one timeout per batch, not one per alert in it.
    """
    global _state_check_blocked_until
    now = time.monotonic()
    if now < _state_check_blocked_until:
        return None
    query = "ALERTS{%s}" % prom_label_matchers(alert.get("labels") or {})
    url = PROM_URL + "/api/v1/query?" + urllib.parse.urlencode({"query": query})
    try:
        with urllib.request.urlopen(url, timeout=timeout) as resp:
            body = json.loads(resp.read().decode("utf-8", "replace"))
        if body.get("status") != "success":
            raise ValueError("prometheus status=%r error=%r" %
                             (body.get("status"), body.get("error")))
        series = (body.get("data") or {}).get("result")
        if not isinstance(series, list):
            raise ValueError("malformed query result: %r" % (series,))
    except (ValueError, OSError) as exc:
        _state_check_blocked_until = now + STATE_CHECK_BACKOFF
        log("state check failed (%s): %s" % (query, exc))
        return None
    _state_check_blocked_until = 0.0
    for sample in series:
        try:
            if float(sample["value"][1]) == 1.0:
                return True
        except (KeyError, IndexError, TypeError, ValueError):
            continue
    return False


# ----------------------------------------------------------------------------- row shaping

def now_pair():
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")
    return ts, ts


def row_id(lane, fingerprint, when):
    return "MON-%s-%s-%s" % (lane.upper()[:24], (fingerprint or "nofp")[:8].upper(),
                             when.strftime("%Y%m%d"))


def build_row(alert, lane, when):
    labels = alert.get("labels") or {}
    ann = alert.get("annotations") or {}
    severity = (labels.get("severity") or "warning").lower()
    alertname = labels.get("alertname") or "Alert"
    host = labels.get("host") or labels.get("instance") or "unknown"

    title = "[%s] %s on %s" % (severity.upper(), alertname, host)
    summary = ann.get("summary")
    if summary:
        title = "%s — %s" % (title, summary)

    detail = [
        ann.get("description") or "",
        "",
        "FIRED %s" % alert.get("startsAt", ""),
        "generator: %s" % (alert.get("generatorURL") or "n/a"),
        "labels: %s" % json.dumps(labels, sort_keys=True),
        "",
        "Filed by fleet-monitoring alert-router. Close it when the alert is resolved; a",
        "resolution event is appended to events.jsonl automatically when Alertmanager reports",
        "the alert resolved.",
    ]
    created, updated = now_pair()
    return {
        "id": row_id(lane, alert.get("fingerprint"), when),
        # lane is stored explicitly: the id uppercases and truncates it, so it is NOT
        # recoverable from the id (a lane like hermes-fleet-ops would come back as "hermes").
        "lane": lane,
        "title": title[:400],
        "status": "pending",
        "priority": SEVERITY_PRIORITY.get(severity, 1),
        "complexity": int(labels.get("complexity") or 2),
        "source": "fleet-monitoring/alert-router",
        "capability_tags": ["+monitoring", "alert", severity],
        "reasoning": "\n".join(detail),
        "foreman_note": ("Alert %s (%s). Grafana: %s" %
                         (alertname, severity, ann.get("dashboard_url") or "see fleet-monitoring")),
        "created_at": created,
        "updated_at": updated,
    }


def build_resolution(alert, lane, when):
    labels = alert.get("labels") or {}
    created, _ = now_pair()
    return {
        "id": row_id(lane, alert.get("fingerprint"), when) + "-RESOLVED",
        "type": "alert-resolved",
        "lane": lane,
        "alertname": labels.get("alertname"),
        "host": labels.get("host") or labels.get("instance"),
        "severity": (labels.get("severity") or "warning").lower(),
        "resolved_at": created,
        "endsAt": alert.get("endsAt"),
    }


def emit_resolution(event, directory):
    """Write ONE resolution event: in place when the lane's board is local, else spooled.

    Shared by the Alertmanager `resolved` path and the pre-resolved-at-webhook-time path
    (MON-GAP-017) so both keep the same dedupe, spool and append invariants.
    """
    target = os.path.join(directory, "events.jsonl")
    if WRITE and os.path.isdir(directory):
        try:
            if event["id"] not in existing_ids(target):
                append_rows(target, [json.dumps(event, separators=(",", ":"))])
                bump("resolved_total")
        except (ValueError, OSError) as exc:
            bump("errors_total")
            log("resolved append failed for %s: %s" % (event.get("lane"), exc))
        return
    try:
        spool_row(event)
        bump("resolved_total")
    except (ValueError, OSError) as exc:
        bump("errors_total")
        log("resolved spool failed: %s" % exc)


def handle_alert(alert, when):
    labels = alert.get("labels") or {}
    lane = (labels.get("lane") or "monitoring").strip().lower()
    if not LANE_RE.match(lane):
        bump("rejected_total")
        log("rejecting alert with unusable lane label: %r" % lane)
        return
    status = (alert.get("status") or "firing").lower()
    directory = lane_dir(lane)

    if status == "resolved":
        # Guard against "absence looks like recovery" false resolutions: only
        # record a resolution if Prometheus still has a live `up` series for
        # this target. A dead exporter must not close a firing alert.
        instance = labels.get("instance") or labels.get("host") or ""
        if instance and not prom_target_up(instance, labels.get("job") or "integrations/unix"):
            bump("resolved_suppressed_total")
            log("suppressing UNVERIFIED resolution for %s/%s: no live up series (target dark?)"
                % (labels.get("alertname"), instance))
            return
        emit_resolution(build_resolution(alert, lane, when), directory)
        return

    # A firing webhook can arrive after the alert already cleared (Alertmanager's
    # group_wait + repeat_interval window, or a rule that flapped back). Writing a
    # pending row then leaves the board with a pre-resolved row + its -RESOLVED twin
    # for a foreman to fold by hand — MON-GAP-017, three sightings. Check the live
    # state first; an unanswerable Prometheus falls through to the row as before.
    live = prom_alert_firing(alert)
    if live is False:
        event = build_resolution(alert, lane, when)
        event["note"] = ("pre-resolved at webhook time: Prometheus reports no firing "
                         "ALERTS series for these labels, so no pending row was written")
        bump("rows_pre_resolved_total")
        log("pre-resolved: %s is not firing in Prometheus; writing resolution only"
            % event["id"])
        emit_resolution(event, directory)
        return
    if live is None:
        bump("rows_statecheck_failed_total")

    row = build_row(alert, lane, when)
    target = os.path.join(directory, "tasks.jsonl")
    if not (WRITE and os.path.isdir(directory)):
        try:
            spool_row(row)
            bump("rows_spooled_total")
            log("spooled row %s (lane %s has no local board)" % (row["id"], lane))
        except (ValueError, OSError) as exc:
            bump("errors_total")
            log("spool failed: %s" % exc)
        return

    try:
        if row["id"] in existing_ids(target):
            bump("rows_deduped_total")
            log("dedupe: %s already on %s" % (row["id"], lane))
            return
        prior, total = append_rows(target, [json.dumps(row, separators=(",", ":"))])
        bump("rows_appended_total")
        log("appended %s to %s (rows %d->%d)" % (row["id"], lane, prior, total))
    except (ValueError, OSError) as exc:
        bump("errors_total")
        log("append failed for %s, spooling instead: %s" % (lane, exc))
        try:
            spool_row(row)
            bump("rows_spooled_total")
        except (ValueError, OSError) as exc2:
            log("spool also failed: %s" % exc2)


# ----------------------------------------------------------------------------- http

class Handler(BaseHTTPRequestHandler):
    server_version = "alert-router/1"
    protocol_version = "HTTP/1.1"

    def _send(self, code, body, ctype="application/json"):
        blob = body if isinstance(body, bytes) else body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(blob)))
        self.end_headers()
        self.wfile.write(blob)

    def _authorised(self):
        if not TOKEN:
            return False
        header = self.headers.get("Authorization", "")
        return header == "Bearer " + TOKEN

    def do_GET(self):  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path == "/health":
            self._send(200, json.dumps({
                "status": "ok",
                "write_mode": "board" if WRITE else "spool",
                "token_configured": bool(TOKEN),
                "counters": COUNTERS,
            }))
            return
        if path == "/metrics":
            lines = ["# TYPE alert_router_events_total counter"]
            for name, value in sorted(COUNTERS.items()):
                lines.append("alert_router_events_total{event=\"%s\"} %d" % (name, value))
            lines.append("alert_router_write_mode{mode=\"%s\"} 1" % ("board" if WRITE else "spool"))
            self._send(200, "\n".join(lines) + "\n", "text/plain; version=0.0.4")
            return
        self._send(404, json.dumps({"error": "not found"}))

    def do_POST(self):  # noqa: N802
        path = urllib.parse.urlparse(self.path).path
        if path != "/webhook":
            self._send(404, json.dumps({"error": "not found"}))
            return
        if not self._authorised():
            bump("rejected_total")
            log("rejected unauthenticated webhook from %s" % self.client_address[0])
            self._send(401, json.dumps({"error": "unauthorized"}))
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length) or b"{}")
        except (ValueError, TypeError) as exc:
            bump("errors_total")
            self._send(400, json.dumps({"error": "bad payload: %s" % exc}))
            return

        alerts = payload.get("alerts") or []
        when = datetime.now(timezone.utc)
        bump("received_total", len(alerts) or 1)
        for alert in alerts:
            try:
                handle_alert(alert, when)
            except Exception as exc:  # never let one bad alert kill the batch
                bump("errors_total")
                log("alert handler error: %r" % exc)
        self._send(200, json.dumps({"handled": len(alerts), "counters": COUNTERS}))

    def log_message(self, fmt, *args):
        log(fmt % args)


def main():
    if not TOKEN:
        log("FATAL: ALERT_ROUTER_TOKEN is unset — every webhook would be rejected")
        return 2
    log("listening on :%d write_mode=%s board_root=%s" %
        (PORT, "board" if WRITE else "spool", BOARD_ROOT))
    ThreadingHTTPServer(("0.0.0.0", PORT), Handler).serve_forever()
    return 0


if __name__ == "__main__":
    sys.exit(main())

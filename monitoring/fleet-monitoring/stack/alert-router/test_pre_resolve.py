#!/usr/bin/env python3
"""MON-GAP-017 — the alert-router must not write a pending row for an alert that has
already cleared by the time the webhook lands.

Each arm runs its own router process (fresh spool, fresh counters) against its own
Prometheus stand-in:

  A  Prometheus still reports the alert FIRING   -> pending row written (today's path)
  B  Prometheus reports NO firing series         -> no pending row; resolution event only,
                                                    note says it was pre-resolved
  C  Prometheus unreachable (dead port)          -> pending row written (fallback) and the
                                                    webhook still answers success
  D  Prometheus answers with a malformed body    -> pending row written (fallback)
  E  Prometheus hangs (accepts, never answers)   -> one 3s timeout for the whole batch,
                                                    rows still written (fallback)
  T  bearer check: no Authorization -> 401, with token -> row

A, C, D and E are the negative controls: if the check were blindly "skip the row", they
fail.

stdout is the evidence: for every arm it prints the PromQL the stub received, the spool
rows by id, and the router's own counters. Stdlib only; no network beyond 127.0.0.1.

  python3 stack/alert-router/test_pre_resolve.py
"""

import http.client
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import threading
import time
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

HERE = os.path.dirname(os.path.abspath(__file__))
ROUTER = os.path.join(HERE, "router.py")
TOKEN = "gap017-test-token"

FAILURES = []
SCRATCH = []
_KEEP_SCRATCH = False


def check(ok, msg):
    print("  %s %s" % ("PASS" if ok else "FAIL", msg))
    if not ok:
        FAILURES.append(msg)
    return ok


def free_port():
    """A port nothing is listening on (closed again before the caller uses it)."""
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def scratch_dir():
    """A fast scratch root for the per-arm spool.

    The router fsyncs every spool append, and the ambient TMPDIR here can be a slow
    spinning disk — that shows up as webhook latency which has nothing to do with the
    state check, so pick a fast filesystem explicitly.
    """
    for base in (os.environ.get("GAP017_SCRATCH_DIR"), "/tmp"):
        if base and os.path.isdir(base) and os.access(base, os.W_OK):
            return tempfile.mkdtemp(prefix="gap017-", dir=base)
    return tempfile.mkdtemp(prefix="gap017-")


# --------------------------------------------------------------- stub prometheus

class StubPrometheus:
    """Minimal /api/v1/query stand-in with a controllable answer.

    `payload` may be a dict (JSON-encoded) or raw bytes (to serve a malformed body).
    `queries` records every `query` parameter it was asked, which is the evidence that
    the router built the right selector.
    """

    def __init__(self):
        self.payload = {"status": "success",
                        "data": {"resultType": "vector", "result": []}}
        self.queries = []
        self.hits = 0
        stub = self

        class Handler(BaseHTTPRequestHandler):
            protocol_version = "HTTP/1.1"

            def do_GET(self):  # noqa: N802
                parsed = urlparse(self.path)
                if parsed.path != "/api/v1/query":
                    self._send(404, b"{}")
                    return
                stub.hits += 1
                stub.queries.append(parse_qs(parsed.query).get("query", [""])[0])
                body = stub.payload
                blob = body if isinstance(body, bytes) else json.dumps(body).encode()
                self._send(200, blob)

            def _send(self, code, blob, ctype="application/json"):
                self.send_response(code)
                self.send_header("Content-Type", ctype)
                self.send_header("Content-Length", str(len(blob)))
                self.end_headers()
                self.wfile.write(blob)

            def log_message(self, *args):
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.httpd.server_address[1]
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def stop(self):
        self.httpd.shutdown()
        self.httpd.server_close()


class BlackHole:
    """Accepts TCP connections on 127.0.0.1:<port> and never answers anything.

    This is the 'Prometheus is up but wedged' case: the state check has to give up on its
    own timeout, and the second alert in the same batch must not pay that timeout again.
    """

    def __init__(self):
        self.sock = socket.socket()
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind(("127.0.0.1", 0))
        self.sock.listen(16)
        self.port = self.sock.getsockname()[1]
        self.conns = []
        threading.Thread(target=self._accept, daemon=True).start()

    def _accept(self):
        while True:
            try:
                conn, _ = self.sock.accept()
            except OSError:
                return
            self.conns.append(conn)

    @property
    def url(self):
        return "http://127.0.0.1:%d" % self.port

    def stop(self):
        self.sock.close()
        for conn in self.conns:
            try:
                conn.close()
            except OSError:
                pass


def firing_result(alertname, host):
    return {"status": "success", "data": {"resultType": "vector", "result": [{
        "metric": {"__name__": "ALERTS", "alertname": alertname, "alertstate": "firing",
                   "host": host, "severity": "warning"},
        "value": [1760000000.0, "1"],
    }]}}


# --------------------------------------------------------------- router harness

class Router:
    """router.py as a subprocess; spool mode by default, board mode with write=True."""

    def __init__(self, prom_url, write=False):
        self.tmp = scratch_dir()
        SCRATCH.append(self.tmp)
        self.spool = os.path.join(self.tmp, "spool")
        self.board_root = os.path.join(self.tmp, "boards")
        self.port = free_port()
        env = dict(os.environ)
        env.pop("ALERT_ROUTER_WRITE", None)  # spool mode, as the brief requires
        env.update({
            "ALERT_ROUTER_TOKEN": TOKEN,
            "ALERT_ROUTER_PORT": str(self.port),
            "ALERT_ROUTER_SPOOL": self.spool,
            "PROM_URL": prom_url,
            "BOARD_ROOT": self.board_root,
        })
        if write:
            env["ALERT_ROUTER_WRITE"] = "1"
            os.makedirs(self.board_dir(), exist_ok=True)
        self.log_path = os.path.join(self.tmp, "router.log")
        self.log = open(self.log_path, "wb")
        self.proc = subprocess.Popen([sys.executable, ROUTER], env=env,
                                     stdout=self.log, stderr=subprocess.STDOUT)
        self._wait_ready()

    def _wait_ready(self, timeout=15.0):
        deadline = time.time() + timeout
        while time.time() < deadline:
            if self.proc.poll() is not None:
                raise RuntimeError("router exited rc=%s\n%s" % (self.proc.returncode, self.log_text()))
            try:
                conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=2)
                conn.request("GET", "/health")
                resp = conn.getresponse()
                resp.read()
                conn.close()
                if resp.status == 200:
                    return
            except OSError:
                time.sleep(0.1)
        raise RuntimeError("router never became ready\n%s" % self.log_text())

    def webhook(self, alerts, token=TOKEN):
        payload = {"version": "4", "status": "firing", "receiver": "alert-router",
                   "groupLabels": {}, "commonLabels": {}, "commonAnnotations": {},
                   "externalURL": "http://alertmanager:9093", "alerts": alerts}
        headers = {"Content-Type": "application/json"}
        if token:
            headers["Authorization"] = "Bearer " + token
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=10)
        conn.request("POST", "/webhook", body=json.dumps(payload), headers=headers)
        resp = conn.getresponse()
        body = json.loads(resp.read() or b"{}")
        status = resp.status
        conn.close()
        return status, body

    def health(self):
        conn = http.client.HTTPConnection("127.0.0.1", self.port, timeout=5)
        conn.request("GET", "/health")
        body = json.loads(conn.getresponse().read())
        conn.close()
        return body

    def spool_rows(self):
        path = os.path.join(self.spool, "board-rows.jsonl")
        if not os.path.exists(path):
            return [], b""
        with open(path, "rb") as fh:
            raw = fh.read()
        rows = [json.loads(line) for line in raw.decode().splitlines() if line.strip()]
        return rows, raw

    def board_dir(self):
        return os.path.join(self.board_root, "monitoring", ".coding-hermes", "board")

    def board_rows(self, filename):
        """Rows of one board file, plus the raw bytes (for the invariant check)."""
        path = os.path.join(self.board_dir(), filename)
        if not os.path.exists(path):
            return [], b""
        with open(path, "rb") as fh:
            raw = fh.read()
        return [json.loads(line) for line in raw.decode().splitlines() if line.strip()], raw

    def log_text(self):
        try:
            with open(self.log_path, "rb") as fh:
                return fh.read().decode("utf-8", "replace")
        except OSError:
            return ""

    def stop(self):
        self.proc.terminate()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.kill()
        self.log.close()


def alert(fingerprint, alertname="DiskWillFillIn24h", host="bunker-mvp", extra=None):
    labels = {"alertname": alertname, "severity": "warning", "lane": "monitoring",
              "job": "integrations/unix", "host": host, "instance": host + ":9100"}
    if extra:
        labels.update(extra)
    return {
        "status": "firing",
        "labels": labels,
        "annotations": {"summary": "%s on %s" % (alertname, host)},
        "startsAt": "2026-10-02T09:00:00Z",
        "endsAt": "0001-01-01T00:00:00Z",
        "generatorURL": "http://prometheus:9090/graph?g0.expr=up",
        "fingerprint": fingerprint,
    }


def row_ids(rows, status=None):
    return [r["id"] for r in rows if status is None or r.get("status") == status]


def main():
    global _KEEP_SCRATCH
    print("MON-GAP-017 — alert-router live-state check before writing pending rows")
    print("router: %s" % ROUTER)

    # ------------------------------------------------------------------ ARM A
    print("\n---- ARM A: Prometheus reports the alert STILL FIRING -> pending row (today's path)")
    stub = StubPrometheus()
    stub.payload = firing_result("DiskWillFillIn24h", "bunker-mvp")
    r = Router(stub.url)
    try:
        d = datetime.now(timezone.utc).strftime("%Y%m%d")
        status, _ = r.webhook([alert("aa11bb22cc33dd44", extra={"mountpoint": '/we"ird'})])
        rows, raw = r.spool_rows()
        ids = row_ids(rows)
        print("  webhook HTTP status: %s" % status)
        print("  stub saw %d query/queries: %s" % (stub.hits, stub.queries))
        print("  spool ids: %s" % ids)
        check(status == 200, "webhook answered 200")
        check(stub.hits == 1, "router queried Prometheus exactly once")
        q = stub.queries[0] if stub.queries else ""
        check(q.startswith("ALERTS{") and q.endswith("}"), "query is an ALERTS selector: %s" % q)
        check(q.count('alertstate="firing"') == 1, 'selector asks for alertstate="firing" once')
        check('alertstate="firing"' in q and 'alertname="DiskWillFillIn24h"' in q,
              "selector carries the alert's own labels")
        check('mountpoint="/we\\"ird"' in q, "label value is escaped for PromQL")
        expect = "MON-MONITORING-AA11BB22-%s" % d
        check(ids == [expect], "exactly one spooled row, id %s" % expect)
        check(all(row.get("status") == "pending" for row in rows),
              "that row is status=pending")
        check(not [x for x in rows if x.get("type") == "alert-resolved"],
              "no resolution event for a still-firing alert")
        check(raw.endswith(b"\n") and not raw.endswith(b"\n\n") and
              all(line.strip() for line in raw.split(b"\n")[:-1]),
              "spool keeps one JSON object per line + trailing newline")
    except Exception as exc:  # noqa: BLE001 - report, don't mask
        check(False, "arm A raised: %r" % exc)
    finally:
        r.stop()
        stub.stop()

    # ------------------------------------------------------------------ ARM B
    print("\n---- ARM B: Prometheus reports NOT FIRING (empty result) -> resolution only")
    stub = StubPrometheus()  # default payload: success + empty result
    r = Router(stub.url)
    try:
        d = datetime.now(timezone.utc).strftime("%Y%m%d")
        status, _ = r.webhook([alert("bb22cc33dd44ee55")])
        rows, raw = r.spool_rows()
        ids = row_ids(rows)
        pending = row_ids(rows, status="pending")
        events = [x for x in rows if x.get("type") == "alert-resolved"]
        print("  webhook HTTP status: %s" % status)
        print("  stub saw %d query/queries: %s" % (stub.hits, stub.queries))
        print("  spool row ids: %s" % ids)
        print("  resolution event: %s" % (json.dumps(events[0], sort_keys=True)
                                          if events else "NONE"))
        check(status == 200, "webhook answered 200")
        check(pending == [], "NO pending row written (was: the MON-GAP-017 defect)")
        expect = "MON-MONITORING-BB22CC33-%s-RESOLVED" % d
        check([x["id"] for x in events] == [expect],
              "resolution event %s present" % expect)
        check(bool(events) and "pre-resolved at webhook time" in (events[0].get("note") or ""),
              "resolution event carries the pre-resolved note")
        check(bool(events) and events[0].get("type") == "alert-resolved"
              and events[0].get("lane") == "monitoring"
              and events[0].get("alertname") == "DiskWillFillIn24h",
              "resolution event keeps the build_resolution shape")
        check(r.health()["counters"]["rows_pre_resolved_total"] == 1,
              "/health rows_pre_resolved_total == 1")
        check(raw.endswith(b"\n") and not raw.endswith(b"\n\n"),
              "spool keeps one JSON object per line + trailing newline")
    except Exception as exc:  # noqa: BLE001
        check(False, "arm B raised: %r" % exc)
    finally:
        r.stop()
        stub.stop()

    # ------------------------------------------------------------------ ARM C
    print("\n---- ARM C: Prometheus unreachable (dead port) -> pending row (fallback)")
    dead = free_port()
    try:
        socket.create_connection(("127.0.0.1", dead), timeout=2).close()
        print("  note: port %d unexpectedly accepts connections" % dead)
    except OSError as exc:
        print("  pre-probe from the test: 127.0.0.1:%d -> %r" % (dead, exc))
    r = Router("http://127.0.0.1:%d" % dead)
    try:
        d = datetime.now(timezone.utc).strftime("%Y%m%d")
        started = time.time()
        status, body = r.webhook([alert("cc33dd44ee55ff66")])
        elapsed = time.time() - started
        rows, _ = r.spool_rows()
        ids = row_ids(rows)
        print("  webhook HTTP status: %s (%.2fs)" % (status, elapsed))
        print("  spool ids: %s" % ids)
        check(status == 200, "webhook returned success despite the state-check failure")
        check(elapsed < 5.0, "webhook was not delayed past the short timeout (%.2fs)" % elapsed)
        expect = "MON-MONITORING-CC33DD44-%s" % d
        check(ids == [expect], "pending row %s written (fallback = today's behaviour)" % expect)
        check(r.health()["counters"]["rows_statecheck_failed_total"] == 1,
              "/health rows_statecheck_failed_total == 1")
        check("state check failed" in r.log_text(),
              "router logged the failed state check")
    except Exception as exc:  # noqa: BLE001
        check(False, "arm C raised: %r" % exc)
    finally:
        r.stop()

    # ------------------------------------------------------------------ ARM D
    print("\n---- ARM D: Prometheus answers a MALFORMED body -> pending row (fallback)")
    stub = StubPrometheus()
    stub.payload = b"<html>503 gateway</html>"  # not JSON at all
    r = Router(stub.url)
    try:
        d = datetime.now(timezone.utc).strftime("%Y%m%d")
        status, _ = r.webhook([alert("dd44ee55ff660011")])
        rows, _ = r.spool_rows()
        ids = row_ids(rows)
        print("  webhook HTTP status: %s" % status)
        print("  spool ids: %s" % ids)
        check(status == 200, "webhook returned success")
        expect = "MON-MONITORING-DD44EE55-%s" % d
        check(ids == [expect], "pending row %s written (fallback)" % expect)
        check(r.health()["counters"]["rows_statecheck_failed_total"] == 1,
              "/health rows_statecheck_failed_total == 1")
    except Exception as exc:  # noqa: BLE001
        check(False, "arm D raised: %r" % exc)
    finally:
        r.stop()
        stub.stop()

    # ------------------------------------------------------------------ ARM E
    print("\n---- ARM E: Prometheus HANGS (accepts, never answers) -> timeout, rows still written")
    hole = BlackHole()
    r = Router(hole.url)
    try:
        d = datetime.now(timezone.utc).strftime("%Y%m%d")
        started = time.time()
        status, _ = r.webhook([alert("ff66001122334455"), alert("6600112233445566")])
        elapsed = time.time() - started
        rows, _ = r.spool_rows()
        ids = row_ids(rows)
        counters = r.health()["counters"]
        attempts = r.log_text().count("state check failed")
        print("  webhook HTTP status: %s (%.2fs for 2 alerts)" % (status, elapsed))
        print("  spool ids: %s" % ids)
        print("  query attempts that reached the hung Prometheus: %d" % len(hole.conns))
        print("  router 'state check failed' log lines: %d" % attempts)
        print("  rows_statecheck_failed_total: %d  rows_spooled_total: %d"
              % (counters["rows_statecheck_failed_total"], counters["rows_spooled_total"]))
        check(status == 200, "webhook returned success against a hung Prometheus")
        check(3.0 <= elapsed < 6.0,
              "one %.1fs timeout for the batch, not one per alert (%.2fs)" % (3.0, elapsed))
        check(ids == ["MON-MONITORING-FF660011-%s" % d, "MON-MONITORING-66001122-%s" % d],
              "both pending rows written (fallback), in order")
        check(len(hole.conns) == 1 and attempts == 1,
              "only the FIRST alert of the batch paid the timeout (1 attempt, 1 log line)")
        check(counters["rows_statecheck_failed_total"] == 2,
              "both alerts counted as uncheckable (rows_statecheck_failed_total=2)")
    except Exception as exc:  # noqa: BLE001
        check(False, "arm E raised: %r" % exc)
    finally:
        r.stop()
        hole.stop()

    # ------------------------------------------------------------------ ARM F
    print("\n---- ARM F: board mode (ALERT_ROUTER_WRITE=1) — same rule, tasks/events")
    stub = StubPrometheus()
    r = Router(stub.url, write=True)
    try:
        d = datetime.now(timezone.utc).strftime("%Y%m%d")
        stub.payload = firing_result("DiskWillFillIn24h", "bunker-mvp")
        r.webhook([alert("1122334455667788")])
        stub.payload = {"status": "success", "data": {"resultType": "vector", "result": []}}
        r.webhook([alert("2233445566778899")])
        r.webhook([{**alert("3344556677889900"), "status": "resolved"}])
        tasks, tasks_raw = r.board_rows("tasks.jsonl")
        events, events_raw = r.board_rows("events.jsonl")
        print("  tasks.jsonl ids: %s" % [row["id"] for row in tasks])
        print("  events.jsonl ids: %s" % [row["id"] for row in events])
        print("  counters: %s" % json.dumps(r.health()["counters"], sort_keys=True))
        check([row["id"] for row in tasks] == ["MON-MONITORING-11223344-%s" % d],
              "only the still-firing alert reached the board")
        check(all(row.get("status") == "pending" for row in tasks),
              "the board row is status=pending")
        check([row["id"] for row in events] == ["MON-MONITORING-22334455-%s-RESOLVED" % d,
                                                "MON-MONITORING-33445566-%s-RESOLVED" % d],
              "pre-resolved alert AND a real resolved webhook both became events")
        check(events and "pre-resolved at webhook time" in (events[0].get("note") or ""),
              "the pre-resolved event keeps its note on the board")
        check(events_raw.endswith(b"\n") and not events_raw.endswith(b"\n\n") and
              tasks_raw.endswith(b"\n") and not tasks_raw.endswith(b"\n\n"),
              "both board files keep one JSON object per line + trailing newline")
    except Exception as exc:  # noqa: BLE001
        check(False, "arm F raised: %r" % exc)
    finally:
        r.stop()
        stub.stop()

    # ------------------------------------------------------------------ token path
    print("\n---- TOKEN: bearer check still enforced (ALERT_ROUTER_TOKEN set)")
    stub = StubPrometheus()
    stub.payload = firing_result("DiskWillFillIn24h", "bunker-mvp")
    r = Router(stub.url)
    try:
        bad, _ = r.webhook([alert("ee55ff6600112233")], token=None)
        good, _ = r.webhook([alert("ee55ff6600112233")])
        rows, _ = r.spool_rows()
        print("  POST without Authorization: %s   with token: %s" % (bad, good))
        print("  spool ids: %s" % row_ids(rows))
        check(bad == 401, "unauthenticated webhook rejected 401")
        check(good == 200, "authenticated webhook accepted")
        check(len(row_ids(rows)) == 1, "only the authenticated alert produced a row")
    except Exception as exc:  # noqa: BLE001
        check(False, "token arm raised: %r" % exc)
    finally:
        r.stop()
        stub.stop()

    print("\n%d check(s) failed" % len(FAILURES))
    for msg in FAILURES:
        print("  FAILED: %s" % msg)
    _KEEP_SCRATCH = bool(FAILURES)
    return 1 if FAILURES else 0


if __name__ == "__main__":
    try:
        rc = main()
    finally:
        if _KEEP_SCRATCH:
            print("scratch kept for inspection: %s" % SCRATCH)
        else:
            for path in SCRATCH:
                shutil.rmtree(path, ignore_errors=True)
    sys.exit(rc)

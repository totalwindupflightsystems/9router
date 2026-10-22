#!/usr/bin/env python3
"""Fake schedulerd for the SCHED-GAP-1756 credential-ladder tests.

Speaks just enough of the operator gate (SCHED-GAP-1602) to prove the drain-restart
script resolves ONE working credential:

  POST /api/v1/pause   -> 200 {"status":"paused"}  when the presented credential is the
                          one this MODE accepts, else 401 {"error":"invalid operator credential"}
  POST /api/v1/resume  -> mirror of pause (MODE=resume_401 always refuses it)
  GET  /api/v1/status  -> {"paused": <bool>, "active_ticks": <int>}
  GET  /api/v1/health  -> {"status":"ok","db":"connected"}
  GET  /_state         -> {"paused":..., "calls":[...]} for test assertions

MODE (env FAKE_MODE):
  operator_ok   only X-Operator-Token == FAKE_OPERATOR_TOKEN is accepted
  bearer_ok     only Authorization: Bearer == FAKE_KEY is accepted
  both_401      nothing is accepted (the daemon knows neither credential)
  resume_401    pause accepts the operator token, resume always answers 401

Binds an ephemeral port and prints PORT=<n> on stdout for the harness.
"""
import json
import os
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

MODE = os.environ.get("FAKE_MODE", "operator_ok")
OP_TOKEN = os.environ.get("FAKE_OPERATOR_TOKEN", "")
KEY = os.environ.get("FAKE_KEY", "")
STATE = {"paused": False, "calls": []}


def operator_accepted(headers):
    if MODE in ("operator_ok", "resume_401"):
        return bool(OP_TOKEN) and headers.get("X-Operator-Token", "") == OP_TOKEN
    if MODE == "bearer_ok":
        return bool(KEY) and headers.get("Authorization", "") == f"Bearer {KEY}"
    return False  # both_401


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *args):  # keep the test output clean
        pass

    def _send(self, code, payload):
        # Compact separators: the Go daemon's encoding/json emits `{"status":"ok","db":"connected"}`,
        # and the helper's health case-pattern matches that exact shape.
        body = json.dumps(payload, separators=(",", ":")).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path == "/api/v1/status":
            return self._send(200, {
                "paused": STATE["paused"],
                "active_ticks": 0 if STATE["paused"] else 3,
            })
        if self.path == "/api/v1/health":
            return self._send(200, {"status": "ok", "db": "connected"})
        if self.path == "/_state":
            return self._send(200, STATE)
        return self._send(404, {"error": "not found"})

    def do_POST(self):
        # Record only WHICH credential shape arrived, never the value.
        STATE["calls"].append({
            "path": self.path,
            "operator_header": bool(self.headers.get("X-Operator-Token")),
            "authorization_header": bool(self.headers.get("Authorization")),
        })
        if self.path not in ("/api/v1/pause", "/api/v1/resume"):
            return self._send(404, {"error": "not found"})
        accepted = operator_accepted(self.headers)
        if self.path == "/api/v1/resume" and MODE == "resume_401":
            accepted = False
        if not accepted:
            return self._send(401, {"error": "invalid operator credential"})
        STATE["paused"] = self.path == "/api/v1/pause"
        return self._send(200, {"status": "paused" if STATE["paused"] else "resumed"})


def main():
    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    print(f"PORT={server.server_address[1]}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

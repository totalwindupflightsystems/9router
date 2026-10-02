#!/usr/bin/env python3
"""fleet-gateway-facade — the door the scheduler speaks when the work is REMOTE.

The scheduler POSTs /v1/responses (stream:true) to ONE global gateway.url, carrying a per-lane
`Authorization: Bearer <key>` and `X-Hermes-Session-Key: <tick id>`. This adapter maps that key to
a remote agent + its box, drives the agent INSIDE its container, and answers in the same SSE shape
the scheduler parses (any typed event = activity; only response.completed / response.failed are
terminal, unmarshalled as {response:{...}, error:{...}}).

An UNMAPPED key is proxied to the local gateway, so adopting this is additive and nothing that
works today regresses.

Why an adapter and not a proxy to a container listener: there is no HTTP listener inside an agent
container. Work is driven by `bunker exec`, so the adapter is a TRANSLATOR, not a tunnel.

Mapping file (0600): ~/.hermes/secrets/fleet-gateway-keys.json
  {"helix": {"key": "<secret>", "box": "hermes-fleet-02"}}

usage:
  fleet-gateway-facade.py --mint              # create/refresh keys for the live agents
  fleet-gateway-facade.py --port 8650        # serve
"""

from __future__ import annotations

import argparse
import json
import os
import secrets
import shlex
import subprocess
import sys
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib import request as urlreq

BUNKER = "/home/kara/.local/bin/bunker"
MAP_FILE = Path.home() / ".hermes/secrets/fleet-gateway-keys.json"
LOCAL_GATEWAY = "http://127.0.0.1:8642"
LOCAL_GATEWAY_KEY_FILE = Path.home() / ".hermes/secrets/gateway.key"
TASK_S = 900
EXEC_TIMEOUT = "900s"
LIVE_AGENTS = {
    "musterflow": "hermes-fleet-02", "helix": "hermes-fleet-02",
    "deepseek-dashboard": "hermes-fleet-02", "rabbit-hole": "hermes-fleet-03",
    "asce": "hermes-fleet-03", "imhotep": "hermes-fleet-03",
    "rethinkdb": "hermes-fleet-04", "temple-runner": "hermes-fleet-04",
}

# --- per-dispatch scoped GitHub credential (kanban t_c4bdf8b5) ---
# The token travels WITH the task: 1-hour, narrowed to the agent's own repo, minted
# here at dispatch time and placed in the session env. It is never written to a home.
SCOPE_TOOL = os.environ.get("FLEET_GH_SCOPE", "/home/kara/.hermes/scripts/fleet-gh-scope.py")
try:
    import importlib.util as _ilu
    _spec = _ilu.spec_from_file_location("fleet_gh_scope", SCOPE_TOOL)
    SCOPE = _ilu.module_from_spec(_spec) if _spec and _spec.loader else None
    if SCOPE is not None:
        _spec.loader.exec_module(SCOPE)
except Exception as _exc:  # noqa: BLE001
    sys.stderr.write("facade: fleet-gh-scope unavailable (%s) — no GH_TOKEN injected\n" % _exc)
    SCOPE = None


def gh_env(agent: str) -> str:
    """`GH_TOKEN=... GITHUB_TOKEN=... ` for this agent's repo, or '' on any failure."""
    if SCOPE is None:
        return ""
    try:
        return SCOPE.env_prefix(SCOPE.dispatch_env(agent))
    except Exception as exc:  # noqa: BLE001
        sys.stderr.write("facade: scoped token failed for %s (%s)\n" % (agent, exc))
        return ""



def load_map() -> dict:
    try:
        with MAP_FILE.open(encoding="utf-8") as fh:
            return json.load(fh)
    except FileNotFoundError:
        return {}


def mint() -> None:
    m = load_map()
    for agent, box in LIVE_AGENTS.items():
        entry = m.get(agent) or {}
        entry.setdefault("key", "fleet-" + secrets.token_urlsafe(32))
        entry["box"] = box
        entry["home"] = "/home/bunker-%s" % agent
        m[agent] = entry
    MAP_FILE.parent.mkdir(parents=True, exist_ok=True)
    MAP_FILE.write_text(json.dumps(m, indent=2), encoding="utf-8")
    os.chmod(MAP_FILE, 0o600)
    print("minted keys for %d agents -> %s (0600)" % (len(m), MAP_FILE))
    for a in sorted(m):
        print("  %-20s box=%s key=%s..." % (a, m[a]["box"], m[a]["key"][:12]))


def key_of(header: str) -> str:
    header = header or ""
    return header[7:].strip() if header.lower().startswith("bearer ") else ""


def extract_prompt(body: dict) -> str:
    """Accept the shapes the scheduler may send: a plain string, a Responses-style input list,
    or a chat-style messages list."""
    inp = body.get("input", body.get("prompt", ""))
    if isinstance(inp, str):
        return inp
    parts: list[str] = []
    if isinstance(inp, list):
        for item in inp:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                content = item.get("content")
                if isinstance(content, str):
                    parts.append(content)
                elif isinstance(content, list):
                    for c in content:
                        if isinstance(c, dict) and c.get("text"):
                            parts.append(str(c["text"]))
                        elif isinstance(c, str):
                            parts.append(c)
                elif item.get("text"):
                    parts.append(str(item["text"]))
    return "\n".join(p for p in parts if p)


def drive(agent: str, box: str, prompt: str) -> tuple[bool, str]:
    """Run the prompt inside the agent's container, exactly the way the proven dispatcher does."""
    ah = "/home/bunker-%s" % agent
    inner = (
        "HOME=%(ah)s PATH=%(ah)s/.local/bin:/usr/local/bin:/usr/bin:/bin %(gh)s"
        "timeout %(t)s %(ah)s/.local/bin/hermes chat -q %(task)s -Q"
        % {"ah": ah, "t": TASK_S, "gh": gh_env(agent), "task": shlex.quote(prompt)}
    )
    argv = [BUNKER, "exec", agent, "--server", box, "--timeout", EXEC_TIMEOUT, "--", "sh", "-c", inner]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=float(TASK_S) + 180)
    except subprocess.TimeoutExpired:
        return False, "bunker exec timed out after %ss" % (float(TASK_S) + 180)
    out, err = (proc.stdout or "").strip(), (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, "bunker exec exit %s: %s" % (proc.returncode, (err or out)[:2000])
    lines = [ln for ln in out.split("\n") if ln.strip()]
    return True, ("\n".join(lines[-6:]) if lines else "")[:8000]


def proxy_local(path: str, method: str, headers: dict, payload: bytes | None) -> tuple[int, bytes, str]:
    """Unmapped key -> the local gateway, unchanged. Keeps the adapter additive.

    The scheduler's global key IS the local gateway's key when nothing is remapped, so the
    incoming Authorization is the correct credential to forward; the key file is a fallback
    for callers that arrive without one.
    """
    key = ""
    try:
        key = LOCAL_GATEWAY_KEY_FILE.read_text(encoding="utf-8").strip()
    except OSError:
        key = key_of(headers.get("Authorization", ""))
    req = urlreq.Request(LOCAL_GATEWAY + path, data=payload, method=method)
    for k, v in headers.items():
        if k.lower() in ("host", "content-length", "authorization"):
            continue
        req.add_header(k, v)
    if key:
        req.add_header("Authorization", "Bearer " + key)
    try:
        with urlreq.urlopen(req, timeout=120) as r:
            return r.status, r.read(), r.headers.get("Content-Type", "application/json")
    except Exception as exc:  # noqa: BLE001
        return 502, json.dumps({"error": {"message": str(exc)}}).encode(), "application/json"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    mapping: dict = {}

    def log_message(self, fmt, *args):  # quieter, prefixed
        sys.stderr.write("facade %s - %s\n" % (self.address_string(), fmt % args))

    def _sse(self, obj: dict) -> None:
        self.wfile.write(b"data: " + json.dumps(obj).encode() + b"\n\n")
        self.wfile.flush()

    def do_GET(self):  # noqa: N802
        if self.path.startswith("/health"):
            body = json.dumps({
                "ok": True, "mapped_agents": len(self.mapping), "local_gateway": LOCAL_GATEWAY,
            }).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return
        self._json(404, {"error": {"message": "not found"}})

    def _json(self, code: int, obj: dict) -> None:
        body = json.dumps(obj).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):  # noqa: N802
        length = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(length) if length else b""
        key = key_of(self.headers.get("Authorization"))
        agent = next((a for a, e in self.mapping.items() if e.get("key") == key), None)

        if agent is None:
            status, body, ctype = proxy_local(self.path, "POST", dict(self.headers), raw)
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
            return

        try:
            body = json.loads(raw or b"{}")
        except json.JSONDecodeError:
            self._json(400, {"error": {"message": "invalid JSON body"}})
            return

        prompt = extract_prompt(body)
        if not prompt.strip():
            self._json(400, {"error": {"message": "no prompt in input"}})
            return

        entry = self.mapping[agent]
        rid = "resp_" + uuid.uuid4().hex[:24]
        tick = self.headers.get("X-Hermes-Session-Key", "")
        want_stream = bool(body.get("stream"))
        started = time.time()
        ok, text = drive(agent, entry.get("box", ""), prompt)
        elapsed = round(time.time() - started, 1)
        sys.stderr.write("facade dispatch agent=%s tick=%s ok=%s %.1fs\n" % (agent, tick, ok, elapsed))

        resp = {
            "id": rid,
            "object": "response",
            "created_at": int(started),
            "model": body.get("model") or "remote-agent",
            "status": "completed" if ok else "failed",
            "output": [{"type": "message", "role": "assistant",
                        "content": [{"type": "output_text", "text": text}]}],
            "usage": {"input_tokens": len(prompt) // 4, "output_tokens": len(text) // 4},
        }
        if not ok:
            resp["error"] = {"type": "agent_error", "message": text[:500]}

        if not want_stream:
            self._json(200, resp)
            return

        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Connection", "close")
        self.end_headers()
        try:
            self._sse({"type": "response.created", "response": {"id": rid, "status": "in_progress"}})
            for i in range(0, len(text), 400):
                self._sse({"type": "response.output_text.delta", "delta": text[i:i + 400]})
            if ok:
                self._sse({"type": "response.completed", "response": resp})
            else:
                self._sse({"type": "response.failed", "response": resp,
                           "error": {"message": text[:500]}})
            self.wfile.write(b"data: [DONE]\n\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            sys.stderr.write("facade client hung up mid-stream agent=%s\n" % agent)
        self.close_connection = True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--mint", action="store_true", help="(re)generate a key per live agent")
    ap.add_argument("--port", type=int, default=8650)
    ap.add_argument("--host", default="127.0.0.1")
    args = ap.parse_args()

    if args.mint:
        mint()
        return 0

    Handler.mapping = load_map()
    if not Handler.mapping:
        print("no mapping — run --mint first", file=sys.stderr)
        return 1
    srv = ThreadingHTTPServer((args.host, args.port), Handler)
    print("fleet-gateway-facade on %s:%d — %d agents mapped, unmapped keys -> %s"
          % (args.host, args.port, len(Handler.mapping), LOCAL_GATEWAY), flush=True)
    srv.serve_forever()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

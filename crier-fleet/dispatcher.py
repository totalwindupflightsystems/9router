#!/usr/bin/env python3
"""Fleet dispatcher — runs on the control box, one loop for every agent on every box.

Why it lives OUTSIDE the containers: a long-running process started through `bunker exec`
dies when that exec's session ends (measured: the in-container bridge was gone after the
starting exec returned, pidfile and all). A poller inside an agent therefore cannot stay up.
This process lives on the control box, which has the bunker CLI, the bus and every agent key.

What is NOT given up: the work itself still runs INSIDE the agent's container, because the
dispatcher runs it with `bunker exec`. The agent keeps its isolation; the poller just stops
being a container process.

Delivery contract (inherited from crier, not invented here):
  * retrieve() LEASES a message, so a dispatcher crash does not lose it.
  * a task that FAILS is deliberately not acked — the lease expires and the bus redelivers.
  * only a completed task is acked, so "acked" means "done", never "picked up".
"""

from __future__ import annotations

import json
import os
import shlex
import subprocess
import sys
import time
import traceback

FLEET = "/home/kara/crier-fleet"
sys.path.insert(0, "/home/kara/crier/clients/python")

from crier_client import Crier  # noqa: E402

BUS = os.environ.get("CRIER_URL", "http://100.97.236.14:8767")
TOKEN_FILE = "/home/kara/.hermes/secrets/crier-fleet.token"
KEYS = os.path.join(FLEET, "keys")
LOG = os.environ.get("DISPATCH_LOG", os.path.join(FLEET, "logs", "dispatcher.log"))
PIDFILE = os.environ.get("DISPATCH_PIDFILE", os.path.join(FLEET, "dispatcher.pid"))
POLL_S = float(os.environ.get("DISPATCH_POLL_S", "5"))
LEASE_S = int(os.environ.get("DISPATCH_LEASE_S", "1800"))
EXEC_TIMEOUT = os.environ.get("DISPATCH_EXEC_TIMEOUT", "400s")
TASK_S = os.environ.get("DISPATCH_TASK_S", "240")

# Invoke bunker by ABSOLUTE PATH. Two binaries exist on this box and PATH order decides which
# one runs: ~/.local/bin/bunker is 0.1.4 (understands the servers' self-signed cert_pin), while
# /usr/local/bin/bunker -> ~/go/bin/bunker is 0.1.3 and predates cert pinning, so it verifies
# the certificate against the bare IP and fails with "cannot validate certificate ... no IP SANs".
# A service that resolves `bunker` from PATH silently gets whichever one PATH offers.
BUNKER = os.environ.get("BUNKER_BIN", "/home/kara/.local/bin/bunker")

# --- per-dispatch scoped GitHub credential ------------------------------------------
# The agent's credential arrives WITH the work: a 1-hour installation token narrowed to
# that agent's own repo, minted on this box at dispatch time and passed in the session
# environment. Nothing durable lands in the agent's home, and the blob an agent could
# leak reaches ONE repo instead of all 37 in the App installation.
# An unreachable scoper is NOT fatal: log it and dispatch without GH_TOKEN.
SCOPE_TOOL = os.environ.get("FLEET_GH_SCOPE", "/home/kara/.hermes/scripts/fleet-gh-scope.py")


def _load_scope():
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location("fleet_gh_scope", SCOPE_TOOL)
        if spec is None or spec.loader is None:
            raise ImportError("no loader for %s" % SCOPE_TOOL)
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
        return mod
    except Exception as exc:  # noqa: BLE001
        # no log() yet at import time
        sys.stderr.write("dispatcher: fleet-gh-scope unavailable (%s) — "
                         "dispatches will carry no GH_TOKEN\n" % exc)
        return None


SCOPE = _load_scope()


def gh_env(agent: str) -> str:
    """`GH_TOKEN=... GITHUB_TOKEN=... ` for the agent's own repo, or ''."""
    if SCOPE is None:
        return ""
    try:
        return SCOPE.env_prefix(SCOPE.dispatch_env(agent))
    except Exception as exc:  # noqa: BLE001
        log("scoped token mint failed for %s (%s) — dispatching without GH_TOKEN" % (agent, exc))
        return ""


# agent id -> bunker server alias (one Hermes agent per project, four per box).
# Read from a FILE by default: a JSON blob inside a systemd EnvironmentFile is fragile
# (quotes and braces are parsed by systemd, not by us).
AGENTS_FILE = os.environ.get("FLEET_AGENTS_FILE", os.path.join(FLEET, "fleet_agents.json"))
if os.environ.get("FLEET_AGENTS"):
    AGENTS: dict[str, str] = json.loads(os.environ["FLEET_AGENTS"])
else:
    with open(AGENTS_FILE, encoding="utf-8") as _fh:
        AGENTS = json.load(_fh)


def log(msg: str) -> None:
    line = "%s %s\n" % (time.strftime("%Y-%m-%dT%H:%M:%S%z"), msg)
    try:
        with open(LOG, "a", encoding="utf-8") as fh:
            fh.write(line)
    except OSError:
        pass
    sys.stdout.write(line)
    sys.stdout.flush()


def token():
    try:
        return open(TOKEN_FILE, encoding="utf-8").read().strip()
    except OSError:
        return None


def client_for(agent: str) -> Crier:
    return Crier(BUS, agent_id=agent, key_path=os.path.join(KEYS, "%s.key" % agent),
                 token=token(), timeout=30.0)


def payload_task(msg) -> str:
    raw = getattr(msg, "payload", None)
    if isinstance(raw, dict):
        for key in ("task", "text", "prompt", "message", "body"):
            if isinstance(raw.get(key), str):
                return raw[key]
        return json.dumps(raw)
    if isinstance(raw, bytes):
        return raw.decode("utf-8", "replace")
    if isinstance(raw, str):
        return raw
    return json.dumps(raw)


def payload_reply_to(msg, default: str = "orchestrator") -> str:
    raw = getattr(msg, "payload", None)
    if isinstance(raw, dict) and isinstance(raw.get("reply_to"), str):
        return raw["reply_to"]
    return default


def dispatch(agent: str, server: str, task: str) -> tuple[bool, str]:
    """Run the task inside the agent's container. Returns (ok, output)."""
    ah = "/home/bunker-%s" % agent
    inner = (
        "HOME=%(ah)s PATH=%(ah)s/.local/bin:/usr/local/bin:/usr/bin:/bin %(gh)s"
        "timeout %(t)s %(ah)s/.local/bin/hermes chat -q %(task)s -Q"
        % {"ah": ah, "t": TASK_S, "gh": gh_env(agent), "task": shlex.quote(task)}
    )
    argv = [BUNKER, "exec", agent, "--server", server, "--timeout", EXEC_TIMEOUT, "--",
            "sh", "-c", inner]
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, timeout=float(TASK_S) + 180)
    except subprocess.TimeoutExpired:
        return False, "bunker exec timed out after %ss" % (float(TASK_S) + 180)
    out = (proc.stdout or "").strip()
    err = (proc.stderr or "").strip()
    if proc.returncode != 0:
        return False, "bunker exec exit %s: %s" % (proc.returncode, (err or out)[:2000])
    # bunker prints its own banner lines; the model's answer is the last non-empty line block
    lines = [ln for ln in out.split("\n") if ln.strip()]
    answer = "\n".join(lines[-6:]) if lines else ""
    return True, answer[:8000]


def main() -> int:
    try:
        with open(PIDFILE, encoding="utf-8") as fh:
            old = int(fh.read().strip().split()[0])
        os.kill(old, 0)
        log("dispatcher already running as pid %s — exiting this copy" % old)
        return 0
    except (OSError, ValueError, IndexError):
        pass
    with open(PIDFILE, "w", encoding="utf-8") as fh:
        fh.write("%s\n" % os.getpid())

    if not AGENTS:
        log("no FLEET_AGENTS configured — nothing to dispatch")
        return 1
    log("dispatcher up: %d agents, bus=%s, poll=%ss, lease=%ss" % (len(AGENTS), BUS, POLL_S, LEASE_S))

    clients = {}
    for agent in AGENTS:
        try:
            clients[agent] = client_for(agent)
        except Exception as exc:
            log("client for %s failed: %s" % (agent, exc))

    while True:
        idle = True
        for agent, server in AGENTS.items():
            crier = clients.get(agent)
            if crier is None:
                continue
            try:
                messages = crier.retrieve(limit=1, lease_seconds=LEASE_S)
            except Exception as exc:
                log("retrieve failed for %s: %s" % (agent, exc))
                continue
            if not messages:
                continue
            idle = False
            for msg in messages:
                mid = str(getattr(msg, "id", "") or "")
                task = payload_task(msg)
                reply_to = payload_reply_to(msg)
                log("dispatch %s -> %s: %s" % (mid, agent, task[:110].replace("\n", " ")))
                started = time.time()
                ok, output = dispatch(agent, server, task)
                elapsed = round(time.time() - started, 1)
                try:
                    crier.deliver(reply_to, {
                        "in_reply_to": mid, "agent": agent, "ok": ok,
                        "seconds": elapsed, "task": task[:500], "reply": output,
                    }, sender=agent)
                except Exception as exc:
                    log("reply delivery failed for %s (left unacked): %s" % (mid, exc))
                    continue
                if ok:
                    try:
                        crier.ack(msg)
                        log("done %s (%s) in %ss — acked" % (mid, agent, elapsed))
                    except Exception as exc:
                        log("ack failed for %s: %s — will redeliver" % (mid, exc))
                else:
                    log("FAILED %s (%s) in %ss — left unacked for redelivery: %s"
                        % (mid, agent, elapsed, output[:300]))
        if idle:
            time.sleep(POLL_S)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        sys.exit(0)
    except Exception:
        log("dispatcher died:\n%s" % traceback.format_exc())
        sys.exit(1)

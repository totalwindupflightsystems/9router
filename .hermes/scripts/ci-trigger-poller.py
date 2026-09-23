#!/usr/bin/env python3
"""ci-trigger-poller — DuckBrain's HTTP server is the trigger base.

The design (Bane 2026-09-23): a push adds an entry to DuckBrain; DuckBrain's own
scheduler tries to PULL THE COMMIT — over http, https or ssh — without fetching a
tree and without a dry run (i.e. fetch that one SHA, nothing more). Only when the
commit is provably retrievable does the job become eligible to schedule on the
mother host's self-hosted runner.

This script is the middle leg. It is deliberately small and dependency-free.

  pending --(lease)--> fetching --(git fetch --depth=1 <repo> <sha>)--> ready
                                      \\--(failure)--> pending(retry) | failed

Why fetch-by-SHA and not ls-remote or a dry-run:
  * `git ls-remote` proves a REF exists, not that a specific commit is fetchable.
  * `git fetch --dry-run` still negotiates and can pull objects.
  * `git fetch --depth=1 <remote> <sha>` pulls exactly one commit object graph
    (no tree walk beyond what git needs), which is the smallest thing that PROVES
    "this sha is retrievable from this remote".

Table: DuckBrain namespace `ci`, declared table `trigger`
  (tables/trigger.table.json -> PostgREST surface /api/ns/ci/tables/trigger)
"""
from __future__ import annotations
import json, os, subprocess, sys, time, urllib.error, urllib.parse, urllib.request

DB        = os.environ.get("DUCKBRAIN_URL", "http://localhost:3000")
NS        = os.environ.get("CI_NS", "ci")
TABLE     = os.environ.get("CI_TABLE", "trigger")
KEY_FILE  = os.environ.get("DUCKBRAIN_KEY_FILE", os.path.expanduser("~/.duckbrain/foreman-status.token"))
MIRRORS   = os.environ.get("CI_MIRRORS", "/var/tmp/ci-mirrors")
LEASE_S   = int(os.environ.get("CI_LEASE_S", "900"))
NODE      = os.environ.get("CI_NODE", os.uname().nodename)
MAX_TRY   = int(os.environ.get("CI_MAX_ATTEMPTS", "3"))
BATCH     = int(os.environ.get("CI_BATCH", "5"))

T = f"{DB}/api/ns/{NS}/tables/{TABLE}"


def key() -> str:
    try:
        return open(KEY_FILE).read().strip()
    except OSError:
        return os.environ.get("DUCKBRAIN_API_KEY", "")


def http(method: str, url: str, body=None, tries: int = 5):
    """DuckBrain rate-limits; retry on 429 with a short backoff."""
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(tries):
        req = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json",
                                              "x-api-key": key()})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                raw = r.read().decode() or "{}"
                return json.loads(raw) if raw.strip().startswith(("[", "{")) else raw
        except urllib.error.HTTPError as e:
            payload = e.read().decode()[:200]
            if e.code == 429 or "Rate limit" in payload:
                time.sleep(2.0 * (attempt + 1))
                continue
            raise RuntimeError(f"{method} {url} -> {e.code} {payload}") from None
        except Exception as exc:  # network blip
            if attempt == tries - 1:
                raise
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"{method} {url} exhausted retries")


def pending(limit: int = BATCH):
    q = urllib.parse.urlencode({"status": "eq.pending", "order": "created_at.asc",
                                "limit": limit})
    rows = http("GET", f"{T}?{q}")
    return rows if isinstance(rows, list) else []


def patch(row_id: str, fields: dict):
    # DuckBrain's PostgREST surface requires the PRIMARY KEY filter for
    # PATCH/DELETE: ?pk=eq.<value>. A ?id=eq. filter is accepted for reads but
    # refused with VALIDATION_ERROR on writes (proven 2026-09-23).
    q = urllib.parse.urlencode({"pk": f"eq.{row_id}"})
    return http("PATCH", f"{T}?{q}", fields)


def mirror_for(repo: str) -> str:
    slug = repo.rstrip("/").split("/")[-1].replace(".git", "")
    d = os.path.join(MIRRORS, slug)
    os.makedirs(d, exist_ok=True)
    if not os.path.isdir(os.path.join(d, ".git")):
        subprocess.run(["git", "init", "-q", "--bare", d], check=True)
    return d


def fetch_sha(repo: str, sha: str, timeout: int = 600):
    """Fetch exactly one commit. Returns (ok, ms, detail)."""
    d = mirror_for(repo)
    env = dict(os.environ, GIT_TERMINAL_PROMPT="0",
               GIT_SSH_COMMAND=os.environ.get(
                   "GIT_SSH_COMMAND", "ssh -o BatchMode=yes -o StrictHostKeyChecking=accept-new"))
    t0 = time.time()
    p = subprocess.run(["git", "-C", d, "fetch", "--depth=1", "--no-tags", repo, sha],
                       capture_output=True, text=True, timeout=timeout, env=env)
    ms = int((time.time() - t0) * 1000)
    if p.returncode != 0:
        return False, ms, (p.stderr or p.stdout).strip()[:300], d
    have = subprocess.run(["git", "-C", d, "cat-file", "-e", f"{sha}^{{commit}}"],
                          capture_output=True).returncode == 0
    if not have:
        return False, ms, "fetch reported success but the commit object is absent", d
    return True, ms, "1 commit", d


def main() -> int:
    os.makedirs(MIRRORS, exist_ok=True)
    rows = pending()
    if not rows:
        print(f"[{NODE}] no pending triggers")
        return 0
    print(f"[{NODE}] {len(rows)} pending trigger(s)")
    now = lambda: time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
    for r in rows:
        rid, repo, sha = r.get("id"), r.get("repo"), r.get("sha")
        if not (rid and repo and sha):
            print(f"  {rid}: malformed row (needs repo+sha) — left pending")
            continue
        try:
            attempts = int(r.get("attempts") or 0)
        except ValueError:
            attempts = 0
        # claim it first: a crash mid-fetch must not leave the row unlocked-looking
        patch(rid, {"status": "fetching", "lease_node": NODE,
                    "lease_until": time.strftime("%Y-%m-%dT%H:%M:%SZ",
                                                 time.gmtime(time.time() + LEASE_S)),
                    "updated_at": now()})
        ok, ms, detail, mirror = fetch_sha(repo, sha)
        if ok:
            patch(rid, {"status": "ready", "fetched_at": now(), "fetch_ms": str(ms),
                        "local_mirror": mirror, "last_error": None,
                        "lease_node": None, "lease_until": None, "updated_at": now()})
            print(f"  {rid} READY  {repo}@{sha[:12]}  {ms}ms")
        else:
            attempts += 1
            status = "failed" if attempts >= MAX_TRY else "pending"
            patch(rid, {"status": status, "attempts": str(attempts), "last_error": detail,
                        "lease_node": None, "lease_until": None, "updated_at": now()})
            print(f"  {rid} {status.upper()} attempt {attempts}/{MAX_TRY}  {detail}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

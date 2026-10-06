#!/usr/bin/env python3
"""Ground truth for the scope work: which fleet repos are PRIVATE, and whether a
repo-scoped token can see a private repo outside its scope.

Anonymous git reads work on PUBLIC repos regardless of the token, so "git ls-remote
of another repo succeeded" is NOT evidence of a leak -- it is evidence the other repo
is public. Denial must be tested against a private repo, and the contrast that matters
is scoped-token vs installation-wide-token on the SAME private repo.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

MANIFEST = Path.home() / ".hermes/secrets/fleet-repo-scope.json"
MINT = Path.home() / ".hermes/scripts/gh-app-token.py"


def mint(agent: str) -> str:
    p = subprocess.run([sys.executable, str(MINT), "token", "--agent", agent],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("mint failed for %s: %s" % (agent, p.stderr.strip()[:200]))
    return p.stdout.strip()


def wide() -> str:
    p = subprocess.run([sys.executable, str(MINT), "token", "totalwindupflightsystems"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("wide mint failed: %s" % p.stderr.strip()[:200])
    return p.stdout.strip()


def can_see(token: str, full: str) -> int:
    p = subprocess.run(["curl", "-s", "-o", "/dev/null", "-w", "%{http_code}",
                        "-H", "Authorization: Bearer " + token, "-H",
                        "Accept: application/vnd.github+json",
                        "https://api.github.com/repos/" + full],
                       capture_output=True, text=True)
    return int(p.stdout.strip() or 0)


def main() -> int:
    agent = sys.argv[1] if len(sys.argv) > 1 else "asce"
    man = json.loads(MANIFEST.read_text(encoding="utf-8"))
    own = man[agent]
    scoped, wide_tok = mint(agent), wide()

    print("agent %s owns %s; its token reaches:" % (agent, own))
    p = subprocess.run(["curl", "-s", "-H", "Authorization: Bearer " + scoped,
                        "-H", "Accept: application/vnd.github+json",
                        "https://api.github.com/installation/repositories?per_page=100"],
                       capture_output=True, text=True)
    d = json.loads(p.stdout)
    print("  %d repo(s): %s" % (d["total_count"], [r["full_name"] for r in d["repositories"]]))

    print("\nprivate repos in the installation, and what each credential sees")
    print("  %-46s %-10s %-12s %s" % ("REPO", "PRIVATE", "scoped tok", "wide tok"))
    privates = 0
    for other, full in sorted(man.items()):
        if other == agent:
            continue
        s = can_see(scoped, full)
        w = can_see(wide_tok, full)
        note = "" if s == 404 else "  <- NOT DENIED"
        if w == 200 and s == 404:
            privates += 1
            note = "  <- scoped token denied, wide token allowed"
        print("  %-46s %-10s %-12s %s%s" % (full, "?", s, w, note))
    print("\n%d repo(s) where the scoped token is denied and the installation-wide token is allowed"
          % privates)
    return 0


if __name__ == "__main__":
    sys.exit(main())

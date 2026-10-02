#!/usr/bin/env python3
"""fleet-gh-scope — per-repo GitHub credential scoping for the cluster agents.

CONTEXT
  Agents hold a GitHub App token. Until now that token was minted with no
  `repositories` narrowing, so EVERY agent token reached all 37 repos in the
  installation (measured: `GET /installation/repositories` -> total_count 37
  from inside agent `asce`). One compromised agent == the whole org's repos.

  The mint-side narrowing was believed broken ("--repos returned 401"). It is
  not broken: with the App installed as `repository_selection: all`, a POST to
  /app/installations/<id>/access_tokens with `{"repositories": ["asce"]}`
  returns a token that reaches exactly that one repo. The earlier failure was a
  scope/lookup problem, and it is now diagnosed in gh-app-token.py:
    * 422 -> the repo name is not in the installation's repo list
             (unknown name, or owner/name typed where a bare name is required),
             NOT a token problem.
    * 401 -> the credential presented was a JWT where an installation token was
             required (or vice-versa), i.e. an endpoint/credential mismatch.

WHAT THIS TOOL DOES
  One source of truth for "which repo is an agent allowed to touch", then four
  verbs built on it:

    repos                  show the agent -> owner/repo manifest
    mint <agent>           print a repo-scoped token (1h, in memory only)
    export <agent>         print `export GH_TOKEN=<tok>` for shell injection
    inject <agent> <cmd>   run <cmd> with the scoped token in the environment
    home <agent>           FALLBACK: install the scoped token as ~/.gh-token
    check <agent>          prove, ON the agent, that its credential reaches
                           exactly its own repo and nothing else
    audit                  all agents: scope + on-agent reach (blast radius)

  The resting state is INJECTION (per dispatch, in-memory, 1h). `home` exists
  only for a human at an agent shell between dispatches; it writes a scoped
  token too, never an installation-wide one, so the blast radius stays 1 repo.

MANIFEST
  ~/.hermes/secrets/fleet-repo-scope.json   {"asce": "totalwindupflightsystems/asce", ...}
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

HOME = Path.home()
MANIFEST = HOME / ".hermes/secrets/fleet-repo-scope.json"
MINT = HOME / ".hermes/scripts/gh-app-token.py"
BUNKER = HOME / ".local/bin/bunker"
AGENTS_FILE = Path("/home/kara/crier-fleet/fleet_agents.json")

# Read-only endpoints used to prove scope.
API = "https://api.github.com"


def load_manifest() -> dict[str, str]:
    try:
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    except FileNotFoundError:
        sys.exit("missing manifest %s" % MANIFEST)


def boxes() -> dict[str, str]:
    try:
        return json.loads(AGENTS_FILE.read_text(encoding="utf-8"))
    except OSError:
        return {}


def split(full: str) -> tuple[str, str]:
    owner, _, name = full.partition("/")
    if not name:
        sys.exit("bad manifest entry %r (want owner/name)" % full)
    return owner, name


def mint_scoped(agent: str) -> str:
    """Mint a 1h installation token narrowed to the agent's repo. Token on stdout only."""
    full = load_manifest().get(agent)
    if not full:
        sys.exit("agent %r is not in the manifest (%s)" % (agent, MANIFEST))
    owner, name = split(full)
    proc = subprocess.run([sys.executable, str(MINT), "token", owner, "--repos", name],
                          capture_output=True, text=True)
    if proc.returncode != 0:
        sys.exit("mint failed for %s (%s): %s" % (agent, full, (proc.stderr or proc.stdout).strip()[:400]))
    token = proc.stdout.strip()
    if not token or " " in token:
        sys.exit("mint for %s produced no usable token: %r" % (agent, token[:80]))
    return token


def reach(token: str) -> list[str]:
    """The exact repo list a token can see, straight from GitHub (not our bookkeeping)."""
    out: list[str] = []
    page = 1
    while True:
        req = f"{API}/installation/repositories?per_page=100&page={page}"
        r = subprocess.run(["curl", "-s", "-H", "Authorization: Bearer " + token,
                            "-H", "Accept: application/vnd.github+json", req],
                           capture_output=True, text=True)
        try:
            d = json.loads(r.stdout)
        except json.JSONDecodeError:
            sys.exit("bad response from GitHub: %s" % r.stdout[:200])
        repos = d.get("repositories") or []
        out += [x["full_name"] for x in repos]
        if len(repos) < 100:
            return out
        page += 1


def agent_ssh(agent: str) -> list[str]:
    """ssh argv for the agent, host resolved from bunker (never from a config IP)."""
    box = boxes().get(agent)
    if not box:
        sys.exit("no box recorded for agent %r in %s" % (agent, AGENTS_FILE))
    info = subprocess.run([str(BUNKER), "info", "--server", box, agent],
                          capture_output=True, text=True)
    host = ""
    for line in (info.stdout or "").splitlines():
        if "SSHFS Mount:" in line:
            for part in line.split():
                if part.startswith("bunker-%s@" % agent):
                    host = part.split("@", 1)[1].split(":", 1)[0]   # strip the path after host
    if not host:
        sys.exit("could not resolve host for %s from `bunker info`:\n%s" % (agent, info.stdout[:400]))
    return ["ssh", "-o", "StrictHostKeyChecking=no", "-o", "UserKnownHostsFile=/dev/null",
            "-o", "LogLevel=ERROR", "-i", str(HOME / (".bunker/keys/%s" % agent)),
            "bunker-%s@%s" % (agent, host)]


def on_agent(agent: str, script: str) -> tuple[int, str]:
    p = subprocess.run(agent_ssh(agent) + [script], capture_output=True, text=True, timeout=120)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


# ---------------------------------------------------------------- verbs

def v_repos(a) -> int:
    man = load_manifest()
    bx = boxes()
    print("%-22s %-16s %s" % ("AGENT", "BOX", "SCOPED REPO"))
    for agent in sorted(man, key=lambda x: (bx.get(x, "?"), x)):
        print("%-22s %-16s %s" % (agent, bx.get(agent, "?"), man[agent]))
    print("\n%d agents, %d repos in manifest" % (len(man), len(man)))
    return 0


def v_mint(a) -> int:
    tok = mint_scoped(a.agent)
    if a.json:
        print(json.dumps({"agent": a.agent, "repo": load_manifest()[a.agent], "token": tok}))
    else:
        print(tok)
    return 0


def v_export(a) -> int:
    print("export GH_TOKEN=%s" % mint_scoped(a.agent))
    return 0


def v_inject(a) -> int:
    env = dict(os.environ)
    env["GH_TOKEN"] = mint_scoped(a.agent)
    env["GITHUB_TOKEN"] = env["GH_TOKEN"]
    return subprocess.run(a.cmd, shell=True, env=env).returncode


def v_home(a) -> int:
    """Fallback path: scoped token as ~/.gh-token (0600). Never installation-wide."""
    tok = mint_scoped(a.agent)
    want = load_manifest()[a.agent]
    script = (
        "umask 077; printf '%%s' %s > ~/.gh-token && chmod 600 ~/.gh-token && "
        "stat -c '%%a %%U %%n' ~/.gh-token" % _sq(tok)
    )
    rc, out = on_agent(a.agent, script)
    print("%s: %s" % (a.agent, out.strip()))
    if rc != 0:
        return rc
    # prove it: the token we just installed must reach exactly this repo
    rc2, out2 = on_agent(a.agent, "curl -s -H \"Authorization: Bearer $(cat ~/.gh-token)\" "
                                  "-H 'Accept: application/vnd.github+json' "
                                  "'" + API + "/installation/repositories?per_page=100'")
    try:
        n = json.loads(out2[out2.find("{"):])["total_count"]
    except Exception:  # noqa: BLE001
        n = "?"
    ok = (n == 1)
    print("  home token reach: %s repo(s) -> %s (want %s)" % (n, "OK" if ok else "STILL TOO WIDE", want))
    return 0 if ok else 1


def _wide_token() -> str:
    """Installation-wide token (the thing we are REMOVING). Used only to pick a
    denial target, never handed to an agent."""
    p = subprocess.run([sys.executable, str(MINT), "token", "totalwindupflightsystems"],
                       capture_output=True, text=True)
    if p.returncode != 0:
        sys.exit("wide mint failed: %s" % p.stderr.strip()[:200])
    return p.stdout.strip()


def _repo_meta(token: str, full: str) -> dict | None:
    p = subprocess.run(["curl", "-s", "-H", "Authorization: Bearer " + token,
                        "-H", "Accept: application/vnd.github+json",
                        API + "/repos/" + full], capture_output=True, text=True)
    try:
        d = json.loads(p.stdout)
    except json.JSONDecodeError:
        return None
    return d if "full_name" in d else None


def private_denial_target(agent: str) -> str | None:
    """A PRIVATE repo the wide token can see and a scoped agent token must NOT.

    Anonymous git/API reads work on public repos whatever the token, so only a
    private repo can show a real denial.
    """
    wt = _wide_token()
    for other, full in sorted(load_manifest().items()):
        if other == agent:
            continue
        m = _repo_meta(wt, full)
        if m and m.get("private"):
            return full
    return None


def v_check(a) -> int:
    """Prove, ON the agent, that the dispatch carrier FLEET_GH_TOKEN is scoped to one repo."""
    tok = mint_scoped(a.agent)
    own = load_manifest()[a.agent]
    target = private_denial_target(a.agent)
    if target is None:
        print("no private repo in the installation to test denial against — "
              "only the reach count is provable")
        target = own
    script = (
        "export PATH=$HOME/.local/bin:$PATH; "
        "export FLEET_GH_TOKEN=" + _sq(tok) + "; "
        + "echo reach=$(gh api installation/repositories --jq '.repositories[].full_name' 2>/dev/null | wc -l); "
        + "echo own=$(git ls-remote https://github.com/" + own + ".git HEAD >/dev/null 2>&1 && echo OK || echo FAIL); "
        + "echo other=$(git ls-remote https://github.com/" + target + ".git HEAD >/dev/null 2>&1 && echo LEAK || echo denied)"
    )
    rc, out = on_agent(a.agent, script)
    print("agent %s (owns %s, denial target %s):" % (a.agent, own, target))
    print("  " + out.strip().replace("\n", "\n  "))
    good = ("reach=1" in out) and ("own=OK" in out) and ("other=denied" in out)
    print("  VERDICT: %s" % ("SCOPED" if good else "** NOT SCOPED **"))
    return 0 if good else 1


def v_audit(a) -> int:
    man = load_manifest()
    bx = boxes()
    rows, bad = [], 0
    for agent in sorted(man):
        owner, name = split(man[agent])
        try:
            tok = mint_scoped(agent)
            r = reach(tok)
        except SystemExit as exc:
            rows.append({"agent": agent, "box": bx.get(agent, "?"), "repo": man[agent],
                         "covered": False, "reach": None, "why": str(exc)[:120]})
            bad += 1
            continue
        other = _other_repo(agent)
        own_ok = man[agent] in r
        wide = len(r) > 1
        rows.append({"agent": agent, "box": bx.get(agent, "?"), "repo": man[agent],
                     "covered": own_ok, "reach": len(r),
                     "leaks": [x for x in r if x != man[agent]],
                     "why": ("" if own_ok and not wide else
                             ("reach %d repos" % len(r) if wide else "own repo not reachable"))})
        if wide or not own_ok:
            bad += 1
    if a.json:
        print(json.dumps({"rows": rows, "unscoped": bad}, indent=2))
        return 1 if bad else 0
    print("%-22s %-16s %-40s %s" % ("AGENT", "BOX", "SCOPED REPO", "TOKEN REACH"))
    for r in rows:
        label = "scoped (1)" if r["reach"] == 1 and r["covered"] else (
            "** %s **" % r["why"] if r["reach"] is not None else "uncovered: %s" % r["why"][:28])
        print("%-22s %-16s %-40s %s" % (r["agent"], r["box"], r["repo"], label))
    print("\n%d/%d agents scoped to exactly one repo" % (len(rows) - bad, len(rows)))
    return 1 if bad else 0


def dispatch_env(agent: str) -> dict:
    """Env to inject for one dispatch: a fresh, repo-scoped, 1-hour token.

    This is the RESTING STATE for agent credentials -- a short-lived token minted
    control-side at dispatch time and handed to the session in its environment,
    never written to a home directory. Never raises: a mint failure must not
    stop the work, so it is logged and the dispatch proceeds without a token.

    THE VARIABLE NAME MATTERS. Hermes scrubs GH_TOKEN/GITHUB_TOKEN out of every
    terminal child (they are on the provider/tool blocklist alongside the LLM API
    keys), so injecting GH_TOKEN works for the process and dies one level down --
    measured on agent asce: FLEET_GH_TOKEN survived the tool boundary, GH_TOKEN
    did not. FLEET_GH_TOKEN is therefore the carrier, and `fleet-git-credential`
    (installed by `setup`) hands it to git in the shape git expects.
    """
    try:
        tok = mint_scoped(agent)
    except SystemExit as exc:
        sys.stderr.write("fleet-gh-scope: no scoped token for %s (%s) -- "
                         "dispatching without FLEET_GH_TOKEN\n" % (agent, exc))
        return {}
    return {"FLEET_GH_TOKEN": tok}


GIT_CREDENTIAL_HELPER = """#!/bin/sh
# git credential helper backed by the per-dispatch scoped GitHub token.
# Written by fleet-gh-scope.py; reads FLEET_GH_TOKEN (never GH_TOKEN, which the
# Hermes terminal scrub removes from tool children).
#   git credential fill  -> sends action=get on stdin
case "$1" in
  get)
    [ -n "$FLEET_GH_TOKEN" ] || exit 0
    printf 'username=x-access-token\\npassword=%s\\n' "$FLEET_GH_TOKEN"
    ;;
esac
exit 0
"""

GH_WRAPPER = """#!/bin/sh
# gh wrapper: lifts the fleet's scoped token into the variable gh understands.
# Hermes strips GH_TOKEN from terminal children, so the per-dispatch token arrives as
# FLEET_GH_TOKEN. Fallback (interactive shell between dispatches): the agent's own
# ~/.gh-token, which is ALSO repo-scoped -- never an installation-wide token.
if [ -z "${GH_TOKEN:-}" ]; then
  if [ -n "${FLEET_GH_TOKEN:-}" ]; then
    GH_TOKEN="$FLEET_GH_TOKEN"
  elif [ -r "$HOME/.gh-token" ]; then
    GH_TOKEN="$(cat "$HOME/.gh-token")"
  fi
  [ -n "${GH_TOKEN:-}" ] && export GH_TOKEN
fi
exec "$HOME/.local/bin/.gh-real" "$@"
"""


def v_setup(a) -> int:
    """One-time, idempotent agent-side plumbing for the injected token.

    Installs the git credential helper and a gh wrapper that understand
    FLEET_GH_TOKEN, then proves git works with a freshly minted scoped token.
    """
    agent = a.agent
    own = load_manifest()[agent]
    tok = mint_scoped(agent)
    other = private_denial_target(agent) or own
    script = _setup_script(tok, own, other)
    rc, out = on_agent(agent, script)
    print("agent %s (denial target %s):" % (agent, other))
    print("  " + out.strip().replace("\n", "\n  "))
    return 0 if rc == 0 and "PROOF own:  OK" in out and "PROOF other:denied" in out else 1


def _setup_script(tok: str, own: str, other: str) -> str:
    return "\n".join([
        "set -e",
        "umask 077",
        "mkdir -p ~/.local/bin",
        "cat > ~/.local/bin/fleet-git-credential <<'CREDEOF'\n" + GIT_CREDENTIAL_HELPER + "CREDEOF",
        "chmod 700 ~/.local/bin/fleet-git-credential",
        # gh wrapper: only wrap once, and only a real binary (never re-wrap the shim)
        "if [ -f ~/.local/bin/gh ] && [ ! -f ~/.local/bin/.gh-real ]; then",
        "  mv ~/.local/bin/gh ~/.local/bin/.gh-real",
        "fi",
        "if [ -f ~/.local/bin/.gh-real ]; then",
        "  cat > ~/.local/bin/gh <<'GHEOF'\n" + GH_WRAPPER + "GHEOF",
        "  chmod 755 ~/.local/bin/gh",
        "fi",
        # git: the scoped helper first, the pre-existing gh helper kept as a fallback
        "git config --global --unset-all 'credential.https://github.com.helper' || true",
        "git config --global --add 'credential.https://github.com.helper' "
        "'!'\"$HOME\"'/.local/bin/fleet-git-credential'",
        "git config --global --add 'credential.https://github.com.helper' "
        "'!'\"$HOME\"'/.local/bin/gh auth git-credential'",
        "export FLEET_GH_TOKEN=" + _sq(tok),
        "echo 'helper: '$(git config --global --get-all 'credential.https://github.com.helper' | tr '\\n' '|')",
        "echo 'gh:     '$(gh --version 2>/dev/null | head -1)",
        "echo 'reach:  '$(gh api installation/repositories --jq '.repositories[].full_name' 2>&1 | tr '\\n' ' ')",
        "echo 'PROOF own:  '$(git ls-remote https://github.com/%s.git HEAD >/dev/null 2>&1 && echo OK || echo FAIL)" % own,
        "echo 'PROOF other:'$(git ls-remote https://github.com/%s.git HEAD >/dev/null 2>&1 && echo LEAK || echo denied)" % other,
    ])


def env_prefix(add: dict) -> str:
    """Shell prefix for `sh -c` that sets variables, each safely quoted."""
    import shlex
    return "".join("%s=%s " % (k, shlex.quote(v)) for k, v in sorted(add.items()))


def v_dispatch_env(a) -> int:
    """What the dispatcher will inject for this agent, redacted unless --raw."""
    add = dispatch_env(a.agent)
    if not add:
        print("no token (see warning above)")
        return 1
    if a.raw:
        print(env_prefix(add))
    else:
        print("would inject: %s (token %d chars, expires within 60 min)"
              % (", ".join(sorted(add)), len(add["GH_TOKEN"])))
    return 0


def _other_repo(agent: str) -> str:
    """A different repo in the installation, to prove the token CANNOT reach it."""
    for other, full in sorted(load_manifest().items()):
        if other != agent:
            return full
    return "totalwindupflightsystems/hermes-agent"


def _sq(s: str) -> str:
    import shlex
    return shlex.quote(s)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)

    sub.add_parser("repos").set_defaults(fn=v_repos)
    p = sub.add_parser("mint"); p.add_argument("agent"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=v_mint)
    p = sub.add_parser("export"); p.add_argument("agent"); p.set_defaults(fn=v_export)
    p = sub.add_parser("inject"); p.add_argument("agent"); p.add_argument("cmd"); p.set_defaults(fn=v_inject)
    p = sub.add_parser("home"); p.add_argument("agent"); p.set_defaults(fn=v_home)
    p = sub.add_parser("setup"); p.add_argument("agent"); p.set_defaults(fn=v_setup)
    p = sub.add_parser("check"); p.add_argument("agent"); p.set_defaults(fn=v_check)
    p = sub.add_parser("dispatch-env"); p.add_argument("agent"); p.add_argument("--raw", action="store_true"); p.set_defaults(fn=v_dispatch_env)
    p = sub.add_parser("audit"); p.add_argument("--json", action="store_true"); p.set_defaults(fn=v_audit)

    a = ap.parse_args()
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())

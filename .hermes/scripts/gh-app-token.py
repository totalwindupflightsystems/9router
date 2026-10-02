#!/usr/bin/env python3
"""Mint short-lived GitHub App credentials for the coding-hermes fleet.

WHY THIS EXISTS
  A personal access token cannot be created by anything except the GitHub web UI
  (no API), and it lives ~90 days as a durable secret on every machine you paste
  it into -- including machines that run agent-authored code. This App replaces
  that: we hold ONE private key centrally and mint per-repo tokens on demand.

WHY THE APP BEATS A PAT
  * Nothing durable on the worker: the token dies within the hour.
  * Scope is per-repo and per-permission, chosen at mint time.
  * Revocation is one click; there is no 90-day reissue chore.
  * The App is the identity, so commits/pushes are attributable to it.

USAGE
  gh-app-token.py list                          # installations (which owners installed it)
  gh-app-token.py token <owner>                 # mint a token for all repos it can reach
  gh-app-token.py token <owner> --repos a,b     # narrow to specific repos
  gh-app-token.py token --agent asce            # narrow to that agent's repo (fleet manifest)
  gh-app-token.py token --agent asce --export   # `export GH_TOKEN=...` for shell injection
  gh-app-token.py token <owner> --permissions contents=write
  gh-app-token.py whoami <owner>                # mint + prove the token works
  gh-app-token.py install-url                   # where the owner installs it

  NOTE ON SCOPE. Requesting --repos is not an error path: with the installation
  set to `repository_selection: all`, the returned token reaches ONLY the listed
  repos (proved with GET /installation/repositories). A request naming a repo the
  installation cannot see is answered 422, not 401 -- see HINT below.

CREDENTIALS (never printed):
  ~/.hermes/secrets/gh-app.json   app id, slug, owner
  ~/.hermes/secrets/gh-app.pem    the App private key (RS256)
  ~/.hermes/secrets/fleet-repo-scope.json   agent -> owner/repo (for --agent)
"""
import argparse
import json
import os
import sys
import time
import urllib.error
import urllib.request

SEC = os.environ.get("GH_APP_SECRETS", os.path.expanduser("~/.hermes/secrets"))
JSON_PATH = os.path.join(SEC, "gh-app.json")
PEM_PATH = os.path.join(SEC, "gh-app.pem")
SCOPE_PATH = os.path.join(SEC, "fleet-repo-scope.json")
API = "https://api.github.com"

# HTTP status -> what it actually means when you are minting fleet credentials.
# Recorded because a repo-scoped mint was once written off as "401, broken":
# it was never an auth failure, and the two are not interchangeable.
HINT = {
    401: "the credential was rejected: an App JWT is required on /app/* endpoints and an "
         "installation token on /installation/* endpoints. Using one where the other belongs "
         "is the classic 401 here -- it does NOT mean the mint is unsupported.",
    403: "authenticated but not permitted: the App lacks the permission the call needs, or the "
         "installation does not cover this resource.",
    404: "not found for THIS credential: an installation token scoped away from a repo sees 404, "
         "not 403. If a repo lookup 404s, check the token's scope before its spelling.",
    422: "the request body names something the installation cannot see -- for `--repos` that "
         "means a name that is not in this installation's repo list (bare repo NAME required, "
         "not owner/name). This is the real cause of most 'scoped mint is broken' reports.",
}


def _req(url, token, method="GET", body=None):
    data = json.dumps(body).encode() if body is not None else None
    r = urllib.request.Request(url, data=data, method=method)
    r.add_header("Authorization", "Bearer %s" % token)
    r.add_header("Accept", "application/vnd.github+json")
    r.add_header("X-GitHub-Api-Version", "2022-11-28")
    if data:
        r.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(r, timeout=30) as fh:
            return json.loads(fh.read().decode())
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:300]
        sys.exit("HTTP %s on %s\n  %s\n  detail: %s" % (e.code, url, HINT.get(e.code, ""), detail))



def _load():
    if not (os.path.exists(JSON_PATH) and os.path.exists(PEM_PATH)):
        sys.exit("missing %s / %s -- register the app via gh-app-manifest.py first"
                 % (JSON_PATH, PEM_PATH))
    meta = json.load(open(JSON_PATH))
    return meta, open(PEM_PATH).read()


def _jwt(meta, pem):
    """App JWT: iss=app_id, <=10 min, RS256. Proves we hold the private key."""
    import jwt  # PyJWT
    now = int(time.time())
    return jwt.encode({"iat": now - 60, "exp": now + 540, "iss": str(meta["id"])},
                      pem, algorithm="RS256")


def installations(meta, pem):
    return _req(API + "/app/installations", _jwt(meta, pem))


def pick_installation(insts, owner):
    for i in insts:
        if i["account"]["login"].lower() == owner.lower():
            return i
    sys.exit("no installation for '%s'. Installed owners: %s\nInstall it: %s"
             % (owner, ", ".join(i["account"]["login"] for i in insts) or "(none)",
                "https://github.com/apps/%s/installations/new" % _load()[0]["slug"]))


def manifest_scope(agent):
    """agent -> (owner, repo_name) from the fleet scope manifest."""
    try:
        man = json.load(open(SCOPE_PATH, encoding="utf-8"))
    except OSError:
        sys.exit("--agent needs %s (agent -> owner/repo)" % SCOPE_PATH)
    full = man.get(agent)
    if not full:
        sys.exit("agent %r is not in %s; known: %s"
                 % (agent, SCOPE_PATH, ", ".join(sorted(man))))
    owner, _, name = full.partition("/")
    return owner, name


def installation_repo_names(inst, meta, pem):
    """The exact repo NAMES this installation can see (paginated)."""
    tok = _req("%s/app/installations/%s/access_tokens" % (API, inst["id"]),
               _jwt(meta, pem), method="POST", body={})["token"]
    names, page = [], 1
    while True:
        d = _req("%s/installation/repositories?per_page=100&page=%d" % (API, page), tok)
        repos = d.get("repositories", [])
        names += [r["name"] for r in repos]
        if len(repos) < 100:
            return names
        page += 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["list", "token", "whoami", "install-url"])
    ap.add_argument("owner", nargs="?")
    ap.add_argument("--agent", help="fleet agent name; resolves owner+repo from the scope manifest")
    ap.add_argument("--repos", help="comma-separated repo names to scope the token to")
    ap.add_argument("--permissions", help="e.g. contents=write,pull_requests=write")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    ap.add_argument("--export", action="store_true", help="emit `export GH_TOKEN=<tok>`")
    a = ap.parse_args()

    meta, pem = _load()

    if a.cmd == "install-url":
        print("https://github.com/apps/%s/installations/new" % meta["slug"])
        return

    insts = installations(meta, pem)

    if a.cmd == "list":
        if not insts:
            print("App '%s' (id %s) is installed nowhere yet.\nInstall: "
                  "https://github.com/apps/%s/installations/new"
                  % (meta["slug"], meta["id"], meta["slug"]))
            return
        print("App '%s' (id %s) installations:" % (meta["slug"], meta["id"]))
        for i in insts:
            print("  %-24s %s  repos=%s  id=%s"
                  % (i["account"]["login"], i["account"]["type"],
                     i.get("repository_selection"), i["id"]))
        return

    if a.agent:
        owner, name = manifest_scope(a.agent)
        if a.owner and a.owner.lower() != owner.lower():
            sys.exit("--owner %s contradicts the manifest for %s (%s/%s)"
                     % (a.owner, a.agent, owner, name))
        a.owner, a.repos = owner, name

    if not a.owner:
        sys.exit("'%s' needs an owner (e.g. totalwindupflightsystems) or --agent <name>" % a.cmd)

    inst = pick_installation(insts, a.owner)
    body = {}
    if a.repos:
        want = [r.strip() for r in a.repos.split(",") if r.strip()]
        # Pre-flight: a name the installation cannot see is a 422 with a useless
        # message, so name the offender here instead.
        known = installation_repo_names(inst, meta, pem)
        unknown = [r for r in want if r not in known]
        if unknown:
            near = {u: [k for k in known if u.lower() in k.lower()][:3] for u in unknown}
            sys.exit("not in installation '%s': %s\n  bare repo names required (not owner/name).\n"
                     "  near matches: %s\n  installation holds %d repos"
                     % (a.owner, ", ".join(unknown), near, len(known)))
        body["repositories"] = want
    if a.permissions:
        body["permissions"] = dict(
            p.split("=", 1) for p in a.permissions.split(",") if "=" in p
        )
    tok = _req("%s/app/installations/%s/access_tokens" % (API, inst["id"]),
               _jwt(meta, pem), method="POST", body=body)

    if a.cmd == "whoami":
        who = _req(API + "/installation/repositories", tok["token"])
        print("token works: %d repo(s) reachable as '%s'"
              % (len(who.get("repositories", [])), a.owner))
        print("expires: %s" % tok["expires_at"])
        return

    if a.json:
        print(json.dumps({"token": tok["token"], "expires_at": tok["expires_at"],
                          "repos": [r["full_name"] for r in
                                    _req(API + "/installation/repositories",
                                         tok["token"]).get("repositories", [])]}))
    elif a.export:
        print("export GH_TOKEN=%s" % tok["token"])
    else:
        # Default: token on stdout ONLY, so `$(gh-app-token.py token owner --repos x)`
        # feeds a credential without it ever reaching a log or the chat.
        print(tok["token"])


if __name__ == "__main__":
    main()

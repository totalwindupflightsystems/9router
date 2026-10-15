# Ephemeral install leg — step-by-step procedure (0-5)

Moved out of SKILL.md (which keeps the contract: mandatory leg, never silently pass, record format, skip semantics). Follow these steps exactly; the pitfalls file `references/ephemeral-install-leg.md` carries the deep pitfall set.

### 0. Discover the host + check tools (self-contained — no session context assumed)

```bash
# 1) Resolve the host from ~/.ssh/config — aliases exist: bunker3 / bunker-las-03 / bunker3-root
grep -A6 -E '^Host .*bunker-las-03' ~/.ssh/config      # HostName is the tailnet IP (currently 100.69.3.13)
ip=$(ssh -G bunker3 | awk '/^hostname /{print $2}')    # resolve fresh; never trust a hardcoded IP
# 2) Tools to check locally
for t in ssh docker bunker; do command -v "$t" >/dev/null && echo "$t: ok" || echo "$t: MISSING"; done
bunker --version     # need >= 0.1.3 (has --server + the 300s spawn fix); older → rebuild: cd ~/bunker && make build
```
Missing `bunker` (or too old) with no way to build it = SKIPPED-install-bunker (below), never a guess.

### 1. Reachability probe; register the server if the CLI doesn't know it

```bash
timeout 15 ssh -o BatchMode=yes -o ConnectTimeout=6 bunker3 \
  'echo HOST_OK; systemctl is-active bunkerd; docker --version | head -1'
# expect: HOST_OK / active / Docker version 26.x — bunkerd ACTIVE is required to spawn
```
- Host unreachable or bunkerd inactive → probe a sibling bunker host (see
  SKILL.md for the sibling list) before filing `SKIPPED-install-bunker`; only a fleet-wide outage
  justifies the skip. **Never silently pass the install check.** When an
  earlier tick already proved the leg on the CURRENT code HEAD (grep the
  project's git log for an install-leg commit and
  `.coding-hermes/dogfood-log.md`), inherit it: cite the proof commit,
  agent/server name, and measured numbers in the report instead of re-spawning
  an ephemeral agent for unchanged code. Inherited proof is evidence-backed
  reuse, never a silent pass — spawn fresh only when the code HEAD, install
  docs, or bunker host actually changed. Cite it as an EXPLICIT skip in the
  report, naming what the prior run established and why this run adds nothing
  — an inherited proof stated as a bare pass reads as a skipped leg.
  Resolve the product repo from the scheduler DB when the prompt's product
  path does not exist (`projects` row: `repo_url`/`deliver`, scheme-stripped;
  cross-check a same-family sibling lane) — a lane workdir with a live board
  can sit next to an absent prompt path and still be the right lane.
- Before declaring a live daemon unreachable, check WHERE bunkerd binds
  (`ss -tlnp` on the box): a daemon bound only to its tailnet IP answers
  nothing to on-box `curl localhost:PORT` while perfectly healthy — connect
  to `tailscale ip -4`, not localhost or the public interface.
- When a captured connect token fails as `invalid token`, strip YAML quotes
  (`tr -d '"'`) before concluding the credential is wrong — a `token: "..."`
  value captured with its quotes mimics an auth failure that is only formatting.
- If `bunker list --server <name>` says `server not found in config`, register it.
  The bunkerd token lives in the box's own config (read over root SSH; keep it OUT of notes, findings,
  repos, and DuckBrain — it belongs only in `/etc/bunkerd/config.yaml` and `~/.bunker/config.yaml`):

```bash
BUNKER_TOKEN="$(ssh bunker3-root 'grep -oP "(?<=token: ).*" /etc/bunkerd/config.yaml' | head -1)" \
  bunker connect "http://$ip:19090" --name bunker-las-03
unset BUNKER_TOKEN
```
No token obtainable → SKIPPED-install-bunker (`no bunker credential`).

### 2. Spin an ephemeral agent (short TTL — it IS throwaway)

```bash
out=$(bunker spawn --server bunker-las-03 --ttl 2h --agent-id df-<proj>-<date> 2>&1)
# Named ids: parse the "Agent created: <id>" line FIRST — the keys-path grep below
# only matches bare hex ids and silently yields empty (reads as a failed spawn) when
# --agent-id carries hyphens, even though the spawn succeeded.
agent=$(echo "$out" | sed -n 's/^Agent created: //p' | head -1)
[ -n "$agent" ] || agent=$(echo "$out" | grep -oP 'keys/\K[a-f0-9]+' | head -1)   # empty = spawn failed — capture $out as evidence
```
Identity: user `bunker-<agent>`, ssh key `~/.config/bunker/keys/<agent>` (older builds use `~/.bunker/keys/`), IP = server tailnet IP, rootless
docker socket `/run/user/<uid>/docker.sock` (uid via `id -u` over ssh). Write `agent=<id> ip=<ip>` into
your scratch notes NOW so the destroy step (5) always runs. Fresh-agent spawn installs rootless docker
(60-90s — the CLI waits up to 300s). Spawn failure → retry ONCE before attributing anything to the
host (spawn-stage errors like `slice-limits: containment landing did not converge` can be transient
on an otherwise-healthy box); a second consecutive failure → clean up any half-spawned user per the
`bunker-agent-isolation` skill, record the failure, and continue.

### 3. Clone the project repo INSIDE the bunker (existing access only)

```bash
ssh -i ~/.bunker/keys/$agent -o IdentitiesOnly=yes -o StrictHostKeyChecking=no \
  "bunker-$agent@$ip" "git clone <origin-url-from-README-AGENTS> ~/app && git -C ~/app rev-parse --short HEAD"
```
- Use the project's OWN documented origin URL — a successful clone proves a fresh user can fetch the code.
- Private repo with no credential in the agent? Stream the tree with existing access instead (tar-over-ssh
  from the control-host checkout; changes nothing on the repo):
  `tar -C <repo> --exclude=.git --exclude=node_modules --exclude=.next -cf - . | ssh -i ~/.bunker/keys/$agent ... "mkdir -p ~/app && tar -C ~/app -xf -"`
  - Run the stream FROM the control host as one pipeline — do not wrap it inside an outer `ssh` session
    to the agent: the nested ssh then runs ON the agent, reads the key file as the REMOTE user, and
    every identity is denied even though the identical command works from the control host.
  - A tar-stream snapshot is NOT a git repo, so tests that shell out to git (repo-toplevel probes) fail
    there; `git init && git add -A && git commit` inside ~/app before running the suite, and treat any
    pre-init failure of a git-dependent test as a leg artifact, not a product defect.
  - When the fresh box has no usable toolchain, the tar-transfer is also the SOURCE-delivery fallback:
    exclude `node_modules`/`.next`/build output in the tar so the fresh `npm install`/build still runs
    for real — only a tar WITHOUT its dependency tree counts as an install proof.
- **Rule (verbatim): do not modify repo visibility/permissions/clone settings.** If neither path works,
  record the failure as a finding — do NOT make the repo public, add the agent as a collaborator, or
  generate/persist new tokens to enable the clone.
- Prefer staging THROUGH the bunker CLI over raw scp to the server IP: a literal-IP
  scp/ssh command string trips the sandbox raw-IP URL scan (approval pend on every
  retry), and a fleet ssh alias does not name the agent — `scp ... <host-alias>:~/x`
  lands in the HOST account's home, not the agent's. After any alias-based transfer,
  verify identity on the receiving side (`ssh <alias> 'whoami; hostname'`) and grep
  the alias block in ~/.ssh/config — the alias's User/HostName pair, not the agent
  id, decides where the file lands.
- Working staging recipe for a bunker agent (destination is `<agent-id>:<relative-path>`
  — an explicit `$HOME/...` remote target fails, and mutating verbs never fall back to
  the `bunker use` default, nor accept the agent id in the env var, so the var carries
  the SERVER name only):
  `BUNKER_SESSION_TARGET=<server> bunker cp <local> <agent-id>:app.tar.gz` then
  `BUNKER_SESSION_TARGET=<server> bunker exec <agent-id> -- bash -c 'mkdir -p ~/app && tar -C ~/app -xzf app.tar.gz'`.
  exec does not forward a piped stdin (a staged-via-stdin file arrives empty) — always
  stage a real file with cp and run it by path under `bash -c`.

### 4. Run the project's documented install path from scratch

First check the fresh box for toolchains the docs never mention
(`which go node npm cargo pip`): a documented install path that assumes a
toolchain absent from a bare Debian user is a docs finding — record the
absence, then hand-install it into `$HOME` (user-space tarball, no sudo) so
the rest of the documented path can still be exercised honestly. The silent
assumption is the finding; do not skip the leg over it.
Time the TOOLCHAIN download separately from the project install
(`install_seconds` = the documented-path time only): a bare box spends most of
the leg downloading node/go itself, and one number conflating both reads as a
slow install in the log and a PERF row that never reproduces on a toolchained
box. A toolchain tarball into `$HOME` in the same command as the install is
fine — print the two timers on separate lines.

Before blaming a connection failure on the product, preflight the agent's
NETWORK: `curl` the same endpoint from the agent AND from the control host.
A URL that resolves on the control host can be unreachable from a fresh fleet
box (no tailnet route, container DNS without systemd-resolved) — a mismatch
is a leg-environment note, not a product finding. Route the leg's queue/DB
calls over the tailnet IP of the control host, never an off-tailnet address.

Secrets the leg must pass (a queue API key, a token): stage them as a small
runner script — write the script with a `$1`-substituted placeholder, `scp`
it to the agent, execute by path passing the secret as the first argument.
Inlining `SECRET=value cmd` into the ssh command string triggers sandbox
approval pends on every retry (raw-IP + pipe-to-interpreter patterns) and
the secret sits in shell history; the staged script clears in one approval
and the secret never echoes into tool output.

```bash
ssh -i ~/.bunker/keys/$agent -o IdentitiesOnly=yes "bunker-$agent@$ip" \
  "cd ~/app && t0=\$(date +%s) && <documented install: make setup | ./install.sh | docker compose up -d --build | npm ci && npm run build | pip install -e . ...> && echo INSTALL_SECONDS=\$(( \$(date +%s) - t0 ))"
```
- Run EXACTLY the documented commands (README/Makefile/docker-compose) — the docs are what is being
  tested; anything you had to guess or add is a friction finding.
- The agent is a bare Debian user: non-root (`sudo` needs a password), no docker-compose plugin by
  default (a documented compose path may require installing it into `~/.docker/cli-plugins`), no
  project toolchains preinstalled. Deps the install docs silently assumed = docs findings.
- **A failing exit that names the expected blocker is a PASS, not a failure.** If the documented
  smoke is `--dry-run` (or equivalent) and it exits non-zero with the exact intended error
  (missing user-supplied asset like a ROM/license, actionable fix message), the validation
  contract works on a clean machine — record it as the smoke result with the error verbatim.

### 5. Run its smoke check, then destroy — ALWAYS

- Run the LONG build inside the ssh command with a `timeout` wrapper sized above the expected build time (Go/React from a cold module cache can take several minutes) — an unterminated ssh that outlives the local tool call loses its output even though the build succeeded on the agent; re-poll via a short ssh that checks for the build artifact instead.
- Do not parse `make build`'s progress noise for success — run the binary's version/help verb afterward and require it to print; for binaries with a `-version`, assert it stamps the cloned commit (`commit=<rev>`) before calling the leg a PASS. If `-version` is not documented in the binary's usage text, `--help` output IS the smoke — a full usage banner proves the artifact executes.
- Keep the agent's `export PATH=$HOME/go/bin:$PATH` (or the toolchain tarball's bin dir) in EVERY ssh invocation of step 4-5 — a fresh shell per ssh means an env var set in one call silently vanishes in the next, and the failure reads as 'binary not found' rather than 'PATH not carried'.
```bash
# smoke: the project's documented verification (README quickstart, make smoke, health curl, version probe, sample run)
ssh -i ~/.bunker/keys/$agent -o IdentitiesOnly=yes "bunker-$agent@$ip" \
  "cd ~/app && <documented smoke check>"            # no documented smoke check = a finding itself
bunker destroy "$agent" --server bunker-las-03      # run even after failures — never leave an agent behind
# EVERY mutating bunker verb (spawn, cp, exec, destroy) takes --server — there is
# no 'current server' fallback for them, so omitting the flag reads as 'agent not
# found' / 'no target bound' and mimics a dead host. Pass it on every call.
```
Capture one-time credentials to a FILE in the same command that generates them: an init-style bootstrap prints its admin key exactly once, and piping that output through `tail`/`head` destroys it — every authenticated smoke probe on the fresh install then dies with no key to retry. Redirect the full init output to a scratch file ON the agent (never a committed artifact) and grep the key from the file for each authed probe. Destroy refusal on live processes is expected when the smoke step left a server running: the gate names the pid — stop it via the pid you saved at launch, retry the destroy, and recheck the server list after ~90s before writing the residue line.
A destroy failure is an explicit escalation note (see `bunker-agent-isolation` for manual cleanup), never
a silent pass; the short TTL is only the backstop, destroy is the contract. A first destroy that aborts
on `tar: ... file changed as we read it` (archive race with a still-writing process, e.g. a git pack or
log) is RETRYABLE, not an escalation: wait ~20s for the writer to finish and destroy again before
treating it as stuck.

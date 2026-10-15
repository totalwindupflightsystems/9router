# Install-leg transfer substitutes (private repos) and startup env traps

The hard rule: never modify repo visibility/permissions/clone settings, never
mint credentials. When the documented clone cannot run inside the bunker with
existing access, use a named substitute and prove the rest of the leg for real.

## The archive-tar substitute (named as such)

For a private repo whose forge denies the bunker agent: `git archive --format=tar.gz -o /tmp/x.tar.gz HEAD` locally (git archive of a path, not a bare tar -C of the checkout — tar -C of a workdir trips sandbox archiving guards), then move it onto the agent: prefer `bunker cp --server <host> /tmp/x.tar.gz <agent>:~/`; when only root ssh to the server works, `install -o <agent-user> -g <agent-user> -m 644 ~/x.tar.gz /home/<agent-user>/x.tar.gz` from the server, then untar on the agent and run the documented build from that tree. Name the substitute in the row AND the dogfood log ('git archive substitute — named as such'), so the leg's evidence is honest about which path was proven (build + smoke) and which was not (forge fetch). For a large tree, plain `tar -czf` with the same excludes is fine — the proof duty is the same: name the substitute and what it did and did not prove.

A PUBLIC repo can also fail to clone from a bunker agent: an egress path can serve 404 for github.com repos (the API 404s for unauthenticated callers too, so `curl -s https://api.github.com/repos/<o>/<r>` from the agent is NOT proof the repo is private — curl the same URL from the control host and compare). A 404 that reproduces from the control host is a proxy/egress artifact of that network: use the git-archive substitute, never widen access, and say in the log that the public-clone fetch specifically was not proven.

## The install leg outlives the exec window

A `docker compose up -d --build` (or any multi-minute build) exceeds the
bunker exec foreground window — a blocking exec hits the tool timeout and you
learn nothing. Stage the leg as a script (env copy, timed `docker compose up
d --build` with rc + seconds captured, then the smoke curl), `bunker cp` it to
the agent, launch it with `nohup bash install.sh > install-out.log 2>&1 &` in
one short exec, and poll the log from separate calls. Do not treat a nonzero
rc from the build command as the verdict: containers can come up healthy after
a rc=1 (compose reports before healthchecks finish) — the smoke curl against
the documented health endpoint, plus one real authenticated request, is the
leg's verdict. Record install_seconds from inside the script, not from wall
clock around the polls.

## Startup env on the fresh box

- Stock `go` on the agent is commonly BELOW go.mod's floor — that is the point
  of the leg: Go's toolchain auto-download makes the documented build still
  work; record the build seconds including the download.
- If the fresh box has NO go at all, hand-installing the toolchain into $HOME is
  the finding-shaped leg per SKILL.md (the silent assumption is the finding).

## Host selection

Probe ALL fleet bunker aliases with one ssh probe each (`systemctl is-active
bunkerd`) before concluding SKIPPED — the named host is a default, not a
requirement, and a single live box is enough. `tailscale status` first, then
the alias sweep; file which hosts were offline and their last-seen staleness.
A fresh-agent image may lack bwrap or deny unprivileged user namespaces
(AppArmor `unprivileged_userns` on Ubuntu 24.04+): the documented install
itself still runs (tier report prints DEGRADED with a named cause — that
honesty is part of the smoke), and `--user` mode / composed mode are the
documented fallback launches to smoke against. An inner-container denial of
the bare launch is not an install failure when the refusal names its cause and
options — record the tier report verbatim.

When NO bunker host answers, a LOCAL fresh-install smoke still proves part of
the install premise: clone to a temp dir, run the documented build verbatim,
then the boot smoke against a scratch DB and a free port — run the daemon
foreground under `timeout N` so an up-daemon ends as exit 124 with the boot log
as proof (only the should-exit-immediately refusal case returns a normal rc).
Record it as the install leg with host=local and STILL file the
SKIPPED-install-bunker row: the clean-machine class (bare toolchain, fresh
state) was not exercised, and the log entry must say both what was proven and
what was not.

## Spawn and destroy mechanics

- Spawn: `bunker spawn <agent-id> --ttl 2h --server <host>` (agent-id positional, must match
  [a-z0-9-]{1,64}; ttl is validated locally before the RPC).
- Mutating bunker commands (destroy, cp, exec) NEVER fall back to `bunker use` — pass the
  per-command `--server <server-name>` flag explicitly or they refuse with 'no target bound'.
  The `BUNKER_SESSION_TARGET=<server-name>` env var is the accepted alternative when flag
  placement is awkward (`bunker exec` rejects flags BEFORE the agent id, so `exec --agent`
  and `exec --server` both fail parsing); the agent is still targeted positionally — `cp`
  as `<agent-id>:path` (there is no --agent flag) and `exec <agent-id> <cmd>`.
- `bunker exec <agent> 'bash -s' < script` delivers EMPTY stdin (the exec stdin pipe is not
  forwarded) — stage the leg script via `bunker cp <local> <agent>:<name>.sh`, then
  `bunker exec <agent> 'bash ~/name.sh'`. Relative remote paths work; explicit `$HOME/...`
  remote paths in the cp target fail.
- `bunker exec` output that shows `sh: 1: cd: can't cd` is the LEG not having run, not a
  leg failure — the exec ran on a box where the staged tree is absent; verify the tree
  exists in a separate short exec before timing the install.
- A destroy is gated on live processes: a server you backgrounded inside a
  command that hit the tool timeout SURVIVES the timeout (the timeout kills the
  tool call, not the remote process) and blocks the destroy. Read the refusal —
  it names pid + cmdline — kill those processes over ssh, then retry. Launch any
  smoke server so you can kill it in a command you control; `cmd & curl ...`
  inside one ssh command is a teardown liability.
`bunker destroy <agent-id> --server <host>` has no `--yes`; it prints a
home-size + archive-deadline line, then 'destroyed', and removes the local key.
Post-destroy, follow the residue-recheck-protocol reference — two recheck
reads, attribute vanishing vs surviving vs growing before filing. A phantom
agent in `bunker list` that `bunker info` says does not exist is usually the
reconciler mid-sweep; recheck after ~90s before filing residue.

## Residue

After destroy, follow the residue-recheck-protocol reference — two recheck
reads, attribute vanishing vs surviving vs growing before filing.

# Scratch server lifecycle on unattended surfaces

How to boot, probe, restart and kill the dogfood scratch server when the tick
runs on an api_server/cron surface. The blockers are the harness's approval
screening, not the product.

## Launch

- Foreground `&`, `nohup`, `disown`, `setsid` wrappers are ALL refused by the
  terminal tool on unattended surfaces. Start the server as a background
  terminal command that wraps env + redirect in one shell string:
  `sh -c 'ENV1=v1 ENV2=v2 bin/crier -port 18821 > /tmp/scratch/server.log 2>&1'`.
- The background call returns immediately with a session_id; the server is NOT
  listening yet. Health-check in a SEPARATE follow-up terminal call (`sleep 1;
  curl -s -m 3 localhost:<port>/health`), never inside the launch command.

## Restart

A kill+relaunch in one foreground command trips the same wrapper screening.
Kill via `fuser -k <port>/tcp` (port-scoped, no pattern) in one call, then
relaunch in a fresh background command. Never `pkill -f` a pattern your own
command line contains — see the pgrep-self-match skill.

## Probe shape-gotchas

- Read the server's OWN config loader for the env names before first boot:
  guessing a DSN-shaped env for a var that is a different backend's only burns a
  boot cycle; the sessions backend may have its own dedicated pair of env vars.
  The error text quotes the bad value (honest), but only the source read
  prevents the cycle.
- Verify the port you curl is YOUR process before trusting any HTTP result —
  `ss -ltn | grep <port>` plus your server's startup log, per the SKILL.md
  foreign-listener pitfall.

## Cleanup

Stop every scratch server (port-scoped kill) and delete scratch DBs before
committing — the pre-commit guard runs the repo's tests and a leaked server can
hold a port or a sqlite file. Read back the post-kill health probe (connection
refused) before writing the cleanup line.

Verify the kill through the PORT and an explicit pid, never a bare `pgrep -f`
pattern: the poll can match its own command line or a defunct zombie and report
the server still alive after a clean kill (and a `pkill -f` whose pattern your
own command contains can SIGTERM the shell running the poll). `ss -tln | grep
<port>` returning nothing plus `ps -p <saved-pid>` gone is the cleanup proof —
save the pid at launch for exactly this.

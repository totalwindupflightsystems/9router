# Two-tree rule (host + repo) — deployment verification depth

The stack lives in TWO places that drift silently: the live host `/root/fleet-monitoring/` and
the dev repo checkout — and the HOST ITSELF carries two live layouts: the TOP-LEVEL files
(`/root/fleet-monitoring/docker-compose.yml`, `alert-router/`, `backup-to-s3.sh`) and the
`stack/` layout (`stack/docker-compose.yml`, `stack/<svc>/`). What uses which: bare
`docker compose ...` run from `/root/fleet-monitoring` and the systemd unit's `ExecStart=` paths
resolve the TOP-LEVEL tree; the `stack/` tree is the canonical/mirrored layout. A fix that lands
in only one of the three (repo, host stack/, host top-level) is NOT deployed — check which
resolver your change flows through before declaring it live.

The host tree has a LOCAL git repo (no remote; `.env` gitignored) — commit host-side changes there
(fixed identity, e.g. `-c user.name=fleet-monitor`) so the nightly git-bundle backup captures them,
and STILL mirror into the dev repo checkout, which holds the origin. Whenever you change a file:

- Apply the fix to BOTH trees (edit host in place, then mirror the same content into the repo and
  commit; or commit in the repo and scp the file up) — `diff <(ssh host cat <file>) <repo-copy>`
  is the cheap drift check before declaring done. The dev repo may carry NO origin remote at all
  (`git remote -v` empty) — check before promising push parity; when absent, the commit is
  local-only and the host's nightly git-bundle backup is the off-host path, so SAY the commit is
  unpushed rather than implying durable remote state.
- **After scp-deploying a file to the live host, verify the DEPLOYED bytes, not the scp exit
  code: `md5sum` both copies must match.** Keep the pre-change host copy as `<file>.bak-<date>`
  in place — it is the instant rollback and the evidence the change was deliberate.
- Verify the fix on at least TWO machines where machine-dependent behavior is plausible (e.g.
  lint passes on the host that lacks a tool and on a box that has it).
- **A service whose source is BAKED into its image needs `build` + `--force-recreate` — and the
  build context is whatever compose file your CWD resolves.** `docker compose restart <svc>` and
  a plain `up -d` reuse the running container and image; an edit to a COPY'd source file
  (`COPY router.py /app/router.py`, no bind mount) is picked up ONLY by
  `docker compose build <svc> && docker compose up -d --force-recreate <svc>`. Because bare
  `docker compose` from `/root/fleet-monitoring` resolves the TOP-LEVEL compose file, its build
  contexts are the top-level dirs — a file deployed under `stack/<svc>/` is invisible to that
  build. Mirror the edited file into the top-level build-context dir (or pass
  `-f stack/docker-compose.yml` explicitly) BEFORE building.
- **Verify the bytes the RUNNING container executes, not the bytes on the host.**
  `docker exec <svc> md5sum /app/<file>` (or `grep -c <new-symbol> /app/<file>`) must match the
  deployed source before any behavioral test; a host-side `md5sum` match proves nothing about
  the image. The symptom this check catches: the new code path silently absent (no new log line,
  no new counter on /health) while every file on disk looks correct, and the defect you just
  fixed 'reproduces' through a container still running the old bytes. Feature counters on
  `/health` (`grep <counter>` in the COUNTERS dict) are the cheapest deployed-ness proof for the
  alert-router.
- Re-run the REPO's own gate (`make lint` / `make config`) after any script/config change — a
  green deploy with a red documented gate means the next operator learns to ignore the gate.

Host-only services that live OUTSIDE the monitoring stack (e.g. the bunker daemon and its config)
follow the same shape in miniature: back up the live config, edit in place, restart the service,
verify from the service journal (not just `systemctl is-active`), and mirror the changed file into
the lane workdir's stack-copy/ so the change is reviewable.
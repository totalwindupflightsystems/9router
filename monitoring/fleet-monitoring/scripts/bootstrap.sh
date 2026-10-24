#!/usr/bin/env bash
# bootstrap.sh — prepare THIS host to run the stack. Idempotent; safe to re-run.
#
# Deliberately small and readable: every step is a command an operator could type, which is
# what makes the rebuild runbook (docs/rebuild.md) followable by someone who has never seen
# this repo. No configuration management daemon to debug when it goes wrong.
set -euo pipefail
cd "$(dirname "$0")/.." || exit 1

log() { printf '\n\033[1m== %s\033[0m\n' "$*"; }
[ "$(id -u)" -eq 0 ] && SUDO= || SUDO=sudo

log "host: $(hostname) $(uname -m)"

# Docker is not assumed. A host created through cloud-init/user-data already has it, but a host
# created straight from the API (hcloud server create, or a rebuild) has only the base image —
# and this script failing with "missing required binary: docker" there is a dead end. Installing
# it here makes the rebuild runbook work no matter how the machine came to exist.
if ! command -v docker >/dev/null 2>&1; then
  log "installing docker"
  curl -fsSL https://get.docker.com | $SUDO sh >/tmp/docker-install.log 2>&1 \
    || { echo "docker install failed — see /tmp/docker-install.log"; exit 1; }
  $SUDO systemctl enable --now docker >/dev/null 2>&1 || true
  echo "  docker $(docker --version 2>/dev/null | awk '{print $3}' | tr -d ,)"
else
  echo "  docker present: $(docker --version | awk '{print $3}' | tr -d ,)"
fi

for bin in docker curl python3; do
  command -v "$bin" >/dev/null || { echo "missing required binary: $bin"; exit 1; }
done
docker compose version >/dev/null 2>&1 || { echo "docker compose plugin required"; exit 1; }

# rclone is what backup-to-s3.sh and restore-check.sh talk to S3 with. Without this step a
# freshly rebuilt host passes `make up` and `make verify` and then fails at its first backup —
# the failure surfaces days later, in the one job whose absence you cannot see from a dashboard
# (BackupFreshnessStale was written for exactly that, but better not to need it).
if ! command -v rclone >/dev/null 2>&1; then
  log "installing rclone (required by backup/restore)"
  curl -fsSL https://rclone.org/install.sh | $SUDO bash >/tmp/rclone-install.log 2>&1 \
    || { echo "rclone install failed — see /tmp/rclone-install.log"; exit 1; }
  command -v rclone >/dev/null 2>&1 && echo "  rclone $(rclone version | head -1 | awk '{print $2}')" \
    || { echo "rclone still missing after install"; exit 1; }
else
  echo "  rclone present: $(rclone version 2>/dev/null | head -1 | awk '{print $2}')"
fi

log "data directories"
$SUDO mkdir -p /var/lib/fleet-monitoring/{spool,node-exporter-textfile}
# Grafana/Prometheus/Loki state lives in named volumes; these are the host-side bits
$SUDO chmod 0755 /var/lib/fleet-monitoring

log "kernel settings for Loki + Prometheus under load"
cat <<'EOF' | $SUDO tee /etc/sysctl.d/99-fleet-monitoring.conf >/dev/null
# Loki and Prometheus open many files; the fleet default is too low for a stack with retention
fs.file-max = 1048576
# Loki compactor is latency-tolerant; keep the box responsive while it runs
vm.swappiness = 10
EOF
$SUDO sysctl --system >/dev/null

log "docker daemon: log rotation (a host this long-lived will otherwise fill /var/lib/docker)"
# The job here is to ensure rotation EXISTS, not to impose our exact numbers. A host that
# already sets max-size has been tuned by somebody (the Coolify master also carries
# default-address-pools, which Coolify needs) — rewriting it for a cosmetic size difference
# would bounce the whole Docker daemon, and every container with it, for nothing.
DOCKER_RESTART_NEEDED=0
if [ -f /etc/docker/daemon.json ]; then
  if python3 -c '
import json,sys
cfg=json.load(open("/etc/docker/daemon.json"))
opts=cfg.get("log-opts") or {}
sys.exit(0 if opts.get("max-size") else 1)'; then
    echo "  rotation already configured — leaving daemon.json untouched (no restart)"
  else
    python3 - <<'PY'
import json
p = "/etc/docker/daemon.json"
with open(p) as fh:
    cfg = json.load(fh)
cfg.setdefault("log-driver", "json-file")
cfg.setdefault("log-opts", {})["max-size"] = "20m"
cfg["log-opts"]["max-file"] = "5"
with open(p, "w") as fh:
    json.dump(cfg, fh, indent=2)
print("  daemon.json: log rotation ADDED")
PY
    DOCKER_RESTART_NEEDED=1
  fi
else
  $SUDO mkdir -p /etc/docker
  cat <<'EOF' | $SUDO tee /etc/docker/daemon.json >/dev/null
{
  "log-driver": "json-file",
  "log-opts": { "max-size": "20m", "max-file": "5" }
}
EOF
  echo "  /etc/docker/daemon.json created"
  DOCKER_RESTART_NEEDED=1
fi

if [ "$DOCKER_RESTART_NEEDED" -eq 1 ]; then
  echo "  restarting docker to apply log rotation — containers with a restart policy come back"
  $SUDO systemctl restart docker || true
  sleep 5
else
  echo "  no docker restart required"
fi

log "tailscale"
if command -v tailscale >/dev/null; then
  $SUDO systemctl enable --now tailscaled >/dev/null 2>&1 || true
  if tailscale status >/dev/null 2>&1; then
    ip=$(tailscale ip -4 2>/dev/null | head -1)
    echo "tailscale up: $ip"
    [ -n "$ip" ] || echo "WARNING: no tailnet IPv4 — agents will not reach this host"
  else
    echo "tailscale installed but not up. Run:"
    echo "  sudo tailscale up --authkey=\$TAILSCALE_AUTHKEY --hostname=\$MONITORING_HOSTNAME --advertise-tags=\$TAILSCALE_TAGS"
  fi
else
  echo "tailscale not installed — install it before agents can push to this host:"
  echo "  curl -fsSL https://tailscale.com/install.sh | sh"
fi

log "firewall posture check"
# The design is outbound-only + tailnet. Verify no service port is world-open.
if command -v nft >/dev/null && $SUDO nft list ruleset 2>/dev/null | grep -q 'policy accept'; then
  echo "NOTE: nftables default-accept. The Hetzner cloud firewall (terraform/) is the real"
  echo "      control here; host-level rules are defence in depth, not the boundary."
fi

log "done"
cat <<'EOF'

Next:
  cp .env.example .env   &&  edit it         (if not done)
  make check-env
  make up
  make verify

If this host will ALSO read the fleet's boards, set ALERT_ROUTER_WRITE=1 and BOARD_ROOT
to the directory holding the lane checkouts.
EOF

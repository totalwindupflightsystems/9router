#!/usr/bin/env bash
# Probe the standby pool. They run Tailscale SSH, so the transport is `root@<tailnet-ip>` with
# no key material at all (keys are ignored by Tailscale SSH) — the same option set the fleet
# sweep uses, which is what makes them comparable rows in the inventory.
set -uo pipefail
HERE="/home/kara/observability-inventory"
mkdir -p "$HERE/raw" "$HERE/agents"
OPTS=(-o BatchMode=yes -o IdentitiesOnly=yes -o ConnectTimeout=8
      -o StrictHostKeyChecking=accept-new -o UserKnownHostsFile="$HOME/.ssh/known_hosts.inventory")
probe_one() {
  local ip="$1" name="$2"
  timeout 45 ssh "${OPTS[@]}" "root@$ip" 'sh -s' < "$HERE/probe-remote.sh" > "$HERE/raw/$name.env" 2>"$HERE/raw/$name.err"
  timeout 45 ssh "${OPTS[@]}" "root@$ip" 'sh -s' < "$HERE/agent-census.sh" > "$HERE/agents/$name.env" 2>"$HERE/agents/$name.err"
  echo "$name: $(wc -l < "$HERE/raw/$name.env") fact lines, $(grep -c 'AGENT_CENSUS_DONE=1' "$HERE/agents/$name.env") census"
}
probe_one 100.122.57.93 standby-cx53-01-2147 &
probe_one 100.66.160.77 standby-cx53-02-2147 &
probe_one 100.100.29.114 standby-cx53-03-2204 &
probe_one 100.106.74.73 standby-cx53-04-2220 &
probe_one 100.74.27.22  standby-cx53-05-2253 &
wait

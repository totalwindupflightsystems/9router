#!/bin/bash
# Auto-generate fresh Tailscale auth key before expiration
# Uses the admin API key to create a reusable auth key every 60 days

set -euo pipefail

AUTH_FILE="$HOME/.hermes/secrets/tailscale-auth.key"
API_KEY_FILE="$HOME/.hermes/secrets/tailscale-api.key"

# The API key for admin operations (different from auth key)
# NEVER hardcode here — read from the secrets file (preferred) or TS_API_KEY env.
if [ -f "$API_KEY_FILE" ]; then
    API_KEY=$(cat "$API_KEY_FILE")
elif [ -n "${TS_API_KEY:-}" ]; then
    API_KEY="$TS_API_KEY"
else
    echo "ERROR: no Tailscale API key (expected $API_KEY_FILE or TS_API_KEY env)" >&2
    exit 1
fi

# Generate new auth key (reusable, preauthorized, 90-day expiry)
RESPONSE=$(curl -s -X POST "https://api.tailscale.com/api/v2/tailnet/-/keys" \
  -K <(printf 'header = "Authorization: Bearer %s"\n' "$API_KEY") \
  -H "Content-Type: application/json" \
  -d '{
    "capabilities": {
      "devices": {
        "create": {
          "reusable": true,
          "ephemeral": false,
          "preauthorized": true
        }
      }
    },
    "expirySeconds": 7776000,
    "description": "KaraHermes-auto-renewed"
  }')

NEW_KEY=$(echo "$RESPONSE" | python3 -c "import sys,json; print(json.load(sys.stdin)['key'])" 2>/dev/null)

if [ -n "$NEW_KEY" ]; then
    echo "$NEW_KEY" > "$AUTH_FILE"
    chmod 600 "$AUTH_FILE"
    echo "New auth key generated: ${NEW_KEY:0:20}..."
    # Restart the SYSTEM tailscale service and re-auth with the new key
    sudo systemctl restart tailscaled 2>/dev/null || true
    sleep 3
    sudo tailscale --socket=/run/tailscale/tailscaled.sock up \
        --authkey="$NEW_KEY" \
        --hostname=karaHermes-mde-7840hs \
        --accept-dns=true 2>/dev/null || true
else
    echo "FAILED to generate new auth key"
    echo "$RESPONSE"
    exit 1
fi
#!/bin/bash
# Watchdog: monitors openrouter/owl-alpha availability
# If the model disappears, updates cron job 8fe2e67ae25f to fall back
# to deepseek-v4-pro (last known good model) and notifies Bane.

set -euo pipefail
# Turn off -u for env sourcing (may have optional vars)
set +u

ENV_FILE="$HOME/.hermes/.env"
MODEL="openrouter/owl-alpha"
FALLBACK_MODEL="deepseek-v4-pro"
FALLBACK_PROVIDER="deepseek"
CRON_JOB_ID="8fe2e67ae25f"
STATE_FILE="$HOME/.hermes/watchdog/owl-alpha-state"
LOG_FILE="$HOME/.hermes/watchdog/owl-alpha.log"

# Load API key
source "$ENV_FILE" 2>/dev/null
if [ -z "${OPENROUTER_API_KEY:-}" ]; then
    echo "[$(date -Iseconds)] ERROR: OPENROUTER_API_KEY not set" >> "$LOG_FILE"
    exit 1
fi

mkdir -p "$(dirname "$STATE_FILE")" "$(dirname "$LOG_FILE")"

# Check if the model exists on OpenRouter
echo "[$(date -Iseconds)] Checking $MODEL..." >> "$LOG_FILE"

RESPONSE=$(curl -s --max-time 15 \
    -K <(printf 'header = "Authorization: Bearer %s"\n' "$OPENROUTER_API_KEY") \
    -H "HTTP-Referer: https://hermes-agent.nousresearch.com" \
    "https://openrouter.ai/api/v1/models/$MODEL" 2>&1)

# Check if model is gone (404, empty, or error in JSON)
if echo "$RESPONSE" | python3 -c "
import sys, json
try:
    data = json.load(sys.stdin)
    err = data.get('error', {})
    code = err.get('code', 0) if isinstance(err, dict) else 0
    if code == 404 or 'not found' in str(err).lower():
        sys.exit(1)
    # If there's an error code, model may be in trouble
    if code > 0:
        sys.exit(2)
    print('OK')
except json.JSONDecodeError:
    sys.exit(1)
" 2>/dev/null; then
    # Model is fine
    echo "[$(date -Iseconds)] $MODEL is available" >> "$LOG_FILE"
    echo "available" > "$STATE_FILE"
    exit 0
fi

EXIT_CODE=$?

# Model is gone or having issues
echo "[$(date -Iseconds)] ALERT: $MODEL returned error (exit $EXIT_CODE): ${RESPONSE:0:500}" >> "$LOG_FILE"

# Check if we already handled this
PREV_STATE=$(cat "$STATE_FILE" 2>/dev/null || echo "available")
if [ "$PREV_STATE" = "gone" ]; then
    echo "[$(date -Iseconds)] Already handled — skipping" >> "$LOG_FILE"
    exit 0
fi

# Mark as gone so we don't repeat
echo "gone" > "$STATE_FILE"

# Update the cron job via hermes CLI
echo "[$(date -Iseconds)] Updating cron job $CRON_JOB_ID: $MODEL → $FALLBACK_MODEL ($FALLBACK_PROVIDER)..." >> "$LOG_FILE"

# Use hermes cronjob update to change the model
HERMES_CLI="/home/kara/.hermes/hermes-agent/venv/bin/hermes"
"$HERMES_CLI" cronjob update "$CRON_JOB_ID" \
    --model "$FALLBACK_MODEL" \
    --provider "$FALLBACK_PROVIDER" \
    2>> "$LOG_FILE"

if [ $? -eq 0 ]; then
    echo "[$(date -Iseconds)] SUCCESS: Cron job updated to $FALLBACK_MODEL" >> "$LOG_FILE"
    # Notify the user
    echo "[$(date -Iseconds)] NOTIFICATION: $MODEL disappeared. Cron job $CRON_JOB_ID (hivemind-foreman) updated to $FALLBACK_MODEL via $FALLBACK_PROVIDER." >> "$LOG_FILE"
else
    echo "[$(date -Iseconds)] FAILED: Could not update cron job. Manual intervention needed." >> "$LOG_FILE"
fi

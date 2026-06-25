#!/bin/bash
#
# context-handoff-sentinel.sh
# Stop hook: writes .ll/ll-context-handoff-needed sentinel when a session ends
# with high context usage and no handoff signal was emitted.
#
# The Python layer (run_with_continuation) is the authoritative sentinel writer
# because it has accurate token counts from the stream-json result event.
# This script is belt-and-suspenders: it uses the estimated_tokens from the
# state file (which PostToolUse updates throughout the session) as a fallback.
#
# Sentinel format: {"written_at":"...","token_count":N,"context_limit":N,"usage_percent":N}
# Consumed by: run_with_continuation() in issue_manager.py / worker_pool.py
# NOT deleted by: session-cleanup.sh (intentionally excluded from rm -f list)
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

ll_resolve_config
if ! ll_feature_enabled "context_monitor.enabled"; then
    exit 0
fi

STATE_FILE=$(ll_config_value "context_monitor.state_file" ".ll/ll-context-state.json")
SENTINEL_FILE=".ll/ll-context-handoff-needed"
# Sentinel threshold: write sentinel when session ends above this percentage.
# Lower than the PostToolUse threshold so the sentinel is written with enough
# remaining context for the explicit handoff instruction turn to fit on resume.
SENTINEL_THRESHOLD=$(ll_config_value "context_monitor.sentinel_threshold" "50")

# Nothing to do if state file doesn't exist
[ -f "$STATE_FILE" ] || exit 0

# Extract fields in a single jq pass
IFS=$'\t' read -r ESTIMATED_TOKENS RESULT_TOKEN_COUNT HANDOFF_COMPLETE CONFIG_CONTEXT_LIMIT <<< \
    "$(jq -r '[
        (.estimated_tokens // 0),
        (.result_token_count // 0),
        (.handoff_complete // "false"),
        (.context_limit // 0)
    ] | @tsv' "$STATE_FILE" 2>/dev/null || echo "0	0	false	0")"

# Skip if handoff already completed in this session — nothing to do
if [ "$HANDOFF_COMPLETE" = "true" ]; then
    exit 0
fi

# Choose best available token count: result_token_count (accurate) over estimated_tokens (heuristic)
TOKEN_COUNT="$ESTIMATED_TOKENS"
if [ "${RESULT_TOKEN_COUNT:-0}" -gt 0 ]; then
    TOKEN_COUNT="$RESULT_TOKEN_COUNT"
fi

# Skip if no usable token data
if [ "${TOKEN_COUNT:-0}" -le 0 ]; then
    exit 0
fi

# Determine context limit: prefer state-file hint, then LL_CONTEXT_LIMIT env var, then config
CONTEXT_LIMIT="${CONFIG_CONTEXT_LIMIT:-0}"
if [ "$CONTEXT_LIMIT" -le 0 ] && [ -n "${LL_CONTEXT_LIMIT:-}" ] && [ "${LL_CONTEXT_LIMIT}" != "0" ]; then
    CONTEXT_LIMIT="$LL_CONTEXT_LIMIT"
fi
if [ "$CONTEXT_LIMIT" -le 0 ]; then
    CONTEXT_LIMIT=$(ll_config_value "context_monitor.context_limit_estimate" "200000")
fi
[ "$CONTEXT_LIMIT" -le 0 ] && CONTEXT_LIMIT=200000

# Calculate usage percentage
USAGE_PERCENT=$((TOKEN_COUNT * 100 / CONTEXT_LIMIT))

# Write sentinel if above threshold
if [ "$USAGE_PERCENT" -ge "$SENTINEL_THRESHOLD" ]; then
    mkdir -p "$(dirname "$SENTINEL_FILE")" 2>/dev/null || true
    printf '{"written_at":"%s","token_count":%d,"context_limit":%d,"usage_percent":%d}\n' \
        "$(date -u +%Y-%m-%dT%H:%M:%SZ)" "$TOKEN_COUNT" "$CONTEXT_LIMIT" "$USAGE_PERCENT" \
        > "$SENTINEL_FILE" 2>/dev/null || true
fi

exit 0

#!/bin/bash
#
# context-monitor.sh
# PostToolUse hook for proactive context monitoring with automatic handoff trigger
#
# Receives JSON on stdin with tool_name, tool_input, tool_response
# Outputs feedback for Claude when context threshold is reached
#

set -euo pipefail

# Source shared utilities library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# Read JSON input from stdin
INPUT=$(cat)

# Resolve config and check feature flag
ll_resolve_config
if ! ll_feature_enabled "context_monitor.enabled"; then
    exit 0
fi

# Read configuration with defaults
THRESHOLD="${LL_HANDOFF_THRESHOLD:-$(ll_config_value "context_monitor.auto_handoff_threshold" "80")}"
# context_limit_estimate is an optional override/fallback; auto-detection sets the final limit below.
CONFIG_LIMIT=$(ll_config_value "context_monitor.context_limit_estimate" "1000000")
STATE_FILE=$(ll_config_value "context_monitor.state_file" ".claude/ll-context-state.json")

# Read estimate weights with defaults
READ_PER_LINE=$(ll_config_value "context_monitor.estimate_weights.read_per_line" "10")
TOOL_CALL_BASE=$(ll_config_value "context_monitor.estimate_weights.tool_call_base" "100")
BASH_PER_CHAR=$(ll_config_value "context_monitor.estimate_weights.bash_output_per_char" "0.3")
PER_TURN_OVERHEAD=$(ll_config_value "context_monitor.estimate_weights.per_turn_overhead" "800")
SYSTEM_PROMPT_BASELINE=$(ll_config_value "context_monitor.estimate_weights.system_prompt_baseline" "10000")

# Post-compaction reset: percentage of context limit to use as new baseline
POST_COMPACT_PERCENT=$(ll_config_value "context_monitor.post_compaction_percent" "30")

# Use JSONL transcript as accurate token baseline (one-turn lag)
USE_TRANSCRIPT_BASELINE=$(ll_config_value "context_monitor.use_transcript_baseline" "true")

# Extract tool information from input
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
TOOL_RESPONSE=$(echo "$INPUT" | jq -c '.tool_response // {}')
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null || echo "")
DETECTED_MODEL=""
if [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
    DETECTED_MODEL=$(jq -rs 'map(select(.type == "assistant")) | last | .message.model // ""' "$TRANSCRIPT_PATH" 2>/dev/null || echo "")
fi

# Estimate tokens for this tool call
estimate_tokens() {
    local tool="$1"
    local response="$2"
    local tokens=0

    case "$tool" in
        Read)
            # Count newlines in response content to estimate lines
            local content
            content=$(echo "$response" | jq -r 'if type == "object" then (.content // "") else (. | tostring) end' 2>/dev/null || echo "")
            if [ -n "$content" ]; then
                local lines
                lines=$(echo "$content" | wc -l | tr -d ' ')
                tokens=$((lines * READ_PER_LINE))
            fi
            ;;
        Grep)
            # Output lines x 5 (half of read weight)
            local output
            output=$(echo "$response" | jq -r 'if type == "array" then length else (. | tostring | split("\n") | length) end' 2>/dev/null || echo "0")
            tokens=$((output * 5))
            ;;
        Bash)
            # Output chars x 0.3
            local stdout_len stderr_len
            stdout_len=$(echo "$response" | jq -r '.stdout // "" | length' 2>/dev/null || echo "0")
            stderr_len=$(echo "$response" | jq -r '.stderr // "" | length' 2>/dev/null || echo "0")
            local total_len=$((stdout_len + stderr_len))
            # Bash arithmetic: multiply by 3 and divide by 10 to approximate * 0.3
            tokens=$((total_len * 3 / 10))
            ;;
        Glob)
            # File count x 20
            local file_count
            file_count=$(echo "$response" | jq -r 'if type == "array" then length else 1 end' 2>/dev/null || echo "1")
            tokens=$((file_count * 20))
            ;;
        Write|Edit)
            # Estimate based on base cost (actual lines changed not in response)
            tokens=$((TOOL_CALL_BASE * 3))
            ;;
        Task)
            tokens=2000
            ;;
        WebFetch)
            tokens=1500
            ;;
        WebSearch)
            tokens=1000
            ;;
        *)
            tokens=$TOOL_CALL_BASE
            ;;
    esac

    # Ensure minimum base cost
    if [ "${tokens%.*}" -lt "$TOOL_CALL_BASE" ] 2>/dev/null; then
        tokens=$TOOL_CALL_BASE
    fi

    # Return integer part only
    echo "${tokens%.*}"
}

# Read the last assistant entry's token usage from JSONL transcript.
# Returns sum of input + cache_creation + cache_read + output tokens, or 0 on failure.
get_transcript_baseline() {
    local path="$1"
    [ -z "$path" ] || [ ! -f "$path" ] && echo 0 && return
    jq -s 'map(select(.type == "assistant")) | last |
        (.message.usage.input_tokens // 0) +
        (.message.usage.cache_creation_input_tokens // 0) +
        (.message.usage.cache_read_input_tokens // 0) +
        (.message.usage.output_tokens // 0)' "$path" 2>/dev/null || echo 0
}

# Map a model identifier to its context window size.
# Config override wins when explicitly set to a non-default value (anything other than 1000000).
# Known claude-*-4* prefixes → 200000; unknown models → config_override fallback.
get_context_limit() {
    local model="$1"
    local config_override="$2"
    # Explicit user override: if set to something other than the default 1000000, honour it.
    [ -n "$config_override" ] && [ "$config_override" != "1000000" ] && echo "$config_override" && return
    case "$model" in
        claude-opus-4*|claude-sonnet-4*|claude-haiku-4*) echo 200000 ;;
        *) echo "${config_override:-200000}" ;;
    esac
}

# Note: get_mtime and parse_iso_date are now provided by lib/common.sh
# as get_mtime() and to_epoch() respectively

# Initialize or read state file
read_state() {
    if [ -f "$STATE_FILE" ]; then
        cat "$STATE_FILE"
    else
        # Ensure directory exists
        mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null || true
        local init_state
        init_state=$(cat <<EOF
{
    "session_start": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "estimated_tokens": 0,
    "tool_calls": 0,
    "threshold_crossed_at": null,
    "handoff_complete": false,
    "breakdown": {}
}
EOF
)
        echo "$init_state"
    fi
}

# Write state file atomically (now uses lib/common.sh)
write_state() {
    local state="$1"
    atomic_write_json "$STATE_FILE" "$state"
}

# Check if context compaction occurred and reset estimate
# Returns reset state on stdout if compaction detected, returns 1 otherwise
check_compaction() {
    local state="$1"
    local precompact_file=".claude/ll-precompact-state.json"

    # No precompact file = no compaction happened
    [ -f "$precompact_file" ] || return 1

    # Read compaction timestamp
    local compacted_at
    compacted_at=$(jq -r '.compacted_at // ""' "$precompact_file" 2>/dev/null || echo "")
    [ -n "$compacted_at" ] && [ "$compacted_at" != "null" ] || return 1

    # Check if we already handled this compaction
    local last_compaction
    last_compaction=$(echo "$state" | jq -r '.last_compaction // ""')
    if [ "$last_compaction" = "$compacted_at" ]; then
        return 1
    fi

    # Compaction detected - reset estimate to safety margin
    local reset_tokens=$((CONTEXT_LIMIT * POST_COMPACT_PERCENT / 100))

    local reset_state
    reset_state=$(echo "$state" | jq \
        --argjson tokens "$reset_tokens" \
        --arg compaction "$compacted_at" \
        '.estimated_tokens = $tokens | .threshold_crossed_at = null | .handoff_complete = false | .last_compaction = $compaction | .breakdown = {}')

    echo "$reset_state"
    return 0
}

# Main logic
main() {
    # Skip if no tool name
    if [ -z "$TOOL_NAME" ]; then
        exit 0
    fi

    # Resolve final context limit: LL_CONTEXT_LIMIT env var wins first, then auto-detection
    # by model prefix, then config value fallback for unknown models.
    CONTEXT_LIMIT="${LL_CONTEXT_LIMIT:-$(get_context_limit "$DETECTED_MODEL" "$CONFIG_LIMIT")}"

    # Estimate tokens for this tool call
    TOKENS=$(estimate_tokens "$TOOL_NAME" "$TOOL_RESPONSE")

    # Acquire lock for state file read-modify-write (4s timeout, hook timeout is 5s)
    STATE_LOCK="${STATE_FILE}.lock"
    if ! acquire_lock "$STATE_LOCK" 4; then
        # Timeout - exit gracefully without blocking
        exit 0
    fi

    # Read current state
    STATE=$(read_state)

    # Check for compaction event and reset if needed
    RESET_STATE=$(check_compaction "$STATE" || true)
    if [ -n "$RESET_STATE" ]; then
        STATE="$RESET_STATE"
        rm -f ".claude/ll-precompact-state.json" 2>/dev/null || true
    fi

    # Extract current values
    CURRENT_TOKENS=$(echo "$STATE" | jq -r '.estimated_tokens // 0')
    CURRENT_CALLS=$(echo "$STATE" | jq -r '.tool_calls // 0')
    THRESHOLD_CROSSED_AT=$(echo "$STATE" | jq -r '.threshold_crossed_at // ""')
    HANDOFF_COMPLETE=$(echo "$STATE" | jq -r '.handoff_complete // false')
    LAST_REMINDER_AT=$(echo "$STATE" | jq -r '.last_reminder_at // ""')

    # Get transcript baseline if enabled (API-exact, one-turn lag)
    TRANSCRIPT_BASELINE=0
    if [ "${USE_TRANSCRIPT_BASELINE}" = "true" ] && [ -n "$TRANSCRIPT_PATH" ]; then
        TRANSCRIPT_BASELINE=$(get_transcript_baseline "$TRANSCRIPT_PATH")
    fi

    # Calculate new totals
    # When transcript baseline is available, use it as the accurate foundation
    # and add only the current-turn heuristic delta on top.
    if [ "${TRANSCRIPT_BASELINE}" -gt 0 ] 2>/dev/null; then
        NEW_TOKENS=$((TRANSCRIPT_BASELINE + TOKENS))
    else
        NEW_TOKENS=$((CURRENT_TOKENS + TOKENS))
    fi
    NEW_CALLS=$((CURRENT_CALLS + 1))

    # Add per-turn overhead for Claude output + user message tokens
    local overhead=$PER_TURN_OVERHEAD
    # Add system prompt baseline on first tool call of session
    if [ "$CURRENT_CALLS" -eq 0 ]; then
        overhead=$((overhead + SYSTEM_PROMPT_BASELINE))
    fi
    NEW_TOKENS=$((NEW_TOKENS + overhead))

    # Track overhead in breakdown
    OVERHEAD_CURRENT=$(echo "$STATE" | jq -r '.breakdown["claude_overhead"] // 0')
    OVERHEAD_NEW=$((OVERHEAD_CURRENT + overhead))

    # Update breakdown by tool type
    TOOL_KEY=$(echo "$TOOL_NAME" | tr '[:upper:]' '[:lower:]')
    TOOL_CURRENT=$(echo "$STATE" | jq -r --arg key "$TOOL_KEY" '.breakdown[$key] // 0')
    TOOL_NEW=$((TOOL_CURRENT + TOKENS))

    # Build new state
    NEW_STATE=$(echo "$STATE" | jq \
        --argjson tokens "$NEW_TOKENS" \
        --argjson calls "$NEW_CALLS" \
        --arg key "$TOOL_KEY" \
        --argjson tool_tokens "$TOOL_NEW" \
        --argjson overhead "$OVERHEAD_NEW" \
        --argjson baseline "$TRANSCRIPT_BASELINE" \
        '.estimated_tokens = $tokens | .tool_calls = $calls | .breakdown[$key] = $tool_tokens | .breakdown["claude_overhead"] = $overhead | .transcript_baseline_tokens = $baseline')

    # Calculate usage percentage
    USAGE_PERCENT=$((NEW_TOKENS * 100 / CONTEXT_LIMIT))

    # Check if threshold reached
    if [ "$USAGE_PERCENT" -ge "$THRESHOLD" ]; then
        # Record threshold crossing time if not already set
        if [ -z "$THRESHOLD_CROSSED_AT" ] || [ "$THRESHOLD_CROSSED_AT" = "null" ]; then
            THRESHOLD_CROSSED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$THRESHOLD_CROSSED_AT" '.threshold_crossed_at = $t')
        fi

        # Skip if handoff already complete
        if [ "$HANDOFF_COMPLETE" = "true" ]; then
            write_state "$NEW_STATE"
            release_lock "$STATE_LOCK"
            exit 0
        fi

        # Check if handoff was completed (file exists and modified after threshold)
        HANDOFF_FILE=".claude/ll-continue-prompt.md"
        if [ -f "$HANDOFF_FILE" ]; then
            PROMPT_MTIME=$(get_mtime "$HANDOFF_FILE")
            THRESHOLD_EPOCH=$(to_epoch "$THRESHOLD_CROSSED_AT")

            # Validate both values are non-zero before comparison
            if [ "$PROMPT_MTIME" -gt 0 ] && [ "$THRESHOLD_EPOCH" -gt 0 ] && \
               [ "$PROMPT_MTIME" -gt "$THRESHOLD_EPOCH" ]; then
                # Handoff complete - mark it and stop reminding
                NEW_STATE=$(echo "$NEW_STATE" | jq '.handoff_complete = true')
                write_state "$NEW_STATE"
                release_lock "$STATE_LOCK"
                exit 0
            fi
        fi

        # Rate-limit reminders: suppress if within 60s of last reminder
        NOW_EPOCH=$(date +%s)
        LAST_EPOCH=$(to_epoch "${LAST_REMINDER_AT:-}")
        if [ "$LAST_EPOCH" -gt 0 ] && [ $((NOW_EPOCH - LAST_EPOCH)) -lt 60 ]; then
            write_state "$NEW_STATE"
            release_lock "$STATE_LOCK"
            exit 0
        fi

        # Handoff not complete - output reminder to Claude
        # Use exit 2 with stderr to ensure feedback reaches Claude in non-interactive mode
        # Reference: https://github.com/anthropics/claude-code/issues/11224
        NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.last_reminder_at = $t')
        if ! write_state "$NEW_STATE"; then
            # State write failed - release lock and exit
            release_lock "$STATE_LOCK"
            exit 0
        fi
        release_lock "$STATE_LOCK"
        echo "[ll] Context ~${USAGE_PERCENT}% used (${NEW_TOKENS}/${CONTEXT_LIMIT} tokens estimated). Run /ll:handoff to preserve your work before context exhaustion." >&2
        exit 2
    fi

    # Write updated state (no output needed)
    write_state "$NEW_STATE"
    release_lock "$STATE_LOCK"
    exit 0
}

main

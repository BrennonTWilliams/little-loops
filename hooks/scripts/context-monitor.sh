#!/bin/bash
#
# context-monitor.sh
# PostToolUse hook for proactive context monitoring with automatic handoff trigger
#
# Receives JSON on stdin with tool_name, tool_input, tool_response
# Outputs feedback for Claude when context threshold is reached
#

set -euo pipefail

# Read JSON input from stdin
INPUT=$(cat)

# Find config file
CONFIG_FILE=""
if [ -f ".claude/ll-config.json" ]; then
    CONFIG_FILE=".claude/ll-config.json"
elif [ -f "ll-config.json" ]; then
    CONFIG_FILE="ll-config.json"
else
    # No config, exit silently
    exit 0
fi

# Check if jq is available (required for reliable JSON parsing)
if ! command -v jq &> /dev/null; then
    exit 0
fi

# Check if context_monitor is enabled
ENABLED=$(jq -r '.context_monitor.enabled // false' "$CONFIG_FILE" 2>/dev/null || echo "false")
if [ "$ENABLED" != "true" ]; then
    exit 0
fi

# Read configuration with defaults
THRESHOLD=$(jq -r '.context_monitor.auto_handoff_threshold // 80' "$CONFIG_FILE" 2>/dev/null)
CONTEXT_LIMIT=$(jq -r '.context_monitor.context_limit_estimate // 150000' "$CONFIG_FILE" 2>/dev/null)
STATE_FILE=$(jq -r '.context_monitor.state_file // ".claude/ll-context-state.json"' "$CONFIG_FILE" 2>/dev/null)

# Read estimate weights with defaults
READ_PER_LINE=$(jq -r '.context_monitor.estimate_weights.read_per_line // 10' "$CONFIG_FILE" 2>/dev/null)
TOOL_CALL_BASE=$(jq -r '.context_monitor.estimate_weights.tool_call_base // 100' "$CONFIG_FILE" 2>/dev/null)
BASH_PER_CHAR=$(jq -r '.context_monitor.estimate_weights.bash_output_per_char // 0.3' "$CONFIG_FILE" 2>/dev/null)

# Extract tool information from input
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
TOOL_RESPONSE=$(echo "$INPUT" | jq -c '.tool_response // {}')

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
                tokens=$(echo "$lines * $READ_PER_LINE" | bc 2>/dev/null || echo "0")
            fi
            ;;
        Grep)
            # Output lines x 5 (half of read weight)
            local output
            output=$(echo "$response" | jq -r 'if type == "array" then length else (. | tostring | split("\n") | length) end' 2>/dev/null || echo "0")
            tokens=$(echo "$output * 5" | bc 2>/dev/null || echo "0")
            ;;
        Bash)
            # Output chars x 0.3
            local stdout_len stderr_len
            stdout_len=$(echo "$response" | jq -r '.stdout // "" | length' 2>/dev/null || echo "0")
            stderr_len=$(echo "$response" | jq -r '.stderr // "" | length' 2>/dev/null || echo "0")
            local total_len=$((stdout_len + stderr_len))
            tokens=$(echo "$total_len * $BASH_PER_CHAR" | bc 2>/dev/null || echo "0")
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
    "handoff_triggered": false,
    "breakdown": {}
}
EOF
)
        echo "$init_state"
    fi
}

# Write state file atomically
write_state() {
    local state="$1"
    mkdir -p "$(dirname "$STATE_FILE")" 2>/dev/null || true
    echo "$state" > "$STATE_FILE"
}

# Main logic
main() {
    # Skip if no tool name
    if [ -z "$TOOL_NAME" ]; then
        exit 0
    fi

    # Estimate tokens for this tool call
    TOKENS=$(estimate_tokens "$TOOL_NAME" "$TOOL_RESPONSE")

    # Read current state
    STATE=$(read_state)

    # Extract current values
    CURRENT_TOKENS=$(echo "$STATE" | jq -r '.estimated_tokens // 0')
    CURRENT_CALLS=$(echo "$STATE" | jq -r '.tool_calls // 0')
    HANDOFF_TRIGGERED=$(echo "$STATE" | jq -r '.handoff_triggered // false')

    # Calculate new totals
    NEW_TOKENS=$((CURRENT_TOKENS + TOKENS))
    NEW_CALLS=$((CURRENT_CALLS + 1))

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
        '.estimated_tokens = $tokens | .tool_calls = $calls | .breakdown[$key] = $tool_tokens')

    # Calculate usage percentage
    USAGE_PERCENT=$((NEW_TOKENS * 100 / CONTEXT_LIMIT))

    # Check if threshold reached and not already triggered
    if [ "$USAGE_PERCENT" -ge "$THRESHOLD" ] && [ "$HANDOFF_TRIGGERED" != "true" ]; then
        # Mark as triggered
        NEW_STATE=$(echo "$NEW_STATE" | jq '.handoff_triggered = true')
        write_state "$NEW_STATE"

        # Output handoff trigger message
        cat <<EOF
[ll] Context ~${USAGE_PERCENT}% used (${NEW_TOKENS}/${CONTEXT_LIMIT} tokens estimated) - threshold ${THRESHOLD}% reached

IMPORTANT: Context usage threshold reached. To preserve your work, please run:
  /ll:handoff

This will generate a continuation prompt for a fresh session.
EOF
        exit 0
    fi

    # Write updated state (no output needed)
    write_state "$NEW_STATE"
    exit 0
}

main

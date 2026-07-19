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
SENTINEL_THRESHOLD=$(ll_config_value "context_monitor.sentinel_threshold" "50")
# context_limit_estimate is an optional override/fallback; auto-detection sets the final limit below.
CONFIG_LIMIT=$(ll_config_value "context_monitor.context_limit_estimate" "")
STATE_FILE=$(ll_config_value "context_monitor.state_file" ".ll/ll-context-state.json")

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

# Extract tool information from input (single jq pass — avoids 3× re-parsing of potentially large INPUT)
# Uses \x1f (unit separator) rather than @tsv's tab: bash `read` treats tab as
# "IFS whitespace" and collapses consecutive delimiters even when IFS is set
# to tab alone, silently shifting later fields when transcript_path is empty.
IFS=$'\x1f' read -r TOOL_NAME TRANSCRIPT_PATH SESSION_ID <<< "$(echo "$INPUT" | jq -r '[(.tool_name // ""), (.transcript_path // ""), (.session_id // "")] | join("\u001f")' 2>/dev/null)"

# Best-effort "handoff_needed" lifecycle row (ENH-2495). Shells out with
# `|| true` so a DB write failure can never flip this hook's exit code.
record_handoff_needed() {
    python3 -c '
import json, sys
from little_loops.session_store import record_session_lifecycle_event, resolve_history_db
record_session_lifecycle_event(
    resolve_history_db(".ll/history.db"),
    session_id=sys.argv[1] or None,
    event="handoff_needed",
    detail=json.loads(sys.argv[2]),
)
' "$SESSION_ID" \
        "$(printf '{"threshold_pct":%s,"sentinel_threshold":%s,"token_count":%s,"context_limit":%s}' \
            "$USAGE_PERCENT" "$SENTINEL_THRESHOLD" "$NEW_TOKENS" "$CONTEXT_LIMIT")" \
        >/dev/null 2>&1 || true
}
# Note: TOOL_RESPONSE is no longer extracted here — estimate_tokens reads .tool_response
# directly from $INPUT, avoiding a full serialization of the response into a shell variable.
# Model detection is deferred to main() after state read, where the cached value is checked first.

# Estimate tokens for this tool call
# Accepts raw hook INPUT JSON — extracts .tool_response only in branches that need it,
# avoiding a full serialization of potentially large response data into shell variables.
estimate_tokens() {
    local tool="$1"
    local raw_input="$2"
    local tokens=0

    case "$tool" in
        Read)
            # Count lines in jq to avoid putting full file content into a bash variable
            local lines
            lines=$(echo "$raw_input" | jq -r '.tool_response | if type == "object" then (.content // "") else (. | tostring) end | split("\n") | length' 2>/dev/null || echo "0")
            tokens=$((lines * READ_PER_LINE))
            ;;
        Grep)
            # Output lines x 5 (half of read weight)
            local output
            output=$(echo "$raw_input" | jq -r '.tool_response | if type == "array" then length else (. | tostring | split("\n") | length) end' 2>/dev/null || echo "0")
            tokens=$((output * 5))
            ;;
        Bash)
            # Output chars x 0.3 — single jq call extracts both lengths
            local total_len
            total_len=$(echo "$raw_input" | jq -r '.tool_response | ((.stdout // "" | length) + (.stderr // "" | length))' 2>/dev/null || echo "0")
            # Bash arithmetic: multiply by 3 and divide by 10 to approximate * 0.3
            tokens=$((total_len * 3 / 10))
            ;;
        Glob)
            # File count x 20
            local file_count
            file_count=$(echo "$raw_input" | jq -r '.tool_response | if type == "array" then length else 1 end' 2>/dev/null || echo "1")
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
# Uses tail -50 instead of full jq -s slurp to avoid reading the entire growing transcript.
get_transcript_baseline() {
    local path="$1"
    [ -z "$path" ] || [ ! -f "$path" ] && echo 0 && return
    local result
    result=$(tail -50 "$path" 2>/dev/null | jq -s 'map(select(.type == "assistant")) | last |
        (.message.usage.input_tokens // 0) +
        (.message.usage.cache_creation_input_tokens // 0) +
        (.message.usage.cache_read_input_tokens // 0) +
        (.message.usage.output_tokens // 0)' 2>/dev/null || echo 0)
    [[ "$result" =~ ^[0-9]+$ ]] && echo "$result" || echo 0
}

# Map a model identifier to its context window size.
# Config override wins when explicitly set to a non-empty, non-zero value (including 1000000 for 1M models).
# Known claude-*-4* prefixes -> 200000; all other models -> 200000.
get_context_limit() {
    local model="$1"
    local config_override="$2"
    # Explicit user override: honor any non-empty, non-zero value (including 1000000 for 1M-context models).
    [ -n "$config_override" ] && [ "$config_override" != "0" ] && echo "$config_override" && return
    # keep in sync with scripts/little_loops/context_window.py:context_window_for()
    case "$model" in
        *\[1m\]) echo 1000000 ;;
        claude-opus-4*|claude-sonnet-4*|claude-haiku-4*) echo 200000 ;;
        *) echo 200000 ;;
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
        # Always start new sessions with handoff_complete=false. The continue-prompt file persists
        # across sessions and must NOT suppress reminders in a new session. The post-threshold
        # mtime check in main() handles marking complete mid-session.
        local handoff_complete="false"
        local init_state
        init_state=$(cat <<EOF
{
    "session_start": "$(date -u +%Y-%m-%dT%H:%M:%SZ)",
    "estimated_tokens": 0,
    "tool_calls": 0,
    "threshold_crossed_at": null,
    "handoff_complete": ${handoff_complete},
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
    local precompact_file=".ll/ll-precompact-state.json"

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

    # Estimate tokens for this tool call (before lock — doesn't need state)
    TOKENS=$(estimate_tokens "$TOOL_NAME" "$INPUT")

    # Acquire lock for state file read-modify-write (3s timeout, ~2s margin within 5s hook timeout)
    STATE_LOCK="${STATE_FILE}.lock"
    if ! acquire_lock "$STATE_LOCK" 3; then
        # Timeout - exit gracefully without blocking
        exit 0
    fi

    # Read current state
    STATE=$(read_state)

    # Extract all state fields in a single jq pass (replaces 7 individual jq calls)
    # Uses one-field-per-line output (jq comma operator) to avoid bash IFS whitespace collapsing
    TOOL_KEY=$(echo "$TOOL_NAME" | tr '[:upper:]' '[:lower:]')
    {
        read -r CURRENT_TOKENS
        read -r CURRENT_CALLS
        read -r THRESHOLD_CROSSED_AT
        read -r HANDOFF_COMPLETE
        read -r LAST_REMINDER_AT
        read -r DETECTED_MODEL
        read -r CACHED_BASELINE
        read -r OVERHEAD_CURRENT
        read -r TOOL_CURRENT
        read -r RESULT_TOKEN_COUNT
        read -r LAST_BASELINE_MTIME
    } <<< "$(echo "$STATE" | jq -r --arg key "$TOOL_KEY" '
        (.estimated_tokens // 0 | tostring),
        (.tool_calls // 0 | tostring),
        (.threshold_crossed_at // "" | tostring),
        (.handoff_complete // false | tostring),
        (.last_reminder_at // "" | tostring),
        (.detected_model // ""),
        (.transcript_baseline_tokens // 0 | tostring),
        (.breakdown["claude_overhead"] // 0 | tostring),
        (.breakdown[$key] // 0 | tostring),
        (.result_token_count // 0 | tostring),
        (.last_baseline_mtime // "0")
    ')"

    # Detect model — use cached value from state; only read transcript on first detection
    if [ -z "$DETECTED_MODEL" ] && [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
        DETECTED_MODEL=$(tail -50 "$TRANSCRIPT_PATH" 2>/dev/null | \
            jq -rs 'map(select(.type == "assistant")) | last | .message.model // ""' 2>/dev/null || echo "")
    fi

    # Resolve final context limit (after model detection for accurate auto-detection)
    CONTEXT_LIMIT="${LL_CONTEXT_LIMIT:-$(get_context_limit "$DETECTED_MODEL" "$CONFIG_LIMIT")}"

    # Check for compaction event and reset if needed (after CONTEXT_LIMIT is resolved)
    RESET_STATE=$(check_compaction "$STATE" || true)
    if [ -n "$RESET_STATE" ]; then
        STATE="$RESET_STATE"
        rm -f ".ll/ll-precompact-state.json" 2>/dev/null || true
        # Re-extract fields that compaction resets
        CURRENT_TOKENS=$(echo "$STATE" | jq -r '.estimated_tokens // 0')
        THRESHOLD_CROSSED_AT=""
        HANDOFF_COMPLETE="false"
        OVERHEAD_CURRENT=0
        TOOL_CURRENT=0
    fi

    # Get transcript baseline — re-read when JSONL mtime advances (new turn written).
    # LAST_BASELINE_MTIME = "0" on first call, triggering initial read.
    # Subsequent calls within the same turn have an unchanged mtime → serve from cache.
    TRANSCRIPT_BASELINE="${CACHED_BASELINE:-0}"
    if [ "${USE_TRANSCRIPT_BASELINE}" = "true" ] && [ -n "$TRANSCRIPT_PATH" ] && [ -f "$TRANSCRIPT_PATH" ]; then
        CURRENT_MTIME=$(get_mtime "$TRANSCRIPT_PATH")
        if [ "${LAST_BASELINE_MTIME:-0}" = "0" ] || \
           [ "$CURRENT_MTIME" -gt "${LAST_BASELINE_MTIME:-0}" ] 2>/dev/null; then
            TRANSCRIPT_BASELINE=$(get_transcript_baseline "$TRANSCRIPT_PATH")
            LAST_BASELINE_MTIME="$CURRENT_MTIME"
        fi
    fi

    # Auto-upgrade: if the measured transcript baseline exceeds the resolved limit but is within
    # plausible 1M range, the model has a larger context window (e.g. 1M variant with stripped suffix).
    # Upper bound 1100000 prevents corrupt reads (e.g. 1517046) from triggering a false upgrade.
    if [ "${TRANSCRIPT_BASELINE:-0}" -gt "$CONTEXT_LIMIT" ] 2>/dev/null && \
       [ "${TRANSCRIPT_BASELINE:-0}" -le 1100000 ] 2>/dev/null; then
        [ "$CONTEXT_LIMIT" -le 200000 ] && CONTEXT_LIMIT=1000000
    fi

    # Calculate new totals
    # Priority: authoritative result event count > transcript baseline > pure heuristics.
    # result_token_count already reflects full turn usage — do NOT add TOKENS on top.
    if [ "${RESULT_TOKEN_COUNT}" -gt 0 ] 2>/dev/null; then
        NEW_TOKENS=$RESULT_TOKEN_COUNT
    elif [ "${TRANSCRIPT_BASELINE}" -gt 0 ] 2>/dev/null; then
        NEW_TOKENS=$((TRANSCRIPT_BASELINE + TOKENS))
    else
        NEW_TOKENS=$((CURRENT_TOKENS + TOKENS))
    fi
    NEW_CALLS=$((CURRENT_CALLS + 1))

    # Add per-turn overhead for Claude output + user message tokens
    local overhead=$PER_TURN_OVERHEAD
    # Add system prompt baseline on first tool call only when no transcript baseline is available.
    # When TRANSCRIPT_BASELINE > 0, the system prompt is already captured via cache_read_input_tokens;
    # adding SYSTEM_PROMPT_BASELINE on top would double-count it (BUG-2146).
    if [ "$CURRENT_CALLS" -eq 0 ] && [ "${TRANSCRIPT_BASELINE:-0}" -le 0 ]; then
        overhead=$((overhead + SYSTEM_PROMPT_BASELINE))
    fi
    NEW_TOKENS=$((NEW_TOKENS + overhead))

    # Sanity clamp: discard impossible token counts (> 3x limit) as transcript misreads.
    # 3x catches real corrupt reads (e.g. 1517046/200000 = 758%) while allowing legitimate
    # estimates that overshoot the limit due to overhead (e.g. 111% on a tight 50k window).
    if [ "$NEW_TOKENS" -gt $((CONTEXT_LIMIT * 3)) ] 2>/dev/null; then
        NEW_TOKENS=$CURRENT_TOKENS
    fi

    # Update breakdown tracking
    OVERHEAD_NEW=$((OVERHEAD_CURRENT + overhead))
    TOOL_NEW=$((TOOL_CURRENT + TOKENS))

    # Build new state (includes detected_model cache and baseline mtime for turn-boundary refresh)
    NEW_STATE=$(echo "$STATE" | jq \
        --argjson tokens "$NEW_TOKENS" \
        --argjson calls "$NEW_CALLS" \
        --arg key "$TOOL_KEY" \
        --argjson tool_tokens "$TOOL_NEW" \
        --argjson overhead "$OVERHEAD_NEW" \
        --argjson baseline "$TRANSCRIPT_BASELINE" \
        --arg model "$DETECTED_MODEL" \
        --argjson limit "$CONTEXT_LIMIT" \
        --arg baseline_mtime "${LAST_BASELINE_MTIME:-0}" \
        '.estimated_tokens = $tokens | .tool_calls = $calls | .breakdown[$key] = $tool_tokens | .breakdown["claude_overhead"] = $overhead | .transcript_baseline_tokens = $baseline | .detected_model = $model | .context_limit = $limit | .last_baseline_mtime = $baseline_mtime')

    # Calculate usage percentage
    USAGE_PERCENT=$((NEW_TOKENS * 100 / CONTEXT_LIMIT))

    # Check if threshold reached
    if [ "$USAGE_PERCENT" -ge "$THRESHOLD" ]; then
        CROSSED_NOW=0
        # Record threshold crossing time if not already set
        if [ -z "$THRESHOLD_CROSSED_AT" ] || [ "$THRESHOLD_CROSSED_AT" = "null" ]; then
            THRESHOLD_CROSSED_AT=$(date -u +%Y-%m-%dT%H:%M:%SZ)
            CROSSED_NOW=1
            NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$THRESHOLD_CROSSED_AT" '.threshold_crossed_at = $t')
            # Append-only crossing log for diagnostics (preserves evidence across state-file overwrites)
            printf '%s | %s/%s (%s%%) | tool=%s\n' \
                "$THRESHOLD_CROSSED_AT" "$NEW_TOKENS" "$CONTEXT_LIMIT" "$USAGE_PERCENT" "$TOOL_NAME" \
                >> ".ll/ll-context-crossings.log" 2>/dev/null || true
        fi

        # Skip if handoff already complete
        if [ "$HANDOFF_COMPLETE" = "true" ]; then
            write_state "$NEW_STATE"
            release_lock "$STATE_LOCK"
            [ "$CROSSED_NOW" = "1" ] && record_handoff_needed || true
            exit 0
        fi

        # Check if handoff was completed (file exists and modified after threshold)
        HANDOFF_FILE=".ll/ll-continue-prompt.md"
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
                [ "$CROSSED_NOW" = "1" ] && record_handoff_needed || true
                exit 0
            fi
        fi

        # Rate-limit reminders: suppress if within 60s of last reminder
        NOW_EPOCH=$(date +%s)
        LAST_EPOCH=$(to_epoch "${LAST_REMINDER_AT:-}")
        if [ "$LAST_EPOCH" -gt 0 ] && [ $((NOW_EPOCH - LAST_EPOCH)) -lt 60 ]; then
            write_state "$NEW_STATE"
            release_lock "$STATE_LOCK"
            [ "$CROSSED_NOW" = "1" ] && record_handoff_needed || true
            exit 0
        fi

        # Handoff not complete - output reminder to Claude
        # Use exit 2 with stderr to ensure feedback reaches Claude in non-interactive mode
        # Reference: https://github.com/anthropics/claude-code/issues/11224
        NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.last_reminder_at = $t')
        if ! write_state "$NEW_STATE"; then
            # State write failed - release lock and exit
            release_lock "$STATE_LOCK"
            [ "$CROSSED_NOW" = "1" ] && record_handoff_needed || true
            exit 0
        fi
        release_lock "$STATE_LOCK"
        [ "$CROSSED_NOW" = "1" ] && record_handoff_needed || true
        echo "[ll] Context ~${USAGE_PERCENT}% used (${NEW_TOKENS}/${CONTEXT_LIMIT} tokens estimated). Run /ll:handoff to preserve your work before context exhaustion." >&2
        exit 2
    fi

    # Write updated state (no output needed)
    write_state "$NEW_STATE"
    release_lock "$STATE_LOCK"
    exit 0
}

main

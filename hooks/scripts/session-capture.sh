#!/usr/bin/env bash
#
# session-capture.sh
# PostToolUse hook: append structured event records to .ll/ll-session-events.jsonl
#
# Fires on every tool invocation. Extracts event type from tool name/args,
# builds a compact JSON record, and appends to the JSONL log for
# consumption by FEAT-1264's PreCompact snapshot builder.
#
# Event schema: {"ts": "ISO8601", "type": "file|task|git|error", "op": "...", "subject": "...", "status": ""}
# All error paths exit 0 — capture failures must not block tool execution.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Check jq before reading stdin — avoids blocking on `cat` when jq is absent
if ! command -v jq &>/dev/null; then
    exit 0
fi

source "${SCRIPT_DIR}/lib/common.sh"

# Resolve config and check feature flag (default: disabled)
ll_resolve_config
if ! ll_feature_enabled "session_capture.enabled"; then
    exit 0
fi

# Read stdin once — all subsequent jq calls operate on this variable
INPUT=$(cat)

# Extract tool name first to gate type-specific field extraction
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null) || TOOL_NAME=""

# Map tool name → event type and extract only the fields needed for that type
EVENT_TYPE=""
EVENT_OP=""
EVENT_SUBJECT=""
EVENT_STATUS=""

case "$TOOL_NAME" in
    Read|Write|Edit|Glob|Grep)
        EVENT_TYPE="file"
        EVENT_OP="$TOOL_NAME"
        # file_path is the primary field; fall back to path (Glob/Grep)
        RAW_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // .tool_input.path // ""' 2>/dev/null) || RAW_PATH=""
        # Normalize: strip leading ./ per subject-normalization rule
        EVENT_SUBJECT="${RAW_PATH#./}"
        ;;
    TodoWrite|TaskCreate|TaskUpdate)
        EVENT_TYPE="task"
        EVENT_OP="$TOOL_NAME"
        # content first (TodoWrite uses content), then id (TaskCreate/TaskUpdate)
        EVENT_SUBJECT=$(echo "$INPUT" | jq -r '
            (.tool_input.content // .tool_input.id // "")
            | if type == "string" then . else @json end
        ' 2>/dev/null) || EVENT_SUBJECT=""
        EVENT_STATUS=$(echo "$INPUT" | jq -r '.tool_input.status // ""' 2>/dev/null) || EVENT_STATUS=""
        ;;
    Bash)
        BASH_CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""' 2>/dev/null) || BASH_CMD=""
        BASH_EXIT=$(echo "$INPUT" | jq -r '.tool_response.exit_code // "" | tostring' 2>/dev/null) || BASH_EXIT=""

        # Error takes priority over git classification
        if [ -n "$BASH_EXIT" ] && [ "$BASH_EXIT" != "0" ] && [ "$BASH_EXIT" != "null" ]; then
            EVENT_TYPE="error"
            EVENT_OP="bash_error"
            EVENT_SUBJECT="${BASH_CMD:0:200}"
            EVENT_STATUS="$BASH_EXIT"
        elif echo "$BASH_CMD" | grep -qE '(^|[[:space:];&|])git([[:space:]]|$)' 2>/dev/null; then
            # Strip content up to and including 'git ' to isolate subcommand + args
            GIT_ARGS="${BASH_CMD#*git }"
            EVENT_TYPE="git"
            EVENT_OP="${GIT_ARGS%% *}"
            REMAINING="${GIT_ARGS#"${EVENT_OP}"}"
            EVENT_SUBJECT="${REMAINING# }"
            EVENT_SUBJECT="${EVENT_SUBJECT:0:200}"
        fi
        ;;
    *)
        # Unknown tool — produce no record
        exit 0
        ;;
esac

# No event type determined (e.g., Bash with exit 0 and no git)
[ -z "$EVENT_TYPE" ] && exit 0

# Capture timestamp
TS=$(date -u +%Y-%m-%dT%H:%M:%SZ 2>/dev/null) || TS="1970-01-01T00:00:00Z"

# Build compact JSON record (jq -cn for compact one-liner — JSONL requires no embedded newlines)
EVENT_JSON=$(jq -cn \
    --arg ts "$TS" \
    --arg type "$EVENT_TYPE" \
    --arg op "$EVENT_OP" \
    --arg subject "$EVENT_SUBJECT" \
    --arg status "$EVENT_STATUS" \
    '{"ts": $ts, "type": $type, "op": $op, "subject": $subject, "status": $status}' 2>/dev/null) || exit 0

# Append to JSONL with lock (lock-safe pattern from lib/common.sh)
EVENTS_FILE=".ll/ll-session-events.jsonl"
EVENTS_LOCK="${EVENTS_FILE}.lock"
mkdir -p "$(dirname "$EVENTS_FILE")" 2>/dev/null || true

if acquire_lock "$EVENTS_LOCK" 3; then
    echo "$EVENT_JSON" >> "$EVENTS_FILE" 2>/dev/null || true
    release_lock "$EVENTS_LOCK"
else
    # Best-effort on lock timeout — still append rather than silently drop
    echo "$EVENT_JSON" >> "$EVENTS_FILE" 2>/dev/null || true
fi

exit 0

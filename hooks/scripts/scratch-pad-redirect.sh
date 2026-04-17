#!/bin/bash
#
# scratch-pad-redirect.sh
# PreToolUse hook that redirects oversized Bash output to a scratch file
# and denies oversized Read calls with an actionable Bash suggestion.
#
# Active only when scratch_pad.enabled is true and (by default) the run is
# in an automation context (permission_mode == "bypassPermissions").
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

allow_response() {
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

if ! command -v jq &> /dev/null; then
    allow_response
fi

INPUT=$(cat)

# Extract fields one-per-line. A trailing sentinel prevents $(...) from stripping
# newlines around legitimately empty fields (e.g. missing permission_mode).
{
    read -r TOOL_NAME || true
    read -r CMD || true
    read -r FILE_PATH || true
    read -r PERM_MODE || true
} <<< "$(echo "$INPUT" | jq -r '
    (.tool_name // ""),
    (.tool_input.command // ""),
    (.tool_input.file_path // ""),
    (.permission_mode // ""),
    "__end__"
' 2>/dev/null)"

if [[ "$TOOL_NAME" != "Bash" && "$TOOL_NAME" != "Read" ]]; then
    allow_response
fi

ll_resolve_config
if ! ll_feature_enabled "scratch_pad.enabled"; then
    allow_response
fi

AUTO_ONLY=$(ll_config_value "scratch_pad.automation_contexts_only" "true")
if [ "$AUTO_ONLY" = "true" ] && [ "$PERM_MODE" != "bypassPermissions" ]; then
    allow_response
fi

THRESHOLD=$(ll_config_value "scratch_pad.threshold_lines" "200")
TAIL_LINES=$(ll_config_value "scratch_pad.tail_lines" "20")

case "$TOOL_NAME" in
    Bash)
        [ -n "$CMD" ] || allow_response

        FIRST_TOKEN=$(echo "$CMD" | awk '{print $1}')
        FIRST_BASE=$(basename "$FIRST_TOKEN" 2>/dev/null || echo "$FIRST_TOKEN")

        MATCH=0
        while IFS= read -r cmd; do
            [ -z "$cmd" ] && continue
            if [ "$FIRST_BASE" = "$cmd" ] || [ "$FIRST_TOKEN" = "$cmd" ]; then
                MATCH=1
                break
            fi
        done < <(jq -r '.scratch_pad.command_allowlist // [] | .[]' "$LL_CONFIG_FILE" 2>/dev/null)

        if [ "$MATCH" -ne 1 ]; then
            allow_response
        fi

        SAFE_NAME=$(echo "$FIRST_BASE" | tr -cd '[:alnum:]_-')
        SAFE_NAME="${SAFE_NAME:-cmd}"
        SCRATCH_PATH=".loops/tmp/scratch/${SAFE_NAME}-$$.txt"
        mkdir -p .loops/tmp/scratch 2>/dev/null || true

        NEW_CMD="${CMD} > ${SCRATCH_PATH} 2>&1; tail -${TAIL_LINES} ${SCRATCH_PATH}"
        CTX="Output redirected to ${SCRATCH_PATH} (last ${TAIL_LINES} lines shown inline)."

        jq -nc --arg new "$NEW_CMD" --arg ctx "$CTX" \
            '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",updatedInput:{command:$new},additionalContext:$ctx}}'
        exit 0
        ;;
    Read)
        [ -n "$FILE_PATH" ] || allow_response
        [ -f "$FILE_PATH" ] || allow_response

        EXT_MATCH=0
        while IFS= read -r ext; do
            [ -z "$ext" ] && continue
            if [[ "$FILE_PATH" == *"$ext" ]]; then
                EXT_MATCH=1
                break
            fi
        done < <(jq -r '.scratch_pad.file_extension_filters // [] | .[]' "$LL_CONFIG_FILE" 2>/dev/null)

        if [ "$EXT_MATCH" -ne 1 ]; then
            allow_response
        fi

        LINES=$(wc -l < "$FILE_PATH" 2>/dev/null | tr -d ' ' || echo 0)
        LINES="${LINES:-0}"
        if [ "$LINES" -lt "$THRESHOLD" ] 2>/dev/null; then
            allow_response
        fi

        SAFE_NAME=$(basename "$FILE_PATH" | tr -cd '[:alnum:]._-')
        SAFE_NAME="${SAFE_NAME:-file}"
        SCRATCH_PATH=".loops/tmp/scratch/${SAFE_NAME}"
        REASON="[scratch-pad] ${FILE_PATH} has ${LINES} lines (threshold ${THRESHOLD}). Use Bash instead: mkdir -p .loops/tmp/scratch && cat \"${FILE_PATH}\" > ${SCRATCH_PATH} && tail -${TAIL_LINES} ${SCRATCH_PATH}"

        jq -nc --arg r "$REASON" \
            '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"deny",permissionDecisionReason:$r}}'
        exit 0
        ;;
esac

allow_response

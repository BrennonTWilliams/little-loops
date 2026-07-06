#!/bin/bash
#
# scratch-pad-redirect.sh
# PreToolUse hook that redirects oversized Bash output to a scratch file.
#
# Active only when scratch_pad.enabled is true and (by default) the run is
# in an automation context (permission_mode == "bypassPermissions").
#
# NOTE: This hook deliberately does NOT intercept Read. Denying a Read with a
# PreToolUse hook leaves the Edit/Write "file has been read" precondition
# unsatisfied, which edit-locks the file for the rest of the session (BUG-2357).
# Read is also self-capping (offset/limit pagination), so interception bought
# nothing for the read-then-edit path. Bash output is uncapped, so the redirect
# below remains valuable.
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

if [[ "$TOOL_NAME" != "Bash" ]]; then
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

TAIL_LINES=$(ll_config_value "scratch_pad.tail_lines" "20")

case "$TOOL_NAME" in
    Bash)
        [ -n "$CMD" ] || allow_response

        FIRST_TOKEN=$(echo "$CMD" | awk '{print $1}')
        FIRST_BASE=$(basename "$FIRST_TOKEN" 2>/dev/null || echo "$FIRST_TOKEN")

        # Unwrap `python -m <module>` / `python3 -m <module>` so the allowlist
        # match sees through the interpreter prefix (BUG-2407).
        EFFECTIVE_NAME="$FIRST_BASE"
        case "$FIRST_BASE" in
            python|python3|python3.*)
                MOD=$(echo "$CMD" | sed -nE 's/.*[[:space:]]-m[[:space:]]+([A-Za-z0-9_.]+).*/\1/p')
                [ -n "$MOD" ] && EFFECTIVE_NAME="${MOD##*.}"
                ;;
        esac

        MATCH=0
        while IFS= read -r cmd; do
            [ -z "$cmd" ] && continue
            if [ "$FIRST_BASE" = "$cmd" ] || [ "$FIRST_TOKEN" = "$cmd" ] || [ "$EFFECTIVE_NAME" = "$cmd" ]; then
                MATCH=1
                break
            fi
        done < <(jq -r '.scratch_pad.command_allowlist // [] | .[]' "$LL_CONFIG_FILE" 2>/dev/null)

        if [ "$MATCH" -ne 1 ]; then
            allow_response
        fi

        # Don't double-wrap a command that already manages its own output.
        # Appending a second redirect would bind to the trailing segment (e.g. a
        # user's own `tail`) and misroute the real producer's output. Guard on
        # output-managing operators only (`>`, `>>` ⊂ `>`, `| tee`) — NOT `;`/`|`,
        # since a bare compound command must be captured, not passed through (BUG-2420).
        case "$CMD" in
            *'>'*|*'| tee '*) allow_response ;;
        esac

        SAFE_NAME=$(echo "$FIRST_BASE" | tr -cd '[:alnum:]_-')
        SAFE_NAME="${SAFE_NAME:-cmd}"
        SCRATCH_PATH=".loops/tmp/scratch/${SAFE_NAME}-$$.txt"

        # Group-wrap in a subshell so a single redirect applies atomically across
        # every `;`/`|` segment of a bare compound command (otherwise it binds to
        # the final segment only and earlier output is lost). Recreate the scratch
        # dir inside the rewritten command so it exists at execution time even when
        # an auto-backgrounded command outlives the turn and the dir was swept — a
        # subshell is robust to `${CMD}` shapes that would break `{ …; }` grouping.
        #
        # Preserve the wrapped command's exit status: a bare `( ${CMD} ) > …; tail …`
        # returns `tail`'s status (≈always 0), masking a failing `pytest`/`mypy`
        # ("Exit code 0 but 5 failures reported"). Capture `$?` and re-raise it via
        # an OUTER subshell so the `exit` scopes to that subshell (never the
        # harness's persistent shell) while `tail` still prints the inline summary.
        NEW_CMD="mkdir -p .loops/tmp/scratch; ( ( ${CMD} ) > ${SCRATCH_PATH} 2>&1; rc=\$?; tail -${TAIL_LINES} ${SCRATCH_PATH}; exit \$rc )"
        CTX="Output redirected to ${SCRATCH_PATH} (last ${TAIL_LINES} lines shown inline)."

        jq -nc --arg new "$NEW_CMD" --arg ctx "$CTX" \
            '{hookSpecificOutput:{hookEventName:"PreToolUse",permissionDecision:"allow",updatedInput:{command:$new},additionalContext:$ctx}}'
        exit 0
        ;;
esac

allow_response

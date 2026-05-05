#!/usr/bin/env bash
#
# check-duplicate-issue-id-post.sh
# PostToolUse hook: reactively delete an issue file written with a duplicate ID
#
# Fires after every Write tool call. If the written file shares an integer ID
# with another existing issue file, deletes the duplicate and emits exit 2
# feedback so Claude is notified to call ll-issues next-id again.
#
# This closes the TOCTOU window in check-duplicate-issue-id.sh: the PreToolUse
# hook cannot guard the gap between returning "allow" and the file landing on
# disk. This hook reacts after the write completes to catch that race.
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# Exit fast if jq is not available
if ! command -v jq &> /dev/null; then
    exit 0
fi

# Read JSON input from stdin
INPUT=$(cat)

# Only process Write tool calls
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")
[ "$TOOL_NAME" != "Write" ] && exit 0

# Extract file path
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null || echo "")
[ -z "$FILE_PATH" ] && exit 0

# Only check .md files
[[ "$FILE_PATH" != *.md ]] && exit 0

# Read issues base dir from config
ll_resolve_config
ISSUES_BASE_DIR=$(jq -r '.issues.base_dir // ".issues"' "$LL_CONFIG_FILE" 2>/dev/null || echo ".issues")

# Only check files in issues directory
[[ "$FILE_PATH" != *"${ISSUES_BASE_DIR}/"* ]] && exit 0

# File must exist (was just written by the Write tool)
[ ! -f "$FILE_PATH" ] && exit 0

# Extract filename and bare issue integer (e.g., 1364 from P2-BUG-1364-title.md)
FILENAME=$(basename "$FILE_PATH")

ISSUE_NUM=$(echo "$FILENAME" | grep -oE '(BUG|FEAT|ENH)-[0-9]{3,}' | grep -oE '[0-9]{3,}' | head -1 || true)
[ -z "$ISSUE_NUM" ] && exit 0

# Find issues directory (absolute or relative path handling)
ISSUES_DIR=""
if [[ "$FILE_PATH" == /* ]]; then
    ISSUES_DIR=$(echo "$FILE_PATH" | grep -oE ".*/${ISSUES_BASE_DIR##*/}" | head -1)
else
    ISSUES_DIR="$ISSUES_BASE_DIR"
fi

[ ! -d "$ISSUES_DIR" ] && exit 0

# Search for another file (not this file) sharing the same integer ID.
# Uses null-terminated find to handle filenames with spaces or special characters.
DUPLICATE=$(find "$ISSUES_DIR" -name "*.md" -type f -print0 2>/dev/null | \
    while IFS= read -r -d '' f; do
        [ "$f" = "$FILE_PATH" ] && continue
        BASENAME=$(basename "$f")
        if echo "$BASENAME" | grep -qE "(^|[-_])(BUG|FEAT|ENH)-${ISSUE_NUM}([-_.]|$)"; then
            printf '%s' "$f"
            break
        fi
    done)

[ -z "$DUPLICATE" ] && exit 0

# Duplicate found — delete the just-written file and notify Claude via exit 2 + stderr.
# The file that triggered this hook (FILE_PATH) is the duplicate; the pre-existing
# file (DUPLICATE) is left intact.
DUPLICATE_BASENAME=$(basename "$DUPLICATE")
rm -f "$FILE_PATH" 2>/dev/null || true
echo "[little-loops] Duplicate ID: ${FILENAME} conflicts with ${DUPLICATE_BASENAME} (integer ${ISSUE_NUM} already allocated). File removed — call ll-issues next-id again for a unique ID." >&2
exit 2

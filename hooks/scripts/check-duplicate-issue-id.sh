#!/bin/bash
#
# check-duplicate-issue-id.sh
# PreToolUse hook to prevent creating duplicate issue IDs
#
# Receives JSON on stdin with tool_name and tool_input
# Returns JSON with permissionDecision: allow|deny
#

set -euo pipefail

# Source shared utilities library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# Allow JSON response function
allow_response() {
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
}

# Check if jq is available (required for reliable JSON parsing)
if ! command -v jq &> /dev/null; then
    allow_response
fi

# Read JSON input from stdin
INPUT=$(cat)

# Extract tool name and file path using jq for reliable parsing
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null || echo "")

# Only check Write and Edit tools
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
    allow_response
fi

# Check if file path is empty
if [[ -z "$FILE_PATH" ]]; then
    allow_response
fi

# Read issues base dir from config, with fallback default
CONFIG_FILE=".claude/ll-config.json"
ISSUES_BASE_DIR=$(jq -r '.issues.base_dir // ".issues"' "$CONFIG_FILE" 2>/dev/null || echo ".issues")

# Only check files in issues directory (uses configured path)
if [[ "$FILE_PATH" != *"${ISSUES_BASE_DIR}/"* ]]; then
    allow_response
fi

# Only check .md files
if [[ "$FILE_PATH" != *.md ]]; then
    allow_response
fi

# Extract filename from path
FILENAME=$(basename "$FILE_PATH")

# Extract issue ID (e.g., BUG-001, FEAT-002, ENH-003, BUG-1234) from filename
# Pattern: P[0-5]-(BUG|FEAT|ENH)-[0-9]{3,}-
# Use || true to prevent exit on no match
ISSUE_ID=$(echo "$FILENAME" | grep -oE '(BUG|FEAT|ENH)-[0-9]{3,}' | head -1 || true)

# If no issue ID found, allow (not a standard issue file)
if [[ -z "$ISSUE_ID" ]]; then
    allow_response
fi

# Find the issues directory (search up from current dir or use path from file)
ISSUES_DIR=""
if [[ "$FILE_PATH" == /* ]]; then
    # Absolute path - extract issues directory
    ISSUES_DIR=$(echo "$FILE_PATH" | grep -oE ".*/${ISSUES_BASE_DIR##*/}" | head -1)
else
    # Relative path - use configured directory
    ISSUES_DIR="$ISSUES_BASE_DIR"
fi

# Check if .issues directory exists
if [[ ! -d "$ISSUES_DIR" ]]; then
    allow_response
fi

# Check if this is a new file (doesn't exist yet) or existing file
if [[ -f "$FILE_PATH" ]]; then
    # File exists - this is an edit, allow it
    allow_response
fi

# Acquire advisory lock for duplicate check (3s timeout)
# This reduces race condition window but doesn't eliminate it completely
ISSUE_LOCK="${ISSUES_DIR}/.issue-id.lock"
if ! acquire_lock "$ISSUE_LOCK" 3; then
    # Timeout - fail open (allow operation)
    # Better to allow potential duplicate than block user
    allow_response
fi

# Search for existing files with the same issue ID
# Use null-terminated find to handle filenames with newlines
EXISTING=$(find "$ISSUES_DIR" -name "*.md" -type f -print0 2>/dev/null | \
    while IFS= read -r -d '' f; do
        BASENAME=$(basename "$f")
        # Use word boundary matching to avoid BUG-001 matching BUG-0010
        if echo "$BASENAME" | grep -qE "(^|[-_])${ISSUE_ID}([-_.]|$)"; then
            printf '%s' "$f"
            break
        fi
    done)

# Release lock
release_lock "$ISSUE_LOCK"

if [[ -n "$EXISTING" ]]; then
    # Duplicate found - deny the operation
    EXISTING_BASENAME=$(basename "$EXISTING")
    cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[little-loops] Duplicate issue ID detected: ${ISSUE_ID} already exists in ${EXISTING_BASENAME}. Use the next available ID."}}
EOF
    exit 0
fi

# No duplicate found - allow
allow_response

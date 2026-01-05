#!/bin/bash
#
# check-duplicate-issue-id.sh
# PreToolUse hook to prevent creating duplicate issue IDs
#
# Receives JSON on stdin with tool_name and tool_input
# Returns JSON with permissionDecision: allow|deny
#

set -euo pipefail

# Read JSON input from stdin
INPUT=$(cat)

# Extract tool name and file path
TOOL_NAME=$(echo "$INPUT" | grep -o '"tool_name"[[:space:]]*:[[:space:]]*"[^"]*"' | sed 's/.*: *"\([^"]*\)"/\1/')
FILE_PATH=$(echo "$INPUT" | grep -o '"file_path"[[:space:]]*:[[:space:]]*"[^"]*"' | head -1 | sed 's/.*: *"\([^"]*\)"/\1/')

# Only check Write and Edit tools
if [[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
fi

# Check if file path is empty
if [[ -z "$FILE_PATH" ]]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
fi

# Only check files in .issues directory
if [[ "$FILE_PATH" != *".issues/"* ]]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
fi

# Only check .md files
if [[ "$FILE_PATH" != *.md ]]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
fi

# Extract filename from path
FILENAME=$(basename "$FILE_PATH")

# Extract issue ID (e.g., BUG-001, FEAT-002, ENH-003) from filename
# Pattern: P[0-5]-(BUG|FEAT|ENH)-[0-9]{3}-
ISSUE_ID=$(echo "$FILENAME" | grep -oE '(BUG|FEAT|ENH)-[0-9]{3}' | head -1)

# If no issue ID found, allow (not a standard issue file)
if [[ -z "$ISSUE_ID" ]]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
fi

# Find the .issues directory (search up from current dir or use path from file)
ISSUES_DIR=""
if [[ "$FILE_PATH" == /* ]]; then
    # Absolute path - extract .issues directory
    ISSUES_DIR=$(echo "$FILE_PATH" | grep -oE '.*/\.issues' | head -1)
else
    # Relative path - use current directory
    ISSUES_DIR=".issues"
fi

# Check if .issues directory exists
if [[ ! -d "$ISSUES_DIR" ]]; then
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
fi

# Check if this is a new file (doesn't exist yet) or existing file
if [[ -f "$FILE_PATH" ]]; then
    # File exists - this is an edit, allow it
    echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
    exit 0
fi

# Search for existing files with the same issue ID
# Use word boundary matching to avoid BUG-001 matching BUG-0010
EXISTING=$(find "$ISSUES_DIR" -name "*.md" -type f 2>/dev/null | while read -r f; do
    BASENAME=$(basename "$f")
    if echo "$BASENAME" | grep -qE "[-_]${ISSUE_ID}[-_.]"; then
        echo "$f"
    fi
done | head -1)

if [[ -n "$EXISTING" ]]; then
    # Duplicate found - deny the operation
    EXISTING_BASENAME=$(basename "$EXISTING")
    cat <<EOF
{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"deny","permissionDecisionReason":"[little-loops] Duplicate issue ID detected: ${ISSUE_ID} already exists in ${EXISTING_BASENAME}. Use the next available ID."}}
EOF
    exit 0
fi

# No duplicate found - allow
echo '{"hookSpecificOutput":{"hookEventName":"PreToolUse","permissionDecision":"allow"}}'
exit 0

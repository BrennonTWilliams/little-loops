#!/usr/bin/env bash
#
# issue-auto-commit.sh
# PostToolUse hook: auto-commit issue file changes when issues.auto_commit is enabled.
#
# Receives JSON on stdin with tool_name, tool_input, tool_response, transcript_path.
# Fires on Write and Edit tool calls; exits 0 immediately if the path is not an
# issue file or if auto_commit is disabled in ll-config.json.
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

# Only process Write and Edit tool calls
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""' 2>/dev/null || echo "")
[[ "$TOOL_NAME" != "Write" && "$TOOL_NAME" != "Edit" ]] && exit 0

# Extract file path
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null || echo "")
[ -z "$FILE_PATH" ] && exit 0

# Only check .md files
[[ "$FILE_PATH" != *.md ]] && exit 0

# Read issues base dir from config to scope path filter
ll_resolve_config 2>/dev/null || true
ISSUES_BASE_DIR=$(jq -r '.issues.base_dir // ".issues"' "${LL_CONFIG_FILE:-/dev/null}" 2>/dev/null || echo ".issues")

# Only process files inside the issues tree
[[ "$FILE_PATH" != *"${ISSUES_BASE_DIR}/"* ]] && exit 0

# Filter to issue filename pattern: P[0-5]-{TYPE}-NNN-...
FILENAME=$(basename "$FILE_PATH")
echo "$FILENAME" | grep -qE '^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}' || exit 0

# Check if auto_commit is enabled (default: false)
ll_feature_enabled "issues.auto_commit" || exit 0

# Read auto_commit_prefix from config (default: "chore(issues)")
COMMIT_PREFIX=$(ll_config_value "issues.auto_commit_prefix" "chore(issues)")

# Extract issue ID from filename (e.g., ENH-1844 from P3-ENH-1844-title.md)
ISSUE_ID=$(echo "$FILENAME" | grep -oE '(BUG|FEAT|ENH|EPIC)-[0-9]{3,}' | head -1 || true)
[ -z "$ISSUE_ID" ] && exit 0

# Extract slug (filename without priority prefix, type-ID prefix, and .md extension)
SLUG=$(echo "$FILENAME" | sed -E 's/^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]+-//' | sed 's/\.md$//')

# Stage the file (idempotent — safe even if already staged)
git add "$FILE_PATH" 2>/dev/null || exit 0

# Working-tree guard: skip commit if there are staged/unstaged changes OTHER than our file.
# After `git add`, our file shows as "M  path" or "A  path" in porcelain output.
OTHER_CHANGES=$(git status --porcelain 2>/dev/null | grep -v "$FILENAME" | grep -c .) || OTHER_CHANGES=0

if [ "$OTHER_CHANGES" -gt 0 ]; then
    echo "[little-loops] auto_commit: skipping commit — working tree has other changes" >&2
    exit 0
fi

# Derive verb from tool name
if [ "$TOOL_NAME" = "Write" ]; then
    VERB="capture"
else
    VERB="update"
fi

# Commit with conventional commit message
git commit -m "${COMMIT_PREFIX}: ${VERB} ${ISSUE_ID} ${SLUG}" 2>/dev/null || true

exit 0

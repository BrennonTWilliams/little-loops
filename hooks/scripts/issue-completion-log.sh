#!/usr/bin/env bash
#
# issue-completion-log.sh
# PostToolUse hook: append session log to issue files closed via frontmatter
# write of `status: done`.
#
# Receives JSON on stdin with tool_name, tool_input, tool_response, transcript_path.
# Fires on Write tool calls; exits 0 immediately if the write isn't an issue file
# being marked done in its YAML frontmatter.
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

# Extract file path and content
FILE_PATH=$(echo "$INPUT" | jq -r '.tool_input.file_path // ""' 2>/dev/null || echo "")
[ -z "$FILE_PATH" ] && exit 0

# Only check .md files
[[ "$FILE_PATH" != *.md ]] && exit 0

# Read issues base dir from config to scope path filter
ll_resolve_config 2>/dev/null || true
ISSUES_BASE_DIR=$(jq -r '.issues.base_dir // ".issues"' "${LL_CONFIG_FILE:-/dev/null}" 2>/dev/null || echo ".issues")

# Only check files inside the issues tree
[[ "$FILE_PATH" != *"${ISSUES_BASE_DIR}/"* ]] && exit 0

# Filter to issue filename pattern: P[0-5]-{TYPE}-NNN-...
FILENAME=$(basename "$FILE_PATH")
echo "$FILENAME" | grep -qE '^P[0-5]-(BUG|FEAT|ENH|EPIC)-[0-9]{3,}' || exit 0

# Inspect the written content for `status: done` in the first frontmatter block
CONTENT=$(echo "$INPUT" | jq -r '.tool_input.content // ""' 2>/dev/null || echo "")
[ -z "$CONTENT" ] && exit 0

echo "$CONTENT" | awk '
    /^---[[:space:]]*$/ { n++; if (n == 2) exit }
    n == 1 && /^status:[[:space:]]*done[[:space:]]*$/ { found = 1; exit }
    END { exit !found }
' || exit 0

# transcript_path is provided directly in PostToolUse stdin — no path lookup needed
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null || echo "")
[ -z "$TRANSCRIPT_PATH" ] && exit 0

# Append session log entry using Python (leverages existing session_log module).
# Pass paths via environment variables to avoid Python SyntaxErrors from quotes in paths.
DEST_PATH="$FILE_PATH" TRANSCRIPT_PATH="$TRANSCRIPT_PATH" python3 -c "
import os
from pathlib import Path
from little_loops.session_log import append_session_log_entry
dest = Path(os.environ['DEST_PATH'])
jsonl = Path(os.environ['TRANSCRIPT_PATH'])
if dest.exists():
    append_session_log_entry(dest, 'hook:posttooluse-status-done', session_jsonl=jsonl)
" 2>/dev/null || true

# Extract decisions and rules from the newly completed issue (fire-and-forget).
# Runs in background subshell so the hook exits immediately regardless of LLM latency.
ISSUE_ID=$(echo "$FILENAME" | grep -oE '(BUG|FEAT|ENH|EPIC)-[0-9]+' || true)
if [ -n "$ISSUE_ID" ]; then
    ( ll-issues decisions extract-from-completed --issue "$ISSUE_ID" --min-confidence 0.8 >/dev/null 2>&1 ) &
fi

exit 0

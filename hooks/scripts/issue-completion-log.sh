#!/usr/bin/env bash
#
# issue-completion-log.sh
# PostToolUse hook: append session log to issues moved to completed/ via Bash tool
#
# Receives JSON on stdin with tool_name, tool_input, tool_response, transcript_path
# Fires on Bash tool calls; exits 0 immediately if not a git mv to completed/
#

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# Read JSON input from stdin
INPUT=$(cat)

# Only process Bash tool calls
TOOL_NAME=$(echo "$INPUT" | jq -r '.tool_name // ""')
[ "$TOOL_NAME" != "Bash" ] && exit 0

# Extract the command from tool_input
CMD=$(echo "$INPUT" | jq -r '.tool_input.command // ""')

# Check if this is a git mv to completed/
echo "$CMD" | grep -qE 'git mv .+completed/' || exit 0

# transcript_path is provided directly in PostToolUse stdin — no path lookup needed
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""')
[ -z "$TRANSCRIPT_PATH" ] && exit 0

# Extract destination path from git mv command
# Handles: git mv "src" "dest" or git add ... && git mv "src" "dest"
# Uses last git mv occurrence, strips surrounding quotes
DEST_PATH=$(echo "$CMD" | grep -oE 'git mv [^ ]+ [^ ]+' | tail -1 | awk '{print $NF}' | tr -d '"'"'")
[ -z "$DEST_PATH" ] && exit 0

# Append session log entry using Python (leverages existing session_log module)
python3 -c "
import sys
from pathlib import Path
from little_loops.session_log import append_session_log_entry
dest = Path('$DEST_PATH')
jsonl = Path('$TRANSCRIPT_PATH')
if dest.exists():
    append_session_log_entry(dest, 'hook:posttooluse-git-mv', session_jsonl=jsonl)
" 2>/dev/null || true

exit 0

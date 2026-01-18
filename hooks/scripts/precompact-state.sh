#!/bin/bash
#
# precompact-state.sh
# PreCompact hook to preserve task state before context compaction
#
# This hook is called before Claude Code compacts context. It captures
# the current state to help resume work after compaction.
#

set -euo pipefail

# Read JSON input from stdin
INPUT=$(cat)

# Check if jq is available (required for reliable JSON parsing)
if ! command -v jq &> /dev/null; then
    exit 0
fi

# Extract any available context from input
TRANSCRIPT_PATH=$(echo "$INPUT" | jq -r '.transcript_path // ""' 2>/dev/null || echo "")

# State file paths
STATE_DIR=".claude"
PRECOMPACT_STATE_FILE="${STATE_DIR}/ll-precompact-state.json"
CONTEXT_STATE_FILE="${STATE_DIR}/ll-context-state.json"

# Ensure state directory exists
mkdir -p "$STATE_DIR" 2>/dev/null || true

# Capture current timestamp
COMPACT_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)

# Initialize precompact state
PRECOMPACT_STATE=$(cat <<EOF
{
    "compacted_at": "$COMPACT_TIME",
    "transcript_path": "$TRANSCRIPT_PATH",
    "preserved": true
}
EOF
)

# If context state exists, merge it into precompact state
if [ -f "$CONTEXT_STATE_FILE" ]; then
    CONTEXT_STATE=$(cat "$CONTEXT_STATE_FILE")
    PRECOMPACT_STATE=$(echo "$PRECOMPACT_STATE" | jq \
        --argjson ctx "$CONTEXT_STATE" \
        '. + {context_state_at_compact: $ctx}')
fi

# Look for active plan files to note in state
ACTIVE_PLANS=$(find thoughts/shared/plans -name "*.md" -mtime -1 2>/dev/null | head -5 | jq -R -s 'split("\n") | map(select(length > 0))' || echo '[]')
PRECOMPACT_STATE=$(echo "$PRECOMPACT_STATE" | jq --argjson plans "$ACTIVE_PLANS" '. + {recent_plan_files: $plans}')

# Look for continue prompt to preserve
CONTINUE_PROMPT=".claude/ll-continue-prompt.md"
if [ -f "$CONTINUE_PROMPT" ]; then
    PRECOMPACT_STATE=$(echo "$PRECOMPACT_STATE" | jq '. + {continue_prompt_exists: true}')
fi

# Write precompact state file
echo "$PRECOMPACT_STATE" > "$PRECOMPACT_STATE_FILE"

# Output feedback to help Claude resume after compaction
echo "[ll] Task state preserved before context compaction. Check .claude/ll-precompact-state.json if resuming work." >&2

exit 0

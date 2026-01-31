#!/bin/bash
#
# user-prompt-check.sh
# UserPromptSubmit hook for little-loops plugin
#
# 1. Reminds user to initialize config if not present
# 2. Implements auto-prompt optimization when enabled
#

set -euo pipefail

# Read JSON input from stdin (contains user prompt)
INPUT=$(cat)

# Find config file
CONFIG_FILE=""
if [ -f ".claude/ll-config.json" ]; then
    CONFIG_FILE=".claude/ll-config.json"
elif [ -f "ll-config.json" ]; then
    CONFIG_FILE="ll-config.json"
fi

# Check if config file exists - warn if not
if [ -z "$CONFIG_FILE" ]; then
    echo "[little-loops] No config found. Run /ll:init to set up little-loops for this project."
    exit 0
fi

# Check if jq is available (required for JSON parsing)
if ! command -v jq &> /dev/null; then
    exit 0
fi

# Extract user prompt from input
USER_PROMPT=$(echo "$INPUT" | jq -r '.prompt // ""' 2>/dev/null || echo "")

# If no prompt, exit silently
if [ -z "$USER_PROMPT" ]; then
    exit 0
fi

# Check if prompt optimization is enabled
ENABLED=$(jq -r '.prompt_optimization.enabled // false' "$CONFIG_FILE" 2>/dev/null || echo "false")
if [ "$ENABLED" != "true" ]; then
    exit 0
fi

# Read optimization settings with defaults
MODE=$(jq -r '.prompt_optimization.mode // "quick"' "$CONFIG_FILE" 2>/dev/null)
CONFIRM=$(jq -r '.prompt_optimization.confirm // true' "$CONFIG_FILE" 2>/dev/null)
BYPASS_PREFIX=$(jq -r '.prompt_optimization.bypass_prefix // "*"' "$CONFIG_FILE" 2>/dev/null)

# Check bypass patterns
# 1. Custom bypass prefix (default: *)
if [ -n "$BYPASS_PREFIX" ] && [[ "$USER_PROMPT" == "$BYPASS_PREFIX"* ]]; then
    exit 0
fi

# 2. Slash commands (/)
if [[ "$USER_PROMPT" == /* ]]; then
    exit 0
fi

# 3. Memory/note mode (#)
if [[ "$USER_PROMPT" == \#* ]]; then
    exit 0
fi

# 4. Questions (?)
if [[ "$USER_PROMPT" == \?* ]]; then
    exit 0
fi

# 5. Short prompts (<10 chars)
PROMPT_LENGTH=${#USER_PROMPT}
if [ "$PROMPT_LENGTH" -lt 10 ]; then
    exit 0
fi

# All checks passed - output the optimization hook prompt
# The hook prompt file uses {{VARIABLE}} placeholders that we substitute

# Resolve script directory explicitly
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
HOOK_PROMPT_FILE="${CLAUDE_PLUGIN_ROOT:-$SCRIPT_DIR/..}/prompts/optimize-prompt-hook.md"

# Validate file exists
if [ ! -f "$HOOK_PROMPT_FILE" ]; then
    # Template missing - exit gracefully
    exit 0
fi

# Read hook prompt and substitute variables
HOOK_CONTENT=$(cat "$HOOK_PROMPT_FILE")

# Direct bash substitution (no escaping needed for parameter expansion)
# Bash parameter expansion doesn't interpret special characters like sed does
HOOK_CONTENT="${HOOK_CONTENT//\{\{USER_PROMPT\}\}/$USER_PROMPT}"
HOOK_CONTENT="${HOOK_CONTENT//\{\{MODE\}\}/$MODE}"
HOOK_CONTENT="${HOOK_CONTENT//\{\{CONFIRM\}\}/$CONFIRM}"

# Output to stderr with exit 2 to ensure it reaches Claude
# Reference: https://github.com/anthropics/claude-code/issues/11224
echo "$HOOK_CONTENT" >&2
exit 2

exit 0

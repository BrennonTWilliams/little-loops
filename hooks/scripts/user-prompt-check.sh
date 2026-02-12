#!/bin/bash
#
# user-prompt-check.sh
# UserPromptSubmit hook for little-loops plugin
#
# 1. Reminds user to initialize config if not present
# 2. Implements auto-prompt optimization when enabled
#

set -euo pipefail

# Source shared utilities library
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
source "${SCRIPT_DIR}/lib/common.sh"

# Read JSON input from stdin (contains user prompt)
INPUT=$(cat)

# Resolve config
ll_resolve_config

# Check if config file exists - warn if not
if [ -z "$LL_CONFIG_FILE" ]; then
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
if ! ll_feature_enabled "prompt_optimization.enabled"; then
    exit 0
fi

# Read optimization settings with defaults
MODE=$(ll_config_value "prompt_optimization.mode" "quick")
CONFIRM=$(ll_config_value "prompt_optimization.confirm" "true")
BYPASS_PREFIX=$(ll_config_value "prompt_optimization.bypass_prefix" "*")

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

# Output to stdout with exit 0 — added as context alongside the user's prompt
# Reference: docs/claude-code/hooks-reference.md (UserPromptSubmit decision control)
echo "$HOOK_CONTENT"
exit 0

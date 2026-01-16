#!/bin/bash
#
# session-start.sh
# SessionStart hook for little-loops plugin
#
# Cleans up state from previous session and loads/displays config
#

set -euo pipefail

# Clean up state from previous session
rm -f .claude/ll-context-state.json 2>/dev/null || true

# Find config file
CONFIG_FILE=".claude/ll-config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    CONFIG_FILE="ll-config.json"
fi

# Display config or warning
if [ -f "$CONFIG_FILE" ]; then
    echo "[little-loops] Config loaded: $CONFIG_FILE"
    head -50 "$CONFIG_FILE"
else
    echo "[little-loops] Warning: No config found. Run /ll:init to create one."
fi

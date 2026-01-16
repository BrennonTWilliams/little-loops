#!/bin/bash
#
# user-prompt-check.sh
# UserPromptSubmit hook for little-loops plugin
#
# Reminds user to initialize config if not present
#

set -euo pipefail

# Check if config file exists
if [ ! -f ".claude/ll-config.json" ] && [ ! -f "ll-config.json" ]; then
    echo "[little-loops] No config found. Run /ll:init to set up little-loops for this project."
fi

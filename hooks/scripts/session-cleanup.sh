#!/bin/bash
#
# session-cleanup.sh
# Stop hook for little-loops plugin
#
# Cleans up lock files, state, and git worktrees
#

set -euo pipefail

# Clean up lock and state files
rm -f .claude/.ll-lock .claude/ll-context-state.json 2>/dev/null || true

# Clean up git worktrees if present
if [ -d .worktrees ] && command -v git >/dev/null 2>&1; then
    git worktree list 2>/dev/null | grep .worktrees | awk '{print $1}' | while read -r w; do
        git worktree remove --force "$w" 2>/dev/null || true
    done || true  # grep returns 1 when no matches found
fi

echo "[little-loops] Session cleanup complete"

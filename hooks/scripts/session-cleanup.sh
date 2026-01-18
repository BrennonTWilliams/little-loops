#!/bin/bash
#
# session-cleanup.sh
# Stop hook for little-loops plugin
#
# Cleans up lock files, state, and git worktrees
#
# Note: No set -e for cleanup scripts - we want to clean up as much as possible
# even if individual steps fail

# Clean up lock and state files
rm -f .claude/.ll-lock .claude/ll-context-state.json 2>/dev/null

# Clean up git worktrees if present
if [ -d .worktrees ] && command -v git >/dev/null 2>&1; then
    # Use process substitution to avoid subshell issues with pipefail
    while IFS= read -r w; do
        [ -n "$w" ] && git worktree remove --force "$w" 2>/dev/null
    done < <(git worktree list 2>/dev/null | grep '\.worktrees' | awk '{print $1}')
fi

echo "[little-loops] Session cleanup complete"
exit 0

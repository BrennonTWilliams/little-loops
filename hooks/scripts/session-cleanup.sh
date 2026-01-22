#!/bin/bash
#
# session-cleanup.sh
# Stop hook for little-loops plugin
#
# Cleans up lock files, state, and git worktrees
#
# IMPORTANT: This is a cleanup script - it must NEVER fail.
# All operations are wrapped to succeed even if the underlying command fails.

# Cleanup function that always succeeds
cleanup() {
    # Clean up lock and state files (relative to CWD which should be project root)
    rm -f .claude/.ll-lock .claude/ll-context-state.json 2>/dev/null || true

    # Clean up git worktrees if present
    if [ -d .worktrees ] && command -v git >/dev/null 2>&1; then
        # Get list of worktrees, filter for .worktrees, remove each
        # All errors are suppressed and ignored
        git worktree list 2>/dev/null | grep '\.worktrees' 2>/dev/null | awk '{print $1}' | while read -r w; do
            [ -n "$w" ] && git worktree remove --force "$w" 2>/dev/null || true
        done || true
    fi

    return 0
}

# Run cleanup, ignoring any errors
cleanup || true

echo "[little-loops] Session cleanup complete"
echo "[ll] cleanup ok" >&2  # Workaround for Claude Code stop hook stderr check
exit 0

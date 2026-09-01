#!/bin/bash
#
# session-cleanup.sh
# Stop hook for little-loops plugin
#
# Cleans up lock files, state, and git worktrees
#
# IMPORTANT: This is a cleanup script - it must NEVER fail.
# All operations are wrapped to succeed even if the underlying command fails.

# pid_alive PID -- true if PID is alive. kill -0 fails with EPERM for a
# process owned by another user, which reads as "dead" without the ps
# fallback (matches orchestrator.py's PermissionError-is-alive handling).
pid_alive() {
    kill -0 "$1" 2>/dev/null || ps -p "$1" >/dev/null 2>&1
}

# read_registry_pid WORKTREE_PATH -- prints line 1 of the ENH-3376 registry
# entry at "$(dirname WORKTREE_PATH)/.registry/$(basename WORKTREE_PATH)" if
# it matches ^[0-9]+$; prints INVALID if the file exists but line 1 does not;
# prints nothing if the file is absent.
read_registry_pid() {
    local w="$1"
    local registry_file="$(dirname "$w")/.registry/$(basename "$w")"
    [ -f "$registry_file" ] || return 0
    local line1
    line1=$(head -n1 "$registry_file" 2>/dev/null)
    if printf '%s' "$line1" | grep -qE '^[0-9]+$'; then
        printf '%s' "$line1"
    else
        printf 'INVALID'
    fi
}

# Cleanup function that always succeeds
cleanup() {
    # Clean up lock and state files (relative to CWD which should be project root)
    rm -f .ll/.ll-lock .ll/ll-context-state.json 2>/dev/null || true

    # NOTE: scratch-pad cleanup deliberately does NOT happen here. This is a Stop
    # handler (fires at every turn end); deleting .loops/tmp/scratch here raced
    # auto-backgrounded allowlisted commands that outlive the turn (BUG-2420).
    # Scratch cleanup now lives in scratch-cleanup.sh, wired to SessionStart.

    # Read worktree base from config, with fallback default
    CONFIG_FILE=".ll/ll-config.json"
    WORKTREE_BASE=".worktrees"
    if command -v jq >/dev/null 2>&1; then
        WORKTREE_BASE=$(jq -r '.parallel.worktree_base // ".worktrees"' "$CONFIG_FILE" 2>/dev/null || echo ".worktrees")
    fi

    # Clean up git worktrees if present
    if [ -d "$WORKTREE_BASE" ] && command -v git >/dev/null 2>&1; then
        # Skip worktree cleanup if this session is running inside a worktree.
        # In a worktree: git-dir != git-common-dir. Removing all worktrees from
        # inside a worktree would destroy sibling parallel workers still in progress.
        GIT_DIR=$(git rev-parse --git-dir 2>/dev/null || echo "")
        GIT_COMMON=$(git rev-parse --git-common-dir 2>/dev/null || echo "")
        if [ -n "$GIT_DIR" ] && [ "$GIT_DIR" != "$GIT_COMMON" ]; then
            return 0
        fi

        # Get list of worktrees, filter for worktree base, remove each
        # All errors are suppressed and ignored
        WORKTREE_PATTERN=$(basename "$WORKTREE_BASE")
        git worktree list 2>/dev/null | grep "$WORKTREE_PATTERN" 2>/dev/null | awk '{print $1}' | while read -r w; do
            if [ -n "$w" ]; then
                # ENH-3378: consult the out-of-tree registry (ENH-3376) and every
                # in-tree marker before deleting — positive evidence of death only.
                REGISTRY_PID=$(read_registry_pid "$w")

                if [ "$REGISTRY_PID" = "INVALID" ]; then
                    continue  # unparseable registry entry — cannot positively exclude liveness
                fi

                if [ -n "$REGISTRY_PID" ] && pid_alive "$REGISTRY_PID"; then
                    continue  # live registry entry — skip
                fi

                HAS_MARKER=0
                MARKER_ALIVE=0
                for MARKER in "${w}"/.ll-session-*; do
                    [ -e "$MARKER" ] || continue
                    HAS_MARKER=1
                    MPID=$(basename "$MARKER" | sed 's/^\.ll-session-//')
                    if pid_alive "$MPID"; then
                        MARKER_ALIVE=1
                        break
                    fi
                done

                if [ "$MARKER_ALIVE" -eq 1 ]; then
                    continue  # live marker — skip
                fi

                if [ -z "$REGISTRY_PID" ] && [ "$HAS_MARKER" -eq 0 ]; then
                    # No registry entry and no marker: no positive evidence either
                    # way. BUG-3373's failure mode was deleting on absence of
                    # evidence; leave these to `ll-parallel --cleanup-orphans`.
                    continue
                fi

                git worktree remove --force "$w" 2>/dev/null || true
            fi
        done || true
    fi

    return 0
}

# Run cleanup, ignoring any errors
cleanup || true

echo "[little-loops] Session cleanup complete"
echo "[ll] cleanup ok" >&2  # Workaround for Claude Code stop hook stderr check
exit 0

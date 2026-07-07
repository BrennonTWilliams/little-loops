#!/bin/bash
#
# scratch-cleanup.sh
# SessionEnd hook for little-loops plugin (BUG-2420, extended)
#
# Prunes stale files from the scratch-pad directory (.loops/tmp/scratch) at
# session termination.
#
# This cleanup previously ran on the `Stop` event (in session-cleanup.sh), but
# `Stop` fires at the end of EVERY assistant turn — so it raced auto-backgrounded
# allowlisted commands that intentionally outlive the turn, deleting the scratch
# dir out from under a command that was still writing to it (zero output
# captured). `SessionEnd` fires only once per session.
#
# But `.loops/tmp/scratch` is a single path shared by EVERY concurrent Claude
# Code session / ll-loop / ll-auto process running against this repo — there is
# no per-session isolation. A blind `rm -rf` here deletes the whole directory
# on any one session's SessionEnd, including files that OTHER, still-running
# sessions are actively writing into via their own backgrounded,
# scratch-pad-redirected commands (observed directly: a concurrent session's
# SessionEnd wiped a still-running pytest redirect mid-run). Scratch filenames
# embed the writing process's PID (scratch-pad-redirect.sh:
# "${SAFE_NAME}-$$.txt"), so cleanup can be scoped to files whose owning PID is
# no longer alive, leaving concurrently-active files untouched.
#
# IMPORTANT: This is a cleanup script - it must NEVER fail. All operations are
# wrapped to succeed even if the underlying command fails.
#
# Cleanup contract (BUG-2525): only sweep files this hook's sibling
# (scratch-pad-redirect.sh) created — those whose name embeds the writing
# process's PID via the `${SAFE_NAME}-$$.txt` shape. User-typed files written
# via `> .loops/tmp/scratch/<name>.txt` have no `-<pid>` suffix and are
# preserved unconditionally; the cleanup does not own them.

# Runs relative to CWD, which should be the project root.
SCRATCH_DIR=".loops/tmp/scratch"

if [ -d "$SCRATCH_DIR" ]; then
    for f in "$SCRATCH_DIR"/*; do
        [ -e "$f" ] || continue
        base=$(basename "$f")
        pid=$(echo "$base" | sed -nE 's/.*-([0-9]+)\.[^.]+$/\1/p')
        # User-typed files have no -<pid> suffix — skip unconditionally (BUG-2525).
        [ -n "$pid" ] || continue
        if kill -0 "$pid" 2>/dev/null; then
            # Owning process is still alive — leave its scratch file alone.
            continue
        fi
        rm -f "$f" 2>/dev/null || true
    done
    # Only remove the directory itself once nothing owned by a live process
    # remains in it; rmdir is a no-op (via || true) if files are still present.
    rmdir "$SCRATCH_DIR" 2>/dev/null || true
fi

exit 0

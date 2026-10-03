#!/bin/bash
#
# scratch-cleanup.sh
# SessionStart hook for little-loops plugin (BUG-2420, extended; re-homed
# from SessionEnd to SessionStart by BUG-3363)
#
# Prunes stale files from the scratch-pad directory (.loops/tmp/scratch) at
# the start of the next session.
#
# This cleanup previously ran on the `Stop` event (in session-cleanup.sh), but
# `Stop` fires at the end of EVERY assistant turn — so it raced auto-backgrounded
# allowlisted commands that intentionally outlive the turn, deleting the scratch
# dir out from under a command that was still writing to it (zero output
# captured). It then ran on `SessionEnd` (once per session) until BUG-3363
# found that event's ~1.5s upstream kill deadline (anthropics/claude-code#32712,
# #41577 — the same class of bug BUG-2483 fixed for session-end.sh) could cancel
# even this fast (~0.07s) hook, printing a spurious "Hook cancelled" error on
# exit. It now runs on `SessionStart` instead: the PID-liveness guard below
# checks the writing process's liveness rather than which event triggered the
# sweep, so it protects concurrently-active writers regardless of trigger.
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

# BUG-3705: the sweep must finish inside the 5s hook timeout (hooks/hooks.json)
# even with thousands of files, so it uses shell builtins for pid extraction
# (no per-file basename/sed forks), batches deletes, and stops at a deadline —
# a truncated run leaves the next session strictly further along.
#
# Age guard: scratch-pad-redirect.sh embeds the exiting hook's own $$, so its
# pid is dead on arrival — liveness alone cannot protect an in-flight sibling
# session's output once the sweep is fast enough to actually reach it. Only
# files untouched for MIN_AGE_MINUTES are candidates (24h: long-running writers
# and files a long session reads back later stay safe).
MIN_AGE_MINUTES=1440
CHUNK_SIZE=500
DEADLINE_SECONDS=3

if [ -d "$SCRATCH_DIR" ]; then
    start=$SECONDS
    dead=()
    n=0
    while IFS= read -r f; do
        base=${f##*/}
        # Pid is the last -<digits> run directly before the final dot
        # (equivalent to sed -nE 's/.*-([0-9]+)\.[^.]+$/\1/p'). User-typed
        # files have no -<pid> suffix — skip unconditionally (BUG-2525).
        case "$base" in *.*) ;; *) continue ;; esac
        [ -n "${base##*.}" ] || continue
        stem=${base%.*}
        case "$stem" in *-*) ;; *) continue ;; esac
        pid=${stem##*-}
        case "$pid" in '' | *[!0-9]*) continue ;; esac
        if kill -0 "$pid" 2>/dev/null; then
            # Owning process is still alive — leave its scratch file alone.
            continue
        fi
        dead[n]="$SCRATCH_DIR/$base"
        n=$((n + 1))
        if [ "$n" -ge "$CHUNK_SIZE" ]; then
            rm -f -- "${dead[@]}" 2>/dev/null || true
            dead=()
            n=0
            [ $((SECONDS - start)) -ge "$DEADLINE_SECONDS" ] && break
        fi
    done < <(find "$SCRATCH_DIR" -maxdepth 1 -type f -mmin +"$MIN_AGE_MINUTES" 2>/dev/null)
    if [ "$n" -gt 0 ]; then
        rm -f -- "${dead[@]}" 2>/dev/null || true
    fi
    # Only remove the directory itself once nothing owned by a live process
    # remains in it; rmdir is a no-op (via || true) if files are still present.
    rmdir "$SCRATCH_DIR" 2>/dev/null || true
fi

exit 0

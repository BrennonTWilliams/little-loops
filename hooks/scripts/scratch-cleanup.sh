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
# Cleanup contract (ENH-3706, superseding BUG-2525's unconditional user-file
# preservation) — two age tiers over regular files directly in the scratch dir:
#   1. Older than 7 days: removed regardless of name or apparent PID liveness.
#      This includes user-typed files without a `-<pid>` suffix (e.g.
#      `test-results.txt`), dotfiles, and names containing spaces or newlines.
#   2. Older than 24h: files whose name embeds a trailing `-<pid>` (the
#      `${SAFE_NAME}-$$.txt` shape from scratch-pad-redirect.sh) are removed
#      when `kill -0` on that pid fails. Files without that shape are kept.
# Younger files are never touched. Limits worth knowing:
#   - Age is mtime-based: writes refresh it, reads do not. A note still being
#     read but not rewritten can be removed after 7 days; keep durable
#     progress/resume notes outside scratch.
#   - The filename pid is a compatibility check, not proof of who wrote the
#     file, and a live pid does not exempt a file idle for more than 7 days.
#   - Selection and deletion are not atomic with concurrent rewrites.
#   - Cleanup is best effort and restartable. The script exits 0 on normal
#     completion and after its cooperative deadline, but the host may kill it
#     at its 5s hook timeout; completed deletions persist and the next
#     invocation continues. 7 days is an eligibility threshold, not a
#     guaranteed maximum age on disk.
#   - Subdirectories and symlinks are never touched.

# Runs relative to CWD, which should be the project root.
SCRATCH_DIR=".loops/tmp/scratch"

# BUG-3705: the sweep aims to finish inside the 5s hook timeout (hooks/hooks.json)
# even with thousands of files, so it uses shell builtins for pid extraction
# (no per-file basename/sed forks), batches deletes, and stops at a cooperative
# deadline — a truncated run leaves the next session strictly further along.
# The deadline is checked between records; it cannot interrupt a blocked
# find/read or deletion.
#
# Age guard: scratch-pad-redirect.sh embeds the exiting hook's own $$, so its
# pid is dead on arrival — liveness alone cannot protect an in-flight sibling
# session's output once the sweep is fast enough to actually reach it. Only
# files untouched for MIN_AGE_MINUTES are candidates for the pid-liveness tier
# (24h: long-running writers stay safe).
MIN_AGE_MINUTES=1440
# ENH-3706: universal retention — anything untouched this long (7d) goes,
# regardless of name or pid liveness.
MAX_AGE_MINUTES=10080
CHUNK_SIZE=500
DEADLINE_SECONDS=3

if [ -d "$SCRATCH_DIR" ]; then
    start=$SECONDS
    # Pass 0 (ENH-3706): universal 7-day tier. -delete runs inside find (no
    # per-file forks) and tolerates files vanishing underneath it. Default -P
    # semantics: symlinks are not followed or matched by -type f. Failure is
    # non-fatal; pass 1 and the next session continue the work.
    find "$SCRATCH_DIR" -maxdepth 1 -type f -mmin +"$MAX_AGE_MINUTES" -delete 2>/dev/null || true
    dead=()
    n=0
    # Pass 1: dead-pid tier. Records are NUL-delimited so a filename containing
    # a newline stays one complete path and cannot select another file.
    while IFS= read -r -d '' f; do
        # Cooperative deadline, checked before every record (skips included).
        [ $((SECONDS - start)) -ge "$DEADLINE_SECONDS" ] && break
        base=${f##*/}
        # Pid is the last -<digits> run directly before the final dot
        # (equivalent to sed -nE 's/.*-([0-9]+)\.[^.]+$/\1/p'). User-typed
        # files have no -<pid> suffix — those wait for the 7-day tier above.
        case "$base" in *.*) ;; *) continue ;; esac
        [ -n "${base##*.}" ] || continue
        stem=${base%.*}
        case "$stem" in *-*) ;; *) continue ;; esac
        pid=${stem##*-}
        case "$pid" in '' | *[!0-9]*) continue ;; esac
        if kill -0 "$pid" 2>/dev/null; then
            # Filename pid is still alive — leave the file for the 7-day tier.
            continue
        fi
        dead[n]="$f"
        n=$((n + 1))
        if [ "$n" -ge "$CHUNK_SIZE" ]; then
            rm -f -- "${dead[@]}" 2>/dev/null || true
            dead=()
            n=0
        fi
    done < <(find "$SCRATCH_DIR" -maxdepth 1 -type f -mmin +"$MIN_AGE_MINUTES" -print0 2>/dev/null)
    if [ "$n" -gt 0 ]; then
        rm -f -- "${dead[@]}" 2>/dev/null || true
    fi
    # Remove the directory itself once empty; rmdir is a no-op (via || true) if
    # files remain. Producers recreate it with `mkdir -p` before redirecting.
    rmdir "$SCRATCH_DIR" 2>/dev/null || true
fi

exit 0

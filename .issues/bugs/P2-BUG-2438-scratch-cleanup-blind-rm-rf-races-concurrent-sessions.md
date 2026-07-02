---
captured_at: '2026-07-02T03:54:24Z'
completed_at: '2026-07-02T03:54:24Z'
discovered_date: 2026-07-02
discovered_by: live-reproduction-during-verification
status: done
priority: P2
type: BUG
relates_to:
- BUG-2420
- BUG-2437
labels:
- hooks
- scratch-pad
- automation
- concurrency
---

# BUG-2438: scratch-cleanup.sh's blind `rm -rf .loops/tmp/scratch` races every OTHER concurrent session in the repo

## Summary

`.loops/tmp/scratch` is a single path shared by every concurrent Claude Code
session / `ll-loop` / `ll-auto` process running against a repo, but
`scratch-cleanup.sh`'s `SessionEnd` handler unconditionally `rm -rf`s the whole
directory whenever *any one* of those sessions terminates — deleting other,
still-running sessions' in-flight backgrounded output out from under them.

## Current Behavior

`hooks/scripts/scratch-cleanup.sh` (a `SessionEnd` hook, added by BUG-2420 to
move scratch cleanup off the racing `Stop` event) did:

```bash
rm -rf ".loops/tmp/scratch" 2>/dev/null || true
```

BUG-2420's fix correctly solved the *same-session* race (a backgrounded
command outliving the turn vs. that same session's own `Stop` handler), by
moving the delete to `SessionEnd`, reasoning that "`SessionEnd` fires only
once, when the whole session terminates, after which no background work
remains." That reasoning implicitly assumed a single active session per repo.

In practice this repo routinely runs many concurrent `claude`/`ll-loop`
processes at once (interactive sessions, `ll-loop run <name>` background
loops, `ll-auto`/`ll-parallel` wave workers, etc.), all sharing the same
repo-root-relative `.loops/tmp/scratch` path. Whenever *any one* of these
processes reaches its own legitimate `SessionEnd`, its `scratch-cleanup.sh`
invocation deletes the entire shared directory — including scratch files that
*other*, still-running sessions are actively writing into via their own
backgrounded, scratch-pad-redirected commands.

## Expected Behavior

Ending one session's lifecycle must not delete another concurrently-running
session's scratch output. Cleanup should only remove files whose owning
process has actually exited, leaving live sessions' files (and the directory,
while any live-owned file remains in it) untouched.

## Root Cause

- **File**: `hooks/scripts/scratch-cleanup.sh`
- **Anchor**: the unconditional `rm -rf ".loops/tmp/scratch"` at the end of
  the script
- **Cause**: `.loops/tmp/scratch` has no per-session/per-process isolation
  (all writers share the one directory), yet cleanup treated "my session
  ended" as "delete the whole directory" instead of "delete only what my
  session was using."

## Discovery

Found empirically while verifying the BUG-2437 fix: running the full
`python -m pytest scripts/tests/` suite in the background (via the
scratch-pad-redirected command, itself already prefixed with `mkdir -p`) had
its output directory vanish mid-run. `ps aux` at the time showed roughly ten
concurrent `claude`/`ll-loop run` processes active against this same repo
(other interactive sessions, `ll-loop run vega-viz`, `prompt-across-issues`,
`sprint-refine-and-implement`, `wire-issue --auto` runs). One of those
sessions' own `SessionEnd` firing during that window is sufficient to explain
the deletion.

## Proposed Solution (applied)

Scratch filenames already embed the writing process's PID
(`scratch-pad-redirect.sh` builds `${SAFE_NAME}-$$.txt`). Changed
`scratch-cleanup.sh` to iterate files in `.loops/tmp/scratch`, extract the
trailing `-<pid>.` segment, and skip (rather than delete) any file whose PID
is still alive per `kill -0 "$pid"`. Files with a dead or unparseable PID are
pruned; the directory itself is only removed via `rmdir` once nothing
remains in it (a no-op, guarded by `|| true`, while a live-owned file is
still present).

## Integration Map

### Files to Modify
- `hooks/scripts/scratch-cleanup.sh` - PID-liveness-aware pruning instead of
  blind `rm -rf`

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` - `SessionEnd` binding to this script; no change needed,
  invocation contract (stdin JSON, must-never-fail, exit 0) is unchanged.

### Similar Patterns
- `hooks/scripts/scratch-pad-redirect.sh` - already embeds `$$` in scratch
  filenames (`SCRATCH_PATH=".loops/tmp/scratch/${SAFE_NAME}-$$.txt"`), which
  this fix relies on to determine ownership.

### Tests
- `scripts/tests/test_hooks_integration.py::TestScratchCleanupSessionEnd` -
  replaced the "removes scratch rm -rf" assertion with a check that the
  script uses `kill -0` and contains no blind `rm -rf` of the shared dir;
  added `test_scratch_cleanup_preserves_file_owned_by_live_process` and
  `test_scratch_cleanup_removes_file_owned_by_dead_process`.

### Documentation
- N/A - internal hook behavior; the shared-path convention itself is
  unchanged (still documented in `.claude/CLAUDE.md`'s "Automation: Scratch
  Pad" section and `docs/reference/HOST_COMPATIBILITY.md`).

### Configuration
- N/A - no config schema changes.

## Steps to Reproduce

1. Have two or more concurrent Claude Code sessions (or `ll-loop run`
   processes) active in the same repo with `scratch_pad.enabled: true`.
2. In session A, background a long allowlisted command (e.g. the full pytest
   suite) via the scratch-pad redirect convention.
3. While session A's command is still running, let session B terminate
   normally (its `SessionEnd` fires `scratch-cleanup.sh`).
4. Observe session A's `.loops/tmp/scratch/` — and its in-progress output
   file — has been deleted, even though session A is still writing to it.

## Actual Behavior

Session B's termination deletes the entire shared scratch directory,
including session A's live, in-progress output.

## Impact

- **Priority**: P2 - Silent, intermittent data loss for backgrounded command
  output in any repo with more than one active little-loops
  session/loop/process at a time — a common state for this project's own
  workflow (interactive sessions plus multiple `ll-loop run` background
  processes routinely run concurrently).
- **Effort**: Small - single-file rewrite of the cleanup loop in
  `scratch-cleanup.sh`, plus test updates; no schema or hook-wiring changes.
- **Risk**: Low - `kill -0` liveness checks are a standard, side-effect-free
  pattern; worst case on a PID-reuse false positive is a stale file lingering
  one extra cleanup cycle, not data loss. Script remains must-never-fail
  (`|| true` throughout, `exit 0`).
- **Breaking Change**: No.

## Related Issues

- **BUG-2420** — introduced the `SessionEnd`-based cleanup this issue refines;
  solved the same-session `Stop` race but assumed single-session exclusivity,
  which this issue removes.
- **BUG-2437** — the sibling defect found in the same investigation (scratch
  dir not self-sufficient at the authoring site; FSM spawn continuations
  losing automation `permission_mode`).

## Resolution

Fixed (2026-07-02). Rewrote `hooks/scripts/scratch-cleanup.sh` to prune only
files whose owning PID (parsed from the `-<pid>.` filename suffix) is no
longer alive, and to remove the directory only once empty. Added regression
tests confirming a live-owned file survives cleanup and a dead-owned file (and
the then-empty directory) is pruned.

Full suite: 13386 passed, 23 skipped.

## Status

**Current Status**: done


## Session Log
- `hook:posttooluse-status-done` - 2026-07-02T03:56:00 - `108b6549-24ca-4d55-a125-5edfe54155dc.jsonl`

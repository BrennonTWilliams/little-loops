---
id: BUG-3707
type: BUG
title: scratch-pad-redirect.sh names files with the exiting hook's pid so the liveness
  guard is illusory
priority: P3
status: cancelled
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T16:28:16Z'
relates_to:
- BUG-3705
- BUG-3702
closed_reason: wont_fix
program_design_not_applicable: true
---

# BUG-3707: scratch-pad-redirect.sh names files with the exiting hook's pid so the liveness guard is illusory

## Summary

`hooks/scripts/scratch-pad-redirect.sh` names redirect files `${SAFE_NAME}-$$.txt`, but `$$` is the PreToolUse hook process's own pid, which exits right after emitting its JSON. Every redirect file is therefore dead-pid on arrival, and `scratch-cleanup.sh`'s `kill -0` liveness guard protects nothing except via pid recycling. `verify_evidence.write_snapshot` has the same shape (pid of an exiting `ll-verify-evidence`). This is the root of BUG-3702 and why BUG-3705 needs an mtime age guard.

Fix on the writer side: emit a runtime `\$\$` inside the rewritten command (`NEW_CMD`) so the filename carries the pid of the shell running the command, making the liveness guard meaningful again.

**Unverified assumption**: Claude Code runs each Bash call in its own shell process for the command's lifetime — spike this before implementing (backgrounded/auto-backgrounded commands especially). Also check filename-shape compatibility with the pid parser in `scratch-cleanup.sh` (`${SAFE_NAME}-<pid>.txt`).

Found during the BUG-3705 pre-implementation review (Opus consult). Not a blocker for BUG-3705, which ships the age guard as the interim protection.


## Current Behavior

`scratch-pad-redirect.sh:105` builds `SCRATCH_PATH=".loops/tmp/scratch/${SAFE_NAME}-$$.txt"`; `$$` is the PreToolUse hook's own pid, which exits right after emitting its JSON, so every redirect file is dead-pid on arrival. `scratch-cleanup.sh`'s `kill -0` liveness guard therefore protects nothing except via pid recycling. (BUG-3705 added a 24h mtime guard, which is the contract that actually protects in-flight files.)

## Expected Behavior

(Original proposal, not adopted.) Emit a runtime `\$\$` inside the rewritten command so the filename carries the pid of the shell running the command and the liveness guard is meaningful again.

## Resolution

**Cancelled (won't-fix)** — 2026-10-03, pre-implementation review with an Opus second opinion (`/ll:advise`, confidence 0.82):

- **The fix has a design hole.** The hook writes `CTX` ("Output redirected to ${SCRATCH_PATH}…") before the command runs, so a runtime `$$` cannot go into `additionalContext`, and the model is told to `Read` the scratch path later. A filename with a runtime pid is unknowable at hook time unless `NEW_CMD` also echoes the resolved path, which changes the inline output shape.
- **The spike answered the unverified assumption, unfavorably.** Two Bash calls reported `$$` = 56845 and 57107, both children of the `claude` process: each call gets a fresh shell that dies when the command returns. The model reads the scratch file after that point, so a runtime pid is dead by then too; the guard would only cover the in-command window. (Spike ran from a headless `-p` session; per-call behavior is assumed identical in the interactive TUI.)
- **BUG-3705 already covers the window.** Its 24h mtime guard (`scratch-cleanup.sh`, `MIN_AGE_MINUTES=1440`) protects a running writer because it keeps mtime fresh. The `-<digits>` suffix is an ownership tag (BUG-2525 contract), not a liveness token.
- BUG-3702 (the `verify_evidence` half) is re-scoped to a pin test and docstring fix.

**Optional follow-up (cleanup, not a bug):** delete the `kill -0` check in `scratch-cleanup.sh` and its comments so the age guard is the explicit sole contract; the misleading liveness comment (`scratch-cleanup.sh`, "PID-liveness guard") is the only residue. Reopen if `MIN_AGE_MINUTES` is lowered below a long-running command's lifetime.

## Steps to Reproduce

1. Run any allowlisted command (e.g. `pytest`) through the PreToolUse `scratch-pad-redirect.sh` hook.
2. Observe the redirect file `.loops/tmp/scratch/<name>-<pid>.txt` carries the hook process's pid, which has already exited.

## Acceptance Criteria

- N/A - cancelled won't-fix; see Resolution. (Superseded by BUG-3705's 24h age guard; BUG-3702 carries the pin test.)

## Impact

- **Priority**: P3 - closed won't-fix
- **Effort**: n/a
- **Risk**: n/a
- **Breaking Change**: No

## Status

**Cancelled** | Created: 2026-10-03 | Priority: P3

---
id: BUG-3707
type: BUG
title: scratch-pad-redirect.sh names files with the exiting hook's pid so the liveness
  guard is illusory
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T16:28:16Z'
relates_to:
- BUG-3705
---

# BUG-3707: scratch-pad-redirect.sh names files with the exiting hook's pid so the liveness guard is illusory

## Summary

`hooks/scripts/scratch-pad-redirect.sh` names redirect files `${SAFE_NAME}-$$.txt`, but `$$` is the PreToolUse hook process's own pid, which exits right after emitting its JSON. Every redirect file is therefore dead-pid on arrival, and `scratch-cleanup.sh`'s `kill -0` liveness guard protects nothing except via pid recycling. `verify_evidence.write_snapshot` has the same shape (pid of an exiting `ll-verify-evidence`). This is the root of BUG-3702 and why BUG-3705 needs an mtime age guard.

Fix on the writer side: emit a runtime `\$\$` inside the rewritten command (`NEW_CMD`) so the filename carries the pid of the shell running the command, making the liveness guard meaningful again.

**Unverified assumption**: Claude Code runs each Bash call in its own shell process for the command's lifetime — spike this before implementing (backgrounded/auto-backgrounded commands especially). Also check filename-shape compatibility with the pid parser in `scratch-cleanup.sh` (`${SAFE_NAME}-<pid>.txt`).

Found during the BUG-3705 pre-implementation review (Opus consult). Not a blocker for BUG-3705, which ships the age guard as the interim protection.


## Current Behavior

[If applicable - describe what currently happens]

## Expected Behavior

[What should happen instead]

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Status

**Open** | Created: [YYYY-MM-DD] | Priority: [P0-P5]

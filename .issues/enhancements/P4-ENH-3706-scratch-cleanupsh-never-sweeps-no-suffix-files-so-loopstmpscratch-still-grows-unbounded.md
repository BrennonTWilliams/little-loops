---
id: ENH-3706
type: ENH
title: scratch-cleanup.sh never sweeps no-suffix files so .loops/tmp/scratch still
  grows unbounded
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T16:28:16Z'
relates_to:
- BUG-3705
---

# ENH-3706: scratch-cleanup.sh never sweeps no-suffix files so .loops/tmp/scratch still grows unbounded

## Summary

At review time (2026-10-03), 2,764 of the 5,152 files in `.loops/tmp/scratch` (54%) had no `-<pid>` suffix. `hooks/scripts/scratch-cleanup.sh` skips them unconditionally (BUG-2525 contract: user-typed files are not owned by the sweep), so the directory grows without bound even after BUG-3705 makes the pid-file sweep complete.

Decide and implement a retention policy for no-suffix files — e.g. an age-based sweep with a much longer threshold than the pid-file guard (7d?), or an opt-in config knob — without reintroducing the BUG-2525 deletion of files a user or loop is still reading (`init-verify-*.txt`, `test-results.txt`).

Found during the BUG-3705 pre-implementation review (Opus consult). Depends on BUG-3705 landing first (shares the `find -mmin` enumeration).


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

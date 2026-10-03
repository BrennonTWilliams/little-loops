---
id: BUG-3705
type: BUG
title: scratch-cleanup.sh sweep exceeds its 5s hook timeout on large scratch dirs,
  leaving dead-pid files unswept
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-10-03'
captured_at: '2026-10-03T01:30:35Z'
---

# BUG-3705: scratch-cleanup.sh sweep exceeds its 5s hook timeout on large scratch dirs, leaving dead-pid files unswept

## Summary

`hooks/scripts/scratch-cleanup.sh` (SessionStart) has a 5s hook timeout (`hooks/hooks.json`) but sweeps `.loops/tmp/scratch` with one `kill -0` / `sed` / `rm` per file. With thousands of dead-pid files the hook is killed part-way through the glob, so dead-pid files late in the sort order are never swept and the directory grows without bound. Found while reviewing BUG-3702.

## Current Behavior

At review time (2026-10-02) `.loops/tmp/scratch` held 5,143 files. The sweep iterates `"$SCRATCH_DIR"/*` in alphabetical order and spawns `basename`/`sed` subprocesses per file; once the 5s timeout kills the hook, the remaining files survive. Each later session repeats the same prefix of the sweep.

## Expected Behavior

The sweep completes within the timeout regardless of directory size (or makes monotonic progress across sessions), so dead-pid files do not accumulate.

## Proposed Solution

Replace the per-file subprocess spawns with shell-builtin parsing (parameter expansion instead of `basename`/`sed`) and/or a single `find`-based pass; optionally bound runtime and sweep oldest-first so partial runs still make progress. Add a test with a few thousand synthetic dead-pid files asserting the hook finishes under the timeout and removes them.

## Impact

- **Priority**: P3 - unbounded scratch growth; also made BUG-3702's snapshot loss intermittent
- **Effort**: Small
- **Risk**: Low - must keep the BUG-2525 contract (files without a `-<pid>` suffix and live-pid files are preserved)

## Acceptance Criteria

- [ ] `scratch-cleanup.sh` removes all dead-pid files from a 5,000-file directory within the hook timeout
- [ ] Files without a `-<pid>` suffix and files owned by a live pid are still preserved
- [ ] `python -m pytest scripts/tests/` exits 0

## Status

**Open** | Created: 2026-10-03 | Priority: P3

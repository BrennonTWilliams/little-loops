---
id: BUG-3392
type: BUG
title: 'll-issues show: derived ''Superseded by'' row hidden when superseding issue
  is deferred/done/cancelled'
priority: P4
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-05'
captured_at: '2026-09-05T23:53:50Z'
---

# BUG-3392: ll-issues show: derived 'Superseded by' row hidden when superseding issue is deferred/done/cancelled

## Summary

[Description extracted from input]

## Current Behavior

`ll-issues show <cancelled-issue>` omits the derived `Superseded by` row when the superseding issue is `deferred` (or `done`/`cancelled`). `scripts/little_loops/cli/issues/show.py` (~line 281) calls `find_issues(config)` with the default status filter, which hides done/cancelled/deferred issues, so `superseded_by(issue_id, _all)` never sees the superseding issue's `supersedes` list.

Repro: FEAT-3388 (`status: deferred`, `supersedes: [FEAT-3385]`) → `ll-issues show FEAT-3385` shows `Cancellation reason: superseded` but no `Superseded by: FEAT-3388` row.

## Expected Behavior

The reverse `Superseded by` edge renders regardless of the superseding issue's status. Supersession is a permanent record; the replacement being deferred or already done should not hide it.

## Proposed Solution

In `show.py`, load the issue list for the supersession/parent lookup with an all-statuses filter (e.g. `find_issues(config, status_filter={"open","in_progress","blocked","deferred","done","cancelled"})`) instead of the default. Add a test in the `ll-issues show` test module: cancelled issue A, deferred issue B with `supersedes: [A]`, assert `Superseded by: B` appears in `show A` output.

## Impact

- **Priority**: [P0-P5] - [Justification]
- **Effort**: [Small/Medium/Large] - [Justification]
- **Risk**: [Low/Medium/High] - [Justification]
- **Breaking Change**: [Yes/No]

## Acceptance Criteria

- [ ] `ll-issues show` renders `Superseded by` when the superseding issue is deferred, done, or cancelled
- [ ] Regression test covering the deferred-superseder case
- [ ] `python -m pytest scripts/tests/` passes

## Status

**Open** | Created: 2026-09-05 | Priority: P4

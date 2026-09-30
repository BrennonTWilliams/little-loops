---
id: BUG-3688
type: BUG
title: Brainstorm loop reports success on a zero-idea run
priority: P3
status: open
discovered_by: ll-issues-create
discovered_date: '2026-09-30'
captured_at: '2026-09-30T05:35:56Z'
labels:
- loops
- brainstorm
relates_to:
- EPIC-3581
- FEAT-3582
---

# BUG-3688: Brainstorm loop reports success on a zero-idea run

## Summary

The shipped `brainstorm` loop can finish `done` with **zero ideas**: `verify_artifacts` only checks that `brainstorm.md` is non-empty, and `converge` writes an honest "No synthesis produced" report that passes it. The 2026-07-01 run (`.loops/runs/brainstorm-20260701T202115`) produced 0 ideas (`lenses.txt` still held all 9 lenses, no `diverge` calls) and still succeeded, and sinks (`file`/`issue`/`decision`) can execute on it.

## Current Behavior

`verify_artifacts` only checks that `brainstorm.md` is non-empty, so a zero-idea run finishes `done` and sinks can execute.

## Expected Behavior

`verify_artifacts` (and the sinks' entry) fail the run to `finalize_failed` when `ideas.jsonl` is missing or has no valid idea rows. Minimal hotfix on the old loop, independent of the EPIC-3581 rewrite (whose `check_floors` / `validate_portfolio` supersede it); the rewrite may delete this check. Every little-loops project on this machine is `local-editable`, so the silent success stays live until FEAT-3582 lands.

## Impact

- **Priority**: P3 - silent success on an empty run, small blast radius
- **Effort**: Small - one added check in `verify_artifacts` plus a fixture
- **Risk**: Low - fails a run that has no ideas; nothing else changes
- **Breaking Change**: No

## Acceptance Criteria

- A run whose `ideas.jsonl` is empty or absent routes to `failed`, and no sink executes (fixture in `scripts/tests/test_brainstorm.py`, extending the existing `verify_artifacts` tests).
- Existing brainstorm tests stay green.

## Status

**Open** | Created: 2026-09-30 | Priority: P3

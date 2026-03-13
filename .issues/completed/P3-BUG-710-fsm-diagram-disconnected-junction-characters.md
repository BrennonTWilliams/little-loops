---
discovered_date: 2026-03-13
discovered_by: manual
---

# BUG-710: FSM diagram renderer produces disconnected box-drawing junction characters

## Summary

The FSM box diagram renderer in `layout.py` produces disconnected-looking patterns where horizontal and vertical lines cross or pass through corner characters without upgrading them to proper junction characters. For example, `─┘─` appears instead of `─┴─`, and `─│` appears instead of `─┼─`.

## Current Behavior

Running `ll-loop s issue-refinement` shows broken junctions at multi-branch rows:

```
┌─success───┘───────────────┐ fail    ← ┘ should be ┴
┌─success───────────────────┘──────│ fail  ← ┘ should be ┴, │ should be ┼
```

## Expected Behavior

Junction characters should be upgraded when lines cross existing box-drawing characters:

```
┌─success───┴───────────────┐ fail    ← ┴ shows horizontal passes through
┌─success───────────────────┴──────┼ fail  ← both junctions connected
```

## Root Cause

- **File**: `scripts/little_loops/cli/loop/layout.py`
- **Cause**: Three code paths unconditionally place characters without checking for existing box-drawing characters:
  1. **Gap-fill post-pass** (~line 990): Only fills spaces with `─`, skipping corners (`┘`, `└`, `┐`, `┌`) and pipes (`│`) that should be upgraded to junctions (`┴`, `┬`, `┼`).
  2. **Right-margin vertical pipe** (~line 1173): Unconditionally writes `│`, overwriting existing `─` characters instead of creating `┼` junctions.
  3. **Left-margin vertical pipe** (~line 1079): Same unconditional `│` placement as right margin.

## Proposed Solution

Add collision detection at all three sites to upgrade characters to appropriate junction types when lines cross.

## Integration Map

### Files to Modify
- `scripts/little_loops/cli/loop/layout.py` — gap-fill post-pass, left-margin vertical pipe, right-margin vertical pipe

### Tests
- `scripts/tests/test_ll_loop_display.py` — existing tests (88 passed)

## Implementation Steps

1. In gap-fill post-pass: when encountering `│` upgrade to `┼`, `┘`/`└` to `┴`, `┐`/`┌` to `┬`
2. In left-margin vertical pipe: when encountering `─` upgrade to `┼`, only place `│` on spaces
3. In right-margin vertical pipe: same collision detection as left margin

## Impact

- **Priority**: P3 - Visual rendering bug, no functional impact
- **Effort**: Small - Three targeted edits in one file
- **Risk**: Low - Display-only change, no execution logic affected
- **Breaking Change**: No

## Blocked By

_None_

## Blocks

_None_

## Labels

`bug`, `cli`, `loop`, `display`

## Resolution

- **Action**: fix
- **Completed**: 2026-03-13
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/loop/layout.py` (~line 990): Gap-fill post-pass now upgrades corner characters (`┘`/`└` → `┴`, `┐`/`┌` → `┬`) and pipes (`│` → `┼`) instead of only filling spaces
- `scripts/little_loops/cli/loop/layout.py` (~line 1079): Left-margin vertical pipe now detects `─` and upgrades to `┼` instead of unconditionally writing `│`
- `scripts/little_loops/cli/loop/layout.py` (~line 1173): Right-margin vertical pipe same collision detection as left margin

### Verification Results
- Tests: PASS (88 passed in test_ll_loop_display.py)
- Visual: Confirmed correct junction characters in `ll-loop s issue-refinement`

## Session Log
- manual fix - 2026-03-13 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/75af90b9-9ad6-4426-ac11-89a956fbe91f.jsonl`

---

## Status

**Completed** | Created: 2026-03-13 | Completed: 2026-03-13 | Priority: P3

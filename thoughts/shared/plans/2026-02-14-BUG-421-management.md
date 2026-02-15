# BUG-421: Fix TOCTOU file deletion race in _move_issue_to_completed()

## Issue Summary

Three `if path.exists(): path.unlink()` TOCTOU race conditions in `_move_issue_to_completed()` can cause `FileNotFoundError` during parallel processing.

## Research Findings

- **Primary target**: `scripts/little_loops/issue_lifecycle.py` lines 302-303, 321-322, 331-332
- **Secondary target**: `scripts/little_loops/parallel/orchestrator.py` line 1085-1086 (same pattern)
- **Fix**: Replace `if path.exists(): path.unlink()` with `path.unlink(missing_ok=True)`
- **Tests**: `scripts/tests/test_issue_lifecycle.py` has `TestMoveIssueToCompleted` class (lines 265-435)

## Implementation Plan

### Phase 1: Fix issue_lifecycle.py (3 locations)

Replace all three TOCTOU patterns in `_move_issue_to_completed()`:

1. **Line 302-303** (destination already exists branch): `if original_path.exists(): original_path.unlink()` → `original_path.unlink(missing_ok=True)`
2. **Line 321-322** (git mv fallback branch): Same replacement
3. **Line 331-332** (untracked source branch): Same replacement

### Phase 2: Fix orchestrator.py (1 location)

Replace TOCTOU pattern in `_complete_issue_lifecycle_if_needed()`:

1. **Line 1085-1086**: `if original_path.exists(): original_path.unlink()` → `original_path.unlink(missing_ok=True)`

### Phase 3: Add concurrent deletion test

Add test to `test_issue_lifecycle.py` that simulates the race condition:
- Delete `original_path` between function entry and unlink call
- Verify no `FileNotFoundError` is raised

### Phase 4: Verification

- [x] `python -m pytest scripts/tests/`
- [ ] `ruff check scripts/`
- [ ] `python -m mypy scripts/little_loops/`

## Success Criteria

- [ ] All three TOCTOU patterns in `_move_issue_to_completed()` replaced
- [ ] Orchestrator TOCTOU pattern replaced
- [ ] Concurrent deletion test added and passing
- [ ] All existing tests pass
- [ ] Lint and type checks pass

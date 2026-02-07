# BUG-234: Issue number collision when pulling from GitHub - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-234-issue-number-collision-pulling-from-github.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

`GitHubSyncManager._get_next_issue_number()` at `sync.py:703-713` delegates to `_get_local_issues()` at `sync.py:325-345`, which only includes the completed directory when `sync_completed` is `True` (default: `False`). This means pulled issues can receive IDs that collide with completed issues.

Meanwhile, `get_next_issue_number()` at `issue_parser.py:37-73` already correctly scans ALL directories (active + completed) and provides globally unique numbering.

### Key Discoveries
- `sync.py` does not import from `issue_parser` at all (line 1-18)
- `issue_lifecycle.py:19` already imports and uses `get_next_issue_number` from `issue_parser`
- The call site is `sync.py:665` inside `_create_local_issue()`
- `issue_parser.get_next_issue_number()` provides global uniqueness across all types (BUG, FEAT, ENH), which matches the project's numbering model

## Desired End State

`_create_local_issue()` uses `get_next_issue_number()` from `issue_parser.py` instead of the private `_get_next_issue_number()` method. The private method is removed. Pulled issues never collide with completed issues.

### How to Verify
- New test: create completed issue with high number, pull new issue, verify no collision
- Existing tests updated to reflect new behavior (global numbering)
- All existing tests pass

## What We're NOT Doing

- Not changing `_get_local_issues()` — it's correctly scoped for its sync purpose (listing files to sync)
- Not modifying `issue_parser.get_next_issue_number()` — it already works correctly
- Not changing the `sync_completed` config behavior for sync listing

## Problem Analysis

Root cause: `_get_next_issue_number()` reuses `_get_local_issues()` which has a different purpose (listing files to sync) than what's needed here (finding the next safe number). The sync-scoping of `_get_local_issues()` is correct for sync operations, but wrong for number assignment.

## Solution Approach

Replace the private `_get_next_issue_number()` method with a call to the existing `get_next_issue_number()` from `issue_parser.py`. This eliminates duplicate logic and ensures completed issues are always considered.

## Implementation Phases

### Phase 1: Update sync.py

#### Overview
Import `get_next_issue_number` from `issue_parser`, replace the call site, and remove the private method.

#### Changes Required

**File**: `scripts/little_loops/sync.py`

1. Add import (inside `TYPE_CHECKING` is insufficient since it's called at runtime):
   ```python
   from little_loops.issue_parser import get_next_issue_number
   ```

2. Update call site at line 665, replacing:
   ```python
   next_num = self._get_next_issue_number(issue_type)
   ```
   with:
   ```python
   next_num = get_next_issue_number(self.config)
   ```

3. Remove `_get_next_issue_number()` method (lines 703-713)

### Phase 2: Update tests

#### Overview
Update existing test and add a new test for the collision scenario.

#### Changes Required

**File**: `scripts/tests/test_sync.py`

1. Update `test_get_next_issue_number` (line 486-497):
   - The test currently checks per-type numbering (BUG only, expects 6)
   - With global numbering, it should still return 6 since those are the only issues
   - But the method is now removed from the manager, so this test needs to verify the new behavior through `_create_local_issue()` or be replaced with a collision test

2. Add new test `test_get_next_issue_number_avoids_completed_collision`:
   - Create completed issue with high number (e.g., `P1-BUG-042-done.md` in completed/)
   - Create active issue with lower number (e.g., `P1-BUG-005-active.md` in bugs/)
   - Verify that pulling a new bug issue gets a number > 42

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_sync.py -v`
- [ ] All tests pass: `python -m pytest scripts/tests/ -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Existing `test_get_next_issue_number` updated to test through `_create_local_issue` or replaced with collision-aware test
- New test proving completed issues prevent number collision
- All existing sync tests continue to pass

## References

- Original issue: `.issues/bugs/P2-BUG-234-issue-number-collision-pulling-from-github.md`
- Buggy method: `scripts/little_loops/sync.py:703-713`
- Correct implementation: `scripts/little_loops/issue_parser.py:37-73`
- Existing usage pattern: `scripts/little_loops/issue_lifecycle.py:19`
- Existing test: `scripts/tests/test_sync.py:486-497`

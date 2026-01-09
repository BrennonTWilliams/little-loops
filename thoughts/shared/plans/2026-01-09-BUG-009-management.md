# BUG-009: git mv fails when destination exists - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P1-BUG-009-git-mv-fails-destination-exists.md`
- **Type**: bug
- **Priority**: P1
- **Action**: fix

## Current State Analysis

The `git mv` command fails during issue lifecycle completion because the destination file already exists. Research revealed two problematic code paths:

### Key Discoveries
1. **orchestrator.py:651-662** - Writes content to `completed_path` BEFORE attempting `git mv`, guaranteeing failure
2. **issue_lifecycle.py:136-152** - `_move_issue_to_completed()` attempts `git mv` without pre-checking if destination exists
3. The codebase has a good pattern at `issue_lifecycle.py:417-426` that checks `completed_path.exists()` before proceeding, but this check happens at the caller level, not in the helper function
4. The orchestrator's `_complete_issue_lifecycle_if_needed()` does check at line 609-611, but then writes the file at line 652 before the `git mv` at line 655

### Current Behavior
1. Orchestrator checks if `completed_path.exists()` (line 609) - returns early if true
2. Orchestrator reads content and prepares resolution section (lines 624-649)
3. Orchestrator writes content to `completed_path` (line 652) - **creates destination**
4. Orchestrator attempts `git mv` (line 655-658) - **fails because destination now exists**
5. Falls back to just unlinking source (line 662)

## Desired End State

Before attempting `git mv`, check if destination exists and handle gracefully:
- If destination exists and source exists: compare content, then just remove source
- If destination exists and differs: use destination (it's newer), remove source
- Only attempt `git mv` when destination does NOT exist

### How to Verify
- Run tests: `python -m pytest scripts/tests/test_issue_lifecycle.py -v`
- Run tests: `python -m pytest scripts/tests/test_orchestrator.py -v`
- Simulate scenario where destination exists before `git mv`

## What We're NOT Doing

- Not changing the fallback behavior when `git mv` fails for other reasons
- Not modifying the commit logic
- Not changing the resolution section format
- Not addressing BUG-007 (worktree file leaks) - that's a separate issue

## Problem Analysis

**Root Cause in orchestrator.py**:
The code writes content to destination BEFORE attempting `git mv`:
```python
# Line 652 - Creates destination
completed_path.write_text(content)

# Line 655-658 - git mv fails because destination exists
result = self._git_lock.run(
    ["mv", str(original_path), str(completed_path)],
    ...
)
```

**Root Cause in issue_lifecycle.py**:
The `_move_issue_to_completed()` helper doesn't check if destination exists. While callers like `complete_issue_lifecycle()` do check, there's a race condition if the file is created between the check and the move.

## Solution Approach

Apply the existing safe pattern from `close_issue()` and `complete_issue_lifecycle()`:
1. Check if destination exists BEFORE any file operations
2. If destination exists: skip `git mv`, just clean up source
3. Only write content and attempt `git mv` when destination doesn't exist
4. For `_move_issue_to_completed()`: add parameter to handle pre-existing destination

## Implementation Phases

### Phase 1: Fix orchestrator.py - Reorder write and git mv

#### Overview
Fix the order of operations in `_complete_issue_lifecycle_if_needed()` to attempt `git mv` before writing content.

#### Changes Required

**File**: `scripts/little_loops/parallel/orchestrator.py`
**Changes**: Reorder lines 651-662 to attempt `git mv` first, then write content

Current (broken):
```python
# Write to completed location
completed_path.write_text(content)

# Use git mv if possible
result = self._git_lock.run(
    ["mv", str(original_path), str(completed_path)],
    cwd=self.repo_path,
)

if result.returncode != 0:
    self.logger.warning(f"git mv failed for {issue_id}: {result.stderr}")
    original_path.unlink()
```

Fixed:
```python
# Use git mv if possible (before writing content)
result = self._git_lock.run(
    ["mv", str(original_path), str(completed_path)],
    cwd=self.repo_path,
)

if result.returncode != 0:
    # git mv failed (destination may exist or other error)
    self.logger.warning(f"git mv failed for {issue_id}: {result.stderr}")
    # Write content to destination (may overwrite existing)
    completed_path.write_text(content)
    # Remove source if it still exists
    if original_path.exists():
        original_path.unlink()
else:
    # git mv succeeded, write updated content
    completed_path.write_text(content)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/orchestrator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/orchestrator.py`

---

### Phase 2: Add test for destination-exists scenario

#### Overview
Add a test case that verifies correct handling when destination file already exists.

#### Changes Required

**File**: `scripts/tests/test_orchestrator.py`
**Changes**: Add test for `_complete_issue_lifecycle_if_needed` with pre-existing destination

```python
def test_complete_lifecycle_destination_exists(self, ...):
    """Test lifecycle completion when destination already exists."""
    # Setup: create both source and destination files
    # source has original content, destination has updated content
    # Call _complete_issue_lifecycle_if_needed
    # Verify: source is removed, destination content preserved, no error
```

#### Success Criteria

**Automated Verification**:
- [ ] New test passes: `python -m pytest scripts/tests/test_orchestrator.py -k "destination_exists" -v`
- [ ] All orchestrator tests pass: `python -m pytest scripts/tests/test_orchestrator.py -v`

---

### Phase 3: Fix _move_issue_to_completed helper

#### Overview
Update the `_move_issue_to_completed()` helper to handle pre-existing destination files gracefully.

#### Changes Required

**File**: `scripts/little_loops/issue_lifecycle.py`
**Changes**: Add destination existence check in `_move_issue_to_completed()`

```python
def _move_issue_to_completed(
    original_path: Path,
    completed_path: Path,
    content: str,
    logger: Logger,
) -> bool:
    """Move issue file to completed dir, preferring git mv for history.
    ...
    """
    # Handle pre-existing destination (e.g., from parallel worker or leak)
    if completed_path.exists():
        logger.info(f"Destination already exists: {completed_path.name}")
        # Update content and remove source
        completed_path.write_text(content)
        if original_path.exists():
            original_path.unlink()
        return True

    result = subprocess.run(
        ["git", "mv", str(original_path), str(completed_path)],
        capture_output=True,
        text=True,
    )
    # ... rest unchanged
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_lifecycle.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_lifecycle.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/issue_lifecycle.py`

---

### Phase 4: Add test for _move_issue_to_completed with existing destination

#### Overview
Add test coverage for the new destination-exists handling in `_move_issue_to_completed()`.

#### Changes Required

**File**: `scripts/tests/test_issue_lifecycle.py`
**Changes**: Add test case for pre-existing destination

```python
def test_move_issue_destination_exists(self, tmp_path: Path, mock_logger: MagicMock) -> None:
    """Test _move_issue_to_completed when destination already exists."""
    original = tmp_path / "bugs" / "issue.md"
    completed = tmp_path / "completed" / "issue.md"
    original.parent.mkdir(parents=True, exist_ok=True)
    completed.parent.mkdir(parents=True, exist_ok=True)

    # Both files exist
    original.write_text("Original content")
    completed.write_text("Older content in destination")

    new_content = "Updated content with resolution"

    # No subprocess call should be made since we skip git mv
    result = _move_issue_to_completed(original, completed, new_content, mock_logger)

    assert result is True
    assert completed.exists()
    assert completed.read_text() == new_content  # Updated with new content
    assert not original.exists()  # Source removed
    mock_logger.info.assert_called()  # Logged the skip
```

#### Success Criteria

**Automated Verification**:
- [ ] New test passes: `python -m pytest scripts/tests/test_issue_lifecycle.py -k "destination_exists" -v`
- [ ] All issue_lifecycle tests pass: `python -m pytest scripts/tests/test_issue_lifecycle.py -v`

---

## Testing Strategy

### Unit Tests
- Test `_move_issue_to_completed()` with destination already exists
- Test `_complete_issue_lifecycle_if_needed()` with destination already exists
- Verify source file is properly cleaned up
- Verify content is written to destination

### Edge Cases
- Destination exists, source exists: should update destination, remove source
- Destination exists, source gone: should update destination only
- Neither exists: error case (not applicable here)

## References

- Original issue: `.issues/bugs/P1-BUG-009-git-mv-fails-destination-exists.md`
- Similar safe pattern: `issue_lifecycle.py:349-358` (close_issue)
- Similar safe pattern: `issue_lifecycle.py:417-426` (complete_issue_lifecycle)
- Problematic code: `orchestrator.py:651-662`
- Problematic code: `issue_lifecycle.py:136-152`

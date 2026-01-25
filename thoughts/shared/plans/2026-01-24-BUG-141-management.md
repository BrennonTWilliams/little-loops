# BUG-141: .claude/ll-context-state.json deletions not excluded from stash - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P3-BUG-141-context-state-json-not-excluded-from-stash.md`
- **Type**: bug
- **Priority**: P3
- **Action**: fix

## Current State Analysis

The `_stash_local_changes()` method in `merge_coordinator.py:125-217` handles stashing uncommitted tracked changes before merge operations. It has explicit exclusions for:

1. **State file** (line 173-174): `if file_path == state_file_str or file_path.endswith(state_file_name)`
2. **Lifecycle file moves** (line 167-169): Detects renames to completed directory
3. **Files in completed directory** (lines 177-184): Checks for `.issues/completed/` paths

### Key Discoveries
- The exclusion logic is applied per-file in a loop iterating over `git status --porcelain` output at `merge_coordinator.py:162-186`
- The `.claude/ll-context-state.json` file is managed by Claude Code, not the orchestrator
- This file frequently appears as deleted (`D` status) during Claude operations
- Including it in stash causes unnecessary stash/restore cycling with no benefit

## Desired End State

The `_stash_local_changes()` method should exclude `.claude/ll-context-state.json` from stashing, since:
1. It's Claude Code internal state, not project code
2. It's frequently modified/deleted during Claude operations
3. Including it causes unnecessary stash cycling
4. It has no bearing on the merge outcome

### How to Verify
- Run tests to confirm exclusion works: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- The new test should verify that `.claude/ll-context-state.json` is NOT stashed while other modified files ARE stashed

## What We're NOT Doing

- **Not excluding all `.claude/` directory files** - The issue proposes this as an alternative, but that's broader scope. We'll do the minimal fix targeting the specific problematic file.
- **Not modifying other stash-related code** - Only the exclusion logic in `_stash_local_changes()`
- **Not adding configuration for this exclusion** - It's a fixed internal file, not user-configurable

## Problem Analysis

The root cause is that `.claude/ll-context-state.json` was not considered when the exclusion logic was written. The existing exclusions target orchestrator-managed files (state file, lifecycle moves, completed directory), but this Claude Code-managed file was missed.

## Solution Approach

Add a simple exclusion check for files ending with `ll-context-state.json`, following the existing pattern used for the state file exclusion. This is consistent with how similar exclusions are implemented (e.g., line 173-174).

## Implementation Phases

### Phase 1: Add Exclusion Logic

#### Overview
Add exclusion for `.claude/ll-context-state.json` in the `_stash_local_changes()` method.

#### Changes Required

**File**: `scripts/little_loops/parallel/merge_coordinator.py`
**Changes**: Add exclusion check after line 184 (after the completed directory check), before line 185 where files are added to the lists.

```python
# Skip Claude Code context state file - managed externally
if file_path.endswith("ll-context-state.json"):
    self.logger.debug(f"Skipping Claude context state file from stash: {file_path}")
    continue
```

Also update the docstring at lines 132-135 to include this new exclusion:

```python
The following are explicitly excluded from stashing:
1. State file - managed by orchestrator and continuously updated
2. Lifecycle file moves - issue files being moved to completed/ directory
3. Files in completed directory - lifecycle-managed files
4. Claude Code context state file - managed by Claude Code externally
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -v`
- [ ] Lint passes: `ruff check scripts/little_loops/parallel/merge_coordinator.py`
- [ ] Types pass: `python -m mypy scripts/little_loops/parallel/merge_coordinator.py`

---

### Phase 2: Add Unit Test

#### Overview
Add a test that verifies `.claude/ll-context-state.json` is excluded from stashing while other files are included.

#### Changes Required

**File**: `scripts/tests/test_merge_coordinator.py`
**Changes**: Add a new test method in the `TestStashLocalChanges` class (after `test_excludes_state_file_from_stash` around line 489)

```python
def test_excludes_claude_context_state_file_from_stash(
    self,
    default_config: ParallelConfig,
    mock_logger: MagicMock,
    temp_git_repo: Path,
) -> None:
    """Should exclude Claude context state file from stash.

    The .claude/ll-context-state.json file is managed by Claude Code and
    frequently appears as deleted during operations. Stashing it causes
    unnecessary stash/restore cycling with no benefit to merge operations.
    """
    coordinator = MergeCoordinator(default_config, mock_logger, temp_git_repo)

    # Create .claude directory and context state file as tracked
    claude_dir = temp_git_repo / ".claude"
    claude_dir.mkdir(exist_ok=True)
    context_state_file = claude_dir / "ll-context-state.json"
    context_state_file.write_text('{"session": "initial"}')
    subprocess.run(["git", "add", ".claude/"], cwd=temp_git_repo, capture_output=True)
    subprocess.run(
        ["git", "commit", "-m", "add claude context state"],
        cwd=temp_git_repo,
        capture_output=True,
    )

    # Modify both the context state file and another tracked file
    context_state_file.write_text('{"session": "modified"}')
    test_file = temp_git_repo / "test.txt"
    test_file.write_text("modified content")

    result = coordinator._stash_local_changes()

    # Should stash the test.txt but NOT the context state file
    assert result is True
    assert coordinator._stash_active is True

    # test.txt should be reverted (stashed)
    assert test_file.read_text() == "initial content"

    # Context state file should NOT be reverted (excluded from stash)
    assert context_state_file.read_text() == '{"session": "modified"}'
```

#### Success Criteria

**Automated Verification**:
- [ ] New test passes: `python -m pytest scripts/tests/test_merge_coordinator.py::TestStashLocalChanges::test_excludes_claude_context_state_file_from_stash -v`
- [ ] All stash-related tests pass: `python -m pytest scripts/tests/test_merge_coordinator.py -k "stash" -v`
- [ ] Full test suite passes: `python -m pytest scripts/tests/test_merge_coordinator.py -v`

---

## Testing Strategy

### Unit Tests
- Test that `.claude/ll-context-state.json` is excluded from stash (new test)
- Verify existing tests still pass (state file exclusion, completed directory exclusion)

### Edge Cases Covered
- File at `.claude/ll-context-state.json` (standard path)
- The `endswith()` check handles the file regardless of whether path is relative or absolute

## References

- Original issue: `.issues/bugs/P3-BUG-141-context-state-json-not-excluded-from-stash.md`
- Related pattern: `merge_coordinator.py:173-174` (state file exclusion)
- Related test: `test_merge_coordinator.py:450-488` (state file exclusion test)

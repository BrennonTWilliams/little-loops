# ENH-131: Extend git_operations test coverage - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P2-ENH-131-git-operations-test-coverage.md
- **Type**: enhancement
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The `get_untracked_files()` function at `scripts/little_loops/git_operations.py:286-324` parses git porcelain output to extract untracked files. It:
- Runs `git status --porcelain` in the specified repo directory
- Parses lines starting with `??` (untracked file marker)
- Handles quoted filenames (spaces in names)
- Returns sorted list of untracked file paths
- Returns empty list on git command failure

### Key Discoveries
- Function location: `scripts/little_loops/git_operations.py:286-324`
- Existing test patterns: `scripts/tests/test_subprocess_mocks.py` uses `patch("subprocess.run")` for mocking
- Similar tests: `TestCheckGitStatus` class mocks subprocess for git commands

## Desired End State

Comprehensive test coverage for `get_untracked_files()` including:
- Normal operation with multiple untracked files
- Files with spaces (quoted in porcelain output)
- Empty repository case
- Git command failure handling
- Mixed status output (only `??` lines should be extracted)

### How to Verify
- Run `pytest scripts/tests/test_git_operations.py -v`
- All tests pass
- Coverage of `get_untracked_files()` function is complete

## What We're NOT Doing

- Not refactoring existing code
- Not adding tests for already-tested functions
- Not creating a real git repository (mocking subprocess instead)

## Solution Approach

Add a new test class `TestGetUntrackedFiles` to a new test file `scripts/tests/test_git_operations.py` (keeping test organization clean). Use subprocess mocking pattern from existing tests.

## Implementation Phases

### Phase 1: Create Test File with `get_untracked_files` Tests

#### Overview
Create new test file with comprehensive coverage for `get_untracked_files()`.

#### Changes Required

**File**: `scripts/tests/test_git_operations.py`
**Changes**: Create new file with test class

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_git_operations.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_git_operations.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_git_operations.py`

## Testing Strategy

### Unit Tests
- `test_returns_empty_list_when_no_untracked_files` - Empty porcelain output
- `test_returns_untracked_files` - Normal case with multiple files
- `test_handles_files_with_spaces` - Quoted filenames with spaces
- `test_handles_special_characters` - Files with special chars
- `test_ignores_non_untracked_status` - Only `??` lines are extracted
- `test_returns_empty_on_git_failure` - CalledProcessError handling
- `test_returns_empty_on_file_not_found` - git not found handling
- `test_returns_sorted_files` - Output is alphabetically sorted
- `test_uses_correct_cwd` - Verifies repo_root is used as cwd

## References

- Original issue: `.issues/enhancements/P2-ENH-131-git-operations-test-coverage.md`
- Similar tests: `scripts/tests/test_subprocess_mocks.py:154-222`
- Target function: `scripts/little_loops/git_operations.py:286-324`

# P2-ENH-131: Extend git_operations test coverage

## Summary

The `git_operations.py` module (600 lines) has **partial test coverage**. Most functions are tested across multiple test files, but `get_untracked_files()` lacks direct test coverage.

## Current State

- **Module**: `scripts/little_loops/git_operations.py`
- **Lines**: 600
- **Test files** (coverage spread across multiple files):
  - `scripts/tests/test_gitignore_suggestions.py` - Tests gitignore functions (414 lines)
  - `scripts/tests/test_subprocess_mocks.py` - Tests `check_git_status()` (lines 154-222)
  - `scripts/tests/test_work_verification.py` - Tests `filter_excluded_files()` and `verify_work_was_done()` from `work_verification.py` module (duplicate implementation)
- **Coverage**: ~70% (most functions tested except `get_untracked_files()`)

## Risk

- `get_untracked_files()` lacks test coverage - could incorrectly parse git output
- Code duplication between `git_operations.py` and `work_verification.py` could cause divergence

## Required Test Coverage

### Currently Untested Functions

1. **`get_untracked_files()`** - Line 286 in `git_operations.py`
   - Parses git porcelain output correctly
   - Handles files with spaces
   - Handles special characters
   - Empty repository case
   - Git command failure handling

### Already Tested Functions (no action needed)

1. **`check_git_status()`** - Tested in `test_subprocess_mocks.py:154-222`
   - Clean working directory detection ✓
   - Staged changes detection ✓
   - Unstaged changes detection ✓
   - Correct git commands verified ✓

2. **`verify_work_was_done()`** - Tested in `test_work_verification.py:146-455`
   - Detects file modifications ✓
   - Only excluded files detection ✓
   - Git-based detection ✓
   - Exception handling ✓

3. **`filter_excluded_files()`** - Tested in `test_work_verification.py:52-143`
   - Directory pattern matching ✓
   - Nested directory exclusions ✓
   - Edge cases with similar prefixes ✓
   - Empty list handling ✓

4. **Gitignore functions** - Tested in `test_gitignore_suggestions.py` (414 lines)
   - All pattern matching functions ✓
   - Suggestion generation ✓
   - Negation pattern support ✓

### Edge Cases for get_untracked_files

- Repository with no commits
- Files with spaces in names
- Files with special characters
- Empty git output

## Acceptance Criteria

- [x] Add tests for `get_untracked_files()` in `scripts/tests/test_gitignore_suggestions.py` (or new file)
- [x] Cover edge cases: files with spaces, special characters, empty output
- [x] Achieve >85% line coverage for `git_operations.py`

## Technical Notes

- Use temporary git repositories for tests (like `test_gitignore_suggestions.py`)
- Mock subprocess for `get_untracked_files()` tests
- Consider consolidating duplicate code in `git_operations.py` and `work_verification.py`

## Dependencies

None

## Labels

`testing`, `git`

## Anchor

Function: `get_untracked_files` in `scripts/little_loops/git_operations.py`

---

## Resolution

- **Action**: implement
- **Completed**: 2026-01-23
- **Status**: Completed

### Changes Made
- `scripts/tests/test_git_operations.py`: Created new test file with 17 comprehensive tests for `get_untracked_files()`

### Tests Added
- `test_returns_empty_list_when_no_untracked_files`
- `test_returns_untracked_files`
- `test_handles_files_with_spaces`
- `test_handles_special_characters`
- `test_ignores_non_untracked_status`
- `test_returns_empty_on_git_failure`
- `test_returns_empty_on_file_not_found`
- `test_returns_sorted_files`
- `test_uses_correct_cwd`
- `test_handles_empty_lines_in_output`
- `test_default_repo_root`
- `test_correct_git_command`
- `test_various_outputs` (parametrized: empty, single, multiple, quoted, modified_only)

### Verification Results
- Tests: PASS (17/17)
- Lint: PASS
- Types: PASS

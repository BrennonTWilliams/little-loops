# ENH-003: Improve issue_lifecycle.py Test Coverage

## Summary

The `issue_lifecycle.py` module has only 13% test coverage. This module handles critical issue state transitions including closing, completing, and creating new issues from failures.

## Current State

- **Coverage**: 13% (119 of 137 statements missing)
- **Module**: `scripts/little_loops/issue_lifecycle.py`

### Uncovered Functions

| Function | Lines | Description |
|----------|-------|-------------|
| `_build_closure_resolution()` | 33 | Build resolution markdown for closed issues |
| `_build_completion_resolution()` | 59 | Build resolution markdown for completed issues |
| `_prepare_issue_content()` | 91-94 | Read and append resolution section |
| `_cleanup_stale_source()` | 110-112 | Remove orphaned files |
| `_move_issue_to_completed()` | 136-152 | Git mv with fallback |
| `_commit_issue_completion()` | 173-201 | Stage and commit changes |
| `verify_issue_completed()` | 215-230 | Verify issue in completed dir |
| `create_issue_from_failure()` | 250-318 | Auto-create bug from failure |
| `close_issue()` | 343-391 | Close issue with status |
| `complete_issue_lifecycle()` | 411-454 | Fallback completion |

## Proposed Tests

### Unit Tests

1. **Resolution Building**
   - Test `_build_closure_resolution()` output format
   - Test `_build_completion_resolution()` with different actions
   - Test date formatting

2. **Content Manipulation**
   - Test `_prepare_issue_content()` appends resolution
   - Test idempotency when resolution already exists

3. **Issue Verification**
   - Test `verify_issue_completed()` with issue in completed
   - Test with issue in both locations (warning case)
   - Test with issue deleted but not moved

4. **Issue Creation**
   - Test `create_issue_from_failure()` generates valid markdown
   - Test error message extraction
   - Test directory creation

### Integration Tests (with temp directories)

1. **Full Close Flow**
   - Test `close_issue()` moves file correctly
   - Test git mv fallback behavior
   - Test stale state handling

2. **Full Complete Flow**
   - Test `complete_issue_lifecycle()` end-to-end
   - Test with command that exited early

## Implementation Approach

1. Use `tmp_path` fixture for filesystem operations
2. Mock `subprocess.run` for git commands
3. Create test fixtures for IssueInfo and BRConfig

## Impact

- **Priority**: P2 (Medium)
- **Effort**: Medium
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [x] Coverage for `issue_lifecycle.py` reaches 75%+
- [x] All new tests pass
- [x] No regressions in existing tests

## Labels

`enhancement`, `testing`, `coverage`, `lifecycle`

---

## Status

**Completed** | Created: 2025-01-05 | Priority: P2

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-05
- **Status**: Completed

### Changes Made
- `scripts/tests/test_issue_lifecycle.py`: Created comprehensive test suite with 35 tests covering:
  - Resolution building functions (`_build_closure_resolution`, `_build_completion_resolution`)
  - Content manipulation (`_prepare_issue_content`)
  - Git operations (`_cleanup_stale_source`, `_move_issue_to_completed`, `_commit_issue_completion`)
  - Issue verification (`verify_issue_completed`)
  - Issue creation from failure (`create_issue_from_failure`)
  - Full close flow (`close_issue`)
  - Full complete lifecycle flow (`complete_issue_lifecycle`)
- `thoughts/shared/plans/2026-01-05-ENH-003-management.md`: Implementation plan

### Verification Results
- Coverage: 97% (up from 13%)
- Tests: 35 new tests, all passing
- Full test suite: 367 tests passing
- Lint: PASS (ruff)
- Types: PASS (mypy)

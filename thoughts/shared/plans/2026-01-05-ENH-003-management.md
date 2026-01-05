# ENH-003: Improve issue_lifecycle.py Test Coverage - Management Plan

## Issue Reference
- **File**: .issues/enhancements/P2-ENH-003-improve-issue-lifecycle-test-coverage.md
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Problem Analysis
The `issue_lifecycle.py` module has only 13% test coverage (119 of 137 statements missing). This module handles critical issue state transitions including:
- Building resolution markdown sections
- Moving issues to completed directory
- Creating commits for issue completion
- Verifying issue completion status
- Creating new bug issues from failures
- Closing issues with status
- Full lifecycle completion fallback

## Solution Approach
Create comprehensive unit and integration tests following existing test patterns:
- Use `tmp_path` fixture for filesystem operations
- Mock `subprocess.run` for git commands (pattern from `test_subprocess_mocks.py`)
- Create test fixtures for IssueInfo and BRConfig
- Use MagicMock for Logger

## Implementation Phases

### Phase 1: Create Test File Structure
**Files**: `scripts/tests/test_issue_lifecycle.py`
**Changes**: Create new test file with imports and fixtures

### Phase 2: Unit Tests for Resolution Building
**Functions**:
- `_build_closure_resolution(close_status, close_reason)`
- `_build_completion_resolution(action)`
**Tests**:
- Verify markdown format output
- Verify date formatting
- Test different action/status values

### Phase 3: Unit Tests for Content Manipulation
**Functions**:
- `_prepare_issue_content(original_path, resolution)`
**Tests**:
- Test appending resolution to content
- Test idempotency (resolution already exists)

### Phase 4: Unit Tests for Git Operations
**Functions**:
- `_cleanup_stale_source(original_path, issue_id, logger)`
- `_move_issue_to_completed(original_path, completed_path, content, logger)`
- `_commit_issue_completion(info, commit_prefix, commit_body, logger)`
**Tests**:
- Test git mv success path
- Test git mv fallback to manual copy+delete
- Test commit success
- Test commit failure (nothing to commit)
- Test cleanup commits

### Phase 5: Unit Tests for Issue Verification
**Functions**:
- `verify_issue_completed(info, config, logger)`
**Tests**:
- Issue properly moved to completed
- Issue exists in both locations (warning)
- Issue deleted but not moved (warning)
- Issue not moved (warning)

### Phase 6: Unit Tests for Issue Creation
**Functions**:
- `create_issue_from_failure(error_output, parent_info, config, logger)`
**Tests**:
- Generates valid markdown
- Extracts error message from output
- Creates directory if needed
- Returns path on success
- Returns None on failure

### Phase 7: Integration Tests for Close Flow
**Functions**:
- `close_issue(info, config, logger, close_reason, close_status)`
**Tests**:
- Full close flow with git mv
- Close when already in completed
- Close with defaults
- Close failure handling

### Phase 8: Integration Tests for Complete Flow
**Functions**:
- `complete_issue_lifecycle(info, config, logger)`
**Tests**:
- Full complete flow
- Complete when already in completed
- Complete when source removed
- Complete failure handling

## Verification Plan
1. Run pytest with coverage: `python -m pytest scripts/tests/test_issue_lifecycle.py -v --cov=scripts/little_loops/issue_lifecycle --cov-report=term-missing`
2. Verify coverage >= 75%
3. Ensure all tests pass
4. Run full test suite to check for regressions

## Acceptance Criteria
- [ ] Coverage for `issue_lifecycle.py` reaches 75%+
- [ ] All new tests pass
- [ ] No regressions in existing tests

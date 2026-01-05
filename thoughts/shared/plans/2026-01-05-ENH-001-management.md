# ENH-001: Improve worker_pool.py Test Coverage - Management Plan

## Issue Reference
- **File**: .issues/enhancements/P2-ENH-001-improve-worker-pool-test-coverage.md
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Problem Analysis

The `worker_pool.py` module currently has only 27% test coverage (204 of 281 statements missing). This module is critical for parallel issue processing and includes:

1. **Worktree Management** - Git worktree creation, configuration copying, and cleanup
2. **Worker Lifecycle** - Pool start/shutdown, task submission, process tracking
3. **Issue Processing** - Full workflow from setup through Claude CLI invocation to cleanup
4. **Error Detection** - Main repo leak detection, verification of work done
5. **Process Management** - Subprocess tracking, termination on timeout/shutdown

Key uncovered areas by line range:
- Lines 83-94: Worker pool `start()` initialization
- Lines 105-138: Worktree setup and process termination
- Lines 154-165: Task submission and callback handling
- Lines 174-183: Completion handler
- Lines 194-355: Main `_process_issue()` workflow
- Lines 414-455: Model detection via API
- Lines 510-587: Claude command execution, changed files detection
- Lines 605-722: Leak detection and cleanup
- Lines 730-772: Baseline status and worktree cleanup

## Solution Approach

Create a comprehensive test file `test_worker_pool.py` with:
1. Unit tests using `unittest.mock` for isolated testing
2. Integration tests with temporary git repos
3. Tests organized by functionality area

## Implementation Phases

### Phase 1: Core Infrastructure Tests
**Files**: `scripts/tests/test_worker_pool.py`
**Changes**:
- Test `start()` creates worktree base directory and initializes executor
- Test `start()` is idempotent (calling twice is safe)
- Test `shutdown()` terminates executor
- Test `shutdown(wait=False)` calls `terminate_all_processes()`

### Phase 2: Worktree Management Tests
**Files**: `scripts/tests/test_worker_pool.py`
**Changes**:
- Test `_setup_worktree()` creates worktree with correct branch name
- Test `_setup_worktree()` copies git identity from main repo
- Test `_setup_worktree()` copies configured files (settings.local.json, .env)
- Test `_setup_worktree()` removes existing worktree if present
- Test `_cleanup_worktree()` removes worktree directory
- Test `_cleanup_worktree()` deletes parallel/* branches
- Test `_cleanup_worktree()` handles non-existent worktree gracefully

### Phase 3: Task Submission Tests
**Files**: `scripts/tests/test_worker_pool.py`
**Changes**:
- Test `submit()` raises RuntimeError if pool not started
- Test `submit()` returns Future and tracks in `_active_workers`
- Test `submit()` with callback invokes callback on completion
- Test `_handle_completion()` tracks pending callbacks
- Test `active_count` property includes running futures and pending callbacks

### Phase 4: Process Management Tests
**Files**: `scripts/tests/test_worker_pool.py`
**Changes**:
- Test `terminate_all_processes()` sends SIGTERM then SIGKILL
- Test `terminate_all_processes()` handles already-terminated processes
- Test process tracking during `_run_claude_command()`

### Phase 5: Issue Processing Tests (Integration)
**Files**: `scripts/tests/test_worker_pool.py`
**Changes**:
- Test `_process_issue()` creates correct branch name format
- Test `_process_issue()` returns failure result on ready_issue failure
- Test `_process_issue()` handles CLOSE verdict correctly
- Test `_process_issue()` handles NOT_READY verdict correctly
- Test `_process_issue()` returns success with changed files on success
- Test `_process_issue()` detects and cleans up leaked files
- Test `_process_issue()` verifies work was done

### Phase 6: Helper Method Tests
**Files**: `scripts/tests/test_worker_pool.py`
**Changes**:
- Test `_get_changed_files()` parses git diff output correctly
- Test `_verify_work_was_done()` accepts code changes
- Test `_verify_work_was_done()` rejects excluded-only changes
- Test `_detect_main_repo_leaks()` identifies leaked files
- Test `_cleanup_leaked_files()` handles tracked and untracked files
- Test `_get_main_repo_baseline()` captures current git status
- Test `cleanup_all_worktrees()` removes all worker-* directories

### Phase 7: Model Detection Tests
**Files**: `scripts/tests/test_worker_pool.py`
**Changes**:
- Test `_detect_worktree_model_via_api()` parses JSON response
- Test `_detect_worktree_model_via_api()` returns None on error
- Test `_detect_worktree_model_via_api()` handles timeout

## Verification Plan

1. Run `python -m pytest scripts/tests/test_worker_pool.py -v` for new tests
2. Run `python -m pytest scripts/tests/ -v` for all tests
3. Run coverage: `python -m pytest --cov=little_loops.parallel.worker_pool scripts/tests/test_worker_pool.py`
4. Verify coverage reaches 70%+
5. Run `ruff check scripts/` for linting
6. Run `python -m mypy scripts/little_loops/` for type checking

## Test Structure

```python
class TestWorkerPoolInit:
    """Tests for WorkerPool initialization."""

class TestWorkerPoolStartShutdown:
    """Tests for start() and shutdown() methods."""

class TestWorkerPoolWorktreeManagement:
    """Tests for _setup_worktree() and _cleanup_worktree()."""

class TestWorkerPoolTaskSubmission:
    """Tests for submit() and callback handling."""

class TestWorkerPoolProcessManagement:
    """Tests for process tracking and termination."""

class TestWorkerPoolProcessIssue:
    """Integration tests for _process_issue() workflow."""

class TestWorkerPoolHelpers:
    """Tests for helper methods (_get_changed_files, etc.)."""

class TestWorkerPoolModelDetection:
    """Tests for _detect_worktree_model_via_api()."""
```

## Dependencies

- pytest
- unittest.mock (patch, MagicMock)
- tempfile (TemporaryDirectory)
- subprocess (for mock targets)
- Existing fixtures from conftest.py

# ENH-004: Improve orchestrator.py Test Coverage - Management Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-004-improve-orchestrator-test-coverage.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Problem Analysis
The `orchestrator.py` module has only 40% test coverage (200 of 331 statements missing). This is the main controller for parallel issue processing and needs comprehensive tests to ensure reliability.

## Solution Approach
Create a new test file `test_orchestrator.py` following the existing test patterns from `test_worker_pool.py` and `test_merge_coordinator.py`. Use mocking extensively to isolate the orchestrator from its dependencies (WorkerPool, MergeCoordinator, IssuePriorityQueue).

## Implementation Phases

### Phase 1: Test Setup and Fixtures
**Files**: `scripts/tests/test_orchestrator.py`
**Changes**: Create fixtures for mocking dependencies

### Phase 2: Initialization Tests
**Coverage target**: Lines 53-94
**Tests**:
- Test `__init__` sets attributes correctly
- Test default repo_path is cwd
- Test components are initialized with shared git lock
- Test state initialization

### Phase 3: Signal Handler Tests
**Coverage target**: Lines 122-133, 229-232
**Tests**:
- Test `_setup_signal_handlers()` installs handlers
- Test `_restore_signal_handlers()` restores originals
- Test `_signal_handler()` sets shutdown flag

### Phase 4: Gitignore and Cleanup Tests
**Coverage target**: Lines 134-227
**Tests**:
- Test `_ensure_gitignore_entries()` adds missing entries
- Test `_ensure_gitignore_entries()` idempotent when entries exist
- Test `_cleanup_orphaned_worktrees()` removes orphaned worktrees

### Phase 5: State Management Tests
**Coverage target**: Lines 234-272
**Tests**:
- Test `_load_state()` creates new state when file doesn't exist
- Test `_load_state()` resumes from existing state
- Test `_save_state()` writes state to file
- Test `_cleanup_state()` removes state file

### Phase 6: Run Method Tests
**Coverage target**: Lines 95-120
**Tests**:
- Test `run()` orchestration flow
- Test `run()` handles KeyboardInterrupt
- Test `run()` handles exceptions
- Test dry_run mode

### Phase 7: Issue Scanning Tests
**Coverage target**: Lines 395-417
**Tests**:
- Test `_scan_issues()` finds issues
- Test `_scan_issues()` applies filters
- Test `_scan_issues()` respects max_issues

### Phase 8: Execute Loop Tests
**Coverage target**: Lines 322-393
**Tests**:
- Test `_execute()` main loop
- Test sequential P0 processing
- Test parallel processing
- Test max issues limit
- Test shutdown handling

### Phase 9: Result Handling Tests
**Coverage target**: Lines 455-530
**Tests**:
- Test `_on_worker_complete()` success path
- Test `_on_worker_complete()` failure path
- Test `_on_worker_complete()` close path
- Test `_merge_sequential()` for P0

### Phase 10: Completion and Reporting Tests
**Coverage target**: Lines 532-589
**Tests**:
- Test `_wait_for_completion()` timeout handling
- Test `_report_results()` output
- Test `_complete_issue_lifecycle_if_needed()`

### Phase 11: Cleanup Tests
**Coverage target**: Lines 702-716
**Tests**:
- Test `_cleanup()` saves state
- Test `_cleanup()` shuts down components
- Test `_cleanup()` cleans worktrees on success

## Verification Plan
- Run `python -m pytest scripts/tests/test_orchestrator.py -v` to verify all tests pass
- Run `python -m pytest --cov=little_loops.parallel.orchestrator scripts/tests/test_orchestrator.py` to check coverage
- Target: 65%+ coverage for orchestrator.py

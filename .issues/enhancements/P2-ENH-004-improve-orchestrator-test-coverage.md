# ENH-004: Improve orchestrator.py Test Coverage

## Summary

The `orchestrator.py` module has only 40% test coverage. This is the main controller for parallel issue processing, coordinating the priority queue, worker pool, and merge coordinator.

## Current State

- **Coverage**: 40% (200 of 331 statements missing)
- **Module**: `scripts/little_loops/parallel/orchestrator.py`

### Uncovered Areas

Key uncovered code sections (line numbers):
- `110-117`: Signal handler setup
- `152, 162, 171`: State loading/saving
- `188-223`: Main run loop initialization
- `231-232, 241-256`: Issue scanning and queue population
- `270-272, 288-289`: P0 sequential processing
- `328-393`: Worker dispatch and result handling
- `404, 415, 425-444`: Merge coordination
- `452-453, 462-494`: Result processing and state updates
- `505-530, 534-560`: Completion handling
- `568-589`: Statistics and summary
- `600-700`: Cleanup and shutdown

### Key Classes/Methods

| Method | Coverage | Description |
|--------|----------|-------------|
| `__init__()` | Partial | Component initialization |
| `run()` | Low | Main orchestration loop |
| `_setup_signal_handlers()` | None | SIGINT/SIGTERM handling |
| `_scan_issues()` | None | Issue discovery |
| `_process_p0_sequentially()` | None | Priority 0 handling |
| `_dispatch_workers()` | None | Parallel worker dispatch |
| `_handle_worker_result()` | None | Result processing |
| `_merge_completed_work()` | None | Merge coordination |
| `_print_summary()` | None | Final statistics |

## Proposed Tests

### Unit Tests

1. **Initialization**
   - Test component creation with various configs
   - Test default values

2. **State Management**
   - Test state save/load roundtrip
   - Test resume from saved state
   - Test state cleanup

3. **Issue Scanning**
   - Test `_scan_issues()` finds correct issues
   - Test priority filtering
   - Test category filtering
   - Test skip_ids filtering

4. **Result Handling**
   - Test `_handle_worker_result()` for success
   - Test for failure
   - Test for timeout

### Integration Tests (with mocks)

1. **Signal Handling**
   - Test graceful shutdown on SIGINT
   - Test state preservation on shutdown

2. **Full Run Simulation**
   - Mock worker pool and merge coordinator
   - Test full orchestration flow
   - Test P0 sequential mode
   - Test parallel worker dispatch

## Implementation Approach

1. Mock `WorkerPool`, `MergeCoordinator`, and `IssuePriorityQueue`
2. Use `tmp_path` for state file operations
3. Test signal handlers with `signal.raise_signal()`

## Dependencies

This issue may benefit from completing first:
- ENH-001 (worker_pool coverage)
- ENH-002 (work_verification coverage)

## Impact

- **Priority**: P2 (Medium)
- **Effort**: High
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [x] Coverage for `orchestrator.py` reaches 65%+ (achieved 83%)
- [x] All new tests pass (54 tests)
- [x] No regressions in existing tests (410 total tests pass)

## Labels

`enhancement`, `testing`, `coverage`, `parallel`, `orchestrator`

---

## Status

**Open** | Created: 2025-01-05 | Priority: P2

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-05
- **Status**: Completed

### Changes Made
- `scripts/tests/test_orchestrator.py`: Created comprehensive test suite with 54 tests covering:
  - Orchestrator initialization (5 tests)
  - Signal handler setup/restore (3 tests)
  - Gitignore entry management (3 tests)
  - Orphaned worktree cleanup (3 tests)
  - State management - load/save/cleanup (6 tests)
  - Run method and dry run mode (4 tests)
  - Issue scanning and filtering (3 tests)
  - Execute loop and shutdown handling (3 tests)
  - P0 sequential processing (1 test)
  - Worker completion callbacks (5 tests)
  - Merge coordination - sequential (3 tests)
  - Completion waiting and timeout (3 tests)
  - Results reporting (2 tests)
  - Issue lifecycle completion (3 tests)
  - Cleanup operations (4 tests)
  - Parallel worker dispatch (1 test)

- `thoughts/shared/plans/2026-01-05-ENH-004-management.md`: Implementation plan

### Verification Results
- Tests: PASS (54 new tests, 410 total)
- Lint: PASS (ruff check)
- Coverage: 83% (exceeded 65% target)

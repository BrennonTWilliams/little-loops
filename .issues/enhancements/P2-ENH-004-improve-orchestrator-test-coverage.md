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

- [ ] Coverage for `orchestrator.py` reaches 65%+
- [ ] All new tests pass
- [ ] No regressions in existing tests

## Labels

`enhancement`, `testing`, `coverage`, `parallel`, `orchestrator`

---

## Status

**Open** | Created: 2025-01-05 | Priority: P2

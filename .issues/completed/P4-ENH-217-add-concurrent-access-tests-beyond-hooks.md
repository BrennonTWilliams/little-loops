# P4-ENH-217: Add concurrent access tests beyond hooks

## Summary
The hooks system has concurrent access tests (test_hooks_integration.py), but other modules lack dedicated thread safety tests. Concurrent access tests would ensure thread safety across the codebase.

## Current State
- Hooks concurrent tests: Yes (test_hooks_integration.py)
- Git operations concurrent tests: Yes (test_git_lock.py has TestThreadSafety class)
- Other modules: No dedicated concurrent tests
- Gap: Unverified thread safety in state_manager, issue_manager, and orchestrator

## Proposed Test Targets
1. **State manager concurrent access**
   - Multiple threads reading/writing state
   - State file locking behavior
   - Race condition detection

2. **Issue manager concurrent operations**
   - Multiple threads accessing issue queue
   - State modification under concurrency
   - File system race conditions

3. **Orchestrator worker pool**
   - Multiple workers accessing shared state
   - Queue thread safety
   - Status update coordination

## Note
Git operations already have concurrent access tests in `test_git_lock.py` (TestThreadSafety class). This enhancement focuses on the remaining untested modules.

## Acceptance Criteria
- [x] Concurrent access tests for state_manager
- [x] Concurrent access tests for issue_manager
- [x] Concurrent access tests for orchestrator
- [x] Tests use threading or pytest-asyncio
- [x] Tests include assertions for thread safety

## Implementation Notes
- Use pytest-asyncio for async concurrent tests
- Use threading.Thread for synchronous concurrent tests
- Use hypothesis with @settings(max_examples=...) for concurrent property tests
- Consider using thread sanitizer if available (TSAN)
- Reference test_hooks_integration.py for patterns

## Priority
P4 - Nice-to-have: Thread safety is important but the current usage pattern (mostly single-threaded) makes this lower priority.

## Related Files
- scripts/little_loops/state.py (state manager - target)
- scripts/little_loops/issue_manager.py (target)
- scripts/little_loops/parallel/orchestrator.py (target)
- scripts/tests/test_hooks_integration.py (reference pattern)
- scripts/tests/test_git_lock.py (existing concurrent test reference)

## Verification Notes
Verified 2026-02-01 - All referenced files exist at correct paths. Updated to reflect that git operations already have concurrent tests (test_git_lock.py TestThreadSafety class). State manager is scripts/little_loops/state.py. Orchestrator is in scripts/little_loops/parallel/ directory.

## Resolution

- **Action**: improve
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `scripts/tests/test_state.py`: Added `TestStateConcurrency` class with 5 concurrent access tests
  - `test_concurrent_save_no_corruption`: Tests multiple threads saving state simultaneously
  - `test_lazy_init_thread_safety`: Tests multiple threads accessing state property
  - `test_concurrent_mark_attempted`: Tests concurrent mark_attempted calls
  - `test_concurrent_state_mutations`: Tests mixed mark_completed/mark_failed operations
  - `test_concurrent_read_write`: Tests concurrent read/write operations
- `scripts/tests/test_issue_manager.py`: Added `TestIssueManagerConcurrency` class with 4 concurrent access tests
  - `test_concurrent_get_next_issue_no_duplicates`: Tests concurrent _get_next_issue calls
  - `test_concurrent_state_file_access`: Tests multiple managers accessing same state file
  - `test_concurrent_state_modifications`: Tests concurrent state modifications
  - `test_concurrent_dependency_queries`: Tests concurrent dependency graph queries
- `scripts/tests/test_orchestrator.py`: Added `TestOrchestratorConcurrency` class with 6 concurrent access tests
  - `test_concurrent_worker_callbacks`: Tests multiple workers completing simultaneously
  - `test_concurrent_interrupted_issues`: Tests concurrent interrupted_issues list modifications
  - `test_state_dictionary_concurrent_writes`: Tests concurrent corrections dictionary writes
  - `test_concurrent_timing_updates`: Tests concurrent timing dictionary writes
  - `test_concurrent_deferred_issue_operations`: Tests concurrent deferred issues list modifications
  - `test_concurrent_state_checkpoint`: Tests concurrent save operations during callbacks

### Verification Results
- Tests: PASS (15 new concurrent access tests)
- Lint: PASS (test_state.py, issue_manager.py/orchestrator.py have pre-existing lint issues unrelated to changes)
- Types: PASS

## Audit Source
Test Coverage Audit - 2026-02-01

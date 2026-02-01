# P4-ENH-217: Add concurrent access tests beyond hooks

## Summary
The hooks system has concurrent access tests (test_hooks_integration.py), but other modules lack dedicated thread safety tests. Concurrent access tests would ensure thread safety across the codebase.

## Current State
- Hooks concurrent tests: Yes (test_hooks_integration.py)
- Other modules: No dedicated concurrent tests
- Gap: Unverified thread safety in critical modules

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

4. **Git operations under concurrency**
   - Multiple git operations in parallel
   - Worktree creation/deletion races
   - Lock file behavior

## Acceptance Criteria
- [ ] Concurrent access tests for state_manager
- [ ] Concurrent access tests for issue_manager
- [ ] Concurrent access tests for orchestrator
- [ ] Concurrent access tests for git operations
- [ ] Tests use threading or pytest-asyncio
- [ ] Tests include assertions for thread safety

## Implementation Notes
- Use pytest-asyncio for async concurrent tests
- Use threading.Thread for synchronous concurrent tests
- Use hypothesis with @settings(max_examples=...) for concurrent property tests
- Consider using thread sanitizer if available (TSAN)
- Reference test_hooks_integration.py for patterns

## Priority
P4 - Nice-to-have: Thread safety is important but the current usage pattern (mostly single-threaded) makes this lower priority.

## Related Files
- scripts/little_loops/state_manager.py (target)
- scripts/little_loops/issue_manager.py (target)
- scripts/little_loops/orchestrator.py (target)
- scripts/tests/test_hooks_integration.py (reference pattern)

## Audit Source
Test Coverage Audit - 2026-02-01

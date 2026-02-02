# P1-ENH-209: Improve orchestrator.py test coverage from 74% to 80%+

## Summary
The orchestrator module (scripts/little_loops/parallel/orchestrator.py) has 74% test coverage with 130 missing statements. This module coordinates parallel execution and manages worker lifecycles.

## Current State
- Coverage: 74% (130 missing statements)
- Location: scripts/little_loops/parallel/orchestrator.py
- Impact: Parallel execution orchestration and signal handling may have untested edge cases

## Targets for Improvement
1. **Signal handling** - SIGINT/SIGTERM graceful shutdown
2. **Worker pool management** - Worker creation, cleanup, and lifecycle
3. **Queue management** - Issue distribution and state tracking
4. **Error propagation** - How worker errors are handled and reported
5. **Concurrent execution** - Multiple workers accessing shared state
6. **Orchestration flows** - Complete end-to-end parallel runs

## Acceptance Criteria
- [ ] Coverage increased from 74% to at least 80%
- [ ] Tests for signal handling (SIGINT/SIGTERM)
- [ ] Tests for worker pool edge cases (empty, full, worker failures)
- [ ] Tests for concurrent state access
- [ ] Integration tests for complete orchestration flows
- [ ] All existing tests continue to pass

## Implementation Notes
- Reference: scripts/tests/test_orchestrator.py (existing tests)
- Signal handling tests require subprocess/fork testing
- Consider using threading/async tests for concurrent scenarios
- Test with temporary directories and worktrees

## Priority
P1 - High: orchestrator is the brain of parallel execution; untested paths can cause data loss or hangs.

## Related Files
- scripts/little_loops/parallel/orchestrator.py (source)
- scripts/tests/test_orchestrator.py (existing tests)
- scripts/pyproject.toml (coverage threshold: 80%)

## Audit Source
Test Coverage Audit - 2026-02-01

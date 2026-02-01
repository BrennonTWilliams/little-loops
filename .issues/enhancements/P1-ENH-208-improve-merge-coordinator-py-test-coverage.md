# P1-ENH-208: Improve merge_coordinator.py test coverage from 66% to 80%+

## Summary
The merge_coordinator module (scripts/little_loops/parallel/merge_coordinator.py) has only 66% test coverage with 151 missing statements. This module handles the complex logic of merging parallel work back to the main branch.

## Current State
- Coverage: 66% (151 missing statements)
- Location: scripts/little_loops/parallel/merge_coordinator.py
- Impact: Merge conflict resolution and parallel execution completion may have untested edge cases

## Targets for Improvement
1. **Merge conflict resolution** - How conflicts are detected and resolved
2. **Retry logic** - Automatic retry behavior on merge failures
3. **Error recovery** - Handling of corrupted worktrees or git state
4. **Concurrent merges** - Multiple workers completing simultaneously
5. **Merge order** - Dependency-aware merge sequencing
6. **Stash management** - Stash/restore logic during merges

## Acceptance Criteria
- [ ] Coverage increased from 66% to at least 80%
- [ ] Tests for merge conflict detection and resolution
- [ ] Tests for retry logic edge cases
- [ ] Tests for concurrent merge scenarios
- [ ] Integration tests with realistic merge conflicts
- [ ] All existing tests continue to pass

## Implementation Notes
- Reference: scripts/tests/parallel/test_merge_coordinator.py (existing tests)
- Create realistic merge conflict scenarios for testing
- Test with temporary git repos and worktrees
- Consider property-based tests for merge ordering

## Priority
P1 - High: merge_coordinator is critical for parallel execution reliability; merge failures can lose work.

## Related Files
- scripts/little_loops/parallel/merge_coordinator.py (source)
- scripts/tests/parallel/test_merge_coordinator.py (existing tests)
- scripts/pyproject.toml (coverage threshold: 80%)

## Audit Source
Test Coverage Audit - 2026-02-01

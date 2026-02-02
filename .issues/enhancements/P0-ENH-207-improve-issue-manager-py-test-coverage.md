# P0-ENH-207: Improve issue_manager.py test coverage from 63% to 80%+

## Summary
The issue_manager module (scripts/little_loops/issue_manager.py) has only 63% test coverage with 122 missing statements. This module contains core sequential processing logic and is critical to the automation workflow.

## Current State
- Coverage: 50% (165 missing statements out of 330 total)
- Location: scripts/little_loops/issue_manager.py
- Impact: Core sequential processing may have untested edge cases
- Missing lines: 108-117, 148-189, 250, 271-275, 299-300, 314-319, 333-338, 342-343, 347-394, 404-408, 420-422, 437, 449-450, 455-489, 509-536, 547-548, 618-619, 654, 684-730, 734-774, 796, 799-800, 803

## Targets for Improvement
1. **Sequential processing workflow** - The main issue processing loop
2. **Error handling and retry logic** - How failures are handled and retried
3. **State management** - Issue state transitions and lifecycle management
4. **Edge cases** - Empty issue lists, malformed issues, concurrent access
5. **Work verification** - Verification logic and verdict handling
6. **Git operations integration** - How git operations are orchestrated

## Acceptance Criteria
- [ ] Coverage increased from 63% to at least 80%
- [ ] Tests for all error handling paths
- [ ] Tests for retry logic edge cases
- [ ] Tests for state machine transitions
- [ ] Integration tests with temporary git repositories
- [ ] All existing tests continue to pass

## Implementation Notes
- Reference: scripts/tests/test_issue_manager.py (existing tests)
- Consider using parametrized tests for similar workflows
- Test with real temporary git repos for end-to-end validation
- Focus on the "happy path" AND error scenarios

## Priority
P0 - Critical: issue_manager is the core of the sequential automation workflow; gaps here affect the primary use case.

## Related Files
- scripts/little_loops/issue_manager.py (source)
- scripts/tests/test_issue_manager.py (existing tests)
- scripts/pyproject.toml (coverage threshold: 80%)

## Audit Source
Test Coverage Audit - 2026-02-01

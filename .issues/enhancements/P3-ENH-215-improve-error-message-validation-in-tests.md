# P3-ENH-215: Improve error message validation in tests

## Summary
Many tests only check that exceptions are raised without validating the error messages. Error messages should be validated to ensure they are helpful and actionable.

## Current State
- Pattern observed: Many tests use `pytest.raises(Exception)` without message validation
- Impact: Error messages can become vague or misleading without tests catching regressions

## Targets for Improvement
1. **Exception message assertions**
   - Use `pytest.raises(ValueError, match="expected message")`
   - Validate error message content is meaningful
   - Check for actionable information in messages

2. **Modules with heavy exception handling**
   - cli.py (user-facing error messages)
   - issue_manager.py (processing error messages)
   - merge_coordinator.py (merge error messages)
   - orchestrator.py (orchestration error messages)

3. **Error message quality criteria**
   - Messages should explain what went wrong
   - Messages should suggest how to fix
   - Messages should include relevant context
   - Messages should be consistent in style

## Acceptance Criteria
- [ ] Audit existing tests for weak exception assertions
- [ ] Add message matching to at least 50% of exception tests
- [ ] Document error message style guide
- [ ] Focus on user-facing error paths first (cli.py)
- [ ] All existing tests continue to pass

## Implementation Notes
- Use `match` parameter in pytest.raises() for regex matching
- Consider using `str(exc)` assertions for complex messages
- Create helper functions for common error message validations
- Prioritize user-facing errors over internal errors

## Priority
P3 - Low: Error message validation improves quality but is not critical; can be addressed incrementally.

## Related Files
- scripts/tests/ (all test files with exception handling)
- scripts/little_loops/cli.py (user-facing errors)
- scripts/little_loops/issue_manager.py (processing error messages)
- scripts/little_loops/parallel/merge_coordinator.py (merge error messages)
- scripts/little_loops/parallel/orchestrator.py (orchestration error messages)
- docs/TESTING.md (document pattern)

## Verification Notes
Verified 2026-02-01 - All referenced files exist at correct paths. Note: merge_coordinator.py is in scripts/little_loops/parallel/ directory.

## Audit Source
Test Coverage Audit - 2026-02-01

# P2-ENH-213: Split large test files into focused modules

## Summary
Several test files have grown excessively large (e.g., test_issue_history.py at 3,586 lines), making them difficult to navigate and maintain. Large test files should be split into focused modules.

## Current State
- Largest test files:
  - test_issue_history.py: ~3,586 lines
  - test_ll_loop.py: likely also large
- Impact: Difficult to navigate, slow to run specific tests, poor maintainability

## Proposed Splits
1. **test_issue_history.py** → split into:
   - test_issue_history_parsing.py (issue parsing logic)
   - test_issue_history_analysis.py (analysis operations)
   - test_issue_history_statistics.py (statistics and trends)
   - test_issue_history_integration.py (integration scenarios)

2. **test_ll_loop.py** → if > 2,000 lines, split into:
   - test_ll_loop_compilation.py (FSM compilation)
   - test_ll_loop_execution.py (loop execution)
   - test_ll_loop_state.py (state persistence)
   - test_ll_loop_cli.py (CLI integration)

3. **Review other test files** for similar splitting opportunities

## Acceptance Criteria
- [ ] test_issue_history.py split into 3-4 focused modules
- [ ] test_ll_loop.py split if > 2,000 lines
- [ ] Each new module has clear, focused responsibility
- [ ] Fixtures moved to conftest.py if shared across splits
- [ ] All tests continue to pass after split
- [ ] Import references updated if needed

## Implementation Notes
- Move shared fixtures to conftest.py before splitting
- Preserve test IDs/names to avoid breaking test runners
- Consider test class grouping for related tests
- Keep integration tests separate from unit tests

## Priority
P2 - Medium: Large test files are a maintainability burden but not blocking; can be addressed incrementally.

## Related Files
- scripts/tests/test_issue_history.py (primary target)
- scripts/tests/test_ll_loop.py (secondary target)
- scripts/tests/conftest.py (fixture location)

## Audit Source
Test Coverage Audit - 2026-02-01

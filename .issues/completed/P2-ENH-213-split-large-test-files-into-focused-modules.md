# P2-ENH-213: Split large test files into focused modules

## Summary
Several test files have grown excessively large (e.g., test_issue_history.py at 3,586 lines), making them difficult to navigate and maintain. Large test files should be split into focused modules.

## Current State
- Largest test files:
  - test_issue_history.py: 3,586 lines (verified)
  - test_ll_loop.py: 3,580 lines (verified)
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
- [ ] test_issue_history.py (3,586 lines) split into 3-4 focused modules
- [ ] test_ll_loop.py (3,580 lines) split into 3-4 focused modules
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

## Status
Identified

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `scripts/tests/test_issue_history.py` → Split into 5 focused modules:
  - `test_issue_history_parsing.py` (issue parsing logic)
  - `test_issue_history_summary.py` (summary and statistics)
  - `test_issue_history_analysis.py` (core analysis operations)
  - `test_issue_history_advanced_analytics.py` (advanced analytics: hotspots, coupling, regression, etc.)
  - `test_issue_history_cli.py` (CLI integration tests)
- `scripts/tests/test_ll_loop.py` → Split into 7 focused modules:
  - `test_ll_loop_parsing.py` (argument parsing and path resolution)
  - `test_ll_loop_commands.py` (basic command unit tests)
  - `test_ll_loop_display.py` (display formatting and serialization)
  - `test_ll_loop_integration.py` (CLI integration tests)
  - `test_ll_loop_state.py` (state management)
  - `test_ll_loop_errors.py` (error handling and messages)
  - `test_ll_loop_execution.py` (compilation, execution, LLM flags, test, simulate)
- `scripts/tests/conftest.py`: Added 6 fixtures from test_ll_loop.py (temp_project, valid_loop_file, invalid_loop_file, loops_dir, events_file, many_events_file)
- Removed original large test files (test_issue_history.py, test_ll_loop.py)

### Verification Results
- Tests: PASS (2286 passed)
- Lint: PASS (no new linting issues)
- Format: PASS (ruff format applied)

## Labels
- testing
- refactoring
- maintainability
- test-organization

## Related Files
- scripts/tests/test_issue_history.py (primary target)
- scripts/tests/test_ll_loop.py (secondary target)
- scripts/tests/conftest.py (fixture location)

## Audit Source
Test Coverage Audit - 2026-02-01

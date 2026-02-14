---
discovered_commit: 51dcccd702a7f8947c624a914f353b8ec65cf55f
discovered_branch: main
discovered_date: 2026-02-10
discovered_by: audit_architecture
focus_area: large-files
---

# ENH-413: Split large test files (optional)

## Summary

Architectural improvement found by `/ll:audit-architecture`. Several test files exceed 2,000 lines, making them harder to navigate. This is lower priority than production code splits.

## Location

- **Files**:
  - `scripts/tests/test_issue_history_advanced_analytics.py` (2,601 lines)
  - `scripts/tests/test_cli.py` (2,389 lines)
  - `scripts/tests/test_merge_coordinator.py` (2,334 lines)
  - `scripts/tests/test_orchestrator.py` (2,079 lines)
  - `scripts/tests/test_issue_manager.py` (2,079 lines)
  - `scripts/tests/test_fsm_executor.py` (1,925 lines)
  - `scripts/tests/test_worker_pool.py` (1,739 lines)

## Finding

### Current State

Large test files contain comprehensive test suites for complex modules. While not as problematic as large production code, they can be harder to navigate and maintain.

### Impact

- **Development velocity**: Slightly harder to find specific tests
- **Maintainability**: Less of an issue than production code
- **Risk**: Low - Tests are isolated from each other
- **Priority**: Low - Optional improvement, not urgent

## Proposed Solution

Split large test files by feature area or test category. This is OPTIONAL and lower priority than production code refactoring.

### Example: test_issue_history_advanced_analytics.py

Could be split into:
```
tests/issue_history/
├── test_issue_history_models.py (dataclass tests)
├── test_issue_history_parsing.py (parsing function tests)
├── test_issue_history_analysis.py (analysis function tests)
├── test_issue_history_formatting.py (formatting function tests)
└── test_issue_history_integration.py (end-to-end tests)
```

### Example: test_cli.py

After ENH-309 splits cli.py, split test file to match:
```
tests/cli/
├── test_auto.py
├── test_parallel.py
├── test_messages.py
├── test_loop.py
├── test_sprint.py
├── test_history.py
├── test_sync.py
└── test_docs.py
```

## Implementation Steps

1. **Wait for production code refactoring** (ENH-309, ENH-390)
2. **Split test_cli.py** to match new cli/ structure
3. **Split test_issue_history_advanced_analytics.py** to match new issue_history/ structure
4. **Optionally split other large test files** if maintainers see value
5. **Update pytest collection** if needed
6. **Run full test suite** to ensure all tests still discovered

## Impact Assessment

- **Severity**: Low - Convenience improvement only
- **Effort**: Small - Straightforward file splitting
- **Risk**: Very low - Tests are isolated, pytest discovery flexible
- **Breaking Change**: No - pytest will find tests in any location

## Benefits

1. **Easier test navigation** - Find tests by feature area
2. **Clearer test organization** - Mirrors production code structure
3. **Parallel test execution** - pytest-xdist can better distribute tests
4. **Isolated changes** - Changes to one area don't affect other tests

## Notes

- This is OPTIONAL and LOW PRIORITY
- Only do this after production code refactoring (ENH-309, ENH-390)
- Test files are less critical than production code
- Large test files are more acceptable than large production files
- Focus effort on high-impact improvements first

## Dependencies

- **Blocks**: None
- **Blocked by**: ENH-309, ENH-390 (should refactor production code first)

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`, `optional`, `low-priority`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P4

---

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID
- Test file line counts verified (all close to reported values):
  - test_issue_history_advanced_analytics.py: 2,601 lines (reported: 2,601)
  - test_cli.py: 2,389 lines (reported: 2,389)
  - test_merge_coordinator.py: 2,334 lines (reported: 2,334)
  - test_orchestrator.py: 2,079 lines (reported: 2,079)
  - test_issue_manager.py: 2,083 lines (reported: 2,079)
  - test_fsm_executor.py: 1,925 lines (reported: 1,925)
  - test_worker_pool.py: 1,737 lines (reported: 1,739)
- Dependencies (ENH-309, ENH-390) not yet completed — test splitting not started

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: 2026-02-11
- **Reason**: Low utility relative to implementation complexity

### Tradeoff Review Scores
- Utility: LOW
- Implementation Effort: MEDIUM
- Complexity Added: LOW
- Technical Debt Risk: LOW
- Maintenance Overhead: LOW

### Rationale
Explicitly optional and low-priority per the issue itself. Blocked by ENH-309 and ENH-390. Large test files are more acceptable than large production files. Reopen only if test navigation becomes a real pain point.

---
discovered_date: 2026-04-11
discovered_by: capture-issue
---

# ENH-1036: Remove Mock-Assertion Tests in test_orchestrator.py

## Summary

`test_orchestrator.py` contains ~15–20 tests whose only assertion is `mock_X.assert_called_once()` on a constructor mock. These verify the test's own mock setup, not orchestration behavior. Also contains multiple near-identical `__init__` state verification tests. Remove the constructor-only mock tests and consolidate duplicate init tests.

## Current Behavior

~21% of `test_orchestrator.py` tests (out of 113) assert only that a mock constructor was called — e.g., `mock_wp.assert_called_once()`. These pass trivially because the test itself invokes the constructor. Additionally, multiple tests repeat near-identical `__init__` attribute verification.

## Expected Behavior

Only tests that verify real orchestration behavior (dependency wiring, error handling, state transitions) remain. Constructor-only mock tests are removed. Duplicate init tests are consolidated into a single parametrized test. Test count reduced by ~15–20.

## Motivation

Constructor-only mock assertions are tautological — they can never fail unless the test itself is broken. They give false confidence, inflate counts, and make the suite harder to audit. Removing them clarifies what the orchestrator is actually tested against.

## Proposed Solution

1. Delete tests where the sole assertion is `mock_X.assert_called_once()` or `mock_X.assert_called_once_with(...)` on a constructor mock with no other behavioral assertions.
2. Identify `__init__` state verification tests that overlap and consolidate into one `@pytest.mark.parametrize` test covering each attribute.

## Integration Map

### Files to Modify
- `scripts/tests/test_orchestrator.py`

### Dependent Files (Callers/Importers)
- N/A — test-only change

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_orchestrator.py` — the file being modified

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Grep for `assert_called_once` in `test_orchestrator.py`; identify tests where that is the only assertion
2. Delete those test functions
3. Identify groups of `__init__` tests with near-identical structure; collapse into parametrized form
4. Run `python -m pytest scripts/tests/test_orchestrator.py -v --tb=short` and confirm all remaining tests pass
5. Verify test count drops by ~15–20

## Impact

- **Priority**: P4 - Test quality cleanup, no behavioral change
- **Effort**: Small-Medium - Requires careful review to avoid removing tests with hidden value
- **Risk**: Low - Tests only; no production code changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`test-quality`, `test_orchestrator`, `captured`

## Status

**Open** | Created: 2026-04-11 | Priority: P4

---

## Session Log
- `/ll:capture-issue` - 2026-04-11T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b9439fb7-57cc-417c-9114-6eea87ed8705.jsonl`

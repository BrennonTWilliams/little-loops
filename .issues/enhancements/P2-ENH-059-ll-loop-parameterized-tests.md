# P2-ENH-059: Refactor ll-loop Tests to Use Parameterized Tests

## Summary

The test suite has repeated patterns that could be consolidated using `@pytest.mark.parametrize` for better maintainability and coverage.

## Problem

Similar test logic is duplicated across multiple test methods:
- Verdict symbol mapping tests (`test_ll_loop.py:867-891`)
- Duration formatting tests (`test_ll_loop.py:849-865`)
- State-to-dict field tests (`test_ll_loop.py:430-647`)

This duplication makes tests harder to maintain and extend.

## Acceptance Criteria

- [ ] Refactor verdict symbol tests to use `@pytest.mark.parametrize`
- [ ] Refactor duration formatting tests to use parameterization
- [ ] Consider parameterizing evaluator type tests in `TestStateToDict`
- [ ] Ensure all existing test cases are preserved
- [ ] No reduction in coverage

## Implementation Notes

```python
# Before: Multiple similar tests
def test_verdict_success_checkmark(self):
    assert get_verdict_symbol("success") == "✓"

def test_verdict_failure_x(self):
    assert get_verdict_symbol("failure") == "✗"

# After: Parameterized
@pytest.mark.parametrize("verdict,expected", [
    ("success", "✓"),
    ("on_success", "✓"),
    ("failure", "✗"),
    ("on_failure", "✗"),
    ("on_error", "✗"),
])
def test_verdict_symbols(self, verdict, expected):
    assert get_verdict_symbol(verdict) == expected


# Duration formatting
@pytest.mark.parametrize("ms,expected", [
    (5000, "5.0s"),
    (30000, "30.0s"),
    (60000, "1:00"),
    (90000, "1:30"),
    (125000, "2:05"),
])
def test_duration_formatting(self, ms, expected):
    assert format_duration(ms) == expected
```

## Related Files

- `scripts/tests/test_ll_loop.py:846-919` - `TestProgressDisplay` class
- `scripts/tests/test_ll_loop.py:382-648` - `TestStateToDict` class

## Priority Justification

P2 - Code quality improvement that makes tests easier to maintain and extend.

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Refactored `TestProgressDisplay` class to use `@pytest.mark.parametrize`:
  - Consolidated 2 duration formatting tests into parameterized tests (3 + 4 = 7 test cases)
  - Consolidated 3 verdict symbol tests into 1 parameterized test (7 test cases)
  - Consolidated 2 action truncation tests into 1 parameterized test (5 test cases)
  - Total: 9 original tests → 4 parameterized tests generating 21 test cases

### Decision: TestStateToDict Not Parameterized
The `TestStateToDict` tests were evaluated but not parameterized because:
- Each test documents a distinct behavior scenario with different field combinations
- Tests create complex `StateConfig` objects with different configurations
- Parameterizing would obscure what's being tested and make failures harder to debug
- Individual tests serve as better documentation for the API

### Verification Results
- Tests: PASS (101 tests)
- Lint: PASS
- Types: PASS

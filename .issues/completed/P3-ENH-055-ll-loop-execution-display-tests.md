# ENH-055: Add Tests for ll-loop Execution and Display Functions

## Summary

The `ll-loop` CLI has several helper functions for execution display and output formatting that are only tested via simulation. The actual `run_foreground`, `print_execution_plan`, and `_state_to_dict` functions should be tested with real objects.

## Current State

- **Test File**: `scripts/tests/test_ll_loop.py`
- **Current Approach**: Tests use `MagicMock` objects to simulate `StateConfig`
- **Missing**: Tests with real `FSMLoop` and `StateConfig` objects

### Functions Needing Better Coverage

From `scripts/little_loops/cli.py`:

| Function | Lines | Current Coverage |
|----------|-------|------------------|
| `print_execution_plan` | 538-572 | None |
| `run_foreground` | 574-642 | None |
| `display_progress` | 584-612 | Simulated only |
| `_state_to_dict` | 724-763 | Mocked objects only |

## Proposed Tests

### Execution Plan Display Tests

```python
class TestPrintExecutionPlan:
    def test_basic_plan_output(self, capsys):
        """Plan output shows states and transitions."""
        fsm = create_test_fsm()
        print_execution_plan(fsm)
        captured = capsys.readouterr()
        assert "States:" in captured.out
        assert fsm.initial in captured.out

    def test_terminal_state_marker(self, capsys):
        """Terminal states marked with [TERMINAL]."""

    def test_long_action_truncated(self, capsys):
        """Actions over 70 chars are truncated with ..."""

    def test_route_display(self, capsys):
        """Route mappings displayed correctly."""
```

### State to Dict Tests

```python
class TestStateToDictReal:
    """Tests using real StateConfig objects."""

    def test_simple_state(self):
        """Convert state with action and on_success."""
        from little_loops.fsm.schema import StateConfig
        state = StateConfig(action="echo hello", on_success="done")
        result = _state_to_dict(state)
        assert result == {"action": "echo hello", "on_success": "done"}

    def test_evaluate_config(self):
        """Convert state with evaluate block."""

    def test_route_config(self):
        """Convert state with route block."""

    def test_all_fields(self):
        """Convert state with all optional fields populated."""
```

### Progress Display Tests

```python
class TestDisplayProgress:
    def test_state_enter_format(self, capsys):
        """state_enter shows iteration and state name."""

    def test_action_start_truncation(self, capsys):
        """Long actions truncated at 60 chars."""

    def test_evaluate_success_symbol(self, capsys):
        """Success verdict shows checkmark."""

    def test_evaluate_failure_symbol(self, capsys):
        """Failure verdict shows x mark."""

    def test_evaluate_with_confidence(self, capsys):
        """Confidence score displayed when present."""
```

## Implementation Approach

1. Import real schema classes:
   ```python
   from little_loops.fsm.schema import FSMLoop, StateConfig, EvaluateConfig, RouteConfig
   ```

2. Create factory functions for test FSMs:
   ```python
   def create_test_fsm(name="test", states=None, initial="start"):
       """Create FSMLoop for testing."""
       if states is None:
           states = {
               "start": StateConfig(action="echo start", on_success="done"),
               "done": StateConfig(terminal=True)
           }
       return FSMLoop(name=name, states=states, initial=initial)
   ```

3. Use `capsys` fixture to capture stdout for display tests

## Impact

- **Priority**: P3 (Low)
- **Effort**: Low
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [x] `print_execution_plan` tested with real FSMLoop objects
- [x] `_state_to_dict` tested with real StateConfig objects (replacing mocks)
- [x] Progress display formatting verified with capsys
- [x] All evaluate config fields covered in _state_to_dict tests

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `display`

---

## Status

**Completed** | Created: 2026-01-15 | Priority: P3

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Added factory functions (`make_test_state`, `make_test_fsm`) for creating real schema objects in tests
- `scripts/tests/test_ll_loop.py`: Replaced MagicMock-based `TestStateToDict` tests with 18 new tests using real `StateConfig`, `EvaluateConfig`, and `RouteConfig` objects
- `scripts/tests/test_ll_loop.py`: Added `TestPrintExecutionPlan` class with 6 tests for execution plan display formatting via CLI dry-run
- `scripts/tests/test_ll_loop.py`: Expanded `TestProgressDisplay` class with 6 new tests for formatting logic (symbols, truncation, confidence, iteration progress)

### Verification Results
- Tests: PASS (80 tests in test_ll_loop.py, 1228 tests total)
- Lint: PASS
- Types: PASS (pre-existing unrelated issue only)

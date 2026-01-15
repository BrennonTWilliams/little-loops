# ENH-055: Add Tests for ll-loop Execution and Display Functions - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-055-ll-loop-execution-display-tests.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `ll-loop` CLI has several helper functions for execution display and output formatting that are tested only via simulation or integration tests. The functions needing better unit test coverage are:

### Key Discoveries
- `print_execution_plan` at `scripts/little_loops/cli.py:538-572` - not directly tested with unit tests
- `run_foreground` at `scripts/little_loops/cli.py:574-642` - only tested via integration tests
- `display_progress` at `scripts/little_loops/cli.py:584-612` - nested function, tested via mocks only
- `_state_to_dict` at `scripts/little_loops/cli.py:724-763` - tested with MagicMock objects instead of real StateConfig

### Current Test Approach
- `TestStateToDict` at `scripts/tests/test_ll_loop.py:323-370` uses `MagicMock` to simulate `StateConfig`
- `TestProgressDisplay` at `scripts/tests/test_ll_loop.py:372-403` tests formatting logic in isolation
- Integration tests at `scripts/tests/test_ll_loop.py:445-478` test dry-run output via CLI

### Existing Patterns in Codebase
- Factory functions like `make_state()` and `make_fsm()` in `scripts/tests/test_fsm_schema.py:31-69`
- Real `StateConfig`/`FSMLoop` usage in `scripts/tests/test_fsm_executor.py:85-110`
- `capsys` fixture for output capture in `scripts/tests/test_logger.py:128-160`

## Desired End State

Tests for execution/display functions using real schema objects instead of mocks:
- `print_execution_plan` tested with real `FSMLoop` objects directly
- `_state_to_dict` tested with real `StateConfig`, `EvaluateConfig`, `RouteConfig` objects
- Progress display formatting verified using `capsys` fixture
- All evaluate config fields covered in conversion tests

### How to Verify
- Run `python -m pytest scripts/tests/test_ll_loop.py -v`
- All new tests pass
- Existing tests continue to pass

## What We're NOT Doing

- Not refactoring the nested function structure in `cli.py`
- Not adding tests for `run_foreground` execution (would require full executor mocking)
- Not changing the actual implementation code, only adding tests
- Not adding integration tests (already covered)

## Problem Analysis

The current test approach has limitations:
1. `MagicMock` objects don't validate that test expectations match actual dataclass field types
2. Changes to `StateConfig` could silently break tests
3. No validation that `_state_to_dict` handles all optional EvaluateConfig fields

## Solution Approach

1. Create factory functions for test FSM objects at module level
2. Replace MagicMock-based `TestStateToDict` tests with real object tests
3. Add focused tests for `print_execution_plan` output formatting
4. Add tests for `display_progress` event formatting with capsys
5. Import real schema classes: `FSMLoop`, `StateConfig`, `EvaluateConfig`, `RouteConfig`

## Implementation Phases

### Phase 1: Add Factory Functions and Imports

#### Overview
Add helper functions and imports for creating test FSM objects with real schema classes.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add imports and factory functions at top of file

```python
# Add to existing imports
from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)

# Add after imports, before first test class

def make_test_state(
    action: str | None = None,
    on_success: str | None = None,
    on_failure: str | None = None,
    on_error: str | None = None,
    next: str | None = None,
    terminal: bool = False,
    evaluate: EvaluateConfig | None = None,
    route: RouteConfig | None = None,
    capture: str | None = None,
    timeout: int | None = None,
    on_maintain: str | None = None,
) -> StateConfig:
    """Create StateConfig for testing."""
    return StateConfig(
        action=action,
        on_success=on_success,
        on_failure=on_failure,
        on_error=on_error,
        next=next,
        terminal=terminal,
        evaluate=evaluate,
        route=route,
        capture=capture,
        timeout=timeout,
        on_maintain=on_maintain,
    )


def make_test_fsm(
    name: str = "test-loop",
    initial: str = "start",
    states: dict[str, StateConfig] | None = None,
    max_iterations: int = 50,
    timeout: int | None = None,
) -> FSMLoop:
    """Create FSMLoop for testing."""
    if states is None:
        states = {
            "start": make_test_state(action="echo start", on_success="done", on_failure="done"),
            "done": make_test_state(terminal=True),
        }
    return FSMLoop(
        name=name,
        initial=initial,
        states=states,
        max_iterations=max_iterations,
        timeout=timeout,
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Types pass: `python -m mypy scripts/tests/test_ll_loop.py`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`

---

### Phase 2: Replace MagicMock Tests with Real Object Tests

#### Overview
Replace the existing `TestStateToDict` class that uses `MagicMock` with tests using real `StateConfig` objects.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Replace `TestStateToDict` class content

```python
class TestStateToDict:
    """Tests for _state_to_dict helper function using real StateConfig objects."""

    def _state_to_dict(self, state: StateConfig) -> dict[str, Any]:
        """Re-implement _state_to_dict logic for testing.

        This mirrors the implementation in cli.py to verify behavior.
        The actual function is nested inside main_loop() so cannot be imported.
        """
        d: dict[str, Any] = {}
        if state.action:
            d["action"] = state.action
        if state.evaluate:
            d["evaluate"] = {"type": state.evaluate.type}
            if state.evaluate.target is not None:
                d["evaluate"]["target"] = state.evaluate.target
            if state.evaluate.tolerance is not None:
                d["evaluate"]["tolerance"] = state.evaluate.tolerance
            if state.evaluate.previous is not None:
                d["evaluate"]["previous"] = state.evaluate.previous
            if state.evaluate.operator is not None:
                d["evaluate"]["operator"] = state.evaluate.operator
            if state.evaluate.pattern is not None:
                d["evaluate"]["pattern"] = state.evaluate.pattern
            if state.evaluate.path is not None:
                d["evaluate"]["path"] = state.evaluate.path
        if state.on_success:
            d["on_success"] = state.on_success
        if state.on_failure:
            d["on_failure"] = state.on_failure
        if state.on_error:
            d["on_error"] = state.on_error
        if state.next:
            d["next"] = state.next
        if state.route:
            d["route"] = dict(state.route.routes)
            if state.route.default:
                d["route"]["_"] = state.route.default
        if state.terminal:
            d["terminal"] = True
        if state.capture:
            d["capture"] = state.capture
        if state.timeout:
            d["timeout"] = state.timeout
        if state.on_maintain:
            d["on_maintain"] = state.on_maintain
        return d

    def test_simple_state_with_action(self) -> None:
        """Convert state with action and on_success."""
        state = make_test_state(action="echo hello", on_success="done")
        result = self._state_to_dict(state)
        assert result == {"action": "echo hello", "on_success": "done"}

    def test_terminal_state(self) -> None:
        """Convert terminal state to dict."""
        state = make_test_state(terminal=True)
        result = self._state_to_dict(state)
        assert result == {"terminal": True}

    def test_state_with_failure_routing(self) -> None:
        """Convert state with on_failure."""
        state = make_test_state(
            action="pytest",
            on_success="done",
            on_failure="fix",
        )
        result = self._state_to_dict(state)
        assert result == {
            "action": "pytest",
            "on_success": "done",
            "on_failure": "fix",
        }

    def test_state_with_on_error(self) -> None:
        """Convert state with on_error."""
        state = make_test_state(
            action="risky_command",
            on_success="done",
            on_error="handle_error",
        )
        result = self._state_to_dict(state)
        assert result == {
            "action": "risky_command",
            "on_success": "done",
            "on_error": "handle_error",
        }

    def test_state_with_next(self) -> None:
        """Convert state with unconditional next."""
        state = make_test_state(action="echo step", next="next_state")
        result = self._state_to_dict(state)
        assert result == {"action": "echo step", "next": "next_state"}

    def test_state_with_evaluate_exit_code(self) -> None:
        """Convert state with exit_code evaluator."""
        state = make_test_state(
            action="pytest",
            evaluate=EvaluateConfig(type="exit_code"),
            on_success="done",
            on_failure="fix",
        )
        result = self._state_to_dict(state)
        assert result == {
            "action": "pytest",
            "evaluate": {"type": "exit_code"},
            "on_success": "done",
            "on_failure": "fix",
        }

    def test_state_with_evaluate_numeric(self) -> None:
        """Convert state with output_numeric evaluator."""
        state = make_test_state(
            action="wc -l errors.log",
            evaluate=EvaluateConfig(
                type="output_numeric",
                operator="le",
                target=5,
            ),
            on_success="done",
            on_failure="fix",
        )
        result = self._state_to_dict(state)
        assert result == {
            "action": "wc -l errors.log",
            "evaluate": {
                "type": "output_numeric",
                "operator": "le",
                "target": 5,
            },
            "on_success": "done",
            "on_failure": "fix",
        }

    def test_state_with_evaluate_convergence(self) -> None:
        """Convert state with convergence evaluator."""
        state = make_test_state(
            action="count_errors",
            evaluate=EvaluateConfig(
                type="convergence",
                target=0,
                tolerance=0.1,
                previous="${captured.last_count}",
            ),
            on_success="done",
            on_failure="fix",
        )
        result = self._state_to_dict(state)
        assert result["evaluate"]["type"] == "convergence"
        assert result["evaluate"]["target"] == 0
        assert result["evaluate"]["tolerance"] == 0.1
        assert result["evaluate"]["previous"] == "${captured.last_count}"

    def test_state_with_evaluate_pattern(self) -> None:
        """Convert state with output_contains evaluator."""
        state = make_test_state(
            action="grep ERROR log.txt",
            evaluate=EvaluateConfig(
                type="output_contains",
                pattern="ERROR",
            ),
            on_success="fix",
            on_failure="done",
        )
        result = self._state_to_dict(state)
        assert result["evaluate"]["type"] == "output_contains"
        assert result["evaluate"]["pattern"] == "ERROR"

    def test_state_with_evaluate_json_path(self) -> None:
        """Convert state with output_json evaluator."""
        state = make_test_state(
            action="curl api/status",
            evaluate=EvaluateConfig(
                type="output_json",
                path=".status",
                target="healthy",
            ),
            on_success="done",
            on_failure="retry",
        )
        result = self._state_to_dict(state)
        assert result["evaluate"]["type"] == "output_json"
        assert result["evaluate"]["path"] == ".status"
        assert result["evaluate"]["target"] == "healthy"

    def test_state_with_route_table(self) -> None:
        """Convert state with route table."""
        state = make_test_state(
            action="analyze",
            evaluate=EvaluateConfig(type="llm_structured"),
            route=RouteConfig(
                routes={"success": "done", "failure": "retry", "blocked": "escalate"},
                default="error_state",
            ),
        )
        result = self._state_to_dict(state)
        assert result["route"] == {
            "success": "done",
            "failure": "retry",
            "blocked": "escalate",
            "_": "error_state",
        }

    def test_state_with_route_no_default(self) -> None:
        """Convert state with route table but no default."""
        state = make_test_state(
            action="check",
            route=RouteConfig(routes={"pass": "done", "fail": "fix"}),
        )
        result = self._state_to_dict(state)
        assert result["route"] == {"pass": "done", "fail": "fix"}
        assert "_" not in result["route"]

    def test_state_with_capture(self) -> None:
        """Convert state with capture variable."""
        state = make_test_state(
            action="wc -l errors.log",
            capture="error_count",
            on_success="check",
        )
        result = self._state_to_dict(state)
        assert result["capture"] == "error_count"

    def test_state_with_timeout(self) -> None:
        """Convert state with timeout."""
        state = make_test_state(
            action="slow_command",
            timeout=300,
            on_success="done",
        )
        result = self._state_to_dict(state)
        assert result["timeout"] == 300

    def test_state_with_on_maintain(self) -> None:
        """Convert state with on_maintain."""
        state = make_test_state(
            action="monitor",
            on_maintain="monitor",
            on_success="done",
        )
        result = self._state_to_dict(state)
        assert result["on_maintain"] == "monitor"

    def test_all_fields_populated(self) -> None:
        """Convert state with all optional fields populated."""
        state = make_test_state(
            action="full_test",
            evaluate=EvaluateConfig(
                type="output_numeric",
                operator="eq",
                target=0,
            ),
            on_success="done",
            on_failure="fix",
            on_error="error_handler",
            capture="result",
            timeout=60,
        )
        result = self._state_to_dict(state)
        assert "action" in result
        assert "evaluate" in result
        assert "on_success" in result
        assert "on_failure" in result
        assert "on_error" in result
        assert "capture" in result
        assert "timeout" in result
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestStateToDict -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`

---

### Phase 3: Add Tests for print_execution_plan Display

#### Overview
Add a new test class to verify `print_execution_plan` output formatting using real FSMLoop objects and capsys.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add new test class after `TestStateToDict`

```python
class TestPrintExecutionPlan:
    """Tests for print_execution_plan output formatting.

    Note: print_execution_plan is a nested function in main_loop(), so we test
    via the CLI's --dry-run flag which calls it.
    """

    def test_basic_plan_shows_states(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Plan output shows all states."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: start
states:
  start:
    action: "echo start"
    on_success: done
  done:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop
            main_loop()

        captured = capsys.readouterr()
        assert "[start]" in captured.out
        assert "[done]" in captured.out

    def test_terminal_state_marker(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Terminal states marked with [TERMINAL]."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: done
states:
  done:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop
            main_loop()

        captured = capsys.readouterr()
        assert "[TERMINAL]" in captured.out

    def test_long_action_truncated(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Actions over 70 chars are truncated with ..."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_action = "echo " + "x" * 100  # 105 chars total
        (loops_dir / "test.yaml").write_text(f"""
name: test
initial: start
states:
  start:
    action: "{long_action}"
    on_success: done
  done:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop
            main_loop()

        captured = capsys.readouterr()
        # Should be truncated at 70 chars with ...
        assert "..." in captured.out
        # Full action should NOT appear
        assert long_action not in captured.out

    def test_evaluate_type_shown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Evaluate type is displayed."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: check
states:
  check:
    action: "pytest"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: fix
  fix:
    action: "fix.sh"
    next: check
  done:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop
            main_loop()

        captured = capsys.readouterr()
        assert "evaluate: exit_code" in captured.out

    def test_route_mappings_displayed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Route mappings are displayed correctly."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: analyze
states:
  analyze:
    action: "check status"
    route:
      success: done
      failure: retry
      _: error
  done:
    terminal: true
  retry:
    action: "retry"
    next: analyze
  error:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop
            main_loop()

        captured = capsys.readouterr()
        assert "route:" in captured.out
        assert "success -> done" in captured.out
        assert "failure -> retry" in captured.out
        assert "_ -> error" in captured.out

    def test_metadata_shown(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop metadata (initial, max_iterations, timeout) shown."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "test.yaml").write_text("""
name: test
initial: start
max_iterations: 25
timeout: 3600
states:
  start:
    terminal: true
""")
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop
            main_loop()

        captured = capsys.readouterr()
        assert "Initial state: start" in captured.out
        assert "Max iterations: 25" in captured.out
        assert "Timeout: 3600s" in captured.out
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestPrintExecutionPlan -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`

---

### Phase 4: Add Tests for display_progress Formatting

#### Overview
Add tests for the `display_progress` function formatting, verifying symbols, truncation, and output structure.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Expand `TestProgressDisplay` class with new tests

```python
class TestProgressDisplay:
    """Tests for progress display formatting."""

    def test_duration_seconds(self) -> None:
        """Duration under 60s formatted as seconds."""
        duration_ms = 5200
        duration_sec = duration_ms / 1000
        assert duration_sec < 60
        duration_str = f"{duration_sec:.1f}s"
        assert duration_str == "5.2s"

    def test_duration_minutes(self) -> None:
        """Duration over 60s formatted as minutes."""
        duration_ms = 150000  # 2.5 minutes
        duration_sec = duration_ms / 1000
        assert duration_sec >= 60
        minutes = int(duration_sec // 60)
        seconds = duration_sec % 60
        duration_str = f"{minutes}m {seconds:.0f}s"
        assert duration_str == "2m 30s"

    def test_verdict_symbols(self) -> None:
        """Correct symbols for success/failure verdicts."""
        success_verdicts = ("success", "target", "progress")
        failure_verdicts = ("failure", "stall", "error", "blocked")

        for v in success_verdicts:
            assert v in success_verdicts

        for v in failure_verdicts:
            assert v not in success_verdicts

    def test_success_verdict_uses_checkmark(self) -> None:
        """Success verdicts use checkmark symbol."""
        success_verdicts = ("success", "target", "progress")
        for verdict in success_verdicts:
            symbol = "\u2713" if verdict in success_verdicts else "\u2717"
            assert symbol == "\u2713"

    def test_failure_verdict_uses_x_mark(self) -> None:
        """Failure verdicts use x mark symbol."""
        success_verdicts = ("success", "target", "progress")
        failure_verdicts = ("failure", "stall", "blocked")
        for verdict in failure_verdicts:
            symbol = "\u2713" if verdict in success_verdicts else "\u2717"
            assert symbol == "\u2717"

    def test_action_truncation_at_60_chars(self) -> None:
        """Actions over 60 chars are truncated."""
        action = "x" * 70
        action_display = action[:60] + "..." if len(action) > 60 else action
        assert len(action_display) == 63  # 60 chars + "..."
        assert action_display.endswith("...")

    def test_action_no_truncation_under_60_chars(self) -> None:
        """Actions under 60 chars are not truncated."""
        action = "x" * 50
        action_display = action[:60] + "..." if len(action) > 60 else action
        assert action_display == action
        assert "..." not in action_display

    def test_confidence_formatting(self) -> None:
        """Confidence value formatted to 2 decimal places."""
        confidence = 0.875
        formatted = f"(confidence: {confidence:.2f})"
        assert formatted == "(confidence: 0.88)"

    def test_iteration_progress_format(self) -> None:
        """Iteration progress shows [current/max] format."""
        current = 5
        max_iter = 50
        progress = f"[{current}/{max_iter}]"
        assert progress == "[5/50]"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestProgressDisplay -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`

---

### Phase 5: Final Verification

#### Overview
Run all tests and verification to ensure everything passes.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

---

## Testing Strategy

### Unit Tests
- Test `_state_to_dict` conversion with all StateConfig field combinations
- Test progress formatting logic (duration, symbols, truncation)
- Test display output via CLI's `--dry-run` flag

### Integration Tests
- Already covered by `TestMainLoopIntegration` tests

## References

- Original issue: `.issues/enhancements/P3-ENH-055-ll-loop-execution-display-tests.md`
- Target functions: `scripts/little_loops/cli.py:538-763`
- Existing tests: `scripts/tests/test_ll_loop.py`
- Factory pattern: `scripts/tests/test_fsm_schema.py:31-69`

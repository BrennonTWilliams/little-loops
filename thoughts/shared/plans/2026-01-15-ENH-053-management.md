# ENH-053: Add Integration Tests for ll-loop CLI - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P2-ENH-053-ll-loop-integration-tests.md`
- **Type**: enhancement
- **Priority**: P2
- **Action**: improve

## Current State Analysis

### Existing Tests in `test_ll_loop.py` (lines 1-402)
- `TestLoopArgumentParsing`: Recreates parsers and tests parsing logic (never calls `main_loop()`)
- `TestResolveLoopPath`: Simulates path resolution (doesn't call actual nested function)
- `TestCmdValidate`, `TestCmdList`, `TestCmdHistory`: Tests logic patterns (doesn't call handlers)
- `TestStateToDict`, `TestProgressDisplay`: Tests formatting logic in isolation

### Existing Tests in `test_cli.py` (lines 566-660)
- `TestMainLoopIntegration`: Has 5 tests that DO call `main_loop()`:
  - `test_main_loop_list_command`
  - `test_main_loop_list_running_command`
  - `test_main_loop_validate_invalid_definition`
  - `test_main_loop_compile_command`
  - `test_main_loop_no_command_shows_help`

### Key Discoveries
- Shorthand conversion at `cli.py:449-454` transforms `ll-loop fix-types` -> `ll-loop run fix-types`
- The `resolve_loop_path()` nested function at `cli.py:527-536` is NOT currently tested
- `cmd_run()` at `cli.py:644-675` needs integration tests with mocked executor
- Pattern for tests: `patch.object(sys, "argv", [...])` with `patch("pathlib.Path.cwd", ...)`

## Desired End State

New tests in `test_ll_loop.py` that:
1. Call `main_loop()` directly with mocked `sys.argv`
2. Test shorthand conversion (loop name -> `run` subcommand)
3. Test each subcommand routes to correct handler
4. Test `--dry-run` outputs execution plan
5. Achieve 60%+ coverage of `main_loop()` function

### How to Verify
- `pytest scripts/tests/test_ll_loop.py -v` passes
- All new tests exercise actual `main_loop()` function
- Coverage report shows improved `main_loop` coverage

## What We're NOT Doing

- Not testing full end-to-end execution (requires real executor)
- Not testing background mode (marked as not implemented in CLI)
- Not refactoring existing unit tests (they provide value)
- Not testing `cmd_resume()` with real state files (complex persistence)

## Solution Approach

Add a new test class `TestMainLoopIntegration` to `test_ll_loop.py` following patterns from `test_cli.py:566-660`. Use mocks for:
- `sys.argv` via `patch.object`
- `pathlib.Path.cwd` to control working directory
- `PersistentExecutor` to avoid real execution
- `load_and_validate` to control FSM loading

## Implementation Phases

### Phase 1: Add Integration Test Class

#### Overview
Add new integration tests to `test_ll_loop.py` that call `main_loop()` directly.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add new test class after existing tests (around line 402)

```python
class TestMainLoopIntegration:
    """Integration tests that call main_loop() directly."""

    def test_shorthand_inserts_run_subcommand(self, tmp_path: Path) -> None:
        """ll-loop fix-types becomes ll-loop run fix-types internally."""
        # Create valid loop file
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: fix-types
initial: check
states:
  check:
    terminal: true
"""
        (loops_dir / "fix-types.yaml").write_text(loop_content)

        with patch.object(sys, "argv", ["ll-loop", "fix-types", "--dry-run"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        # --dry-run should succeed and return 0
        assert result == 0

    def test_run_dry_run_outputs_plan(self, tmp_path: Path, capsys) -> None:
        """--dry-run outputs execution plan without running."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: start
states:
  start:
    action: "echo hello"
    on_success: done
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--dry-run"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "Execution plan for: test-loop" in captured.out
        assert "[start]" in captured.out
        assert "[done]" in captured.out

    def test_run_with_max_iterations_override(self, tmp_path: Path) -> None:
        """--max-iterations overrides loop definition."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: done
max_iterations: 5
states:
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        captured_fsm = []

        def mock_executor_init(self, fsm, **kwargs):
            captured_fsm.append(fsm)
            # Don't actually run

        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "-n", "20", "--dry-run"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 0

    def test_run_missing_loop_returns_error(self, tmp_path: Path) -> None:
        """run with non-existent loop returns error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        with patch.object(sys, "argv", ["ll-loop", "run", "nonexistent"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 1

    def test_validate_valid_loop_succeeds(self, tmp_path: Path, capsys) -> None:
        """validate with valid loop returns success."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: valid-loop
initial: start
states:
  start:
    action: "echo test"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "valid-loop.yaml").write_text(loop_content)

        with patch.object(sys, "argv", ["ll-loop", "validate", "valid-loop"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "valid" in captured.out.lower() or "Valid" in captured.out

    def test_validate_missing_loop_returns_error(self, tmp_path: Path) -> None:
        """validate with missing loop returns error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        with patch.object(sys, "argv", ["ll-loop", "validate", "nonexistent"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 1

    def test_list_empty_loops_dir(self, tmp_path: Path, capsys) -> None:
        """list with empty .loops/ directory shows no loops."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        with patch.object(sys, "argv", ["ll-loop", "list"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "No loops" in captured.out or captured.out.strip() == ""

    def test_list_multiple_loops(self, tmp_path: Path, capsys) -> None:
        """list shows all available loops."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        (loops_dir / "loop-a.yaml").write_text("name: a")
        (loops_dir / "loop-b.yaml").write_text("name: b")
        (loops_dir / "loop-c.yaml").write_text("name: c")

        with patch.object(sys, "argv", ["ll-loop", "list"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "loop-a" in captured.out
        assert "loop-b" in captured.out
        assert "loop-c" in captured.out

    def test_list_no_loops_dir(self, tmp_path: Path, capsys) -> None:
        """list with missing .loops/ directory handles gracefully."""
        with patch.object(sys, "argv", ["ll-loop", "list"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        # Should handle missing .loops/ gracefully
        assert result == 0

    def test_status_no_state_returns_error(self, tmp_path: Path) -> None:
        """status with no saved state returns error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        with patch.object(sys, "argv", ["ll-loop", "status", "test-loop"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 1

    def test_stop_no_running_loop_returns_error(self, tmp_path: Path) -> None:
        """stop with no running loop returns error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        with patch.object(sys, "argv", ["ll-loop", "stop", "test-loop"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 1

    def test_history_no_events_returns_gracefully(self, tmp_path: Path) -> None:
        """history with no events handles gracefully."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        with patch.object(sys, "argv", ["ll-loop", "history", "test-loop"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                from little_loops.cli import main_loop
                result = main_loop()

        # Should return 0 even with no events
        assert result == 0

    def test_compile_valid_paradigm(self, tmp_path: Path) -> None:
        """compile with valid paradigm creates output file."""
        input_file = tmp_path / "paradigm.yaml"
        input_file.write_text("""
name: test-paradigm
paradigm: simple
goal: "Test goal"
""")

        with patch("little_loops.fsm.compilers.compile_paradigm") as mock_compile:
            from little_loops.fsm.schema import FSMLoop, StateConfig
            mock_fsm = FSMLoop(
                name="compiled",
                paradigm="simple",
                initial="start",
                states={"start": StateConfig(terminal=True)},
                max_iterations=10,
            )
            mock_compile.return_value = mock_fsm

            with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 0
        # Output file should be created
        output_file = tmp_path / "paradigm.fsm.yaml"
        assert output_file.exists()

    def test_compile_with_output_flag(self, tmp_path: Path) -> None:
        """compile -o specifies output file path."""
        input_file = tmp_path / "paradigm.yaml"
        input_file.write_text("name: test\nparadigm: simple")
        output_file = tmp_path / "custom-output.yaml"

        with patch("little_loops.fsm.compilers.compile_paradigm") as mock_compile:
            from little_loops.fsm.schema import FSMLoop, StateConfig
            mock_fsm = FSMLoop(
                name="compiled",
                paradigm="simple",
                initial="start",
                states={"start": StateConfig(terminal=True)},
                max_iterations=10,
            )
            mock_compile.return_value = mock_fsm

            with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]):
                from little_loops.cli import main_loop
                result = main_loop()

        assert result == 0
        assert output_file.exists()

    def test_compile_missing_input_returns_error(self, tmp_path: Path) -> None:
        """compile with missing input file returns error."""
        with patch.object(sys, "argv", ["ll-loop", "compile", str(tmp_path / "nonexistent.yaml")]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_unknown_command_shows_help(self, capsys) -> None:
        """Unknown command shows help."""
        with patch.object(sys, "argv", ["ll-loop"]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestMainLoopIntegration -v`
- [ ] All tests call `main_loop()` directly
- [ ] No import errors or mock failures

---

### Phase 2: Add Required Imports

#### Overview
Update imports at top of test file to support new tests.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add `sys` import and `patch` from unittest.mock

```python
import sys
from unittest.mock import patch
```

#### Success Criteria

**Automated Verification**:
- [ ] Import statements work
- [ ] Tests can access `sys` and `patch`

---

### Phase 3: Run Tests and Verify

#### Overview
Run all tests to verify implementation.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_ll_loop.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_ll_loop.py`

---

## Testing Strategy

### Unit Tests
- Existing tests in `TestLoopArgumentParsing` provide unit-level coverage
- Keep existing tests for fast feedback

### Integration Tests
- New `TestMainLoopIntegration` class tests actual CLI entry point
- Uses temporary directories for isolation
- Mocks `sys.argv` and `Path.cwd` to control environment

## References

- Original issue: `.issues/enhancements/P2-ENH-053-ll-loop-integration-tests.md`
- CLI implementation: `scripts/little_loops/cli.py:415-916`
- Existing integration patterns: `scripts/tests/test_cli.py:566-660`
- Current ll-loop tests: `scripts/tests/test_ll_loop.py:1-402`

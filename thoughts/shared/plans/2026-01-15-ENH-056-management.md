# ENH-056: Add End-to-End Execution Test for ll-loop - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P1-ENH-056-ll-loop-end-to-end-execution-test.md`
- **Type**: enhancement
- **Priority**: P1
- **Action**: improve

## Current State Analysis

The `ll-loop` test suite currently lacks any test that exercises the actual execution path through `PersistentExecutor.run()`. All existing tests use `--dry-run` mode, which stops at `print_execution_plan()` without executing any loop iterations.

### Key Discoveries
- `run_foreground()` at `cli.py:574-642` orchestrates execution with progress display
- `PersistentExecutor.run()` at `persistence.py:280` wraps `FSMExecutor.run()` with state persistence
- `subprocess.run()` at `executor.py:141` is called by `DefaultActionRunner` for action execution
- Events (`state_enter`, `action_start`, `evaluate`, `route`) are emitted during execution and displayed via `display_progress()` callback at `cli.py:584-612`
- Exit code determination happens at `cli.py:642`: `0` if `terminated_by == "terminal"`, `1` otherwise

### Patterns to Follow
- Existing tests use `monkeypatch.chdir(tmp_path)` and `patch.object(sys, "argv", [...])` pattern at `test_ll_loop.py:951-955`
- `capsys` fixture captures stdout for verification at `test_ll_loop.py:681-683`
- Simple loop definitions with `exit_code` evaluator work well for deterministic tests

## Desired End State

A comprehensive test class `TestEndToEndExecution` that:
1. Actually executes loops through `main_loop()` without `--dry-run`
2. Mocks `subprocess.run()` to avoid actual shell execution
3. Verifies progress display output captures state transitions
4. Verifies correct exit codes (0 for terminal, 1 for non-terminal)
5. Tests both successful completion and max_iterations exit

### How to Verify
- Run `python -m pytest scripts/tests/test_ll_loop.py::TestEndToEndExecution -v`
- All tests pass
- Progress display output contains expected event markers

## What We're NOT Doing

- Not testing actual subprocess execution (that's integration testing)
- Not testing LLM evaluators (using deterministic `exit_code` evaluator only)
- Not testing background mode or resume functionality (separate issues)
- Not modifying any production code - purely adding tests

## Problem Analysis

The core execution path from `main_loop()` -> `cmd_run()` -> `run_foreground()` -> `executor.run()` is untested. This is the primary value proposition of `ll-loop` and represents a critical gap in test coverage.

## Solution Approach

Create a new test class `TestEndToEndExecution` in `test_ll_loop.py` with tests that:
1. Mock `subprocess.run` to return controlled exit codes
2. Execute loops via `main_loop()` without `--dry-run`
3. Capture and verify progress display output
4. Verify correct return codes

## Implementation Phases

### Phase 1: Add End-to-End Execution Tests

#### Overview
Add a new test class with tests for actual loop execution.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add new test class `TestEndToEndExecution` after `TestErrorHandling`

```python
class TestEndToEndExecution:
    """Tests for actual loop execution through PersistentExecutor.run().

    These tests verify the core execution path that --dry-run mode skips:
    - PersistentExecutor.run() is called
    - Progress display receives and formats events
    - Correct exit codes are returned

    All tests mock subprocess.run() to avoid actual shell execution.
    """

    def test_executes_loop_to_terminal_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop executes to terminal state and returns 0."""
        import subprocess
        from unittest.mock import MagicMock

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-exec
initial: check
max_iterations: 3
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-exec.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-exec"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 0
        assert mock_run.called

        captured = capsys.readouterr()
        # Verify progress display shows state entry
        assert "[1/3] check" in captured.out
        # Verify success verdict shown
        assert "\u2713" in captured.out or "success" in captured.out
        # Verify transition to terminal state
        assert "done" in captured.out
        # Verify completion message
        assert "Loop completed" in captured.out

    def test_exits_on_max_iterations(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop exits with code 1 when max_iterations reached."""
        import subprocess
        from unittest.mock import MagicMock

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-max
initial: check
max_iterations: 2
states:
  check:
    action: "echo fail"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-max.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run") as mock_run:
            # Always return failure so loop keeps iterating
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="error",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-max"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 1  # Non-terminal exit
        assert mock_run.call_count == 2  # Ran exactly max_iterations times

        captured = capsys.readouterr()
        # Should show both iterations
        assert "[1/2] check" in captured.out
        assert "[2/2] check" in captured.out

    def test_displays_failure_verdict(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Failure verdicts display with x mark."""
        import subprocess
        from unittest.mock import MagicMock

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-fail
initial: check
max_iterations: 1
states:
  check:
    action: "echo fail"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-fail.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=1,
                stdout="",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-fail"]):
                from little_loops.cli import main_loop

                main_loop()

        captured = capsys.readouterr()
        # Verify failure verdict shown with x mark
        assert "\u2717" in captured.out or "failure" in captured.out

    def test_displays_route_transition(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Route transitions are displayed."""
        import subprocess
        from unittest.mock import MagicMock

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-route
initial: check
max_iterations: 3
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: retry
  retry:
    action: "echo retry"
    next: check
  done:
    terminal: true
"""
        (loops_dir / "test-route.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-route"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Verify route transition shown
        assert "-> done" in captured.out

    def test_quiet_mode_suppresses_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--quiet flag suppresses progress display."""
        import subprocess
        from unittest.mock import MagicMock

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-quiet
initial: done
max_iterations: 1
states:
  done:
    terminal: true
"""
        (loops_dir / "test-quiet.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run"):  # Won't be called for terminal state
            with patch.object(sys, "argv", ["ll-loop", "run", "test-quiet", "--quiet"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Output should be minimal/empty in quiet mode
        assert "Running loop" not in captured.out
        assert "Loop completed" not in captured.out

    def test_creates_state_files(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Execution creates state and events files."""
        import subprocess
        from unittest.mock import MagicMock

        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-state
initial: check
max_iterations: 2
states:
  check:
    action: "echo test"
    evaluate:
      type: exit_code
    on_success: done
    on_failure: check
  done:
    terminal: true
"""
        (loops_dir / "test-state.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("subprocess.run") as mock_run:
            mock_run.return_value = MagicMock(
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-state"]):
                from little_loops.cli import main_loop

                main_loop()

        # Verify state files created
        running_dir = loops_dir / ".running"
        assert running_dir.exists()
        state_file = running_dir / "test-state.state.json"
        assert state_file.exists()
        events_file = running_dir / "test-state.events.jsonl"
        assert events_file.exists()

        # Verify events file has content
        with open(events_file) as f:
            events = [json.loads(line) for line in f if line.strip()]
        event_types = [e["event"] for e in events]
        assert "loop_start" in event_types
        assert "state_enter" in event_types
        assert "loop_complete" in event_types
```

Also need to add import for `subprocess` at top of file if not present.

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_ll_loop.py::TestEndToEndExecution -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_ll_loop.py`

**Manual Verification**:
- [ ] All 6 new tests pass
- [ ] Tests actually exercise `PersistentExecutor.run()` (verify subprocess.run is called)
- [ ] Progress display output is correctly captured and verified

---

## Testing Strategy

### Unit Tests
- Each test verifies a specific aspect of execution behavior
- `subprocess.run` is mocked to return controlled exit codes
- `capsys` verifies progress display output

### Coverage
- Terminal state completion (exit code 0)
- Max iterations exit (exit code 1)
- Failure verdict display
- Route transition display
- Quiet mode behavior
- State/events file creation

## References

- Original issue: `.issues/enhancements/P1-ENH-056-ll-loop-end-to-end-execution-test.md`
- Execution path: `cli.py:574-642` (`run_foreground()`)
- Subprocess call: `executor.py:141`
- Existing test patterns: `test_ll_loop.py:935-958`

"""Tests for ll-loop CLI command."""

from __future__ import annotations

import json
import subprocess
import sys
from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest
import yaml

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)

if TYPE_CHECKING:
    pass


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


class TestCompileEndToEnd:
    """End-to-end tests for paradigm compilation without mocking."""

    def test_compile_goal_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Goal paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: goal
goal: "No errors"
tools:
  - "echo check"
  - "echo fix"
"""
        input_file = tmp_path / "goal.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "goal.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        assert output_file.exists()

        # Verify output structure
        fsm_data = yaml.safe_load(output_file.read_text())
        assert "states" in fsm_data
        assert "initial" in fsm_data
        assert fsm_data["initial"] == "evaluate"
        assert "evaluate" in fsm_data["states"]
        assert "fix" in fsm_data["states"]
        assert "done" in fsm_data["states"]

    def test_compile_convergence_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Convergence paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: convergence
name: "reduce-errors"
check: "echo 5"
toward: 0
using: "echo fix"
"""
        input_file = tmp_path / "convergence.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "convergence.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

        fsm_data = yaml.safe_load(output_file.read_text())
        assert fsm_data["initial"] == "measure"
        assert "measure" in fsm_data["states"]
        assert "apply" in fsm_data["states"]
        assert "done" in fsm_data["states"]

    def test_compile_invariants_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Invariants paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: invariants
name: "quality-checks"
constraints:
  - name: "tests"
    check: "echo test"
    fix: "echo fix-tests"
  - name: "lint"
    check: "echo lint"
    fix: "echo fix-lint"
"""
        input_file = tmp_path / "invariants.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "invariants.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

        fsm_data = yaml.safe_load(output_file.read_text())
        assert fsm_data["initial"] == "check_tests"
        assert "check_tests" in fsm_data["states"]
        assert "fix_tests" in fsm_data["states"]
        assert "check_lint" in fsm_data["states"]
        assert "fix_lint" in fsm_data["states"]
        assert "all_valid" in fsm_data["states"]

    def test_compile_imperative_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Imperative paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: imperative
name: "fix-cycle"
steps:
  - "echo step1"
  - "echo step2"
until:
  check: "echo done"
"""
        input_file = tmp_path / "imperative.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "imperative.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

        fsm_data = yaml.safe_load(output_file.read_text())
        assert fsm_data["initial"] == "step_0"
        assert "step_0" in fsm_data["states"]
        assert "step_1" in fsm_data["states"]
        assert "check_done" in fsm_data["states"]
        assert "done" in fsm_data["states"]

    def test_compiled_output_passes_validation(self, tmp_path: Path) -> None:
        """Compiled FSM passes validate_fsm() check."""
        paradigm_yaml = """
paradigm: goal
goal: "Test validation"
tools:
  - "echo check"
  - "echo fix"
"""
        input_file = tmp_path / "validate-test.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "validate-test.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

        # Load and validate the FSM
        from little_loops.fsm.schema import FSMLoop
        from little_loops.fsm.validation import validate_fsm

        fsm_data = yaml.safe_load(output_file.read_text())
        fsm = FSMLoop.from_dict(fsm_data)
        errors = validate_fsm(fsm)

        # No error-level validation issues
        assert not any(e.severity.value == "error" for e in errors)

    def test_compile_unknown_paradigm_returns_error(self, tmp_path: Path) -> None:
        """Unknown paradigm type returns error."""
        paradigm_yaml = """
paradigm: nonexistent-type
name: "test"
"""
        input_file = tmp_path / "unknown.paradigm.yaml"
        input_file.write_text(paradigm_yaml)

        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_compile_goal_missing_required_field_returns_error(self, tmp_path: Path) -> None:
        """Goal paradigm missing 'goal' field returns error."""
        paradigm_yaml = """
paradigm: goal
tools:
  - "echo check"
"""
        input_file = tmp_path / "incomplete.paradigm.yaml"
        input_file.write_text(paradigm_yaml)

        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_compile_default_output_path(self, tmp_path: Path) -> None:
        """Without -o flag, output uses input filename with .fsm.yaml extension."""
        paradigm_yaml = """
paradigm: goal
goal: "Test"
tools:
  - "echo check"
"""
        input_file = tmp_path / "my-paradigm.yaml"
        input_file.write_text(paradigm_yaml)

        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        # Default output replaces .yaml with .fsm.yaml
        default_output = tmp_path / "my-paradigm.fsm.yaml"
        assert default_output.exists()


class TestEndToEndExecution:
    """Tests for actual loop execution through PersistentExecutor.run().

    These tests verify the core execution path that --dry-run mode skips:
    - PersistentExecutor.run() is called and executes the loop
    - Correct exit codes are returned (0 for terminal, 1 for non-terminal)
    - State and events files are created during execution
    - Completion messages display correct final state and iteration count

    All tests mock subprocess.run() at the executor level to avoid actual
    shell execution while still exercising the full execution path.

    Note: These tests verify event generation via the events file rather than
    display output, as the display callback mechanism requires separate testing.
    """

    def test_executes_loop_to_terminal_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop executes to terminal state and returns 0."""
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
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
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
        # Verify loop header displayed
        assert "Running loop: test-exec" in captured.out
        assert "Max iterations: 3" in captured.out
        # Verify completion message shows correct final state
        assert "Loop completed: done" in captured.out
        assert "1 iterations" in captured.out

    def test_exits_on_max_iterations(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop exits with code 1 when max_iterations reached."""
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
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            # Always return failure so loop keeps iterating
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo fail"],
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
        # Verify loop header and completion message
        assert "Running loop: test-max" in captured.out
        assert "Max iterations: 2" in captured.out
        # Final state is check (not done) because max_iterations reached
        assert "Loop completed: check" in captured.out
        assert "2 iterations" in captured.out

    def test_reports_final_state_on_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop reports correct final state when action fails."""
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
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo fail"],
                returncode=1,
                stdout="",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-fail"]):
                from little_loops.cli import main_loop

                main_loop()

        captured = capsys.readouterr()
        # Verify completion message - final state is check (stayed there after failure)
        assert "Loop completed: check" in captured.out
        assert "1 iterations" in captured.out

    def test_successful_route_to_terminal(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Loop with multiple states routes successfully to terminal."""
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
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-route"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Verify successful completion
        assert "Loop completed: done" in captured.out
        assert "1 iterations" in captured.out

    def test_quiet_mode_suppresses_output(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--quiet flag suppresses progress display."""
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
        # Note: Won't actually call subprocess.run for terminal-only loop
        with patch("little_loops.fsm.executor.subprocess.run"):
            with patch.object(sys, "argv", ["ll-loop", "run", "test-quiet", "--quiet"]):
                from little_loops.cli import main_loop

                result = main_loop()

            assert result == 0
            captured = capsys.readouterr()
            # Output should be minimal/empty in quiet mode
            assert "Running loop" not in captured.out
            assert "Loop completed" not in captured.out

    def test_quiet_mode_suppresses_logo(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--quiet flag suppresses logo display."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-quiet-logo
initial: done
max_iterations: 1
states:
  done:
    terminal: true
"""
        (loops_dir / "test-quiet-logo.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run"):
            with patch.object(sys, "argv", ["ll-loop", "run", "test-quiet-logo", "--quiet"]):
                from little_loops.cli import main_loop

                result = main_loop()

            assert result == 0
            captured = capsys.readouterr()
            # Logo should not be displayed in quiet mode
            assert "little loops" not in captured.out

    def test_per_iteration_progress_shows_state_and_elapsed(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Each iteration prints iteration number, state name, and elapsed time."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-progress
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
        (loops_dir / "test-progress.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-progress"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Per-iteration line must contain iteration number, state name, and elapsed time in (Xs) format
        assert "[1/3] check" in captured.out
        assert "(0s)" in captured.out

    def test_per_iteration_progress_suppressed_by_quiet(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--quiet suppresses per-iteration progress lines."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-quiet-iter
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
        (loops_dir / "test-quiet-iter.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(sys, "argv", ["ll-loop", "run", "test-quiet-iter", "--quiet"]):
                from little_loops.cli import main_loop

                result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # No per-iteration lines in quiet mode
        assert "[1/" not in captured.out

    def test_background_flag_shows_warning(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """--background flag shows warning that it's not implemented."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-background
initial: done
max_iterations: 1
states:
  done:
    terminal: true
"""
        (loops_dir / "test-background.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch("little_loops.fsm.executor.subprocess.run"):
            with patch.object(sys, "argv", ["ll-loop", "run", "test-background", "--background"]):
                from little_loops.cli import main_loop

                result = main_loop()

            assert result == 0
            captured = capsys.readouterr()
            # Warning should appear about background mode
            assert "Background mode not yet implemented" in captured.out
            assert "running in foreground" in captured.out

    def test_creates_state_files(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Execution creates state and events files."""
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
        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
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
        # Verify all expected event types were emitted
        assert "loop_start" in event_types
        assert "state_enter" in event_types
        assert "action_start" in event_types
        assert "action_complete" in event_types
        assert "evaluate" in event_types
        assert "route" in event_types
        assert "loop_complete" in event_types


class TestLLMFlags:
    """Tests for --no-llm and --llm-model CLI flags.

    These tests verify that the LLM-related CLI flags are correctly parsed
    and their values are properly passed through to the FSM configuration.
    """

    def test_no_llm_flag_accepted_with_dry_run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-llm flag is accepted by the CLI with --dry-run."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: done
states:
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm", "--dry-run"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_llm_model_flag_accepted_with_dry_run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--llm-model flag is accepted by the CLI with --dry-run."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: done
states:
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys,
            "argv",
            ["ll-loop", "run", "test-loop", "--llm-model", "claude-opus-4-20250514", "--dry-run"],
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_no_llm_and_llm_model_combined(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """Both --no-llm and --llm-model flags can be used together."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: done
states:
  done:
    terminal: true
"""
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys,
            "argv",
            [
                "ll-loop",
                "run",
                "test-loop",
                "--no-llm",
                "--llm-model",
                "claude-opus-4-20250514",
                "--dry-run",
            ],
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_no_llm_sets_fsm_llm_enabled_false(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-llm sets fsm.llm.enabled to False before execution."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: check
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
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        captured_fsm = None

        # Import here to get original init before patching
        from little_loops.fsm.persistence import PersistentExecutor

        original_init: Callable[..., None] = PersistentExecutor.__init__

        def capture_persistent_executor_init(self: Any, fsm: Any, **kwargs: Any) -> None:
            nonlocal captured_fsm
            captured_fsm = fsm
            # Call original init
            original_init(self, fsm, **kwargs)

        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(PersistentExecutor, "__init__", capture_persistent_executor_init):
                with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm"]):
                    from little_loops.cli import main_loop

                    main_loop()

        assert captured_fsm is not None
        assert captured_fsm.llm.enabled is False

    def test_llm_model_sets_fsm_llm_model(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--llm-model sets fsm.llm.model to the specified value."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: check
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
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        captured_fsm = None

        # Import here to get original init before patching
        from little_loops.fsm.persistence import PersistentExecutor

        original_init: Callable[..., None] = PersistentExecutor.__init__

        def capture_persistent_executor_init(self: Any, fsm: Any, **kwargs: Any) -> None:
            nonlocal captured_fsm
            captured_fsm = fsm
            original_init(self, fsm, **kwargs)

        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(PersistentExecutor, "__init__", capture_persistent_executor_init):
                with patch.object(
                    sys,
                    "argv",
                    ["ll-loop", "run", "test-loop", "--llm-model", "claude-opus-4-20250514"],
                ):
                    from little_loops.cli import main_loop

                    main_loop()

        assert captured_fsm is not None
        assert captured_fsm.llm.model == "claude-opus-4-20250514"

    def test_llm_model_overrides_default_model(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--llm-model overrides the default model value."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Loop with custom llm config that will be overridden
        loop_content = """
name: test-loop
initial: check
llm:
  model: "claude-sonnet-4-20250514"
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
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        captured_fsm = None

        # Import here to get original init before patching
        from little_loops.fsm.persistence import PersistentExecutor

        original_init: Callable[..., None] = PersistentExecutor.__init__

        def capture_persistent_executor_init(self: Any, fsm: Any, **kwargs: Any) -> None:
            nonlocal captured_fsm
            captured_fsm = fsm
            original_init(self, fsm, **kwargs)

        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(PersistentExecutor, "__init__", capture_persistent_executor_init):
                with patch.object(
                    sys,
                    "argv",
                    ["ll-loop", "run", "test-loop", "--llm-model", "claude-opus-4-20250514"],
                ):
                    from little_loops.cli import main_loop

                    main_loop()

        assert captured_fsm is not None
        # CLI flag should override the YAML-specified model
        assert captured_fsm.llm.model == "claude-opus-4-20250514"

    def test_no_llm_preserves_other_llm_config(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """--no-llm only changes enabled, preserving other LLM settings."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_content = """
name: test-loop
initial: check
llm:
  model: "claude-opus-4-20250514"
  max_tokens: 512
  timeout: 60
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
        (loops_dir / "test-loop.yaml").write_text(loop_content)

        monkeypatch.chdir(tmp_path)
        captured_fsm = None

        # Import here to get original init before patching
        from little_loops.fsm.persistence import PersistentExecutor

        original_init: Callable[..., None] = PersistentExecutor.__init__

        def capture_persistent_executor_init(self: Any, fsm: Any, **kwargs: Any) -> None:
            nonlocal captured_fsm
            captured_fsm = fsm
            original_init(self, fsm, **kwargs)

        with patch("little_loops.fsm.executor.subprocess.run") as mock_run:
            mock_run.return_value = subprocess.CompletedProcess(
                args=["bash", "-c", "echo test"],
                returncode=0,
                stdout="test",
                stderr="",
            )
            with patch.object(PersistentExecutor, "__init__", capture_persistent_executor_init):
                with patch.object(sys, "argv", ["ll-loop", "run", "test-loop", "--no-llm"]):
                    from little_loops.cli import main_loop

                    main_loop()

        assert captured_fsm is not None
        assert captured_fsm.llm.enabled is False
        # Other settings should be preserved from YAML
        assert captured_fsm.llm.model == "claude-opus-4-20250514"
        assert captured_fsm.llm.max_tokens == 512
        assert captured_fsm.llm.timeout == 60


class TestCmdTest:
    """Tests for ll-loop test subcommand."""

    def test_test_nonexistent_loop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with non-existent loop shows error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1
        captured = capsys.readouterr()
        assert "not found" in captured.out.lower() or "not found" in captured.err.lower()

    def test_test_shell_action_success(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with successful shell command shows success verdict."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
paradigm: goal
name: test-echo
goal: echo works
tools:
  - "echo hello"
  - "echo fixed"
max_iterations: 5
"""
        (loops_dir / "test-echo.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-echo"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "SUCCESS" in captured.out
        assert "evaluate → done" in captured.out or "evaluate" in captured.out
        assert "configured correctly" in captured.out

    def test_test_shell_action_failure(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with failing shell command shows failure verdict."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
paradigm: goal
name: test-fail
goal: exit with error
tools:
  - "exit 1"
  - "echo fixed"
max_iterations: 5
"""
        (loops_dir / "test-fail.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-fail"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0  # Test succeeds even if loop would fail
        captured = capsys.readouterr()
        assert "FAILURE" in captured.out
        assert "evaluate → fix" in captured.out or "fix" in captured.out
        assert "configured correctly" in captured.out

    def test_test_slash_command_skipped(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with slash command action is skipped."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
paradigm: goal
name: test-slash
goal: slash command works
tools:
  - "/ll:check-code"
  - "/ll:check-code fix"
max_iterations: 5
"""
        (loops_dir / "test-slash.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-slash"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0  # Should succeed but skip execution
        captured = capsys.readouterr()
        assert "SKIPPED" in captured.out
        assert "slash command" in captured.out.lower()
        assert "valid" in captured.out

    def test_test_parse_error_in_evaluator(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with evaluator that can't parse output shows error verdict."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
name: test-parse-error
initial: check
states:
  check:
    action: "echo 'not a number'"
    evaluate:
      type: output_numeric
      operator: eq
      target: 0
    on_success: done
    on_failure: fix
    on_error: done
  fix:
    action: "echo fixing"
    next: check
  done:
    terminal: true
max_iterations: 5
"""
        (loops_dir / "test-parse-error.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-parse-error"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1  # Test fails due to evaluator error
        captured = capsys.readouterr()
        assert "ERROR" in captured.out
        assert "output_numeric" in captured.out
        assert "issues" in captured.out.lower()

    def test_test_no_action_initial_state(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Test with initial state having no action shows no action to test."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_yaml = """
name: test-no-action
initial: start
states:
  start:
    next: done
  done:
    terminal: true
max_iterations: 5
"""
        (loops_dir / "test-no-action.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "test", "test-no-action"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "no action" in captured.out.lower()
        assert "valid" in captured.out.lower()

    def test_test_subcommand_registered(self) -> None:
        """Test subcommand is registered in known_subcommands."""
        # This verifies the subcommand won't be treated as a loop name
        import sys as _sys
        from unittest.mock import patch as mock_patch

        with mock_patch.object(_sys, "argv", ["ll-loop", "test", "--help"]):
            # If test is not a known subcommand, it would be parsed as a loop name
            # and "run" would be inserted, causing different behavior
            from little_loops.cli import main_loop

            # Should not raise SystemExit for unrecognized subcommand
            # (--help will cause SystemExit 0, which is expected)
            try:
                main_loop()
            except SystemExit as e:
                # --help causes exit 0
                assert e.code == 0


class TestCmdSimulate:
    """Tests for ll-loop simulate command."""

    def test_simulate_subcommand_registered(self) -> None:
        """Simulate subcommand is registered in known_subcommands."""
        import sys as _sys
        from unittest.mock import patch as mock_patch

        with mock_patch.object(_sys, "argv", ["ll-loop", "simulate", "--help"]):
            from little_loops.cli import main_loop

            try:
                main_loop()
            except SystemExit as e:
                assert e.code == 0

    def test_simulate_nonexistent_loop(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """simulate with nonexistent loop returns error."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "simulate", "nonexistent"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1

    def test_simulate_all_pass_scenario(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """simulate with --scenario=all-pass runs to terminal."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = """
name: test-sim
initial: check
states:
  check:
    action: "run_check"
    on_success: done
    on_failure: fix
  fix:
    action: "run_fix"
    next: check
  done:
    terminal: true
max_iterations: 5
"""
        (loops_dir / "test-sim.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "simulate", "test-sim", "--scenario=all-pass"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATION: test-sim" in captured.out
        assert "scenario=all-pass" in captured.out
        assert "Summary" in captured.out
        assert "terminal" in captured.out

    def test_simulate_first_fail_scenario(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """simulate with --scenario=first-fail shows fix transition."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = """
name: test-sim
initial: check
states:
  check:
    action: "run_check"
    on_success: done
    on_failure: fix
  fix:
    action: "run_fix"
    next: check
  done:
    terminal: true
max_iterations: 5
"""
        (loops_dir / "test-sim.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "simulate", "test-sim", "--scenario=first-fail"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # First fail means: check (fail) -> fix -> check (pass) -> done
        assert "check → fix" in captured.out
        assert "fix → check" in captured.out
        assert "check → done" in captured.out

    def test_simulate_max_iterations_limit(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """simulate caps iterations at 20 by default."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = """
name: test-sim
initial: check
states:
  check:
    action: "run_check"
    on_success: done
    on_failure: check
  done:
    terminal: true
max_iterations: 100
"""
        (loops_dir / "test-sim.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "simulate", "test-sim", "--scenario=all-fail"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "Limiting simulation to 20 iterations" in captured.out
        assert "max_iterations" in captured.out

    def test_simulate_custom_max_iterations(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """simulate respects --max-iterations override."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = """
name: test-sim
initial: check
states:
  check:
    action: "run_check"
    on_success: done
    on_failure: check
  done:
    terminal: true
max_iterations: 100
"""
        (loops_dir / "test-sim.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys,
            "argv",
            ["ll-loop", "simulate", "test-sim", "--scenario=all-fail", "-n", "3"],
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        # Should not show limiting message since user explicitly set iterations
        assert "Limiting simulation" not in captured.out
        assert "Iterations: 3" in captured.out

    def test_simulate_shows_simulated_actions(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """simulate output shows [SIMULATED] markers."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_yaml = """
name: test-sim
initial: check
states:
  check:
    action: "mypy src/"
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        (loops_dir / "test-sim.yaml").write_text(loop_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "simulate", "test-sim", "--scenario=all-pass"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "[SIMULATED]" in captured.out
        assert "mypy src/" in captured.out

    def test_simulate_with_paradigm_file(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """simulate auto-compiles paradigm files."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        # Use imperative paradigm with correct structure
        paradigm_yaml = """
name: imperative-test
paradigm: imperative
steps:
  - "echo step1"
  - "echo step2"
until:
  check: "echo done"
"""
        (loops_dir / "imperative-test.yaml").write_text(paradigm_yaml)

        monkeypatch.chdir(tmp_path)
        with patch.object(
            sys, "argv", ["ll-loop", "simulate", "imperative-test", "--scenario=all-pass"]
        ):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0
        captured = capsys.readouterr()
        assert "SIMULATION: imperative-test" in captured.out
        # With all-pass scenario, terminates on success
        assert "terminal" in captured.out

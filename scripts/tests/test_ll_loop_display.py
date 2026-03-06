"""Tests for ll-loop CLI command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from little_loops.cli.loop._helpers import run_foreground
from little_loops.cli.loop.info import _render_fsm_diagram
from little_loops.fsm.executor import ExecutionResult
from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)

if TYPE_CHECKING:
    pass


class MockExecutor:
    """Mock executor that emits a fixed sequence of events then returns a result."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        self._events = events
        self._on_event: Any = None

    def run(self) -> ExecutionResult:
        for event in self._events:
            if self._on_event:
                self._on_event(event)
        return ExecutionResult(
            final_state="done",
            iterations=1,
            terminated_by="terminal",
            duration_ms=100,
            captured={},
        )


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


class TestStateToDict:
    """Tests for StateConfig.to_dict() method using real StateConfig objects."""

    def test_simple_state_with_action(self) -> None:
        """Convert state with action and on_success."""
        state = make_test_state(action="echo hello", on_success="done")
        result = state.to_dict()
        assert result == {"action": "echo hello", "on_success": "done"}

    def test_terminal_state(self) -> None:
        """Convert terminal state to dict."""
        state = make_test_state(terminal=True)
        result = state.to_dict()
        assert result == {"terminal": True}

    def test_state_with_failure_routing(self) -> None:
        """Convert state with on_failure."""
        state = make_test_state(
            action="pytest",
            on_success="done",
            on_failure="fix",
        )
        result = state.to_dict()
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
        result = state.to_dict()
        assert result == {
            "action": "risky_command",
            "on_success": "done",
            "on_error": "handle_error",
        }

    def test_state_with_next(self) -> None:
        """Convert state with unconditional next."""
        state = make_test_state(action="echo step", next="next_state")
        result = state.to_dict()
        assert result == {"action": "echo step", "next": "next_state"}

    def test_state_with_evaluate_exit_code(self) -> None:
        """Convert state with exit_code evaluator."""
        state = make_test_state(
            action="pytest",
            evaluate=EvaluateConfig(type="exit_code"),
            on_success="done",
            on_failure="fix",
        )
        result = state.to_dict()
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
        result = state.to_dict()
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
        result = state.to_dict()
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
        result = state.to_dict()
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
        result = state.to_dict()
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
        result = state.to_dict()
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
        result = state.to_dict()
        assert result["route"] == {"pass": "done", "fail": "fix"}
        assert "_" not in result["route"]

    def test_state_with_capture(self) -> None:
        """Convert state with capture variable."""
        state = make_test_state(
            action="wc -l errors.log",
            capture="error_count",
            on_success="check",
        )
        result = state.to_dict()
        assert result["capture"] == "error_count"

    def test_state_with_timeout(self) -> None:
        """Convert state with timeout."""
        state = make_test_state(
            action="slow_command",
            timeout=300,
            on_success="done",
        )
        result = state.to_dict()
        assert result["timeout"] == 300

    def test_state_with_on_maintain(self) -> None:
        """Convert state with on_maintain."""
        state = make_test_state(
            action="monitor",
            on_maintain="monitor",
            on_success="done",
        )
        result = state.to_dict()
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
        result = state.to_dict()
        assert "action" in result
        assert "evaluate" in result
        assert "on_success" in result
        assert "on_failure" in result
        assert "on_error" in result
        assert "capture" in result
        assert "timeout" in result


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

    def test_prompt_action_shows_3_lines_in_dry_run(
        self,
        tmp_path: Path,
        monkeypatch: pytest.MonkeyPatch,
        capsys: pytest.CaptureFixture[str],
    ) -> None:
        """Prompt action type shows first 3 lines in dry-run execution plan."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        long_prompt = "\n".join(f"Line {i}: " + "x" * 50 for i in range(10))
        yaml_content = "name: test\ninitial: fix\nstates:\n  fix:\n    action: |\n"
        for line in long_prompt.splitlines():
            yaml_content += f"      {line}\n"
        yaml_content += (
            "    action_type: prompt\n    on_success: done\n  done:\n    terminal: true\n"
        )
        (loops_dir / "test.yaml").write_text(yaml_content)
        monkeypatch.chdir(tmp_path)
        with patch.object(sys, "argv", ["ll-loop", "run", "test", "--dry-run"]):
            from little_loops.cli import main_loop

            main_loop()

        captured = capsys.readouterr()
        assert "..." in captured.out
        assert "Line 0" in captured.out
        assert "Line 9" not in captured.out

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


class TestProgressDisplay:
    """Tests for progress display formatting."""

    @pytest.mark.parametrize(
        "duration_ms,expected",
        [
            (5200, "5.2s"),
            (30000, "30.0s"),
            (59900, "59.9s"),
        ],
    )
    def test_duration_seconds(self, duration_ms: int, expected: str) -> None:
        """Duration under 60s formatted as seconds."""
        duration_sec = duration_ms / 1000
        assert duration_sec < 60
        duration_str = f"{duration_sec:.1f}s"
        assert duration_str == expected

    @pytest.mark.parametrize(
        "duration_ms,expected",
        [
            (60000, "1m 0s"),
            (90000, "1m 30s"),
            (150000, "2m 30s"),
            (3600000, "60m 0s"),
        ],
    )
    def test_duration_minutes(self, duration_ms: int, expected: str) -> None:
        """Duration over 60s formatted as minutes."""
        duration_sec = duration_ms / 1000
        assert duration_sec >= 60
        minutes = int(duration_sec // 60)
        seconds = duration_sec % 60
        duration_str = f"{minutes}m {seconds:.0f}s"
        assert duration_str == expected

    @pytest.mark.parametrize(
        "verdict,expected_symbol",
        [
            ("success", "\u2713"),
            ("target", "\u2713"),
            ("progress", "\u2713"),
            ("failure", "\u2717"),
            ("stall", "\u2717"),
            ("error", "\u2717"),
            ("blocked", "\u2717"),
        ],
    )
    def test_verdict_symbols(self, verdict: str, expected_symbol: str) -> None:
        """Correct symbols for success/failure verdicts."""
        success_verdicts = ("success", "target", "progress")
        symbol = "\u2713" if verdict in success_verdicts else "\u2717"
        assert symbol == expected_symbol

    @pytest.mark.parametrize(
        "action_length,expect_truncation",
        [
            (50, False),
            (120, False),
            (121, True),
            (150, True),
            (200, True),
        ],
    )
    def test_action_truncation(self, action_length: int, expect_truncation: bool) -> None:
        """Actions over 120 chars are truncated with ellipsis."""
        action = "x" * action_length
        action_display = action[:120] + "..." if len(action) > 120 else action
        if expect_truncation:
            assert len(action_display) == 123  # 120 chars + "..."
            assert action_display.endswith("...")
        else:
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


class TestRenderFsmDiagram:
    """Tests for _render_fsm_diagram() output."""

    def _make_fsm(
        self,
        name: str = "test",
        initial: str = "start",
        states: dict[str, StateConfig] | None = None,
    ) -> FSMLoop:
        return FSMLoop(name=name, initial=initial, states=states or {}, max_iterations=50)

    def test_single_terminal_state(self) -> None:
        """Single terminal state renders just the state box."""
        fsm = self._make_fsm(
            initial="done",
            states={"done": StateConfig(terminal=True)},
        )
        result = _render_fsm_diagram(fsm)
        assert "done" in result
        assert "\u250c" in result  # box top-left corner

    def test_linear_flow_shows_labels(self) -> None:
        """Linear A->B->C shows transition labels in main flow line."""
        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step a", on_success="b"),
                "b": StateConfig(action="step b", on_success="c"),
                "c": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        # All three states appear in boxes
        assert "a" in result
        assert "b" in result
        assert "c" in result
        # Transition labels are shown
        assert "success" in result
        # Box-drawing characters present
        assert "\u250c" in result

    def test_next_transition_label(self) -> None:
        """Unconditional next transition shows 'next' label."""
        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="echo", next="b"),
                "b": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        assert "next" in result

    def test_branching_fsm_shows_branches_section(self) -> None:
        """Failure branch not on main path appears visually as 2D box."""
        fsm = self._make_fsm(
            initial="test",
            states={
                "test": StateConfig(action="pytest", on_success="done", on_failure="fix"),
                "fix": StateConfig(action="fix.sh", on_success="done"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        # Main flow states in boxes
        assert "test" in result
        assert "done" in result
        assert "success" in result
        # Branch edges shown
        assert "fail" in result
        assert "\u25b6" in result  # arrow head ▶
        # Off-path state rendered as box (not just text)
        lines = result.split("\n")
        fix_box_lines = [line for line in lines if "fix" in line and "\u2502" in line]
        assert fix_box_lines, "fix should be rendered inside a box with │ borders"

    def test_cyclic_fsm_shows_back_edges_section(self) -> None:
        """Back-edge (retry loop) rendered with 2D vertical connectors."""
        fsm = self._make_fsm(
            initial="evaluate",
            states={
                "evaluate": StateConfig(action="check", on_success="done", on_failure="fix"),
                "fix": StateConfig(action="fix.sh", on_success="evaluate"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        # fix -> evaluate back-edge: both states and label appear
        assert "evaluate" in result
        assert "fix" in result
        assert "fail" in result
        # Vertical connectors present for routed edges
        assert "\u2502" in result  # │ vertical connector
        # Off-path box rendered with box-drawing chars
        assert "\u25b2" in result or "\u25bc" in result  # ▲ or ▼ arrow

    def test_self_loop_annotated(self) -> None:
        """Self-loop transition is annotated with loop indicator."""
        fsm = self._make_fsm(
            initial="monitor",
            states={
                "monitor": StateConfig(
                    action="check",
                    on_success="done",
                    on_failure="monitor",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        assert "\u21ba" in result  # ↺ self-loop indicator

    def test_route_table_branches(self) -> None:
        """Route table verdicts appear for non-main-flow targets."""
        fsm = self._make_fsm(
            initial="route_state",
            states={
                "route_state": StateConfig(
                    action="analyze",
                    route=RouteConfig(
                        routes={"pass": "done", "fail": "retry", "skip": "done"},
                        default=None,
                    ),
                ),
                "done": StateConfig(terminal=True),
                "retry": StateConfig(action="retry", on_success="done"),
            },
        )
        result = _render_fsm_diagram(fsm)
        # Main path states in boxes
        assert "route_state" in result
        assert "done" in result
        # Route labels appear
        assert "pass" in result
        assert "fail" in result
        assert "skip" in result

    def test_main_flow_order(self) -> None:
        """Main flow states appear in left-to-right order."""
        fsm = self._make_fsm(
            initial="first",
            states={
                "first": StateConfig(action="a", on_success="second"),
                "second": StateConfig(action="b", on_success="third"),
                "third": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        # Name row is index 1 (index 0 is top border)
        name_line = result.split("\n")[1]
        pos_first = name_line.index("first")
        pos_second = name_line.index("second")
        pos_third = name_line.index("third")
        assert pos_first < pos_second < pos_third

    def test_bidirectional_back_edge_both_pipes_on_label_rows(self) -> None:
        """Both │ pipes appear on each label row when connector has up+down edges."""
        fsm = self._make_fsm(
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="check",
                    on_success="done",
                    on_failure="fix",
                    on_error="fix",
                ),
                "fix": StateConfig(action="fix.sh", next="evaluate"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")
        # Find rows that contain a label (fail or next)
        fail_rows = [ln for ln in lines if "fail" in ln]
        next_rows = [ln for ln in lines if "next" in ln and "\u2502" in ln]
        # Each label row must contain both │ characters (two pipe chars)
        for row in fail_rows + next_rows:
            assert row.count("\u2502") >= 2, f"Expected both pipes on label row: {row!r}"

    def test_multiple_off_path_states_same_depth(self) -> None:
        """Two off-path states appear at the same vertical depth (side-by-side)."""
        # Mirrors fix-quality-and-tests: two check→fix pairs with fix-tests→check-quality cross-edge
        fsm = self._make_fsm(
            initial="check-quality",
            states={
                "check-quality": StateConfig(
                    action="lint",
                    on_success="check-tests",
                    on_failure="fix-quality",
                ),
                "fix-quality": StateConfig(action="fix lint", next="check-quality"),
                "check-tests": StateConfig(
                    action="pytest",
                    on_success="done",
                    on_failure="fix-tests",
                ),
                "fix-tests": StateConfig(action="fix tests", next="check-quality"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")

        # Both off-path box name rows must appear on the SAME line index
        fix_quality_row = next(
            (i for i, ln in enumerate(lines) if "fix-quality" in ln and "\u2502" in ln), None
        )
        fix_tests_row = next(
            (i for i, ln in enumerate(lines) if "fix-tests" in ln and "\u2502" in ln), None
        )
        assert fix_quality_row is not None, "fix-quality box not found"
        assert fix_tests_row is not None, "fix-tests box not found"
        assert fix_quality_row == fix_tests_row, (
            f"fix-quality at row {fix_quality_row}, fix-tests at row {fix_tests_row}; "
            "expected same row (side-by-side layout)"
        )

        # fix-tests should show a left-going arrow (◄) for its cross-edge to check-quality
        fix_tests_name_line = lines[fix_tests_row]
        assert "\u25c4" in fix_tests_name_line, (
            f"Expected ◄ left-going arrow on fix-tests name row: {fix_tests_name_line!r}"
        )


class TestDisplayProgressEvents:
    """Tests for display_progress event formatting in run_foreground."""

    def _make_args(self, quiet: bool = False, verbose: bool = False) -> argparse.Namespace:
        return argparse.Namespace(quiet=quiet, verbose=verbose)

    def _make_fsm(self) -> FSMLoop:
        return make_test_fsm()

    def test_action_complete_exit_124_shown_as_timed_out(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Exit code 124 is displayed as 'timed out' not 'exit: 124'."""
        events = [
            {"event": "action_complete", "duration_ms": 120000, "exit_code": 124},
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args())
        captured = capsys.readouterr()
        assert "timed out" in captured.out
        assert "exit: 124" not in captured.out

    def test_action_complete_nonzero_exit_shown_as_exit_code(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-124 non-zero exit codes are displayed as 'exit: N'."""
        events = [
            {"event": "action_complete", "duration_ms": 1000, "exit_code": 1},
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args())
        captured = capsys.readouterr()
        assert "exit: 1" in captured.out
        assert "timed out" not in captured.out

    def test_evaluate_error_shows_raw_preview(self, capsys: pytest.CaptureFixture[str]) -> None:
        """raw_preview is shown below error verdict line."""
        events = [
            {
                "event": "evaluate",
                "verdict": "error",
                "error": "Empty result field in Claude CLI response",
                "raw_preview": '{"is_error": false, "result": ""}',
            },
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args())
        captured = capsys.readouterr()
        assert "raw:" in captured.out
        assert '{"is_error": false' in captured.out

    def test_evaluate_success_no_raw_preview(self, capsys: pytest.CaptureFixture[str]) -> None:
        """raw_preview is not shown for successful verdicts."""
        events = [
            {
                "event": "evaluate",
                "verdict": "success",
                "confidence": 0.9,
                "raw_preview": "should not appear",
            },
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args())
        captured = capsys.readouterr()
        assert "should not appear" not in captured.out
        assert "raw:" not in captured.out

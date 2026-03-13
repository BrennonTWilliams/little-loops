"""Tests for ll-loop CLI command."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import TYPE_CHECKING, Any
from unittest.mock import patch

import pytest

from little_loops.cli.loop._helpers import EXIT_CODES, run_foreground
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
        assert "\u25b6" in result or "\u25bc" in result  # ▶ or ▼ arrow
        # Corner characters at pipe-to-horizontal turns
        assert "\u2514" in result or "\u250c" in result  # └ or ┌ corner chars

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
        """Main flow states appear in top-to-bottom order (vertical layout)."""
        fsm = self._make_fsm(
            initial="first",
            states={
                "first": StateConfig(action="a", on_success="second"),
                "second": StateConfig(action="b", on_success="third"),
                "third": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")
        # Find the row index where each state name appears in a box (with │ border)
        first_row = next(i for i, ln in enumerate(lines) if "first" in ln and "\u2502" in ln)
        second_row = next(i for i, ln in enumerate(lines) if "second" in ln and "\u2502" in ln)
        third_row = next(i for i, ln in enumerate(lines) if "third" in ln and "\u2502" in ln)
        assert first_row < second_row < third_row

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
        """Two off-path states appear in boxes with back-edges to main path."""
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

        # Both off-path states must appear in boxes
        fix_quality_row = next(
            (i for i, ln in enumerate(lines) if "fix-quality" in ln and "\u2502" in ln), None
        )
        fix_tests_row = next(
            (i for i, ln in enumerate(lines) if "fix-tests" in ln and "\u2502" in ln), None
        )
        assert fix_quality_row is not None, "fix-quality box not found"
        assert fix_tests_row is not None, "fix-tests box not found"

        # In layered layout, fix-quality and fix-tests are at different depths
        # (fix-quality at depth 1, fix-tests at depth 2). Both should be visible.
        # Back-edges should be rendered (▲ for upward arrows in margin)
        assert "\u25b6" in result, (
            "Expected \u25b6 (▶) margin back-edge arrow for back-edges to check-quality"
        )

    def test_linear_off_path_chain_all_states_visible(self) -> None:
        """All states in a linear off-path chain appear as distinct non-overlapping boxes.

        Regression for BUG-658: fix/check_commit/commit form a chain below evaluate,
        all back-anchored to the same main-path state. In the layered layout, these
        states appear at increasing depths (top-to-bottom), not side-by-side.
        """
        fsm = self._make_fsm(
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="check",
                    on_success="done",
                    on_failure="fix",
                    on_partial="evaluate",
                ),
                "fix": StateConfig(action="fix", next="check_commit"),
                "check_commit": StateConfig(
                    action="check-c",
                    on_success="commit",
                    on_failure="evaluate",
                ),
                "commit": StateConfig(action="commit", next="evaluate"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")

        # All 4 non-terminal states must appear in a box line
        for state in ("evaluate", "fix", "check_commit", "commit"):
            box_lines = [ln for ln in lines if state in ln and "\u2502" in ln]
            assert box_lines, f"{state!r} should be rendered in a box with \u2502 borders"

        # In layered layout, off-path states are at different vertical depths (top-to-bottom)
        fix_row = next(i for i, ln in enumerate(lines) if "fix" in ln and "\u2502" in ln)
        cc_row = next(
            i for i, ln in enumerate(lines) if "check_commit" in ln and "\u2502" in ln
        )
        commit_row = next(
            i
            for i, ln in enumerate(lines)
            if "commit" in ln and "check_commit" not in ln and "\u2502" in ln
        )
        assert fix_row < cc_row < commit_row, (
            f"Off-path states should appear top-to-bottom; "
            f"fix={fix_row}, check_commit={cc_row}, commit={commit_row}"
        )

    def test_issue_refinement_git_topology(self) -> None:
        """Regression for BUG-664: 6-state issue-refinement topology renders correctly.

        Tests that:
        - All 6 states appear in boxes
        - Back-edges from check_commit and commit route to evaluate (correct target)
        - Both ↺ partial and ↺ error self-loops appear for evaluate
        - States are laid out vertically in correct order
        """
        fsm = self._make_fsm(
            initial="evaluate",
            states={
                "evaluate": StateConfig(
                    action="evaluate",
                    on_success="evaluate",
                    on_failure="format_issues",
                    on_partial="evaluate",
                    on_error="evaluate",
                ),
                "format_issues": StateConfig(action="format", next="score_issues"),
                "score_issues": StateConfig(action="score", next="refine_issues"),
                "refine_issues": StateConfig(action="refine", next="check_commit"),
                "check_commit": StateConfig(
                    action="check",
                    on_success="commit",
                    on_failure="evaluate",
                    on_error="evaluate",
                ),
                "commit": StateConfig(action="commit", next="evaluate"),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")

        # 1. All 6 states appear in boxes (line with state name AND │ border)
        for state in (
            "evaluate",
            "format_issues",
            "score_issues",
            "refine_issues",
            "check_commit",
            "commit",
        ):
            box_lines = [ln for ln in lines if state in ln and "\u2502" in ln]
            assert box_lines, f"{state!r} should be rendered in a box with \u2502 borders"

        # 2. ▶ appears at box connection point (horizontal connector enters box from left)
        right_arrow_count = result.count("\u25b6")
        assert right_arrow_count >= 1, (
            f"Expected at least 1 \u25b6 (▶) at evaluate box connection, "
            f"found {right_arrow_count}. Full diagram:\n{result}"
        )

        # 2b. Corner characters (┌/┬/└) at pipe-to-horizontal turn points
        assert "\u250c" in result or "\u252c" in result, (
            f"Expected \u250c (┌) or \u252c (┬) corner at top of back-edge pipe. "
            f"Full diagram:\n{result}"
        )
        assert "\u2514" in result, (
            f"Expected \u2514 (└) corner where pipe ends. "
            f"Full diagram:\n{result}"
        )

        # 3. Combined label "fail/error" or "error/fail" should appear for the merged edge
        assert "fail/" in result or "/fail" in result, (
            f"Expected combined fail/error label for check_commit\u2192evaluate, "
            f"not separate pipes. Full diagram:\n{result}"
        )

        # 4. Both ↺ partial and ↺ error self-loops appear for evaluate
        assert "\u21ba" in result, "Expected \u21ba self-loop marker for evaluate"
        assert "partial" in result, "Expected 'partial' self-loop label"

        # 5. No garbled labels — no line should have a letter immediately after │
        import re

        for ln in lines:
            garbled = re.findall(r"\u2502[a-zA-Z]", ln)
            assert not garbled, (
                f"Garbled label detected (letter touching pipe): {garbled!r} in line: {ln!r}"
            )

        # 6. Box borders should not be overwritten — └ and ┘ should appear in boxes
        border_lines = [ln for ln in lines if "\u2514" in ln or "\u2518" in ln]
        assert border_lines, "Box bottom borders (└/┘) should be present"

        # 7. States appear in top-to-bottom vertical order
        eval_row = next(i for i, ln in enumerate(lines) if "evaluate" in ln and "\u2502" in ln)
        fmt_row = next(
            i for i, ln in enumerate(lines) if "format_issues" in ln and "\u2502" in ln
        )
        score_row = next(
            i for i, ln in enumerate(lines) if "score_issues" in ln and "\u2502" in ln
        )
        assert eval_row < fmt_row < score_row, "States should appear top-to-bottom"

    def test_main_path_cycle_renders_back_edge(self) -> None:
        """Main-path cycle edge (last → initial) renders as left-margin back-edge.

        Regression test: when the main path forms a cycle (e.g. commit → start
        via 'next'), the backward edge must render as a left-margin back-edge
        arrow, not be silently dropped.
        """
        fsm = self._make_fsm(
            initial="start",
            states={
                "start": StateConfig(action="count", next="work"),
                "work": StateConfig(action="do", on_success="decide"),
                "decide": StateConfig(
                    action="eval", on_success="commit", on_failure="done"
                ),
                "commit": StateConfig(action="save", next="start"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)

        # Back-edge from commit → start must have left-margin corner characters
        assert "┌" in result or "┬" in result, (
            f"Main-path cycle should render as back-edge with top corner.\n{result}"
        )
        # The ▶ connector entering the target box
        assert "▶" in result, (
            f"Main-path cycle back-edge should have ▶ connector.\n{result}"
        )
        # All states should be visible
        for state in ("start", "work", "decide", "commit", "done"):
            box_lines = [ln for ln in result.split("\n") if state in ln and "│" in ln]
            assert box_lines, f"{state!r} should be rendered in a box"

    def test_branch_to_terminal_skip_layer_renders_edge(self) -> None:
        """Branch edge to terminal state spanning multiple layers renders as right-margin edge.

        Regression test (BUG-678): when a branch edge (on_failure/on_error)
        targets a terminal state that is 2+ layers away, the forward skip-layer
        edge must render as a right-margin arrow, not be silently dropped.

        Topology: start → work → evaluate → commit → cleanup → done
        with evaluate.on_failure → done.  Longest-path assignment places
        done at layer 5 (via cleanup), making evaluate(2) → done(5) a
        forward skip-layer edge spanning 3 layers.
        """
        fsm = self._make_fsm(
            initial="start",
            states={
                "start": StateConfig(action="scan", on_success="work"),
                "work": StateConfig(action="do", on_success="evaluate"),
                "evaluate": StateConfig(
                    action="check", on_success="commit", on_failure="done"
                ),
                "commit": StateConfig(action="save", on_success="cleanup"),
                "cleanup": StateConfig(action="tidy", on_success="done"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)

        # Right-margin corner characters for forward skip-layer edge
        assert "┐" in result or "┘" in result or "┤" in result, (
            f"Forward skip-layer edge should render right-margin corners.\n{result}"
        )
        # The ◀ connector entering the target box from the right
        assert "◀" in result, (
            f"Forward skip-layer edge should have ◀ connector.\n{result}"
        )
        # All states should be visible
        for state in ("start", "work", "evaluate", "commit", "cleanup", "done"):
            box_lines = [ln for ln in result.split("\n") if state in ln and "│" in ln]
            assert box_lines, f"{state!r} should be rendered in a box"

    def test_inter_layer_offset_edge_draws_horizontal_connector(self) -> None:
        """Offset inter-layer edge draws ─ connector from source box to pipe.

        When a state branches to two states on the next layer, the off-center
        destination gets a horizontal connector (───┐ or ┌───) linking the
        source box boundary to the vertical pipe.
        """
        # a → b (success) and a → c (failure), both on next layer.
        # b and c share a layer; one pipe aligns with a, the other is offset.
        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step", on_success="b", on_failure="c"),
                "b": StateConfig(terminal=True),
                "c": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)

        # Horizontal connector should appear for the offset edge
        assert "\u2500" in result, (
            f"Offset inter-layer edge should have ─ horizontal connector.\n{result}"
        )
        # Corner piece where horizontal meets vertical
        assert "\u2510" in result or "\u250c" in result, (
            f"Offset inter-layer edge should have ┐ or ┌ corner.\n{result}"
        )

    def test_skip_layer_forward_edges_sharing_node_connected(self) -> None:
        """Two skip-layer forward edges sharing a node render connected horizontals.

        Regression test (BUG-686): when two forward skip-layer edges share
        a common node, the horizontal connector for the outer pipe must cross
        the inner pipe with a junction character (┴ or ┼), not stop short.

        Topology (main path): a → b → c → d → e → f → g → h
          Edge 1: b --fail--> e  (skips c, d — forward skip-layer)
          Edge 2: e --fail--> h  (skips f, g — forward skip-layer)
        Both are right-margin pipes sharing node e. At e's row, Edge 2's
        horizontal must cross Edge 1's vertical pipe with a junction char.
        Extra layers (f, g) between e and h prevent layer merge.
        """
        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step_a", on_success="b"),
                "b": StateConfig(action="step_b", on_success="c", on_failure="e"),
                "c": StateConfig(action="step_c", on_success="d"),
                "d": StateConfig(action="step_d", on_success="e"),
                "e": StateConfig(action="step_e", on_success="f", on_failure="h"),
                "f": StateConfig(action="step_f", on_success="g"),
                "g": StateConfig(action="step_g", on_success="h"),
                "h": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)

        # Both ◀ arrows should render (one per skip-layer target)
        arrow_count = result.count("\u25c0")
        assert arrow_count >= 2, (
            f"Expected at least 2 ◀ arrows for two skip-layer edges, "
            f"found {arrow_count}.\n{result}"
        )

        # No disconnected gap pattern: ┘ followed by spaces then ┐
        # (this is the symptom of the bug — inner pipe corner stops outer horizontal)
        import re

        for ln in result.split("\n"):
            gap_match = re.search(r"\u2518\s+\u2510", ln)
            assert not gap_match, (
                f"Disconnected gap between inner and outer pipe detected: {ln!r}\n{result}"
            )

        # Junction characters (┴ or ┼) should appear where outer pipe crosses inner
        assert "\u2534" in result or "\u253c" in result, (
            f"Expected ┴ or ┼ crossing junction where outer pipe crosses inner.\n{result}"
        )

    def test_highlighted_state_uses_configured_color(self) -> None:
        """highlight_state box uses the configured ANSI color; other boxes do not."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step a", on_success="b"),
                "b": StateConfig(terminal=True),
            },
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm, highlight_state="a", highlight_color="36")

        # Highlighted state box has the color code
        assert "\033[36m" in result
        # Bold variant used for state name
        assert "\033[36;1m" in result

    def test_highlighted_state_default_green(self) -> None:
        """highlight_state defaults to color code '32' (green)."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm, highlight_state="start")

        assert "\033[32m" in result

    def test_no_highlight_state_unchanged(self) -> None:
        """Without highlight_state, output contains no ANSI codes from box drawing."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step", on_success="b"),
                "b": StateConfig(terminal=True),
            },
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm)

        # No ANSI codes in box chars (edge labels may add color but not box borders)
        # State names should appear plain
        assert "a" in result
        assert "b" in result
        # No color from box borders (highlight not active)
        assert "\033[32m\u250c" not in result  # no colored top-left corner

    def test_unknown_highlight_state_no_crash(self) -> None:
        """Providing a non-existent state as highlight_state does not crash."""
        fsm = self._make_fsm(
            initial="a",
            states={"a": StateConfig(terminal=True)},
        )
        result = _render_fsm_diagram(fsm, highlight_state="nonexistent", highlight_color="32")
        assert "a" in result


class TestAdaptiveLayoutTopologies:
    """Tests for topology-specific adaptive layout rendering."""

    def _make_fsm(
        self,
        name: str = "test",
        initial: str = "start",
        states: dict[str, StateConfig] | None = None,
    ) -> FSMLoop:
        return FSMLoop(name=name, initial=initial, states=states or {}, max_iterations=50)

    def test_two_state_linear_vertical(self) -> None:
        """2-state linear FSM renders vertically."""
        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step", on_success="b"),
                "b": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")
        a_row = next(i for i, ln in enumerate(lines) if "a" in ln and "\u2502" in ln)
        b_row = next(i for i, ln in enumerate(lines) if "b" in ln and "\u2502" in ln)
        assert a_row < b_row, "2-state linear should render top-to-bottom"
        assert "\u25bc" in result, "Expected \u25bc vertical arrow between states"

    def test_four_state_linear_vertical(self) -> None:
        """4-state linear FSM renders vertically in correct order."""
        fsm = self._make_fsm(
            initial="s1",
            states={
                "s1": StateConfig(action="a", on_success="s2"),
                "s2": StateConfig(action="b", on_success="s3"),
                "s3": StateConfig(action="c", on_success="s4"),
                "s4": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")
        rows = {}
        for state in ("s1", "s2", "s3", "s4"):
            rows[state] = next(
                i for i, ln in enumerate(lines) if state in ln and "\u2502" in ln
            )
        assert rows["s1"] < rows["s2"] < rows["s3"] < rows["s4"]

    def test_diamond_pattern(self) -> None:
        """Diamond pattern (fan-out + fan-in) renders with branches and convergence."""
        fsm = self._make_fsm(
            initial="start",
            states={
                "start": StateConfig(action="check", on_success="left", on_failure="right"),
                "left": StateConfig(action="path-a", on_success="end"),
                "right": StateConfig(action="path-b", on_success="end"),
                "end": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")
        # All states appear in boxes
        for state in ("start", "left", "right", "end"):
            box_lines = [ln for ln in lines if state in ln and "\u2502" in ln]
            assert box_lines, f"{state!r} should be in a box"
        # Both "success" and "fail" labels appear
        assert "success" in result
        assert "fail" in result

    def test_fan_in_three_paths(self) -> None:
        """Fan-in with 3+ paths converging on a single state."""
        fsm = self._make_fsm(
            initial="dispatch",
            states={
                "dispatch": StateConfig(
                    action="route",
                    route=RouteConfig(routes={"a": "path_a", "b": "path_b", "c": "path_c"}),
                ),
                "path_a": StateConfig(action="a", on_success="merge"),
                "path_b": StateConfig(action="b", on_success="merge"),
                "path_c": StateConfig(action="c", on_success="merge"),
                "merge": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        # All states in boxes
        for state in ("dispatch", "path_a", "path_b", "path_c", "merge"):
            assert state in result, f"{state!r} should appear in diagram"
        # Route labels present
        for lbl in ("a", "b", "c"):
            assert lbl in result

    def test_terminal_width_no_overflow(self) -> None:
        """Diagram lines do not exceed terminal width."""
        from unittest.mock import patch as _patch

        from little_loops.cli import output as output_mod

        # Simulate a narrow terminal
        with _patch.object(output_mod, "terminal_width", return_value=80):
            fsm = self._make_fsm(
                initial="evaluate",
                states={
                    "evaluate": StateConfig(
                        action="check",
                        on_success="done",
                        on_failure="fix",
                        on_partial="evaluate",
                    ),
                    "fix": StateConfig(action="fix", next="evaluate"),
                    "done": StateConfig(terminal=True),
                },
            )
            result = _render_fsm_diagram(fsm)
            for i, line in enumerate(result.split("\n")):
                # Strip ANSI codes for width check
                import re

                clean = re.sub(r"\033\[[0-9;]*m", "", line)
                assert len(clean) <= 80, (
                    f"Line {i} exceeds terminal width (80): {len(clean)} chars: {line!r}"
                )

    def test_multiple_self_loops_all_shown(self) -> None:
        """State with multiple self-loops shows all labels."""
        fsm = self._make_fsm(
            initial="monitor",
            states={
                "monitor": StateConfig(
                    action="check",
                    on_success="done",
                    on_partial="monitor",
                    on_error="monitor",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        assert "\u21ba" in result
        assert "partial" in result
        assert "error" in result


class TestDisplayProgressEvents:
    """Tests for display_progress event formatting in run_foreground."""

    def _make_args(
        self, quiet: bool = False, verbose: bool = False, show_diagrams: bool = False
    ) -> argparse.Namespace:
        return argparse.Namespace(quiet=quiet, verbose=verbose, show_diagrams=show_diagrams)

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

    def test_verbose_shell_output_printed_once(self, capsys: pytest.CaptureFixture[str]) -> None:
        """In verbose mode, shell action output appears exactly once (not via both action_output and output_preview)."""
        events = [
            {"event": "action_output", "line": "  fmt  | verify"},
            {"event": "action_output", "line": "   \u2713   |   \u2713  "},
            {
                "event": "action_complete",
                "exit_code": 0,
                "duration_ms": 100,
                "output_preview": "  fmt  | verify\n   \u2713   |   \u2713  ",
                "is_prompt": False,
            },
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
        out = capsys.readouterr().out
        assert out.count("fmt") == 1

    def test_nonverbose_shell_output_shows_preview(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """In non-verbose mode, shell output_preview is shown (action_output events are suppressed)."""
        events = [
            {"event": "action_output", "line": "streamed line"},
            {
                "event": "action_complete",
                "exit_code": 0,
                "duration_ms": 100,
                "output_preview": "preview line",
                "is_prompt": False,
            },
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(verbose=False))
        out = capsys.readouterr().out
        assert "preview line" in out
        assert "streamed line" not in out

    def test_show_diagrams_state_enter_prints_diagram(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams flag causes state_enter events to print the FSM diagram."""
        from unittest.mock import patch

        from little_loops.cli.loop import info as info_mod

        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch.object(
            info_mod, "_render_fsm_diagram", wraps=info_mod._render_fsm_diagram
        ) as mock_render:
            run_foreground(executor, self._make_fsm(), self._make_args(show_diagrams=True))
            mock_render.assert_called_once_with(
                self._make_fsm(), highlight_state="start", highlight_color="32"
            )
        out = capsys.readouterr().out
        # Diagram contains box drawing characters
        assert "\u250c" in out

    def test_verbose_without_show_diagrams_no_diagram(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--verbose alone does not print the FSM diagram."""
        from unittest.mock import patch

        from little_loops.cli.loop import info as info_mod

        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch.object(info_mod, "_render_fsm_diagram") as mock_render:
            run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
            mock_render.assert_not_called()

    def test_no_flags_state_enter_no_diagram(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Without --show-diagrams, state_enter events do not print the FSM diagram."""
        from unittest.mock import patch

        from little_loops.cli.loop import info as info_mod

        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch.object(info_mod, "_render_fsm_diagram") as mock_render:
            run_foreground(executor, self._make_fsm(), self._make_args(verbose=False))
            mock_render.assert_not_called()

    def test_verbose_and_show_diagrams_prints_diagram(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--verbose and --show-diagrams combined prints diagram and verbose output."""
        from unittest.mock import patch

        from little_loops.cli.loop import info as info_mod

        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
            {"event": "action_output", "line": "verbose output line"},
        ]
        executor = MockExecutor(events)
        with patch.object(
            info_mod, "_render_fsm_diagram", wraps=info_mod._render_fsm_diagram
        ) as mock_render:
            run_foreground(
                executor, self._make_fsm(), self._make_args(verbose=True, show_diagrams=True)
            )
            mock_render.assert_called_once_with(
                self._make_fsm(), highlight_state="start", highlight_color="32"
            )
        out = capsys.readouterr().out
        assert "\u250c" in out
        assert "verbose output line" in out


class TestRunForegroundExitCodes:
    """Tests for run_foreground exit code mapping (BUG-605)."""

    def _make_args(self) -> argparse.Namespace:
        return argparse.Namespace(quiet=False, verbose=False, show_diagrams=False)

    def _make_fsm(self) -> FSMLoop:
        return make_test_fsm()

    def _run_with_terminated_by(self, terminated_by: str) -> int:
        """Run run_foreground with a mock executor returning given terminated_by."""

        class _Executor:
            def __init__(self, tb: str) -> None:
                self._tb = tb
                self._on_event: Any = None

            def run(self) -> ExecutionResult:
                return ExecutionResult(
                    final_state="done",
                    iterations=1,
                    terminated_by=self._tb,
                    duration_ms=100,
                    captured={},
                )

        with patch("builtins.print"):
            return run_foreground(_Executor(terminated_by), self._make_fsm(), self._make_args())

    @pytest.mark.parametrize("terminated_by", ["terminal", "signal", "handoff"])
    def test_zero_exit_code_for_graceful_termination(self, terminated_by: str) -> None:
        """terminal, signal, and handoff all return exit code 0."""
        assert self._run_with_terminated_by(terminated_by) == 0

    @pytest.mark.parametrize("terminated_by", ["max_iterations", "timeout"])
    def test_nonzero_exit_code_for_limit_termination(self, terminated_by: str) -> None:
        """max_iterations and timeout return exit code 1."""
        assert self._run_with_terminated_by(terminated_by) == 1

    def test_unknown_terminated_by_returns_1(self) -> None:
        """Unknown terminated_by values fall back to exit code 1."""
        assert self._run_with_terminated_by("unexpected_value") == 1

    def test_exit_codes_dict_matches_expected_mapping(self) -> None:
        """EXIT_CODES dict has the expected keys and values."""
        assert EXIT_CODES["terminal"] == 0
        assert EXIT_CODES["signal"] == 0
        assert EXIT_CODES["handoff"] == 0
        assert EXIT_CODES["max_iterations"] == 1
        assert EXIT_CODES["timeout"] == 1

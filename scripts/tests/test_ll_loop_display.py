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
from little_loops.cli.loop.layout import (
    _ACTION_TYPE_BADGES,
    _ROUTE_BADGE,
    _SUB_LOOP_BADGE,
    _collect_edges,
    _get_state_badge,
)
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

    def __init__(self, events: list[dict[str, Any]], loops_dir: Path = Path(".")) -> None:
        self._events = events
        self._on_event: Any = None
        self.loops_dir = loops_dir

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
    on_yes: str | None = None,
    on_no: str | None = None,
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
        on_yes=on_yes,
        on_no=on_no,
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
            "start": make_test_state(action="echo start", on_yes="done", on_no="done"),
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
        state = make_test_state(action="echo hello", on_yes="done")
        result = state.to_dict()
        assert result == {"action": "echo hello", "on_yes": "done"}

    def test_terminal_state(self) -> None:
        """Convert terminal state to dict."""
        state = make_test_state(terminal=True)
        result = state.to_dict()
        assert result == {"terminal": True}

    def test_state_with_failure_routing(self) -> None:
        """Convert state with on_failure."""
        state = make_test_state(
            action="pytest",
            on_yes="done",
            on_no="fix",
        )
        result = state.to_dict()
        assert result == {
            "action": "pytest",
            "on_yes": "done",
            "on_no": "fix",
        }

    def test_state_with_on_error(self) -> None:
        """Convert state with on_error."""
        state = make_test_state(
            action="risky_command",
            on_yes="done",
            on_error="handle_error",
        )
        result = state.to_dict()
        assert result == {
            "action": "risky_command",
            "on_yes": "done",
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
            on_yes="done",
            on_no="fix",
        )
        result = state.to_dict()
        assert result == {
            "action": "pytest",
            "evaluate": {"type": "exit_code"},
            "on_yes": "done",
            "on_no": "fix",
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
            on_yes="done",
            on_no="fix",
        )
        result = state.to_dict()
        assert result == {
            "action": "wc -l errors.log",
            "evaluate": {
                "type": "output_numeric",
                "operator": "le",
                "target": 5,
            },
            "on_yes": "done",
            "on_no": "fix",
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
            on_yes="done",
            on_no="fix",
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
            on_yes="fix",
            on_no="done",
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
            on_yes="done",
            on_no="retry",
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
                routes={"yes": "done", "no": "retry", "blocked": "escalate"},
                default="error_state",
            ),
        )
        result = state.to_dict()
        assert result["route"] == {
            "yes": "done",
            "no": "retry",
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
            on_yes="check",
        )
        result = state.to_dict()
        assert result["capture"] == "error_count"

    def test_state_with_timeout(self) -> None:
        """Convert state with timeout."""
        state = make_test_state(
            action="slow_command",
            timeout=300,
            on_yes="done",
        )
        result = state.to_dict()
        assert result["timeout"] == 300

    def test_state_with_on_maintain(self) -> None:
        """Convert state with on_maintain."""
        state = make_test_state(
            action="monitor",
            on_maintain="monitor",
            on_yes="done",
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
            on_yes="done",
            on_no="fix",
            on_error="error_handler",
            capture="result",
            timeout=60,
        )
        result = state.to_dict()
        assert "action" in result
        assert "evaluate" in result
        assert "on_yes" in result
        assert "on_no" in result
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
    on_yes: done
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
    on_yes: done
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
        yaml_content += "    action_type: prompt\n    on_yes: done\n  done:\n    terminal: true\n"
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
    on_yes: done
    on_no: fix
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
            ("yes", "\u2713"),
            ("target", "\u2713"),
            ("progress", "\u2713"),
            ("no", "\u2717"),
            ("stall", "\u2717"),
            ("error", "\u2717"),
            ("blocked", "\u2717"),
        ],
    )
    def test_verdict_symbols(self, verdict: str, expected_symbol: str) -> None:
        """Correct symbols for success/failure verdicts."""
        success_verdicts = ("yes", "target", "progress")
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
                "a": StateConfig(action="step a", on_yes="b"),
                "b": StateConfig(action="step b", on_yes="c"),
                "c": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        # All three states appear in boxes
        assert "a" in result
        assert "b" in result
        assert "c" in result
        # Transition labels are shown
        assert "yes" in result
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
                "test": StateConfig(action="pytest", on_yes="done", on_no="fix"),
                "fix": StateConfig(action="fix.sh", on_yes="done"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        # Main flow states in boxes
        assert "test" in result
        assert "done" in result
        assert "yes" in result
        # Branch edges shown
        assert "no" in result
        assert "◄" in result or "▶" in result  # some arrowhead present
        # Off-path state rendered as box (not just text)
        lines = result.split("\n")
        fix_box_lines = [line for line in lines if "fix" in line and "\u2502" in line]
        assert fix_box_lines, "fix should be rendered inside a box with │ borders"

    def test_cyclic_fsm_shows_back_edges_section(self) -> None:
        """Back-edge (retry loop) rendered with 2D vertical connectors."""
        fsm = self._make_fsm(
            initial="evaluate",
            states={
                "evaluate": StateConfig(action="check", on_yes="done", on_no="fix"),
                "fix": StateConfig(action="fix.sh", on_yes="evaluate"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        # fix -> evaluate back-edge: both states and label appear
        assert "evaluate" in result
        assert "fix" in result
        assert "no" in result
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
                    on_yes="done",
                    on_no="monitor",
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
                "retry": StateConfig(action="retry", on_yes="done"),
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
                "first": StateConfig(action="a", on_yes="second"),
                "second": StateConfig(action="b", on_yes="third"),
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
                    on_yes="done",
                    on_no="fix",
                    on_error="fix",
                ),
                "fix": StateConfig(action="fix.sh", next="evaluate"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        # All edges and states appear in diagram
        assert "evaluate" in result
        assert "fix" in result
        assert "done" in result
        assert "no" in result or "no/error" in result
        assert "next" in result
        assert "yes" in result

    def test_multiple_off_path_states_same_depth(self) -> None:
        """Two off-path states appear in boxes with back-edges to main path."""
        # Mirrors fix-quality-and-tests: two check→fix pairs with fix-tests→check-quality cross-edge
        fsm = self._make_fsm(
            initial="check-quality",
            states={
                "check-quality": StateConfig(
                    action="lint",
                    on_yes="check-tests",
                    on_no="fix-quality",
                ),
                "fix-quality": StateConfig(action="fix lint", next="check-quality"),
                "check-tests": StateConfig(
                    action="pytest",
                    on_yes="done",
                    on_no="fix-tests",
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
                    on_yes="done",
                    on_no="fix",
                    on_partial="evaluate",
                ),
                "fix": StateConfig(action="fix", next="check_commit"),
                "check_commit": StateConfig(
                    action="check-c",
                    on_yes="commit",
                    on_no="evaluate",
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
        cc_row = next(i for i, ln in enumerate(lines) if "check_commit" in ln and "\u2502" in ln)
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
                    on_yes="evaluate",
                    on_no="format_issues",
                    on_partial="evaluate",
                    on_error="evaluate",
                ),
                "format_issues": StateConfig(action="format", next="score_issues"),
                "score_issues": StateConfig(action="score", next="refine_issues"),
                "refine_issues": StateConfig(action="refine", next="check_commit"),
                "check_commit": StateConfig(
                    action="check",
                    on_yes="commit",
                    on_no="evaluate",
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
            f"Expected \u2514 (└) corner where pipe ends. Full diagram:\n{result}"
        )

        # 3. Combined label "no/error" or "error/no" should appear for the merged edge
        assert "no/" in result or "/no" in result, (
            f"Expected combined no/error label for check_commit\u2192evaluate, "
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
        fmt_row = next(i for i, ln in enumerate(lines) if "format_issues" in ln and "\u2502" in ln)
        score_row = next(i for i, ln in enumerate(lines) if "score_issues" in ln and "\u2502" in ln)
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
                "work": StateConfig(action="do", on_yes="decide"),
                "decide": StateConfig(action="eval", on_yes="commit", on_no="done"),
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
        assert "▶" in result, f"Main-path cycle back-edge should have ▶ connector.\n{result}"
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
        with evaluate.on_no → done.  Longest-path assignment places
        done at layer 5 (via cleanup), making evaluate(2) → done(5) a
        forward skip-layer edge spanning 3 layers.
        """
        fsm = self._make_fsm(
            initial="start",
            states={
                "start": StateConfig(action="scan", on_yes="work"),
                "work": StateConfig(action="do", on_yes="evaluate"),
                "evaluate": StateConfig(action="check", on_yes="commit", on_no="done"),
                "commit": StateConfig(action="save", on_yes="cleanup"),
                "cleanup": StateConfig(action="tidy", on_yes="done"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)

        # Right-margin corner characters for forward skip-layer edge
        assert "┐" in result or "┘" in result or "┤" in result, (
            f"Forward skip-layer edge should render right-margin corners.\n{result}"
        )
        # The ◀ connector entering the target box from the right
        assert "◀" in result, f"Forward skip-layer edge should have ◀ connector.\n{result}"
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
                "a": StateConfig(action="step", on_yes="b", on_no="c"),
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

    def test_cross_column_forward_edge_connects_to_source_center(self) -> None:
        """Cross-column forward edge renders corner at source box center.

        When a source box is offset from the destination (e.g. source is in a
        multi-box layer and destination is centered in a single-box layer),
        the horizontal connector must extend to the source box center with
        a └ or ┘ corner character, not stop at the source box edge.
        """
        # a branches to b and c on layer 2.
        # c (right side) transitions to d (single box, centered layer 3).
        # The c→d edge is cross-column: d's center is left of c's left edge.
        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step_a", on_yes="b", on_no="c"),
                "b": StateConfig(terminal=True),
                "c": StateConfig(action="step_c", on_yes="d"),
                "d": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)

        # The connector from d's center to c's center should have └ or ┘
        assert "\u2518" in result or "\u2514" in result, (
            f"Cross-column forward edge should have └ or ┘ corner at source box center.\n{result}"
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
                "a": StateConfig(action="step_a", on_yes="b"),
                "b": StateConfig(action="step_b", on_yes="c", on_no="e"),
                "c": StateConfig(action="step_c", on_yes="d"),
                "d": StateConfig(action="step_d", on_yes="e"),
                "e": StateConfig(action="step_e", on_yes="f", on_no="h"),
                "f": StateConfig(action="step_f", on_yes="g"),
                "g": StateConfig(action="step_g", on_yes="h"),
                "h": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)

        # Both ◀ arrows should render (one per skip-layer target)
        arrow_count = result.count("\u25c0")
        assert arrow_count >= 2, (
            f"Expected at least 2 ◀ arrows for two skip-layer edges, found {arrow_count}.\n{result}"
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

    def test_same_layer_edge_does_not_occlude_intermediate_box(self) -> None:
        """Same-layer transition does not draw connector through intermediate state boxes.

        Regression test (BUG-730): when states A, B, C share a layer and there
        is a same-layer transition from A to C, the horizontal connector must
        not overwrite the borders or interior of B.

        Topology: start → a → [b, c, d] (same layer), a --next--> d (same layer,
        skips over b and c).  All three share a row; the A→D connector must not
        write through B or C's cells.
        """
        fsm = self._make_fsm(
            initial="start",
            states={
                "start": StateConfig(
                    action="init",
                    on_yes="b",
                    on_no="c",
                    on_error="d",
                ),
                "b": StateConfig(action="step_b", on_yes="end"),
                "c": StateConfig(action="step_c", on_yes="end", next="d"),
                "d": StateConfig(action="step_d", on_yes="end"),
                "end": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)

        # All states must appear in their own boxes (name visible inside │...│)
        for state in ("start", "b", "c", "d", "end"):
            box_lines = [ln for ln in result.split("\n") if state in ln and "│" in ln]
            assert box_lines, f"{state!r} should be rendered in a box.\n{result}"

        # The intermediate states (b, c) must have their names readable on their
        # name row — not replaced by ─ connector characters from a same-layer edge.
        for state in ("b", "c", "d"):
            # A name-row line looks like: │ state_name ... │
            # If occluded, the line containing the state name would be absent or
            # the state name would be replaced by ─ characters.
            name_lines = [ln for ln in result.split("\n") if state in ln and "│" in ln]
            assert name_lines, (
                f"State {state!r} name occluded by connector: not visible in any box line.\n{result}"
            )

    def test_same_layer_right_to_left_edge_has_correct_arrowhead(self) -> None:
        """Right-to-left same-layer edge renders ◀ at destination, not ▶.

        Regression test (BUG-1498): when two states share a layer and a
        transition runs right-to-left (dst is left of src), the rendered
        connector must use ◀ pointing at the destination and must not contain
        a spurious ▶ on that row.

        Topology: start → a → b (different layers); a ←yes─ b (same layer,
        right-to-left).  The b→a edge should render as  a ◀──yes─ b.
        """
        # Topology: start branches to both "alpha" and "beta" (same layer).
        # beta.on_yes → alpha is a right-to-left same-layer edge because
        # "alpha" sorts before "beta" in layout order (left of "beta").
        fsm = self._make_fsm(
            initial="start",
            states={
                "start": StateConfig(action="init", on_yes="alpha", on_no="beta"),
                "alpha": StateConfig(action="step_a", on_yes="done"),
                "beta": StateConfig(action="step_b", on_yes="alpha"),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)

        # Strip ANSI codes for plain-text assertions
        import re

        plain = re.sub(r"\x1b\[[0-9;]*m", "", result)

        # The right-to-left same-layer edge (beta → alpha) must use ◀
        assert "◄" in plain, f"Right-to-left same-layer edge should have ◀ arrowhead.\n{plain}"
        # No ▶ should appear on the row that contains both state names
        rows_with_both = [
            ln for ln in plain.split("\n") if "alpha" in ln and "beta" in ln and "│" in ln
        ]
        for row in rows_with_both:
            assert "▶" not in row, (
                f"Spurious ▶ found on right-to-left same-layer edge row.\n{row}\nFull diagram:\n{plain}"
            )

    def test_highlighted_state_uses_configured_color(self) -> None:
        """highlight_state box uses the configured ANSI color; other boxes do not."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step a", on_yes="b"),
                "b": StateConfig(terminal=True),
            },
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm, highlight_state="a", highlight_color="36")

        # Highlighted state box borders carry both fg and bg fill (no gap)
        assert "\033[36;46m" in result
        # State name uses bright-white fg + bg color + bold
        assert "\033[97;46;1m" in result
        # Interior cells filled with bg color
        assert "\033[46m " in result

    def test_highlighted_state_default_green(self) -> None:
        """highlight_state defaults to color code '32' (green)."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm, highlight_state="start")

        assert "\033[32;42m" in result
        assert "\033[42m " in result

    def test_no_highlight_state_unchanged(self) -> None:
        """Without highlight_state, output contains no ANSI codes from box drawing."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step", on_yes="b"),
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

    def test_edge_label_custom_color_applied(self) -> None:
        """Custom edge_label_colors overrides the default ANSI code for known labels."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step a", on_yes="b"),
                "b": StateConfig(terminal=True),
            },
        )
        custom_colors = {
            "yes": "99",
            "no": "38;5;208",
            "error": "31",
            "partial": "33",
            "next": "2",
            "_": "2",
            "blocked": "31",
            "retry_exhausted": "38;5;208",
        }
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm, edge_label_colors=custom_colors)

        # Custom ANSI code for "yes" should appear
        assert "\033[99m" in result

    def test_edge_label_custom_color_overrides_default(self) -> None:
        """When edge_label_colors overrides 'yes', the default green code is not used for it."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step a", on_yes="b"),
                "b": StateConfig(terminal=True),
            },
        )
        # Override "yes" with a unique color code unlikely to appear from any other source
        custom_colors = {
            "yes": "55",
            "no": "38;5;208",
            "error": "31",
            "partial": "33",
            "next": "2",
            "_": "2",
            "blocked": "31",
            "retry_exhausted": "38;5;208",
        }
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm, edge_label_colors=custom_colors)

        assert "\033[55m" in result
        # Default green "32" should not appear as the edge label color for "yes"
        assert "\033[32myes" not in result

    def test_non_highlighted_state_name_bold(self) -> None:
        """Non-highlighted state names are rendered in bold for visual hierarchy."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action="step a", on_yes="b"),
                "b": StateConfig(terminal=True),
            },
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm)

        # State names should be bold (ANSI SGR 1); no highlight_state set so both boxes are non-highlighted
        assert "\033[1m" in result, "Non-highlighted state names should use bold (ANSI code 1)"

    def test_back_edge_labels_no_collision_on_shared_midpoint(self) -> None:
        """Two back-edges with the same midpoint row must land on distinct lines.

        With 3-row boxes and 3-row inter-layer arrow gaps, the name rows are
        1, 7, 13, 19, 25 for a 5-state linear chain.  The b→a back-edge has
        midpoint (7+13)//2=10 and the c→init back-edge has midpoint (1+19)//2=10;
        without the fix both labels write to the same grid row and clobber each
        other (regression: BUG-1499).
        """
        fsm = self._make_fsm(
            initial="init",
            states={
                "init": StateConfig(on_yes="a"),
                "a": StateConfig(on_yes="b"),
                "b": StateConfig(on_yes="c", route=RouteConfig(routes={"retry_a": "a"})),
                "c": StateConfig(on_yes="done", route=RouteConfig(routes={"retry_i": "init"})),
                "done": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")
        assert any("retry_a" in ln for ln in lines), "retry_a label not rendered"
        assert any("retry_i" in ln for ln in lines), "retry_i label not rendered"
        assert not any("retry_a" in ln and "retry_i" in ln for ln in lines), (
            "Labels 'retry_a' and 'retry_i' collide on the same line (BUG-1499)"
        )

    def test_skip_forward_label_no_collision_on_shared_source_row(self) -> None:
        """Skip-forward label must not land on the same row as an adjacent-layer label
        when both edges share a source state (regression: BUG-1501).

        S has both S→layer1 (adjacent, label "yes") and S→layer2 (skip-forward,
        label "error").  Without the fix the skip-forward nudge pass has no
        knowledge of the adjacent label row and both land on arrow_start_row.
        """
        fsm = self._make_fsm(
            initial="s",
            states={
                "s": StateConfig(
                    action="step s",
                    on_yes="layer1",
                    route=RouteConfig(routes={"error": "layer2"}),
                ),
                "layer1": StateConfig(on_yes="layer2"),
                "layer2": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")
        assert any("yes" in ln for ln in lines), "yes label not rendered"
        assert any("error" in ln for ln in lines), "error label not rendered"
        assert not any("yes" in ln and "error" in ln for ln in lines), (
            "Labels 'yes' and 'error' collide on the same line (BUG-1501)"
        )


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
                "a": StateConfig(action="step", on_yes="b"),
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
                "s1": StateConfig(action="a", on_yes="s2"),
                "s2": StateConfig(action="b", on_yes="s3"),
                "s3": StateConfig(action="c", on_yes="s4"),
                "s4": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")
        rows = {}
        for state in ("s1", "s2", "s3", "s4"):
            rows[state] = next(i for i, ln in enumerate(lines) if state in ln and "\u2502" in ln)
        assert rows["s1"] < rows["s2"] < rows["s3"] < rows["s4"]

    def test_diamond_pattern(self) -> None:
        """Diamond pattern (fan-out + fan-in) renders with branches and convergence."""
        fsm = self._make_fsm(
            initial="start",
            states={
                "start": StateConfig(action="check", on_yes="left", on_no="right"),
                "left": StateConfig(action="path-a", on_yes="end"),
                "right": StateConfig(action="path-b", on_yes="end"),
                "end": StateConfig(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        lines = result.split("\n")
        # All states appear in boxes
        for state in ("start", "left", "right", "end"):
            box_lines = [ln for ln in lines if state in ln and "\u2502" in ln]
            assert box_lines, f"{state!r} should be in a box"
        # Both "yes" and "no" labels appear
        assert "yes" in result
        assert "no" in result

    def test_fan_in_three_paths(self) -> None:
        """Fan-in with 3+ paths converging on a single state."""
        fsm = self._make_fsm(
            initial="dispatch",
            states={
                "dispatch": StateConfig(
                    action="route",
                    route=RouteConfig(routes={"a": "path_a", "b": "path_b", "c": "path_c"}),
                ),
                "path_a": StateConfig(action="a", on_yes="merge"),
                "path_b": StateConfig(action="b", on_yes="merge"),
                "path_c": StateConfig(action="c", on_yes="merge"),
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
                        on_yes="done",
                        on_no="fix",
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
                    on_yes="done",
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

    def test_fanout_merged_label_truncated_with_ellipsis(self) -> None:
        """Regression for BUG-1500: \u22655 transitions to same dst truncate with \u2026

        A fan-out state whose 5 routes all target the same destination produces
        an ~85-char merged label.  Without the fix the label overflows the content
        area and corrupts adjacent box borders.  With the fix the label is
        truncated at total_content_w with an ellipsis and no border corruption
        occurs.
        """
        import re
        from unittest.mock import patch as _patch

        from little_loops.cli import output as output_mod

        long_merged = (
            "system_problem/max_rounds_exhausted/degrade_give_up/retry_flood/blender_5_incompatible"
        )
        with _patch.object(output_mod, "terminal_width", return_value=80):
            fsm = self._make_fsm(
                initial="investigate_failure",
                states={
                    "investigate_failure": StateConfig(
                        action="investigate",
                        route=RouteConfig(
                            routes={
                                "system_problem": "done",
                                "max_rounds_exhausted": "done",
                                "degrade_give_up": "done",
                                "retry_flood": "done",
                                "blender_5_incompatible": "done",
                            }
                        ),
                    ),
                    "done": StateConfig(terminal=True),
                },
            )
            result = _render_fsm_diagram(fsm)

        lines = result.split("\n")

        # Full merged label must not appear (it overflows content area)
        assert long_merged not in result, (
            "Full untruncated merged label should not appear; expected truncation"
        )

        # Truncation marker must be present
        assert "\u2026" in result, "Long merged forward-edge label should be truncated with \u2026"

        # No letter should immediately follow a box-border pipe (garbled-label guard)
        for ln in lines:
            garbled = re.findall(r"\u2502[a-zA-Z]", ln)
            assert not garbled, (
                f"Garbled label (letter touching pipe \u2502): {garbled!r} in: {ln!r}"
            )


class TestDisplayProgressEvents:
    """Tests for display_progress event formatting in run_foreground."""

    def _make_args(
        self,
        quiet: bool = False,
        verbose: bool = False,
        follow: bool = False,
        show_diagrams: bool | str | None = None,
        clear: bool = False,
        diagram_edge_labels: str | None = None,
        diagram_state_detail: str | None = None,
        diagram_scope: str | None = None,
    ) -> argparse.Namespace:
        # Normalize legacy bool: False → None, True stays as True sentinel for resolve_facets.
        if show_diagrams is False:
            show_diagrams = None
        return argparse.Namespace(
            quiet=quiet,
            verbose=verbose,
            follow=follow,
            show_diagrams=show_diagrams,
            diagram_edge_labels=diagram_edge_labels,
            diagram_state_detail=diagram_state_detail,
            diagram_scope=diagram_scope,
            clear=clear,
        )

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
                "verdict": "yes",
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

    def test_verbose_action_output_not_clipped(self, capsys: pytest.CaptureFixture[str]) -> None:
        """In verbose mode, long action_output lines render in full with no '...' trailer (BUG-1118)."""
        from unittest.mock import patch as _patch

        long_line = "x" * 200
        events = [
            {"event": "action_output", "line": long_line},
        ]
        executor = MockExecutor(events)
        with _patch("little_loops.cli.loop._helpers.terminal_width", return_value=80):
            run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
        out = capsys.readouterr().out
        assert long_line in out
        assert long_line + "..." not in out

    def test_verbose_action_start_prompt_not_clipped(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """BUG-1154: verbose action_start prompt lines render in full with no '...' trailer."""
        from unittest.mock import patch as _patch

        long_line = "p" * 200
        events = [
            {"event": "action_start", "action": long_line, "is_prompt": True},
        ]
        executor = MockExecutor(events)
        with _patch("little_loops.cli.loop._helpers.terminal_width", return_value=80):
            run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
        out = capsys.readouterr().out
        assert long_line in out
        assert long_line + "..." not in out

    def test_verbose_action_start_shell_not_clipped(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """BUG-1154: verbose action_start shell command renders in full with no '...' trailer."""
        from unittest.mock import patch as _patch

        long_cmd = "echo " + "y" * 200
        events = [
            {"event": "action_start", "action": long_cmd, "is_prompt": False},
        ]
        executor = MockExecutor(events)
        with _patch("little_loops.cli.loop._helpers.terminal_width", return_value=80):
            run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
        out = capsys.readouterr().out
        assert long_cmd in out
        assert long_cmd + "..." not in out

    def test_verbose_evaluate_reason_not_clipped(self, capsys: pytest.CaptureFixture[str]) -> None:
        """BUG-1154: verbose evaluate reason renders in full (no 300-char cap)."""
        from unittest.mock import patch as _patch

        long_reason = "r" * 500
        events = [
            {"event": "evaluate", "verdict": "yes", "confidence": 0.9, "reason": long_reason},
        ]
        executor = MockExecutor(events)
        with _patch("little_loops.cli.loop._helpers.terminal_width", return_value=80):
            run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
        out = capsys.readouterr().out
        assert long_reason in out
        assert long_reason[:300] + "..." not in out

    def test_verbose_evaluate_reason_multiline_preserved(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """BUG-1154: verbose evaluate reason with embedded newlines renders as multiple rows."""
        reason = "first line of reason\nsecond line of reason\nthird line of reason"
        events = [
            {"event": "evaluate", "verdict": "yes", "confidence": 0.9, "reason": reason},
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
        out = capsys.readouterr().out
        lines_with_reason = [ln for ln in out.splitlines() if "line of reason" in ln]
        assert len(lines_with_reason) == 3, f"Expected 3 reason rows, got: {lines_with_reason}"

    def test_verbose_evaluate_raw_preview_not_clipped(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """BUG-1154: verbose evaluate raw_preview renders in full (no 200-char cap)."""
        long_preview = "z" * 400
        events = [
            {
                "event": "evaluate",
                "verdict": "error",
                "error": "parse failure",
                "raw_preview": long_preview,
            },
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
        out = capsys.readouterr().out
        assert long_preview in out

    def test_nonverbose_action_start_still_clips(self, capsys: pytest.CaptureFixture[str]) -> None:
        """ENH-1693: non-verbose action_start prompt shows single-line preview, no multi-line display."""
        from unittest.mock import patch as _patch

        long_line = "p" * 200
        many_lines = "\n".join(f"line {i}" for i in range(8))
        events = [
            {"event": "action_start", "action": long_line, "is_prompt": True},
            {"event": "action_start", "action": many_lines, "is_prompt": True},
        ]
        executor = MockExecutor(events)
        with _patch("little_loops.cli.loop._helpers.terminal_width", return_value=80):
            run_foreground(executor, self._make_fsm(), self._make_args(verbose=False))
        out = capsys.readouterr().out
        assert long_line not in out
        assert "..." in out
        assert "3 more lines" not in out

    def test_nonverbose_action_start_prompt_no_line_count_header(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-1693: non-verbose action_start prompt does not emit the (N lines) header."""
        multi_line = "first line\nsecond line\nthird line"
        events = [
            {"event": "action_start", "action": multi_line, "is_prompt": True},
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(verbose=False))
        out = capsys.readouterr().out
        assert "(3 lines)" not in out
        assert "second line" not in out

    def test_nonverbose_action_start_prompt_single_line_preview(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-1693: non-verbose action_start prompt shows ✦ glyph + truncated first line."""
        from unittest.mock import patch as _patch

        first_line = "x" * 80
        events = [
            {"event": "action_start", "action": first_line + "\nsecond line", "is_prompt": True},
        ]
        executor = MockExecutor(events)
        with _patch("little_loops.cli.loop._helpers.terminal_width", return_value=80):
            run_foreground(executor, self._make_fsm(), self._make_args(verbose=False))
        out = capsys.readouterr().out
        assert "✦" in out
        assert "second line" not in out
        assert "..." in out
        assert first_line not in out  # full 80-char line should not appear untruncated

    def test_verbose_action_start_prompt_shows_line_count_header(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """ENH-1693: verbose action_start prompt shows (N lines) header and all content."""
        prompt = "line one\nline two\nline three"
        events = [
            {"event": "action_start", "action": prompt, "is_prompt": True},
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
        out = capsys.readouterr().out
        assert "(3 lines)" in out
        assert "line one" in out
        assert "line two" in out
        assert "line three" in out

    def test_nonverbose_evaluate_reason_still_caps_at_300(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """BUG-1154: non-verbose evaluate reason retains 300-char cap with '...' trailer."""
        long_reason = "r" * 500
        events = [
            {"event": "evaluate", "verdict": "yes", "confidence": 0.9, "reason": long_reason},
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(verbose=False))
        out = capsys.readouterr().out
        assert long_reason not in out
        assert ("r" * 300) + "..." in out

    def test_nonverbose_shell_output_shows_streamed_lines(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """In non-verbose mode, action_output lines are still streamed (no longer suppressed)."""
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
        assert "streamed line" in out
        assert "← response" not in out

    def test_nonverbose_prompt_output_no_preview(self, capsys: pytest.CaptureFixture[str]) -> None:
        """In non-verbose mode, action_complete does not show a post-hoc preview (output already streamed)."""
        events = [
            {
                "event": "action_complete",
                "exit_code": 0,
                "duration_ms": 5000,
                "output_preview": "Line 1\nLine 2\nLine 3",
                "is_prompt": True,
            }
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(verbose=False))
        out = capsys.readouterr().out
        assert "Line 1" not in out
        assert "← response" not in out
        assert "5.0s" in out

    def test_verbose_prompt_output_not_shown_at_action_complete(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """In verbose mode, prompt output streams via action_output; action_complete must not duplicate it."""
        events = [
            {"event": "action_output", "line": "streamed line"},
            {
                "event": "action_complete",
                "exit_code": 0,
                "duration_ms": 5000,
                "output_preview": "streamed line",
                "is_prompt": True,
            },
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(verbose=True))
        out = capsys.readouterr().out
        assert out.count("streamed line") == 1

    def test_quiet_prompt_output_not_shown(self, capsys: pytest.CaptureFixture[str]) -> None:
        """In quiet mode, no output preview is shown for prompt states."""
        events = [
            {
                "event": "action_complete",
                "exit_code": 0,
                "duration_ms": 1000,
                "output_preview": "should not appear",
                "is_prompt": True,
            }
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args(quiet=True))
        out = capsys.readouterr().out
        assert "should not appear" not in out

    def test_show_diagrams_state_enter_prints_diagram(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams flag causes state_enter events to print the FSM diagram."""
        from unittest.mock import patch

        from little_loops.cli.loop import layout as layout_mod

        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch.object(
            layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
        ) as mock_render:
            # bare --show-diagrams \u2192 True sentinel \u2192 summary preset (main scope)
            run_foreground(executor, self._make_fsm(), self._make_args(show_diagrams=True))
            mock_render.assert_called_once_with(
                self._make_fsm(),
                highlight_state="start",
                highlight_color="32",
                edge_label_colors=None,
                badges=None,
                mode="main",
                suppress_labels=False,
                title_only=False,
            )
        out = capsys.readouterr().out
        # Diagram contains box drawing characters
        assert "\u250c" in out

    def test_show_diagrams_clean_forwarded_to_render(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams=clean (formerly mini) forwards suppress_labels+title_only to _render_fsm_diagram."""
        from unittest.mock import patch

        from little_loops.cli.loop import layout as layout_mod

        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch.object(
            layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
        ) as mock_render:
            run_foreground(executor, self._make_fsm(), self._make_args(show_diagrams="clean"))
            mock_render.assert_called_once_with(
                self._make_fsm(),
                highlight_state="start",
                highlight_color="32",
                edge_label_colors=None,
                badges=None,
                mode="main",
                suppress_labels=True,
                title_only=True,
            )
        out = capsys.readouterr().out
        assert "\u250c" in out

    def test_show_diagrams_slim_forwarded_to_render(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams=slim forwards suppress_labels=True, title_only=True, mode=main."""
        from unittest.mock import patch

        from little_loops.cli.loop import layout as layout_mod

        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch.object(
            layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
        ) as mock_render:
            run_foreground(executor, self._make_fsm(), self._make_args(show_diagrams="slim"))
            mock_render.assert_called_once_with(
                self._make_fsm(),
                highlight_state="start",
                highlight_color="32",
                edge_label_colors=None,
                badges=None,
                mode="main",
                suppress_labels=True,
                title_only=True,
            )
        out = capsys.readouterr().out
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

        from little_loops.cli.loop import layout as layout_mod

        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
            {"event": "action_output", "line": "verbose output line"},
        ]
        executor = MockExecutor(events)
        with patch.object(
            layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
        ) as mock_render:
            run_foreground(
                executor, self._make_fsm(), self._make_args(verbose=True, show_diagrams=True)
            )
            mock_render.assert_called_once_with(
                self._make_fsm(),
                highlight_state="start",
                highlight_color="32",
                edge_label_colors=None,
                badges=None,
                mode="main",
                suppress_labels=False,
                title_only=False,
            )
        out = capsys.readouterr().out
        assert "\u250c" in out
        assert "verbose output line" in out

    def test_clear_flag_emits_ansi_clear_when_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--clear flag with --show-diagrams emits alt-screen entry then ANSI clear when stdout is a tty."""
        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch("sys.stdout.isatty", return_value=True):
            run_foreground(
                executor, self._make_fsm(), self._make_args(clear=True, show_diagrams=True)
            )
        out = capsys.readouterr().out
        assert "\033[2J\033[H" in out
        assert "\033[?1049h" in out
        # Alt-screen entry must precede the per-render clear
        assert out.index("\033[?1049h") < out.index("\033[2J\033[H")

    def test_clear_flag_suppressed_when_not_tty(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--clear flag does not emit ANSI sequences when stdout is not a tty."""
        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch("sys.stdout.isatty", return_value=False):
            run_foreground(
                executor, self._make_fsm(), self._make_args(clear=True, show_diagrams=True)
            )
        out = capsys.readouterr().out
        assert "\033[2J" not in out
        assert "\033[?1049h" not in out

    def test_show_diagrams_and_clear_enters_alt_screen(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams + --clear on a tty enters the alternate screen buffer."""
        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch("sys.stdout.isatty", return_value=True):
            run_foreground(
                executor, self._make_fsm(), self._make_args(show_diagrams=True, clear=True)
            )
        out = capsys.readouterr().out
        assert "\033[?1049h" in out
        assert out.index("\033[?1049h") < out.index("\033[2J\033[H")

    def test_clear_only_no_alt_screen(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--clear without --show-diagrams does NOT enter the alternate screen buffer."""
        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch("sys.stdout.isatty", return_value=True):
            run_foreground(
                executor, self._make_fsm(), self._make_args(clear=True, show_diagrams=False)
            )
        out = capsys.readouterr().out
        assert "\033[?1049h" not in out
        assert "\033[2J\033[H" in out

    def test_show_diagrams_only_no_alt_screen(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--show-diagrams without --clear does NOT enter the alternate screen buffer."""
        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch("sys.stdout.isatty", return_value=True):
            run_foreground(
                executor, self._make_fsm(), self._make_args(show_diagrams=True, clear=False)
            )
        out = capsys.readouterr().out
        assert "\033[?1049h" not in out

    def test_alt_screen_exited_on_normal_completion(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Alt screen is exited (\\033[?1049l) after executor returns normally."""
        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        with patch("sys.stdout.isatty", return_value=True):
            run_foreground(
                executor, self._make_fsm(), self._make_args(show_diagrams=True, clear=True)
            )
        out = capsys.readouterr().out
        assert "\033[?1049l" in out

    def test_alt_screen_exited_on_executor_exception(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Alt screen is exited even when executor raises an exception."""

        class RaisingExecutor(MockExecutor):
            def run(self) -> ExecutionResult:
                raise RuntimeError("executor boom")

        executor = RaisingExecutor(events=[])
        with patch("sys.stdout.isatty", return_value=True):
            with pytest.raises(RuntimeError):
                run_foreground(
                    executor, self._make_fsm(), self._make_args(show_diagrams=True, clear=True)
                )
        out = capsys.readouterr().out
        assert "\033[?1049l" in out

    def test_scroll_region_set_when_alt_screen_active(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--show-diagrams + --clear emits a DECSTBM scroll-region sequence after pinned pane."""
        import re

        events = [{"event": "state_enter", "state": "start", "iteration": 1}]
        executor = MockExecutor(events)
        with patch("sys.stdout.isatty", return_value=True):
            run_foreground(
                executor, self._make_fsm(), self._make_args(show_diagrams=True, clear=True)
            )
        out = capsys.readouterr().out
        # DECSTBM: \033[<top>;<bottom>r
        assert re.search(r"\033\[\d+;\d+r", out), f"Expected scroll region sequence in: {out!r}"

    def test_scroll_region_reset_before_alt_screen_exit(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Scroll region (\\033[r) is reset before alt-screen exit (\\033[?1049l)."""
        events = [{"event": "state_enter", "state": "start", "iteration": 1}]
        executor = MockExecutor(events)
        with patch("sys.stdout.isatty", return_value=True):
            run_foreground(
                executor, self._make_fsm(), self._make_args(show_diagrams=True, clear=True)
            )
        out = capsys.readouterr().out
        assert "\033[r" in out
        assert "\033[?1049l" in out
        # The final \033[r in the stream must precede the alt-screen exit so
        # the main buffer is left without a restricted scroll region.
        assert out.rindex("\033[r") < out.rindex("\033[?1049l")

    def test_tall_fsm_falls_back_to_single_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        """On a short terminal a tall layered FSM falls back to single-line (not neighborhood).

        Neighborhood is skipped for layered topologies because it looks like a broken
        layered diagram.  The fallback ladder is now full → single.
        """
        import os
        import shutil

        tall_fsm = make_test_fsm(
            initial="s0",
            states={
                f"s{i}": make_test_state(
                    action=f"action {i}",
                    on_yes=f"s{i + 1}" if i < 19 else None,
                    terminal=(i == 19),
                )
                for i in range(20)
            },
        )
        events = [{"event": "state_enter", "state": "s5", "iteration": 1}]
        executor = MockExecutor(events)
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((80, 12))),
        ):
            run_foreground(executor, tall_fsm, self._make_args(show_diagrams=True, clear=True))
        out = capsys.readouterr().out
        # Single-line fallback: fsm: <preds> → [s5] → <succs>; far states must NOT appear.
        assert "fsm:" in out
        assert "[s5]" in out
        assert "s19" not in out

    def test_extreme_short_terminal_falls_back_to_single_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """On a tiny terminal the pinned pane falls back to the single-line status."""
        import os
        import shutil

        events = [{"event": "state_enter", "state": "start", "iteration": 1}]
        executor = MockExecutor(events)
        with (
            patch("sys.stdout.isatty", return_value=True),
            patch.object(shutil, "get_terminal_size", return_value=os.terminal_size((80, 6))),
        ):
            run_foreground(
                executor, self._make_fsm(), self._make_args(show_diagrams=True, clear=True)
            )
        out = capsys.readouterr().out
        assert "fsm:" in out
        assert "[start]" in out

    def test_clear_flag_suppressed_for_sub_loop_state_enter(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--clear flag does NOT emit clear-screen for depth>0 (sub-loop) state_enter events."""
        events = [
            {"event": "state_enter", "state": "child_state", "iteration": 1, "depth": 1},
        ]
        executor = MockExecutor(events)
        with patch("sys.stdout.isatty", return_value=True):
            run_foreground(executor, self._make_fsm(), self._make_args(clear=True))
        out = capsys.readouterr().out
        assert "\033[2J" not in out

    def test_sub_loop_diagram_keeps_parent_state_highlighted(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """During sub-loop execution, parent FSM diagram keeps the sub-loop state highlighted.

        When depth=1 child events arrive, _render_fsm_diagram should be called with
        the last depth=0 state as highlight_state, not the child state.
        """
        from unittest.mock import patch

        from little_loops.cli.loop import layout as layout_mod

        fsm = make_test_fsm(
            initial="run_sub_loop",
            states={
                "run_sub_loop": make_test_state(action="echo sub", on_yes="done"),
                "done": make_test_state(terminal=True),
            },
        )
        events = [
            {"event": "state_enter", "state": "run_sub_loop", "iteration": 1},
            {"event": "state_enter", "state": "child_state_1", "iteration": 1, "depth": 1},
            {"event": "state_enter", "state": "child_state_2", "iteration": 2, "depth": 1},
        ]
        executor = MockExecutor(events)
        with patch.object(
            layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
        ) as mock_render:
            run_foreground(executor, fsm, self._make_args(show_diagrams=True))
            assert mock_render.call_count == 3
            for call_args in mock_render.call_args_list:
                assert call_args.kwargs["highlight_state"] == "run_sub_loop", (
                    f"Expected highlight_state='run_sub_loop', got {call_args.kwargs['highlight_state']!r}"
                )

    def test_sub_loop_state_enter_indented_with_depth(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """state_enter event with depth=1 is prefixed with 2-space indent."""
        events = [
            {"event": "state_enter", "state": "child_state", "iteration": 1, "depth": 1},
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args())
        out = capsys.readouterr().out
        state_lines = [ln for ln in out.splitlines() if "child_state" in ln]
        assert state_lines, "Expected state_enter output for child_state"
        assert state_lines[0].startswith("  "), f"Expected 2-space indent, got: {state_lines[0]!r}"

    def test_depth_zero_state_enter_not_indented(self, capsys: pytest.CaptureFixture[str]) -> None:
        """state_enter event with no depth (depth=0) is not indented."""
        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args())
        out = capsys.readouterr().out
        state_lines = [ln for ln in out.splitlines() if "start" in ln and "[" in ln]
        assert state_lines, "Expected state_enter output for start"
        assert not state_lines[0].startswith("  "), "Depth-0 output should not be indented"

    def test_sub_loop_child_diagram_rendered_during_sub_loop_execution(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """During sub-loop execution only the deepest active loop diagram is rendered.

        When a depth=1 state_enter event arrives, _render_fsm_diagram is called for
        the child FSM only (not the parent). The header shows the parent breadcrumb.
        """
        from unittest.mock import call, patch

        from little_loops.cli.loop import layout as layout_mod

        child_fsm = make_test_fsm(
            name="child-loop",
            initial="child_state_1",
            states={
                "child_state_1": make_test_state(action="echo child", next="done"),
                "done": make_test_state(terminal=True),
            },
        )
        parent_fsm = make_test_fsm(
            name="parent-loop",
            initial="run_sub_loop",
            states={
                "run_sub_loop": StateConfig(loop="child-loop", next="done"),
                "done": make_test_state(terminal=True),
            },
        )
        events = [
            {"event": "state_enter", "state": "run_sub_loop", "iteration": 1},
            {"event": "state_enter", "state": "child_state_1", "iteration": 1, "depth": 1},
        ]
        executor = MockExecutor(events)
        with (
            patch.object(
                layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
            ) as mock_render,
            patch("little_loops.cli.loop._helpers.load_loop", return_value=child_fsm),
        ):
            run_foreground(executor, parent_fsm, self._make_args(show_diagrams=True))

        # depth=0: 1 render (parent FSM)
        # depth=1: 1 render (child FSM — deepest active, parent is not shown)
        assert mock_render.call_count == 2, f"Expected 2 render calls, got {mock_render.call_count}"
        calls = mock_render.call_args_list
        assert calls[0] == call(
            parent_fsm,
            highlight_state="run_sub_loop",
            highlight_color="32",
            edge_label_colors=None,
            badges=None,
            mode="main",
            suppress_labels=False,
            title_only=False,
        )
        assert calls[1] == call(
            child_fsm,
            highlight_state="child_state_1",
            highlight_color="32",
            edge_label_colors=None,
            badges=None,
            mode="main",
            suppress_labels=False,
            title_only=False,
        )
        out = capsys.readouterr().out
        # Breadcrumb in header instead of a separator line
        assert "child-loop" in out
        assert "parent-loop" in out
        assert "run_sub_loop" in out

    def test_grandchild_sub_loop_diagram_rendered_at_depth_2(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """At each depth, only the deepest active loop diagram is rendered.

        Emits depth=0 → depth=1 → depth=2 events and asserts 3 total render calls:
          - depth=0: 1 render (parent only)
          - depth=1: 1 render (child only — deepest active)
          - depth=2: 1 render (grandchild only — deepest active)
        Headers carry breadcrumb context instead of stacked separator lines.
        """
        from unittest.mock import patch

        from little_loops.cli.loop import layout as layout_mod

        grandchild_fsm = make_test_fsm(
            name="grandchild-loop",
            initial="gc_state_1",
            states={
                "gc_state_1": make_test_state(action="echo gc"),
                "done": make_test_state(terminal=True),
            },
        )
        child_fsm = make_test_fsm(
            name="child-loop",
            initial="child_state_1",
            states={
                "child_state_1": StateConfig(loop="grandchild-loop", next="done"),
                "done": make_test_state(terminal=True),
            },
        )
        parent_fsm = make_test_fsm(
            name="parent-loop",
            initial="run_sub_loop",
            states={
                "run_sub_loop": StateConfig(loop="child-loop", next="done"),
                "done": make_test_state(terminal=True),
            },
        )
        events = [
            {"event": "state_enter", "state": "run_sub_loop", "iteration": 1, "depth": 0},
            {"event": "state_enter", "state": "child_state_1", "iteration": 1, "depth": 1},
            {"event": "state_enter", "state": "gc_state_1", "iteration": 1, "depth": 2},
        ]
        executor = MockExecutor(events)

        def mock_load_loop(name_or_path: str, loops_dir, logger):  # type: ignore[no-untyped-def]
            if name_or_path == "child-loop":
                return child_fsm
            if name_or_path == "grandchild-loop":
                return grandchild_fsm
            raise FileNotFoundError(name_or_path)

        with (
            patch.object(
                layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
            ) as mock_render,
            patch("little_loops.cli.loop._helpers.load_loop", side_effect=mock_load_loop),
        ):
            run_foreground(executor, parent_fsm, self._make_args(show_diagrams=True))

        # One render per depth event — only the deepest active loop is shown.
        assert mock_render.call_count == 3, f"Expected 3 render calls, got {mock_render.call_count}"
        calls = mock_render.call_args_list
        # depth=0: parent only
        assert calls[0].args[0] is parent_fsm
        assert calls[0].kwargs["highlight_state"] == "run_sub_loop"
        # depth=1: child only (deepest active)
        assert calls[1].args[0] is child_fsm
        assert calls[1].kwargs["highlight_state"] == "child_state_1"
        # depth=2: grandchild only (deepest active)
        assert calls[2].args[0] is grandchild_fsm
        assert calls[2].kwargs["highlight_state"] == "gc_state_1"
        out = capsys.readouterr().out
        # Breadcrumb headers instead of separator lines
        assert "child-loop" in out
        assert "grandchild-loop" in out

    def test_shallow_reentry_clears_deeper_sub_loop_diagrams(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Re-entering a shallower depth clears deeper sub-loop diagrams.

        After depth=0 → depth=1 → depth=2, then another depth=0 event, only the
        parent diagram is rendered (no child or grandchild).
        """
        from unittest.mock import patch

        from little_loops.cli.loop import layout as layout_mod

        grandchild_fsm = make_test_fsm(
            name="grandchild-loop",
            initial="gc_state_1",
            states={"gc_state_1": make_test_state(action="echo gc")},
        )
        child_fsm = make_test_fsm(
            name="child-loop",
            initial="child_state_1",
            states={
                "child_state_1": StateConfig(loop="grandchild-loop", next="done"),
                "done": make_test_state(terminal=True),
            },
        )
        parent_fsm = make_test_fsm(
            name="parent-loop",
            initial="run_sub_loop",
            states={
                "run_sub_loop": StateConfig(loop="child-loop", next="done"),
                "done": make_test_state(terminal=True),
            },
        )
        events = [
            {"event": "state_enter", "state": "run_sub_loop", "iteration": 1, "depth": 0},
            {"event": "state_enter", "state": "child_state_1", "iteration": 1, "depth": 1},
            {"event": "state_enter", "state": "gc_state_1", "iteration": 1, "depth": 2},
            # Re-enter depth=0: clears depth=1 and depth=2
            {"event": "state_enter", "state": "done", "iteration": 2, "depth": 0},
        ]
        executor = MockExecutor(events)

        def mock_load_loop(name_or_path: str, loops_dir, logger):  # type: ignore[no-untyped-def]
            if name_or_path == "child-loop":
                return child_fsm
            if name_or_path == "grandchild-loop":
                return grandchild_fsm
            raise FileNotFoundError(name_or_path)

        with (
            patch.object(
                layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
            ) as mock_render,
            patch("little_loops.cli.loop._helpers.load_loop", side_effect=mock_load_loop),
        ):
            run_foreground(executor, parent_fsm, self._make_args(show_diagrams=True))

        # One render per depth event — deepest active loop only.
        # depth=0 "run_sub_loop": 1 render (parent)
        # depth=1 "child_state_1": 1 render (child)
        # depth=2 "gc_state_1": 1 render (grandchild)
        # depth=0 "done": 1 render (parent — deeper levels cleared)
        assert mock_render.call_count == 4, f"Expected 4 render calls, got {mock_render.call_count}"
        # The last render call should be parent only with "done" highlighted
        last_call = mock_render.call_args_list[-1]
        assert last_call.args[0] is parent_fsm
        assert last_call.kwargs["highlight_state"] == "done"

    def test_top_level_loop_header_shown_when_show_diagrams(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Top-level loop header is printed before the FSM diagram when show_diagrams=True."""
        events = [
            {"event": "state_enter", "state": "start", "iteration": 1},
        ]
        executor = MockExecutor(events)
        fsm = make_test_fsm(name="my-loop")
        run_foreground(executor, fsm, self._make_args(show_diagrams=True))
        out = capsys.readouterr().out
        assert "== loop: my-loop" in out

    def test_sub_loop_route_indented_with_depth(self, capsys: pytest.CaptureFixture[str]) -> None:
        """route event with depth=1 is prefixed with 2-space indent."""
        events = [
            {"event": "route", "from": "a", "to": "b", "depth": 1},
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._make_args())
        out = capsys.readouterr().out
        route_lines = [ln for ln in out.splitlines() if "->" in ln and "b" in ln]
        assert route_lines, "Expected route output"
        assert route_lines[0].startswith("  "), f"Expected 2-space indent, got: {route_lines[0]!r}"

    def test_run_foreground_startup_shows_artifact_paths(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """run_foreground startup prints artifact paths when loop_path is provided."""
        events: list[dict[str, Any]] = []
        executor = MockExecutor(events)
        fsm = self._make_fsm()
        fsm.context = {"output_dir": ".loops/output/"}
        loop_path = Path("loops/test-loop.yaml")
        run_foreground(executor, fsm, self._make_args(), loop_path=loop_path)
        captured = capsys.readouterr()
        assert "  loop:" in captured.out
        assert "loops/test-loop.yaml" in captured.out
        assert "  output_dir:" in captured.out
        assert ".loops/output/" in captured.out
        # Artifact lines appear after Max iterations and before the blank line
        max_iter_pos = captured.out.find("Max iterations:")
        loop_pos = captured.out.find("  loop:")
        assert max_iter_pos >= 0
        assert loop_pos >= 0
        assert max_iter_pos < loop_pos


class TestRunForegroundExitCodes:
    """Tests for run_foreground exit code mapping (BUG-605)."""

    def _make_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            quiet=False,
            verbose=False,
            follow=False,
            show_diagrams=None,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
        )

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


class TestRunForegroundResumeMode:
    """Tests for run_foreground(mode='resume') wiring (BUG-1645)."""

    def _make_args(self) -> argparse.Namespace:
        return argparse.Namespace(
            quiet=False,
            verbose=False,
            follow=False,
            show_diagrams=None,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
        )

    def _make_fsm(self) -> FSMLoop:
        return make_test_fsm()

    def test_resume_returns_1_when_nothing_to_resume(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """``executor.resume()`` returning None → exit 1, no alt-screen sequences emitted.

        Regression guard for the "nothing to resume" early-return added in BUG-1645.
        The early-return must run before any alt-screen sequence is emitted, so the
        terminal is never left in alt-screen mode when there is nothing to resume.
        """

        class _Executor:
            def __init__(self) -> None:
                self._on_event: Any = None

            def resume(self) -> ExecutionResult | None:
                return None

        rc = run_foreground(_Executor(), self._make_fsm(), self._make_args(), mode="resume")
        out = capsys.readouterr().out
        assert rc == 1
        assert "\033[?1049h" not in out  # alt-screen enter never emitted
        assert "\033[?1049l" not in out  # alt-screen exit never emitted

    def test_resume_dispatches_to_executor_resume_not_run(self) -> None:
        """mode='resume' calls executor.resume(), not executor.run()."""

        class _Executor:
            def __init__(self) -> None:
                self._on_event: Any = None
                self.resume_called = False
                self.run_called = False

            def resume(self) -> ExecutionResult:
                self.resume_called = True
                return ExecutionResult(
                    final_state="done",
                    iterations=1,
                    terminated_by="terminal",
                    duration_ms=100,
                    captured={},
                )

            def run(self) -> ExecutionResult:
                self.run_called = True
                return ExecutionResult(
                    final_state="done",
                    iterations=1,
                    terminated_by="terminal",
                    duration_ms=100,
                    captured={},
                )

        exec_obj = _Executor()
        with patch("builtins.print"):
            rc = run_foreground(exec_obj, self._make_fsm(), self._make_args(), mode="resume")
        assert rc == 0
        assert exec_obj.resume_called is True
        assert exec_obj.run_called is False

    def test_resume_prints_resumed_and_completed_prefix(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """mode='resume' completion line uses 'Resumed and completed:' prefix."""

        class _Executor:
            def __init__(self) -> None:
                self._on_event: Any = None

            def resume(self) -> ExecutionResult:
                return ExecutionResult(
                    final_state="done",
                    iterations=3,
                    terminated_by="terminal",
                    duration_ms=2500,
                    captured={},
                )

        rc = run_foreground(_Executor(), self._make_fsm(), self._make_args(), mode="resume")
        out = capsys.readouterr().out
        assert rc == 0
        assert "Resumed and completed" in out
        assert "Loop completed" not in out

    def test_invalid_mode_raises_value_error(self) -> None:
        """Unknown mode strings are rejected up-front."""

        class _Executor:
            def __init__(self) -> None:
                self._on_event: Any = None

            def run(self) -> ExecutionResult:
                raise AssertionError("should not be called")

        with pytest.raises(ValueError, match="invalid mode"):
            run_foreground(_Executor(), self._make_fsm(), self._make_args(), mode="bogus")


class TestStateBadges:
    """Tests for unicode badge constants and _get_state_badge helper."""

    def test_badge_constants_match_spec(self) -> None:
        """Badge strings match the spec values."""
        assert _ACTION_TYPE_BADGES["prompt"] == "\u2726"  # ✦
        assert _ACTION_TYPE_BADGES["slash_command"] == "/\u2501\u25ba"  # /━►
        assert _ACTION_TYPE_BADGES["shell"] == "\u276f_"  # ❯_
        assert _ACTION_TYPE_BADGES["mcp_tool"] == "\u26a1"  # ⚡
        assert _SUB_LOOP_BADGE == "\u21b3\u27f3"  # ↳⟳

    def test_get_state_badge_none_state(self) -> None:
        """No state → empty badge."""
        assert _get_state_badge(None) == ""

    def test_get_state_badge_no_action(self) -> None:
        """State with no action or action_type → empty badge."""
        assert _get_state_badge(StateConfig()) == ""

    def test_get_state_badge_action_types(self) -> None:
        """Known action_types map to their unicode badges."""
        for action_type, expected in _ACTION_TYPE_BADGES.items():
            state = StateConfig(action="x", action_type=action_type)
            assert _get_state_badge(state) == expected, f"action_type={action_type!r}"

    def test_get_state_badge_shell_fallback(self) -> None:
        """State with action but no action_type falls back to shell badge."""
        state = StateConfig(action="echo hi")
        assert _get_state_badge(state) == _ACTION_TYPE_BADGES["shell"]

    def test_get_state_badge_sub_loop(self) -> None:
        """State with loop field returns sub-loop badge regardless of action_type."""
        state = StateConfig(loop="child-loop.yaml")
        assert _get_state_badge(state) == _SUB_LOOP_BADGE

    def test_sub_loop_badge_takes_precedence_over_action_type(self) -> None:
        """loop field checked before action_type for badge selection."""
        state = StateConfig(action_type="prompt", loop="child.yaml")
        assert _get_state_badge(state) == _SUB_LOOP_BADGE

    def test_diagram_contains_prompt_badge(self) -> None:
        """FSM diagram output contains ✦ in top border with space padding on each side."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={
                "start": StateConfig(action="do something", action_type="prompt", next="done"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=5,
        )
        result = _render_fsm_diagram(fsm)
        assert "\u2726" in result  # ✦ prompt badge present
        top_border = next(ln for ln in result.split("\n") if "\u250c" in ln)
        assert " \u2726 " in top_border  # space padding on each side

    def test_badge_border_width_accounts_for_padding(self) -> None:
        """Box width is large enough for badge + 2 padding spaces even when badge > label."""
        # Use a sub-loop badge (↳⟳, display width 2) on a state with a very short name
        # so badge_w + 2 > len(label). The box must still render without truncating the badge.
        fsm = FSMLoop(
            name="test",
            initial="x",
            states={
                "x": StateConfig(loop="child.yaml", next="done"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=1,
        )
        result = _render_fsm_diagram(fsm)
        top_border = next(
            ln for ln in result.split("\n") if "\u250c" in ln and _SUB_LOOP_BADGE[0] in ln
        )
        # Both padding spaces must appear alongside the badge
        assert " " + _SUB_LOOP_BADGE[0] in top_border  # leading space before badge

    def test_highlighted_badge_is_colorized(self) -> None:
        """Badge characters in top border use _bc() colorization when state is highlighted."""
        import little_loops.cli.output as output_mod

        fsm = FSMLoop(
            name="test",
            initial="start",
            states={
                "start": StateConfig(action="do something", action_type="prompt", next="done"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=5,
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm, highlight_state="start", highlight_color="36")
        # The badge ✦ must appear wrapped in the highlight color
        assert "\033[36;46m\u2726" in result

    def test_route_badge_constant(self) -> None:
        """_ROUTE_BADGE is the dedicated branching/routing unicode character."""
        assert _ROUTE_BADGE == "\u2443"  # ⑃

    def test_get_state_badge_route_state(self) -> None:
        """State with route field returns the route badge."""
        state = StateConfig(route=RouteConfig(routes={"yes": "a", "no": "b"}))
        assert _get_state_badge(state) == _ROUTE_BADGE

    def test_route_badge_lower_priority_than_sub_loop(self) -> None:
        """loop field takes precedence over route for badge selection."""
        state = StateConfig(
            loop="child.yaml",
            route=RouteConfig(routes={"yes": "a"}),
        )
        assert _get_state_badge(state) == _SUB_LOOP_BADGE

    def test_diagram_contains_route_badge(self) -> None:
        """FSM diagram output contains ⑃ for a route state."""
        fsm = FSMLoop(
            name="test",
            initial="route_format",
            states={
                "route_format": StateConfig(
                    route=RouteConfig(routes={"pass": "done", "fail": "done"})
                ),
                "done": StateConfig(terminal=True),
            },
            max_iterations=5,
        )
        result = _render_fsm_diagram(fsm)
        assert "\u2443" in result  # ⑃ route badge in top border


class TestEdgeLineColorization:
    """Tests that FSM transition line characters are colored by edge semantic type.

    ENH-813: Color-code transition lines (│ pipes, ─ dashes, corner connectors,
    ▼▶ arrowheads) in addition to the existing label text colorization.
    """

    def _make_fsm(
        self,
        initial: str = "a",
        states: dict[str, StateConfig] | None = None,
    ) -> FSMLoop:
        return FSMLoop(name="test", initial=initial, states=states or {}, max_iterations=10)

    def test_collect_edges_includes_on_blocked(self) -> None:
        """_collect_edges() collects on_blocked transitions as 'blocked' label."""
        fsm = self._make_fsm(
            states={
                "a": StateConfig(action="step", on_blocked="b"),
                "b": StateConfig(terminal=True),
            }
        )
        edges = _collect_edges(fsm)
        assert ("a", "b", "blocked") in edges

    def test_collect_edges_includes_on_retry_exhausted(self) -> None:
        """_collect_edges() collects on_retry_exhausted transitions."""
        fsm = self._make_fsm(
            states={
                "a": StateConfig(action="step", max_retries=3, on_retry_exhausted="b"),
                "b": StateConfig(terminal=True),
            }
        )
        edges = _collect_edges(fsm)
        assert ("a", "b", "retry_exhausted") in edges

    def test_collect_edges_includes_on_rate_limit_exhausted(self) -> None:
        """_collect_edges() collects on_rate_limit_exhausted transitions. BUG-1109."""
        fsm = self._make_fsm(
            states={
                "a": StateConfig(
                    action="step",
                    max_rate_limit_retries=3,
                    on_rate_limit_exhausted="b",
                ),
                "b": StateConfig(terminal=True),
            }
        )
        edges = _collect_edges(fsm)
        assert ("a", "b", "rate_limit_exhausted") in edges

    def test_collect_edges_excludes_rate_limit_waiting(self) -> None:
        # rate_limit_waiting is an event-only heartbeat, not a routed edge —
        # first absence assertion in this suite (ENH-1149).
        fsm = self._make_fsm(
            states={
                "a": StateConfig(
                    action="step",
                    max_rate_limit_retries=3,
                    on_rate_limit_exhausted="b",
                ),
                "b": StateConfig(terminal=True),
            }
        )
        edges = _collect_edges(fsm)
        assert not any(label == "rate_limit_waiting" for _, _, label in edges)

    def test_error_edge_connector_chars_are_colored_red(self) -> None:
        """on_error transition connector characters (│, ▼) are colored red."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            states={
                "a": StateConfig(action="step", on_error="b"),
                "b": StateConfig(terminal=True),
            }
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm)

        # The pipe │ or arrowhead ▼ should be wrapped in red ANSI (code 31)
        assert "\033[31m\u2502" in result or "\033[31m\u25bc" in result, (
            f"Expected red ANSI on error edge connector chars.\n{result!r}"
        )

    def test_yes_edge_connector_chars_are_colored_green(self) -> None:
        """on_yes transition connector characters are colored green."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            states={
                "a": StateConfig(action="step", on_yes="b"),
                "b": StateConfig(terminal=True),
            }
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm)

        # Green code 32 on │ or ▼
        assert "\033[32m\u2502" in result or "\033[32m\u25bc" in result, (
            f"Expected green ANSI on yes edge connector chars.\n{result!r}"
        )

    def test_no_edge_connector_chars_are_colored_orange(self) -> None:
        """on_no transition connector characters are colored orange."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            states={
                "a": StateConfig(action="step", on_no="b"),
                "b": StateConfig(terminal=True),
            }
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm)

        # Orange code 38;5;208 on │ or ▼
        assert "\033[38;5;208m\u2502" in result or "\033[38;5;208m\u25bc" in result, (
            f"Expected orange ANSI on no edge connector chars.\n{result!r}"
        )

    def test_blocked_edge_connector_chars_are_colored_red(self) -> None:
        """on_blocked transition connector characters are colored red."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            states={
                "a": StateConfig(action="step", on_blocked="b"),
                "b": StateConfig(terminal=True),
            }
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm)

        assert "\033[31m\u2502" in result or "\033[31m\u25bc" in result, (
            f"Expected red ANSI on blocked edge connector chars.\n{result!r}"
        )

    def test_back_edge_connector_chars_are_colored(self) -> None:
        """Back-edge (loop-back) connector characters are colored by edge type."""
        import little_loops.cli.output as output_mod

        # a → b (on_yes), b → a (on_error, back-edge)
        fsm = self._make_fsm(
            states={
                "a": StateConfig(action="step_a", on_yes="b"),
                "b": StateConfig(action="step_b", on_error="a", on_yes="c"),
                "c": StateConfig(terminal=True),
            }
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm)

        # Back-edge uses │ (vertical) and ▶ (arrowhead): expect red on error back-edge
        assert "\033[31m\u2502" in result or "\033[31m\u25b6" in result, (
            f"Expected red ANSI on error back-edge connector chars.\n{result!r}"
        )

    def test_no_ansi_on_connector_chars_when_color_disabled(self) -> None:
        """When _USE_COLOR is False, no ANSI codes appear on connector characters."""
        import little_loops.cli.output as output_mod

        fsm = self._make_fsm(
            states={
                "a": StateConfig(action="step", on_error="b"),
                "b": StateConfig(terminal=True),
            }
        )
        with patch.object(output_mod, "_USE_COLOR", False):
            result = _render_fsm_diagram(fsm)

        assert "\033[" not in result, f"Expected no ANSI codes when color disabled.\n{result!r}"


class TestCustomGlyphOverride:
    """Tests for custom glyph/badge overrides in FSM box diagrams."""

    def _make_fsm(
        self,
        initial: str = "a",
        states: dict[str, StateConfig] | None = None,
    ) -> FSMLoop:
        from little_loops.fsm.schema import FSMLoop

        if states is None:
            states = {"a": StateConfig(terminal=True)}
        return FSMLoop(name="test", initial=initial, states=states)

    def test_custom_prompt_badge_applied(self) -> None:
        """Custom 'prompt' badge is rendered instead of the default ✦."""
        from little_loops.cli.loop.layout import _render_fsm_diagram as _render

        fsm = self._make_fsm(states={"a": StateConfig(action_type="prompt", terminal=True)})
        result = _render(fsm, badges={"prompt": "P"})
        assert "P" in result
        assert "\u2726" not in result  # default ✦ not present

    def test_custom_shell_badge_applied(self) -> None:
        """Custom 'shell' badge overrides the default ❯_."""
        from little_loops.cli.loop.layout import _render_fsm_diagram as _render

        fsm = self._make_fsm(states={"a": StateConfig(action="run something", terminal=True)})
        result = _render(fsm, badges={"shell": "S"})
        assert "S" in result
        assert "\u276f_" not in result  # default ❯_ not present

    def test_partial_override_leaves_defaults_intact(self) -> None:
        """Overriding one glyph does not change other glyphs."""
        from little_loops.cli.loop.layout import _render_fsm_diagram as _render

        fsm = self._make_fsm(
            initial="a",
            states={
                "a": StateConfig(action_type="mcp_tool", on_yes="b"),
                "b": StateConfig(action_type="prompt", terminal=True),
            },
        )
        # Override only prompt; mcp_tool should keep its default
        result = _render(fsm, badges={"prompt": "PROMPT"})
        assert "PROMPT" in result
        assert "\u26a1" in result  # default ⚡ for mcp_tool still present

    def test_no_badges_arg_uses_defaults(self) -> None:
        """Calling _render_fsm_diagram without badges= yields default glyphs."""
        from little_loops.cli.loop.layout import _render_fsm_diagram as _render

        fsm = self._make_fsm(states={"a": StateConfig(action_type="prompt", terminal=True)})
        result = _render(fsm)
        assert "\u2726" in result  # default ✦ present


# ---------------------------------------------------------------------------
# ENH-1672: DiagramFacets + resolve_facets unit tests
# ---------------------------------------------------------------------------


class TestDiagramFacets:
    """Unit tests for diagram_modes.DiagramFacets, PRESET_EXPANSIONS, and resolve_facets."""

    def test_each_preset_resolves_to_documented_facets(self) -> None:
        from little_loops.cli.loop.diagram_modes import PRESET_EXPANSIONS, DiagramFacets

        expected: dict[str, DiagramFacets] = {
            "detailed": DiagramFacets("layered", True, "full", "full", "preset"),
            "summary": DiagramFacets("layered", True, "full", "main", "preset"),
            "clean": DiagramFacets("layered", False, "title", "main", "preset"),
            "local": DiagramFacets("neighborhood", True, "title", "main", "preset"),
            "slim": DiagramFacets("neighborhood", False, "title", "main", "preset"),
            "oneline": DiagramFacets("inline", True, "title", "full", "preset"),
        }
        for name, exp in expected.items():
            assert PRESET_EXPANSIONS[name] == exp, f"Preset {name!r} mismatch"

    def test_topology_values_resolve_with_defaults(self) -> None:
        from little_loops.cli.loop.diagram_modes import resolve_facets

        for topo in ("layered", "neighborhood", "inline"):
            args = argparse.Namespace(
                show_diagrams=topo,
                diagram_edge_labels=None,
                diagram_state_detail=None,
                diagram_scope=None,
            )
            f = resolve_facets(args)
            assert f is not None
            assert f.topology == topo
            assert f.source == "topology"
            assert f.edge_labels is True
            assert f.state_detail == "full"
            assert f.scope == "full"

    def test_modifier_overrides_preset(self) -> None:
        from little_loops.cli.loop.diagram_modes import resolve_facets

        # clean preset has edge_labels=False; override with on → edge_labels=True
        args = argparse.Namespace(
            show_diagrams="clean",
            diagram_edge_labels="on",
            diagram_state_detail=None,
            diagram_scope=None,
        )
        f = resolve_facets(args)
        assert f is not None
        assert f.edge_labels is True  # override applied
        assert f.state_detail == "title"  # preset default preserved

    def test_absent_modifiers_preserve_preset(self) -> None:
        from little_loops.cli.loop.diagram_modes import resolve_facets

        args = argparse.Namespace(
            show_diagrams="clean",
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
        )
        f = resolve_facets(args)
        assert f is not None
        assert f.edge_labels is False  # clean preset default
        assert f.state_detail == "title"

    def test_bare_flag_sentinel_resolves_to_summary_default(self) -> None:
        from little_loops.cli.loop.diagram_modes import resolve_facets

        args = argparse.Namespace(
            show_diagrams=True,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
        )
        f = resolve_facets(args)
        assert f is not None
        assert f.topology == "layered"
        assert f.scope == "main"
        assert f.source == "default"

    def test_none_show_diagrams_returns_none(self) -> None:
        from little_loops.cli.loop.diagram_modes import resolve_facets

        args = argparse.Namespace(show_diagrams=None)
        assert resolve_facets(args) is None

    def test_legacy_values_raise_argument_type_error(self) -> None:
        import argparse as ap

        from little_loops.cli.loop.diagram_modes import _parse_show_diagrams

        for legacy in ("main", "full", "mini"):
            with pytest.raises(ap.ArgumentTypeError) as exc_info:
                _parse_show_diagrams(legacy)
            assert legacy in str(exc_info.value) or "renamed" in str(exc_info.value)

    def test_unknown_value_raises_argument_type_error(self) -> None:
        import argparse as ap

        from little_loops.cli.loop.diagram_modes import _parse_show_diagrams

        with pytest.raises(ap.ArgumentTypeError):
            _parse_show_diagrams("bogus")


# ---------------------------------------------------------------------------
# ENH-1641: --show-diagrams main/full mode tests
# ---------------------------------------------------------------------------


class TestShowDiagramsMode:
    """Renderer-level tests for the ``mode`` parameter on ``_render_fsm_diagram``.

    ``main`` hides off-happy-path edges (error, partial, blocked, retry_exhausted,
    rate_limit_exhausted, throttle_hard) and the states that become unreachable
    once those edges are removed. ``full`` preserves the legacy all-edges view.
    """

    def _fsm_with_error_branch(self) -> FSMLoop:
        return FSMLoop(
            name="test-main",
            initial="start",
            states={
                "start": StateConfig(action="echo start", on_yes="done", on_error="fail_terminal"),
                "done": StateConfig(terminal=True),
                "fail_terminal": StateConfig(terminal=True),
            },
            max_iterations=5,
        )

    def test_show_diagrams_main_hides_error_edges(self) -> None:
        """main mode strips error/blocked/retry_exhausted edge labels from output."""
        import re as _re

        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = FSMLoop(
            name="test",
            initial="start",
            states={
                "start": StateConfig(
                    action="echo start",
                    on_yes="done",
                    on_error="fail",
                    on_blocked="fail",
                    on_retry_exhausted="fail",
                ),
                "done": StateConfig(terminal=True),
                "fail": StateConfig(terminal=True),
            },
            max_iterations=5,
        )
        result = _render_fsm_diagram(fsm, mode="main")
        plain = _re.compile(r"\033\[[0-9;]*m").sub("", result)
        assert "error" not in plain
        assert "blocked" not in plain
        assert "retry_exhausted" not in plain
        assert "yes" in plain

    def test_show_diagrams_main_hides_unreachable_fail_terminals(self) -> None:
        """main mode hides states only reachable via stripped error edges."""
        import re as _re

        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = self._fsm_with_error_branch()
        result = _render_fsm_diagram(fsm, mode="main")
        plain = _re.compile(r"\033\[[0-9;]*m").sub("", result)
        assert "fail_terminal" not in plain
        assert "start" in plain
        assert "done" in plain

    def test_show_diagrams_main_keeps_reachable_terminals(self) -> None:
        """main mode keeps terminal states reachable via happy-path edges."""
        import re as _re

        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = self._fsm_with_error_branch()
        result = _render_fsm_diagram(fsm, mode="main")
        plain = _re.compile(r"\033\[[0-9;]*m").sub("", result)
        assert "done" in plain

    def test_show_diagrams_full_matches_legacy_output(self) -> None:
        """full mode produces the same output as today's default (no mode kwarg)."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = self._fsm_with_error_branch()
        legacy = _render_fsm_diagram(fsm)
        full = _render_fsm_diagram(fsm, mode="full")
        assert legacy == full

    def test_show_diagrams_main_falls_back_to_full_when_highlight_off_path(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Active state off the main path triggers a full-mode fallback render
        for that iteration with an explanatory one-line note prepended.
        """
        from unittest.mock import patch

        from little_loops.cli.loop import layout as layout_mod

        fsm = self._fsm_with_error_branch()
        events = [
            {"event": "state_enter", "state": "fail_terminal", "iteration": 1},
        ]
        executor = MockExecutor(events)
        args = argparse.Namespace(
            quiet=True,
            verbose=False,
            show_diagrams="summary",
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
        )
        with patch.object(
            layout_mod, "_render_fsm_diagram", wraps=layout_mod._render_fsm_diagram
        ) as mock_render:
            run_foreground(executor, fsm, args)

        modes_seen = [c.kwargs.get("mode") for c in mock_render.call_args_list]
        assert "full" in modes_seen, f"Expected full-mode fallback render, got {modes_seen}"
        out = capsys.readouterr().out
        assert "showing full diagram" in out
        assert "fail_terminal" in out


class TestShowDiagramsMiniMode:
    """Renderer-level tests for ``mode='mini'`` on ``_render_fsm_diagram``.

    ``mini`` is a skeleton view: state boxes show only the title (no body
    lines), edges render without label text, and the edge set inherits
    ``main``'s happy-path filter.
    """

    def _strip_ansi(self, s: str) -> str:
        import re as _re

        return _re.compile(r"\033\[[0-9;]*m").sub("", s)

    def _fsm_with_action(self) -> FSMLoop:
        return FSMLoop(
            name="test-mini",
            initial="start",
            states={
                "start": StateConfig(
                    action="echo first-action-line\nsecond-action-line",
                    on_yes="done",
                    on_no="retry",
                ),
                "retry": StateConfig(action="echo retry-action", next="start"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=5,
        )

    def test_show_diagrams_mini_box_contains_only_state_title(self) -> None:
        """mini mode suppresses per-state action body lines."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = self._fsm_with_action()
        result = _render_fsm_diagram(fsm, mode="mini")
        plain = self._strip_ansi(result)
        # Action body content must NOT appear inside boxes
        assert "first-action-line" not in plain
        assert "second-action-line" not in plain
        assert "retry-action" not in plain
        # State names DO appear
        assert "start" in plain
        assert "retry" in plain
        assert "done" in plain

    def test_show_diagrams_mini_edges_have_no_labels(self) -> None:
        """mini mode suppresses edge labels (no 'yes', 'no', 'next' text)."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = self._fsm_with_action()
        result = _render_fsm_diagram(fsm, mode="mini")
        plain = self._strip_ansi(result)
        # State names still present
        assert "start" in plain
        assert "done" in plain
        # Edge labels suppressed
        assert "yes" not in plain
        assert "no" not in plain
        assert "next" not in plain

    def test_show_diagrams_mini_active_state_still_highlighted(self) -> None:
        """Active-state highlighting still applies in mini mode."""
        import little_loops.cli.output as output_mod
        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = self._fsm_with_action()
        with patch.object(output_mod, "_USE_COLOR", True):
            result = _render_fsm_diagram(fsm, highlight_state="start", mode="mini")
        # Green border (ANSI 32) + green background fill (ANSI 42) — same
        # highlighting pipeline as main/full modes.
        assert "\033[32;42m" in result
        assert "\033[42m " in result

    def test_show_diagrams_mini_inherits_main_edge_filter(self) -> None:
        """mini mode hides off-happy-path edges (inherits main's filter)."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = FSMLoop(
            name="test-mini-filter",
            initial="start",
            states={
                "start": StateConfig(
                    action="echo start",
                    on_yes="done",
                    on_error="fail_terminal",
                ),
                "done": StateConfig(terminal=True),
                "fail_terminal": StateConfig(terminal=True),
            },
            max_iterations=5,
        )
        result = _render_fsm_diagram(fsm, mode="mini")
        plain = self._strip_ansi(result)
        # Off-happy-path state and edge filtered out
        assert "fail_terminal" not in plain
        assert "error" not in plain
        # Happy-path states still appear
        assert "start" in plain
        assert "done" in plain


class TestShowDiagramsArgparse:
    """Argparse parsing tests for the restructured ``--show-diagrams`` flag."""

    def _parse_run_args(self, argv: list[str]) -> argparse.Namespace:
        captured: dict[str, argparse.Namespace] = {}

        def fake_cmd_run(loop, args, loops_dir, logger):  # type: ignore[no-untyped-def]
            captured["args"] = args
            return 0

        with (
            patch("sys.argv", argv),
            patch("little_loops.cli.loop.run.cmd_run", fake_cmd_run),
        ):
            from little_loops.cli.loop import main_loop

            main_loop()
        return captured["args"]

    def _parse_run_args_expect_error(self, argv: list[str]) -> str:
        """Parse argv, expect SystemExit, and return the error message."""
        import io

        with pytest.raises(SystemExit):
            with patch("sys.argv", argv), patch("sys.stderr", io.StringIO()) as fake_err:
                from little_loops.cli.loop import main_loop

                main_loop()
        return fake_err.getvalue()

    def test_bare_show_diagrams_stores_sentinel(self) -> None:
        args = self._parse_run_args(["ll-loop", "run", "my-loop", "--show-diagrams"])
        assert args.show_diagrams is True  # const=True sentinel

    def test_show_diagrams_preset_summary(self) -> None:
        args = self._parse_run_args(["ll-loop", "run", "my-loop", "--show-diagrams=summary"])
        assert args.show_diagrams == "summary"

    def test_show_diagrams_preset_detailed(self) -> None:
        args = self._parse_run_args(["ll-loop", "run", "my-loop", "--show-diagrams=detailed"])
        assert args.show_diagrams == "detailed"

    def test_show_diagrams_preset_clean(self) -> None:
        args = self._parse_run_args(["ll-loop", "run", "my-loop", "--show-diagrams=clean"])
        assert args.show_diagrams == "clean"

    def test_show_diagrams_preset_slim(self) -> None:
        args = self._parse_run_args(["ll-loop", "run", "my-loop", "--show-diagrams=slim"])
        assert args.show_diagrams == "slim"

    def test_show_diagrams_topology_layered(self) -> None:
        args = self._parse_run_args(["ll-loop", "run", "my-loop", "--show-diagrams=layered"])
        assert args.show_diagrams == "layered"

    def test_show_diagrams_topology_neighborhood(self) -> None:
        args = self._parse_run_args(["ll-loop", "run", "my-loop", "--show-diagrams=neighborhood"])
        assert args.show_diagrams == "neighborhood"

    def test_show_diagrams_absent_is_none(self) -> None:
        args = self._parse_run_args(["ll-loop", "run", "my-loop"])
        assert args.show_diagrams is None

    def test_legacy_main_raises_migration_hint(self) -> None:
        err = self._parse_run_args_expect_error(
            ["ll-loop", "run", "my-loop", "--show-diagrams=main"]
        )
        assert "main was renamed" in err
        assert "summary" in err

    def test_legacy_full_raises_migration_hint(self) -> None:
        err = self._parse_run_args_expect_error(
            ["ll-loop", "run", "my-loop", "--show-diagrams=full"]
        )
        assert "full was renamed" in err
        assert "detailed" in err

    def test_legacy_mini_raises_migration_hint(self) -> None:
        err = self._parse_run_args_expect_error(
            ["ll-loop", "run", "my-loop", "--show-diagrams=mini"]
        )
        assert "mini was renamed" in err
        assert "clean" in err

    def test_modifier_flags_parsed(self) -> None:
        args = self._parse_run_args(
            [
                "ll-loop",
                "run",
                "my-loop",
                "--show-diagrams=clean",
                "--diagram-edge-labels=on",
                "--diagram-state-detail=full",
                "--diagram-scope=main",
            ]
        )
        assert args.diagram_edge_labels == "on"
        assert args.diagram_state_detail == "full"
        assert args.diagram_scope == "main"


class TestShowDiagramsSubprocessReemit:
    """Tests for run_background re-emitting --show-diagrams + modifiers to the subprocess cmd."""

    def _capture_cmd(
        self,
        show_diagrams_value: object,
        diagram_edge_labels: str | None = None,
        diagram_state_detail: str | None = None,
        diagram_scope: str | None = None,
    ) -> list[str]:
        from unittest.mock import MagicMock

        from little_loops.cli.loop._helpers import run_background

        captured: dict[str, list[str]] = {}

        def fake_popen(cmd, *_args, **_kwargs):  # type: ignore[no-untyped-def]
            captured["cmd"] = list(cmd)
            mock_proc = MagicMock()
            mock_proc.pid = 12345
            return mock_proc

        args_ns = argparse.Namespace(
            input=None,
            max_iterations=None,
            no_llm=False,
            llm_model=None,
            verbose=False,
            show_diagrams=show_diagrams_value,
            diagram_edge_labels=diagram_edge_labels,
            diagram_state_detail=diagram_state_detail,
            diagram_scope=diagram_scope,
            quiet=False,
            queue=False,
            context=[],
            program_md=None,
            delay=None,
            handoff_threshold=None,
            context_limit=None,
        )
        with patch("subprocess.Popen", side_effect=fake_popen):
            with patch("builtins.open"):
                with patch("pathlib.Path.write_text"):
                    run_background("my-loop", args_ns, Path("/tmp/fake-loops"))
        return captured["cmd"]

    def test_preset_summary_reemitted_to_cmd(self) -> None:
        cmd = self._capture_cmd("summary")
        assert "--show-diagrams" in cmd
        idx = cmd.index("--show-diagrams")
        assert cmd[idx + 1] == "summary"

    def test_preset_detailed_reemitted_to_cmd(self) -> None:
        cmd = self._capture_cmd("detailed")
        assert "--show-diagrams" in cmd
        idx = cmd.index("--show-diagrams")
        assert cmd[idx + 1] == "detailed"

    def test_preset_clean_reemitted_to_cmd(self) -> None:
        cmd = self._capture_cmd("clean")
        assert "--show-diagrams" in cmd
        idx = cmd.index("--show-diagrams")
        assert cmd[idx + 1] == "clean"

    def test_preset_slim_reemitted_to_cmd(self) -> None:
        cmd = self._capture_cmd("slim")
        assert "--show-diagrams" in cmd
        idx = cmd.index("--show-diagrams")
        assert cmd[idx + 1] == "slim"

    def test_none_mode_suppresses_flag_from_cmd(self) -> None:
        cmd = self._capture_cmd(None)
        assert "--show-diagrams" not in cmd

    def test_bare_flag_sentinel_reemitted_bare(self) -> None:
        cmd = self._capture_cmd(True)
        assert "--show-diagrams" in cmd
        idx = cmd.index("--show-diagrams")
        # bare flag: next token is not a value for --show-diagrams
        assert idx == len(cmd) - 1 or not cmd[idx + 1].startswith("--show")

    def test_edge_labels_off_reemitted(self) -> None:
        cmd = self._capture_cmd("clean", diagram_edge_labels="off")
        assert "--diagram-edge-labels" in cmd
        idx = cmd.index("--diagram-edge-labels")
        assert cmd[idx + 1] == "off"

    def test_state_detail_title_reemitted(self) -> None:
        cmd = self._capture_cmd("summary", diagram_state_detail="title")
        assert "--diagram-state-detail" in cmd
        idx = cmd.index("--diagram-state-detail")
        assert cmd[idx + 1] == "title"

    def test_scope_main_reemitted(self) -> None:
        cmd = self._capture_cmd("detailed", diagram_scope="main")
        assert "--diagram-scope" in cmd
        idx = cmd.index("--diagram-scope")
        assert cmd[idx + 1] == "main"

    def test_none_modifiers_not_reemitted(self) -> None:
        cmd = self._capture_cmd("summary")
        assert "--diagram-edge-labels" not in cmd
        assert "--diagram-state-detail" not in cmd
        assert "--diagram-scope" not in cmd


class TestChoosePinnedLayout:
    """Tests for the pure pinned-pane fallback ladder helper."""

    def test_picks_first_variant_when_it_fits(self) -> None:
        from little_loops.cli.loop._helpers import _choose_pinned_layout

        full = "a\nb\nc"  # 3 lines
        pinned, h = _choose_pinned_layout(rows=20, variants=[full, "x", "y"], min_action_rows=6)
        assert pinned == full
        assert h == 3

    def test_falls_back_to_compact_when_full_too_big(self) -> None:
        from little_loops.cli.loop._helpers import _choose_pinned_layout

        full = "\n".join(["row"] * 20)  # 20 lines
        compact = "x\ny\nz"  # 3 lines
        pinned, h = _choose_pinned_layout(
            rows=10, variants=[full, compact, "single"], min_action_rows=6
        )
        # full = 20 + 6 = 26 > 10; compact = 3 + 6 = 9 ≤ 10
        assert pinned == compact
        assert h == 3

    def test_returns_last_when_none_fit(self) -> None:
        from little_loops.cli.loop._helpers import _choose_pinned_layout

        pinned, h = _choose_pinned_layout(
            rows=2, variants=["full\nfull", "single line"], min_action_rows=6
        )
        # Even single requires 1 + 6 = 7 > 2 → returns last variant anyway
        assert pinned == "single line"
        assert h == 1


class TestRenderNeighborhoodDiagram:
    """Tests for _render_neighborhood_diagram pure renderer."""

    def test_renders_preds_active_succs(self) -> None:
        from little_loops.cli.loop.layout import _render_neighborhood_diagram

        fsm = make_test_fsm(
            initial="a",
            states={
                "a": make_test_state(action="...", on_yes="b"),
                "b": make_test_state(action="...", on_yes="c", on_no="d"),
                "c": make_test_state(terminal=True),
                "d": make_test_state(terminal=True),
            },
        )
        out = _render_neighborhood_diagram(fsm, "b")
        assert "a" in out
        assert "b" in out
        assert "c" in out
        assert "d" in out

    def test_unknown_active_returns_empty(self) -> None:
        from little_loops.cli.loop.layout import _render_neighborhood_diagram

        fsm = make_test_fsm()
        assert _render_neighborhood_diagram(fsm, "nonexistent") == ""

    def test_single_succ_aligns_with_arrow_row_when_multiple_preds(self) -> None:
        """3 preds + 1 succ: the succ box must sit on the arrow row, not row 0.

        Regression: previously `_build_stack` filled top-down, so the lone
        succ landed at row 0 while the arrow was drawn at the active state's
        center row (row 4 for n_rows=3), pointing into empty space.
        """
        import re

        from little_loops.cli.loop.layout import _render_neighborhood_diagram

        fsm = make_test_fsm(
            initial="a",
            states={
                "a": make_test_state(action="...", on_yes="target"),
                "b": make_test_state(action="...", on_yes="target"),
                "c": make_test_state(action="...", on_yes="target"),
                "target": make_test_state(action="...", on_yes="end"),
                "end": make_test_state(terminal=True),
            },
        )
        out = _render_neighborhood_diagram(fsm, "target")
        ansi_re = re.compile(r"\x1b\[[0-9;]*m")
        lines = [ansi_re.sub("", ln) for ln in out.split("\n")]

        target_row = next(i for i, ln in enumerate(lines) if "target" in ln)
        end_row = next(i for i, ln in enumerate(lines) if "end" in ln)
        # Active "target" label and lone succ "end" label must share the same
        # row — that's the row the ──▶ arrow is drawn on.
        assert target_row == end_row, (
            f"target at row {target_row}, end at row {end_row}; output:\n{out}"
        )

    def test_main_mode_filters_on_error_preds(self) -> None:
        """mode='main' must hide preds that only connect via on_error.

        Contrast with mode='full' which still includes them.
        """
        from little_loops.cli.loop.layout import _render_neighborhood_diagram

        fsm = make_test_fsm(
            initial="a",
            states={
                "a": make_test_state(action="...", on_yes="target"),
                "x_err_only": make_test_state(action="...", on_error="target"),
                "target": make_test_state(action="...", on_yes="end"),
                "end": make_test_state(terminal=True),
            },
        )
        out_main = _render_neighborhood_diagram(fsm, "target", mode="main")
        out_full = _render_neighborhood_diagram(fsm, "target", mode="full")
        assert "x_err_only" not in out_main, out_main
        assert "a" in out_main
        assert "x_err_only" in out_full

    def test_prev_state_pred_gets_orange_border(self) -> None:
        """The pred named in prev_state renders with an ANSI 33 (orange) border."""
        import re

        from little_loops.cli import output as output_mod
        from little_loops.cli.loop import layout as layout_mod
        from little_loops.cli.loop.layout import _render_neighborhood_diagram

        # Initial is "start" so the preds (alpha/beta/gamma) render as bare
        # names rather than with the "→ " initial-state prefix.
        fsm = make_test_fsm(
            initial="start",
            states={
                "start": make_test_state(
                    action="...", on_yes="alpha", on_no="beta", on_error="gamma"
                ),
                "alpha": make_test_state(action="...", on_yes="target"),
                "beta": make_test_state(action="...", on_yes="target"),
                "gamma": make_test_state(action="...", on_yes="target"),
                "target": make_test_state(action="...", on_yes="end"),
                "end": make_test_state(terminal=True),
            },
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            out = _render_neighborhood_diagram(fsm, "target", prev_state="beta")

        orange = f"\x1b[{layout_mod._PREV_STATE_COLOR}m"
        ansi_re = re.compile(r"\x1b\[[0-9;]*m")
        raw_lines = out.split("\n")
        stripped = [ansi_re.sub("", ln) for ln in raw_lines]

        def label_rows(label: str) -> list[str]:
            # Box mid row looks like "│ <label>   │" once ANSI is stripped;
            # labels are space-padded to the widest pred so just look for the
            # label preceded by "│ " (the box's left border + 1 space).
            needle = f"│ {label} "
            return [raw_lines[i] for i, ln in enumerate(stripped) if needle in ln]

        b_rows = label_rows("beta")
        assert b_rows, f"no row containing pred 'beta'; output:\n{out}"
        assert all(orange in ln for ln in b_rows), (
            f"expected orange border ({orange!r}) on every 'beta' row; output:\n{out}"
        )
        for sibling in ("alpha", "gamma"):
            sib_rows = label_rows(sibling)
            assert sib_rows, f"no row containing pred {sibling!r}"
            assert not any(orange in ln for ln in sib_rows), (
                f"sibling pred {sibling!r} unexpectedly orange; output:\n{out}"
            )

    def test_prev_state_silently_skipped_when_not_in_preds(self) -> None:
        """prev_state naming a non-pred is silently dropped — no crash, no escape."""
        from little_loops.cli import output as output_mod
        from little_loops.cli.loop import layout as layout_mod
        from little_loops.cli.loop.layout import _render_neighborhood_diagram

        fsm = make_test_fsm(
            initial="a",
            states={
                "a": make_test_state(action="...", on_yes="target"),
                "b": make_test_state(action="...", on_yes="target"),
                "target": make_test_state(action="...", on_yes="end"),
                "end": make_test_state(terminal=True),
            },
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            out = _render_neighborhood_diagram(fsm, "target", prev_state="not_a_real_state")

        orange = f"\x1b[{layout_mod._PREV_STATE_COLOR}m"
        assert orange not in out, f"unexpected orange border; output:\n{out}"

    def test_highlighted_active_state_uses_bg_fill(self) -> None:
        """Active state box in neighborhood diagram has background fill on interior cells."""
        import re

        from little_loops.cli import output as output_mod
        from little_loops.cli.loop.layout import _render_neighborhood_diagram

        fsm = make_test_fsm(
            initial="a",
            states={
                "a": make_test_state(action="...", on_yes="target"),
                "target": make_test_state(action="...", on_yes="end"),
                "end": make_test_state(terminal=True),
            },
        )
        with patch.object(output_mod, "_USE_COLOR", True):
            out = _render_neighborhood_diagram(fsm, "target", highlight_color="36")

        # bg cyan fill (\033[46m) should appear in interior cells of the active box
        assert "\x1b[46m " in out, f"expected bg fill in neighborhood active box; output:\n{out}"
        # state name uses bright-white fg + bg + bold
        ansi_re = re.compile(r"\x1b\[[0-9;]*m")
        assert "\x1b[97;46;1m" in out, (
            f"expected bright-white-fg+bg+bold name code; output:\n{ansi_re.sub('', out)}"
        )


class MockExecutorWithEventBus:
    """Mock executor that emits events through a real EventBus (tests event_bus.register path)."""

    def __init__(self, events: list[dict[str, Any]]) -> None:
        from little_loops.events import EventBus

        self._events = events
        self.event_bus = EventBus()
        self.loops_dir = Path(".")

    def run(self) -> ExecutionResult:
        for event in self._events:
            self.event_bus.emit(event)
        return ExecutionResult(
            final_state="done",
            iterations=1,
            terminated_by="terminal",
            duration_ms=100,
            captured={},
        )


class TestFollowMode:
    """Tests for --follow streaming mode in run_foreground (ENH-1685)."""

    def _make_fsm(self) -> FSMLoop:
        return make_test_fsm()

    def _args(
        self, follow: bool = False, quiet: bool = False, verbose: bool = False
    ) -> argparse.Namespace:
        return argparse.Namespace(
            follow=follow,
            quiet=quiet,
            verbose=verbose,
            show_diagrams=None,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
        )

    def test_follow_true_emits_history_formatted_events(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--follow outputs _format_history_event lines to stdout as events fire."""
        events = [
            {
                "event": "state_enter",
                "state": "diagnose",
                "iteration": 1,
                "ts": "2026-01-01T00:00:00",
            },
        ]
        executor = MockExecutorWithEventBus(events)
        run_foreground(executor, self._make_fsm(), self._args(follow=True))
        captured = capsys.readouterr()
        assert "state_enter" in captured.out
        assert "diagnose" in captured.out

    def test_follow_false_does_not_emit_history_formatted_events(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Without --follow, _format_history_event lines are not written to stdout."""
        events = [
            {
                "event": "state_enter",
                "state": "diagnose",
                "iteration": 1,
                "ts": "2026-01-01T00:00:00",
            },
        ]
        executor = MockExecutorWithEventBus(events)
        run_foreground(executor, self._make_fsm(), self._args(follow=False))
        captured = capsys.readouterr()
        # Normal display_progress output does not use _format_history_event timestamp format
        assert "state_enter" not in captured.out

    def test_follow_quiet_shows_only_history_lines(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """--follow --quiet outputs history-formatted lines without display_progress output."""
        events = [
            {
                "event": "state_enter",
                "state": "propose",
                "iteration": 2,
                "ts": "2026-01-01T00:00:01",
            },
        ]
        executor = MockExecutorWithEventBus(events)
        run_foreground(executor, self._make_fsm(), self._args(follow=True, quiet=True))
        captured = capsys.readouterr()
        assert "state_enter" in captured.out
        assert "propose" in captured.out

    def test_follow_route_event_rendered(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--follow renders route events (from → to transitions)."""
        events = [
            {"event": "route", "from": "diagnose", "to": "propose", "ts": "2026-01-01T00:00:01"},
        ]
        executor = MockExecutorWithEventBus(events)
        run_foreground(executor, self._make_fsm(), self._args(follow=True))
        captured = capsys.readouterr()
        assert "route" in captured.out

    def test_follow_via_on_event_fallback(self, capsys: pytest.CaptureFixture[str]) -> None:
        """--follow wires callback via _on_event when executor has no event_bus."""
        events = [
            {
                "event": "state_enter",
                "state": "fallback_state",
                "iteration": 1,
                "ts": "2026-01-01T00:00:00",
            },
        ]
        executor = MockExecutor(events)
        run_foreground(executor, self._make_fsm(), self._args(follow=True, quiet=True))
        captured = capsys.readouterr()
        assert "state_enter" in captured.out
        assert "fallback_state" in captured.out


class TestRunForegroundCapture:
    """Tests for ENH-1703: run_foreground always-on log capture."""

    def _make_args(self, foreground_internal: bool = False) -> argparse.Namespace:
        return argparse.Namespace(
            quiet=False,
            verbose=False,
            follow=False,
            show_diagrams=None,
            diagram_edge_labels=None,
            diagram_state_detail=None,
            diagram_scope=None,
            clear=False,
            foreground_internal=foreground_internal,
        )

    def _make_fsm(self) -> FSMLoop:
        return make_test_fsm()

    def _make_executor(self) -> Any:
        class _Executor:
            def __init__(self) -> None:
                self._on_event: Any = None

            def run(self) -> ExecutionResult:
                return ExecutionResult(
                    final_state="done",
                    iterations=1,
                    terminated_by="terminal",
                    duration_ms=100,
                    captured={},
                )

        return _Executor()

    def test_log_file_written_when_instance_id_provided(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Log file is created at running_dir/{instance_id}.log for foreground runs."""
        running_dir = tmp_path / ".running"
        running_dir.mkdir()

        run_foreground(
            self._make_executor(),
            self._make_fsm(),
            self._make_args(),
            instance_id="my-loop-20260101T120000",
            running_dir=running_dir,
        )
        capsys.readouterr()  # consume captured output to keep test output clean

        log_file = running_dir / "my-loop-20260101T120000.log"
        assert log_file.exists(), "Log file should be created"
        assert log_file.stat().st_size > 0, "Log file should have content"

    def test_log_file_has_no_ansi_sequences(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Log file content is plain text — ANSI sequences stripped."""
        running_dir = tmp_path / ".running"
        running_dir.mkdir()
        ansi_re = __import__("re").compile(r"\x1b\[[0-9;]*[mABCDEFGHJKSTfhilmnprsu]")

        run_foreground(
            self._make_executor(),
            self._make_fsm(),
            self._make_args(),
            instance_id="my-loop-20260101T120000",
            running_dir=running_dir,
        )
        capsys.readouterr()  # consume captured output to keep test output clean

        log_content = (running_dir / "my-loop-20260101T120000.log").read_text()
        assert not ansi_re.search(log_content), "Log file must not contain ANSI escape sequences"

    def test_no_log_file_without_instance_id(self, tmp_path: Path) -> None:
        """No log file is created when instance_id is None (backward-compatible default)."""
        running_dir = tmp_path / ".running"
        running_dir.mkdir()

        with patch("builtins.print"):
            run_foreground(
                self._make_executor(),
                self._make_fsm(),
                self._make_args(),
                instance_id=None,
                running_dir=running_dir,
            )

        assert list(running_dir.glob("*.log")) == [], "No log file without instance_id"

    def test_no_tee_for_foreground_internal(self, tmp_path: Path) -> None:
        """Background-spawned foreground children (foreground_internal=True) skip tee to avoid double writes."""
        running_dir = tmp_path / ".running"
        running_dir.mkdir()

        with patch("builtins.print"):
            run_foreground(
                self._make_executor(),
                self._make_fsm(),
                self._make_args(foreground_internal=True),
                instance_id="my-loop-20260101T120000",
                running_dir=running_dir,
            )

        assert list(running_dir.glob("*.log")) == [], "No tee for foreground_internal children"

    def test_stdout_restored_after_run(self, tmp_path: Path) -> None:
        """sys.stdout is restored to original after run_foreground completes."""
        running_dir = tmp_path / ".running"
        running_dir.mkdir()
        orig_stdout = sys.stdout

        with patch("builtins.print"):
            run_foreground(
                self._make_executor(),
                self._make_fsm(),
                self._make_args(),
                instance_id="my-loop-20260101T120000",
                running_dir=running_dir,
            )

        assert sys.stdout is orig_stdout, "sys.stdout must be restored after tee teardown"

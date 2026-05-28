"""Tests for StateFeedRenderer class."""

import argparse

import pytest

from little_loops.cli.loop._helpers import StateFeedRenderer
from little_loops.fsm.schema import FSMLoop, StateConfig


def _make_test_fsm(name: str = "test-loop") -> FSMLoop:
    """Create a minimal FSMLoop for testing."""
    states = {
        "start": StateConfig(action="echo start", on_yes="done"),
        "done": StateConfig(terminal=True),
    }
    return FSMLoop(
        name=name,
        initial="start",
        states=states,
        max_iterations=50,
    )


def _make_args(
    quiet: bool = False,
    verbose: bool = False,
    show_diagrams: bool | str | None = None,
    clear: bool = False,
) -> argparse.Namespace:
    if show_diagrams is False:
        show_diagrams = None
    return argparse.Namespace(
        quiet=quiet,
        verbose=verbose,
        show_diagrams=show_diagrams,
        clear=clear,
        diagram_edge_labels=None,
        diagram_state_detail=None,
        diagram_scope=None,
        follow=False,
    )


class TestStateFeedRendererInit:
    """Tests for StateFeedRenderer instantiation."""

    def test_instantiate_with_defaults(self) -> None:
        """StateFeedRenderer can be instantiated with required params."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        assert renderer.fsm is fsm
        assert renderer.args is args
        assert renderer.quiet is False
        assert renderer.verbose is False

    def test_instantiate_quiet_mode(self) -> None:
        """StateFeedRenderer sets quiet flag from args."""
        fsm = _make_test_fsm()
        args = _make_args(quiet=True)
        renderer = StateFeedRenderer(fsm, args)
        assert renderer.quiet is True

    def test_instantiate_verbose_mode(self) -> None:
        """StateFeedRenderer sets verbose flag from args."""
        fsm = _make_test_fsm()
        args = _make_args(verbose=True)
        renderer = StateFeedRenderer(fsm, args)
        assert renderer.verbose is True


class TestStateFeedRendererHandleEvent:
    """Tests for StateFeedRenderer.handle_event output formatting."""

    def test_state_enter_prints_iteration_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """state_enter event prints iteration count and state name."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "state_enter", "state": "start", "iteration": 1, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "[1/50]" in captured.out
        assert "start" in captured.out

    def test_action_start_prints_preview(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """action_start event prints action preview."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "action_start", "action": "echo hello world", "is_prompt": False, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "echo hello world" in captured.out

    def test_action_start_prompt_shows_preview(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """action_start with is_prompt=True shows preview with diamond marker."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {
                "event": "action_start",
                "action": "Please analyze\nthis code\ncarefully",
                "is_prompt": True,
                "depth": 0,
            }
        )
        captured = capsys.readouterr()
        assert "Please analyze" in captured.out

    def test_action_output_prints_line(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """action_output event prints the output line."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "action_output", "line": "hello from action", "depth": 0}
        )
        captured = capsys.readouterr()
        assert "hello from action" in captured.out

    def test_action_complete_shows_duration(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """action_complete event prints duration."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "action_complete", "duration_ms": 1500, "exit_code": 0, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "1.5s" in captured.out

    def test_action_complete_exit_124_shown_as_timed_out(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Exit code 124 is displayed as 'timed out'."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "action_complete", "duration_ms": 120000, "exit_code": 124, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "timed out" in captured.out
        assert "exit: 124" not in captured.out

    def test_action_complete_nonzero_exit_shown(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-124 non-zero exit codes display 'exit: N'."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "action_complete", "duration_ms": 1000, "exit_code": 1, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "exit: 1" in captured.out

    def test_evaluate_yes_shows_checkmark(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Yes verdict shows checkmark symbol."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {
                "event": "evaluate",
                "verdict": "yes",
                "confidence": 0.95,
                "reason": "looks good",
                "depth": 0,
            }
        )
        captured = capsys.readouterr()
        assert "0.95" in captured.out

    def test_evaluate_no_shows_xmark(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """No verdict shows x-mark symbol."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "evaluate", "verdict": "no", "confidence": 0.2, "reason": "not ready", "depth": 0}
        )
        captured = capsys.readouterr()
        assert "0.20" in captured.out

    def test_evaluate_error_shows_raw_preview(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Error verdict shows raw_preview content."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {
                "event": "evaluate",
                "verdict": "error",
                "error": "Empty result field",
                "raw_preview": '{"is_error": false, "result": ""}',
                "depth": 0,
            }
        )
        captured = capsys.readouterr()
        assert "raw:" in captured.out
        assert '{"is_error": false' in captured.out

    def test_route_shows_transition(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Route event shows transition arrow to target state."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "route", "to": "done", "depth": 0}
        )
        captured = capsys.readouterr()
        assert "done" in captured.out

    def test_max_iterations_summary(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """max_iterations_summary event prints summary message."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {
                "event": "max_iterations_summary",
                "summary_state": "check_status",
                "iterations": 50,
                "depth": 0,
            }
        )
        captured = capsys.readouterr()
        assert "check_status" in captured.out
        assert "50" in captured.out

    def test_stall_detected_shows_message(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """stall_detected event prints stall info."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {
                "event": "stall_detected",
                "state": "start",
                "exit_code": 0,
                "verdict": "yes",
                "consecutive": 3,
                "action": "abort",
                "depth": 0,
            }
        )
        captured = capsys.readouterr()
        assert "stall_detected" in captured.out
        assert "start" in captured.out

    def test_quiet_mode_suppresses_output(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Quiet mode suppresses most event output."""
        fsm = _make_test_fsm()
        args = _make_args(quiet=True)
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "state_enter", "state": "start", "iteration": 1, "depth": 0}
        )
        captured = capsys.readouterr()
        assert captured.out == ""

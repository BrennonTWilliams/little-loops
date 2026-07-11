"""Tests for StateFeedRenderer class."""

import argparse
from pathlib import Path

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

    def test_state_enter_prints_iteration_line(self, capsys: pytest.CaptureFixture[str]) -> None:
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

    def test_action_start_prints_preview(self, capsys: pytest.CaptureFixture[str]) -> None:
        """action_start event prints action preview."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "action_start", "action": "echo hello world", "is_prompt": False, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "echo hello world" in captured.out

    def test_action_start_prompt_shows_preview(self, capsys: pytest.CaptureFixture[str]) -> None:
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

    def test_action_output_prints_line(self, capsys: pytest.CaptureFixture[str]) -> None:
        """action_output event prints the output line."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event({"event": "action_output", "line": "hello from action", "depth": 0})
        captured = capsys.readouterr()
        assert "hello from action" in captured.out

    def test_action_complete_shows_duration(self, capsys: pytest.CaptureFixture[str]) -> None:
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

    def test_action_complete_nonzero_exit_shown(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Non-124 non-zero exit codes display 'exit: N'."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "action_complete", "duration_ms": 1000, "exit_code": 1, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "exit: 1" in captured.out

    def test_action_complete_updates_model(self, capsys: pytest.CaptureFixture[str]) -> None:
        """action_complete with 'model' field updates self.model for future renders."""
        fsm = _make_test_fsm()
        args = _make_args(show_diagrams=True)
        renderer = StateFeedRenderer(fsm, args, model="sonnet")
        assert renderer.model == "sonnet"
        renderer.handle_event(
            {
                "event": "action_complete",
                "duration_ms": 500,
                "exit_code": 0,
                "depth": 0,
                "model": "claude-sonnet-4-6",
            }
        )
        assert renderer.model == "claude-sonnet-4-6"
        renderer.handle_event(
            {"event": "state_enter", "state": "start", "iteration": 1, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "claude-sonnet-4-6" in captured.out

    def test_evaluate_yes_shows_checkmark(self, capsys: pytest.CaptureFixture[str]) -> None:
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

    def test_evaluate_no_shows_xmark(self, capsys: pytest.CaptureFixture[str]) -> None:
        """No verdict shows x-mark symbol."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {
                "event": "evaluate",
                "verdict": "no",
                "confidence": 0.2,
                "reason": "not ready",
                "depth": 0,
            }
        )
        captured = capsys.readouterr()
        assert "0.20" in captured.out

    def test_evaluate_error_shows_raw_preview(self, capsys: pytest.CaptureFixture[str]) -> None:
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

    def test_route_shows_transition(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Route event shows transition arrow to target state."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event({"event": "route", "to": "done", "depth": 0})
        captured = capsys.readouterr()
        assert "done" in captured.out

    def test_max_steps_summary(self, capsys: pytest.CaptureFixture[str]) -> None:
        """max_steps_summary event prints summary message."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {
                "event": "max_steps_summary",
                "summary_state": "check_status",
                "iterations": 50,
                "depth": 0,
            }
        )
        captured = capsys.readouterr()
        assert "check_status" in captured.out
        assert "50" in captured.out

    def test_stall_detected_shows_message(self, capsys: pytest.CaptureFixture[str]) -> None:
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

    def test_quiet_mode_suppresses_output(self, capsys: pytest.CaptureFixture[str]) -> None:
        """Quiet mode suppresses most event output."""
        fsm = _make_test_fsm()
        args = _make_args(quiet=True)
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "state_enter", "state": "start", "iteration": 1, "depth": 0}
        )
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_non_pinned_handle_event_prints_artifact_lines(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-pinned handle_event prints artifact paths between header and diagram."""
        fsm = _make_test_fsm()
        fsm.context = {"output_dir": ".loops/output/"}
        args = _make_args(show_diagrams=True)
        loop_path = Path("loops/test-loop.yaml")
        renderer = StateFeedRenderer(fsm, args, loop_path=loop_path)
        renderer.handle_event(
            {"event": "state_enter", "state": "start", "iteration": 1, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "  loop:" in captured.out
        assert "loops/test-loop.yaml" in captured.out
        assert "  output_dir:" in captured.out
        assert ".loops/output/" in captured.out
        # Header comes before artifact lines
        header_pos = captured.out.find("== loop:")
        loop_pos = captured.out.find("  loop:")
        assert header_pos >= 0
        assert loop_pos >= 0
        assert header_pos < loop_pos

    def test_non_pinned_handle_event_prints_model_when_provided(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-pinned handle_event renders model line when model kwarg is set."""
        fsm = _make_test_fsm()
        args = _make_args(show_diagrams=True)
        renderer = StateFeedRenderer(fsm, args, model="claude-opus-4-7")
        renderer.handle_event(
            {"event": "state_enter", "state": "start", "iteration": 1, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "  model:" in captured.out
        assert "claude-opus-4-7" in captured.out

    def test_non_pinned_handle_event_omits_model_when_none(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Non-pinned handle_event does not render model line when model is None."""
        fsm = _make_test_fsm()
        args = _make_args(show_diagrams=True)
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {"event": "state_enter", "state": "start", "iteration": 1, "depth": 0}
        )
        captured = capsys.readouterr()
        assert "  model:" not in captured.out

    def test_baseline_complete_shows_per_arm_timing(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """baseline_complete event displays per-arm timing and token counts."""
        fsm = _make_test_fsm()
        args = _make_args()
        renderer = StateFeedRenderer(fsm, args)
        renderer.handle_event(
            {
                "event": "baseline_complete",
                "harness_duration_ms": 3200,
                "baseline_duration_ms": 1100,
                "harness_tokens": 15000,
                "baseline_tokens": 5000,
                "depth": 0,
            }
        )
        captured = capsys.readouterr()
        assert "baseline:" in captured.out
        assert "harness:" in captured.out
        assert "3.2s" in captured.out
        assert "1.1s" in captured.out
        assert "15000" in captured.out
        assert "5000" in captured.out


class TestArtifactLines:
    """Tests for _artifact_lines helper."""

    def test_extracts_path_like_context_values(self) -> None:
        """_artifact_lines extracts context values that look like filesystem paths."""
        from little_loops.cli.loop._helpers import _artifact_lines

        fsm = FSMLoop(
            name="test-loop",
            initial="start",
            states={"start": StateConfig(action="echo start")},
            max_iterations=10,
            context={
                "output_dir": ".loops/plans/",
                "plan_dir": "./output",
                "debug": "true",
                "threshold": "LOW",
                "template_ref": "${captured.run_dir.output}",
            },
        )
        loop_path = Path("/tmp/test-loop.yaml")
        result = _artifact_lines(fsm, loop_path)

        assert result[0] == ("loop", str(loop_path))
        keys = {k for k, v in result}
        assert "output_dir" in keys
        assert "plan_dir" in keys
        assert "debug" not in keys
        assert "threshold" not in keys
        assert "template_ref" not in keys

    def test_no_loop_path_omits_loop_entry(self) -> None:
        """_artifact_lines with loop_path=None excludes the 'loop' key."""
        from little_loops.cli.loop._helpers import _artifact_lines

        fsm = _make_test_fsm()
        result = _artifact_lines(fsm, None)
        keys = {k for k, v in result}
        assert "loop" not in keys

    def test_no_context_returns_only_loop_path(self) -> None:
        """_artifact_lines with empty context returns only the loop path entry."""
        from little_loops.cli.loop._helpers import _artifact_lines

        fsm = _make_test_fsm()
        loop_path = Path("loops/test.yaml")
        result = _artifact_lines(fsm, loop_path)
        assert result == [("loop", str(loop_path))]

    def test_root_paths_are_extracted(self) -> None:
        """_artifact_lines extracts absolute and home-dir paths."""
        from little_loops.cli.loop._helpers import _artifact_lines

        fsm = FSMLoop(
            name="test-loop",
            initial="start",
            states={"start": StateConfig(action="echo start")},
            max_iterations=10,
            context={
                "tmp_dir": "/tmp/scratch",
                "home_dir": "~/loop-output",
            },
        )
        result = _artifact_lines(fsm, None)
        keys = {k for k, v in result}
        assert "tmp_dir" in keys
        assert "home_dir" in keys

    def test_builtin_loop_shows_filename_only(self) -> None:
        """A built-in FSM loop path is displayed by filename only."""
        from little_loops.cli.loop._helpers import (
            _artifact_lines,
            get_builtin_loops_dir,
        )

        fsm = _make_test_fsm()
        loop_path = get_builtin_loops_dir() / "general-task.yaml"
        result = _artifact_lines(fsm, loop_path)
        assert result[0] == ("loop", "general-task.yaml")

    def test_project_loop_shows_cwd_relative_path(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A project-level loop under cwd is displayed relative to cwd."""
        from little_loops.cli.loop._helpers import _artifact_lines

        monkeypatch.chdir(tmp_path)
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()
        loop_path = loops_dir / "general-task.yaml"
        loop_path.write_text("")

        fsm = _make_test_fsm()
        result = _artifact_lines(fsm, loop_path)
        assert result[0] == ("loop", ".loops/general-task.yaml")

    def test_context_path_under_cwd_is_relativized(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An absolute context path under cwd is shown relative, keeping trailing slash."""
        from little_loops.cli.loop._helpers import _artifact_lines

        monkeypatch.chdir(tmp_path)
        run_dir = str(tmp_path / ".loops" / "runs" / "general-task-20260709T182714") + "/"

        fsm = FSMLoop(
            name="test-loop",
            initial="start",
            states={"start": StateConfig(action="echo start")},
            max_iterations=10,
            context={"run_dir": run_dir},
        )
        result = _artifact_lines(fsm, None)
        pairs = dict(result)
        assert pairs["run_dir"] == ".loops/runs/general-task-20260709T182714/"

    def test_context_path_outside_cwd_is_unchanged(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An absolute context path outside cwd is left unchanged."""
        from little_loops.cli.loop._helpers import _artifact_lines

        monkeypatch.chdir(tmp_path)
        fsm = FSMLoop(
            name="test-loop",
            initial="start",
            states={"start": StateConfig(action="echo start")},
            max_iterations=10,
            context={"tmp_dir": "/tmp/scratch"},
        )
        result = _artifact_lines(fsm, None)
        pairs = dict(result)
        assert pairs["tmp_dir"] == "/tmp/scratch"


class TestResolveInputValue:
    """Tests for _resolve_input_value (ENH-2596)."""

    def test_returns_value_from_input_key(self) -> None:
        from little_loops.cli.loop._helpers import _resolve_input_value

        fsm = _make_test_fsm()
        fsm.context["input"] = "some task string"
        assert _resolve_input_value(fsm, show_input=True) == "some task string"

    def test_returns_none_when_show_input_false(self) -> None:
        from little_loops.cli.loop._helpers import _resolve_input_value

        fsm = _make_test_fsm()
        fsm.context["input"] = "some task string"
        assert _resolve_input_value(fsm, show_input=False) is None

    def test_returns_none_when_absent(self) -> None:
        from little_loops.cli.loop._helpers import _resolve_input_value

        fsm = _make_test_fsm()
        assert _resolve_input_value(fsm, show_input=True) is None

    def test_returns_none_when_empty_string(self) -> None:
        from little_loops.cli.loop._helpers import _resolve_input_value

        fsm = _make_test_fsm()
        fsm.context["input"] = ""
        assert _resolve_input_value(fsm, show_input=True) is None

    def test_returns_none_for_dict_spread_case(self) -> None:
        """When --input's dict keys matched existing context, no scalar was stored."""
        from little_loops.cli.loop._helpers import _resolve_input_value

        fsm = _make_test_fsm()
        fsm.context["foo"] = "bar"
        assert _resolve_input_value(fsm, show_input=True) is None

    def test_custom_input_key(self) -> None:
        from little_loops.cli.loop._helpers import _resolve_input_value

        fsm = _make_test_fsm()
        fsm.input_key = "task"
        fsm.context["task"] = "custom key value"
        assert _resolve_input_value(fsm, show_input=True) == "custom key value"


class TestRenderArtifactHeaderLines:
    """Tests for _render_artifact_header_lines (ENH-2596)."""

    def test_input_packed_onto_loop_line(self) -> None:
        from little_loops.cli.loop._helpers import _render_artifact_header_lines

        fsm = _make_test_fsm()
        loop_path = Path("loops/test.yaml")
        lines = _render_artifact_header_lines(fsm, loop_path, None, "hello world", 200)
        assert len(lines) == 1
        assert "loop:" in lines[0]
        assert "input: " in lines[0]
        assert "hello world" in lines[0]

    def test_no_input_segment_when_absent(self) -> None:
        from little_loops.cli.loop._helpers import _render_artifact_header_lines

        fsm = _make_test_fsm()
        loop_path = Path("loops/test.yaml")
        lines = _render_artifact_header_lines(fsm, loop_path, None, None, 200)
        assert len(lines) == 1
        assert "input:" not in lines[0]

    def test_model_packed_onto_run_dir_line(self) -> None:
        from little_loops.cli.loop._helpers import _render_artifact_header_lines

        fsm = FSMLoop(
            name="test-loop",
            initial="start",
            states={"start": StateConfig(action="echo start")},
            max_iterations=10,
            context={"run_dir": ".loops/runs/test-loop/2026-07-11"},
        )
        lines = _render_artifact_header_lines(fsm, None, "claude-opus-4-8", None, 200)
        run_dir_line = next(ln for ln in lines if "run_dir:" in ln)
        assert "model: " in run_dir_line
        assert "claude-opus-4-8" in run_dir_line
        assert not any(ln.strip().startswith("model:") for ln in lines)

    def test_model_standalone_line_when_no_run_dir(self) -> None:
        """No run_dir context value → model: falls back to its own line."""
        from little_loops.cli.loop._helpers import _render_artifact_header_lines

        fsm = _make_test_fsm()
        lines = _render_artifact_header_lines(fsm, None, "claude-opus-4-8", None, 200)
        assert any(ln.strip().startswith("model:") for ln in lines)

    def test_long_input_truncated_to_width(self) -> None:
        from little_loops.cli.loop._helpers import _render_artifact_header_lines
        from little_loops.cli.output import strip_ansi

        fsm = _make_test_fsm()
        loop_path = Path("loops/test.yaml")
        long_input = "x" * 500
        lines = _render_artifact_header_lines(fsm, loop_path, None, long_input, 60)
        visible = strip_ansi(lines[0])
        assert len(visible) <= 60
        assert visible.endswith("…")

    def test_both_input_and_model_packed(self) -> None:
        from little_loops.cli.loop._helpers import _render_artifact_header_lines

        fsm = FSMLoop(
            name="test-loop",
            initial="start",
            states={"start": StateConfig(action="echo start")},
            max_iterations=10,
            context={"run_dir": ".loops/runs/test-loop/2026-07-11"},
        )
        loop_path = Path("loops/test.yaml")
        lines = _render_artifact_header_lines(fsm, loop_path, "claude-opus-4-8", "my input", 200)
        loop_line = next(ln for ln in lines if ln.strip().startswith("loop:"))
        run_dir_line = next(ln for ln in lines if "run_dir:" in ln)
        assert "input: " in loop_line and "my input" in loop_line
        assert "model: " in run_dir_line and "claude-opus-4-8" in run_dir_line

"""Tests for FEAT-3033: idle-timeout detection plumbed into the FSM action runner.

Covers:
- Schema round-trip and validation for idle_timeout / default_idle_timeout
- Prompt-path pass-through: idle_timeout forwarded to run_claude_command,
  exc.output == "idle_timeout" mapped to timeout_kind, duration_ms elapsed
- Shell/mcp selector-loop idle tracking (runners.py, executor._run_subprocess)
- BUG-3034 semantics: timeout=0/negative means "no deadline", never
  "already expired"
- ${prev.timeout_kind} interpolation and end-to-end routing via a
  shell_exit-style classifier state
- Checkpoint restore tolerance for a pre-change prev_result lacking
  timeout_kind
- Precedence: state.idle_timeout overrides fsm.default_idle_timeout
- Kwarg-gating: an ActionRunner without idle_timeout support still runs
  when idle is disabled
"""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

from little_loops.fsm.executor import ActionResult, DefaultActionRunner, FSMExecutor
from little_loops.fsm.persistence import LoopState
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.fsm.validation._base import KNOWN_TOP_LEVEL_KEYS
from tests.test_fsm_executor import MockActionRunner
from tests.test_fsm_runners import _make_ready_selector, _make_selector_mock_process, _MockFileObj


class TestSchemaRoundTrip:
    """AC-1: idle_timeout / default_idle_timeout round-trip through schema."""

    def test_state_idle_timeout_round_trips(self) -> None:
        state = StateConfig(action="cmd", idle_timeout=900)
        data = state.to_dict()
        assert data["idle_timeout"] == 900
        restored = StateConfig.from_dict(data, "s")
        assert restored.idle_timeout == 900

    def test_state_idle_timeout_omitted_when_none(self) -> None:
        state = StateConfig(action="cmd")
        assert "idle_timeout" not in state.to_dict()
        restored = StateConfig.from_dict({"action": "cmd"}, "s")
        assert restored.idle_timeout is None

    def test_fsm_default_idle_timeout_round_trips(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            default_idle_timeout=300,
        )
        data = fsm.to_dict()
        assert data["default_idle_timeout"] == 300
        restored = FSMLoop.from_dict(data)
        assert restored.default_idle_timeout == 300

    def test_default_idle_timeout_is_known_top_level_key(self) -> None:
        assert "default_idle_timeout" in KNOWN_TOP_LEVEL_KEYS


class TestPromptPathTimeoutKind:
    """AC-3/AC-5: prompt path maps the idle_timeout sentinel to timeout_kind."""

    def test_idle_sentinel_maps_to_idle_timeout_kind(self) -> None:
        runner = DefaultActionRunner()
        with patch(
            "little_loops.fsm.runners.run_claude_command",
            side_effect=subprocess.TimeoutExpired("cmd", 60, output="idle_timeout"),
        ):
            result = runner.run("/ll:slow-skill", 60, True, idle_timeout=15)

        assert result.exit_code == 124
        assert result.timeout_kind == "idle"
        assert "idle" in result.stderr.lower()

    def test_bare_timeout_maps_to_wall_timeout_kind(self) -> None:
        runner = DefaultActionRunner()
        with patch(
            "little_loops.fsm.runners.run_claude_command",
            side_effect=subprocess.TimeoutExpired("cmd", 60),
        ):
            result = runner.run("/ll:slow-skill", 60, True)

        assert result.exit_code == 124
        assert result.timeout_kind == "wall"

    def test_idle_timeout_forwarded_to_run_claude_command(self) -> None:
        runner = DefaultActionRunner()
        received: dict = {}

        def fake_run(**kwargs: object) -> MagicMock:
            received.update(kwargs)
            completed = MagicMock()
            completed.stdout = ""
            completed.stderr = ""
            completed.returncode = 0
            return completed

        with patch("little_loops.fsm.runners.run_claude_command", side_effect=fake_run):
            runner.run("/ll:fast-skill", 60, True, idle_timeout=42)

        assert received["idle_timeout"] == 42

    def test_duration_ms_reflects_elapsed_not_budget(self) -> None:
        """AC-7: a timeout firing quickly must not report the full budget."""
        runner = DefaultActionRunner()
        with patch(
            "little_loops.fsm.runners.run_claude_command",
            side_effect=subprocess.TimeoutExpired("cmd", 3600),
        ):
            result = runner.run("/ll:slow-skill", 3600, True)

        assert result.duration_ms < 3600 * 1000


class TestShellSelectorLoopIdle:
    """AC-4/AC-5/AC-10: shell selector-loop idle tracking in runners.py."""

    def test_idle_zero_disables_idle_detection(self) -> None:
        """AC-2: idle_timeout=0 reproduces today's wall-clock-only behavior."""
        proc = _make_selector_mock_process()
        sel = MagicMock()
        sel.get_map.return_value = {"k": "v"}
        sel.select.return_value = []
        sel.close.return_value = None

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.fsm.runners._kill_process_group") as mock_killpg,
        ):
            result = DefaultActionRunner().run("sleep 100", 0.05, False, idle_timeout=0)

        assert result.exit_code == 124
        assert result.timeout_kind == "wall"
        mock_killpg.assert_called_once_with(proc)

    def test_silence_past_idle_timeout_kills_with_idle_kind(self) -> None:
        """A process producing no output for longer than idle_timeout is killed."""
        proc = _make_selector_mock_process()
        fake_now = [1000.0]

        def _time() -> float:
            return fake_now[0]

        def _select(timeout: float | None = None) -> list:
            del timeout
            fake_now[0] += 3.0  # each poll advances the clock by 3s
            return []

        sel = MagicMock()
        sel.get_map.return_value = {"k": "v"}
        sel.select.side_effect = _select
        sel.close.return_value = None

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.fsm.runners._kill_process_group") as mock_killpg,
            patch("little_loops.fsm.runners.time.time", side_effect=_time),
        ):
            # Wall-clock budget (1000s) is far larger than idle_timeout (5s)
            # so only the idle sensor can fire here.
            result = DefaultActionRunner().run("hang forever", 1000, False, idle_timeout=5)

        assert result.exit_code == 124
        assert result.timeout_kind == "idle"
        assert "idle" in result.stderr.lower()
        mock_killpg.assert_called_once_with(proc)

    def test_steady_output_past_idle_timeout_not_killed(self) -> None:
        """AC-4: output arriving faster than idle_timeout is never killed, however long it runs."""
        proc = _make_selector_mock_process()
        proc.stdout = _MockFileObj(["line1\n", "line2\n", "line3\n"])
        proc.stderr = _MockFileObj([])
        fake_now = [1000.0]

        def _time() -> float:
            return fake_now[0]

        ready_key = MagicMock()
        ready_key.fileobj = proc.stdout
        ready_key.data = "stdout"

        calls = {"n": 0}

        def _select(timeout: float | None = None) -> list:
            del timeout
            fake_now[0] += 4.0  # less than idle_timeout=5 each poll
            calls["n"] += 1
            return [(ready_key, 1)]

        def _get_map() -> dict:
            # 3 lines then EOF — stop returning ready pipes once exhausted.
            return {} if calls["n"] > 3 else {"stdout": "data"}

        sel = MagicMock()
        sel.get_map.side_effect = _get_map
        sel.select.side_effect = _select
        sel.close.return_value = None

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.fsm.runners._kill_process_group") as mock_killpg,
            patch("little_loops.fsm.runners.time.time", side_effect=_time),
        ):
            result = DefaultActionRunner().run("stream", 1000, False, idle_timeout=5)

        assert result.exit_code == proc.returncode
        assert result.timeout_kind is None
        mock_killpg.assert_not_called()

    def test_partial_line_liveness_boundary_documented(self) -> None:
        """Known boundary (Accept-it option, see runners.py comment): a read
        (even of an unterminated line, once readline() eventually returns
        one) resets the idle clock; genuine silence past idle_timeout still
        kills. This pins current, documented behavior — a child that writes
        a partial line then truly wedges before a newline is the one case
        this loop cannot detect (readline() blocks past both sensors), which
        is exactly the boundary the "Accept it" option documents.
        """
        proc = _make_selector_mock_process()
        fake_now = [1000.0]

        def _time() -> float:
            return fake_now[0]

        stdout_key = MagicMock()
        stdout_key.fileobj = MagicMock()
        stdout_key.data = "stdout"
        stdout_key.fileobj.readline.return_value = "partial-no-newline"

        sel = MagicMock()
        sel.get_map.return_value = {"stdout": "data"}
        sel.close.return_value = None
        # One ready read (resets last_output_at), then silence forever —
        # advancing 6s per empty poll so the idle sensor (5s) fires on the
        # first post-read check.
        select_calls = {"n": 0}

        def _select(timeout: float | None = None) -> list:
            del timeout
            select_calls["n"] += 1
            if select_calls["n"] == 1:
                return [(stdout_key, 1)]
            fake_now[0] += 6.0
            return []

        sel.select.side_effect = _select

        with (
            patch("little_loops.fsm.runners.subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.runners.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.fsm.runners._kill_process_group"),
            patch("little_loops.fsm.runners.time.time", side_effect=_time),
        ):
            result = DefaultActionRunner().run(
                "partial-line-then-silent", 1000, False, idle_timeout=5
            )

        assert result.exit_code == 124
        assert result.timeout_kind == "idle"


class TestMcpSelectorLoopIdle:
    """AC-10/AC-12: executor._run_subprocess idle tracking (mcp path)."""

    def _make_executor(self) -> FSMExecutor:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )
        return FSMExecutor(fsm, action_runner=MockActionRunner())

    def test_mcp_idle_kill_carries_idle_kind(self) -> None:
        executor = self._make_executor()
        proc = MagicMock()
        proc.stdout = _MockFileObj([])
        proc.stderr = _MockFileObj([])
        proc.returncode = -9
        proc.pid = 1
        proc.wait.return_value = None
        fake_now = [1000.0]

        def _time() -> float:
            return fake_now[0]

        def _select(timeout: float | None = None) -> list:
            del timeout
            fake_now[0] += 3.0
            return []

        sel = MagicMock()
        sel.get_map.return_value = {"k": "v"}
        sel.select.side_effect = _select
        sel.close.return_value = None

        with (
            patch("subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.executor.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.fsm.executor._kill_process_group"),
            patch("little_loops.fsm.executor.time.time", side_effect=_time),
        ):
            result = executor._run_subprocess(["mcp-call"], timeout=1000, idle_timeout=5)

        assert result.exit_code == 124
        assert result.timeout_kind == "idle"

    def test_mcp_zero_or_negative_timeout_means_no_deadline(self) -> None:
        """AC-13 / BUG-3034: 0 or negative wall-clock budget never means
        'already expired' for the mcp selector loop.
        """
        executor = self._make_executor()
        proc = MagicMock()
        proc.stdout = _MockFileObj(["ok\n"])
        proc.stderr = _MockFileObj([])
        proc.returncode = 0
        proc.pid = 1
        proc.wait.return_value = None
        sel = _make_ready_selector({})

        with (
            patch("subprocess.Popen", return_value=proc),
            patch("little_loops.fsm.executor.selectors.DefaultSelector", return_value=sel),
        ):
            result = executor._run_subprocess(["mcp-call"], timeout=0)

        # Ran to completion (EOF) rather than being instantly killed.
        assert result.exit_code == 0
        assert result.timeout_kind is None

    def test_mcp_idle_kill_still_produces_timeout_verdict(self) -> None:
        """AC-12: mcp_result evaluator keeps the 'timeout' verdict for both
        wall-clock and idle kills; timeout_kind is the only discriminator.
        """
        from little_loops.fsm.evaluators import evaluate_mcp_result

        idle_result = evaluate_mcp_result("", 124)
        assert idle_result.verdict == "timeout"


class TestBaselineArmIdle:
    """AC-8: _run_baseline_arm resolves idle the same way as the harness arm."""

    def test_baseline_arm_forwards_idle_timeout(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            default_idle_timeout=20,
        )
        executor = FSMExecutor(fsm, action_runner=MockActionRunner())
        state = StateConfig(action="/ll:baseline", idle_timeout=7)
        received: dict = {}

        def fake_run(**kwargs: object) -> MagicMock:
            received.update(kwargs)
            completed = MagicMock()
            completed.stdout = ""
            completed.stderr = ""
            completed.returncode = 0
            return completed

        with patch("little_loops.fsm.executor.run_claude_command", side_effect=fake_run):
            executor._run_baseline_arm("/ll:baseline", state)

        assert received["idle_timeout"] == 7  # state override wins over fsm default (20)

    def test_baseline_arm_timeout_duration_ms_elapsed(self) -> None:
        fsm = FSMLoop(name="test", initial="s", states={"s": StateConfig(terminal=True)})
        executor = FSMExecutor(fsm, action_runner=MockActionRunner())
        state = StateConfig(action="/ll:baseline", timeout=3600)

        with patch(
            "little_loops.fsm.executor.run_claude_command",
            side_effect=subprocess.TimeoutExpired("cmd", 3600),
        ):
            result = executor._run_baseline_arm("/ll:baseline", state)

        assert result.exit_code == 124
        assert result.duration_ms < 3600 * 1000
        assert result.timeout_kind == "wall"


class TestIdleTimeoutPrecedence:
    """AC-2: state.idle_timeout overrides fsm.default_idle_timeout."""

    def test_state_idle_timeout_overrides_fsm_default(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="/ll:act", idle_timeout=7, next="done"),
                "done": StateConfig(terminal=True),
            },
            default_idle_timeout=99,
        )
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert mock_runner.idle_timeouts[0] == 7

    def test_fsm_default_used_when_state_unset(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="/ll:act", next="done"),
                "done": StateConfig(terminal=True),
            },
            default_idle_timeout=99,
        )
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert mock_runner.idle_timeouts[0] == 99

    def test_idle_disabled_omits_kwarg_for_old_runners(self) -> None:
        """AC-9: kwarg-gating — a runner without idle_timeout support still
        runs when idle resolves to 0 (disabled), since the kwarg is omitted.
        """

        class LegacyRunner:
            """Predates FEAT-3033 — no idle_timeout parameter."""

            def __init__(self) -> None:
                self.calls: list[str] = []

            def run(
                self,
                action: str,
                timeout: int,
                is_slash_command: bool,
                on_output_line=None,
                agent=None,
                tools=None,
                on_usage=None,
                on_usage_detailed=None,
                model=None,
                working_dir=None,
                automation_profile=None,
                **kwargs,
            ) -> ActionResult:
                self.calls.append(action)
                return ActionResult(output="", stderr="", exit_code=0, duration_ms=1)

        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="/ll:act", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        legacy = LegacyRunner()
        executor = FSMExecutor(fsm, action_runner=legacy)
        result = executor.run()

        assert legacy.calls == ["/ll:act"]
        assert result.terminated_by == "terminal"


class TestEndToEndTimeoutKindRouting:
    """AC-6: ${prev.timeout_kind} interpolates and routes via a
    shell_exit-style classifier state — the Use Case's differentiated-recovery
    idiom, not just an interpolation unit test.
    """

    def _build_fsm(self) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="do-work", on_error="classify"),
                "classify": StateConfig(
                    action='test "${prev.timeout_kind:default=}" = "idle"',
                    on_yes="escalate_wedged",
                    on_no="retry_implement",
                ),
                "escalate_wedged": StateConfig(terminal=True),
                "retry_implement": StateConfig(terminal=True),
            },
        )

    def test_idle_kill_routes_to_escalate(self) -> None:
        fsm = self._build_fsm()
        mock_runner = MockActionRunner()
        mock_runner.set_result("do-work", exit_code=124, timeout_kind="idle")
        mock_runner.set_result('test "idle" = "idle"', exit_code=0)
        mock_runner.set_result('test "wall" = "idle"', exit_code=1)

        result = FSMExecutor(fsm, action_runner=mock_runner).run()

        assert result.final_state == "escalate_wedged"

    def test_wall_clock_kill_routes_to_retry(self) -> None:
        fsm = self._build_fsm()
        mock_runner = MockActionRunner()
        mock_runner.set_result("do-work", exit_code=124, timeout_kind="wall")
        mock_runner.set_result('test "idle" = "idle"', exit_code=0)
        mock_runner.set_result('test "wall" = "idle"', exit_code=1)

        result = FSMExecutor(fsm, action_runner=mock_runner).run()

        assert result.final_state == "retry_implement"

    def test_exit_124_still_routes_error_regardless_of_timeout_kind(self) -> None:
        """BUG-1640/BUG-1815 routing to verdict 'error' is unperturbed by
        the new field when an explicit evaluate: gate is configured.
        """
        from little_loops.fsm.evaluators import evaluate
        from little_loops.fsm.schema import EvaluateConfig

        result = evaluate(
            config=EvaluateConfig(type="llm_structured"),
            output="",
            exit_code=124,
            context=None,
            model=None,
        )
        assert result.verdict == "error"


class TestCheckpointRestoreTolerance:
    """AC-6: a checkpoint written before this change restores without error."""

    def test_prev_result_without_timeout_kind_restores(self) -> None:
        data = {
            "loop_name": "test",
            "current_state": "next_state",
            "iteration": 1,
            "captured": {},
            "prev_result": {"output": "x", "exit_code": 0, "state": "prior"},
            "last_result": None,
            "started_at": "2026-01-01T00:00:00Z",
            "status": "running",
        }
        state = LoopState.from_dict(data)
        assert state.prev_result is not None
        assert "timeout_kind" not in state.prev_result

    def test_prev_default_interpolation_resolves_empty_for_legacy_checkpoint(self) -> None:
        from little_loops.fsm.interpolation import InterpolationContext, interpolate

        ctx = InterpolationContext(prev={"output": "x", "exit_code": 0, "state": "prior"})
        assert interpolate("${prev.timeout_kind:default=}", ctx) == ""

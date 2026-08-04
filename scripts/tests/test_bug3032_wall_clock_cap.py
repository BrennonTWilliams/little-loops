"""Tests for BUG-3032: prompt states opted into idle detection lose the
undeclared 3600s wall-clock fallback; every other path keeps it.

Covers:
- Opt-in ON: prompt state with idle_timeout (state- or loop-level) and no
  explicit timeout receives 0 (uncapped), not 3600.
- Opt-in OFF: same state without any idle declaration still receives 3600.
- Shell non-leak: a shell state in a loop with default_idle_timeout still
  receives 3600 — the action_mode == "prompt" gate.
- MCP non-leak: an MCP state with neither set still receives 30 (unchanged).
- Contributed non-leak: a contributed-action state in a loop declaring
  default_idle_timeout still receives 3600 (line untouched).
- Precedence: state.timeout / fsm.default_timeout still win over the
  relaxation even when idle is declared.
- _run_baseline_arm mirrors the same idle-gated relaxation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from little_loops.fsm.executor import ActionResult, FSMExecutor
from little_loops.fsm.schema import FSMLoop, StateConfig
from tests.test_fsm_executor import MockActionRunner


class TestPromptWallClockRelaxation:
    """Opt-in ON: idle declared -> no wall-clock cap for prompt states."""

    def test_state_idle_timeout_uncaps_prompt_state(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="/ll:act", idle_timeout=60, next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert mock_runner.timeouts[0] == 0

    def test_fsm_default_idle_timeout_uncaps_prompt_state(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="/ll:act", next="done"),
                "done": StateConfig(terminal=True),
            },
            default_idle_timeout=30,
        )
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert mock_runner.timeouts[0] == 0

    def test_opt_in_off_keeps_3600_fallback(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="/ll:act", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert mock_runner.timeouts[0] == 3600

    def test_state_timeout_still_wins_over_relaxation(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="/ll:act", idle_timeout=60, timeout=900, next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert mock_runner.timeouts[0] == 900

    def test_fsm_default_timeout_still_wins_over_relaxation(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="/ll:act", idle_timeout=60, next="done"),
                "done": StateConfig(terminal=True),
            },
            default_timeout=1200,
        )
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert mock_runner.timeouts[0] == 1200


class TestActionModeNonLeak:
    """The relaxation must never leak into shell/mcp/contributed states."""

    def test_shell_state_keeps_3600_despite_loop_idle_default(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="echo hi", action_type="shell", next="done"),
                "done": StateConfig(terminal=True),
            },
            default_idle_timeout=30,
        )
        mock_runner = MockActionRunner()
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        executor.run()

        assert mock_runner.timeouts[0] == 3600

    def test_mcp_state_keeps_30_regardless_of_idle(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="some_tool", action_type="mcp_tool", next="done"),
                "done": StateConfig(terminal=True),
            },
            default_idle_timeout=30,
        )
        executor = FSMExecutor(fsm)
        with patch.object(executor, "_run_subprocess") as mock_subprocess:
            mock_subprocess.return_value = ActionResult(
                output="", stderr="", exit_code=0, duration_ms=1
            )
            executor.run()

        assert mock_subprocess.call_args.kwargs["timeout"] == 30

    def test_contributed_state_keeps_3600_despite_loop_idle_default(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="do_thing", action_type="contrib_action", next="done"),
                "done": StateConfig(terminal=True),
            },
            default_idle_timeout=30,
        )
        contrib = MockActionRunner()
        executor = FSMExecutor(fsm)
        executor._contributed_actions["contrib_action"] = contrib
        executor.run()

        assert contrib.timeouts[0] == 3600


class TestBaselineArmWallClockRelaxation:
    """_run_baseline_arm mirrors the same idle-gated relaxation."""

    def test_baseline_arm_idle_declared_uncaps_timeout(self) -> None:
        fsm = FSMLoop(name="test", initial="act", states={"act": StateConfig(terminal=True)})
        executor = FSMExecutor(fsm)
        state = StateConfig(action="/ll:skill", idle_timeout=45, terminal=True)

        received: dict = {}

        def fake_run(**kwargs: object) -> MagicMock:
            received.update(kwargs)
            completed = MagicMock()
            completed.stdout = ""
            completed.stderr = ""
            completed.returncode = 0
            return completed

        with patch("little_loops.fsm.executor.run_claude_command", side_effect=fake_run):
            executor._run_baseline_arm("/ll:skill", state)

        assert received["timeout"] == 0

    def test_baseline_arm_no_idle_keeps_3600(self) -> None:
        fsm = FSMLoop(name="test", initial="act", states={"act": StateConfig(terminal=True)})
        executor = FSMExecutor(fsm)
        state = StateConfig(action="/ll:skill", terminal=True)

        received: dict = {}

        def fake_run(**kwargs: object) -> MagicMock:
            received.update(kwargs)
            completed = MagicMock()
            completed.stdout = ""
            completed.stderr = ""
            completed.returncode = 0
            return completed

        with patch("little_loops.fsm.executor.run_claude_command", side_effect=fake_run):
            executor._run_baseline_arm("/ll:skill", state)

        assert received["timeout"] == 3600

    def test_baseline_arm_explicit_timeout_wins_over_relaxation(self) -> None:
        fsm = FSMLoop(name="test", initial="act", states={"act": StateConfig(terminal=True)})
        executor = FSMExecutor(fsm)
        state = StateConfig(action="/ll:skill", idle_timeout=45, timeout=500, terminal=True)

        received: dict = {}

        def fake_run(**kwargs: object) -> MagicMock:
            received.update(kwargs)
            completed = MagicMock()
            completed.stdout = ""
            completed.stderr = ""
            completed.returncode = 0
            return completed

        with patch("little_loops.fsm.executor.run_claude_command", side_effect=fake_run):
            executor._run_baseline_arm("/ll:skill", state)

        assert received["timeout"] == 500


class TestEvaluatorReachedOnLongPromptRun:
    """A long-running, idle-opted-in prompt state is no longer 124-killed at
    3600s; its (successful, non-timeout) output reaches the evaluator."""

    def test_uncapped_prompt_state_result_not_short_circuited(self) -> None:
        fsm = FSMLoop(
            name="test",
            initial="act",
            states={
                "act": StateConfig(action="/ll:act", idle_timeout=60, next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        mock_runner = MockActionRunner()
        mock_runner.always_return(output="finished after 90 minutes", exit_code=0)
        executor = FSMExecutor(fsm, action_runner=mock_runner)
        result = executor.run()

        assert mock_runner.timeouts[0] == 0
        assert result.terminated_by == "terminal"

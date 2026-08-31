"""Tests for little_loops.runner_spec (ENH-2668).

Covers:
- :class:`ActionSpec` is a frozen value object (establishes the same
  convention as :class:`~little_loops.host_runner.HostInvocation`).
- ``RunnerResult`` remains importable from its pre-extraction location
  (``little_loops.cli.harness``) via re-export.
- Dispatch-table completeness: all five ll-harness runner kinds plus
  ``RunnerType.LOOP`` exist on the enum.
- ``run_action()`` produces byte-for-byte identical ``RunnerResult`` shapes
  to the pre-extraction per-CLI implementations, for each dispatched runner
  type (skill/cmd/mcp/prompt).
"""

from __future__ import annotations

import dataclasses
import subprocess
import sys
from unittest.mock import MagicMock, patch

import pytest

from little_loops.host_runner import AutomationContext, HostInvocation
from little_loops.runner_spec import ActionSpec, RunnerResult, RunnerType, run_action


def _make_completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class FakeRunner:
    def build_streaming(self, *, prompt: str, **_: object) -> HostInvocation:
        return HostInvocation(binary="claude", args=["-p", prompt])

    def build_blocking_json(self, *, prompt: str, model: str | None = None) -> HostInvocation:
        return HostInvocation(binary="claude", args=["-p", prompt])


class CapturingRunner:
    """A FakeRunner whose build_streaming() records the kwargs it received.

    ENH-3097 AC 13: the plain ``FakeRunner`` above absorbs automation= into
    ``**_: object`` without a signature change, so it keeps existing tests
    green — but it discards the value, making it unusable for asserting what
    the resolved automation context carries. This variant captures it.
    """

    def __init__(self) -> None:
        self.build_streaming_calls: list[dict] = []

    def build_streaming(self, *, prompt: str, **kwargs: object) -> HostInvocation:
        self.build_streaming_calls.append(kwargs)
        return HostInvocation(binary="claude", args=["-p", prompt])


class TestActionSpecFrozen:
    def test_action_spec_is_frozen(self) -> None:
        """Mutating an ActionSpec must raise FrozenInstanceError (host_runner convention)."""
        spec = ActionSpec(name="x", runner=RunnerType.CMD, target="echo hi")
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.target = "echo bye"  # type: ignore[misc]

    def test_timeout_none_is_constructible(self) -> None:
        """BUG-2928: timeout widened from int to int | None to admit "no outer bound"."""
        spec = ActionSpec(name="x", runner=RunnerType.LOOP, target="loops/x.yaml", timeout=None)
        assert spec.timeout is None


class TestDefaultTimeoutFor:
    """BUG-2928: per-runner default subprocess timeout resolved in cli/queue.py."""

    def test_loop_default_is_none(self) -> None:
        from little_loops.cli.queue import _default_timeout_for

        assert _default_timeout_for(RunnerType.LOOP) is None

    @pytest.mark.parametrize(
        "runner", [RunnerType.SKILL, RunnerType.CMD, RunnerType.MCP, RunnerType.PROMPT]
    )
    def test_non_loop_defaults_are_concrete_ints(self, runner: RunnerType) -> None:
        """CMD/MCP dispatch handlers do raw deadline arithmetic and raise TypeError on None."""
        from little_loops.cli.queue import _default_timeout_for

        result = _default_timeout_for(runner)
        assert result == 120
        assert result is not None


class TestRunnerResultReexport:
    def test_runner_result_importable_from_harness(self) -> None:
        """RunnerResult must stay importable from its pre-extraction location."""
        from little_loops.cli.harness import RunnerResult as HarnessRunnerResult

        assert HarnessRunnerResult is RunnerResult


class TestRunnerTypeCompleteness:
    def test_all_harness_runner_kinds_present(self) -> None:
        names = {member.value for member in RunnerType}
        assert {"skill", "cmd", "mcp", "prompt", "dsl", "loop"} <= names

    def test_loop_not_in_dispatch_table(self) -> None:
        """RunnerType.LOOP is intentionally excluded from run_action()'s dispatch."""
        spec = ActionSpec(name="x", runner=RunnerType.LOOP, target="loops/x.yaml")
        with pytest.raises(ValueError, match="LOOP"):
            run_action(spec)


class TestRunActionDispatch:
    def test_skill_dispatch_matches_legacy_shape(self) -> None:
        spec = ActionSpec(
            name="check-code",
            runner=RunnerType.SKILL,
            target="check-code",
            args={"runner_args": []},
            timeout=120,
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="ok")),
        ):
            result = run_action(spec)

        assert result == RunnerResult(stdout="ok", stderr="", exit_code=0)

    def test_skill_dispatch_timeout(self) -> None:
        spec = ActionSpec(name="x", runner=RunnerType.SKILL, target="x", timeout=1)
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)),
        ):
            result = run_action(spec)

        assert result.timed_out is True
        assert result.exit_code == 2

    def test_prompt_dispatch_matches_legacy_shape(self) -> None:
        spec = ActionSpec(
            name="p", runner=RunnerType.PROMPT, target="What is 2+2?", args={"model": None}
        )
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="4")),
        ):
            result = run_action(spec)

        assert result == RunnerResult(stdout="4", stderr="", exit_code=0)

    def test_prompt_dispatch_merges_invocation_env(self) -> None:
        """ENH-3184 AC4: _run_prompt() previously dropped invocation.env
        entirely; it must now merge it via project_child_env(), matching
        _run_skill()'s existing behaviour."""
        spec = ActionSpec(
            name="p", runner=RunnerType.PROMPT, target="What is 2+2?", args={"model": None}
        )

        class EnvRunner:
            def build_blocking_json(self, *, prompt: str, model: str | None = None):
                return HostInvocation(binary="claude", args=["-p", prompt], env={"FOO": "bar"})

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=EnvRunner()),
            patch(
                "subprocess.run", return_value=_make_completed(returncode=0, stdout="4")
            ) as mock_run,
        ):
            run_action(spec)

        assert mock_run.call_args.kwargs["env"]["FOO"] == "bar"

    def test_mcp_dispatch_matches_legacy_shape(self) -> None:
        spec = ActionSpec(
            name="mcp",
            runner=RunnerType.MCP,
            target="srv:tool",
            args={"mcp_params": {"a": 1}},
        )
        with patch(
            "little_loops.runner_spec.call_mcp_tool", return_value=({"ok": True}, 0)
        ) as mock_call:
            result = run_action(spec)

        mock_call.assert_called_once_with("srv", "tool", {"a": 1}, timeout=120)
        assert result.exit_code == 0
        assert result.stdout == '{"ok": true}'

    def test_cmd_dispatch_matches_legacy_shape(self) -> None:
        spec = ActionSpec(name="echo hi", runner=RunnerType.CMD, target="echo hi", timeout=5)
        result = run_action(spec)
        assert result.exit_code == 0
        assert result.stdout == "hi\n"

    def test_cmd_dispatch_sets_ll_python_env(self) -> None:
        """ENH-3365: _run_cmd()'s bash -c spawn must expose
        LL_PYTHON=sys.executable so a heredoc invoking
        $${LL_PYTHON:-python3} always resolves to the exact interpreter
        running the loop, not whatever `python3` is first on PATH.
        """
        spec = ActionSpec(
            name="print ll_python", runner=RunnerType.CMD, target="echo $LL_PYTHON", timeout=5
        )
        result = run_action(spec)
        assert result.stdout.strip() == sys.executable

    def test_cmd_hang_before_stdout_eof_times_out(self) -> None:
        """BUG-2777: a process that holds stdout open without exiting must still
        time out — the drain loop must not block until EOF before checking the
        deadline. Mirrors test_fsm_runners.py::test_hanging_process_timeout_fires_during_read.
        """
        proc = MagicMock()
        proc.stdout = MagicMock()
        proc.stderr = MagicMock()
        proc.returncode = None
        proc.pid = 12345
        proc.wait.return_value = None
        proc.kill.return_value = None

        sel = MagicMock()
        sel.get_map.return_value = {"pipe": "data"}  # never empty -> loop continues
        sel.select.return_value = []  # no data ever ready
        sel.close.return_value = None
        sel.register.return_value = None

        spec = ActionSpec(name="hang", runner=RunnerType.CMD, target="sleep 9999", timeout=0)

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.runner_spec._kill_process_group") as mock_killpg,
        ):
            result = run_action(spec)

        assert result.timed_out is True
        assert result.exit_code == 2
        mock_killpg.assert_called_once_with(proc)


class TestRunSkillAutomationCompat:
    """ENH-3097 AC 2/AC 13: _run_skill()'s spec.args automation compat surface.

    The only externally-facing compatibility surface in ENH-3097 — no
    in-tree producer sets spec.args["automation_profile"]/
    ["disable_background_tasks"] (every consumer is out-of-tree
    ll-harness/ll-action/extension runners), so nothing else in the suite
    covers a key rename here.
    """

    def test_legacy_dict_keys_still_work(self) -> None:
        spec = ActionSpec(
            name="x",
            runner=RunnerType.SKILL,
            target="x",
            args={"automation_profile": "ll-auto", "disable_background_tasks": True},
        )
        runner = CapturingRunner()
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=runner),
            patch("subprocess.run", return_value=_make_completed()),
        ):
            run_action(spec)

        automation = runner.build_streaming_calls[0]["automation"]
        assert automation is not None
        assert automation.profile == "ll-auto"
        assert automation.disable_background_tasks is True

    def test_automation_key_works(self) -> None:
        spec = ActionSpec(
            name="x",
            runner=RunnerType.SKILL,
            target="x",
            args={"automation": AutomationContext(profile="ctx-profile")},
        )
        runner = CapturingRunner()
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=runner),
            patch("subprocess.run", return_value=_make_completed()),
        ):
            run_action(spec)

        automation = runner.build_streaming_calls[0]["automation"]
        assert automation is not None
        assert automation.profile == "ctx-profile"

    def test_conflict_explicit_automation_wins_and_warns(self) -> None:
        spec = ActionSpec(
            name="x",
            runner=RunnerType.SKILL,
            target="x",
            args={
                "automation": AutomationContext(profile="explicit"),
                "automation_profile": "legacy",
            },
        )
        runner = CapturingRunner()
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=runner),
            patch("subprocess.run", return_value=_make_completed()),
            pytest.warns(DeprecationWarning, match="_run_skill()"),
        ):
            run_action(spec)

        automation = runner.build_streaming_calls[0]["automation"]
        assert automation is not None
        assert automation.profile == "explicit"

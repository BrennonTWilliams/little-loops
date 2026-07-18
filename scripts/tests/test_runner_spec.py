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
from unittest.mock import patch

import pytest

from little_loops.host_runner import HostInvocation
from little_loops.runner_spec import ActionSpec, RunnerResult, RunnerType, run_action


def _make_completed(returncode: int = 0, stdout: str = "", stderr: str = "") -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


class FakeRunner:
    def build_streaming(self, *, prompt: str, **_: object) -> HostInvocation:
        return HostInvocation(binary="claude", args=["-p", prompt])

    def build_blocking_json(self, *, prompt: str, model: str | None = None) -> HostInvocation:
        return HostInvocation(binary="claude", args=["-p", prompt])


class TestActionSpecFrozen:
    def test_action_spec_is_frozen(self) -> None:
        """Mutating an ActionSpec must raise FrozenInstanceError (host_runner convention)."""
        spec = ActionSpec(name="x", runner=RunnerType.CMD, target="echo hi")
        with pytest.raises(dataclasses.FrozenInstanceError):
            spec.target = "echo bye"  # type: ignore[misc]


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
            patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=1)
            ),
        ):
            result = run_action(spec)

        assert result.timed_out is True
        assert result.exit_code == 2

    def test_prompt_dispatch_matches_legacy_shape(self) -> None:
        spec = ActionSpec(name="p", runner=RunnerType.PROMPT, target="What is 2+2?", args={"model": None})
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="4")),
        ):
            result = run_action(spec)

        assert result == RunnerResult(stdout="4", stderr="", exit_code=0)

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

"""Tests for little_loops.cli.harness (ll-harness CLI)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.harness import (
    _parse_harness_args,
    cmd_cmd,
    cmd_dsl,
    cmd_mcp,
    cmd_prompt,
    cmd_skill,
    main_harness,
)
from little_loops.host_runner import HostInvocation

# ---------------------------------------------------------------------------
# Shared helpers (mirroring test_action.py patterns)
# ---------------------------------------------------------------------------


class FakeRunner:
    """Test double for HostRunner."""

    name = "claude-code"

    def build_streaming(self, **_: object) -> HostInvocation:
        return HostInvocation(binary="claude", args=[])

    def build_blocking_json(self, **_: object) -> HostInvocation:
        return HostInvocation(binary="claude", args=[])


def _make_completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _make_namespace(**kwargs: Any) -> Any:
    import argparse

    ns = argparse.Namespace(
        exit_code=None,
        semantic=None,
        timeout=120,
        output="text",
        verbose=False,
        model=None,
    )
    for k, v in kwargs.items():
        setattr(ns, k, v)
    return ns


def _llm_verdict(verdict: str, confidence: float = 0.9, reason: str = "ok") -> str:
    """Helper to create mock evaluate_llm_structured CompletedProcess stdout."""
    return json.dumps(
        {
            "type": "result",
            "subtype": "success",
            "structured_output": {
                "verdict": verdict,
                "confidence": confidence,
                "reason": reason,
            },
        }
    )


# ---------------------------------------------------------------------------
# TestParser
# ---------------------------------------------------------------------------


class TestParser:
    """Tests for _build_harness_parser() and _parse_harness_args()."""

    def test_skill_subparser_target(self) -> None:
        args = _parse_harness_args(["skill", "check-code"])
        assert args.runner == "skill"
        assert args.target == "check-code"
        assert args.runner_args == []

    def test_skill_subparser_with_runner_args(self) -> None:
        args = _parse_harness_args(["skill", "refine-issue", "FEAT-1851"])
        assert args.runner == "skill"
        assert args.target == "refine-issue"
        assert args.runner_args == ["FEAT-1851"]

    def test_cmd_subparser(self) -> None:
        args = _parse_harness_args(["cmd", "echo hello"])
        assert args.runner == "cmd"
        assert args.target == "echo hello"

    def test_mcp_subparser(self) -> None:
        args = _parse_harness_args(["mcp", "my-server:my-tool"])
        assert args.runner == "mcp"
        assert args.target == "my-server:my-tool"
        assert args.mcp_args == "{}"

    def test_mcp_subparser_with_args(self) -> None:
        args = _parse_harness_args(["mcp", "srv:tool", "--args", '{"key": "val"}'])
        assert args.mcp_args == '{"key": "val"}'

    def test_prompt_subparser(self) -> None:
        args = _parse_harness_args(["prompt", "What is 2+2?"])
        assert args.runner == "prompt"
        assert args.target == "What is 2+2?"

    def test_prompt_subparser_with_model(self) -> None:
        args = _parse_harness_args(
            ["prompt", "What is 2+2?", "--model", "claude-haiku-4-5-20251001"]
        )
        assert args.runner == "prompt"
        assert args.model == "claude-haiku-4-5-20251001"

    def test_prompt_model_defaults_none(self) -> None:
        args = _parse_harness_args(["prompt", "What is 2+2?"])
        assert args.model is None

    def test_model_flag_absent_from_skill(self) -> None:
        with pytest.raises(SystemExit):
            _parse_harness_args(["skill", "check-code", "--model", "claude-haiku-4-5-20251001"])

    def test_model_flag_absent_from_cmd(self) -> None:
        with pytest.raises(SystemExit):
            _parse_harness_args(["cmd", "echo hi", "--model", "claude-haiku-4-5-20251001"])

    def test_model_flag_absent_from_mcp(self) -> None:
        with pytest.raises(SystemExit):
            _parse_harness_args(["mcp", "srv:tool", "--model", "claude-haiku-4-5-20251001"])

    def test_exit_code_flag(self) -> None:
        args = _parse_harness_args(["cmd", "true", "--exit-code", "0"])
        assert args.exit_code == 0

    def test_semantic_flag(self) -> None:
        args = _parse_harness_args(["cmd", "echo hi", "--semantic", "says hello"])
        assert args.semantic == "says hello"

    def test_timeout_default(self) -> None:
        args = _parse_harness_args(["cmd", "true"])
        assert args.timeout == 120

    def test_timeout_override(self) -> None:
        args = _parse_harness_args(["cmd", "true", "--timeout", "60"])
        assert args.timeout == 60

    def test_output_default(self) -> None:
        args = _parse_harness_args(["cmd", "true"])
        assert args.output == "text"

    def test_output_json(self) -> None:
        args = _parse_harness_args(["cmd", "true", "--output", "json"])
        assert args.output == "json"

    def test_verbose_flag(self) -> None:
        args = _parse_harness_args(["cmd", "true", "--verbose"])
        assert args.verbose is True

    def test_missing_runner_exits(self) -> None:
        with pytest.raises(SystemExit):
            _parse_harness_args([])

    def test_invalid_output_choice_exits(self) -> None:
        with pytest.raises(SystemExit):
            _parse_harness_args(["cmd", "true", "--output", "xml"])


# ---------------------------------------------------------------------------
# TestCmdSkill
# ---------------------------------------------------------------------------


class TestCmdSkill:
    """Tests for cmd_skill()."""

    def test_skill_pass_no_criteria(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 0 when runner completes and no evaluator criteria are supplied."""
        args = _make_namespace(runner="skill", target="check-code", runner_args=[])

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout="All checks passed"),
            ),
        ):
            result = cmd_skill(args)

        assert result == 0
        out = capsys.readouterr().out
        assert "PASS" in out

    def test_skill_with_runner_args(self) -> None:
        """Passes runner_args as part of the skill prompt."""
        args = _make_namespace(runner="skill", target="refine-issue", runner_args=["FEAT-1851"])
        captured_prompt = []

        def fake_build_streaming(*, prompt: str, **_: object) -> HostInvocation:
            captured_prompt.append(prompt)
            return HostInvocation(binary="claude", args=[])

        fake_runner = FakeRunner()
        fake_runner.build_streaming = fake_build_streaming  # type: ignore[method-assign]

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=fake_runner),
            patch("subprocess.run", return_value=_make_completed()),
        ):
            cmd_skill(args)

        assert captured_prompt[0] == "/ll:refine-issue FEAT-1851"

    def test_skill_exit_code_pass(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 0 when captured exit code matches --exit-code."""
        args = _make_namespace(runner="skill", target="check-code", runner_args=[], exit_code=0)

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0)),
        ):
            result = cmd_skill(args)

        assert result == 0

    def test_skill_exit_code_fail(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 1 when captured exit code does not match --exit-code."""
        args = _make_namespace(runner="skill", target="check-code", runner_args=[], exit_code=0)

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=1)),
        ):
            result = cmd_skill(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_skill_timeout_returns_2(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 2 when runner times out."""
        args = _make_namespace(runner="skill", target="check-code", runner_args=[])

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120)
            ),
        ):
            result = cmd_skill(args)

        assert result == 2

    def test_skill_binary_not_found_returns_2(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 2 when host CLI binary is not found."""
        args = _make_namespace(runner="skill", target="check-code", runner_args=[])

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", side_effect=FileNotFoundError("claude not found")),
        ):
            result = cmd_skill(args)

        assert result == 2

    def test_skill_passes_non_interactive_env_to_subprocess(self) -> None:
        """cmd_skill merges LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS into subprocess env (BUG-2110)."""
        args = _make_namespace(runner="skill", target="check-code", runner_args=[])
        captured_env: dict[str, str] = {}

        def fake_build_streaming(*, prompt: str, **_: object) -> HostInvocation:
            return HostInvocation(
                binary="claude",
                args=[],
                env={"LL_NON_INTERACTIVE": "1", "DANGEROUSLY_SKIP_PERMISSIONS": "1"},
            )

        fake_runner = FakeRunner()
        fake_runner.build_streaming = fake_build_streaming  # type: ignore[method-assign]

        def capture_run(cmd: Any, **kwargs: Any) -> subprocess.CompletedProcess:
            captured_env.update(kwargs.get("env", {}))
            return _make_completed(returncode=0)

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=fake_runner),
            patch("subprocess.run", side_effect=capture_run),
        ):
            cmd_skill(args)

        assert "LL_NON_INTERACTIVE" in captured_env, "LL_NON_INTERACTIVE must be in subprocess env"
        assert captured_env["LL_NON_INTERACTIVE"] == "1"
        assert "DANGEROUSLY_SKIP_PERMISSIONS" in captured_env
        assert captured_env["DANGEROUSLY_SKIP_PERMISSIONS"] == "1"


# ---------------------------------------------------------------------------
# TestCmdCmd
# ---------------------------------------------------------------------------


class TestCmdCmd:
    """Tests for cmd_cmd()."""

    def _make_popen_mock(
        self, stdout_lines: list[str], stderr_lines: list[str], returncode: int = 0
    ) -> MagicMock:
        mock_proc = MagicMock()
        mock_proc.stdout = iter(stdout_lines)
        mock_proc.stderr = iter(stderr_lines)
        mock_proc.returncode = returncode
        mock_proc.wait.return_value = None
        mock_proc.kill.return_value = None
        return mock_proc

    def test_cmd_captures_stdout(self, capsys: pytest.CaptureFixture) -> None:
        """Captures stdout from the shell command."""
        args = _make_namespace(runner="cmd", target="echo hello", verbose=True)
        mock_proc = self._make_popen_mock(["hello\n"], [])

        with patch("subprocess.Popen", return_value=mock_proc):
            result = cmd_cmd(args)

        assert result == 0
        out = capsys.readouterr().out
        assert "hello" in out

    def test_cmd_exit_code_pass(self) -> None:
        """Exits 0 when exit code matches --exit-code."""
        args = _make_namespace(runner="cmd", target="true", exit_code=0)
        mock_proc = self._make_popen_mock([], [], returncode=0)

        with patch("subprocess.Popen", return_value=mock_proc):
            result = cmd_cmd(args)

        assert result == 0

    def test_cmd_exit_code_fail(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 1 when exit code does not match --exit-code."""
        args = _make_namespace(runner="cmd", target="false", exit_code=0)
        mock_proc = self._make_popen_mock([], [], returncode=1)

        with patch("subprocess.Popen", return_value=mock_proc):
            result = cmd_cmd(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_cmd_no_criteria_always_pass(self) -> None:
        """Exits 0 with no criteria when runner completes."""
        args = _make_namespace(runner="cmd", target="false")
        mock_proc = self._make_popen_mock([], [], returncode=1)

        with patch("subprocess.Popen", return_value=mock_proc):
            result = cmd_cmd(args)

        assert result == 0

    def test_cmd_timeout_returns_2(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 2 on timeout."""
        args = _make_namespace(runner="cmd", target="sleep 999", timeout=1)
        mock_proc = self._make_popen_mock([], [])
        # First call (with timeout=) raises; second call (post-kill, no timeout) succeeds.
        mock_proc.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="bash", timeout=1),
            None,
        ]

        with patch("subprocess.Popen", return_value=mock_proc):
            result = cmd_cmd(args)

        assert result == 2
        mock_proc.kill.assert_called_once()

    def test_cmd_json_output(self, capsys: pytest.CaptureFixture) -> None:
        """--output json produces valid JSON with result field."""
        args = _make_namespace(runner="cmd", target="echo hi", output="json")
        mock_proc = self._make_popen_mock(["hi\n"], [])

        with patch("subprocess.Popen", return_value=mock_proc):
            result = cmd_cmd(args)

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["result"] == "PASS"
        assert "stdout" in data


# ---------------------------------------------------------------------------
# TestCmdMcp
# ---------------------------------------------------------------------------


class TestCmdMcp:
    """Tests for cmd_mcp()."""

    def test_mcp_calls_tool(self) -> None:
        """Calls call_mcp_tool with correct server, tool, and params."""
        args = _make_namespace(runner="mcp", target="my-server:my-tool", mcp_args="{}")
        captured: list[Any] = []

        def fake_call(server: str, tool: str, params: dict, **_: Any) -> tuple[dict, int]:
            captured.append((server, tool, params))
            return {"content": [{"type": "text", "text": "ok"}]}, 0

        with patch("little_loops.runner_spec.call_mcp_tool", side_effect=fake_call):
            result = cmd_mcp(args)

        assert result == 0
        assert captured[0] == ("my-server", "my-tool", {})

    def test_mcp_passes_json_args(self) -> None:
        """Passes parsed JSON args to call_mcp_tool."""
        args = _make_namespace(
            runner="mcp", target="srv:tool", mcp_args='{"key": "val", "num": 42}'
        )
        captured: list[dict] = []

        def fake_call(server: str, tool: str, params: dict, **_: Any) -> tuple[dict, int]:
            captured.append(params)
            return {}, 0

        with patch("little_loops.runner_spec.call_mcp_tool", side_effect=fake_call):
            cmd_mcp(args)

        assert captured[0] == {"key": "val", "num": 42}

    def test_mcp_invalid_target_format(self, capsys: pytest.CaptureFixture) -> None:
        """Returns 2 when target lacks colon separator."""
        args = _make_namespace(runner="mcp", target="notavalidtarget", mcp_args="{}")
        result = cmd_mcp(args)
        assert result == 2

    def test_mcp_invalid_json_args(self, capsys: pytest.CaptureFixture) -> None:
        """Returns 2 when --args is not valid JSON."""
        args = _make_namespace(runner="mcp", target="srv:tool", mcp_args="{bad json}")
        result = cmd_mcp(args)
        assert result == 2

    def test_mcp_tool_error_exit_code(self, capsys: pytest.CaptureFixture) -> None:
        """Returns 0 with no criteria even when MCP returns non-zero exit code."""
        args = _make_namespace(runner="mcp", target="srv:tool", mcp_args="{}")

        with patch(
            "little_loops.runner_spec.call_mcp_tool",
            return_value=({"isError": True, "content": []}, 1),
        ):
            result = cmd_mcp(args)

        assert result == 0

    def test_mcp_exit_code_criterion_fail(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 1 when exit code does not match --exit-code criterion."""
        args = _make_namespace(runner="mcp", target="srv:tool", mcp_args="{}", exit_code=0)

        with patch(
            "little_loops.runner_spec.call_mcp_tool",
            return_value=({}, 1),
        ):
            result = cmd_mcp(args)

        assert result == 1


# ---------------------------------------------------------------------------
# TestCmdPrompt
# ---------------------------------------------------------------------------


class TestCmdPrompt:
    """Tests for cmd_prompt()."""

    def test_prompt_sends_request(self) -> None:
        """Calls resolve_host().build_blocking_json with the prompt text."""
        args = _make_namespace(runner="prompt", target="What is 2+2?")
        captured_prompt: list[str] = []

        def fake_build_blocking_json(*, prompt: str, **_: object) -> HostInvocation:
            captured_prompt.append(prompt)
            return HostInvocation(binary="claude", args=[])

        fake_runner = FakeRunner()
        fake_runner.build_blocking_json = fake_build_blocking_json  # type: ignore[method-assign]

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=fake_runner),
            patch("subprocess.run", return_value=_make_completed(stdout="4")),
        ):
            result = cmd_prompt(args)

        assert result == 0
        assert captured_prompt[0] == "What is 2+2?"

    def test_prompt_timeout_returns_2(self) -> None:
        """Exits 2 on timeout."""
        args = _make_namespace(runner="prompt", target="hello")

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120)
            ),
        ):
            result = cmd_prompt(args)

        assert result == 2

    def test_prompt_binary_not_found_returns_2(self) -> None:
        """Exits 2 when host CLI binary is not found."""
        args = _make_namespace(runner="prompt", target="hello")

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", side_effect=FileNotFoundError("claude not found")),
        ):
            result = cmd_prompt(args)

        assert result == 2

    def test_prompt_threads_model(self) -> None:
        """Passes --model value to build_blocking_json."""
        args = _make_namespace(
            runner="prompt", target="What is 2+2?", model="claude-haiku-4-5-20251001"
        )
        captured: dict[str, object] = {}

        def fake_build_blocking_json(
            *, prompt: str, model: str | None = None, **_: object
        ) -> HostInvocation:
            captured["prompt"] = prompt
            captured["model"] = model
            return HostInvocation(binary="claude", args=[])

        fake_runner = FakeRunner()
        fake_runner.build_blocking_json = fake_build_blocking_json  # type: ignore[method-assign]

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=fake_runner),
            patch("subprocess.run", return_value=_make_completed(stdout="4")),
        ):
            cmd_prompt(args)

        assert captured["model"] == "claude-haiku-4-5-20251001"

    def test_prompt_model_none_when_omitted(self) -> None:
        """Passes model=None to build_blocking_json when --model is not supplied."""
        args = _make_namespace(runner="prompt", target="hello")
        captured: dict[str, object] = {}

        def fake_build_blocking_json(
            *, prompt: str, model: str | None = None, **_: object
        ) -> HostInvocation:
            captured["model"] = model
            return HostInvocation(binary="claude", args=[])

        fake_runner = FakeRunner()
        fake_runner.build_blocking_json = fake_build_blocking_json  # type: ignore[method-assign]

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=fake_runner),
            patch("subprocess.run", return_value=_make_completed(stdout="hi")),
        ):
            cmd_prompt(args)

        assert captured["model"] is None


# ---------------------------------------------------------------------------
# TestSemanticEvaluator
# ---------------------------------------------------------------------------


class TestSemanticEvaluator:
    """Tests for --semantic evaluator interaction."""

    def test_semantic_yes_passes(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 0 when evaluate_llm_structured returns 'yes'."""
        from little_loops.fsm.evaluators import EvaluationResult

        args = _make_namespace(runner="cmd", target="echo hi", semantic="output contains hi")
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["hi\n"])
        mock_proc.stderr = iter([])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch(
                "little_loops.cli.harness.evaluate_llm_structured",
                return_value=EvaluationResult(verdict="yes", details={"confidence": 0.9}),
            ),
        ):
            result = cmd_cmd(args)

        assert result == 0
        out = capsys.readouterr().out
        assert "PASS" in out
        assert "yes" in out

    @pytest.mark.parametrize("verdict", ["no", "blocked", "partial"])
    def test_semantic_non_yes_fails(self, verdict: str, capsys: pytest.CaptureFixture) -> None:
        """Exits 1 when evaluate_llm_structured returns non-yes verdict."""
        from little_loops.fsm.evaluators import EvaluationResult

        args = _make_namespace(runner="cmd", target="echo hi", semantic="some criterion")
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["hi\n"])
        mock_proc.stderr = iter([])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch(
                "little_loops.cli.harness.evaluate_llm_structured",
                return_value=EvaluationResult(verdict=verdict, details={}),
            ),
        ):
            result = cmd_cmd(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_both_criteria_must_pass(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 1 when exit code passes but semantic fails."""
        from little_loops.fsm.evaluators import EvaluationResult

        args = _make_namespace(runner="cmd", target="echo hi", exit_code=0, semantic="must fail")
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["hi\n"])
        mock_proc.stderr = iter([])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        with (
            patch("subprocess.Popen", return_value=mock_proc),
            patch(
                "little_loops.cli.harness.evaluate_llm_structured",
                return_value=EvaluationResult(verdict="no", details={}),
            ),
        ):
            result = cmd_cmd(args)

        assert result == 1


# ---------------------------------------------------------------------------
# TestMainHarness
# ---------------------------------------------------------------------------


class TestMainHarness:
    """Integration tests for main_harness()."""

    def test_main_harness_cmd_pass(self, capsys: pytest.CaptureFixture) -> None:
        """main_harness returns 0 for a passing cmd invocation."""
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["hello\n"])
        mock_proc.stderr = iter([])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        with (
            patch("sys.argv", ["ll-harness", "cmd", "echo hello", "--exit-code", "0"]),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            result = main_harness(["cmd", "echo hello", "--exit-code", "0"])

        assert result == 0

    def test_main_harness_cmd_fail(self, capsys: pytest.CaptureFixture) -> None:
        """main_harness returns 1 for a failing cmd invocation."""
        mock_proc = MagicMock()
        mock_proc.stdout = iter([])
        mock_proc.stderr = iter([])
        mock_proc.returncode = 1
        mock_proc.wait.return_value = None

        with (
            patch("sys.argv", ["ll-harness", "cmd", "false", "--exit-code", "0"]),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            result = main_harness(["cmd", "false", "--exit-code", "0"])

        assert result == 1

    def test_main_harness_skill_pass(self, capsys: pytest.CaptureFixture) -> None:
        """main_harness returns 0 for a passing skill invocation."""
        with (
            patch("sys.argv", ["ll-harness", "skill", "check-code"]),
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0)),
        ):
            result = main_harness(["skill", "check-code"])

        assert result == 0

    def test_main_harness_mcp_pass(self, capsys: pytest.CaptureFixture) -> None:
        """main_harness returns 0 for a passing mcp invocation."""
        with (
            patch("sys.argv", ["ll-harness", "mcp", "srv:tool"]),
            patch("little_loops.runner_spec.call_mcp_tool", return_value=({}, 0)),
        ):
            result = main_harness(["mcp", "srv:tool"])

        assert result == 0

    def test_main_harness_prompt_pass(self, capsys: pytest.CaptureFixture) -> None:
        """main_harness returns 0 for a passing prompt invocation."""
        with (
            patch("sys.argv", ["ll-harness", "prompt", "hello"]),
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="response")),
        ):
            result = main_harness(["prompt", "hello"])

        assert result == 0

    def test_main_harness_json_output(self, capsys: pytest.CaptureFixture) -> None:
        """main_harness --output json produces parseable JSON."""
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["hi\n"])
        mock_proc.stderr = iter([])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        with (
            patch("sys.argv", ["ll-harness", "cmd", "echo hi", "--output", "json"]),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            result = main_harness(["cmd", "echo hi", "--output", "json"])

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["result"] == "PASS"
        assert "exit_code" in data
        assert "semantic" in data

    def test_main_harness_verbose_shows_output_on_pass(self, capsys: pytest.CaptureFixture) -> None:
        """--verbose shows captured output even when result is PASS."""
        mock_proc = MagicMock()
        mock_proc.stdout = iter(["secret output\n"])
        mock_proc.stderr = iter([])
        mock_proc.returncode = 0
        mock_proc.wait.return_value = None

        with (
            patch("sys.argv", ["ll-harness", "cmd", "echo secret output", "--verbose"]),
            patch("subprocess.Popen", return_value=mock_proc),
        ):
            result = main_harness(["cmd", "echo secret output", "--verbose"])

        assert result == 0
        out = capsys.readouterr().out
        assert "secret output" in out

    def test_main_harness_dsl_dispatches(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """main_harness dispatches 'dsl' runner to cmd_dsl."""

        task_file = tmp_path / "task.yaml"
        task_file.write_text(
            "prompt: complete the transition\nblanks: [on_yes]\n"
            "expected: {on_yes: done}\nsource_dsl: loop\ntask_type: fill-in-the-blank\n"
        )

        with patch("little_loops.cli.harness.cmd_dsl", return_value=0) as mock_dsl:
            result = main_harness(["dsl", str(task_file)])

        assert result == 0
        mock_dsl.assert_called_once()


# ---------------------------------------------------------------------------
# TestDslSubcommandParser
# ---------------------------------------------------------------------------


class TestDslSubcommandParser:
    """Tests for the 'dsl' subparser in _build_harness_parser()."""

    def test_dsl_subparser_path(self, tmp_path: Path) -> None:
        args = _parse_harness_args(["dsl", str(tmp_path)])
        assert args.runner == "dsl"
        assert args.path == str(tmp_path)

    def test_dsl_subparser_with_model(self, tmp_path: Path) -> None:
        args = _parse_harness_args(["dsl", str(tmp_path), "--model", "claude-haiku-4-5-20251001"])
        assert args.model == "claude-haiku-4-5-20251001"

    def test_dsl_model_defaults_none(self, tmp_path: Path) -> None:
        args = _parse_harness_args(["dsl", str(tmp_path)])
        assert args.model is None

    def test_dsl_subparser_exit_code_flag(self, tmp_path: Path) -> None:
        args = _parse_harness_args(["dsl", str(tmp_path), "--exit-code", "0"])
        assert args.exit_code == 0

    def test_dsl_subparser_semantic_flag(self, tmp_path: Path) -> None:
        args = _parse_harness_args(["dsl", str(tmp_path), "--semantic", "contains expected"])
        assert args.semantic == "contains expected"

    def test_dsl_subparser_timeout_override(self, tmp_path: Path) -> None:
        args = _parse_harness_args(["dsl", str(tmp_path), "--timeout", "60"])
        assert args.timeout == 60

    def test_dsl_subparser_output_json(self, tmp_path: Path) -> None:
        args = _parse_harness_args(["dsl", str(tmp_path), "--output", "json"])
        assert args.output == "json"

    def test_dsl_subparser_verbose(self, tmp_path: Path) -> None:
        args = _parse_harness_args(["dsl", str(tmp_path), "--verbose"])
        assert args.verbose is True


# ---------------------------------------------------------------------------
# TestCmdDsl
# ---------------------------------------------------------------------------


class TestCmdDsl:
    """Tests for cmd_dsl()."""

    def _make_task_yaml(self, tmp_path: Path, name: str = "task.yaml") -> Path:
        p = tmp_path / name
        p.write_text(
            "prompt: Complete this FSM transition.\n"
            "blanks:\n  - on_yes\nblanks:\n  - on_yes\n"
            "expected:\n  on_yes: done\n"
            "source_dsl: loop\n"
            "task_type: fill-in-the-blank\n"
            "source_file: loops/my-loop.yaml\n"
            "generated_at: 2026-06-11T00:00:00Z\n"
        )
        return p

    def test_cmd_dsl_single_file_pass(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Single task file with passing prompt → exits 0 and prints pass-rate."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="done")),
        ):
            result = cmd_dsl(args)

        assert result == 0
        out = capsys.readouterr().out
        assert "pass-rate" in out
        assert "1/1" in out

    def test_cmd_dsl_single_file_fail(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Single task file with failing prompt → exits 1."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file), exit_code=0)

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=1, stdout="")),
        ):
            result = cmd_dsl(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "pass-rate" in out
        assert "0/1" in out

    def test_cmd_dsl_directory_scans_yaml_files(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Directory with multiple .yaml files runs each task."""
        for i in range(3):
            self._make_task_yaml(tmp_path, f"task{i}.yaml")
        args = _make_namespace(runner="dsl", path=str(tmp_path))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="done")),
        ):
            result = cmd_dsl(args)

        assert result == 0
        out = capsys.readouterr().out
        assert "3/3" in out

    def test_cmd_dsl_path_not_found(self, capsys: pytest.CaptureFixture) -> None:
        """Missing path returns 2."""
        args = _make_namespace(runner="dsl", path="/nonexistent/path")
        result = cmd_dsl(args)
        assert result == 2

    def test_cmd_dsl_empty_directory(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Directory with no .yaml files returns 2."""
        args = _make_namespace(runner="dsl", path=str(tmp_path))
        result = cmd_dsl(args)
        assert result == 2

    def test_cmd_dsl_passes_model_to_prompt(self, tmp_path: Path) -> None:
        """--model flag is forwarded to cmd_prompt."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file), model="claude-haiku-4-5-20251001")
        captured: dict[str, object] = {}

        def fake_build_blocking_json(
            *, prompt: str, model: str | None = None, **_: object
        ) -> HostInvocation:
            captured["model"] = model
            return HostInvocation(binary="claude", args=[])

        fake_runner = FakeRunner()
        fake_runner.build_blocking_json = fake_build_blocking_json  # type: ignore[method-assign]

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=fake_runner),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="done")),
        ):
            cmd_dsl(args)

        assert captured["model"] == "claude-haiku-4-5-20251001"

    def test_cmd_dsl_wilson_ci_in_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """Output includes Wilson CI bounds."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="done")),
        ):
            cmd_dsl(args)

        out = capsys.readouterr().out
        assert "95% CI" in out


# ---------------------------------------------------------------------------
# TestHarnessEventPersistence
# ---------------------------------------------------------------------------


class TestHarnessEventPersistence:
    """ENH-2740: ll-harness call sites write harness_events rows."""

    def _make_task_yaml(self, tmp_path: Path, name: str = "task.yaml") -> Path:
        p = tmp_path / name
        p.write_text(
            "prompt: Complete this FSM transition.\n"
            "blanks:\n  - on_yes\n"
            "expected:\n  on_yes: done\n"
            "source_dsl: loop\n"
            "task_type: fill-in-the-blank\n"
        )
        return p

    def test_pass_run_writes_row(self) -> None:
        from little_loops.session_store import recent

        args = _make_namespace(runner="skill", target="check-code", runner_args=[])
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="ok")),
        ):
            result = cmd_skill(args)

        assert result == 0
        rows = recent(kind="harness", limit=10)
        assert len(rows) == 1
        assert rows[0]["runner"] == "skill"
        assert rows[0]["target"] == "check-code"
        assert rows[0]["exit_code"] == 0
        assert rows[0]["semantic_passed"] == 1

    def test_fail_run_writes_row(self) -> None:
        from little_loops.session_store import recent

        args = _make_namespace(runner="cmd", target="false", exit_code=0)
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=1)),
        ):
            result = cmd_cmd(args)

        assert result == 1
        rows = recent(kind="harness", limit=10)
        assert rows[0]["semantic_passed"] == 0

    def test_timeout_records_timed_out(self) -> None:
        from little_loops.session_store import recent

        args = _make_namespace(runner="skill", target="check-code", runner_args=[])
        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run", side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120)
            ),
        ):
            result = cmd_skill(args)

        assert result == 2
        rows = recent(kind="harness", limit=10)
        assert rows[0]["timed_out"] == 1

    def test_dsl_batch_writes_aggregate_and_per_task_rows(self, tmp_path: Path) -> None:
        from little_loops.session_store import recent

        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="done")),
        ):
            cmd_dsl(args)

        rows = recent(kind="harness", limit=20)
        aggregate = next(r for r in rows if r["runner"] == "dsl")
        task_row = next(r for r in rows if r["runner"] == "dsl-task")
        assert task_row["target"] == task_file.name
        assert task_row["parent_id"] == aggregate["id"]

    def test_main_harness_succeeds_when_db_unopenable(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A DB write failure (unopenable path) must not change the harness exit code."""
        # A directory is not default-shaped, so LL_HISTORY_DB routes there verbatim
        # and sqlite fails to open it as a database file.
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0)),
        ):
            result = main_harness(["cmd", "true"])

        assert result == 0

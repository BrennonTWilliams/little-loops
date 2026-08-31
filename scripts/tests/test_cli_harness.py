"""Tests for little_loops.cli.harness (ll-harness CLI)."""

from __future__ import annotations

import json
import subprocess
from datetime import UTC, datetime, timedelta
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


class _MockFileObj:
    """File-like object supporting fileno() and readline() for selector tests."""

    def __init__(self, lines: list[str] | None = None):
        self._lines = list(lines) if lines else []
        self._pos = 0

    def fileno(self) -> int:
        return id(self) % 65536

    def readline(self) -> str:
        if self._pos < len(self._lines):
            line = self._lines[self._pos]
            self._pos += 1
            return line
        return ""  # EOF


def _make_selector_mock_process(
    stdout_lines: list[str] | None = None,
    stderr_lines: list[str] | None = None,
    returncode: int = 0,
) -> MagicMock:
    """Mock Popen process compatible with runner_spec._run_cmd's selector loop."""
    proc = MagicMock()
    proc.stdout = _MockFileObj(stdout_lines or [])
    proc.stderr = _MockFileObj(stderr_lines or [])
    proc.returncode = returncode
    proc.pid = 12345
    proc.wait.return_value = None
    proc.kill.return_value = None
    return proc


def _make_ready_selector() -> MagicMock:
    """Mock DefaultSelector returning all registered keys as ready on every select()."""
    sel = MagicMock()
    registered: dict = {}

    def _register(fobj, events, data=None):
        registered[fobj] = (events, data)

    def _unregister(fobj):
        registered.pop(fobj, None)

    def _select(timeout=None):
        result = []
        for fobj, (events, data) in list(registered.items()):
            key = MagicMock()
            key.fileobj = fobj
            key.data = data
            result.append((key, events))
        return result

    sel.register.side_effect = _register
    sel.unregister.side_effect = _unregister
    sel.get_map.side_effect = lambda: dict(registered)
    sel.select.side_effect = _select
    sel.close.return_value = None
    return sel


class TestCmdCmd:
    """Tests for cmd_cmd()."""

    def test_cmd_captures_stdout(self, capsys: pytest.CaptureFixture) -> None:
        """Captures stdout from the shell command."""
        args = _make_namespace(runner="cmd", target="echo hello", verbose=True)
        mock_proc = _make_selector_mock_process(["hello\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
        ):
            result = cmd_cmd(args)

        assert result == 0
        out = capsys.readouterr().out
        assert "hello" in out

    def test_cmd_exit_code_pass(self) -> None:
        """Exits 0 when exit code matches --exit-code."""
        args = _make_namespace(runner="cmd", target="true", exit_code=0)
        mock_proc = _make_selector_mock_process(returncode=0)
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
        ):
            result = cmd_cmd(args)

        assert result == 0

    def test_cmd_exit_code_fail(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 1 when exit code does not match --exit-code."""
        args = _make_namespace(runner="cmd", target="false", exit_code=0)
        mock_proc = _make_selector_mock_process(returncode=1)
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
        ):
            result = cmd_cmd(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "FAIL" in out

    def test_cmd_no_criteria_always_pass(self) -> None:
        """Exits 0 with no criteria when runner completes."""
        args = _make_namespace(runner="cmd", target="false")
        mock_proc = _make_selector_mock_process(returncode=1)
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
        ):
            result = cmd_cmd(args)

        assert result == 0

    def test_cmd_timeout_returns_2(self, capsys: pytest.CaptureFixture) -> None:
        """Exits 2 on timeout, enforced via the wall-clock deadline (BUG-2777).

        Simulates a hang by making the selector report no ready pipes while
        get_map() stays non-empty, forcing the deadline check to fire — this
        exercises the same dead-zone the bug covers (drain never reaching EOF).
        """
        args = _make_namespace(runner="cmd", target="sleep 999", timeout=0)
        mock_proc = _make_selector_mock_process()
        sel = MagicMock()
        sel.get_map.return_value = {"pipe": "data"}  # never empty → loop continues
        sel.select.return_value = []  # no data ever ready
        sel.close.return_value = None
        sel.register.return_value = None

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.runner_spec._kill_process_group") as mock_killpg,
        ):
            result = cmd_cmd(args)

        assert result == 2
        mock_killpg.assert_called_once_with(mock_proc)

    def test_cmd_json_output(self, capsys: pytest.CaptureFixture) -> None:
        """--output json produces valid JSON with result field."""
        args = _make_namespace(runner="cmd", target="echo hi", output="json")
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
        ):
            result = cmd_cmd(args)

        assert result == 0
        out = capsys.readouterr().out
        data = json.loads(out)
        assert data["result"] == "PASS"
        assert "stdout" in data

    def test_no_issue_id_omits_prepatch_evidence_key(self, capsys: pytest.CaptureFixture) -> None:
        """ENH-2998: without --issue-id, output is unchanged -- no key added."""
        args = _make_namespace(runner="cmd", target="echo hi", output="json")
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
        ):
            result = cmd_cmd(args)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "prepatch_evidence" not in data

    def test_issue_id_with_no_bundle_omits_key_not_an_error(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        """ENH-2998: --issue-id with no persisted row is a silent absence,
        never an error -- the common case where prepatch_check was never
        enabled."""
        args = _make_namespace(runner="cmd", target="echo hi", output="json", issue_id="ENH-9999")
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.cli.harness._read_prepatch_evidence", return_value=None),
        ):
            result = cmd_cmd(args)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "prepatch_evidence" not in data

    def test_issue_id_with_bundle_adds_additive_key(self, capsys: pytest.CaptureFixture) -> None:
        """ENH-2998: a persisted bundle is surfaced verbatim, additively --
        cli/harness.py does not re-implement or re-run the check."""
        args = _make_namespace(runner="cmd", target="echo hi", output="json", issue_id="ENH-9999")
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()
        bundle = {"base_ref": "deadbeef", "verdict": "clean", "outcomes": []}

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch(
                "little_loops.cli.harness._read_prepatch_evidence", return_value=bundle
            ) as mock_read,
            patch("little_loops.prepatch_check.run_prepatch_check") as mock_run,
        ):
            result = cmd_cmd(args)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data["prepatch_evidence"] == bundle
        mock_read.assert_called_once_with("ENH-9999")
        mock_run.assert_not_called()

    def test_no_history_omits_keys(self, capsys: pytest.CaptureFixture) -> None:
        """ENH-3223 AC3: no matching history -- new fields are simply omitted."""
        args = _make_namespace(runner="cmd", target="echo hi", output="json")
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch("little_loops.cli.harness._read_target_history", return_value=None),
        ):
            result = cmd_cmd(args)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "history_pass_rate" not in data
        assert "history_abstention_rate" not in data

    def test_history_present_adds_additive_keys(self, capsys: pytest.CaptureFixture) -> None:
        """ENH-3223 AC1/AC5: a resolved history dict is folded in verbatim,
        under keys distinct from `prepatch_evidence`/existing payload keys."""
        args = _make_namespace(runner="cmd", target="echo hi", output="json")
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()
        history = {
            "history_pass_rate": 0.8,
            "history_pass_rate_runs": 10,
            "history_abstention_rate": 0.25,
            "history_judged_runs": 4,
            "history_since": "2026-07-18T00:00:00Z",
        }

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch(
                "little_loops.cli.harness._read_target_history", return_value=history
            ) as mock_read,
        ):
            result = cmd_cmd(args)

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        for key, value in history.items():
            assert data[key] == value
        # AC5: the two rates render under distinct field names, not a shared "scored" key.
        assert "history_pass_rate_runs" in data
        assert "history_judged_runs" in data
        mock_read.assert_called_once_with("echo hi")


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
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
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
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
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
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch(
                "little_loops.cli.harness.evaluate_llm_structured",
                return_value=EvaluationResult(verdict="no", details={}),
            ),
        ):
            result = cmd_cmd(args)

        assert result == 1


# ---------------------------------------------------------------------------
# TestAbstentionVerdict (ENH-3185 AC9)
# ---------------------------------------------------------------------------


class TestAbstentionVerdict:
    """Tests for `cannot_judge` exit-code/reporting semantics (ENH-3185 AC9)."""

    @pytest.mark.parametrize("verdict", ["cannot_judge", "cannot_judge_uncertain"])
    def test_semantic_abstain_exits_3(self, verdict: str, capsys: pytest.CaptureFixture) -> None:
        """No failure but >=1 abstention → exit 3, distinct from PASS(0)/FAIL(1)/ERROR(2)."""
        from little_loops.fsm.evaluators import EvaluationResult

        args = _make_namespace(runner="cmd", target="echo hi", semantic="some criterion")
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch(
                "little_loops.cli.harness.evaluate_llm_structured",
                return_value=EvaluationResult(verdict=verdict, details={}),
            ),
        ):
            result = cmd_cmd(args)

        assert result == 3
        out = capsys.readouterr().out
        assert "ABSTAIN" in out

    def test_exit_code_fail_dominates_semantic_abstain(self, capsys: pytest.CaptureFixture) -> None:
        """Precedence is fail > abstain > pass: a mixed run reports FAIL/exit 1."""
        from little_loops.fsm.evaluators import EvaluationResult

        args = _make_namespace(
            runner="cmd", target="echo hi", exit_code=99, semantic="some criterion"
        )
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch(
                "little_loops.cli.harness.evaluate_llm_structured",
                return_value=EvaluationResult(verdict="cannot_judge", details={}),
            ),
        ):
            result = cmd_cmd(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "FAIL" in out


# ---------------------------------------------------------------------------
# TestMainHarness
# ---------------------------------------------------------------------------


class TestMainHarness:
    """Integration tests for main_harness()."""

    def test_main_harness_cmd_pass(self, capsys: pytest.CaptureFixture) -> None:
        """main_harness returns 0 for a passing cmd invocation."""
        mock_proc = _make_selector_mock_process(["hello\n"])
        sel = _make_ready_selector()

        with (
            patch("sys.argv", ["ll-harness", "cmd", "echo hello", "--exit-code", "0"]),
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
        ):
            result = main_harness(["cmd", "echo hello", "--exit-code", "0"])

        assert result == 0

    def test_main_harness_cmd_fail(self, capsys: pytest.CaptureFixture) -> None:
        """main_harness returns 1 for a failing cmd invocation."""
        mock_proc = _make_selector_mock_process(returncode=1)
        sel = _make_ready_selector()

        with (
            patch("sys.argv", ["ll-harness", "cmd", "false", "--exit-code", "0"]),
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
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
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("sys.argv", ["ll-harness", "cmd", "echo hi", "--output", "json"]),
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
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
        mock_proc = _make_selector_mock_process(["secret output\n"])
        sel = _make_ready_selector()

        with (
            patch("sys.argv", ["ll-harness", "cmd", "echo secret output", "--verbose"]),
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
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
            "blanks:\n  - on_yes\n"
            "expected:\n  on_yes: done\n"
            "source_dsl: loop\n"
            "task_type: fill-in-the-blank\n"
            "source_file: loops/my-loop.yaml\n"
            "generated_at: 2026-06-11T00:00:00Z\n"
        )
        return p

    def _make_task_yaml_no_expected(self, tmp_path: Path, name: str = "task.yaml") -> Path:
        """BUG-3196: a task declaring no `expected:` — for tests not about grading."""
        p = tmp_path / name
        p.write_text(
            "prompt: Complete this FSM transition.\n"
            "blanks:\n  - on_yes\n"
            "source_dsl: loop\n"
            "task_type: fill-in-the-blank\n"
        )
        return p

    _ANSWER_JSON = '```json\n{"on_yes": "done"}\n```'

    def test_cmd_dsl_single_file_pass(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """Single task file with a matching answer object → exits 0 and prints pass-rate."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout=self._ANSWER_JSON),
            ),
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
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout=self._ANSWER_JSON),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 0
        out = capsys.readouterr().out
        assert "3/3" in out

    @pytest.mark.conformance
    def test_cmd_dsl_all_abstain_excludes_from_ci_and_exits_3(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """ENH-3185 AC9: an all-abstain DSL run excludes the denominator and exits 3.

        BUG-3196: uses the no-`expected:` fixture so this test keeps testing
        abstention (via --semantic alone), not `expected:` grading — the
        verdict payload's JSON object shares no keys with an `expected:`
        mapping and would otherwise grade UNPARSEABLE (AC2b).
        """
        task_file = self._make_task_yaml_no_expected(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file), semantic="some criterion")

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout=_llm_verdict("cannot_judge")),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 3
        out = capsys.readouterr().out
        assert "abstained" in out

    def test_cmd_dsl_partial_abstain_flips_pass_to_inconclusive(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC5c: >=1 abstention + >=1 graded pass + no failure/ungraded exits 3, not 0."""
        self._make_task_yaml_no_expected(tmp_path, "task-pass.yaml")
        self._make_task_yaml_no_expected(tmp_path, "task-abstain.yaml")
        args = _make_namespace(runner="dsl", path=str(tmp_path), semantic="some criterion")

        from little_loops.fsm.evaluators import EvaluationResult

        verdicts = iter(
            [
                EvaluationResult(verdict="yes", details={}),
                EvaluationResult(verdict="cannot_judge", details={}),
            ]
        )

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="anything")),
            patch(
                "little_loops.cli.harness.evaluate_llm_structured",
                side_effect=lambda **_kwargs: next(verdicts),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 3
        out = capsys.readouterr().out
        assert "1/1" in out

    def test_cmd_dsl_expected_mismatch_fails_and_reports_detail(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC1: a mismatched `expected` value fails and exits 1, reported distinguishably."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(
                    returncode=0, stdout='```json\n{"on_yes": "finish"}\n```'
                ),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "0/1" in out
        assert "on_yes" in out

    def test_cmd_dsl_unparseable_answer_counts_as_failure_in_denominator(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC2: no recoverable JSON object grades UNPARSEABLE, a failure in the denominator."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout="the answer is done"),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "0/1" in out
        assert "unparseable" in out

    def test_cmd_dsl_bare_brace_unrelated_json_grades_unparseable_not_mismatch(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC2b: a bare-brace object sharing no keys with `expected` is discarded, not read."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout=_llm_verdict("yes")),
            ),
        ):
            result = cmd_dsl(args)

        out = capsys.readouterr().out
        assert result == 1
        assert "unparseable" in out
        assert "mismatch" not in out

    def test_cmd_dsl_all_ungraded_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC3/AC5: a set with no `expected:` and no --semantic is wholly ungraded → exit 2."""
        task_file = self._make_task_yaml_no_expected(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="done")),
        ):
            result = cmd_dsl(args)

        assert result == 2
        out = capsys.readouterr().out
        assert "ungraded" in out

    def test_cmd_dsl_exit_code_flag_does_not_grade_ungraded_task(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC4: --exit-code alone does not make an `expected`-less task graded."""
        task_file = self._make_task_yaml_no_expected(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file), exit_code=0)

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="done")),
        ):
            result = cmd_dsl(args)

        assert result == 2
        out = capsys.readouterr().out
        assert "ungraded" in out

    def test_cmd_dsl_ungraded_ordered_before_abstain(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC5b: a mix of ungraded + abstained tasks reports the ungraded `2`, not `3`."""
        ungraded_file = self._make_task_yaml_no_expected(tmp_path, "task-ungraded.yaml")
        self._make_task_yaml_no_expected(tmp_path, "task-ungraded2.yaml")
        args = _make_namespace(runner="dsl", path=str(tmp_path))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="x")),
        ):
            result = cmd_dsl(args)

        assert result == 2
        assert ungraded_file.exists()

    def test_cmd_dsl_infra_error_excluded_and_exits_2(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC5d: a per-task timeout is excluded from the denominator and exits 2, not 'abstained'."""
        task_file = self._make_task_yaml_no_expected(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=120),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 2
        out = capsys.readouterr().out
        assert "abstained" not in out

    def test_cmd_dsl_malformed_yaml_grades_fail_and_run_continues(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC5e: unparseable task YAML grades FAIL; the remaining tasks in the set still run."""
        bad = tmp_path / "task-bad.yaml"
        bad.write_text("prompt: [unterminated\n")
        self._make_task_yaml(tmp_path, "task-good.yaml")
        args = _make_namespace(runner="dsl", path=str(tmp_path))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout=self._ANSWER_JSON),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "1/2" in out
        assert "malformed task file" in out

    def test_cmd_dsl_missing_prompt_key_grades_fail(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC5e: a task file with no `prompt:` key grades FAIL rather than raising."""
        bad = tmp_path / "task-bad.yaml"
        bad.write_text("expected:\n  on_yes: done\n")
        args = _make_namespace(runner="dsl", path=str(bad))

        result = cmd_dsl(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "malformed task file" in out

    def test_cmd_dsl_non_mapping_expected_grades_malformed(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC5e: `expected:` that is not a mapping grades malformed rather than raising."""
        p = tmp_path / "task.yaml"
        p.write_text("prompt: Do a thing.\nexpected:\n  - a\n  - b\n")
        args = _make_namespace(runner="dsl", path=str(p))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch("subprocess.run", return_value=_make_completed(returncode=0, stdout="a")),
        ):
            result = cmd_dsl(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "malformed" in out

    @pytest.mark.conformance
    def test_cmd_dsl_mismatch_outranks_abstain(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC6: an `expected` mismatch is a hard FAIL even when --semantic abstains."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file), semantic="some criterion")

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(
                    returncode=0, stdout='```json\n{"on_yes": "finish"}\n```'
                ),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 1
        out = capsys.readouterr().out
        assert "0/1" in out

    def test_cmd_dsl_expected_normalizes_whitespace_and_quotes(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC7: normalization strips whitespace and one layer of matching quotes."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(
                    returncode=0, stdout='```json\n{"on_yes": "  \\"done\\"  "}\n```'
                ),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 0

    def test_cmd_dsl_missing_key_is_mismatch_extra_key_ignored(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """AC8: a missing expected key is a mismatch; an extra answer key is not penalized."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout='```json\n{"extra": "x"}\n```'),
            ),
        ):
            result = cmd_dsl(args)

        assert result == 1

    def test_cmd_dsl_prompt_contains_no_python_list_repr(self, tmp_path: Path) -> None:
        """AC9: the generated prompt never contains a Python list repr like ['on_yes']."""
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))
        captured: dict[str, object] = {}

        def fake_build_blocking_json(*, prompt: str, **_: object) -> HostInvocation:
            captured["prompt"] = prompt
            return HostInvocation(binary="claude", args=[])

        fake_runner = FakeRunner()
        fake_runner.build_blocking_json = fake_build_blocking_json  # type: ignore[method-assign]

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=fake_runner),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout=self._ANSWER_JSON),
            ),
        ):
            cmd_dsl(args)

        assert "['on_yes']" not in str(captured["prompt"])

    @pytest.mark.conformance
    def test_cmd_dsl_task_row_records_host_exit_code_and_verdict(self, tmp_path: Path) -> None:
        """AC10/10a/10b: exactly one dsl-task row, with the host rc/timed_out/verdict."""
        from little_loops.session_store import recent

        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file), semantic="some criterion")

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=5, stdout=self._ANSWER_JSON),
            ),
        ):
            cmd_dsl(args)

        rows = recent(kind="harness", limit=20)
        dsl_task_rows = [r for r in rows if r["runner"] == "dsl-task"]
        prompt_rows = [r for r in rows if r["runner"] == "prompt"]
        assert len(dsl_task_rows) == 1
        assert dsl_task_rows[0]["exit_code"] == 5
        assert dsl_task_rows[0]["timed_out"] == 0
        assert not prompt_rows

    def test_cmd_dsl_aggregate_row_carries_run_outcome(self, tmp_path: Path) -> None:
        """AC11: the aggregate `dsl` row is updated with the run's outcome after the loop."""
        from little_loops.session_store import recent

        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout=self._ANSWER_JSON),
            ),
        ):
            cmd_dsl(args)

        rows = recent(kind="harness", limit=20)
        aggregate = next(r for r in rows if r["runner"] == "dsl")
        assert aggregate["exit_code"] == 0
        assert aggregate["semantic_passed"] == 1

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

    def test_cmd_dsl_per_task_never_reads_history_on_prompt_text(
        self, tmp_path: Path, capsys: pytest.CaptureFixture
    ) -> None:
        """ENH-3223 AC4: the per-task path must not query on `args.target` --
        inside `_evaluate_and_report()` that value is the raw prompt text, not
        `task_file.name`, the value actually written to `harness_events.target`.
        """
        task_file = self._make_task_yaml(tmp_path)
        args = _make_namespace(runner="dsl", path=str(task_file))

        with (
            patch("little_loops.runner_spec.resolve_host", return_value=FakeRunner()),
            patch(
                "subprocess.run",
                return_value=_make_completed(returncode=0, stdout=self._ANSWER_JSON),
            ),
            patch("little_loops.cli.harness._read_target_history") as mock_read,
        ):
            result = cmd_dsl(args)

        assert result == 0
        mock_read.assert_not_called()


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


# ---------------------------------------------------------------------------
# TestReadTargetHistory (ENH-3223)
# ---------------------------------------------------------------------------


class TestReadTargetHistory:
    """Tests for `_read_target_history()` — the historical rate reader."""

    def _seed(self, target: str, rows: list[dict]) -> None:
        from little_loops.session_store import (
            DEFAULT_DB_PATH,
            record_harness_event,
            resolve_history_db,
        )

        # Match the read path's DB resolution — the conftest isolates writes via
        # LL_HISTORY_DB, so DEFAULT_DB_PATH would land on the real .ll/history.db
        # while _read_target_history reads from the env-override temp path.
        db = resolve_history_db(DEFAULT_DB_PATH)
        for row in rows:
            record_harness_event(db, target=target, **row)

    def test_below_threshold_returns_none(self) -> None:
        """AC7: fewer than `_HISTORY_MIN_SCORED` scored rows -- suppressed entirely."""
        from little_loops.cli.harness import _HISTORY_MIN_SCORED, _read_target_history

        assert _HISTORY_MIN_SCORED > 2
        self._seed(
            "some-target",
            [
                {"ts": "2026-08-01T00:00:00Z", "runner": "cmd", "semantic_passed": True},
                {"ts": "2026-08-02T00:00:00Z", "runner": "cmd", "semantic_passed": True},
            ],
        )

        assert _read_target_history("some-target") is None

    def test_at_threshold_renders(self) -> None:
        """AC7: exactly `_HISTORY_MIN_SCORED` scored rows -- rendered, not suppressed."""
        from little_loops.cli.harness import _HISTORY_MIN_SCORED, _read_target_history

        now = datetime.now(UTC)
        self._seed(
            "some-target",
            [
                {
                    "ts": (now - timedelta(days=i)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "runner": "cmd",
                    "semantic_passed": True,
                }
                for i in range(1, _HISTORY_MIN_SCORED + 1)
            ],
        )

        history = _read_target_history("some-target")

        assert history is not None
        assert history["history_pass_rate"] == 1.0
        assert history["history_pass_rate_runs"] == _HISTORY_MIN_SCORED

    def test_distinct_denominators_for_pass_and_abstention(self) -> None:
        """AC5: pass-rate and abstention-rate denominators are different
        populations and must not collide under one key."""
        from little_loops.cli.harness import _read_target_history

        now = datetime.now(UTC)
        rows = []
        # Four semantically-judged rows (one abstained) -- feeds both counters.
        for i in range(4):
            verdict = "cannot_judge" if i == 0 else "yes"
            rows.append(
                {
                    "ts": (now - timedelta(days=i + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "runner": "cmd",
                    "semantic_verdict": verdict,
                    "semantic_passed": None if verdict == "cannot_judge" else True,
                }
            )
        # Three more exit-code-only rows (no --semantic) -- pass-rate only.
        for i in range(3):
            rows.append(
                {
                    "ts": (now - timedelta(days=i + 10)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "runner": "cmd",
                    "semantic_passed": True,
                }
            )
        self._seed("some-target", rows)

        history = _read_target_history("some-target")

        assert history is not None
        assert history["history_pass_rate_runs"] == 6  # 3 non-abstained judged + 3 exit-only
        assert history["history_judged_runs"] == 4
        assert history["history_pass_rate_runs"] != history["history_judged_runs"]
        assert abs(history["history_abstention_rate"] - 0.25) < 1e-9

    def test_window_excludes_old_rows(self) -> None:
        """AC6: rows older than the window are excluded from both rates."""
        from little_loops.cli.harness import _HISTORY_MIN_SCORED, _read_target_history

        rows = [
            {"ts": "2020-01-01T00:00:00Z", "runner": "cmd", "semantic_passed": False}
            for _ in range(_HISTORY_MIN_SCORED)
        ]
        rows += [
            {"ts": f"2026-08-1{i}T00:00:00Z", "runner": "cmd", "semantic_passed": True}
            for i in range(_HISTORY_MIN_SCORED)
        ]
        self._seed("some-target", rows)

        history = _read_target_history("some-target")

        assert history is not None
        assert history["history_pass_rate"] == 1.0  # old failing rows excluded
        assert history["history_pass_rate_runs"] == _HISTORY_MIN_SCORED

    def test_none_when_db_empty(self) -> None:
        from little_loops.cli.harness import _read_target_history

        assert _read_target_history("nonexistent-target") is None


# ---------------------------------------------------------------------------
# TestTargetHistoryRegression (ENH-3223 AC2)
# ---------------------------------------------------------------------------


class TestTargetHistoryRegression:
    """AC2: the current run's own row must not leak into its reported rate."""

    def test_current_run_excluded_from_reported_rate(self, capsys: pytest.CaptureFixture) -> None:
        from little_loops.fsm.evaluators import EvaluationResult
        from little_loops.session_store import DEFAULT_DB_PATH, record_harness_event, resolve_history_db

        target = "some-target"
        db = resolve_history_db(DEFAULT_DB_PATH)
        now = datetime.now(UTC)
        for i in range(3):
            record_harness_event(
                db,
                ts=(now - timedelta(days=i + 1)).strftime("%Y-%m-%dT%H:%M:%SZ"),
                runner="cmd",
                target=target,
                semantic_verdict="cannot_judge",
                semantic_passed=None,
            )

        args = _make_namespace(
            runner="cmd", target=target, output="json", semantic="some criterion"
        )
        mock_proc = _make_selector_mock_process(["hi\n"])
        sel = _make_ready_selector()

        with (
            patch("little_loops.runner_spec.subprocess.Popen", return_value=mock_proc),
            patch("little_loops.runner_spec.selectors.DefaultSelector", return_value=sel),
            patch(
                "little_loops.cli.harness.evaluate_llm_structured",
                return_value=EvaluationResult(verdict="cannot_judge", details={}),
            ),
        ):
            result = cmd_cmd(args)

        assert result == 3
        data = json.loads(capsys.readouterr().out)
        # The read happens before `_record_harness_event()` for this run -- if a
        # future refactor moved the write above the read, this would become 4.
        assert data["history_judged_runs"] == 3
        assert data["history_abstention_rate"] == 1.0

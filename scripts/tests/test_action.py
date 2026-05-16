"""Tests for little_loops.cli.action (ll-action CLI)."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.action import (
    _load_skills,
    _read_skill_description,
    cmd_capabilities,
    cmd_invoke,
    cmd_list,
    main_action,
)
from little_loops.host_runner import CapabilityReport, HostCapabilities, HostInvocation


class FakeRunner:
    """Test double for HostRunner; modeled on FakeCodex in test_host_runner.py."""

    name = "claude-code"
    capabilities = HostCapabilities()

    def __init__(self, detect_returns: bool = True) -> None:
        self._detect_returns = detect_returns

    def detect(self) -> bool:
        return self._detect_returns

    def build_streaming(self, **_: object) -> HostInvocation:
        return HostInvocation(binary="claude", args=[])

    def build_blocking_json(self, **_: object) -> HostInvocation:
        return HostInvocation(binary="claude", args=[])

    def build_version_check(self) -> HostInvocation:
        return HostInvocation(binary="claude", args=["--version"])

    def build_detached(self, **_: object) -> HostInvocation:
        return HostInvocation(binary="claude", args=[])

    def describe_capabilities(self) -> CapabilityReport:
        return CapabilityReport(host="fake", binary="fake", version="0.0")


# =============================================================================
# Helpers
# =============================================================================


def _make_completed(
    returncode: int = 0, stdout: str = "", stderr: str = ""
) -> subprocess.CompletedProcess:
    return subprocess.CompletedProcess(args=[], returncode=returncode, stdout=stdout, stderr=stderr)


def _make_namespace(**kwargs: Any) -> Any:
    import argparse

    return argparse.Namespace(**kwargs)


# =============================================================================
# _read_skill_description
# =============================================================================


class TestReadSkillDescription:
    def test_extracts_description(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text(
            '---\ndescription: "Refine an issue with codebase context"\nmodel: sonnet\n---\n# Content'
        )
        assert _read_skill_description(skill_md) == "Refine an issue with codebase context"

    def test_handles_unquoted_description(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\ndescription: Simple description\nmodel: sonnet\n---\n# Content")
        assert _read_skill_description(skill_md) == "Simple description"

    def test_returns_empty_when_no_frontmatter(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("# No frontmatter here")
        assert _read_skill_description(skill_md) == ""

    def test_returns_empty_when_no_description_key(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "SKILL.md"
        skill_md.write_text("---\nmodel: sonnet\n---\n# Content")
        assert _read_skill_description(skill_md) == ""

    def test_returns_empty_on_missing_file(self, tmp_path: Path) -> None:
        skill_md = tmp_path / "nonexistent.md"
        assert _read_skill_description(skill_md) == ""


# =============================================================================
# _load_skills
# =============================================================================


class TestLoadSkills:
    def test_discovers_skills_from_plugin_root(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills"
        for skill_name, desc in [
            ("refine-issue", "Refine"),
            ("confidence-check", "Check confidence"),
        ]:
            skill_dir = skills_dir / skill_name
            skill_dir.mkdir(parents=True)
            (skill_dir / "SKILL.md").write_text(f"---\ndescription: {desc}\n---\n")

        with patch("little_loops.cli.action._find_plugin_root", return_value=tmp_path):
            skills = _load_skills()

        assert len(skills) == 2
        names = [s["name"] for s in skills]
        assert "confidence-check" in names
        assert "refine-issue" in names

    def test_skill_dict_has_name_and_description(self, tmp_path: Path) -> None:
        skills_dir = tmp_path / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text('---\ndescription: "My skill desc"\n---\n')

        with patch("little_loops.cli.action._find_plugin_root", return_value=tmp_path):
            skills = _load_skills()

        assert skills == [{"name": "my-skill", "description": "My skill desc"}]

    def test_returns_empty_list_when_no_skills(self, tmp_path: Path) -> None:
        (tmp_path / "skills").mkdir()
        with patch("little_loops.cli.action._find_plugin_root", return_value=tmp_path):
            skills = _load_skills()
        assert skills == []


# =============================================================================
# cmd_invoke — stream-json mode
# =============================================================================


class TestCmdInvokeStreamJson:
    def test_emits_action_start_and_complete(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_namespace(
            skill="refine-issue", args=["P2-ENH-1229"], timeout=300, output="stream-json"
        )

        with patch(
            "little_loops.subprocess_utils.run_claude_command", return_value=_make_completed(0)
        ):
            result = cmd_invoke(args)

        assert result == 0
        captured = capsys.readouterr().out.strip().splitlines()
        events = [json.loads(line) for line in captured]
        assert events[0]["event"] == "action_start"
        assert events[0]["skill"] == "refine-issue"
        assert events[0]["args"] == ["P2-ENH-1229"]
        assert events[-1]["event"] == "action_complete"
        assert events[-1]["exit_code"] == 0

    def test_emits_action_output_per_line(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_namespace(skill="refine-issue", args=[], timeout=300, output="stream-json")

        def fake_run(command, timeout, stream_callback, **kwargs):
            stream_callback("line one", False)
            stream_callback("line two", False)
            stream_callback("stderr line", True)  # should be suppressed
            return _make_completed(0)

        with patch("little_loops.subprocess_utils.run_claude_command", side_effect=fake_run):
            cmd_invoke(args)

        events = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
        output_events = [e for e in events if e["event"] == "action_output"]
        assert len(output_events) == 2
        assert output_events[0]["line"] == "line one"
        assert output_events[1]["line"] == "line two"

    def test_forwards_timeout_to_run_claude_command(self) -> None:
        args = _make_namespace(
            skill="confidence-check", args=["FEAT-042"], timeout=120, output="stream-json"
        )

        with patch(
            "little_loops.subprocess_utils.run_claude_command", return_value=_make_completed(0)
        ) as mock_run:
            cmd_invoke(args)

        call_kwargs = mock_run.call_args
        assert call_kwargs.kwargs["timeout"] == 120

    def test_command_includes_skill_and_args(self) -> None:
        args = _make_namespace(
            skill="refine-issue", args=["P2", "ENH-100"], timeout=300, output="stream-json"
        )

        with patch(
            "little_loops.subprocess_utils.run_claude_command", return_value=_make_completed(0)
        ) as mock_run:
            cmd_invoke(args)

        command = mock_run.call_args.kwargs["command"]
        assert command == "/ll:refine-issue P2 ENH-100"

    def test_command_no_args(self) -> None:
        args = _make_namespace(skill="refine-issue", args=[], timeout=300, output="stream-json")

        with patch(
            "little_loops.subprocess_utils.run_claude_command", return_value=_make_completed(0)
        ) as mock_run:
            cmd_invoke(args)

        command = mock_run.call_args.kwargs["command"]
        assert command == "/ll:refine-issue"

    def test_timeout_returns_exit_code_124(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_namespace(skill="refine-issue", args=[], timeout=1, output="stream-json")

        with patch(
            "little_loops.subprocess_utils.run_claude_command",
            side_effect=subprocess.TimeoutExpired("claude", 1),
        ):
            result = cmd_invoke(args)

        assert result == 124
        events = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
        complete = next(e for e in events if e["event"] == "action_complete")
        assert complete["exit_code"] == 124

    def test_nonzero_exit_code_propagated(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_namespace(skill="refine-issue", args=[], timeout=300, output="stream-json")

        with patch(
            "little_loops.subprocess_utils.run_claude_command", return_value=_make_completed(1)
        ):
            result = cmd_invoke(args)

        assert result == 1
        events = [json.loads(line) for line in capsys.readouterr().out.strip().splitlines()]
        complete = next(e for e in events if e["event"] == "action_complete")
        assert complete["exit_code"] == 1


# =============================================================================
# cmd_invoke — json mode
# =============================================================================


class TestCmdInvokeJsonMode:
    def test_returns_single_json_object(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_namespace(
            skill="refine-issue", args=["P2-ENH-1229"], timeout=300, output="json"
        )

        def fake_run(command, timeout, stream_callback, **kwargs):
            stream_callback("output line 1", False)
            stream_callback("output line 2", False)
            return _make_completed(0)

        with patch("little_loops.subprocess_utils.run_claude_command", side_effect=fake_run):
            result = cmd_invoke(args)

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["exit_code"] == 0
        assert "output line 1" in output["output"]
        assert "output line 2" in output["output"]
        assert output["error"] is None

    def test_captures_stderr_in_error_field(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_namespace(skill="refine-issue", args=[], timeout=300, output="json")

        def fake_run(command, timeout, stream_callback, **kwargs):
            stream_callback("err msg", True)
            return _make_completed(1)

        with patch("little_loops.subprocess_utils.run_claude_command", side_effect=fake_run):
            cmd_invoke(args)

        output = json.loads(capsys.readouterr().out)
        assert output["error"] == "err msg"
        assert output["exit_code"] == 1

    def test_timeout_json_mode(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_namespace(skill="refine-issue", args=[], timeout=1, output="json")

        with patch(
            "little_loops.subprocess_utils.run_claude_command",
            side_effect=subprocess.TimeoutExpired("claude", 1),
        ):
            result = cmd_invoke(args)

        assert result == 124
        output = json.loads(capsys.readouterr().out)
        assert output["exit_code"] == 124


# =============================================================================
# cmd_capabilities
# =============================================================================


class TestCmdCapabilities:
    def test_emits_full_capability_report(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        args = _make_namespace(output="json")

        mock_version = MagicMock()
        mock_version.stdout = "claude 1.0.3\n"

        with (
            patch(
                "little_loops.cli.action.resolve_host", return_value=FakeRunner(detect_returns=True)
            ),
            patch("little_loops.cli.action.subprocess.run", return_value=mock_version),
        ):
            result = cmd_capabilities(args)

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["host"] == "fake"
        assert output["binary"] == "fake"
        assert output["version"] == "claude 1.0.3"
        assert isinstance(output["capabilities"], list)
        assert isinstance(output["hooks"], list)

    def test_version_empty_when_host_unavailable(
        self, capsys: pytest.CaptureFixture
    ) -> None:
        args = _make_namespace(output="json")

        with (
            patch(
                "little_loops.cli.action.resolve_host",
                return_value=FakeRunner(detect_returns=False),
            ),
        ):
            result = cmd_capabilities(args)

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["host"] == "fake"
        assert output["version"] == ""

    def test_version_empty_on_timeout(self, capsys: pytest.CaptureFixture) -> None:
        args = _make_namespace(output="json")

        with (
            patch(
                "little_loops.cli.action.resolve_host", return_value=FakeRunner(detect_returns=True)
            ),
            patch(
                "little_loops.cli.action.subprocess.run",
                side_effect=subprocess.TimeoutExpired("claude", 10),
            ),
        ):
            result = cmd_capabilities(args)

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output["version"] == ""


# =============================================================================
# cmd_list
# =============================================================================


class TestCmdList:
    def test_returns_skill_list(self, capsys: pytest.CaptureFixture, tmp_path: Path) -> None:
        args = _make_namespace(output="json")
        skills_dir = tmp_path / "skills" / "my-skill"
        skills_dir.mkdir(parents=True)
        (skills_dir / "SKILL.md").write_text('---\ndescription: "My skill"\n---\n')

        with patch("little_loops.cli.action._find_plugin_root", return_value=tmp_path):
            result = cmd_list(args)

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output == [{"name": "my-skill", "description": "My skill"}]

    def test_returns_empty_list_when_no_skills(
        self, capsys: pytest.CaptureFixture, tmp_path: Path
    ) -> None:
        args = _make_namespace(output="json")
        (tmp_path / "skills").mkdir()

        with patch("little_loops.cli.action._find_plugin_root", return_value=tmp_path):
            result = cmd_list(args)

        assert result == 0
        output = json.loads(capsys.readouterr().out)
        assert output == []


# =============================================================================
# main_action — entry-point pattern
# =============================================================================


class TestMainAction:
    def test_invoke_subcommand_dispatch(self) -> None:
        with (
            patch.object(
                sys, "argv", ["ll-action", "invoke", "refine-issue", "--args", "P2-ENH-1229"]
            ),
            patch(
                "little_loops.subprocess_utils.run_claude_command", return_value=_make_completed(0)
            ),
        ):
            result = main_action()

        assert result == 0

    def test_capabilities_subcommand_dispatch(self) -> None:
        mock_version = MagicMock()
        mock_version.stdout = "claude 1.0.3\n"

        with (
            patch.object(sys, "argv", ["ll-action", "capabilities"]),
            patch(
                "little_loops.cli.action.resolve_host", return_value=FakeRunner(detect_returns=True)
            ),
            patch("little_loops.cli.action.subprocess.run", return_value=mock_version),
        ):
            result = main_action()

        assert result == 0

    def test_list_subcommand_dispatch(self, tmp_path: Path) -> None:
        (tmp_path / "skills").mkdir()

        with (
            patch.object(sys, "argv", ["ll-action", "list"]),
            patch("little_loops.cli.action._find_plugin_root", return_value=tmp_path),
        ):
            result = main_action()

        assert result == 0

    def test_no_subcommand_exits_with_error(self) -> None:
        with (
            patch.object(sys, "argv", ["ll-action"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main_action()

        assert exc_info.value.code != 0

    def test_invoke_with_timeout_flag(self) -> None:
        with (
            patch.object(
                sys, "argv", ["ll-action", "invoke", "confidence-check", "--timeout", "60"]
            ),
            patch(
                "little_loops.subprocess_utils.run_claude_command", return_value=_make_completed(0)
            ) as mock_run,
        ):
            main_action()

        assert mock_run.call_args.kwargs["timeout"] == 60

    def test_invoke_json_output_flag(self, capsys: pytest.CaptureFixture) -> None:
        with (
            patch.object(sys, "argv", ["ll-action", "invoke", "refine-issue", "--output", "json"]),
            patch(
                "little_loops.subprocess_utils.run_claude_command", return_value=_make_completed(0)
            ),
        ):
            main_action()

        output = json.loads(capsys.readouterr().out)
        assert "exit_code" in output
        assert "duration_ms" in output

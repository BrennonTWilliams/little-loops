"""Tests for cli/doctor.py - ll-doctor CLI entry point."""

from __future__ import annotations

import json
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.doctor import main_doctor
from little_loops.host_runner import CapabilityEntry, CapabilityReport, HookEntry


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear host env vars so tests start from a known state."""
    monkeypatch.delenv("LL_HOST_CLI", raising=False)
    monkeypatch.delenv("LL_HOOK_HOST", raising=False)
    yield


def _make_runner(report: CapabilityReport) -> MagicMock:
    runner = MagicMock()
    runner.describe_capabilities.return_value = report
    return runner


def _capture_print() -> tuple[list[str], object]:
    """Return (lines, side_effect) for capturing print() calls including no-arg ones."""
    lines: list[str] = []
    return lines, lambda *a: lines.append(str(a[0]) if a else "")


class TestMainDoctor:
    """Tests for main_doctor entry point."""

    def test_exit_zero_when_all_capabilities_supported(self) -> None:
        """Returns 0 when no capabilities have status 'unsupported'."""
        report = CapabilityReport(
            host="claude-code",
            binary="claude",
            version="",
            capabilities=[
                CapabilityEntry("streaming", "full"),
                CapabilityEntry("permission_skip", "full"),
            ],
        )
        runner = _make_runner(report)

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print"),
        ):
            result = main_doctor()

        assert result == 0

    def test_exit_one_when_critical_capability_missing(self) -> None:
        """Returns 1 when any capability status is 'unsupported'."""
        report = CapabilityReport(
            host="codex",
            binary="codex",
            version="",
            capabilities=[
                CapabilityEntry("streaming", "full"),
                CapabilityEntry("agent_select", "unsupported", "codex lacks agent selection"),
            ],
        )
        runner = _make_runner(report)

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print"),
        ):
            result = main_doctor()

        assert result == 1

    def test_partial_capability_does_not_trigger_exit_one(self) -> None:
        """Returns 0 when capabilities are 'partial' but none are 'unsupported'."""
        report = CapabilityReport(
            host="opencode",
            binary="opencode",
            version="",
            capabilities=[
                CapabilityEntry("streaming", "partial", "limited streaming"),
            ],
        )
        runner = _make_runner(report)

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print"),
        ):
            result = main_doctor()

        assert result == 0

    def test_empty_capabilities_returns_zero(self) -> None:
        """Returns 0 when the capabilities list is empty (no critical gaps)."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print"),
        ):
            result = main_doctor()

        assert result == 0

    def test_text_output_shows_host_info(self) -> None:
        """Text output includes host name and binary."""
        report = CapabilityReport(
            host="claude-code",
            binary="claude",
            version="",
            capabilities=[],
        )
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        output = "\n".join(lines)
        assert "claude-code" in output
        assert "claude" in output

    def test_empty_version_shown_as_unknown(self) -> None:
        """Empty version string is displayed as '(unknown)' in text output."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        output = "\n".join(lines)
        assert "(unknown)" in output

    def test_status_symbols_in_text_output(self) -> None:
        """Text output uses ✓/✗/○ symbols for full/unsupported/partial statuses."""
        report = CapabilityReport(
            host="codex",
            binary="codex",
            version="",
            capabilities=[
                CapabilityEntry("streaming", "full"),
                CapabilityEntry("permission_skip", "partial"),
                CapabilityEntry("agent_select", "unsupported"),
            ],
        )
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        output = "\n".join(lines)
        assert "✓" in output
        assert "○" in output
        assert "✗" in output

    def test_capability_note_appears_in_text_output(self) -> None:
        """Capability note text is included alongside the status symbol."""
        report = CapabilityReport(
            host="codex",
            binary="codex",
            version="",
            capabilities=[
                CapabilityEntry("json_schema", "unsupported", "no inline schema flag"),
            ],
        )
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        output = "\n".join(lines)
        assert "no inline schema flag" in output

    def test_hooks_section_printed_when_hooks_present(self) -> None:
        """Text output includes hooks section when hooks are present."""
        report = CapabilityReport(
            host="claude-code",
            binary="claude",
            version="",
            capabilities=[],
            hooks=[
                HookEntry("pre_tool_use", "installed"),
                HookEntry("post_tool_use", "absent"),
            ],
        )
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        output = "\n".join(lines)
        assert "pre_tool_use" in output
        assert "post_tool_use" in output

    def test_json_output_flag(self) -> None:
        """--json flag outputs valid JSON with host, capabilities, and hooks keys."""
        report = CapabilityReport(
            host="claude-code",
            binary="claude",
            version="",
            capabilities=[CapabilityEntry("streaming", "full")],
            hooks=[],
        )
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print", side_effect=side_effect),
        ):
            result = main_doctor()

        assert result == 0
        data = json.loads("\n".join(lines))
        assert data["host"] == "claude-code"
        assert data["binary"] == "claude"
        assert len(data["capabilities"]) == 1
        assert data["capabilities"][0]["name"] == "streaming"
        assert data["capabilities"][0]["status"] == "full"
        assert "hooks" in data

    def test_json_short_flag(self) -> None:
        """-j is accepted as shorthand for --json."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "-j"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        data = json.loads("\n".join(lines))
        assert "host" in data

    def test_json_version_fallback_to_unknown(self) -> None:
        """JSON output shows '(unknown)' when version is empty."""
        report = CapabilityReport(host="codex", binary="codex", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        data = json.loads("\n".join(lines))
        assert data["version"] == "(unknown)"

    def test_json_unsupported_capability_still_returns_exit_one(self) -> None:
        """Exit code 1 applies even when --json mode is active."""
        report = CapabilityReport(
            host="codex",
            binary="codex",
            version="",
            capabilities=[CapabilityEntry("agent_select", "unsupported")],
        )
        runner = _make_runner(report)

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print"),
        ):
            result = main_doctor()

        assert result == 1

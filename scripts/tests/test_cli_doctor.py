"""Tests for cli/doctor.py - ll-doctor CLI entry point."""

from __future__ import annotations

import json
import subprocess
from collections.abc import Iterator
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.doctor import main_doctor
from little_loops.host_runner import (
    CapabilityEntry,
    CapabilityReport,
    ClaudeCodeRunner,
    HostInvocation,
    HostNotConfigured,
)


@pytest.fixture
def isolated_env(monkeypatch: pytest.MonkeyPatch) -> Iterator[None]:
    """Clear host env vars so tests start from a known state."""
    monkeypatch.delenv("LL_HOST_CLI", raising=False)
    monkeypatch.delenv("LL_HOOK_HOST", raising=False)
    yield


def _make_runner(report: CapabilityReport) -> MagicMock:
    runner = MagicMock()
    runner.describe_capabilities.return_value = report
    runner.detect.return_value = False
    return runner


def _capture_print() -> tuple[list[str], object]:
    """Return (lines, side_effect) for capturing print() calls including no-arg ones."""
    lines: list[str] = []
    return lines, lambda *a: lines.append(str(a[0]) if a else "")


def _json_safe_config() -> MagicMock:
    """A BRConfig mock whose analytics_capture/issues fields are JSON-serializable."""
    mock_config = MagicMock()
    mock_config.analytics_capture.skills = ["*"]
    mock_config.analytics_capture.cli_commands = ["*"]
    mock_config.analytics_capture.corrections = True
    mock_config.analytics_capture.file_events = True
    mock_config.analytics_capture.correction_patterns = []
    mock_config.issues.auto_commit = False
    mock_config.issues.auto_commit_prefix = "chore(issues)"
    return mock_config


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

    def test_exit_zero_on_real_claude_code_report(self) -> None:
        """BUG-2759: ll-doctor must exit 0 for a healthy claude-code host — a
        hand-built fixture can't reproduce a stale-entry regression like the
        json_schema/structured_output contradiction, so this exercises the
        real ClaudeCodeRunner.describe_capabilities() output directly."""
        runner = ClaudeCodeRunner()

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig"),
            patch("builtins.print"),
        ):
            result = main_doctor()

        assert result == 0

    def test_advisory_capability_unsupported_does_not_fail(self) -> None:
        """An unsupported *advisory* capability is reported but must not fail
        the exit code. claude_md_suppression is an optimization, not a
        correctness requirement — claude-code honestly reports it unsupported
        (the CLI has no flag to skip CLAUDE.md), and that must not make the
        primary host fail its own health check."""
        report = CapabilityReport(
            host="claude-code",
            binary="claude",
            version="",
            capabilities=[
                CapabilityEntry("streaming", "full"),
                CapabilityEntry("claude_md_suppression", "unsupported", "no flag exists"),
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

    def test_claude_md_suppression_reported_unsupported(self) -> None:
        """The claude CLI exposes no flag that skips CLAUDE.md, so the
        capability must report 'unsupported'. It was previously 'full' on the
        grounds that the LL_AUTOMATION env signal is honored — but that signal
        only prunes our own hook output, a different and much smaller thing.
        Reporting 'full' made ll-doctor claim a capability the host lacks."""
        entries = {c.name: c for c in ClaudeCodeRunner().describe_capabilities().capabilities}
        assert entries["claude_md_suppression"].status == "unsupported"

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

    def test_json_output_flag(self) -> None:
        """--json flag outputs valid JSON with host and capabilities keys."""
        report = CapabilityReport(
            host="claude-code",
            binary="claude",
            version="",
            capabilities=[CapabilityEntry("streaming", "full")],
        )
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
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
        # BUG-2760: the never-populated ``hooks`` key was removed entirely.
        assert "hooks" not in data

    def test_json_short_flag(self) -> None:
        """-j is accepted as shorthand for --json."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "-j"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
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
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
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
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
            patch("builtins.print"),
        ):
            result = main_doctor()

        assert result == 1

    def test_json_output_includes_analytics_capture_and_issues_sections(self) -> None:
        """--json is a superset of text output: analytics_capture/issues keys (ENH-2762)."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        mock_config = MagicMock()
        mock_config.analytics_capture.skills = ["*"]
        mock_config.analytics_capture.cli_commands = ["*"]
        mock_config.analytics_capture.corrections = True
        mock_config.analytics_capture.file_events = False
        mock_config.analytics_capture.correction_patterns = ["fix:", "wrong"]
        mock_config.issues.auto_commit = True
        mock_config.issues.auto_commit_prefix = "chore(issues)"

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=mock_config),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        data = json.loads("\n".join(lines))
        assert data["analytics_capture"] == {
            "skills": ["*"],
            "cli_commands": ["*"],
            "corrections": True,
            "file_events": False,
            "correction_patterns": ["fix:", "wrong"],
        }
        assert data["issues"] == {
            "auto_commit": True,
            "auto_commit_prefix": "chore(issues)",
        }

    def test_analytics_capture_section_all_enabled(self) -> None:
        """Analytics Capture section appears with ✓ symbols when all fields enabled."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        mock_config = MagicMock()
        mock_config.analytics_capture.skills = ["*"]
        mock_config.analytics_capture.cli_commands = ["*"]
        mock_config.analytics_capture.corrections = True
        mock_config.analytics_capture.file_events = True

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=mock_config),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        output = "\n".join(lines)
        assert "Analytics Capture" in output
        assert "corrections" in output
        assert "file_events" in output
        assert "enabled" in output

    def test_analytics_capture_section_file_events_disabled(self) -> None:
        """Analytics Capture section shows ✗ for file_events when disabled."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        mock_config = MagicMock()
        mock_config.analytics_capture.skills = ["*"]
        mock_config.analytics_capture.cli_commands = ["*"]
        mock_config.analytics_capture.corrections = True
        mock_config.analytics_capture.file_events = False

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=mock_config),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        output = "\n".join(lines)
        assert "Analytics Capture" in output
        assert "✗" in output
        assert "disabled" in output

    def test_issues_auto_commit_section_enabled(self) -> None:
        """Issues section shows ✓ and 'enabled' when auto_commit is True."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        mock_config = MagicMock()
        mock_config.analytics_capture.skills = ["*"]
        mock_config.analytics_capture.cli_commands = ["*"]
        mock_config.analytics_capture.corrections = True
        mock_config.analytics_capture.file_events = True
        mock_config.issues.auto_commit = True
        mock_config.issues.auto_commit_prefix = "chore(issues)"

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=mock_config),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        output = "\n".join(lines)
        assert "Issues" in output
        assert "auto_commit" in output
        assert "enabled" in output
        assert "✓" in output

    def test_issues_auto_commit_section_disabled(self) -> None:
        """Issues section shows ✗ and 'disabled' when auto_commit is False."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        lines, side_effect = _capture_print()

        mock_config = MagicMock()
        mock_config.analytics_capture.skills = ["*"]
        mock_config.analytics_capture.cli_commands = ["*"]
        mock_config.analytics_capture.corrections = True
        mock_config.analytics_capture.file_events = True
        mock_config.issues.auto_commit = False
        mock_config.issues.auto_commit_prefix = "chore(issues)"

        with (
            patch("sys.argv", ["ll-doctor"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=mock_config),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        output = "\n".join(lines)
        assert "Issues" in output
        assert "auto_commit" in output
        assert "disabled" in output
        assert "✗" in output


class TestVersionProbe:
    """Tests for the build_version_check() probe wired into main_doctor (ENH-2761)."""

    def test_probes_version_when_binary_detected(self) -> None:
        """A detected binary is probed and its output populates the version field."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        runner.detect.return_value = True
        runner.build_version_check.return_value = HostInvocation(
            binary="claude", args=["--version"]
        )
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
            patch("builtins.print", side_effect=side_effect),
            patch(
                "little_loops.cli.doctor.subprocess.run",
                return_value=MagicMock(stdout="2.1.0\n"),
            ),
        ):
            main_doctor()

        data = json.loads("\n".join(lines))
        assert data["version"] == "2.1.0"

    def test_skips_probe_when_binary_not_detected(self) -> None:
        """detect() returning False skips the subprocess probe entirely."""
        report = CapabilityReport(host="codex", binary="codex", version="", capabilities=[])
        runner = _make_runner(report)
        runner.detect.return_value = False
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
            patch("builtins.print", side_effect=side_effect),
            patch("little_loops.cli.doctor.subprocess.run") as mock_run,
        ):
            main_doctor()

        mock_run.assert_not_called()
        data = json.loads("\n".join(lines))
        assert data["version"] == "(unknown)"

    def test_probe_timeout_falls_back_to_unknown(self) -> None:
        """A subprocess timeout degrades to '(unknown)' rather than crashing."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        runner.detect.return_value = True
        runner.build_version_check.return_value = HostInvocation(
            binary="claude", args=["--version"]
        )
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
            patch("builtins.print", side_effect=side_effect),
            patch(
                "little_loops.cli.doctor.subprocess.run",
                side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=10),
            ),
        ):
            main_doctor()

        data = json.loads("\n".join(lines))
        assert data["version"] == "(unknown)"

    def test_probe_failing_binary_falls_back_to_unknown(self) -> None:
        """An OSError/FileNotFoundError from the probe degrades to '(unknown)'."""
        report = CapabilityReport(host="claude-code", binary="claude", version="", capabilities=[])
        runner = _make_runner(report)
        runner.detect.return_value = True
        runner.build_version_check.return_value = HostInvocation(
            binary="claude", args=["--version"]
        )
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
            patch("builtins.print", side_effect=side_effect),
            patch(
                "little_loops.cli.doctor.subprocess.run",
                side_effect=FileNotFoundError("claude not found"),
            ),
        ):
            main_doctor()

        data = json.loads("\n".join(lines))
        assert data["version"] == "(unknown)"

    def test_probe_host_not_configured_falls_back_to_unknown(self) -> None:
        """build_version_check() raising HostNotConfigured degrades to '(unknown)'."""
        report = CapabilityReport(host="opencode", binary="opencode", version="", capabilities=[])
        runner = _make_runner(report)
        runner.detect.return_value = True
        runner.build_version_check.side_effect = HostNotConfigured("opencode has no version check")
        lines, side_effect = _capture_print()

        with (
            patch("sys.argv", ["ll-doctor", "--json"]),
            patch("little_loops.host_runner.resolve_host", return_value=runner),
            patch("little_loops.host_runner.apply_host_cli_from_config"),
            patch("little_loops.config.BRConfig", return_value=_json_safe_config()),
            patch("builtins.print", side_effect=side_effect),
        ):
            main_doctor()

        data = json.loads("\n".join(lines))
        assert data["version"] == "(unknown)"


class TestCheckRegistry:
    """Tests for the CheckResult / _CHECKS check-registry protocol (FEAT-2793)."""

    def test_capability_check_results_mirror_report_entries(self) -> None:
        """_capability_check_results() converts capabilities to error-severity CheckResults."""
        from little_loops.cli.doctor import CheckResult, _capability_check_results

        report = CapabilityReport(
            host="claude-code",
            binary="claude",
            version="",
            capabilities=[
                CapabilityEntry("streaming", "full"),
                CapabilityEntry("agent_select", "unsupported", "no support"),
            ],
        )

        results = _capability_check_results(report)

        assert results == [
            CheckResult(name="streaming", status="full", note="", severity="error"),
            CheckResult(
                name="agent_select", status="unsupported", note="no support", severity="error"
            ),
        ]

    def test_register_check_appends_and_runs(self) -> None:
        """register_check() adds a callable that _run_registered_checks() invokes."""
        from little_loops.cli import doctor
        from little_loops.cli.doctor import CheckResult, _run_registered_checks, register_check

        original = list(doctor._CHECKS)
        try:
            doctor._CHECKS.clear()
            register_check(lambda: [CheckResult(name="fake_check", status="full", note="ok")])

            results = _run_registered_checks()

            assert results == [CheckResult(name="fake_check", status="full", note="ok")]
        finally:
            doctor._CHECKS.clear()
            doctor._CHECKS.extend(original)

    def test_exit_code_ignores_informational_unsupported(self) -> None:
        """An 'informational' severity result never flips the exit code, even if unsupported."""
        from little_loops.cli.doctor import CheckResult, _exit_code_for

        results = [
            CheckResult(name="optional_subsystem", status="unsupported", severity="informational"),
        ]

        assert _exit_code_for(results) == 0

    def test_exit_code_flips_on_error_unsupported(self) -> None:
        """An 'error' severity 'unsupported' result flips the exit code to 1."""
        from little_loops.cli.doctor import CheckResult, _exit_code_for

        assert _exit_code_for([CheckResult(name="core", status="unsupported")]) == 1

    def test_mixed_severity_registered_check_affects_exit_code_via_main_doctor(self) -> None:
        """A registered error-tier unsupported check flips main_doctor()'s exit code to 1
        even when the host-capability report itself is fully supported — mirrors
        cmd_validate()'s mixed-severity folding (test_ll_loop_commands.py)."""
        from little_loops.cli import doctor
        from little_loops.cli.doctor import CheckResult, register_check

        report = CapabilityReport(
            host="claude-code",
            binary="claude",
            version="",
            capabilities=[CapabilityEntry("streaming", "full")],
        )
        runner = _make_runner(report)

        original = list(doctor._CHECKS)
        try:
            doctor._CHECKS.clear()
            register_check(
                lambda: [
                    CheckResult(
                        name="informational_gap", status="unsupported", severity="informational"
                    ),
                    CheckResult(name="broken_install", status="unsupported", severity="error"),
                ]
            )

            with (
                patch("sys.argv", ["ll-doctor"]),
                patch("little_loops.host_runner.resolve_host", return_value=runner),
                patch("little_loops.host_runner.apply_host_cli_from_config"),
                patch("little_loops.config.BRConfig"),
                patch("builtins.print"),
            ):
                result = main_doctor()

            assert result == 1
        finally:
            doctor._CHECKS.clear()
            doctor._CHECKS.extend(original)

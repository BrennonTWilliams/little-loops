"""Tests for ll-history CLI subcommands.

Focuses on coverage NOT already in test_issue_history_cli.py:
- root subcommand (completely untested)
- analyze --format yaml routing
- sessions --json edge case
- export stdout mode

Note: imports inside main_history() are function-local, so mocking goes to
source modules (little_loops.issue_history.*, little_loops.history_reader.*),
NOT to little_loops.cli.history.*.
"""

from __future__ import annotations

import json
import sys
from datetime import date
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.history import main_history


def _make_empty_analysis():
    """Build a minimal HistoryAnalysis for mocking calculate_analysis."""
    from little_loops.issue_history import HistoryAnalysis, HistorySummary

    return HistoryAnalysis(
        generated_date=date(2026, 1, 1),
        total_completed=0,
        total_active=0,
        date_range_start=None,
        date_range_end=None,
        summary=HistorySummary(total_count=0),
    )


# ---------------------------------------------------------------------------
# root subcommand
# ---------------------------------------------------------------------------


class TestHistoryRootSubcommand:
    """Tests for ll-history root subcommand (completely untested elsewhere)."""

    def test_root_no_db_returns_1(self, tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
        """root returns 1 when no DB or no root node found."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        with patch.object(sys, "argv", ["ll-history", "root"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1
        captured = capsys.readouterr()
        assert "No project-root summary node found" in captured.out

    def test_root_missing_db_still_returns_1(self, tmp_path: Path) -> None:
        """root returns 1 when .ll/history.db does not exist."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        with patch.object(sys, "argv", ["ll-history", "root"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1

    def test_root_json_flag_accepted_returns_1_without_db(self, tmp_path: Path) -> None:
        """--json flag is accepted and returns 1 gracefully when no DB."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        with patch.object(sys, "argv", ["ll-history", "root", "--json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1

    def test_root_expand_flag_accepted(self, tmp_path: Path) -> None:
        """--expand flag is accepted without crashing."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        with patch.object(sys, "argv", ["ll-history", "root", "--expand"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1

    def test_root_limit_flag_accepted(self, tmp_path: Path) -> None:
        """--limit flag is accepted without crashing."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        with patch.object(sys, "argv", ["ll-history", "root", "--limit", "5"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1


# ---------------------------------------------------------------------------
# analyze subcommand — yaml format routing
# ---------------------------------------------------------------------------


class TestHistoryAnalyzeYaml:
    """Test analyze --format yaml routing (yaml not heavily tested elsewhere)."""

    def test_analyze_yaml_calls_format_yaml_function(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        # Imports inside main_history are function-local → mock at source module
        with patch.object(
            sys, "argv", ["ll-history", "analyze", "--format", "yaml", "-d", str(issues_dir)]
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    with patch(
                        "little_loops.issue_history.calculate_analysis",
                        return_value=_make_empty_analysis(),
                    ):
                        with patch("little_loops.issue_history.format_analysis_yaml") as mock_fmt:
                            mock_fmt.return_value = "analysis: empty\n"
                            result = main_history()

        assert result == 0
        mock_fmt.assert_called_once()
        captured = capsys.readouterr()
        assert "analysis: empty" in captured.out

    def test_analyze_yaml_exit_code_zero(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        with patch.object(
            sys, "argv", ["ll-history", "analyze", "--format", "yaml", "-d", str(issues_dir)]
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    with patch(
                        "little_loops.issue_history.calculate_analysis",
                        return_value=_make_empty_analysis(),
                    ):
                        result = main_history()

        assert result == 0


# ---------------------------------------------------------------------------
# sessions subcommand — json output
# ---------------------------------------------------------------------------


class TestHistorySessionsJson:
    """Test sessions subcommand --json flag."""

    def test_sessions_json_empty_returns_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        with patch.object(sys, "argv", ["ll-history", "sessions", "ENH-999", "--json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                # sessions_for_issue is from little_loops.history_reader
                with patch("little_loops.history_reader.sessions_for_issue", return_value=[]):
                    result = main_history()
        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert isinstance(data, list)
        assert data == []

    def test_sessions_no_match_text_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        with patch.object(sys, "argv", ["ll-history", "sessions", "ENH-999"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.history_reader.sessions_for_issue", return_value=[]):
                    result = main_history()
        assert result == 0
        captured = capsys.readouterr()
        assert "No sessions found" in captured.out


# ---------------------------------------------------------------------------
# export subcommand — stdout mode
# ---------------------------------------------------------------------------


class TestHistoryExportStdout:
    """Test export subcommand output to stdout."""

    def test_export_prints_to_stdout(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        with patch.object(
            sys,
            "argv",
            ["ll-history", "export", "testing", "-d", str(issues_dir)],
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    with patch(
                        "little_loops.issue_history.synthesize_docs",
                        return_value="# Doc output\n",
                    ):
                        result = main_history()
        assert result == 0
        captured = capsys.readouterr()
        assert "# Doc output" in captured.out

    def test_export_empty_issues_exits_zero(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir()

        with patch.object(
            sys, "argv", ["ll-history", "export", "some-topic", "-d", str(issues_dir)]
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    result = main_history()
        assert result == 0

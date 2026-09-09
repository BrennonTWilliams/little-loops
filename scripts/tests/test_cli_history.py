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
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "root"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1
        captured = capsys.readouterr()
        assert "No project-root summary node found" in captured.out

    def test_root_missing_db_still_returns_1(self, tmp_path: Path) -> None:
        """root returns 1 when .ll/history.db does not exist."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "root"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1

    def test_root_json_flag_accepted_returns_1_without_db(self, tmp_path: Path) -> None:
        """--json flag is accepted and returns 1 gracefully when no DB."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "root", "--json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1

    def test_root_expand_flag_accepted(self, tmp_path: Path) -> None:
        """--expand flag is accepted without crashing."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        with patch.object(sys, "argv", ["ll-history", "root", "--expand"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()
        assert result == 1

    def test_root_limit_flag_accepted(self, tmp_path: Path) -> None:
        """--limit flag is accepted without crashing."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
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
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

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
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

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
# rework subcommand (FEAT-2867)
# ---------------------------------------------------------------------------


class TestHistoryReworkSubcommand:
    """Test the rework subcommand's argument wiring and format routing."""

    def test_rework_text_default_empty_history(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "rework"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "Rework Rate Analysis" in captured.out
        assert "No closed-issue history found" in captured.out

    def test_rework_json_format_routes_to_json_formatter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "rework", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["windows"] == []
        assert payload["min_sample_size"] == 5

    def test_rework_min_sample_and_follow_up_days_flags_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(
            sys,
            "argv",
            ["ll-history", "rework", "--min-sample", "2", "--follow-up-days", "7"],
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_rework_help_exits_zero_after_quality_subparser_added(self) -> None:
        """FEAT-3183: adding the `quality` subparser must not disturb `rework`."""
        with patch.object(sys, "argv", ["ll-history", "rework", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code == 0


# ---------------------------------------------------------------------------
# quality subcommand (FEAT-3183)
# ---------------------------------------------------------------------------


class TestHistoryQualitySubcommand:
    """Test the quality subcommand's argument wiring and format routing."""

    def test_quality_text_default_empty_history(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "Agent Quality Report" in captured.out
        assert "No closed-issue history found" in captured.out

    def test_quality_json_format_routes_to_json_formatter(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--format", "json"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        payload = json.loads(capsys.readouterr().out)
        assert payload["windows"] == []
        assert payload["min_sample_size"] == 5
        assert len(payload["definitions"]) == 4

    def test_quality_min_sample_flag_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--min-sample", "2"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_quality_help_exits_zero(self) -> None:
        with patch.object(sys, "argv", ["ll-history", "quality", "--help"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code == 0

    def test_quality_sensitivity_flag_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--sensitivity", "0.5"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_quality_baseline_windows_flag_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--baseline-windows", "2"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_quality_all_windows_flag_accepted(self, tmp_path: Path) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        (tmp_path / ".issues").mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "quality", "--all-windows"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0

    def test_quality_sensitivity_negative_rejected(self) -> None:
        with patch.object(sys, "argv", ["ll-history", "quality", "--sensitivity=-1"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code != 0

    def test_quality_baseline_windows_zero_rejected(self) -> None:
        with patch.object(sys, "argv", ["ll-history", "quality", "--baseline-windows=0"]):
            with pytest.raises(SystemExit) as exc_info:
                main_history()
        assert exc_info.value.code != 0


class TestHistoryQualityWorkspaceFlag:
    """`--workspace` (FEAT-3410): manifest-driven cross-repo aggregation."""

    @staticmethod
    def _member_db(repo_dir: Path, *, schema_version: str) -> None:
        import sqlite3

        (repo_dir / ".issues").mkdir(parents=True, exist_ok=True)
        ll_dir = repo_dir / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(ll_dir / "history.db")
        conn.execute("CREATE TABLE meta (key TEXT PRIMARY KEY, value TEXT)")
        conn.execute(
            "INSERT INTO meta (key, value) VALUES ('schema_version', ?)", (schema_version,)
        )
        conn.commit()
        conn.close()

    def test_workspace_flag_two_member_manifest_shows_both_labels(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store.schema import SCHEMA_VERSION

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        self._member_db(tmp_path / "member_a", schema_version=str(SCHEMA_VERSION))
        self._member_db(tmp_path / "member_b", schema_version=str(SCHEMA_VERSION))
        (tmp_path / "ll-workspace.yaml").write_text(
            "members:\n"
            "  - repo: member_a\n"
            "    role: primary\n"
            "  - repo: member_b\n"
            "    role: sibling\n"
        )

        with patch.object(sys, "argv", ["ll-history", "quality", "--workspace"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        out = capsys.readouterr().out
        assert "member_a (primary)" in out
        assert "member_b (sibling)" in out

    def test_workspace_bare_flag_no_manifest_matches_no_flag_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()

        with patch.object(sys, "argv", ["ll-history", "quality"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                assert main_history() == 0
        no_flag_output = capsys.readouterr().out

        with patch.object(sys, "argv", ["ll-history", "quality", "--workspace"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                assert main_history() == 0
        bare_flag_output = capsys.readouterr().out

        assert bare_flag_output == no_flag_output

    def test_workspace_missing_declared_manifest_exits_nonzero(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        missing = tmp_path / "does-not-exist.yaml"

        with patch.object(sys, "argv", ["ll-history", "quality", "--workspace", str(missing)]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result != 0
        assert str(missing) in capsys.readouterr().err

    def test_workspace_flag_absent_ignores_discoverable_manifest(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        from little_loops.session_store.schema import SCHEMA_VERSION

        (tmp_path / ".ll").mkdir()
        (tmp_path / ".issues").mkdir()
        self._member_db(tmp_path / "member_a", schema_version=str(SCHEMA_VERSION))
        (tmp_path / "ll-workspace.yaml").write_text(
            "members:\n  - repo: member_a\n    role: primary\n"
        )

        with patch.object(sys, "argv", ["ll-history", "quality"]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                result = main_history()

        assert result == 0
        out = capsys.readouterr().out
        assert "member_a (primary)" not in out
        assert "No closed-issue history found" in out


# ---------------------------------------------------------------------------
# sessions subcommand — json output
# ---------------------------------------------------------------------------


class TestHistorySessionsJson:
    """Test sessions subcommand --json flag."""

    def test_sessions_json_empty_returns_list(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
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
        ll_dir.mkdir(exist_ok=True)
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
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

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
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

        with patch.object(
            sys, "argv", ["ll-history", "export", "some-topic", "-d", str(issues_dir)]
        ):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    result = main_history()
        assert result == 0


# ---------------------------------------------------------------------------
# analyze subcommand — db_path propagation
# ---------------------------------------------------------------------------


class TestHistoryAnalyzeDbPath:
    """Test that analyze branch resolves and passes db_path to calculate_analysis."""

    def test_analyze_passes_db_path(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """analyze branch should pass a resolved db_path to calculate_analysis."""
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(exist_ok=True)
        issues_dir = tmp_path / ".issues"
        issues_dir.mkdir(exist_ok=True)

        with patch.object(sys, "argv", ["ll-history", "analyze", "-d", str(issues_dir)]):
            with patch("pathlib.Path.cwd", return_value=tmp_path):
                with patch("little_loops.issue_history.scan_completed_issues", return_value=[]):
                    with patch(
                        "little_loops.issue_history.calculate_analysis",
                        return_value=_make_empty_analysis(),
                    ) as mock_calc:
                        main_history()

        mock_calc.assert_called_once()
        call_kwargs = mock_calc.call_args.kwargs
        assert "db_path" in call_kwargs
        assert call_kwargs["db_path"] is not None

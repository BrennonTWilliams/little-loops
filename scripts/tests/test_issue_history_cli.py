"""Tests for issue_history module."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest


class TestHistoryArgumentParsing:
    """Tests for ll-history argument parsing."""

    def _parse_history_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_history."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        summary_parser = subparsers.add_parser("summary")
        summary_parser.add_argument("--json", action="store_true")
        summary_parser.add_argument("-d", "--directory", type=Path, default=None)
        return parser.parse_args(args)

    def test_summary_default(self) -> None:
        """Test summary with defaults."""
        args = self._parse_history_args(["summary"])
        assert args.command == "summary"
        assert args.json is False
        assert args.directory is None

    def test_summary_json_flag(self) -> None:
        """Test --json flag."""
        args = self._parse_history_args(["summary", "--json"])
        assert args.json is True

    def test_summary_json_short_form(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """-j is accepted by ll-history summary and produces JSON output (ENH-909)."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(
            sys, "argv", ["ll-history", "summary", "-j", "-d", str(tmp_path / ".issues")]
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        import json as json_mod

        data = json_mod.loads(captured.out)
        assert isinstance(data, dict)

    def test_summary_directory(self) -> None:
        """Test -d flag."""
        args = self._parse_history_args(["summary", "-d", "/custom/path"])
        assert args.directory == Path("/custom/path")

    def test_summary_combined(self) -> None:
        """Test combined flags."""
        args = self._parse_history_args(["summary", "--json", "-d", "/path"])
        assert args.json is True
        assert args.directory == Path("/path")


class TestMainHistoryIntegration:
    """Integration tests for main_history entry point."""

    def test_main_history_no_command(self) -> None:
        """Test main_history with no command shows help."""
        with patch.object(sys, "argv", ["ll-history"]):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 1

    def test_main_history_summary_empty(self, tmp_path: Path) -> None:
        """Test main_history summary with empty directory."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(sys, "argv", ["ll-history", "summary", "-d", str(tmp_path / ".issues")]):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_main_history_summary_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test main_history summary --json output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys, "argv", ["ll-history", "summary", "--json", "-d", str(tmp_path / ".issues")]
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total_count"] == 1
        assert data["type_counts"]["BUG"] == 1

    def test_main_history_summary_text(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test main_history summary text output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")
        (completed_dir / "P2-ENH-002-test.md").write_text("# ENH-002\n")

        with patch.object(sys, "argv", ["ll-history", "summary", "-d", str(tmp_path / ".issues")]):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

        captured = capsys.readouterr()
        assert "Total Completed: 2" in captured.out
        assert "BUG" in captured.out
        assert "ENH" in captured.out


class TestAnalyzeArgumentParsing:
    """Tests for ll-history analyze argument parsing."""

    def _parse_history_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_history."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")

        # summary
        summary_parser = subparsers.add_parser("summary")
        summary_parser.add_argument("--json", action="store_true")
        summary_parser.add_argument("-d", "--directory", type=Path, default=None)

        # analyze
        analyze_parser = subparsers.add_parser("analyze")
        analyze_parser.add_argument(
            "-f",
            "--format",
            type=str,
            choices=["text", "json", "markdown", "yaml"],
            default="text",
        )
        analyze_parser.add_argument("-d", "--directory", type=Path, default=None)
        analyze_parser.add_argument(
            "-p",
            "--period",
            type=str,
            choices=["weekly", "monthly", "quarterly"],
            default="monthly",
        )
        date_group = analyze_parser.add_mutually_exclusive_group()
        date_group.add_argument("-c", "--compare", type=int, default=None)
        date_group.add_argument("--since", type=str, default=None, metavar="DATE")
        analyze_parser.add_argument("--until", type=str, default=None, metavar="DATE")

        return parser.parse_args(args)

    def test_analyze_default(self) -> None:
        """Test analyze with defaults."""
        args = self._parse_history_args(["analyze"])
        assert args.command == "analyze"
        assert args.format == "text"
        assert args.period == "monthly"
        assert args.compare is None

    def test_analyze_format_markdown(self) -> None:
        """Test --format markdown."""
        args = self._parse_history_args(["analyze", "--format", "markdown"])
        assert args.format == "markdown"

    def test_analyze_format_short(self) -> None:
        """Test -f json."""
        args = self._parse_history_args(["analyze", "-f", "json"])
        assert args.format == "json"

    def test_analyze_compare(self) -> None:
        """Test --compare flag."""
        args = self._parse_history_args(["analyze", "--compare", "30"])
        assert args.compare == 30

    def test_analyze_period_quarterly(self) -> None:
        """Test --period quarterly."""
        args = self._parse_history_args(["analyze", "--period", "quarterly"])
        assert args.period == "quarterly"

    def test_analyze_combined(self) -> None:
        """Test multiple flags together."""
        args = self._parse_history_args(["analyze", "-f", "markdown", "-p", "weekly", "-c", "14"])
        assert args.format == "markdown"
        assert args.period == "weekly"
        assert args.compare == 14

    def test_analyze_since(self) -> None:
        """Test --since flag."""
        args = self._parse_history_args(["analyze", "--since", "2026-01-01"])
        assert args.since == "2026-01-01"
        assert args.compare is None

    def test_analyze_until(self) -> None:
        """Test --until flag."""
        args = self._parse_history_args(["analyze", "--until", "2026-03-31"])
        assert args.until == "2026-03-31"

    def test_analyze_date_range(self) -> None:
        """Test --since and --until combined."""
        args = self._parse_history_args(
            ["analyze", "--since", "2026-01-01", "--until", "2026-03-31"]
        )
        assert args.since == "2026-01-01"
        assert args.until == "2026-03-31"

    def test_analyze_since_defaults_none(self) -> None:
        """--since defaults to None."""
        args = self._parse_history_args(["analyze"])
        assert args.since is None
        assert args.until is None


class TestMainHistoryAnalyze:
    """Integration tests for ll-history analyze."""

    def test_main_history_analyze_text(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze text output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "Issue History Analysis" in captured.out

    def test_main_history_analyze_markdown(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze --format markdown."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--format", "markdown", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "# Issue History Analysis Report" in captured.out

    def test_main_history_analyze_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze --format json."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--format", "json", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert "total_completed" in data

    def test_main_history_analyze_with_compare(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze --compare."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--compare", "30", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_main_history_analyze_empty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test ll-history analyze with empty directory."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        assert "Completed: 0" in captured.out

    def test_main_history_analyze_since(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test --since filters out issues completed before the date."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-old.md").write_text(
            "# BUG-001\n\n## Resolution\n**Completed**: 2025-12-31\n"
        )
        (completed_dir / "P1-BUG-002-new.md").write_text(
            "# BUG-002\n\n## Resolution\n**Completed**: 2026-01-15\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "analyze",
                "--since",
                "2026-01-01",
                "--format",
                "json",
                "-d",
                str(tmp_path / ".issues"),
            ],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total_completed"] == 1

    def test_main_history_analyze_until(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test --until filters out issues completed after the date."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-q1.md").write_text(
            "# BUG-001\n\n## Resolution\n**Completed**: 2026-03-15\n"
        )
        (completed_dir / "P1-BUG-002-q2.md").write_text(
            "# BUG-002\n\n## Resolution\n**Completed**: 2026-04-05\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "analyze",
                "--until",
                "2026-03-31",
                "--format",
                "json",
                "-d",
                str(tmp_path / ".issues"),
            ],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total_completed"] == 1

    def test_main_history_analyze_date_range(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Test --since and --until together scope the analysis window."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-before.md").write_text(
            "# BUG-001\n\n## Resolution\n**Completed**: 2025-12-31\n"
        )
        (completed_dir / "P1-BUG-002-in.md").write_text(
            "# BUG-002\n\n## Resolution\n**Completed**: 2026-02-14\n"
        )
        (completed_dir / "P1-BUG-003-after.md").write_text(
            "# BUG-003\n\n## Resolution\n**Completed**: 2026-04-01\n"
        )

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "analyze",
                "--since",
                "2026-01-01",
                "--until",
                "2026-03-31",
                "--format",
                "json",
                "-d",
                str(tmp_path / ".issues"),
            ],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        captured = capsys.readouterr()
        data = json.loads(captured.out)
        assert data["total_completed"] == 1

    def test_main_history_analyze_compare_and_since_mutually_exclusive(
        self, tmp_path: Path
    ) -> None:
        """Test that --compare and --since are mutually exclusive."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "analyze",
                "--compare",
                "30",
                "--since",
                "2026-01-01",
                "-d",
                str(tmp_path / ".issues"),
            ],
        ):
            from little_loops.cli import main_history

            with pytest.raises(SystemExit) as exc_info:
                main_history()
            assert exc_info.value.code != 0


class TestAnalyzeDateArgParsing:
    """Tests for --since/--until argument parsing in ll-history analyze."""

    def test_analyze_since_default_none(self, tmp_path: Path) -> None:
        """--since and --until default to None (no filtering)."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(sys, "argv", ["ll-history", "analyze", "-d", str(tmp_path / ".issues")]):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_analyze_since_parsed(self, tmp_path: Path) -> None:
        """--since is accepted and stored as a string."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--since", "2026-01-01", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_analyze_until_parsed(self, tmp_path: Path) -> None:
        """--until is accepted and stored as a string."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "--until", "2026-03-31", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_analyze_since_short_form(self, tmp_path: Path) -> None:
        """-S is accepted as --since in ll-history analyze (ENH-910)."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(
            sys,
            "argv",
            ["ll-history", "analyze", "-S", "2026-01-01", "-d", str(tmp_path / ".issues")],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0


class TestExportShortForms:
    """Tests for short form aliases on ll-history export subcommand (ENH-910)."""

    def test_export_output_short_form(self, tmp_path: Path) -> None:
        """-o is accepted as --output in ll-history export (ENH-910)."""
        from unittest.mock import patch

        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        out_file = tmp_path / "out.md"

        with (
            patch.object(
                sys,
                "argv",
                [
                    "ll-history",
                    "export",
                    "cli",
                    "-o",
                    str(out_file),
                    "-d",
                    str(tmp_path / ".issues"),
                ],
            ),
            patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
            patch("little_loops.issue_history.synthesize_docs", return_value="# Doc"),
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        assert out_file.exists()

    def test_export_since_short_form(self, tmp_path: Path) -> None:
        """-S is accepted as --since in ll-history export (ENH-910)."""
        from unittest.mock import patch

        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with (
            patch.object(
                sys,
                "argv",
                [
                    "ll-history",
                    "export",
                    "cli",
                    "-S",
                    "2026-01-01",
                    "-d",
                    str(tmp_path / ".issues"),
                ],
            ),
            patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
            patch("little_loops.issue_history.synthesize_docs", return_value="# Doc"),
            patch("builtins.print"),
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

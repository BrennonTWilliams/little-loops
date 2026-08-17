"""Tests for issue_history module."""

from __future__ import annotations

import argparse
import json
import subprocess
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
        summary_parser.add_argument("-S", "--since", type=str, default=None, metavar="DATE")
        summary_parser.add_argument("--until", type=str, default=None, metavar="DATE")
        return parser.parse_args(args)

    def test_summary_default(self) -> None:
        """Test summary with defaults."""
        args = self._parse_history_args(["summary"])
        assert args.command == "summary"
        assert args.json is False
        assert args.directory is None
        assert args.since is None
        assert args.until is None

    def test_summary_since_flag(self) -> None:
        """--since is accepted by summary (ENH-3237)."""
        args = self._parse_history_args(["summary", "--since", "2026-01-01"])
        assert args.since == "2026-01-01"

    def test_summary_since_short_form(self) -> None:
        """-S is accepted as the short form of --since (ENH-3237)."""
        args = self._parse_history_args(["summary", "-S", "2026-01-01"])
        assert args.since == "2026-01-01"

    def test_summary_until_flag(self) -> None:
        """--until is accepted by summary (ENH-3237)."""
        args = self._parse_history_args(["summary", "--until", "2026-03-31"])
        assert args.until == "2026-03-31"

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

    def test_main_history_summary_empty(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test main_history summary with empty directory."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / ".ll" / "history.db"))

        with patch.object(sys, "argv", ["ll-history", "summary", "-d", str(tmp_path / ".issues")]):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_main_history_summary_json(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test main_history summary --json output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / ".ll" / "history.db"))

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
        assert data["source"] == "files"

    def test_main_history_summary_text(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Test main_history summary text output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")
        (completed_dir / "P2-ENH-002-test.md").write_text("# ENH-002\n")
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / ".ll" / "history.db"))

        with patch.object(sys, "argv", ["ll-history", "summary", "-d", str(tmp_path / ".issues")]):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

        captured = capsys.readouterr()
        assert "Total Completed: 2" in captured.out
        assert "BUG" in captured.out
        assert "ENH" in captured.out


class TestIntentFlagPassThrough:
    """ENH-1114: --intent/--intent-limit flags on ll-history are a no-op pass-through."""

    def test_intent_flag_does_not_break_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--intent flag (before subcommand) is accepted by ll-history and does not alter output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / ".ll" / "history.db"))

        # --intent is on the top-level parser, so it comes before the subcommand name
        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--intent",
                "rate limit",
                "summary",
                "-d",
                str(tmp_path / ".issues"),
            ],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_intent_limit_flag_does_not_break_summary(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--intent-limit flag (before subcommand) is accepted by ll-history and does not alter output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        monkeypatch.setenv("LL_HISTORY_DB", str(tmp_path / ".ll" / "history.db"))

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--intent",
                "FSM",
                "--intent-limit",
                "25",
                "summary",
                "-d",
                str(tmp_path / ".issues"),
            ],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0


class TestSummaryDbSource:
    """ENH-1621: ll-history summary prefers the unified session DB."""

    def _write_done_issue(self, base: Path, name: str, body: str) -> None:
        issues = base / ".issues" / "enhancements"
        issues.mkdir(parents=True, exist_ok=True)
        (issues / name).write_text(body, encoding="utf-8")

    def test_summary_uses_db_when_populated(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """When the session DB has done rows, summary reads from it (no file scan needed)."""
        from little_loops.session_store import backfill

        # Seed a backfilled DB inside a project root, but leave the
        # file-source directory empty so we can prove the DB was used.
        seed_dir = tmp_path / "seed-issues" / "enhancements"
        seed_dir.mkdir(parents=True)
        (seed_dir / "P1-ENH-100-x.md").write_text(
            "---\nid: ENH-100\nstatus: done\ntype: ENH\npriority: P1\n"
            "completed_at: 2026-05-21T12:00:00Z\n---\n",
            encoding="utf-8",
        )

        project_root = tmp_path / "proj"
        project_root.mkdir()
        db_path = project_root / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        monkeypatch.setenv("LL_HISTORY_DB", str(db_path))
        backfill(db_path, issues_dir=tmp_path / "seed-issues", loops_dir=tmp_path / "no")

        # Empty issues directory: file-scan path would yield zero.
        empty_issues = project_root / ".issues"
        empty_issues.mkdir()

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--config",
                str(project_root),
                "summary",
                "--json",
                "-d",
                str(empty_issues),
            ],
        ):
            from little_loops.cli import main_history

            assert main_history() == 0

        data = json.loads(capsys.readouterr().out)
        assert data["total_count"] == 1
        assert data["type_counts"].get("ENH") == 1

    def test_summary_uses_live_written_db_rows(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """summary reads rows seeded via SQLiteTransport.send() (live-write path)."""
        from little_loops.session_store import SQLiteTransport, ensure_db

        project_root = tmp_path / "proj"
        project_root.mkdir()
        db_path = project_root / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        monkeypatch.setenv("LL_HISTORY_DB", str(db_path))
        ensure_db(db_path)

        transport = SQLiteTransport(db_path)
        transport.send(
            {
                "event": "issue.completed",
                "ts": "2026-05-26T10:00:00+00:00",
                "issue_id": "BUG-200",
                "issue_type": "BUG",
                "priority": "P1",
                "file_path": str(project_root / ".issues" / "bugs" / "P1-BUG-200-live.md"),
                "completed_at": "2026-05-26T10:00:00Z",
            }
        )
        transport.close()

        empty_issues = project_root / ".issues"
        empty_issues.mkdir(exist_ok=True)

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--config",
                str(project_root),
                "summary",
                "--json",
                "-d",
                str(empty_issues),
            ],
        ):
            from little_loops.cli import main_history

            assert main_history() == 0

        data = json.loads(capsys.readouterr().out)
        assert data["total_count"] == 1
        assert data["type_counts"].get("BUG") == 1

    def test_summary_falls_back_to_files_when_db_empty(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An absent/empty DB falls back to scan_completed_issues() — no regression."""
        project_root = tmp_path / "proj"
        project_root.mkdir()
        # No DB created — fall-back path must trigger.
        completed_dir = project_root / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")
        monkeypatch.setenv("LL_HISTORY_DB", str(project_root / ".ll" / "history.db"))

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--config",
                str(project_root),
                "summary",
                "--json",
                "-d",
                str(project_root / ".issues"),
            ],
        ):
            from little_loops.cli import main_history

            assert main_history() == 0

        data = json.loads(capsys.readouterr().out)
        assert data["total_count"] == 1
        assert data["type_counts"].get("BUG") == 1


class TestSummaryWindow:
    """ENH-3237: `ll-history summary --json --since/--until`."""

    def test_source_field_present_without_window(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """The JSON payload always names its source, window flags or not."""
        project_root = tmp_path / "proj"
        project_root.mkdir()
        completed_dir = project_root / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")
        monkeypatch.setenv("LL_HISTORY_DB", str(project_root / ".ll" / "history.db"))

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--config",
                str(project_root),
                "summary",
                "--json",
                "-d",
                str(project_root / ".issues"),
            ],
        ):
            from little_loops.cli import main_history

            assert main_history() == 0

        data = json.loads(capsys.readouterr().out)
        assert data["source"] == "files"
        assert data["since"] is None
        assert data["until"] is None

    def test_empty_window_on_populated_store_stays_db_sourced(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """A quiet window on a populated store returns zero counts sourced from
        issue_events, not a file-scan fallback (the fallback trap)."""
        from little_loops.session_store import backfill

        seed_dir = tmp_path / "seed-issues" / "enhancements"
        seed_dir.mkdir(parents=True)
        (seed_dir / "P1-ENH-100-x.md").write_text(
            "---\nid: ENH-100\nstatus: done\ntype: ENH\npriority: P1\n"
            "completed_at: 2026-05-21T12:00:00Z\n---\n",
            encoding="utf-8",
        )

        project_root = tmp_path / "proj"
        project_root.mkdir()
        db_path = project_root / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        monkeypatch.setenv("LL_HISTORY_DB", str(db_path))
        backfill(db_path, issues_dir=tmp_path / "seed-issues", loops_dir=tmp_path / "no")

        # File-scan directory has the same file — proves the DB path (not the
        # file fallback) is what answered, since the window excludes it.
        empty_issues = project_root / ".issues"
        empty_issues.mkdir()

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--config",
                str(project_root),
                "summary",
                "--json",
                "--since",
                "2027-01-01",
                "-d",
                str(empty_issues),
            ],
        ):
            from little_loops.cli import main_history

            assert main_history() == 0

        data = json.loads(capsys.readouterr().out)
        assert data["total_count"] == 0
        assert data["source"] == "issue_events"
        assert data["since"] == "2027-01-01"

    def test_window_boundaries_are_inclusive(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """--since/--until bound completed_date inclusively."""
        from little_loops.session_store import backfill

        seed_dir = tmp_path / "seed-issues" / "enhancements"
        seed_dir.mkdir(parents=True)
        (seed_dir / "P1-ENH-100-in.md").write_text(
            "---\nid: ENH-100\nstatus: done\ntype: ENH\npriority: P1\n"
            "completed_at: 2026-05-10T12:00:00Z\n---\n",
            encoding="utf-8",
        )
        (seed_dir / "P1-ENH-101-out.md").write_text(
            "---\nid: ENH-101\nstatus: done\ntype: ENH\npriority: P1\n"
            "completed_at: 2026-06-01T12:00:00Z\n---\n",
            encoding="utf-8",
        )

        project_root = tmp_path / "proj"
        project_root.mkdir()
        db_path = project_root / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        monkeypatch.setenv("LL_HISTORY_DB", str(db_path))
        backfill(db_path, issues_dir=tmp_path / "seed-issues", loops_dir=tmp_path / "no")

        empty_issues = project_root / ".issues"
        empty_issues.mkdir()

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--config",
                str(project_root),
                "summary",
                "--json",
                "--since",
                "2026-05-10",
                "--until",
                "2026-05-10",
                "-d",
                str(empty_issues),
            ],
        ):
            from little_loops.cli import main_history

            assert main_history() == 0

        data = json.loads(capsys.readouterr().out)
        assert data["total_count"] == 1
        assert data["type_counts"].get("ENH") == 1

    def test_loop_run_window_counts_in_flight_run_as_started_not_ended(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """An in-flight run (ended_at IS NULL) counts as started-not-ended."""
        from little_loops.session_store import ensure_db, record_loop_run_summary

        project_root = tmp_path / "proj"
        project_root.mkdir()
        db_path = project_root / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        monkeypatch.setenv("LL_HISTORY_DB", str(db_path))
        ensure_db(db_path)

        record_loop_run_summary(
            db_path,
            run_id="run-in-flight",
            loop_name="test-loop",
            started_at="2026-05-15T10:00:00Z",
            ended_at=None,
        )
        record_loop_run_summary(
            db_path,
            run_id="run-finished",
            loop_name="test-loop",
            started_at="2026-05-15T10:00:00Z",
            ended_at="2026-05-15T11:00:00Z",
        )

        empty_issues = project_root / ".issues"
        empty_issues.mkdir()

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--config",
                str(project_root),
                "summary",
                "--json",
                "--since",
                "2026-05-15",
                "--until",
                "2026-05-15",
                "-d",
                str(empty_issues),
            ],
        ):
            from little_loops.cli import main_history

            assert main_history() == 0

        data = json.loads(capsys.readouterr().out)
        assert data["loop_runs_started"] == 2
        assert data["loop_runs_ended"] == 1

    def test_loop_runs_null_when_db_unqueryable(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str], monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """loop_runs_started/ended are null, not 0, when the DB can't be read.

        A merely *absent* DB doesn't isolate this: `ll-history`'s own
        `cli_event_context` writes a `cli_events` row (creating the DB file
        with an empty schema) on every invocation, before `summary`'s
        dispatch even runs — so an empty-but-valid DB reports real zero
        counts, not null (ENH-3237). Only a DB that fails to open/query at
        all should report null.
        """
        project_root = tmp_path / "proj"
        project_root.mkdir()
        completed_dir = project_root / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        db_path = project_root / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        db_path.write_text("not a sqlite file", encoding="utf-8")
        monkeypatch.setenv("LL_HISTORY_DB", str(db_path))

        with patch.object(
            sys,
            "argv",
            [
                "ll-history",
                "--config",
                str(project_root),
                "summary",
                "--json",
                "-d",
                str(project_root / ".issues"),
            ],
        ):
            from little_loops.cli import main_history

            assert main_history() == 0

        data = json.loads(capsys.readouterr().out)
        assert data["loop_runs_started"] is None
        assert data["loop_runs_ended"] is None


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
        summary_parser.add_argument("-S", "--since", type=str, default=None, metavar="DATE")
        summary_parser.add_argument("--until", type=str, default=None, metavar="DATE")

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

    def test_main_history_analyze_since_relative_directory_matches_absolute(
        self,
        tmp_path: Path,
        capsys: pytest.CaptureFixture[str],
        monkeypatch: pytest.MonkeyPatch,
    ) -> None:
        """BUG-3243: --since counts must not depend on -d being relative or absolute.

        Uses a file with no completed_at/Resolution date, so the count only
        reflects the git-log fallback path this bug affects.
        """
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(
            ["git", "config", "user.email", "test@example.com"], cwd=tmp_path, check=True
        )
        subprocess.run(["git", "config", "user.name", "Test"], cwd=tmp_path, check=True)
        bugs_dir = tmp_path / ".issues" / "bugs"
        bugs_dir.mkdir(parents=True)
        (bugs_dir / "P1-BUG-001-test.md").write_text("---\nstatus: done\n---\n\n# BUG-001\n")
        subprocess.run(["git", "add", ".issues/bugs/P1-BUG-001-test.md"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-qm", "add issue"], cwd=tmp_path, check=True)

        monkeypatch.chdir(tmp_path)

        def run_analyze(directory_arg: str) -> int:
            with patch.object(
                sys,
                "argv",
                [
                    "ll-history",
                    "analyze",
                    "--since",
                    "2020-01-01",
                    "--format",
                    "json",
                    "-d",
                    directory_arg,
                ],
            ):
                from little_loops.cli import main_history

                return main_history()

        assert run_analyze(str(tmp_path / ".issues")) == 0
        absolute_total = json.loads(capsys.readouterr().out)["total_completed"]

        assert run_analyze(".issues") == 0
        relative_total = json.loads(capsys.readouterr().out)["total_completed"]

        assert absolute_total == relative_total == 1

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


class TestExportTypeScoring:
    """Tests for --type and --scoring wiring in ll-history export (FEAT-978)."""

    def test_export_type_bug(self, tmp_path: Path) -> None:
        """--type BUG is forwarded to synthesize_docs as issue_type='BUG'."""
        from unittest.mock import patch

        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with (
            patch.object(
                sys,
                "argv",
                ["ll-history", "export", "cli", "--type", "BUG", "-d", str(tmp_path / ".issues")],
            ),
            patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
            patch("little_loops.issue_history.synthesize_docs", return_value="# Doc") as mock_synth,
            patch("builtins.print"),
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        assert mock_synth.call_args.kwargs["issue_type"] == "BUG"

    def test_export_type_feat(self, tmp_path: Path) -> None:
        """--type FEAT is forwarded to synthesize_docs as issue_type='FEAT'."""
        from unittest.mock import patch

        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with (
            patch.object(
                sys,
                "argv",
                ["ll-history", "export", "cli", "--type", "FEAT", "-d", str(tmp_path / ".issues")],
            ),
            patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
            patch("little_loops.issue_history.synthesize_docs", return_value="# Doc") as mock_synth,
            patch("builtins.print"),
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        assert mock_synth.call_args.kwargs["issue_type"] == "FEAT"

    def test_export_type_epic(self, tmp_path: Path) -> None:
        """--type EPIC is forwarded to synthesize_docs as issue_type='EPIC'."""
        from unittest.mock import patch

        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with (
            patch.object(
                sys,
                "argv",
                ["ll-history", "export", "cli", "--type", "EPIC", "-d", str(tmp_path / ".issues")],
            ),
            patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
            patch("little_loops.issue_history.synthesize_docs", return_value="# Doc") as mock_synth,
            patch("builtins.print"),
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        assert mock_synth.call_args.kwargs["issue_type"] == "EPIC"

    def test_export_type_default_none(self, tmp_path: Path) -> None:
        """export without --type passes issue_type=None to synthesize_docs."""
        from unittest.mock import patch

        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with (
            patch.object(
                sys,
                "argv",
                ["ll-history", "export", "cli", "-d", str(tmp_path / ".issues")],
            ),
            patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
            patch("little_loops.issue_history.synthesize_docs", return_value="# Doc") as mock_synth,
            patch("builtins.print"),
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        assert mock_synth.call_args.kwargs["issue_type"] is None

    def test_export_scoring_bm25(self, tmp_path: Path) -> None:
        """--scoring bm25 is forwarded to synthesize_docs as scoring='bm25'."""
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
                    "--scoring",
                    "bm25",
                    "-d",
                    str(tmp_path / ".issues"),
                ],
            ),
            patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
            patch("little_loops.issue_history.synthesize_docs", return_value="# Doc") as mock_synth,
            patch("builtins.print"),
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        assert mock_synth.call_args.kwargs["scoring"] == "bm25"

    def test_export_scoring_hybrid(self, tmp_path: Path) -> None:
        """--scoring hybrid is forwarded to synthesize_docs as scoring='hybrid'."""
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
                    "--scoring",
                    "hybrid",
                    "-d",
                    str(tmp_path / ".issues"),
                ],
            ),
            patch("little_loops.issue_history.analysis._load_issue_contents", return_value={}),
            patch("little_loops.issue_history.synthesize_docs", return_value="# Doc") as mock_synth,
            patch("builtins.print"),
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        assert mock_synth.call_args.kwargs["scoring"] == "hybrid"


class TestSessionsSubcommand:
    """ll-history sessions <ID> — lists sessions that touched an issue (ENH-1711)."""

    def _setup_db(self, db_path: Path, issue_id: str, session_id: str, jsonl: str) -> None:
        from little_loops.session_store import connect as ss_connect
        from little_loops.session_store import ensure_db

        ensure_db(db_path)
        conn = ss_connect(db_path)
        try:
            conn.execute(
                "INSERT INTO issue_events(ts, issue_id, transition, captured_at) "
                "VALUES(?, ?, ?, ?)",
                ("2026-01-10T00:00:00Z", issue_id, "open", "2026-01-10T00:00:00Z"),
            )
            conn.execute(
                "INSERT INTO message_events(ts, session_id, content) VALUES(?, ?, ?)",
                ("2026-01-10T10:00:00Z", session_id, "work"),
            )
            conn.execute(
                "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
                (session_id, jsonl),
            )
            conn.commit()
        finally:
            conn.close()

    def test_sessions_subcommand_lists_sessions(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        db_path = ll_dir / "history.db"
        self._setup_db(db_path, "ENH-1710", "sess-77", "/path/sess-77.jsonl")

        with patch.object(
            sys, "argv", ["ll-history", "--config", str(tmp_path), "sessions", "ENH-1710"]
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        out = capsys.readouterr().out
        assert "sess-77" in out
        assert "/path/sess-77.jsonl" in out

    def test_sessions_subcommand_json_output(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        db_path = ll_dir / "history.db"
        self._setup_db(db_path, "ENH-88", "sess-88", "/path/sess-88.jsonl")

        with patch.object(
            sys,
            "argv",
            ["ll-history", "--config", str(tmp_path), "sessions", "ENH-88", "--json"],
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["session_id"] == "sess-88"
        assert data[0]["jsonl_path"] == "/path/sess-88.jsonl"

    def test_sessions_subcommand_no_match(
        self, tmp_path: Path, capsys: pytest.CaptureFixture[str]
    ) -> None:
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir(parents=True, exist_ok=True)
        (ll_dir / "history.db")  # ensure_db happens inside main_history

        with patch.object(
            sys, "argv", ["ll-history", "--config", str(tmp_path), "sessions", "NOPE-000"]
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
        assert "No sessions found for NOPE-000" in capsys.readouterr().out

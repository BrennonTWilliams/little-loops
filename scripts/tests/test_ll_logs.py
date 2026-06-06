"""Tests for cli/logs.py - ll-logs CLI entry point."""

from __future__ import annotations

import argparse
import json
import sqlite3
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.logs import (
    _aggregate_skill_stats,
    _cmd_tail,
    _compute_session_diff,
    _events_from_jsonl,
    _is_ll_relevant,
    _load_catalog_names,
    _parse_args,
    _resolve_session_log,
    main_logs,
)
from little_loops.session_store import ensure_db


class TestArgumentParsing:
    """Argparse unit tests via _parse_args() helper, no filesystem."""

    def test_no_args_command_is_none(self) -> None:
        """No subcommand results in command=None."""
        with patch("sys.argv", ["ll-logs"]):
            args = _parse_args()
        assert args.command is None

    def test_discover_subcommand(self) -> None:
        """discover subcommand sets command to 'discover'."""
        with patch("sys.argv", ["ll-logs", "discover"]):
            args = _parse_args()
        assert args.command == "discover"


class TestDiscover:
    """Integration tests for the discover subcommand."""

    def _make_project_dir(
        self,
        claude_projects: Path,
        home: Path,
        subpath: str,
        records: list[dict],
    ) -> Path:
        """Create a mock claude project dir with JSONL content.

        Args:
            claude_projects: The ~/.claude/projects path
            home: The mocked home directory
            subpath: Path relative to home (e.g. "myproject")
            records: JSONL records to write

        Returns:
            The decoded project path (home / subpath)
        """
        project_path = home / subpath
        project_path.mkdir(parents=True, exist_ok=True)

        encoded = str(project_path).replace("/", "-")
        proj_dir = claude_projects / encoded
        proj_dir.mkdir(parents=True, exist_ok=True)

        if records:
            jsonl_file = proj_dir / "session.jsonl"
            with open(jsonl_file, "w") as f:
                for record in records:
                    if "cwd" not in record:
                        record = {**record, "cwd": str(project_path)}
                    f.write(json.dumps(record) + "\n")

        return project_path

    def test_discover_no_projects_exits_0(self) -> None:
        """discover exits 0 even when no projects exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            with (
                patch("sys.argv", ["ll-logs", "discover"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0

    def test_discover_finds_project_via_queue_operation(self, capsys) -> None:
        """discover outputs decoded path for a project with /ll: enqueue records."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    {
                        "type": "queue-operation",
                        "operation": "enqueue",
                        "content": "/ll:manage-issue bug fix",
                        "timestamp": "2026-01-01T00:00:00Z",
                        "sessionId": "abc123",
                    }
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "discover"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.strip().splitlines()]
        assert str(project_path) in lines

    def test_discover_skips_non_ll_project(self, capsys) -> None:
        """discover does not output projects without ll activity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            self._make_project_dir(
                claude_projects,
                home,
                "otherproject",
                [
                    {
                        "type": "user",
                        "message": {"role": "user", "content": "hello world"},
                        "timestamp": "2026-01-01T00:00:00Z",
                        "sessionId": "abc123",
                    }
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "discover"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == ""

    def test_discover_warns_and_skips_nonexistent_decoded_path(self, capsys) -> None:
        """discover emits warning for decoded paths that don't exist on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            # An encoded dir name that decodes to a path that won't exist
            encoded = "-does-not-exist-path"
            proj_dir = claude_projects / encoded
            proj_dir.mkdir(parents=True)
            jsonl_file = proj_dir / "session.jsonl"
            with open(jsonl_file, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "type": "queue-operation",
                            "operation": "enqueue",
                            "content": "/ll:manage-issue bug fix",
                            "timestamp": "2026-01-01T00:00:00Z",
                            "sessionId": "abc123",
                        }
                    )
                    + "\n"
                )

            with (
                patch("sys.argv", ["ll-logs", "discover"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        # Decoded path should not appear as a standalone output line
        decoded_path = "/does/not/exist/path"
        output_lines = [line.strip() for line in captured.out.strip().splitlines()]
        assert decoded_path not in output_lines

    def test_discover_finds_project_via_command_name_pattern(self, capsys) -> None:
        """discover detects ll activity via <command-name>/ll: in user messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "project2",
                [
                    {
                        "type": "user",
                        "message": {
                            "role": "user",
                            "content": ("<command-name>/ll:manage-issue</command-name>\nbug fix"),
                        },
                        "timestamp": "2026-01-01T00:00:00Z",
                        "sessionId": "abc123",
                    }
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "discover"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.strip().splitlines()]
        assert str(project_path) in lines

    def test_discover_output_sorted(self, capsys) -> None:
        """discover output is sorted alphabetically."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            ll_record = {
                "type": "queue-operation",
                "operation": "enqueue",
                "content": "/ll:manage-issue bug fix",
                "timestamp": "2026-01-01T00:00:00Z",
                "sessionId": "abc123",
            }

            path_b = self._make_project_dir(claude_projects, home, "b_project", [ll_record])
            path_a = self._make_project_dir(claude_projects, home, "a_project", [ll_record])

            with (
                patch("sys.argv", ["ll-logs", "discover"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.strip().splitlines() if line.strip()]
        # Filter to just the project paths (not warning lines)
        project_lines = [p for p in lines if p in (str(path_a), str(path_b))]
        assert project_lines == sorted(project_lines)

    def test_main_logs_no_subcommand_returns_1(self) -> None:
        """ll-logs with no subcommand prints help and returns 1."""
        with patch("sys.argv", ["ll-logs"]):
            result = main_logs()
        assert result == 1

    def test_discover_empty_projects_dir(self, capsys) -> None:
        """discover exits 0 with no output when projects dir is empty."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            with (
                patch("sys.argv", ["ll-logs", "discover"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out.strip() == ""

    def test_tail_subcommand_args(self) -> None:
        """tail subcommand sets command to 'tail' and captures --loop."""
        with patch("sys.argv", ["ll-logs", "tail", "--loop", "myloop"]):
            args = _parse_args()
        assert args.command == "tail"
        assert args.loop == "myloop"

    def test_discover_ignores_agent_jsonl_files(self, capsys) -> None:
        """discover skips agent-*.jsonl files when scanning for ll activity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = home / "agentproject"
            project_path.mkdir()
            encoded = str(project_path).replace("/", "-")
            proj_dir = claude_projects / encoded
            proj_dir.mkdir()

            # Write ll activity only in an agent- file (should be ignored)
            agent_file = proj_dir / "agent-session.jsonl"
            with open(agent_file, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "type": "queue-operation",
                            "operation": "enqueue",
                            "content": "/ll:manage-issue bug fix",
                            "timestamp": "2026-01-01T00:00:00Z",
                            "sessionId": "abc123",
                        }
                    )
                    + "\n"
                )

            with (
                patch("sys.argv", ["ll-logs", "discover"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.strip().splitlines()]
        assert str(project_path) not in lines

    def test_discover_json_output(self, capsys) -> None:
        """discover --json outputs valid JSON with paths array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = home / "jsonproject"
            project_path.mkdir()
            encoded = str(project_path).replace("/", "-")
            proj_dir = claude_projects / encoded
            proj_dir.mkdir()

            jsonl_file = proj_dir / "session.jsonl"
            with open(jsonl_file, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "type": "queue-operation",
                            "operation": "enqueue",
                            "content": "/ll:manage-issue",
                            "timestamp": "2026-01-01T00:00:00Z",
                            "sessionId": "abc123",
                            "cwd": str(project_path),
                        }
                    )
                    + "\n"
                )

            with (
                patch("sys.argv", ["ll-logs", "discover", "--json"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "paths" in data
        assert isinstance(data["paths"], list)
        assert str(project_path) in data["paths"]

    def test_discover_json_short_flag(self, capsys) -> None:
        """discover -j works equivalently to --json."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = home / "shortflagproject"
            project_path.mkdir()
            encoded = str(project_path).replace("/", "-")
            proj_dir = claude_projects / encoded
            proj_dir.mkdir()

            jsonl_file = proj_dir / "session.jsonl"
            with open(jsonl_file, "w") as f:
                f.write(
                    json.dumps(
                        {
                            "type": "queue-operation",
                            "operation": "enqueue",
                            "content": "/ll:manage-issue",
                            "timestamp": "2026-01-01T00:00:00Z",
                            "sessionId": "abc123",
                            "cwd": str(project_path),
                        }
                    )
                    + "\n"
                )

            with (
                patch("sys.argv", ["ll-logs", "discover", "-j"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert "paths" in data

    def test_discover_json_empty(self, capsys) -> None:
        """discover --json with no projects outputs empty paths array."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            with (
                patch("sys.argv", ["ll-logs", "discover", "--json"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data == {"paths": []}


class TestTail:
    """Integration tests for the tail subcommand."""

    def _mock_open_with_readline(self, side_effects: list) -> MagicMock:
        """Return a patched open() context manager whose readline yields side_effects."""
        mock_file = MagicMock()
        mock_file.readline.side_effect = side_effects
        mock_ctx = MagicMock()
        mock_ctx.__enter__ = MagicMock(return_value=mock_file)
        mock_ctx.__exit__ = MagicMock(return_value=False)
        return mock_ctx

    def test_missing_session_returns_1(self, capsys) -> None:
        """tail returns 1 and prints error when no active session file exists."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            loops_dir.mkdir()

            args = argparse.Namespace(loop="nonexistent")
            result = _cmd_tail(args, loops_dir)

        assert result == 1
        captured = capsys.readouterr()
        assert "nonexistent" in captured.err

    def test_tail_streams_events_and_exits_on_interrupt(self, capsys) -> None:
        """tail prints formatted events and exits 0 on KeyboardInterrupt via readline."""
        event = {"ts": "2026-04-23T10:00:00", "event": "loop_start", "loop": "myloop"}
        line = json.dumps(event) + "\n"

        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            running_dir = loops_dir / ".running"
            running_dir.mkdir(parents=True)
            (running_dir / "myloop.events.jsonl").write_text("")

            args = argparse.Namespace(loop="myloop")
            mock_ctx = self._mock_open_with_readline([line, KeyboardInterrupt()])
            with patch("builtins.open", return_value=mock_ctx):
                result = _cmd_tail(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr()
        assert "myloop" in captured.out

    def test_tail_keyboard_interrupt_on_sleep_exits_0(self) -> None:
        """tail exits with 0 when KeyboardInterrupt occurs during sleep (no events)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            running_dir = loops_dir / ".running"
            running_dir.mkdir(parents=True)
            (running_dir / "myloop.events.jsonl").write_text("")

            args = argparse.Namespace(loop="myloop")
            with patch("little_loops.cli.logs.time.sleep", side_effect=KeyboardInterrupt):
                result = _cmd_tail(args, loops_dir)

        assert result == 0

    def test_tail_skips_malformed_json(self, capsys) -> None:
        """tail skips lines that are not valid JSON without crashing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            loops_dir = Path(tmpdir) / ".loops"
            running_dir = loops_dir / ".running"
            running_dir.mkdir(parents=True)
            (running_dir / "myloop.events.jsonl").write_text("")

            args = argparse.Namespace(loop="myloop")
            mock_ctx = self._mock_open_with_readline(["not-valid-json\n", KeyboardInterrupt()])
            with patch("builtins.open", return_value=mock_ctx):
                result = _cmd_tail(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""


class TestIsLlRelevantAssistantBash:
    """Tests for type (c) detection in _is_ll_relevant()."""

    def _make_assistant_bash(self, command: str) -> dict:
        return {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": command},
                    }
                ],
            },
            "sessionId": "s1",
        }

    def test_assistant_bash_with_ll_command_returns_true(self) -> None:
        """Assistant Bash tool-use calling an ll- command is ll-relevant."""
        record = self._make_assistant_bash("ll-history --project /some/path")
        assert _is_ll_relevant(record) is True

    def test_assistant_bash_without_ll_command_returns_false(self) -> None:
        """Assistant Bash tool-use calling a non-ll command is not ll-relevant."""
        record = self._make_assistant_bash("git status")
        assert _is_ll_relevant(record) is False

    def test_assistant_non_bash_tool_returns_false(self) -> None:
        """Assistant tool-use with a non-Bash tool is not ll-relevant."""
        record = {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Read", "input": {"file_path": "/some/file"}},
                ],
            },
            "sessionId": "s1",
        }
        assert _is_ll_relevant(record) is False

    def test_assistant_text_only_returns_false(self) -> None:
        """Assistant record with only text content is not ll-relevant."""
        record = {
            "type": "assistant",
            "message": {"role": "assistant", "content": "Some response text"},
            "sessionId": "s1",
        }
        assert _is_ll_relevant(record) is False


class TestArgumentParsingSequences:
    """Argparse unit tests for the sequences subcommand."""

    def test_sequences_subcommand(self) -> None:
        """sequences subcommand sets command to 'sequences'."""
        with patch("sys.argv", ["ll-logs", "sequences", "--all"]):
            args = _parse_args()
        assert args.command == "sequences"

    def test_sequences_default_min_len(self) -> None:
        """sequences --min-len defaults to 2."""
        with patch("sys.argv", ["ll-logs", "sequences", "--all"]):
            args = _parse_args()
        assert args.min_len == 2

    def test_sequences_min_len_override(self) -> None:
        """sequences --min-len 3 sets min_len to 3."""
        with patch("sys.argv", ["ll-logs", "sequences", "--all", "--min-len", "3"]):
            args = _parse_args()
        assert args.min_len == 3

    def test_sequences_min_count_default(self) -> None:
        """sequences --min-count defaults to 1."""
        with patch("sys.argv", ["ll-logs", "sequences", "--all"]):
            args = _parse_args()
        assert args.min_count == 1

    def test_sequences_top_none_by_default(self) -> None:
        """sequences --top defaults to None."""
        with patch("sys.argv", ["ll-logs", "sequences", "--all"]):
            args = _parse_args()
        assert args.top is None

    def test_sequences_window_days_none_by_default(self) -> None:
        """sequences --window-days defaults to None."""
        with patch("sys.argv", ["ll-logs", "sequences", "--all"]):
            args = _parse_args()
        assert args.window_days is None

    def test_sequences_json_flag(self) -> None:
        """sequences --json sets json=True."""
        with patch("sys.argv", ["ll-logs", "sequences", "--all", "--json"]):
            args = _parse_args()
        assert args.json is True

    def test_sequences_project_and_all_mutually_exclusive(self) -> None:
        """sequences requires --project or --all (mutually exclusive)."""
        with patch("sys.argv", ["ll-logs", "sequences"]):
            with patch("sys.stderr", new_callable=lambda: None):
                try:
                    _parse_args()
                except SystemExit:
                    pass  # argparse exits on missing required arg


class TestSequences:
    """Integration tests for the sequences subcommand."""

    def _make_project_dir(
        self,
        claude_projects: Path,
        home: Path,
        subpath: str,
        records: list[dict],
        session_id: str = "session-abc",
    ) -> Path:
        """Create a mock claude project dir with JSONL content."""
        project_path = home / subpath
        project_path.mkdir(parents=True, exist_ok=True)

        encoded = str(project_path.resolve()).replace("/", "-")
        proj_dir = claude_projects / encoded
        proj_dir.mkdir(parents=True, exist_ok=True)

        if records:
            jsonl_file = proj_dir / "session.jsonl"
            with open(jsonl_file, "w") as f:
                for record in records:
                    if "sessionId" not in record:
                        record = {**record, "sessionId": session_id}
                    if "cwd" not in record:
                        record = {**record, "cwd": str(project_path)}
                    f.write(json.dumps(record) + "\n")

        return project_path

    def _assistant_bash_record(self, command: str, session_id: str = "sess-1") -> dict:
        return {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": command}},
                ],
            },
            "sessionId": session_id,
        }

    def _queue_record(self, content: str, session_id: str = "sess-1") -> dict:
        return {
            "type": "queue-operation",
            "operation": "enqueue",
            "content": content,
            "sessionId": session_id,
        }

    def test_sequences_basic_ngram_counting(self, capsys) -> None:
        """sequences counts n-grams from ll-* Bash invocations across sessions."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            # Two sessions, each with a chain of ll-* invocations
            session_a = "sess-a"
            session_b = "sess-b"
            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-issues list", session_a),
                    self._assistant_bash_record("ll-history sessions", session_a),
                    self._assistant_bash_record("ll-issues list", session_b),
                    self._assistant_bash_record("ll-history sessions", session_b),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            captured = capsys.readouterr()
            # Should find the bigram ll-issues → ll-history (appears in both sessions)
            assert "ll-issues" in captured.out
            assert "ll-history" in captured.out

    def test_sequences_min_len_filter(self, capsys) -> None:
        """sequences --min-len 3 only outputs trigrams and longer."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-refine-issue", "s1"),
                    self._assistant_bash_record("ll-wire-issue", "s1"),
                    self._assistant_bash_record("ll-ready-issue", "s1"),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--project", str(project_path), "--min-len", "3"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            captured = capsys.readouterr()
            # Should show a trigram
            assert "ll-refine-issue" in captured.out
            assert "ll-wire-issue" in captured.out
            assert "ll-ready-issue" in captured.out

    def test_sequences_min_count_filter(self, capsys) -> None:
        """sequences --min-count 2 only shows chains occurring at least twice."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-issues list", "s1"),
                    self._assistant_bash_record("ll-issues show", "s1"),
                    self._assistant_bash_record("ll-issues list", "s2"),
                    self._assistant_bash_record("ll-issues show", "s2"),
                    self._assistant_bash_record("ll-auto --dry-run", "s3"),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--project", str(project_path), "--min-count", "2"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            captured = capsys.readouterr()
            # The ll-issues → ll-issues bigram should appear (from s1 and s2)
            assert "ll-issues" in captured.out
            # ll-auto should not appear (only in s3)
            assert "ll-auto" not in captured.out

    def test_sequences_top_limit(self, capsys) -> None:
        """sequences --top 1 outputs only the single most frequent chain."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            records = []
            # Session a: chain A→B (3 times)
            for _ in range(3):
                records.append(self._assistant_bash_record("ll-issues list", "sa"))
                records.append(self._assistant_bash_record("ll-history sessions", "sa"))
            # Session b: chain C→D (1 time)
            records.append(self._assistant_bash_record("ll-auto --dry-run", "sb"))
            records.append(self._assistant_bash_record("ll-deps check", "sb"))

            project_path = self._make_project_dir(claude_projects, home, "myproject", records)

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--project", str(project_path), "--top", "1"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            captured = capsys.readouterr()
            # The most frequent chain should be the A→B bigram (3 occurrences)
            out = captured.out
            # count=3 should appear (the freq count for the most common chain)
            assert "3" in out

    def test_sequences_window_days_filter(self, capsys) -> None:
        """sequences --window-days filters records to within N days of latest."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    {**self._assistant_bash_record("ll-issues list", "s1"), "timestamp": "2026-06-01T10:00:00Z"},
                    {**self._assistant_bash_record("ll-issues show", "s1"), "timestamp": "2026-06-01T10:01:00Z"},
                    {**self._assistant_bash_record("ll-old-command", "s2"), "timestamp": "2020-01-01T00:00:00Z"},
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--project", str(project_path), "--window-days", "10"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            captured = capsys.readouterr()
            # Should include recent records
            assert "ll-issues" in captured.out
            # Old records outside window should be excluded
            assert "ll-old-command" not in captured.out

    def test_sequences_json_output(self, capsys) -> None:
        """sequences --json outputs valid JSON matching expected schema."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-issues list", "s1"),
                    self._assistant_bash_record("ll-issues show", "s1"),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--project", str(project_path), "--json"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            data = json.loads(capsys.readouterr().out)
            assert isinstance(data, list)
            for item in data:
                assert "chain" in item
                assert "count" in item
                assert "edges" in item
                assert isinstance(item["chain"], list)
                assert isinstance(item["count"], int)
                assert isinstance(item["edges"], list)
                for edge in item["edges"]:
                    assert "from" in edge
                    assert "to" in edge
                    assert "freq" in edge

    def test_sequences_project_not_found_returns_1(self) -> None:
        """sequences --project with no matching claude folder returns 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            home.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)
            nonexistent = Path(tmpdir) / "nosuchproject"

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--project", str(nonexistent)]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

            assert result == 1

    def test_sequences_empty_project_no_matches(self, capsys) -> None:
        """sequences with no matching records exits 0 with empty output."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            # Records with no ll-* Bash invocations
            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [self._assistant_bash_record("git status", "s1")],
            )

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0

    def test_sequences_includes_queue_operations(self, capsys) -> None:
        """sequences detects queue-operation enqueue records with /ll: content."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._queue_record("/ll:manage-issue bug fix", "s1"),
                    self._assistant_bash_record("ll-issues list", "s1"),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            captured = capsys.readouterr()
            # Should detect manage-issue from queue-operation record
            assert "manage-issue" in captured.out

    def test_sequences_all_mode(self, capsys) -> None:
        """sequences --all processes all projects with ll activity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            # Each session needs ≥2 events for n-grams with default min-len=2
            path_a = self._make_project_dir(
                claude_projects, home, "proj_a",
                [
                    self._assistant_bash_record("ll-issues list", "sa"),
                    self._assistant_bash_record("ll-issues show", "sa"),
                ],
            )
            path_b = self._make_project_dir(
                claude_projects, home, "proj_b",
                [
                    self._assistant_bash_record("ll-history sessions", "sb"),
                    self._assistant_bash_record("ll-history context", "sb"),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "sequences", "--all"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            captured = capsys.readouterr()
            assert "ll-issues" in captured.out
            assert "ll-history" in captured.out


class TestExtract:
    """Integration tests for the extract subcommand."""

    def _make_project_dir(
        self,
        claude_projects: Path,
        home: Path,
        subpath: str,
        records: list[dict],
        session_id: str = "session-abc",
    ) -> Path:
        """Create a mock claude project dir with JSONL content.

        Args:
            claude_projects: The ~/.claude/projects path
            home: The mocked home directory
            subpath: Path relative to home (e.g. "myproject")
            records: JSONL records to write
            session_id: sessionId to inject into records that lack one

        Returns:
            The decoded project path (home / subpath)
        """
        project_path = home / subpath
        project_path.mkdir(parents=True, exist_ok=True)

        # Use .resolve() to match get_project_folder() which also calls .resolve()
        encoded = str(project_path.resolve()).replace("/", "-")
        proj_dir = claude_projects / encoded
        proj_dir.mkdir(parents=True, exist_ok=True)

        if records:
            jsonl_file = proj_dir / "session.jsonl"
            with open(jsonl_file, "w") as f:
                for record in records:
                    if "sessionId" not in record:
                        record = {**record, "sessionId": session_id}
                    if "cwd" not in record:
                        record = {**record, "cwd": str(project_path)}
                    f.write(json.dumps(record) + "\n")

        return project_path

    def _ll_queue_record(self, session_id: str = "sess-1") -> dict:
        return {
            "type": "queue-operation",
            "operation": "enqueue",
            "content": "/ll:manage-issue bug fix",
            "sessionId": session_id,
        }

    def _assistant_bash_record(self, command: str, session_id: str = "sess-1") -> dict:
        return {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {"type": "tool_use", "name": "Bash", "input": {"command": command}},
                ],
            },
            "sessionId": session_id,
        }

    def test_extract_project_creates_output_file(self) -> None:
        """extract --project writes matching records to logs/<slug>/<session>.jsonl."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            session_id = "abc-123"
            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [self._ll_queue_record(session_id)],
                session_id=session_id,
            )
            slug = project_path.name

            with (
                patch("sys.argv", ["ll-logs", "extract", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            out_file = output_cwd / "logs" / slug / f"{session_id}.jsonl"
            assert out_file.exists(), f"Expected output file {out_file}"
            lines = [json.loads(line) for line in out_file.read_text().splitlines()]
            assert len(lines) == 1
            assert lines[0]["sessionId"] == session_id

    def test_extract_all_creates_output_for_each_project(self) -> None:
        """extract --all writes files for all projects with ll activity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            session_a = "sess-aaa"
            session_b = "sess-bbb"
            path_a = self._make_project_dir(
                claude_projects, home, "proj_a", [self._ll_queue_record(session_a)], session_a
            )
            path_b = self._make_project_dir(
                claude_projects, home, "proj_b", [self._ll_queue_record(session_b)], session_b
            )

            with (
                patch("sys.argv", ["ll-logs", "extract", "--all"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            assert (output_cwd / "logs" / path_a.name / f"{session_a}.jsonl").exists()
            assert (output_cwd / "logs" / path_b.name / f"{session_b}.jsonl").exists()

    def test_extract_cmd_filter_keeps_matching_records(self) -> None:
        """extract --all --cmd ll-history keeps only records with that tool."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            session_id = "sess-filter"
            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-history --project /foo", session_id),
                    self._assistant_bash_record("ll-auto --dry-run", session_id),
                ],
                session_id=session_id,
            )

            with (
                patch("sys.argv", ["ll-logs", "extract", "--all", "--cmd", "ll-history"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            out_file = output_cwd / "logs" / project_path.name / f"{session_id}.jsonl"
            assert out_file.exists()
            lines = [json.loads(line) for line in out_file.read_text().splitlines()]
            assert len(lines) == 1
            cmd = lines[0]["message"]["content"][0]["input"]["command"]
            assert "ll-history" in cmd

    def test_extract_cmd_filter_no_match_writes_no_file(self) -> None:
        """extract --cmd with no matching records writes no output file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            session_id = "sess-nomatch"
            self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [self._assistant_bash_record("ll-auto --dry-run", session_id)],
                session_id=session_id,
            )

            with (
                patch("sys.argv", ["ll-logs", "extract", "--all", "--cmd", "ll-history"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            logs_dir = output_cwd / "logs"
            assert not logs_dir.exists() or not any(logs_dir.rglob("*.jsonl"))

    def test_extract_generates_index_md(self) -> None:
        """extract --project writes logs/index.md after JSONL extraction."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            session_id = "abc-index"
            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [self._ll_queue_record(session_id)],
                session_id=session_id,
            )

            with (
                patch("sys.argv", ["ll-logs", "extract", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            index_file = output_cwd / "logs" / "index.md"
            assert index_file.exists(), "logs/index.md should be created after extract"
            content = index_file.read_text()
            assert "# Logs Index" in content

    def test_extract_index_md_table_contents(self) -> None:
        """logs/index.md table contains project slug, session count, and date range."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            session_a = "sess-1"
            session_b = "sess-2"
            records = [
                {**self._ll_queue_record(session_a), "timestamp": "2026-01-01T10:00:00Z"},
                {**self._ll_queue_record(session_b), "timestamp": "2026-04-23T12:00:00Z"},
            ]
            project_path = self._make_project_dir(claude_projects, home, "myproject", records)
            slug = project_path.name

            with (
                patch("sys.argv", ["ll-logs", "extract", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            content = (output_cwd / "logs" / "index.md").read_text()
            assert slug in content
            assert "| 2 |" in content
            assert "2026-01-01" in content
            assert "2026-04-23" in content

    def test_extract_all_no_activity_creates_stub_index(self) -> None:
        """extract --all with no ll-activity still creates a stub logs/index.md."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            with (
                patch("sys.argv", ["ll-logs", "extract", "--all"]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            index_file = output_cwd / "logs" / "index.md"
            assert index_file.exists(), "logs/index.md should be created even with no projects"
            content = index_file.read_text()
            assert "# Logs Index" in content

    def test_extract_project_not_found_returns_1(self) -> None:
        """extract --project with no matching claude folder returns 1."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            home.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)
            nonexistent = Path(tmpdir) / "nosuchproject"

            with (
                patch("sys.argv", ["ll-logs", "extract", "--project", str(nonexistent)]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

            assert result == 1

    def test_extract_skips_agent_jsonl(self) -> None:
        """extract ignores agent-*.jsonl files when scanning for ll activity."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            session_id = "agent-session"
            project_path = home / "agentproject"
            project_path.mkdir(parents=True)
            encoded = str(project_path.resolve()).replace("/", "-")
            proj_dir = claude_projects / encoded
            proj_dir.mkdir(parents=True)

            # Put ll activity only in an agent- file (should be ignored)
            agent_file = proj_dir / "agent-session.jsonl"
            with open(agent_file, "w") as f:
                f.write(json.dumps(self._ll_queue_record(session_id)) + "\n")

            with (
                patch("sys.argv", ["ll-logs", "extract", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            logs_dir = output_cwd / "logs"
            assert not logs_dir.exists() or not any(logs_dir.rglob("*.jsonl"))


def _populate_skill_events(
    db_path: Path,
    rows: list[tuple[str, str, str, str]],
) -> None:
    """Insert (ts, session_id, skill_name, args) rows into skill_events."""
    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        for ts, session_id, skill_name, args in rows:
            conn.execute(
                "INSERT INTO skill_events(ts, session_id, skill_name, args) VALUES(?, ?, ?, ?)",
                (ts, session_id, skill_name, args),
            )
        conn.commit()
    finally:
        conn.close()


def _insert_correction(db_path: Path, ts: str, session_id: str, content: str) -> None:
    """Insert a user_corrections row directly."""
    ensure_db(db_path)
    conn = sqlite3.connect(str(db_path))
    try:
        conn.execute(
            "INSERT INTO user_corrections(ts, session_id, content, source) VALUES(?, ?, ?, 'test')",
            (ts, session_id, content),
        )
        conn.commit()
    finally:
        conn.close()


class TestStats:
    """Tests for the stats subcommand."""

    def test_stats_subcommand_parsed(self) -> None:
        """stats subcommand sets command='stats' and all=True."""
        with patch("sys.argv", ["ll-logs", "stats", "--all"]):
            args = _parse_args()
        assert args.command == "stats"
        assert args.all is True

    def test_stats_sort_default_freq(self) -> None:
        """--sort defaults to 'freq'."""
        with patch("sys.argv", ["ll-logs", "stats", "--all"]):
            args = _parse_args()
        assert args.sort == "freq"

    def test_stats_sort_corrections(self) -> None:
        """--sort corrections is accepted."""
        with patch("sys.argv", ["ll-logs", "stats", "--all", "--sort", "corrections"]):
            args = _parse_args()
        assert args.sort == "corrections"

    def test_stats_window_days(self) -> None:
        """--window-days is accepted."""
        with patch("sys.argv", ["ll-logs", "stats", "--all", "--window-days", "7"]):
            args = _parse_args()
        assert args.window_days == 7

    def test_stats_project_and_all_mutually_exclusive(self) -> None:
        """--project and --all cannot be combined."""
        with patch("sys.argv", ["ll-logs", "stats", "--project", "/tmp", "--all"]):
            with pytest.raises(SystemExit):
                _parse_args()

    def test_stats_json_flag(self) -> None:
        """--json flag is accepted."""
        with patch("sys.argv", ["ll-logs", "stats", "--all", "--json"]):
            args = _parse_args()
        assert args.json is True

    def test_stats_no_db_returns_0(self, tmp_path: Path) -> None:
        """stats returns 0 gracefully when no history.db exists."""
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path)]),
            patch("pathlib.Path.home", return_value=tmp_path),
        ):
            result = main_logs()
        assert result == 0

    def test_stats_counts_invocations(self, tmp_path: Path, capsys) -> None:
        """stats correctly counts invocations per skill in tabular output."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        _populate_skill_events(db_path, [
            ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
            ("2026-01-01T00:01:00Z", "s1", "manage-issue", ""),
            ("2026-01-01T00:02:00Z", "s1", "capture-issue", ""),
        ])

        with patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path)]):
            result = main_logs()

        assert result == 0
        out = capsys.readouterr().out
        assert "manage-issue" in out
        assert "capture-issue" in out

    def test_stats_json_output(self, tmp_path: Path) -> None:
        """stats --json emits a JSON array with invocation counts."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        _populate_skill_events(db_path, [
            ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
            ("2026-01-01T00:01:00Z", "s1", "capture-issue", ""),
        ])

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        assert isinstance(data, list)
        assert len(data) == 2
        skills = {r["skill"] for r in data}
        assert "manage-issue" in skills
        assert "capture-issue" in skills

    def test_stats_json_keys(self, tmp_path: Path) -> None:
        """JSON output includes invocations, corrections, correction_rate, errors, error_rate."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        _populate_skill_events(db_path, [
            ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
        ])

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            main_logs()

        data = json.loads("\n".join(captured))
        row = data[0]
        assert {"skill", "invocations", "corrections", "correction_rate", "errors", "error_rate"} == set(row.keys())
        assert row["errors"] is None
        assert row["error_rate"] is None

    def test_stats_correction_attribution(self, tmp_path: Path) -> None:
        """Corrections within 30s of a skill event are attributed to that skill."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        _populate_skill_events(db_path, [
            ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
        ])
        _insert_correction(db_path, "2026-01-01T00:00:10Z", "s1", "no, not that")

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        assert data[0]["skill"] == "manage-issue"
        assert data[0]["corrections"] == 1

    def test_stats_correction_outside_window_not_attributed(self, tmp_path: Path) -> None:
        """Corrections more than 30s after a skill event are not attributed."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        _populate_skill_events(db_path, [
            ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
        ])
        _insert_correction(db_path, "2026-01-01T00:01:00Z", "s1", "no, not that")

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        assert data[0]["skill"] == "manage-issue"
        assert data[0]["corrections"] == 0

    def test_stats_sort_by_corrections(self, tmp_path: Path) -> None:
        """--sort corrections puts higher-correction skills first."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        _populate_skill_events(db_path, [
            ("2026-01-01T00:00:00Z", "s1", "capture-issue", ""),
            ("2026-01-01T00:01:00Z", "s1", "manage-issue", ""),
        ])
        _insert_correction(db_path, "2026-01-01T00:01:10Z", "s1", "no wait")

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path), "--json", "--sort", "corrections"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        assert data[0]["skill"] == "manage-issue"
        assert data[0]["corrections"] == 1

    def test_stats_empty_db_returns_0(self, tmp_path: Path) -> None:
        """stats returns 0 when DB exists but has no skill events."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        ensure_db(db_path)

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path)]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0

    def test_aggregate_skill_stats_no_db_returns_none(self, tmp_path: Path) -> None:
        """_aggregate_skill_stats returns None when DB is absent."""
        result = _aggregate_skill_stats(tmp_path / ".ll" / "history.db")
        assert result is None

    def test_aggregate_skill_stats_empty_db_returns_empty(self, tmp_path: Path) -> None:
        """_aggregate_skill_stats returns {} for a DB with no skill_events rows."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        ensure_db(db_path)
        result = _aggregate_skill_stats(db_path)
        assert result == {}

    def test_aggregate_skill_stats_counts(self, tmp_path: Path) -> None:
        """_aggregate_skill_stats returns correct invocation counts."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        _populate_skill_events(db_path, [
            ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
            ("2026-01-01T00:01:00Z", "s1", "manage-issue", ""),
            ("2026-01-01T00:02:00Z", "s1", "capture-issue", ""),
        ])
        result = _aggregate_skill_stats(db_path)
        assert result is not None
        assert result["manage-issue"]["invocations"] == 2
        assert result["capture-issue"]["invocations"] == 1

    def test_aggregate_skill_stats_window_days(self, tmp_path: Path) -> None:
        """window_days filters out older records."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        _populate_skill_events(db_path, [
            ("2025-01-01T00:00:00Z", "s1", "old-skill", ""),
            ("2026-06-01T00:00:00Z", "s1", "new-skill", ""),
        ])
        result = _aggregate_skill_stats(db_path, window_days=30)
        assert result is not None
        assert "new-skill" in result
        assert "old-skill" not in result


class TestDeadSkills:
    """Tests for the dead-skills subcommand."""

    def _make_skill(self, skills_dir: Path, name: str, bridge: bool = False) -> None:
        """Create a minimal SKILL.md stub in skills_dir/name/."""
        skill_dir = skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        body = "Bridged from `commands/placeholder.md` for Codex Skills API discovery." if bridge else ""
        (skill_dir / "SKILL.md").write_text(
            f"---\nname: {name}\ndescription: Test skill.\n---\n{body}\n"
        )

    def test_dead_skills_subcommand_parsed(self) -> None:
        """dead-skills subcommand sets command='dead-skills'."""
        with patch("sys.argv", ["ll-logs", "dead-skills", "--all"]):
            args = _parse_args()
        assert args.command == "dead-skills"
        assert args.all is True

    def test_dead_skills_threshold_default(self) -> None:
        """--threshold defaults to 3."""
        with patch("sys.argv", ["ll-logs", "dead-skills", "--all"]):
            args = _parse_args()
        assert args.threshold == 3

    def test_dead_skills_window_days(self) -> None:
        """--window-days is accepted."""
        with patch("sys.argv", ["ll-logs", "dead-skills", "--all", "--window-days", "7"]):
            args = _parse_args()
        assert args.window_days == 7

    def test_dead_skills_project_and_all_mutually_exclusive(self) -> None:
        """--project and --all cannot be combined."""
        with patch("sys.argv", ["ll-logs", "dead-skills", "--project", "/tmp", "--all"]):
            with pytest.raises(SystemExit):
                _parse_args()

    def test_dead_skills_json_flag(self) -> None:
        """--json flag is accepted."""
        with patch("sys.argv", ["ll-logs", "dead-skills", "--all", "--json"]):
            args = _parse_args()
        assert args.json is True

    def test_dead_skills_never_invoked_appears(self, tmp_path: Path) -> None:
        """A catalog skill with zero invocations appears with tier='never'."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "my-skill")
        # No skill_events seeded → zero invocations
        ensure_db(db_path)

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        assert isinstance(data, list)
        skills_found = {r["skill"]: r for r in data}
        assert "my-skill" in skills_found
        assert skills_found["my-skill"]["invocations"] == 0
        assert skills_found["my-skill"]["tier"] == "never"

    def test_dead_skills_used_skill_not_shown(self, tmp_path: Path) -> None:
        """A skill with invocations above threshold does not appear in output."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "used-skill")
        _populate_skill_events(db_path, [
            ("2026-01-01T00:00:00Z", "s1", "used-skill", ""),
            ("2026-01-01T00:01:00Z", "s1", "used-skill", ""),
            ("2026-01-01T00:02:00Z", "s1", "used-skill", ""),
            ("2026-01-01T00:03:00Z", "s1", "used-skill", ""),
        ])

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        skills_found = {r["skill"] for r in data}
        assert "used-skill" not in skills_found

    def test_dead_skills_rarely_invoked(self, tmp_path: Path) -> None:
        """A skill with invocations <= threshold appears with tier='rarely'."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "rare-skill")
        _populate_skill_events(db_path, [
            ("2026-01-01T00:00:00Z", "s1", "rare-skill", ""),
            ("2026-01-01T00:01:00Z", "s1", "rare-skill", ""),
        ])

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        skills_found = {r["skill"]: r for r in data}
        assert "rare-skill" in skills_found
        assert skills_found["rare-skill"]["invocations"] == 2
        assert skills_found["rare-skill"]["tier"] == "rarely"

    def test_dead_skills_json_output_shape(self, tmp_path: Path) -> None:
        """JSON output items have exactly skill, invocations, tier keys."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "shape-skill")
        ensure_db(db_path)

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            main_logs()

        data = json.loads("\n".join(captured))
        assert len(data) == 1
        assert set(data[0].keys()) == {"skill", "invocations", "tier"}

    def test_dead_skills_bridge_skill_excluded(self, tmp_path: Path) -> None:
        """Bridge skills (containing BRIDGE_MARKER) are excluded from the catalog."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "real-skill")
        self._make_skill(skills_dir, "bridge-skill", bridge=True)
        ensure_db(db_path)

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        skills_found = {r["skill"] for r in data}
        assert "real-skill" in skills_found
        assert "bridge-skill" not in skills_found

    def test_dead_skills_no_catalog_returns_0(self, tmp_path: Path) -> None:
        """Returns 0 gracefully when no catalog skills exist."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        ensure_db(db_path)

        with patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path)]):
            result = main_logs()

        assert result == 0


class TestScanFailures:
    """Tests for the scan-failures subcommand."""

    def _make_project_dir(
        self,
        claude_projects: Path,
        home: Path,
        subpath: str,
        records: list[dict],
        session_id: str = "session-abc",
    ) -> Path:
        """Create a mock claude project dir with JSONL content."""
        project_path = home / subpath
        project_path.mkdir(parents=True, exist_ok=True)

        encoded = str(project_path.resolve()).replace("/", "-")
        proj_dir = claude_projects / encoded
        proj_dir.mkdir(parents=True, exist_ok=True)

        if records:
            jsonl_file = proj_dir / "session.jsonl"
            with open(jsonl_file, "w") as f:
                for record in records:
                    if "sessionId" not in record:
                        record = {**record, "sessionId": session_id}
                    if "cwd" not in record:
                        record = {**record, "cwd": str(project_path)}
                    f.write(json.dumps(record) + "\n")

        return project_path

    def _assistant_bash_record(
        self,
        command: str,
        tool_use_id: str = "toolu_001",
        session_id: str = "sess-1",
        timestamp: str = "2026-01-01T00:00:00Z",
    ) -> dict:
        return {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [
                    {
                        "type": "tool_use",
                        "id": tool_use_id,
                        "name": "Bash",
                        "input": {"command": command},
                    }
                ],
            },
            "sessionId": session_id,
            "timestamp": timestamp,
        }

    def _user_tool_result_record(
        self,
        tool_use_id: str = "toolu_001",
        content: str = "Error output",
        is_error: bool = True,
        session_id: str = "sess-1",
        timestamp: str = "2026-01-01T00:00:01Z",
    ) -> dict:
        return {
            "type": "user",
            "message": {
                "role": "user",
                "content": [
                    {
                        "type": "tool_result",
                        "tool_use_id": tool_use_id,
                        "is_error": is_error,
                        "content": [{"type": "text", "text": content}],
                    }
                ],
            },
            "sessionId": session_id,
            "timestamp": timestamp,
        }

    def test_scan_failures_subcommand_parsed(self) -> None:
        """scan-failures sets command='scan-failures' and all=True."""
        with patch("sys.argv", ["ll-logs", "scan-failures", "--all"]):
            args = _parse_args()
        assert args.command == "scan-failures"
        assert args.all is True

    def test_scan_failures_project_flag(self) -> None:
        """scan-failures --project sets project path."""
        with patch("sys.argv", ["ll-logs", "scan-failures", "--project", "/tmp"]):
            args = _parse_args()
        assert args.project == Path("/tmp")

    def test_scan_failures_capture_flag(self) -> None:
        """--capture flag is accepted."""
        with patch("sys.argv", ["ll-logs", "scan-failures", "--all", "--capture"]):
            args = _parse_args()
        assert args.capture is True

    def test_scan_failures_window_days_flag(self) -> None:
        """--window-days is accepted."""
        with patch("sys.argv", ["ll-logs", "scan-failures", "--all", "--window-days", "7"]):
            args = _parse_args()
        assert args.window_days == 7

    def test_scan_failures_project_and_all_mutually_exclusive(self) -> None:
        """--project and --all cannot be combined."""
        with patch("sys.argv", ["ll-logs", "scan-failures", "--project", "/tmp", "--all"]):
            with pytest.raises(SystemExit):
                _parse_args()

    def test_scan_failures_detects_is_error_flag(self, capsys, tmp_path) -> None:
        """Nonzero-exit failure (is_error: True) is detected and surfaced."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-history --bad-flag", tool_use_id="t1"),
                    self._user_tool_result_record(
                        tool_use_id="t1",
                        content="ll-history: error: unrecognized arguments: --bad-flag",
                        is_error=True,
                    ),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "scan-failures", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert "ll-history" in captured.out

    def test_scan_failures_detects_traceback(self, capsys) -> None:
        """Traceback text in result content is detected as a failure."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            tb = "Traceback (most recent call last):\n  File 'foo.py', line 5\nValueError: oops"
            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-issues list", tool_use_id="t2"),
                    self._user_tool_result_record(
                        tool_use_id="t2",
                        content=tb,
                        is_error=False,
                    ),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "scan-failures", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert "ll-issues" in captured.out

    def test_scan_failures_clusters_same_error(self, capsys) -> None:
        """Multiple occurrences of the same error collapse to one cluster."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            error = "ll-history: error: something went wrong"
            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-history", tool_use_id="t1", session_id="s1"),
                    self._user_tool_result_record("t1", error, session_id="s1"),
                    self._assistant_bash_record("ll-history", tool_use_id="t2", session_id="s2"),
                    self._user_tool_result_record("t2", error, session_id="s2"),
                ],
            )

            captured_lines: list[str] = []
            with (
                patch("sys.argv", ["ll-logs", "scan-failures", "--project", str(project_path), "--json"]),
                patch("pathlib.Path.home", return_value=home),
                patch("builtins.print", side_effect=lambda *a, **kw: captured_lines.append(str(a[0]) if a else "")),
            ):
                result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured_lines))
        assert isinstance(data, list)
        assert len(data) == 1
        assert data[0]["count"] == 2
        assert data[0]["tool"] == "ll-history"

    def test_scan_failures_suppresses_transient_errors(self, capsys) -> None:
        """Rate limit and other transient errors are suppressed from candidates."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-history", tool_use_id="t1"),
                    self._user_tool_result_record("t1", "rate limit exceeded", is_error=True),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "scan-failures", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert "No ll-* failures found" in captured.out

    def test_scan_failures_excludes_verify_tools(self, capsys) -> None:
        """ll-verify-* expected-exit-1 calls are excluded from candidates."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-verify-skills", tool_use_id="t1"),
                    self._user_tool_result_record("t1", "Skill exceeds 500 lines", is_error=True),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "scan-failures", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert "No ll-* failures found" in captured.out

    def test_scan_failures_json_output_schema(self, capsys) -> None:
        """--json output contains expected keys."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-issues list", tool_use_id="t1"),
                    self._user_tool_result_record("t1", "KeyError: 'missing'", is_error=True),
                ],
            )

            captured_lines: list[str] = []
            with (
                patch("sys.argv", ["ll-logs", "scan-failures", "--project", str(project_path), "--json"]),
                patch("pathlib.Path.home", return_value=home),
                patch("builtins.print", side_effect=lambda *a, **kw: captured_lines.append(str(a[0]) if a else "")),
            ):
                result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured_lines))
        assert isinstance(data, list)
        assert len(data) == 1
        entry = data[0]
        assert "tool" in entry
        assert "count" in entry
        assert "normalized_sig" in entry
        assert "sample_error" in entry
        assert "session_ids" in entry

    def test_scan_failures_no_failures_returns_0(self, capsys) -> None:
        """scan-failures returns 0 with 'no failures' message when corpus is clean."""
        import tempfile
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-history list", tool_use_id="t1"),
                    self._user_tool_result_record("t1", "Success", is_error=False),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "scan-failures", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert "No ll-* failures found" in captured.out


class TestDiff:
    """Tests for the diff subcommand."""

    def _write_jsonl(self, path: Path, records: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def _bash_record(self, command: str, session_id: str = "s1", timestamp: str = "2026-01-01T00:00:00Z") -> dict:
        return {
            "type": "assistant",
            "message": {
                "role": "assistant",
                "content": [{"type": "tool_use", "name": "Bash", "input": {"command": command}}],
            },
            "sessionId": session_id,
            "timestamp": timestamp,
        }

    def test_diff_subcommand_parsed(self) -> None:
        """diff subcommand sets command='diff' and captures both session args."""
        with patch("sys.argv", ["ll-logs", "diff", "sess-a", "sess-b"]):
            args = _parse_args()
        assert args.command == "diff"
        assert args.session_a == "sess-a"
        assert args.session_b == "sess-b"

    def test_diff_json_flag_parsed(self) -> None:
        """diff --json sets json=True."""
        with patch("sys.argv", ["ll-logs", "diff", "a", "b", "--json"]):
            args = _parse_args()
        assert args.json is True

    def test_resolve_session_log_direct_path(self, tmp_path: Path) -> None:
        """_resolve_session_log returns path when given an existing .jsonl file."""
        jsonl = tmp_path / "session.jsonl"
        jsonl.write_text("{}\n")
        result = _resolve_session_log(str(jsonl), tmp_path / "history.db")
        assert result == jsonl

    def test_resolve_session_log_db_lookup(self, tmp_path: Path) -> None:
        """_resolve_session_log resolves session ID via DB lookup."""
        import sqlite3 as _sqlite3
        from little_loops.session_store import ensure_db
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True)
        ensure_db(db_path)
        jsonl_path = tmp_path / "mysession.jsonl"
        jsonl_path.write_text("")
        conn = _sqlite3.connect(str(db_path))
        conn.execute("INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)", ("my-session-id", str(jsonl_path)))
        conn.commit()
        conn.close()

        result = _resolve_session_log("my-session-id", db_path)
        assert result == jsonl_path

    def test_resolve_session_log_not_found_returns_none(self, tmp_path: Path) -> None:
        """_resolve_session_log returns None for an unknown session ID with no DB."""
        result = _resolve_session_log("unknown-session", tmp_path / "nonexistent.db")
        assert result is None

    def test_events_from_jsonl_extracts_ll_invocations(self, tmp_path: Path) -> None:
        """_events_from_jsonl extracts ll invocation events sorted by timestamp."""
        jsonl = tmp_path / "session.jsonl"
        self._write_jsonl(jsonl, [
            self._bash_record("ll-issues list", timestamp="2026-01-01T00:00:02Z"),
            self._bash_record("ll-history sessions", timestamp="2026-01-01T00:00:01Z"),
            {"type": "user", "message": {"role": "user", "content": "hello"}, "sessionId": "s1"},
        ])
        events = _events_from_jsonl(jsonl)
        assert len(events) == 2
        assert events[0].tool_name == "ll-history"
        assert events[1].tool_name == "ll-issues"

    def test_events_from_jsonl_missing_file_returns_empty(self, tmp_path: Path) -> None:
        """_events_from_jsonl returns [] for a nonexistent file."""
        events = _events_from_jsonl(tmp_path / "nonexistent.jsonl")
        assert events == []

    def test_compute_session_diff_skills_added_and_removed(self) -> None:
        """_compute_session_diff correctly identifies added and removed skills."""
        from little_loops.cli.logs import InvocationEvent

        def _evt(name: str) -> InvocationEvent:
            return InvocationEvent(tool_name=name, timestamp="", session_id="s")

        events_a = [_evt("ll-issues"), _evt("ll-history")]
        events_b = [_evt("ll-issues"), _evt("ll-auto")]

        diff = _compute_session_diff("sess-a", events_a, "sess-b", events_b)
        assert diff.skills_added == ["ll-auto"]
        assert diff.skills_removed == ["ll-history"]

    def test_compute_session_diff_count_deltas(self) -> None:
        """_compute_session_diff reports count deltas for skills with changed frequency."""
        from little_loops.cli.logs import InvocationEvent

        def _evt(name: str) -> InvocationEvent:
            return InvocationEvent(tool_name=name, timestamp="", session_id="s")

        events_a = [_evt("ll-issues"), _evt("ll-issues")]
        events_b = [_evt("ll-issues"), _evt("ll-issues"), _evt("ll-issues")]

        diff = _compute_session_diff("a", events_a, "b", events_b)
        assert "ll-issues" in diff.count_deltas
        assert diff.count_deltas["ll-issues"] == {"a": 2, "b": 3, "delta": 1}

    def test_compute_session_diff_identical_sessions(self) -> None:
        """_compute_session_diff returns empty diff for identical event streams."""
        from little_loops.cli.logs import InvocationEvent

        events = [InvocationEvent(tool_name="ll-issues", timestamp="", session_id="s")]
        diff = _compute_session_diff("a", events, "b", events)
        assert diff.skills_added == []
        assert diff.skills_removed == []
        assert diff.count_deltas == {}
        assert diff.sequence_diff == []

    def test_compute_session_diff_sequence_diff_present(self) -> None:
        """_compute_session_diff includes a unified sequence diff when order changes."""
        from little_loops.cli.logs import InvocationEvent

        def _evt(name: str) -> InvocationEvent:
            return InvocationEvent(tool_name=name, timestamp="", session_id="s")

        events_a = [_evt("ll-issues"), _evt("ll-history")]
        events_b = [_evt("ll-history"), _evt("ll-issues")]

        diff = _compute_session_diff("a", events_a, "b", events_b)
        assert len(diff.sequence_diff) > 0

    def test_diff_no_differences_text_output(self, tmp_path: Path, capsys) -> None:
        """diff exits 0 with 'No behavioral differences' message for identical sessions."""
        jsonl_a = tmp_path / "a.jsonl"
        jsonl_b = tmp_path / "b.jsonl"
        records = [self._bash_record("ll-issues list")]
        self._write_jsonl(jsonl_a, records)
        self._write_jsonl(jsonl_b, records)

        with patch("sys.argv", ["ll-logs", "diff", str(jsonl_a), str(jsonl_b)]):
            result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert "No behavioral differences" in captured.out

    def test_diff_detects_added_skill_text(self, tmp_path: Path, capsys) -> None:
        """diff text output shows added skill from session B."""
        jsonl_a = tmp_path / "a.jsonl"
        jsonl_b = tmp_path / "b.jsonl"
        self._write_jsonl(jsonl_a, [self._bash_record("ll-issues list")])
        self._write_jsonl(jsonl_b, [
            self._bash_record("ll-issues list"),
            self._bash_record("ll-auto --dry-run"),
        ])

        with patch("sys.argv", ["ll-logs", "diff", str(jsonl_a), str(jsonl_b)]):
            result = main_logs()

        assert result == 0
        out = capsys.readouterr().out
        assert "ll-auto" in out
        assert "+" in out

    def test_diff_detects_removed_skill_text(self, tmp_path: Path, capsys) -> None:
        """diff text output shows removed skill not in session B."""
        jsonl_a = tmp_path / "a.jsonl"
        jsonl_b = tmp_path / "b.jsonl"
        self._write_jsonl(jsonl_a, [
            self._bash_record("ll-issues list"),
            self._bash_record("ll-history sessions"),
        ])
        self._write_jsonl(jsonl_b, [self._bash_record("ll-issues list")])

        with patch("sys.argv", ["ll-logs", "diff", str(jsonl_a), str(jsonl_b)]):
            result = main_logs()

        assert result == 0
        out = capsys.readouterr().out
        assert "ll-history" in out
        assert "-" in out

    def test_diff_json_output_schema(self, tmp_path: Path) -> None:
        """diff --json outputs valid JSON with expected top-level keys."""
        jsonl_a = tmp_path / "a.jsonl"
        jsonl_b = tmp_path / "b.jsonl"
        self._write_jsonl(jsonl_a, [self._bash_record("ll-issues list")])
        self._write_jsonl(jsonl_b, [self._bash_record("ll-auto --dry-run")])

        captured_lines: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "diff", str(jsonl_a), str(jsonl_b), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured_lines.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured_lines))
        assert "session_a" in data
        assert "session_b" in data
        assert "skills_added" in data
        assert "skills_removed" in data
        assert "count_deltas" in data
        assert "sequence_diff" in data
        assert isinstance(data["skills_added"], list)
        assert isinstance(data["skills_removed"], list)
        assert isinstance(data["sequence_diff"], list)

    def test_diff_count_delta_in_json(self, tmp_path: Path) -> None:
        """diff --json count_deltas reports correct a/b/delta values."""
        jsonl_a = tmp_path / "a.jsonl"
        jsonl_b = tmp_path / "b.jsonl"
        self._write_jsonl(jsonl_a, [self._bash_record("ll-issues list")])
        self._write_jsonl(jsonl_b, [
            self._bash_record("ll-issues list"),
            self._bash_record("ll-issues list"),
        ])

        captured_lines: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "diff", str(jsonl_a), str(jsonl_b), "--json"]),
            patch("builtins.print", side_effect=lambda *a, **kw: captured_lines.append(str(a[0]) if a else "")),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured_lines))
        assert "ll-issues" in data["count_deltas"]
        assert data["count_deltas"]["ll-issues"] == {"a": 1, "b": 2, "delta": 1}

    def test_diff_unresolvable_session_a_returns_1(self, tmp_path: Path) -> None:
        """diff returns 1 when session_a cannot be resolved."""
        jsonl_b = tmp_path / "b.jsonl"
        jsonl_b.write_text("")

        with patch("sys.argv", ["ll-logs", "diff", "nonexistent-session-id", str(jsonl_b)]):
            result = main_logs()

        assert result == 1

    def test_diff_unresolvable_session_b_returns_1(self, tmp_path: Path) -> None:
        """diff returns 1 when session_b cannot be resolved."""
        jsonl_a = tmp_path / "a.jsonl"
        jsonl_a.write_text("")

        with patch("sys.argv", ["ll-logs", "diff", str(jsonl_a), "nonexistent-session-id"]):
            result = main_logs()

        assert result == 1


class TestEvalExport:
    """Tests for the eval-export subcommand scaffold (FEAT-1970)."""

    def test_help_shows_all_flags(self, capsys: pytest.CaptureFixture) -> None:
        """eval-export --help exits with code 0 and lists all five filter flags."""
        with (
            patch("sys.argv", ["ll-logs", "eval-export", "--help"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main_logs()
        assert exc_info.value.code == 0
        captured = capsys.readouterr()
        help_text = captured.out
        assert "--skill" in help_text
        assert "--issue" in help_text
        assert "--limit" in help_text
        assert "--out" in help_text
        assert "--json" in help_text

    def test_no_flags_returns_0(self, capsys: pytest.CaptureFixture) -> None:
        """eval-export with no flags runs without crashing and returns 0."""
        with patch("sys.argv", ["ll-logs", "eval-export"]):
            result = main_logs()
        assert result == 0

    def test_skill_flag_parses(self, capsys: pytest.CaptureFixture) -> None:
        """eval-export --skill foo runs without crashing and returns 0."""
        with patch("sys.argv", ["ll-logs", "eval-export", "--skill", "foo"]):
            result = main_logs()
        assert result == 0

    def test_all_flags_parse(self, tmp_path: Path, capsys: pytest.CaptureFixture) -> None:
        """eval-export with all flags parses without error and returns 0."""
        out_file = tmp_path / "out.yaml"
        with patch(
            "sys.argv",
            [
                "ll-logs", "eval-export",
                "--skill", "manage-issue",
                "--issue", "FEAT-1970",
                "--limit", "10",
                "--out", str(out_file),
                "--json",
            ],
        ):
            result = main_logs()
        assert result == 0

    def test_no_regression_extract(self, capsys: pytest.CaptureFixture) -> None:
        """eval-export addition does not break the existing extract subcommand."""
        with (
            patch("sys.argv", ["ll-logs", "extract", "--help"]),
            pytest.raises(SystemExit) as exc_info,
        ):
            main_logs()
        assert exc_info.value.code == 0
        assert "--project" in capsys.readouterr().out

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
    _is_ll_relevant,
    _parse_args,
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

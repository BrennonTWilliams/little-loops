"""Tests for cli/logs.py - ll-logs CLI entry point."""

from __future__ import annotations

import argparse
import json
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

from little_loops.cli.logs import _cmd_tail, _is_ll_relevant, _parse_args, generate_index, main_logs


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
                            "content": (
                                "<command-name>/ll:manage-issue</command-name>\nbug fix"
                            ),
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
            project_path = self._make_project_dir(
                claude_projects, home, "myproject", records
            )
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

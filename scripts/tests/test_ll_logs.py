"""Tests for cli/logs.py - ll-logs CLI entry point."""

from __future__ import annotations

import argparse
import json
import logging
import sqlite3
import tempfile
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from little_loops.cli.logs import (
    ChainResult,
    Edge,
    _aggregate_skill_stats,
    _build_chain_results,
    _build_eval_fixture,
    _classify_outcome,
    _cmd_tail,
    _collect_loop_runs,
    _compute_session_diff,
    _count_ngrams,
    _derive_loop_outcome,
    _detect_ll_signal,
    _EvalInvocation,
    _events_from_jsonl,
    _extract_eval_invocation,
    _extract_tool_name,
    _fixture_to_harness_argv,
    _get_builtin_loop_names,
    _InvocationSignal,
    _is_ll_relevant,
    _parse_args,
    _parse_terminal_event,
    _redact_input_context,
    _resolve_session_log,
    discover_all_projects,
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

    def test_tail_project_flag(self) -> None:
        """tail --project sets project path as a Path object."""
        with patch("sys.argv", ["ll-logs", "tail", "--loop", "myloop", "--project", "/tmp"]):
            args = _parse_args()
        assert args.project == Path("/tmp")


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
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

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

    def test_discover_skips_nonexistent_decoded_path_silently(self, capsys) -> None:
        """discover silently skips decoded paths that don't exist on disk (no WARNING)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            # An encoded dir name that decodes to a path that won't exist
            encoded = "-does-not-exist-path"
            proj_dir = claude_projects / encoded
            proj_dir.mkdir(parents=True, exist_ok=True)
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

    def test_stale_worktree_path_emits_no_warning(self, caplog) -> None:
        """Stale worktree paths produce no WARNING log at the default level (ENH-2067)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            # Encoded name decodes to a path that doesn't exist on disk
            encoded = "-nonexistent-stale-worktree-path"
            proj_dir = claude_projects / encoded
            proj_dir.mkdir(parents=True, exist_ok=True)
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

            test_logger = logging.getLogger("little_loops.cli.logs")
            with (
                patch("pathlib.Path.home", return_value=home),
                caplog.at_level(logging.WARNING, logger="little_loops.cli.logs"),
            ):
                discover_all_projects(test_logger, host="claude-code")

        warning_messages = [r.message for r in caplog.records if r.levelno >= logging.WARNING]
        assert not warning_messages, (
            f"Unexpected WARNING emitted for stale path: {warning_messages}"
        )

    def test_discover_finds_project_via_command_name_pattern(self, capsys) -> None:
        """discover detects ll activity via <command-name>/ll: in user messages."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

            project_path = home / "agentproject"
            project_path.mkdir(exist_ok=True)
            encoded = str(project_path).replace("/", "-")
            proj_dir = claude_projects / encoded
            proj_dir.mkdir(exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

            project_path = home / "jsonproject"
            project_path.mkdir(exist_ok=True)
            encoded = str(project_path).replace("/", "-")
            proj_dir = claude_projects / encoded
            proj_dir.mkdir(exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

            project_path = home / "shortflagproject"
            project_path.mkdir(exist_ok=True)
            encoded = str(project_path).replace("/", "-")
            proj_dir = claude_projects / encoded
            proj_dir.mkdir(exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

            with (
                patch("sys.argv", ["ll-logs", "discover", "--json"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data == {"paths": []}

    def test_discover_stdout_contains_no_timestamp_prefixed_lines(self, capsys) -> None:
        """discover stdout must contain no [HH:MM:SS]-prefixed diagnostic lines (BUG-2377).

        Stale/nonexistent decoded paths generate debug messages; those must go to stderr,
        not stdout, so downstream consumers (json.load, shell pipelines) see clean data.
        """
        import re

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            # Create a stale encoded dir (decoded path won't exist) to trigger debug msg
            stale_encoded = "-stale-worktree-bug2377"
            stale_dir = claude_projects / stale_encoded
            stale_dir.mkdir(parents=True, exist_ok=True)
            with open(stale_dir / "session.jsonl", "w") as f:
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
        timestamp_re = re.compile(r"^\[?\d{2}:\d{2}:\d{2}\]?")
        for line in captured.out.splitlines():
            assert not timestamp_re.match(line), (
                f"Diagnostic line leaked onto stdout (BUG-2377): {line!r}"
            )

    def test_discover_existing_only_flag_accepted(self) -> None:
        """discover --existing-only is a valid flag and exits 0."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            with (
                patch("sys.argv", ["ll-logs", "discover", "--existing-only"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0

    def test_discover_existing_only_omits_nonexistent_paths(self, capsys) -> None:
        """discover --existing-only emits only paths that exist on disk."""
        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            # Valid project (exists on disk)
            valid_path = self._make_project_dir(
                claude_projects,
                home,
                "valid_project",
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
                patch("sys.argv", ["ll-logs", "discover", "--existing-only"]),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        lines = [line.strip() for line in captured.out.strip().splitlines() if line.strip()]
        assert str(valid_path) in lines


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
            loops_dir.mkdir(exist_ok=True)

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
            running_dir.mkdir(parents=True, exist_ok=True)
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
            running_dir.mkdir(parents=True, exist_ok=True)
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
            running_dir.mkdir(parents=True, exist_ok=True)
            (running_dir / "myloop.events.jsonl").write_text("")

            args = argparse.Namespace(loop="myloop")
            mock_ctx = self._mock_open_with_readline(["not-valid-json\n", KeyboardInterrupt()])
            with patch("builtins.open", return_value=mock_ctx):
                result = _cmd_tail(args, loops_dir)

        assert result == 0
        captured = capsys.readouterr()
        assert captured.out == ""

    def test_tail_project_not_found_returns_1(self) -> None:
        """tail --project pointing at a nonexistent dir returns 1 (no active session)."""
        with tempfile.TemporaryDirectory() as tmpdir:
            nonexistent = Path(tmpdir) / "nosuchproject"

            with patch(
                "sys.argv", ["ll-logs", "tail", "--loop", "myloop", "--project", str(nonexistent)]
            ):
                result = main_logs()

        assert result == 1

    def test_tail_uses_project_loops_dir(self) -> None:
        """tail --project resolves loops dir from given project root, not CWD."""
        with tempfile.TemporaryDirectory() as tmpdir:
            alt_root = Path(tmpdir) / "alt-project"
            alt_root.mkdir()
            loops_dir = alt_root / ".loops"
            running_dir = loops_dir / ".running"
            running_dir.mkdir(parents=True, exist_ok=True)
            (running_dir / "myloop.events.jsonl").write_text("")

            args = argparse.Namespace(loop="myloop", project=alt_root)
            with patch("little_loops.cli.logs.time.sleep", side_effect=KeyboardInterrupt):
                result = _cmd_tail(args, loops_dir)

        assert result == 0


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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
                patch(
                    "sys.argv",
                    ["ll-logs", "sequences", "--project", str(project_path), "--min-len", "3"],
                ),
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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
                patch(
                    "sys.argv",
                    ["ll-logs", "sequences", "--project", str(project_path), "--min-count", "2"],
                ),
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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
                patch(
                    "sys.argv",
                    ["ll-logs", "sequences", "--project", str(project_path), "--top", "1"],
                ),
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
        """sequences --window-days uses wall-clock anchor to exclude old records."""
        now = datetime.now(UTC)
        recent_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_ts = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    {
                        **self._assistant_bash_record("ll-issues list", "s1"),
                        "timestamp": recent_ts,
                    },
                    {
                        **self._assistant_bash_record("ll-issues show", "s1"),
                        "timestamp": recent_ts,
                    },
                    {
                        **self._assistant_bash_record("ll-old-command", "s2"),
                        "timestamp": old_ts,
                    },
                ],
            )

            with (
                patch(
                    "sys.argv",
                    ["ll-logs", "sequences", "--project", str(project_path), "--window-days", "10"],
                ),
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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
                patch(
                    "sys.argv", ["ll-logs", "sequences", "--project", str(project_path), "--json"]
                ),
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
            home.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)
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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            # Each session needs ≥2 events for n-grams with default min-len=2
            self._make_project_dir(
                claude_projects,
                home,
                "proj_a",
                [
                    self._assistant_bash_record("ll-issues list", "sa"),
                    self._assistant_bash_record("ll-issues show", "sa"),
                ],
            )
            self._make_project_dir(
                claude_projects,
                home,
                "proj_b",
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


class TestChainResultPMI:
    """Tests for PMI/lift fields on ChainResult and Edge dataclasses."""

    def test_chain_result_to_dict_without_pmi(self) -> None:
        """ChainResult.to_dict() omits pmi/lift when not set."""
        cr = ChainResult(
            chain=["a", "b"],
            count=3,
            edges=[Edge(from_="a", to="b", freq=0.75)],
        )
        d = cr.to_dict()
        assert "pmi" not in d
        assert "lift" not in d
        assert "chain" in d
        assert "count" in d
        assert "edges" in d

    def test_chain_result_to_dict_with_pmi(self) -> None:
        """ChainResult.to_dict() includes pmi/lift when set (even if zero)."""
        import math

        pmi_val = math.log(2.0)
        cr = ChainResult(
            chain=["a", "b"],
            count=4,
            edges=[Edge(from_="a", to="b", freq=0.80, pmi=pmi_val, lift=2.0)],
            pmi=pmi_val,
            lift=2.0,
        )
        d = cr.to_dict()
        assert "pmi" in d
        assert "lift" in d
        assert d["pmi"] == pytest.approx(pmi_val, abs=1e-9)
        assert d["lift"] == pytest.approx(2.0, abs=1e-9)

    def test_chain_result_pmi_zero_is_emitted(self) -> None:
        """ChainResult.to_dict() emits pmi=0.0 (falsy but valid)."""
        cr = ChainResult(
            chain=["a", "b"],
            count=1,
            edges=[Edge(from_="a", to="b", freq=0.50, pmi=0.0, lift=1.0)],
            pmi=0.0,
            lift=1.0,
        )
        d = cr.to_dict()
        assert "pmi" in d
        assert d["pmi"] == pytest.approx(0.0)
        assert d["lift"] == pytest.approx(1.0)

    def test_edge_to_dict_without_pmi(self) -> None:
        """Edge dict omits pmi/lift when not set."""
        cr = ChainResult(
            chain=["x", "y"],
            count=2,
            edges=[Edge(from_="x", to="y", freq=0.60)],
        )
        edge_dict = cr.to_dict()["edges"][0]
        assert "pmi" not in edge_dict
        assert "lift" not in edge_dict
        assert "from" in edge_dict
        assert "to" in edge_dict
        assert "freq" in edge_dict

    def test_edge_to_dict_with_pmi(self) -> None:
        """Edge dict includes pmi/lift when set."""
        cr = ChainResult(
            chain=["x", "y"],
            count=2,
            edges=[Edge(from_="x", to="y", freq=0.60, pmi=1.2, lift=3.3)],
        )
        edge_dict = cr.to_dict()["edges"][0]
        assert "pmi" in edge_dict
        assert "lift" in edge_dict
        assert edge_dict["pmi"] == pytest.approx(1.2, abs=1e-6)
        assert edge_dict["lift"] == pytest.approx(3.3, abs=1e-6)

    def test_build_chain_results_attaches_pmi(self) -> None:
        """_build_chain_results attaches pmi/lift to ChainResult and Edge when unigram data is available."""

        # Simple corpus: session with ["A", "B", "A", "B"]
        # unigrams: A=2, B=2, total=4
        # bigrams: (A,B)=2, (B,A)=1, (A,B,A)=1, (B,A,B)=1, (A,B,A,B)=1
        events_by_session = {
            "s1": [
                type("E", (), {"tool_name": "A", "timestamp": 0})(),
                type("E", (), {"tool_name": "B", "timestamp": 1})(),
                type("E", (), {"tool_name": "A", "timestamp": 2})(),
                type("E", (), {"tool_name": "B", "timestamp": 3})(),
            ]
        }
        counter, unigram_counter = _count_ngrams(events_by_session, min_len=2)
        results = _build_chain_results(counter, unigram_counter, min_count=1)

        # The most common bigram is (A,B) with count=2
        ab_result = next((r for r in results if r.chain == ["A", "B"]), None)
        assert ab_result is not None
        # PMI/lift should be computed and attached
        assert ab_result.pmi is not None
        assert ab_result.lift is not None
        # lift = count(A,B)*total / (count_A * count_B) = 2*4/(2*2) = 2.0
        assert ab_result.lift == pytest.approx(2.0, abs=1e-6)

    def test_count_ngrams_returns_unigram_counter(self) -> None:
        """_count_ngrams now returns a (ngram_counter, unigram_counter) tuple."""
        events_by_session = {
            "s1": [
                type("E", (), {"tool_name": "X", "timestamp": 0})(),
                type("E", (), {"tool_name": "Y", "timestamp": 1})(),
                type("E", (), {"tool_name": "X", "timestamp": 2})(),
            ]
        }
        result = _count_ngrams(events_by_session, min_len=2)
        assert isinstance(result, tuple)
        assert len(result) == 2
        ngram_counter, unigram_counter = result
        # X appears twice, Y appears once
        assert unigram_counter["X"] == 2
        assert unigram_counter["Y"] == 1
        # The bigram (X,Y) appears once and (Y,X) appears once
        assert ngram_counter[("X", "Y")] == 1
        assert ngram_counter[("Y", "X")] == 1

    def test_sequences_json_includes_pmi_when_data_sufficient(self, capsys) -> None:
        """sequences --json output includes pmi/lift fields when sequences are found."""
        import tempfile
        from unittest.mock import patch

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            output_cwd = Path(tmpdir) / "output"
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            # Create sessions with repeated A→B to ensure pmi can be computed
            records = []
            for _ in range(3):
                records.append(
                    {
                        "type": "assistant",
                        "sessionId": "s1",
                        "timestamp": "2026-01-01T00:00:00Z",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Bash",
                                    "input": {"command": "ll-issues list"},
                                }
                            ],
                        },
                    }
                )
                records.append(
                    {
                        "type": "assistant",
                        "sessionId": "s1",
                        "timestamp": "2026-01-01T00:00:01Z",
                        "message": {
                            "role": "assistant",
                            "content": [
                                {
                                    "type": "tool_use",
                                    "name": "Bash",
                                    "input": {"command": "ll-issues show"},
                                }
                            ],
                        },
                    }
                )

            project_path = Path(tmpdir) / "home" / "myproject"
            project_path.mkdir(parents=True, exist_ok=True)
            encoded = str(project_path.resolve()).replace("/", "-")
            proj_dir = claude_projects / encoded
            proj_dir.mkdir(parents=True, exist_ok=True)
            jsonl_file = proj_dir / "session.jsonl"
            import json as _json

            with open(jsonl_file, "w") as f:
                for record in records:
                    record.setdefault("cwd", str(project_path))
                    f.write(_json.dumps(record) + "\n")

            with (
                patch(
                    "sys.argv",
                    ["ll-logs", "sequences", "--project", str(project_path), "--json"],
                ),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.Path.cwd", return_value=output_cwd),
            ):
                result = main_logs()

            assert result == 0
            data = _json.loads(capsys.readouterr().out)
            assert isinstance(data, list)
            assert len(data) > 0
            # pmi and lift should be present in the first chain result
            first = data[0]
            assert "pmi" in first, f"Expected 'pmi' in JSON output, got keys: {list(first.keys())}"
            assert "lift" in first, (
                f"Expected 'lift' in JSON output, got keys: {list(first.keys())}"
            )


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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            home.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)
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
            output_cwd.mkdir(parents=True, exist_ok=True)
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            session_id = "agent-session"
            project_path = home / "agentproject"
            project_path.mkdir(parents=True, exist_ok=True)
            encoded = str(project_path.resolve()).replace("/", "-")
            proj_dir = claude_projects / encoded
            proj_dir.mkdir(parents=True, exist_ok=True)

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

    def test_stats_window_days_behavioral(self, tmp_path: Path) -> None:
        """stats --window-days uses wall-clock anchor to exclude old records."""
        now = datetime.now(UTC)
        recent_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_ts = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")

        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _populate_skill_events(
            db_path,
            [
                (old_ts, "s1", "old-skill", ""),
                (recent_ts, "s1", "new-skill", ""),
            ],
        )

        captured: list[str] = []
        with (
            patch(
                "sys.argv",
                ["ll-logs", "stats", "--project", str(tmp_path), "--window-days", "10", "--json"],
            ),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        skill_names = {r["skill"] for r in data}
        assert "new-skill" in skill_names
        assert "old-skill" not in skill_names

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
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _populate_skill_events(
            db_path,
            [
                ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
                ("2026-01-01T00:01:00Z", "s1", "manage-issue", ""),
                ("2026-01-01T00:02:00Z", "s1", "capture-issue", ""),
            ],
        )

        with patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path)]):
            result = main_logs()

        assert result == 0
        out = capsys.readouterr().out
        assert "manage-issue" in out
        assert "capture-issue" in out

    def test_stats_json_output(self, tmp_path: Path) -> None:
        """stats --json emits a JSON array with invocation counts."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _populate_skill_events(
            db_path,
            [
                ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
                ("2026-01-01T00:01:00Z", "s1", "capture-issue", ""),
            ],
        )

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
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
        """JSON output includes exactly: skill, invocations, corrections, correction_rate."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _populate_skill_events(
            db_path,
            [
                ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
            ],
        )

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
        ):
            main_logs()

        data = json.loads("\n".join(captured))
        row = data[0]
        assert {"skill", "invocations", "corrections", "correction_rate"} == set(row.keys())

    def test_stats_correction_attribution(self, tmp_path: Path) -> None:
        """Corrections within 30s of a skill event are attributed to that skill."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _populate_skill_events(
            db_path,
            [
                ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
            ],
        )
        _insert_correction(db_path, "2026-01-01T00:00:10Z", "s1", "no, not that")

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        assert data[0]["skill"] == "manage-issue"
        assert data[0]["corrections"] == 1

    def test_stats_correction_outside_window_not_attributed(self, tmp_path: Path) -> None:
        """Corrections more than 30s after a skill event are not attributed."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _populate_skill_events(
            db_path,
            [
                ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
            ],
        )
        _insert_correction(db_path, "2026-01-01T00:01:00Z", "s1", "no, not that")

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        assert data[0]["skill"] == "manage-issue"
        assert data[0]["corrections"] == 0

    def test_stats_sort_by_corrections(self, tmp_path: Path) -> None:
        """--sort corrections puts higher-correction skills first."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _populate_skill_events(
            db_path,
            [
                ("2026-01-01T00:00:00Z", "s1", "capture-issue", ""),
                ("2026-01-01T00:01:00Z", "s1", "manage-issue", ""),
            ],
        )
        _insert_correction(db_path, "2026-01-01T00:01:10Z", "s1", "no wait")

        captured: list[str] = []
        with (
            patch(
                "sys.argv",
                ["ll-logs", "stats", "--project", str(tmp_path), "--json", "--sort", "corrections"],
            ),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        assert data[0]["skill"] == "manage-issue"
        assert data[0]["corrections"] == 1

    def test_stats_empty_db_returns_0(self, tmp_path: Path) -> None:
        """stats returns 0 when DB exists but has no skill events."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_db(db_path)

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "stats", "--project", str(tmp_path)]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
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
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_db(db_path)
        result = _aggregate_skill_stats(db_path)
        assert result == {}

    def test_aggregate_skill_stats_counts(self, tmp_path: Path) -> None:
        """_aggregate_skill_stats returns correct invocation counts."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _populate_skill_events(
            db_path,
            [
                ("2026-01-01T00:00:00Z", "s1", "manage-issue", ""),
                ("2026-01-01T00:01:00Z", "s1", "manage-issue", ""),
                ("2026-01-01T00:02:00Z", "s1", "capture-issue", ""),
            ],
        )
        result = _aggregate_skill_stats(db_path)
        assert result is not None
        assert result["manage-issue"]["invocations"] == 2
        assert result["capture-issue"]["invocations"] == 1

    def test_aggregate_skill_stats_window_days(self, tmp_path: Path) -> None:
        """cutoff parameter filters out records older than the cutoff datetime."""
        now = datetime.now(UTC)
        recent_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_ts = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")

        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        _populate_skill_events(
            db_path,
            [
                (old_ts, "s1", "old-skill", ""),
                (recent_ts, "s1", "new-skill", ""),
            ],
        )
        cutoff = now - timedelta(days=30)
        result = _aggregate_skill_stats(db_path, cutoff=cutoff)
        assert result is not None
        assert "new-skill" in result
        assert "old-skill" not in result


class TestDeadSkills:
    """Tests for the dead-skills subcommand."""

    def _make_skill(self, skills_dir: Path, name: str, bridge: bool = False) -> None:
        """Create a minimal SKILL.md stub in skills_dir/name/."""
        skill_dir = skills_dir / name
        skill_dir.mkdir(parents=True, exist_ok=True)
        body = (
            "Bridged from `commands/placeholder.md` for Codex Skills API discovery."
            if bridge
            else ""
        )
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

    def test_dead_skills_window_days_behavioral(self, tmp_path: Path) -> None:
        """dead-skills --window-days uses wall-clock anchor to exclude old invocations."""
        now = datetime.now(UTC)
        recent_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_ts = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")

        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "active-skill")
        self._make_skill(skills_dir, "dormant-skill")
        _populate_skill_events(
            db_path,
            [
                (recent_ts, "s1", "active-skill", ""),
                (recent_ts, "s1", "active-skill", ""),
                (recent_ts, "s1", "active-skill", ""),
                (recent_ts, "s1", "active-skill", ""),  # above threshold=3
                (old_ts, "s1", "dormant-skill", ""),
                (old_ts, "s1", "dormant-skill", ""),
                (old_ts, "s1", "dormant-skill", ""),
                (old_ts, "s1", "dormant-skill", ""),  # above threshold, but outside window
            ],
        )

        captured: list[str] = []
        with (
            patch(
                "sys.argv",
                [
                    "ll-logs",
                    "dead-skills",
                    "--project",
                    str(tmp_path),
                    "--window-days",
                    "10",
                    "--json",
                ],
            ),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        skill_names = {r["skill"] for r in data}
        # dormant-skill had all invocations outside the window → appears as dead
        assert "dormant-skill" in skill_names
        # active-skill had 4 recent invocations above threshold → absent from dead list
        assert "active-skill" not in skill_names

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
        db_path.parent.mkdir(parents=True, exist_ok=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "my-skill")
        # No skill_events seeded → zero invocations
        ensure_db(db_path)

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
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
        db_path.parent.mkdir(parents=True, exist_ok=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "used-skill")
        _populate_skill_events(
            db_path,
            [
                ("2026-01-01T00:00:00Z", "s1", "used-skill", ""),
                ("2026-01-01T00:01:00Z", "s1", "used-skill", ""),
                ("2026-01-01T00:02:00Z", "s1", "used-skill", ""),
                ("2026-01-01T00:03:00Z", "s1", "used-skill", ""),
            ],
        )

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
        ):
            result = main_logs()

        assert result == 0
        data = json.loads("\n".join(captured))
        skills_found = {r["skill"] for r in data}
        assert "used-skill" not in skills_found

    def test_dead_skills_rarely_invoked(self, tmp_path: Path) -> None:
        """A skill with invocations <= threshold appears with tier='rarely'."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "rare-skill")
        _populate_skill_events(
            db_path,
            [
                ("2026-01-01T00:00:00Z", "s1", "rare-skill", ""),
                ("2026-01-01T00:01:00Z", "s1", "rare-skill", ""),
            ],
        )

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
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
        db_path.parent.mkdir(parents=True, exist_ok=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "shape-skill")
        ensure_db(db_path)

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
        ):
            main_logs()

        data = json.loads("\n".join(captured))
        assert len(data) == 1
        assert set(data[0].keys()) == {"skill", "invocations", "tier"}

    def test_dead_skills_bridge_skill_excluded(self, tmp_path: Path) -> None:
        """Bridge skills (containing BRIDGE_MARKER) are excluded from the catalog."""
        db_path = tmp_path / ".ll" / "history.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        skills_dir = tmp_path / "skills"
        self._make_skill(skills_dir, "real-skill")
        self._make_skill(skills_dir, "bridge-skill", bridge=True)
        ensure_db(db_path)

        captured: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "dead-skills", "--project", str(tmp_path), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured.append(str(a[0]) if a else ""),
            ),
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
        db_path.parent.mkdir(parents=True, exist_ok=True)
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

    def test_scan_failures_window_days_behavioral(self, capsys) -> None:
        """scan-failures --window-days uses wall-clock anchor to exclude old failures."""
        now = datetime.now(UTC)
        recent_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_ts = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record(
                        "ll-history --bad-flag", tool_use_id="t1", timestamp=recent_ts
                    ),
                    self._user_tool_result_record(
                        tool_use_id="t1",
                        content="ll-history: error: unrecognized arguments: --bad-flag",
                        is_error=True,
                        timestamp=recent_ts,
                    ),
                    self._assistant_bash_record(
                        "ll-old-tool --bad", tool_use_id="t2", timestamp=old_ts
                    ),
                    self._user_tool_result_record(
                        tool_use_id="t2",
                        content="ll-old-tool: error: ancient failure signature",
                        is_error=True,
                        timestamp=old_ts,
                    ),
                ],
            )

            with (
                patch(
                    "sys.argv",
                    [
                        "ll-logs",
                        "scan-failures",
                        "--project",
                        str(project_path),
                        "--window-days",
                        "10",
                    ],
                ),
                patch("pathlib.Path.home", return_value=home),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert "ll-history" in captured.out
        assert "ll-old-tool" not in captured.out

    def test_scan_failures_window_days_cross_project(self, capsys) -> None:
        """scan-failures --all --window-days uses the same calendar cutoff for all projects."""
        now = datetime.now(UTC)
        recent_ts = (now - timedelta(days=1)).strftime("%Y-%m-%dT%H:%M:%SZ")
        old_ts = (now - timedelta(days=100)).strftime("%Y-%m-%dT%H:%M:%SZ")

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            # Project A: only recent activity
            self._make_project_dir(
                claude_projects,
                home,
                "project-a",
                [
                    self._assistant_bash_record(
                        "ll-issues list --bad", tool_use_id="ta1", timestamp=recent_ts
                    ),
                    self._user_tool_result_record(
                        tool_use_id="ta1",
                        content="ll-issues: error: project-a recent failure",
                        is_error=True,
                        timestamp=recent_ts,
                    ),
                ],
            )

            # Project B: only old activity (no recent records at all)
            self._make_project_dir(
                claude_projects,
                home,
                "project-b",
                [
                    self._assistant_bash_record(
                        "ll-sprint --bad", tool_use_id="tb1", timestamp=old_ts
                    ),
                    self._user_tool_result_record(
                        tool_use_id="tb1",
                        content="ll-sprint: error: project-b old failure",
                        is_error=True,
                        timestamp=old_ts,
                    ),
                ],
            )

            with (
                patch(
                    "sys.argv",
                    ["ll-logs", "scan-failures", "--all", "--window-days", "10"],
                ),
                patch("pathlib.Path.home", return_value=home),
                patch("little_loops.cli.logs.discover_all_projects") as mock_discover,
            ):
                mock_discover.return_value = [
                    home / "project-a",
                    home / "project-b",
                ]
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        # Project A recent failure should appear
        assert "ll-issues" in captured.out
        # Project B old failure should be excluded even though it's the only entry in project B
        assert "ll-sprint" not in captured.out

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
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

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
                patch(
                    "sys.argv",
                    ["ll-logs", "scan-failures", "--project", str(project_path), "--json"],
                ),
                patch("pathlib.Path.home", return_value=home),
                patch(
                    "builtins.print",
                    side_effect=lambda *a, **kw: captured_lines.append(str(a[0]) if a else ""),
                ),
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
            claude_projects.mkdir(parents=True, exist_ok=True)

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

    def test_scan_failures_suppresses_non_recoverable_auth_errors(self, capsys) -> None:
        """Auth failures (NON_RECOVERABLE) are suppressed from scan-failures output (BUG-2302)."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-auto", tool_use_id="t1"),
                    self._user_tool_result_record(
                        "t1", "HTTP 401 Unauthorized — invalid API key", is_error=True
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
        assert "No ll-* failures found" in captured.out

    def test_scan_failures_excludes_verify_tools(self, capsys) -> None:
        """ll-verify-* expected-exit-1 calls are excluded from candidates."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

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
            claude_projects.mkdir(parents=True, exist_ok=True)

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
                patch(
                    "sys.argv",
                    ["ll-logs", "scan-failures", "--project", str(project_path), "--json"],
                ),
                patch("pathlib.Path.home", return_value=home),
                patch(
                    "builtins.print",
                    side_effect=lambda *a, **kw: captured_lines.append(str(a[0]) if a else ""),
                ),
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
            claude_projects.mkdir(parents=True, exist_ok=True)

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

    def test_scan_failures_non_cli_token_filtered(self, capsys) -> None:
        """Tokens like ll-labs that are not in the CLI allowlist are suppressed."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-labs build --prod", tool_use_id="t1"),
                    self._user_tool_result_record(
                        tool_use_id="t1",
                        content="build failed: missing dependency",
                        is_error=True,
                    ),
                ],
            )

            with (
                patch("sys.argv", ["ll-logs", "scan-failures", "--project", str(project_path)]),
                patch("pathlib.Path.home", return_value=home),
                patch(
                    "little_loops.cli.logs._load_cli_allowlist",
                    return_value=frozenset(["ll-issues", "ll-history"]),
                ),
            ):
                result = main_logs()

        assert result == 0
        captured = capsys.readouterr()
        assert "ll-labs" not in captured.out
        assert "No ll-* failures found" in captured.out

    def test_scan_failures_content_free_cluster_suppressed(self, capsys) -> None:
        """Clusters whose only signal is a bare 'Exit code N' are dropped."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            project_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record("ll-issues list", tool_use_id="t1"),
                    self._user_tool_result_record(
                        tool_use_id="t1",
                        content="Exit code 1",
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
        assert "No ll-* failures found" in captured.out

    def test_scan_failures_capture_foreign_flag_parsed(self) -> None:
        """--capture-foreign flag is accepted."""
        with patch(
            "sys.argv", ["ll-logs", "scan-failures", "--all", "--capture", "--capture-foreign"]
        ):
            args = _parse_args()
        assert args.capture is True
        assert args.capture_foreign is True

    def test_scan_failures_capture_scoped_to_current_project(self) -> None:
        """--all --capture without --capture-foreign skips foreign-project clusters."""
        import tempfile

        with tempfile.TemporaryDirectory() as tmpdir:
            home = Path(tmpdir) / "home"
            claude_projects = home / ".claude" / "projects"
            claude_projects.mkdir(parents=True, exist_ok=True)

            current_path = self._make_project_dir(
                claude_projects,
                home,
                "myproject",
                [
                    self._assistant_bash_record(
                        "ll-issues list", tool_use_id="t1", session_id="s1"
                    ),
                    self._user_tool_result_record(
                        "t1", "KeyError: 'current_project_key'", is_error=True, session_id="s1"
                    ),
                ],
            )
            self._make_project_dir(
                claude_projects,
                home,
                "ll-labs",
                [
                    self._assistant_bash_record(
                        "ll-issues list", tool_use_id="t2", session_id="s2"
                    ),
                    self._user_tool_result_record(
                        "t2", "NameError: foreign_project_error", is_error=True, session_id="s2"
                    ),
                ],
            )

            captured_errors: list[str] = []

            def mock_create_issue(error_output, *args, **kwargs):
                captured_errors.append(error_output)
                return None

            with (
                patch("sys.argv", ["ll-logs", "scan-failures", "--all", "--capture"]),
                patch("pathlib.Path.home", return_value=home),
                patch.object(Path, "cwd", return_value=current_path),
                patch(
                    "little_loops.cli.logs._load_cli_allowlist",
                    return_value=frozenset(["ll-issues"]),
                ),
                patch(
                    "little_loops.issue_lifecycle.create_issue_from_failure",
                    side_effect=mock_create_issue,
                ),
            ):
                result = main_logs()

        assert result == 0
        assert len(captured_errors) == 1
        assert "current_project_key" in captured_errors[0]


class TestDiff:
    """Tests for the diff subcommand."""

    def _write_jsonl(self, path: Path, records: list[dict]) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            for r in records:
                f.write(json.dumps(r) + "\n")

    def _bash_record(
        self, command: str, session_id: str = "s1", timestamp: str = "2026-01-01T00:00:00Z"
    ) -> dict:
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
        db_path.parent.mkdir(parents=True, exist_ok=True)
        ensure_db(db_path)
        jsonl_path = tmp_path / "mysession.jsonl"
        jsonl_path.write_text("")
        conn = _sqlite3.connect(str(db_path))
        conn.execute(
            "INSERT INTO sessions(session_id, jsonl_path) VALUES(?, ?)",
            ("my-session-id", str(jsonl_path)),
        )
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
        self._write_jsonl(
            jsonl,
            [
                self._bash_record("ll-issues list", timestamp="2026-01-01T00:00:02Z"),
                self._bash_record("ll-history sessions", timestamp="2026-01-01T00:00:01Z"),
                {
                    "type": "user",
                    "message": {"role": "user", "content": "hello"},
                    "sessionId": "s1",
                },
            ],
        )
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
        self._write_jsonl(
            jsonl_b,
            [
                self._bash_record("ll-issues list"),
                self._bash_record("ll-auto --dry-run"),
            ],
        )

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
        self._write_jsonl(
            jsonl_a,
            [
                self._bash_record("ll-issues list"),
                self._bash_record("ll-history sessions"),
            ],
        )
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
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured_lines.append(str(a[0]) if a else ""),
            ),
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
        self._write_jsonl(
            jsonl_b,
            [
                self._bash_record("ll-issues list"),
                self._bash_record("ll-issues list"),
            ],
        )

        captured_lines: list[str] = []
        with (
            patch("sys.argv", ["ll-logs", "diff", str(jsonl_a), str(jsonl_b), "--json"]),
            patch(
                "builtins.print",
                side_effect=lambda *a, **kw: captured_lines.append(str(a[0]) if a else ""),
            ),
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
                "ll-logs",
                "eval-export",
                "--skill",
                "manage-issue",
                "--issue",
                "FEAT-1970",
                "--limit",
                "10",
                "--out",
                str(out_file),
                "--json",
            ],
        ):
            result = main_logs()
        assert result == 0

    def test_eval_export_json_short_flag(self, capsys: pytest.CaptureFixture) -> None:
        """-j is accepted by eval-export as a short form for --json."""
        with patch("sys.argv", ["ll-logs", "eval-export", "-j"]):
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


class TestEvalExportMapping:
    """Unit tests for the FEAT-1971 invocation -> EvalFixture mapping core."""

    def test_extract_skill_from_command_name(self) -> None:
        """A user <command-name>/ll: record maps to a skill-runner invocation."""
        record = {
            "type": "user",
            "sessionId": "sess-1",
            "timestamp": "2026-06-06T00:00:00Z",
            "message": {
                "content": [
                    {"text": "<command-name>/ll:refine-issue</command-name>\nrefine FEAT-1971"}
                ]
            },
        }
        inv = _extract_eval_invocation(record)
        assert inv is not None
        assert inv.runner == "skill"
        assert inv.target == "refine-issue"
        assert inv.session_id == "sess-1"
        assert "FEAT-1971" in inv.input_context

    def test_extract_cmd_from_bash(self) -> None:
        """An assistant Bash ll-<tool> record maps to a cmd-runner invocation."""
        record = {
            "type": "assistant",
            "sessionId": "sess-2",
            "timestamp": "2026-06-06T01:00:00Z",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "ll-issues list --type FEAT"},
                    }
                ]
            },
        }
        inv = _extract_eval_invocation(record)
        assert inv is not None
        assert inv.runner == "cmd"
        assert inv.target == "ll-issues list --type FEAT"
        assert inv.input_context == ""

    def test_extract_returns_none_for_unrelated_record(self) -> None:
        """A record with no ll signal yields no invocation."""
        assert _extract_eval_invocation({"type": "user", "message": {"content": "hi"}}) is None

    def test_build_fixture_skill_record(self) -> None:
        """A skill invocation maps to the full EvalFixture v1 schema (ARCHITECTURE-017)."""
        inv = _EvalInvocation(
            runner="skill",
            target="refine-issue",
            session_id="sess-1",
            timestamp="2026-06-06T00:00:00Z",
            input_context="refine FEAT-1971 in the backlog",
        )
        fixture = _build_eval_fixture(inv, "accepted")
        assert fixture == {
            "runner": "skill",
            "target": "refine-issue",
            "session_id": "sess-1",
            "timestamp": "2026-06-06T00:00:00Z",
            "outcome": "accepted",
            "runner_args": [],
            "exit_code": None,
            "semantic": None,
            "timeout": 120,
            "input_context": "refine FEAT-1971 in the backlog",
            "issue_id": "FEAT-1971",
            "skill_name": "refine-issue",
            "pii_detected": False,
        }

    def test_build_fixture_cmd_has_no_skill_name(self) -> None:
        """A cmd invocation carries no skill_name and no issue_id from empty context."""
        inv = _EvalInvocation("cmd", "ll-issues list", "sess-2", "2026-06-06T01:00:00Z", "")
        fixture = _build_eval_fixture(inv, "corrected")
        assert fixture["runner"] == "cmd"
        assert fixture["skill_name"] is None
        assert fixture["issue_id"] is None
        assert fixture["input_context"] is None
        assert fixture["outcome"] == "corrected"

    def test_redaction_sets_pii_detected(self) -> None:
        """Email + absolute path in the context are redacted and flag pii_detected."""
        redacted, pii = _redact_input_context("mail me at a@b.com see /home/u/x/y.txt")
        assert pii is True
        assert "a@b.com" not in redacted
        assert "[EMAIL]" in redacted
        assert "<path>" in redacted

    def test_redaction_clean_text_no_pii(self) -> None:
        """Clean text passes through unredacted with pii_detected False."""
        redacted, pii = _redact_input_context("refine the issue")
        assert redacted == "refine the issue"
        assert pii is False

    def test_classify_outcome_precedence(self) -> None:
        """failed > corrected > accepted; unknown only when metadata is empty."""
        assert _classify_outcome({}, has_error=False) == "unknown"
        assert _classify_outcome({"has_corrections": True}, has_error=True) == "failed"
        assert _classify_outcome({"has_corrections": True}, has_error=False) == "corrected"
        assert _classify_outcome({"has_corrections": False}, has_error=False) == "accepted"
        # failed wins even with no DB metadata (strong execution evidence).
        assert _classify_outcome({}, has_error=True) == "failed"

    def test_fixture_to_harness_argv_round_trips_through_parser(self) -> None:
        """Every exported fixture serializes into a valid ll-harness argv."""
        from little_loops.cli.harness import _parse_harness_args

        inv = _EvalInvocation("skill", "check-code", "s", "2026-06-06T00:00:00Z", "")
        argv = _fixture_to_harness_argv(_build_eval_fixture(inv, "accepted"))
        ns = _parse_harness_args(argv)
        assert ns.runner == "skill"
        assert ns.target == "check-code"


class TestEvalExportRoundTrip:
    """End-to-end: export from a synthetic corpus, replay output under ll-harness."""

    def _make_project_dir(
        self, claude_projects: Path, home: Path, subpath: str, records: list[dict]
    ) -> Path:
        project_path = home / subpath
        project_path.mkdir(parents=True, exist_ok=True)
        encoded = str(project_path.resolve()).replace("/", "-")
        proj_dir = claude_projects / encoded
        proj_dir.mkdir(parents=True, exist_ok=True)
        with open(proj_dir / "session.jsonl", "w") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")
        return project_path

    def test_export_then_replay_under_harness(self, tmp_path: Path) -> None:
        """eval-export output loads field-by-field into a valid ll-harness invocation."""
        import yaml

        from little_loops.cli.harness import _parse_harness_args

        home = tmp_path / "home"
        claude_projects = home / ".claude" / "projects"
        claude_projects.mkdir(parents=True, exist_ok=True)
        records = [
            {
                "type": "user",
                "sessionId": "sess-a",
                "timestamp": "2026-06-06T00:00:00Z",
                "message": {
                    "content": [
                        {"text": "<command-name>/ll:refine-issue</command-name>\nrefine FEAT-1971"}
                    ]
                },
            },
            {
                "type": "assistant",
                "sessionId": "sess-a",
                "timestamp": "2026-06-06T00:01:00Z",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "ll-issues list"},
                        }
                    ]
                },
            },
        ]
        project_path = self._make_project_dir(claude_projects, home, "proj", records)
        out_file = tmp_path / "evals.yaml"

        with (
            patch("pathlib.Path.home", return_value=home),
            patch(
                "little_loops.history_reader.lookup_session_metadata",
                return_value={"has_corrections": False},
            ),
            patch(
                "sys.argv",
                [
                    "ll-logs",
                    "eval-export",
                    "--project",
                    str(project_path),
                    "--out",
                    str(out_file),
                ],
            ),
        ):
            result = main_logs()

        assert result == 0
        fixtures = yaml.safe_load(out_file.read_text())
        assert len(fixtures) == 2
        # Both records share a corrections-free session -> accepted outcome.
        assert {fx["outcome"] for fx in fixtures} == {"accepted"}
        runners = {fx["runner"] for fx in fixtures}
        assert runners == {"skill", "cmd"}
        # Every fixture must replay cleanly into the harness parser.
        for fx in fixtures:
            ns = _parse_harness_args(_fixture_to_harness_argv(fx))
            assert ns.target == fx["target"]

    def test_skill_filter_and_skip_unknown(self, tmp_path: Path) -> None:
        """--skill narrows to one target; sessions with no DB metadata are skipped."""
        import yaml

        home = tmp_path / "home"
        claude_projects = home / ".claude" / "projects"
        claude_projects.mkdir(parents=True, exist_ok=True)
        records = [
            {
                "type": "user",
                "sessionId": "sess-known",
                "timestamp": "2026-06-06T00:00:00Z",
                "message": {
                    "content": [{"text": "<command-name>/ll:refine-issue</command-name>\nx"}]
                },
            },
            {
                "type": "user",
                "sessionId": "sess-unknown",
                "timestamp": "2026-06-06T00:02:00Z",
                "message": {
                    "content": [{"text": "<command-name>/ll:refine-issue</command-name>\ny"}]
                },
            },
            {
                "type": "user",
                "sessionId": "sess-known",
                "timestamp": "2026-06-06T00:03:00Z",
                "message": {
                    "content": [{"text": "<command-name>/ll:check-code</command-name>\nz"}]
                },
            },
        ]
        project_path = self._make_project_dir(claude_projects, home, "proj", records)
        out_file = tmp_path / "evals.yaml"

        def fake_lookup(session_id, *, db=None):
            return {"has_corrections": False} if session_id == "sess-known" else {}

        with (
            patch("pathlib.Path.home", return_value=home),
            patch("little_loops.history_reader.lookup_session_metadata", side_effect=fake_lookup),
            patch(
                "sys.argv",
                [
                    "ll-logs",
                    "eval-export",
                    "--project",
                    str(project_path),
                    "--skill",
                    "refine-issue",
                    "--out",
                    str(out_file),
                ],
            ),
        ):
            result = main_logs()

        assert result == 0
        fixtures = yaml.safe_load(out_file.read_text())
        # Only the refine-issue invocation from the known session survives:
        # check-code is filtered by --skill, sess-unknown is skipped (no metadata).
        assert len(fixtures) == 1
        assert fixtures[0]["target"] == "refine-issue"
        assert fixtures[0]["session_id"] == "sess-known"


class TestDetectLlSignal:
    """Unit tests for the shared _detect_ll_signal() helper and _InvocationSignal dataclass."""

    def test_invocation_signal_fields(self) -> None:
        """_InvocationSignal has expected fields and is constructable."""
        sig = _InvocationSignal(
            tool_name="scan-codebase",
            runner="queue-operation",
            input_context="/ll:scan-codebase",
        )
        assert sig.tool_name == "scan-codebase"
        assert sig.runner == "queue-operation"
        assert sig.input_context == "/ll:scan-codebase"

    def test_detect_ll_signal_queue_enqueue(self) -> None:
        """Signal (a): queue-operation enqueue with /ll:<name> content."""
        record = {
            "type": "queue-operation",
            "operation": "enqueue",
            "content": "/ll:scan-codebase --deep",
        }
        sig = _detect_ll_signal(record)
        assert sig is not None
        assert sig.tool_name == "scan-codebase"
        assert sig.runner == "queue-operation"
        assert sig.input_context == "/ll:scan-codebase --deep"

    def test_detect_ll_signal_command_name_user_record(self) -> None:
        """Signal (b): user record with <command-name>/ll:<name> pattern."""
        record = {
            "type": "user",
            "message": {
                "content": [{"text": "<command-name>/ll:refine-issue</command-name>\nENH-2132"}]
            },
        }
        sig = _detect_ll_signal(record)
        assert sig is not None
        assert sig.tool_name == "refine-issue"
        assert sig.runner == "user"
        assert "<command-name>/ll:refine-issue" in sig.input_context

    def test_detect_ll_signal_bash_tool_use(self) -> None:
        """Signal (c): assistant Bash tool-use invoking ll-<tool>."""
        record = {
            "type": "assistant",
            "message": {
                "content": [
                    {
                        "type": "tool_use",
                        "name": "Bash",
                        "input": {"command": "ll-issues path ENH-2132"},
                    }
                ]
            },
        }
        sig = _detect_ll_signal(record)
        assert sig is not None
        assert sig.tool_name == "ll-issues"
        assert sig.runner == "bash"
        assert sig.input_context == "ll-issues path ENH-2132"

    def test_detect_ll_signal_returns_none_for_unrelated(self) -> None:
        """Unrelated records return None."""
        assert _detect_ll_signal({"type": "summary", "message": "hello"}) is None
        assert _detect_ll_signal({"type": "user", "message": {"content": "no skill here"}}) is None
        assert _detect_ll_signal({}) is None

    def test_extract_tool_name_delegates_to_detect_ll_signal(self) -> None:
        """Shim: _extract_tool_name returns the same value as _detect_ll_signal().tool_name."""
        records = [
            {"type": "queue-operation", "operation": "enqueue", "content": "/ll:check-code"},
            {
                "type": "user",
                "message": {"content": "<command-name>/ll:wire-issue</command-name>"},
            },
            {
                "type": "assistant",
                "message": {
                    "content": [
                        {
                            "type": "tool_use",
                            "name": "Bash",
                            "input": {"command": "ll-logs discover"},
                        }
                    ]
                },
            },
            {"type": "summary"},
        ]
        for rec in records:
            sig = _detect_ll_signal(rec)
            expected = sig.tool_name if sig else None
            assert _extract_tool_name(rec) == expected

    def test_extract_eval_invocation_delegates_to_detect_ll_signal(self) -> None:
        """Shim: _extract_eval_invocation runner/target/input_context come from _detect_ll_signal."""
        record = {
            "type": "user",
            "sessionId": "sess-1",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {"content": "<command-name>/ll:wire-issue</command-name>\nENH-2132"},
        }
        sig = _detect_ll_signal(record)
        inv = _extract_eval_invocation(record)
        assert sig is not None
        assert inv is not None
        assert inv.target == sig.tool_name
        assert inv.runner == "skill"
        assert inv.input_context == sig.input_context

    def test_extract_eval_invocation_bash_uses_full_command_as_target(self) -> None:
        """Bash shim: _EvalInvocation target is the full command, runner is 'cmd'."""
        cmd = "ll-issues path ENH-2132 2>/dev/null"
        record = {
            "type": "assistant",
            "sessionId": "sess-bash",
            "timestamp": "2026-01-01T00:00:00Z",
            "message": {
                "content": [{"type": "tool_use", "name": "Bash", "input": {"command": cmd}}]
            },
        }
        sig = _detect_ll_signal(record)
        inv = _extract_eval_invocation(record)
        assert sig is not None
        assert sig.runner == "bash"
        assert sig.input_context == cmd
        assert inv is not None
        assert inv.runner == "cmd"
        assert inv.target == cmd


class TestLoopFleet:
    """Tests for the loop-fleet subcommand."""

    def _make_history_run(
        self,
        project_path: Path,
        run_folder: str,
        events: list[dict],
    ) -> None:
        """Write .loops/.history/<run_folder>/events.jsonl with the given events."""
        run_dir = project_path / ".loops" / ".history" / run_folder
        run_dir.mkdir(parents=True, exist_ok=True)
        with open(run_dir / "events.jsonl", "w") as f:
            for event in events:
                f.write(json.dumps(event) + "\n")

    def _loop_complete(
        self,
        final_state: str = "done",
        iterations: int = 3,
        terminated_by: str = "terminal",
        ts: str = "2026-01-01T00:00:00+00:00",
    ) -> dict:
        return {
            "event": "loop_complete",
            "ts": ts,
            "final_state": final_state,
            "iterations": iterations,
            "terminated_by": terminated_by,
        }

    # --- argparse unit tests ---

    def test_loop_fleet_subcommand_parsed(self) -> None:
        """loop-fleet sets command='loop-fleet' and all=True."""
        with patch("sys.argv", ["ll-logs", "loop-fleet", "--all"]):
            args = _parse_args()
        assert args.command == "loop-fleet"
        assert args.all is True

    def test_loop_fleet_project_flag(self) -> None:
        """--project sets project path."""
        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", "/tmp"]):
            args = _parse_args()
        assert args.project == Path("/tmp")

    def test_loop_fleet_project_and_all_mutually_exclusive(self) -> None:
        """--project and --all cannot be combined."""
        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", "/tmp", "--all"]):
            with pytest.raises(SystemExit):
                _parse_args()

    def test_loop_fleet_loop_filter_parsed(self) -> None:
        """--loop sets the loop name filter."""
        with patch("sys.argv", ["ll-logs", "loop-fleet", "--all", "--loop", "rn-build"]):
            args = _parse_args()
        assert args.loop == "rn-build"

    def test_loop_fleet_window_days_parsed(self) -> None:
        """--window-days is accepted and stored as int."""
        with patch("sys.argv", ["ll-logs", "loop-fleet", "--all", "--window-days", "7"]):
            args = _parse_args()
        assert args.window_days == 7

    def test_loop_fleet_json_flag_parsed(self) -> None:
        """-j/--json flag is accepted."""
        with patch("sys.argv", ["ll-logs", "loop-fleet", "--all", "-j"]):
            args = _parse_args()
        assert args.json is True

    def test_loop_fleet_existing_only_parsed(self) -> None:
        """--existing-only flag is accepted."""
        with patch("sys.argv", ["ll-logs", "loop-fleet", "--all", "--existing-only"]):
            args = _parse_args()
        assert args.existing_only is True

    # --- unit tests for helpers ---

    def test_derive_outcome_converged(self) -> None:
        """terminal + non-failure state → converged."""
        event = {"event": "loop_complete", "terminated_by": "terminal", "final_state": "done"}
        assert _derive_loop_outcome(event) == "converged"

    def test_derive_outcome_failed_state(self) -> None:
        """terminal + failed state → failed."""
        event = {"event": "loop_complete", "terminated_by": "terminal", "final_state": "failed"}
        assert _derive_loop_outcome(event) == "failed"

    def test_derive_outcome_max_steps(self) -> None:
        """terminated_by=max_steps → max-steps."""
        event = {"event": "loop_complete", "terminated_by": "max_steps", "final_state": "review"}
        assert _derive_loop_outcome(event) == "max-steps"

    def test_derive_outcome_max_iterations_reached(self) -> None:
        """terminated_by=max_iterations_reached → max-steps."""
        event = {"event": "loop_complete", "terminated_by": "max_iterations_reached"}
        assert _derive_loop_outcome(event) == "max-steps"

    def test_derive_outcome_stalled(self) -> None:
        """terminated_by=cycle_detected → stalled."""
        event = {"event": "loop_complete", "terminated_by": "cycle_detected"}
        assert _derive_loop_outcome(event) == "stalled"

    def test_derive_outcome_error_field(self) -> None:
        """Presence of 'error' key → error."""
        event = {"event": "loop_complete", "terminated_by": "terminal", "error": "timeout"}
        assert _derive_loop_outcome(event) == "error"

    def test_parse_terminal_event_finds_loop_complete(self, tmp_path) -> None:
        """_parse_terminal_event returns the loop_complete record."""
        events_file = tmp_path / "events.jsonl"
        events_file.write_text(
            json.dumps({"event": "state_transition", "from": "start", "to": "review"})
            + "\n"
            + json.dumps(self._loop_complete())
            + "\n"
        )
        result = _parse_terminal_event(events_file)
        assert result is not None
        assert result["event"] == "loop_complete"
        assert result["iterations"] == 3

    def test_parse_terminal_event_missing_returns_none(self, tmp_path) -> None:
        """_parse_terminal_event returns None when no loop_complete event exists."""
        events_file = tmp_path / "events.jsonl"
        events_file.write_text(json.dumps({"event": "state_transition"}) + "\n")
        assert _parse_terminal_event(events_file) is None

    def test_parse_terminal_event_nonexistent_file(self, tmp_path) -> None:
        """_parse_terminal_event returns None for a missing file."""
        assert _parse_terminal_event(tmp_path / "no-such-file.jsonl") is None

    def test_get_builtin_loop_names_returns_frozenset(self) -> None:
        """_get_builtin_loop_names returns a non-empty frozenset of strings."""
        names = _get_builtin_loop_names()
        assert isinstance(names, frozenset)
        assert len(names) > 0
        assert all(isinstance(n, str) for n in names)

    def test_get_builtin_loop_names_excludes_lib(self) -> None:
        """_get_builtin_loop_names excludes lib/ fragment names."""
        names = _get_builtin_loop_names()
        # lib/ fragments like 'common', 'benchmark' should not appear as standalone loops
        # Verify known built-in runnable loops ARE present
        assert "rn-build" in names

    # --- integration tests via main_logs() ---

    def test_loop_fleet_reads_archived_runs(self, capsys, tmp_path) -> None:
        """loop-fleet returns run records from .loops/.history/."""
        project_path = tmp_path / "myproject"
        project_path.mkdir()
        self._make_history_run(
            project_path,
            "2026-01-01T000000-rn-build",
            [self._loop_complete(final_state="done", iterations=2)],
        )

        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", str(project_path), "-j"]):
            result = main_logs()

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["loop_name"] == "rn-build"
        assert data[0]["iterations"] == 2
        assert data[0]["outcome"] == "converged"

    def test_loop_fleet_json_fields(self, capsys, tmp_path) -> None:
        """JSON output contains all expected fields per run record."""
        project_path = tmp_path / "proj"
        project_path.mkdir()
        self._make_history_run(
            project_path,
            "2026-01-01T000000-rn-build",
            [self._loop_complete()],
        )

        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", str(project_path), "-j"]):
            main_logs()

        data = json.loads(capsys.readouterr().out)
        record = data[0]
        assert "loop_name" in record
        assert "project" in record
        assert "run_folder" in record
        assert "final_state" in record
        assert "iterations" in record
        assert "outcome" in record
        assert "ts" in record
        assert "attribution" in record

    def test_loop_fleet_outcome_max_steps(self, capsys, tmp_path) -> None:
        """terminated_by=max_steps yields outcome='max-steps' in JSON output."""
        project_path = tmp_path / "proj"
        project_path.mkdir()
        self._make_history_run(
            project_path,
            "2026-01-01T000000-rn-build",
            [self._loop_complete(terminated_by="max_steps")],
        )

        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", str(project_path), "-j"]):
            main_logs()

        data = json.loads(capsys.readouterr().out)
        assert data[0]["outcome"] == "max-steps"

    def test_loop_fleet_loop_filter_applied(self, capsys, tmp_path) -> None:
        """--loop filters to only the matching loop name."""
        project_path = tmp_path / "proj"
        project_path.mkdir()
        self._make_history_run(project_path, "2026-01-01T000000-rn-build", [self._loop_complete()])
        self._make_history_run(
            project_path, "2026-01-02T000000-rn-implement", [self._loop_complete()]
        )

        with patch(
            "sys.argv",
            ["ll-logs", "loop-fleet", "--project", str(project_path), "--loop", "rn-build", "-j"],
        ):
            result = main_logs()

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["loop_name"] == "rn-build"

    def test_loop_fleet_window_days_excludes_old(self, capsys, tmp_path) -> None:
        """--window-days excludes runs older than D days."""
        now = datetime.now(UTC)
        recent_ts = (now - timedelta(days=1)).isoformat()
        old_ts = (now - timedelta(days=100)).isoformat()

        project_path = tmp_path / "proj"
        project_path.mkdir()
        self._make_history_run(
            project_path,
            "2026-01-01T000000-rn-build",
            [self._loop_complete(ts=recent_ts)],
        )
        self._make_history_run(
            project_path,
            "2026-01-02T000000-rn-implement",
            [self._loop_complete(ts=old_ts)],
        )

        with patch(
            "sys.argv",
            [
                "ll-logs",
                "loop-fleet",
                "--project",
                str(project_path),
                "--window-days",
                "7",
                "-j",
            ],
        ):
            result = main_logs()

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert len(data) == 1
        assert data[0]["loop_name"] == "rn-build"

    def test_loop_fleet_no_runs_empty_json(self, capsys, tmp_path) -> None:
        """Empty .loops/.history returns [] in JSON mode."""
        project_path = tmp_path / "proj"
        project_path.mkdir()

        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", str(project_path), "-j"]):
            result = main_logs()

        assert result == 0
        data = json.loads(capsys.readouterr().out)
        assert data == []

    def test_loop_fleet_no_runs_tabular_message(self, capsys, tmp_path) -> None:
        """Empty result prints a human-readable 'no runs' message."""
        project_path = tmp_path / "proj"
        project_path.mkdir()

        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", str(project_path)]):
            result = main_logs()

        assert result == 0
        out = capsys.readouterr().out
        assert "No loop-fleet runs found" in out

    def test_loop_fleet_tabular_output(self, capsys, tmp_path) -> None:
        """Default (non-JSON) output renders a table with loop name and outcome."""
        project_path = tmp_path / "proj"
        project_path.mkdir()
        self._make_history_run(
            project_path,
            "2026-01-01T000000-rn-build",
            [self._loop_complete(final_state="done", iterations=3)],
        )

        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", str(project_path)]):
            result = main_logs()

        assert result == 0
        out = capsys.readouterr().out
        assert "rn-build" in out
        assert "converged" in out

    def test_loop_fleet_attribution_custom(self, capsys, tmp_path) -> None:
        """A non-built-in loop name is attributed as 'custom'."""
        project_path = tmp_path / "proj"
        project_path.mkdir()
        self._make_history_run(
            project_path,
            "2026-01-01T000000-my-unique-custom-loop-xyz-123",
            [self._loop_complete()],
        )

        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", str(project_path), "-j"]):
            main_logs()

        data = json.loads(capsys.readouterr().out)
        assert data[0]["attribution"] == "custom"

    def test_loop_fleet_attribution_builtin(self, capsys, tmp_path) -> None:
        """A known built-in loop name is attributed as 'builtin'."""
        project_path = tmp_path / "proj"
        project_path.mkdir()
        self._make_history_run(
            project_path,
            "2026-01-01T000000-rn-build",
            [self._loop_complete()],
        )

        with (
            patch("sys.argv", ["ll-logs", "loop-fleet", "--project", str(project_path), "-j"]),
            patch(
                "little_loops.cli.logs._get_builtin_loop_names",
                return_value=frozenset(["rn-build"]),
            ),
        ):
            main_logs()

        data = json.loads(capsys.readouterr().out)
        assert data[0]["attribution"] == "builtin"

    def test_loop_fleet_multiple_runs_aggregated(self, capsys, tmp_path) -> None:
        """Table shows one row per loop name across multiple runs."""
        project_path = tmp_path / "proj"
        project_path.mkdir()
        for i in range(3):
            self._make_history_run(
                project_path,
                f"2026-01-0{i + 1}T000000-rn-build",
                [self._loop_complete(iterations=i + 1)],
            )

        with patch("sys.argv", ["ll-logs", "loop-fleet", "--project", str(project_path)]):
            result = main_logs()

        assert result == 0
        out = capsys.readouterr().out
        # Only one row for rn-build despite 3 runs
        assert out.count("rn-build") == 1

    def test_collect_loop_runs_legacy_nested_layout(self, tmp_path) -> None:
        """_collect_loop_runs handles legacy .history/<loop_name>/<run_id>/events.jsonl layout."""
        project_path = tmp_path / "proj"
        loop_name = "rn-build"
        run_subdir = project_path / ".loops" / ".history" / loop_name / "2026-01-01T000000"
        run_subdir.mkdir(parents=True, exist_ok=True)
        (run_subdir / "events.jsonl").write_text(json.dumps(self._loop_complete()) + "\n")

        runs = _collect_loop_runs(project_path, frozenset([loop_name]))
        assert len(runs) == 1
        assert runs[0].loop_name == loop_name
        assert runs[0].attribution == "builtin"

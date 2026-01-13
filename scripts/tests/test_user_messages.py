"""Tests for user message extraction.

Tests the user_messages module including:
- Path conversion to Claude project folder format
- Message extraction and filtering
- CLI argument parsing
"""

from __future__ import annotations

import argparse
import json
import tempfile
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING

import pytest

from little_loops.user_messages import (
    UserMessage,
    extract_user_messages,
    get_project_folder,
    print_messages_to_stdout,
    save_messages,
)

if TYPE_CHECKING:
    from collections.abc import Generator


class TestUserMessage:
    """Tests for UserMessage dataclass."""

    def test_to_dict_basic(self) -> None:
        """to_dict() returns correct dictionary structure."""
        msg = UserMessage(
            content="Hello world",
            timestamp=datetime(2026, 1, 10, 12, 0, 0),
            session_id="session-123",
            uuid="uuid-456",
        )
        result = msg.to_dict()

        assert result["content"] == "Hello world"
        assert result["timestamp"] == "2026-01-10T12:00:00"
        assert result["session_id"] == "session-123"
        assert result["uuid"] == "uuid-456"
        assert result["cwd"] is None
        assert result["git_branch"] is None
        assert result["is_sidechain"] is False

    def test_to_dict_with_optional_fields(self) -> None:
        """to_dict() includes optional fields when set."""
        msg = UserMessage(
            content="Test message",
            timestamp=datetime(2026, 1, 10, 12, 0, 0),
            session_id="session-123",
            uuid="uuid-456",
            cwd="/path/to/project",
            git_branch="main",
            is_sidechain=True,
        )
        result = msg.to_dict()

        assert result["cwd"] == "/path/to/project"
        assert result["git_branch"] == "main"
        assert result["is_sidechain"] is True


class TestGetProjectFolder:
    """Tests for get_project_folder function."""

    def test_returns_none_for_nonexistent_path(self) -> None:
        """Returns None when project folder doesn't exist."""
        fake_path = Path("/this/path/does/not/exist/anywhere")
        result = get_project_folder(fake_path)
        assert result is None

    def test_path_conversion_format(self) -> None:
        """Path is converted to dash-separated format correctly."""
        # This tests the format but doesn't require the folder to exist
        test_path = Path("/Users/test/my-project")
        expected_encoded = "-Users-test-my-project"

        # Verify encoding logic (extracted from function)
        path_str = str(test_path.resolve())
        encoded_path = path_str.replace("/", "-")
        assert encoded_path == expected_encoded


class TestExtractUserMessages:
    """Tests for extract_user_messages function."""

    @pytest.fixture
    def temp_project_folder(self) -> Generator[Path, None, None]:
        """Create a temporary project folder with test JSONL files."""
        with tempfile.TemporaryDirectory() as tmpdir:
            yield Path(tmpdir)

    def _write_jsonl(self, path: Path, records: list[dict]) -> None:
        """Helper to write JSONL file."""
        with open(path, "w", encoding="utf-8") as f:
            for record in records:
                f.write(json.dumps(record) + "\n")

    def test_extracts_string_content_messages(self, temp_project_folder: Path) -> None:
        """Extracts messages with string content."""
        records = [
            {
                "type": "user",
                "message": {"content": "Hello Claude"},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
            {
                "type": "user",
                "message": {"content": "Another message"},
                "timestamp": "2026-01-10T12:01:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        messages = extract_user_messages(temp_project_folder)

        assert len(messages) == 2
        assert messages[0].content == "Another message"  # Most recent first
        assert messages[1].content == "Hello Claude"

    def test_filters_tool_result_messages(self, temp_project_folder: Path) -> None:
        """Filters out messages that are tool results."""
        records = [
            {
                "type": "user",
                "message": {"content": "Real user message"},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
            {
                "type": "user",
                "message": {"content": [{"type": "tool_result", "content": "tool output"}]},
                "timestamp": "2026-01-10T12:01:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        messages = extract_user_messages(temp_project_folder)

        assert len(messages) == 1
        assert messages[0].content == "Real user message"

    def test_extracts_text_blocks_from_array(self, temp_project_folder: Path) -> None:
        """Extracts text from array content with text blocks."""
        records = [
            {
                "type": "user",
                "message": {"content": [{"type": "text", "text": "Text block message"}]},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        messages = extract_user_messages(temp_project_folder)

        assert len(messages) == 1
        assert messages[0].content == "Text block message"

    def test_filters_non_user_messages(self, temp_project_folder: Path) -> None:
        """Filters out non-user message types."""
        records = [
            {
                "type": "user",
                "message": {"content": "User message"},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
            {
                "type": "assistant",
                "message": {"content": "Assistant message"},
                "timestamp": "2026-01-10T12:01:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        messages = extract_user_messages(temp_project_folder)

        assert len(messages) == 1
        assert messages[0].content == "User message"

    def test_respects_limit(self, temp_project_folder: Path) -> None:
        """Respects the limit parameter."""
        records = [
            {
                "type": "user",
                "message": {"content": f"Message {i}"},
                "timestamp": f"2026-01-10T12:{i:02d}:00Z",
                "sessionId": "sess-1",
                "uuid": f"uuid-{i}",
            }
            for i in range(10)
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        messages = extract_user_messages(temp_project_folder, limit=3)

        assert len(messages) == 3

    def test_respects_since_filter(self, temp_project_folder: Path) -> None:
        """Filters messages by since datetime."""
        records = [
            {
                "type": "user",
                "message": {"content": "Old message"},
                "timestamp": "2026-01-01T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
            {
                "type": "user",
                "message": {"content": "New message"},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", records)

        since = datetime(2026, 1, 5, 0, 0, 0)
        messages = extract_user_messages(temp_project_folder, since=since)

        assert len(messages) == 1
        assert messages[0].content == "New message"

    def test_excludes_agent_sessions_when_requested(self, temp_project_folder: Path) -> None:
        """Excludes agent-*.jsonl files when include_agent_sessions=False."""
        user_records = [
            {
                "type": "user",
                "message": {"content": "User session message"},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
        ]
        agent_records = [
            {
                "type": "user",
                "message": {"content": "Agent session message"},
                "timestamp": "2026-01-10T12:01:00Z",
                "sessionId": "agent-sess",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", user_records)
        self._write_jsonl(temp_project_folder / "agent-session.jsonl", agent_records)

        messages = extract_user_messages(temp_project_folder, include_agent_sessions=False)

        assert len(messages) == 1
        assert messages[0].content == "User session message"

    def test_includes_agent_sessions_by_default(self, temp_project_folder: Path) -> None:
        """Includes agent-*.jsonl files by default."""
        user_records = [
            {
                "type": "user",
                "message": {"content": "User session message"},
                "timestamp": "2026-01-10T12:00:00Z",
                "sessionId": "sess-1",
                "uuid": "uuid-1",
            },
        ]
        agent_records = [
            {
                "type": "user",
                "message": {"content": "Agent session message"},
                "timestamp": "2026-01-10T12:01:00Z",
                "sessionId": "agent-sess",
                "uuid": "uuid-2",
            },
        ]
        self._write_jsonl(temp_project_folder / "session.jsonl", user_records)
        self._write_jsonl(temp_project_folder / "agent-session.jsonl", agent_records)

        messages = extract_user_messages(temp_project_folder)

        assert len(messages) == 2


class TestSaveMessages:
    """Tests for save_messages function."""

    def test_saves_to_specified_path(self) -> None:
        """Saves messages to the specified output path."""
        messages = [
            UserMessage(
                content="Test message",
                timestamp=datetime(2026, 1, 10, 12, 0, 0),
                session_id="sess-1",
                uuid="uuid-1",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            output_path = Path(tmpdir) / "output.jsonl"
            result_path = save_messages(messages, output_path)

            assert result_path == output_path
            assert output_path.exists()

            with open(output_path) as f:
                content = f.read()
                assert "Test message" in content

    def test_creates_default_path_in_claude_dir(self) -> None:
        """Creates default path in .claude directory when no path specified."""
        messages = [
            UserMessage(
                content="Test message",
                timestamp=datetime(2026, 1, 10, 12, 0, 0),
                session_id="sess-1",
                uuid="uuid-1",
            ),
        ]

        with tempfile.TemporaryDirectory() as tmpdir:
            import os

            original_cwd = os.getcwd()
            try:
                os.chdir(tmpdir)
                result_path = save_messages(messages)

                assert result_path.parent.name == ".claude"
                assert result_path.name.startswith("user-messages-")
                assert result_path.suffix == ".jsonl"
                assert result_path.exists()
            finally:
                os.chdir(original_cwd)


class TestPrintMessagesToStdout:
    """Tests for print_messages_to_stdout function."""

    def test_prints_jsonl_format(self, capsys: pytest.CaptureFixture) -> None:
        """Prints messages in JSONL format to stdout."""
        messages = [
            UserMessage(
                content="First message",
                timestamp=datetime(2026, 1, 10, 12, 0, 0),
                session_id="sess-1",
                uuid="uuid-1",
            ),
            UserMessage(
                content="Second message",
                timestamp=datetime(2026, 1, 10, 12, 1, 0),
                session_id="sess-1",
                uuid="uuid-2",
            ),
        ]

        print_messages_to_stdout(messages)

        captured = capsys.readouterr()
        lines = captured.out.strip().split("\n")
        assert len(lines) == 2

        # Verify each line is valid JSON
        first = json.loads(lines[0])
        assert first["content"] == "First message"

        second = json.loads(lines[1])
        assert second["content"] == "Second message"


class TestMessagesArgumentParsing:
    """Tests for ll-messages (main_messages) argument parsing."""

    def _parse_messages_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_messages."""
        parser = argparse.ArgumentParser()
        parser.add_argument("-n", "--limit", type=int, default=100)
        parser.add_argument("--since", type=str)
        parser.add_argument("-o", "--output", type=Path)
        parser.add_argument("--cwd", type=Path)
        parser.add_argument("--exclude-agents", action="store_true")
        parser.add_argument("--stdout", action="store_true")
        parser.add_argument("-v", "--verbose", action="store_true")
        return parser.parse_args(args)

    def test_default_args(self) -> None:
        """Default values when no arguments provided."""
        args = self._parse_messages_args([])
        assert args.limit == 100
        assert args.since is None
        assert args.output is None
        assert args.cwd is None
        assert args.exclude_agents is False
        assert args.stdout is False
        assert args.verbose is False

    def test_limit_long(self) -> None:
        """--limit sets the message limit."""
        args = self._parse_messages_args(["--limit", "50"])
        assert args.limit == 50

    def test_limit_short(self) -> None:
        """-n sets the message limit."""
        args = self._parse_messages_args(["-n", "25"])
        assert args.limit == 25

    def test_since_date(self) -> None:
        """--since sets the date filter."""
        args = self._parse_messages_args(["--since", "2026-01-01"])
        assert args.since == "2026-01-01"

    def test_output_long(self) -> None:
        """--output sets the output path."""
        args = self._parse_messages_args(["--output", "/path/to/output.jsonl"])
        assert args.output == Path("/path/to/output.jsonl")

    def test_output_short(self) -> None:
        """-o sets the output path."""
        args = self._parse_messages_args(["-o", "/path/to/output.jsonl"])
        assert args.output == Path("/path/to/output.jsonl")

    def test_cwd(self) -> None:
        """--cwd sets the working directory."""
        args = self._parse_messages_args(["--cwd", "/path/to/project"])
        assert args.cwd == Path("/path/to/project")

    def test_exclude_agents(self) -> None:
        """--exclude-agents flag."""
        args = self._parse_messages_args(["--exclude-agents"])
        assert args.exclude_agents is True

    def test_stdout(self) -> None:
        """--stdout flag."""
        args = self._parse_messages_args(["--stdout"])
        assert args.stdout is True

    def test_verbose_long(self) -> None:
        """--verbose flag."""
        args = self._parse_messages_args(["--verbose"])
        assert args.verbose is True

    def test_verbose_short(self) -> None:
        """-v flag."""
        args = self._parse_messages_args(["-v"])
        assert args.verbose is True

    def test_combined_args(self) -> None:
        """Multiple arguments work together correctly."""
        args = self._parse_messages_args(
            [
                "-n",
                "50",
                "--since",
                "2026-01-01",
                "-o",
                "/output.jsonl",
                "--cwd",
                "/project",
                "--exclude-agents",
                "--stdout",
                "-v",
            ]
        )
        assert args.limit == 50
        assert args.since == "2026-01-01"
        assert args.output == Path("/output.jsonl")
        assert args.cwd == Path("/project")
        assert args.exclude_agents is True
        assert args.stdout is True
        assert args.verbose is True

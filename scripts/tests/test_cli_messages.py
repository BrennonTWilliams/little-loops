"""Tests for ll-messages CLI entry point flag combinations.

Complements test_cli.py (TestMainMessagesIntegration, TestMainMessagesAdditionalCoverage)
and test_user_messages.py (arg parsing). Focuses on flag-interaction behavior through
main_messages() that is NOT already tested:
- --commands-only skips extract_user_messages
- --skip-cli skips extract_commands
- --stdout prints to stdout instead of file
- --exclude-agents propagation to both extractors

Note: imports inside main_messages() are function-local, so mocking goes to
source modules (little_loops.user_messages.*), NOT to little_loops.cli.messages.*.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import pytest

from little_loops.cli.messages import main_messages
from little_loops.user_messages import CommandRecord, UserMessage


# ---------------------------------------------------------------------------
# Shared helpers
# ---------------------------------------------------------------------------


def _make_message(session_id: str = "sess-1", content: str = "hello") -> UserMessage:
    return UserMessage(
        content=content,
        timestamp=datetime(2026, 1, 1, 0, 0, 0),
        session_id=session_id,
        uuid="uuid-1",
    )


def _make_command(session_id: str = "sess-1", content: str = "pytest") -> CommandRecord:
    return CommandRecord(
        content=content,
        timestamp=datetime(2026, 1, 1, 0, 0, 0),
        session_id=session_id,
        tool="Bash",
        uuid="uuid-cmd-1",
    )


# Mock path for get_project_folder — imported from little_loops.user_messages
# inside main_messages(), so must be patched at source module
_PROJECT_FOLDER_PATH = "little_loops.user_messages.get_project_folder"
_EXTRACT_MESSAGES_PATH = "little_loops.user_messages.extract_user_messages"
_EXTRACT_COMMANDS_PATH = "little_loops.user_messages.extract_commands"


# ---------------------------------------------------------------------------
# --commands-only flag
# ---------------------------------------------------------------------------


class TestMessagesCommandsOnly:
    """--commands-only skips extract_user_messages and extracts only commands."""

    def test_commands_only_does_not_call_extract_user_messages(self) -> None:
        with patch(_PROJECT_FOLDER_PATH, return_value=Path("/mock/project")):
            with patch(_EXTRACT_MESSAGES_PATH) as mock_msgs:
                with patch(_EXTRACT_COMMANDS_PATH, return_value=[_make_command()]):
                    with patch(
                        "little_loops.cli.messages._save_combined",
                        return_value=Path("/out.jsonl"),
                    ):
                        with patch.object(
                            sys, "argv", ["ll-messages", "--commands-only"]
                        ):
                            result = main_messages()
        assert result == 0
        mock_msgs.assert_not_called()

    def test_commands_only_does_call_extract_commands(self) -> None:
        with patch(_PROJECT_FOLDER_PATH, return_value=Path("/mock/project")):
            with patch(_EXTRACT_MESSAGES_PATH, return_value=[]):
                with patch(_EXTRACT_COMMANDS_PATH) as mock_cmds:
                    mock_cmds.return_value = [_make_command()]
                    with patch(
                        "little_loops.cli.messages._save_combined",
                        return_value=Path("/out.jsonl"),
                    ):
                        with patch.object(
                            sys, "argv", ["ll-messages", "--commands-only"]
                        ):
                            result = main_messages()
        assert result == 0
        mock_cmds.assert_called_once()

    def test_commands_only_with_since_date_parses_correctly(self) -> None:
        with patch(_PROJECT_FOLDER_PATH, return_value=Path("/mock/project")):
            with patch(_EXTRACT_COMMANDS_PATH) as mock_cmds:
                mock_cmds.return_value = [_make_command()]
                with patch(
                    "little_loops.cli.messages._save_combined",
                    return_value=Path("/out.jsonl"),
                ):
                    with patch.object(
                        sys,
                        "argv",
                        ["ll-messages", "--commands-only", "--since", "2026-01-01"],
                    ):
                        result = main_messages()
        assert result == 0
        call_kwargs = mock_cmds.call_args.kwargs
        assert call_kwargs.get("since") is not None


# ---------------------------------------------------------------------------
# --skip-cli flag
# ---------------------------------------------------------------------------


class TestMessagesSkipCli:
    """--skip-cli skips extract_commands; user messages still extracted."""

    def test_skip_cli_does_not_call_extract_commands(self) -> None:
        with patch(_PROJECT_FOLDER_PATH, return_value=Path("/mock/project")):
            with patch(_EXTRACT_MESSAGES_PATH, return_value=[_make_message()]):
                with patch(_EXTRACT_COMMANDS_PATH) as mock_cmds:
                    with patch(
                        "little_loops.cli.messages._save_combined",
                        return_value=Path("/out.jsonl"),
                    ):
                        with patch.object(
                            sys, "argv", ["ll-messages", "--skip-cli"]
                        ):
                            result = main_messages()
        assert result == 0
        mock_cmds.assert_not_called()

    def test_skip_cli_still_extracts_messages(self) -> None:
        with patch(_PROJECT_FOLDER_PATH, return_value=Path("/mock/project")):
            with patch(_EXTRACT_MESSAGES_PATH) as mock_msgs:
                mock_msgs.return_value = [_make_message()]
                with patch(
                    "little_loops.cli.messages._save_combined",
                    return_value=Path("/out.jsonl"),
                ):
                    with patch.object(sys, "argv", ["ll-messages", "--skip-cli"]):
                        result = main_messages()
        assert result == 0
        mock_msgs.assert_called_once()


# ---------------------------------------------------------------------------
# --stdout flag
# ---------------------------------------------------------------------------


class TestMessagesStdout:
    """--stdout prints records to stdout instead of writing a file."""

    def test_stdout_flag_does_not_write_file(self) -> None:
        with patch(_PROJECT_FOLDER_PATH, return_value=Path("/mock/project")):
            with patch(_EXTRACT_MESSAGES_PATH, return_value=[_make_message()]):
                with patch(_EXTRACT_COMMANDS_PATH, return_value=[]):
                    with patch(
                        "little_loops.cli.messages._save_combined"
                    ) as mock_save:
                        with patch.object(
                            sys, "argv", ["ll-messages", "--stdout"]
                        ):
                            result = main_messages()
        assert result == 0
        mock_save.assert_not_called()

    def test_stdout_flag_prints_json_lines(
        self, capsys: pytest.CaptureFixture[str]
    ) -> None:
        msg = _make_message(content="test stdout message")
        with patch(_PROJECT_FOLDER_PATH, return_value=Path("/mock/project")):
            with patch(_EXTRACT_MESSAGES_PATH, return_value=[msg]):
                with patch(_EXTRACT_COMMANDS_PATH, return_value=[]):
                    with patch.object(sys, "argv", ["ll-messages", "--stdout"]):
                        result = main_messages()
        assert result == 0
        captured = capsys.readouterr()
        lines = [l for l in captured.out.strip().splitlines() if l]
        assert len(lines) > 0
        for line in lines:
            parsed = json.loads(line)
            assert isinstance(parsed, dict)


# ---------------------------------------------------------------------------
# --exclude-agents flag behavior through main_messages
# ---------------------------------------------------------------------------


class TestMessagesExcludeAgentsIntegration:
    """Test that --exclude-agents propagates correctly to both extractors."""

    def test_exclude_agents_passed_to_messages_extractor(self) -> None:
        with patch(_PROJECT_FOLDER_PATH, return_value=Path("/mock/project")):
            with patch(_EXTRACT_MESSAGES_PATH) as mock_msgs:
                mock_msgs.return_value = []
                with patch(_EXTRACT_COMMANDS_PATH, return_value=[]):
                    with patch.object(
                        sys, "argv", ["ll-messages", "--exclude-agents"]
                    ):
                        result = main_messages()
        assert result == 0
        call_kwargs = mock_msgs.call_args.kwargs
        assert call_kwargs.get("include_agent_sessions") is False

    def test_exclude_agents_passed_to_commands_extractor(self) -> None:
        with patch(_PROJECT_FOLDER_PATH, return_value=Path("/mock/project")):
            with patch(_EXTRACT_MESSAGES_PATH, return_value=[]):
                with patch(_EXTRACT_COMMANDS_PATH) as mock_cmds:
                    mock_cmds.return_value = []
                    with patch.object(
                        sys, "argv", ["ll-messages", "--exclude-agents"]
                    ):
                        result = main_messages()
        assert result == 0
        call_kwargs = mock_cmds.call_args.kwargs
        assert call_kwargs.get("include_agent_sessions") is False

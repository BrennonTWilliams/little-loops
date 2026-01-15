"""Tests for little_loops.subprocess_utils module.

Tests cover:
- detect_context_handoff() pattern matching
- read_continuation_prompt() file reading
- run_claude_command() subprocess execution with:
  - Streaming callbacks
  - Timeout handling
  - Process lifecycle callbacks
  - Output capture
"""

from __future__ import annotations

import io
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from little_loops.subprocess_utils import (
    CONTEXT_HANDOFF_PATTERN,
    CONTINUATION_PROMPT_PATH,
    detect_context_handoff,
    read_continuation_prompt,
    run_claude_command,
)

# =============================================================================
# Fixtures
# =============================================================================


@pytest.fixture
def temp_repo(tmp_path: Path) -> Path:
    """Create a temporary repository directory."""
    return tmp_path


@pytest.fixture
def temp_repo_with_prompt(temp_repo: Path) -> Path:
    """Repository with continuation prompt file."""
    prompt_path = temp_repo / ".claude" / "ll-continue-prompt.md"
    prompt_path.parent.mkdir(parents=True)
    prompt_path.write_text("Continue from previous session.\n\nContext: Testing")
    return temp_repo


@pytest.fixture
def mock_popen() -> Generator[MagicMock, None, None]:
    """Mock subprocess.Popen that completes immediately with no output."""
    mock_process = MagicMock(spec=subprocess.Popen)
    mock_process.stdout = io.StringIO("")
    mock_process.stderr = io.StringIO("")
    mock_process.returncode = 0
    mock_process.poll.return_value = 0
    mock_process.wait.return_value = 0

    with patch("subprocess.Popen", return_value=mock_process) as mock:
        yield mock


# =============================================================================
# TestDetectContextHandoff
# =============================================================================


class TestDetectContextHandoff:
    """Tests for detect_context_handoff() function."""

    def test_detects_standard_handoff_signal(self) -> None:
        """Matches 'CONTEXT_HANDOFF: Ready for fresh session'."""
        output = "Some output\nCONTEXT_HANDOFF: Ready for fresh session\nMore output"
        assert detect_context_handoff(output) is True

    def test_detects_with_extra_whitespace(self) -> None:
        """Matches with extra spaces after colon."""
        output = "CONTEXT_HANDOFF:   Ready for fresh session"
        assert detect_context_handoff(output) is True

    def test_returns_false_for_no_signal(self) -> None:
        """Regular output returns False."""
        output = "Normal output without any special signals"
        assert detect_context_handoff(output) is False

    def test_returns_false_for_empty_string(self) -> None:
        """Empty string returns False."""
        assert detect_context_handoff("") is False

    def test_returns_false_for_partial_match(self) -> None:
        """'CONTEXT_HANDOFF' alone returns False."""
        output = "CONTEXT_HANDOFF: Something else"
        assert detect_context_handoff(output) is False

    def test_matches_in_multiline_output(self) -> None:
        """Finds signal embedded in longer output."""
        output = """
        Processing issue BUG-001...
        Work completed successfully.
        CONTEXT_HANDOFF: Ready for fresh session
        Cleaning up resources.
        """
        assert detect_context_handoff(output) is True

    def test_case_sensitive(self) -> None:
        """Lowercase 'context_handoff' returns False."""
        output = "context_handoff: Ready for fresh session"
        assert detect_context_handoff(output) is False

    def test_pattern_constant_exists(self) -> None:
        """CONTEXT_HANDOFF_PATTERN constant is defined."""
        assert CONTEXT_HANDOFF_PATTERN is not None
        assert CONTEXT_HANDOFF_PATTERN.pattern == r"CONTEXT_HANDOFF:\s*Ready for fresh session"


# =============================================================================
# TestReadContinuationPrompt
# =============================================================================


class TestReadContinuationPrompt:
    """Tests for read_continuation_prompt() function."""

    def test_reads_existing_prompt_file(self, temp_repo_with_prompt: Path) -> None:
        """Returns contents when file exists."""
        result = read_continuation_prompt(temp_repo_with_prompt)
        assert result is not None
        assert "Continue from previous session." in result
        assert "Context: Testing" in result

    def test_returns_none_when_file_missing(self, temp_repo: Path) -> None:
        """Returns None when path doesn't exist."""
        result = read_continuation_prompt(temp_repo)
        assert result is None

    def test_uses_repo_path_when_provided(self, temp_repo_with_prompt: Path) -> None:
        """Uses repo_path / .claude/ll-continue-prompt.md."""
        result = read_continuation_prompt(temp_repo_with_prompt)
        assert result is not None

    def test_uses_cwd_when_repo_path_none(
        self, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Uses Path.cwd() when repo_path is None."""
        monkeypatch.chdir(tmp_path)
        # No prompt file in tmp_path
        result = read_continuation_prompt(None)
        assert result is None

    def test_handles_empty_file(self, temp_repo: Path) -> None:
        """Returns empty string for empty file."""
        prompt_path = temp_repo / ".claude" / "ll-continue-prompt.md"
        prompt_path.parent.mkdir(parents=True)
        prompt_path.write_text("")

        result = read_continuation_prompt(temp_repo)
        assert result == ""

    def test_handles_unicode_content(self, temp_repo: Path) -> None:
        """Reads UTF-8 content correctly."""
        prompt_path = temp_repo / ".claude" / "ll-continue-prompt.md"
        prompt_path.parent.mkdir(parents=True)
        prompt_path.write_text("Unicode content: \u2714 \u2717 \U0001f600")

        result = read_continuation_prompt(temp_repo)
        assert result is not None
        assert "\u2714" in result  # Check mark
        assert "\U0001f600" in result  # Emoji

    def test_prompt_path_constant(self) -> None:
        """CONTINUATION_PROMPT_PATH constant is correct."""
        assert CONTINUATION_PROMPT_PATH == Path(".claude/ll-continue-prompt.md")


# =============================================================================
# TestRunClaudeCommand
# =============================================================================


class TestRunClaudeCommand:
    """Tests for run_claude_command() basic functionality."""

    def test_returns_completed_process(self) -> None:
        """Returns subprocess.CompletedProcess."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                # Configure selector to immediately return empty (no data)
                mock_selector.return_value.get_map.return_value = {}

                result = run_claude_command("test command")

                assert isinstance(result, subprocess.CompletedProcess)

    def test_constructs_correct_command_args(self) -> None:
        """Uses ['claude', '--dangerously-skip-permissions', '-p', command]."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("/ll:test_command")

        assert len(captured_args) == 1
        assert captured_args[0] == [
            "claude",
            "--dangerously-skip-permissions",
            "-p",
            "/ll:test_command",
        ]

    def test_sets_maintain_project_working_dir_env(self) -> None:
        """Sets CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR=1."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        captured_env: dict[str, str] = {}

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_env.update(kwargs.get("env", {}))
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test")

        assert "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR" in captured_env
        assert captured_env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] == "1"

    def test_uses_working_dir_when_provided(self, tmp_path: Path) -> None:
        """Passes cwd to Popen."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        captured_cwd: list[Path | None] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_cwd.append(kwargs.get("cwd"))
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test", working_dir=tmp_path)

        assert captured_cwd[0] == tmp_path


# =============================================================================
# TestRunClaudeCommandOutputCapture
# =============================================================================


class TestRunClaudeCommandOutputCapture:
    """Tests for output capture functionality."""

    def test_captures_stdout_lines(self) -> None:
        """stdout contains all output lines."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("line 1\nline 2\nline 3\n")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = mock_selector.return_value
                # Track call count to control flow
                call_count = [0]

                def get_map_side_effect() -> dict[Any, Any]:
                    call_count[0] += 1
                    if call_count[0] <= 3:  # Process 3 lines
                        return {"stdout": True}
                    return {}

                selector_instance.get_map.side_effect = get_map_side_effect

                # Mock select to return stdout file object
                key = Mock()
                key.fileobj = mock_process.stdout
                selector_instance.select.return_value = [(key, None)]
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                result = run_claude_command("test")

        assert "line 1" in result.stdout
        assert "line 2" in result.stdout
        assert "line 3" in result.stdout

    def test_captures_stderr_lines(self) -> None:
        """stderr contains all error lines."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("error 1\nerror 2\n")
        mock_process.returncode = 1
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = mock_selector.return_value
                call_count = [0]

                def get_map_side_effect() -> dict[Any, Any]:
                    call_count[0] += 1
                    if call_count[0] <= 2:
                        return {"stderr": True}
                    return {}

                selector_instance.get_map.side_effect = get_map_side_effect

                key = Mock()
                key.fileobj = mock_process.stderr
                selector_instance.select.return_value = [(key, None)]
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                result = run_claude_command("test")

        assert "error 1" in result.stderr
        assert "error 2" in result.stderr

    def test_joins_lines_with_newlines(self) -> None:
        """Output joined with '\\n'."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("a\nb\n")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = mock_selector.return_value
                call_count = [0]

                def get_map_side_effect() -> dict[Any, Any]:
                    call_count[0] += 1
                    if call_count[0] <= 2:
                        return {"stdout": True}
                    return {}

                selector_instance.get_map.side_effect = get_map_side_effect

                key = Mock()
                key.fileobj = mock_process.stdout
                selector_instance.select.return_value = [(key, None)]
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                result = run_claude_command("test")

        # Lines are joined with newline
        assert result.stdout == "a\nb"

    def test_returncode_captured(self) -> None:
        """CompletedProcess has correct returncode."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 42
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}
                result = run_claude_command("test")

        assert result.returncode == 42

    def test_none_returncode_becomes_zero(self) -> None:
        """None returncode becomes 0."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}
                result = run_claude_command("test")

        assert result.returncode == 0


# =============================================================================
# TestRunClaudeCommandStreaming
# =============================================================================


class TestRunClaudeCommandStreaming:
    """Tests for streaming callback functionality."""

    def test_calls_stream_callback_for_stdout(self) -> None:
        """Callback called with (line, False) for stdout."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("output line\n")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        callback_calls: list[tuple[str, bool]] = []

        def callback(line: str, is_stderr: bool) -> None:
            callback_calls.append((line, is_stderr))

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = mock_selector.return_value
                call_count = [0]

                def get_map_side_effect() -> dict[Any, Any]:
                    call_count[0] += 1
                    if call_count[0] == 1:
                        return {"stdout": True}
                    return {}

                selector_instance.get_map.side_effect = get_map_side_effect

                key = Mock()
                key.fileobj = mock_process.stdout
                selector_instance.select.return_value = [(key, None)]
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                run_claude_command("test", stream_callback=callback)

        assert len(callback_calls) == 1
        assert callback_calls[0] == ("output line", False)

    def test_calls_stream_callback_for_stderr(self) -> None:
        """Callback called with (line, True) for stderr."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("error line\n")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        callback_calls: list[tuple[str, bool]] = []

        def callback(line: str, is_stderr: bool) -> None:
            callback_calls.append((line, is_stderr))

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = mock_selector.return_value
                call_count = [0]

                def get_map_side_effect() -> dict[Any, Any]:
                    call_count[0] += 1
                    if call_count[0] == 1:
                        return {"stderr": True}
                    return {}

                selector_instance.get_map.side_effect = get_map_side_effect

                key = Mock()
                key.fileobj = mock_process.stderr
                selector_instance.select.return_value = [(key, None)]
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                run_claude_command("test", stream_callback=callback)

        assert len(callback_calls) == 1
        assert callback_calls[0] == ("error line", True)

    def test_stream_callback_none_doesnt_error(self) -> None:
        """Works when stream_callback is None."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("output\n")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = mock_selector.return_value
                call_count = [0]

                def get_map_side_effect() -> dict[Any, Any]:
                    call_count[0] += 1
                    if call_count[0] == 1:
                        return {"stdout": True}
                    return {}

                selector_instance.get_map.side_effect = get_map_side_effect

                key = Mock()
                key.fileobj = mock_process.stdout
                selector_instance.select.return_value = [(key, None)]
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                # Should not raise
                result = run_claude_command("test", stream_callback=None)
                assert result is not None


# =============================================================================
# TestRunClaudeCommandTimeout
# =============================================================================


class TestRunClaudeCommandTimeout:
    """Tests for timeout handling."""

    def test_raises_timeout_expired_when_exceeded(self) -> None:
        """Raises subprocess.TimeoutExpired."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = mock_selector.return_value

                # Make get_map always return something (simulating hanging process)
                selector_instance.get_map.return_value = {"stdout": True}
                # Make select return nothing (no ready streams)
                selector_instance.select.return_value = []
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                # Mock time to simulate timeout
                start_time = time.time()
                time_values = [start_time, start_time + 0.5, start_time + 2.0]
                time_index = [0]

                def mock_time() -> float:
                    result = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return result

                with patch("time.time", side_effect=mock_time):
                    with pytest.raises(subprocess.TimeoutExpired):
                        run_claude_command("test", timeout=1)

    def test_kills_process_on_timeout(self) -> None:
        """process.kill() called on timeout."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = mock_selector.return_value
                selector_instance.get_map.return_value = {"stdout": True}
                selector_instance.select.return_value = []
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                start_time = time.time()
                time_values = [start_time, start_time + 2.0]
                time_index = [0]

                def mock_time() -> float:
                    result = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return result

                with patch("time.time", side_effect=mock_time):
                    with pytest.raises(subprocess.TimeoutExpired):
                        run_claude_command("test", timeout=1)

        mock_process.kill.assert_called_once()

    def test_timeout_zero_means_no_timeout(self) -> None:
        """timeout=0 allows indefinite running (no timeout check)."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}

                # Should not raise even with simulated long time
                result = run_claude_command("test", timeout=0)
                assert result is not None


# =============================================================================
# TestRunClaudeCommandProcessCallbacks
# =============================================================================


class TestRunClaudeCommandProcessCallbacks:
    """Tests for process lifecycle callbacks."""

    def test_calls_on_process_start(self) -> None:
        """on_process_start called with Popen."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        start_callback_calls: list[Any] = []

        def on_start(proc: Any) -> None:
            start_callback_calls.append(proc)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test", on_process_start=on_start)

        assert len(start_callback_calls) == 1
        assert start_callback_calls[0] is mock_process

    def test_calls_on_process_end_on_success(self) -> None:
        """on_process_end called after normal completion."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        end_callback_calls: list[Any] = []

        def on_end(proc: Any) -> None:
            end_callback_calls.append(proc)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test", on_process_end=on_end)

        assert len(end_callback_calls) == 1
        assert end_callback_calls[0] is mock_process

    def test_calls_on_process_end_on_timeout(self) -> None:
        """on_process_end called in finally block even on timeout."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()

        end_callback_calls: list[Any] = []

        def on_end(proc: Any) -> None:
            end_callback_calls.append(proc)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = mock_selector.return_value
                selector_instance.get_map.return_value = {"stdout": True}
                selector_instance.select.return_value = []
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                start_time = time.time()
                time_values = [start_time, start_time + 2.0]
                time_index = [0]

                def mock_time() -> float:
                    result = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return result

                with patch("time.time", side_effect=mock_time):
                    with pytest.raises(subprocess.TimeoutExpired):
                        run_claude_command("test", timeout=1, on_process_end=on_end)

        # on_process_end should still be called
        assert len(end_callback_calls) == 1

    def test_callbacks_none_doesnt_error(self) -> None:
        """Works when callbacks are None."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}

                # Should not raise
                result = run_claude_command("test", on_process_start=None, on_process_end=None)
                assert result is not None


# =============================================================================
# TestRunClaudeCommandIntegration
# =============================================================================


class TestRunClaudeCommandIntegration:
    """Integration-style tests for run_claude_command()."""

    def test_handles_nonzero_exit(self) -> None:
        """Non-zero exit doesn't raise exception."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("error message")
        mock_process.returncode = 1
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}

                # Should not raise
                result = run_claude_command("test")
                assert result.returncode == 1

    def test_handles_process_with_no_output(self) -> None:
        """Works with empty stdout/stderr."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}

                result = run_claude_command("test")
                assert result.stdout == ""
                assert result.stderr == ""

    def test_command_in_result(self) -> None:
        """CompletedProcess contains command args."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                mock_selector.return_value.get_map.return_value = {}

                result = run_claude_command("/ll:test_cmd")

        assert result.args == [
            "claude",
            "--dangerously-skip-permissions",
            "-p",
            "/ll:test_cmd",
        ]

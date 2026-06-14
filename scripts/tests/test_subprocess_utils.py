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
import os
import signal
import subprocess
import time
from collections.abc import Generator
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, Mock, patch

import pytest

from little_loops.host_runner import ClaudeCodeRunner
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
    prompt_path = temp_repo / ".ll" / "ll-continue-prompt.md"
    prompt_path.parent.mkdir(parents=True, exist_ok=True)
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


@pytest.fixture(autouse=True)
def _patch_resolve_host() -> Generator[None, None, None]:
    """Patch resolve_host so run_claude_command tests don't depend on PATH.

    Uses a real ClaudeCodeRunner so build_streaming produces the same argv as
    the legacy hardcoded list, keeping all existing argv snapshot assertions valid.
    """
    with patch("little_loops.subprocess_utils.resolve_host", return_value=ClaudeCodeRunner()):
        yield


def _patch_selector_cm(mock_selector: MagicMock) -> None:
    """Configure mock selector to work as a context manager.

    DefaultSelector is used as `with DefaultSelector() as sel:`, so the mock
    instance's __enter__ must return itself for attribute access to work.
    """
    instance = mock_selector.return_value
    instance.__enter__ = Mock(return_value=instance)
    instance.__exit__ = Mock(return_value=False)


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
        """Uses repo_path / .ll/ll-continue-prompt.md."""
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
        prompt_path = temp_repo / ".ll" / "ll-continue-prompt.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text("")

        result = read_continuation_prompt(temp_repo)
        assert result == ""

    def test_handles_unicode_content(self, temp_repo: Path) -> None:
        """Reads UTF-8 content correctly."""
        prompt_path = temp_repo / ".ll" / "ll-continue-prompt.md"
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        prompt_path.write_text("Unicode content: \u2714 \u2717 \U0001f600")

        result = read_continuation_prompt(temp_repo)
        assert result is not None
        assert "\u2714" in result  # Check mark
        assert "\U0001f600" in result  # Emoji

    def test_prompt_path_constant(self) -> None:
        """CONTINUATION_PROMPT_PATH constant is correct."""
        assert CONTINUATION_PROMPT_PATH == Path(".ll/ll-continue-prompt.md")


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
                _patch_selector_cm(mock_selector)
                # Configure selector to immediately return empty (no data)
                mock_selector.return_value.get_map.return_value = {}

                result = run_claude_command("test command")

                assert isinstance(result, subprocess.CompletedProcess)

    def test_constructs_correct_command_args(self) -> None:
        """Uses ['claude', '--dangerously-skip-permissions', '--output-format', 'stream-json', '-p', command]."""
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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("/ll:test-command")

        assert len(captured_args) == 1
        assert captured_args[0] == [
            "claude",
            "--dangerously-skip-permissions",
            "--verbose",
            "--output-format",
            "stream-json",
            "-p",
            "/ll:test-command",
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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test")

        assert "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR" in captured_env
        assert captured_env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] == "1"

    def test_sets_non_interactive_env_vars(self) -> None:
        """run_claude_command propagates LL_NON_INTERACTIVE and DANGEROUSLY_SKIP_PERMISSIONS to Popen (BUG-2110)."""
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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test")

        assert "LL_NON_INTERACTIVE" in captured_env, "LL_NON_INTERACTIVE must reach Popen env"
        assert captured_env["LL_NON_INTERACTIVE"] == "1"
        assert "DANGEROUSLY_SKIP_PERMISSIONS" in captured_env
        assert captured_env["DANGEROUSLY_SKIP_PERMISSIONS"] == "1"

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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test", working_dir=tmp_path)

        assert captured_cwd[0] == tmp_path

    def test_sets_git_dir_env_for_worktree(self, tmp_path: Path) -> None:
        """Sets GIT_DIR and GIT_WORK_TREE when working_dir/.git is a worktree file."""
        actual_gitdir = tmp_path / "real_gitdir"
        actual_gitdir.mkdir(exist_ok=True)
        git_file = tmp_path / ".git"
        git_file.write_text(f"gitdir: {actual_gitdir}\n")

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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test", working_dir=tmp_path)

        assert "GIT_DIR" in captured_env
        assert "GIT_WORK_TREE" in captured_env
        assert captured_env["GIT_DIR"] == str(actual_gitdir.resolve())
        assert captured_env["GIT_WORK_TREE"] == str(tmp_path)

    def test_no_git_dir_env_for_normal_repo(self, tmp_path: Path) -> None:
        """Does not set GIT_DIR when working_dir/.git is a directory (normal repo)."""
        git_dir = tmp_path / ".git"
        git_dir.mkdir(exist_ok=True)

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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test", working_dir=tmp_path)

        assert "GIT_DIR" not in captured_env
        assert "GIT_WORK_TREE" not in captured_env

    def test_no_git_dir_env_when_no_working_dir(self) -> None:
        """Does not set GIT_DIR when working_dir is None."""
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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test")

        assert "GIT_DIR" not in captured_env
        assert "GIT_WORK_TREE" not in captured_env


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
                _patch_selector_cm(mock_selector)
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
                _patch_selector_cm(mock_selector)
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
                _patch_selector_cm(mock_selector)
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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                result = run_claude_command("test")

        assert result.returncode == 42

    def test_none_returncode_becomes_negative_nine(self) -> None:
        """None returncode (killed/unreapable process) becomes -9, not 0."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                result = run_claude_command("test")

        assert result.returncode == -9
        assert result.returncode != 0

    def test_killed_process_double_timeout_returns_nonzero(self) -> None:
        """When process is killed and second wait also times out, returncode is -9."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        # First wait (post-stream) times out, second wait (after kill) also times out
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired(cmd="test", timeout=30),
            subprocess.TimeoutExpired(cmd="test", timeout=10),
        ]
        mock_process.kill = Mock()
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                with patch("os.getpgid", return_value=99), patch("os.killpg") as mock_killpg:
                    result = run_claude_command("test")

        mock_killpg.assert_called_once_with(99, signal.SIGKILL)
        assert result.returncode == -9, "Killed process must not report success"


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
                _patch_selector_cm(mock_selector)
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
                _patch_selector_cm(mock_selector)
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
                _patch_selector_cm(mock_selector)
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
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
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
                    with patch("os.getpgid", return_value=99), patch("os.killpg"):
                        with pytest.raises(subprocess.TimeoutExpired):
                            run_claude_command("test", timeout=1)

    def test_kills_process_on_timeout(self) -> None:
        """os.killpg() called on timeout."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
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
                    with patch("os.getpgid", return_value=99), patch("os.killpg") as mock_killpg:
                        with pytest.raises(subprocess.TimeoutExpired):
                            run_claude_command("test", timeout=1)

        mock_killpg.assert_called_once_with(99, signal.SIGKILL)
        mock_process.wait.assert_called_once_with(timeout=10)

    def test_timeout_zero_means_no_timeout(self) -> None:
        """timeout=0 allows indefinite running (no timeout check)."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
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
                _patch_selector_cm(mock_selector)
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
                _patch_selector_cm(mock_selector)
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
        mock_process.pid = 12345

        end_callback_calls: list[Any] = []

        def on_end(proc: Any) -> None:
            end_callback_calls.append(proc)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
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
                    with patch("os.getpgid", return_value=99), patch("os.killpg"):
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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}

                # Should not raise
                result = run_claude_command("test", on_process_start=None, on_process_end=None)
                assert result is not None


# =============================================================================
# TestRunClaudeCommandSelectorCleanup
# =============================================================================


class TestRunClaudeCommandSelectorCleanup:
    """Tests for selector resource cleanup (BUG-230)."""

    def test_selector_closed_on_success(self) -> None:
        """Selector is closed after normal completion."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = MagicMock()
                selector_instance.get_map.return_value = {}
                mock_selector.return_value = selector_instance
                selector_instance.__enter__ = Mock(return_value=selector_instance)
                selector_instance.__exit__ = Mock(return_value=False)

                run_claude_command("test")

        selector_instance.__exit__.assert_called_once()

    def test_selector_closed_on_timeout(self) -> None:
        """Selector is closed even when timeout occurs."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                selector_instance = MagicMock()
                selector_instance.get_map.return_value = {"stdout": True}
                selector_instance.select.return_value = []
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()
                mock_selector.return_value = selector_instance
                selector_instance.__enter__ = Mock(return_value=selector_instance)
                selector_instance.__exit__ = Mock(return_value=False)

                start_time = time.time()
                time_values = [start_time, start_time + 2.0]
                time_index = [0]

                def mock_time() -> float:
                    result = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return result

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", return_value=99), patch("os.killpg"):
                        with pytest.raises(subprocess.TimeoutExpired):
                            run_claude_command("test", timeout=1)

        selector_instance.__exit__.assert_called_once()


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
                _patch_selector_cm(mock_selector)
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
                _patch_selector_cm(mock_selector)
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
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}

                result = run_claude_command("/ll:test_cmd")

        assert result.args == [
            "claude",
            "--dangerously-skip-permissions",
            "--verbose",
            "--output-format",
            "stream-json",
            "-p",
            "/ll:test_cmd",
        ]


# =============================================================================
# TestRunClaudeCommandIdleTimeout
# =============================================================================


class TestRunClaudeCommandIdleTimeout:
    """Tests for idle timeout handling (BUG-302)."""

    def test_raises_timeout_on_idle(self) -> None:
        """Raises TimeoutExpired when no output for idle_timeout seconds."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                selector_instance = mock_selector.return_value

                # Simulate hanging process (streams open, no data)
                selector_instance.get_map.return_value = {"stdout": True}
                selector_instance.select.return_value = []
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                # Mock time: start, first loop check, then idle exceeded
                start_time = 1000.0
                time_values = [start_time, start_time, start_time + 0.5, start_time + 11.0]
                time_index = [0]

                def mock_time() -> float:
                    result = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return result

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", return_value=99), patch("os.killpg") as mock_killpg:
                        with pytest.raises(subprocess.TimeoutExpired) as exc_info:
                            run_claude_command("test", timeout=3600, idle_timeout=10)

                assert exc_info.value.timeout == 10
                mock_killpg.assert_called_once_with(99, signal.SIGKILL)

    def test_idle_timeout_zero_means_disabled(self) -> None:
        """idle_timeout=0 never triggers idle timeout."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}

                # Should complete normally even with idle_timeout=0
                result = run_claude_command("test", idle_timeout=0)
                assert result is not None

    def test_idle_timeout_resets_on_output(self) -> None:
        """Output activity resets the idle timer."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("line1\nline2\n")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                selector_instance = mock_selector.return_value
                call_count = [0]

                def get_map_side_effect() -> dict[Any, Any]:
                    call_count[0] += 1
                    if call_count[0] <= 2:  # Process 2 lines
                        return {"stdout": True}
                    return {}

                selector_instance.get_map.side_effect = get_map_side_effect

                key = Mock()
                key.fileobj = mock_process.stdout
                selector_instance.select.return_value = [(key, None)]
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                # Should complete without hitting idle timeout since output resets timer
                result = run_claude_command("test", idle_timeout=10)
                assert "line1" in result.stdout
                assert "line2" in result.stdout

    def test_idle_timeout_output_field_set(self) -> None:
        """TimeoutExpired has output='idle_timeout' for idle timeouts."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                selector_instance = mock_selector.return_value

                selector_instance.get_map.return_value = {"stdout": True}
                selector_instance.select.return_value = []
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                start_time = 1000.0
                time_values = [start_time, start_time, start_time + 0.5, start_time + 11.0]
                time_index = [0]

                def mock_time() -> float:
                    result = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return result

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", return_value=99), patch("os.killpg"):
                        with pytest.raises(subprocess.TimeoutExpired) as exc_info:
                            run_claude_command("test", timeout=3600, idle_timeout=10)

                assert exc_info.value.output == "idle_timeout"

    def test_on_process_end_called_on_idle_timeout(self) -> None:
        """on_process_end called in finally block even on idle timeout."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()
        mock_process.pid = 12345

        end_callback_calls: list[Any] = []

        def on_end(proc: Any) -> None:
            end_callback_calls.append(proc)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                selector_instance = mock_selector.return_value
                selector_instance.get_map.return_value = {"stdout": True}
                selector_instance.select.return_value = []
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                start_time = 1000.0
                time_values = [start_time, start_time, start_time + 0.5, start_time + 11.0]
                time_index = [0]

                def mock_time() -> float:
                    result = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return result

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", return_value=99), patch("os.killpg"):
                        with pytest.raises(subprocess.TimeoutExpired):
                            run_claude_command(
                                "test", timeout=3600, idle_timeout=10, on_process_end=on_end
                            )

        # on_process_end should still be called via finally block
        assert len(end_callback_calls) == 1


# =============================================================================
# TestRunClaudeCommandWaitTimeout
# =============================================================================


class TestRunClaudeCommandWaitTimeout:
    """Tests for timeout on process.wait() calls (BUG-420)."""

    def test_wait_has_timeout_after_kill_on_timeout(self) -> None:
        """process.wait(timeout=10) called after killpg on total timeout."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
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
                    with patch("os.getpgid", return_value=99), patch("os.killpg") as mock_killpg:
                        with pytest.raises(subprocess.TimeoutExpired):
                            run_claude_command("test", timeout=1)

        mock_killpg.assert_called_once_with(99, signal.SIGKILL)
        mock_process.wait.assert_called_once_with(timeout=10)

    def test_wait_has_timeout_after_kill_on_idle_timeout(self) -> None:
        """process.wait(timeout=10) called after killpg on idle timeout."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()
        mock_process.pid = 12345

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                selector_instance = mock_selector.return_value
                selector_instance.get_map.return_value = {"stdout": True}
                selector_instance.select.return_value = []
                selector_instance.register = Mock()
                selector_instance.unregister = Mock()

                start_time = 1000.0
                time_values = [start_time, start_time, start_time + 0.5, start_time + 11.0]
                time_index = [0]

                def mock_time() -> float:
                    result = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return result

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", return_value=99), patch("os.killpg") as mock_killpg:
                        with pytest.raises(subprocess.TimeoutExpired):
                            run_claude_command("test", timeout=3600, idle_timeout=10)

        mock_killpg.assert_called_once_with(99, signal.SIGKILL)
        mock_process.wait.assert_called_once_with(timeout=10)

    def test_wait_has_timeout_on_normal_completion(self) -> None:
        """process.wait(timeout=30) called on normal exit."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}

                run_claude_command("test")

        mock_process.wait.assert_called_once_with(timeout=30)

    def test_logs_warning_when_wait_times_out_after_kill(self) -> None:
        """Warning logged when process doesn't terminate after kill."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.kill = Mock()
        mock_process.pid = 99999
        mock_process.wait.side_effect = subprocess.TimeoutExpired("cmd", 10)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
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
                    with patch("os.getpgid", return_value=99), patch("os.killpg") as mock_killpg:
                        with patch("little_loops.subprocess_utils.logger") as mock_logger:
                            with pytest.raises(subprocess.TimeoutExpired):
                                run_claude_command("test", timeout=1)

                            mock_killpg.assert_called_once_with(99, signal.SIGKILL)
                            mock_logger.warning.assert_called_once_with(
                                "Process %s did not terminate within 10s after kill",
                                99999,
                            )

    def test_kills_process_when_normal_wait_times_out(self) -> None:
        """Process group killed and waited again when normal wait(timeout=30) expires."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.pid = 55555
        # First wait(timeout=30) times out, second wait(timeout=10) succeeds
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired("cmd", 30),
            None,
        ]
        mock_process.kill = Mock()

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}

                with patch("os.getpgid", return_value=99), patch("os.killpg") as mock_killpg:
                    with patch("little_loops.subprocess_utils.logger") as mock_logger:
                        run_claude_command("test")

                        mock_logger.warning.assert_called_once_with(
                            "Process %s did not exit within 30s after streams closed, killing",
                            55555,
                        )

        mock_killpg.assert_called_once_with(99, signal.SIGKILL)
        assert mock_process.wait.call_count == 2
        mock_process.wait.assert_any_call(timeout=30)
        mock_process.wait.assert_any_call(timeout=10)


# =============================================================================
# TestRunClaudeCommandModelDetection
# =============================================================================


class TestRunClaudeCommandModelDetection:
    """Tests for stream-json event parsing and on_model_detected callback (ENH-838)."""

    def _make_single_line_selector(self, mock_selector: Any, mock_process: Mock) -> None:
        """Configure selector to return stdout key once then exit loop."""
        _patch_selector_cm(mock_selector)
        selector_instance = mock_selector.return_value
        call_count = [0]

        def get_map_side_effect() -> dict[Any, Any]:
            call_count[0] += 1
            return {"stdout": True} if call_count[0] == 1 else {}

        selector_instance.get_map.side_effect = get_map_side_effect
        key = Mock()
        key.fileobj = mock_process.stdout
        selector_instance.select.return_value = [(key, None)]
        selector_instance.register = Mock()
        selector_instance.unregister = Mock()

    def test_on_model_detected_called_with_model_name(self) -> None:
        """on_model_detected callback fired with model name from system/init event."""
        init_event = '{"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}\n'
        mock_process = Mock()
        mock_process.stdout = io.StringIO(init_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        detected: list[str] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                run_claude_command("test", on_model_detected=lambda m: detected.append(m))

        assert detected == ["claude-sonnet-4-6"]

    def test_init_event_not_added_to_stdout(self) -> None:
        """Init event line must not appear in result.stdout."""
        init_event = '{"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}\n'
        mock_process = Mock()
        mock_process.stdout = io.StringIO(init_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                result = run_claude_command("test")

        assert result.stdout == ""

    def test_assistant_event_text_extracted_to_stdout(self) -> None:
        """Text content from assistant event appears in result.stdout."""
        assistant_event = (
            '{"type": "assistant", "message": {"content": ['
            '{"type": "text", "text": "Hello world"}]}}\n'
        )
        mock_process = Mock()
        mock_process.stdout = io.StringIO(assistant_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                result = run_claude_command("test")

        assert result.stdout == "Hello world"

    def test_assistant_event_text_passed_to_stream_callback(self) -> None:
        """stream_callback receives extracted text from assistant event."""
        assistant_event = (
            '{"type": "assistant", "message": {"content": ['
            '{"type": "text", "text": "Stream me"}]}}\n'
        )
        mock_process = Mock()
        mock_process.stdout = io.StringIO(assistant_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        callback_calls: list[tuple[str, bool]] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                run_claude_command(
                    "test",
                    stream_callback=lambda line, is_stderr: callback_calls.append(
                        (line, is_stderr)
                    ),
                )

        assert callback_calls == [("Stream me", False)]

    def test_assistant_event_multiline_text_dispatched_per_line(self) -> None:
        """Multi-paragraph assistant text dispatches stream_callback once per real line (BUG-1118)."""
        assistant_event = (
            '{"type": "assistant", "message": {"content": ['
            '{"type": "text", "text": "Para one line A\\nPara one line B"},'
            '{"type": "text", "text": "Para two only"}]}}\n'
        )
        mock_process = Mock()
        mock_process.stdout = io.StringIO(assistant_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        callback_calls: list[tuple[str, bool]] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                result = run_claude_command(
                    "test",
                    stream_callback=lambda line, is_stderr: callback_calls.append(
                        (line, is_stderr)
                    ),
                )

        # "\n\n".join joins blocks; .splitlines() then yields 4 lines:
        # ["Para one line A", "Para one line B", "", "Para two only"]
        assert callback_calls == [
            ("Para one line A", False),
            ("Para one line B", False),
            ("", False),
            ("Para two only", False),
        ]
        # stdout reconstruction preserves the full text via "\n".join
        assert result.stdout == "Para one line A\nPara one line B\n\nPara two only"

    def test_unknown_event_type_skipped(self) -> None:
        """Non-init, non-assistant, non-result JSON events are skipped: no stdout, no callback."""
        tool_use_event = '{"type": "tool_use", "id": "tu_123", "name": "Bash"}\n'
        mock_process = Mock()
        mock_process.stdout = io.StringIO(tool_use_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        callback_calls: list[Any] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                result = run_claude_command(
                    "test",
                    stream_callback=lambda line, is_stderr: callback_calls.append(
                        (line, is_stderr)
                    ),
                )

        assert result.stdout == ""
        assert callback_calls == []

    def test_on_usage_callback_called_with_result_event(self) -> None:
        """on_usage callback receives (input_tokens + cache_read, output_tokens) from result event."""
        result_event = (
            '{"type": "result", "usage": {"input_tokens": 1000, "output_tokens": 200, '
            '"cache_read_input_tokens": 500, "cache_creation_input_tokens": 0}}\n'
        )
        mock_process = Mock()
        mock_process.stdout = io.StringIO(result_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        usage_calls: list[tuple[int, int]] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                result = run_claude_command(
                    "test",
                    on_usage=lambda inp, out: usage_calls.append((inp, out)),
                )

        assert usage_calls == [(1500, 200)]
        assert result.stdout == ""

    def test_on_usage_not_called_when_result_has_no_usage(self) -> None:
        """on_usage callback is not fired when result event has no usage block."""
        result_event = '{"type": "result", "subtype": "success", "cost_usd": 0.01}\n'
        mock_process = Mock()
        mock_process.stdout = io.StringIO(result_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        usage_calls: list[tuple[int, int]] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                run_claude_command(
                    "test",
                    on_usage=lambda inp, out: usage_calls.append((inp, out)),
                )

        assert usage_calls == []

    def test_on_usage_detailed_callback_called_with_result_event(self) -> None:
        """on_usage_detailed callback receives all four token fields plus model."""
        result_event = (
            '{"type": "result", "model": "claude-sonnet-4-6", "usage": {"input_tokens": 1000, '
            '"output_tokens": 200, "cache_read_input_tokens": 500, "cache_creation_input_tokens": 75}}\n'
        )
        mock_process = Mock()
        mock_process.stdout = io.StringIO(result_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        from little_loops.subprocess_utils import TokenUsage

        detailed_calls: list[TokenUsage] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                run_claude_command("test", on_usage_detailed=detailed_calls.append)

        assert len(detailed_calls) == 1
        u = detailed_calls[0]
        assert u.input_tokens == 1000
        assert u.output_tokens == 200
        assert u.cache_read_tokens == 500
        assert u.cache_creation_tokens == 75
        assert u.model == "claude-sonnet-4-6"

    def test_on_usage_detailed_not_called_when_no_usage(self) -> None:
        """on_usage_detailed is not fired when result event has no usage block."""
        result_event = '{"type": "result", "subtype": "success"}\n'
        mock_process = Mock()
        mock_process.stdout = io.StringIO(result_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        from little_loops.subprocess_utils import TokenUsage

        detailed_calls: list[TokenUsage] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                run_claude_command("test", on_usage_detailed=detailed_calls.append)

        assert detailed_calls == []

    def test_result_event_is_error_appends_to_stderr(self) -> None:
        """result event with is_error=True appends [result] prefixed error to stderr."""
        result_event = (
            '{"type": "result", "is_error": true, "error": "Permission denied: tool failed"}\n'
        )
        mock_process = Mock()
        mock_process.stdout = io.StringIO(result_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                result = run_claude_command("test")

        assert "[result] Permission denied: tool failed" in result.stderr
        assert result.stdout == ""

    def test_result_event_no_is_error_does_not_append_to_stderr(self) -> None:
        """result event without is_error does not add anything to stderr."""
        result_event = '{"type": "result", "subtype": "success", "result": "done"}\n'
        mock_process = Mock()
        mock_process.stdout = io.StringIO(result_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                result = run_claude_command("test")

        assert result.stderr == ""

    def test_non_json_line_passes_through(self) -> None:
        """Non-JSON stdout lines pass through as raw text (backward compat)."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("plain text line\n")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                result = run_claude_command("test")

        assert result.stdout == "plain text line"

    def _make_two_line_selector(self, mock_selector: Any, mock_process: Mock) -> None:
        """Configure selector to return stdout key twice then exit loop."""
        _patch_selector_cm(mock_selector)
        selector_instance = mock_selector.return_value
        call_count = [0]

        def get_map_side_effect() -> dict[Any, Any]:
            call_count[0] += 1
            return {"stdout": True} if call_count[0] <= 2 else {}

        selector_instance.get_map.side_effect = get_map_side_effect
        key = Mock()
        key.fileobj = mock_process.stdout
        selector_instance.select.return_value = [(key, None)]
        selector_instance.register = Mock()
        selector_instance.unregister = Mock()

    def test_model_falls_back_to_init_event_when_result_has_no_model(self) -> None:
        """TokenUsage.model uses init-event model when result event omits model (BUG-1897)."""
        init_event = '{"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}\n'
        result_event = (
            '{"type": "result", "usage": {"input_tokens": 100, "output_tokens": 50, '
            '"cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}\n'
        )
        mock_process = Mock()
        mock_process.stdout = io.StringIO(init_event + result_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        from little_loops.subprocess_utils import TokenUsage

        detailed_calls: list[TokenUsage] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_two_line_selector(mock_selector, mock_process)
                run_claude_command("test", on_usage_detailed=detailed_calls.append)

        assert len(detailed_calls) == 1
        assert detailed_calls[0].model == "claude-sonnet-4-6"

    def test_result_event_model_takes_priority_over_init_event_model(self) -> None:
        """Explicit model field in result event takes priority over init-captured model."""
        init_event = '{"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}\n'
        result_event = (
            '{"type": "result", "model": "claude-opus-4-8", "usage": {"input_tokens": 100, '
            '"output_tokens": 50, "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}}\n'
        )
        mock_process = Mock()
        mock_process.stdout = io.StringIO(init_event + result_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        from little_loops.subprocess_utils import TokenUsage

        detailed_calls: list[TokenUsage] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_two_line_selector(mock_selector, mock_process)
                run_claude_command("test", on_usage_detailed=detailed_calls.append)

        assert len(detailed_calls) == 1
        assert detailed_calls[0].model == "claude-opus-4-8"

    def test_on_model_detected_none_no_error(self) -> None:
        """Omitting on_model_detected when init event arrives raises no error."""
        init_event = '{"type": "system", "subtype": "init", "model": "claude-sonnet-4-6"}\n'
        mock_process = Mock()
        mock_process.stdout = io.StringIO(init_event)
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_single_line_selector(mock_selector, mock_process)
                result = run_claude_command("test")  # no on_model_detected

        assert result is not None  # no exception


# =============================================================================
# TestRunClaudeCommandAgentToolsFlags
# =============================================================================


class TestRunClaudeCommandAgentToolsFlags:
    """Tests for --agent and --tools flag support in run_claude_command() (FEAT-1011)."""

    def _make_mock_process(self) -> Mock:
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        return mock_process

    def test_agent_flag_appended_to_cmd_args(self) -> None:
        """--agent <name> is appended to cmd_args when agent is set."""
        mock_process = self._make_mock_process()
        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("/ll:test", agent="my-agent")

        assert len(captured_args) == 1
        assert "--agent" in captured_args[0]
        assert captured_args[0][captured_args[0].index("--agent") + 1] == "my-agent"

    def test_tools_flag_appended_as_csv(self) -> None:
        """--tools Bash,Edit is appended to cmd_args when tools is set."""
        mock_process = self._make_mock_process()
        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("/ll:test", tools=["Bash", "Edit"])

        assert len(captured_args) == 1
        assert "--tools" in captured_args[0]
        assert captured_args[0][captured_args[0].index("--tools") + 1] == "Bash,Edit"

    def test_agent_and_tools_both_appended(self) -> None:
        """Both --agent and --tools are appended when both are set."""
        mock_process = self._make_mock_process()
        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("/ll:test", agent="my-agent", tools=["ToolSearch"])

        assert len(captured_args) == 1
        args = captured_args[0]
        assert "--agent" in args
        assert args[args.index("--agent") + 1] == "my-agent"
        assert "--tools" in args
        assert args[args.index("--tools") + 1] == "ToolSearch"

    def test_no_agent_or_tools_flags_when_none(self) -> None:
        """No --agent or --tools flags when both are None (default)."""
        mock_process = self._make_mock_process()
        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("/ll:test")

        assert len(captured_args) == 1
        assert "--agent" not in captured_args[0]
        assert "--tools" not in captured_args[0]

    def test_tools_single_item_no_trailing_comma(self) -> None:
        """Single tool is passed without trailing comma."""
        mock_process = self._make_mock_process()
        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("/ll:test", tools=["ToolSearch"])

        assert len(captured_args) == 1
        idx = captured_args[0].index("--tools")
        assert captured_args[0][idx + 1] == "ToolSearch"

    def test_model_flag_appended_to_cmd_args(self) -> None:
        """--model <id> is appended to cmd_args when model is set."""
        mock_process = self._make_mock_process()
        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("/ll:test", model="claude-haiku-4-5-20251001")

        assert len(captured_args) == 1
        assert "--model" in captured_args[0]
        idx = captured_args[0].index("--model")
        assert captured_args[0][idx + 1] == "claude-haiku-4-5-20251001"

    def test_no_model_flag_when_none(self) -> None:
        """No --model flag is added when model is None (default)."""
        mock_process = self._make_mock_process()
        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("/ll:test")

        assert len(captured_args) == 1
        assert "--model" not in captured_args[0]


class TestRunClaudeCommandResumeSession:
    """Tests for resume_session flag in run_claude_command() (BUG-1377 Option E)."""

    def _make_mock_process(self) -> Mock:
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None
        return mock_process

    def test_resume_session_adds_continue_flag(self) -> None:
        """resume_session=True inserts --continue before -p in cmd_args."""
        mock_process = self._make_mock_process()
        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test command", resume_session=True)

        assert len(captured_args) == 1
        args = captured_args[0]
        assert "--continue" in args
        continue_idx = args.index("--continue")
        p_idx = args.index("-p")
        assert continue_idx < p_idx, "--continue must appear before -p"

    def test_no_continue_flag_by_default(self) -> None:
        """resume_session=False (default) does not add --continue to cmd_args."""
        mock_process = self._make_mock_process()
        captured_args: list[Any] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test command")

        assert len(captured_args) == 1
        assert "--continue" not in captured_args[0]


class TestAssembleGuillatinePrompt:
    """Tests for assemble_guillotine_prompt() (BUG-1377 Option J)."""

    def test_includes_original_task(self, tmp_path: Path) -> None:
        """Assembled prompt includes truncated original command for task intent."""
        from little_loops.subprocess_utils import assemble_guillotine_prompt

        prompt = assemble_guillotine_prompt(
            original_command="/ll:manage-issue bug fix BUG-1377",
            captured_stdout="Partial work...",
            token_stats={"input_tokens": 180_000, "output_tokens": 5_000, "context_limit": 200_000},
        )

        assert "CONTEXT LIMIT REACHED" in prompt
        assert "/ll:manage-issue bug fix BUG-1377" in prompt
        assert "Original Task" in prompt

    def test_includes_stdout_tail(self, tmp_path: Path) -> None:
        """Assembled prompt includes a tail of captured_stdout."""
        from little_loops.subprocess_utils import assemble_guillotine_prompt

        long_output = "line\n" * 10_000
        prompt = assemble_guillotine_prompt(
            original_command="task",
            captured_stdout=long_output,
            token_stats={"input_tokens": 180_000, "output_tokens": 5_000, "context_limit": 200_000},
        )

        assert "Last Session Output" in prompt
        # Tail must be present but total prompt must not contain all 10K lines
        assert len(prompt) < len(long_output)

    def test_handles_empty_stdout(self, tmp_path: Path) -> None:
        """Empty captured_stdout produces a valid prompt with fallback message."""
        from little_loops.subprocess_utils import assemble_guillotine_prompt

        prompt = assemble_guillotine_prompt(
            original_command="task",
            captured_stdout="",
            token_stats={"input_tokens": 0, "output_tokens": 0, "context_limit": 200_000},
        )

        assert "CONTEXT LIMIT REACHED" in prompt
        assert "interrupted at session start" in prompt or "no output captured" in prompt.lower()

    def test_includes_token_stats(self, tmp_path: Path) -> None:
        """Token statistics are included in the assembled prompt."""
        from little_loops.subprocess_utils import assemble_guillotine_prompt

        prompt = assemble_guillotine_prompt(
            original_command="task",
            captured_stdout="output",
            token_stats={
                "input_tokens": 185_000,
                "output_tokens": 5_000,
                "context_limit": 200_000,
                "trigger_reason": "usage 95%",
            },
        )

        assert "190,000" in prompt or "190000" in prompt  # total tokens
        assert "200,000" in prompt or "200000" in prompt  # context limit
        assert "usage 95%" in prompt

    def test_sprint_context_prepends_framing_block(self) -> None:
        """When sprint_context is set, sprint framing appears before the standard body (BUG-2141)."""
        from little_loops.parallel.types import SprintWorkerContext
        from little_loops.subprocess_utils import assemble_guillotine_prompt

        ctx = SprintWorkerContext(issue_id="FEAT-025", branch="main")
        prompt = assemble_guillotine_prompt(
            original_command="/ll:manage-issue feature implement FEAT-025",
            captured_stdout="Partial work...",
            token_stats={
                "input_tokens": 185_000,
                "output_tokens": 10_000,
                "context_limit": 200_000,
            },
            sprint_context=ctx,
        )

        assert "Sprint Worker Context" in prompt
        assert "FEAT-025" in prompt
        assert "exit immediately" in prompt
        assert "Branch: main" in prompt
        # Framing must come before the standard body
        assert prompt.index("Sprint Worker Context") < prompt.index("CONTEXT LIMIT REACHED")

    def test_no_sprint_context_unaffected(self) -> None:
        """Without sprint_context, output is identical to the original (no framing added)."""
        from little_loops.subprocess_utils import assemble_guillotine_prompt

        prompt = assemble_guillotine_prompt(
            original_command="task",
            captured_stdout="output",
            token_stats={"input_tokens": 0, "output_tokens": 0, "context_limit": 200_000},
        )

        assert "Sprint Worker Context" not in prompt
        assert prompt.startswith("⚠ CONTEXT LIMIT REACHED")


class TestSentinelHelpers:
    """Tests for write_sentinel() and read_sentinel() (BUG-1377 Option G)."""

    def test_write_and_read_sentinel(self, tmp_path: Path) -> None:
        """write_sentinel creates valid JSON; read_sentinel reads and deletes it."""
        from little_loops.subprocess_utils import SENTINEL_PATH, read_sentinel, write_sentinel

        write_sentinel(tmp_path, token_count=130_000, context_limit=200_000)
        sentinel_file = tmp_path / SENTINEL_PATH
        assert sentinel_file.exists()

        data = read_sentinel(tmp_path)
        assert data is not None
        assert data["token_count"] == 130_000
        assert data["context_limit"] == 200_000
        assert data["usage_percent"] == 65
        assert "written_at" in data

        # Consumed: file deleted after read
        assert not sentinel_file.exists()

    def test_read_sentinel_returns_none_when_absent(self, tmp_path: Path) -> None:
        """read_sentinel returns None when no sentinel file exists."""
        from little_loops.subprocess_utils import read_sentinel

        assert read_sentinel(tmp_path) is None

    def test_read_sentinel_idempotent(self, tmp_path: Path) -> None:
        """Second read_sentinel call returns None (sentinel consumed on first read)."""
        from little_loops.subprocess_utils import read_sentinel, write_sentinel

        write_sentinel(tmp_path, token_count=100_000, context_limit=200_000)
        read_sentinel(tmp_path)
        assert read_sentinel(tmp_path) is None


# =============================================================================
# TestRunClaudeCommandHostRunner
# =============================================================================


class TestRunClaudeCommandHostRunner:
    """Tests for resolve_host() delegation in run_claude_command()."""

    def test_delegates_to_resolve_host(self) -> None:
        """run_claude_command calls resolve_host() and uses the returned HostInvocation."""
        from little_loops.host_runner import HostInvocation

        mock_invocation = HostInvocation(
            binary="myhost",
            args=[
                "--dangerously-skip-permissions",
                "--verbose",
                "--output-format",
                "stream-json",
                "-p",
                "test",
            ],
            env={"CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1"},
        )
        mock_runner = Mock()
        mock_runner.build_streaming.return_value = mock_invocation

        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        captured_args: list[list[str]] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_args.append(args)
            return mock_process

        with patch("little_loops.subprocess_utils.resolve_host", return_value=mock_runner):
            with patch("subprocess.Popen", side_effect=capture_popen):
                with patch("selectors.DefaultSelector") as mock_selector:
                    _patch_selector_cm(mock_selector)
                    mock_selector.return_value.get_map.return_value = {}
                    run_claude_command("test")

        mock_runner.build_streaming.assert_called_once_with(
            prompt="test",
            working_dir=None,
            resume=False,
            agent=None,
            tools=None,
            model=None,
        )
        assert captured_args[0][0] == "myhost"

    def test_invocation_env_overrides_os_environ(self) -> None:
        """HostInvocation.env values win over conflicting os.environ keys."""
        from little_loops.host_runner import HostInvocation

        mock_invocation = HostInvocation(
            binary="claude",
            args=["-p", "test"],
            env={"CONFLICT_KEY": "from_runner", "CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR": "1"},
        )
        mock_runner = Mock()
        mock_runner.build_streaming.return_value = mock_invocation

        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        captured_env: dict[str, str] = {}

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_env.update(kwargs.get("env", {}))
            return mock_process

        with patch("little_loops.subprocess_utils.resolve_host", return_value=mock_runner):
            with patch("subprocess.Popen", side_effect=capture_popen):
                with patch("selectors.DefaultSelector") as mock_selector:
                    _patch_selector_cm(mock_selector)
                    mock_selector.return_value.get_map.return_value = {}
                    with patch.dict(os.environ, {"CONFLICT_KEY": "from_environ"}):
                        run_claude_command("test")

        assert captured_env["CONFLICT_KEY"] == "from_runner"

    def test_host_not_configured_propagates(self) -> None:
        """HostNotConfigured from resolve_host() propagates through run_claude_command()."""
        from little_loops.host_runner import HostNotConfigured

        with patch(
            "little_loops.subprocess_utils.resolve_host", side_effect=HostNotConfigured("no host")
        ):
            with pytest.raises(HostNotConfigured):
                run_claude_command("test")


class _NeverEOFStdout:
    """Fake stdout whose pipe never reaches EOF.

    Simulates the hang regression: a background Workflow/Task child process
    inherits the stdout pipe's write-end, so ``readline()`` never returns the
    empty string (EOF) even though the ``claude`` turn finished. Each scripted
    line is yielded once; any read *past* the scripted lines returns a sentinel
    "LEAKED" assistant event, proving the reader failed to stop on the terminal
    ``result`` event.
    """

    def __init__(self, lines: list[str]) -> None:
        self._lines = list(lines)
        self.read_past_result = False

    def readline(self) -> str:
        if self._lines:
            return self._lines.pop(0)
        self.read_past_result = True
        return (
            '{"type": "assistant", "message": {"content": [{"type": "text", "text": "LEAKED"}]}}\n'
        )


class TestRunClaudeCommandResultBreak:
    """The reader must stop on the stream-json ``result`` event rather than
    waiting for pipe EOF, which inherited background-task FDs may never deliver
    (ll-auto 3600s hang-on-success regression)."""

    def _make_never_eof_selector(self, mock_selector: Any, mock_process: Mock) -> None:
        """Selector whose get_map() is ALWAYS truthy (pipe never EOFs).

        With the fix, the loop terminates only because ``result_seen`` triggers a
        ``break``; without it the loop would spin until the wall-clock timeout.
        """
        _patch_selector_cm(mock_selector)
        instance = mock_selector.return_value
        instance.get_map.return_value = {"stdout": True}  # never empties -> no EOF exit
        key = Mock()
        key.fileobj = mock_process.stdout
        instance.select.return_value = [(key, None)]
        instance.register = Mock()
        instance.unregister = Mock()

    def test_breaks_on_result_event_without_pipe_eof(self) -> None:
        """run_claude_command returns on the result event even though stdout never EOFs."""
        assistant_event = (
            '{"type": "assistant", "message": {"content": ['
            '{"type": "text", "text": "Done implementing"}]}}\n'
        )
        result_event = (
            '{"type": "result", "subtype": "success", '
            '"usage": {"input_tokens": 1000, "output_tokens": 200}}\n'
        )
        fake_stdout = _NeverEOFStdout([assistant_event, result_event])
        mock_process = Mock()
        mock_process.stdout = fake_stdout
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        usage_calls: list[tuple[int, int]] = []

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                self._make_never_eof_selector(mock_selector, mock_process)
                # Short timeout: a regression (no break) fails fast instead of
                # hanging CI. The fix returns near-instantly, well under this.
                result = run_claude_command(
                    "test",
                    timeout=5,
                    on_usage=lambda inp, out: usage_calls.append((inp, out)),
                )

        # Stopped on the result event: never read past it into the leak sentinel.
        assert fake_stdout.read_past_result is False
        assert "LEAKED" not in result.stdout
        # Assistant text captured; usage callback fired before the break.
        assert result.stdout == "Done implementing"
        assert usage_calls == [(1000, 200)]
        # Clean return (not a TimeoutExpired); process reaped via wait().
        assert result.returncode == 0
        mock_process.wait.assert_called_once_with(timeout=30)


# =============================================================================
# TestProcessGroupKill
# =============================================================================


class TestProcessGroupKill:
    """Tests for process-group kill behaviour (ENH-1999)."""

    def _make_mock_process(self, pid: int = 12345) -> Mock:
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.wait.return_value = None
        mock_process.kill = Mock()
        mock_process.pid = pid
        return mock_process

    def _time_out_values(self, start: float = 1000.0) -> list:
        return [start, start, start + 2.0]

    def test_popen_uses_start_new_session(self) -> None:
        """Popen is called with start_new_session=True."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = 0
        mock_process.wait.return_value = None

        captured_kwargs: list[dict] = []

        def capture_popen(args: Any, **kwargs: Any) -> Mock:
            captured_kwargs.append(kwargs)
            return mock_process

        with patch("subprocess.Popen", side_effect=capture_popen):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}
                run_claude_command("test")

        assert len(captured_kwargs) == 1
        assert captured_kwargs[0].get("start_new_session") is True

    def test_wall_clock_timeout_uses_killpg(self) -> None:
        """Wall-clock timeout path calls os.killpg, not process.kill."""
        mock_process = self._make_mock_process(pid=11111)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {"stdout": True}
                mock_selector.return_value.select.return_value = []
                mock_selector.return_value.register = Mock()
                mock_selector.return_value.unregister = Mock()

                start_time = 1000.0
                time_values = [start_time, start_time + 2.0]
                time_index = [0]

                def mock_time() -> float:
                    val = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return val

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", return_value=55) as mock_getpgid:
                        with patch("os.killpg") as mock_killpg:
                            with pytest.raises(subprocess.TimeoutExpired):
                                run_claude_command("test", timeout=1)

        mock_getpgid.assert_called_once_with(11111)
        mock_killpg.assert_called_once_with(55, signal.SIGKILL)
        mock_process.kill.assert_not_called()

    def test_idle_timeout_uses_killpg(self) -> None:
        """Idle-timeout path calls os.killpg, not process.kill."""
        mock_process = self._make_mock_process(pid=22222)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {"stdout": True}
                mock_selector.return_value.select.return_value = []
                mock_selector.return_value.register = Mock()
                mock_selector.return_value.unregister = Mock()

                start_time = 1000.0
                time_values = [start_time, start_time, start_time + 0.5, start_time + 11.0]
                time_index = [0]

                def mock_time() -> float:
                    val = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return val

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", return_value=66) as mock_getpgid:
                        with patch("os.killpg") as mock_killpg:
                            with pytest.raises(subprocess.TimeoutExpired):
                                run_claude_command("test", timeout=3600, idle_timeout=10)

        mock_getpgid.assert_called_once_with(22222)
        mock_killpg.assert_called_once_with(66, signal.SIGKILL)
        mock_process.kill.assert_not_called()

    def test_fallback_kill_uses_killpg(self) -> None:
        """Post-stream-close fallback kill path calls os.killpg."""
        mock_process = Mock()
        mock_process.stdout = io.StringIO("")
        mock_process.stderr = io.StringIO("")
        mock_process.returncode = None
        mock_process.pid = 33333
        mock_process.kill = Mock()
        mock_process.wait.side_effect = [
            subprocess.TimeoutExpired("cmd", 30),
            None,
        ]

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {}

                with patch("os.getpgid", return_value=77) as mock_getpgid:
                    with patch("os.killpg") as mock_killpg:
                        run_claude_command("test")

        mock_getpgid.assert_called_once_with(33333)
        mock_killpg.assert_called_once_with(77, signal.SIGKILL)
        mock_process.kill.assert_not_called()

    def test_falls_back_to_process_kill_on_process_lookup_error(self) -> None:
        """_kill_process_group falls back to process.kill() when killpg raises ProcessLookupError."""
        mock_process = self._make_mock_process(pid=44444)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {"stdout": True}
                mock_selector.return_value.select.return_value = []
                mock_selector.return_value.register = Mock()
                mock_selector.return_value.unregister = Mock()

                start_time = 1000.0
                time_values = [start_time, start_time + 2.0]
                time_index = [0]

                def mock_time() -> float:
                    val = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return val

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", side_effect=ProcessLookupError("no such process")):
                        with pytest.raises(subprocess.TimeoutExpired):
                            run_claude_command("test", timeout=1)

        mock_process.kill.assert_called_once()

    def test_falls_back_to_process_kill_on_permission_error(self) -> None:
        """_kill_process_group falls back when killpg raises PermissionError."""
        mock_process = self._make_mock_process(pid=55555)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {"stdout": True}
                mock_selector.return_value.select.return_value = []
                mock_selector.return_value.register = Mock()
                mock_selector.return_value.unregister = Mock()

                start_time = 1000.0
                time_values = [start_time, start_time + 2.0]
                time_index = [0]

                def mock_time() -> float:
                    val = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return val

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", return_value=88):
                        with patch("os.killpg", side_effect=PermissionError("denied")):
                            with pytest.raises(subprocess.TimeoutExpired):
                                run_claude_command("test", timeout=1)

        mock_process.kill.assert_called_once()

    def test_falls_back_to_process_kill_when_killpg_absent(self) -> None:
        """_kill_process_group falls back when os.killpg raises AttributeError (non-POSIX)."""
        mock_process = self._make_mock_process(pid=66666)

        with patch("subprocess.Popen", return_value=mock_process):
            with patch("selectors.DefaultSelector") as mock_selector:
                _patch_selector_cm(mock_selector)
                mock_selector.return_value.get_map.return_value = {"stdout": True}
                mock_selector.return_value.select.return_value = []
                mock_selector.return_value.register = Mock()
                mock_selector.return_value.unregister = Mock()

                start_time = 1000.0
                time_values = [start_time, start_time + 2.0]
                time_index = [0]

                def mock_time() -> float:
                    val = time_values[min(time_index[0], len(time_values) - 1)]
                    time_index[0] += 1
                    return val

                with patch("time.time", side_effect=mock_time):
                    with patch("os.getpgid", side_effect=AttributeError("no killpg on Windows")):
                        with pytest.raises(subprocess.TimeoutExpired):
                            run_claude_command("test", timeout=1)

        mock_process.kill.assert_called_once()

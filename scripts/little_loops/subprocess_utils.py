"""Subprocess utilities for Claude CLI invocation.

Provides shared functionality for running Claude CLI commands with
real-time output streaming, timeout handling, and context handoff detection.
"""

from __future__ import annotations

import logging
import os
import re
import selectors
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

logger = logging.getLogger(__name__)

# Callback type: (line: str, is_stderr: bool) -> None
OutputCallback = Callable[[str, bool], None]

# Process lifecycle callback: (process: Popen) -> None
ProcessCallback = Callable[[subprocess.Popen[str]], None]

# Context handoff detection pattern
CONTEXT_HANDOFF_PATTERN = re.compile(r"CONTEXT_HANDOFF:\s*Ready for fresh session")
CONTINUATION_PROMPT_PATH = Path(".claude/ll-continue-prompt.md")


def detect_context_handoff(output: str) -> bool:
    """Check if output contains a context handoff signal.

    Args:
        output: Command output to check

    Returns:
        True if context handoff was signaled
    """
    return bool(CONTEXT_HANDOFF_PATTERN.search(output))


def read_continuation_prompt(repo_path: Path | None = None) -> str | None:
    """Read the continuation prompt file if it exists.

    Args:
        repo_path: Optional repository root path

    Returns:
        Contents of continuation prompt, or None if not found
    """
    prompt_path = (repo_path or Path.cwd()) / CONTINUATION_PROMPT_PATH
    if prompt_path.exists():
        return prompt_path.read_text()
    return None


def run_claude_command(
    command: str,
    timeout: int = 3600,
    working_dir: Path | None = None,
    stream_callback: OutputCallback | None = None,
    on_process_start: ProcessCallback | None = None,
    on_process_end: ProcessCallback | None = None,
    idle_timeout: int = 0,
) -> subprocess.CompletedProcess[str]:
    """Invoke Claude CLI command with real-time output streaming.

    Args:
        command: Command to pass to Claude CLI
        timeout: Timeout in seconds (0 for no timeout)
        working_dir: Optional working directory for the command
        stream_callback: Optional callback for streaming output lines.
            Called with (line, is_stderr) for each line of output.
        on_process_start: Optional callback invoked after process starts.
            Receives the Popen object for tracking/management.
        on_process_end: Optional callback invoked after process completes.
            Receives the Popen object. Called in finally block.
        idle_timeout: Kill process if no output for this many seconds (0 to disable).

    Returns:
        CompletedProcess with stdout/stderr captured

    Raises:
        subprocess.TimeoutExpired: If command exceeds timeout or idle timeout.
            When triggered by idle timeout, the output field is set to "idle_timeout".
    """
    cmd_args = ["claude", "--dangerously-skip-permissions", "-p", command]

    # Set environment to keep Claude in the project working directory (BUG-007)
    # This helps prevent file writes from leaking to the main repo in worktrees
    env = os.environ.copy()
    env["CLAUDE_BASH_MAINTAIN_PROJECT_WORKING_DIR"] = "1"

    process = subprocess.Popen(
        cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
        cwd=working_dir,
        env=env,
    )

    if on_process_start:
        on_process_start(process)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    # Use selectors for non-blocking read from both streams
    with selectors.DefaultSelector() as sel:
        if process.stdout:
            sel.register(process.stdout, selectors.EVENT_READ)
        if process.stderr:
            sel.register(process.stderr, selectors.EVENT_READ)

        start_time = time.time()
        last_output_time = start_time

        try:
            while sel.get_map():
                now = time.time()
                if timeout and (now - start_time) > timeout:
                    process.kill()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Process %s did not terminate within 10s after kill",
                            process.pid,
                        )
                    raise subprocess.TimeoutExpired(cmd_args, timeout)

                if idle_timeout and (now - last_output_time) > idle_timeout:
                    process.kill()
                    try:
                        process.wait(timeout=10)
                    except subprocess.TimeoutExpired:
                        logger.warning(
                            "Process %s did not terminate within 10s after kill",
                            process.pid,
                        )
                    raise subprocess.TimeoutExpired(cmd_args, idle_timeout, output="idle_timeout")

                ready = sel.select(timeout=1.0)
                for key, _ in ready:
                    line = key.fileobj.readline()  # type: ignore[union-attr]
                    if not line:
                        sel.unregister(key.fileobj)
                        continue

                    last_output_time = time.time()
                    line = line.rstrip("\n")
                    is_stderr = key.fileobj is process.stderr

                    if is_stderr:
                        stderr_lines.append(line)
                    else:
                        stdout_lines.append(line)

                    if stream_callback:
                        stream_callback(line, is_stderr)

            try:
                process.wait(timeout=30)
            except subprocess.TimeoutExpired:
                logger.warning(
                    "Process %s did not exit within 30s after streams closed, killing",
                    process.pid,
                )
                process.kill()
                try:
                    process.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    logger.warning(
                        "Process %s did not terminate within 10s after kill",
                        process.pid,
                    )
        finally:
            if on_process_end:
                on_process_end(process)

    return subprocess.CompletedProcess(
        cmd_args,
        process.returncode or 0,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
    )

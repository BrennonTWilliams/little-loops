"""Subprocess utilities for Claude CLI invocation.

Provides shared functionality for running Claude CLI commands with
real-time output streaming and timeout handling.
"""

from __future__ import annotations

import selectors
import subprocess
import time
from collections.abc import Callable
from pathlib import Path

# Callback type: (line: str, is_stderr: bool) -> None
OutputCallback = Callable[[str, bool], None]

# Process lifecycle callback: (process: Popen) -> None
ProcessCallback = Callable[[subprocess.Popen[str]], None]


def run_claude_command(
    command: str,
    timeout: int = 3600,
    working_dir: Path | None = None,
    stream_callback: OutputCallback | None = None,
    on_process_start: ProcessCallback | None = None,
    on_process_end: ProcessCallback | None = None,
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

    Returns:
        CompletedProcess with stdout/stderr captured

    Raises:
        subprocess.TimeoutExpired: If command exceeds timeout
    """
    cmd_args = ["claude", "--dangerously-skip-permissions", "-p", command]

    process = subprocess.Popen(
        cmd_args,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        bufsize=1,  # Line buffered
        cwd=working_dir,
    )

    if on_process_start:
        on_process_start(process)

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    # Use selectors for non-blocking read from both streams
    sel = selectors.DefaultSelector()
    if process.stdout:
        sel.register(process.stdout, selectors.EVENT_READ)
    if process.stderr:
        sel.register(process.stderr, selectors.EVENT_READ)

    start_time = time.time()

    try:
        while sel.get_map():
            if timeout and (time.time() - start_time) > timeout:
                process.kill()
                raise subprocess.TimeoutExpired(cmd_args, timeout)

            ready = sel.select(timeout=1.0)
            for key, _ in ready:
                line = key.fileobj.readline()  # type: ignore[union-attr]
                if not line:
                    sel.unregister(key.fileobj)
                    continue

                line = line.rstrip("\n")
                is_stderr = key.fileobj is process.stderr

                if is_stderr:
                    stderr_lines.append(line)
                else:
                    stdout_lines.append(line)

                if stream_callback:
                    stream_callback(line, is_stderr)

        process.wait()
    finally:
        if on_process_end:
            on_process_end(process)

    return subprocess.CompletedProcess(
        cmd_args,
        process.returncode or 0,
        stdout="\n".join(stdout_lines),
        stderr="\n".join(stderr_lines),
    )

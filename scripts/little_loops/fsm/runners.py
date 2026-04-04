"""FSM action runner implementations.

Provides the protocol and concrete implementations for action execution:
- ActionRunner: Protocol defining the runner interface
- DefaultActionRunner: Subprocess-based runner for real execution
- SimulationActionRunner: Interactive/scenario-based runner for testing and dry-runs
"""

from __future__ import annotations

import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Protocol

from little_loops.fsm.types import ActionResult
from little_loops.subprocess_utils import run_claude_command


def _now_ms() -> int:
    """Get current time in milliseconds."""
    return int(time.time() * 1000)


class ActionRunner(Protocol):
    """Protocol for action execution."""

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        on_output_line: Callable[[str], None] | None = None,
    ) -> ActionResult:
        """Execute an action and return the result.

        Args:
            action: The command to execute
            timeout: Timeout in seconds
            is_slash_command: True if this is a slash command (starts with /)
            on_output_line: Optional callback invoked for each output line

        Returns:
            ActionResult with output, stderr, exit_code, duration_ms
        """
        ...


class DefaultActionRunner:
    """Execute actions via subprocess or Claude CLI."""

    def __init__(self) -> None:
        self._current_process: subprocess.Popen[str] | None = None

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        on_output_line: Callable[[str], None] | None = None,
    ) -> ActionResult:
        """Execute action and return result, streaming output line by line.

        Args:
            action: The command to execute
            timeout: Timeout in seconds
            is_slash_command: True if action starts with /
            on_output_line: Optional callback invoked for each stdout line

        Returns:
            ActionResult with execution details
        """
        start = _now_ms()

        if is_slash_command:
            # Execute via Claude CLI using run_claude_command() so that the
            # subprocess loads the full plugin/tool context (including deferred
            # tools like Skill). The old --no-session-persistence path prevented
            # ToolSearch from resolving deferred tool schemas (BUG-946).
            def _stream_cb(line: str, is_stderr: bool) -> None:
                if not is_stderr and on_output_line:
                    on_output_line(line)

            def _on_proc_start(p: subprocess.Popen[str]) -> None:
                self._current_process = p

            def _on_proc_end(p: subprocess.Popen[str]) -> None:
                self._current_process = None

            try:
                completed = run_claude_command(
                    command=action,
                    timeout=timeout,
                    stream_callback=_stream_cb,
                    on_process_start=_on_proc_start,
                    on_process_end=_on_proc_end,
                )
            except subprocess.TimeoutExpired:
                return ActionResult(
                    output="",
                    stderr="Action timed out",
                    exit_code=124,
                    duration_ms=timeout * 1000,
                )
            return ActionResult(
                output=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
                duration_ms=_now_ms() - start,
            )

        # Shell command
        cmd = ["bash", "-c", action]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._current_process = process
        output_chunks: list[str] = []
        stderr_chunks: list[str] = []

        def _drain_stderr() -> None:
            assert process.stderr is not None
            for line in process.stderr:
                stderr_chunks.append(line)

        stderr_thread = threading.Thread(target=_drain_stderr, daemon=True)
        stderr_thread.start()

        try:
            for line in process.stdout:  # type: ignore[union-attr]
                output_chunks.append(line)
                if on_output_line:
                    on_output_line(line.rstrip())
            process.wait(timeout=timeout)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
            stderr_thread.join(timeout=5)
            return ActionResult(
                output="".join(output_chunks),
                stderr="".join(stderr_chunks) or "Action timed out",
                exit_code=124,
                duration_ms=timeout * 1000,
            )
        finally:
            self._current_process = None
        stderr_thread.join(timeout=5)
        stderr = "".join(stderr_chunks)
        return ActionResult(
            output="".join(output_chunks),
            stderr=stderr,
            exit_code=process.returncode,
            duration_ms=_now_ms() - start,
        )


@dataclass
class SimulationActionRunner:
    """Action runner for simulation mode - prompts user instead of executing.

    This runner allows users to trace through FSM logic without executing
    real commands. It can either prompt interactively for results or use
    predefined scenarios.

    Attributes:
        scenario: Predefined result pattern ("all-pass", "all-fail", "first-fail", "alternating")
        call_count: Number of actions simulated so far
        calls: List of all actions that would have been executed
    """

    scenario: str | None = None
    call_count: int = 0
    calls: list[str] = field(default_factory=list)

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        on_output_line: Callable[[str], None] | None = None,
    ) -> ActionResult:
        """Prompt user for simulated result instead of executing.

        Args:
            action: The command that would be executed
            timeout: Timeout (ignored in simulation)
            is_slash_command: Whether this is a slash command
            on_output_line: Ignored in simulation

        Returns:
            ActionResult with simulated exit code
        """
        del timeout, on_output_line  # unused in simulation
        self.calls.append(action)
        self.call_count += 1

        cmd_type = "slash command" if is_slash_command else "shell command"
        print(f"    [SIMULATED] Would execute ({cmd_type}): {action}")

        if self.scenario:
            exit_code = self._scenario_result()
            scenario_label = {
                "all-pass": "Success (scenario: all-pass)",
                "all-fail": "Failure (scenario: all-fail)",
                "all-error": "Error (scenario: all-error)",
                "first-fail": "Failure" if self.call_count == 1 else "Success",
                "alternating": "Failure" if self.call_count % 2 == 1 else "Success",
            }.get(self.scenario, "Success")
            print(f"    [AUTO] Result: {scenario_label}")
        else:
            exit_code = self._prompt_result()

        return ActionResult(
            output=f"[simulated output for: {action}]",
            stderr="",
            exit_code=exit_code,
            duration_ms=0,
        )

    def _scenario_result(self) -> int:
        """Return exit code based on scenario pattern.

        Returns:
            0 for success, 1 for failure, 2 for error based on scenario logic
        """
        if self.scenario == "all-pass":
            return 0
        elif self.scenario == "all-fail":
            return 1
        elif self.scenario == "all-error":
            return 2
        elif self.scenario == "first-fail":
            # First call fails, rest pass
            return 1 if self.call_count == 1 else 0
        elif self.scenario == "alternating":
            # Odd calls fail, even calls pass
            return 1 if self.call_count % 2 == 1 else 0
        return 0

    def _prompt_result(self) -> int:
        """Prompt user for simulated exit code.

        Returns:
            Exit code based on user selection
        """
        print()
        print("    ? What should the simulated result be?")
        print("      1) Success (exit 0) [default]")
        print("      2) Failure (exit 1)")
        print("      3) Error (exit 2)")

        while True:
            try:
                sys.stdout.write("    > ")
                sys.stdout.flush()
                choice = sys.stdin.readline().strip()
                if choice in ("1", ""):
                    return 0
                elif choice == "2":
                    return 1
                elif choice == "3":
                    return 2
                print("    Invalid choice. Enter 1, 2, or 3.")
            except (EOFError, KeyboardInterrupt):
                print()
                return 0

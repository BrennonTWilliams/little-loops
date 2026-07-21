"""FSM action runner implementations.

Provides the protocol and concrete implementations for action execution:
- ActionRunner: Protocol defining the runner interface
- DefaultActionRunner: Subprocess-based runner for real execution
- SimulationActionRunner: Interactive/scenario-based runner for testing and dry-runs
"""

from __future__ import annotations

import selectors
import subprocess
import sys
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

from little_loops.fsm.host_guard import RssSampler
from little_loops.fsm.types import ActionResult
from little_loops.subprocess_utils import (
    DetailedUsageCallback,
    TokenUsage,
    UsageCallback,
    _kill_process_group,
    run_claude_command,
)


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
        agent: str | None = None,
        tools: list[str] | None = None,
        on_usage: UsageCallback | None = None,
        on_usage_detailed: DetailedUsageCallback | None = None,
        model: str | None = None,
        working_dir: Path | None = None,
        automation_profile: str | None = None,
    ) -> ActionResult:
        """Execute an action and return the result.

        Args:
            action: The command to execute
            timeout: Timeout in seconds
            is_slash_command: True if this is a slash command (starts with /)
            on_output_line: Optional callback invoked for each output line
            agent: Optional agent name to pass as --agent to Claude CLI (prompt-mode only)
            tools: Optional list of tool names to pass as --tools CSV to Claude CLI (prompt-mode only)
            on_usage: Optional callback invoked with (input_tokens, output_tokens) on completion
            on_usage_detailed: Optional callback invoked with a TokenUsage dataclass on completion
            working_dir: Optional cwd for the spawned subprocess (ENH-2609). None
                inherits the parent process's cwd (existing behavior).
            automation_profile: ENH-2714 opt-in automation-context static-prefix
                pruning profile name (prompt-mode only). None preserves full
                unpruned behavior.

        Returns:
            ActionResult with output, stderr, exit_code, duration_ms
        """
        ...


class DefaultActionRunner:
    """Execute actions via subprocess or Claude CLI.

    Attributes:
        sample_rss: When True (set by the executor when the host-guard
            cumulative RSS budget is active, ENH-2453), each spawned
            subprocess's RSS is sampled while it runs and the peak is
            reported via ``ActionResult.peak_rss_mb``.
    """

    def __init__(self, sample_rss: bool = False) -> None:
        """Initialize the runner.

        Args:
            sample_rss: Enable per-subprocess peak-RSS sampling (ENH-2453).
        """
        self._current_process: subprocess.Popen[str] | None = None
        self.sample_rss = sample_rss

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        on_output_line: Callable[[str], None] | None = None,
        agent: str | None = None,
        tools: list[str] | None = None,
        on_usage: UsageCallback | None = None,
        on_usage_detailed: DetailedUsageCallback | None = None,
        model: str | None = None,
        working_dir: Path | None = None,
        automation_profile: str | None = None,
    ) -> ActionResult:
        """Execute action and return result, streaming output line by line.

        Args:
            action: The command to execute
            timeout: Timeout in seconds
            is_slash_command: True if action starts with /
            on_output_line: Optional callback invoked for each stdout line
            agent: Optional agent name to pass as --agent to Claude CLI (prompt-mode only)
            tools: Optional list of tool names to pass as --tools CSV (prompt-mode only)
            on_usage: Optional callback invoked with (input_tokens, output_tokens) on completion
            on_usage_detailed: Optional callback invoked with a TokenUsage dataclass on completion
            model: Optional model override to pass as --model to Claude CLI (prompt-mode only)
            working_dir: Optional cwd for the spawned subprocess (ENH-2609). None
                inherits the parent process's cwd.
            automation_profile: ENH-2714 opt-in automation-context static-prefix
                pruning profile name (prompt-mode only). None preserves full
                unpruned behavior.

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

            samplers: list[RssSampler] = []
            peak_rss: list[float | None] = [None]

            def _on_proc_start(p: subprocess.Popen[str]) -> None:
                self._current_process = p
                if self.sample_rss:
                    sampler = RssSampler(p.pid)
                    sampler.start()
                    samplers.append(sampler)

            def _on_proc_end(p: subprocess.Popen[str]) -> None:
                self._current_process = None
                if samplers:
                    peak_rss[0] = samplers.pop().stop()

            collected_usage: list[TokenUsage] = []

            def _collect_usage(u: TokenUsage) -> None:
                collected_usage.append(u)
                if on_usage_detailed:
                    on_usage_detailed(u)

            try:
                completed = run_claude_command(
                    command=action,
                    timeout=timeout,
                    stream_callback=_stream_cb,
                    on_process_start=_on_proc_start,
                    on_process_end=_on_proc_end,
                    agent=agent,
                    tools=tools,
                    on_usage=on_usage,
                    on_usage_detailed=_collect_usage,
                    model=model,
                    working_dir=working_dir,
                    automation_profile=automation_profile,
                )
            except subprocess.TimeoutExpired:
                return ActionResult(
                    output="",
                    stderr="Action timed out",
                    exit_code=124,
                    duration_ms=timeout * 1000,
                )
            except Exception as exc:
                return ActionResult(
                    output="",
                    stderr=f"Action failed: {exc}",
                    exit_code=1,
                    duration_ms=_now_ms() - start,
                )
            return ActionResult(
                output=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
                duration_ms=_now_ms() - start,
                usage_events=collected_usage,
                peak_rss_mb=peak_rss[0],
            )

        # Shell command — selector-based I/O with wall-clock timeout enforcement.
        # Uses selectors.DefaultSelector to read stdout and stderr concurrently
        # with bounded polling (sel.select(timeout=1.0)), checking the wall-clock
        # deadline before each read. This closes the timeout dead-zone in the old
        # `for line in process.stdout` pattern which blocked indefinitely when a
        # shell process hung before producing any output.
        cmd = ["bash", "-c", action]
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            cwd=working_dir,
        )
        self._current_process = process
        deadline = time.time() + timeout

        # ENH-2453: sample the subprocess's RSS while it runs (budget-gated).
        shell_sampler: RssSampler | None = None
        if self.sample_rss:
            shell_sampler = RssSampler(process.pid)
            shell_sampler.start()

        output_chunks: list[str] = []
        stderr_chunks: list[str] = []

        sel = selectors.DefaultSelector()
        if process.stdout is not None:
            sel.register(process.stdout, selectors.EVENT_READ, data="stdout")
        if process.stderr is not None:
            sel.register(process.stderr, selectors.EVENT_READ, data="stderr")

        timed_out = False
        try:
            while sel.get_map():
                # Bounded poll — never block longer than 1 second
                remaining = deadline - time.time()
                if remaining <= 0:
                    timed_out = True
                    break
                poll_timeout = min(1.0, remaining)
                ready = sel.select(timeout=poll_timeout)
                if not ready:
                    # No pipes ready within poll window — loop re-checks deadline
                    continue
                for key, _mask in ready:
                    line = key.fileobj.readline()  # type: ignore[union-attr]
                    if line:
                        if key.data == "stdout":
                            output_chunks.append(line)
                            if on_output_line:
                                on_output_line(line.rstrip())
                        else:
                            stderr_chunks.append(line)
                    else:
                        # EOF on this pipe — unregister it
                        sel.unregister(key.fileobj)
        finally:
            sel.close()
            self._current_process = None

        shell_peak_rss = shell_sampler.stop() if shell_sampler is not None else None

        if timed_out:
            _kill_process_group(process)
            # Drain any remaining output after the kill
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            return ActionResult(
                output="".join(output_chunks),
                stderr="".join(stderr_chunks) or "Action timed out",
                exit_code=124,
                duration_ms=timeout * 1000,
                peak_rss_mb=shell_peak_rss,
            )

        process.wait(timeout=5)
        return ActionResult(
            output="".join(output_chunks),
            stderr="".join(stderr_chunks),
            exit_code=process.returncode,
            duration_ms=_now_ms() - start,
            peak_rss_mb=shell_peak_rss,
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
        agent: str | None = None,
        tools: list[str] | None = None,
        on_usage: UsageCallback | None = None,
        on_usage_detailed: DetailedUsageCallback | None = None,
        model: str | None = None,
        working_dir: Path | None = None,
        automation_profile: str | None = None,
    ) -> ActionResult:
        """Prompt user for simulated result instead of executing.

        Args:
            action: The command that would be executed
            timeout: Timeout (ignored in simulation)
            is_slash_command: Whether this is a slash command
            on_output_line: Ignored in simulation
            agent: Ignored in simulation
            tools: Ignored in simulation
            on_usage: Ignored in simulation
            on_usage_detailed: Ignored in simulation
            model: Ignored in simulation
            working_dir: Ignored in simulation
            automation_profile: Ignored in simulation

        Returns:
            ActionResult with simulated exit code
        """
        # unused in simulation
        del timeout, on_output_line, agent, tools, on_usage, model, working_dir
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

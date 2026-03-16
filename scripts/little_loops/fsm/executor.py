"""FSM Executor - Runtime engine for FSM loop execution.

This module provides the execution engine that runs FSM loops:
- Executes actions (shell commands or slash commands)
- Evaluates results using appropriate evaluators
- Routes to next states based on verdicts
- Tracks iteration count and enforces limits
- Manages captured variables and context
"""

from __future__ import annotations

import json
import subprocess
import sys
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Protocol

from little_loops.fsm.evaluators import (
    EvaluationResult,
    evaluate,
    evaluate_exit_code,
    evaluate_llm_structured,
    evaluate_mcp_result,
)
from little_loops.fsm.handoff_handler import HandoffHandler
from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    interpolate,
    interpolate_dict,
)
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.fsm.signal_detector import DetectedSignal, SignalDetector
from little_loops.session_log import get_current_session_jsonl


@dataclass
class ExecutionResult:
    """Result from FSM execution.

    Attributes:
        final_state: Name of the state when execution stopped
        iterations: Total iterations executed
        terminated_by: Reason for termination (terminal, max_iterations, timeout, signal, error, handoff)
        duration_ms: Total execution time in milliseconds
        captured: All captured variable values
        error: Error message if terminated_by is "error"
        handoff: True if execution stopped due to handoff signal
        continuation_prompt: Continuation context from handoff signal
    """

    final_state: str
    iterations: int
    terminated_by: str  # "terminal", "max_iterations", "timeout", "signal", "error", "handoff"
    duration_ms: int
    captured: dict[str, dict[str, Any]]
    error: str | None = None
    handoff: bool = False
    continuation_prompt: str | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "final_state": self.final_state,
            "iterations": self.iterations,
            "terminated_by": self.terminated_by,
            "duration_ms": self.duration_ms,
            "captured": self.captured,
        }
        if self.error is not None:
            result["error"] = self.error
        if self.handoff:
            result["handoff"] = self.handoff
        if self.continuation_prompt is not None:
            result["continuation_prompt"] = self.continuation_prompt
        return result


@dataclass
class ActionResult:
    """Result from action execution.

    Attributes:
        output: stdout from the action
        stderr: stderr from the action
        exit_code: Exit code from the action
        duration_ms: Execution time in milliseconds
    """

    output: str
    stderr: str
    exit_code: int
    duration_ms: int


# Type for event callback
EventCallback = Callable[[dict[str, Any]], None]


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
            # Execute via Claude CLI
            cmd = [
                "claude",
                "--dangerously-skip-permissions",
                "--no-session-persistence",
                "-p",
                action,
            ]
        else:
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


def _now_ms() -> int:
    """Get current time in milliseconds."""
    return int(time.time() * 1000)


def _iso_now() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


class FSMExecutor:
    """Execute an FSM loop.

    The executor runs an FSM from its initial state until:
    - A terminal state is reached
    - max_iterations is exceeded
    - A timeout occurs
    - A shutdown signal is received
    - An unrecoverable error occurs

    Events are emitted via the callback for observability.
    """

    def __init__(
        self,
        fsm: FSMLoop,
        event_callback: EventCallback | None = None,
        action_runner: ActionRunner | None = None,
        signal_detector: SignalDetector | None = None,
        handoff_handler: HandoffHandler | None = None,
    ):
        """Initialize the executor.

        Args:
            fsm: The FSM loop to execute
            event_callback: Optional callback for events
            action_runner: Optional custom action runner (for testing)
            signal_detector: Optional signal detector for output parsing
            handoff_handler: Optional handler for handoff signals
        """
        self.fsm = fsm
        self.event_callback = event_callback or (lambda _: None)
        self.action_runner: ActionRunner = action_runner or DefaultActionRunner()
        self.signal_detector = signal_detector
        self.handoff_handler = handoff_handler

        # Runtime state
        self.current_state = fsm.initial
        self.iteration = 0
        self.captured: dict[str, dict[str, Any]] = {}
        self.prev_result: dict[str, Any] | None = None
        self.started_at = ""
        self.start_time_ms = 0
        self.elapsed_offset_ms = (
            0  # milliseconds from segments before current run (set by PersistentExecutor on resume)
        )

        # Shutdown flag for graceful signal handling
        self._shutdown_requested = False

        # Pending handoff signal (set by _run_action, checked by main loop)
        self._pending_handoff: DetectedSignal | None = None

        # Pending error payload from FATAL_ERROR signal (set by _run_action, checked by main loop)
        self._pending_error: str | None = None

        # Per-state retry tracking for max_retries support.
        # _retry_counts[state_name] = number of consecutive re-entries into that state.
        # Incremented each time we enter the same state as the previous iteration.
        # Reset when a different state is entered, or after retry exhaustion.
        self._retry_counts: dict[str, int] = {}
        # State entered in the previous iteration (None on first iteration or after resume).
        self._prev_state: str | None = None

    def request_shutdown(self) -> None:
        """Request graceful shutdown of the executor.

        Sets a flag that will be checked at the start of each iteration,
        allowing the loop to exit cleanly after the current state completes.
        """
        self._shutdown_requested = True

    def run(self) -> ExecutionResult:
        """Execute the FSM until terminal state or limits reached.

        Returns:
            ExecutionResult with final state and execution metadata
        """
        self.started_at = _iso_now()
        self.start_time_ms = _now_ms()

        self._emit("loop_start", {"loop": self.fsm.name})

        try:
            while True:
                # Check shutdown request (signal handling)
                if self._shutdown_requested:
                    return self._finish("signal")

                # Check iteration limit
                if self.iteration >= self.fsm.max_iterations:
                    return self._finish("max_iterations")

                # Check timeout
                if self.fsm.timeout:
                    elapsed = _now_ms() - self.start_time_ms + self.elapsed_offset_ms
                    if elapsed > self.fsm.timeout * 1000:
                        return self._finish("timeout")

                # Get current state config
                state_config = self.fsm.states[self.current_state]

                # Update per-state retry tracking based on transition from previous iteration.
                # If re-entering the same state consecutively, increment retry count.
                # If entering a different state, clear the previous state's retry count.
                if self._prev_state is not None:
                    if self.current_state == self._prev_state:
                        self._retry_counts[self.current_state] = (
                            self._retry_counts.get(self.current_state, 0) + 1
                        )
                    else:
                        self._retry_counts.pop(self._prev_state, None)

                # Check terminal
                if state_config.terminal:
                    # Handle maintain mode - restart loop instead of terminating
                    if self.fsm.maintain:
                        self.iteration += 1
                        maintain_target = state_config.on_maintain or self.fsm.initial
                        self._emit(
                            "route",
                            {
                                "from": self.current_state,
                                "to": maintain_target,
                                "reason": "maintain",
                            },
                        )
                        self._prev_state = self.current_state
                        self.current_state = maintain_target
                        continue
                    return self._finish("terminal")

                # Check per-state retry limit. If the consecutive re-entry count exceeds
                # max_retries, skip execution and route to on_retry_exhausted instead.
                if state_config.max_retries is not None:
                    retry_count = self._retry_counts.get(self.current_state, 0)
                    if retry_count > state_config.max_retries:
                        # on_retry_exhausted is guaranteed non-None by validation when
                        # max_retries is set, but we fall back to an error if misconfigured.
                        exhausted_state: str = state_config.on_retry_exhausted or ""
                        if not exhausted_state:
                            return self._finish(
                                "error",
                                error=f"State '{self.current_state}' exceeded max_retries "
                                "but on_retry_exhausted is not set",
                            )
                        self._emit(
                            "retry_exhausted",
                            {
                                "state": self.current_state,
                                "retries": retry_count,
                                "next": exhausted_state,
                            },
                        )
                        self._retry_counts.pop(self.current_state, None)
                        self._prev_state = self.current_state
                        self.current_state = exhausted_state
                        continue

                self.iteration += 1
                self._emit(
                    "state_enter",
                    {
                        "state": self.current_state,
                        "iteration": self.iteration,
                    },
                )

                # Execute state
                next_state = self._execute_state(state_config)

                # Check for pending error signal (FATAL_ERROR)
                if self._pending_error is not None:
                    return self._finish("error", error=self._pending_error)

                # Check for pending handoff signal
                if self._pending_handoff:
                    return self._handle_handoff(self._pending_handoff)

                # Handle maintain mode
                if next_state is None and self.fsm.maintain:
                    next_state = state_config.on_maintain or self.fsm.initial

                # SIGKILL in _execute_state sets shutdown flag and returns None
                if next_state is None and self._shutdown_requested:
                    return self._finish("signal")

                if next_state is None:
                    return self._finish("error", error="No valid transition")

                # At this point next_state is guaranteed to be str
                resolved_next: str = next_state

                self._emit(
                    "route",
                    {
                        "from": self.current_state,
                        "to": resolved_next,
                    },
                )

                self._prev_state = self.current_state
                self.current_state = resolved_next

                # Interruptible backoff sleep between iterations
                if self.fsm.backoff and self.fsm.backoff > 0:
                    deadline = time.time() + self.fsm.backoff
                    while time.time() < deadline:
                        if self._shutdown_requested:
                            break
                        time.sleep(min(0.1, deadline - time.time()))

        except InterpolationError as exc:
            return self._finish(
                "error",
                error=(
                    f"Missing context variable in state '{self.current_state}': {exc}. "
                    f"Run with: ll-loop run {self.fsm.name} --context KEY=VALUE"
                ),
            )
        except Exception as exc:
            return self._finish("error", error=str(exc))

    def _execute_state(self, state: StateConfig) -> str | None:
        """Execute a single state and return next state name.

        Args:
            state: The state configuration to execute

        Returns:
            Next state name, or None if no valid transition
        """
        # Build interpolation context
        ctx = self._build_context()

        # Handle unconditional transition
        if state.next:
            if state.action:
                result = self._run_action(state.action, state, ctx)
                self.prev_result = {
                    "output": result.output,
                    "exit_code": result.exit_code,
                    "state": self.current_state,
                }
                if result.exit_code is not None and result.exit_code < 0:
                    # Process killed by signal — do not silently advance via next
                    if state.on_error:
                        return interpolate(state.on_error, ctx)
                    self.request_shutdown()
                    return None
            return interpolate(state.next, ctx)

        # Execute action if present
        action_result = None
        if state.action:
            action_result = self._run_action(state.action, state, ctx)

        # Evaluate
        eval_result = self._evaluate(state, action_result, ctx)
        self.prev_result = {
            "output": action_result.output if action_result else "",
            "exit_code": action_result.exit_code if action_result else 0,
            "state": self.current_state,
        }

        # Update context with result for routing interpolation
        if eval_result:
            ctx.result = {
                "verdict": eval_result.verdict,
                "details": eval_result.details,
            }

        # Route based on verdict
        verdict = eval_result.verdict if eval_result else "yes"
        return self._route(state, verdict, ctx)

    def _run_action(
        self,
        action_template: str,
        state: StateConfig,
        ctx: InterpolationContext,
    ) -> ActionResult:
        """Execute action and optionally capture result.

        Args:
            action_template: Action string (may contain variables)
            state: State configuration
            ctx: Interpolation context

        Returns:
            ActionResult with output and exit code
        """
        action = interpolate(action_template, ctx)
        action_mode = self._action_mode(state)

        self._emit("action_start", {"action": action, "is_prompt": action_mode == "prompt"})

        def _on_line(line: str) -> None:
            self._emit("action_output", {"line": line})

        if action_mode == "mcp_tool":
            # Direct MCP tool call — bypass action_runner entirely
            interpolated_params = interpolate_dict(state.params, ctx) if state.params else {}
            cmd = ["mcp-call", action, json.dumps(interpolated_params)]
            result = self._run_subprocess(
                cmd,
                timeout=state.timeout or self.fsm.default_timeout or 30,
                on_output_line=_on_line,
            )
        else:
            result = self.action_runner.run(
                action,
                timeout=state.timeout or self.fsm.default_timeout or 3600,
                is_slash_command=action_mode == "prompt",
                on_output_line=_on_line,
            )

        preview = result.output[-2000:].strip() if result.output else None
        payload: dict[str, Any] = {
            "exit_code": result.exit_code,
            "duration_ms": result.duration_ms,
            "output_preview": preview,
            "is_prompt": action_mode == "prompt",
        }
        if action_mode == "prompt":
            session_jsonl = get_current_session_jsonl()
            payload["session_jsonl"] = str(session_jsonl) if session_jsonl else None
        self._emit("action_complete", payload)

        # Capture if requested
        if state.capture:
            self.captured[state.capture] = {
                "output": result.output,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            }

        # Check for signals in output
        if self.signal_detector:
            signal = self.signal_detector.detect_first(result.output)
            if signal:
                if signal.signal_type == "handoff":
                    self._pending_handoff = signal
                elif signal.signal_type == "error":
                    self._pending_error = signal.payload
                elif signal.signal_type == "stop":
                    self.request_shutdown()

        return result

    def _run_subprocess(
        self,
        cmd: list[str],
        timeout: int,
        on_output_line: Any | None = None,
    ) -> ActionResult:
        """Run a subprocess directly and return ActionResult.

        Follows the same Popen + stderr-drain-thread pattern as DefaultActionRunner.

        Args:
            cmd: Command and arguments to execute
            timeout: Timeout in seconds
            on_output_line: Optional callback for each stdout line

        Returns:
            ActionResult with output, stderr, exit_code, duration_ms
        """
        start = _now_ms()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
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
                stderr="".join(stderr_chunks) or "MCP call timed out",
                exit_code=124,
                duration_ms=timeout * 1000,
            )
        finally:
            pass
        stderr_thread.join(timeout=5)
        return ActionResult(
            output="".join(output_chunks),
            stderr="".join(stderr_chunks),
            exit_code=process.returncode,
            duration_ms=_now_ms() - start,
        )

    def _evaluate(
        self,
        state: StateConfig,
        action_result: ActionResult | None,
        ctx: InterpolationContext,
    ) -> EvaluationResult | None:
        """Evaluate action result.

        Args:
            state: State configuration
            action_result: Result from action execution (may be None)
            ctx: Interpolation context

        Returns:
            EvaluationResult, or None if no evaluation needed
        """
        if state.evaluate is None:
            # Default evaluation based on action type
            if action_result:
                action_mode = self._action_mode(state)

                if action_mode == "mcp_tool":
                    # MCP tool call: use mcp_result evaluator
                    result = evaluate_mcp_result(action_result.output, action_result.exit_code)
                elif action_mode == "prompt":
                    # Slash command or prompt: use LLM evaluation
                    if not self.fsm.llm.enabled:
                        result = EvaluationResult(
                            verdict="error",
                            details={"error": "LLM evaluation disabled via --no-llm"},
                        )
                    else:
                        result = evaluate_llm_structured(
                            action_result.output,
                            model=self.fsm.llm.model,
                            max_tokens=self.fsm.llm.max_tokens,
                            timeout=self.fsm.llm.timeout,
                        )
                else:
                    # Shell command: use exit code
                    result = evaluate_exit_code(action_result.exit_code)

                self._emit(
                    "evaluate",
                    {
                        "type": "default",
                        "verdict": result.verdict,
                        **result.details,
                    },
                )
                return result
            return None

        # Explicit evaluation config
        raw_output = action_result.output if action_result else ""
        if state.evaluate.source:
            try:
                eval_input = interpolate(state.evaluate.source, ctx)
            except InterpolationError:
                eval_input = raw_output
        else:
            eval_input = raw_output

        if state.evaluate.type == "llm_structured" and not self.fsm.llm.enabled:
            result = EvaluationResult(
                verdict="error",
                details={"error": "LLM evaluation disabled via --no-llm"},
            )
        else:
            result = evaluate(
                config=state.evaluate,
                output=eval_input,
                exit_code=action_result.exit_code if action_result else 0,
                context=ctx,
            )

        self._emit(
            "evaluate",
            {
                "type": state.evaluate.type,
                "verdict": result.verdict,
                **result.details,
            },
        )

        return result

    def _route(
        self,
        state: StateConfig,
        verdict: str,
        ctx: InterpolationContext,
    ) -> str | None:
        """Determine next state from verdict.

        Resolution order (from design doc):
        1. next (unconditional) - handled before this method
        2. route (full routing table)
        3. on_success/on_failure/on_error (shorthand)
        4. terminal - handled in main loop
        5. error

        Args:
            state: State configuration
            verdict: Verdict string from evaluation
            ctx: Interpolation context

        Returns:
            Next state name, or None if no valid route
        """
        if state.route:
            routes = state.route.routes
            if verdict in routes:
                return self._resolve_route(routes[verdict], ctx)
            if state.route.default:
                return self._resolve_route(state.route.default, ctx)
            if verdict == "error" and state.route.error:
                return self._resolve_route(state.route.error, ctx)
            return None

        # Shorthand routing
        if verdict == "yes" and state.on_yes:
            return self._resolve_route(state.on_yes, ctx)
        if verdict == "no" and state.on_no:
            return self._resolve_route(state.on_no, ctx)
        if verdict == "error" and state.on_error:
            return self._resolve_route(state.on_error, ctx)
        if verdict == "partial" and state.on_partial:
            return self._resolve_route(state.on_partial, ctx)
        if verdict == "blocked" and state.on_blocked:
            return self._resolve_route(state.on_blocked, ctx)

        return None

    def _resolve_route(self, route: str, ctx: InterpolationContext) -> str:
        """Resolve route target, handling special tokens.

        Args:
            route: Route target string
            ctx: Interpolation context

        Returns:
            Resolved state name
        """
        if route == "$current":
            return self.current_state
        return interpolate(route, ctx)

    def _action_mode(self, state: StateConfig) -> str:
        """Return execution mode for the state: 'prompt', 'shell', or 'mcp_tool'."""
        if state.action_type == "mcp_tool":
            return "mcp_tool"
        if state.action_type in ("prompt", "slash_command"):
            return "prompt"
        if state.action_type == "shell":
            return "shell"
        # Heuristic: / prefix = slash_command (prompt mode)
        if state.action is not None and state.action.startswith("/"):
            return "prompt"
        return "shell"

    def _build_context(self) -> InterpolationContext:
        """Build interpolation context for current state.

        Returns:
            InterpolationContext with all runtime values
        """
        return InterpolationContext(
            context=self.fsm.context,
            captured=self.captured,
            prev=self.prev_result,
            result=None,
            state_name=self.current_state,
            iteration=self.iteration,
            loop_name=self.fsm.name,
            started_at=self.started_at,
            elapsed_ms=_now_ms() - self.start_time_ms + self.elapsed_offset_ms,
        )

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        """Emit an event via the callback."""
        self.event_callback(
            {
                "event": event,
                "ts": _iso_now(),
                **data,
            }
        )

    def _finish(self, terminated_by: str, error: str | None = None) -> ExecutionResult:
        """Finalize execution and return result."""
        self._emit(
            "loop_complete",
            {
                "final_state": self.current_state,
                "iterations": self.iteration,
                "terminated_by": terminated_by,
            },
        )

        return ExecutionResult(
            final_state=self.current_state,
            iterations=self.iteration,
            terminated_by=terminated_by,
            duration_ms=_now_ms() - self.start_time_ms + self.elapsed_offset_ms,
            captured=self.captured,
            error=error,
        )

    def _handle_handoff(self, signal: DetectedSignal) -> ExecutionResult:
        """Handle a detected handoff signal.

        Emits a handoff_detected event and optionally invokes the handoff handler.

        Args:
            signal: The detected handoff signal

        Returns:
            ExecutionResult with handoff information
        """
        self._emit(
            "handoff_detected",
            {
                "state": self.current_state,
                "iteration": self.iteration,
                "continuation": signal.payload,
            },
        )

        # Invoke handler if configured
        if self.handoff_handler:
            result = self.handoff_handler.handle(self.fsm.name, signal.payload)
            if result.spawned_process is not None:
                self._emit(
                    "handoff_spawned",
                    {
                        "pid": result.spawned_process.pid,
                        "state": self.current_state,
                    },
                )

        return ExecutionResult(
            final_state=self.current_state,
            iterations=self.iteration,
            terminated_by="handoff",
            duration_ms=_now_ms() - self.start_time_ms + self.elapsed_offset_ms,
            captured=self.captured,
            handoff=True,
            continuation_prompt=signal.payload,
        )

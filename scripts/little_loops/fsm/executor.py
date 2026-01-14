"""FSM Executor - Runtime engine for FSM loop execution.

This module provides the execution engine that runs FSM loops:
- Executes actions (shell commands or slash commands)
- Evaluates results using appropriate evaluators
- Routes to next states based on verdicts
- Tracks iteration count and enforces limits
- Manages captured variables and context
"""

from __future__ import annotations

import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from little_loops.fsm.evaluators import (
    EvaluationResult,
    evaluate,
    evaluate_exit_code,
    evaluate_llm_structured,
)
from little_loops.fsm.interpolation import InterpolationContext, interpolate
from little_loops.fsm.schema import FSMLoop, StateConfig


@dataclass
class ExecutionResult:
    """Result from FSM execution.

    Attributes:
        final_state: Name of the state when execution stopped
        iterations: Total iterations executed
        terminated_by: Reason for termination (terminal, max_iterations, timeout, error)
        duration_ms: Total execution time in milliseconds
        captured: All captured variable values
        error: Error message if terminated_by is "error"
    """

    final_state: str
    iterations: int
    terminated_by: str  # "terminal", "max_iterations", "timeout", "error"
    duration_ms: int
    captured: dict[str, dict[str, Any]]
    error: str | None = None

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
    ) -> ActionResult:
        """Execute an action and return the result.

        Args:
            action: The command to execute
            timeout: Timeout in seconds
            is_slash_command: True if this is a slash command (starts with /)

        Returns:
            ActionResult with output, stderr, exit_code, duration_ms
        """
        ...


class DefaultActionRunner:
    """Execute actions via subprocess or Claude CLI."""

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
    ) -> ActionResult:
        """Execute action and return result.

        Args:
            action: The command to execute
            timeout: Timeout in seconds
            is_slash_command: True if action starts with /

        Returns:
            ActionResult with execution details
        """
        start = _now_ms()

        if is_slash_command:
            # Execute via Claude CLI
            cmd = [
                "claude",
                "--dangerously-skip-permissions",
                "-p",
                action,
            ]
        else:
            # Shell command
            cmd = ["bash", "-c", action]

        try:
            result = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                timeout=timeout,
            )
            return ActionResult(
                output=result.stdout,
                stderr=result.stderr,
                exit_code=result.returncode,
                duration_ms=_now_ms() - start,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                output="",
                stderr="Action timed out",
                exit_code=124,  # Standard timeout exit code
                duration_ms=timeout * 1000,
            )


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
    - An unrecoverable error occurs

    Events are emitted via the callback for observability.
    """

    def __init__(
        self,
        fsm: FSMLoop,
        event_callback: EventCallback | None = None,
        action_runner: ActionRunner | None = None,
    ):
        """Initialize the executor.

        Args:
            fsm: The FSM loop to execute
            event_callback: Optional callback for events
            action_runner: Optional custom action runner (for testing)
        """
        self.fsm = fsm
        self.event_callback = event_callback or (lambda e: None)
        self.action_runner: ActionRunner = action_runner or DefaultActionRunner()

        # Runtime state
        self.current_state = fsm.initial
        self.iteration = 0
        self.captured: dict[str, dict[str, Any]] = {}
        self.prev_result: dict[str, Any] | None = None
        self.started_at = ""
        self.start_time_ms = 0

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
                # Check iteration limit
                if self.iteration >= self.fsm.max_iterations:
                    return self._finish("max_iterations")

                # Check timeout
                if self.fsm.timeout:
                    elapsed = _now_ms() - self.start_time_ms
                    if elapsed > self.fsm.timeout * 1000:
                        return self._finish("timeout")

                # Get current state config
                state_config = self.fsm.states[self.current_state]

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
                        self.current_state = maintain_target
                        continue
                    return self._finish("terminal")

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

                # Handle maintain mode
                if next_state is None and self.fsm.maintain:
                    next_state = state_config.on_maintain or self.fsm.initial

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

                self.current_state = resolved_next

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
                self._run_action(state.action, state, ctx)
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
        verdict = eval_result.verdict if eval_result else "success"
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

        self._emit("action_start", {"action": action})

        result = self.action_runner.run(
            action,
            timeout=state.timeout or 120,
            is_slash_command=action.startswith("/"),
        )

        self._emit(
            "action_complete",
            {
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            },
        )

        # Capture if requested
        if state.capture:
            self.captured[state.capture] = {
                "output": result.output,
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            }

        return result

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
                if state.action and state.action.startswith("/"):
                    # Slash command: use LLM evaluation
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
                    },
                )
                return result
            return None

        # Explicit evaluation config
        result = evaluate(
            config=state.evaluate,
            output=action_result.output if action_result else "",
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
        if verdict == "success" and state.on_success:
            return self._resolve_route(state.on_success, ctx)
        if verdict == "failure" and state.on_failure:
            return self._resolve_route(state.on_failure, ctx)
        if verdict == "error" and state.on_error:
            return self._resolve_route(state.on_error, ctx)

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
            elapsed_ms=_now_ms() - self.start_time_ms,
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

    def _finish(
        self, terminated_by: str, error: str | None = None
    ) -> ExecutionResult:
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
            duration_ms=_now_ms() - self.start_time_ms,
            captured=self.captured,
            error=error,
        )

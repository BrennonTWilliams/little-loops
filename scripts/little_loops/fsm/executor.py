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
import random
import subprocess
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

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
from little_loops.fsm.rate_limit_circuit import RateLimitCircuit
from little_loops.fsm.runners import (
    ActionRunner,
    DefaultActionRunner,
    SimulationActionRunner,  # noqa: F401 — re-exported for backward compatibility
    _now_ms,
)
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.fsm.signal_detector import DetectedSignal, SignalDetector
from little_loops.fsm.types import ActionResult, Evaluator, EventCallback, ExecutionResult
from little_loops.issue_lifecycle import FailureType, classify_failure
from little_loops.session_log import get_current_session_jsonl

# Maximum number of per-state rate-limit retries before emitting rate_limit_exhausted.
_DEFAULT_RATE_LIMIT_RETRIES: int = 3
# Base backoff in seconds; actual sleep = base * 2^(attempt-1) + uniform(0, base).
_DEFAULT_RATE_LIMIT_BACKOFF_BASE: int = 30
# Total wall-clock budget (seconds) across short + long tiers before routing to
# on_rate_limit_exhausted. Mirrors RateLimitsConfig.max_wait_seconds default (6h).
_DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS: int = 21600
# Long-wait tier ladder (seconds), walked once the short-tier budget is spent.
# Mirrors RateLimitsConfig.long_wait_ladder default.
_DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER: list[int] = [300, 900, 1800, 3600]
# Event name emitted when rate-limit retries are exhausted.
RATE_LIMIT_EXHAUSTED_EVENT: str = "rate_limit_exhausted"
# Event name emitted when consecutive rate-limit exhaustions reach the storm threshold.
RATE_LIMIT_STORM_EVENT: str = "rate_limit_storm"
# Event name emitted every ~60s during a long-wait rate-limit sleep so UIs can show live progress.
RATE_LIMIT_WAITING_EVENT: str = "rate_limit_waiting"
# Interval (seconds) between rate_limit_waiting heartbeat emissions during long-wait sleeps.
_RATE_LIMIT_HEARTBEAT_INTERVAL: float = 60.0
# Number of consecutive rate_limit_exhausted events that constitute a storm.
_RATE_LIMIT_STORM_THRESHOLD: int = 3
# Action types that consume LLM quota and are gated by the shared circuit breaker.
# `_action_mode()` collapses both to "prompt"; the frozenset documents intent.
LLM_ACTION_TYPES: frozenset[str] = frozenset({"slash_command", "prompt"})


def _iso_now() -> str:
    """Get current time as ISO 8601 string."""
    return datetime.now(UTC).isoformat()


@dataclass
class RouteContext:
    """Context passed to before_route / after_route interceptors."""

    state_name: str
    state: StateConfig
    verdict: str
    action_result: ActionResult | None
    eval_result: EvaluationResult | None
    ctx: InterpolationContext
    iteration: int


@dataclass
class RouteDecision:
    """Returned by before_route to redirect or veto a routing transition.

    Return semantics for before_route:
      None (implicit)         → passthrough, routing proceeds normally
      RouteDecision("state")  → redirect, bypass _route() and use "state" directly
      RouteDecision(None)     → veto, _execute_state() returns None → _finish("error")
    """

    next_state: str | None  # str → redirect; None → veto


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
        loops_dir: Path | None = None,
        circuit: RateLimitCircuit | None = None,
    ):
        """Initialize the executor.

        Args:
            fsm: The FSM loop to execute
            event_callback: Optional callback for events
            action_runner: Optional custom action runner (for testing)
            signal_detector: Optional signal detector for output parsing
            handoff_handler: Optional handler for handoff signals
            loops_dir: Base directory for resolving sub-loop references
            circuit: Optional shared rate-limit circuit breaker for 429 coordination
        """
        self.fsm = fsm
        self.event_callback = event_callback or (lambda _: None)
        self.action_runner: ActionRunner = action_runner or DefaultActionRunner()
        self.signal_detector = signal_detector
        self.handoff_handler = handoff_handler
        self.loops_dir = loops_dir
        self._circuit = circuit

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

        # Currently running MCP subprocess (set by _run_subprocess, cleared in finally).
        # Enables external shutdown code to kill the process on SIGTERM.
        self._current_process: subprocess.Popen[str] | None = None

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

        # Per-state rate-limit retry tracking (parallel to _retry_counts).
        # _rate_limit_retries[state_name] = dict-of-record:
        #   {
        #       "short_retries": int,       # attempts in short-burst tier
        #       "long_retries": int,        # attempts in long-wait tier
        #       "total_wait_seconds": float,
        #       "first_seen_at": float | None,  # epoch timestamp of first 429
        #   }
        # Incremented inside _handle_rate_limit on each detected rate-limit response.
        # Reset when the state completes without a rate-limit, or after exhaustion.
        self._rate_limit_retries: dict[str, dict[str, Any]] = {}

        # Consecutive rate_limit_exhausted emissions across all states. Reset on any
        # successful non-rate-limited state transition. When this reaches
        # _RATE_LIMIT_STORM_THRESHOLD, a RATE_LIMIT_STORM event is emitted.
        self._consecutive_rate_limit_exhaustions: int = 0

        # Nesting depth for sub-loop event forwarding (0 = top-level, 1+ = sub-loop).
        # Set by the parent executor when constructing child executors.
        self._depth: int = 0

        # Extension hook registries — populated by wire_extensions()
        self._contributed_actions: dict[str, ActionRunner] = {}
        self._contributed_evaluators: dict[str, Evaluator] = {}
        self._interceptors: list[Any] = []

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

    def _execute_sub_loop(self, state: StateConfig, ctx: InterpolationContext) -> str | None:
        """Execute a sub-loop state by loading and running a child FSM.

        Args:
            state: The state configuration with loop field set
            ctx: Interpolation context for routing

        Returns:
            Next state name based on child loop verdict, or None
        """
        from little_loops.cli.loop._helpers import resolve_loop_path
        from little_loops.fsm.validation import load_and_validate

        assert state.loop is not None  # guarded by caller
        loop_path = resolve_loop_path(state.loop, self.loops_dir or Path(".loops"))
        child_fsm, _ = load_and_validate(loop_path)

        # Pass parent context to child if requested
        if state.context_passthrough:
            # Extract .output strings from capture result dicts so ${context.key} resolves
            # to the plain output string (e.g. "ENH-123") rather than the full capture object.
            captured_as_context = {
                k: v["output"] if isinstance(v, dict) and "exit_code" in v else v
                for k, v in self.captured.items()
            }
            child_fsm.context = {**self.fsm.context, **captured_as_context, **child_fsm.context}

        depth = self._depth + 1

        def _sub_event_callback(event: dict) -> None:
            # Only inject depth if not already set by a deeper nested sub-loop
            if "depth" not in event:
                self.event_callback({**event, "depth": depth})
            else:
                self.event_callback(event)

        child_executor = FSMExecutor(
            child_fsm,
            action_runner=self.action_runner,
            loops_dir=self.loops_dir,
            event_callback=_sub_event_callback,
            circuit=self._circuit,
        )
        child_executor._depth = depth  # propagate depth for further nesting
        child_result = child_executor.run()

        # Merge child captures back into parent under the state name
        if state.context_passthrough and child_executor.captured:
            self.captured[self.current_state] = child_executor.captured

        # Route based on child termination reason and terminal state name
        if child_result.terminated_by == "terminal":
            if child_result.final_state == "done":
                return interpolate(state.on_yes, ctx) if state.on_yes else None
            else:
                # Reached a non-done terminal (e.g. "failed") → failure
                return interpolate(state.on_no, ctx) if state.on_no else None
        elif child_result.terminated_by == "error":
            # Runtime child failure (not a YAML load error)
            if state.on_error:
                return interpolate(state.on_error, ctx)
            return interpolate(state.on_no, ctx) if state.on_no else None
        else:
            # max_iterations, timeout, signal — all are failure
            return interpolate(state.on_no, ctx) if state.on_no else None

    def _execute_state(self, state: StateConfig) -> str | None:
        """Execute a single state and return next state name.

        Args:
            state: The state configuration to execute

        Returns:
            Next state name, or None if no valid transition
        """
        # Build interpolation context
        ctx = self._build_context()

        # Dispatch to sub-loop handler if this is a sub-loop state
        if state.loop is not None:
            try:
                return self._execute_sub_loop(state, ctx)
            except (FileNotFoundError, ValueError):
                if state.on_error:
                    return interpolate(state.on_error, ctx)
                raise

        # Handle unconditional transition
        if state.next:
            if state.action:
                self._maybe_wait_for_circuit(state)
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
                # Non-zero exit: if on_error is defined, treat next as success path only
                if result.exit_code != 0 and state.on_error:
                    return interpolate(state.on_error, ctx)
            return interpolate(state.next, ctx)

        # Execute action if present
        action_result = None
        if state.action:
            self._maybe_wait_for_circuit(state)
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
        route_ctx = RouteContext(
            state_name=self.current_state,
            state=state,
            verdict=verdict,
            action_result=action_result,
            eval_result=eval_result,
            ctx=ctx,
            iteration=self.iteration,
        )
        # 429 / rate-limit detection — runs before interceptors so an in-place retry
        # returns early without dispatching to registered before_route hooks.
        if action_result is not None:
            _combined = (action_result.output or "") + "\n" + (action_result.stderr or "")
            _failure_type, _reason = classify_failure(_combined, action_result.exit_code)
            if _failure_type == FailureType.TRANSIENT and (
                "rate limit" in _reason.lower() or "quota" in _reason.lower()
            ):
                _handled, _target = self._handle_rate_limit(state, route_ctx.state_name)
                if _handled:
                    return _target
            else:
                # Not rate-limited: reset counter so future 429s start from zero.
                self._rate_limit_retries.pop(route_ctx.state_name, None)
                # Successful non-rate-limited outcome resets the storm counter.
                self._consecutive_rate_limit_exhaustions = 0

        for interceptor in self._interceptors:
            if hasattr(interceptor, "before_route"):
                decision = interceptor.before_route(route_ctx)
                if isinstance(decision, RouteDecision):
                    if decision.next_state is None:
                        return None  # veto
                    return decision.next_state  # redirect — bypass _route()
        next_state = self._route(state, verdict, ctx)
        for interceptor in self._interceptors:
            if hasattr(interceptor, "after_route"):
                interceptor.after_route(route_ctx)
        return next_state

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
        elif action_mode == "contributed":
            assert (
                state.action_type is not None
            )  # guaranteed by _action_mode returning "contributed"
            runner = self._contributed_actions[state.action_type]
            result = runner.run(
                action,
                timeout=state.timeout or self.fsm.default_timeout or 3600,
                is_slash_command=False,
                on_output_line=_on_line,
            )
        else:
            result = self.action_runner.run(
                action,
                timeout=state.timeout or self.fsm.default_timeout or 3600,
                is_slash_command=action_mode == "prompt",
                on_output_line=_on_line,
                agent=state.agent if action_mode == "prompt" else None,
                tools=state.tools if action_mode == "prompt" else None,
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
                "output": result.output.rstrip("\n\r"),
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
                stderr="".join(stderr_chunks) or "MCP call timed out",
                exit_code=124,
                duration_ms=timeout * 1000,
            )
        finally:
            self._current_process = None
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

        if state.evaluate.type in self._contributed_evaluators:
            result = self._contributed_evaluators[state.evaluate.type](
                state.evaluate,
                eval_input,
                action_result.exit_code if action_result else 0,
                ctx,
            )
        elif state.evaluate.type == "llm_structured" and not self.fsm.llm.enabled:
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

        # Dynamic on_<verdict> shorthands from extra_routes
        if verdict in state.extra_routes:
            return self._resolve_route(state.extra_routes[verdict], ctx)

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
        if state.action_type in self._contributed_actions:
            return "contributed"
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

    def _handle_rate_limit(
        self, state: StateConfig, state_name: str
    ) -> tuple[bool, str | None]:
        """Handle a detected 429/rate-limit action outcome.

        Implements the two-tier retry ladder:
        1. Short-burst tier: up to ``max_rate_limit_retries`` attempts with
           exponential backoff (``rate_limit_backoff_base_seconds * 2^n + jitter``).
        2. Long-wait tier: walks ``rate_limit_long_wait_ladder`` with index capped
           at the last entry, accumulating ``total_wait_seconds``.

        Routes to ``on_rate_limit_exhausted`` (falling back to ``on_error``) only
        once ``total_wait_seconds >= rate_limit_max_wait_seconds``. Emits
        ``rate_limit_exhausted`` on routing (including tier counters) and
        ``rate_limit_storm`` when consecutive exhaustions reach the threshold.

        Returns:
            (handled, target). ``handled=True`` means the caller should return
            ``target`` directly (in-place retry uses ``state_name``; exhaustion
            uses the routed target). ``handled=False`` should not occur for the
            current rate-limit classification path but is reserved for future
            extensions.
        """
        _short_max = (
            state.max_rate_limit_retries
            if state.max_rate_limit_retries is not None
            else _DEFAULT_RATE_LIMIT_RETRIES
        )
        _backoff_base = (
            state.rate_limit_backoff_base_seconds
            if state.rate_limit_backoff_base_seconds is not None
            else _DEFAULT_RATE_LIMIT_BACKOFF_BASE
        )
        _max_wait = (
            state.rate_limit_max_wait_seconds
            if state.rate_limit_max_wait_seconds is not None
            else _DEFAULT_RATE_LIMIT_MAX_WAIT_SECONDS
        )
        _ladder = (
            state.rate_limit_long_wait_ladder
            if state.rate_limit_long_wait_ladder is not None
            else _DEFAULT_RATE_LIMIT_LONG_WAIT_LADDER
        )

        record = self._rate_limit_retries.get(state_name)
        if record is None:
            record = {
                "short_retries": 0,
                "long_retries": 0,
                "total_wait_seconds": 0.0,
                "first_seen_at": time.time(),
            }
            self._rate_limit_retries[state_name] = record

        short_retries = int(record.get("short_retries", 0))
        long_retries = int(record.get("long_retries", 0))
        total_wait = float(record.get("total_wait_seconds", 0.0))

        if short_retries < _short_max:
            # Short-burst tier — exponential backoff with jitter. Budget is not
            # checked here; short-tier always advances to long-wait on exhaustion.
            short_retries += 1
            record["short_retries"] = short_retries
            _sleep = _backoff_base * (2 ** (short_retries - 1)) + random.uniform(
                0, _backoff_base
            )
            if self._circuit is not None:
                self._circuit.record_rate_limit(_sleep)
            total_wait += self._interruptible_sleep(_sleep)
            record["total_wait_seconds"] = total_wait
            return True, state_name  # retry in place

        # Long-wait tier — walk ladder with capped index.
        long_retries += 1
        record["long_retries"] = long_retries
        _idx = min(long_retries - 1, len(_ladder) - 1)
        _wait = float(_ladder[_idx])
        if self._circuit is not None:
            self._circuit.record_rate_limit(_wait)
        _tier_start = time.time()
        _deadline = _tier_start + _wait
        _total_wait_before_tier = total_wait
        total_wait += self._interruptible_sleep(
            _wait,
            on_heartbeat=lambda elapsed: self._emit(
                RATE_LIMIT_WAITING_EVENT,
                {
                    "state": state_name,
                    "elapsed_seconds": elapsed,
                    "next_attempt_at": _deadline,
                    "total_waited_seconds": _total_wait_before_tier + elapsed,
                    "budget_seconds": _max_wait,
                    "tier": "long_wait",
                },
            ),
        )
        record["total_wait_seconds"] = total_wait
        if total_wait >= _max_wait:
            return True, self._exhaust_rate_limit(state, state_name, record)
        return True, state_name  # retry in place

    def _maybe_wait_for_circuit(self, state: StateConfig) -> None:
        """Pre-action circuit-breaker check: sleep until shared 429 recovery.

        Skips quietly when no circuit is injected, when the state's action is not
        an LLM-quota consumer, or when the circuit has no active recovery window.
        """
        if self._circuit is None:
            return
        if self._action_mode(state) != "prompt":
            return
        recovery = self._circuit.get_estimated_recovery()
        if recovery is None:
            return
        wait = recovery - time.time()
        if wait > 0:
            self._interruptible_sleep(wait)

    def _interruptible_sleep(
        self,
        duration: float,
        on_heartbeat: Callable[[float], None] | None = None,
    ) -> float:
        """Sleep for up to ``duration`` seconds in 100ms ticks, exiting promptly
        on ``_shutdown_requested``. Returns the actual elapsed seconds so callers
        can accumulate wall-clock time spent in rate-limit waits.

        If ``on_heartbeat`` is provided, it is invoked with the elapsed seconds
        roughly every ``_RATE_LIMIT_HEARTBEAT_INTERVAL`` seconds so UIs can show
        live progress during long waits. The short-tier call site intentionally
        omits the callback to preserve backward-compatible silent behavior.
        """
        if duration <= 0:
            return 0.0
        _start = time.time()
        _deadline = _start + duration
        last_heartbeat = _start
        while time.time() < _deadline:
            if self._shutdown_requested:
                break
            time.sleep(min(0.1, _deadline - time.time()))
            if on_heartbeat is not None:
                _now = time.time()
                if _now - last_heartbeat >= _RATE_LIMIT_HEARTBEAT_INTERVAL:
                    on_heartbeat(_now - _start)
                    last_heartbeat = _now
        return time.time() - _start

    def _exhaust_rate_limit(
        self, state: StateConfig, state_name: str, record: dict[str, Any]
    ) -> str | None:
        """Finalize rate-limit exhaustion: emit event, storm detection, and
        return the routed target. Pops the per-state record and is called only
        once the wall-clock budget is spent.
        """
        self._rate_limit_retries.pop(state_name, None)
        target = state.on_rate_limit_exhausted or state.on_error
        self._emit(
            RATE_LIMIT_EXHAUSTED_EVENT,
            {
                "state": state_name,
                "retries": int(record.get("short_retries", 0))
                + int(record.get("long_retries", 0)),
                "short_retries": int(record.get("short_retries", 0)),
                "long_retries": int(record.get("long_retries", 0)),
                "total_wait_seconds": float(record.get("total_wait_seconds", 0.0)),
                "next": target,
            },
        )
        self._consecutive_rate_limit_exhaustions += 1
        if self._consecutive_rate_limit_exhaustions >= _RATE_LIMIT_STORM_THRESHOLD:
            self._emit(
                RATE_LIMIT_STORM_EVENT,
                {
                    "state": state_name,
                    "count": self._consecutive_rate_limit_exhaustions,
                },
            )
        return target

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

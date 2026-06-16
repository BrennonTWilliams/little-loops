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
import selectors
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from little_loops.fsm.evaluators import (
    EvaluationResult,
    evaluate,
    evaluate_blind_comparator,
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
from little_loops.fsm.stall_detector import Stall, StallDetector
from little_loops.fsm.types import ActionResult, Evaluator, EventCallback, ExecutionResult
from little_loops.issue_lifecycle import FailureType, classify_failure
from little_loops.session_log import get_current_session_jsonl
from little_loops.subprocess_utils import (
    UsageCallback,
    _kill_process_group,
    run_claude_command,
)

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
# Event name emitted when the stall detector fires on N consecutive
# identical (state, exit_code, verdict) transitions. See FEAT-1637.
STALL_DETECTED_EVENT: str = "stall_detected"
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
# Progressive throttle defaults: calls 1..normal_max pass through, at warn_max emit warning,
# at hard_max route to on_throttle_hard, beyond hard_max hard-stop.
_DEFAULT_THROTTLE_NORMAL_MAX: int = 3
_DEFAULT_THROTTLE_WARN_MAX: int = 8
_DEFAULT_THROTTLE_HARD_MAX: int = 12
# Event names for progressive tool-call throttling within a single state visit.
THROTTLE_WARN_EVENT: str = "throttle_warn"
THROTTLE_HARD_EVENT: str = "throttle_hard"
THROTTLE_STOP_EVENT: str = "throttle_stop"
# Action types that consume LLM quota and are gated by the shared circuit breaker.
# `_action_mode()` collapses both to "prompt"; the frozenset documents intent.
LLM_ACTION_TYPES: frozenset[str] = frozenset({"slash_command", "prompt"})
# Maximum per-state API server error retries before falling through to normal routing.
_DEFAULT_API_ERROR_RETRIES: int = 2
# Flat backoff in seconds between API server error retries (no exponential ladder).
_DEFAULT_API_ERROR_BACKOFF: int = 30


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
        self.messages: list[str] = []
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

        # BUG-1226 / BUG-158: true between emitting a `route` event and
        # entering the target state. Gates the "flush one pending state on
        # timeout / max_iterations" behavior so we only flush when there is
        # actually a pending state.
        self._just_routed: bool = False

        # ENH-1631 / BUG-158: true once the on_max_iterations summary state
        # has been dispatched. Prevents the cap guard from re-triggering
        # before the summary state completes. Also gates the terminal-check
        # short-circuit so the handler executes at least once before
        # terminating (BUG-158 dual-bug fix).
        self._summary_state_executed: bool = False

        # FEAT-1822: Per-item A/B comparison results accumulated during baseline
        # execution. Populated by _execute_with_baseline(), written to ab.json
        # by _finish().
        self._ab_results: list[dict[str, Any]] = []
        self._ab_item_index: int = 0

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

        # States currently mid rate-limit in-place retry. Populated by _route_next_state
        # when _handle_rate_limit returns an in-place target; consumed (discarded) by the
        # retry-counting block on the next same-state re-entry.  Exempts infrastructure
        # pauses from the max_retries budget (BUG-2065 Fix 2).
        self._rate_limit_in_flight: set[str] = set()

        # Consecutive rate_limit_exhausted emissions across all states. Reset on any
        # successful non-rate-limited state transition. When this reaches
        # _RATE_LIMIT_STORM_THRESHOLD, a RATE_LIMIT_STORM event is emitted.
        self._consecutive_rate_limit_exhaustions: int = 0

        # Per-state API server error retry tracking (parallel to _rate_limit_retries).
        # _api_error_retries[state_name] = {"retries": int, "total_wait": float}
        # Reset when the state completes without a server error, or after exhaustion.
        self._api_error_retries: dict[str, dict[str, Any]] = {}

        # Per-state tool-call throttle counter. Counts successive action executions within
        # a single continuous state visit. Reset on state exit; NOT serialized to LoopState
        # (throttle counts measure instantaneous visit-level activity, not cumulative retries).
        self._throttle_counts: dict[str, int] = {}

        # Per-edge revisit counter for cycle detection.
        # _edge_revisit_counts["from_state->to_state"] = number of times that edge has fired.
        # When any edge exceeds max_edge_revisits, the loop terminates with cycle_detected.
        self._edge_revisit_counts: dict[str, int] = {}

        # Stall detector for repeated (state, exit_code, verdict) triples.
        # Enabled via fsm.circuit.repeated_failure (FEAT-1637); None when not configured.
        self._stall_detector: StallDetector | None = None
        if fsm.circuit is not None and fsm.circuit.repeated_failure is not None:
            self._stall_detector = StallDetector(window=fsm.circuit.repeated_failure.window)
        # Set by _execute_state when the detector fires with on_repeated_failure="abort";
        # checked by run() to terminate via _finish("stall_detected", ...).
        self._pending_stall_abort: Stall | None = None

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
                    if self.fsm.on_max_iterations is not None and not self._summary_state_executed:
                        # BUG-158: if we just routed from a sub-loop state
                        # (e.g. its on_error fired at the iteration cap),
                        # flush one pending non-sub-loop state before
                        # entering the summary handler so its action isn't
                        # silently lost. Mirrors the BUG-1226 timeout guard
                        # at lines 320-341. Single-step: no cascade.
                        # Gate: only flush when the route originated from a
                        # sub-loop (checked via _prev_state.loop). Normal
                        # self-routes are not sub-loop–originated and their
                        # action already executed — flushing them would
                        # double-count the iteration.
                        # Gate uses `pending.action is not None` (broader
                        # than the timeout guard's shell-only gate) so both
                        # shell-action and prompt-action intermediate states
                        # are flushed.
                        if self._just_routed:
                            prev_config = self.fsm.states.get(self._prev_state or "")
                            if prev_config is not None and prev_config.loop is not None:
                                pending = self.fsm.states.get(self.current_state)
                                if (
                                    pending is not None
                                    and not pending.terminal
                                    and pending.loop is None
                                    and pending.action is not None
                                ):
                                    self._flush_pending_shell_state(pending)
                        self._emit(
                            "max_iterations_summary",
                            {
                                "summary_state": self.fsm.on_max_iterations,
                                "iterations": self.iteration,
                            },
                        )
                        self._summary_state_executed = True
                        self.current_state = self.fsm.on_max_iterations
                        # Fall through — let the summary state run in this iteration.
                        # (do not `continue`; that would re-trigger the cap check
                        # before the state executes since self.iteration is unchanged.)
                    else:
                        return self._finish("max_iterations")

                # Check timeout
                if self.fsm.timeout:
                    elapsed = _now_ms() - self.start_time_ms + self.elapsed_offset_ms
                    if elapsed > self.fsm.timeout * 1000:
                        # BUG-1226: if timeout fires in the race window between
                        # a `route` event and `state_enter`, flush one pending
                        # shell-action state before honoring the timeout so its
                        # side effect (e.g. copying a handshake flag) is not
                        # silently lost. Bounded to shell actions — slash
                        # commands and sub-loops would violate the timeout
                        # budget. Single-step: no cascade.
                        if self._just_routed:
                            pending = self.fsm.states.get(self.current_state)
                            if (
                                pending is not None
                                and not pending.terminal
                                and pending.loop is None
                                and pending.action is not None
                                and self._action_mode(pending) == "shell"
                            ):
                                self._flush_pending_shell_state(pending)
                        return self._finish("timeout")

                # Get current state config
                state_config = self.fsm.states[self.current_state]

                # Update per-state retry tracking based on transition from previous iteration.
                # If re-entering the same state consecutively, increment retry count.
                # If entering a different state, clear the previous state's retry count.
                if self._prev_state is not None:
                    if self.current_state == self._prev_state:
                        # Rate-limit in-place retries are infrastructure pauses, not action
                        # failures — exempt them from max_retries budget (BUG-2065 Fix 2).
                        if self.current_state not in self._rate_limit_in_flight:
                            self._retry_counts[self.current_state] = (
                                self._retry_counts.get(self.current_state, 0) + 1
                            )
                        self._rate_limit_in_flight.discard(self.current_state)
                    else:
                        self._retry_counts.pop(self._prev_state, None)
                        self._throttle_counts.pop(self._prev_state, None)
                        self._rate_limit_in_flight.discard(self._prev_state)

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
                        self._just_routed = True
                        continue
                    # ENH-1631: if we arrived here via the on_max_iterations summary
                    # state, preserve terminated_by="max_iterations" so audit tooling
                    # and PersistentExecutor see "interrupted" rather than "completed".
                    if self._summary_state_executed:
                        # BUG-158: when current_state IS the on_max_iterations
                        # handler, it hasn't executed yet — let it run once before
                        # terminating. The _summary_state_executed flag prevents the
                        # cap guard from re-triggering; it shouldn't prevent the
                        # handler from executing its action.
                        if self.current_state != self.fsm.on_max_iterations:
                            return self._finish("max_iterations")
                        # Fall through — execute the handler's action this iteration.
                    else:
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
                self._just_routed = False
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

                # Check for pending stall abort (FEAT-1637). The detector
                # fired with on_repeated_failure="abort" inside _execute_state;
                # terminate cleanly via _finish (mirrors the cycle_detected
                # guard below at lines 397-416).
                if self._pending_stall_abort is not None:
                    stall = self._pending_stall_abort
                    s_state, s_exit, s_verdict = stall.triple
                    return self._finish(
                        "stall_detected",
                        error=(
                            f"Stall detected: state '{s_state}' produced "
                            f"(exit_code={s_exit}, verdict='{s_verdict}') "
                            f"for {stall.count} consecutive iterations"
                        ),
                    )

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
                    # BUG-158: if the on_max_iterations summary handler executed
                    # and returned None (no routing targets — typical for terminal
                    # handlers that produce diagnostic output), terminate with the
                    # max_iterations reason instead of an error.
                    if self._summary_state_executed:
                        return self._finish("max_iterations")
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

                # Per-edge revisit tracking for cycle detection.
                edge_key = f"{self.current_state}->{resolved_next}"
                self._edge_revisit_counts[edge_key] = self._edge_revisit_counts.get(edge_key, 0) + 1
                if self._edge_revisit_counts[edge_key] > self.fsm.max_edge_revisits:
                    self._emit(
                        "cycle_detected",
                        {
                            "edge": edge_key,
                            "from": self.current_state,
                            "to": resolved_next,
                            "count": self._edge_revisit_counts[edge_key],
                            "max": self.fsm.max_edge_revisits,
                        },
                    )
                    return self._finish(
                        "cycle_detected",
                        error=f"Cycle detected: edge {edge_key} traversed "
                        f"{self._edge_revisit_counts[edge_key]} times "
                        f"(limit: {self.fsm.max_edge_revisits})",
                    )

                self._prev_state = self.current_state
                self.current_state = resolved_next
                self._just_routed = True

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

        # Simulation mode: stub dispatch instead of loading/running the real child FSM.
        # Mirrors the ENH-1164 treatment of parallel: states — no side effects, no real child
        # execution. Dynamic loop names that can't resolve in simulation yield a display label
        # from the raw template rather than aborting with InterpolationError.
        if isinstance(self.action_runner, SimulationActionRunner):
            try:
                display_name = interpolate(state.loop, ctx)
            except InterpolationError:
                display_name = state.loop  # raw template as label when context not populated
            sim_result = self.action_runner.run(
                action=f"[sub-loop: {display_name}]",
                timeout=0,
                is_slash_command=False,
            )
            if sim_result.exit_code == 0:
                return interpolate(state.on_yes, ctx) if state.on_yes else None
            elif sim_result.exit_code == 2:
                if state.on_error:
                    return interpolate(state.on_error, ctx)
                return interpolate(state.on_no, ctx) if state.on_no else None
            else:
                return interpolate(state.on_no, ctx) if state.on_no else None

        loop_name = interpolate(state.loop, ctx)
        loop_path = resolve_loop_path(loop_name, self.loops_dir or Path(".loops"))
        child_fsm, _ = load_and_validate(loop_path)

        # Bind child context: explicit with: bindings take precedence over legacy passthrough
        if state.with_:
            from little_loops.fsm.interpolation import interpolate_dict

            resolved = interpolate_dict(state.with_, ctx)
            # Apply declared defaults for unbound optional parameters
            for param_name, param_spec in child_fsm.parameters.items():
                if (
                    param_name not in resolved
                    and not param_spec.required
                    and param_spec.default is not None
                ):
                    resolved[param_name] = param_spec.default
            # Runtime check: required parameters must be present after interpolation
            for param_name, param_spec in child_fsm.parameters.items():
                if param_spec.required and param_name not in resolved:
                    raise ValueError(
                        f"Sub-loop '{state.loop}' requires parameter '{param_name}' "
                        f"but it is not bound in 'with'"
                    )
            # Merge: child's own context block provides base; with: bindings override
            child_fsm.context = {**child_fsm.context, **resolved}
            # Runner-managed runtime invariants must survive explicit `with:` binding. run_dir is
            # injected into the parent context by the runner (cli/loop/run.py) and every loop
            # assumes its presence (writes goals.json, batch-plan.json, etc.). The
            # context_passthrough branch inherits it via **self.fsm.context; the with: branch
            # must re-inject it explicitly or the child's first os.makedirs('${context.run_dir}')
            # -> os.makedirs('') crashes. setdefault keeps an explicit `with: run_dir:` override
            # winning if a caller ever sets one.
            if "run_dir" in self.fsm.context:
                child_fsm.context.setdefault("run_dir", self.fsm.context["run_dir"])
        elif state.context_passthrough:
            # Extract .output strings from capture result dicts so ${context.key} resolves
            # to the plain output string (e.g. "ENH-123") rather than the full capture object.
            captured_as_context = {
                k: v["output"] if isinstance(v, dict) and "exit_code" in v else v
                for k, v in self.captured.items()
            }
            child_fsm.context = {**self.fsm.context, **captured_as_context, **child_fsm.context}

        depth = self._depth + 1
        child_events: list[dict] = []

        def _sub_event_callback(event: dict) -> None:
            child_events.append(event)
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

        # Clamp child timeout to parent's remaining wall-clock budget so a slow sub-loop
        # can't silently consume the parent's deadline with no recourse for the parent FSM.
        if self.fsm.timeout:
            elapsed_ms = _now_ms() - self.start_time_ms + self.elapsed_offset_ms
            remaining_s = max(1, int((self.fsm.timeout * 1000 - elapsed_ms) // 1000))
            if child_fsm.timeout is None or child_fsm.timeout > remaining_s:
                child_fsm.timeout = remaining_s

        child_result = child_executor.run()

        # Capture child event stream as a JSON-lines string if the state declares a capture key
        if state.capture and child_events:
            import json as _json

            self.captured[state.capture] = {
                "output": "\n".join(_json.dumps(e) for e in child_events),
                "exit_code": None,
            }

        # Merge child captures back into parent under the state name
        if (state.context_passthrough or state.with_) and child_executor.captured:
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

    def _execute_learning_state(self, state: StateConfig, ctx: InterpolationContext) -> str | None:
        """Execute a FEAT-1283 ``type: learning`` state.

        Resolves the target list at runtime: if ``learning.targets_csv`` is set,
        it is interpolated and CSV-split; otherwise ``learning.targets`` is used
        directly.  The retry limit is resolved similarly: ``learning.max_retries_expr``
        (if set) is interpolated and int()-cast; otherwise ``learning.max_retries``
        (default 2) is used.

        For each target:
          1. Look up its record in the learning-tests registry (ENH-1282).
          2. If proven → continue.
          3. If refuted → emit ``learning_target_refuted`` + ``learning_blocked``
             and route to ``on_blocked`` (preferred) or ``on_no``.
          4. If missing or stale → emit ``learning_target_stale`` and invoke
             ``/ll:explore-api <target>`` via the executor's action_runner;
             re-check the registry; repeat up to ``max_retries`` times before
             emitting ``learning_blocked`` (reason ``retries_exhausted``) and
             routing to ``on_blocked``/``on_no``.

        When every target ends up proven, emit ``learning_complete`` and route
        to ``on_yes``. Returns the resolved next-state name (or ``None`` when no
        route is configured for the terminal verdict, mirroring ``_route``).
        """
        from little_loops.learning_tests import check_learning_test

        assert state.learning is not None  # guarded by caller

        # Resolve target list at runtime (ENH-1741: targets_csv support).
        if state.learning.targets_csv is not None:
            raw_csv = interpolate(state.learning.targets_csv, ctx)
            targets = [t.strip() for t in raw_csv.split(",") if t.strip()]
        else:
            targets = list(state.learning.targets)

        # Resolve retry limit at runtime (ENH-1741: max_retries_expr support).
        if state.learning.max_retries_expr is not None:
            max_retries = int(interpolate(state.learning.max_retries_expr, ctx))
        else:
            max_retries = state.learning.max_retries

        def _blocked_target(reason: str, target: str) -> str | None:
            self._emit(
                "learning_blocked",
                {"state": self.current_state, "target": target, "reason": reason},
            )
            route = state.on_blocked or state.on_no
            return interpolate(route, ctx) if route else None

        for target in targets:
            record = check_learning_test(target)

            attempts = 0
            while record is None or record.status == "stale":
                if attempts >= max_retries:
                    return _blocked_target("retries_exhausted", target)

                if record is None:
                    self._emit(
                        "learning_target_stale",
                        {"state": self.current_state, "target": target, "cause": "missing"},
                    )
                else:
                    self._emit(
                        "learning_target_stale",
                        {"state": self.current_state, "target": target, "cause": "stale"},
                    )

                self._emit(
                    "learning_explore_invoked",
                    {"state": self.current_state, "target": target, "attempt": attempts + 1},
                )
                self._run_action(f"/ll:explore-api {target}", state, ctx)
                attempts += 1
                record = check_learning_test(target)

            if record.status == "refuted":
                self._emit(
                    "learning_target_refuted",
                    {"state": self.current_state, "target": target},
                )
                return _blocked_target("refuted", target)

            self._emit(
                "learning_target_proven",
                {"state": self.current_state, "target": target},
            )

        self._emit(
            "learning_complete",
            {"state": self.current_state, "targets": targets},
        )
        return interpolate(state.on_yes, ctx) if state.on_yes else None

    def _compute_progress_fingerprint(self, ctx: InterpolationContext) -> tuple[object, ...] | None:
        """Return an (mtime, size) fingerprint for configured progress_paths, or None.

        Called just before stall_detector.record() so that file changes made by
        intermediate next:-only states are visible to the detector. Returns None
        when no progress_paths are configured (preserves existing semantics).

        Paths listed in exclude_paths (BUG-1767) are resolved and removed before
        building the fingerprint tuple so that a loop's internal bookkeeping files
        cannot reset the stall window on every cycle.
        """
        if self.fsm.circuit is None or self.fsm.circuit.repeated_failure is None:
            return None
        rf = self.fsm.circuit.repeated_failure
        paths = rf.progress_paths
        if not paths:
            return None

        excluded: set[str] = set()
        for raw_excl in rf.exclude_paths:
            try:
                excluded.add(interpolate(raw_excl, ctx))
            except Exception:
                pass

        entries: list[tuple[float, int]] = []
        for raw_path in paths:
            try:
                resolved = interpolate(raw_path, ctx)
            except Exception:
                continue
            if resolved in excluded:
                continue
            p = Path(resolved)
            if p.exists():
                st = p.stat()
                entries.append((st.st_mtime, st.st_size))
            else:
                entries.append((0.0, 0))
        return tuple(entries) if entries else None

    def _check_throttle(self, state: StateConfig, state_name: str) -> str | None:
        """Increment the per-state tool-call counter and enforce throttle thresholds.

        Called after every action execution within a state visit. Returns the forced
        next-state name when the hard threshold is reached, or None when execution
        should continue normally (warn events are emitted but do not redirect).

        Sets self._pending_error and returns "__STOP__" when the call count exceeds
        hard_max with no on_throttle_hard target — the caller must propagate this as
        a None return from _execute_state so the main loop detects _pending_error.
        """
        count = self._throttle_counts.get(state_name, 0) + 1
        self._throttle_counts[state_name] = count

        throttle = state.throttle
        normal_max = (
            throttle.normal_max
            if (throttle and throttle.normal_max is not None)
            else _DEFAULT_THROTTLE_NORMAL_MAX
        )
        warn_max = (
            throttle.warn_max
            if (throttle and throttle.warn_max is not None)
            else _DEFAULT_THROTTLE_WARN_MAX
        )
        hard_max = (
            throttle.hard_max
            if (throttle and throttle.hard_max is not None)
            else _DEFAULT_THROTTLE_HARD_MAX
        )

        if count == warn_max:
            self._emit(
                THROTTLE_WARN_EVENT,
                {
                    "state": state_name,
                    "count": count,
                    "normal_max": normal_max,
                    "warn_max": warn_max,
                    "hard_max": hard_max,
                },
            )

        # States with type="learning" (FEAT-1283) are exempt from hard_max — they
        # legitimately make N calls per visit (one per unproven target).
        if state.type == "learning":
            return None

        if count == hard_max:
            next_target = state.on_throttle_hard or state.on_error
            self._emit(
                THROTTLE_HARD_EVENT,
                {"state": state_name, "count": count, "hard_max": hard_max, "next": next_target},
            )
            return next_target

        if count > hard_max:
            self._emit(
                THROTTLE_STOP_EVENT,
                {"state": state_name, "count": count, "hard_max": hard_max},
            )
            self._pending_error = (
                f"Throttle stop: state '{state_name}' exceeded hard_max={hard_max} "
                "tool calls with no on_throttle_hard target"
            )
            return "__STOP__"

        return None

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
            except (FileNotFoundError, ValueError, InterpolationError):
                if state.on_error:
                    return interpolate(state.on_error, ctx)
                raise

        # FEAT-1283: dispatch to learning-state handler when both type="learning"
        # AND a LearningConfig is present. The bare `type="learning"` marker
        # (used pre-FEAT-1283 only as a throttle hard_max exemption hint, see
        # ThrottleConfig docstring) falls through to normal action execution.
        if state.type == "learning" and state.learning is not None:
            return self._execute_learning_state(state, ctx)

        # Handle unconditional transition
        if state.next:
            if state.action:
                self._maybe_wait_for_circuit(state)
                result, routed = self._run_action_or_route(state, ctx)
                if routed is not None:
                    return routed
                throttle_next = self._check_throttle(state, self.current_state)
                if throttle_next == "__STOP__":
                    return None
                if throttle_next is not None:
                    return throttle_next
                assert result is not None
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
                    error_target = interpolate(state.on_error, ctx)
                    if (
                        state.retryable_exit_codes is not None
                        and result.exit_code is not None
                        and result.exit_code not in state.retryable_exit_codes
                    ):
                        # Non-retryable exit code — bypass retry, route to
                        # on_retry_exhausted (if set) or on_error directly.
                        if state.on_retry_exhausted:
                            return state.on_retry_exhausted
                        return error_target
                    return error_target
            return interpolate(state.next, ctx)

        # Execute action if present
        action_result = None
        if state.action and self._action_mode(state) != "contract":
            self._maybe_wait_for_circuit(state)
            baseline_cfg = ctx.context.get("_baseline")
            if baseline_cfg and isinstance(baseline_cfg, dict) and baseline_cfg.get("enabled"):
                # Baseline mode: spawn parallel arms, harness drives routing
                action_result, routed = self._execute_with_baseline(state, ctx, baseline_cfg)
                if routed is not None:
                    return routed
            else:
                action_result, routed = self._run_action_or_route(state, ctx)
            if routed is not None:
                return routed
            throttle_next = self._check_throttle(state, self.current_state)
            if throttle_next == "__STOP__":
                return None
            if throttle_next is not None:
                return throttle_next

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

        # Stall detection (FEAT-1637). Record this transition's triple and
        # check whether the last `window` triples are identical. On stall,
        # either abort (set _pending_stall_abort for run() to catch) or
        # override next_state to the configured recovery target.
        stall_route_target: str | None = None
        if self._stall_detector is not None:
            stall_exit_code = action_result.exit_code if action_result else 0
            stall_fingerprint = self._compute_progress_fingerprint(ctx)
            self._stall_detector.record(
                self.current_state, stall_exit_code, verdict, stall_fingerprint
            )
            stall = self._stall_detector.check()
            if stall is not None:
                assert self.fsm.circuit is not None
                assert self.fsm.circuit.repeated_failure is not None
                cfg_action = self.fsm.circuit.repeated_failure.on_repeated_failure
                self._emit(
                    STALL_DETECTED_EVENT,
                    {
                        "state": self.current_state,
                        "exit_code": stall_exit_code,
                        "verdict": verdict,
                        "consecutive": stall.count,
                        "action": "abort" if cfg_action == "abort" else f"route:{cfg_action}",
                    },
                )
                if cfg_action == "abort":
                    self._pending_stall_abort = stall
                    return None
                # Route to recovery target; bypass _route() entirely so the
                # eval verdict does not pull us elsewhere first.
                stall_route_target = cfg_action

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
        # BUG-2065 Fix 1: guard on exit_code != 0 so that successful actions whose
        # output incidentally contains "rate limit" text are never intercepted.
        if action_result is not None:
            _combined = (action_result.output or "") + "\n" + (action_result.stderr or "")
            _failure_type, _reason = classify_failure(_combined, action_result.exit_code)
            if (
                action_result.exit_code != 0
                and _failure_type == FailureType.TRANSIENT
                and ("rate limit" in _reason.lower() or "quota" in _reason.lower())
            ):
                _handled, _target = self._handle_rate_limit(state, route_ctx.state_name)
                if _handled:
                    self._rate_limit_in_flight.add(route_ctx.state_name)
                    return _target
            elif (
                action_result.exit_code != 0
                and _failure_type == FailureType.TRANSIENT
                and "api server error" in _reason.lower()
            ):
                _handled, _target = self._handle_api_error(state, route_ctx.state_name)
                if _handled:
                    return _target
                # exhausted — fall through to normal verdict routing
            else:
                # Not rate-limited or server-error (or exit_code=0): reset counters so
                # future transients start fresh.
                self._rate_limit_retries.pop(route_ctx.state_name, None)
                self._consecutive_rate_limit_exhaustions = 0
                self._api_error_retries.pop(route_ctx.state_name, None)

        # Stall-route override: if the detector elected to route to a recovery
        # state, honor it now (bypass interceptors and _route) so the
        # configured target wins over the eval verdict.
        if stall_route_target is not None:
            return stall_route_target

        # Non-retryable exit code filter for eval-based error routing. When a
        # state uses retryable_exit_codes and the action fails with a code that
        # is NOT retryable, bypass the normal error route (which may be a
        # self-retry) and go directly to on_retry_exhausted (or on_error).
        if (
            verdict == "error"
            and state.retryable_exit_codes is not None
            and action_result is not None
            and action_result.exit_code is not None
            and action_result.exit_code not in state.retryable_exit_codes
        ):
            if state.on_retry_exhausted:
                return state.on_retry_exhausted
            if state.on_error:
                return interpolate(state.on_error, ctx)

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
        on_usage: UsageCallback | None = None,
    ) -> ActionResult:
        """Execute action and optionally capture result.

        Args:
            action_template: Action string (may contain variables)
            state: State configuration
            ctx: Interpolation context
            on_usage: Optional callback invoked with (input_tokens, output_tokens) on completion

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
                on_usage=on_usage,
            )
        else:
            result = self.action_runner.run(
                action,
                timeout=state.timeout or self.fsm.default_timeout or 3600,
                is_slash_command=action_mode == "prompt",
                on_output_line=_on_line,
                agent=state.agent if action_mode == "prompt" else None,
                tools=state.tools if action_mode == "prompt" else None,
                on_usage=on_usage,
                model=state.model if action_mode == "prompt" else None,
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
        # Aggregate token usage from host-CLI invocations (prompt / slash_command only)
        if result.usage_events:
            total_input = sum(u.input_tokens for u in result.usage_events)
            total_output = sum(u.output_tokens for u in result.usage_events)
            total_cache_read = sum(u.cache_read_tokens for u in result.usage_events)
            total_cache_creation = sum(u.cache_creation_tokens for u in result.usage_events)
            model = result.usage_events[-1].model
            payload["input_tokens"] = total_input
            payload["output_tokens"] = total_output
            payload["cache_read_tokens"] = total_cache_read
            payload["cache_creation_tokens"] = total_cache_creation
            payload["model"] = model
        self._emit("action_complete", payload)

        # Capture if requested
        if state.capture:
            self.captured[state.capture] = {
                "output": result.output.rstrip("\n\r"),
                "stderr": result.stderr,
                "exit_code": result.exit_code,
                "duration_ms": result.duration_ms,
            }

        # Append to shared messages log if requested
        if state.append_to_messages:
            post_ctx = self._build_context()
            message = interpolate(state.append_to_messages, post_ctx)
            self.messages.append(message)
            self._emit(
                "messages_append",
                {"message": message, "state": self.current_state},
            )

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

        Uses selector-based I/O with wall-clock timeout enforcement so the
        timeout is honoured even when the process hangs before producing output.
        """
        start = _now_ms()
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        self._current_process = process
        deadline = time.time() + timeout

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
                remaining = deadline - time.time()
                if remaining <= 0:
                    timed_out = True
                    break
                poll_timeout = min(1.0, remaining)
                ready = sel.select(timeout=poll_timeout)
                if not ready:
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
                        sel.unregister(key.fileobj)
        finally:
            sel.close()
            self._current_process = None

        if timed_out:
            _kill_process_group(process)
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait()
            return ActionResult(
                output="".join(output_chunks),
                stderr="".join(stderr_chunks) or "MCP call timed out",
                exit_code=124,
                duration_ms=timeout * 1000,
            )

        process.wait(timeout=5)
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
            if verdict == "no" and state.route.error:
                return self._resolve_route(state.route.error, ctx)
            return None

        # Shorthand routing
        if verdict == "yes" and state.on_yes:
            return self._resolve_route(state.on_yes, ctx)
        if verdict == "no" and state.on_no:
            return self._resolve_route(state.on_no, ctx)
        if verdict == "no" and not state.on_no and state.on_error:
            return self._resolve_route(state.on_error, ctx)
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

    def _flush_pending_shell_state(self, state: StateConfig) -> None:
        """Execute a pending shell-action state's action before honoring a
        wall-clock timeout. BUG-1226: closes the narrow race between emitting
        a `route` event and `state_enter` so handshake states (e.g. autodev's
        ``copy_broke_down``) do not silently drop their side effect when the
        timeout fires in that window. Single-step: we run the action but do
        not follow its routing — ``final_state`` stays as the flushed state.
        """
        assert state.action is not None  # guarded by caller
        self.iteration += 1
        self._just_routed = False
        self._emit(
            "state_enter",
            {
                "state": self.current_state,
                "iteration": self.iteration,
                "flushed": True,
            },
        )
        ctx = self._build_context()
        try:
            self._run_action(state.action, state, ctx)
        except Exception:
            # Deliberately swallow — the timeout is being honored regardless
            # of whether the flushed action succeeded.
            pass

    def _action_mode(self, state: StateConfig) -> str:
        """Return execution mode for the state: 'prompt', 'shell', 'mcp_tool', or 'contract'."""
        if state.action_type == "contract":
            return "contract"
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

    def _execute_with_baseline(
        self,
        state: StateConfig,
        ctx: InterpolationContext,
        baseline_cfg: dict[str, Any],
    ) -> tuple[ActionResult | None, str | None]:
        """Execute harness arm + baseline arm in parallel.

        The harness arm drives FSM routing; the baseline arm runs a single-shot
        skill invocation with no eval gates for data collection only.

        Returns (action_result, routed_target) where action_result is from the
        harness arm and routed_target is None (routing happens in _execute_state).
        """
        from concurrent.futures import ThreadPoolExecutor

        harness_tokens: list[tuple[int, int]] = []
        baseline_tokens: list[tuple[int, int]] = []

        def _on_harness_usage(input_tokens: int, output_tokens: int) -> None:
            harness_tokens.append((input_tokens, output_tokens))

        def _on_baseline_usage(input_tokens: int, output_tokens: int) -> None:
            baseline_tokens.append((input_tokens, output_tokens))

        # Determine baseline skill: use --baseline-skill override or extract from action
        baseline_skill_name = baseline_cfg.get("skill")
        if baseline_skill_name is None:
            action_text = interpolate(state.action, ctx)  # type: ignore[arg-type]
            baseline_skill_name = _extract_skill_from_action(action_text)

        assert state.action is not None  # caller-guarded by `if state.action:`
        with ThreadPoolExecutor(max_workers=2) as pool:
            harness_future = pool.submit(
                self._run_action, state.action, state, ctx, _on_harness_usage
            )
            baseline_future = pool.submit(
                self._run_baseline_arm, baseline_skill_name, state, _on_baseline_usage
            )
            harness_result: ActionResult = harness_future.result()
            baseline_result: ActionResult = baseline_future.result()

        harness_total_tokens = sum(t[0] + t[1] for t in harness_tokens)
        baseline_total_tokens = sum(t[0] + t[1] for t in baseline_tokens)

        self._emit(
            "baseline_complete",
            {
                "harness_duration_ms": harness_result.duration_ms,
                "baseline_duration_ms": baseline_result.duration_ms,
                "harness_tokens": harness_total_tokens,
                "baseline_tokens": baseline_total_tokens,
            },
        )

        # FEAT-1822: Run blind comparison and accumulate per-item results.
        # The blind comparator is non-fatal: if it errors, we record a
        # degraded result but let the harness routing proceed unchanged.
        try:
            comparison = evaluate_blind_comparator(
                output_harness=harness_result.output,
                output_baseline=baseline_result.output,
            )
            item: dict[str, Any] = {
                "index": self._ab_item_index,
                "harness_pass": comparison.get("harness_pass", False),
                "baseline_pass": comparison.get("baseline_pass", False),
                "harness_tokens": harness_total_tokens,
                "baseline_tokens": baseline_total_tokens,
                "harness_duration_ms": harness_result.duration_ms,
                "baseline_duration_ms": baseline_result.duration_ms,
                "confidence": comparison.get("confidence", 0.0),
                "reason": comparison.get("reason", ""),
            }
            self._ab_results.append(item)
            self._ab_item_index += 1
            self._emit("ab_comparison", {**item, "raw": comparison.get("raw", {})})
        except Exception:
            # Blind evaluation failure is non-fatal — record degraded result
            item = {
                "index": self._ab_item_index,
                "harness_pass": False,
                "baseline_pass": False,
                "harness_tokens": harness_total_tokens,
                "baseline_tokens": baseline_total_tokens,
                "harness_duration_ms": harness_result.duration_ms,
                "baseline_duration_ms": baseline_result.duration_ms,
                "confidence": 0.0,
                "reason": "Blind evaluation failed",
                "error": "evaluation_error",
            }
            self._ab_results.append(item)
            self._ab_item_index += 1

        return harness_result, None

    def _run_baseline_arm(
        self,
        skill_command: str,
        state: StateConfig,
        on_usage: UsageCallback | None = None,
    ) -> ActionResult:
        """Run a single-shot baseline skill invocation with no eval gates.

        Args:
            skill_command: Slash command for the baseline skill (e.g., "/ll:some-skill")
            state: State configuration (for timeout)
            on_usage: Optional callback for token capture

        Returns:
            ActionResult with output, exit code, and duration
        """
        start = _now_ms()
        timeout = state.timeout or self.fsm.default_timeout or 3600
        try:
            completed = run_claude_command(
                command=skill_command,
                timeout=timeout,
                on_usage=on_usage,
            )
            return ActionResult(
                output=completed.stdout,
                stderr=completed.stderr,
                exit_code=completed.returncode,
                duration_ms=_now_ms() - start,
            )
        except subprocess.TimeoutExpired:
            return ActionResult(
                output="",
                stderr="Baseline action timed out",
                exit_code=124,
                duration_ms=timeout * 1000,
            )

    def _run_action_or_route(
        self, state: StateConfig, ctx: InterpolationContext
    ) -> tuple[ActionResult | None, str | None]:
        """Run the state action, routing unhandled exceptions to on_error.

        Returns (action_result, routed_target). ``routed_target`` is a non-None
        next-state string only when an exception was raised AND ``state.on_error``
        is defined; in that case ``action_result`` is None. When no on_error is
        set, the exception is re-raised for the top-level ``run()`` handler.
        """
        assert state.action is not None  # caller-guarded
        try:
            return self._run_action(state.action, state, ctx), None
        except Exception as exc:
            if state.on_error:
                self._emit(
                    "action_error",
                    {
                        "state": self.current_state,
                        "error": str(exc),
                        "route": "on_error",
                    },
                )
                return None, interpolate(state.on_error, ctx)
            raise

    def _build_context(self) -> InterpolationContext:
        """Build interpolation context for current state.

        Returns:
            InterpolationContext with all runtime values
        """
        from little_loops.fsm.interpolation import interpolate_dict

        ctx = InterpolationContext(
            context=self.fsm.context,
            captured=self.captured,
            prev=self.prev_result,
            result=None,
            state_name=self.current_state,
            iteration=self.iteration,
            loop_name=self.fsm.name,
            started_at=self.started_at,
            elapsed_ms=_now_ms() - self.start_time_ms + self.elapsed_offset_ms,
            messages=list(self.messages),
        )

        # Populate param namespace from fragment bindings (if this state uses a fragment)
        state = self.fsm.states.get(self.current_state)
        if state is not None and (state.fragment_bindings or state.fragment_parameters):
            resolved = interpolate_dict(state.fragment_bindings, ctx)
            # Apply declared defaults for unbound optional parameters
            for param_name, param_spec in state.fragment_parameters.items():
                if (
                    param_name not in resolved
                    and not param_spec.required
                    and param_spec.default is not None
                ):
                    resolved[param_name] = param_spec.default
            # Runtime enforcement: required parameters must be bound
            for param_name, param_spec in state.fragment_parameters.items():
                if param_spec.required and param_name not in resolved:
                    raise ValueError(
                        f"Fragment '{state.fragment_name}' requires parameter '{param_name}' "
                        f"but it is not bound in 'with'"
                    )
            ctx.param = resolved

        return ctx

    def _emit(self, event: str, data: dict[str, Any]) -> None:
        """Emit an event via the callback."""
        self.event_callback(
            {
                "event": event,
                "ts": _iso_now(),
                **data,
            }
        )

    def _handle_rate_limit(self, state: StateConfig, state_name: str) -> tuple[bool, str | None]:
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
            _sleep = _backoff_base * (2 ** (short_retries - 1)) + random.uniform(0, _backoff_base)
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
                "retries": int(record.get("short_retries", 0)) + int(record.get("long_retries", 0)),
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

    def _handle_api_error(self, state: StateConfig, state_name: str) -> tuple[bool, str | None]:
        """Handle a detected API server error with short-burst flat backoff.

        Unlike ``_handle_rate_limit``, uses a flat backoff with no long-wait tier and
        falls through to normal FSM routing after ``_DEFAULT_API_ERROR_RETRIES`` attempts
        so transient infrastructure hiccups don't permanently misdirect the loop.

        Returns:
            ``(True, state_name)`` to retry the state in place, or
            ``(False, None)`` when the retry budget is exhausted (caller falls
            through to normal verdict routing).
        """
        record = self._api_error_retries.setdefault(state_name, {"retries": 0, "total_wait": 0.0})
        if record["retries"] >= _DEFAULT_API_ERROR_RETRIES:
            self._api_error_retries.pop(state_name, None)
            self._emit("api_error_exhausted", {"state": state_name, "retries": record["retries"]})
            return False, None
        record["retries"] += 1
        slept = self._interruptible_sleep(_DEFAULT_API_ERROR_BACKOFF)
        record["total_wait"] += slept
        self._emit(
            "api_error_retry",
            {
                "state": state_name,
                "attempt": record["retries"],
                "backoff": _DEFAULT_API_ERROR_BACKOFF,
            },
        )
        return True, state_name

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

        # FEAT-1822: Write ab.json if baseline comparison results exist
        if self._ab_results:
            try:
                from little_loops.ab_writer import calculate_ab_summary, write_ab_json

                run_dir = self.fsm.context.get("run_dir", "")
                if run_dir:
                    summary = calculate_ab_summary(self._ab_results)
                    write_ab_json(summary, run_dir)
                    self._emit(
                        "ab_summary",
                        {
                            "harness_pass_rate": summary.harness_pass_rate,
                            "baseline_pass_rate": summary.baseline_pass_rate,
                            "delta": summary.delta,
                            "item_count": len(summary.per_item),
                        },
                    )
            except Exception:
                pass  # Non-fatal: loop still completes

        return ExecutionResult(
            final_state=self.current_state,
            iterations=self.iteration,
            terminated_by=terminated_by,
            duration_ms=_now_ms() - self.start_time_ms + self.elapsed_offset_ms,
            captured=self.captured,
            error=error,
            messages=list(self.messages),
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


def _extract_skill_from_action(action: str) -> str:
    """Extract the base skill name from an action string.

    For slash commands like "/ll:some-skill --arg value", returns "/ll:some-skill".
    For other actions, returns the action as-is.
    """
    stripped = action.strip()
    if stripped.startswith("/"):
        parts = stripped.split(maxsplit=1)
        return parts[0]
    return stripped

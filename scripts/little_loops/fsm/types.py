"""FSM result types for loop and action execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

from little_loops.subprocess_utils import TokenUsage

if TYPE_CHECKING:
    from little_loops.fsm.evaluators import EvaluationResult
    from little_loops.fsm.interpolation import InterpolationContext
    from little_loops.fsm.schema import EvaluateConfig


# ENH-2814: a run that lands on a terminal state declared `failure: true`
# exits with this distinct code, so shell scripts, cron wrappers and any
# subprocess caller of `ll-loop run` can tell a failed loop from a successful
# one. Kept separate from 1 (which covers the infra/limit terminations in
# cli/loop/_helpers.py::EXIT_CODES) so callers can distinguish "the loop ran
# and reported failure" from "the loop never reached a terminal at all".
# Lives here, not in cli/, so low-level consumers (parallel/, learning_tests/)
# can import it without pulling in the CLI package.
FAILURE_TERMINAL_EXIT_CODE: int = 2


@dataclass
class ExecutionResult:
    """Result from FSM execution.

    Attributes:
        final_state: Name of the state when execution stopped
        iterations: Total step executions (state enters)
        terminated_by: Reason for termination. Values: "terminal", "max_steps" (step cap reached;
            legacy "max_iterations" renamed), "max_iterations_reached" (full-pass cap reached),
            "timeout", "interrupted" (SIGTERM/session kill), "user_stopped" (ll-loop stop wrote
            user-stop.marker before signalling, ENH-2522), "system_signal" (POSIX process killed
            by signal N with no user-stop marker — e.g. kernel OOM/SIGKILL, ENH-2522),
            "error", "handoff", "cycle_detected", "stall_detected", "host_pressure_abort"
            (ENH-2452), "host_budget_exceeded" (ENH-2453).
        duration_ms: Total execution time in milliseconds
        captured: All captured variable values
        failure_terminal: True when execution stopped on a terminal state whose
            ``StateConfig.failure`` flag is set (ENH-2814). This is the single
            signal consumers use to tell a failed run from a successful one —
            ``terminated_by == "terminal"`` alone does NOT imply success. Drives
            the nonzero ``ll-loop run`` exit code, the persisted
            ``final_status="failed"``, and sub-loop ``on_no`` routing.
        error: Error message if terminated_by is "error"
        handoff: True if execution stopped due to handoff signal
        continuation_prompt: Continuation context from handoff signal
    """

    final_state: str
    iterations: int
    terminated_by: str  # "terminal", "max_steps", "max_iterations_reached", "timeout", "interrupted", "user_stopped", "system_signal", "error", "handoff", "cycle_detected"
    duration_ms: int
    captured: dict[str, dict[str, Any]]
    failure_terminal: bool = False
    error: str | None = None
    handoff: bool = False
    continuation_prompt: str | None = None
    messages: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        result: dict[str, Any] = {
            "final_state": self.final_state,
            "iterations": self.iterations,
            "terminated_by": self.terminated_by,
            "duration_ms": self.duration_ms,
            "captured": self.captured,
        }
        if self.failure_terminal:
            result["failure_terminal"] = self.failure_terminal
        if self.error is not None:
            result["error"] = self.error
        if self.handoff:
            result["handoff"] = self.handoff
        if self.continuation_prompt is not None:
            result["continuation_prompt"] = self.continuation_prompt
        if self.messages:
            result["messages"] = self.messages
        return result


@dataclass
class ActionResult:
    """Result from action execution.

    Attributes:
        output: stdout from the action
        stderr: stderr from the action
        exit_code: Exit code from the action
        duration_ms: Execution time in milliseconds
        usage_events: Token usage events from host-CLI invocations (empty for shell actions)
        peak_rss_mb: Peak resident memory of the spawned subprocess in MB
            (ENH-2453); None when RSS sampling was disabled or unavailable
        result_seen: Whether a stream-json "result" event was observed before
            the subprocess exited (BUG-2731); False for non-host-CLI actions
            (shell, simulation) where no stream-json protocol applies
        session_id: Host CLI session ID from the stream-json system/init event
            (FEAT-2711); None for non-host-CLI actions or when undetected.
        timeout_kind: Distinguishes an idle kill from a wall-clock kill on a
            timeout (FEAT-3033); "idle", "wall", or None when the action did
            not time out. exit_code stays 124 for both kinds (BUG-1640 /
            BUG-1815 routing is unaffected) — this field is the only
            discriminator.
    """

    output: str
    stderr: str
    exit_code: int
    duration_ms: int
    usage_events: list[TokenUsage] = field(default_factory=list)
    peak_rss_mb: float | None = None
    result_seen: bool = False
    session_id: str | None = None
    timeout_kind: str | None = None


# Type for event callback
EventCallback = Callable[[dict[str, Any]], None]

# Type for evaluator functions
# Parameter order: config, output, exit_code, context — matches evaluate() call signature
Evaluator = Callable[
    ["EvaluateConfig", str, int, "InterpolationContext"],
    "EvaluationResult",
]

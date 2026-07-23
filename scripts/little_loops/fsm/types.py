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
        error: Error message if terminated_by is "error"
        handoff: True if execution stopped due to handoff signal
        continuation_prompt: Continuation context from handoff signal
    """

    final_state: str
    iterations: int
    terminated_by: str  # "terminal", "max_steps", "max_iterations_reached", "timeout", "interrupted", "user_stopped", "system_signal", "error", "handoff", "cycle_detected"
    duration_ms: int
    captured: dict[str, dict[str, Any]]
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
    """

    output: str
    stderr: str
    exit_code: int
    duration_ms: int
    usage_events: list[TokenUsage] = field(default_factory=list)
    peak_rss_mb: float | None = None
    result_seen: bool = False


# Type for event callback
EventCallback = Callable[[dict[str, Any]], None]

# Type for evaluator functions
# Parameter order: config, output, exit_code, context — matches evaluate() call signature
Evaluator = Callable[
    ["EvaluateConfig", str, int, "InterpolationContext"],
    "EvaluationResult",
]

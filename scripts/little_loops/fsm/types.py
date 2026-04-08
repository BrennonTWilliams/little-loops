"""FSM result types for loop and action execution."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from little_loops.fsm.evaluators import EvaluationResult
    from little_loops.fsm.interpolation import InterpolationContext
    from little_loops.fsm.schema import EvaluateConfig


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

# Type for evaluator functions
# Parameter order: config, output, exit_code, context — matches evaluate() call signature
Evaluator = Callable[
    ["EvaluateConfig", str, int, "InterpolationContext"],
    "EvaluationResult",
]

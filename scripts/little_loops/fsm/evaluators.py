"""Tier 1 Deterministic Evaluators for FSM loop execution.

These evaluators interpret action output without any API calls.
They are fast, free, and reproducible.

Supported evaluator types:
    exit_code: Map Unix exit codes to verdicts (0=success, 1=failure, 2+=error)
    output_numeric: Compare numeric output to target value
    output_json: Extract and compare JSON path values
    output_contains: Pattern matching on stdout
    convergence: Track progress toward a target value
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    interpolate,
)
from little_loops.fsm.schema import EvaluateConfig


@dataclass
class EvaluationResult:
    """Result from an evaluator.

    Attributes:
        verdict: The routing key for state transitions
        details: Evaluator-specific metadata for debugging/logging
    """

    verdict: str
    details: dict[str, Any]


def evaluate_exit_code(exit_code: int) -> EvaluationResult:
    """Map Unix exit code to verdict.

    Args:
        exit_code: The process exit code

    Returns:
        EvaluationResult with verdict:
            - 0 -> success
            - 1 -> failure
            - 2+ -> error
    """
    if exit_code == 0:
        verdict = "success"
    elif exit_code == 1:
        verdict = "failure"
    else:
        verdict = "error"

    return EvaluationResult(verdict=verdict, details={"exit_code": exit_code})


def evaluate_output_numeric(
    output: str,
    operator: str,
    target: float,
) -> EvaluationResult:
    """Parse stdout as number and compare to target.

    Args:
        output: The action stdout to parse as a number
        operator: Comparison operator (eq, ne, lt, le, gt, ge)
        target: Target value to compare against

    Returns:
        EvaluationResult with verdict:
            - Condition met -> success
            - Condition not met -> failure
            - Parse error -> error
    """
    try:
        value = float(output.strip())
    except ValueError:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Cannot parse as number: {output[:100]}"},
        )

    operators = {
        "eq": lambda v, t: v == t,
        "ne": lambda v, t: v != t,
        "lt": lambda v, t: v < t,
        "le": lambda v, t: v <= t,
        "gt": lambda v, t: v > t,
        "ge": lambda v, t: v >= t,
    }

    if operator not in operators:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Unknown operator: {operator}"},
        )

    condition_met = operators[operator](value, target)
    return EvaluationResult(
        verdict="success" if condition_met else "failure",
        details={"value": value, "target": target, "operator": operator},
    )


def _extract_json_path(data: Any, path: str) -> Any:
    """Extract value from dict using jq-style path like '.summary.failed'.

    Args:
        data: The parsed JSON data (dict or list)
        path: Dot-separated path, optionally starting with '.'

    Returns:
        The value at the specified path

    Raises:
        KeyError: If path not found in data
    """
    if path.startswith("."):
        path = path[1:]
    parts = path.split(".")
    current = data
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        elif isinstance(current, list) and part.isdigit():
            idx = int(part)
            if 0 <= idx < len(current):
                current = current[idx]
            else:
                raise KeyError(path)
        else:
            raise KeyError(path)
    return current


def _compare_values(
    value: int | float, operator: str, target: int | float, path: str
) -> EvaluationResult:
    """Compare numeric values using operator.

    Args:
        value: The extracted value to compare
        operator: Comparison operator
        target: Target value
        path: JSON path for details

    Returns:
        EvaluationResult with comparison result
    """
    operators = {
        "eq": lambda v, t: v == t,
        "ne": lambda v, t: v != t,
        "lt": lambda v, t: v < t,
        "le": lambda v, t: v <= t,
        "gt": lambda v, t: v > t,
        "ge": lambda v, t: v >= t,
    }

    if operator not in operators:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Unknown operator: {operator}"},
        )

    condition_met = operators[operator](value, target)
    return EvaluationResult(
        verdict="success" if condition_met else "failure",
        details={"value": value, "path": path, "target": target, "operator": operator},
    )


def evaluate_output_json(
    output: str,
    path: str,
    operator: str,
    target: Any,
) -> EvaluationResult:
    """Parse JSON and extract value at path, then compare.

    Args:
        output: The action stdout containing JSON
        path: jq-style dot notation path (e.g., '.summary.failed')
        operator: Comparison operator (eq, ne, lt, le, gt, ge)
        target: Target value for comparison

    Returns:
        EvaluationResult with verdict:
            - Condition met -> success
            - Condition not met -> failure
            - Parse/path error -> error
    """
    try:
        data = json.loads(output)
    except json.JSONDecodeError as e:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Invalid JSON: {e}"},
        )

    try:
        value = _extract_json_path(data, path)
    except KeyError:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Path not found: {path}"},
        )

    # Use numeric comparison if both values are numeric
    if isinstance(value, (int, float)) and isinstance(target, (int, float)):
        return _compare_values(value, operator, target, path)

    # For non-numeric values, only eq and ne are supported
    if operator == "eq":
        verdict = "success" if value == target else "failure"
    elif operator == "ne":
        verdict = "success" if value != target else "failure"
    else:
        return EvaluationResult(
            verdict="error",
            details={
                "error": f"Operator {operator} not supported for non-numeric values"
            },
        )

    return EvaluationResult(
        verdict=verdict,
        details={"value": value, "path": path, "target": target, "operator": operator},
    )


def evaluate_output_contains(
    output: str,
    pattern: str,
    negate: bool = False,
) -> EvaluationResult:
    """Check if pattern exists in output.

    Pattern can be regex or substring. If regex fails to compile,
    falls back to substring matching.

    Args:
        output: The action stdout to search
        pattern: Regex pattern or substring
        negate: If True, invert the match result

    Returns:
        EvaluationResult with verdict:
            - Found (negate=False) -> success
            - Found (negate=True) -> failure
            - Not found (negate=False) -> failure
            - Not found (negate=True) -> success
    """
    # Try regex first, fall back to substring
    try:
        matched = bool(re.search(pattern, output))
    except re.error:
        matched = pattern in output

    if negate:
        verdict = "failure" if matched else "success"
    else:
        verdict = "success" if matched else "failure"

    return EvaluationResult(
        verdict=verdict,
        details={"matched": matched, "pattern": pattern, "negate": negate},
    )


def evaluate_convergence(
    current: float,
    previous: float | None,
    target: float,
    tolerance: float = 0,
    direction: str = "minimize",
) -> EvaluationResult:
    """Compare current value to target and previous.

    Args:
        current: Current metric value
        previous: Previous metric value (None if first iteration)
        target: Target value to reach
        tolerance: Acceptable distance from target
        direction: 'minimize' or 'maximize'

    Returns:
        EvaluationResult with verdict:
            - Value within tolerance of target -> target
            - Value improved toward target -> progress
            - Value unchanged or worsened -> stall
    """
    # Check if target reached (within tolerance)
    if abs(current - target) <= tolerance:
        return EvaluationResult(
            verdict="target",
            details={"current": current, "target": target, "delta": 0},
        )

    # First iteration has no previous value
    if previous is None:
        return EvaluationResult(
            verdict="progress",
            details={
                "current": current,
                "previous": None,
                "target": target,
                "delta": None,
            },
        )

    # Calculate progress
    delta = current - previous

    if direction == "minimize":
        # For minimizing, negative delta is progress
        made_progress = delta < 0
    else:
        # For maximizing, positive delta is progress
        made_progress = delta > 0

    verdict = "progress" if made_progress else "stall"

    return EvaluationResult(
        verdict=verdict,
        details={
            "current": current,
            "previous": previous,
            "target": target,
            "delta": delta,
            "direction": direction,
        },
    )


def evaluate(
    config: EvaluateConfig,
    output: str,
    exit_code: int,
    context: InterpolationContext,
) -> EvaluationResult:
    """Dispatch to appropriate evaluator based on config type.

    Args:
        config: Evaluator configuration with type and parameters
        output: Action stdout
        exit_code: Action exit code
        context: Runtime context for variable interpolation

    Returns:
        EvaluationResult from the appropriate evaluator

    Raises:
        ValueError: If evaluator type is unknown
    """
    eval_type = config.type

    if eval_type == "exit_code":
        return evaluate_exit_code(exit_code)

    elif eval_type == "output_numeric":
        # Target must be numeric
        numeric_target = float(config.target) if config.target is not None else 0.0
        return evaluate_output_numeric(
            output=output,
            operator=config.operator or "eq",
            target=numeric_target,
        )

    elif eval_type == "output_json":
        return evaluate_output_json(
            output=output,
            path=config.path or "",
            operator=config.operator or "eq",
            target=config.target,
        )

    elif eval_type == "output_contains":
        return evaluate_output_contains(
            output=output,
            pattern=config.pattern or "",
            negate=config.negate,
        )

    elif eval_type == "convergence":
        # Resolve previous value from interpolation if configured
        previous: float | None = None
        if config.previous:
            try:
                previous = float(interpolate(config.previous, context))
            except (InterpolationError, ValueError):
                # Previous unavailable on first iteration, continue with None
                pass

        # Parse current value from output
        try:
            current = float(output.strip())
        except ValueError:
            return EvaluationResult(
                verdict="error",
                details={"error": f"Cannot parse output as number: {output[:100]}"},
            )

        # Resolve target (may be interpolated string like "${context.target}")
        convergence_target: float
        if isinstance(config.target, str):
            try:
                convergence_target = float(interpolate(config.target, context))
            except (InterpolationError, ValueError) as e:
                return EvaluationResult(
                    verdict="error",
                    details={"error": f"Cannot resolve target: {e}"},
                )
        else:
            convergence_target = float(config.target) if config.target is not None else 0.0

        # Resolve tolerance (may be interpolated string)
        tolerance: float = 0.0
        if config.tolerance is not None:
            if isinstance(config.tolerance, str):
                try:
                    tolerance = float(interpolate(config.tolerance, context))
                except (InterpolationError, ValueError):
                    tolerance = 0.0
            else:
                tolerance = float(config.tolerance)

        return evaluate_convergence(
            current=current,
            previous=previous,
            target=convergence_target,
            tolerance=tolerance,
            direction=config.direction,
        )

    elif eval_type == "llm_structured":
        # Tier 2 evaluator - not implemented in FEAT-043
        raise ValueError(
            f"Evaluator type '{eval_type}' is a Tier 2 evaluator (see FEAT-044)"
        )

    else:
        raise ValueError(f"Unknown evaluator type: {eval_type}")

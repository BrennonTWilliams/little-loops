"""FSM Evaluators for loop execution.

This module provides evaluators that interpret action output and produce
verdicts for state transitions.

Supported evaluator types:

Tier 1 (Deterministic - no API calls):
    exit_code: Map Unix exit codes to verdicts (0=success, 1=failure, 2+=error)
    output_numeric: Compare numeric output to target value
    output_json: Extract and compare JSON path values
    output_contains: Pattern matching on stdout
    convergence: Track progress toward a target value

Tier 2 (LLM-based):
    llm_structured: Use LLM with structured output for natural language evaluation
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any

# Optional import for LLM evaluator
try:
    import anthropic

    ANTHROPIC_AVAILABLE = True
except ImportError:
    anthropic = None  # type: ignore[assignment]
    ANTHROPIC_AVAILABLE = False

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


# Default schema for LLM structured evaluation
DEFAULT_LLM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["success", "failure", "blocked", "partial"],
            "description": (
                "- success: The action completed its goal\n"
                "- failure: The action failed, should retry\n"
                "- blocked: Cannot proceed without external help\n"
                "- partial: Made progress but not complete"
            ),
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence in this verdict (0-1)",
        },
        "reason": {
            "type": "string",
            "description": "Brief explanation",
        },
    },
    "required": ["verdict", "confidence", "reason"],
}

DEFAULT_LLM_PROMPT = "Evaluate whether this action succeeded based on its output."


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


def evaluate_llm_structured(
    output: str,
    prompt: str | None = None,
    schema: dict[str, Any] | None = None,
    min_confidence: float = 0.5,
    uncertain_suffix: bool = False,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 256,
    timeout: int = 30,
) -> EvaluationResult:
    """Evaluate action output using LLM with structured output.

    This is the ONLY place in the FSM system that uses LLM structured output.
    Requires the anthropic package to be installed (pip install little-loops[llm]).

    Args:
        output: Action stdout to evaluate
        prompt: Custom evaluation prompt (defaults to basic success check)
        schema: Custom JSON schema for structured response
        min_confidence: Minimum confidence threshold (0-1)
        uncertain_suffix: If True, append _uncertain to low-confidence verdicts
        model: Model identifier for API calls
        max_tokens: Maximum tokens for response
        timeout: Timeout in seconds

    Returns:
        EvaluationResult with verdict from LLM and confidence/reason in details
    """
    if not ANTHROPIC_AVAILABLE or anthropic is None:
        return EvaluationResult(
            verdict="error",
            details={
                "error": "anthropic package not installed. Install with: pip install little-loops[llm]",
                "missing_dependency": True,
            },
        )

    try:
        client = anthropic.Anthropic()
    except anthropic.AuthenticationError as e:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Anthropic authentication error: {e}", "auth_error": True},
        )

    effective_schema = schema or DEFAULT_LLM_SCHEMA
    effective_prompt = prompt or DEFAULT_LLM_PROMPT

    # Truncate output to avoid context limits (keep last 4000 chars)
    truncated = output[-4000:] if len(output) > 4000 else output

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            timeout=timeout,
            messages=[
                {
                    "role": "user",
                    "content": f"{effective_prompt}\n\n<action_output>\n{truncated}\n</action_output>",
                }
            ],
            tools=[
                {
                    "name": "evaluate",
                    "description": "Provide your evaluation of the action result",
                    "input_schema": effective_schema,
                }
            ],
            tool_choice={"type": "tool", "name": "evaluate"},
        )
    except anthropic.APITimeoutError:
        return EvaluationResult(
            verdict="error",
            details={"error": "LLM evaluation timeout", "timeout": True},
        )
    except anthropic.APIError as e:
        return EvaluationResult(
            verdict="error",
            details={"error": f"LLM API error: {e}", "api_error": True},
        )

    # Extract structured result from tool use
    llm_result: dict[str, Any] | None = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "evaluate":
            llm_result = block.input  # type: ignore[assignment]
            break

    if llm_result is None:
        return EvaluationResult(
            verdict="error",
            details={"error": "No evaluation in LLM response"},
        )

    # Build result with confidence handling
    verdict = str(llm_result.get("verdict", "error"))
    confidence = float(llm_result.get("confidence", 1.0))
    confident = confidence >= min_confidence

    # Optionally modify verdict for low confidence
    if uncertain_suffix and not confident:
        verdict = f"{verdict}_uncertain"

    return EvaluationResult(
        verdict=verdict,
        details={
            "confidence": confidence,
            "confident": confident,
            "reason": llm_result.get("reason", ""),
            "raw": llm_result,
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
        return evaluate_llm_structured(
            output=output,
            prompt=config.prompt,
            schema=config.schema,
            min_confidence=config.min_confidence,
            uncertain_suffix=config.uncertain_suffix,
        )

    else:
        raise ValueError(f"Unknown evaluator type: {eval_type}")

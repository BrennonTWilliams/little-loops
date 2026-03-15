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
    diff_stall: Detect stalled iterations via git diff comparison

Tier 2 (LLM-based):
    llm_structured: Use LLM with structured output for natural language evaluation
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import time
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    interpolate,
)
from little_loops.fsm.schema import DEFAULT_LLM_MODEL, EvaluateConfig


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
            "enum": ["yes", "no", "blocked", "partial"],
            "description": (
                "- yes: The condition/check evaluated to true\n"
                "- no: The condition/check evaluated to false\n"
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

_NUMERIC_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "eq": lambda v, t: v == t,
    "ne": lambda v, t: v != t,
    "lt": lambda v, t: v < t,
    "le": lambda v, t: v <= t,
    "gt": lambda v, t: v > t,
    "ge": lambda v, t: v >= t,
}


def evaluate_exit_code(exit_code: int) -> EvaluationResult:
    """Map Unix exit code to verdict.

    Args:
        exit_code: The process exit code

    Returns:
        EvaluationResult with verdict:
            - 0 -> yes
            - 1 -> no
            - 2+ -> error
    """
    if exit_code == 0:
        verdict = "yes"
    elif exit_code == 1:
        verdict = "no"
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
            - Condition met -> yes
            - Condition not met -> no
            - Parse error -> error
    """
    try:
        value = float(output.strip())
    except ValueError:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Cannot parse as number: {output[:100]}"},
        )

    if operator not in _NUMERIC_OPERATORS:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Unknown operator: {operator}"},
        )

    condition_met = _NUMERIC_OPERATORS[operator](value, target)
    return EvaluationResult(
        verdict="yes" if condition_met else "no",
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
    if operator not in _NUMERIC_OPERATORS:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Unknown operator: {operator}"},
        )

    condition_met = _NUMERIC_OPERATORS[operator](value, target)
    return EvaluationResult(
        verdict="yes" if condition_met else "no",
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
            - Condition met -> yes
            - Condition not met -> no
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
        verdict = "yes" if value == target else "no"
    elif operator == "ne":
        verdict = "yes" if value != target else "no"
    else:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Operator {operator} not supported for non-numeric values"},
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
            - Found (negate=False) -> yes
            - Found (negate=True) -> no
            - Not found (negate=False) -> no
            - Not found (negate=True) -> yes
    """
    # Try regex first, fall back to substring
    try:
        matched = bool(re.search(pattern, output))
    except re.error:
        matched = pattern in output

    if negate:
        verdict = "no" if matched else "yes"
    else:
        verdict = "yes" if matched else "no"

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


def evaluate_diff_stall(
    scope: list[str] | None = None,
    max_stall: int = 1,
) -> EvaluationResult:
    """Detect stalled iterations by comparing git diff --stat between runs.

    On first call, snapshots the current diff and returns 'yes'.
    On subsequent calls, compares current diff to the previous snapshot.
    If the diff is identical for max_stall consecutive iterations, returns
    'no' (stalled). If different, resets the stall counter and returns
    'yes' (progress).

    State is persisted in /tmp using a key derived from the scope argument,
    so different loops with different scopes maintain independent stall counters.

    Args:
        scope: Optional list of paths to limit the git diff to. Defaults to
            the entire working tree.
        max_stall: Number of consecutive no-change iterations before stall
            verdict. Defaults to 1.

    Returns:
        EvaluationResult with verdict:
            - yes: diff changed since last iteration (progress made)
            - no: diff unchanged for max_stall iterations (stalled)
            - error: git command failed or timed out
    """
    cmd = ["git", "diff", "--stat"]
    if scope:
        cmd += ["--"] + scope

    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return EvaluationResult(verdict="error", details={"error": "git diff timed out"})
    except FileNotFoundError:
        return EvaluationResult(verdict="error", details={"error": "git not found in PATH"})

    if proc.returncode != 0:
        return EvaluationResult(
            verdict="error",
            details={"error": f"git diff failed: {proc.stderr[:200]}"},
        )

    current_diff = proc.stdout

    # Derive a stable cache key from the scope so independent loops don't collide
    scope_str = "|".join(sorted(scope)) if scope else "_root_"
    cache_key = hashlib.md5(scope_str.encode()).hexdigest()[:12]
    state_file = Path(f"/tmp/ll-diff-stall-{cache_key}.txt")
    count_file = Path(f"/tmp/ll-diff-stall-{cache_key}.count")

    # Read previous snapshot and stall count
    previous_diff: str | None = None
    stall_count = 0
    try:
        previous_diff = state_file.read_text()
        stall_count = int(count_file.read_text().strip())
    except (FileNotFoundError, ValueError):
        pass

    # First iteration: save snapshot and report progress
    if previous_diff is None:
        state_file.write_text(current_diff)
        count_file.write_text("0")
        return EvaluationResult(
            verdict="yes",
            details={"stall_count": 0, "max_stall": max_stall, "diff_changed": True},
        )

    if current_diff == previous_diff:
        stall_count += 1
        count_file.write_text(str(stall_count))
        if stall_count >= max_stall:
            return EvaluationResult(
                verdict="no",
                details={"stall_count": stall_count, "max_stall": max_stall, "diff_changed": False},
            )
        # Not yet at max_stall threshold — still report yes so loop continues
        return EvaluationResult(
            verdict="yes",
            details={"stall_count": stall_count, "max_stall": max_stall, "diff_changed": False},
        )
    else:
        # Progress: update snapshot and reset counter
        state_file.write_text(current_diff)
        count_file.write_text("0")
        return EvaluationResult(
            verdict="yes",
            details={"stall_count": 0, "max_stall": max_stall, "diff_changed": True},
        )


def evaluate_mcp_result(output: str, exit_code: int) -> EvaluationResult:
    """Evaluate an MCP tool call result from the mcp-call subprocess.

    Maps exit codes and MCP response envelope fields to routing verdicts.

    Exit code conventions (set by mcp-call):
        0   → parse isError from JSON envelope
        1   → tool_error (tool ran but isError: true)
        124 → timeout (transport-level timeout)
        127 → not_found (server or tool missing from .mcp.json)

    Args:
        output: stdout from mcp-call (MCP response envelope JSON)
        exit_code: Exit code from mcp-call subprocess

    Returns:
        EvaluationResult with verdict:
            - success    → isError: false
            - tool_error → isError: true
            - not_found  → server/tool not in .mcp.json (exit 127)
            - timeout    → transport-level timeout (exit 124)
    """
    if exit_code == 127:
        return EvaluationResult(
            verdict="not_found",
            details={"exit_code": exit_code, "error": "Server or tool not found in .mcp.json"},
        )

    if exit_code == 124:
        return EvaluationResult(
            verdict="timeout",
            details={"exit_code": exit_code, "error": "MCP tool call timed out"},
        )

    # Parse MCP envelope JSON from stdout
    try:
        envelope = json.loads(output.strip()) if output.strip() else {}
    except json.JSONDecodeError:
        return EvaluationResult(
            verdict="tool_error",
            details={"exit_code": exit_code, "error": f"Invalid JSON from mcp-call: {output[:200]}"},
        )

    is_error = envelope.get("isError", exit_code != 0)

    if is_error:
        return EvaluationResult(
            verdict="tool_error",
            details={"exit_code": exit_code, "envelope": envelope},
        )

    return EvaluationResult(
        verdict="success",
        details={"exit_code": exit_code, "envelope": envelope},
    )


def evaluate_llm_structured(
    output: str,
    prompt: str | None = None,
    schema: dict[str, Any] | None = None,
    min_confidence: float = 0.5,
    uncertain_suffix: bool = False,
    model: str = DEFAULT_LLM_MODEL,
    max_tokens: int = 256,
    timeout: int = 30,
) -> EvaluationResult:
    """Evaluate action output using LLM with structured output via Claude CLI.

    This is the ONLY place in the FSM system that uses LLM structured output.
    Requires the ``claude`` CLI to be installed and authenticated.

    Args:
        output: Action stdout to evaluate
        prompt: Custom evaluation prompt (defaults to basic success check)
        schema: Custom JSON schema for structured response
        min_confidence: Minimum confidence threshold (0-1)
        uncertain_suffix: If True, append _uncertain to low-confidence verdicts
        model: Model identifier (CLI aliases like "sonnet" or full names)
        max_tokens: Maximum tokens for response (passed to --max-turns is not
            applicable; kept for signature compat)
        timeout: Timeout in seconds

    Returns:
        EvaluationResult with verdict from LLM and confidence/reason in details
    """
    effective_schema = schema or DEFAULT_LLM_SCHEMA
    effective_prompt = prompt or DEFAULT_LLM_PROMPT

    # Truncate output to avoid context limits (keep last 4000 chars)
    truncated = output[-4000:] if len(output) > 4000 else output

    user_prompt = (
        f"{effective_prompt}\n\n"
        f"<action_output>\n{truncated}\n</action_output>\n\n"
        f"Respond with ONLY valid JSON (no markdown fences, no explanation) "
        f"matching this schema:\n{json.dumps(effective_schema)}"
    )

    cmd = [
        "claude",
        "-p",
        user_prompt,
        "--output-format",
        "json",
        "--model",
        model,
        "--dangerously-skip-permissions",
        "--no-session-persistence",
    ]

    t0 = time.monotonic()
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout)
    except subprocess.TimeoutExpired:
        return EvaluationResult(
            verdict="error",
            details={"error": "LLM evaluation timeout", "timeout": True},
        )
    except FileNotFoundError:
        return EvaluationResult(
            verdict="error",
            details={
                "error": "claude CLI not found. Install from https://docs.anthropic.com/en/docs/claude-code",
                "missing_dependency": True,
            },
        )
    llm_latency_ms = int((time.monotonic() - t0) * 1000)

    if proc.returncode != 0:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Claude CLI error: {proc.stderr.strip()}", "api_error": True},
        )

    # Guard: empty stdout with exit 0 (API error not reflected in exit code)
    if not proc.stdout.strip():
        stderr_info = proc.stderr.strip()[:200] if proc.stderr else ""
        error_msg = "Claude CLI returned empty output"
        if stderr_info:
            error_msg += f" (stderr: {stderr_info})"
        return EvaluationResult(
            verdict="error",
            details={"error": error_msg, "empty_output": True},
        )

    # Parse the CLI JSON envelope and extract structured result.
    # The envelope format is {"result": "<json-string>", "is_error": false, ...}.
    # Some CLI versions set is_error=true with exit 0, or return result as a dict.
    # If stdout is JSONL (multiple JSON objects), use the last non-empty line.
    try:
        stdout = proc.stdout.strip()
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            # Try JSONL: take the last non-empty line
            lines = [line for line in stdout.split("\n") if line.strip()]
            if not lines:
                raise
            envelope = json.loads(lines[-1])

        # Check is_error flag (some CLI versions exit 0 but report error in envelope)
        if envelope.get("is_error", False):
            err_text = str(envelope.get("result", "") or "")[:200]
            return EvaluationResult(
                verdict="error",
                details={"error": f"Claude CLI reported error: {err_text}", "api_error": True},
            )

        raw_result = envelope.get("result", "")
        if isinstance(raw_result, dict):
            # Some CLI versions embed the structured object directly
            llm_result: dict[str, Any] = raw_result
        elif raw_result:
            llm_result = json.loads(raw_result)
        else:
            # Fallback: some CLI versions return the structured JSON directly at
            # the top level without a "result" wrapper.
            if "verdict" in envelope:
                llm_result = envelope
            else:
                raw_preview = proc.stdout[:300]
                return EvaluationResult(
                    verdict="error",
                    details={
                        "error": "Empty result field in Claude CLI response",
                        "raw_preview": raw_preview,
                    },
                )
    except (json.JSONDecodeError, TypeError, ValueError) as e:
        raw_preview = proc.stdout[:300] if proc.stdout else "(empty)"
        return EvaluationResult(
            verdict="error",
            details={"error": f"Failed to parse LLM response: {e}", "raw_preview": raw_preview},
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
            "llm_model": model,
            "llm_latency_ms": llm_latency_ms,
            "llm_prompt": user_prompt[:500],
            "llm_raw_output": proc.stdout[:500] if proc.stdout else "",
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
        if config.target is None:
            raise ValueError("output_numeric evaluator requires 'target' to be set")
        elif isinstance(config.target, str):
            try:
                resolved = interpolate(config.target, context) if context else config.target
                numeric_target = float(resolved)
            except (InterpolationError, ValueError) as e:
                raise ValueError(
                    f"output_numeric target must be numeric, got: {config.target!r}"
                ) from e
        else:
            numeric_target = float(config.target)
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
            if config.target is None:
                raise ValueError("convergence evaluator requires 'target' to be set")
            convergence_target = float(config.target)

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

    elif eval_type == "diff_stall":
        return evaluate_diff_stall(
            scope=config.scope,
            max_stall=config.max_stall,
        )

    elif eval_type == "llm_structured":
        return evaluate_llm_structured(
            output=output,
            prompt=config.prompt,
            schema=config.schema,
            min_confidence=config.min_confidence,
            uncertain_suffix=config.uncertain_suffix,
        )

    elif eval_type == "mcp_result":
        return evaluate_mcp_result(output=output, exit_code=exit_code)

    else:
        raise ValueError(f"Unknown evaluator type: {eval_type}")

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
    action_stall: Detect when the same action string or output repeats for N consecutive iterations
    harbor_scorer: Interpret Harbor-format benchmark scorer exit code and float stdout

Tier 2 (LLM-based):
    llm_structured: Use LLM with structured output for natural language evaluation
    contract: Read producer/consumer file pairs and assert contract alignment via LLM judge

Tier 3 (External process):
    mcp_result: Parse MCP tool call response envelope
"""

from __future__ import annotations

import hashlib
import json
import random
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
from little_loops.host_runner import resolve_host


@dataclass
class EvaluationResult:
    """Result from an evaluator.

    Attributes:
        verdict: The routing key for state transitions
        details: Evaluator-specific metadata for debugging/logging
    """

    verdict: str
    details: dict[str, Any]


# Evidence contract injected into every LLM evaluator prompt (ENH-2342).
# Requires the model to cite verbatim output text for each verdict; absent evidence
# is coerced to "no" at the parsing layer so self-grade optimism can't slip through.
CHECK_SEMANTIC_EVIDENCE_CONTRACT = """
IMPORTANT: For each condition you evaluate:
1. State your verdict: Yes / No / Partial
2. Provide a VERBATIM quote from the output that supports your verdict (exact text, in quotes)
3. If you cannot quote specific text, your verdict is automatically No (or Partial if context suggests partial progress)

Do not assert a verdict without evidence. "The task appears complete" is not evidence.
"""

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
        "evidence": {
            "type": "string",
            "description": (
                "Verbatim quote from the action output that supports the verdict. "
                "Empty string means no evidence was found; verdict will be coerced to 'no'."
            ),
        },
    },
    "required": ["verdict", "confidence", "reason", "evidence"],
}

DEFAULT_LLM_PROMPT = "Evaluate whether this action succeeded based on its output."


def _extract_tagged_structured_output(text: str) -> dict[str, Any] | None:
    """Mine a ``<StructuredOutput>`` tag block for a verdict dict.

    Anthropic's ``claude`` CLI honors ``--json-schema`` and returns the parsed
    verdict in the envelope's ``structured_output`` field. Non-Anthropic hosts
    reached through the same CLI (e.g. a MiniMax backend) ignore the flag and
    instead emit the verdict as ``<StructuredOutput><verdict>…</verdict>…`` tags
    inside the envelope's ``result`` string. This fallback recovers the verdict
    from that tag format so the same evaluators work host-agnostically.

    Args:
        text: The raw ``result`` string that failed JSON parsing.

    Returns:
        A dict shaped like the default LLM schema output (``verdict``,
        ``confidence``, ``reason``, ``evidence``) when a ``<verdict>`` tag is
        present, else ``None``. Fields absent from the tags are omitted so the
        caller's downstream defaults/coercion apply unchanged.
    """
    # Strip a ```json / ``` fence if a proxy wrapped the tags in one.
    fenced = re.search(r"```(?:json)?\s*(.*?)\s*```", text, re.DOTALL | re.IGNORECASE)
    if fenced:
        text = fenced.group(1)

    verdict_match = re.search(r"<verdict>\s*(.*?)\s*</verdict>", text, re.DOTALL | re.IGNORECASE)
    if not verdict_match:
        return None

    result: dict[str, Any] = {"verdict": verdict_match.group(1).strip().lower()}

    conf_match = re.search(r"<confidence>\s*(.*?)\s*</confidence>", text, re.DOTALL | re.IGNORECASE)
    if conf_match:
        try:
            result["confidence"] = float(conf_match.group(1).strip())
        except ValueError:
            pass  # leave unset; caller defaults confidence to 1.0

    reason_match = re.search(r"<reason>\s*(.*?)\s*</reason>", text, re.DOTALL | re.IGNORECASE)
    if reason_match:
        result["reason"] = reason_match.group(1).strip()

    evidence_match = re.search(r"<evidence>\s*(.*?)\s*</evidence>", text, re.DOTALL | re.IGNORECASE)
    if evidence_match:
        result["evidence"] = evidence_match.group(1).strip()

    return result


# Schema for blind A/B comparator: evaluates two anonymized outputs
BLIND_COMPARATOR_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict_a": {
            "type": "string",
            "enum": ["yes", "no"],
            "description": "Whether Output A meets the evaluation criteria",
        },
        "verdict_b": {
            "type": "string",
            "enum": ["yes", "no"],
            "description": "Whether Output B meets the evaluation criteria",
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence in these verdicts (0-1)",
        },
        "reason": {
            "type": "string",
            "description": "Brief explanation comparing the two outputs",
        },
    },
    "required": ["verdict_a", "verdict_b", "confidence", "reason"],
}

DEFAULT_BLIND_COMPARATOR_PROMPT = (
    "You are evaluating two outputs (labeled 'Output A' and 'Output B') that were "
    "produced by independent runs of the same task. Judge whether each output meets "
    "the evaluation criteria below. Be objective and impartial — the labels 'A' and "
    "'B' are arbitrary and do not indicate which is better."
)

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
    error_patterns: list[str] | None = None,
) -> EvaluationResult:
    """Check if pattern exists in output.

    Pattern can be regex or substring. If regex fails to compile,
    falls back to substring matching.

    Args:
        output: The action stdout to search
        pattern: Regex pattern or substring
        negate: If True, invert the match result
        error_patterns: Optional list of substrings that, when matched in output
            and the main pattern is not found, yield verdict="error". This allows
            loops to route auth/error output to on_error without raising an exception.

    Returns:
        EvaluationResult with verdict:
            - Found (negate=False) -> yes
            - Found (negate=True) -> no
            - Not found (negate=False) -> no (or "error" if error_patterns matched)
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

    # Check error_patterns before returning "no" — only when main pattern didn't match
    if verdict == "no" and not negate and error_patterns:
        for ep in error_patterns:
            if ep in output:
                return EvaluationResult(
                    verdict="error",
                    details={
                        "matched": False,
                        "pattern": pattern,
                        "negate": negate,
                        "error_pattern": ep,
                    },
                )

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


def evaluate_classify(
    output: str,
    line: str | int | None = None,
) -> EvaluationResult:
    """Read a token from stdout and return it as the verdict.

    Intended for single-state multi-way routing: the action prints exactly one
    token to stdout and the route: table maps that token to the next state.

    Args:
        output: The action stdout to read the token from
        line: Which line to select. 'last' (default) picks the last non-empty
              line; 'first' picks the first non-empty line; an integer index
              selects that line (0-based, negative indices supported).

    Returns:
        EvaluationResult with verdict = trimmed token, or "" when output is
        empty (which _route() maps to the route.default fallback).
    """
    lines = [ln for ln in output.splitlines() if ln.strip()]
    if not lines:
        return EvaluationResult(
            verdict="",
            details={"token": "", "line": line, "source_lines": 0},
        )

    selector = line if line is not None else "last"
    if selector == "last":
        selected = lines[-1]
    elif selector == "first":
        selected = lines[0]
    elif isinstance(selector, int):
        try:
            selected = lines[selector]
        except IndexError:
            return EvaluationResult(
                verdict="",
                details={
                    "token": "",
                    "line": line,
                    "source_lines": len(lines),
                    "error": "index out of range",
                },
            )
    else:
        selected = lines[-1]

    token = selected.strip()
    return EvaluationResult(
        verdict=token,
        details={"token": token, "line": line},
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
    loops_tmp = Path.cwd() / ".loops" / "tmp"
    loops_tmp.mkdir(parents=True, exist_ok=True)
    state_file = loops_tmp / f"ll-diff-stall-{cache_key}.txt"
    count_file = loops_tmp / f"ll-diff-stall-{cache_key}.count"

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


def evaluate_score_stall(
    history_file: str,
    max_stall: int = 1,
    epsilon: float = 0.5,
) -> EvaluationResult:
    """Detect a scored-output plateau by reading a per-round score-history file.

    The history file holds one numeric rubric score per line (the aggregate for
    each refine round), appended by the loop's score state under
    ${context.run_dir}/. This evaluator reads the full history and tracks the
    running best-so-far: a round counts as *progress* only when its score exceeds
    the previous best by more than epsilon (which resets the stall counter);
    otherwise the stall counter increments. When the counter reaches max_stall
    consecutive non-improving rounds the scores have plateaued and the evaluator
    returns 'no' (accept best-so-far / stop).

    Unlike diff_stall, this evaluator is stateless across calls — the history
    file itself is the persisted state, so a test can feed a flat score history
    and assert the plateau verdict deterministically.

    Args:
        history_file: Path to the newline-delimited score-history file.
        max_stall: Consecutive non-improving rounds before a stall verdict.
        epsilon: Minimum improvement over best-so-far counted as progress.

    Returns:
        EvaluationResult with verdict:
            - yes: scores still improving, or not enough history yet (continue)
            - no: scores plateaued for max_stall consecutive rounds (stop)
    """
    path = Path(history_file)
    scores: list[float] = []
    try:
        raw = path.read_text()
    except (FileNotFoundError, OSError):
        raw = ""

    for line in raw.splitlines():
        token = line.strip()
        if not token:
            continue
        try:
            scores.append(float(token))
        except ValueError:
            continue

    # Not enough history to judge a plateau — keep going.
    if len(scores) < 2:
        return EvaluationResult(
            verdict="yes",
            details={
                "stall_count": 0,
                "max_stall": max_stall,
                "epsilon": epsilon,
                "rounds": len(scores),
                "best": scores[-1] if scores else None,
            },
        )

    best = scores[0]
    stall = 0
    for score in scores[1:]:
        if score > best + epsilon:
            best = score
            stall = 0
        else:
            if score > best:
                best = score
            stall += 1

    verdict = "no" if stall >= max_stall else "yes"
    return EvaluationResult(
        verdict=verdict,
        details={
            "stall_count": stall,
            "max_stall": max_stall,
            "epsilon": epsilon,
            "rounds": len(scores),
            "best": best,
        },
    )


def evaluate_open_question_stall(
    history_file: str,
    max_stall: int = 1,
    epsilon: float = 0.0,
) -> EvaluationResult:
    """Detect an open-question-count plateau by reading a per-round count-history file (ENH-2446).

    Companion to :func:`evaluate_score_stall`. Where score_stall tracks the
    running *best* (higher = better), open_question_stall tracks the running
    *minimum* (lower = better — open questions being resolved is progress).
    A round counts as *progress* only when its count is strictly less than the
    previous minimum by more than epsilon; otherwise the stall counter
    increments. When the counter reaches ``max_stall`` consecutive
    non-progress rounds the open-question reduction has plateaued and the
    evaluator returns ``no`` (stop refining and let ``decide`` / ``emit_needs_manual_review``
    surface). Mirrors the ENH-2428 score_stall pattern; inverts the direction
    of progress so the same stall-plateau semantics apply.

    Args:
        history_file: Path to the newline-delimited open-question-count history file.
        max_stall: Consecutive non-progress rounds before a stall verdict.
        epsilon: Minimum count reduction (relative to min-so-far) counted as progress.

    Returns:
        EvaluationResult with verdict:
            - yes: counts still decreasing, or not enough history yet (continue)
            - no: counts plateaued for ``max_stall`` consecutive rounds (stop)
    """
    path = Path(history_file)
    counts: list[float] = []
    try:
        raw = path.read_text()
    except (FileNotFoundError, OSError):
        raw = ""

    for line in raw.splitlines():
        token = line.strip()
        if not token:
            continue
        try:
            counts.append(float(token))
        except ValueError:
            continue

    # Not enough history to judge a plateau — keep going.
    if len(counts) < 2:
        return EvaluationResult(
            verdict="yes",
            details={
                "stall_count": 0,
                "max_stall": max_stall,
                "epsilon": epsilon,
                "rounds": len(counts),
                "best": counts[-1] if counts else None,
            },
        )

    best = counts[0]
    stall = 0
    for count in counts[1:]:
        if count < best - epsilon:
            best = count
            stall = 0
        else:
            if count < best:
                best = count
            stall += 1

    verdict = "no" if stall >= max_stall else "yes"
    return EvaluationResult(
        verdict=verdict,
        details={
            "stall_count": stall,
            "max_stall": max_stall,
            "epsilon": epsilon,
            "rounds": len(counts),
            "best": best,
        },
    )


def evaluate_action_stall(
    track: list[str] | None = None,
    max_repeat: int = 2,
    context: InterpolationContext | None = None,
) -> EvaluationResult:
    """Detect when the same action string or output repeats for N consecutive iterations.

    On first call, snapshots the hashed values of the tracked context keys and returns
    'yes'. On subsequent calls, compares the current hash to the previous snapshot.
    If the hash is identical for max_repeat consecutive iterations, returns 'no'
    (stalled). If different, resets the stall counter and returns 'yes' (progress).

    State is persisted in .loops/tmp using a key derived from the tracked keys,
    so different states/loops maintain independent stall counters.

    Args:
        track: Context keys to track. Defaults to ["action"] when None.
        max_repeat: Number of consecutive identical-hash iterations before stall verdict.
            Defaults to 2.
        context: Runtime interpolation context for resolving tracked keys.

    Returns:
        EvaluationResult with verdict:
            - yes: tracked values changed since last iteration (progress made)
            - no: tracked values identical for max_repeat iterations (stalled)
    """
    effective_track: list[str] = track if track is not None else ["action"]

    # Resolve each tracked key from context and hash the combined values.
    # Keys may be bare names (e.g. "action") or namespaced (e.g. "context.action").
    # Try namespaced forms first: context.<key>, captured.<key>, then bare ${key}.
    parts: list[str] = []
    for key in effective_track:
        value: str = ""
        if context is not None:
            # If key already contains a dot it's already namespaced; use as-is.
            if "." in key:
                try:
                    value = str(interpolate(f"${{{key}}}", context))
                except InterpolationError:
                    value = ""
            else:
                # Try context.<key> first, then captured.<key>, then give up.
                resolved = False
                for namespace in ("context", "captured", "prev", "result"):
                    try:
                        value = str(interpolate(f"${{{namespace}.{key}}}", context))
                        resolved = True
                        break
                    except InterpolationError:
                        continue
                if not resolved:
                    value = ""
        parts.append(f"{key}={value}")

    combined = "|".join(parts)
    current_hash = hashlib.md5(combined.encode()).hexdigest()

    # Derive a stable cache key from the tracked keys
    track_str = "|".join(sorted(effective_track))
    cache_key = hashlib.md5(track_str.encode()).hexdigest()[:12]
    loops_tmp = Path.cwd() / ".loops" / "tmp"
    loops_tmp.mkdir(parents=True, exist_ok=True)
    state_file = loops_tmp / f"ll-action-stall-{cache_key}.txt"
    count_file = loops_tmp / f"ll-action-stall-{cache_key}.count"

    # Read previous hash and stall count
    previous_hash: str | None = None
    stall_count = 0
    try:
        previous_hash = state_file.read_text().strip()
        stall_count = int(count_file.read_text().strip())
    except (FileNotFoundError, ValueError):
        pass

    # First iteration: save hash and report progress
    if previous_hash is None:
        state_file.write_text(current_hash)
        count_file.write_text("0")
        return EvaluationResult(
            verdict="yes",
            details={
                "stall_count": 0,
                "max_repeat": max_repeat,
                "hash_changed": True,
                "tracked_keys": effective_track,
            },
        )

    hash_changed = current_hash != previous_hash

    if hash_changed:
        # Progress: update snapshot and reset counter
        state_file.write_text(current_hash)
        count_file.write_text("0")
        return EvaluationResult(
            verdict="yes",
            details={
                "stall_count": 0,
                "max_repeat": max_repeat,
                "hash_changed": True,
                "tracked_keys": effective_track,
            },
        )
    else:
        # Same hash as last time
        stall_count += 1
        count_file.write_text(str(stall_count))
        if stall_count >= max_repeat:
            return EvaluationResult(
                verdict="no",
                details={
                    "stall_count": stall_count,
                    "max_repeat": max_repeat,
                    "hash_changed": False,
                    "tracked_keys": effective_track,
                    "repeated_hash": current_hash,
                },
            )
        # Not yet at max_repeat threshold — still report yes so loop continues
        return EvaluationResult(
            verdict="yes",
            details={
                "stall_count": stall_count,
                "max_repeat": max_repeat,
                "hash_changed": False,
                "tracked_keys": effective_track,
            },
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
            details={
                "exit_code": exit_code,
                "error": f"Invalid JSON from mcp-call: {output[:200]}",
            },
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


def evaluate_harbor_scorer(output: str, exit_code: int) -> EvaluationResult:
    """Evaluate a Harbor-format benchmark scorer result.

    The scorer is a shell command that prints a float score (0.0–1.0) to stdout
    and exits 0 on success or non-zero on failure.

    Args:
        output: stdout from the scorer subprocess (expected: a bare float)
        exit_code: Exit code from the scorer subprocess

    Returns:
        EvaluationResult with verdict:
            - yes   → exit 0 and stdout parses as a float
            - no    → exit non-zero (scorer determined failure)
            - error → exit 0 but stdout is not parseable as a float
    """
    if exit_code != 0:
        return EvaluationResult(
            verdict="no",
            details={"exit_code": exit_code},
        )

    try:
        score = float(output.strip())
    except (ValueError, AttributeError):
        return EvaluationResult(
            verdict="error",
            details={
                "exit_code": exit_code,
                "error": f"Scorer stdout is not a float: {output[:200]}",
            },
        )

    return EvaluationResult(
        verdict="yes",
        details={"score": score, "exit_code": 0},
    )


def evaluate_llm_structured(
    output: str,
    prompt: str | None = None,
    schema: dict[str, Any] | None = None,
    min_confidence: float = 0.5,
    uncertain_suffix: bool = False,
    model: str = DEFAULT_LLM_MODEL,
    max_tokens: int = 256,
    timeout: int = 1800,
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
    effective_prompt = (prompt or DEFAULT_LLM_PROMPT) + "\n\n" + CHECK_SEMANTIC_EVIDENCE_CONTRACT

    # Truncate output to avoid context limits (keep last 4000 chars)
    truncated = output[-4000:] if len(output) > 4000 else output

    user_prompt = f"{effective_prompt}\n\n<action_output>\n{truncated}\n</action_output>"

    invocation = resolve_host().build_blocking_json(prompt=user_prompt, model=model)
    # Builder drops json_schema (Protocol surface only) and omits the
    # claude-CLI-specific --no-session-persistence flag; augment at call site.
    args = list(invocation.args) + [
        "--json-schema",
        json.dumps(effective_schema),
        "--no-session-persistence",
    ]

    t0 = time.monotonic()
    try:
        proc = subprocess.run(
            [invocation.binary, *args], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        return EvaluationResult(
            verdict="error",
            details={"error": "LLM evaluation timeout", "timeout": True},
        )
    except FileNotFoundError:
        return EvaluationResult(
            verdict="error",
            details={
                "error": f"{invocation.binary} CLI not found. Install the active host CLI (see LL_HOST_CLI).",
                "missing_dependency": True,
            },
        )
    llm_latency_ms = int((time.monotonic() - t0) * 1000)

    if proc.returncode != 0:
        return EvaluationResult(
            verdict="error",
            details={
                "error": f"{invocation.binary} CLI error: {proc.stderr.strip()}",
                "api_error": True,
            },
        )

    # Guard: empty stdout with exit 0 (API error not reflected in exit code)
    if not proc.stdout.strip():
        stderr_info = proc.stderr.strip()[:200] if proc.stderr else ""
        error_msg = f"{invocation.binary} CLI returned empty output"
        if stderr_info:
            error_msg += f" (stderr: {stderr_info})"
        return EvaluationResult(
            verdict="error",
            details={"error": error_msg, "empty_output": True},
        )

    # Parse the CLI JSON envelope and extract structured result.
    # With --json-schema the envelope is:
    #   success: {"type":"result","subtype":"success","structured_output":{...},...}
    #   failure: {"type":"result","subtype":"error_max_structured_output_retries",...}
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

        # Check structured-output retry exhaustion (--json-schema failure mode)
        if envelope.get("subtype") == "error_max_structured_output_retries":
            return EvaluationResult(
                verdict="error",
                details={
                    "error": "Claude CLI could not produce valid structured output after retries",
                    "api_error": True,
                },
            )

        # Check legacy is_error flag (some CLI versions exit 0 but report error in envelope)
        if envelope.get("is_error", False):
            err_text = str(envelope.get("result", "") or "")[:200]
            return EvaluationResult(
                verdict="error",
                details={"error": f"Claude CLI reported error: {err_text}", "api_error": True},
            )

        # --json-schema mode returns validated dict in "structured_output"
        if isinstance(envelope.get("structured_output"), dict):
            llm_result: dict[str, Any] = envelope["structured_output"]
        else:
            raw_result = envelope.get("result", "")
            if isinstance(raw_result, dict):
                llm_result = raw_result
            elif raw_result:
                try:
                    llm_result = json.loads(raw_result)
                except json.JSONDecodeError:
                    # Non-Anthropic hosts (e.g. MiniMax via the claude CLI) ignore
                    # --json-schema and emit the verdict as <StructuredOutput> tags
                    # inside "result" rather than a JSON string. Recover it before
                    # treating the response as unparseable.
                    tagged = _extract_tagged_structured_output(raw_result)
                    if tagged is None:
                        raise
                    llm_result = tagged
            elif "verdict" in envelope:
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

    # Evidence coercion (ENH-2342): when using the default schema, a verdict without
    # verbatim evidence is treated as "no" — prevents LLM optimism from passing silently.
    # Custom schemas bypass this; callers that supply their own schema control the contract.
    evidence = llm_result.get("evidence", "")
    evidence_coerced = schema is None and not evidence.strip() and verdict not in ("error",)
    if evidence_coerced:
        verdict = "no"

    # Optionally modify verdict for low confidence
    if uncertain_suffix and not confident:
        verdict = f"{verdict}_uncertain"

    return EvaluationResult(
        verdict=verdict,
        details={
            "confidence": confidence,
            "confident": confident,
            "reason": llm_result.get("reason", ""),
            "evidence": evidence,
            "evidence_coerced": evidence_coerced,
            "raw": llm_result,
            "llm_model": model,
            "llm_latency_ms": llm_latency_ms,
            "llm_prompt": user_prompt[:500],
            "llm_raw_output": proc.stdout[:500] if proc.stdout else "",
        },
    )


def evaluate_blind_comparator(
    output_harness: str,
    output_baseline: str,
    prompt: str | None = None,
    model: str = DEFAULT_LLM_MODEL,
    timeout: int = 1800,
) -> dict[str, Any]:
    """Blindly evaluate two outputs, returning pass/fail for each arm.

    Outputs are randomly labeled "Output A" / "Output B" so the LLM judge
    cannot distinguish the harness arm from the baseline arm. The mapping is
    de-anonymized after judgment so callers receive harness/baseline verdicts.

    Args:
        output_harness: stdout from the harness (gated) arm
        output_baseline: stdout from the baseline (ungated) arm
        prompt: Custom evaluation prompt (appended to default framing)
        model: Model identifier for the judge
        timeout: Timeout in seconds

    Returns:
        Dict with keys: harness_pass (bool), baseline_pass (bool),
        confidence (float), reason (str), raw (dict with A/B verdicts)
    """
    effective_prompt = prompt or DEFAULT_BLIND_COMPARATOR_PROMPT

    # Truncate outputs to avoid context limits
    truncated_harness = output_harness[-4000:] if len(output_harness) > 4000 else output_harness
    truncated_baseline = output_baseline[-4000:] if len(output_baseline) > 4000 else output_baseline

    # Randomize order: coin flip determines whether harness→A / baseline→B
    harness_is_a = random.choice([True, False])
    if harness_is_a:
        output_a, output_b = truncated_harness, truncated_baseline
    else:
        output_a, output_b = truncated_baseline, truncated_harness

    user_prompt = (
        f"{effective_prompt}\n\n"
        f"<output_a>\n{output_a}\n</output_a>\n\n"
        f"<output_b>\n{output_b}\n</output_b>"
    )

    invocation = resolve_host().build_blocking_json(prompt=user_prompt, model=model)
    args = list(invocation.args) + [
        "--json-schema",
        json.dumps(BLIND_COMPARATOR_SCHEMA),
        "--no-session-persistence",
    ]

    try:
        proc = subprocess.run(
            [invocation.binary, *args], capture_output=True, text=True, timeout=timeout
        )
    except subprocess.TimeoutExpired:
        # On timeout, both fail — conservative default
        return {
            "harness_pass": False,
            "baseline_pass": False,
            "confidence": 0.0,
            "reason": "LLM evaluation timed out",
            "raw": {"verdict_a": "timeout", "verdict_b": "timeout"},
            "error": "timeout",
        }
    except FileNotFoundError:
        return {
            "harness_pass": False,
            "baseline_pass": False,
            "confidence": 0.0,
            "reason": f"{invocation.binary} CLI not found",
            "raw": {"verdict_a": "error", "verdict_b": "error"},
            "error": "missing_cli",
        }

    if proc.returncode != 0:
        return {
            "harness_pass": False,
            "baseline_pass": False,
            "confidence": 0.0,
            "reason": f"Judge CLI error: {proc.stderr.strip()[:200]}",
            "raw": {"verdict_a": "error", "verdict_b": "error"},
            "error": "api_error",
        }

    if not proc.stdout.strip():
        return {
            "harness_pass": False,
            "baseline_pass": False,
            "confidence": 0.0,
            "reason": "Judge returned empty output",
            "raw": {"verdict_a": "error", "verdict_b": "error"},
            "error": "empty_output",
        }

    try:
        stdout = proc.stdout.strip()
        try:
            envelope = json.loads(stdout)
        except json.JSONDecodeError:
            lines = [line for line in stdout.split("\n") if line.strip()]
            if not lines:
                raise
            envelope = json.loads(lines[-1])

        if envelope.get("subtype") == "error_max_structured_output_retries":
            return {
                "harness_pass": False,
                "baseline_pass": False,
                "confidence": 0.0,
                "reason": "Judge could not produce valid structured output after retries",
                "raw": {"verdict_a": "error", "verdict_b": "error"},
                "error": "retry_exhausted",
            }

        if envelope.get("is_error", False):
            err_text = str(envelope.get("result", "") or "")[:200]
            return {
                "harness_pass": False,
                "baseline_pass": False,
                "confidence": 0.0,
                "reason": f"Judge reported error: {err_text}",
                "raw": {"verdict_a": "error", "verdict_b": "error"},
                "error": "api_error",
            }

        if isinstance(envelope.get("structured_output"), dict):
            result: dict[str, Any] = envelope["structured_output"]
        else:
            raw_result = envelope.get("result", "")
            if isinstance(raw_result, dict):
                result = raw_result
            elif raw_result:
                result = json.loads(raw_result)
            else:
                return {
                    "harness_pass": False,
                    "baseline_pass": False,
                    "confidence": 0.0,
                    "reason": "Empty result field in judge response",
                    "raw": {"verdict_a": "error", "verdict_b": "error"},
                    "error": "empty_result",
                }
    except (json.JSONDecodeError, TypeError, ValueError):
        return {
            "harness_pass": False,
            "baseline_pass": False,
            "confidence": 0.0,
            "reason": "Failed to parse judge response",
            "raw": {"verdict_a": "error", "verdict_b": "error"},
            "error": "parse_error",
        }

    # De-anonymize
    verdict_a = str(result.get("verdict_a", "no"))
    verdict_b = str(result.get("verdict_b", "no"))
    confidence = float(result.get("confidence", 0.0))
    reason = str(result.get("reason", ""))

    if harness_is_a:
        harness_pass = verdict_a == "yes"
        baseline_pass = verdict_b == "yes"
    else:
        harness_pass = verdict_b == "yes"
        baseline_pass = verdict_a == "yes"

    return {
        "harness_pass": harness_pass,
        "baseline_pass": baseline_pass,
        "confidence": confidence,
        "reason": reason,
        "raw": {"verdict_a": verdict_a, "verdict_b": verdict_b, "harness_is_a": harness_is_a},
    }


def evaluate_contract(
    config: EvaluateConfig,
    context: InterpolationContext,
    model: str = DEFAULT_LLM_MODEL,
    timeout: int = 1800,
) -> EvaluationResult:
    """Evaluate producer/consumer contract alignment using an LLM judge.

    Reads each producer/consumer file pair, applies optional regex extraction,
    then asks an LLM judge whether the producer satisfies the consumer contract.
    Returns yes only when all pairs align; any failure routes no/error.

    Args:
        config: EvaluateConfig with type="contract" and pairs list
        context: Interpolation context (unused by this evaluator directly)
        model: LLM model identifier
        timeout: Subprocess timeout in seconds

    Returns:
        EvaluationResult with verdict yes/no/error and pair_results in details
    """
    pairs = config.pairs
    if not pairs:
        return EvaluationResult(
            verdict="error",
            details={"error": "contract evaluator requires at least one pair in evaluate.pairs"},
        )

    contract_schema = {
        "type": "object",
        "properties": {
            "verdict": {"type": "string", "enum": ["yes", "no"]},
            "confidence": {"type": "number"},
            "reason": {"type": "string"},
        },
        "required": ["verdict", "confidence", "reason"],
    }

    pair_results: list[dict[str, Any]] = []

    for pair in pairs:
        producer_path = pair.get("producer", "")
        consumer_path = pair.get("consumer", "")
        producer_pattern = pair.get("producer_pattern")
        consumer_pattern = pair.get("consumer_pattern")
        contract_rule = pair.get("contract", "the producer and consumer must be compatible")

        # Read producer file
        try:
            producer_content = Path(producer_path).read_text()
        except OSError as e:
            pair_results.append(
                {
                    "producer": producer_path,
                    "consumer": consumer_path,
                    "verdict": "error",
                    "error": f"cannot read producer file: {e}",
                }
            )
            continue

        # Read consumer file
        try:
            consumer_content = Path(consumer_path).read_text()
        except OSError as e:
            pair_results.append(
                {
                    "producer": producer_path,
                    "consumer": consumer_path,
                    "verdict": "error",
                    "error": f"cannot read consumer file: {e}",
                }
            )
            continue

        # Apply optional regex extraction
        if producer_pattern:
            matches = re.findall(producer_pattern, producer_content, re.DOTALL)
            if not matches:
                pair_results.append(
                    {
                        "producer": producer_path,
                        "consumer": consumer_path,
                        "verdict": "error",
                        "error": f"producer_pattern matched nothing in {producer_path}",
                    }
                )
                continue
            producer_slice = "\n".join(matches)
        else:
            producer_slice = (
                producer_content[-4000:] if len(producer_content) > 4000 else producer_content
            )

        if consumer_pattern:
            matches = re.findall(consumer_pattern, consumer_content, re.DOTALL)
            if not matches:
                pair_results.append(
                    {
                        "producer": producer_path,
                        "consumer": consumer_path,
                        "verdict": "error",
                        "error": f"consumer_pattern matched nothing in {consumer_path}",
                    }
                )
                continue
            consumer_slice = "\n".join(matches)
        else:
            consumer_slice = (
                consumer_content[-4000:] if len(consumer_content) > 4000 else consumer_content
            )

        judge_prompt = (
            f"You are evaluating whether a producer output satisfies a consumer contract.\n\n"
            f"Contract rule: {contract_rule}\n\n"
            f'<producer path="{producer_path}">\n{producer_slice}\n</producer>\n\n'
            f'<consumer path="{consumer_path}">\n{consumer_slice}\n</consumer>\n\n'
            "Does the producer satisfy the consumer contract? "
            "Consider field names, types, casing, and structure. "
            "Answer yes if aligned, no if mismatched."
        )

        invocation = resolve_host().build_blocking_json(prompt=judge_prompt, model=model)
        args = list(invocation.args) + [
            "--json-schema",
            json.dumps(contract_schema),
            "--no-session-persistence",
        ]

        t0 = time.monotonic()
        try:
            proc = subprocess.run(
                [invocation.binary, *args], capture_output=True, text=True, timeout=timeout
            )
        except subprocess.TimeoutExpired:
            pair_results.append(
                {
                    "producer": producer_path,
                    "consumer": consumer_path,
                    "verdict": "error",
                    "error": "LLM judge timed out",
                    "llm_latency_ms": int((time.monotonic() - t0) * 1000),
                }
            )
            continue
        except FileNotFoundError:
            return EvaluationResult(
                verdict="error",
                details={
                    "error": f"{invocation.binary} CLI not found. Install the active host CLI (see LL_HOST_CLI).",
                    "missing_dependency": True,
                },
            )
        llm_latency_ms = int((time.monotonic() - t0) * 1000)

        if proc.returncode != 0:
            pair_results.append(
                {
                    "producer": producer_path,
                    "consumer": consumer_path,
                    "verdict": "error",
                    "error": f"CLI error: {proc.stderr.strip()}",
                    "llm_latency_ms": llm_latency_ms,
                }
            )
            continue

        if not proc.stdout.strip():
            pair_results.append(
                {
                    "producer": producer_path,
                    "consumer": consumer_path,
                    "verdict": "error",
                    "error": "CLI returned empty output",
                    "llm_latency_ms": llm_latency_ms,
                }
            )
            continue

        try:
            stdout = proc.stdout.strip()
            try:
                envelope = json.loads(stdout)
            except json.JSONDecodeError:
                lines = [line for line in stdout.split("\n") if line.strip()]
                if not lines:
                    raise
                envelope = json.loads(lines[-1])

            if envelope.get("subtype") == "error_max_structured_output_retries":
                pair_results.append(
                    {
                        "producer": producer_path,
                        "consumer": consumer_path,
                        "verdict": "error",
                        "error": "Claude CLI could not produce valid structured output after retries",
                        "llm_latency_ms": llm_latency_ms,
                    }
                )
                continue

            if envelope.get("is_error", False):
                err_text = str(envelope.get("result", "") or "")[:200]
                pair_results.append(
                    {
                        "producer": producer_path,
                        "consumer": consumer_path,
                        "verdict": "error",
                        "error": f"Claude CLI reported error: {err_text}",
                        "llm_latency_ms": llm_latency_ms,
                    }
                )
                continue

            if isinstance(envelope.get("structured_output"), dict):
                llm_result: dict[str, Any] = envelope["structured_output"]
            else:
                raw_result = envelope.get("result", "")
                if isinstance(raw_result, dict):
                    llm_result = raw_result
                elif raw_result:
                    llm_result = json.loads(raw_result)
                elif "verdict" in envelope:
                    llm_result = envelope
                else:
                    pair_results.append(
                        {
                            "producer": producer_path,
                            "consumer": consumer_path,
                            "verdict": "error",
                            "error": "empty result field in CLI response",
                            "llm_latency_ms": llm_latency_ms,
                        }
                    )
                    continue

        except (json.JSONDecodeError, TypeError, ValueError) as e:
            pair_results.append(
                {
                    "producer": producer_path,
                    "consumer": consumer_path,
                    "verdict": "error",
                    "error": f"failed to parse LLM response: {e}",
                    "llm_latency_ms": llm_latency_ms,
                }
            )
            continue

        pair_results.append(
            {
                "producer": producer_path,
                "consumer": consumer_path,
                "verdict": str(llm_result.get("verdict", "error")),
                "confidence": float(llm_result.get("confidence", 1.0)),
                "reason": llm_result.get("reason", ""),
                "llm_latency_ms": llm_latency_ms,
            }
        )

    # Aggregate: yes only if all pairs aligned; error takes precedence over no
    if any(p["verdict"] == "error" for p in pair_results):
        overall = "error"
    elif all(p["verdict"] == "yes" for p in pair_results):
        overall = "yes"
    else:
        overall = "no"

    return EvaluationResult(
        verdict=overall,
        details={"pair_results": pair_results},
    )


def evaluate_comparator(
    config: EvaluateConfig,
    output: str,
    context: InterpolationContext,
) -> EvaluationResult:
    """Evaluate using blind A/B comparison against a stored baseline."""
    from pathlib import Path

    if config.baseline_path is None:
        return EvaluationResult(
            verdict="no_baseline",
            details={"reason": "No baseline_path configured"},
        )

    baseline_file = Path(config.baseline_path) / "output.txt"
    if not baseline_file.exists():
        if config.auto_promote:
            baseline_file.parent.mkdir(parents=True, exist_ok=True)
            baseline_file.write_text(output)
            return EvaluationResult(
                verdict="yes",
                details={
                    "reason": "No baseline found; current output promoted as new baseline.",
                    "bootstrapped": True,
                },
            )
        return EvaluationResult(
            verdict="no_baseline",
            details={"reason": f"Baseline file not found: {baseline_file}"},
        )

    baseline_text = baseline_file.read_text()
    min_pairs = max(1, config.min_pairs if config.min_pairs is not None else 1)
    harness_wins = 0
    baseline_wins = 0
    last_reason = ""
    last_raw: dict[str, Any] = {}

    for _ in range(min_pairs):
        result = evaluate_blind_comparator(output, baseline_text, prompt=config.prompt)
        if result.get("harness_pass"):
            harness_wins += 1
        if result.get("baseline_pass"):
            baseline_wins += 1
        last_reason = result.get("reason", "")
        last_raw = result.get("raw", {})

    if harness_wins > baseline_wins:
        verdict = "yes"
    elif baseline_wins > harness_wins:
        verdict = "no"
    else:
        verdict = "tie"

    if config.auto_promote and verdict == "yes":
        baseline_file.write_text(output)

    return EvaluationResult(
        verdict=verdict,
        details={
            "harness_wins": harness_wins,
            "baseline_wins": baseline_wins,
            "min_pairs": min_pairs,
            "reason": last_reason,
            "raw": last_raw,
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

    # BUG-1640: Action-level timeouts (exit_code=124) short-circuit to "error"
    # so loop authors' on_error: branches fire instead of being routed via
    # on_no: based on truncated output. mcp_result is exempted because it has
    # its own established "timeout" verdict (see evaluate_mcp_result).
    if exit_code == 124 and eval_type != "mcp_result":
        return EvaluationResult(
            verdict="error",
            details={"exit_code": exit_code, "error": "action timed out"},
        )

    # BUG-1815: Non-timeout non-zero exit codes short-circuit to "error" for
    # evaluator types that don't intrinsically check exit codes. Exit-code-aware
    # evaluators (exit_code, mcp_result, harbor_scorer, diff_stall, llm_structured)
    # are exempt because they handle exit codes via their own logic.
    _EXIT_CODE_AWARE_EVALUATORS: frozenset[str] = frozenset(
        {
            "exit_code",
            "mcp_result",
            "harbor_scorer",
            "diff_stall",
            "score_stall",
            "open_question_stall",
            "action_stall",
            "llm_structured",
            "contract",
        }
    )
    if exit_code != 0 and eval_type not in _EXIT_CODE_AWARE_EVALUATORS:
        return EvaluationResult(
            verdict="error",
            details={
                "exit_code": exit_code,
                "error": f"action exited with code {exit_code}",
            },
        )

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
            error_patterns=config.error_patterns,
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

    elif eval_type == "score_stall":
        history_file = config.history_file or "${context.run_dir}/.score_history"
        if context:
            try:
                history_file = interpolate(history_file, context)
            except InterpolationError:
                pass  # Use raw path on resolution failure
        return evaluate_score_stall(
            history_file=history_file,
            max_stall=config.max_stall,
            epsilon=config.epsilon,
        )

    elif eval_type == "open_question_stall":
        history_file = config.history_file or "${context.run_dir}/.open_questions_history"
        if context:
            try:
                history_file = interpolate(history_file, context)
            except InterpolationError:
                pass  # Use raw path on resolution failure
        return evaluate_open_question_stall(
            history_file=history_file,
            max_stall=config.max_stall,
            epsilon=config.epsilon,
        )

    elif eval_type == "action_stall":
        return evaluate_action_stall(
            track=config.track,
            max_repeat=config.max_repeat,
            context=context,
        )

    elif eval_type == "llm_structured":
        prompt = config.prompt
        if prompt and context:
            try:
                prompt = interpolate(prompt, context)
            except InterpolationError:
                pass  # Use raw prompt on resolution failure
        return evaluate_llm_structured(
            output=output,
            prompt=prompt,
            schema=config.schema,
            min_confidence=config.min_confidence,
            uncertain_suffix=config.uncertain_suffix,
        )

    elif eval_type == "mcp_result":
        return evaluate_mcp_result(output=output, exit_code=exit_code)

    elif eval_type == "harbor_scorer":
        return evaluate_harbor_scorer(output=output, exit_code=exit_code)

    elif eval_type == "comparator":
        return evaluate_comparator(config=config, output=output, context=context)

    elif eval_type == "contract":
        return evaluate_contract(config=config, context=context)

    elif eval_type == "classify":
        return evaluate_classify(output=output, line=config.line)

    else:
        raise ValueError(f"Unknown evaluator type: {eval_type}")

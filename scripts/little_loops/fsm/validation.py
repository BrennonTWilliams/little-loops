"""FSM loop validation logic.

This module provides validation for FSM loop definitions, ensuring
structural correctness and catching common configuration errors.

Validation checks:
- Initial state exists in states dict
- All referenced states exist
- At least one terminal state
- Evaluator configs have required fields for their type
- No conflicting routing (shorthand vs full route)
- Numeric fields in valid ranges (max_iterations > 0, backoff >= 0, timeout > 0)
"""

from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from little_loops.fsm.evaluators import _NUMERIC_OPERATORS
from little_loops.fsm.fragments import resolve_flow, resolve_fragments, resolve_inheritance
from little_loops.fsm.schema import EvaluateConfig, FSMLoop, ParameterSpec, StateConfig

logger = logging.getLogger(__name__)


class ValidationSeverity(Enum):
    """Severity level for validation issues."""

    ERROR = "error"
    WARNING = "warning"


@dataclass
class ValidationError:
    """Structured validation error.

    Attributes:
        message: Human-readable error description
        path: Path to the problematic element (e.g., "states.check.route")
        severity: Error severity (error or warning)
    """

    message: str
    path: str | None = None
    severity: ValidationSeverity = ValidationSeverity.ERROR

    def __str__(self) -> str:
        """Format error for display."""
        prefix = f"[{self.severity.value.upper()}]"
        if self.path:
            return f"{prefix} {self.path}: {self.message}"
        return f"{prefix} {self.message}"


# Evaluator type to required fields mapping
EVALUATOR_REQUIRED_FIELDS: dict[str, list[str]] = {
    "exit_code": [],
    "output_numeric": ["operator", "target"],
    "output_json": ["path", "operator", "target"],
    "output_contains": ["pattern"],
    "convergence": ["target"],
    "diff_stall": [],
    "action_stall": [],
    "llm_structured": [],
    "mcp_result": [],
    "harbor_scorer": [],
    "comparator": ["baseline_path"],
    "contract": ["pairs"],
    "classify": [],
}

# Non-LLM evaluator types: all evaluator types except llm_structured
# Derived from EVALUATOR_REQUIRED_FIELDS so new types are automatically included
NON_LLM_EVALUATOR_TYPES: frozenset[str] = frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {
    "llm_structured",
    "comparator",
    "contract",
}

# Meta-loop detector: action string patterns that indicate harness artifact writes
_META_LOOP_ACTION_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"loops/[\w-]+\.yaml"),
    re.compile(r"skills/[\w-]+/SKILL\.md"),
    re.compile(r"agents/[\w-]+\.md"),
    re.compile(r"commands/[\w-]+\.md"),
    re.compile(r"\.claude/(CLAUDE\.md|settings)"),
)

# Action string tokens that indicate meta-loop behavior
_META_LOOP_ACTION_TOKENS: frozenset[str] = frozenset({"yaml_state_editor", "replace_action"})

# Import paths that identify a loop as a meta-loop (harness optimization framework)
_META_LOOP_IMPORT_TRIGGERS: frozenset[str] = frozenset({"lib/benchmark.yaml"})

# MR-3: shared-tmp path detector. The runner injects ${context.run_dir} resolving
# to .loops/runs/<loop>-<timestamp>/; loops that hardcode .loops/tmp/ instead
# cause state corruption under concurrent runs (ll-parallel, retries, etc.).
_SHARED_TMP_PATH_RE = re.compile(r"\.loops/tmp/[\w./-]+")

# ENH-1961: Regex for extracting captured variable names from ${captured.<var>.*} references
_CAPTURED_REF_RE = re.compile(r"\$\{captured\.(\w+)")

# Full-reference form, capturing the var name and the remainder up to the closing
# brace so we can detect a `:default=` guard. A reference written as
# `${captured.x.output:default=...}` is provably safe even on paths that bypass
# the capturing state — the interpolation engine (interpolation.py) substitutes
# the default when the path is missing — so it must NOT be flagged by the
# capture-reachability check. _CAPTURED_REF_RE alone can't see the guard.
_CAPTURED_REF_FULL_RE = re.compile(r"\$\{captured\.(\w+)([^}]*)\}")


def _unguarded_captured_refs(text: str) -> set[str]:
    """Return captured var names that have at least one reference WITHOUT a
    `:default=` guard. Vars referenced only via `${captured.x...:default=...}`
    are omitted: the default makes a missing value safe, so they should not
    trigger missing-capture or bypass-path diagnostics.
    """
    refs: set[str] = set()
    for var_name, remainder in _CAPTURED_REF_FULL_RE.findall(text):
        if ":default=" not in remainder:
            refs.add(var_name)
    return refs


# ENH-1819: Regex patterns for detecting multimodal evaluation in prompt actions
_MULTIMODAL_EVAL_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"Read the screenshot", re.IGNORECASE),
    re.compile(r"view the (generated )?(website|page|image)", re.IGNORECASE),
    re.compile(r"screenshot\.(png|jpg|jpeg|webp)"),
    re.compile(r"\.(png|jpg|jpeg|webp)\b.*\b(read|view|evaluate|score|judge)", re.IGNORECASE),
)

# Valid comparison operators
VALID_OPERATORS = {"eq", "ne", "lt", "le", "gt", "ge"}

# Valid values for the top-level `visibility:` field (audience axis for
# `ll-loop list` filtering). "public" is the default when the field is absent.
VALID_VISIBILITY: frozenset[str] = frozenset({"public", "internal", "example"})

# All top-level keys recognized by FSMLoop.from_dict()
KNOWN_TOP_LEVEL_KEYS: frozenset[str] = frozenset(
    {
        "name",
        "description",
        "initial",
        "states",
        "context",
        "parameters",
        "scope",
        "max_steps",
        "on_max_steps",
        "max_iterations",
        "on_max_iterations",
        "max_edge_revisits",
        "backoff",
        "timeout",
        "default_timeout",
        "maintain",
        "llm",
        "on_handoff",
        "input_key",
        "required_inputs",
        "config",
        "category",
        "labels",
        "visibility",
        "commands",
        "targets",
        "circuit",
        "meta_self_eval_ok",
        "shared_state_ok",
        "partial_route_ok",
        "artifact_versioning",
        "artifact_versioning_ok",
        "generator_fix_ok",
        "import",
        "fragments",
        "from",
        "flow",
        "state_defs",
    }
)

# Special tokens accepted as the `on_repeated_failure` target on the
# stall detector — `"abort"` means terminate via _finish("stall_detected").
STALL_SPECIAL_TOKENS: frozenset[str] = frozenset({"abort"})

# Valid parameter types for the 'parameters:' block
VALID_PARAMETER_TYPES: frozenset[str] = frozenset(
    {"string", "integer", "number", "boolean", "enum", "path"}
)


def _validate_evaluator(state_name: str, evaluate: EvaluateConfig) -> list[ValidationError]:
    """Validate evaluator configuration for type-specific requirements.

    Args:
        state_name: Name of the state containing this evaluator
        evaluate: The evaluator configuration to validate

    Returns:
        List of validation errors found
    """
    errors: list[ValidationError] = []
    path = f"states.{state_name}.evaluate"

    # Check that evaluator type is recognized
    valid_types = set(EVALUATOR_REQUIRED_FIELDS.keys())
    if evaluate.type not in valid_types:
        errors.append(
            ValidationError(
                message=f"Unknown evaluator type '{evaluate.type}'. "
                f"Must be one of: {', '.join(sorted(valid_types))}",
                path=path,
            )
        )
        return errors  # Can't check required fields for unknown type

    # Check required fields for evaluator type
    required = EVALUATOR_REQUIRED_FIELDS.get(evaluate.type, [])
    for field_name in required:
        value = getattr(evaluate, field_name, None)
        if value is None:
            errors.append(
                ValidationError(
                    message=f"Evaluator type '{evaluate.type}' requires '{field_name}' field",
                    path=path,
                )
            )

    # Validate operator if present
    if evaluate.operator is not None and evaluate.operator not in VALID_OPERATORS:
        errors.append(
            ValidationError(
                message=f"Invalid operator '{evaluate.operator}'. "
                f"Must be one of: {', '.join(sorted(VALID_OPERATORS))}",
                path=f"{path}.operator",
            )
        )

    # Validate convergence-specific fields
    if evaluate.type == "convergence":
        if evaluate.direction not in ("minimize", "maximize"):
            errors.append(
                ValidationError(
                    message=f"Invalid direction '{evaluate.direction}'. "
                    "Must be 'minimize' or 'maximize'",
                    path=f"{path}.direction",
                )
            )
        # Only validate tolerance if it's a numeric value (not an interpolation string)
        if (
            evaluate.tolerance is not None
            and isinstance(evaluate.tolerance, (int, float))
            and evaluate.tolerance < 0
        ):
            errors.append(
                ValidationError(
                    message="Tolerance cannot be negative",
                    path=f"{path}.tolerance",
                )
            )

    # Validate llm_structured-specific fields
    if evaluate.type == "llm_structured":
        if evaluate.min_confidence < 0 or evaluate.min_confidence > 1:
            errors.append(
                ValidationError(
                    message="min_confidence must be between 0 and 1",
                    path=f"{path}.min_confidence",
                )
            )

    # Validate diff_stall-specific fields
    if evaluate.type == "diff_stall":
        if evaluate.max_stall < 1:
            errors.append(
                ValidationError(
                    message="max_stall must be >= 1",
                    path=f"{path}.max_stall",
                )
            )

    # Validate action_stall-specific fields
    if evaluate.type == "action_stall":
        if evaluate.max_repeat < 1:
            errors.append(
                ValidationError(
                    message="max_repeat must be >= 1",
                    path=f"{path}.max_repeat",
                )
            )

    return errors


def _validate_parameters(fsm: FSMLoop) -> list[ValidationError]:
    """Validate the loop's top-level parameters: block.

    Args:
        fsm: The FSM loop to validate

    Returns:
        List of validation errors found
    """
    errors: list[ValidationError] = []

    for param_name, param_spec in fsm.parameters.items():
        path = f"parameters.{param_name}"

        if param_spec.type not in VALID_PARAMETER_TYPES:
            errors.append(
                ValidationError(
                    message=(
                        f"Unknown parameter type '{param_spec.type}'. "
                        f"Must be one of: {', '.join(sorted(VALID_PARAMETER_TYPES))}"
                    ),
                    path=path,
                )
            )

        if param_spec.type == "enum" and not param_spec.values:
            errors.append(
                ValidationError(
                    message="Parameter type 'enum' requires a 'values' list",
                    path=path,
                )
            )

        if param_spec.required and param_spec.default is not None:
            errors.append(
                ValidationError(
                    message="Parameter cannot be both 'required: true' and have a 'default' value",
                    path=path,
                )
            )

    return errors


def _check_param_type(value: Any, spec: ParameterSpec) -> str | None:
    """Return an error message if value does not match spec.type, else None."""
    if spec.type == "string" and not isinstance(value, str):
        return f"expected string, got {type(value).__name__}"
    if spec.type == "integer" and not isinstance(value, int):
        return f"expected integer, got {type(value).__name__}"
    if spec.type == "number" and not isinstance(value, (int, float)):
        return f"expected number, got {type(value).__name__}"
    if spec.type == "boolean" and not isinstance(value, bool):
        return f"expected boolean, got {type(value).__name__}"
    if spec.type == "enum" and spec.values and value not in spec.values:
        return f"expected one of {spec.values!r}, got {value!r}"
    return None


def _validate_with_bindings(fsm: FSMLoop, loop_dir: Path) -> list[ValidationError]:
    """Validate with: bindings against child loop parameter contracts.

    Called from load_and_validate (not validate_fsm) because resolving child loops
    requires file-system access via the loop directory path.

    Args:
        fsm: The parent FSM loop
        loop_dir: Directory to resolve child loop paths from

    Returns:
        List of validation errors found
    """
    errors: list[ValidationError] = []

    for state_name, state in fsm.states.items():
        if state.loop is None or not state.with_:
            continue

        # Try to resolve and load the child loop; skip if unavailable
        try:
            from little_loops.cli.loop._helpers import resolve_loop_path

            loop_path = resolve_loop_path(state.loop, loop_dir)
            child_fsm, _ = load_and_validate(loop_path)
        except Exception:
            continue

        if not child_fsm.parameters:
            continue  # Child has no declared contract — nothing to cross-validate

        path = f"states.{state_name}"

        # Unknown with: keys (not declared by child)
        for key in state.with_:
            if key not in child_fsm.parameters:
                errors.append(
                    ValidationError(
                        message=(
                            f"'with.{key}' is not a declared parameter of loop '{state.loop}'. "
                            f"Declared: {', '.join(sorted(child_fsm.parameters))}"
                        ),
                        path=f"{path}.with.{key}",
                    )
                )

        # Required parameters not bound
        for param_name, param_spec in child_fsm.parameters.items():
            if param_spec.required and param_name not in state.with_:
                errors.append(
                    ValidationError(
                        message=(
                            f"Required parameter '{param_name}' of loop '{state.loop}' "
                            f"is not bound in 'with'"
                        ),
                        path=f"{path}.with",
                    )
                )

        # Statically-detectable type mismatches (skip interpolation strings)
        for param_name, value in state.with_.items():
            if param_name not in child_fsm.parameters:
                continue
            if isinstance(value, str) and "${" in value:
                continue
            type_error = _check_param_type(value, child_fsm.parameters[param_name])
            if type_error:
                errors.append(
                    ValidationError(
                        message=f"Parameter '{param_name}': {type_error}",
                        path=f"{path}.with.{param_name}",
                    )
                )

    return errors


def _validate_loop_references(fsm: FSMLoop, loop_dir: Path) -> list[ValidationError]:
    """Validate that every state's loop: reference resolves to an actual loop file.

    Called from load_and_validate (not validate_fsm) because resolving child loops
    requires file-system access via the loop directory path.
    """
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if state.loop is None:
            continue
        # Skip dynamically interpolated loop names — they can only be checked at runtime
        if "${" in state.loop:
            continue
        try:
            from little_loops.cli.loop._helpers import resolve_loop_path

            resolve_loop_path(state.loop, loop_dir)
        except FileNotFoundError:
            errors.append(
                ValidationError(
                    message=f"Loop reference '{state.loop}' does not resolve to any file.",
                    path=f"states.{state_name}.loop",
                    severity=ValidationSeverity.WARNING,
                )
            )
    return errors


def _validate_fragment_bindings(fsm: FSMLoop, loop_dir: Path) -> list[ValidationError]:
    """Validate fragment with: bindings against fragment parameter contracts.

    Called from load_and_validate (not validate_fsm) because fragment parameters
    are populated by resolve_fragments which runs before dataclass parsing.

    Args:
        fsm: The FSM loop to validate
        loop_dir: Directory containing the loop file (unused; kept for API symmetry with
            _validate_with_bindings)

    Returns:
        List of validation errors found
    """
    # Runner-injected vars available at runtime but not at static analysis time
    RUNNER_INJECTED = {"run_dir", "loop_name", "started_at", "input_hash"}

    errors: list[ValidationError] = []

    for state_name, state in fsm.states.items():
        if not state.fragment_parameters:
            continue  # No declared contract — nothing to cross-validate

        path = f"states.{state_name}"

        # Unknown with: keys (not declared by fragment)
        for key in state.fragment_bindings:
            if key not in state.fragment_parameters:
                errors.append(
                    ValidationError(
                        message=(
                            f"'with.{key}' is not a declared parameter of fragment "
                            f"'{state.fragment_name}'. "
                            f"Declared: {', '.join(sorted(state.fragment_parameters))}"
                        ),
                        path=f"{path}.with.{key}",
                    )
                )

        # Required parameters not bound (whitelist runner-injected vars)
        for param_name, param_spec in state.fragment_parameters.items():
            if param_spec.required and param_name not in state.fragment_bindings:
                if param_name in RUNNER_INJECTED:
                    continue  # Available at runtime; not a static error
                errors.append(
                    ValidationError(
                        message=(
                            f"Required parameter '{param_name}' of fragment "
                            f"'{state.fragment_name}' is not bound in 'with'"
                        ),
                        path=f"{path}.with",
                    )
                )

        # Statically-detectable type mismatches (skip interpolation strings)
        for param_name, value in state.fragment_bindings.items():
            if param_name not in state.fragment_parameters:
                continue
            if isinstance(value, str) and "${" in value:
                continue
            type_error = _check_param_type(value, state.fragment_parameters[param_name])
            if type_error:
                errors.append(
                    ValidationError(
                        message=f"Parameter '{param_name}': {type_error}",
                        path=f"{path}.with.{param_name}",
                    )
                )

    return errors


def _validate_state_action(state_name: str, state: StateConfig) -> list[ValidationError]:
    """Validate state action configuration.

    Args:
        state_name: Name of the state to validate
        state: The state configuration to validate

    Returns:
        List of validation errors found
    """
    errors: list[ValidationError] = []
    path = f"states.{state_name}"

    # append_to_messages must contain at least one ${...} interpolation expression
    if state.append_to_messages is not None:
        if "${" not in state.append_to_messages:
            errors.append(
                ValidationError(
                    message=(
                        "'append_to_messages' must contain a ${...} interpolation expression "
                        f"(e.g. '${{captured.{state_name}.output}}')"
                    ),
                    path=f"{path}.append_to_messages",
                )
            )

    # model: override is silently ignored for non-prompt states (host CLI is not invoked)
    if state.model is not None and state.action_type not in ("prompt", "slash_command", None):
        errors.append(
            ValidationError(
                message="model: override is ignored for shell/mcp_tool/contract states",
                path=f"{path}.model",
                severity=ValidationSeverity.WARNING,
            )
        )

    # params field is only valid for mcp_tool states
    if state.params and state.action_type != "mcp_tool":
        errors.append(
            ValidationError(
                message="'params' field is only valid when action_type is 'mcp_tool'",
                path=f"{path}.params",
            )
        )

    # loop and action are mutually exclusive
    if state.loop is not None and state.action is not None:
        errors.append(
            ValidationError(
                message="'loop' and 'action' are mutually exclusive — "
                "a sub-loop state cannot also have an action",
                path=f"{path}",
            )
        )

    # with: requires loop: to be set
    if state.with_ and state.loop is None:
        errors.append(
            ValidationError(
                message="'with' is only valid when 'loop' is set",
                path=f"{path}.with",
            )
        )

    # FEAT-1283: type=learning requires a populated LearningConfig
    if state.type == "learning" and state.learning is not None:
        if not state.learning.targets and not state.learning.targets_csv:
            errors.append(
                ValidationError(
                    message="type=learning requires non-empty 'learning.targets' or 'learning.targets_csv'",
                    path=f"{path}.learning.targets",
                )
            )
        if state.learning.max_retries < 0:
            errors.append(
                ValidationError(
                    message=(
                        f"learning.max_retries must be >= 0, got {state.learning.max_retries}"
                    ),
                    path=f"{path}.learning.max_retries",
                )
            )
        if state.on_yes is None:
            errors.append(
                ValidationError(
                    message="type=learning requires 'on_yes' (target for all-proven)",
                    path=f"{path}.on_yes",
                )
            )
        if state.on_blocked is None and state.on_no is None:
            errors.append(
                ValidationError(
                    message=(
                        "type=learning requires 'on_blocked' or 'on_no' "
                        "(target for refuted / retries_exhausted)"
                    ),
                    path=f"{path}",
                )
            )

    # with: and context_passthrough are mutually exclusive
    if state.with_ and state.context_passthrough:
        errors.append(
            ValidationError(
                message=(
                    "'with' and 'context_passthrough' are mutually exclusive — "
                    "use 'with' for explicit parameter bindings or 'context_passthrough' "
                    "for legacy bulk passthrough, not both"
                ),
                path=f"{path}",
            )
        )

    return errors


def _validate_state_routing(state_name: str, state: StateConfig) -> list[ValidationError]:
    """Validate state routing configuration.

    Checks for conflicting routing definitions (shorthand vs full route).

    Args:
        state_name: Name of the state to validate
        state: The state configuration to validate

    Returns:
        List of validation errors/warnings found
    """
    errors: list[ValidationError] = []
    path = f"states.{state_name}"

    has_shorthand = (
        state.on_yes is not None
        or state.on_no is not None
        or state.on_error is not None
        or state.on_partial is not None
        or state.on_blocked is not None
        or bool(state.extra_routes)
    )
    has_route = state.route is not None

    # Warn about conflicting definitions
    if has_shorthand and has_route:
        errors.append(
            ValidationError(
                message="Both shorthand routing (on_yes/on_no/on_error) "
                "and full route table defined. Route table will take precedence.",
                path=path,
                severity=ValidationSeverity.WARNING,
            )
        )

    # Check for no valid transition definition
    has_next = state.next is not None
    has_terminal = state.terminal
    has_loop = state.loop is not None

    if not has_shorthand and not has_route and not has_next and not has_terminal and not has_loop:
        errors.append(
            ValidationError(
                message="State has no transition defined. Add routing, 'next', "
                "or mark as 'terminal: true'",
                path=path,
            )
        )

    # Validate retry field pairing: max_retries requires on_retry_exhausted and vice versa
    if state.max_retries is not None and state.on_retry_exhausted is None:
        errors.append(
            ValidationError(
                message="'max_retries' requires 'on_retry_exhausted' to also be set",
                path=path,
            )
        )
    if state.on_retry_exhausted is not None and state.max_retries is None:
        errors.append(
            ValidationError(
                message="'on_retry_exhausted' requires 'max_retries' to also be set",
                path=path,
            )
        )
    if state.max_retries is not None and state.max_retries < 1:
        errors.append(
            ValidationError(
                message=f"'max_retries' must be >= 1, got {state.max_retries}",
                path=path,
            )
        )

    # Validate retryable_exit_codes: requires on_error; all codes must be positive ints
    if state.retryable_exit_codes is not None:
        if state.on_error is None:
            errors.append(
                ValidationError(
                    message="'retryable_exit_codes' requires 'on_error' to also be set",
                    path=path,
                )
            )
        for code in state.retryable_exit_codes:
            if not isinstance(code, int) or code < 1:
                errors.append(
                    ValidationError(
                        message=(
                            f"'retryable_exit_codes' entries must be positive "
                            f"integers, got {code!r}"
                        ),
                        path=f"{path}.retryable_exit_codes",
                    )
                )
                break

    # Validate rate-limit retry field pairing (mirrors max_retries/on_retry_exhausted)
    if state.max_rate_limit_retries is not None and state.on_rate_limit_exhausted is None:
        errors.append(
            ValidationError(
                message="'max_rate_limit_retries' requires 'on_rate_limit_exhausted' to also be set",
                path=path,
            )
        )
    if state.on_rate_limit_exhausted is not None and state.max_rate_limit_retries is None:
        errors.append(
            ValidationError(
                message="'on_rate_limit_exhausted' requires 'max_rate_limit_retries' to also be set",
                path=path,
            )
        )
    if state.max_rate_limit_retries is not None and state.max_rate_limit_retries < 1:
        errors.append(
            ValidationError(
                message=f"'max_rate_limit_retries' must be >= 1, got {state.max_rate_limit_retries}",
                path=path,
            )
        )
    if (
        state.rate_limit_backoff_base_seconds is not None
        and state.rate_limit_backoff_base_seconds < 1
    ):
        errors.append(
            ValidationError(
                message=(
                    f"'rate_limit_backoff_base_seconds' must be >= 1, "
                    f"got {state.rate_limit_backoff_base_seconds}"
                ),
                path=path,
            )
        )
    if state.rate_limit_max_wait_seconds is not None and state.rate_limit_max_wait_seconds < 1:
        errors.append(
            ValidationError(
                message=(
                    f"'rate_limit_max_wait_seconds' must be >= 1, "
                    f"got {state.rate_limit_max_wait_seconds}"
                ),
                path=path,
            )
        )
    if state.rate_limit_long_wait_ladder is not None:
        if len(state.rate_limit_long_wait_ladder) == 0:
            errors.append(
                ValidationError(
                    message="'rate_limit_long_wait_ladder' must be non-empty if specified",
                    path=path,
                )
            )
        else:
            for idx, value in enumerate(state.rate_limit_long_wait_ladder):
                if not isinstance(value, int) or value < 1:
                    errors.append(
                        ValidationError(
                            message=(
                                f"'rate_limit_long_wait_ladder[{idx}]' must be a "
                                f"positive integer, got {value!r}"
                            ),
                            path=path,
                        )
                    )

    # Validate throttle config when present
    if state.throttle is not None:
        t = state.throttle
        fields = {
            "normal_max": t.normal_max,
            "warn_max": t.warn_max,
            "hard_max": t.hard_max,
        }
        for field_name, val in fields.items():
            if val is not None and (not isinstance(val, int) or val < 1):
                errors.append(
                    ValidationError(
                        message=f"'throttle.{field_name}' must be a positive integer, got {val!r}",
                        path=path,
                    )
                )
        # Enforce ordering when all three are set
        if t.normal_max is not None and t.warn_max is not None and t.normal_max >= t.warn_max:
            errors.append(
                ValidationError(
                    message=(
                        f"'throttle.normal_max' ({t.normal_max}) must be less than "
                        f"'throttle.warn_max' ({t.warn_max})"
                    ),
                    path=path,
                )
            )
        if t.warn_max is not None and t.hard_max is not None and t.warn_max >= t.hard_max:
            errors.append(
                ValidationError(
                    message=(
                        f"'throttle.warn_max' ({t.warn_max}) must be less than "
                        f"'throttle.hard_max' ({t.hard_max})"
                    ),
                    path=path,
                )
            )

    return errors


def _validate_targets(fsm: FSMLoop) -> list[ValidationError]:
    """Validate top-level targets[] entries (ENH-1552).

    Rejects any targets[].states[] entry whose sibling file: value does not
    end with a .yaml extension.
    """
    errors: list[ValidationError] = []
    for i, target in enumerate(fsm.targets):
        if target.file is not None and not target.file.endswith(".yaml"):
            errors.append(
                ValidationError(
                    message=(f"targets[{i}].file must be a .yaml file, got '{target.file}'"),
                    path=f"targets[{i}].file",
                )
            )
    return errors


def _validate_failure_terminal_action(fsm: FSMLoop) -> list[ValidationError]:
    """Warn when a failure-named terminal state has no diagnostic predecessor.

    Failure terminals (failed, error, aborted) should have at least one
    predecessor state with an action or sub-loop that provides diagnostic
    output before termination. Otherwise the failure is silent — the
    executor calls _finish("terminal") before any action on the terminal
    itself can execute.

    Severity is WARNING (not ERROR) so that existing loops with bare
    failure terminals continue to load, and test_terminal_only_state_valid
    (which filters by ERROR) passes without modification.
    """
    FAILURE_TERMINAL_NAMES: frozenset[str] = frozenset({"failed", "error", "aborted"})
    errors: list[ValidationError] = []

    terminal_states = fsm.get_terminal_states()
    failure_terminals = terminal_states & FAILURE_TERMINAL_NAMES

    for ft_name in failure_terminals:
        has_diagnostic_predecessor = False
        for state_name, state in fsm.states.items():
            if state_name == ft_name:
                continue
            if ft_name in state.get_referenced_states():
                if state.action is not None or state.loop is not None:
                    has_diagnostic_predecessor = True
                    break

        if not has_diagnostic_predecessor:
            errors.append(
                ValidationError(
                    message=(
                        f"Failure-named terminal state '{ft_name}' has no predecessor "
                        "state with a diagnostic action. Add a non-terminal diagnostic "
                        "state (e.g. 'diagnose') with an action or sub-loop that routes "
                        f"to '{ft_name}'."
                    ),
                    path=f"states.{ft_name}",
                    severity=ValidationSeverity.WARNING,
                )
            )

    return errors


def validate_fsm(fsm: FSMLoop) -> list[ValidationError]:
    """Validate FSM structure and return list of errors.

    Performs comprehensive validation:
    - Initial state exists
    - All referenced states exist
    - At least one terminal state
    - Evaluator configurations are valid
    - Routing configurations are valid
    - Numeric fields are in valid ranges (max_iterations > 0, backoff >= 0, timeout > 0)

    Args:
        fsm: The FSM loop to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[ValidationError] = []
    defined_states = fsm.get_all_state_names()

    # Warn when no top-level description: field is set. The field is optional
    # for FSM execution but required for goal-alignment skills (debug-loop-run,
    # audit-loop-run) and for ll-loop show --json to surface intent text.
    if not fsm.description:
        errors.append(
            ValidationError(
                path="<root>",
                message=("No 'description' field defined. Add a top-level description: key."),
                severity=ValidationSeverity.WARNING,
            )
        )

    # Validate parameters block
    errors.extend(_validate_parameters(fsm))

    # Validate targets block (ENH-1552)
    errors.extend(_validate_targets(fsm))

    # Check initial state exists
    if fsm.initial not in defined_states:
        errors.append(
            ValidationError(
                message=f"Initial state '{fsm.initial}' not found in states",
                path="initial",
            )
        )

    # Check at least one terminal state
    terminal_states = fsm.get_terminal_states()
    if not terminal_states:
        errors.append(
            ValidationError(
                message="No terminal state defined. At least one state must have 'terminal: true'",
                path="states",
            )
        )

    # Validate each state
    for state_name, state in fsm.states.items():
        # Check all referenced states exist
        refs = state.get_referenced_states()
        for ref in refs:
            # $current is a special token for retry
            if ref != "$current" and ref not in defined_states:
                errors.append(
                    ValidationError(
                        message=f"References unknown state '{ref}'",
                        path=f"states.{state_name}",
                    )
                )

        # Validate action configuration
        errors.extend(_validate_state_action(state_name, state))

        # Validate evaluator if present
        if state.evaluate is not None:
            errors.extend(_validate_evaluator(state_name, state.evaluate))

        # Validate routing configuration
        errors.extend(_validate_state_routing(state_name, state))

    # Check numeric field ranges
    if fsm.max_steps <= 0:
        errors.append(
            ValidationError(
                message=f"max_steps must be > 0, got {fsm.max_steps}",
                path="max_steps",
            )
        )
    if fsm.max_iterations is not None and fsm.max_iterations <= 0:
        errors.append(
            ValidationError(
                message=f"max_iterations must be > 0, got {fsm.max_iterations}",
                path="max_iterations",
            )
        )
    if fsm.max_edge_revisits <= 0:
        errors.append(
            ValidationError(
                message=f"max_edge_revisits must be > 0, got {fsm.max_edge_revisits}",
                path="max_edge_revisits",
            )
        )
    if fsm.backoff is not None and fsm.backoff < 0:
        errors.append(
            ValidationError(
                message=f"backoff must be >= 0, got {fsm.backoff}",
                path="backoff",
            )
        )
    if fsm.timeout is not None and fsm.timeout <= 0:
        errors.append(
            ValidationError(
                message=f"timeout must be > 0, got {fsm.timeout}",
                path="timeout",
            )
        )
    if fsm.llm.max_tokens <= 0:
        errors.append(
            ValidationError(
                message=f"llm.max_tokens must be > 0, got {fsm.llm.max_tokens}",
                path="llm.max_tokens",
            )
        )
    if fsm.llm.timeout <= 0:
        errors.append(
            ValidationError(
                message=f"llm.timeout must be > 0, got {fsm.llm.timeout}",
                path="llm.timeout",
            )
        )

    # Check for unreachable states (warning only)
    reachable = _find_reachable_states(fsm)
    unreachable = defined_states - reachable
    for state_name in unreachable:
        errors.append(
            ValidationError(
                message="State is not reachable from initial state",
                path=f"states.{state_name}",
                severity=ValidationSeverity.WARNING,
            )
        )

    errors.extend(_validate_failure_terminal_action(fsm))

    errors.extend(_validate_meta_loop_evaluation(fsm))

    errors.extend(_validate_input_key_without_guard(fsm))

    errors.extend(_validate_artifact_isolation(fsm))

    errors.extend(_validate_harness_multimodal_evaluator_blind_spot(fsm))

    errors.extend(_validate_partial_route_dead_end(fsm))

    errors.extend(_validate_artifact_overwrite(fsm))

    errors.extend(_validate_generator_fix_discipline(fsm))

    errors.extend(_validate_classify_route_default(fsm))

    errors.extend(_validate_zero_retry_counter(fsm))

    errors.extend(_validate_on_max_steps(fsm, defined_states))
    errors.extend(_validate_on_max_iterations(fsm, defined_states))

    errors.extend(_validate_circuit(fsm, defined_states))

    errors.extend(_validate_progress_paths_isolation(fsm))

    errors.extend(_validate_capture_reachability(fsm))

    return errors


def _is_meta_loop(fsm: FSMLoop) -> bool:
    """Return True if fsm is classified as a meta-loop.

    A loop is meta if ANY of the following match:
    1. Any state action string matches a harness-artifact path regex
       (writes another loop YAML, skill, agent, command, or project config)
    2. The loop's import list contains lib/benchmark.yaml
    3. Any state action references yaml_state_editor or replace_action
    """
    # Condition 2: imports lib/benchmark.yaml
    if any(imp in _META_LOOP_IMPORT_TRIGGERS for imp in fsm.imports):
        return True
    # Conditions 1 and 3: scan action strings
    for state in fsm.states.values():
        if state.action is None:
            continue
        for pattern in _META_LOOP_ACTION_PATTERNS:
            if pattern.search(state.action):
                return True
        for token in _META_LOOP_ACTION_TOKENS:
            if token in state.action:
                return True
    return False


def _validate_meta_loop_evaluation(fsm: FSMLoop) -> list[ValidationError]:
    """Validate meta-loop evaluation rules MR-1 and MR-2.

    MR-1 (ERROR): meta-loop must have at least one non-LLM evaluator.
    MR-2 (WARNING): meta-loop should reference a captured baseline in an evaluator.

    Both rules are suppressed by ``meta_self_eval_ok: true`` at the loop top-level.
    """
    errors: list[ValidationError] = []
    if fsm.meta_self_eval_ok or not _is_meta_loop(fsm):
        return errors

    # Collect all evaluator types used across all states
    evaluator_types: set[str] = set()
    for state in fsm.states.values():
        if state.evaluate is not None:
            evaluator_types.add(state.evaluate.type)

    # MR-1: must have at least one non-LLM evaluator
    if not evaluator_types & NON_LLM_EVALUATOR_TYPES:
        errors.append(
            ValidationError(
                message=(
                    "Loop modifies harness artifacts but has no non-LLM evaluator. "
                    "LLM self-grades on harness updates are unreliable (SHOR Table 1: "
                    "33-55% accuracy). Pair every check_semantic state with at least one "
                    "of: exit_code, output_numeric, convergence, diff_stall, action_stall, mcp_result. "
                    "Note: llm_structured and comparator both use the LLM and do not satisfy MR-1. "
                    "To suppress with justification, set `meta_self_eval_ok: true` at the "
                    "loop top-level."
                ),
                path="<root>",
                severity=ValidationSeverity.ERROR,
            )
        )

    # MR-2: should reference a captured baseline in a later evaluator
    capture_names: set[str] = {state.capture for state in fsm.states.values() if state.capture}
    if capture_names and not _has_baseline_reference(fsm, capture_names):
        errors.append(
            ValidationError(
                message=(
                    "Meta-loop appears to lack a measure→propose→apply→re-measure "
                    "spine: no captured baseline value is referenced by a later evaluator. "
                    "Meta-loops should compare a post-change score against a pre-change "
                    "baseline (see loops/harness-optimize.yaml as reference template). "
                    "To suppress, set `meta_self_eval_ok: true`."
                ),
                path="<root>",
                severity=ValidationSeverity.WARNING,
            )
        )

    return errors


# Regex patterns for detecting counter-increment actions.
# Must contain a printf/echo writing to a file AND an arithmetic increment.
_COUNTER_FILE_WRITE_RE = re.compile(r"(?:printf|echo)\s+.*>")
_COUNTER_INCREMENT_RE = re.compile(
    r"\$\(\(.*\+\s*1\s*\)\)"  # $((N + 1)) or $((N+1))
    r"|\+\+"  # C-style increment
    r"|\+=1"  # compound assignment
    r"|awk\s+.*\+\+"  # awk with increment
)


def _validate_zero_retry_counter(fsm: FSMLoop) -> list[ValidationError]:
    """Detect counter + output_numeric combos that yield zero effective retries.

    A common loop-authoring footgun: a state increments a counter file and then
    evaluates ``output_numeric`` with ``operator: lt, target: 1`` against it.
    After the first increment the counter is 1, ``1 < 1 == false``, so the
    retry budget is 0 by construction. Author almost always intended target=2.
    """
    errors: list[ValidationError] = []

    for state_name, state in fsm.states.items():
        if not state.action or not state.evaluate:
            continue

        ev = state.evaluate
        if ev.type != "output_numeric":
            continue
        if ev.operator is None or ev.target is None:
            continue

        # Must be a number-like target for numeric comparison
        try:
            target = float(ev.target)
        except (ValueError, TypeError):
            continue

        if not _is_counter_action(state.action):
            continue

        # Check: after first increment (0→1), does operator(1, target) already fail?
        op_fn = _NUMERIC_OPERATORS.get(ev.operator)
        if op_fn is None:
            continue

        if not op_fn(1.0, target):
            suggested_target = _suggested_target(ev.operator, target)
            errors.append(
                ValidationError(
                    message=(
                        f"Zero retry budget: operator={ev.operator} target={target} "
                        f"means the first post-increment value (1) already fails "
                        f"({ev.operator}(1, {target}) == False). "
                        f"Did you mean target={suggested_target}?"
                    ),
                    path=f"states.{state_name}.evaluate",
                    severity=ValidationSeverity.WARNING,
                )
            )

    return errors


def _is_counter_action(action: str) -> bool:
    """Return True if the action string contains a counter-increment pattern."""
    return bool(_COUNTER_FILE_WRITE_RE.search(action) and _COUNTER_INCREMENT_RE.search(action))


def _suggested_target(operator: str, target: float) -> str:
    """Suggest a target value that allows at least one retry."""
    # For lt/le with a too-low target, suggest target+1 so first post-increment passes
    if operator in ("lt", "le"):
        return str(int(target) + 1)
    # For eq with target=0, suggest 1 so the counter can eventually match
    if operator == "eq" and target == 0:
        return "1"
    # For other cases, suggest target+1 as a default nudge
    return str(int(target) + 1)


def _validate_harness_multimodal_evaluator_blind_spot(fsm: FSMLoop) -> list[ValidationError]:
    """Warn when harness loops use LLM multimodal eval as sole gate to terminal.

    LLMs can silently fall back to text-only analysis when reading images,
    producing verdicts based on incomplete information. The output_contains
    evaluator can verify the LLM wrote the pass string but not that it
    actually processed the image. This is the same class of failure as MR-1
    (LLM self-evaluation bias) applied to artifact evaluation rather than
    harness modification.

    Suppressed by ``meta_self_eval_ok: true`` at the loop top-level.
    """
    errors: list[ValidationError] = []
    if fsm.meta_self_eval_ok or fsm.category != "harness":
        return errors

    terminal_states = fsm.get_terminal_states()

    for state_name, state in fsm.states.items():
        if state.action_type != "prompt" or not state.action:
            continue
        if state.evaluate is None or state.evaluate.type != "output_contains":
            continue
        if not any(p.search(state.action) for p in _MULTIMODAL_EVAL_PATTERNS):
            continue
        if state.on_yes not in terminal_states:
            continue
        errors.append(
            ValidationError(
                message=(
                    f"State '{state_name}' evaluates a screenshot/image via LLM "
                    "prompt and routes directly to a terminal on success. The "
                    "output_contains evaluator can verify the LLM wrote the pass "
                    "string but not that the LLM actually processed the image. "
                    "Consider adding a shell-action verification state (e.g., "
                    "functional smoke test) between scoring and the terminal."
                ),
                path=f"states.{state_name}",
                severity=ValidationSeverity.WARNING,
            )
        )

    return errors


def _find_shared_tmp_writes(fsm: FSMLoop) -> list[tuple[str, str]]:
    """Return (state_name, matched_path) for every action referencing shared .loops/tmp/.

    Scans `state.action` only. Prompts and sub-loop bindings can also reference
    paths, but those are out of static-scan reach: action strings are the
    place where loop YAMLs directly encode artifact paths.
    """
    findings: list[tuple[str, str]] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        for match in _SHARED_TMP_PATH_RE.finditer(state.action):
            findings.append((state_name, match.group(0)))
    return findings


def _validate_input_key_without_guard(fsm: FSMLoop) -> list[ValidationError]:
    """Warn when a loop sets a custom input_key but omits required_inputs.

    A loop that accepts a runtime input via a named key (e.g. input_key: description)
    but doesn't declare required_inputs will silently proceed with an empty value if the
    user forgets to pass one. Declaring required_inputs shifts that failure to start-time.
    """
    if fsm.input_key == "input":
        return []
    if fsm.required_inputs:
        return []
    return [
        ValidationError(
            message=(
                f"Loop sets input_key: '{fsm.input_key}' but does not declare "
                f"required_inputs. If this input is mandatory, add "
                f"'required_inputs: [\"{fsm.input_key}\"]' to make the runner "
                f"abort when no input is provided."
            ),
            path="required_inputs",
            severity=ValidationSeverity.WARNING,
        )
    ]


def _validate_artifact_isolation(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-3: loops must isolate artifacts to ${context.run_dir}.

    The runner injects ${context.run_dir} pointing at .loops/runs/<loop>-<ts>/
    and creates the folder before execution. Loops that write intermediate
    state (queues, checkpoints, generated files) to shared .loops/tmp/ paths
    will corrupt each other under concurrent runs (ll-parallel workers, retries,
    repeated invocations).

    Suppressed by `shared_state_ok: true` at the loop top-level for loops that
    intentionally share state across runs.
    """
    if fsm.shared_state_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, path in _find_shared_tmp_writes(fsm):
        errors.append(
            ValidationError(
                message=(
                    f"State writes to shared '{path}' instead of "
                    "'${context.run_dir}/...'. Concurrent runs of this loop "
                    "(e.g., under ll-parallel) will corrupt each other's state. "
                    "Use the runner-injected `${context.run_dir}` for per-run "
                    "artifact paths, or set `shared_state_ok: true` at the loop "
                    "top-level if cross-run sharing is intentional."
                ),
                path=f"states.{state_name}.action",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


def _is_llm_judged(state: StateConfig) -> bool:
    """Return True if this state will be graded by the default LLM judge.

    Mirrors the action-mode detection in executor._action_mode() (not imported
    here because that is runtime code). A state is LLM-judged when:
    - it has no explicit evaluate block AND its action is a prompt or slash_command, OR
    - it has an explicit evaluate block of type llm_structured or check_semantic.
    """
    if state.evaluate is None:
        # Heuristic: explicit action_type wins; fall back to leading "/" on action string.
        action_type = state.action_type
        if action_type in ("prompt", "slash_command"):
            return True
        if action_type is None and state.action and state.action.lstrip().startswith("/"):
            return True
        return False
    return state.evaluate.type in ("llm_structured", "check_semantic")


def _validate_partial_route_dead_end(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-4: LLM-judged states with only on_yes have a partial/no dead-end.

    A state gated by the default LLM judge can receive yes/no/partial verdicts.
    If only on_yes is mapped (and no on_no, on_partial, next, or route table with
    a default exist), a partial or no verdict returns None from _route and silently
    terminates the loop — the parent treats this as failed.

    Suppressed by `partial_route_ok: true` at the loop top-level for the rare
    case where dead-ending on a non-yes verdict is intentional.
    """
    if fsm.partial_route_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if not _is_llm_judged(state):
            continue
        # States with an unconditional next: or a full route: table are safe.
        if state.next is not None or state.route is not None:
            continue
        # Only flag when on_yes is set but at least one of on_no/on_partial is missing.
        if state.on_yes is None:
            continue
        missing = [v for v in ("no", "partial") if getattr(state, f"on_{v}") is None]
        if not missing:
            continue
        unrouted = " or ".join(f"`{v}`" for v in missing)
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] LLM-judged prompt routes only on_yes; "
                    f"a {unrouted} verdict has no route and will dead-end the loop "
                    "(parent reads this as failed). Add on_no/on_partial, use `next:` "
                    "for an unconditional handoff, or a `route:` table with a default. "
                    "Set `partial_route_ok: true` at the loop top-level to suppress "
                    "if intentional. (ENH-1917)"
                ),
                path=f"states.{state_name}",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


def _validate_artifact_overwrite(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-5 (ENH-1957): harness loops should version artifacts per iteration.

    A harness-category loop that iteratively generates and overwrites a flat artifact
    path (e.g. ``${context.run_dir}/image.svg``) loses all intermediate versions.
    Only the final iteration survives. This rule flags iterative generate→evaluate→generate
    cycles that write to artifact paths without declaring versioning intent.

    Suppressed by ``artifact_versioning: true`` (loop snapshots per-iteration artifacts)
    or ``artifact_versioning_ok: true`` (intentional overwrite, e.g. artifact varies
    by task).
    """
    if fsm.artifact_versioning or fsm.artifact_versioning_ok:
        return []
    if fsm.category not in ("harness",):
        return []

    errors: list[ValidationError] = []

    # Find states that write to artifact paths (shell actions with file output)
    writers: dict[str, set[str]] = {}  # state_name -> set of artifact paths
    for state_name, state in fsm.states.items():
        if not state.action or state.action_type not in ("shell", None):
            continue
        # Skip sub-loop delegation states
        if state.action_type == "loop":
            continue
        action = state.action
        # Find run_dir-based artifact writes: ${context.run_dir}/<path> or $RUNDIR/<path>
        import re

        # Match patterns like: ${context.run_dir}/output.svg, $RUNDIR/image.png, > path
        # We look for output redirections or cp/mv commands writing to run_dir
        artifact_refs = set()
        for pattern in (
            r'\$\{context\.run_dir\}/([^\s"\';&]+)',
            r'\$\{captured\.[^}]+\}/([^\s"\';&]+)',
        ):
            for m in re.finditer(pattern, action):
                artifact_refs.add(m.group(1))
        # Also detect explicit cp/mv writing to run_dir paths
        for m in re.finditer(r'(?:cp|mv)\s+.*\s+\$\{context\.run_dir\}/([^\s"\';&]+)', action):
            artifact_refs.add(m.group(1))
        if artifact_refs:
            writers[state_name] = artifact_refs

    if not writers:
        return []

    # Detect iterative cycles: a writer state that is reachable from itself
    # via a non-trivial path through other states (generate → evaluate → generate)
    for state_name in writers:
        refs = fsm.states[state_name].get_referenced_states()
        # Check if this writer or its downstream states loop back to this writer
        visited: set[str] = set()
        to_visit = list(refs - {"$current"})
        while to_visit:
            target = to_visit.pop()
            if target in visited or target not in fsm.states:
                continue
            visited.add(target)
            if target == state_name:
                # Found a cycle: this writer state is reachable from itself
                artifact_list = ", ".join(sorted(writers[state_name]))
                errors.append(
                    ValidationError(
                        message=(
                            f"[state: {state_name}] Harness loop writes artifact(s) "
                            f"({artifact_list}) to a flat path in an iterative cycle "
                            f"({state_name} → ... → {state_name}). Per-iteration versions "
                            "are lost; only the final output survives. Add per-iteration "
                            "snapshots (see oracle generator-evaluator for pattern) and "
                            "declare `artifact_versioning: true`, or set "
                            "`artifact_versioning_ok: true` if intentional. (ENH-1957)"
                        ),
                        path=f"states.{state_name}",
                        severity=ValidationSeverity.WARNING,
                    )
                )
                break
            target_state = fsm.states.get(target)
            if target_state is not None:
                target_refs = target_state.get_referenced_states()
                for r in target_refs:
                    if r != "$current" and r not in visited:
                        to_visit.append(r)

    return errors


def _validate_generator_fix_discipline(fsm: FSMLoop) -> list[ValidationError]:
    """Validate rule MR-6 (ENH-2079): meta-loops should not hand-patch generator artifacts.

    Detects the hand-patching anti-pattern: a ``shell``-type state that writes to the
    same file path as a non-shell (LLM-type) generator state in the same loop.
    Hand-patching creates fragile output that diverges from the generator on the next
    run; the stable fix is to update the generator action instead.

    Suppressed by ``generator_fix_ok: true`` at the loop top-level for intentional
    post-processing cases.
    """
    if fsm.generator_fix_ok or not _is_meta_loop(fsm):
        return []

    # Markers that indicate a prompt/slash_command state is generating file artifacts
    _GENERATOR_MARKERS = ("yaml_state_editor", "replace_action", "to_file:")

    _PATH_PATTERNS = (
        re.compile(r'\$\{context\.run_dir\}/([^\s"\';&|]+)'),
        re.compile(r'\$\{captured\.[^}]+\}/([^\s"\';&|]+)'),
    )

    def _extract_paths(action: str) -> set[str]:
        paths: set[str] = set()
        for pat in _PATH_PATTERNS:
            for m in pat.finditer(action):
                paths.add(m.group(1).rstrip("/"))
        return paths

    shell_targets: dict[str, set[str]] = {}  # state_name -> set of file paths
    generator_targets: dict[str, set[str]] = {}  # state_name -> set of file paths

    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        action = state.action
        paths = _extract_paths(action)
        if not paths:
            continue
        action_type = state.action_type
        if action_type in ("shell", None):
            shell_targets[state_name] = paths
        elif action_type in ("prompt", "slash_command"):
            if any(marker in action for marker in _GENERATOR_MARKERS):
                generator_targets[state_name] = paths

    errors: list[ValidationError] = []
    for gen_name, gen_paths in generator_targets.items():
        for shell_name, shell_paths in shell_targets.items():
            overlap = gen_paths & shell_paths
            if overlap:
                artifact_list = ", ".join(sorted(overlap))
                errors.append(
                    ValidationError(
                        message=(
                            f"[states: {gen_name}, {shell_name}] Hand-patching anti-pattern: "
                            f"LLM-generator state '{gen_name}' and shell state '{shell_name}' "
                            f"both write to ({artifact_list}). Move the fix into the generator "
                            "action so every run produces correct output automatically. "
                            "Set `generator_fix_ok: true` to suppress for intentional "
                            "post-processing. (ENH-2079)"
                        ),
                        path=f"states.{shell_name}",
                        severity=ValidationSeverity.WARNING,
                    )
                )

    return errors


def _validate_classify_route_default(fsm: FSMLoop) -> list[ValidationError]:
    """Validate that classify states with a route: table include a default: fallback.

    A ``classify`` state whose ``route:`` table has no ``default:`` will dead-end
    whenever the action emits a token not listed in the table. This rule flags
    that gap as a WARNING so loop authors add a catch-all branch.

    Suppressed by ``partial_route_ok: true`` at the loop top-level when a
    dead-end on an unlisted token is intentional.
    """
    if fsm.partial_route_ok:
        return []
    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if state.evaluate is None or state.evaluate.type != "classify":
            continue
        if state.route is None or state.route.default is not None:
            continue
        errors.append(
            ValidationError(
                message=(
                    f"[state: {state_name}] classify route: table has no default: — "
                    "unknown tokens will dead-end the loop. Add a default: catch-all, "
                    "or set `partial_route_ok: true` at the loop top-level to suppress."
                ),
                path=f"states.{state_name}",
                severity=ValidationSeverity.WARNING,
            )
        )
    return errors


def _has_baseline_reference(fsm: FSMLoop, capture_names: set[str]) -> bool:
    """Return True if any evaluate block references a captured variable."""
    for state in fsm.states.values():
        ev = state.evaluate
        if ev is None:
            continue
        # Check string fields that may interpolate captured values
        candidates = [ev.previous, ev.source]
        if isinstance(ev.target, str):
            candidates.append(ev.target)
        for field_val in candidates:
            if not field_val:
                continue
            for name in capture_names:
                if f"captured.{name}" in field_val:
                    return True
    return False


def _validate_on_max_steps(fsm: FSMLoop, defined_states: set[str]) -> list[ValidationError]:
    """Validate the top-level `on_max_steps` field (BUG-2204).

    Checks that the named state exists when `on_max_steps` is set.
    """
    errors: list[ValidationError] = []
    if fsm.on_max_steps is None:
        return errors
    if fsm.on_max_steps not in defined_states:
        errors.append(
            ValidationError(
                message=(
                    f"on_max_steps references unknown state "
                    f"'{fsm.on_max_steps}' (must be a declared state)"
                ),
                path="on_max_steps",
            )
        )
    return errors


def _validate_on_max_iterations(fsm: FSMLoop, defined_states: set[str]) -> list[ValidationError]:
    """Validate the top-level `on_max_iterations` field (BUG-2204: iteration-cap summary state).

    Checks that the named state exists when `on_max_iterations` is set.
    """
    errors: list[ValidationError] = []
    if fsm.on_max_iterations is None:
        return errors
    if fsm.on_max_iterations not in defined_states:
        errors.append(
            ValidationError(
                message=(
                    f"on_max_iterations references unknown state "
                    f"'{fsm.on_max_iterations}' (must be a declared state)"
                ),
                path="on_max_iterations",
            )
        )
    return errors


def _validate_circuit(fsm: FSMLoop, defined_states: set[str]) -> list[ValidationError]:
    """Validate the top-level `circuit:` block (FEAT-1637).

    Checks:
    - `circuit.repeated_failure.window` is a positive integer.
    - `circuit.repeated_failure.on_repeated_failure` is either the special
      token ``"abort"`` or the name of a declared state.
    """
    errors: list[ValidationError] = []
    if fsm.circuit is None or fsm.circuit.repeated_failure is None:
        return errors

    rf = fsm.circuit.repeated_failure
    if rf.window < 1:
        errors.append(
            ValidationError(
                message=f"circuit.repeated_failure.window must be >= 1, got {rf.window}",
                path="circuit.repeated_failure.window",
            )
        )

    if rf.recurrent_window is not None and rf.recurrent_window < 2:
        errors.append(
            ValidationError(
                message=(
                    f"circuit.repeated_failure.recurrent_window must be >= 2, "
                    f"got {rf.recurrent_window}"
                ),
                path="circuit.repeated_failure.recurrent_window",
            )
        )

    target = rf.on_repeated_failure
    if target not in STALL_SPECIAL_TOKENS and target not in defined_states:
        errors.append(
            ValidationError(
                message=(
                    f"circuit.repeated_failure.on_repeated_failure references "
                    f"unknown state '{target}' (must be a declared state or "
                    f'the literal "abort")'
                ),
                path="circuit.repeated_failure.on_repeated_failure",
            )
        )

    return errors


# Matches common interpolation prefixes used in loop YAML paths so we can
# extract the portable relative component for action-string scanning.
_INTERPOLATION_PREFIX_RE = re.compile(r"^\$\{[^}]+\}/")


def _strip_interpolation_prefix(path: str) -> str:
    """Return the path with any leading ${...}/ prefix removed."""
    return _INTERPOLATION_PREFIX_RE.sub("", path)


def _validate_progress_paths_isolation(fsm: FSMLoop) -> list[ValidationError]:
    """Warn when a state's action writes to a file listed in progress_paths (BUG-1767).

    When a loop's own bookkeeping files appear in both progress_paths and the
    state action strings, every append to those files resets the stall window,
    silently disabling the BUG-1674 stall guard for that loop. Authors should
    move such files to exclude_paths so the stall detector can still fire.
    """
    if fsm.circuit is None or fsm.circuit.repeated_failure is None:
        return []
    rf = fsm.circuit.repeated_failure
    if not rf.progress_paths:
        return []

    # Build a set of the relative path components we need to look for.
    watched = {_strip_interpolation_prefix(p) for p in rf.progress_paths}
    # Exclude paths that are already in exclude_paths — author acknowledged.
    excluded = {_strip_interpolation_prefix(p) for p in rf.exclude_paths}
    active_watched = watched - excluded
    if not active_watched:
        return []

    errors: list[ValidationError] = []
    for state_name, state in fsm.states.items():
        if not state.action:
            continue
        for path_fragment in active_watched:
            if path_fragment in state.action:
                errors.append(
                    ValidationError(
                        message=(
                            f"State action references '{path_fragment}', which is also "
                            "listed in circuit.repeated_failure.progress_paths. Writes "
                            "to this file will reset the stall window every cycle, "
                            "silently disabling stall detection. Move it to "
                            "circuit.repeated_failure.exclude_paths to separate "
                            "bookkeeping files from real progress signals."
                        ),
                        path=f"states.{state_name}.action",
                        severity=ValidationSeverity.WARNING,
                    )
                )
    return errors


def _dominated_by_any(fsm: FSMLoop, dominators: set[str], dominated: str) -> bool:
    """Return True if the set ``dominators`` collectively dominates ``dominated``.

    Group domination: every path from the initial state to ``dominated`` must
    pass through at least one state in ``dominators``. Checked by removing all
    dominator states from the graph and testing whether ``dominated`` is still
    reachable from the initial state.

    This generalizes single-state domination — used when a capture variable is
    produced by more than one state on mutually-exclusive branches, where the
    reference is safe as long as *some* capturing state runs on every path.

    Args:
        fsm: The FSM loop to analyze
        dominators: Names of the states that should collectively dominate
        dominated: Name of the state that should be dominated

    Returns:
        True if the dominators collectively dominate ``dominated``
    """
    if dominated in dominators:
        return True
    if dominated not in fsm.states:
        return False

    visited: set[str] = set()
    to_visit: deque[str] = deque([fsm.initial])

    while to_visit:
        current = to_visit.popleft()
        if current in visited or current not in fsm.states:
            continue
        if current in dominators:
            continue  # Block this node (simulate removal)

        visited.add(current)

        if current == dominated:
            # Reached dominated without going through any dominator
            return False

        state = fsm.states[current]
        for ref in state.get_referenced_states():
            if ref != "$current" and ref not in visited:
                to_visit.append(ref)

    # Dominated not reachable without the dominators → they dominate
    return True


def _dominates(fsm: FSMLoop, dominator: str, dominated: str) -> bool:
    """Return True if dominator dominates dominated in the FSM graph.

    A state D dominates S if every path from the initial state to S must pass
    through D. Thin single-state wrapper around :func:`_dominated_by_any`.
    """
    if dominator not in fsm.states:
        return False
    return _dominated_by_any(fsm, {dominator}, dominated)


def _find_bypass_path_any(fsm: FSMLoop, dominators: set[str], dominated: str) -> list[str]:
    """Find an example path from initial to dominated that bypasses all dominators.

    Uses BFS to find the shortest path that avoids every state in ``dominators``.
    Returns empty list if no bypass exists (should not happen when called after
    :func:`_dominated_by_any` returns False).
    """
    parent: dict[str, str] = {}
    to_visit: deque[str] = deque([fsm.initial])
    visited: set[str] = set()

    while to_visit:
        current = to_visit.popleft()
        if current in visited or current not in fsm.states:
            continue
        if current in dominators:
            continue

        visited.add(current)

        if current == dominated:
            # Reconstruct path
            path = [dominated]
            while path[-1] in parent:
                path.append(parent[path[-1]])
            path.reverse()
            return path

        state = fsm.states[current]
        for ref in state.get_referenced_states():
            if ref != "$current" and ref not in visited:
                if ref not in parent:
                    parent[ref] = current
                to_visit.append(ref)

    return []


def _find_bypass_path(fsm: FSMLoop, dominator: str, dominated: str) -> list[str]:
    """Find an example path from initial to dominated that bypasses dominator.

    Thin single-state wrapper around :func:`_find_bypass_path_any`.
    """
    return _find_bypass_path_any(fsm, {dominator}, dominated)


def _has_sub_loop_state(fsm: FSMLoop) -> bool:
    """Return True if any state in the FSM has ``loop:`` set (delegates to a child loop).

    Used by ENH-1961 to distinguish "capture lives in a sub-loop" from "capture is missing".
    """
    return any(state.loop is not None for state in fsm.states.values())


def _validate_capture_reachability(fsm: FSMLoop) -> list[ValidationError]:
    """Validate that ``${captured.*}`` references are dominated by their capturing states.

    ENH-1961: For each state that references ``${captured.<var>.*}`` in its action
    or evaluate source, checks that the capturing state dominates the referencing
    state (i.e., all paths from the initial state pass through the capture state).

    Emits:
    - WARNING when a capture state does not dominate a referencing state
      (the reference may crash at runtime on paths that bypass the capture).
    - ERROR when a referenced capture variable has no capturing state at all
      in this FSM (excluding sub-loop captures which live in child namespaces).
    """
    errors: list[ValidationError] = []

    # Step 1: Build capture map (var_name → set of capturing state names).
    # A variable may be captured by more than one state on mutually-exclusive
    # branches (e.g. fifo_pop vs select_next dispatched by schedule_mode); the
    # reference is safe as long as the *set* collectively dominates it.
    capture_map: dict[str, set[str]] = {}
    for state_name, state in fsm.states.items():
        if state.capture:
            capture_map.setdefault(state.capture, set()).add(state_name)

    # Step 2: Build reference map (state_name → set of captured var names referenced)
    reference_map: dict[str, set[str]] = {}
    for state_name, state in fsm.states.items():
        # Skip sub-loop delegation states — their action is a loop name,
        # and captured vars belong to the child loop's namespace.
        if state.loop is not None:
            continue

        # Only collect references NOT guarded by `:default=` — a guarded
        # reference is safe even when the capture is missing on some path.
        refs: set[str] = set()
        if state.action:
            refs.update(_unguarded_captured_refs(state.action))
        if state.evaluate is not None and state.evaluate.source:
            refs.update(_unguarded_captured_refs(state.evaluate.source))
        if refs:
            reference_map[state_name] = refs

    if not reference_map:
        return errors

    # Step 3: For each reference, check dominance of capturing state
    for ref_state_name, ref_vars in reference_map.items():
        for var_name in ref_vars:
            if var_name not in capture_map:
                # Referenced capture variable has no capturing state in this FSM.
                # ENH-1998: downgrade to WARNING (not silent skip) when sub-loops
                # are present — the capture may live in a child namespace, but a
                # typo'd name should still surface rather than go completely dark.
                if _has_sub_loop_state(fsm):
                    errors.append(
                        ValidationError(
                            message=(
                                f"References ${{captured.{var_name}.*}} but no state in "
                                f"this loop captures '{var_name}'. "
                                f"If '{var_name}' is produced by a sub-loop, this may be "
                                f"intentional; otherwise add 'capture: {var_name}' to the "
                                f"state that produces this value."
                            ),
                            path=f"states.{ref_state_name}.action",
                            severity=ValidationSeverity.WARNING,
                        )
                    )
                    continue
                # No sub-loops: this is genuinely missing.
                errors.append(
                    ValidationError(
                        message=(
                            f"References ${{captured.{var_name}.*}} but no state in "
                            f"this loop captures '{var_name}'. Add 'capture: {var_name}' "
                            f"to the state that produces this value."
                        ),
                        path=f"states.{ref_state_name}.action",
                        severity=ValidationSeverity.ERROR,
                    )
                )
                continue

            # Capturing states present in this FSM (shouldn't drop any normally)
            cap_states = {s for s in capture_map[var_name] if s in fsm.states}
            if not cap_states:
                continue

            # Group dominance check: do the capturing states collectively
            # dominate ref_state_name (does at least one run on every path)?
            if not _dominated_by_any(fsm, cap_states, ref_state_name):
                bypass_path = _find_bypass_path_any(fsm, cap_states, ref_state_name)
                path_str = " → ".join(bypass_path) if bypass_path else "unknown path"

                if len(cap_states) == 1:
                    captured_by = f"state '{next(iter(cap_states))}' which may not"
                else:
                    names = ", ".join(f"'{s}'" for s in sorted(cap_states))
                    captured_by = f"states {names}, none of which"

                errors.append(
                    ValidationError(
                        message=(
                            f"References ${{captured.{var_name}.*}} but '{var_name}' "
                            f"is captured by {captured_by} "
                            f"execute on all paths to '{ref_state_name}'. "
                            f"Path(s) bypassing capture: {path_str}"
                        ),
                        path=f"states.{ref_state_name}.action",
                        severity=ValidationSeverity.WARNING,
                    )
                )

    return errors


def _find_reachable_states(fsm: FSMLoop) -> set[str]:
    """Find all states reachable from the initial state.

    Uses breadth-first search to find all reachable states. Seeds the BFS
    with the initial state plus top-level transition targets that act as
    alternate entry points: ``on_max_iterations`` (fires when the iteration
    cap is hit) and ``circuit.repeated_failure.on_repeated_failure`` (fires
    when the circuit breaker trips). These are real edges the runtime can
    take, so states reached only through them are not orphans.

    Args:
        fsm: The FSM loop to analyze

    Returns:
        Set of reachable state names
    """
    reachable: set[str] = set()
    to_visit: deque[str] = deque([fsm.initial])
    if fsm.on_max_steps is not None:
        to_visit.append(fsm.on_max_steps)
    if fsm.on_max_iterations is not None:
        to_visit.append(fsm.on_max_iterations)
    if fsm.circuit is not None and fsm.circuit.repeated_failure is not None:
        target = fsm.circuit.repeated_failure.on_repeated_failure
        if target not in STALL_SPECIAL_TOKENS:
            to_visit.append(target)

    while to_visit:
        current = to_visit.popleft()
        if current in reachable or current not in fsm.states:
            continue

        reachable.add(current)
        state = fsm.states[current]
        refs = state.get_referenced_states()

        for ref in refs:
            if ref != "$current" and ref not in reachable:
                to_visit.append(ref)

    return reachable


def is_runnable_loop(path: Path) -> bool:
    """Cheap check for whether a YAML file is a runnable FSM loop definition.

    Returns True iff the file parses as a YAML mapping with the required
    top-level keys ``name``, ``initial``, and either ``states`` or ``flow``
    (the shorthand resolved by :func:`resolve_flow`). This matches the
    required-fields gate in :func:`load_and_validate` so "counted by the
    verifier" stays in sync with "runnable by ll-loop validate".

    When the raw YAML contains a ``from:`` key, inheritance is resolved first
    (mirroring :func:`load_and_validate`) so pure context-override stubs whose
    parent provides ``initial``/``states`` return True. Library fragments under
    ``loops/lib/`` still return False — their parent chain also lacks ``initial``.
    """
    try:
        data = yaml.safe_load(path.read_text())
    except (OSError, yaml.YAMLError):
        return False
    if not isinstance(data, dict):
        return False
    if "from" in data:
        try:
            data = resolve_inheritance(data, path.parent)
        except Exception:
            return False
    has_flow = "states" in data or "flow" in data
    return "name" in data and "initial" in data and has_flow


def load_and_validate(
    path: Path,
    raise_on_error: bool = True,
) -> tuple[FSMLoop, list[ValidationError]]:
    """Load YAML file and validate FSM structure.

    Args:
        path: Path to the YAML file to load
        raise_on_error: When True (default), raise ValueError on ERROR violations.
            When False, return all violations (errors + warnings) without raising.

    Returns:
        When raise_on_error=True: (FSMLoop, list of WARNING-severity ValidationErrors)
        When raise_on_error=False: (FSMLoop, list of all ValidationErrors sorted errors-first)

    Raises:
        FileNotFoundError: If the file doesn't exist
        yaml.YAMLError: If the file is not valid YAML
        ValueError: If raise_on_error=True and validation fails (contains error details)
    """
    if not path.exists():
        raise FileNotFoundError(f"FSM file not found: {path}")

    with open(path) as f:
        data: dict[str, Any] = yaml.safe_load(f)

    if not isinstance(data, dict):
        raise ValueError(f"FSM file must contain a YAML mapping, got {type(data)}")

    # Resolve `from:` inheritance before any further checks, so a child loop
    # can omit fields its parent provides (including `initial`/`states`) and
    # so a parent's `import:`/`fragments:` blocks survive into the merged
    # result for the subsequent `resolve_fragments` pass.
    data = resolve_inheritance(data, path.parent)

    # Expand flow: linear shorthand into states: before required-fields check
    data = resolve_flow(data)

    # Check required fields before parsing
    missing = []
    for field in ["name", "initial"]:
        if field not in data:
            missing.append(field)
    if "states" not in data:
        missing.append("states (or flow)")

    if missing:
        raise ValueError(f"FSM file missing required fields: {', '.join(missing)}")

    # Check for unknown top-level keys before parsing
    unknown_key_warnings: list[ValidationError] = []
    unknown = set(data.keys()) - KNOWN_TOP_LEVEL_KEYS
    if unknown:
        unknown_key_warnings.append(
            ValidationError(
                path="<root>",
                message=f"Unknown top-level keys: {', '.join(sorted(unknown))}",
                severity=ValidationSeverity.WARNING,
            )
        )

    visibility_val = data.get("visibility")
    if visibility_val is not None and visibility_val not in VALID_VISIBILITY:
        unknown_key_warnings.append(
            ValidationError(
                path="visibility",
                message=(
                    f"Invalid visibility: {visibility_val!r}. "
                    f"Must be one of: {', '.join(sorted(VALID_VISIBILITY))}. "
                    "Loop will be treated as 'public'."
                ),
                severity=ValidationSeverity.WARNING,
            )
        )

    # Resolve fragment libraries before parsing into dataclass
    data = resolve_fragments(data, path.parent)

    # Parse into dataclass
    fsm = FSMLoop.from_dict(data)

    # Validate
    errors = validate_fsm(fsm)

    # Validate with: bindings against child loop parameters (requires file-system access)
    errors.extend(_validate_with_bindings(fsm, path.parent))
    errors.extend(_validate_loop_references(fsm, path.parent))
    errors.extend(_validate_fragment_bindings(fsm, path.parent))

    # Filter to errors only (not warnings) for raising
    error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
    struct_warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
    all_warnings = unknown_key_warnings + struct_warnings

    if not raise_on_error:
        return fsm, error_list + all_warnings

    if error_list:
        error_messages = "\n  ".join(str(e) for e in error_list)
        raise ValueError(f"FSM validation failed:\n  {error_messages}")

    for warning in all_warnings:
        logger.warning(str(warning))

    return fsm, all_warnings

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
from collections import deque
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

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
    "llm_structured": [],
    "mcp_result": [],
    "harbor_scorer": [],
}

# Valid comparison operators
VALID_OPERATORS = {"eq", "ne", "lt", "le", "gt", "ge"}

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
        "max_iterations",
        "max_edge_revisits",
        "backoff",
        "timeout",
        "default_timeout",
        "maintain",
        "llm",
        "on_handoff",
        "input_key",
        "config",
        "category",
        "labels",
        "commands",
        "targets",
        "import",
        "fragments",
        "from",
        "flow",
        "state_defs",
    }
)

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
        if not state.learning.targets:
            errors.append(
                ValidationError(
                    message="type=learning requires non-empty 'learning.targets'",
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
    if fsm.max_iterations <= 0:
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

    return errors


def _find_reachable_states(fsm: FSMLoop) -> set[str]:
    """Find all states reachable from the initial state.

    Uses breadth-first search to find all reachable states.

    Args:
        fsm: The FSM loop to analyze

    Returns:
        Set of reachable state names
    """
    reachable: set[str] = set()
    to_visit: deque[str] = deque([fsm.initial])

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


def load_and_validate(path: Path) -> tuple[FSMLoop, list[ValidationError]]:
    """Load YAML file and validate FSM structure.

    Args:
        path: Path to the YAML file to load

    Returns:
        Tuple of (validated FSMLoop instance, list of WARNING-severity ValidationErrors)

    Raises:
        FileNotFoundError: If the file doesn't exist
        yaml.YAMLError: If the file is not valid YAML
        ValueError: If validation fails (contains error details)
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

    # Resolve fragment libraries before parsing into dataclass
    data = resolve_fragments(data, path.parent)

    # Parse into dataclass
    fsm = FSMLoop.from_dict(data)

    # Validate
    errors = validate_fsm(fsm)

    # Validate with: bindings against child loop parameters (requires file-system access)
    errors.extend(_validate_with_bindings(fsm, path.parent))

    # Filter to errors only (not warnings) for raising
    error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]

    if error_list:
        error_messages = "\n  ".join(str(e) for e in error_list)
        raise ValueError(f"FSM validation failed:\n  {error_messages}")

    # Collect all warnings (unknown-key warnings + structural warnings)
    struct_warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
    all_warnings = unknown_key_warnings + struct_warnings
    for warning in all_warnings:
        logger.warning(str(warning))

    return fsm, all_warnings

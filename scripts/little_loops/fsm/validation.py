"""FSM loop validation logic.

This module provides validation for FSM loop definitions, ensuring
structural correctness and catching common configuration errors.

Validation checks:
- Initial state exists in states dict
- All referenced states exist
- At least one terminal state
- Evaluator configs have required fields for their type
- No conflicting routing (shorthand vs full route)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any

import yaml

from little_loops.fsm.schema import EvaluateConfig, FSMLoop, StateConfig

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
    "llm_structured": [],
}

# Valid comparison operators
VALID_OPERATORS = {"eq", "ne", "lt", "le", "gt", "ge"}


def _validate_evaluator(
    state_name: str, evaluate: EvaluateConfig
) -> list[ValidationError]:
    """Validate evaluator configuration for type-specific requirements.

    Args:
        state_name: Name of the state containing this evaluator
        evaluate: The evaluator configuration to validate

    Returns:
        List of validation errors found
    """
    errors: list[ValidationError] = []
    path = f"states.{state_name}.evaluate"

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
        if evaluate.tolerance is not None and evaluate.tolerance < 0:
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

    return errors


def _validate_state_routing(
    state_name: str, state: StateConfig
) -> list[ValidationError]:
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
        state.on_success is not None
        or state.on_failure is not None
        or state.on_error is not None
    )
    has_route = state.route is not None

    # Warn about conflicting definitions
    if has_shorthand and has_route:
        errors.append(
            ValidationError(
                message="Both shorthand routing (on_success/on_failure/on_error) "
                "and full route table defined. Route table will take precedence.",
                path=path,
                severity=ValidationSeverity.WARNING,
            )
        )

    # Check for no valid transition definition
    has_next = state.next is not None
    has_terminal = state.terminal

    if not has_shorthand and not has_route and not has_next and not has_terminal:
        errors.append(
            ValidationError(
                message="State has no transition defined. Add routing, 'next', "
                "or mark as 'terminal: true'",
                path=path,
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

    Args:
        fsm: The FSM loop to validate

    Returns:
        List of validation errors (empty if valid)
    """
    errors: list[ValidationError] = []
    defined_states = fsm.get_all_state_names()

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
                message="No terminal state defined. At least one state must have "
                "'terminal: true'",
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

        # Validate evaluator if present
        if state.evaluate is not None:
            errors.extend(_validate_evaluator(state_name, state.evaluate))

        # Validate routing configuration
        errors.extend(_validate_state_routing(state_name, state))

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
    to_visit: list[str] = [fsm.initial]

    while to_visit:
        current = to_visit.pop(0)
        if current in reachable or current not in fsm.states:
            continue

        reachable.add(current)
        state = fsm.states[current]
        refs = state.get_referenced_states()

        for ref in refs:
            if ref != "$current" and ref not in reachable:
                to_visit.append(ref)

    return reachable


def load_and_validate(path: Path) -> FSMLoop:
    """Load YAML file and validate FSM structure.

    Args:
        path: Path to the YAML file to load

    Returns:
        Validated FSMLoop instance

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

    # Check required fields before parsing
    missing = []
    for field in ["name", "initial", "states"]:
        if field not in data:
            missing.append(field)

    if missing:
        raise ValueError(
            f"FSM file missing required fields: {', '.join(missing)}"
        )

    # Parse into dataclass
    fsm = FSMLoop.from_dict(data)

    # Validate
    errors = validate_fsm(fsm)

    # Filter to errors only (not warnings) for raising
    error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]

    if error_list:
        error_messages = "\n  ".join(str(e) for e in error_list)
        raise ValueError(f"FSM validation failed:\n  {error_messages}")

    # Log warnings
    warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
    for warning in warnings:
        logger.warning(str(warning))

    return fsm

"""Structural rule family: schema-shape checks not gated by a numbered MR
suppress flag (evaluator field requirements, parameter/binding contracts,
state action/routing shape, cost ceilings, targets, failure terminals,
zero-retry-counter, input-key guard, on_max_steps/on_max_iterations,
host_guard, prompt_size_guard, circuit) plus the `validate_fsm` dispatcher
and the `load_and_validate`/`is_runnable_loop` entry points.
"""

from __future__ import annotations

import difflib
import logging
import re
from pathlib import Path
from typing import Any

import yaml

from little_loops.fsm.evaluators import _NUMERIC_OPERATORS
from little_loops.fsm.fragments import resolve_flow, resolve_fragments, resolve_inheritance
from little_loops.fsm.loop_paths import resolve_loop_path
from little_loops.fsm.schema import EvaluateConfig, FSMLoop, StateConfig, evaluate_config_known_fields

from little_loops.fsm.validation._base import (
    EVALUATOR_REQUIRED_FIELDS,
    KNOWN_TOP_LEVEL_KEYS,
    STALL_SPECIAL_TOKENS,
    VALID_OPERATORS,
    VALID_PARAMETER_TYPES,
    VALID_VISIBILITY,
    ValidationError,
    ValidationSeverity,
    _check_param_type,
    _find_reachable_states,
    _is_llm_judged,
)
from little_loops.fsm.validation.evaluator_rules import (
    _validate_abandonment_verdict,
    _validate_classify_route_default,
    _validate_haiku_pinned_generator,
    _validate_llm_evidence_contract,
    _validate_parse_swallow,
    _validate_pruning_profile,
    _validate_session_mode_evaluator_inheritance,
    _validate_terminal_action_ok,
)
from little_loops.fsm.validation.meta_rules import (
    _validate_artifact_isolation,
    _validate_artifact_overwrite,
    _validate_generator_fix_discipline,
    _validate_harness_multimodal_evaluator_blind_spot,
    _validate_meta_loop_evaluation,
    _validate_partial_route_dead_end,
)
from little_loops.fsm.validation.reachability import (
    _validate_capture_reachability,
    _validate_loop_references,
    _validate_policy_dimensions_scored,
    _validate_progress_paths_isolation,
)
from little_loops.fsm.validation.shell_safety import (
    _validate_bash_default_interpolation,
    _validate_overescaped_shell,
    _validate_unsafe_context_interpolation,
)

logger = logging.getLogger(__name__)


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

    # Validate score_stall-specific fields
    if evaluate.type == "score_stall":
        if evaluate.max_stall < 1:
            errors.append(
                ValidationError(
                    message="max_stall must be >= 1",
                    path=f"{path}.max_stall",
                )
            )
        if evaluate.epsilon < 0:
            errors.append(
                ValidationError(
                    message="epsilon must be >= 0",
                    path=f"{path}.epsilon",
                )
            )

    # Validate open_question_stall-specific fields (ENH-2446).
    # Mirrors score_stall's max_stall/epsilon guard so the schema rejects bad
    # configurations at validate time rather than at runtime.
    if evaluate.type == "open_question_stall":
        if evaluate.max_stall < 1:
            errors.append(
                ValidationError(
                    message="max_stall must be >= 1",
                    path=f"{path}.max_stall",
                )
            )
        if evaluate.epsilon < 0:
            errors.append(
                ValidationError(
                    message="epsilon must be >= 0",
                    path=f"{path}.epsilon",
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

    # model: override is silently ignored for non-prompt action states UNLESS an
    # llm_structured/check_semantic evaluate block consumes it for verdict dispatch
    # (ENH-2713 — model: now threads into the evaluator path too, not just actions).
    if (
        state.model is not None
        and state.action_type not in ("prompt", "slash_command", None)
        and not _is_llm_judged(state)
    ):
        errors.append(
            ValidationError(
                message="model: override is ignored for shell/mcp_tool/contract states",
                path=f"{path}.model",
                severity=ValidationSeverity.WARNING,
            )
        )

    # effort: override follows the same action-type applicability as model:
    # (ENH-2869) — silently ignored for non-prompt action states unless an
    # llm_structured/check_semantic evaluate block consumes it.
    if (
        state.effort is not None
        and state.action_type not in ("prompt", "slash_command", None)
        and not _is_llm_judged(state)
    ):
        errors.append(
            ValidationError(
                message="effort: override is ignored for shell/mcp_tool/contract states",
                path=f"{path}.effort",
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

    # worktree: requires loop: to be set (ENH-2609)
    if state.worktree is not None and state.loop is None:
        errors.append(
            ValidationError(
                message="'worktree' is only valid when 'loop' is set — "
                "per-state worktree attach applies to sub-loop delegation only",
                path=f"{path}.worktree",
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

    # Validate cost_ceiling config when present (ENH-2477)
    if state.cost_ceiling is not None:
        errors.extend(_validate_state_cost_ceiling(state_name, state, path))

    return errors

def _validate_state_cost_ceiling(
    state_name: str, state: StateConfig, path: str
) -> list[ValidationError]:
    """Validate per-state ``cost_ceiling`` config (ENH-2477).

    Rejects:
      - non-numeric values (type mismatch)
      - negative ``cost_ceiling_per_state`` or ``cost_warn_at`` values
      - ``cost_warn_at`` >= ``cost_ceiling_per_state`` (logically inconsistent —
        the warning would fire at or above the hard cap)

    Returns an empty list when no ceiling is set, or when the config is valid.
    """
    errors: list[ValidationError] = []
    ceiling = state.cost_ceiling
    assert ceiling is not None  # caller guards

    cap = ceiling.cost_ceiling_per_state
    warn = ceiling.cost_warn_at

    if cap is not None:
        if not isinstance(cap, (int, float)) or isinstance(cap, bool):
            errors.append(
                ValidationError(
                    message=(
                        f"'cost_ceiling.cost_ceiling_per_state' must be a number, got {cap!r}"
                    ),
                    path=path,
                )
            )
        elif cap < 0:
            errors.append(
                ValidationError(
                    message=(
                        f"'cost_ceiling.cost_ceiling_per_state' must be non-negative, got {cap}"
                    ),
                    path=path,
                )
            )

    if warn is not None:
        if not isinstance(warn, (int, float)) or isinstance(warn, bool):
            errors.append(
                ValidationError(
                    message=(f"'cost_ceiling.cost_warn_at' must be a number, got {warn!r}"),
                    path=path,
                )
            )
        elif warn < 0:
            errors.append(
                ValidationError(
                    message=(f"'cost_ceiling.cost_warn_at' must be non-negative, got {warn}"),
                    path=path,
                )
            )

    if (
        cap is not None
        and warn is not None
        and isinstance(cap, (int, float))
        and isinstance(warn, (int, float))
        and not isinstance(cap, bool)
        and not isinstance(warn, bool)
        and warn > cap
    ):
        errors.append(
            ValidationError(
                message=(
                    f"'cost_ceiling.cost_warn_at' ({warn}) must not exceed "
                    f"'cost_ceiling.cost_ceiling_per_state' ({cap})"
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
    """Warn when a failure terminal state has no diagnostic predecessor.

    Failure terminals should have at least one predecessor state with an
    action or sub-loop that provides diagnostic output before termination.
    Otherwise the failure is silent — the executor calls _finish("terminal")
    before any action on the terminal itself can execute.

    ENH-2814: failure-ness is read from ``StateConfig.failure`` (via
    ``get_failure_states()``), the single source of truth, rather than
    re-tested against the ``FAILURE_TERMINAL_NAMES`` name convention. That
    set now only *defaults* the flag at parse time, so this validator keeps
    its previous coverage while also catching explicitly-declared failure
    terminals whose names fall outside it (``blocked``, ``impl_failed``, ...).

    Severity is WARNING (not ERROR) so that existing loops with bare
    failure terminals continue to load, and test_terminal_only_state_valid
    (which filters by ERROR) passes without modification.
    """
    errors: list[ValidationError] = []

    failure_terminals = fsm.get_failure_states() & fsm.get_terminal_states()

    for ft_name in sorted(failure_terminals):
        has_diagnostic_predecessor = False
        for state_name, state in fsm.states.items():
            if state_name == ft_name:
                continue
            if ft_name in state.get_referenced_states():
                # `learning:` is an action-bearing primitive too (it shells out
                # to ll-learning-tests), so a `learning` state routing to a
                # failure terminal is a genuine diagnostic predecessor.
                if state.action is not None or state.loop is not None or state.learning is not None:
                    has_diagnostic_predecessor = True
                    break

        if not has_diagnostic_predecessor:
            errors.append(
                ValidationError(
                    message=(
                        f"Failure terminal state '{ft_name}' has no predecessor "
                        "state with a diagnostic action. Add a non-terminal diagnostic "
                        "state (e.g. 'diagnose') with an action or sub-loop that routes "
                        f"to '{ft_name}'."
                    ),
                    path=f"states.{ft_name}",
                    severity=ValidationSeverity.WARNING,
                )
            )

    return errors

def validate_fsm(
    fsm: FSMLoop, orchestration_request_path: str | None = None
) -> list[ValidationError]:
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
        orchestration_request_path: Optional project-level ``orchestration.request_path``
            config default (ENH-2810), consulted by MR-12 Check 3's exemption when a
            state has no explicit ``request_path`` of its own.

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

    errors.extend(_validate_terminal_action_ok(fsm))

    errors.extend(_validate_meta_loop_evaluation(fsm))

    errors.extend(_validate_input_key_without_guard(fsm))

    errors.extend(_validate_artifact_isolation(fsm))

    errors.extend(_validate_harness_multimodal_evaluator_blind_spot(fsm))

    errors.extend(_validate_partial_route_dead_end(fsm))

    errors.extend(_validate_artifact_overwrite(fsm))

    errors.extend(_validate_generator_fix_discipline(fsm))

    errors.extend(_validate_bash_default_interpolation(fsm))

    errors.extend(_validate_overescaped_shell(fsm))

    errors.extend(_validate_parse_swallow(fsm))

    errors.extend(_validate_abandonment_verdict(fsm))

    errors.extend(_validate_pruning_profile(fsm, orchestration_request_path))

    errors.extend(_validate_unsafe_context_interpolation(fsm))

    errors.extend(_validate_classify_route_default(fsm))

    errors.extend(_validate_policy_dimensions_scored(fsm))

    errors.extend(_validate_zero_retry_counter(fsm))

    errors.extend(_validate_on_max_steps(fsm, defined_states))
    errors.extend(_validate_on_max_iterations(fsm, defined_states))

    errors.extend(_validate_circuit(fsm, defined_states))

    errors.extend(_validate_host_guard(fsm, defined_states))

    errors.extend(_validate_prompt_size_guard(fsm))

    errors.extend(_validate_progress_paths_isolation(fsm))

    errors.extend(_validate_capture_reachability(fsm))

    errors.extend(_validate_llm_evidence_contract(fsm))
    errors.extend(_validate_haiku_pinned_generator(fsm))
    errors.extend(_validate_session_mode_evaluator_inheritance(fsm))

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

def _validate_host_guard(fsm: FSMLoop, defined_states: set[str]) -> list[ValidationError]:
    """Validate the top-level ``host_guard:`` block (ENH-2452 / ENH-2453).

    Checks:
    - percentage thresholds are within 0..100 and ``critical_pct >= warn_pct``
    - ``on_pressure`` is one of ``cool_down`` / ``route`` / ``abort``
    - ``pressure_state`` is set and declared when ``on_pressure="route"``
    - ``on_abort_route`` references a declared state when set
    - ``on_budget_exceeded`` is ``route`` or ``abort``; ``budget_state`` is set
      and declared when routing with an enabled budget
    """
    from little_loops.fsm.host_guard import ON_BUDGET_VALUES, ON_PRESSURE_VALUES

    errors: list[ValidationError] = []
    hg = fsm.host_guard

    for name, value in (("warn_pct", hg.warn_pct), ("critical_pct", hg.critical_pct)):
        if not 0 <= value <= 100:
            errors.append(
                ValidationError(
                    message=f"host_guard.{name} must be between 0 and 100, got {value}",
                    path=f"host_guard.{name}",
                )
            )
    if hg.critical_pct < hg.warn_pct:
        errors.append(
            ValidationError(
                message=(
                    f"host_guard.critical_pct ({hg.critical_pct}) must be >= "
                    f"warn_pct ({hg.warn_pct})"
                ),
                path="host_guard.critical_pct",
            )
        )
    if hg.cooldown_ms < 0:
        errors.append(
            ValidationError(
                message=f"host_guard.cooldown_ms must be >= 0, got {hg.cooldown_ms}",
                path="host_guard.cooldown_ms",
            )
        )

    if hg.on_pressure not in ON_PRESSURE_VALUES:
        errors.append(
            ValidationError(
                message=(
                    f"host_guard.on_pressure must be one of "
                    f"{sorted(ON_PRESSURE_VALUES)}, got '{hg.on_pressure}'"
                ),
                path="host_guard.on_pressure",
            )
        )
    if hg.on_pressure == "route":
        if hg.pressure_state is None:
            errors.append(
                ValidationError(
                    message="host_guard.pressure_state is required when on_pressure='route'",
                    path="host_guard.pressure_state",
                )
            )
        elif hg.pressure_state not in defined_states:
            errors.append(
                ValidationError(
                    message=(
                        f"host_guard.pressure_state references unknown state "
                        f"'{hg.pressure_state}' (must be a declared state)"
                    ),
                    path="host_guard.pressure_state",
                )
            )
    if hg.on_abort_route is not None and hg.on_abort_route not in defined_states:
        errors.append(
            ValidationError(
                message=(
                    f"host_guard.on_abort_route references unknown state "
                    f"'{hg.on_abort_route}' (must be a declared state)"
                ),
                path="host_guard.on_abort_route",
            )
        )

    if hg.max_cumulative_subproc_mb < 0:
        errors.append(
            ValidationError(
                message=(
                    f"host_guard.max_cumulative_subproc_mb must be >= 0, "
                    f"got {hg.max_cumulative_subproc_mb}"
                ),
                path="host_guard.max_cumulative_subproc_mb",
            )
        )
    if hg.on_budget_exceeded not in ON_BUDGET_VALUES:
        errors.append(
            ValidationError(
                message=(
                    f"host_guard.on_budget_exceeded must be one of "
                    f"{sorted(ON_BUDGET_VALUES)}, got '{hg.on_budget_exceeded}'"
                ),
                path="host_guard.on_budget_exceeded",
            )
        )
    if hg.max_cumulative_subproc_mb > 0 and hg.on_budget_exceeded == "route":
        if hg.budget_state is None:
            errors.append(
                ValidationError(
                    message=(
                        "host_guard.budget_state is required when "
                        "on_budget_exceeded='route' and the budget is enabled"
                    ),
                    path="host_guard.budget_state",
                )
            )
        elif hg.budget_state not in defined_states:
            errors.append(
                ValidationError(
                    message=(
                        f"host_guard.budget_state references unknown state "
                        f"'{hg.budget_state}' (must be a declared state)"
                    ),
                    path="host_guard.budget_state",
                )
            )

    return errors

def _validate_prompt_size_guard(fsm: FSMLoop) -> list[ValidationError]:
    """Validate the top-level ``prompt_size_guard:`` block (ENH-2486).

    Checks:
    - ``warn_chars`` is a non-negative integer (0 disables the guard).
    """
    errors: list[ValidationError] = []
    psg = fsm.prompt_size_guard

    if psg.warn_chars < 0:
        errors.append(
            ValidationError(
                message=f"prompt_size_guard.warn_chars must be >= 0, got {psg.warn_chars}",
                path="prompt_size_guard.warn_chars",
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

def _validate_evaluate_unknown_keys(
    fsm: FSMLoop, raw_data: dict[str, Any]
) -> list[ValidationError]:
    """Validate rule MR-14 (ENH-2896): unknown keys under a state's ``evaluate:``.

    By the time a state reaches ``validate_fsm``, ``EvaluateConfig.from_dict``
    has already parsed it — silently dropping any key it doesn't recognize
    (BUG-2893/BUG-2894's root cause). Every other structural rule receives the
    already-parsed ``FSMLoop``/``StateConfig``/``EvaluateConfig`` objects, but
    that's exactly the shape that can no longer reveal a dropped key. This rule
    is therefore the one deliberate exception: it takes the **raw pre-parse
    dict** (``raw_data``, the same object ``load_and_validate`` diffs against
    ``KNOWN_TOP_LEVEL_KEYS`` before calling ``FSMLoop.from_dict``) and walks
    each state's raw ``evaluate:`` sub-mapping directly, mirroring that
    top-level check's set-difference shape at the state level.

    Suppressed by ``evaluate_unknown_keys_ok: true`` at the loop top-level.
    """
    if fsm.evaluate_unknown_keys_ok:
        return []

    errors: list[ValidationError] = []
    known_fields = evaluate_config_known_fields()
    states_data = raw_data.get("states")
    if not isinstance(states_data, dict):
        return errors

    for state_name, state_data in states_data.items():
        if not isinstance(state_data, dict):
            continue
        evaluate_data = state_data.get("evaluate")
        if not isinstance(evaluate_data, dict):
            continue

        unknown = set(evaluate_data.keys()) - known_fields
        for key in sorted(unknown):
            suggestion = ""
            matches = difflib.get_close_matches(key, known_fields, n=1)
            if matches:
                suggestion = f" Did you mean `{matches[0]}`?"
            errors.append(
                ValidationError(
                    path=f"states.{state_name}.evaluate",
                    message=(
                        f"[state: {state_name}] Unknown evaluate key `{key}` for "
                        f"evaluator type `{evaluate_data.get('type', '?')}` — this key "
                        "is silently dropped by EvaluateConfig.from_dict and has no "
                        f"effect.{suggestion} Set `evaluate_unknown_keys_ok: true` to "
                        "suppress. (ENH-2896 MR-14)"
                    ),
                    severity=ValidationSeverity.WARNING,
                )
            )
    return errors


def load_and_validate(
    path: Path,
    raise_on_error: bool = True,
    orchestration_request_path: str | None = None,
) -> tuple[FSMLoop, list[ValidationError]]:
    """Load YAML file and validate FSM structure.

    Args:
        path: Path to the YAML file to load
        raise_on_error: When True (default), raise ValueError on ERROR violations.
            When False, return all violations (errors + warnings) without raising.
        orchestration_request_path: Optional project-level ``orchestration.request_path``
            config default (ENH-2810), threaded into ``validate_fsm`` for MR-12 Check 3's
            config-level exemption.

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

    # MR-14 (ENH-2896): unknown evaluate: keys, using the raw pre-parse `data`
    # captured above (EvaluateConfig.from_dict already dropped anything unknown
    # by this point, so `fsm` alone cannot reveal it — see the rule's docstring).
    unknown_key_warnings.extend(_validate_evaluate_unknown_keys(fsm, data))

    # Validate
    errors = validate_fsm(fsm, orchestration_request_path)

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
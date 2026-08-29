from __future__ import annotations

import logging
import re
from collections import deque
from dataclasses import dataclass
from enum import Enum
from typing import Any

from little_loops.fsm.schema import FSMLoop, ParameterSpec, StateConfig

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
    "score_stall": [],
    "open_question_stall": [],
    "action_stall": [],
    "llm_structured": [],
    "mcp_result": [],
    "harbor_scorer": [],
    "comparator": ["baseline_path"],
    "contract": ["pairs"],
    "classify": [],
    "advisor_consult": ["question", "verdict_map"],
}

# Non-LLM evaluator types: all evaluator types except llm_structured
# Derived from EVALUATOR_REQUIRED_FIELDS so new types are automatically included
NON_LLM_EVALUATOR_TYPES: frozenset[str] = frozenset(EVALUATOR_REQUIRED_FIELDS.keys()) - {
    "llm_structured",
    "comparator",
    "contract",
    "advisor_consult",
}

# Valid comparison operators
VALID_OPERATORS: frozenset[str] = frozenset({"eq", "ne", "lt", "le", "gt", "ge"})

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
        "default_idle_timeout",
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
        "artifact_output",
        "artifact_mode",
        "generator_fix_ok",
        "bash_default_ok",
        "shell_pid_ok",
        "parse_swallow_ok",
        "policy_dims_scored_ok",
        "unsafe_context_interpolation_ok",
        "pruning_profile",
        "pruning_profile_ok",
        "tamper_guard",
        "tamper_guard_ok",
        "prepatch_check",
        "prepatch_check_ok",
        "session_mode",
        "session_mode_ok",
        "haiku_generator_ok",
        "capture_reachability_ok",
        "terminal_action_ok",
        "abandonment_verdict_ok",
        "evaluate_unknown_keys_ok",
        "abstention_route_ok",
        "gate_completeness_ok",
        "import",
        "fragments",
        "from",
        "flow",
        "state_defs",
        "singleton",
    }
)

# Special tokens accepted as the `on_repeated_failure` target on the
# stall detector — `"abort"` means terminate via _finish("stall_detected").
STALL_SPECIAL_TOKENS: frozenset[str] = frozenset({"abort"})

# Valid parameter types for the 'parameters:' block
VALID_PARAMETER_TYPES: frozenset[str] = frozenset(
    {"string", "integer", "number", "boolean", "enum", "path"}
)


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
    return state.evaluate.type in ("llm_structured", "check_semantic", "advisor_consult")


_SKILL_INVOKE_RE = re.compile(r"/ll:([a-zA-Z0-9_-]+)")


def _effective_session_mode(fsm: FSMLoop, state: StateConfig) -> str:
    """Resolve the effective session_mode for a state: state override, then loop default.

    Mirrors ``_effective_pruning_profile``'s two-level resolution. Defaults to
    "fresh" when neither the state nor the loop sets it (FEAT-2711).
    """
    if state.session_mode is not None:
        return state.session_mode
    return fsm.session_mode or "fresh"


# Matches common interpolation prefixes used in loop YAML paths so we can
# extract the portable relative component for action-string scanning.
_INTERPOLATION_PREFIX_RE = re.compile(r"^\$\{[^}]+\}/")


def _strip_interpolation_prefix(path: str) -> str:
    """Return the path with any leading ${...}/ prefix removed."""
    return _INTERPOLATION_PREFIX_RE.sub("", path)


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

"""Paradigm compilers for FSM loop generation.

Each paradigm (goal, convergence, invariants, imperative) compiles to the
universal FSM schema via deterministic template expansion. This provides
a simple authoring experience while maintaining a single execution engine.

Compilers transform high-level paradigm YAML specifications into FSMLoop
instances that can be validated and executed. Each compiler is a pure
function (~50-100 lines) that performs template expansion with variable
substitution.

Example usage:
    >>> spec = {
    ...     "paradigm": "goal",
    ...     "goal": "No type errors in src/",
    ...     "tools": ["/ll:check_code types", "/ll:manage_issue bug fix"],
    ... }
    >>> fsm = compile_paradigm(spec)
    >>> fsm.initial
    'evaluate'
"""

from __future__ import annotations

import re
from typing import Any

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    RouteConfig,
    StateConfig,
)


def _slugify(text: str, max_length: int = 50) -> str:
    """Convert text to slug format for FSM names.

    Args:
        text: Text to convert to slug
        max_length: Maximum length of the resulting slug

    Returns:
        Lowercase slug with hyphens, truncated to max_length
    """
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-").lower()[:max_length]


def _build_evaluate_config(evaluator_spec: dict[str, Any] | None) -> EvaluateConfig | None:
    """Build EvaluateConfig from evaluator specification dict.

    Args:
        evaluator_spec: Optional evaluator configuration dict with keys:
            - type: Evaluator type (exit_code, output_contains, output_numeric, llm_structured)
            - pattern: Pattern string for output_contains
            - operator: Comparison operator for output_numeric (eq, lt, gt, le, ge, ne)
            - target: Target value for output_numeric

    Returns:
        EvaluateConfig instance if spec provided, None otherwise
    """
    if evaluator_spec is None:
        return None

    eval_type = evaluator_spec.get("type", "exit_code")

    # For exit_code, we can return None to use the default behavior
    if eval_type == "exit_code":
        return None

    return EvaluateConfig(
        type=eval_type,
        pattern=evaluator_spec.get("pattern"),
        operator=evaluator_spec.get("operator"),
        target=evaluator_spec.get("target"),
    )


def compile_paradigm(spec: dict[str, Any]) -> FSMLoop:
    """Route to appropriate compiler based on paradigm field.

    This is the main entry point for paradigm compilation. It examines
    the 'paradigm' field in the spec and routes to the appropriate
    compiler function.

    Args:
        spec: Paradigm specification dictionary. Must include a 'paradigm'
            field (defaults to 'fsm' if not present).

    Returns:
        Compiled FSMLoop instance

    Raises:
        ValueError: If the paradigm is unknown

    Example:
        >>> spec = {"paradigm": "goal", "goal": "Clean", "tools": ["cmd"]}
        >>> fsm = compile_paradigm(spec)
        >>> fsm.paradigm
        'goal'
    """
    paradigm = spec.get("paradigm", "fsm")

    compilers = {
        "goal": compile_goal,
        "convergence": compile_convergence,
        "invariants": compile_invariants,
        "imperative": compile_imperative,
        "fsm": _passthrough_fsm,
    }

    if paradigm not in compilers:
        raise ValueError(
            f"Unknown paradigm: '{paradigm}'. Must be one of: {', '.join(sorted(compilers.keys()))}"
        )

    return compilers[paradigm](spec)


def _passthrough_fsm(spec: dict[str, Any]) -> FSMLoop:
    """Pass through FSM spec directly (no compilation needed).

    Args:
        spec: FSM specification dictionary matching FSMLoop schema

    Returns:
        FSMLoop instance created from the spec
    """
    return FSMLoop.from_dict(spec)


def compile_goal(spec: dict[str, Any]) -> FSMLoop:
    """Compile goal paradigm to FSM.

    Goal paradigm: evaluate → (success → done, failure → fix), fix → evaluate

    The goal paradigm is the simplest: it repeatedly checks a condition
    and applies a fix until the goal is achieved.

    Input spec:
        paradigm: goal
        goal: "No type errors in src/"
        tools:
          - /ll:check_code types      # Check tool (first)
          - /ll:manage_issue bug fix  # Fix tool (second, optional)
        max_iterations: 50            # Optional, defaults to 50 (examples show 20 for brevity)
        name: "my-goal"               # Optional, auto-generated from goal
        evaluator:                    # Optional evaluator config
          type: output_contains
          pattern: "Success"

    Args:
        spec: Goal paradigm specification dict

    Returns:
        Compiled FSMLoop instance with evaluate/fix/done states

    Raises:
        ValueError: If required fields are missing
    """
    # Validate required fields
    if "goal" not in spec:
        raise ValueError("Goal paradigm requires 'goal' field")
    if "tools" not in spec or not spec["tools"]:
        raise ValueError("Goal paradigm requires 'tools' field with at least one tool")

    goal = spec["goal"]
    tools = spec["tools"]
    check_tool = tools[0]
    fix_tool = tools[1] if len(tools) > 1 else tools[0]

    name = spec.get("name", f"goal-{_slugify(goal)}")

    # Extract evaluator config if provided
    evaluate_config = _build_evaluate_config(spec.get("evaluator"))

    states = {
        "evaluate": StateConfig(
            action=check_tool,
            evaluate=evaluate_config,
            on_success="done",
            on_failure="fix",
            on_error="fix",
        ),
        "fix": StateConfig(
            action=fix_tool,
            next="evaluate",
        ),
        "done": StateConfig(terminal=True),
    }

    return FSMLoop(
        name=name,
        paradigm="goal",
        initial="evaluate",
        states=states,
        max_iterations=spec.get("max_iterations", 50),
        backoff=spec.get("backoff"),
        timeout=spec.get("timeout"),
    )


def compile_convergence(spec: dict[str, Any]) -> FSMLoop:
    """Compile convergence paradigm to FSM.

    Convergence paradigm: measure → (target → done, progress → apply, stall → done),
                          apply → measure

    The convergence paradigm drives a metric toward a target value. It measures
    the current value, compares to the previous measurement, and routes based
    on whether progress is being made.

    Input spec:
        paradigm: convergence
        name: "reduce-lint-errors"
        check: "ruff check src/ --output-format=json | jq '.count'"
        toward: 0
        using: "/ll:check_code fix"
        tolerance: 0  # Optional, defaults to 0

    Args:
        spec: Convergence paradigm specification dict

    Returns:
        Compiled FSMLoop instance with measure/apply/done states

    Raises:
        ValueError: If required fields are missing
    """
    # Validate required fields
    required = ["name", "check", "toward", "using"]
    missing = [f for f in required if f not in spec]
    if missing:
        raise ValueError(f"Convergence paradigm requires: {', '.join(missing)}")

    name = spec["name"]
    metric_cmd = spec["check"]
    target = spec["toward"]
    fix_action = spec["using"]
    tolerance = spec.get("tolerance", 0)

    # Build context for variable interpolation
    context = {
        "metric_cmd": metric_cmd,
        "target": target,
        "tolerance": tolerance,
    }

    states = {
        "measure": StateConfig(
            action="${context.metric_cmd}",
            capture="current_value",
            evaluate=EvaluateConfig(
                type="convergence",
                target="${context.target}",
                tolerance="${context.tolerance}",
                previous="${prev.output}",
            ),
            route=RouteConfig(
                routes={
                    "target": "done",
                    "progress": "apply",
                    "stall": "done",
                }
            ),
        ),
        "apply": StateConfig(
            action=fix_action,
            next="measure",
        ),
        "done": StateConfig(terminal=True),
    }

    return FSMLoop(
        name=name,
        paradigm="convergence",
        initial="measure",
        states=states,
        context=context,
        max_iterations=spec.get("max_iterations", 50),
        backoff=spec.get("backoff"),
        timeout=spec.get("timeout"),
    )


def compile_invariants(spec: dict[str, Any]) -> FSMLoop:
    """Compile invariants paradigm to FSM.

    Invariants paradigm: check_1 → (success → check_2, failure → fix_1),
                         fix_1 → check_1, ...

    The invariants paradigm chains multiple constraints. Each constraint
    is checked in sequence; if any fails, its fix is applied before
    re-checking. When all pass, the loop can optionally restart (maintain mode).

    Input spec:
        paradigm: invariants
        name: "code-quality-guardian"
        constraints:
          - name: "tests-pass"
            check: "pytest"
            fix: "/ll:manage_issue bug fix"
            evaluator:               # Optional per-constraint
              type: output_contains
              pattern: "passed"
          - name: "lint-clean"
            check: "ruff check src/"
            fix: "/ll:check_code fix"
        maintain: true  # Optional, restarts after all valid

    Args:
        spec: Invariants paradigm specification dict

    Returns:
        Compiled FSMLoop instance with check/fix pairs and all_valid terminal

    Raises:
        ValueError: If required fields are missing or constraint is invalid
    """
    # Validate required fields
    if "name" not in spec:
        raise ValueError("Invariants paradigm requires 'name' field")
    if "constraints" not in spec or not spec["constraints"]:
        raise ValueError(
            "Invariants paradigm requires 'constraints' field with at least one constraint"
        )

    name = spec["name"]
    constraints = spec["constraints"]
    maintain = spec.get("maintain", False)

    # Validate each constraint
    for i, constraint in enumerate(constraints):
        if "name" not in constraint:
            raise ValueError(f"Constraint {i} requires 'name' field")
        if "check" not in constraint:
            raise ValueError(f"Constraint '{constraint.get('name', i)}' requires 'check' field")
        if "fix" not in constraint:
            raise ValueError(f"Constraint '{constraint.get('name', i)}' requires 'fix' field")

    states: dict[str, StateConfig] = {}

    for i, constraint in enumerate(constraints):
        check_state = f"check_{constraint['name']}"
        fix_state = f"fix_{constraint['name']}"

        # Next check state or terminal
        next_check = (
            f"check_{constraints[i + 1]['name']}" if i + 1 < len(constraints) else "all_valid"
        )

        # Extract evaluator config if provided for this constraint
        evaluate_config = _build_evaluate_config(constraint.get("evaluator"))

        states[check_state] = StateConfig(
            action=constraint["check"],
            evaluate=evaluate_config,
            on_success=next_check,
            on_failure=fix_state,
        )
        states[fix_state] = StateConfig(
            action=constraint["fix"],
            next=check_state,
        )

    # Terminal state with optional maintain loop-back
    first_check = f"check_{constraints[0]['name']}"
    states["all_valid"] = StateConfig(
        terminal=True,
        on_maintain=first_check if maintain else None,
    )

    return FSMLoop(
        name=name,
        paradigm="invariants",
        initial=first_check,
        states=states,
        maintain=maintain,
        max_iterations=spec.get("max_iterations", 50),
        backoff=spec.get("backoff"),
        timeout=spec.get("timeout"),
    )


def compile_imperative(spec: dict[str, Any]) -> FSMLoop:
    """Compile imperative paradigm to FSM.

    Imperative paradigm: step_0 → step_1 → ... → check_done →
                         (success → done, failure → step_0)

    The imperative paradigm runs a sequence of steps, then checks an
    exit condition. If the condition fails, the sequence restarts from
    the beginning.

    Input spec:
        paradigm: imperative
        name: "fix-all-types"
        steps:
          - /ll:check_code types
          - /ll:manage_issue bug fix
        until:
          check: "mypy src/"
          passes: true
          evaluator:               # Optional evaluator for exit condition
            type: output_contains
            pattern: "Success"
        max_iterations: 50            # Optional, defaults to 50 (examples show 20 for brevity)
        backoff: 2  # Seconds between iterations

    Args:
        spec: Imperative paradigm specification dict

    Returns:
        Compiled FSMLoop instance with step sequence and check_done

    Raises:
        ValueError: If required fields are missing
    """
    # Validate required fields
    if "name" not in spec:
        raise ValueError("Imperative paradigm requires 'name' field")
    if "steps" not in spec or not spec["steps"]:
        raise ValueError("Imperative paradigm requires 'steps' field with at least one step")
    if "until" not in spec:
        raise ValueError("Imperative paradigm requires 'until' field")
    if "check" not in spec["until"]:
        raise ValueError("Imperative paradigm 'until' requires 'check' field")

    name = spec["name"]
    steps = spec["steps"]
    until_check = spec["until"]["check"]

    # Extract evaluator config for exit condition if provided
    evaluate_config = _build_evaluate_config(spec["until"].get("evaluator"))

    states: dict[str, StateConfig] = {}

    # Create step states
    for i, step in enumerate(steps):
        state_name = f"step_{i}"
        next_state = f"step_{i + 1}" if i + 1 < len(steps) else "check_done"

        states[state_name] = StateConfig(
            action=step,
            next=next_state,
        )

    # Create check_done state with optional evaluator
    states["check_done"] = StateConfig(
        action=until_check,
        evaluate=evaluate_config,
        on_success="done",
        on_failure="step_0",
    )

    # Terminal state
    states["done"] = StateConfig(terminal=True)

    return FSMLoop(
        name=name,
        paradigm="imperative",
        initial="step_0",
        states=states,
        max_iterations=spec.get("max_iterations", 50),
        backoff=spec.get("backoff"),
        timeout=spec.get("timeout"),
    )

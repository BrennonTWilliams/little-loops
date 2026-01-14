# FEAT-041: Paradigm Compilers - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P1-FEAT-041-paradigm-compilers.md`
- **Type**: feature
- **Priority**: P1
- **Action**: implement

## Current State Analysis

FEAT-040 established the FSM schema infrastructure:

### Key Discoveries
- FSMLoop dataclass at `scripts/little_loops/fsm/schema.py:324-440` provides the target structure
- StateConfig at `schema.py:164-277` represents individual states with routing options
- EvaluateConfig at `schema.py:21-126` supports convergence evaluator type
- RouteConfig at `schema.py:128-162` handles verdict-to-state mapping
- `validate_fsm()` at `validation.py:191-264` validates FSM structure
- `FSMLoop.from_dict()` at `schema.py:386-409` converts dict to typed dataclass
- Slugify pattern at `issue_parser.py:22-33` for generating names from text

### FSM Module Interface
- Public exports in `fsm/__init__.py:30-39` include FSMLoop, StateConfig, EvaluateConfig, RouteConfig, validate_fsm

## Desired End State

A `compilers.py` module that:
1. Transforms high-level paradigm YAML dicts into FSMLoop instances
2. Supports 4 paradigms: goal, convergence, invariants, imperative
3. Routes paradigm specs through `compile_paradigm()` dispatcher
4. Validates all required fields and raises clear errors
5. Produces FSMs that pass `validate_fsm()`

### How to Verify
- All unit tests pass for each compiler
- Generated FSMs pass `validate_fsm()` with no errors
- Each compiler handles edge cases (missing fields, single-item cases)

## What We're NOT Doing

- **NOT implementing the executor** - deferred to FEAT-045
- **NOT implementing variable interpolation runtime** - deferred to FEAT-042
- **NOT adding YAML loading** - compilers receive already-parsed dicts
- **NOT adding CLI commands** - deferred to FEAT-047
- **NOT implementing evaluators** - deferred to FEAT-043

## Solution Approach

Create deterministic compilers as pure functions that transform paradigm dicts to FSM dicts, then convert to FSMLoop via `FSMLoop.from_dict()`. Each compiler follows a fixed template pattern as documented in `docs/generalized-fsm-loop.md`.

## Implementation Phases

### Phase 1: Create compilers.py with Goal Compiler

#### Overview
Create the new `compilers.py` module with the dispatch function and the simplest compiler (goal).

#### Changes Required

**File**: `scripts/little_loops/fsm/compilers.py`
**Changes**: Create new file with:
- Module docstring
- Imports from schema module
- `_slugify()` helper function (simple version for FSM names)
- `compile_paradigm()` dispatcher function
- `compile_goal()` compiler

```python
"""Paradigm compilers for FSM loop generation.

Each paradigm (goal, convergence, invariants, imperative) compiles to the
universal FSM schema via deterministic template expansion. This provides
a simple authoring experience while maintaining a single execution engine.
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
    """Convert text to slug format for FSM names."""
    text = re.sub(r"[^\w\s-]", "", text)
    text = re.sub(r"[-\s]+", "-", text)
    return text.strip("-").lower()[:max_length]


def compile_paradigm(spec: dict[str, Any]) -> FSMLoop:
    """Route to appropriate compiler based on paradigm field."""
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
            f"Unknown paradigm: '{paradigm}'. "
            f"Must be one of: {', '.join(sorted(compilers.keys()))}"
        )

    return compilers[paradigm](spec)


def _passthrough_fsm(spec: dict[str, Any]) -> FSMLoop:
    """Pass through FSM spec directly (no compilation needed)."""
    return FSMLoop.from_dict(spec)


def compile_goal(spec: dict[str, Any]) -> FSMLoop:
    """Compile goal paradigm to FSM.

    Goal paradigm: evaluate → (success → done, failure → fix), fix → evaluate

    Input spec:
        paradigm: goal
        goal: "No type errors in src/"
        tools:
          - /ll:check_code types
          - /ll:manage_issue bug fix
        max_iterations: 20

    Args:
        spec: Goal paradigm specification dict

    Returns:
        Compiled FSMLoop instance

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

    states = {
        "evaluate": StateConfig(
            action=check_tool,
            on_success="done",
            on_failure="fix",
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
```

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Add compile_paradigm to exports

#### Success Criteria

**Automated Verification**:
- [ ] `python -c "from little_loops.fsm.compilers import compile_paradigm, compile_goal"` succeeds
- [ ] `python -m mypy scripts/little_loops/fsm/compilers.py` passes
- [ ] `ruff check scripts/little_loops/fsm/compilers.py` passes

---

### Phase 2: Implement Convergence Compiler

#### Overview
Add the convergence compiler that produces measure/apply/done FSM with context variables and convergence evaluator.

#### Changes Required

**File**: `scripts/little_loops/fsm/compilers.py`
**Changes**: Add `compile_convergence()` function

```python
def compile_convergence(spec: dict[str, Any]) -> FSMLoop:
    """Compile convergence paradigm to FSM.

    Convergence paradigm: measure → (target → done, progress → apply, stall → done), apply → measure

    Input spec:
        paradigm: convergence
        name: "reduce-lint-errors"
        check: "ruff check src/ --output-format=json | jq '.count'"
        toward: 0
        using: "/ll:check_code fix"
        tolerance: 0

    Args:
        spec: Convergence paradigm specification dict

    Returns:
        Compiled FSMLoop instance

    Raises:
        ValueError: If required fields are missing
    """
    # Validate required fields
    required = ["name", "check", "toward", "using"]
    missing = [f for f in required if f not in spec]
    if missing:
        raise ValueError(
            f"Convergence paradigm requires: {', '.join(missing)}"
        )

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
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -c "from little_loops.fsm.compilers import compile_convergence"` succeeds
- [ ] `python -m mypy scripts/little_loops/fsm/compilers.py` passes

---

### Phase 3: Implement Invariants Compiler

#### Overview
Add the invariants compiler that chains constraint checks with fix states and supports `maintain` mode.

#### Changes Required

**File**: `scripts/little_loops/fsm/compilers.py`
**Changes**: Add `compile_invariants()` function

```python
def compile_invariants(spec: dict[str, Any]) -> FSMLoop:
    """Compile invariants paradigm to FSM.

    Invariants paradigm: check_1 → (success → check_2, failure → fix_1), fix_1 → check_1, ...

    Input spec:
        paradigm: invariants
        name: "code-quality-guardian"
        constraints:
          - name: "tests-pass"
            check: "pytest"
            fix: "/ll:manage_issue bug fix"
          - name: "lint-clean"
            check: "ruff check src/"
            fix: "/ll:check_code fix"
        maintain: true

    Args:
        spec: Invariants paradigm specification dict

    Returns:
        Compiled FSMLoop instance

    Raises:
        ValueError: If required fields are missing
    """
    # Validate required fields
    if "name" not in spec:
        raise ValueError("Invariants paradigm requires 'name' field")
    if "constraints" not in spec or not spec["constraints"]:
        raise ValueError("Invariants paradigm requires 'constraints' field with at least one constraint")

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
            f"check_{constraints[i + 1]['name']}"
            if i + 1 < len(constraints)
            else "all_valid"
        )

        states[check_state] = StateConfig(
            action=constraint["check"],
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
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -c "from little_loops.fsm.compilers import compile_invariants"` succeeds
- [ ] `python -m mypy scripts/little_loops/fsm/compilers.py` passes

---

### Phase 4: Implement Imperative Compiler

#### Overview
Add the imperative compiler that creates step sequences with an `until` check loop.

#### Changes Required

**File**: `scripts/little_loops/fsm/compilers.py`
**Changes**: Add `compile_imperative()` function

```python
def compile_imperative(spec: dict[str, Any]) -> FSMLoop:
    """Compile imperative paradigm to FSM.

    Imperative paradigm: step_0 → step_1 → ... → check_done → (success → done, failure → step_0)

    Input spec:
        paradigm: imperative
        name: "fix-all-types"
        steps:
          - /ll:check_code types
          - /ll:manage_issue bug fix
        until:
          check: "mypy src/"
          passes: true
        max_iterations: 20
        backoff: 2

    Args:
        spec: Imperative paradigm specification dict

    Returns:
        Compiled FSMLoop instance

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

    states: dict[str, StateConfig] = {}

    # Create step states
    for i, step in enumerate(steps):
        state_name = f"step_{i}"
        next_state = f"step_{i + 1}" if i + 1 < len(steps) else "check_done"

        states[state_name] = StateConfig(
            action=step,
            next=next_state,
        )

    # Create check_done state
    states["check_done"] = StateConfig(
        action=until_check,
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
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -c "from little_loops.fsm.compilers import compile_imperative"` succeeds
- [ ] `python -m mypy scripts/little_loops/fsm/compilers.py` passes
- [ ] `ruff check scripts/little_loops/fsm/compilers.py` passes

---

### Phase 5: Write Unit Tests

#### Overview
Create comprehensive test suite for all compilers.

#### Changes Required

**File**: `scripts/tests/test_fsm_compilers.py`
**Changes**: Create new test file with tests for all compilers

```python
"""Tests for FSM paradigm compilers."""

from __future__ import annotations

import pytest

from little_loops.fsm import validate_fsm
from little_loops.fsm.compilers import (
    compile_convergence,
    compile_goal,
    compile_imperative,
    compile_invariants,
    compile_paradigm,
)


class TestCompileParadigm:
    """Tests for compile_paradigm dispatcher."""

    def test_routes_to_goal_compiler(self) -> None:
        """paradigm: goal routes to compile_goal."""
        spec = {
            "paradigm": "goal",
            "goal": "No errors",
            "tools": ["check", "fix"],
        }
        fsm = compile_paradigm(spec)
        assert fsm.paradigm == "goal"

    def test_routes_to_convergence_compiler(self) -> None:
        """paradigm: convergence routes to compile_convergence."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_paradigm(spec)
        assert fsm.paradigm == "convergence"

    def test_routes_to_invariants_compiler(self) -> None:
        """paradigm: invariants routes to compile_invariants."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [{"name": "c1", "check": "cmd", "fix": "fix"}],
        }
        fsm = compile_paradigm(spec)
        assert fsm.paradigm == "invariants"

    def test_routes_to_imperative_compiler(self) -> None:
        """paradigm: imperative routes to compile_imperative."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["step1"],
            "until": {"check": "cmd"},
        }
        fsm = compile_paradigm(spec)
        assert fsm.paradigm == "imperative"

    def test_fsm_passthrough(self) -> None:
        """paradigm: fsm passes through unchanged."""
        spec = {
            "paradigm": "fsm",
            "name": "test",
            "initial": "start",
            "states": {
                "start": {"terminal": True},
            },
        }
        fsm = compile_paradigm(spec)
        assert fsm.name == "test"

    def test_default_to_fsm(self) -> None:
        """Missing paradigm defaults to fsm."""
        spec = {
            "name": "test",
            "initial": "start",
            "states": {"start": {"terminal": True}},
        }
        fsm = compile_paradigm(spec)
        assert fsm.name == "test"

    def test_unknown_paradigm_raises(self) -> None:
        """Unknown paradigm raises ValueError."""
        spec = {"paradigm": "unknown"}
        with pytest.raises(ValueError, match="Unknown paradigm"):
            compile_paradigm(spec)


class TestGoalCompiler:
    """Tests for compile_goal."""

    def test_basic_goal(self) -> None:
        """Goal with two tools produces evaluate/fix/done."""
        spec = {
            "paradigm": "goal",
            "goal": "No type errors",
            "tools": ["/ll:check_code types", "/ll:manage_issue bug fix"],
            "max_iterations": 20,
        }
        fsm = compile_goal(spec)

        assert fsm.name.startswith("goal-")
        assert fsm.paradigm == "goal"
        assert fsm.initial == "evaluate"
        assert "evaluate" in fsm.states
        assert "fix" in fsm.states
        assert "done" in fsm.states
        assert fsm.states["evaluate"].on_success == "done"
        assert fsm.states["evaluate"].on_failure == "fix"
        assert fsm.states["fix"].next == "evaluate"
        assert fsm.states["done"].terminal is True
        assert fsm.max_iterations == 20

    def test_goal_single_tool(self) -> None:
        """Goal with one tool uses same for check and fix."""
        spec = {
            "paradigm": "goal",
            "goal": "Clean",
            "tools": ["/ll:check_code fix"],
        }
        fsm = compile_goal(spec)

        assert fsm.states["evaluate"].action == "/ll:check_code fix"
        assert fsm.states["fix"].action == "/ll:check_code fix"

    def test_goal_custom_name(self) -> None:
        """Goal with custom name uses it."""
        spec = {
            "paradigm": "goal",
            "name": "my-custom-goal",
            "goal": "Test",
            "tools": ["cmd"],
        }
        fsm = compile_goal(spec)
        assert fsm.name == "my-custom-goal"

    def test_goal_missing_goal_raises(self) -> None:
        """Missing goal field raises ValueError."""
        spec = {"paradigm": "goal", "tools": ["cmd"]}
        with pytest.raises(ValueError, match="requires 'goal' field"):
            compile_goal(spec)

    def test_goal_missing_tools_raises(self) -> None:
        """Missing tools field raises ValueError."""
        spec = {"paradigm": "goal", "goal": "Test"}
        with pytest.raises(ValueError, match="requires 'tools' field"):
            compile_goal(spec)

    def test_goal_validates(self) -> None:
        """Generated FSM passes validation."""
        spec = {
            "paradigm": "goal",
            "goal": "Test",
            "tools": ["cmd1", "cmd2"],
        }
        fsm = compile_goal(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity.value == "error" for e in errors)


class TestConvergenceCompiler:
    """Tests for compile_convergence."""

    def test_basic_convergence(self) -> None:
        """Convergence spec produces measure/apply/done."""
        spec = {
            "paradigm": "convergence",
            "name": "reduce-errors",
            "check": "mypy src/ | grep -c error",
            "toward": 0,
            "using": "/ll:check_code fix",
        }
        fsm = compile_convergence(spec)

        assert fsm.name == "reduce-errors"
        assert fsm.paradigm == "convergence"
        assert fsm.initial == "measure"
        assert "measure" in fsm.states
        assert "apply" in fsm.states
        assert "done" in fsm.states
        assert fsm.states["apply"].next == "measure"
        assert fsm.states["done"].terminal is True

    def test_convergence_with_tolerance(self) -> None:
        """Tolerance field propagates to context."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "check": "cmd",
            "toward": 10,
            "using": "fix",
            "tolerance": 2,
        }
        fsm = compile_convergence(spec)

        assert fsm.context["tolerance"] == 2
        assert fsm.context["target"] == 10

    def test_convergence_has_context(self) -> None:
        """Convergence creates context for interpolation."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_convergence(spec)

        assert "metric_cmd" in fsm.context
        assert "target" in fsm.context
        assert "tolerance" in fsm.context

    def test_convergence_measure_evaluator(self) -> None:
        """Measure state has convergence evaluator."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_convergence(spec)

        measure = fsm.states["measure"]
        assert measure.evaluate is not None
        assert measure.evaluate.type == "convergence"

    def test_convergence_missing_fields_raises(self) -> None:
        """Missing required fields raises ValueError."""
        spec = {"paradigm": "convergence", "name": "test"}
        with pytest.raises(ValueError, match="Convergence paradigm requires"):
            compile_convergence(spec)

    def test_convergence_validates(self) -> None:
        """Generated FSM passes validation."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_convergence(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity.value == "error" for e in errors)


class TestInvariantsCompiler:
    """Tests for compile_invariants."""

    def test_two_constraints(self) -> None:
        """Two constraints chain correctly."""
        spec = {
            "paradigm": "invariants",
            "name": "guardian",
            "constraints": [
                {"name": "tests", "check": "pytest", "fix": "fix1"},
                {"name": "lint", "check": "ruff", "fix": "fix2"},
            ],
        }
        fsm = compile_invariants(spec)

        assert fsm.name == "guardian"
        assert fsm.paradigm == "invariants"
        assert fsm.initial == "check_tests"
        assert "check_tests" in fsm.states
        assert "fix_tests" in fsm.states
        assert "check_lint" in fsm.states
        assert "fix_lint" in fsm.states
        assert "all_valid" in fsm.states

        # Check chaining
        assert fsm.states["check_tests"].on_success == "check_lint"
        assert fsm.states["check_tests"].on_failure == "fix_tests"
        assert fsm.states["fix_tests"].next == "check_tests"
        assert fsm.states["check_lint"].on_success == "all_valid"
        assert fsm.states["check_lint"].on_failure == "fix_lint"
        assert fsm.states["all_valid"].terminal is True

    def test_single_constraint(self) -> None:
        """Single constraint produces minimal FSM."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [{"name": "c1", "check": "cmd", "fix": "fix"}],
        }
        fsm = compile_invariants(spec)

        assert fsm.initial == "check_c1"
        assert fsm.states["check_c1"].on_success == "all_valid"

    def test_maintain_mode(self) -> None:
        """maintain=true sets on_maintain in all_valid."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [{"name": "c1", "check": "cmd", "fix": "fix"}],
            "maintain": True,
        }
        fsm = compile_invariants(spec)

        assert fsm.maintain is True
        assert fsm.states["all_valid"].on_maintain == "check_c1"

    def test_maintain_false(self) -> None:
        """maintain=false has no on_maintain."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [{"name": "c1", "check": "cmd", "fix": "fix"}],
            "maintain": False,
        }
        fsm = compile_invariants(spec)

        assert fsm.maintain is False
        assert fsm.states["all_valid"].on_maintain is None

    def test_invariants_missing_name_raises(self) -> None:
        """Missing name raises ValueError."""
        spec = {"paradigm": "invariants", "constraints": []}
        with pytest.raises(ValueError, match="requires 'name' field"):
            compile_invariants(spec)

    def test_invariants_missing_constraints_raises(self) -> None:
        """Missing constraints raises ValueError."""
        spec = {"paradigm": "invariants", "name": "test"}
        with pytest.raises(ValueError, match="requires 'constraints' field"):
            compile_invariants(spec)

    def test_constraint_missing_fields_raises(self) -> None:
        """Constraint missing fields raises ValueError."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [{"name": "c1", "check": "cmd"}],  # missing fix
        }
        with pytest.raises(ValueError, match="requires 'fix' field"):
            compile_invariants(spec)

    def test_invariants_validates(self) -> None:
        """Generated FSM passes validation."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [
                {"name": "c1", "check": "cmd1", "fix": "fix1"},
                {"name": "c2", "check": "cmd2", "fix": "fix2"},
            ],
        }
        fsm = compile_invariants(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity.value == "error" for e in errors)


class TestImperativeCompiler:
    """Tests for compile_imperative."""

    def test_three_steps(self) -> None:
        """Three steps produce step_0/step_1/step_2/check_done."""
        spec = {
            "paradigm": "imperative",
            "name": "fix-all",
            "steps": ["cmd1", "cmd2", "cmd3"],
            "until": {"check": "verify"},
        }
        fsm = compile_imperative(spec)

        assert fsm.name == "fix-all"
        assert fsm.paradigm == "imperative"
        assert fsm.initial == "step_0"
        assert "step_0" in fsm.states
        assert "step_1" in fsm.states
        assert "step_2" in fsm.states
        assert "check_done" in fsm.states
        assert "done" in fsm.states

        # Check chaining
        assert fsm.states["step_0"].next == "step_1"
        assert fsm.states["step_1"].next == "step_2"
        assert fsm.states["step_2"].next == "check_done"

    def test_single_step(self) -> None:
        """Single step goes directly to check_done."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd"],
            "until": {"check": "verify"},
        }
        fsm = compile_imperative(spec)

        assert fsm.states["step_0"].next == "check_done"

    def test_until_condition(self) -> None:
        """until.check becomes check_done action."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd"],
            "until": {"check": "mypy src/"},
        }
        fsm = compile_imperative(spec)

        assert fsm.states["check_done"].action == "mypy src/"
        assert fsm.states["check_done"].on_success == "done"
        assert fsm.states["check_done"].on_failure == "step_0"

    def test_backoff_propagates(self) -> None:
        """backoff field propagates to FSM."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd"],
            "until": {"check": "verify"},
            "backoff": 2,
        }
        fsm = compile_imperative(spec)

        assert fsm.backoff == 2

    def test_imperative_missing_name_raises(self) -> None:
        """Missing name raises ValueError."""
        spec = {"paradigm": "imperative", "steps": ["cmd"], "until": {"check": "x"}}
        with pytest.raises(ValueError, match="requires 'name' field"):
            compile_imperative(spec)

    def test_imperative_missing_steps_raises(self) -> None:
        """Missing steps raises ValueError."""
        spec = {"paradigm": "imperative", "name": "test", "until": {"check": "x"}}
        with pytest.raises(ValueError, match="requires 'steps' field"):
            compile_imperative(spec)

    def test_imperative_missing_until_raises(self) -> None:
        """Missing until raises ValueError."""
        spec = {"paradigm": "imperative", "name": "test", "steps": ["cmd"]}
        with pytest.raises(ValueError, match="requires 'until' field"):
            compile_imperative(spec)

    def test_until_missing_check_raises(self) -> None:
        """until without check raises ValueError."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd"],
            "until": {},
        }
        with pytest.raises(ValueError, match="'until' requires 'check' field"):
            compile_imperative(spec)

    def test_imperative_validates(self) -> None:
        """Generated FSM passes validation."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd1", "cmd2"],
            "until": {"check": "verify"},
        }
        fsm = compile_imperative(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity.value == "error" for e in errors)
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -m pytest scripts/tests/test_fsm_compilers.py -v` passes
- [ ] All tests pass with no failures
- [ ] Type checking passes: `python -m mypy scripts/little_loops/fsm/`

---

### Phase 6: Update Module Exports and Final Verification

#### Overview
Update the FSM module's `__init__.py` to export the compiler function and run final verification.

#### Changes Required

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Add compile_paradigm to exports

```python
from little_loops.fsm.compilers import compile_paradigm

__all__ = [
    # ... existing exports ...
    "compile_paradigm",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -m pytest scripts/tests/test_fsm_schema.py scripts/tests/test_fsm_compilers.py -v` all pass
- [ ] `ruff check scripts/little_loops/fsm/` passes
- [ ] `python -m mypy scripts/little_loops/fsm/` passes
- [ ] Import test: `python -c "from little_loops.fsm import compile_paradigm; print('OK')"`

---

## Testing Strategy

### Unit Tests
- Each compiler tested with valid inputs producing expected FSM structure
- Missing required fields raise clear ValueError messages
- Generated FSMs pass `validate_fsm()` with no errors
- Edge cases: single-item lists, optional fields omitted

### Integration Tests
- `compile_paradigm()` routes correctly to each compiler
- FSM passthrough mode works for `paradigm: fsm`
- Default paradigm is "fsm" when not specified

## References

- Original issue: `.issues/features/P1-FEAT-041-paradigm-compilers.md`
- Design doc: `docs/generalized-fsm-loop.md` sections "Paradigm Definitions" and "Paradigm Compilation"
- FSM schema: `scripts/little_loops/fsm/schema.py`
- Validation: `scripts/little_loops/fsm/validation.py`

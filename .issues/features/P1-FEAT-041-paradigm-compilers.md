# FEAT-041: Paradigm Compilers

## Summary

Implement deterministic compilers that transform high-level paradigm YAML into the universal FSM schema. Each paradigm maps to a fixed FSM template with variable substitution.

## Priority

P1 - Required for user-friendly loop authoring

## Dependencies

- FEAT-040: FSM Schema Definition and Validation

## Blocked By

- FEAT-040

## Description

Users author loops in one of four high-level paradigms. Each paradigm compiles to FSM via a deterministic Python function (~50-100 lines each). This keeps the authoring experience simple while maintaining a single execution engine.

### Paradigms to Implement

| Paradigm | Template Pattern |
|----------|------------------|
| Goal | `evaluate → (success → done, failure → fix), fix → evaluate` |
| Convergence | `measure → (target → done, progress → apply, stall → done), apply → measure` |
| Invariants | `check_1 → (success → check_2, failure → fix_1), fix_1 → check_1, ...` |
| Imperative | `step_0 → step_1 → ... → check_done → (success → done, failure → step_0)` |

### Files to Create

```
scripts/little_loops/fsm/
└── compilers.py
```

## Technical Details

### Compiler Interface

```python
# compilers.py
from little_loops.fsm.schema import FSMLoop

def compile_paradigm(spec: dict) -> FSMLoop:
    """Route to appropriate compiler based on paradigm field."""
    paradigm = spec.get("paradigm", "fsm")
    compilers = {
        "goal": compile_goal,
        "convergence": compile_convergence,
        "invariants": compile_invariants,
        "imperative": compile_imperative,
        "fsm": lambda s: s,  # Pass-through
    }
    if paradigm not in compilers:
        raise ValueError(f"Unknown paradigm: {paradigm}")
    return compilers[paradigm](spec)
```

### Goal Compiler

```python
def compile_goal(spec: dict) -> dict:
    """
    Goal paradigm → FSM

    Input:
      paradigm: goal
      goal: "No type errors in src/"
      tools:
        - /ll:check_code types
        - /ll:manage_issue bug fix
      max_iterations: 20

    Output: evaluate/fix/done FSM
    """
    check_tool = spec["tools"][0]
    fix_tool = spec["tools"][1] if len(spec["tools"]) > 1 else spec["tools"][0]

    return {
        "name": f"goal-{_slugify(spec['goal'])}",
        "paradigm": "goal",
        "initial": "evaluate",
        "states": {
            "evaluate": {
                "action": check_tool,
                "on_success": "done",
                "on_failure": "fix",
            },
            "fix": {
                "action": fix_tool,
                "next": "evaluate",
            },
            "done": {"terminal": True},
        },
        "max_iterations": spec.get("max_iterations", 50),
    }
```

### Convergence Compiler

```python
def compile_convergence(spec: dict) -> dict:
    """
    Convergence paradigm → FSM

    Input:
      paradigm: convergence
      name: "reduce-lint-errors"
      check: "ruff check src/ --output-format=json | jq '.count'"
      toward: 0
      using: "/ll:check_code fix"
      tolerance: 0
    """
    return {
        "name": spec["name"],
        "paradigm": "convergence",
        "initial": "measure",
        "context": {
            "metric_cmd": spec["check"],
            "target": spec["toward"],
            "tolerance": spec.get("tolerance", 0),
        },
        "states": {
            "measure": {
                "action": "${context.metric_cmd}",
                "capture": "current_value",
                "evaluate": {
                    "type": "convergence",
                    "target": "${context.target}",
                    "tolerance": "${context.tolerance}",
                    "previous": "${prev.output}",
                },
                "route": {
                    "target": "done",
                    "progress": "apply",
                    "stall": "done",
                },
            },
            "apply": {
                "action": spec["using"],
                "next": "measure",
            },
            "done": {"terminal": True},
        },
    }
```

### Invariants Compiler

```python
def compile_invariants(spec: dict) -> dict:
    """
    Invariants paradigm → FSM

    Input:
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
    """
    states = {}
    constraints = spec["constraints"]

    for i, constraint in enumerate(constraints):
        check_state = f"check_{constraint['name']}"
        fix_state = f"fix_{constraint['name']}"
        next_check = (
            f"check_{constraints[i + 1]['name']}"
            if i + 1 < len(constraints)
            else "all_valid"
        )

        states[check_state] = {
            "action": constraint["check"],
            "on_success": next_check,
            "on_failure": fix_state,
        }
        states[fix_state] = {
            "action": constraint["fix"],
            "next": check_state,
        }

    states["all_valid"] = {
        "terminal": True,
        "on_maintain": f"check_{constraints[0]['name']}" if spec.get("maintain") else None,
    }

    return {
        "name": spec["name"],
        "paradigm": "invariants",
        "initial": f"check_{constraints[0]['name']}",
        "states": states,
        "maintain": spec.get("maintain", False),
    }
```

### Imperative Compiler

```python
def compile_imperative(spec: dict) -> dict:
    """
    Imperative paradigm → FSM

    Input:
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
    """
    states = {}
    steps = spec["steps"]

    for i, step in enumerate(steps):
        state_name = f"step_{i}"
        next_state = f"step_{i + 1}" if i + 1 < len(steps) else "check_done"
        states[state_name] = {
            "action": step,
            "next": next_state,
        }

    states["check_done"] = {
        "action": spec["until"]["check"],
        "on_success": "done",
        "on_failure": "step_0",
    }
    states["done"] = {"terminal": True}

    return {
        "name": spec["name"],
        "paradigm": "imperative",
        "initial": "step_0",
        "states": states,
        "max_iterations": spec.get("max_iterations", 50),
        "backoff": spec.get("backoff"),
    }
```

## Acceptance Criteria

- [ ] `compile_goal()` produces evaluate/fix/done FSM from goal spec
- [ ] `compile_convergence()` produces measure/apply/done FSM with context variables
- [ ] `compile_invariants()` chains constraint checks with fix states, supports `maintain`
- [ ] `compile_imperative()` creates step sequence with `until` check loop
- [ ] `compile_paradigm()` routes to correct compiler or passes through FSM
- [ ] All compilers validate required fields and raise clear errors
- [ ] Generated FSMs pass `validate_fsm()` from FEAT-040
- [ ] Each compiler is ~50-100 lines, easy to review

## Testing Requirements

```python
# tests/unit/test_compilers.py
class TestGoalCompiler:
    def test_basic_goal(self):
        """Goal with two tools produces evaluate/fix/done."""

    def test_goal_single_tool(self):
        """Goal with one tool uses same for check and fix."""

class TestConvergenceCompiler:
    def test_basic_convergence(self):
        """Convergence spec produces measure/apply/done."""

    def test_convergence_with_tolerance(self):
        """Tolerance field propagates to context."""

class TestInvariantsCompiler:
    def test_two_constraints(self):
        """Two constraints chain correctly."""

    def test_maintain_mode(self):
        """maintain=true sets on_maintain in all_valid."""

class TestImperativeCompiler:
    def test_three_steps(self):
        """Three steps produce step_0/step_1/step_2/check_done."""

    def test_until_condition(self):
        """until.check becomes check_done action."""
```

## Reference

- Design doc: `docs/generalized-fsm-loop.md` sections "Paradigm Definitions" and "Paradigm Compilation"

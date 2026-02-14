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
            "tools": ["/ll:check-code types", "/ll:manage-issue bug fix"],
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
            "tools": ["/ll:check-code fix"],
        }
        fsm = compile_goal(spec)

        assert fsm.states["evaluate"].action == "/ll:check-code fix"
        assert fsm.states["fix"].action == "/ll:check-code fix"

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

    def test_goal_name_slugified(self) -> None:
        """Goal name is properly slugified from goal text."""
        spec = {
            "paradigm": "goal",
            "goal": "No Type Errors in src/",
            "tools": ["cmd"],
        }
        fsm = compile_goal(spec)
        assert fsm.name == "goal-no-type-errors-in-src"

    def test_goal_missing_goal_raises(self) -> None:
        """Missing goal field raises ValueError."""
        spec = {"paradigm": "goal", "tools": ["cmd"]}
        with pytest.raises(ValueError, match="Goal paradigm requires"):
            compile_goal(spec)

    def test_goal_missing_tools_raises(self) -> None:
        """Missing tools field raises ValueError."""
        spec = {"paradigm": "goal", "goal": "Test"}
        with pytest.raises(ValueError, match="Goal paradigm requires"):
            compile_goal(spec)

    def test_goal_empty_tools_raises(self) -> None:
        """Empty tools list raises ValueError."""
        spec = {"paradigm": "goal", "goal": "Test", "tools": []}
        with pytest.raises(ValueError, match="'tools' requires at least one tool"):
            compile_goal(spec)

    def test_goal_with_backoff(self) -> None:
        """Backoff field is propagated."""
        spec = {
            "paradigm": "goal",
            "goal": "Test",
            "tools": ["cmd"],
            "backoff": 2.5,
        }
        fsm = compile_goal(spec)
        assert fsm.backoff == 2.5

    def test_goal_with_timeout(self) -> None:
        """Timeout field is propagated."""
        spec = {
            "paradigm": "goal",
            "goal": "Test",
            "tools": ["cmd"],
            "timeout": 300,
        }
        fsm = compile_goal(spec)
        assert fsm.timeout == 300

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
            "using": "/ll:check-code fix",
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

    def test_convergence_measure_routing(self) -> None:
        """Measure state routes on target/progress/stall verdicts."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_convergence(spec)

        measure = fsm.states["measure"]
        assert measure.route is not None
        assert measure.route.routes["target"] == "done"
        assert measure.route.routes["progress"] == "apply"
        assert measure.route.routes["stall"] == "done"

    def test_convergence_captures_value(self) -> None:
        """Measure state captures current_value."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_convergence(spec)

        assert fsm.states["measure"].capture == "current_value"

    def test_convergence_missing_name_raises(self) -> None:
        """Missing name raises ValueError."""
        spec = {
            "paradigm": "convergence",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        with pytest.raises(ValueError, match="Convergence paradigm requires"):
            compile_convergence(spec)

    def test_convergence_missing_check_raises(self) -> None:
        """Missing check raises ValueError."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "toward": 0,
            "using": "fix",
        }
        with pytest.raises(ValueError, match="Convergence paradigm requires"):
            compile_convergence(spec)

    def test_convergence_missing_toward_raises(self) -> None:
        """Missing toward raises ValueError."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "check": "cmd",
            "using": "fix",
        }
        with pytest.raises(ValueError, match="Convergence paradigm requires"):
            compile_convergence(spec)

    def test_convergence_missing_using_raises(self) -> None:
        """Missing using raises ValueError."""
        spec = {
            "paradigm": "convergence",
            "name": "test",
            "check": "cmd",
            "toward": 0,
        }
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

    def test_three_constraints(self) -> None:
        """Three constraints chain correctly."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [
                {"name": "c1", "check": "cmd1", "fix": "fix1"},
                {"name": "c2", "check": "cmd2", "fix": "fix2"},
                {"name": "c3", "check": "cmd3", "fix": "fix3"},
            ],
        }
        fsm = compile_invariants(spec)

        assert fsm.states["check_c1"].on_success == "check_c2"
        assert fsm.states["check_c2"].on_success == "check_c3"
        assert fsm.states["check_c3"].on_success == "all_valid"

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

    def test_maintain_default_false(self) -> None:
        """maintain defaults to false."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [{"name": "c1", "check": "cmd", "fix": "fix"}],
        }
        fsm = compile_invariants(spec)

        assert fsm.maintain is False
        assert fsm.states["all_valid"].on_maintain is None

    def test_invariants_missing_name_raises(self) -> None:
        """Missing name raises ValueError."""
        spec = {"paradigm": "invariants", "constraints": []}
        with pytest.raises(ValueError, match="Invariants paradigm requires"):
            compile_invariants(spec)

    def test_invariants_missing_constraints_raises(self) -> None:
        """Missing constraints raises ValueError."""
        spec = {"paradigm": "invariants", "name": "test"}
        with pytest.raises(ValueError, match="Invariants paradigm requires"):
            compile_invariants(spec)

    def test_invariants_empty_constraints_raises(self) -> None:
        """Empty constraints list raises ValueError."""
        spec = {"paradigm": "invariants", "name": "test", "constraints": []}
        with pytest.raises(ValueError, match="'constraints' requires at least one constraint"):
            compile_invariants(spec)

    def test_constraint_missing_name_raises(self) -> None:
        """Constraint missing name raises ValueError."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [{"check": "cmd", "fix": "fix"}],
        }
        with pytest.raises(ValueError, match="Constraint 0 requires 'name' field"):
            compile_invariants(spec)

    def test_constraint_missing_check_raises(self) -> None:
        """Constraint missing check raises ValueError."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [{"name": "c1", "fix": "fix"}],
        }
        with pytest.raises(ValueError, match="requires 'check' field"):
            compile_invariants(spec)

    def test_constraint_missing_fix_raises(self) -> None:
        """Constraint missing fix raises ValueError."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [{"name": "c1", "check": "cmd"}],
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

    def test_timeout_propagates(self) -> None:
        """timeout field propagates to FSM."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd"],
            "until": {"check": "verify"},
            "timeout": 600,
        }
        fsm = compile_imperative(spec)

        assert fsm.timeout == 600

    def test_max_iterations_propagates(self) -> None:
        """max_iterations field propagates to FSM."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd"],
            "until": {"check": "verify"},
            "max_iterations": 10,
        }
        fsm = compile_imperative(spec)

        assert fsm.max_iterations == 10

    def test_default_max_iterations(self) -> None:
        """Default max_iterations is 50."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd"],
            "until": {"check": "verify"},
        }
        fsm = compile_imperative(spec)

        assert fsm.max_iterations == 50

    def test_imperative_missing_name_raises(self) -> None:
        """Missing name raises ValueError."""
        spec = {"paradigm": "imperative", "steps": ["cmd"], "until": {"check": "x"}}
        with pytest.raises(ValueError, match="Imperative paradigm requires"):
            compile_imperative(spec)

    def test_imperative_missing_steps_raises(self) -> None:
        """Missing steps raises ValueError."""
        spec = {"paradigm": "imperative", "name": "test", "until": {"check": "x"}}
        with pytest.raises(ValueError, match="Imperative paradigm requires"):
            compile_imperative(spec)

    def test_imperative_empty_steps_raises(self) -> None:
        """Empty steps list raises ValueError."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": [],
            "until": {"check": "x"},
        }
        with pytest.raises(ValueError, match="'steps' requires at least one step"):
            compile_imperative(spec)

    def test_imperative_missing_until_raises(self) -> None:
        """Missing until raises ValueError."""
        spec = {"paradigm": "imperative", "name": "test", "steps": ["cmd"]}
        with pytest.raises(ValueError, match="Imperative paradigm requires"):
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


class TestEvaluatorSupport:
    """Tests for evaluator configuration support in paradigm compilers."""

    def test_goal_with_output_contains_evaluator(self) -> None:
        """Goal paradigm passes output_contains evaluator to evaluate state."""
        spec = {
            "paradigm": "goal",
            "goal": "Lint passes",
            "tools": ["ruff check src/", "ruff check --fix src/"],
            "evaluator": {
                "type": "output_contains",
                "pattern": "All checks passed",
            },
        }
        fsm = compile_goal(spec)

        assert fsm.states["evaluate"].evaluate is not None
        assert fsm.states["evaluate"].evaluate.type == "output_contains"
        assert fsm.states["evaluate"].evaluate.pattern == "All checks passed"

    def test_goal_with_output_numeric_evaluator(self) -> None:
        """Goal paradigm passes output_numeric evaluator to evaluate state."""
        spec = {
            "paradigm": "goal",
            "goal": "No errors",
            "tools": ["error_count.sh", "fix_errors.sh"],
            "evaluator": {
                "type": "output_numeric",
                "operator": "eq",
                "target": 0,
            },
        }
        fsm = compile_goal(spec)

        assert fsm.states["evaluate"].evaluate is not None
        assert fsm.states["evaluate"].evaluate.type == "output_numeric"
        assert fsm.states["evaluate"].evaluate.operator == "eq"
        assert fsm.states["evaluate"].evaluate.target == 0

    def test_goal_with_llm_structured_evaluator(self) -> None:
        """Goal paradigm passes llm_structured evaluator to evaluate state."""
        spec = {
            "paradigm": "goal",
            "goal": "Code is clean",
            "tools": ["code_review.sh", "auto_fix.sh"],
            "evaluator": {
                "type": "llm_structured",
            },
        }
        fsm = compile_goal(spec)

        assert fsm.states["evaluate"].evaluate is not None
        assert fsm.states["evaluate"].evaluate.type == "llm_structured"

    def test_goal_with_exit_code_evaluator_returns_none(self) -> None:
        """Goal with exit_code evaluator returns None (uses default behavior)."""
        spec = {
            "paradigm": "goal",
            "goal": "Tests pass",
            "tools": ["pytest", "fix_tests.sh"],
            "evaluator": {
                "type": "exit_code",
            },
        }
        fsm = compile_goal(spec)

        # exit_code is the default, so we return None to use runtime default
        assert fsm.states["evaluate"].evaluate is None

    def test_goal_without_evaluator(self) -> None:
        """Goal without evaluator config has None evaluate field."""
        spec = {
            "paradigm": "goal",
            "goal": "Tests pass",
            "tools": ["pytest", "fix_tests.sh"],
        }
        fsm = compile_goal(spec)

        assert fsm.states["evaluate"].evaluate is None

    def test_goal_with_evaluator_validates(self) -> None:
        """Goal with evaluator passes validation."""
        spec = {
            "paradigm": "goal",
            "goal": "Lint clean",
            "tools": ["ruff check src/", "ruff check --fix src/"],
            "evaluator": {
                "type": "output_contains",
                "pattern": "0 errors",
            },
        }
        fsm = compile_goal(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity.value == "error" for e in errors)

    def test_invariants_with_per_constraint_evaluator(self) -> None:
        """Invariants paradigm passes per-constraint evaluator config."""
        spec = {
            "paradigm": "invariants",
            "name": "quality-gate",
            "constraints": [
                {
                    "name": "lint",
                    "check": "ruff check src/",
                    "fix": "ruff check --fix src/",
                    "evaluator": {
                        "type": "output_contains",
                        "pattern": "0 errors",
                    },
                },
                {
                    "name": "types",
                    "check": "mypy src/",
                    "fix": "/ll:manage-issue bug fix",
                    # No evaluator - uses default
                },
            ],
        }
        fsm = compile_invariants(spec)

        # First constraint has evaluator
        assert fsm.states["check_lint"].evaluate is not None
        assert fsm.states["check_lint"].evaluate.type == "output_contains"
        assert fsm.states["check_lint"].evaluate.pattern == "0 errors"

        # Second constraint has no evaluator
        assert fsm.states["check_types"].evaluate is None

    def test_invariants_mixed_evaluators(self) -> None:
        """Invariants with different evaluator types per constraint."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [
                {
                    "name": "c1",
                    "check": "cmd1",
                    "fix": "fix1",
                    "evaluator": {"type": "output_contains", "pattern": "OK"},
                },
                {
                    "name": "c2",
                    "check": "cmd2",
                    "fix": "fix2",
                    "evaluator": {"type": "output_numeric", "operator": "lt", "target": 5},
                },
                {
                    "name": "c3",
                    "check": "cmd3",
                    "fix": "fix3",
                    "evaluator": {"type": "llm_structured"},
                },
            ],
        }
        fsm = compile_invariants(spec)

        assert fsm.states["check_c1"].evaluate.type == "output_contains"
        assert fsm.states["check_c2"].evaluate.type == "output_numeric"
        assert fsm.states["check_c2"].evaluate.operator == "lt"
        assert fsm.states["check_c2"].evaluate.target == 5
        assert fsm.states["check_c3"].evaluate.type == "llm_structured"

    def test_invariants_with_evaluator_validates(self) -> None:
        """Invariants with evaluator passes validation."""
        spec = {
            "paradigm": "invariants",
            "name": "test",
            "constraints": [
                {
                    "name": "c1",
                    "check": "cmd",
                    "fix": "fix",
                    "evaluator": {"type": "output_contains", "pattern": "passed"},
                },
            ],
        }
        fsm = compile_invariants(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity.value == "error" for e in errors)

    def test_imperative_with_until_evaluator(self) -> None:
        """Imperative paradigm passes evaluator config to check_done state."""
        spec = {
            "paradigm": "imperative",
            "name": "build-loop",
            "steps": ["npm run build"],
            "until": {
                "check": "npm test",
                "evaluator": {
                    "type": "output_numeric",
                    "operator": "eq",
                    "target": 0,
                },
            },
        }
        fsm = compile_imperative(spec)

        assert fsm.states["check_done"].evaluate is not None
        assert fsm.states["check_done"].evaluate.type == "output_numeric"
        assert fsm.states["check_done"].evaluate.operator == "eq"
        assert fsm.states["check_done"].evaluate.target == 0

    def test_imperative_with_output_contains_evaluator(self) -> None:
        """Imperative with output_contains evaluator for exit condition."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd1"],
            "until": {
                "check": "verify",
                "evaluator": {
                    "type": "output_contains",
                    "pattern": "SUCCESS",
                },
            },
        }
        fsm = compile_imperative(spec)

        assert fsm.states["check_done"].evaluate.type == "output_contains"
        assert fsm.states["check_done"].evaluate.pattern == "SUCCESS"

    def test_imperative_without_until_evaluator(self) -> None:
        """Imperative without evaluator in until has None evaluate field."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd1"],
            "until": {"check": "verify"},
        }
        fsm = compile_imperative(spec)

        assert fsm.states["check_done"].evaluate is None

    def test_imperative_with_evaluator_validates(self) -> None:
        """Imperative with evaluator passes validation."""
        spec = {
            "paradigm": "imperative",
            "name": "test",
            "steps": ["cmd"],
            "until": {
                "check": "verify",
                "evaluator": {"type": "output_contains", "pattern": "OK"},
            },
        }
        fsm = compile_imperative(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity.value == "error" for e in errors)

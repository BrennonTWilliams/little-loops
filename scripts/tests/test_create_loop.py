"""Tests for /ll:create-loop skill artifacts.

Since /ll:create-loop is a prompt-based skill (markdown instructions for Claude),
we cannot directly unit test the interactive wizard flow. Instead, we test:

1. Template YAML definitions compile to valid FSMs
2. Example YAML patterns from the command documentation are valid
3. CLI validation works on generated loop files
4. File creation in .loops/ directory structure
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.fsm import validate_fsm
from little_loops.fsm.compilers import compile_paradigm
from little_loops.fsm.validation import ValidationSeverity

# =============================================================================
# Template Definition Tests
# =============================================================================


class TestTemplateDefinitions:
    """Tests that template definitions from create-loop/SKILL.md are valid.

    These templates are defined in skills/create-loop/SKILL.md lines 72-141.
    """

    def test_python_quality_template(self) -> None:
        """Python quality template compiles to valid FSM."""
        spec = {
            "paradigm": "invariants",
            "name": "python-quality",
            "constraints": [
                {"name": "lint", "check": "ruff check src/", "fix": "ruff check --fix src/"},
                {"name": "types", "check": "mypy src/", "fix": "echo 'Fix type errors'"},
                {"name": "format", "check": "ruff format --check src/", "fix": "ruff format src/"},
            ],
            "maintain": False,
            "max_iterations": 20,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "invariants"
        assert fsm.name == "python-quality"

    def test_javascript_quality_template(self) -> None:
        """JavaScript quality template compiles to valid FSM."""
        spec = {
            "paradigm": "invariants",
            "name": "javascript-quality",
            "constraints": [
                {"name": "lint", "check": "npx eslint src/", "fix": "npx eslint --fix src/"},
                {"name": "types", "check": "npx tsc --noEmit", "fix": "echo 'Fix type errors'"},
            ],
            "maintain": False,
            "max_iterations": 20,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "invariants"
        assert fsm.name == "javascript-quality"

    def test_tests_until_passing_template(self) -> None:
        """Tests-until-passing template compiles to valid FSM."""
        spec = {
            "paradigm": "goal",
            "name": "tests-until-passing",
            "goal": "All tests pass",
            "tools": ["pytest", "/ll:manage-issue bug fix"],
            "max_iterations": 20,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "goal"
        assert fsm.name == "tests-until-passing"

    def test_full_quality_gate_template(self) -> None:
        """Full quality gate template compiles to valid FSM."""
        spec = {
            "paradigm": "invariants",
            "name": "full-quality-gate",
            "constraints": [
                {"name": "tests", "check": "pytest", "fix": "/ll:manage-issue bug fix"},
                {"name": "types", "check": "mypy src/", "fix": "/ll:manage-issue bug fix"},
                {"name": "lint", "check": "ruff check src/", "fix": "ruff check --fix src/"},
            ],
            "maintain": False,
            "max_iterations": 20,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.paradigm == "invariants"
        assert fsm.name == "full-quality-gate"


# =============================================================================
# Goal Paradigm Tests
# =============================================================================


class TestGoalParadigmGeneration:
    """Tests for goal paradigm YAML generation patterns.

    Based on examples from skills/create-loop/SKILL.md lines 378-408.
    """

    def test_basic_goal_yaml(self) -> None:
        """Basic goal paradigm YAML is valid."""
        spec = {
            "paradigm": "goal",
            "name": "fix-types-and-lint",
            "goal": "Type and lint checks pass",
            "tools": ["mypy src/ && ruff check src/", "/ll:check-code fix"],
            "max_iterations": 10,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.initial == "evaluate"
        assert "evaluate" in fsm.states
        assert "fix" in fsm.states
        assert "done" in fsm.states

    def test_goal_state_transitions(self) -> None:
        """Goal FSM has correct state transitions."""
        spec = {
            "paradigm": "goal",
            "name": "test-goal",
            "goal": "Tests pass",
            "tools": ["pytest", "fix_tests.sh"],
        }
        fsm = compile_paradigm(spec)

        assert fsm.states["evaluate"].on_success == "done"
        assert fsm.states["evaluate"].on_failure == "fix"
        assert fsm.states["fix"].next == "evaluate"
        assert fsm.states["done"].terminal is True

    def test_goal_with_output_contains_evaluator(self) -> None:
        """Goal with output_contains evaluator is valid."""
        spec = {
            "paradigm": "goal",
            "name": "custom-check",
            "goal": "Custom check passes",
            "tools": ["custom_check.sh", "custom_fix.sh"],
            "evaluator": {"type": "output_contains", "pattern": "SUCCESS"},
            "max_iterations": 10,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.states["evaluate"].evaluate is not None
        assert fsm.states["evaluate"].evaluate.type == "output_contains"
        assert fsm.states["evaluate"].evaluate.pattern == "SUCCESS"

    def test_goal_with_output_numeric_evaluator(self) -> None:
        """Goal with output_numeric evaluator is valid."""
        spec = {
            "paradigm": "goal",
            "name": "error-count-check",
            "goal": "No errors",
            "tools": ["error_count.sh", "fix_errors.sh"],
            "evaluator": {"type": "output_numeric", "operator": "eq", "target": 0},
            "max_iterations": 10,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.states["evaluate"].evaluate is not None
        assert fsm.states["evaluate"].evaluate.type == "output_numeric"
        assert fsm.states["evaluate"].evaluate.operator == "eq"
        assert fsm.states["evaluate"].evaluate.target == 0

    def test_goal_with_llm_structured_evaluator(self) -> None:
        """Goal with llm_structured evaluator is valid."""
        spec = {
            "paradigm": "goal",
            "name": "ai-review",
            "goal": "Code is clean",
            "tools": ["code_review.sh", "auto_fix.sh"],
            "evaluator": {"type": "llm_structured"},
            "max_iterations": 10,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.states["evaluate"].evaluate is not None
        assert fsm.states["evaluate"].evaluate.type == "llm_structured"

    def test_goal_single_tool(self) -> None:
        """Goal with single tool uses it for both check and fix."""
        spec = {
            "paradigm": "goal",
            "name": "single-tool",
            "goal": "Clean",
            "tools": ["/ll:check-code fix"],
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.states["evaluate"].action == "/ll:check-code fix"
        assert fsm.states["fix"].action == "/ll:check-code fix"


# =============================================================================
# Invariants Paradigm Tests
# =============================================================================


class TestInvariantsParadigmGeneration:
    """Tests for invariants paradigm YAML generation patterns.

    Based on examples from skills/create-loop/SKILL.md lines 477-518.
    """

    def test_basic_invariants_yaml(self) -> None:
        """Basic invariants paradigm YAML is valid."""
        spec = {
            "paradigm": "invariants",
            "name": "code-quality-guardian",
            "constraints": [
                {"name": "tests-pass", "check": "pytest", "fix": "/ll:manage-issue bug fix"},
                {"name": "types-valid", "check": "mypy src/", "fix": "/ll:manage-issue bug fix"},
                {"name": "lint-clean", "check": "ruff check src/", "fix": "ruff check --fix src/"},
            ],
            "maintain": False,
            "max_iterations": 50,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.initial == "check_tests-pass"
        assert fsm.paradigm == "invariants"

    def test_invariants_constraint_chaining(self) -> None:
        """Invariants constraints chain correctly."""
        spec = {
            "paradigm": "invariants",
            "name": "chained-checks",
            "constraints": [
                {"name": "c1", "check": "cmd1", "fix": "fix1"},
                {"name": "c2", "check": "cmd2", "fix": "fix2"},
                {"name": "c3", "check": "cmd3", "fix": "fix3"},
            ],
        }
        fsm = compile_paradigm(spec)

        # Check -> next check on success
        assert fsm.states["check_c1"].on_success == "check_c2"
        assert fsm.states["check_c2"].on_success == "check_c3"
        assert fsm.states["check_c3"].on_success == "all_valid"

        # Check -> fix on failure
        assert fsm.states["check_c1"].on_failure == "fix_c1"
        assert fsm.states["check_c2"].on_failure == "fix_c2"
        assert fsm.states["check_c3"].on_failure == "fix_c3"

        # Fix -> back to same check
        assert fsm.states["fix_c1"].next == "check_c1"
        assert fsm.states["fix_c2"].next == "check_c2"
        assert fsm.states["fix_c3"].next == "check_c3"

    def test_invariants_with_maintain_true(self) -> None:
        """Invariants with maintain=true creates restart loop."""
        spec = {
            "paradigm": "invariants",
            "name": "continuous-quality",
            "constraints": [
                {"name": "lint", "check": "ruff check src/", "fix": "ruff check --fix src/"}
            ],
            "maintain": True,
            "max_iterations": 100,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.maintain is True
        assert fsm.states["all_valid"].on_maintain == "check_lint"

    def test_invariants_with_maintain_false(self) -> None:
        """Invariants with maintain=false terminates after all valid."""
        spec = {
            "paradigm": "invariants",
            "name": "one-shot-quality",
            "constraints": [
                {"name": "lint", "check": "ruff check src/", "fix": "ruff check --fix src/"}
            ],
            "maintain": False,
        }
        fsm = compile_paradigm(spec)
        assert fsm.maintain is False
        assert fsm.states["all_valid"].on_maintain is None
        assert fsm.states["all_valid"].terminal is True

    def test_invariants_with_per_constraint_evaluator(self) -> None:
        """Invariants with per-constraint evaluator is valid."""
        spec = {
            "paradigm": "invariants",
            "name": "custom-guardian",
            "constraints": [
                {
                    "name": "custom-check",
                    "check": "custom_check.sh",
                    "fix": "custom_fix.sh",
                    "evaluator": {"type": "output_contains", "pattern": "OK"},
                },
            ],
            "maintain": False,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.states["check_custom-check"].evaluate is not None
        assert fsm.states["check_custom-check"].evaluate.type == "output_contains"

    def test_invariants_mixed_evaluators(self) -> None:
        """Invariants with different evaluator types per constraint."""
        spec = {
            "paradigm": "invariants",
            "name": "mixed-evaluators",
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
                    # No evaluator - uses default exit_code
                },
            ],
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)

        assert fsm.states["check_c1"].evaluate is not None
        assert fsm.states["check_c1"].evaluate.type == "output_contains"
        assert fsm.states["check_c2"].evaluate is not None
        assert fsm.states["check_c2"].evaluate.type == "output_numeric"
        assert fsm.states["check_c2"].evaluate.operator == "lt"
        assert fsm.states["check_c2"].evaluate.target == 5
        assert fsm.states["check_c3"].evaluate is None  # Default


# =============================================================================
# Convergence Paradigm Tests
# =============================================================================


class TestConvergenceParadigmGeneration:
    """Tests for convergence paradigm YAML generation patterns.

    Based on examples from skills/create-loop/SKILL.md lines 574-598.
    """

    def test_basic_convergence_yaml(self) -> None:
        """Basic convergence paradigm YAML is valid."""
        spec = {
            "paradigm": "convergence",
            "name": "eliminate-lint-errors",
            "check": "ruff check src/ 2>&1 | grep -c 'error' || echo 0",
            "toward": 0,
            "using": "/ll:check-code fix",
            "tolerance": 0,
            "max_iterations": 50,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.initial == "measure"
        assert "measure" in fsm.states
        assert "apply" in fsm.states
        assert "done" in fsm.states
        assert fsm.paradigm == "convergence"

    def test_convergence_state_transitions(self) -> None:
        """Convergence FSM has correct state transitions."""
        spec = {
            "paradigm": "convergence",
            "name": "reduce-errors",
            "check": "error_count.sh",
            "toward": 0,
            "using": "fix_errors.sh",
        }
        fsm = compile_paradigm(spec)

        measure = fsm.states["measure"]
        assert measure.route is not None
        assert measure.route.routes["target"] == "done"
        assert measure.route.routes["progress"] == "apply"
        assert measure.route.routes["stall"] == "done"

        assert fsm.states["apply"].next == "measure"
        assert fsm.states["done"].terminal is True

    def test_convergence_with_tolerance(self) -> None:
        """Convergence with tolerance propagates to context."""
        spec = {
            "paradigm": "convergence",
            "name": "improve-coverage",
            "check": "pytest --cov=src --cov-report=term | grep TOTAL | awk '{print $4}'",
            "toward": 80,
            "using": "/ll:manage-issue feature implement",
            "tolerance": 1,
            "max_iterations": 20,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.context["target"] == 80
        assert fsm.context["tolerance"] == 1

    def test_convergence_has_context(self) -> None:
        """Convergence creates context for interpolation."""
        spec = {
            "paradigm": "convergence",
            "name": "test-convergence",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_paradigm(spec)

        assert "metric_cmd" in fsm.context
        assert "target" in fsm.context
        assert "tolerance" in fsm.context

    def test_convergence_measure_evaluator(self) -> None:
        """Measure state has convergence evaluator."""
        spec = {
            "paradigm": "convergence",
            "name": "test-measure",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_paradigm(spec)

        measure = fsm.states["measure"]
        assert measure.evaluate is not None
        assert measure.evaluate.type == "convergence"

    def test_convergence_captures_value(self) -> None:
        """Measure state captures current_value."""
        spec = {
            "paradigm": "convergence",
            "name": "test-capture",
            "check": "cmd",
            "toward": 0,
            "using": "fix",
        }
        fsm = compile_paradigm(spec)

        assert fsm.states["measure"].capture == "current_value"


# =============================================================================
# Imperative Paradigm Tests
# =============================================================================


class TestImperativeParadigmGeneration:
    """Tests for imperative paradigm YAML generation patterns.

    Based on examples from skills/create-loop/SKILL.md lines 662-696.
    """

    def test_basic_imperative_yaml(self) -> None:
        """Basic imperative paradigm YAML is valid."""
        spec = {
            "paradigm": "imperative",
            "name": "fix-test-check",
            "steps": ["/ll:check-code fix", "pytest", "mypy src/"],
            "until": {"check": "mypy src/ && ruff check src/ && pytest"},
            "max_iterations": 50,
            "backoff": 2,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.initial == "step_0"
        assert "step_0" in fsm.states
        assert "step_1" in fsm.states
        assert "step_2" in fsm.states
        assert "check_done" in fsm.states
        assert "done" in fsm.states
        assert fsm.paradigm == "imperative"

    def test_imperative_step_chaining(self) -> None:
        """Imperative steps chain correctly."""
        spec = {
            "paradigm": "imperative",
            "name": "three-steps",
            "steps": ["cmd1", "cmd2", "cmd3"],
            "until": {"check": "verify"},
        }
        fsm = compile_paradigm(spec)

        assert fsm.states["step_0"].next == "step_1"
        assert fsm.states["step_1"].next == "step_2"
        assert fsm.states["step_2"].next == "check_done"

    def test_imperative_until_condition(self) -> None:
        """Until condition becomes check_done state."""
        spec = {
            "paradigm": "imperative",
            "name": "test-until",
            "steps": ["cmd"],
            "until": {"check": "mypy src/"},
        }
        fsm = compile_paradigm(spec)

        assert fsm.states["check_done"].action == "mypy src/"
        assert fsm.states["check_done"].on_success == "done"
        assert fsm.states["check_done"].on_failure == "step_0"

    def test_imperative_single_step(self) -> None:
        """Single step goes directly to check_done."""
        spec = {
            "paradigm": "imperative",
            "name": "single-step",
            "steps": ["cmd"],
            "until": {"check": "verify"},
        }
        fsm = compile_paradigm(spec)

        assert fsm.states["step_0"].next == "check_done"

    def test_imperative_with_until_evaluator(self) -> None:
        """Imperative with until evaluator is valid."""
        spec = {
            "paradigm": "imperative",
            "name": "build-loop",
            "steps": ["npm run build"],
            "until": {
                "check": "npm test",
                "evaluator": {"type": "output_numeric", "operator": "eq", "target": 0},
            },
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.states["check_done"].evaluate is not None
        assert fsm.states["check_done"].evaluate.type == "output_numeric"
        assert fsm.states["check_done"].evaluate.operator == "eq"
        assert fsm.states["check_done"].evaluate.target == 0

    def test_imperative_with_output_contains_evaluator(self) -> None:
        """Imperative with output_contains evaluator for exit condition."""
        spec = {
            "paradigm": "imperative",
            "name": "test-output-contains",
            "steps": ["cmd1"],
            "until": {
                "check": "verify",
                "evaluator": {"type": "output_contains", "pattern": "SUCCESS"},
            },
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.states["check_done"].evaluate is not None
        assert fsm.states["check_done"].evaluate.type == "output_contains"
        assert fsm.states["check_done"].evaluate.pattern == "SUCCESS"

    def test_imperative_backoff_propagates(self) -> None:
        """Backoff field propagates to FSM."""
        spec = {
            "paradigm": "imperative",
            "name": "with-backoff",
            "steps": ["cmd"],
            "until": {"check": "verify"},
            "backoff": 2,
        }
        fsm = compile_paradigm(spec)
        assert fsm.backoff == 2

    def test_imperative_timeout_propagates(self) -> None:
        """Timeout field propagates to FSM."""
        spec = {
            "paradigm": "imperative",
            "name": "with-timeout",
            "steps": ["cmd"],
            "until": {"check": "verify"},
            "timeout": 600,
        }
        fsm = compile_paradigm(spec)
        assert fsm.timeout == 600


# =============================================================================
# CLI Validation Tests
# =============================================================================


class TestLoopFileValidation:
    """Tests for loop file creation and validation via CLI."""

    @pytest.fixture
    def loops_dir(self, tmp_path: Path) -> Path:
        """Create a .loops directory."""
        loops = tmp_path / ".loops"
        loops.mkdir()
        return loops

    def test_valid_goal_loop_file(self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
        """Valid goal loop file passes ll-loop validate."""
        loop_content = """
paradigm: goal
name: test-goal
goal: Tests pass
tools:
  - pytest
  - echo fix
max_iterations: 10
"""
        (loops_dir / "test-goal.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "test-goal"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_valid_invariants_loop_file(
        self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid invariants loop file passes ll-loop validate."""
        loop_content = """
paradigm: invariants
name: quality-gate
constraints:
  - name: lint
    check: ruff check src/
    fix: ruff check --fix src/
maintain: false
max_iterations: 20
"""
        (loops_dir / "quality-gate.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "quality-gate"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_valid_convergence_loop_file(
        self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid convergence loop file passes ll-loop validate."""
        loop_content = """
paradigm: convergence
name: reduce-errors
check: "echo 5"
toward: 0
using: echo fix
tolerance: 0
max_iterations: 20
"""
        (loops_dir / "reduce-errors.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "reduce-errors"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_valid_imperative_loop_file(
        self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Valid imperative loop file passes ll-loop validate."""
        loop_content = """
paradigm: imperative
name: build-test
steps:
  - echo build
  - echo test
until:
  check: "echo done"
max_iterations: 10
"""
        (loops_dir / "build-test.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "build-test"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 0

    def test_invalid_loop_file_fails_validation(
        self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
    ) -> None:
        """Invalid loop file fails ll-loop validate."""
        loop_content = """
paradigm: goal
name: bad-goal
# Missing required 'goal' and 'tools' fields
"""
        (loops_dir / "bad-goal.yaml").write_text(loop_content)
        monkeypatch.chdir(loops_dir.parent)

        with patch.object(sys, "argv", ["ll-loop", "validate", "bad-goal"]):
            from little_loops.cli import main_loop

            result = main_loop()

        assert result == 1
        captured = capsys.readouterr()
        # Error should mention the issue
        output = captured.err.lower() + captured.out.lower()
        assert "error" in output or "require" in output


# =============================================================================
# File Creation Tests
# =============================================================================


class TestLoopFileCreation:
    """Tests for loop file creation in .loops/ directory."""

    def test_loops_directory_creation(self, tmp_path: Path) -> None:
        """Loop file can be created after .loops/ directory exists."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_content = {
            "paradigm": "goal",
            "name": "test-loop",
            "goal": "Test passes",
            "tools": ["pytest", "echo fix"],
        }

        loop_file = loops_dir / "test-loop.yaml"
        loop_file.write_text(yaml.dump(loop_content))

        assert loop_file.exists()
        loaded = yaml.safe_load(loop_file.read_text())
        assert loaded["name"] == "test-loop"

    def test_loop_file_naming_convention(self, tmp_path: Path) -> None:
        """Loop files use name.yaml naming convention."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_names = ["fix-types", "quality-guardian", "reduce-errors", "build-test-check"]

        for name in loop_names:
            loop_content = {
                "paradigm": "goal",
                "name": name,
                "goal": "Test",
                "tools": ["cmd"],
            }
            loop_file = loops_dir / f"{name}.yaml"
            loop_file.write_text(yaml.dump(loop_content))

            assert loop_file.exists()
            loaded = yaml.safe_load(loop_file.read_text())
            assert loaded["name"] == name

    def test_existing_file_detection(self, tmp_path: Path) -> None:
        """Existing loop file can be detected before overwrite."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_file = loops_dir / "existing-loop.yaml"
        loop_file.write_text("name: existing-loop")

        # Simulate the check from create-loop/SKILL.md Step 5
        exists = loop_file.exists()
        assert exists is True

    def test_load_and_validate_created_file(self, tmp_path: Path) -> None:
        """Created loop file can be loaded via compile_paradigm (how CLI does it)."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        loop_content = """
paradigm: goal
name: validated-loop
goal: Tests pass
tools:
  - pytest
  - echo fix
max_iterations: 10
"""
        loop_file = loops_dir / "validated-loop.yaml"
        loop_file.write_text(loop_content)

        # CLI uses compile_paradigm for paradigm files, not load_and_validate directly
        data = yaml.safe_load(loop_file.read_text())
        fsm = compile_paradigm(data)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.name == "validated-loop"
        assert fsm.paradigm == "goal"

    def test_all_paradigm_files_load_correctly(self, tmp_path: Path) -> None:
        """All paradigm types can be written and loaded correctly via compile_paradigm."""
        loops_dir = tmp_path / ".loops"
        loops_dir.mkdir()

        paradigm_examples = {
            "goal": {
                "paradigm": "goal",
                "name": "goal-example",
                "goal": "Tests pass",
                "tools": ["pytest", "fix"],
            },
            "invariants": {
                "paradigm": "invariants",
                "name": "invariants-example",
                "constraints": [{"name": "c1", "check": "cmd", "fix": "fix"}],
            },
            "convergence": {
                "paradigm": "convergence",
                "name": "convergence-example",
                "check": "cmd",
                "toward": 0,
                "using": "fix",
            },
            "imperative": {
                "paradigm": "imperative",
                "name": "imperative-example",
                "steps": ["cmd"],
                "until": {"check": "verify"},
            },
        }

        for paradigm_name, spec in paradigm_examples.items():
            loop_file = loops_dir / f"{paradigm_name}-example.yaml"
            loop_file.write_text(yaml.dump(spec))

            # CLI uses compile_paradigm for paradigm files
            data = yaml.safe_load(loop_file.read_text())
            fsm = compile_paradigm(data)
            errors = validate_fsm(fsm)
            assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
            assert fsm.name == f"{paradigm_name}-example"
            assert fsm.paradigm == paradigm_name

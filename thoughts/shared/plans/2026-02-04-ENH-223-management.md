# ENH-223: Add Tests for /ll:create-loop Skill - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-223-add-create-loop-skill-tests.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The `/ll:create-loop` skill is defined in `commands/create_loop.md` as an interactive wizard that guides users through creating FSM loop configurations. It's a **prompt-based skill** (markdown instructions that Claude follows), not Python code that can be directly unit tested.

### Key Discoveries

1. **Wizard Flow** (`commands/create_loop.md:27-196`): The wizard has multiple steps:
   - Step 0: Template vs. custom mode selection
   - Step 0.1-0.2: Template selection and customization
   - Step 1: Paradigm selection (goal, invariants, convergence, imperative)
   - Step 2: Paradigm-specific questions
   - Step 3: Loop naming
   - Step 4: Preview and confirm
   - Step 5: Save and validate

2. **Template Definitions** (`commands/create_loop.md:72-141`): Four pre-built templates:
   - `python-quality` (invariants paradigm)
   - `javascript-quality` (invariants paradigm)
   - `tests-until-passing` (goal paradigm)
   - `full-quality-gate` (invariants paradigm)

3. **YAML Generation**: Each paradigm has specific YAML structure documented:
   - Goal: `paradigm`, `goal`, `tools`, `max_iterations`, optional `evaluator`
   - Invariants: `paradigm`, `name`, `constraints` (each with name/check/fix), optional `maintain`
   - Convergence: `paradigm`, `name`, `check`, `toward`, `using`, optional `tolerance`
   - Imperative: `paradigm`, `name`, `steps`, `until` (with check), optional `backoff`

4. **Existing Test Patterns** (`scripts/tests/test_fsm_compilers.py`):
   - Tests use `compile_paradigm()` to compile YAML specs to FSM
   - Tests verify the compiled FSM structure and validation
   - Uses `validate_fsm()` to check for errors

5. **CLI Validation** (`scripts/little_loops/cli.py:489`): `ll-loop validate <name>` validates loop files

### What CAN Be Tested

Since the create_loop command is a markdown prompt (not Python code), we cannot unit test the interactive wizard flow itself. However, we CAN test:

1. **Template YAML validity**: Parse the template YAML and validate it compiles correctly
2. **YAML generation patterns**: Test that YAML patterns from the command compile to valid FSMs
3. **File creation behavior**: Test `ll-loop validate` CLI on generated files
4. **Template variable substitution**: Test that placeholder replacement produces valid YAML

### What CANNOT Be Directly Tested

- Interactive wizard flow (AskUserQuestion calls)
- Claude's interpretation of markdown instructions
- User interaction paths through the wizard

## Desired End State

A new test file `scripts/tests/test_create_loop.py` that:
1. Validates all 4 template definitions produce valid FSMs
2. Tests YAML generation patterns for each paradigm
3. Tests `ll-loop validate` on generated loop files
4. Tests file creation in `.loops/` directory structure

### How to Verify
- All tests pass with `pytest scripts/tests/test_create_loop.py -v`
- Tests cover all 4 paradigms (goal, convergence, invariants, imperative)
- Tests verify YAML generation produces valid output

## What We're NOT Doing

- Not testing the interactive wizard flow itself (this is a markdown prompt, not Python code)
- Not testing AskUserQuestion responses (requires mocking Claude)
- Not testing the full end-to-end wizard (would require integration tests with Claude)
- Not adding new dependencies or complex mocking frameworks

## Solution Approach

Create tests that validate the **artifacts** produced by the create_loop command:
1. Template YAML definitions from the command documentation
2. Example YAML patterns for each paradigm
3. CLI validation behavior
4. File system operations

## Implementation Phases

### Phase 1: Create Test File Structure

#### Overview
Create the test file with imports, fixtures, and basic structure.

#### Changes Required

**File**: `scripts/tests/test_create_loop.py`
**Changes**: Create new file with test class structure

```python
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
from little_loops.fsm.validation import load_and_validate, ValidationSeverity
```

#### Success Criteria

**Automated Verification**:
- [ ] File exists: `test -f scripts/tests/test_create_loop.py`
- [ ] Imports work: `python -c "from scripts.tests.test_create_loop import *"`

---

### Phase 2: Template Validation Tests

#### Overview
Test that all 4 template definitions from `commands/create_loop.md` compile to valid FSMs.

#### Changes Required

**File**: `scripts/tests/test_create_loop.py`
**Changes**: Add template validation test class

```python
class TestTemplateDefinitions:
    """Tests that template definitions from create_loop.md are valid."""

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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_create_loop.py::TestTemplateDefinitions -v`

---

### Phase 3: Paradigm YAML Generation Tests

#### Overview
Test that example YAML patterns for each paradigm from the command documentation produce valid FSMs.

#### Changes Required

**File**: `scripts/tests/test_create_loop.py`
**Changes**: Add paradigm-specific tests

```python
class TestGoalParadigmGeneration:
    """Tests for goal paradigm YAML generation patterns."""

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


class TestInvariantsParadigmGeneration:
    """Tests for invariants paradigm YAML generation patterns."""

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

    def test_invariants_with_maintain_true(self) -> None:
        """Invariants with maintain=true creates restart loop."""
        spec = {
            "paradigm": "invariants",
            "name": "continuous-quality",
            "constraints": [{"name": "lint", "check": "ruff check src/", "fix": "ruff check --fix src/"}],
            "maintain": True,
            "max_iterations": 100,
        }
        fsm = compile_paradigm(spec)
        errors = validate_fsm(fsm)
        assert not any(e.severity == ValidationSeverity.ERROR for e in errors)
        assert fsm.maintain is True
        assert fsm.states["all_valid"].on_maintain == "check_lint"

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


class TestConvergenceParadigmGeneration:
    """Tests for convergence paradigm YAML generation patterns."""

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


class TestImperativeParadigmGeneration:
    """Tests for imperative paradigm YAML generation patterns."""

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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_create_loop.py::TestGoalParadigmGeneration -v`
- [ ] Tests pass: `pytest scripts/tests/test_create_loop.py::TestInvariantsParadigmGeneration -v`
- [ ] Tests pass: `pytest scripts/tests/test_create_loop.py::TestConvergenceParadigmGeneration -v`
- [ ] Tests pass: `pytest scripts/tests/test_create_loop.py::TestImperativeParadigmGeneration -v`

---

### Phase 4: CLI Validation Tests

#### Overview
Test that `ll-loop validate` CLI works correctly on loop files.

#### Changes Required

**File**: `scripts/tests/test_create_loop.py`
**Changes**: Add CLI validation tests

```python
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

    def test_valid_invariants_loop_file(self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    def test_valid_convergence_loop_file(self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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

    def test_valid_imperative_loop_file(self, loops_dir: Path, monkeypatch: pytest.MonkeyPatch) -> None:
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
        assert "error" in captured.err.lower() or "error" in captured.out.lower()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_create_loop.py::TestLoopFileValidation -v`

---

### Phase 5: File Creation Tests

#### Overview
Test file creation behavior in `.loops/` directory.

#### Changes Required

**File**: `scripts/tests/test_create_loop.py`
**Changes**: Add file creation tests

```python
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

        # Simulate the check from create_loop.md Step 5
        exists = loop_file.exists()
        assert exists is True

    def test_load_and_validate_created_file(self, tmp_path: Path) -> None:
        """Created loop file can be loaded and validated."""
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

        fsm = load_and_validate(loop_file)
        assert fsm.name == "validated-loop"
        assert fsm.paradigm == "goal"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_create_loop.py::TestLoopFileCreation -v`
- [ ] All tests pass: `pytest scripts/tests/test_create_loop.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_create_loop.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_create_loop.py`

---

## Testing Strategy

### Unit Tests
- Template validation (4 templates)
- YAML generation patterns (4 paradigms × multiple configurations)
- File creation and naming

### Integration Tests
- CLI `ll-loop validate` on generated files
- Load and validate round-trip

## References

- Original issue: `.issues/enhancements/P3-ENH-223-add-create-loop-skill-tests.md`
- Command definition: `commands/create_loop.md`
- Compiler tests pattern: `scripts/tests/test_fsm_compilers.py`
- Schema validation: `scripts/little_loops/fsm/validation.py`
- Existing loop tests: `scripts/tests/test_ll_loop_*.py`

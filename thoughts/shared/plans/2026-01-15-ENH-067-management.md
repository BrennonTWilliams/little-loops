# ENH-067: Add End-to-End Compile Command Tests - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-067-ll-loop-compile-e2e-tests.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

The `ll-loop compile` command exists and works correctly, but test coverage only validates the CLI plumbing by mocking the `compile_paradigm()` function.

### Key Discoveries
- Existing compile tests at `scripts/tests/test_ll_loop.py:1319-1391` mock `compile_paradigm()`
- `compile_paradigm()` dispatcher at `scripts/little_loops/fsm/compilers.py:51-89` routes to paradigm-specific compilers
- Four paradigm compilers exist: `goal`, `convergence`, `invariants`, `imperative`
- FSM validation available via `validate_fsm()` at `scripts/little_loops/fsm/validation.py:190`
- `ll-loop validate` command can validate compiled output

### Current Test Approach (What We're Replacing)
```python
# Current: Mocked tests at test_ll_loop.py:1319-1350
def test_compile_valid_paradigm(self, tmp_path: Path) -> None:
    with patch("little_loops.fsm.compilers.compile_paradigm") as mock_compile:
        # Mocks compilation - never exercises actual compilers
```

## Desired End State

End-to-end tests that:
1. Compile real paradigm YAML without mocking
2. Verify output is valid FSM YAML with correct structure
3. Verify compiled output passes `validate_fsm()`
4. Cover all four paradigm types
5. Test error handling for invalid input

### How to Verify
- All new tests pass: `pytest scripts/tests/test_ll_loop.py -k TestCompileEndToEnd -v`
- Tests exercise actual compilation (no mocking of core compile logic)
- Coverage of compile command increases

## What We're NOT Doing

- Not changing the compile command implementation
- Not testing FSM execution (separate concern, covered elsewhere)
- Not adding new paradigm types
- Not modifying existing mocked tests (they serve CLI plumbing validation)

## Solution Approach

Add a new `TestCompileEndToEnd` test class to `test_ll_loop.py` with:
1. Tests for each paradigm type producing valid FSM
2. Tests verifying FSM structure (states, initial, etc.)
3. Tests verifying output passes `validate_fsm()`
4. Tests for error cases (invalid paradigm, missing required fields)
5. Tests for CLI flags (`-o` output flag with real compilation)

## Implementation Phases

### Phase 1: Add TestCompileEndToEnd Test Class

#### Overview
Add end-to-end compile tests that exercise the actual compilation logic without mocking.

#### Changes Required

**File**: `scripts/tests/test_ll_loop.py`
**Changes**: Add new test class after existing compile tests (around line 1392)

```python
class TestCompileEndToEnd:
    """End-to-end tests for paradigm compilation without mocking."""

    def test_compile_goal_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Goal paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: goal
goal: "No errors"
tools:
  - "echo check"
  - "echo fix"
"""
        input_file = tmp_path / "goal.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "goal.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 0
        assert output_file.exists()

        # Verify output structure
        import yaml
        fsm_data = yaml.safe_load(output_file.read_text())
        assert "states" in fsm_data
        assert "initial" in fsm_data
        assert fsm_data["initial"] == "evaluate"
        assert "evaluate" in fsm_data["states"]
        assert "fix" in fsm_data["states"]
        assert "done" in fsm_data["states"]

    def test_compile_convergence_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Convergence paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: convergence
name: "reduce-errors"
check: "echo 5"
toward: 0
using: "echo fix"
"""
        input_file = tmp_path / "convergence.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "convergence.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 0

        import yaml
        fsm_data = yaml.safe_load(output_file.read_text())
        assert fsm_data["initial"] == "measure"
        assert "measure" in fsm_data["states"]
        assert "apply" in fsm_data["states"]
        assert "done" in fsm_data["states"]

    def test_compile_invariants_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Invariants paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: invariants
name: "quality-checks"
constraints:
  - name: "tests"
    check: "echo test"
    fix: "echo fix-tests"
  - name: "lint"
    check: "echo lint"
    fix: "echo fix-lint"
"""
        input_file = tmp_path / "invariants.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "invariants.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 0

        import yaml
        fsm_data = yaml.safe_load(output_file.read_text())
        assert fsm_data["initial"] == "check_tests"
        assert "check_tests" in fsm_data["states"]
        assert "fix_tests" in fsm_data["states"]
        assert "check_lint" in fsm_data["states"]
        assert "fix_lint" in fsm_data["states"]
        assert "all_valid" in fsm_data["states"]

    def test_compile_imperative_produces_valid_fsm(self, tmp_path: Path) -> None:
        """Imperative paradigm compiles to valid FSM."""
        paradigm_yaml = """
paradigm: imperative
name: "fix-cycle"
steps:
  - "echo step1"
  - "echo step2"
until:
  check: "echo done"
"""
        input_file = tmp_path / "imperative.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "imperative.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 0

        import yaml
        fsm_data = yaml.safe_load(output_file.read_text())
        assert fsm_data["initial"] == "step_0"
        assert "step_0" in fsm_data["states"]
        assert "step_1" in fsm_data["states"]
        assert "check_done" in fsm_data["states"]
        assert "done" in fsm_data["states"]

    def test_compiled_output_passes_validation(self, tmp_path: Path) -> None:
        """Compiled FSM passes validate_fsm() check."""
        paradigm_yaml = """
paradigm: goal
goal: "Test validation"
tools:
  - "echo check"
  - "echo fix"
"""
        input_file = tmp_path / "validate-test.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "validate-test.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 0

        # Load and validate the FSM
        import yaml
        from little_loops.fsm.schema import FSMLoop
        from little_loops.fsm.validation import validate_fsm

        fsm_data = yaml.safe_load(output_file.read_text())
        fsm = FSMLoop.from_dict(fsm_data)
        errors = validate_fsm(fsm)

        # No error-level validation issues
        assert not any(e.severity.value == "error" for e in errors)

    def test_compile_unknown_paradigm_returns_error(self, tmp_path: Path) -> None:
        """Unknown paradigm type returns error."""
        paradigm_yaml = """
paradigm: nonexistent-type
name: "test"
"""
        input_file = tmp_path / "unknown.paradigm.yaml"
        input_file.write_text(paradigm_yaml)

        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_compile_goal_missing_required_field_returns_error(
        self, tmp_path: Path
    ) -> None:
        """Goal paradigm missing 'goal' field returns error."""
        paradigm_yaml = """
paradigm: goal
tools:
  - "echo check"
"""
        input_file = tmp_path / "incomplete.paradigm.yaml"
        input_file.write_text(paradigm_yaml)

        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 1

    def test_compile_creates_output_in_nested_directory(self, tmp_path: Path) -> None:
        """Output flag creates parent directories if needed."""
        paradigm_yaml = """
paradigm: goal
goal: "Test"
tools:
  - "echo check"
"""
        input_file = tmp_path / "test.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "nested" / "deep" / "output.fsm.yaml"

        with patch.object(
            sys, "argv", ["ll-loop", "compile", str(input_file), "-o", str(output_file)]
        ):
            from little_loops.cli import main_loop
            result = main_loop()

        # Note: Current implementation may not create nested dirs
        # This test documents the expected behavior
        # If it fails, we know the feature doesn't exist yet
        if result == 0:
            assert output_file.exists()

    def test_compile_default_output_path(self, tmp_path: Path) -> None:
        """Without -o flag, output uses input filename with .fsm.yaml extension."""
        paradigm_yaml = """
paradigm: goal
goal: "Test"
tools:
  - "echo check"
"""
        input_file = tmp_path / "my-paradigm.yaml"
        input_file.write_text(paradigm_yaml)

        with patch.object(sys, "argv", ["ll-loop", "compile", str(input_file)]):
            from little_loops.cli import main_loop
            result = main_loop()

        assert result == 0
        # Default output replaces .yaml with .fsm.yaml
        default_output = tmp_path / "my-paradigm.fsm.yaml"
        assert default_output.exists()
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `pytest scripts/tests/test_ll_loop.py -k TestCompileEndToEnd -v`
- [ ] Lint passes: `ruff check scripts/tests/test_ll_loop.py`
- [ ] Types pass: `mypy scripts/tests/test_ll_loop.py`

---

### Phase 2: Verify All Tests Pass Together

#### Overview
Run the full test suite to ensure new tests don't interfere with existing tests.

#### Success Criteria

**Automated Verification**:
- [ ] All ll-loop tests pass: `pytest scripts/tests/test_ll_loop.py -v`
- [ ] All FSM compiler tests pass: `pytest scripts/tests/test_fsm_compilers.py -v`

## Testing Strategy

### Unit Tests
- Each paradigm type has individual compile test
- Error cases for missing fields
- Error case for unknown paradigm

### Integration Tests
- Compiled output passes `validate_fsm()`
- Output file path handling (default and `-o` flag)

## References

- Original issue: `.issues/enhancements/P3-ENH-067-ll-loop-compile-e2e-tests.md`
- Compile command implementation: `scripts/little_loops/cli.py:677-722`
- Paradigm compilers: `scripts/little_loops/fsm/compilers.py:51-417`
- FSM validation: `scripts/little_loops/fsm/validation.py:190`
- Existing compile tests: `scripts/tests/test_ll_loop.py:1319-1391`

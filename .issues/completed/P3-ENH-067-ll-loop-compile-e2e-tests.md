# ENH-067: Add End-to-End Compile Command Tests for ll-loop

## Summary

The `ll-loop compile` command tests currently mock the actual compilation logic. There are no end-to-end tests that verify paradigm-to-FSM compilation produces valid, executable loop definitions.

## Current State

- **Test File**: `scripts/tests/test_ll_loop.py`
- **Compile Tests**: Mock internal compilation
- **Coverage**: Compilation logic not exercised

### Current Test Approach

```python
def test_compile_valid_paradigm(self, tmp_path, monkeypatch):
    """Tests compile creates output file."""
    # Creates input file
    # Mocks compilation internals
    # Only verifies output file created, not contents
```

### What's Missing

Tests that:
1. Compile real paradigm definitions
2. Verify output is valid FSM YAML
3. Verify compiled output is executable
4. Test different paradigm types

## Proposed Tests

### End-to-End Compilation Tests

```python
class TestCompileEndToEnd:
    """End-to-end tests for paradigm compilation."""

    def test_compile_produces_valid_fsm(self, tmp_path):
        """Compiled output should be valid FSM schema."""
        paradigm_yaml = """
paradigm: goal
goal: "No type errors"
tools:
  - "mypy src/"
  - "/ll:manage-issue bug fix"
"""
        input_file = tmp_path / "goal.paradigm.yaml"
        input_file.write_text(paradigm_yaml)
        output_file = tmp_path / "goal.fsm.yaml"

        # Run compile
        result = subprocess.run(
            ["ll-loop", "compile", str(input_file), "-o", str(output_file)],
            capture_output=True, text=True
        )

        assert result.returncode == 0
        assert output_file.exists()

        # Verify output is valid FSM
        import yaml
        fsm = yaml.safe_load(output_file.read_text())
        assert "states" in fsm
        assert "initial" in fsm

    def test_compiled_output_validates(self, tmp_path):
        """Compiled FSM should pass validation."""
        # Compile paradigm
        # Run ll-loop validate on output
        # Verify passes

    def test_compiled_output_executes(self, tmp_path):
        """Compiled FSM should be executable."""
        # Compile paradigm
        # Run ll-loop run on compiled output
        # Verify execution completes

    def test_compile_each_paradigm_type(self, tmp_path):
        """Each supported paradigm type compiles successfully."""
        # Actual supported paradigms from compilers.py:
        paradigms = [
            "goal",
            "convergence",
            "invariants",
            "imperative",
        ]
        for paradigm in paradigms:
            # Create paradigm file with required fields
            # Compile
            # Verify valid output
```

### Compilation Error Handling

```python
    def test_compile_invalid_paradigm_shows_error(self, tmp_path):
        """Invalid paradigm should produce clear error message."""
        invalid_yaml = """
paradigm: nonexistent-type
config: {}
"""
        # Verify compile fails with helpful message

    def test_compile_missing_required_field(self, tmp_path):
        """Missing required field should error clearly."""
        incomplete_yaml = """
paradigm: goal
# missing: goal field
# missing: tools field
"""
        # Verify error mentions missing field

    def test_compile_output_flag_creates_directory(self, tmp_path):
        """-o flag creates parent directories if needed."""
        # Verify nested output path works
```

## Implementation Approach

Add tests to `test_ll_loop.py` or new `test_compile_integration.py`:

1. Create real paradigm YAML files
2. Run `compile` command without mocking internals
3. Verify output files contain valid FSM structure
4. Optionally execute compiled output to verify end-to-end

## Impact

- **Priority**: P3 (Medium)
- **Effort**: Medium
- **Risk**: Low (adding tests only)
- **Breaking Change**: No

## Acceptance Criteria

- [x] Test compiles real paradigm without mocking
- [x] Test verifies output is valid FSM YAML
- [x] Test verifies compiled output passes validation
- [ ] Test verifies compiled output can execute (not implemented - separate concern covered by FSM executor tests)
- [x] Test covers multiple paradigm types
- [x] Test verifies error handling for invalid input
- [x] All new tests pass

## Labels

`enhancement`, `testing`, `coverage`, `ll-loop`, `compile`, `paradigm`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-01-15
- **Status**: Completed

### Changes Made
- `scripts/tests/test_ll_loop.py`: Added new `TestCompileEndToEnd` test class with 8 tests
  - `test_compile_goal_produces_valid_fsm` - Goal paradigm compilation
  - `test_compile_convergence_produces_valid_fsm` - Convergence paradigm compilation
  - `test_compile_invariants_produces_valid_fsm` - Invariants paradigm compilation
  - `test_compile_imperative_produces_valid_fsm` - Imperative paradigm compilation
  - `test_compiled_output_passes_validation` - FSM validation check
  - `test_compile_unknown_paradigm_returns_error` - Error handling for unknown paradigm
  - `test_compile_goal_missing_required_field_returns_error` - Error handling for missing fields
  - `test_compile_default_output_path` - Default output path behavior
- Added `yaml` import to test file

### Verification Results
- Tests: PASS (122 tests, 8 new)
- Lint: PASS
- Types: PASS

### Notes
The "compiled output can execute" criterion was intentionally not implemented as a separate test. Execution testing is already covered by `TestEndToEndExecution` class, and mixing compile tests with execution tests would conflate concerns. The `test_compiled_output_passes_validation` test ensures the compiled output is structurally valid for execution.

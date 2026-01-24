# ENH-129: FSM Validation Test Coverage - Implementation Plan

## Issue Reference
- **File**: .issues/enhancements/P1-ENH-129-fsm-validation-test-coverage.md
- **Type**: enhancement
- **Priority**: P1
- **Action**: implement

## Current State Analysis

The issue claims `validation.py` has "no test coverage," but tests already exist in `test_fsm_schema.py`:
- `TestFSMValidation` (lines 465-578) - 9 tests
- `TestEvaluatorValidation` (lines 581-731) - 7 tests
- `TestLoadAndValidate` (lines 734-800) - 4 tests
- `TestValidationError` (lines 803-824) - 2 tests

### Key Discoveries
- Tests exist but coverage is incomplete
- Many edge cases and error paths are untested
- The issue's acceptance criteria to create a new file (`test_fsm_validation.py`) is not necessary - adding to existing file is better

## Desired End State

Comprehensive test coverage for `validation.py` with:
- All validation functions directly tested
- All error messages verified
- Edge cases covered (empty states, circular refs, self-refs)
- >90% line coverage

### How to Verify
- `python -m pytest scripts/tests/test_fsm_schema.py -v` - all tests pass
- `python -m pytest --cov=little_loops.fsm.validation --cov-report=term-missing scripts/tests/test_fsm_schema.py` - >90% coverage

## What We're NOT Doing

- Not creating a separate `test_fsm_validation.py` file - adding to existing `test_fsm_schema.py` maintains test organization
- Not refactoring existing tests - they are well-structured
- Not testing `schema.py` methods - those are already covered

## Gap Analysis

### `_validate_evaluator()` (lines 72-140) - Missing Tests

| Line Range | Feature | Current Coverage | Gap |
|------------|---------|-----------------|-----|
| 86-95 | Required fields check | Partial | Missing: `output_numeric` missing `target`, `output_json` missing `operator` |
| 97-105 | Valid operators | Partial | Missing: valid operator test (only invalid tested) |
| 107-116 | Convergence direction | None | Missing: invalid direction test |
| 118-128 | Tolerance validation | Partial | Missing: interpolation string tolerance skips validation |
| 130-138 | min_confidence | Partial | Missing: boundary values (0, 1 are valid) |

### `_validate_state_routing()` (lines 143-187) - Missing Tests

| Line Range | Feature | Current Coverage | Gap |
|------------|---------|-----------------|-----|
| 158-161 | Shorthand detection | Partial | Missing: `on_error` only case |
| 175-177 | Valid transitions | Partial | Missing: `next` only, terminal only as valid |

### `validate_fsm()` (lines 190-261) - Missing Tests

| Line Range | Feature | Current Coverage | Gap |
|------------|---------|-----------------|-----|
| 207 | get_all_state_names | Implicit | Missing: empty states dict |
| 229-240 | State validation loop | Partial | Missing: self-reference, circular refs |

### `_find_reachable_states()` (lines 264-291) - Missing Tests

| Line Range | Feature | Current Coverage | Gap |
|------------|---------|-----------------|-----|
| 276 | BFS initialization | None | No direct unit tests |
| 280 | Skip non-existent | None | Missing: initial state doesn't exist in states |
| 287-289 | Ref traversal | Implicit | Missing: complex graph with multiple paths |

### `load_and_validate()` (lines 294-344) - Missing Tests

| Line Range | Feature | Current Coverage | Gap |
|------------|---------|-----------------|-----|
| 314-315 | Type check | None | Missing: non-dict YAML root |
| 311-312 | YAML parsing | None | Missing: invalid YAML syntax |
| 339-342 | Warning logging | None | Missing: warnings are logged not raised |

## Implementation Phases

### Phase 1: Evaluator Validation Edge Cases

#### Overview
Add tests for missing evaluator validation paths.

#### Changes Required

**File**: `scripts/tests/test_fsm_schema.py`
**Changes**: Add tests to `TestEvaluatorValidation` class

```python
def test_output_numeric_requires_target(self) -> None:
    """output_numeric requires target field."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="test",
                evaluate=EvaluateConfig(type="output_numeric", operator="eq"),  # no target
                on_success="done",
                on_failure="done",
            ),
            "done": make_state(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    assert any("requires 'target' field" in e.message for e in errors)


def test_output_json_requires_operator(self) -> None:
    """output_json requires operator field."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="test",
                evaluate=EvaluateConfig(
                    type="output_json",
                    path="$.result",
                    target=0,
                    # no operator
                ),
                on_success="done",
                on_failure="done",
            ),
            "done": make_state(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    assert any("requires 'operator' field" in e.message for e in errors)


def test_valid_operators_accepted(self) -> None:
    """All valid operators are accepted."""
    for op in ["eq", "ne", "lt", "le", "gt", "ge"]:
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(type="output_numeric", operator=op, target=5),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0, f"Operator {op} should be valid"


def test_convergence_invalid_direction(self) -> None:
    """Convergence with invalid direction is rejected."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="test",
                evaluate=EvaluateConfig(
                    type="convergence",
                    target=0,
                    direction="invalid",
                ),
                on_success="done",
                on_failure="done",
            ),
            "done": make_state(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    assert any("Invalid direction" in e.message for e in errors)


def test_convergence_valid_directions(self) -> None:
    """Convergence with valid directions passes."""
    for direction in ["minimize", "maximize"]:
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target=0,
                        direction=direction,
                    ),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0, f"Direction {direction} should be valid"


def test_convergence_interpolation_tolerance_skips_validation(self) -> None:
    """Interpolation string tolerance skips numeric validation."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="test",
                evaluate=EvaluateConfig(
                    type="convergence",
                    target=0,
                    tolerance="${context.tolerance}",  # interpolation string
                ),
                on_success="done",
                on_failure="done",
            ),
            "done": make_state(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
    assert len(error_list) == 0


def test_min_confidence_boundary_values(self) -> None:
    """min_confidence at boundaries (0 and 1) is valid."""
    for confidence in [0, 0.0, 1, 1.0]:
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        min_confidence=confidence,
                    ),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0, f"min_confidence={confidence} should be valid"


def test_min_confidence_negative(self) -> None:
    """Negative min_confidence is rejected."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="test",
                evaluate=EvaluateConfig(
                    type="llm_structured",
                    min_confidence=-0.1,
                ),
                on_success="done",
                on_failure="done",
            ),
            "done": make_state(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    assert any("between 0 and 1" in e.message for e in errors)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema.py::TestEvaluatorValidation -v`

---

### Phase 2: State Routing and Structure Validation

#### Overview
Add tests for routing validation and FSM structure edge cases.

#### Changes Required

**File**: `scripts/tests/test_fsm_schema.py`
**Changes**: Add tests to `TestFSMValidation` class

```python
def test_on_error_only_shorthand(self) -> None:
    """State with only on_error shorthand is valid."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="risky-operation",
                on_error="handle_error",
                next="done",  # fallback for success/failure
            ),
            "handle_error": make_state(action="log", next="done"),
            "done": make_state(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
    assert len(error_list) == 0


def test_next_only_transition_valid(self) -> None:
    """State with only 'next' transition is valid."""
    fsm = FSMLoop(
        name="test",
        initial="step1",
        states={
            "step1": StateConfig(action="echo 1", next="step2"),
            "step2": StateConfig(action="echo 2", next="done"),
            "done": make_state(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
    assert len(error_list) == 0


def test_terminal_only_state_valid(self) -> None:
    """Terminal state with no action is valid."""
    fsm = FSMLoop(
        name="test",
        initial="start",
        states={
            "start": make_state(action="test", on_success="end", on_failure="end"),
            "end": StateConfig(terminal=True),  # no action, no routing
        },
    )
    errors = validate_fsm(fsm)
    error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
    assert len(error_list) == 0


def test_self_reference_transition(self) -> None:
    """State referencing itself is valid (retry pattern)."""
    fsm = FSMLoop(
        name="test",
        initial="retry_state",
        states={
            "retry_state": StateConfig(
                action="might-fail",
                on_success="done",
                on_failure="retry_state",  # self-reference
            ),
            "done": make_state(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
    assert len(error_list) == 0


def test_circular_state_references(self) -> None:
    """Circular references without terminal produce error."""
    fsm = FSMLoop(
        name="test",
        initial="a",
        states={
            "a": StateConfig(action="step a", next="b"),
            "b": StateConfig(action="step b", next="c"),
            "c": StateConfig(action="step c", next="a"),  # circular
        },
    )
    errors = validate_fsm(fsm)
    # No terminal state error
    assert any("No terminal state defined" in e.message for e in errors)


def test_empty_states_dict(self) -> None:
    """Empty states dict produces errors."""
    fsm = FSMLoop(
        name="test",
        initial="start",
        states={},
    )
    errors = validate_fsm(fsm)
    # Initial state not found
    assert any("Initial state 'start' not found" in e.message for e in errors)
    # No terminal state
    assert any("No terminal state defined" in e.message for e in errors)


def test_multiple_terminal_states(self) -> None:
    """Multiple terminal states are valid."""
    fsm = FSMLoop(
        name="test",
        initial="check",
        states={
            "check": StateConfig(
                action="test",
                on_success="success_end",
                on_failure="failure_end",
            ),
            "success_end": StateConfig(terminal=True),
            "failure_end": StateConfig(terminal=True),
        },
    )
    errors = validate_fsm(fsm)
    error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
    assert len(error_list) == 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema.py::TestFSMValidation -v`

---

### Phase 3: load_and_validate Edge Cases

#### Overview
Add tests for YAML loading edge cases and warning behavior.

#### Changes Required

**File**: `scripts/tests/test_fsm_schema.py`
**Changes**: Add tests to `TestLoadAndValidate` class

```python
def test_invalid_yaml_syntax(self) -> None:
    """Invalid YAML syntax raises yaml.YAMLError."""
    yaml_content = """
name: test
initial: [unclosed bracket
states:
  done:
    terminal: true
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = Path(f.name)

    try:
        with pytest.raises(yaml.YAMLError):
            load_and_validate(path)
    finally:
        path.unlink()


def test_non_dict_yaml_root(self) -> None:
    """Non-dict YAML root raises ValueError."""
    yaml_content = "- item1\n- item2\n"  # list, not dict
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="must contain a YAML mapping"):
            load_and_validate(path)
    finally:
        path.unlink()


def test_warnings_logged_not_raised(self) -> None:
    """Warnings are logged but don't raise exceptions."""
    yaml_content = """
name: test-loop
initial: start
states:
  start:
    action: test
    on_success: done
    on_failure: done
  done:
    terminal: true
  orphan:
    action: unreachable
    next: done
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = Path(f.name)

    try:
        # Should not raise despite unreachable state warning
        fsm = load_and_validate(path)
        assert fsm.name == "test-loop"
        assert "orphan" in fsm.states
    finally:
        path.unlink()


def test_missing_name_field(self) -> None:
    """Missing 'name' field raises ValueError."""
    yaml_content = """
initial: start
states:
  start:
    terminal: true
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="missing required fields.*name"):
            load_and_validate(path)
    finally:
        path.unlink()


def test_missing_states_field(self) -> None:
    """Missing 'states' field raises ValueError."""
    yaml_content = """
name: test
initial: start
"""
    with tempfile.NamedTemporaryFile(mode="w", suffix=".yaml", delete=False) as f:
        f.write(yaml_content)
        path = Path(f.name)

    try:
        with pytest.raises(ValueError, match="missing required fields.*states"):
            load_and_validate(path)
    finally:
        path.unlink()
```

**Add import at top of file**:
```python
import yaml  # Add to existing imports
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema.py::TestLoadAndValidate -v`

---

### Phase 4: ValidationError and Severity Tests

#### Overview
Add tests for ValidationError formatting and severity handling.

#### Changes Required

**File**: `scripts/tests/test_fsm_schema.py`
**Changes**: Add tests to `TestValidationError` class

```python
def test_error_str_without_path(self) -> None:
    """String format without path."""
    error = ValidationError(
        message="General error",
        severity=ValidationSeverity.ERROR,
    )
    assert str(error) == "[ERROR] General error"


def test_warning_str_with_path(self) -> None:
    """Warning format includes path."""
    error = ValidationError(
        message="Potential issue",
        path="states.orphan",
        severity=ValidationSeverity.WARNING,
    )
    assert str(error) == "[WARNING] states.orphan: Potential issue"


def test_default_severity_is_error(self) -> None:
    """Default severity is ERROR."""
    error = ValidationError(message="Something wrong")
    assert error.severity == ValidationSeverity.ERROR


def test_severity_enum_values(self) -> None:
    """Severity enum has expected values."""
    assert ValidationSeverity.ERROR.value == "error"
    assert ValidationSeverity.WARNING.value == "warning"
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_schema.py::TestValidationError -v`

---

### Phase 5: Final Verification

#### Overview
Run full test suite and verify coverage.

#### Success Criteria

**Automated Verification**:
- [ ] All tests pass: `python -m pytest scripts/tests/test_fsm_schema.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_fsm_schema.py`
- [ ] Types pass: `python -m mypy scripts/tests/test_fsm_schema.py`
- [ ] Coverage >90%: `python -m pytest --cov=little_loops.fsm.validation --cov-report=term-missing scripts/tests/test_fsm_schema.py`

## Testing Strategy

### Unit Tests
- Each validation function tested via `validate_fsm()` integration
- Error messages tested with substring matching
- Both valid and invalid configurations tested

### Edge Cases
- Empty states dict
- Self-referential transitions
- Circular references
- Interpolation strings in numeric fields
- Boundary values for min_confidence

## References

- Original issue: `.issues/enhancements/P1-ENH-129-fsm-validation-test-coverage.md`
- Existing tests: `scripts/tests/test_fsm_schema.py:465-824`
- Module under test: `scripts/little_loops/fsm/validation.py:1-345`

# ENH-200: Error Message Format Inconsistency - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-200-error-message-format-inconsistency.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Research Findings

### Key Discoveries
- `scripts/little_loops/fsm/compilers.py` contains 4 paradigm validators with inconsistent error formats
- Convergence paradigm (lines 232-236) uses batch validation: `requires: field1, field2`
- Goal, Invariants, Imperative paradigms use individual validation: `requires 'field' field`
- Tests in `scripts/tests/test_fsm_compilers.py` validate these specific error message formats
- No programmatic parsing of error messages - only caught by CLI and displayed to users

### Current State

#### Goal Paradigm (`compilers.py:163-167`)
```python
if "goal" not in spec:
    raise ValueError("Goal paradigm requires 'goal' field")
if "tools" not in spec or not spec["tools"]:
    raise ValueError("Goal paradigm requires 'tools' field with at least one tool")
```

#### Convergence Paradigm (`compilers.py:232-236`)
```python
required = ["name", "check", "toward", "using"]
missing = [f for f in required if f not in spec]
if missing:
    raise ValueError(f"Convergence paradigm requires: {', '.join(missing)}")
```

#### Invariants Paradigm (`compilers.py:322-328`)
```python
if "name" not in spec:
    raise ValueError("Invariants paradigm requires 'name' field")
if "constraints" not in spec or not spec["constraints"]:
    raise ValueError("Invariants paradigm requires 'constraints' field with at least one constraint")
```

#### Imperative Paradigm (`compilers.py:421-429`)
```python
if "name" not in spec:
    raise ValueError("Imperative paradigm requires 'name' field")
if "steps" not in spec or not spec["steps"]:
    raise ValueError("Imperative paradigm requires 'steps' field with at least one step")
```

### Patterns to Follow
Based on codebase analysis, the **batch validation pattern** (Convergence) is superior because:
1. Lists all missing fields at once (better UX)
2. Used elsewhere in the codebase (`validation.py:315-337`)
3. Already has tests that use partial matching (`"Convergence paradigm requires"`)
4. More efficient - single validation pass

### Test Impact
- Goal tests: lines 151-167 - use exact match patterns
- Convergence tests: lines 301-343 - already use prefix matching
- Invariants tests: lines 458-504 - use exact match patterns
- Imperative tests: lines 625-663 - use exact match patterns

## Desired End State

All four paradigm validators will use the batch validation pattern:
```python
required = ["field1", "field2", ...]
missing = [f for f in required if f not in spec]
if missing:
    raise ValueError(f"{Paradigm} paradigm requires: {', '.join(missing)}")
```

For fields requiring additional validation (e.g., non-empty collections):
```python
if "field" in spec and not spec["field"]:
    raise ValueError(f"{Paradigm} paradigm 'field' requires at least one item")
```

### How to Verify
- Run tests: `python -m pytest scripts/tests/test_fsm_compilers.py -v`
- All existing tests pass with updated match patterns
- Error messages are consistent across all paradigms

## What We're NOT Doing
- **Not changing ValidationError** - The structured validation format in `validation.py` is separate and used differently
- **Not changing nested field validation** - Constraint/step level errors will keep their current format (they use index/name references)
- **Not changing CLI error handling** - The CLI catch block at `cli.py:702` will work the same
- **Not adding new functionality** - This is purely a formatting consistency change

## Solution Approach

Standardize all paradigm validators to use the **batch validation pattern**:
1. Collect all required field names in a list
2. Find missing fields
3. Raise single ValueError listing all missing fields together
4. For collection fields requiring non-empty check, use separate validation

This provides:
- Better user experience (see all missing fields at once)
- Consistent error format across paradigms
- More efficient validation (single pass)

## Implementation Phases

### Phase 1: Update Goal Paradigm Validator

**File**: `scripts/little_loops/fsm/compilers.py`
**Lines**: 163-167

**Changes**:
```python
# Current code (lines 163-167):
if "goal" not in spec:
    raise ValueError("Goal paradigm requires 'goal' field")
if "tools" not in spec or not spec["tools"]:
    raise ValueError("Goal paradigm requires 'tools' field with at least one tool")

# New code:
required = ["goal", "tools"]
missing = [f for f in required if f not in spec]
if missing:
    raise ValueError(f"Goal paradigm requires: {', '.join(missing)}")

if "tools" in spec and not spec["tools"]:
    raise ValueError("Goal paradigm 'tools' requires at least one tool")
```

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_compilers.py::TestGoalCompiler -v`
- [ ] Error message format matches convergence pattern

### Phase 2: Update Invariants Paradigm Validator

**File**: `scripts/little_loops/fsm/compilers.py`
**Lines**: 322-328

**Changes**:
```python
# Current code (lines 322-328):
if "name" not in spec:
    raise ValueError("Invariants paradigm requires 'name' field")
if "constraints" not in spec or not spec["constraints"]:
    raise ValueError(
        "Invariants paradigm requires 'constraints' field with at least one constraint"
    )

# New code:
required = ["name", "constraints"]
missing = [f for f in required if f not in spec]
if missing:
    raise ValueError(f"Invariants paradigm requires: {', '.join(missing)}")

if "constraints" in spec and not spec["constraints"]:
    raise ValueError("Invariants paradigm 'constraints' requires at least one constraint")
```

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_compilers.py::TestInvariantsCompiler -v`
- [ ] Error message format matches convergence pattern

### Phase 3: Update Imperative Paradigm Validator

**File**: `scripts/little_loops/fsm/compilers.py`
**Lines**: 421-427

**Changes**:
```python
# Current code (lines 421-427):
if "name" not in spec:
    raise ValueError("Imperative paradigm requires 'name' field")
if "steps" not in spec or not spec["steps"]:
    raise ValueError("Imperative paradigm requires 'steps' field with at least one step")
if "until" not in spec:
    raise ValueError("Imperative paradigm requires 'until' field")

# New code:
required = ["name", "steps", "until"]
missing = [f for f in required if f not in spec]
if missing:
    raise ValueError(f"Imperative paradigm requires: {', '.join(missing)}")

if "steps" in spec and not spec["steps"]:
    raise ValueError("Imperative paradigm 'steps' requires at least one step")
```

**Success Criteria**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_compilers.py::TestImperativeCompiler -v`
- [ ] Error message format matches convergence pattern

### Phase 4: Update Tests

**File**: `scripts/tests/test_fsm_compilers.py`

**Goal paradigm tests** (lines 151-167):
- Change match patterns from `"requires 'field' field"` to `"Goal paradigm requires"`
- Update test for empty tools to match new format

**Invariants paradigm tests** (lines 458-504):
- Change top-level validation match patterns to use prefix matching: `"Invariants paradigm requires"`
- Keep constraint-level tests unchanged (they use nested validation)

**Imperative paradigm tests** (lines 625-663):
- Change match patterns from `"requires 'field' field"` to `"Imperative paradigm requires"`
- Update test for empty steps to match new format
- Keep nested 'until.check' validation test unchanged

**Success Criteria**:
- [ ] All compiler tests pass: `python -m pytest scripts/tests/test_fsm_compilers.py -v`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`

## Testing Strategy

### Unit Tests
- Update existing tests to use prefix matching for batch error messages
- Verify all missing field scenarios are tested
- Verify empty collection scenarios are tested

### Integration Tests
- CLI tests in `test_cli.py` should continue to work (they catch ValueError generically)
- ll-loop tests in `test_ll_loop.py` should continue to work

## References

- Original issue: `.issues/enhancements/P4-ENH-200-error-message-format-inconsistency.md`
- Main file: `scripts/little_loops/fsm/compilers.py:163-429`
- Test file: `scripts/tests/test_fsm_compilers.py`
- Pattern reference: `scripts/little_loops/fsm/compilers.py:232-236` (convergence - current best practice)
- Validation pattern: `scripts/little_loops/fsm/validation.py:315-337` (FSM file validation uses similar pattern)

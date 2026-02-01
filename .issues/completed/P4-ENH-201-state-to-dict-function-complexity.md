# _state_to_dict Helper Function Has Repetitive Conditional Logic

## Type
ENH

## Priority
P4

## Status
OPEN

## Description

The `_state_to_dict` function in `cli.py` (lines 800-839) has repetitive conditional logic for serializing optional fields. Each field requires an `if` statement to check if it's not None before adding to the result dict.

**Current implementation:**
```python
def _state_to_dict(state) -> dict:
    d: dict = {}
    if state.action:
        d["action"] = state.action
    if state.evaluate:
        d["evaluate"] = {"type": state.evaluate.type}
        if state.evaluate.target is not None:
            d["evaluate"]["target"] = state.evaluate.target
        if state.evaluate.tolerance is not None:
            d["evaluate"]["tolerance"] = state.evaluate.tolerance
        # ... 5 more if statements
    if state.on_success:
        d["on_success"] = state.on_success
    # ... 8 more if statements
    return d
```

**Evidence:**
- `scripts/little_loops/cli.py:800-839` - 40 lines of repetitive conditionals

**Anchor:** `_state_to_dict` (function name)

**Impact:**
Code maintainability (minor). The function is harder to read and modify. Adding new fields requires adding more `if` statements.

**Note:**
The `StateConfig.to_dict()` method already exists (fsm/schema.py:203-232) and does the same thing more cleanly. The `_state_to_dict` function in cli.py duplicates this logic with nested handling for the `evaluate` field. The `EvaluateConfig.to_dict()` method (fsm/schema.py:76-108) already handles the optional evaluate fields properly.

## Files Affected
- `scripts/little_loops/cli.py`

## Recommendation

**Option 1: Simply use StateConfig.to_dict() directly (Recommended)**
Since `StateConfig.to_dict()` (fsm/schema.py:203-232) already handles all the optional fields correctly and `EvaluateConfig.to_dict()` (fsm/schema.py:76-108) handles the nested evaluate fields, the `_state_to_dict` function in cli.py can simply call `state.to_dict()` directly. The `StateConfig.to_dict()` method already:
- Handles all the conditional checks
- Properly serializes nested `evaluate` via `self.evaluate.to_dict()`
- Serializes `route` via `self.route.to_dict()`

**Option 2: Remove _state_to_dict entirely and inline the to_dict() call**
The function is a thin wrapper that duplicates existing logic. Consider removing it and calling `state.to_dict()` directly wherever `_state_to_dict` is used.

**Option 3: Keep as-is**
The function works correctly and is only used in one place (compile output).

## Related Issues
None

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-01
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli.py`: Removed `_state_to_dict()` function (40 lines) and updated call site at line 782 to use `state.to_dict()` directly
- `scripts/tests/test_ll_loop.py`: Removed duplicate `_state_to_dict()` method from `TestStateToDict` class and updated all test methods to use `state.to_dict()` directly

### Verification Results
- Tests: PASS (16/16 TestStateToDict tests, 15/15 compile-related tests)
- Lint: PASS
- Types: PASS

### Additional Benefits
- Now includes `action_type` field in compiled output (was previously missing)
- Now includes additional `evaluate` fields like `negate`, `prompt`, `schema`, `min_confidence`, `uncertain_suffix`, `source`, `direction`
- Now includes `route._error` key for error routing
- Reduced code duplication - the canonical `StateConfig.to_dict()` is now the single source of truth

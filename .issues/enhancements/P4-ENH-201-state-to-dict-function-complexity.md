# _state_to_dict Helper Function Has Repetitive Conditional Logic

## Type
ENH

## Priority
P4

## Status
OPEN

## Description

The `_state_to_dict` function in `cli.py` (lines 851-890) has repetitive conditional logic for serializing optional fields. Each field requires an `if` statement to check if it's not None before adding to the result dict.

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
        # ... 7 more if statements
    if state.on_success:
        d["on_success"] = state.on_success
    # ... 9 more if statements
    return d
```

**Evidence:**
- `scripts/little_loops/cli.py:851-890` - 40 lines of repetitive conditionals

**Impact:**
Code maintainability (minor). The function is harder to read and modify. Adding new fields requires adding more `if` statements.

**Note:**
The `StateConfig.to_dict()` method already exists (schema.py:200-229) and does the same thing more cleanly. The `_state_to_dict` function in cli.py duplicates this logic with nested handling for the `evaluate` field.

## Files Affected
- `scripts/little_loops/cli.py`

## Recommendation

**Option 1: Use StateConfig.to_dict() with evaluate handling (Recommended)**
```python
def _state_to_dict(state) -> dict:
    d = state.to_dict()
    # Flatten evaluate if needed for YAML output
    if state.evaluate:
        d["evaluate"] = {"type": state.evaluate.type}
        # Add non-None fields
        for field in ["target", "tolerance", "previous", "operator", "pattern", "path"]:
            value = getattr(state.evaluate, field, None)
            if value is not None:
                d["evaluate"][field] = value
    return d
```

**Option 2: Add a helper for optional field adding**
```python
def _add_if_not_none(d: dict, key: str, value: Any) -> None:
    if value is not None:
        d[key] = value
```

**Option 3: Keep as-is**
The function works correctly and is only used in one place (compile output).

## Related Issues
None

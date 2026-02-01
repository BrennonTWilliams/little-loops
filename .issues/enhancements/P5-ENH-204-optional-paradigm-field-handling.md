# Paradigm Field is Optional in Schema but Assumed in Command

## Type
ENH

## Priority
P5

## Status
OPEN

## Description

The `paradigm` field in `FSMLoop` schema is optional (`str | None = None`), but the `/ll:create_loop` command assumes every loop will have a paradigm.

**Schema definition (schema.py:354):**
```python
paradigm: str | None = None
```

**Command documentation:**
- Every template and paradigm example includes a `paradigm` field
- No examples of FSM files without a paradigm field

**Use case for `paradigm: None`:**
- Hand-written FSM YAML files
- Pre-compiled FSM files (`.fsm.yaml`)
- Cases where the source paradigm is not relevant

**Evidence:**
- `scripts/little_loops/fsm/schema.py:354`
- `commands/create_loop.md` - All examples include `paradigm`

**Impact:**
Extremely minor. The `/ll:create_loop` command always sets the paradigm field (correctly). Hand-authored FSM files can omit it. The executor doesn't require it.

## Files Affected
- `scripts/little_loops/fsm/schema.py`
- `commands/create_loop.md`

## Recommendation
No action needed. This is working as intended:
- `/ll:create_loop` always sets paradigm (correct for its use case)
- Schema allows None for hand-authored files (correct flexibility)
- Executor works with or without it

## Related Issues
None

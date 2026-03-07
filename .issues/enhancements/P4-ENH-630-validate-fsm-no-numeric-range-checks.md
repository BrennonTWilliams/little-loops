---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# ENH-630: `validate_fsm` has no range checks for `max_iterations`, `backoff`, or `timeout` numeric fields

## Summary

`validate_fsm()` checks structural concerns (unreachable states, missing routing, required evaluator fields) but performs no validation of FSM-level numeric field values. `max_iterations=0`, `backoff=-5.0`, and `timeout=0` are all accepted without warning. The related BUG-602 covers the `max_iterations=0` runtime behavior; this issue covers adding validation to `validate_fsm` to catch these at load time.

## Location

- **File**: `scripts/little_loops/fsm/validation.py`
- **Line(s)**: 190–261 (at scan commit: 12a6af0)
- **Anchor**: `in function validate_fsm()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/validation.py#L190-L261)
- **Code**:
```python
def validate_fsm(fsm: FSMLoop) -> list[str]:
    errors: list[str] = []
    # Checks: initial state, terminal states, state references, evaluator fields
    # No checks for: max_iterations > 0, backoff >= 0, timeout > 0
    ...
```

## Current Behavior

Invalid numeric values pass validation silently:
- `max_iterations: 0` — loop exits immediately (BUG-602)
- `backoff: -5` — negative sleep, likely raises `time.sleep(-5)` ValueError at runtime
- `timeout: 0` — loop times out immediately on first state entry

## Expected Behavior

`validate_fsm()` should emit validation errors for:
- `max_iterations <= 0`
- `backoff < 0` (negative sleep duration)
- `timeout <= 0`
- `LLMConfig.max_tokens <= 0`
- `LLMConfig.timeout <= 0`

## Motivation

Catching these at load time (before execution begins) gives users a clear error message pointing to the misconfiguration. Runtime errors for these cases are confusing — `time.sleep(-5)` is a `ValueError`, `timeout=0` appears as an immediate `"timed_out"` status.

## Proposed Solution

```python
# In validate_fsm(), after existing structural checks:
if fsm.max_iterations is not None and fsm.max_iterations <= 0:
    errors.append(f"max_iterations must be > 0, got {fsm.max_iterations}")
if fsm.backoff is not None and fsm.backoff < 0:
    errors.append(f"backoff must be >= 0, got {fsm.backoff}")
if fsm.timeout is not None and fsm.timeout <= 0:
    errors.append(f"timeout must be > 0, got {fsm.timeout}")
```

## Scope Boundaries

- Only `validate_fsm()` changes; no runtime behavior changes
- Schema types remain the same (validation is a check, not a type constraint)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — `validate_fsm()`

### Tests
- `scripts/tests/test_fsm_validation.py` — add tests for each new validation rule

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add numeric range checks at end of `validate_fsm()`
2. Add tests for each: `max_iterations=0`, `backoff=-1`, `timeout=0`

## Impact

- **Priority**: P4 — Improves developer experience; prevents confusing runtime errors from misconfiguration
- **Effort**: Small — Straightforward additions to `validate_fsm()`
- **Risk**: Low — Purely additive validation; no existing valid configs are rejected
- **Breaking Change**: No (configs with 0/negative values were already broken at runtime)

## Labels

`enhancement`, `fsm`, `validation`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P4

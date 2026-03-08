---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
---

# ENH-626: Identical operator dispatch dict defined twice in `evaluate_output_numeric` and `_compare_values`

## Summary

The same 6-key operator dispatch dict (`{"eq": ..., "ne": ..., "lt": ..., "le": ..., "gt": ..., "ge": ...}`) is defined verbatim inside both `evaluate_output_numeric()` and `_compare_values()` in `evaluators.py`. Adding a new operator requires updating both functions independently, and the two copies can silently diverge.

## Location

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Line(s)**: 127–134 and 194–201 (at scan commit: 12a6af0)
- **Anchor**: `in function evaluate_output_numeric()` and `in function _compare_values()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/evaluators.py#L127-L134)
- **Code**:
```python
# In evaluate_output_numeric (lines 127-134):
operators = {
    "eq": lambda v, t: v == t,
    "ne": lambda v, t: v != t,
    "lt": lambda v, t: v < t,
    "le": lambda v, t: v <= t,
    "gt": lambda v, t: v > t,
    "ge": lambda v, t: v >= t,
}
# Identical dict again in _compare_values (lines 194-201)
```

## Current Behavior

Both functions define and use their own copy of the operators dict. An operator added to one function would need to be mirrored in the other manually.

## Expected Behavior

A single module-level `NUMERIC_OPERATORS` dict is defined once and referenced by both functions.

## Motivation

Code duplication here is a maintenance hazard. The `evaluators.py` module is the sole location for evaluation logic, and keeping operator definitions centralized makes it easy to add operators (e.g., `"contains"`, `"startswith"`) in a single place.

## Success Metrics

- Operator dict definitions in `evaluators.py`: 2 → 1 (module-level `_NUMERIC_OPERATORS` constant)
- Lines of duplicate code eliminated: ~14 lines
- All existing tests in `test_fsm_evaluators.py` pass unchanged (no behavior change)

## Acceptance Criteria

- [ ] `_NUMERIC_OPERATORS` module-level constant defined once in `evaluators.py`
- [ ] `evaluate_output_numeric()` references `_NUMERIC_OPERATORS` instead of defining its own dict
- [ ] `_compare_values()` references `_NUMERIC_OPERATORS` instead of defining its own dict
- [ ] All existing tests in `scripts/tests/test_fsm_evaluators.py` pass without modification

## Proposed Solution

```python
# Module-level constant
_NUMERIC_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "eq": lambda v, t: v == t,
    "ne": lambda v, t: v != t,
    "lt": lambda v, t: v < t,
    "le": lambda v, t: v <= t,
    "gt": lambda v, t: v > t,
    "ge": lambda v, t: v >= t,
}

# Both functions reference _NUMERIC_OPERATORS instead of defining their own
```

## Scope Boundaries

- Only `evaluators.py` needs to change
- No interface or behavior changes; pure refactor

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — extract `_NUMERIC_OPERATORS` constant; update `evaluate_output_numeric()` and `_compare_values()`

### Tests
- `scripts/tests/test_fsm_evaluators.py` — existing tests cover behavior; no new tests needed

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Extract module-level `_NUMERIC_OPERATORS` dict in `evaluators.py`
2. Replace inline dict in `evaluate_output_numeric()` and `_compare_values()` with references to `_NUMERIC_OPERATORS`

## Impact

- **Priority**: P4 — Maintenance improvement; no user-visible impact
- **Effort**: Small — Pure refactor of ~15 lines
- **Risk**: Low — No behavior change; only affects internal structure
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `evaluator`, `refactor`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5ca2eb1f-9d78-4680-b741-5613ecbf49b3.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d11c154b-ec01-40ba-bc51-c1eb3dd6ae2f.jsonl` — Supersedes ENH-539 (closed as duplicate)
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cb0f358f-581f-41c1-aedf-c51ecbc7de35.jsonl` — VALID: duplicate `operators` dicts confirmed at `evaluators.py:127` and `:194`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ffa5dd0-e20c-4a43-a802-b64281d1b1d9.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P4

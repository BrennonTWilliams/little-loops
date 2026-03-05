---
discovered_commit: 47c81c895baaac1acac69d105ed75ff1ec82ed2c
discovered_branch: main
discovered_date: 2026-03-03T21:56:26Z
discovered_by: scan-codebase
---

# ENH-539: Duplicate `operators` Dict in `evaluators.py` — Should Be Module-Level Constant

## Summary

The same six-entry `operators` dict (`"eq"`, `"ne"`, `"lt"`, `"le"`, `"gt"`, `"ge"` → lambda comparisons) is constructed verbatim inside both `evaluate_output_numeric()` and `_compare_values()`. Every call to either function recreates the dict. This is a straightforward refactor to a module-level constant.

## Location

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Line(s)**: 137–144 and 204–211 (at scan commit: 47c81c8)
- **Anchor**: `in function evaluate_output_numeric()` and `in function _compare_values()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/47c81c895baaac1acac69d105ed75ff1ec82ed2c/scripts/little_loops/fsm/evaluators.py#L137-L144)
- **Code**:
```python
# evaluate_output_numeric (lines 137-144):
operators = {
    "eq": lambda v, t: v == t,
    "ne": lambda v, t: v != t,
    "lt": lambda v, t: v < t,
    "le": lambda v, t: v <= t,
    "gt": lambda v, t: v > t,
    "ge": lambda v, t: v >= t,
}

# _compare_values (lines 204-211): identical dict
operators = { ... }  # byte-for-byte same
```

## Current Behavior

Two identical dicts with six lambda functions are constructed on every call to `evaluate_output_numeric` and `_compare_values`.

## Expected Behavior

A single `_COMPARISON_OPERATORS: dict[str, Callable[[float, float], bool]]` constant is defined once at module level and referenced by both functions.

## Motivation

Minor code quality issue: duplication means any change to operator behavior (e.g., adding `"approximately"`) requires updating two places. The performance impact is negligible for most use cases but the clarity improvement is free.

## Proposed Solution

```python
# At module level (~line 88, before evaluate_exit_code):
from typing import Callable

_COMPARISON_OPERATORS: dict[str, Callable[[float, float], bool]] = {
    "eq": lambda v, t: v == t,
    "ne": lambda v, t: v != t,
    "lt": lambda v, t: v < t,
    "le": lambda v, t: v <= t,
    "gt": lambda v, t: v > t,
    "ge": lambda v, t: v >= t,
}

# In evaluate_output_numeric and _compare_values:
operators = _COMPARISON_OPERATORS  # or just reference directly
```

## Scope Boundaries

- Only `evaluators.py`; no other files
- Does not change operator behavior or add new operators
- Both functions still independently validate the `operator` parameter

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — extract `_COMPARISON_OPERATORS` constant, update both functions

### Dependent Files (Callers/Importers)
- N/A — internal implementation detail

### Similar Patterns
- N/A

### Tests
- Existing evaluator tests cover this path; no new tests needed

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Define `_COMPARISON_OPERATORS` dict at module level in `evaluators.py`
2. Replace local `operators = {...}` in `evaluate_output_numeric` and `_compare_values` with references to `_COMPARISON_OPERATORS`
3. Confirm existing tests pass

## Impact

- **Priority**: P4 — Minor code quality; negligible performance gain
- **Effort**: Small — 5-minute refactor
- **Risk**: Low — Pure refactor; behavior identical
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `docs/generalized-fsm-loop.md` | Evaluator types — numeric comparisons (line 545) |

## Labels

`enhancement`, `ll-loop`, `refactor`, `scan-codebase`

## Session Log

- `/ll:scan-codebase` — 2026-03-03T21:56:26Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e92cdbc5-332d-41d2-89ed-2d48dd0a91ec.jsonl`
- `/ll:refine-issue` — 2026-03-03T23:10:00Z — `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c3cb1f4-f971-445f-9de1-5971204cbe4e.jsonl` — Linked `docs/generalized-fsm-loop.md`; noted duplicate at `evaluators.py:137` and `:204`
- `/ll:format-issue` - 2026-03-03 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c342da13-af7c-45e2-907d-7258a66682e8.jsonl`
- `/ll:map-dependencies` - 2026-03-05T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b2d766fe-2cc3-467b-a046-6a331a5941d9.jsonl` — Added Blocks FEAT-543 (docs overlap, auto)

## Blocks

- FEAT-543 — `docs/generalized-fsm-loop.md` overlap (higher priority; complete first)

---

**Open** | Created: 2026-03-03 | Priority: P4

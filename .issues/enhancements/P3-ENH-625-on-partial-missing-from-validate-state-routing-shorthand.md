---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 93
---

# ENH-625: `on_partial` missing from `_validate_state_routing` shorthand check — valid routing rejected

## Summary

`_validate_state_routing()` in `validation.py` checks whether a state has at least one routing path defined. It tests for `on_success`, `on_failure`, `on_error`, `route`, `next`, and `terminal`. It does not test for `on_partial`. A state that has *only* `on_partial` set (no other routing) is incorrectly flagged with "State has no transition defined" even though `on_partial` is a valid routing path handled by the executor.

## Location

- **File**: `scripts/little_loops/fsm/validation.py`
- **Line(s)**: 158–186 (at scan commit: 12a6af0)
- **Anchor**: `in function _validate_state_routing()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/validation.py#L158-L186)
- **Code**:
```python
has_shorthand = (
    state.on_success is not None or state.on_failure is not None or state.on_error is not None
)
# on_partial is not included in has_shorthand
```

## Current Behavior

A state with only `on_partial: some_state` set fails validation with "State `<name>` has no transition defined", even though the executor handles `"partial"` verdicts via `_route()`. Any loop YAML that uses `on_partial` as the sole routing for a state cannot be validated successfully.

## Expected Behavior

`on_partial` should be recognized as a valid routing indicator alongside `on_success`, `on_failure`, and `on_error`.

## Motivation

The `on_partial` verdict is a first-class routing type supported by both the executor (`FSMExecutor._route()`) and the `llm_structured` evaluator schema (which includes `"partial"` as a valid verdict). Excluding it from the validation check is a gap that prevents valid loop configurations from passing validation.

## Proposed Solution

Add `on_partial` to the `has_shorthand` check:

```python
has_shorthand = (
    state.on_success is not None
    or state.on_failure is not None
    or state.on_error is not None
    or state.on_partial is not None   # add this
)
```

## Scope Boundaries

- Only the `_validate_state_routing` shorthand check needs updating
- No changes to executor routing logic or schema definitions

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/validation.py` — `_validate_state_routing()`

### Tests
- `scripts/tests/test_fsm_validation.py` — add test: state with only `on_partial` should pass routing validation

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Add `or state.on_partial is not None` to `has_shorthand` in `_validate_state_routing()`
2. Add test verifying a state with only `on_partial` passes validation

## Impact

- **Priority**: P3 — Any user trying to use `on_partial` routing in a raw FSM YAML will hit a false validation error; blocks legitimate use of a documented feature
- **Effort**: Small — One-line fix plus one test
- **Risk**: Low — Purely additive; only relaxes an overly strict check
- **Breaking Change**: No

## Labels

`enhancement`, `fsm`, `validation`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f5f06f0-0429-44e7-9663-02fef909f58e.jsonl`
- `/ll:verify-issues` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d11c154b-ec01-40ba-bc51-c1eb3dd6ae2f.jsonl` — Added `## Blocks: FEAT-634` backlink (was missing)
- `/ll:ready-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`

## Blocks

- FEAT-634 (paradigm compiler `on_partial` routing — prerequisite: ENH-625 must be merged first)

## Resolution

Added `or state.on_partial is not None` to the `has_shorthand` check in `_validate_state_routing()`. Added test `test_on_partial_only_shorthand_is_valid` to `test_fsm_schema.py`. All 3374 tests pass.

### Changes
- `scripts/little_loops/fsm/validation.py` — `has_shorthand` now includes `on_partial`
- `scripts/tests/test_fsm_schema.py` — new test verifying `on_partial`-only state passes routing validation

## Session Log
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

## Status

**Completed** | Created: 2026-03-07 | Priority: P3

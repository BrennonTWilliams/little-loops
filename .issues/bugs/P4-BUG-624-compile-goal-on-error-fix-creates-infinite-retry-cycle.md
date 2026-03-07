---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
---

# BUG-624: `compile_goal` hard-codes `on_error="fix"` creating infinite retry cycle on evaluator errors

## Summary

The `goal` paradigm compiler hard-codes `on_error="fix"` for the `evaluate` state. When the evaluator itself returns an `"error"` verdict (e.g., the `claude` CLI is unavailable, an LLM call times out, or the structured output is malformed), the FSM routes to `"fix"` and back to `"evaluate"` indefinitely. The loop cycles until `max_iterations` is reached rather than terminating immediately on a persistent infrastructure failure.

## Location

- **File**: `scripts/little_loops/fsm/compilers.py`
- **Line(s)**: 224–238 (at scan commit: 12a6af0)
- **Anchor**: `in function compile_goal()`
- **Permalink**: [View on GitHub](https://github.com/BrennonTWilliams/little-loops/blob/12a6af03c58a3b8f355e265a895b3950db89b66c/scripts/little_loops/fsm/compilers.py#L224-L238)
- **Code**:
```python
"evaluate": StateConfig(
    action=check_action,
    action_type=check_type,
    evaluate=evaluate_config,
    on_success="done",
    on_failure="fix",
    on_error="fix",   # hard-coded — routes evaluator errors to "fix"
),
```

## Current Behavior

When a `goal`-paradigm loop's `evaluate` state encounters an evaluator error (verdict `"error"`, not `"failure"`), the FSM routes to `"fix"` and then back to `"evaluate"`. This repeats for every remaining iteration. The loop logs many `evaluate→fix→evaluate` cycles before eventually stopping at `max_iterations`.

## Expected Behavior

Evaluator-level errors (infrastructure failures: LLM unavailable, malformed API response) should terminate the loop immediately with `terminated_by="error"` rather than cycling through `"fix"` states that cannot address them. Action-level failures (the code being evaluated is wrong) should continue routing to `"fix"` as intended.

## Steps to Reproduce

1. Create a `goal`-paradigm loop with `evaluate_type: llm_structured`.
2. Run it while the `claude` CLI is unavailable or returns a non-JSON response.
3. Observe: the loop cycles evaluate→fix→evaluate until `max_iterations` is exhausted.

## Root Cause

- **File**: `scripts/little_loops/fsm/compilers.py`
- **Anchor**: `in function compile_goal()`
- **Cause**: `on_error` routes to `"fix"` treating evaluator errors (LLM/infra failures) the same as action failures, which is incorrect.

## Proposed Solution

Either remove `on_error` from the compiled `evaluate` state (causing `_route()` to return `None` and terminate with `_finish("error")`), or add a dedicated terminal error state:

```python
# Option A: let on_error fall through to FSM error termination
"evaluate": StateConfig(
    action=check_action,
    action_type=check_type,
    evaluate=evaluate_config,
    on_success="done",
    on_failure="fix",
    # on_error omitted — evaluator errors terminate the loop
),

# Option B: route to explicit error terminal state
states["error"] = StateConfig(terminal=True)
# and set on_error="error" in evaluate state
```

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/compilers.py` — `compile_goal()`

### Similar Patterns
- `scripts/little_loops/fsm/compilers.py` — `compile_invariants()` does not set `on_error` (different behavior); `compile_convergence()` also lacks `on_error`

### Tests
- `scripts/tests/test_fsm_compilers.py` — add test verifying `evaluate` state has no `on_error` (or routes to terminal)

### Documentation
- N/A

## Implementation Steps

1. Remove `on_error="fix"` from the compiled `evaluate` state in `compile_goal()`
2. Verify existing tests pass (the fix state exists for action failures, not evaluator errors)
3. Add test for evaluator-error termination behavior

## Impact

- **Priority**: P4 — Affects goal-paradigm loops using LLM evaluation when infrastructure fails; burns unnecessary iterations
- **Effort**: Small — Remove one line from `compile_goal()`
- **Risk**: Low — Change only affects the evaluator-error path; action failure still routes to fix correctly
- **Breaking Change**: No (changes behavior of previously misconfigured error path)

## Labels

`bug`, `fsm`, `compiler`, `loop`, `captured`

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`

---

**Open** | Created: 2026-03-07 | Priority: P4

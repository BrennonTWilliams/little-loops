---
discovered_commit: 12a6af03c58a3b8f355e265a895b3950db89b66c
discovered_branch: main
discovered_date: 2026-03-07T05:53:04Z
discovered_by: scan-codebase
confidence_score: 100
outcome_confidence: 100
status: done
completed_at: 2026-03-07T00:00:00Z
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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Termination mechanism when `on_error` is absent** (`executor.py:725-734`, `run():462`):
- `_route()` checks `on_success`, `on_failure`, `on_error` in order; each is skipped if `None`
- When `on_error is None` and verdict is `"error"`, `_route()` falls through and returns `None`
- Back in `run()`, `next_state is None` triggers `_finish("error", error="No valid transition")` at `executor.py:462`
- This is the desired termination — all other compilers (`compile_invariants`, `compile_convergence`, `compile_imperative`) omit `on_error` and rely on this same fall-through path

**Evaluator error sources** (`evaluators.py`):
- `evaluate_exit_code`: exit code ≥ 2 → `"error"` verdict (`evaluators.py:95-96`)
- `evaluate_output_numeric`: non-numeric output string → `"error"` verdict (`evaluators.py:122-125`)
- `evaluate_llm_structured`: LLM API/subprocess failure, non-JSON response → `"error"` verdict (`evaluators.py:434-437`)

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

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/compilers.py:110` — dispatch table maps `paradigm: goal` to `compile_goal`; no caller changes needed

### Similar Patterns
- `scripts/little_loops/fsm/compilers.py` — `compile_invariants()` does not set `on_error` (different behavior); `compile_convergence()` also lacks `on_error`

### Tests
- `scripts/tests/test_fsm_compilers.py` — add test verifying `evaluate` state has no `on_error` (or routes to terminal)
- `scripts/tests/test_fsm_compiler_properties.py` — property tests for `compile_goal`; verify evaluator-error path

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Reference files (read-only — no changes needed):**
- `scripts/little_loops/fsm/executor.py:691-734` — `_route()` — confirms `on_error=None` falls through to `None` return
- `scripts/little_loops/fsm/executor.py:447-462` — `run()` — `next_state is None` triggers `_finish("error", error="No valid transition")`
- `scripts/little_loops/fsm/schema.py:168-292` — `StateConfig` — `on_error: str | None = None` (default `None`)

**Test files to add cases to:**
- `scripts/tests/test_fsm_compilers.py` — `TestGoalCompiler` class; follow `test_goal_without_evaluator` at `:943-954` for asserting `is None`
- `scripts/tests/test_fsm_compiler_properties.py` — `TestGoalCompilerProperties`; follow `@given(spec=goal_spec())` pattern at `:171-227`

## Implementation Steps

1. Remove `on_error="fix"` from the compiled `evaluate` state in `compile_goal()`
2. Verify existing tests pass (the fix state exists for action failures, not evaluator errors)
3. Add test for evaluator-error termination behavior

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Step 1 — exact change** (`compilers.py:231`):
Remove the line `on_error="fix",` from the `evaluate` `StateConfig` in `compile_goal()`.

**Step 3 — unit test to add** in `test_fsm_compilers.py` (`TestGoalCompiler` class):
```python
def test_evaluate_state_has_no_on_error(self) -> None:
    """compile_goal evaluate state must not route evaluator errors to fix."""
    spec = {
        "paradigm": "goal",
        "goal": "No type errors",
        "tools": ["/ll:check-code types", "/ll:manage-issue bug fix"],
    }
    fsm = compile_goal(spec)
    assert fsm.states["evaluate"].on_error is None
```
Follows pattern at `test_fsm_compilers.py:943-954` (`test_goal_without_evaluator`).

**Step 3b — property test to add** in `test_fsm_compiler_properties.py` (`TestGoalCompilerProperties`):
```python
@given(spec=goal_spec())
@settings(max_examples=100)
def test_evaluate_state_has_no_on_error(self, spec: dict) -> None:
    """evaluate on_error must be None for all valid goal specs."""
    fsm = compile_goal(spec)
    assert fsm.states["evaluate"].on_error is None
```
Follows pattern at `test_fsm_compiler_properties.py:171-227`.

**Step 4 — run tests**:
```bash
python -m pytest scripts/tests/test_fsm_compilers.py scripts/tests/test_fsm_compiler_properties.py -v
```

## Impact

- **Priority**: P4 — Affects goal-paradigm loops using LLM evaluation when infrastructure fails; burns unnecessary iterations
- **Effort**: Small — Remove one line from `compile_goal()`
- **Risk**: Low — Change only affects the evaluator-error path; action failure still routes to fix correctly
- **Breaking Change**: No (changes behavior of previously misconfigured error path)

## Labels

`bug`, `fsm`, `compiler`, `loop`, `captured`

## Resolution

- **Status**: Completed
- **Resolved**: 2026-03-07
- **Fix**: Removed `on_error="fix"` from the `evaluate` `StateConfig` in `compile_goal()` (`compilers.py:231`). Evaluator errors now fall through `_route()` returning `None`, which triggers `_finish("error", error="No valid transition")` — matching the behavior of all other compilers.
- **Tests added**:
  - `test_fsm_compilers.py`: `TestGoalCompiler.test_evaluate_state_has_no_on_error`
  - `test_fsm_compiler_properties.py`: `TestGoalCompilerProperties.test_evaluate_state_has_no_on_error`
- **Verification**: 115 tests pass

## Session Log
- `/ll:scan-codebase` - 2026-03-07T05:53:04Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8d7aaeac-a482-4a78-9f78-be55d16b7093.jsonl`
- `/ll:format-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e777632e-41b7-40d4-b52b-e02d2120c1b8.jsonl`
- `/ll:refine-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffe8067e-0faf-4a13-97c6-c7842f173890.jsonl`
- `/ll:confidence-check` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ec3f4ee6-18fd-456e-b792-d7cd8e7e7944.jsonl`
- `/ll:manage-issue` - 2026-03-07T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current.jsonl`

---

**Completed** | Created: 2026-03-07 | Priority: P4

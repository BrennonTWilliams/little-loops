---
discovered_date: 2026-03-15
discovered_by: analyze-loop
source_loop: sprint-build-and-validate
source_state: route_validation
---

# BUG-760: route_validation evaluate prompt has uninterpolated ${context.*} variables

## Summary

The `route_validation` state in the `sprint-build-and-validate` loop uses an `llm_structured` evaluate whose `prompt` field contains `${context.readiness_threshold}` and `${context.outcome_threshold}`. These template variables are not substituted before the prompt is sent to the LLM — the model receives the literal strings instead of the configured values `85` and `70`. As a result, the LLM cannot make a meaningful threshold comparison and is likely to return a `blocked` or incorrect verdict.

## Loop Context

- **Loop**: `sprint-build-and-validate`
- **State**: `route_validation`
- **Signal type**: action_failure (evaluate misconfiguration)
- **Occurrences**: 1 (observed at iteration 7, loop status: failed)
- **Last observed**: 2026-03-15T22:48:44+00:00

## History Excerpt

Events leading to this signal:

```json
[
  {
    "event": "action_complete",
    "state": "validate_issues",
    "exit_code": 0,
    "duration_ms": 115055,
    "is_prompt": true,
    "output": "No active sprint is loaded — `ll-sprint show` returns nothing..."
  },
  {
    "event": "evaluate",
    "state": "route_validation",
    "verdict": "blocked",
    "llm_prompt": "Do any sprint issues fail readiness checks (readiness < ${context.readiness_threshold}\nor outcome confidence < ${context.outcome_threshold})?\nReturn \"yes\" if all issues pass and are implementation-ready.\nReturn \"no\" if any issues need fixing.",
    "reason": "No active sprint is loaded. Cannot determine readiness without knowing which sprint or issues to check."
  },
  {
    "event": "loop_complete",
    "terminated_by": "error",
    "final_state": "route_validation",
    "iterations": 7
  }
]
```

## Expected Behavior

The evaluate prompt should have `${context.readiness_threshold}` and `${context.outcome_threshold}` substituted with their configured values (`85` and `70` respectively) before being sent to the LLM, consistent with how `${context.*}` variables are interpolated in `action` fields.

## Root Cause

- **File**: `scripts/little_loops/fsm/evaluators.py`
- **Anchor**: `evaluate()` function, `llm_structured` dispatch branch (line ~807-814)
- **Cause**: The `llm_structured` branch passes `config.prompt` raw to `evaluate_llm_structured()` without calling `interpolate()` on it. The `context: InterpolationContext` parameter is in scope at `evaluate()` and is already used for other evaluate types (`output_numeric.target` at line ~719, `convergence.previous/target/tolerance` at lines ~752-789), but the `llm_structured` branch is the only one that skips interpolation on its string field.

The `interpolate` function is already imported in `evaluators.py:32-36` — no new imports needed.

**Interpolation coverage by field type** (current state):

| Field | Interpolated | Location |
|---|---|---|
| `action:` string | Yes | `executor.py:620` |
| `evaluate.source:` | Yes | `executor.py:794` |
| `evaluate.target:` (output_numeric) | Yes | `evaluators.py:~719` |
| `evaluate.target/previous/tolerance:` (convergence) | Yes | `evaluators.py:~752-789` |
| `evaluate.prompt:` (llm_structured) | **No** | `evaluators.py:~809` — gap |

## Proposed Fix

In `evaluators.py`, interpolate `config.prompt` before passing it to `evaluate_llm_structured()`. Follow the same defensive pattern used by `output_numeric` (interpolate if context present, fallback to raw on error):

```python
# In the llm_structured branch of evaluate():
prompt = config.prompt
if prompt and context:
    try:
        prompt = interpolate(prompt, context)
    except InterpolationError:
        pass  # Use raw prompt on resolution failure

return evaluate_llm_structured(
    output=output,
    prompt=prompt,
    schema=config.schema,
    min_confidence=config.min_confidence,
    uncertain_suffix=config.uncertain_suffix,
)

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/evaluators.py` — add `interpolate(config.prompt, context)` in the `llm_structured` branch of `evaluate()` before calling `evaluate_llm_structured()`

### Files to Read (no changes expected)
- `scripts/little_loops/fsm/interpolation.py` — `interpolate()` and `InterpolationContext` (already imported in `evaluators.py`)
- `loops/sprint-build-and-validate.yaml` — the loop config that exposed this bug; no change needed, the YAML is correct

### Dependent Files (callers)
- `scripts/little_loops/fsm/executor.py:806` — calls `evaluate(config=state.evaluate, output=eval_input, exit_code=..., context=ctx)`; passes `ctx` already, so no change needed here

### Tests
- `scripts/tests/test_fsm_evaluators.py` — add test case: `test_dispatch_llm_structured_interpolates_prompt` — verify `${context.*}` in prompt is resolved before being sent to LLM
  - Model after existing `test_dispatch_output_numeric_interpolated_target` at line ~429

### Similar Patterns
- `evaluators.py:~719` — `output_numeric` pattern: `resolved = interpolate(config.target, context) if context else config.target` — use the same try/except guard
- `evaluators.py:~752-789` — `convergence` pattern: consistent `try/except InterpolationError` fallback

## Implementation Steps

1. **Open `evaluators.py`** and locate the `llm_structured` branch inside `evaluate()` (~line 807-814)
2. **Add interpolation**: before `evaluate_llm_structured(prompt=config.prompt, ...)`, resolve `config.prompt` via `interpolate()` using the existing `context` parameter (follow the `output_numeric` guard pattern)
3. **Add unit test** in `test_fsm_evaluators.py`: mock the LLM call, pass `EvaluateConfig(type="llm_structured", prompt="readiness < ${context.threshold}")` with `ctx = InterpolationContext(context={"threshold": "85"})`, assert resolved prompt is sent to the LLM
4. **Run tests**: `python -m pytest scripts/tests/test_fsm_evaluators.py -v -k llm`

## Acceptance Criteria

- [ ] `${context.readiness_threshold}` in evaluate prompts resolves to `85` (or configured value)
- [ ] `${context.outcome_threshold}` in evaluate prompts resolves to `70` (or configured value)
- [ ] Unit test confirms context variable interpolation applies to `evaluate.prompt` fields

## Labels

`bug`, `loops`, `captured`

## Status

**Open** | Created: 2026-03-15 | Priority: P2


## Session Log
- `/ll:refine-issue` - 2026-03-15T23:04:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c84ab5a-c97c-49a5-bd30-6defbaef2cab.jsonl`

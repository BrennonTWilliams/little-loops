---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 75
parent_issue: FEAT-988
---

# FEAT-990: FSMExecutor Hook Dispatch — Tests and Code Wiring

## Summary

Verify and complete the test coverage for contributed action/evaluator/interceptor dispatch (FEAT-987), add smoke import tests, remove dead type suppressions, and apply the schema widening and re-export wiring needed to make contributed action type strings valid at load time and importable from the public package API.

## Parent Issue

Decomposed from FEAT-988: FSMExecutor Hook Dispatch — Tests and Wiring Pass

## Current Behavior

After FEAT-987 adds runtime dispatch for contributed action types, three gaps remain:
- A loop YAML with an unknown `action_type` (e.g., `webhook`) fails `load_and_validate()` with a JSON Schema error
- `StateConfig.action_type` is annotated as `Literal["prompt", "slash_command", "shell", "mcp_tool"] | None`, causing mypy errors when contributed type strings are passed
- `RouteContext` and `RouteDecision` are not exported from the public `little_loops` package
- Dead `# type: ignore[arg-type]` suppressions exist in `test_ll_loop_display.py`

## Expected Behavior

- A loop YAML with any `action_type` string (including custom values like `webhook`) passes `load_and_validate()` without error
- `from little_loops import RouteContext, RouteDecision` works for extension authors
- mypy passes on `executor.py` and `schema.py` after annotation widening
- All test classes pass: `TestContributedActionDispatch`, `TestContributedEvaluatorDispatch`, `TestRouteInterceptors` (= `TestInterceptorDispatch`), `TestRouteContextDataclass`, `TestRouteDecisionDataclass`
- Smoke import tests in `test_extension.py` pass

## Use Case

An extension author building a contributed action handler (e.g., a `webhook` action type) needs:
- Their custom `action_type` string to pass JSON Schema validation at load time
- `RouteContext` and `RouteDecision` to be importable from the public `little_loops` package
- Confidence that dispatch tests cover their hook integration point

Without these, contributing a new action type fails silently or requires reaching into internal submodules.

## Proposed Solution

### 1. Verify Existing Test Classes

The following tests are already implemented — verify they pass with no modifications after Steps 2–4:

- `scripts/tests/test_fsm_executor.py:3643–3726` — `TestRouteContext`
- `scripts/tests/test_fsm_executor.py:3729–3746` — `TestRouteDecision`
- `scripts/tests/test_fsm_executor.py:3749–3824` — `TestContributedActionDispatch`
- `scripts/tests/test_fsm_executor.py:3827–4011` — `TestInterceptorDispatch` (= `TestRouteInterceptors`)
- `scripts/tests/test_ll_loop_execution.py:1602–1701` — `TestContributedEvaluatorDispatch`

### 2. Schema Widening

**`scripts/little_loops/fsm/schema.py:214`** — widen `StateConfig.action_type`:

```python
# Before
action_type: Literal["prompt", "slash_command", "shell", "mcp_tool"] | None = None

# After
action_type: str | None = None
```

**`scripts/little_loops/fsm/fsm-loop-schema.json:177`** — relax `action_type` enum:

```json
// Before
"action_type": {
    "type": "string",
    "enum": ["prompt", "slash_command", "shell", "mcp_tool"]
}

// After (remove enum, keep type)
"action_type": {
    "type": "string"
}
```

### 3. Re-Export Wiring

**`scripts/little_loops/__init__.py`** — add `RouteContext`, `RouteDecision` to package-level public exports and `__all__` (lines ~9–17, ~37–72):

```python
from little_loops.fsm import (
    ...,
    RouteContext,
    RouteDecision,
)
```

Note: `fsm/__init__.py` already re-exports these at lines 86–94 — no changes needed there.

### 4. Add Smoke Import Tests

**`scripts/tests/test_extension.py`** — add smoke import tests following `TestNewProtocols` pattern at line 266:

```python
from little_loops import RouteContext
from little_loops import RouteDecision
```

### 5. Remove Dead Type Suppressions

**`scripts/tests/test_ll_loop_display.py:2109`** — remove `# type: ignore[arg-type]` (becomes dead after annotation widening)
**`scripts/tests/test_ll_loop_display.py:2124`** — same; remove the suppression comment

## Implementation Steps

1. Widen `StateConfig.action_type` annotation at `schema.py:214` (`Literal[...]` → `str | None`)
2. Relax `action_type` enum in `fsm-loop-schema.json` at lines 174–178 (remove `"enum"` key, keep `"type": "string"`)
3. Add `RouteContext`/`RouteDecision` to `little_loops/__init__.py` imports and `__all__`
4. Run existing tests to verify `TestRouteContext`, `TestRouteDecision`, `TestContributedActionDispatch`, `TestInterceptorDispatch`, `TestContributedEvaluatorDispatch` all pass
5. Add smoke import tests in `scripts/tests/test_extension.py`
6. Remove dead `# type: ignore[arg-type]` suppressions at `test_ll_loop_display.py:2109,2124`
7. Verify mypy passes on `executor.py` and `schema.py`

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/schema.py:214` — widen `action_type` annotation (`Literal[...]` → `str | None`)
- `scripts/little_loops/fsm/fsm-loop-schema.json:174–178` — relax enum (remove `"enum"` key, keep `"type": "string"`)
- `scripts/little_loops/__init__.py` — add `RouteContext`/`RouteDecision` to imports and `__all__`
- `scripts/tests/test_extension.py` — add smoke import tests (follow `TestNewProtocols` pattern at line 270)
- `scripts/tests/test_ll_loop_display.py:2109,2124` — remove dead `# type: ignore[arg-type]` suppressions

**Already complete (no action needed):**
- `scripts/little_loops/fsm/__init__.py` — `RouteContext`/`RouteDecision` already re-exported at lines 86–94

### Dependent Files (Read-Only Context)

- `scripts/little_loops/fsm/executor.py` — defines `RouteContext` (line 54), `RouteDecision` (line 67)
- `scripts/little_loops/fsm/validation.py:197–200` — `state.action_type != "mcp_tool"` check; compatible with widening
- `scripts/little_loops/cli/loop/layout.py:127–128` — already handles unknown types via dict `.get()` fallback
- `scripts/little_loops/cli/loop/info.py:558–559,755–756,767` — renders `action_type` as direct string; no enum dependency
- `scripts/little_loops/cli/loop/_helpers.py:162` — `state.action_type == "prompt"` check; compatible with widening

### Similar Patterns

- `scripts/tests/test_fsm_executor.py` — `TestActionType` class: existing pattern near new test classes
- `scripts/tests/test_fsm_evaluators.py:49–63` — `@pytest.mark.parametrize` pattern
- `scripts/tests/test_fsm_schema.py:80–179` — `TestEvaluateConfig`: pattern for dataclass tests

### Tests

**Already implemented (verify pass):**
- `scripts/tests/test_fsm_executor.py:3643–4011` — `TestRouteContext`, `TestRouteDecision`, `TestContributedActionDispatch`, `TestInterceptorDispatch`
- `scripts/tests/test_ll_loop_execution.py:1602–1701` — `TestContributedEvaluatorDispatch`

**At-risk existing tests (verify unmodified):**
- `scripts/tests/test_fsm_executor.py` — `TestActionType`, `TestActionTypeMcpTool`
- `scripts/tests/test_ll_loop_execution.py` — 8 direct `_evaluate()` call sites (lines 921, 960, 1008, 1052, 1093, 1641, 1673, 1699)

**New to add:**
- `scripts/tests/test_extension.py` — smoke import tests for `RouteContext`/`RouteDecision` from public API

## Acceptance Criteria

- [x] Loop YAML with `action_type: webhook` passes `load_and_validate()` without schema error
- [x] `from little_loops import RouteContext, RouteDecision` works
- [x] mypy passes on `executor.py` and `schema.py` after annotation widening
- [x] `TestContributedActionDispatch`, `TestContributedEvaluatorDispatch`, `TestInterceptorDispatch` pass in `test_fsm_executor.py`/`test_ll_loop_execution.py`
- [x] `TestRouteContext`, `TestRouteDecision` pass in `test_fsm_executor.py`
- [x] Smoke import tests pass in `test_extension.py`
- [x] Dead `# type: ignore` suppressions removed from `test_ll_loop_display.py`
- [x] All pre-existing tests pass unmodified

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small-Medium — schema/annotation changes are 2-line edits; tests are mostly verify-only
- **Risk**: Low — type/schema relaxation only; no runtime execution path changes
- **Depends On**: FEAT-987 (core executor dispatch must be implemented first)
- **Blocks**: FEAT-985 (wire_extensions() — needs public RouteContext/RouteDecision exports)

## Labels

`feature`, `fsm`, `executor`, `extension-hooks`, `testing`, `wiring`, `decomposed`

## Resolution

Implemented 2026-04-07. All changes were mechanical type/schema relaxations with no runtime behavior changes:

1. `schema.py:214` — widened `StateConfig.action_type` from `Literal[...]` to `str | None`
2. `fsm-loop-schema.json:174–178` — removed `enum` constraint from `action_type`, kept `type: string`
3. `little_loops/__init__.py` — added `RouteContext`/`RouteDecision` to imports and `__all__`
4. `test_extension.py` — added two smoke import tests in `TestNewProtocols`
5. `test_ll_loop_display.py:2109,2124` — removed dead `# type: ignore[arg-type]` suppressions
6. `executor.py:493` — added `assert state.action_type is not None` to satisfy mypy narrowing after annotation widening

All 4440 tests pass; mypy clean on `executor.py` and `schema.py`.

## Status

**Completed** | Created: 2026-04-07 | Completed: 2026-04-07 | Priority: P4

## Session Log
- `/ll:ready-issue` - 2026-04-08T04:25:04 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a5e8ff3f-6ff1-4255-b8b3-8511d145a869.jsonl`
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b5b8fb2-d663-482d-be59-6aa37de8e735.jsonl`

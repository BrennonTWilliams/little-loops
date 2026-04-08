---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 88
outcome_confidence: 80
parent_issue: FEAT-984
---

# FEAT-988: FSMExecutor Hook Dispatch — Tests and Wiring Pass

## Summary

Write unit tests for the contributed action/evaluator/interceptor dispatch added by FEAT-987, and apply the schema widening and re-export wiring needed to make contributed action type strings valid at load time and importable from the public package API.

## Use Case

After FEAT-987 adds the runtime dispatch, a developer with `action_type: webhook` in their loop YAML currently fails JSON Schema validation before the executor ever runs. This issue fixes that by relaxing the `action_type` enum, widens the mypy annotation, and exports `RouteContext`/`RouteDecision` from the public API so extension authors can build `before_route` interceptors without importing from internal submodules.

## Parent Issue

Decomposed from FEAT-984: FSMExecutor Hook Dispatch for Contributed Actions, Evaluators, and Route Interceptors

## Context

Depends on FEAT-987 (core executor dispatch) being complete. The tests exercise the new dispatch paths; the wiring changes (schema, re-exports) make the extension system usable end-to-end by plugin developers.

## Proposed Solution

### 1. Tests — New Test Classes

#### `scripts/tests/test_fsm_executor.py`

Add **`TestContributedActionDispatch`** (follow `TestActionType` pattern at lines 234–366):
- Contributed `action_type` string returns `"contributed"` from `_action_mode()`
- Dispatches to registered runner, does NOT call `self.action_runner`
- Unregistered type falls through to default dispatch

Add **`TestRouteInterceptors`** (use `MockActionRunner.always_return()`, assert on `ExecutionResult.final_state`):
- `before_route` veto returns `None` (loop halts)
- `before_route` redirect returns `decision.next_state` directly (bypasses `_route()`)
- `after_route` fires after routing
- `state.next:` unconditional transition does NOT fire interceptors
- Sub-loop branch does NOT fire interceptors

Add **`TestContributedEvaluatorDispatch`** (follow `@pytest.mark.parametrize` pattern at `test_fsm_evaluators.py:49–63`):
- Contributed evaluator type is called before `evaluate()`
- Result passed through routing
- Unregistered type falls through to built-in `evaluate()`

#### `scripts/tests/test_fsm_schema.py`

Add **`TestRouteContextDataclass`** (follow `TestEvaluateConfig` at `test_fsm_schema.py:80–179`):
- Field defaults and construction for `RouteContext`

Add **`TestRouteDecisionDataclass`** (follow `TestHandoffResult` at `test_handoff_handler.py:103–123`):
- `next_state=None` (veto) and `next_state="some_state"` (redirect)

### 2. Schema Widening

**`scripts/little_loops/fsm/schema.py:214`** — widen `StateConfig.action_type`:

```python
# Before
action_type: Literal["prompt", "slash_command", "shell", "mcp_tool"] | None = None

# After
action_type: str | None = None
```

The `from_dict()` method at line 279 already passes through any string at runtime — only the static annotation needs widening.

**`scripts/little_loops/fsm/fsm-loop-schema.json:177`** — relax `action_type` enum. Remove the `"enum"` restriction or replace with a `oneOf` that allows additional strings:

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

A loop YAML with `action_type: webhook` currently fails `load_and_validate()` before the executor sees it.

### 3. Re-Export Wiring

**`scripts/little_loops/fsm/__init__.py`** — add `RouteContext`, `RouteDecision` to re-export block (lines 86–92) and `__all__` (lines 133–178):

```python
from little_loops.fsm.types import (
    ...,
    RouteContext,
    RouteDecision,
)
```

**`scripts/little_loops/__init__.py`** — add `RouteContext`, `RouteDecision` to package-level public exports and `__all__` (lines 9–14, 39–43):

```python
from little_loops.fsm import (
    ...,
    RouteContext,
    RouteDecision,
)
```

### 4. review-loop Reference Update

**`skills/review-loop/reference.md:103–132`** — QC-3 `action_type` mismatch check only knows `prompt`, `shell`, `slash_command`, `mcp_tool`. Update QC-3 to treat unknown values as potential contributed types (warn, not error).

### 5. Documentation Updates

- **`docs/reference/API.md:4040–4053`** — `ActionRunner Protocol` section: update description to note it also serves as the contributed-actions runtime dispatch interface (not just testing/customization)
- **`docs/ARCHITECTURE.md:454–458`** — Extension component table: add the three new `_contributed_actions`, `_contributed_evaluators`, `_interceptors` registries

## Integration Map

### Files to Modify

- `scripts/tests/test_fsm_executor.py` — add 3 new test classes
- `scripts/tests/test_fsm_schema.py` — add 2 new dataclass test classes
- `scripts/little_loops/fsm/schema.py:214` — widen `action_type` annotation
- `scripts/little_loops/fsm/fsm-loop-schema.json:177` — relax enum
- `scripts/little_loops/fsm/__init__.py` — add re-exports (lines 86–92, 133–178)
- `scripts/little_loops/__init__.py` — add re-exports (lines 9–14, 39–43)
- `skills/review-loop/reference.md:103–132` — QC-3 update
- `docs/reference/API.md:4040–4053` — ActionRunner description update
- `docs/ARCHITECTURE.md:454–458` — extension table update

### At-Risk Existing Tests (verify pass)

- `scripts/tests/test_fsm_executor.py:234–366` — `TestActionType`; verify contributed check does not intercept known type strings
- `scripts/tests/test_fsm_executor.py:369–532` — `TestActionTypeMcpTool`
- `scripts/tests/test_ll_loop_execution.py:889–1097` — 5 direct `_evaluate()` call sites

## Acceptance Criteria

- [ ] `TestContributedActionDispatch`, `TestContributedEvaluatorDispatch`, `TestRouteInterceptors` pass in `test_fsm_executor.py`
- [ ] `TestRouteContextDataclass`, `TestRouteDecisionDataclass` pass in `test_fsm_schema.py`
- [ ] Loop YAML with `action_type: webhook` passes `load_and_validate()` without schema error
- [ ] `from little_loops import RouteContext, RouteDecision` works
- [ ] `mypy` passes on `executor.py` and `schema.py` after annotation widening
- [ ] QC-3 in `review-loop/reference.md` warns (not errors) on unknown `action_type` values
- [ ] All pre-existing tests pass unmodified

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Medium — 5 new test classes + scattered small wiring changes
- **Risk**: Low — tests and type/schema relaxation; no changes to runtime execution path
- **Depends On**: FEAT-987 (core executor dispatch must be implemented first)
- **Blocks**: FEAT-985 (wire_extensions() — needs public RouteContext/RouteDecision exports)

## Labels

`feature`, `fsm`, `executor`, `extension-hooks`, `testing`, `wiring`, `decomposed`

## Status

**Open** | Created: 2026-04-07 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3f3aa3c7-ca33-4c8b-b435-c5b746906130.jsonl`

---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 71
parent_issue: FEAT-984
---

# FEAT-988: FSMExecutor Hook Dispatch — Tests and Wiring Pass

## Summary

Write unit tests for the contributed action/evaluator/interceptor dispatch added by FEAT-987, and apply the schema widening and re-export wiring needed to make contributed action type strings valid at load time and importable from the public package API.

## Current Behavior

After FEAT-987 adds runtime dispatch for contributed action types, three gaps remain that prevent end-to-end usability of the extension system:
- A loop YAML with an unknown `action_type` (e.g., `webhook`) fails `load_and_validate()` with a JSON Schema error — the `action_type` enum in `fsm-loop-schema.json` only lists built-in types, so the FSM executor never runs
- `StateConfig.action_type` is annotated as `Literal["prompt", "slash_command", "shell", "mcp_tool"] | None`, causing mypy errors when contributed type strings are passed
- `RouteContext` and `RouteDecision` are not exported from the public `little_loops` package, requiring extension authors to import from internal submodules (`little_loops.fsm.types`)
- No unit tests cover the contributed action, evaluator, or interceptor dispatch paths added by FEAT-987

## Expected Behavior

- A loop YAML with any `action_type` string (including custom values like `webhook`) passes `load_and_validate()` without error
- `from little_loops import RouteContext, RouteDecision` works for extension authors building `before_route` interceptors
- mypy passes on `executor.py` and `schema.py` after annotation widening
- Unit tests (`TestContributedActionDispatch`, `TestContributedEvaluatorDispatch`, `TestRouteInterceptors`, `TestRouteContextDataclass`, `TestRouteDecisionDataclass`) pass and verify all dispatch paths introduced by FEAT-987

## Use Case

After FEAT-987 adds the runtime dispatch, a developer with `action_type: webhook` in their loop YAML currently fails JSON Schema validation before the executor ever runs. This issue fixes that by relaxing the `action_type` enum, widens the mypy annotation, and exports `RouteContext`/`RouteDecision` from the public API so extension authors can build `before_route` interceptors without importing from internal submodules.

## Motivation

FEAT-987 adds the runtime dispatch mechanism but leaves the extension system non-functional in practice: contributed action types are blocked at schema validation, the public API is incomplete (missing `RouteContext`/`RouteDecision` exports), and there are no tests to confirm dispatch behavior. This issue delivers the validation, API, and test coverage that makes the extension system actually usable by plugin developers. It also unblocks FEAT-985 (`wire_extensions()`), which depends on the public exports.

## Parent Issue

Decomposed from FEAT-984: FSMExecutor Hook Dispatch for Contributed Actions, Evaluators, and Route Interceptors

## Context

Depends on FEAT-987 (core executor dispatch) being complete. The tests exercise the new dispatch paths; the wiring changes (schema, re-exports) make the extension system usable end-to-end by plugin developers.

## Proposed Solution

### 1. Tests — New Test Classes

#### `scripts/tests/test_fsm_executor.py`

Add **`TestContributedActionDispatch`** (follow `TestActionType` pattern at lines 238–370):
- Contributed `action_type` string returns `"contributed"` from `_action_mode()`
- Dispatches to registered runner, does NOT call `self.action_runner`
- Unregistered type falls through to default dispatch (heuristic: `/` prefix → `"prompt"`, else → `"shell"`)

Populate contributed action registry via direct assignment after constructing executor:
```python
executor._contributed_actions["webhook"] = contributed_runner
```

`MockActionRunner` is a plain `@dataclass`; `always_return()` is an **instance method** (not a classmethod):
```python
mock_runner = MockActionRunner()
mock_runner.always_return(exit_code=0, output="ok")
```

Add **`TestRouteInterceptors`** (use `MockActionRunner()` instance then call `always_return()` on it, assert on `ExecutionResult`):
- `before_route` veto (`RouteDecision(next_state=None)`) → `result.terminated_by == "error"` (executor calls `_finish("error")`)
- `before_route` redirect (`RouteDecision(next_state="some_state")`) returns `decision.next_state` directly (bypasses `_route()`)
- `after_route` fires after routing; assert the interceptor method was called
- `state.next:` unconditional transition exits `_execute_state()` before the interceptor loop — does NOT fire interceptors
- Sub-loop branch also exits before the interceptor loop — does NOT fire interceptors

Populate interceptor registry via direct assignment after constructing executor:
```python
executor._interceptors.append(my_interceptor)
```

Add **`TestContributedEvaluatorDispatch`** (follow `@pytest.mark.parametrize` pattern at `test_fsm_evaluators.py:49–63`):
- Contributed evaluator type is called before built-in `evaluate()`
- Result passed through routing
- Unregistered type falls through to built-in `evaluate()`

Contributed evaluator is a `Callable[[EvaluateConfig, str, int, InterpolationContext], EvaluationResult]` (`Evaluator` type alias at `types.py:79–82`). Called at `executor.py:668–674` as `self._contributed_evaluators[state.evaluate.type](config, eval_input, exit_code, ctx)`.

Populate via:
```python
executor._contributed_evaluators["my_type"] = my_evaluator_fn
```

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

**`scripts/little_loops/fsm/__init__.py`** — **already complete** (landed with FEAT-987). `RouteContext` and `RouteDecision` are already imported from `little_loops.fsm.executor` at lines 86–94 and listed in `__all__` at lines 162–163. No changes needed here.

**`scripts/little_loops/__init__.py`** — add `RouteContext`, `RouteDecision` to package-level public exports and `__all__` (lines 9–14, 37–72). They are imported from `little_loops.fsm` (not `little_loops.fsm.types`):

```python
from little_loops.fsm import (
    ...,
    RouteContext,
    RouteDecision,
)
```

Note: `RouteContext` and `RouteDecision` are defined in `executor.py` (lines 54–63, 66–77), not `types.py`. The `fsm/__init__.py` re-export chain already handles the indirection correctly.

### 4. review-loop Reference Update

**`skills/review-loop/reference.md:103–132`** — QC-3 `action_type` mismatch check only knows `prompt`, `shell`, `slash_command`, `mcp_tool`. Update QC-3 to treat unknown values as potential contributed types (warn, not error).

### 5. Documentation Updates

- **`docs/reference/API.md:4040–4053`** — `ActionRunner Protocol` section: update description to note it also serves as the contributed-actions runtime dispatch interface (not just testing/customization)
- **`docs/ARCHITECTURE.md:454–458`** — Extension component table: add the three new `_contributed_actions`, `_contributed_evaluators`, `_interceptors` registries

## Implementation Steps

1. Write `TestContributedActionDispatch`, `TestRouteInterceptors`, `TestContributedEvaluatorDispatch` in `test_fsm_executor.py` (follow `TestActionType` at lines 238–370 and `@pytest.mark.parametrize` pattern at `test_fsm_evaluators.py:49–63`)
2. Write `TestRouteContextDataclass`, `TestRouteDecisionDataclass` in `test_fsm_schema.py` (follow `TestEvaluateConfig` at lines 80–179 and `TestHandoffResult` at `test_handoff_handler.py:103–123`); import `RouteContext`/`RouteDecision` from `little_loops.fsm.executor`
3. Widen `StateConfig.action_type` annotation at `schema.py:214` (`Literal[...]` → `str | None`; `Literal` import stays — still used elsewhere in the file)
4. Relax `action_type` enum in `fsm-loop-schema.json` at lines 174–178 (remove `"enum"` key, keep `"type": "string"`)
5. Add `RouteContext`/`RouteDecision` to `little_loops/__init__.py` imports (~lines 9–17) and `__all__` (~lines 37–72); skip `fsm/__init__.py` — already complete
6. Update `review-loop/reference.md` QC-3 to warn (not error) on unknown `action_type` values; update `API.md` and `ARCHITECTURE.md`
7. Verify pre-existing tests pass unmodified (`TestActionType`, `TestActionTypeMcpTool`, direct `_evaluate()` call sites in `test_ll_loop_execution.py`)

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Verify** (not rewrite) `TestContributedActionDispatch`, `TestInterceptorDispatch`, `TestContributedEvaluatorDispatch`, `TestRouteContext`, `TestRouteDecision` in `test_fsm_executor.py:3643–4011` and `test_ll_loop_execution.py:1602–1701` — all already implemented; confirm they pass with no modifications after Steps 3–5
9. Add smoke import tests in `scripts/tests/test_extension.py` — `from little_loops import RouteContext` and `from little_loops import RouteDecision`, following `TestNewProtocols` pattern at line 270
10. Remove dead `# type: ignore[arg-type]` suppressions at `scripts/tests/test_ll_loop_display.py:2109,2124` after annotation widening
11. Update `skills/review-loop/SKILL.md:128–198` QC-3 block alongside `reference.md` — same warn-not-error change for unknown `action_type` values

## Integration Map

### Files to Modify

- `scripts/tests/test_fsm_executor.py` — add 3 new test classes
- `scripts/tests/test_fsm_schema.py` — add 2 new dataclass test classes; import `RouteContext`/`RouteDecision` from `little_loops.fsm.executor`
- `scripts/little_loops/fsm/schema.py:214` — widen `action_type` annotation (`Literal[...]` → `str | None`)
- `scripts/little_loops/fsm/fsm-loop-schema.json:174–178` — relax enum (remove `"enum"` key, keep `"type": "string"`)
- `scripts/little_loops/__init__.py` — add `RouteContext`/`RouteDecision` to imports (lines ~9–17) and `__all__` (lines ~37–72)
- `skills/review-loop/reference.md:103–132` — QC-3 update
- `docs/reference/API.md:4040–4053` — ActionRunner description update
- `docs/ARCHITECTURE.md:454–458` — extension table update

**Already complete (no action needed):**
- `scripts/little_loops/fsm/__init__.py` — `RouteContext`/`RouteDecision` already re-exported at lines 86–94 and listed in `__all__` at lines 162–163 (landed with FEAT-987)

### Dependent Files (Callers/Importers)

- `scripts/little_loops/fsm/executor.py` — defines `RouteContext` (line 54), `RouteDecision` (line 66), `_action_mode()` (line 760), contributed dispatch in `_run_action()` (lines 492–499), `_evaluate()` (lines 668–674), interceptor loop in `_execute_state()` (lines 446–456)
- `scripts/little_loops/fsm/__init__.py` — already re-exports `RouteContext`/`RouteDecision` from `executor` (lines 86–94)
- `scripts/little_loops/__init__.py` — package-level re-exports; must add `RouteContext`/`RouteDecision` (currently absent)
- `scripts/little_loops/extension.py` — imports `RouteContext`, `RouteDecision` from `executor`; defines `before_route`/`after_route` hook interfaces
- Any loop YAML using `action_type:` — validated against `fsm-loop-schema.json` at load time; blocked by current `"enum"` at lines 174–178
- FEAT-985 (`wire_extensions()`) — blocked on `RouteContext`/`RouteDecision` in the public `little_loops` API

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/validation.py:197–200` — contains `state.action_type != "mcp_tool"` string comparison used in MCP params validation; compatible with widening but verify the check survives the annotation change
- `scripts/little_loops/cli/loop/layout.py:127–128` — `_get_state_badge()` uses dict `.get(state.action_type, f"[{state.action_type}]")` fallback; already handles unknown contributed types correctly, no change needed
- `scripts/little_loops/cli/loop/info.py:558–559,755–756,767` — renders `action_type` in state summary tables and diagrams as a direct string; no enum dependency, fully compatible
- `scripts/little_loops/cli/loop/_helpers.py:162` — `state.action_type == "prompt"` display branch; compatible with widening, takes `else` path for contributed types

### Similar Patterns

- `scripts/tests/test_fsm_executor.py` — `TestActionType` class: pattern to follow for `TestContributedActionDispatch`
- `scripts/tests/test_fsm_evaluators.py` — `@pytest.mark.parametrize` at lines 49–63: pattern for `TestContributedEvaluatorDispatch`
- `scripts/tests/test_fsm_schema.py` — `TestEvaluateConfig`: pattern for `TestRouteContextDataclass`
- `scripts/tests/test_handoff_handler.py` — `TestHandoffResult`: pattern for `TestRouteDecisionDataclass`

### Tests

New tests (to add):
- `scripts/tests/test_fsm_executor.py` — `TestContributedActionDispatch`, `TestRouteInterceptors`, `TestContributedEvaluatorDispatch`
- `scripts/tests/test_fsm_schema.py` — `TestRouteContextDataclass`, `TestRouteDecisionDataclass`

At-risk existing tests (verify pass):
- `scripts/tests/test_fsm_executor.py` — `TestActionType`; verify contributed check does not intercept known type strings
- `scripts/tests/test_fsm_executor.py` — `TestActionTypeMcpTool`
- `scripts/tests/test_ll_loop_execution.py` — 5 direct `_evaluate()` call sites

_Wiring pass added by `/ll:wire-issue`:_

**CRITICAL — Tests already written (verify, don't rewrite):**
- `scripts/tests/test_fsm_executor.py:3643–3726` — `TestRouteContext` already implemented
- `scripts/tests/test_fsm_executor.py:3729–3746` — `TestRouteDecision` already implemented
- `scripts/tests/test_fsm_executor.py:3749–3824` — `TestContributedActionDispatch` already implemented
- `scripts/tests/test_fsm_executor.py:3827–4011` — `TestInterceptorDispatch` (= `TestRouteInterceptors`) already implemented
- `scripts/tests/test_ll_loop_execution.py:1602–1701` — `TestContributedEvaluatorDispatch` already implemented

Implementation Steps 1–2 are partially complete. Verify these pass rather than rewriting them.

**New gap — to write:**
- `scripts/tests/test_extension.py` — add smoke import tests for `RouteContext`/`RouteDecision` from `little_loops` public API, following `TestNewProtocols` pattern at line 270 (`from little_loops import RouteContext` / `from little_loops import RouteDecision`)

**Cleanup — dead suppression after widening:**
- `scripts/tests/test_ll_loop_display.py:2109` — `# type: ignore[arg-type]` becomes a no-op after `action_type` widens to `str | None`; remove the suppression comment
- `scripts/tests/test_ll_loop_display.py:2124` — same; remove the suppression comment

**Correction — `_evaluate()` call site count:**
- `scripts/tests/test_ll_loop_execution.py` — 8 direct `_evaluate()` call sites (lines 921, 960, 1008, 1052, 1093, 1641, 1673, 1699), not 5 as listed above

### Documentation

- `docs/reference/API.md` — `ActionRunner Protocol` section: note it serves as contributed-actions runtime dispatch interface
- `docs/ARCHITECTURE.md` — Extension component table: add `_contributed_actions`, `_contributed_evaluators`, `_interceptors` registries

_Wiring pass added by `/ll:wire-issue`:_
- `skills/review-loop/SKILL.md:128–198` — QC-3 block discusses `action_type` values `prompt`, `shell`, `slash_command` by name; mirrors the `reference.md` QC-3 section already listed in Files to Modify — must also be updated to warn (not error) on unknown values

### Configuration

- `scripts/little_loops/fsm/fsm-loop-schema.json` — JSON Schema for loop YAML; `action_type` enum must be relaxed to allow arbitrary strings

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
- `hook:posttooluse-git-mv` - 2026-04-08T03:54:52 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b5b8fb2-d663-482d-be59-6aa37de8e735.jsonl`
- `/ll:wire-issue` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/cbf4e0db-2b1c-458f-8742-2a3e5c6eaf5c.jsonl`
- `/ll:refine-issue` - 2026-04-08T03:36:12 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/74b8c434-7f50-4e1a-8d06-f8c08909b50b.jsonl`
- `/ll:format-issue` - 2026-04-08T03:32:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/356230f7-8b45-4085-9885-caa20e004bc6.jsonl`
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3f3aa3c7-ca33-4c8b-b435-c5b746906130.jsonl`
- `/ll:confidence-check` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/2cc9a39a-f4a1-4144-bc8d-ce2841277af4.jsonl`
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0b5b8fb2-d663-482d-be59-6aa37de8e735.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-07
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- FEAT-990: FSMExecutor Hook Dispatch — Tests and Code Wiring
- FEAT-991: FSMExecutor Hook Dispatch — Skill and Docs Update

---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 90
outcome_confidence: 82
parent_issue: FEAT-984
---

# FEAT-987: FSMExecutor Core Hook Dispatch (Attributes + Action/Evaluator/Interceptor Dispatch)

## Summary

Add `_contributed_actions`, `_contributed_evaluators`, and `_interceptors` attributes to `FSMExecutor.__init__()`, then wire them into `_action_mode()`, `_run_action()`, `_evaluate()`, and `_execute_state()`. This is the runtime dispatch half of the FEAT-915 extension system.

## Use Case

A developer building a custom FSM loop extension registers a contributed action type (e.g., `action_type: webhook`) on an `FSMExecutor` instance. At runtime the executor detects the contributed type, dispatches to their `ActionRunner` implementation, and fires registered route interceptors — enabling per-loop routing observability or redirect overrides without touching core infrastructure.

## Parent Issue

Decomposed from FEAT-984: FSMExecutor Hook Dispatch for Contributed Actions, Evaluators, and Route Interceptors

## Context

FEAT-983 defines the Protocol and type foundations (`RouteContext`, `RouteDecision`, `Evaluator`). This issue implements the `FSMExecutor` changes needed to actually dispatch to registered extensions at runtime. `wire_extensions()` (FEAT-985) will populate these registries; this issue only defines them and uses them.

## Current Behavior

`FSMExecutor` has no concept of contributed action types or evaluators. `_action_mode()` uses a hardcoded sequential-if chain. Route interceptors do not exist.

## Expected Behavior

- `FSMExecutor.__init__()` initializes three new attributes
- `_action_mode()` checks `_contributed_actions` before fallback to shell
- `_run_action()` dispatches to contributed runner when mode is `"contributed"`
- `_evaluate()` dispatches to contributed evaluator before built-in `evaluate()`
- `before_route`/`after_route` interceptors fire around `_route()` in `_execute_state()`

## Proposed Solution

### 1. New Attributes in `FSMExecutor.__init__()`

Add after `self._depth: int = 0` at `executor.py:125`:

```python
# Extension hook registries — populated by wire_extensions()
self._contributed_actions: dict[str, ActionRunner] = {}
self._contributed_evaluators: dict[str, Evaluator] = {}
self._interceptors: list[Any] = []
```

`Any` is already imported at `executor.py:19` — no new import needed.

### 2. Contributed Action Dispatch

**`_action_mode()` (lines 693–704)** — the method uses 4 sequential `if` statements:
- line 695: `if state.action_type == "mcp_tool":`
- line 697: `if state.action_type in ("prompt", "slash_command"):`
- line 699: `if state.action_type == "shell":` ← insert after this line
- lines 701–703: `/`-prefix heuristic
- line 704: fallthrough `return "shell"`

Insert after line 699:

```python
if state.action_type in self._contributed_actions:
    return "contributed"
```

**`_run_action()` (lines 431–446)** — current dispatch: `if action_mode == "mcp_tool":` at line 431, `else:` at line 440. Convert to ternary:

```python
elif action_mode == "contributed":
    runner = self._contributed_actions[state.action_type]
    result = runner.run(
        action,
        timeout=state.timeout or self.fsm.default_timeout or 3600,
        is_slash_command=False,
        on_output_line=_on_line,
    )
else:  # prompt / shell — unchanged
    result = self.action_runner.run(...)
```

### 3. Contributed Evaluator Dispatch

**`_evaluate()` (explicit path, lines 598–629)** — insert contributed evaluator check **before line 608** (`llm_structured` guard), demoting the existing `if` to `elif`:

```python
if state.evaluate.type in self._contributed_evaluators:
    result = self._contributed_evaluators[state.evaluate.type](
        state.evaluate, eval_input,
        action_result.exit_code if action_result else 0,
        ctx,
    )
elif state.evaluate.type == "llm_structured" and not self.fsm.llm.enabled:  # was 'if'
    result = EvaluationResult(
        verdict="error",
        details={"error": "LLM evaluation disabled via --no-llm"},
    )
else:
    result = evaluate(...)  # unchanged
```

Do NOT apply to the default path (lines 561–596, `state.evaluate is None`).

### 4. `before_route` / `after_route` Interceptor Dispatch

Refactor `executor.py:404–405` (the single `_route()` call site in `_execute_state()`):

```python
# executor.py:404–405 (after modification)
verdict = eval_result.verdict if eval_result else "yes"
route_ctx = RouteContext(
    state_name=self.current_state, state=state, verdict=verdict,
    action_result=action_result, eval_result=eval_result,
    ctx=ctx, iteration=self.iteration,
)
# before_route interceptors
for interceptor in self._interceptors:
    if hasattr(interceptor, "before_route"):
        decision = interceptor.before_route(route_ctx)
        if isinstance(decision, RouteDecision):
            if decision.next_state is None:
                return None   # veto
            return decision.next_state   # redirect — bypass _route()
# Core routing
next_state = self._route(state, verdict, ctx)
# after_route interceptors
for interceptor in self._interceptors:
    if hasattr(interceptor, "after_route"):
        interceptor.after_route(route_ctx)
return next_state
```

**Bypass paths that intentionally skip interceptors** (do NOT add dispatch here):
- `executor.py:355`: `return self._execute_sub_loop(...)` — sub-loop
- `executor.py:378`: `return interpolate(state.next, ctx)` — unconditional `next:` transition

## Integration Map

### Files to Modify

- `scripts/little_loops/fsm/executor.py`
  - `__init__()` after line 125: add three new attributes
  - `_action_mode()` after line 699: add contributed check
  - `_run_action()` lines 431–446: add `elif "contributed"` branch
  - `_evaluate()` before line 608: add contributed evaluator check
  - `_execute_state()` lines 404–405: add interceptor dispatch wrapper

### Imports Needed

- `RouteContext`, `RouteDecision` from `scripts/little_loops/fsm/types.py` (added by FEAT-983)
- `Evaluator` type alias from `scripts/little_loops/fsm/types.py` (added by FEAT-983)
- `ActionRunner` already imported via `from little_loops.fsm.runners import ActionRunner` at line 36
- `Any` already imported at line 19

### Dependent Files (read-only — no changes needed)

- `scripts/little_loops/fsm/persistence.py` — `PersistentExecutor` inherits new attributes transparently
- `scripts/little_loops/cli/loop/testing.py` — imports `FSMExecutor`; no change required
- `scripts/little_loops/fsm/runners.py` — canonical home of `ActionRunner` Protocol

## Verification

After implementation, verify these existing tests still pass without modification:

- `scripts/tests/test_fsm_executor.py:234–366` — `TestActionType`; at-risk if contributed check intercepts known type strings (insert after the three existing checks)
- `scripts/tests/test_fsm_executor.py:369–532` — `TestActionTypeMcpTool`; at-risk if `if/elif/else` restructuring disturbs the `mcp_tool` branch
- `scripts/tests/test_ll_loop_execution.py:889–1097` — 5 direct `_evaluate()` calls; pass only if `_contributed_evaluators = {}` in `__init__()`

## Acceptance Criteria

- [ ] `_contributed_actions`, `_contributed_evaluators`, `_interceptors` initialized in `FSMExecutor.__init__()`
- [ ] `_action_mode()` returns `"contributed"` when `state.action_type` is in `_contributed_actions`
- [ ] `_run_action()` dispatches to contributed runner when mode is `"contributed"`
- [ ] `_evaluate()` calls contributed evaluator before `evaluate()` when type is in `_contributed_evaluators`
- [ ] `before_route` interceptors fire before `_route()` with correct `RouteContext`; veto returns `None`; redirect bypasses `_route()`
- [ ] `after_route` interceptors fire after `_route()` returns
- [ ] Existing action/evaluator dispatch paths unchanged when no contributed types registered
- [ ] `state.next:` and sub-loop branches do NOT fire interceptors
- [ ] All three existing test suites (TestActionType, TestActionTypeMcpTool, direct _evaluate() calls) pass

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small-Medium — surgical edits to 5 specific locations in executor.py
- **Risk**: High — interceptors in the execution path; subtle bugs can break unrelated loop runs
- **Depends On**: FEAT-983 (Protocol and type definitions for RouteContext, RouteDecision, Evaluator)
- **Blocks**: FEAT-988 (tests + wiring), FEAT-985 (wire_extensions())

## Labels

`feature`, `fsm`, `executor`, `extension-hooks`, `decomposed`

## Status

**Open** | Created: 2026-04-07 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/3f3aa3c7-ca33-4c8b-b435-c5b746906130.jsonl`

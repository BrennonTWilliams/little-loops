---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 85
---

# FEAT-984: FSMExecutor Hook Dispatch for Contributed Actions, Evaluators, and Route Interceptors

## Summary

Extend `FSMExecutor` to dispatch to contributed action types, contributed evaluators, and `before_route`/`after_route` interceptors. Adds `_contributed_actions`, `_contributed_evaluators`, and `_interceptors` attributes, then wires them into the existing dispatch paths in `_action_mode()`, `_run_action()`, and `_evaluate()`.

## Parent Issue

Decomposed from FEAT-915: Bidirectional Extension Hooks with Interceptors and Contributed Actions

## Context

FEAT-983 defines the Protocol and type foundations. This issue implements the FSM executor changes needed to actually dispatch to the registered extensions at runtime. `wire_extensions()` upgrade (FEAT-985) populates these registries; this issue only needs to define them and use them.

## Current Behavior

`FSMExecutor` has no concept of contributed action types or evaluators. `_action_mode()` uses a hardcoded `if/elif` chain. Route interceptors do not exist.

## Expected Behavior

- `FSMExecutor.__init__()` initializes three new attributes
- `_action_mode()` checks `_contributed_actions` before fallback
- `_run_action()` dispatches to contributed runner when mode is `"contributed"`
- `_evaluate()` dispatches to contributed evaluator before `evaluate()`
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

Add `Any` to existing `from typing import ...` import in `executor.py`.

### 2. Contributed Action Dispatch

**`_action_mode()` (line 701)** — add after `if state.action_type == "shell": return "shell"` (line 697) and before the `/`-prefix heuristic (line 699):

```python
if state.action_type in self._contributed_actions:
    return "contributed"
```

**`_run_action()` (lines 428–443)** — current dispatch is binary (`if "mcp_tool" ... else ...`). Convert to ternary by inserting `elif` before the existing `else`:

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

**`_evaluate()` (lines 605–616)** — insert contributed evaluator check **before line 605** (the `llm_structured`/`--no-llm` guard), demoting the existing `if` to `elif`:

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

### 4. `before_route` / `after_route` Interceptor Dispatch

**Do NOT add dispatch inside `_route()` itself** — it has 8 return sites. Instead, refactor `executor.py:400-402` (the single call site in `_execute_state()`) to capture the return value and wrap with interceptor calls:

```python
# executor.py:400-402 (after modification)
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

Note: `before_route` redirect returns `decision.next_state` directly as `next_state` (bypasses `_route()` entirely — it is a direct state name, not a new verdict).

### Bypass Paths That Intentionally Skip Interceptors

`before_route`/`after_route` dispatch only fires on the evaluate-then-route path:
- Line 355: `return self._execute_sub_loop(...)` — sub-loop (no interception; child executor handles routing)
- Line 378: `return interpolate(state.next, ctx)` — unconditional `next:` transition (deterministic, no interception needed)

Do NOT add interceptor dispatch to these branches.

## Integration Map

### Files to Modify
- `scripts/little_loops/fsm/executor.py`
  - `__init__()` after line 125: add three new attributes
  - `_action_mode()` after line 697: add contributed check
  - `_run_action()` lines 428–443: add `elif "contributed"` branch
  - `_evaluate()` before line 605: add contributed evaluator check
  - `_execute_state()` lines 400–402: add interceptor dispatch wrapper

### Dependent Files (Callers/Importers)
- `scripts/little_loops/fsm/__init__.py` — import `RouteContext`, `RouteDecision` from executor (or types.py); these are needed in executor.py at definition time
- `scripts/little_loops/fsm/types.py` — `Evaluator` alias (defined in FEAT-983); imported by executor

### Tests
- `scripts/tests/test_fsm_executor.py` — existing `MockActionRunner` at lines 26–86; add contributed action/evaluator dispatch tests using same mock pattern
- `scripts/tests/test_fsm_evaluators.py` — add contributed evaluator registration/dispatch tests

## Acceptance Criteria

- [ ] `_contributed_actions`, `_contributed_evaluators`, `_interceptors` initialized in `FSMExecutor.__init__()`
- [ ] `_action_mode()` returns `"contributed"` when `state.action_type` is in `_contributed_actions`
- [ ] `_run_action()` dispatches to contributed runner when mode is `"contributed"`
- [ ] `_evaluate()` calls contributed evaluator before `evaluate()` when type is in `_contributed_evaluators`
- [ ] `before_route` interceptors fire before `_route()` with correct `RouteContext`; veto returns `None`; redirect bypasses `_route()`
- [ ] `after_route` interceptors fire after `_route()` returns
- [ ] Existing action/evaluator dispatch paths unchanged when no contributed types registered
- [ ] `state.next:` and sub-loop branches do NOT fire interceptors

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Medium — touches core execution path, multiple methods
- **Risk**: High — interceptors in the execution path; subtle bugs can break unrelated loop runs
- **Depends On**: FEAT-983 (Protocol and type definitions)
- **Blocks**: FEAT-985 (needs executor attributes to exist before wiring)

## Status

**Open** | Created: 2026-04-07 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b2501d7-f66b-4a19-80a6-6fecea4283e8.jsonl`

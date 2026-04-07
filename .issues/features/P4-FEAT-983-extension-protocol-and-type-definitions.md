---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 90
---

# FEAT-983: Extension Protocol and Type Definitions

## Summary

Define the foundational type system for bidirectional extension hooks: `InterceptorExtension`, `ActionProviderExtension`, and `EvaluatorProviderExtension` protocols; `RouteContext` and `RouteDecision` dataclasses; and the `Evaluator` type alias. Export all new types from the public `__init__.py` files.

## Parent Issue

Decomposed from FEAT-915: Bidirectional Extension Hooks with Interceptors and Contributed Actions

## Context

FEAT-911 implemented observe-only extensions (`LLExtension.on_event()`). This child issue establishes the type foundations required before any dispatch or wiring can be added to the FSM executor or `wire_extensions()`. All other FEAT-915 child issues depend on the types defined here.

## Current Behavior

No `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`, `RouteContext`, `RouteDecision`, or `Evaluator` type exist in the codebase.

## Expected Behavior

- Three independent Protocol classes defined in `extension.py`
- Two dataclasses (`RouteContext`, `RouteDecision`) defined
- `Evaluator` type alias added to `fsm/types.py`
- All new types exported from `scripts/little_loops/__init__.py` and `scripts/little_loops/fsm/__init__.py`

## Proposed Solution

### 1. Add Protocols to `extension.py`

Insert after `LLExtension` definition at `extension.py:50`. Use independent `Protocol` classes (NOT `InterceptorExtension(LLExtension, Protocol)`). Model after `LLExtension:28-50` (`@runtime_checkable`, attribute + method pattern):

```python
class InterceptorExtension(Protocol):
    def before_route(self, context: RouteContext) -> RouteDecision | None: ...
    def after_route(self, context: RouteContext) -> None: ...
    def before_issue_close(self, info: IssueInfo) -> bool | None: ...

class ActionProviderExtension(Protocol):
    def provided_actions(self) -> dict[str, ActionRunner]: ...

class EvaluatorProviderExtension(Protocol):
    def provided_evaluators(self) -> dict[str, Evaluator]: ...
```

No `isinstance()` checks against Protocol types exist in production code — detection is done via `hasattr()`/`getattr()` in `wire_extensions()`, same as `event_filter` at `extension.py:165`.

### 2. Define `RouteContext` and `RouteDecision` Dataclasses

Add to `executor.py` (or `fsm/types.py`), before `FSMExecutor` class:

```python
@dataclass
class RouteContext:
    """Context passed to before_route / after_route interceptors."""
    state_name:    str                       # executor.current_state — executor.py:92
    state:         StateConfig               # route tables and shortcuts — schema.py:180
    verdict:       str                       # routing key: "yes"/"no"/"error"/"partial"/"blocked"/custom
    action_result: ActionResult | None       # None when state has no action field — types.py:52
    eval_result:   EvaluationResult | None   # None when state has no evaluator — evaluators.py:40
    ctx:           InterpolationContext      # ctx.result pre-populated at route time — interpolation.py:37
    iteration:     int                       # 1-based iteration counter — executor.py:96

@dataclass
class RouteDecision:
    """Returned by before_route to redirect or veto a routing transition."""
    next_state: str | None  # str → redirect; None → veto
```

Return semantics for `before_route`:
- `None` (implicit) → passthrough — routing proceeds normally through `_route()`
- `RouteDecision("other-state")` → bypass `_route()`, use `"other-state"` directly as `next_state`
- `RouteDecision(None)` → veto → `_execute_state()` returns `None` → `_finish("error", ...)`

Return semantics for `before_issue_close`:
- `None` (implicit) → passthrough
- `False` → veto (consistent with all lifecycle functions returning `-> bool`)

### 3. Add `Evaluator` Type Alias to `fsm/types.py`

Add after `EventCallback = Callable[[dict[str, Any]], None]` at `fsm/types.py:70`:

```python
Evaluator = Callable[["EvaluateConfig", str, int, "InterpolationContext"], "EvaluationResult"]
```

Use forward-reference strings to avoid circular imports (`EvaluateConfig` in `schema.py`, `EvaluationResult` in `evaluators.py`, `InterpolationContext` in `interpolation.py`). Parameter order matches `evaluate()` call signature: `config`, `output`, `exit_code`, `context`.

### 4. Update `__init__.py` Exports

**`scripts/little_loops/__init__.py`** — add to `from little_loops.extension import (...)` block and to `__all__` under `# extensions`:
- `InterceptorExtension`
- `ActionProviderExtension`
- `EvaluatorProviderExtension`

**`scripts/little_loops/fsm/__init__.py`** — add to imports and to `__all__` (lines 133–178):
- `RouteContext`
- `RouteDecision`
- `Evaluator`

## Integration Map

### Files to Modify
- `scripts/little_loops/extension.py` — add three Protocol classes after `LLExtension` at line 50
- `scripts/little_loops/fsm/executor.py` — add `RouteContext` and `RouteDecision` dataclasses before `FSMExecutor`
- `scripts/little_loops/fsm/types.py` — add `Evaluator` alias after line 70
- `scripts/little_loops/__init__.py` — export new Protocol types
- `scripts/little_loops/fsm/__init__.py` — export `RouteContext`, `RouteDecision`, `Evaluator`

### Similar Patterns
- `scripts/little_loops/extension.py:28-50` — `LLExtension` with `@runtime_checkable` — follow for new Protocol classes
- `scripts/little_loops/fsm/runners.py:27-48` — `ActionRunner` Protocol (without `@runtime_checkable`)
- `scripts/little_loops/fsm/types.py:70` — `EventCallback = Callable[...]` — follow for `Evaluator` alias

### Tests
- `scripts/tests/test_extension.py` — add structural protocol compliance tests for `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`

## Acceptance Criteria

- [ ] `InterceptorExtension` Protocol defined in `extension.py` with `before_route`, `after_route`, `before_issue_close` methods
- [ ] `ActionProviderExtension` Protocol defined with `provided_actions()` returning `dict[str, ActionRunner]`
- [ ] `EvaluatorProviderExtension` Protocol defined with `provided_evaluators()` returning `dict[str, Evaluator]`
- [ ] `RouteContext` and `RouteDecision` defined as `@dataclass` with correct field types
- [ ] `Evaluator` type alias added to `fsm/types.py` after `EventCallback` (line 70)
- [ ] All new types exported from `__init__.py` files
- [ ] Existing `NoopLoggerExtension` and observe-only extension tests continue to pass

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small — type definitions only, no logic changes
- **Risk**: Low — additive only, no existing behavior changed
- **Depends On**: FEAT-911 (completed)
- **Blocks**: FEAT-984, FEAT-985

## Status

**Open** | Created: 2026-04-07 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b2501d7-f66b-4a19-80a6-6fecea4283e8.jsonl`

---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 93
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

## Use Case

**Who**: A developer building a third-party little-loops extension

**Context**: When they want to intercept FSM routing decisions, contribute custom actions, or provide custom evaluators to a loop

**Goal**: Implement one or more of the new Protocol types on their extension class without inheriting from `LLExtension`

**Outcome**: `wire_extensions()` detects the implemented protocols via structural typing (`hasattr()`) and automatically wires up the extension's interceptors, actions, and evaluators — no explicit registration or base class required

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
    iteration:     int                       # 1-based iteration counter — executor.py:93

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
- `scripts/little_loops/extension.py` — add three Protocol classes after `LLExtension` at line 49; add `from little_loops.issue_parser import IssueInfo` to imports (required by `before_issue_close` signature — `IssueInfo` is defined at `issue_parser.py:202`, not currently imported in `extension.py`)
- `scripts/little_loops/fsm/executor.py` — add `RouteContext` and `RouteDecision` dataclasses before `FSMExecutor`
- `scripts/little_loops/fsm/types.py` — add `Evaluator` alias after line 70
- `scripts/little_loops/__init__.py` — export new Protocol types (add to `from little_loops.extension import (...)` block at lines 9–14 and to `__all__` at lines 39–43)
- `scripts/little_loops/fsm/__init__.py` — export `RouteContext`, `RouteDecision`, `Evaluator`; add to `from little_loops.fsm.executor import (...)` block at lines 86–92

### Similar Patterns
- `scripts/little_loops/extension.py:28-49` — `LLExtension` with `@runtime_checkable` — `LLExtension` uses this because it's checked via `isinstance()` elsewhere; the new protocols do NOT need `@runtime_checkable` since detection is via `hasattr()`/`getattr()` only
- `scripts/little_loops/fsm/runners.py:28-49` — `ActionRunner` Protocol (no `@runtime_checkable`) — **preferred model** for the new Protocol classes
- `scripts/little_loops/fsm/types.py:70` — `EventCallback = Callable[...]` — follow for `Evaluator` alias

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `scripts/little_loops/issue_parser.py:202` — `IssueInfo` dataclass definition. Must be imported in `extension.py` for `before_issue_close(self, info: IssueInfo)`. Add `from little_loops.issue_parser import IssueInfo` to `extension.py` imports.
- `scripts/little_loops/fsm/executor.py:93` — `self.iteration = 0` (initialized as 0; incremented to 1-based before `_execute_state()` is called).
- `scripts/little_loops/fsm/evaluators.py:40-50` — `EvaluationResult` dataclass fields: `verdict: str` (line 49), `details: dict[str, Any]` (line 50).
- `scripts/little_loops/extension.py:165` — `wire_extensions()` detection uses `getattr(ext, "event_filter", None)` exclusively — no `isinstance()` against Protocol types. New protocols must also be detected via `hasattr()`, not `isinstance()`, confirming `@runtime_checkable` is unnecessary on the new Protocols.
- `scripts/little_loops/fsm/__init__.py:86-92` — existing `from little_loops.fsm.executor import (...)` block already exports `ActionResult`, `ActionRunner`, `EventCallback`, `ExecutionResult`, `FSMExecutor`. `RouteContext` and `RouteDecision` join this block.
- `scripts/little_loops/__init__.py:9-14` — `from little_loops.extension import (...)` block; `39-43` — `# extensions` section of `__all__`. New Protocol names append to both.

### Tests
- `scripts/tests/test_extension.py` — add structural protocol compliance tests for `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_fsm_executor.py` — add `TestRouteContext` and `TestRouteDecision` dataclass tests (new types live in `executor.py`; follow `TestEvaluationResult` pattern in `test_fsm_evaluators.py:30-43`); test `next_state=None` veto case for `RouteDecision`
- `scripts/tests/test_extension.py` — add smoke import test verifying no circular import from `extension.py → issue_parser.py` chain (new `from little_loops.issue_parser import IssueInfo` creates a previously non-existent transitive dependency for all `extension.py` callers)

### Dependent Files (Callers/Importers)
- N/A — additive only; no existing callers until FEAT-984 and FEAT-985 add dispatch wiring

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:5067` — `# little_loops.extension` section and Quick Import block (lines 3594–3610) will not include the three new Protocol types after FEAT-983; `docs/reference/API.md:3583` — `little_loops.fsm.types` description lists only `ExecutionResult, ActionResult` (misses `Evaluator`). **Low priority — defer doc updates to FEAT-984/985** when the types gain behavioral context.
- `docs/ARCHITECTURE.md:454-458` — extension component table lists only `LLExtension`, `ExtensionLoader`, `NoopLoggerExtension`, `wire_extensions`; three new Protocol classes absent. Narrative at line 450 covers only `on_event()`. **Low priority — defer to FEAT-984/985.**
- `docs/reference/CONFIGURATION.md:606` — extensions key description states "Extensions implement the `LLExtension` protocol"; becomes incomplete. **Low priority — defer to FEAT-984/985.**

### Configuration
- N/A

## Implementation Steps

1. Add `from little_loops.issue_parser import IssueInfo` to `extension.py` imports (required by `InterceptorExtension.before_issue_close` signature)
2. Add `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension` Protocol classes to `extension.py` after `LLExtension` (ends at line 49); model after `ActionRunner` in `fsm/runners.py:28-49` — no `@runtime_checkable`
3. Add `RouteContext` and `RouteDecision` dataclasses to `fsm/executor.py` before `FSMExecutor` (line 52)
4. Add `Evaluator` type alias to `fsm/types.py` after `EventCallback` (line 70)
5. Export Protocol types from `scripts/little_loops/__init__.py` (import block lines 9–14, `__all__` lines 39–43)
6. Export `RouteContext`, `RouteDecision`, `Evaluator` from `scripts/little_loops/fsm/__init__.py` (executor import block lines 86–92, `__all__` lines 133–178)
7. Add structural protocol compliance tests in `scripts/tests/test_extension.py` (follow pattern at `test_extension.py:22-32`)
8. Run `python -m pytest scripts/tests/test_extension.py -v` to verify no regressions

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

9. Add `TestRouteContext` and `TestRouteDecision` to `scripts/tests/test_fsm_executor.py` — test construction with all required fields, `action_result=None` / `eval_result=None` optional cases, and `RouteDecision(None)` veto case (follow `TestEvaluationResult` in `test_fsm_evaluators.py:30-43`)
10. Add smoke import assertion to `scripts/tests/test_extension.py` — verify `from little_loops import InterceptorExtension` succeeds without circular import error (new `extension.py → issue_parser` import chain)

## Acceptance Criteria

- [x] `InterceptorExtension` Protocol defined in `extension.py` with `before_route`, `after_route`, `before_issue_close` methods
- [x] `ActionProviderExtension` Protocol defined with `provided_actions()` returning `dict[str, ActionRunner]`
- [x] `EvaluatorProviderExtension` Protocol defined with `provided_evaluators()` returning `dict[str, Evaluator]`
- [x] `RouteContext` and `RouteDecision` defined as `@dataclass` with correct field types
- [x] `Evaluator` type alias added to `fsm/types.py` after `EventCallback` (line 70)
- [x] All new types exported from `__init__.py` files
- [x] Existing `NoopLoggerExtension` and observe-only extension tests continue to pass

## API/Interface

New types exported from public `__init__.py` files. Signatures are specified in full in Proposed Solution.

**`scripts/little_loops/extension.py`** — three Protocol classes:
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

**`scripts/little_loops/fsm/executor.py`** — two dataclasses:
```python
@dataclass
class RouteContext:
    state_name: str; state: StateConfig; verdict: str
    action_result: ActionResult | None; eval_result: EvaluationResult | None
    ctx: InterpolationContext; iteration: int

@dataclass
class RouteDecision:
    next_state: str | None  # str → redirect; None → veto
```

**`scripts/little_loops/fsm/types.py`** — one type alias:
```python
Evaluator = Callable[["EvaluateConfig", str, int, "InterpolationContext"], "EvaluationResult"]
```

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small — type definitions only, no logic changes
- **Risk**: Low — additive only, no existing behavior changed
- **Depends On**: FEAT-911 (completed)
- **Blocks**: FEAT-984, FEAT-985

## Labels

`feature`, `extension`, `type-definitions`

## Status

**Completed** | Created: 2026-04-07 | Resolved: 2026-04-07 | Priority: P4

## Resolution

Implemented all type definitions as specified. Three Protocol classes (`InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`) added to `extension.py`; `RouteContext` and `RouteDecision` dataclasses added to `fsm/executor.py`; `Evaluator` type alias added to `fsm/types.py` with `TYPE_CHECKING` imports to avoid circular imports. All types exported from both `__init__.py` files. 4422 tests pass.

## Session Log
- `/ll:manage-issue` - 2026-04-07T00:00:00 - implemented FEAT-983 — extension protocol and type definitions
- `/ll:ready-issue` - 2026-04-08T02:16:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/de2f2afe-3578-4944-87f3-ea4946505e3f.jsonl`
- `/ll:confidence-check` - 2026-04-07T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fed4a5e7-1236-4d5f-b7d7-a7de0154ff53.jsonl`
- `/ll:wire-issue` - 2026-04-07T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/memory/MEMORY.md`
- `/ll:refine-issue` - 2026-04-07T23:49:42 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8f7a07ce-ed95-46ff-8782-94f65304e6aa.jsonl`
- `/ll:format-issue` - 2026-04-07T23:46:09 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b13c9144-bc31-4872-936b-dae656e662c4.jsonl`
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b2501d7-f66b-4a19-80a6-6fecea4283e8.jsonl`

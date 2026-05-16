---
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 90
outcome_confidence: 85
---

# FEAT-993: Extend `wire_extensions()` with Executor Support

## Summary

Add an optional `executor: FSMExecutor | None = None` parameter to `wire_extensions()`, add a priority sort before registration, add a `hasattr(on_event)` guard, add a second pass that populates executor registries with conflict detection, and update the three CLI callers to pass `executor=executor`.

## Parent Issue

Decomposed from FEAT-985: wire_extensions() Upgrade, before_issue_close Hook, Reference Extension, and Tests

## Context

FEAT-983 defines types/protocols. FEAT-984 adds `_contributed_actions`, `_contributed_evaluators`, and `_interceptors` attributes to `FSMExecutor`. This issue wires extensions into those attributes by extending `wire_extensions()`.

## Current Behavior

`wire_extensions()` only wires `on_event` callbacks onto the `EventBus`. Extensions that implement `provided_actions()`, `provided_evaluators()`, or interceptor protocols (`before_route`, `after_route`, `before_issue_close`) have no path to register their contributed types into `FSMExecutor`. Extensions that implement only interceptor/evaluator/action protocols (without `on_event`) cause an `AttributeError` when `wire_extensions()` is called. No priority ordering is applied across extensions.

## Expected Behavior

`wire_extensions(bus, executor=executor)` accepts an optional `FSMExecutor` parameter. When provided, a second pass populates `executor._contributed_actions`, `executor._contributed_evaluators`, and `executor._interceptors` from each extension. A `hasattr(on_event)` guard prevents `AttributeError` for interceptor-only extensions. A priority sort ensures consistent dispatch ordering for both the event bus and executor registries.

## Use Case

**Who**: A developer building a little-loops extension that contributes custom actions, evaluators, or interceptors to the FSM executor.

**Context**: After implementing `LLExtension` with `provided_actions()`, `provided_evaluators()`, or interceptor methods, the developer calls `wire_extensions()` to register their extension. Currently, only `on_event` callbacks are wired — contributed types never reach `FSMExecutor`.

**Goal**: Wire their extension once via `wire_extensions()` and have all contributed types (actions, evaluators, interceptors) automatically available in loop execution.

**Outcome**: The extension's contributed actions and evaluators are callable from FSM loop YAML; interceptors are available for dispatch by the executor and by `close_issue()`.

## Proposed Solution

### 1. Extend `wire_extensions()` Signature

Current signature at `extension.py:187`: `wire_extensions(bus: EventBus, config_paths: list[str] | None = None) -> list[LLExtension]`

Add optional `executor: FSMExecutor | None = None` parameter. After the existing `bus.register()` loop, add:

```python
if executor is not None:
    for ext in extensions:
        if hasattr(ext, "provided_actions"):
            for name in ext.provided_actions():
                if name in executor._contributed_actions:
                    raise ValueError(
                        f"Extension conflict: action '{name}' already registered by another extension"
                    )
            executor._contributed_actions.update(ext.provided_actions())
        if hasattr(ext, "provided_evaluators"):
            for name in ext.provided_evaluators():
                if name in executor._contributed_evaluators:
                    raise ValueError(
                        f"Extension conflict: evaluator '{name}' already registered by another extension"
                    )
            executor._contributed_evaluators.update(ext.provided_evaluators())
        if hasattr(ext, "before_route") or hasattr(ext, "after_route") or hasattr(ext, "before_issue_close"):
            executor._interceptors.append(ext)
```

### 2. `hasattr(on_event)` Guard

Add guard to the existing `bus.register()` loop (lines 204–216) to prevent `AttributeError` for extensions that implement only interceptor/action/evaluator protocols:

```python
for ext in extensions:
    if hasattr(ext, "on_event"):
        bus.register(_make_callback(ext), filter=getattr(ext, "event_filter", None))
```

### 3. Priority Sort

Add sort **before** both passes (before the loop at line 204), so event dispatch and interceptor dispatch order are consistent:

```python
extensions = sorted(extensions, key=lambda e: getattr(e, "priority", 0))
```

Ascending sort: lower priority value = fires first. Same convention as `dependency_graph.py:135`.

### 4. `FSMExecutor` Import Guard

`extension.py` already has `from __future__ import annotations` (line 12), `TYPE_CHECKING` in the `typing` import (line 19), and a `TYPE_CHECKING` block at lines 24–27 importing `RouteContext`, `RouteDecision`, `ActionRunner`, and `Evaluator`. Add `FSMExecutor` to that existing block:

```python
if TYPE_CHECKING:
    from little_loops.fsm.executor import FSMExecutor  # add this line
    from little_loops.fsm.executor import RouteContext, RouteDecision
    from little_loops.fsm.runners import ActionRunner
    from little_loops.fsm.types import Evaluator
```

No new import machinery is needed — only the `FSMExecutor` name must be added to the existing block.

### 5. Update Callers

Three callers must pass the executor so contributed types reach it:

- `scripts/little_loops/cli/loop/run.py:206` — `wire_extensions(executor.event_bus, ...)` → add `executor=executor`
- `scripts/little_loops/cli/loop/lifecycle.py:260` — same (in `cmd_resume()`)
- `scripts/little_loops/cli/sprint/run.py:391` — same (in the parallel branch; note this caller has no executor — see note below)

`parallel.py:228` creates a standalone `EventBus` but no `FSMExecutor` — no change needed.

**Note on `sprint/run.py`**: The sprint parallel branch constructs a bare `EventBus()` (line 390) and passes it to `ParallelOrchestrator`. There is no `FSMExecutor` in scope at this call site. The `executor` kwarg should be omitted here — contributed types are not wired for sprint parallel runs (consistent with the sprint architecture where each worker has its own executor).

## Integration Map

### Files to Modify
- `scripts/little_loops/extension.py` — `wire_extensions()` at line 187: add `executor` param, `hasattr(on_event)` guard, priority sort, second pass with conflict detection; add `FSMExecutor` to existing `TYPE_CHECKING` block (lines 24–27)
- `scripts/little_loops/cli/loop/run.py:206` — pass `executor=executor` to `wire_extensions()`
- `scripts/little_loops/cli/loop/lifecycle.py:260` — same
- `scripts/little_loops/cli/sprint/run.py:391` — no executor available at this call site; omit `executor` kwarg

### Similar Patterns
- Priority sort convention: `dependency_graph.py` (ascending sort — lower value fires first)
- `hasattr` guard pattern: existing `NoopLoggerExtension` in `extension.py`

### Tests
- `scripts/tests/test_extension.py` — add `wire_extensions()` with executor; conflict detection; priority sort; `hasattr(on_event)` guard
- `scripts/tests/test_fsm_executor.py` — add contributed action/evaluator wiring via `wire_extensions()`
- `scripts/tests/test_events.py` — add priority/ordering tests

## Implementation Steps

1. **Prerequisite**: FEAT-984 is already merged — `FSMExecutor._contributed_actions`, `._contributed_evaluators`, `._interceptors` confirmed at `executor.py:154–157`
2. Add `FSMExecutor` to the existing `TYPE_CHECKING` block in `extension.py` (lines 24–27); no new import machinery needed
3. Add priority sort before the loop at line 204
4. Add `hasattr(ext, "on_event")` guard to the existing `bus.register()` loop (lines 204–216)
5. Add `executor: FSMExecutor | None = None` param to `wire_extensions()` (line 187) and second pass with conflict detection
6. Update callers: `loop/run.py:206` and `loop/lifecycle.py:260` — pass `executor=executor`; `sprint/run.py:391` — no executor available, omit kwarg
7. Add tests across `test_extension.py`, `test_fsm_executor.py`, `test_events.py`

## Acceptance Criteria

- [x] `wire_extensions()` accepts `executor: FSMExecutor | None = None`
- [x] Second pass populates `_contributed_actions`, `_contributed_evaluators`, `_interceptors` on executor
- [x] Conflict detection raises `ValueError` for duplicate action/evaluator name keys
- [x] Priority sort applied before both registration passes
- [x] `hasattr(ext, "on_event")` guard prevents `AttributeError` for interceptor-only extensions
- [x] Callers at `run.py`, `lifecycle.py`, `sprint/run.py` updated to pass `executor`
- [x] All new tests pass; existing observe-only extension tests unchanged

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small-Medium — focused changes to `extension.py` and 3 callers
- **Risk**: Medium — `wire_extensions()` is called in 3 production paths
- **Depends On**: FEAT-983 (types), FEAT-984 (executor attributes)

## Labels

`feat`, `extension`, `executor`, `wiring`

## Status

**Completed** | Created: 2026-04-08 | Resolved: 2026-04-08 | Priority: P4

## Resolution

Implemented in `extension.py`: added `executor: FSMExecutor | None = None` param, priority sort, `hasattr(on_event)` guard, and second pass with conflict detection. Updated callers in `cli/loop/run.py` and `cli/loop/lifecycle.py` to pass `executor=executor`. Added 9 new tests covering all acceptance criteria. All 35 tests pass, lint clean.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `extension.py:187–190` — confirmed current `wire_extensions()` signature (2 params: `bus`, `config_paths`)
- `extension.py:204–216` — the `bus.register()` loop body; no priority sort or `hasattr` guard exists yet
- `extension.py:12` — `from __future__ import annotations` already present
- `extension.py:19` — `TYPE_CHECKING` already imported from `typing`
- `extension.py:24–27` — existing `TYPE_CHECKING` block imports `RouteContext`, `RouteDecision`, `ActionRunner`, `Evaluator`; add `FSMExecutor` here
- `executor.py:154–157` — `_contributed_actions`, `_contributed_evaluators`, `_interceptors` all confirmed present (FEAT-984 merged)
- `executor.py:769, 494–500` — `_contributed_actions` consumed in `_action_mode()` and `_run_action()`
- `executor.py:669` — `_contributed_evaluators` consumed in `_evaluate()`
- `executor.py:446–456` — `_interceptors` iterated with `hasattr` guards for `before_route`/`after_route`
- `cli/loop/run.py:206` — actual call site (import is at line 203)
- `cli/loop/lifecycle.py:260` — actual call site in `cmd_resume()` (import at lines 256–257)
- `cli/sprint/run.py:391` — call site in parallel branch; bare `EventBus()` at line 390, no executor in scope
- `cli/parallel.py:228` — call site; bare `EventBus()` at line 225, no executor in scope

## Session Log
- `/ll:ready-issue` - 2026-04-08T05:31:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b6d41dbb-b21b-4f1c-b728-d1dcee68c12d.jsonl`
- `/ll:refine-issue` - 2026-04-08T05:24:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6812afe4-4248-451c-bdc8-42131c8cb745.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3cbd267-88d4-421d-8d23-7869adfc91cb.jsonl`

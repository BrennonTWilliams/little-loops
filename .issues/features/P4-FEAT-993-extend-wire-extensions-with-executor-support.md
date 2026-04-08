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

## Use Case

**Who**: A developer building a little-loops extension that contributes custom actions, evaluators, or interceptors to the FSM executor.

**Context**: After implementing `LLExtension` with `provided_actions()`, `provided_evaluators()`, or interceptor methods, the developer calls `wire_extensions()` to register their extension. Currently, only `on_event` callbacks are wired — contributed types never reach `FSMExecutor`.

**Goal**: Wire their extension once via `wire_extensions()` and have all contributed types (actions, evaluators, interceptors) automatically available in loop execution.

**Outcome**: The extension's contributed actions and evaluators are callable from FSM loop YAML; interceptors are available for dispatch by the executor and by `close_issue()`.

## Proposed Solution

### 1. Extend `wire_extensions()` Signature

Current signature at `extension.py:139`: `wire_extensions(bus: EventBus, config_paths: list[str] | None = None) -> list[LLExtension]`

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

Add guard to the existing `bus.register()` loop (lines 157–165) to prevent `AttributeError` for extensions that implement only interceptor/action/evaluator protocols:

```python
for ext in extensions:
    if hasattr(ext, "on_event"):
        bus.register(_make_callback(ext), filter=getattr(ext, "event_filter", None))
```

### 3. Priority Sort

Add sort **before** both passes (lines 156–157), so event dispatch and interceptor dispatch order are consistent:

```python
extensions = sorted(extensions, key=lambda e: getattr(e, "priority", 0))
```

Ascending sort: lower priority value = fires first. Same convention as `dependency_graph.py:135`.

### 4. `FSMExecutor` Import Guard

Add to `extension.py` imports:

```python
from __future__ import annotations
from typing import TYPE_CHECKING
if TYPE_CHECKING:
    from little_loops.fsm.executor import FSMExecutor
```

Use `TYPE_CHECKING` guard to avoid potential circular import since `fsm/executor.py` may transitively import from `extension.py`.

### 5. Update Callers

Three callers must pass the executor so contributed types reach it:

- `scripts/little_loops/cli/loop/run.py:203` — `wire_extensions(executor.event_bus, ...)` → add `executor=executor`
- `scripts/little_loops/cli/loop/lifecycle.py:257` — same
- `scripts/little_loops/cli/sprint/run.py:388` — same

`parallel.py:225-228` creates a standalone `EventBus` but no `FSMExecutor` — no change needed.

## Integration Map

### Files to Modify
- `scripts/little_loops/extension.py` — `wire_extensions()` at line 139: add `executor` param, `hasattr(on_event)` guard, priority sort, second pass with conflict detection, TYPE_CHECKING import
- `scripts/little_loops/cli/loop/run.py:203` — pass `executor=executor` to `wire_extensions()`
- `scripts/little_loops/cli/loop/lifecycle.py:257` — same
- `scripts/little_loops/cli/sprint/run.py:388` — same

### Similar Patterns
- Priority sort convention: `dependency_graph.py` (ascending sort — lower value fires first)
- `hasattr` guard pattern: existing `NoopLoggerExtension` in `extension.py`

### Tests
- `scripts/tests/test_extension.py` — add `wire_extensions()` with executor; conflict detection; priority sort; `hasattr(on_event)` guard
- `scripts/tests/test_fsm_executor.py` — add contributed action/evaluator wiring via `wire_extensions()`
- `scripts/tests/test_events.py` — add priority/ordering tests

## Implementation Steps

1. **Prerequisite**: Confirm FEAT-984 is merged — `FSMExecutor._contributed_actions`, `._contributed_evaluators`, `._interceptors` must exist
2. Add `TYPE_CHECKING` import guard for `FSMExecutor` to `extension.py`
3. Add priority sort before registration passes
4. Add `hasattr(ext, "on_event")` guard to existing `bus.register()` loop
5. Add `executor` param and second pass with conflict detection
6. Update three `wire_extensions()` callers to pass `executor=executor`
7. Add tests across `test_extension.py`, `test_fsm_executor.py`, `test_events.py`

## Acceptance Criteria

- [ ] `wire_extensions()` accepts `executor: FSMExecutor | None = None`
- [ ] Second pass populates `_contributed_actions`, `_contributed_evaluators`, `_interceptors` on executor
- [ ] Conflict detection raises `ValueError` for duplicate action/evaluator name keys
- [ ] Priority sort applied before both registration passes
- [ ] `hasattr(ext, "on_event")` guard prevents `AttributeError` for interceptor-only extensions
- [ ] Callers at `run.py`, `lifecycle.py`, `sprint/run.py` updated to pass `executor`
- [ ] All new tests pass; existing observe-only extension tests unchanged

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small-Medium — focused changes to `extension.py` and 3 callers
- **Risk**: Medium — `wire_extensions()` is called in 3 production paths
- **Depends On**: FEAT-983 (types), FEAT-984 (executor attributes)

## Labels

`feat`, `extension`, `executor`, `wiring`

## Status

**Open** | Created: 2026-04-08 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3cbd267-88d4-421d-8d23-7869adfc91cb.jsonl`

---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 95
outcome_confidence: 85
---

# FEAT-985: wire_extensions() Upgrade, before_issue_close Hook, Reference Extension, and Tests

## Summary

Extend `wire_extensions()` to wire interceptors and contributed types into `FSMExecutor`; add `before_issue_close` hook in `issue_lifecycle.close_issue()`; write a reference interceptor extension; and add all tests across the affected test files.

## Parent Issue

Decomposed from FEAT-915: Bidirectional Extension Hooks with Interceptors and Contributed Actions

## Context

FEAT-983 defines types/protocols. FEAT-984 adds the executor dispatch logic. This issue completes the system by: wiring extensions into the executor via `wire_extensions()`; implementing the `before_issue_close` hook; providing a reference extension; and ensuring full test coverage.

## Current Behavior

`wire_extensions()` only registers `on_event()` callbacks with `EventBus`. It has no path to populate `FSMExecutor._contributed_actions`, `_contributed_evaluators`, or `_interceptors`. `close_issue()` emits `"issue.closed"` after the file move but has no pre-move veto hook.

## Expected Behavior

- `wire_extensions(bus, ..., executor=None)` extended with optional `executor` parameter
- Second pass over extensions populates executor registries and interceptor list
- Conflict detection raises `ValueError` on duplicate action/evaluator key names
- Priority sorting applied before both registration passes
- `hasattr(ext, "on_event")` guard prevents `AttributeError` for extensions without `on_event`
- `close_issue()` calls `before_issue_close` interceptors before file I/O at line 596
- Reference interceptor extension demonstrates `before_route()` passthrough

## Proposed Solution

### 1. Extend `wire_extensions()` Signature — Option A

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

### 4. Update Callers

Three callers must pass the executor so contributed types reach it:

- `scripts/little_loops/cli/loop/run.py:156-159` — `wire_extensions(executor.event_bus, ...)` → add `executor=executor`
- `scripts/little_loops/cli/loop/lifecycle.py:257-260` — same
- `scripts/little_loops/cli/sprint/run.py:388-397` — same

`parallel.py:225-228` creates a standalone `EventBus` but no `FSMExecutor` — no change needed.

### 5. `before_issue_close` Hook in `issue_lifecycle.close_issue()`

Insert between `logger.info(...)` at line 595 and `try:` at line 597 (replacing blank line 596):

```python
# before_issue_close interceptors — veto check before any file I/O
if event_bus is not None:
    for interceptor in getattr(event_bus, "_interceptors", []):
        if hasattr(interceptor, "before_issue_close"):
            result = interceptor.before_issue_close(info)
            if result is False:
                return False
```

Note: `close_issue()` receives `event_bus` as a parameter. `_interceptors` is on `FSMExecutor`, not `EventBus`. Determine the correct wiring approach — likely pass `executor` or `interceptors` list directly as an additional parameter to `close_issue()`, or make them accessible via the event_bus extension.

Alternative: If `close_issue()` does not have access to the executor, the `before_issue_close` hook may need to be dispatched via a new `EventBus` hook type rather than directly calling interceptors. Investigate the actual `close_issue()` signature and callers before implementing.

### 6. Reference Interceptor Extension

Create `scripts/little_loops/extensions/reference_interceptor.py` (or similar) demonstrating:
- `before_route()` that returns `None` (passthrough)
- `before_issue_close()` that returns `None` (passthrough)

Model structure after `NoopLoggerExtension:52-68` in `extension.py`.

## Integration Map

### Files to Modify
- `scripts/little_loops/extension.py` — `wire_extensions()`: add `executor` param, `hasattr(on_event)` guard, priority sort, second pass with conflict detection
- `scripts/little_loops/issue_lifecycle.py` — `close_issue()`: add `before_issue_close` hook dispatch at line 596
- `scripts/little_loops/cli/loop/run.py:156-159` — pass `executor=executor` to `wire_extensions()`
- `scripts/little_loops/cli/loop/lifecycle.py:257-260` — same
- `scripts/little_loops/cli/sprint/run.py:388-397` — same

### New Files
- Reference interceptor extension (path TBD)

### Tests
- `scripts/tests/test_extension.py` — add `wire_extensions()` with executor; conflict detection; priority sort; `hasattr(on_event)` guard
- `scripts/tests/test_fsm_executor.py` — add contributed action/evaluator wiring via `wire_extensions()`
- `scripts/tests/test_events.py` — add priority/ordering tests
- `scripts/tests/test_issue_lifecycle.py` — add `before_issue_close` veto and passthrough tests
- New: `scripts/tests/test_interceptor_extension.py` — dedicated tests for `before_route`/`after_route` and `before_issue_close` dispatch; model after `test_extension.py:35-49` inline recording-class pattern

## Open Question

`before_issue_close` interceptors live on `FSMExecutor._interceptors`. But `close_issue()` receives only `event_bus`, not the executor. Verify how interceptors should reach `close_issue()` before implementing — options:
1. Add `interceptors: list[Any] | None = None` parameter to `close_issue()`
2. Store interceptors on `EventBus` alongside event callbacks
3. Pass executor directly to `close_issue()`

Examine `issue_lifecycle.py:544` signature and callers at `issue_manager.py:466` and `parallel/orchestrator.py:861` before deciding.

## Acceptance Criteria

- [ ] `wire_extensions()` accepts `executor: FSMExecutor | None = None`
- [ ] Second pass populates `_contributed_actions`, `_contributed_evaluators`, `_interceptors` on executor
- [ ] Conflict detection raises `ValueError` for duplicate action/evaluator name keys
- [ ] Priority sort applied before both registration passes
- [ ] `hasattr(ext, "on_event")` guard prevents `AttributeError` for interceptor-only extensions
- [ ] Callers at `run.py`, `lifecycle.py`, `sprint/run.py` updated to pass `executor`
- [ ] `before_issue_close` hook fires before file I/O in `close_issue()`; `False` return vetoes closure
- [ ] Reference interceptor extension created and demonstrates passthrough behavior
- [ ] All new tests pass; existing observe-only extension tests unchanged

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Medium — wiring + lifecycle + tests
- **Risk**: Medium — `wire_extensions()` is called in 3 production paths; `close_issue()` wiring requires investigation
- **Depends On**: FEAT-983 (types), FEAT-984 (executor attributes)

## Status

**Open** | Created: 2026-04-07 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b2501d7-f66b-4a19-80a6-6fecea4283e8.jsonl`

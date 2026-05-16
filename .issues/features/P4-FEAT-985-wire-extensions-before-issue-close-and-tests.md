---
discovered_date: 2026-04-07
discovered_by: issue-size-review
confidence_score: 80
outcome_confidence: 53
---

# FEAT-985: wire_extensions() Upgrade, before_issue_close Hook, Reference Extension, and Tests

## Summary

Extend `wire_extensions()` to wire interceptors and contributed types into `FSMExecutor`; add `before_issue_close` hook in `issue_lifecycle.close_issue()`; write a reference interceptor extension; and add all tests across the affected test files.

## Parent Issue

Decomposed from FEAT-915: Bidirectional Extension Hooks with Interceptors and Contributed Actions

## Context

FEAT-983 defines types/protocols. FEAT-984 adds the executor dispatch logic. This issue completes the system by: wiring extensions into the executor via `wire_extensions()`; implementing the `before_issue_close` hook; providing a reference extension; and ensuring full test coverage.

## Use Case

**Who**: A developer building a little-loops extension that contributes custom actions, evaluators, or interceptors to the FSM executor.

**Context**: After implementing `LLExtension` with `provided_actions()`, `provided_evaluators()`, or interceptor methods, the developer calls `wire_extensions()` to register their extension. Currently, only `on_event` callbacks are wired — contributed types never reach `FSMExecutor`.

**Goal**: Wire their extension once via `wire_extensions()` and have all contributed types (actions, evaluators, interceptors) automatically available in loop execution.

**Outcome**: The extension's contributed actions and evaluators are callable from FSM loop YAML, and `before_issue_close` veto logic fires before any file I/O when an issue is closed during a loop run.

## Motivation

This feature:
- Closes the gap between FEAT-983 (type protocols) and FEAT-984 (executor attributes) — without this wiring, those two issues deliver protocols that are never populated
- Enables extension authors to contribute custom actions/evaluators without manual executor wiring in each CLI entry point
- Adds a veto point (`before_issue_close`) that prevents destructive operations during loop runs when an interceptor signals not to proceed
- Completes the bidirectional extension system — extensions can now both observe events (existing) and influence execution (new)

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

**Resolution of Open Question (from codebase research)**: `EventBus` has no `_interceptors` field — it only has `_observers` and `_file_sinks`. The `event_bus._interceptors` approach in the original draft will not work. **Use Option 1: add an `interceptors` parameter to `close_issue()`.**

Current signature (`issue_lifecycle.py:544–552`):
```python
def close_issue(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    close_reason: str | None,
    close_status: str | None,
    fix_commit: str | None = None,
    files_changed: list[str] | None = None,
    event_bus: EventBus | None = None,
) -> bool:
```

Add `interceptors: list[Any] | None = None` as the last parameter. Insert between `logger.info(...)` at line 595 and `try:` at line 597:

```python
# before_issue_close interceptors — veto check before any file I/O
if interceptors:
    for interceptor in interceptors:
        if hasattr(interceptor, "before_issue_close"):
            result = interceptor.before_issue_close(info)
            if result is False:
                return False
```

**Caller updates needed**: All three current callers pass only 5 positional args and receive `event_bus=None`. Two callers are in the orchestrator which has executor access:
- `issue_manager.py:502` — no executor context; pass `interceptors=None` (no change needed unless signature requires it)
- `orchestrator.py:861` — has executor; pass `interceptors=executor._interceptors` (or however the orchestrator holds the executor reference)
- `orchestrator.py:964` — same (second close_issue call site, currently missing from the Integration Map)

### 6. Reference Interceptor Extension

Create `scripts/little_loops/extensions/reference_interceptor.py` (or similar) demonstrating:
- `before_route()` that returns `None` (passthrough)
- `before_issue_close()` that returns `None` (passthrough)

Model structure after `NoopLoggerExtension:52-68` in `extension.py`.

## API/Interface

```python
# wire_extensions() — extended signature
def wire_extensions(
    bus: EventBus,
    config_paths: list[str] | None = None,
    executor: FSMExecutor | None = None,
) -> list[LLExtension]:
    """Register extensions with the event bus and optionally populate executor registries."""

# close_issue() — add interceptors parameter (Option 1, confirmed by codebase research)
def close_issue(
    info: IssueInfo,
    config: BRConfig,
    logger: Logger,
    close_reason: str | None,
    close_status: str | None,
    fix_commit: str | None = None,
    files_changed: list[str] | None = None,
    event_bus: EventBus | None = None,
    interceptors: list[Any] | None = None,
) -> bool:
    """Close issue; returns False if vetoed by a before_issue_close interceptor."""
```

## Integration Map

### Files to Modify
- `scripts/little_loops/extension.py` — `wire_extensions()` at line 139: add `executor` param, `hasattr(on_event)` guard, priority sort, second pass with conflict detection
- `scripts/little_loops/issue_lifecycle.py` — `close_issue()` at line 544: add `interceptors` param and `before_issue_close` dispatch at line 596
- `scripts/little_loops/cli/loop/run.py:203` — pass `executor=executor` to `wire_extensions()`
- `scripts/little_loops/cli/loop/lifecycle.py:257` — same
- `scripts/little_loops/cli/sprint/run.py:388` — same

### New Files
- `scripts/little_loops/extensions/` — directory does not yet exist; must be created (along with `__init__.py`)
- `scripts/little_loops/extensions/reference_interceptor.py` — reference interceptor extension

### Dependent Files (Callers/Importers)
- `scripts/little_loops/cli/loop/run.py:203` — calls `wire_extensions(executor.event_bus, ...)`
- `scripts/little_loops/cli/loop/lifecycle.py:257` — calls `wire_extensions()`
- `scripts/little_loops/cli/sprint/run.py:388` — calls `wire_extensions()`
- `scripts/little_loops/cli/parallel.py:226` — calls `wire_extensions()` (standalone EventBus only, no executor change needed)
- `scripts/little_loops/issue_manager.py:502` — calls `close_issue()` with 5 positional args, no event_bus or interceptors; no executor context, passes `interceptors=None`
- `scripts/little_loops/parallel/orchestrator.py:861` — calls `close_issue()` with 5 positional args; needs update to pass `interceptors`
- `scripts/little_loops/parallel/orchestrator.py:964` — second `close_issue()` call site (same pattern); also needs update to pass `interceptors`

### Similar Patterns
- Priority sort convention: `dependency_graph.py` (ascending sort — lower value fires first)
- `hasattr` guard pattern: existing `NoopLoggerExtension` in `extension.py`
- Conflict detection: other registry conflict patterns in the codebase

### Tests
- `scripts/tests/test_extension.py` — add `wire_extensions()` with executor; conflict detection; priority sort; `hasattr(on_event)` guard
- `scripts/tests/test_fsm_executor.py` — add contributed action/evaluator wiring via `wire_extensions()`
- `scripts/tests/test_events.py` — add priority/ordering tests
- `scripts/tests/test_issue_lifecycle.py` — add `before_issue_close` veto and passthrough tests
- New: `scripts/tests/test_interceptor_extension.py` — dedicated tests for `before_route`/`after_route` and `before_issue_close` dispatch; model after inline recording-class pattern in `test_extension.py`

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_manager.py:1520` — patches `little_loops.issue_manager.close_issue`; update to assert `interceptors=` kwarg is passed (or not passed) once orchestrator callers are updated [Agent 1 + 3 finding]
- `scripts/tests/test_orchestrator.py:1289, 1540, 2078` — patches `little_loops.issue_lifecycle.close_issue` at 3 call sites; update assertions after orchestrator callers pass `interceptors=executor._interceptors` [Agent 1 + 3 finding]

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:5249–5257` — documents `wire_extensions()` signature and Parameters table; will be stale (missing `executor` param) [Agent 2 finding]
- `docs/reference/API.md:5262–5263` — Behavior section describes only EventBus wiring; second executor pass absent after FEAT-985 [Agent 2 finding]
- `docs/reference/API.md:5266–5268` — Error handling section missing new `ValueError` raised on duplicate action/evaluator key conflicts [Agent 2 finding]
- `docs/reference/API.md:1966–1988` — `close_issue()` signature missing `interceptors` param; Returns says always `True` but FEAT-985 adds `False` veto path [Agent 2 finding]
- `docs/ARCHITECTURE.md:454–458` — Components table does not include new `extensions/` subpackage or `ReferenceInterceptorExtension` [Agent 2 finding]
- `docs/ARCHITECTURE.md:472–478` — Wiring table rows for 3 CLI entry points describe EventBus-only wiring; executor registry wiring absent after FEAT-985 [Agent 2 finding]

### Configuration
- N/A — no new config keys or settings files affected

## Implementation Steps

1. **Prerequisite**: Confirm FEAT-984 is merged — `FSMExecutor._contributed_actions`, `._contributed_evaluators`, `._interceptors` must exist before FEAT-985 can wire into them
2. **Extend `wire_extensions()`** (`extension.py:139`): add `executor: FSMExecutor | None = None` param; add priority sort (`sorted(..., key=lambda e: getattr(e, "priority", 0))`); add `hasattr(ext, "on_event")` guard to existing loop; add second pass over extensions populating executor registries with conflict detection
3. **Update three `wire_extensions()` callers** to pass `executor=executor`: `loop/run.py:203`, `loop/lifecycle.py:257`, `sprint/run.py:388`
4. **Extend `close_issue()`** (`issue_lifecycle.py:544`): add `interceptors: list[Any] | None = None` param; insert veto loop between line 595 (logger.info) and line 597 (try block)
5. **Update `close_issue()` callers**: `orchestrator.py:861` and `orchestrator.py:964` — pass `interceptors=executor._interceptors` (or however orchestrator holds the executor); `issue_manager.py:502` — no change needed (already passes no interceptors)
6. **Create reference interceptor extension**: create `scripts/little_loops/extensions/__init__.py` and `scripts/little_loops/extensions/reference_interceptor.py`; model structure after `NoopLoggerExtension` at `extension.py:52–67`
7. **Add tests** across all affected test files; verify existing observe-only extension tests (in `test_extension.py:TestWireExtensions`) are unchanged

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

8. **Add `FSMExecutor` import to `extension.py`** — the new `executor: FSMExecutor | None = None` annotation requires an import of `FSMExecutor` from `little_loops.fsm.executor`; use `TYPE_CHECKING` guard (`if TYPE_CHECKING: from little_loops.fsm.executor import FSMExecutor`) to avoid potential circular import since `fsm/executor.py` may transitively import from `extension.py`
9. **Update `test_issue_manager.py:1520`** — after Step 5 updates `issue_manager.py` (no-op `interceptors=None`), update the `mock_close.assert_called_once()` assertion to verify `interceptors` kwarg is absent or `None`
10. **Update `test_orchestrator.py:1289, 1540, 2078`** — after Step 5 updates orchestrator callers to pass `interceptors=executor._interceptors`, update the three `patch("...close_issue", return_value=True)` blocks to assert the `interceptors=` kwarg is passed with the executor's interceptors list
11. **Update `docs/reference/API.md`** — add `executor` param to `wire_extensions()` signature at line 5249; update Behavior section at line 5262 to describe executor pass; add `ValueError` to Error handling at line 5266; add `interceptors` param to `close_issue()` at line 1966 and update Returns at line 1988 to document `False` veto path
12. **Update `docs/ARCHITECTURE.md`** — add `extensions/` subpackage row to Components table at line 454; update wiring table rows at lines 472–478 to note executor registry wiring for the three loop/sprint CLI entry points

## Open Question — RESOLVED

**Use Option 1: add `interceptors: list[Any] | None = None` to `close_issue()`.**

Research confirmed:
- `EventBus` (events.py) has only `_observers` and `_file_sinks` — no `_interceptors` field; Option 2 is not viable
- `close_issue()` signature is at `issue_lifecycle.py:544–552`; `event_bus` is already the last param but is `None` in all current callers
- All callers (`issue_manager.py:502`, `orchestrator.py:861`, `orchestrator.py:964`) pass only 5 positional args — none pass `event_bus` today
- `issue_manager.py` has no executor context — it will pass `interceptors=None`
- `orchestrator.py` has executor access and will pass `interceptors=executor._interceptors` at both call sites

Option 1 keeps `close_issue()` decoupled from both `EventBus` internals and `FSMExecutor`, and cleanly handles the case where no interceptors are registered.

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

## Labels

`feat`, `extension`, `executor`, `hooks`, `wiring`

## Status

**Open** | Created: 2026-04-07 | Priority: P4

## Session Log
- `hook:posttooluse-git-mv` - 2026-04-08T05:12:45 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3cbd267-88d4-421d-8d23-7869adfc91cb.jsonl`
- `/ll:wire-issue` - 2026-04-07T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/auto.jsonl`
- `/ll:refine-issue` - 2026-04-08T00:32:08 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/5c382aff-97a4-46a3-8961-ff8991a9761a.jsonl`
- `/ll:format-issue` - 2026-04-08T00:28:14 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8c4a940a-aa45-4b73-ac86-b855f9c1ae7d.jsonl`
- `/ll:issue-size-review` - 2026-04-07T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6b2501d7-f66b-4a19-80a6-6fecea4283e8.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3cbd267-88d4-421d-8d23-7869adfc91cb.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-04-08
- **Reason**: Issue too large for single session (score: 11/11)

### Decomposed Into
- FEAT-993: Extend `wire_extensions()` with Executor Support
- FEAT-994: Add `before_issue_close` Veto Hook to `close_issue()`
- FEAT-995: Reference Interceptor Extension and Docs Update

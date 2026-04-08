---
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 78
---

# FEAT-995: Reference Interceptor Extension and Docs Update

## Summary

Create the `scripts/little_loops/extensions/` package with a `reference_interceptor.py` demonstrating passthrough `before_route()` and `before_issue_close()` behavior; write dedicated tests in `test_interceptor_extension.py`; update `API.md` and `ARCHITECTURE.md` to reflect the new extension system.

## Parent Issue

Decomposed from FEAT-985: wire_extensions() Upgrade, before_issue_close Hook, Reference Extension, and Tests

## Context

FEAT-993 and FEAT-994 add the wiring and lifecycle hook machinery. This issue provides the reference implementation that extension authors can model after, and updates documentation to accurately describe the extended `wire_extensions()` and `close_issue()` signatures.

## Current Behavior

- `scripts/little_loops/extensions/` package does not exist
- `docs/reference/API.md` `wire_extensions()` shows the 2-param signature without the `executor` parameter added in FEAT-993
- `docs/reference/API.md` `close_issue()` is missing both `event_bus` and `interceptors` params present in the actual implementation (`issue_lifecycle.py:551`)
- `docs/ARCHITECTURE.md` Components table does not list an `extensions/` subpackage

## Expected Behavior

- `scripts/little_loops/extensions/` package exists with `ReferenceInterceptorExtension` implementing passthrough `before_route()` and `before_issue_close()`
- `test_interceptor_extension.py` passes: passthrough, veto, and `wire_extensions()` wiring integration
- `docs/reference/API.md` accurately reflects `wire_extensions()` with `executor` param, `close_issue()` with `event_bus` and `interceptors` params including the `False` veto return path and `ValueError` for duplicate keys
- `docs/ARCHITECTURE.md` lists the `extensions/` subpackage in the Components table and reflects executor wiring

## Use Case

**Who**: Extension author implementing custom interceptor logic for `ll-loop`

**Context**: After FEAT-993 and FEAT-994 land, developers want a concrete, copy-pasteable starting point for building veto or routing interceptors without reading FSM internals

**Goal**: Copy `ReferenceInterceptorExtension`, rename the class, and implement real `before_issue_close()` or `before_route()` logic

**Outcome**: A working custom interceptor wired via `wire_extensions()` with minimal boilerplate

## Motivation

This feature would:
- Provide a copy-pasteable reference implementation reducing onboarding friction for the interceptor system introduced by FEAT-993/FEAT-994
- Keep `API.md` and `ARCHITECTURE.md` accurate — `close_issue()` docs already omit the `event_bus` param present in production code today
- Establish `scripts/little_loops/extensions/` as the canonical home for bundled reference implementations

## Proposed Solution

### 1. Create `extensions/` Package

Create new directory `scripts/little_loops/extensions/` with:
- `__init__.py` (empty or minimal exports)
- `reference_interceptor.py` — reference interceptor extension

Model `reference_interceptor.py` structure after `NoopLoggerExtension` at `extension.py:100–115`. The `InterceptorExtension` protocol (which defines `before_route`, `after_route`, `before_issue_close`) is at `extension.py:58–75` — the reference class should implement this interface.

```python
from little_loops import RouteContext, RouteDecision  # public API, confirmed exported
from little_loops.issue_parser import IssueInfo       # already imported in extension.py:22


class ReferenceInterceptorExtension:
    """Reference implementation demonstrating passthrough interceptor behavior.

    before_route() and before_issue_close() return None (passthrough).
    Copy and customize to implement real veto logic.
    """

    def before_route(self, context: RouteContext) -> RouteDecision | None:
        """Return None to pass through without modifying routing."""
        return None

    def before_issue_close(self, info: IssueInfo) -> bool | None:
        """Return None to pass through; return False to veto the close."""
        return None
```

`RouteContext` and `RouteDecision` are `@dataclass` types defined in `fsm/executor.py:53–76` and re-exported via `fsm/__init__.py:86–94` and `little_loops/__init__.py:18`. `from little_loops import RouteContext, RouteDecision` is the canonical import (confirmed by smoke tests at `test_extension.py:288–298`).

### 2. Tests

Create `scripts/tests/test_interceptor_extension.py` — dedicated tests for interceptor dispatch:
- `before_route()` passthrough (returns `None`)
- `before_issue_close()` passthrough (returns `None`)
- Veto behavior when `before_issue_close()` returns `False`
- Integration with `wire_extensions()` (interceptor appended to `executor._interceptors`)

Model after the inline recording-class pattern in `test_extension.py`. Confirmed patterns:
- Basic recorder with `on_event` closure at `test_extension.py:38–49`
- Multiple independent recorders at `test_extension.py:207–226`
- Recorder with `event_filter` at `test_extension.py:232–246`
- Interceptor protocol stub at `test_extension.py:303–316` — this is the closest model; it defines inline `before_route`, `after_route`, and `before_issue_close` with `return None`

All patterns use `patch.object(ExtensionLoader, "load_all", return_value=[...])` to inject test extensions.

### 3. Update `docs/reference/API.md`

- Lines 5249–5257 — `wire_extensions()` signature block (currently shows 2-param version); add `executor: FSMExecutor | None = None` param and update Parameters table
- Lines 5262–5263 — Behavior section (currently EventBus-only description); add second executor pass description
- Lines 5266–5268 — Error handling section; add `ValueError` for duplicate action/evaluator key conflict
- Lines 1966–1988 — `close_issue()` signature block; **note**: docs already show stale signature missing `event_bus` param (which is present in actual code at `issue_lifecycle.py:551`); add both `event_bus` and `interceptors` params; update Returns to document `False` veto path

### 4. Update `docs/ARCHITECTURE.md`

- Lines 454–462 — Components table currently lists `LLExtension`, `EventBus`, `ExtensionLoader`, `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension` (all in `extension.py`); add new `extensions/` subpackage row for `ReferenceInterceptorExtension`
- Lines 472–478 — Wiring table currently shows EventBus-only for `ll-loop`, `ll-parallel`, `ll-sprint`; update `ll-loop` rows (`run.py`, `lifecycle.py`) to note executor registry wiring (after FEAT-993); `ll-sprint` parallel branch and `ll-parallel` remain EventBus-only

## API/Interface

```python
from little_loops import RouteContext, RouteDecision
from little_loops.issue_parser import IssueInfo


class ReferenceInterceptorExtension:
    """Reference implementation demonstrating passthrough interceptor behavior.

    before_route() and before_issue_close() return None (passthrough).
    Copy and customize to implement real veto logic.
    """

    def before_route(self, context: RouteContext) -> RouteDecision | None:
        """Return None to pass through without modifying routing."""
        return None

    def before_issue_close(self, info: IssueInfo) -> bool | None:
        """Return None to pass through; return False to veto the close."""
        return None
```

No changes to existing public API — new class only.

## Integration Map

### New Files
- `scripts/little_loops/extensions/__init__.py`
- `scripts/little_loops/extensions/reference_interceptor.py`
- `scripts/tests/test_interceptor_extension.py`

### Files to Modify
- `docs/reference/API.md` — 4 locations (lines 5249, 5262, 5266, 1966)
- `docs/ARCHITECTURE.md` — 2 locations (lines 454, 472)
- `CONTRIBUTING.md` — lines 178–253 directory tree; add `extensions/` row alongside other subpackages [wiring pass]

### Similar Patterns
- `NoopLoggerExtension` at `extension.py:100–115` — model class structure after this
- `InterceptorExtension` protocol at `extension.py:58–75` — the reference class implements these methods
- Inline recording-class pattern in `test_extension.py:38–49, 207–226, 303–316` — model tests after these; closest is line 303 which stubs all three interceptor methods

## Implementation Steps

1. Create `scripts/little_loops/extensions/__init__.py`
2. Create `scripts/little_loops/extensions/reference_interceptor.py` modeled after `NoopLoggerExtension`
3. Create `scripts/tests/test_interceptor_extension.py` with passthrough and veto tests
4. Update `docs/reference/API.md` at lines 5249, 5262, 5266, 1966
5. Update `docs/ARCHITECTURE.md` at lines 454, 472

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

6. Update `CONTRIBUTING.md:178–253` — add `extensions/` subpackage row to the `scripts/little_loops/` ASCII directory tree, alongside `dependency_mapper/`, `workflow_sequence/`, `fsm/`, `parallel/`, etc.

## Acceptance Criteria

- [ ] `scripts/little_loops/extensions/` package created with `__init__.py`
- [ ] `reference_interceptor.py` demonstrates `before_route()` and `before_issue_close()` passthrough
- [ ] `test_interceptor_extension.py` covers passthrough, veto, and wiring integration
- [ ] `API.md` updated: `wire_extensions()` executor param, `close_issue()` interceptors param and False return, ValueError documented
- [ ] `ARCHITECTURE.md` updated: extensions/ subpackage in Components table, executor wiring in wiring table

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small — new files + targeted doc updates
- **Risk**: Low — no production code changes
- **Depends On**: FEAT-993 (for accurate docs on wire_extensions), FEAT-994 (for accurate docs on close_issue); can be written in parallel

## Labels

`feat`, `extension`, `docs`, `reference`

## Status

**Open** | Created: 2026-04-08 | Priority: P4

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `extension.py:58–75` — `InterceptorExtension` protocol (defines `before_route`, `after_route`, `before_issue_close`)
- `extension.py:100–115` — `NoopLoggerExtension` (model for class structure; has `__init__` with `log_path` and `on_event` method)
- `extension.py:22` — `from little_loops.issue_parser import IssueInfo` already imported
- `fsm/executor.py:53–63` — `RouteContext` dataclass (fields: `state_name`, `state`, `verdict`, `action_result`, `eval_result`, `ctx`, `iteration`)
- `fsm/executor.py:66–76` — `RouteDecision` dataclass (`next_state: str | None`; `None`=passthrough, string=redirect, `RouteDecision(None)`=veto)
- `little_loops/__init__.py:18, 52–53` — `RouteContext` and `RouteDecision` confirmed in public `__all__`
- `test_extension.py:288–298` — smoke tests confirm `from little_loops import RouteContext, RouteDecision` works
- `test_extension.py:303–316` — inline interceptor stub (closest model for test_interceptor_extension.py)
- `scripts/little_loops/extensions/` — directory does NOT exist yet (must be created with `__init__.py`)
- `docs/reference/API.md:1966–1988` — `close_issue()` docs already missing `event_bus` param; add both `event_bus` and `interceptors` in the same pass
- `docs/ARCHITECTURE.md:454–462` — Components table already includes `InterceptorExtension`, `ActionProviderExtension`, `EvaluatorProviderExtension`; add new row for `extensions/` subpackage

## Session Log
- `/ll:confidence-check` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/40b51a9d-c96a-476d-8d72-459ce0a30b49.jsonl`
- `/ll:format-issue` - 2026-04-08T12:52:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b1ba72aa-ca56-4f5a-a469-7b8bd7aa2766.jsonl`
- `/ll:refine-issue` - 2026-04-08T05:24:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6812afe4-4248-451c-bdc8-42131c8cb745.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3cbd267-88d4-421d-8d23-7869adfc91cb.jsonl`
- `/ll:wire-issue` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/current-session.jsonl`

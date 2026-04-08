---
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 88
outcome_confidence: 82
---

# FEAT-995: Reference Interceptor Extension and Docs Update

## Summary

Create the `scripts/little_loops/extensions/` package with a `reference_interceptor.py` demonstrating passthrough `before_route()` and `before_issue_close()` behavior; write dedicated tests in `test_interceptor_extension.py`; update `API.md` and `ARCHITECTURE.md` to reflect the new extension system.

## Parent Issue

Decomposed from FEAT-985: wire_extensions() Upgrade, before_issue_close Hook, Reference Extension, and Tests

## Context

FEAT-993 and FEAT-994 add the wiring and lifecycle hook machinery. This issue provides the reference implementation that extension authors can model after, and updates documentation to accurately describe the extended `wire_extensions()` and `close_issue()` signatures.

## Proposed Solution

### 1. Create `extensions/` Package

Create new directory `scripts/little_loops/extensions/` with:
- `__init__.py` (empty or minimal exports)
- `reference_interceptor.py` — reference interceptor extension

Model `reference_interceptor.py` structure after `NoopLoggerExtension` at `extension.py:52–67`:

```python
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

### 2. Tests

Create `scripts/tests/test_interceptor_extension.py` — dedicated tests for interceptor dispatch:
- `before_route()` passthrough (returns `None`)
- `before_issue_close()` passthrough (returns `None`)
- Veto behavior when `before_issue_close()` returns `False`
- Integration with `wire_extensions()` (interceptor appended to `executor._interceptors`)

Model after the inline recording-class pattern in `test_extension.py`.

### 3. Update `docs/reference/API.md`

- Line 5249–5257 — add `executor` param to `wire_extensions()` signature and Parameters table
- Line 5262–5263 — update Behavior section to describe executor pass (second registration pass for actions/evaluators/interceptors)
- Line 5266–5268 — add `ValueError` to Error handling section (duplicate action/evaluator key conflict)
- Line 1966–1988 — add `interceptors: list[Any] | None = None` to `close_issue()` signature; update Returns to document `False` veto path

### 4. Update `docs/ARCHITECTURE.md`

- Line 454–458 — add `extensions/` subpackage row to Components table (`ReferenceInterceptorExtension`)
- Line 472–478 — update wiring table rows for 3 CLI entry points to note executor registry wiring (after FEAT-993)

## Integration Map

### New Files
- `scripts/little_loops/extensions/__init__.py`
- `scripts/little_loops/extensions/reference_interceptor.py`
- `scripts/tests/test_interceptor_extension.py`

### Files to Modify
- `docs/reference/API.md` — 4 locations (lines 5249, 5262, 5266, 1966)
- `docs/ARCHITECTURE.md` — 2 locations (lines 454, 472)

### Similar Patterns
- `NoopLoggerExtension` at `extension.py:52–67` — model structure after this
- Inline recording-class pattern in `test_extension.py`

## Implementation Steps

1. Create `scripts/little_loops/extensions/__init__.py`
2. Create `scripts/little_loops/extensions/reference_interceptor.py` modeled after `NoopLoggerExtension`
3. Create `scripts/tests/test_interceptor_extension.py` with passthrough and veto tests
4. Update `docs/reference/API.md` at lines 5249, 5262, 5266, 1966
5. Update `docs/ARCHITECTURE.md` at lines 454, 472

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

## Session Log
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3cbd267-88d4-421d-8d23-7869adfc91cb.jsonl`

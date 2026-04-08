---
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 90
outcome_confidence: 85
---

# FEAT-994: Add `before_issue_close` Veto Hook to `close_issue()`

## Summary

Add an `interceptors: list[Any] | None = None` parameter to `close_issue()`, insert a veto dispatch loop before file I/O, and update `orchestrator.py` callers to pass `interceptors=executor._interceptors`.

## Parent Issue

Decomposed from FEAT-985: wire_extensions() Upgrade, before_issue_close Hook, Reference Extension, and Tests

## Context

`close_issue()` currently emits `"issue.closed"` after the file move but has no pre-move veto hook. FEAT-993 registers interceptors into `executor._interceptors` via `wire_extensions()`. This issue adds the dispatch point so those interceptors can veto a close before any file I/O occurs.

## Use Case

**Who**: An extension author implementing `before_issue_close()` to prevent issue closure during certain loop states.

**Goal**: When an interceptor returns `False` from `before_issue_close()`, the close is aborted and no files are moved.

**Outcome**: `close_issue()` returns `False` without moving files; the caller (orchestrator) handles the veto appropriately.

## Proposed Solution

### 1. Extend `close_issue()` Signature

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

### 2. Update Orchestrator Callers

- `scripts/little_loops/parallel/orchestrator.py:861` — has executor; pass `interceptors=executor._interceptors`
- `scripts/little_loops/parallel/orchestrator.py:964` — same (second `close_issue()` call site)
- `scripts/little_loops/issue_manager.py:502` — no executor context; no change needed (already passes no interceptors, defaults to `None`)

### 3. Update Test Assertions

- `scripts/tests/test_issue_manager.py:1520` — patches `little_loops.issue_manager.close_issue`; update to assert `interceptors` kwarg is absent or `None`
- `scripts/tests/test_orchestrator.py:1289, 1540, 2078` — patches `little_loops.issue_lifecycle.close_issue` at 3 call sites; update assertions to verify `interceptors=executor._interceptors` is passed

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — `close_issue()` at line 544: add `interceptors` param and `before_issue_close` dispatch at line 596
- `scripts/little_loops/parallel/orchestrator.py:861` — pass `interceptors=executor._interceptors`
- `scripts/little_loops/parallel/orchestrator.py:964` — same

### Files Unchanged
- `scripts/little_loops/issue_manager.py:502` — no executor context; no change needed

### Tests
- `scripts/tests/test_issue_lifecycle.py` — add `before_issue_close` veto and passthrough tests
- `scripts/tests/test_issue_manager.py:1520` — update mock assertion for `interceptors` kwarg
- `scripts/tests/test_orchestrator.py:1289, 1540, 2078` — update assertions after callers pass `interceptors=executor._interceptors`

## Implementation Steps

1. Add `interceptors: list[Any] | None = None` param to `close_issue()` in `issue_lifecycle.py:544`
2. Insert veto dispatch loop between line 595 (logger.info) and line 597 (try block)
3. Update `orchestrator.py:861` to pass `interceptors=executor._interceptors`
4. Update `orchestrator.py:964` to pass `interceptors=executor._interceptors`
5. Add `before_issue_close` veto and passthrough tests to `test_issue_lifecycle.py`
6. Update `test_issue_manager.py:1520` mock assertion
7. Update `test_orchestrator.py:1289, 1540, 2078` mock assertions

## Acceptance Criteria

- [ ] `close_issue()` accepts `interceptors: list[Any] | None = None`
- [ ] `before_issue_close` hook fires before file I/O; `False` return vetoes closure
- [ ] `close_issue()` returns `False` when vetoed (no files moved)
- [ ] Orchestrator callers pass `interceptors=executor._interceptors` at both call sites
- [ ] `issue_manager.py` caller unchanged (no executor context)
- [ ] Veto and passthrough tests pass in `test_issue_lifecycle.py`
- [ ] Existing orchestrator and issue_manager test assertions updated

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small — focused changes to `issue_lifecycle.py` and `orchestrator.py`
- **Risk**: Low-Medium — `close_issue()` is on the critical path for issue closure
- **Depends On**: FEAT-983 (interceptor protocol), FEAT-984 (executor attributes); can be implemented independently of FEAT-993

## Labels

`feat`, `extension`, `hooks`, `lifecycle`

## Status

**Open** | Created: 2026-04-08 | Priority: P4

## Session Log
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3cbd267-88d4-421d-8d23-7869adfc91cb.jsonl`

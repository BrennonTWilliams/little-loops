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

Current signature (`issue_lifecycle.py:544–553`):
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

- `scripts/little_loops/parallel/orchestrator.py:861–867` — `_on_worker_complete()`: passes 5 positional args today; add `interceptors=executor._interceptors` if `ParallelOrchestrator` stores a reference to interceptors; otherwise pass `interceptors=None` (see gap note below)
- `scripts/little_loops/parallel/orchestrator.py:964–970` — `_merge_sequential()`: same pattern as above
- `scripts/little_loops/issue_manager.py:502–508` — no executor context; no change needed (defaults to `None`)

**Gap — orchestrator interceptor source**: `ParallelOrchestrator` coordinates workers in separate processes, each with their own `FSMExecutor`. The orchestrator itself does not own an `FSMExecutor`. Verify whether `ParallelOrchestrator` stores a top-level interceptors list populated at startup (e.g., from `wire_extensions()` return value), or whether the orchestrator callers should simply pass `interceptors=None` until a parent-level interceptors list is added.

### 3. Update Test Assertions

- `scripts/tests/test_issue_manager.py:1519–1524` — patches `little_loops.issue_manager.close_issue` (import-site name); currently uses `mock_close.assert_called_once()` with no kwarg assertions; update to verify `interceptors` is absent or `None` (e.g., `mock_close.assert_called_once_with(..., interceptors=None)` or keep `assert_called_once()` if issue_manager never passes it)
- `scripts/tests/test_orchestrator.py:1289` — patches `little_loops.issue_lifecycle.close_issue` (definition module); no kwarg assertions currently; update after orchestrator callers are determined
- `scripts/tests/test_orchestrator.py:1540` — same patch, `_merge_sequential` path; update accordingly
- `scripts/tests/test_orchestrator.py:2078` — same patch, `interrupted=True` path; `close_issue` is never reached here (guarded by `return` at line 851); assertion confirms `mark_completed` and `mark_failed` are not called — no kwarg update needed

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — `close_issue()` at lines 544–553: add `interceptors` param; insert veto dispatch loop between line 595 (`logger.info`) and line 597 (`try:`)
- `scripts/little_loops/parallel/orchestrator.py:861–867` — `_on_worker_complete()`: update `close_issue()` call (see gap note in Proposed Solution)
- `scripts/little_loops/parallel/orchestrator.py:964–970` — `_merge_sequential()`: same

### Files Unchanged
- `scripts/little_loops/issue_manager.py:502–508` — 5 positional args, no executor context; no change needed

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

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `issue_lifecycle.py:544–553` — confirmed current `close_issue()` signature; `def` at 544, closing `) -> bool:` at 553
- `issue_lifecycle.py:595` — confirmed `logger.info(f"Closing {info.issue_id}: ...")` — last line before file I/O
- `issue_lifecycle.py:597` — confirmed `try:` — opens block with `_build_closure_resolution` (599), `_prepare_issue_content` (602), `_move_issue_to_completed` (605), git commit (608)
- `orchestrator.py:861–867` — `_on_worker_complete()` first call: 5 positional args, omits `fix_commit`, `files_changed`, `event_bus`
- `orchestrator.py:964–970` — `_merge_sequential()` second call: same 5-arg pattern; `info` null-check folded into `if` condition
- `issue_manager.py:502–508` — confirmed 5 positional args; patches target `"little_loops.issue_manager.close_issue"` (import-site)
- `test_issue_manager.py:1519` — patch: `patch("little_loops.issue_manager.close_issue", return_value=True)`; assertion: `mock_close.assert_called_once()` (no kwarg checking)
- `test_orchestrator.py:1289` — patch: `patch("little_loops.issue_lifecycle.close_issue", return_value=True)` (definition site)
- `test_orchestrator.py:1540` — same patch, `_merge_sequential` path
- `test_orchestrator.py:2078` — same patch, `interrupted=True` path; `close_issue` never reached (return at line 851 guards it); assertions check `_interrupted_issues` and confirm neither `mark_completed` nor `mark_failed` called
- `executor.py:157` — `self._interceptors: list[Any] = []` confirmed

## Session Log
- `/ll:refine-issue` - 2026-04-08T05:24:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6812afe4-4248-451c-bdc8-42131c8cb745.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3cbd267-88d4-421d-8d23-7869adfc91cb.jsonl`

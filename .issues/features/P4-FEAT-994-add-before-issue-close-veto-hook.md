---
discovered_date: 2026-04-08
discovered_by: issue-size-review
confidence_score: 100
outcome_confidence: 86
---

# FEAT-994: Add `before_issue_close` Veto Hook to `close_issue()`

## Summary

Add an `interceptors: list[Any] | None = None` parameter to `close_issue()`, insert a veto dispatch loop before file I/O, and update `orchestrator.py` callers to pass `interceptors=executor._interceptors`.

## Current Behavior

`close_issue()` emits `"issue.closed"` after the file move but has no pre-move veto hook. Interceptors registered via `wire_extensions()` have no opportunity to inspect or veto a close before file I/O occurs.

## Expected Behavior

When `close_issue()` is called with `interceptors` populated, each interceptor's `before_issue_close()` method is dispatched before any file I/O. If any interceptor returns `False`, `close_issue()` immediately returns `False` without moving files. Interceptors returning `None` or truthy values allow closure to proceed normally.

## Motivation

FEAT-993 registers interceptors into `executor._interceptors` via `wire_extensions()`, but without a dispatch point in `close_issue()`, those interceptors cannot influence issue closure. Extension authors implementing `before_issue_close()` need a pre-file-I/O veto hook to control when issues are allowed to close — for example, to prevent closure during certain loop states.

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

- `scripts/little_loops/parallel/orchestrator.py:861–867` — `_on_worker_complete()`: passes 5 positional args today; add `interceptors=None` (no executor in scope — see resolved gap below)
- `scripts/little_loops/parallel/orchestrator.py:964–970` — `_merge_sequential()`: same; add `interceptors=None`
- `scripts/little_loops/issue_manager.py:502–508` — no executor context; no change needed (defaults to `None`)

**Resolved Gap — orchestrator interceptor source**: `ParallelOrchestrator` does **not** own an `FSMExecutor` and has no `_interceptors` attribute. Workers run in separate subprocesses, each with their own executor. At both orchestrator `close_issue()` call sites, only `self` (the orchestrator) and `result` (a `WorkerResult`) are in scope — no executor variable exists.

Additionally, `wire_extensions()` is called at the CLI layer (`cli/parallel.py:228`, `cli/sprint/run.py:391`) **without** an `executor=` argument, so the interceptors injection path (`extension.py:224–241`) is never entered for parallel/sprint runs. The return value of `wire_extensions()` is discarded at both call sites, and `ParallelOrchestrator.__init__` has no parameter to accept interceptors.

**Conclusion**: Orchestrator callers should pass `interceptors=None` (or omit the kwarg) in this issue. Forwarding interceptors through the parallel pipeline would require a future issue to: (1) add an `interceptors` parameter to `ParallelOrchestrator.__init__`, (2) update `cli/parallel.py` and `cli/sprint/run.py` to capture and filter `wire_extensions()` return value, and (3) pass it to the orchestrator constructor.

### 3. Update Test Assertions

- `scripts/tests/test_issue_manager.py:1519–1524` — patches `little_loops.issue_manager.close_issue` (import-site name); currently uses `mock_close.assert_called_once()` with no kwarg assertions; update to verify `interceptors` is absent or `None` (e.g., `mock_close.assert_called_once_with(..., interceptors=None)` or keep `assert_called_once()` if issue_manager never passes it)
- `scripts/tests/test_orchestrator.py:1289` — patches `little_loops.issue_lifecycle.close_issue` (definition module); no kwarg assertions currently; update after orchestrator callers are determined
- `scripts/tests/test_orchestrator.py:1540` — same patch, `_merge_sequential` path; update accordingly
- `scripts/tests/test_orchestrator.py:2078` — same patch, `interrupted=True` path; `close_issue` is never reached here (guarded by `return` at line 851); assertion confirms `mark_completed` and `mark_failed` are not called — no kwarg update needed

## API/Interface

Extended `close_issue()` signature in `issue_lifecycle.py`:

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
    interceptors: list[Any] | None = None,  # NEW — veto hook dispatch
) -> bool:
```

**Interceptor protocol** (`before_issue_close` hook):

```python
class MyExtension:
    def before_issue_close(self, info: IssueInfo) -> bool | None:
        """Return False to veto closure; None or True to allow."""
        ...
```

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_lifecycle.py` — `close_issue()` at lines 544–553: add `interceptors` param; insert veto dispatch loop between line 595 (`logger.info`) and line 597 (`try:`)
- `scripts/little_loops/parallel/orchestrator.py:861–867` — `_on_worker_complete()`: update `close_issue()` call (see gap note in Proposed Solution)
- `scripts/little_loops/parallel/orchestrator.py:964–970` — `_merge_sequential()`: same

### Files Unchanged
- `scripts/little_loops/issue_manager.py:502–508` — 5 positional args, no executor context; no change needed

### Context-Only (No Modifications)
- `scripts/little_loops/cli/parallel.py:225–235` — calls `wire_extensions()` without `executor=`; discards return value; constructs `ParallelOrchestrator` without interceptors
- `scripts/little_loops/cli/sprint/run.py:387–397` — same pattern as `cli/parallel.py`
- `scripts/little_loops/cli/loop/run.py:206` — calls `wire_extensions(executor.event_bus, config.extensions, executor=executor)`; interceptors path IS entered; extensions with `before_issue_close` will be registered into `executor._interceptors`
- `scripts/little_loops/cli/loop/lifecycle.py:260` — same pattern as `loop/run.py`; another FSM loop entry point that fully populates `_interceptors` including `before_issue_close` implementors
- `scripts/little_loops/extension.py:187–245` — `wire_extensions()` injects interceptors into `executor._interceptors` only when `executor=` is passed; returns full extension list; `extension.py:240` already gates on `hasattr(ext, "before_issue_close")`
- `scripts/little_loops/fsm/executor.py:157` — `self._interceptors: list[Any] = []`; only populated via `wire_extensions(..., executor=executor)` in loop CLI paths

### Dependent Files (Callers/Importers)

- `scripts/little_loops/parallel/orchestrator.py` — calls `close_issue()` at `_on_worker_complete()` and `_merge_sequential()`
- `scripts/little_loops/issue_manager.py` — calls `close_issue()` (no interceptor context; no change needed)

### Similar Patterns

- N/A — first veto hook in `close_issue()`; the `before_issue_close` dispatch pattern mirrors future pre-action hooks

### Tests
- `scripts/tests/test_issue_lifecycle.py` — add `before_issue_close` veto and passthrough tests to `TestCloseIssue` (lines 843–977); follow the `event_bus=` kwarg test pattern at line 1495 (`TestEventBusEmission`)
- `scripts/tests/test_issue_manager.py:1520` — `mock_close.assert_called_once()` (no kwarg check); no change needed since `issue_manager.py` never passes `interceptors`
- `scripts/tests/test_orchestrator.py:1289` — `patch("little_loops.issue_lifecycle.close_issue")`; assertion is on `queue.mark_completed`, not `close_issue` call args; no kwarg assertion to update
- `scripts/tests/test_orchestrator.py:1540` — same; assertion on `queue.mark_completed` only; no kwarg assertion to update
- `scripts/tests/test_orchestrator.py:2078` — confirmed unreachable (`interrupted=True` path returns before `close_issue` call); no change needed

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_issue_lifecycle.py` — new test cases needed beyond basic veto/passthrough: (a) multiple interceptors called in order, (b) first-interceptor veto short-circuits remaining interceptors without calling them; follow `TestInterceptorDispatch` patterns in `test_fsm_executor.py:3938–3987`
- `scripts/tests/test_extension.py:483–499` — `test_interceptor_extension_protocol_satisfied` already verifies `before_issue_close` is part of the `InterceptorExtension` protocol; no change needed but confirms protocol is pre-wired

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md:1963–1988` — `close_issue()` signature block; currently omits `event_bus` (pre-existing gap) and will omit `interceptors` after this change; update tracked under FEAT-995

### Configuration

- N/A — no config changes required

## Implementation Steps

1. Add `interceptors: list[Any] | None = None` param to `close_issue()` in `issue_lifecycle.py:544`
2. Insert veto dispatch loop between line 595 (logger.info) and line 597 (try block)
3. Update `orchestrator.py:861` (`_on_worker_complete`) to add `interceptors=None` kwarg
4. Update `orchestrator.py:964` (`_merge_sequential`) to add `interceptors=None` kwarg
5. Add `before_issue_close` veto and passthrough tests to `test_issue_lifecycle.py` (`TestCloseIssue` class, after line 977); follow `event_bus=` kwarg pattern at line 1495
6. Add multiple-interceptor ordering test and short-circuit test (follow `TestInterceptorDispatch` in `test_fsm_executor.py:3938–3987`)
7. `test_issue_manager.py:1525` — `assert_called_once()` has no kwarg check; no update needed since `issue_manager.py` never passes `interceptors`
8. `test_orchestrator.py:1289, 1540` — assertions are on `queue.mark_completed`, not `close_issue` call args; no kwarg assertions to update
9. `test_orchestrator.py:2078` — `close_issue` is unreachable in interrupted path; no change needed

## Acceptance Criteria

- [x] `close_issue()` accepts `interceptors: list[Any] | None = None`
- [x] `before_issue_close` hook fires before file I/O; `False` return vetoes closure
- [x] `close_issue()` returns `False` when vetoed (no files moved)
- [x] Orchestrator callers pass `interceptors=None` at both call sites (no executor in orchestrator scope; interceptor forwarding is a future issue)
- [x] `issue_manager.py` caller unchanged (no executor context)
- [x] Veto and passthrough tests pass in `test_issue_lifecycle.py`
- [x] Existing orchestrator and issue_manager test assertions updated

## Impact

- **Priority**: P4 - Strategic
- **Effort**: Small — focused changes to `issue_lifecycle.py` and `orchestrator.py`
- **Risk**: Low-Medium — `close_issue()` is on the critical path for issue closure
- **Depends On**: FEAT-983 (interceptor protocol), FEAT-984 (executor attributes); can be implemented independently of FEAT-993

## Labels

`feat`, `extension`, `hooks`, `lifecycle`

## Status

**Completed** | Created: 2026-04-08 | Completed: 2026-04-08 | Priority: P4

## Resolution

**Status**: Implemented
**Reason**: feature_implemented
**Completed**: 2026-04-08

### Changes Made
- `scripts/little_loops/issue_lifecycle.py`: Added `interceptors: list[Any] | None = None` param to `close_issue()`; inserted veto dispatch loop before file I/O; added `from typing import Any` import
- `scripts/little_loops/parallel/orchestrator.py`: Added explicit `interceptors=None` kwarg to both `close_issue()` call sites (`_on_worker_complete` and `_merge_sequential`)
- `scripts/tests/test_issue_lifecycle.py`: Added 4 new tests to `TestCloseIssue`: veto prevents close, passthrough allows close, multiple interceptors called in order, first veto short-circuits remaining interceptors

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
- `/ll:manage-issue` - 2026-04-08T00:00:00 - implemented FEAT-994: before_issue_close veto hook
- `/ll:ready-issue` - 2026-04-08T05:48:28 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b7ed2dcf-ec05-45d3-acce-9b9fe52c883a.jsonl`
- `/ll:confidence-check` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0d5edce3-b3e1-49e0-8dee-543319933326.jsonl`
- `/ll:wire-issue` - 2026-04-08T00:00:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/auto-issue-processor.yaml`
- `/ll:refine-issue` - 2026-04-08T05:39:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/22ca8212-2a52-4f10-a3ed-90023ad7d499.jsonl`
- `/ll:format-issue` - 2026-04-08T05:36:25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d14cc21c-1436-4133-a150-4c74955a0244.jsonl`
- `/ll:refine-issue` - 2026-04-08T05:24:31 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6812afe4-4248-451c-bdc8-42131c8cb745.jsonl`
- `/ll:issue-size-review` - 2026-04-08T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b3cbd267-88d4-421d-8d23-7869adfc91cb.jsonl`

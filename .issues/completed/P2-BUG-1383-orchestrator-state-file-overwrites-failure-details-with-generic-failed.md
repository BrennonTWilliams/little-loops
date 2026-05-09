---
id: BUG-1383
type: BUG
priority: P2
status: active
captured_at: '2026-05-09T01:55:56Z'
completed_at: '2026-05-09T17:45:49Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
decision_needed: false
confidence_score: 98
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
---

# BUG-1383: orchestrator state file overwrites failure details with generic Failed string

## Summary

The orchestrator state file overwrites per-issue failure details with the hardcoded string `"Failed"`, discarding any worker-captured error messages and making post-mortem analysis impossible.

## Current Behavior

When the orchestrator writes the final state file after a parallel sprint run, it replaces every failure reason with the hardcoded string `"Failed"`:

```python
self.state.failed_issues = dict.fromkeys(self.queue.failed_ids, "Failed")
```

Even if the worker captured a meaningful error message, it is thrown away at this point. The state file always shows:

```json
"failed_issues": {
    "BUG-639": "Failed",
    "BUG-637": "Failed"
}
```

## Root Cause

**File**: `scripts/little_loops/orchestrator.py` (line 599)

`dict.fromkeys()` assigns the same value to every key, ignoring any per-issue error detail that the workers may have stored. The orchestrator does not aggregate worker error messages before building the state — or if it does, that information is not passed to this call site.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Correct file path**: `scripts/little_loops/parallel/orchestrator.py` (note the `/parallel/` subdirectory)
- **Anchor**: `ParallelOrchestrator._save_state()` — reconstructs `state.failed_issues` from scratch on every call, always using `dict.fromkeys(self.queue.failed_ids, "Failed")`
- **Second anchor**: `ParallelOrchestrator._on_worker_complete()` (~line 887) — the callback where `result.error` (rich string from `WorkerResult`) is available but only logged; never stored in any accumulator before calling `self.queue.mark_failed(result.issue_id)`
- **Queue design**: `IssuePriorityQueue._failed` is a `set[str]` (IDs only); `mark_failed(issue_id)` takes no error string. The queue has no storage for failure reasons.
- **No existing accumulator**: There is no `_worker_errors` dict or equivalent in `ParallelOrchestrator` or `IssuePriorityQueue`. The proposed attribute must be created.
- **State field is typed correctly**: `OrchestratorState.failed_issues: dict[str, str]` already supports per-issue strings; the schema is correct but never populated with real messages.

## Impact

- `.parallel-manage-state.json` is useless for post-mortem analysis
- Operators must rely on individual worker logs to understand failure causes
- Even after BUG-1381 and BUG-1382 are fixed and workers capture real errors, those errors are discarded here

## Expected Behavior

`failed_issues` in the state file should map each issue ID to its actual failure reason as captured by the worker that processed it.

## Steps to Reproduce

1. Run a parallel sprint with multiple issues: `ll-sprint <sprint-name>`
2. Ensure at least one issue worker fails (e.g., supply an issue that causes a Claude error)
3. After the run completes, open `.parallel-manage-state.json`
4. Observe: `"failed_issues"` shows `{"BUG-XXX": "Failed"}` for all failures, regardless of the actual error captured by the worker

## Implementation Steps

1. Audit how `orchestrator.py` receives worker results — identify where per-issue errors are stored (likely a dict or list of `WorkerResult` objects)
2. Add or expose a `_worker_errors` mapping that accumulates `issue_id -> error_string` as workers complete
3. Replace the `dict.fromkeys()` call with a dict comprehension that looks up the actual error

### Codebase Research Findings

_Added by `/ll:refine-issue` — concrete steps with real file references:_

1. In `scripts/little_loops/parallel/orchestrator.py` — `ParallelOrchestrator.__init__()`: add `self._worker_errors: dict[str, str] = {}`
2. In `_on_worker_complete()` (~line 959): add `self._worker_errors[result.issue_id] = result.error or "Failed"` in the failure branch (before `self.queue.mark_failed(...)`)
3. In `_on_worker_complete()` merge-failure branches (~lines 924, 927, 958): add `self._worker_errors[result.issue_id] = f"Merge failed: ..."` before each `mark_failed` call
4. In `_save_state()` (~line 599): replace `dict.fromkeys(self.queue.failed_ids, "Failed")` with `{issue_id: self._worker_errors.get(issue_id, "Failed") for issue_id in self.queue.failed_ids}`
5. In `scripts/tests/test_orchestrator.py` — extend `test_save_state_writes_file()` (~line 1092): inject a mock `WorkerResult` with a specific `.error` string, trigger `_on_worker_complete()`, then assert the state file's `failed_issues` contains the actual string (not `"Failed"`). Follow test pattern in `scripts/tests/test_state.py` `TestStateManager.test_mark_failed()`
6. Verify: `python -m pytest scripts/tests/test_orchestrator.py -v -k "save_state or worker_complete"`

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

7. Extend `test_orchestrator.py::TestOnWorkerComplete::test_on_worker_complete_failure` (~line 1494) — after the existing `mark_failed` assertion, add: `assert orchestrator._worker_errors["BUG-001"] == "Processing failed"`
8. Extend `test_orchestrator.py::TestOnWorkerComplete::test_on_worker_complete_failure_marks_failed` (~line 2836) — same: add `_worker_errors` assertion alongside the existing `mark_failed` assertion
9. Write `TestStateManagement::test_save_state_uses_worker_errors_not_generic_failed` — directly sets `orchestrator._worker_errors`, calls `_save_state()`, asserts the state file contains the real error string (not `"Failed"`) — this is the primary regression guard for BUG-1383
10. Write `TestStateManagement::test_save_state_fallback_for_unknown_failed_id` — failed ID with no `_worker_errors` entry; assert fallback `"Failed"` is written
11. Write `TestOnWorkerComplete::test_on_worker_complete_stores_error_in_worker_errors` — constructs `WorkerResult(error="…")`, calls `_on_worker_complete()`, asserts `_worker_errors` populated
12. Write `TestOnWorkerComplete::test_on_worker_complete_stores_fallback_when_error_is_none` — `WorkerResult(error=None)`; assert `_worker_errors[id] == "Failed"`

## Proposed Solution

```python
# Before (line 599):
self.state.failed_issues = dict.fromkeys(self.queue.failed_ids, "Failed")

# After:
self.state.failed_issues = {
    issue_id: self._worker_errors.get(issue_id, "Failed")
    for issue_id in self.queue.failed_ids
}
```

Where `self._worker_errors` is populated as workers report failures. The exact attribute name depends on the current orchestrator design — adjust accordingly.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Complete implementation (3 coordinated changes in `scripts/little_loops/parallel/orchestrator.py`):**

**Change 1 — Initialize accumulator in `__init__`:**
```python
# in ParallelOrchestrator.__init__()
self._worker_errors: dict[str, str] = {}
```

**Change 2 — Populate accumulator in `_on_worker_complete()` failure branch (~line 959–961):**
```python
# Before:
else:
    self.logger.error(f"{result.issue_id} failed: {result.error}")
    self.queue.mark_failed(result.issue_id)

# After:
else:
    self.logger.error(f"{result.issue_id} failed: {result.error}")
    self._worker_errors[result.issue_id] = result.error or "Failed"
    self.queue.mark_failed(result.issue_id)
```

Also populate `_worker_errors` at the merge-failure branches (~lines 924, 927, 958):
```python
self._worker_errors[result.issue_id] = f"Merge failed: {result.error or 'merge error'}"
self.queue.mark_failed(result.issue_id)
```

**Change 3 — Use accumulator in `_save_state()` (~line 599):**
```python
# Before:
self.state.failed_issues = dict.fromkeys(self.queue.failed_ids, "Failed")

# After (already proposed above — confirmed correct):
self.state.failed_issues = {
    issue_id: self._worker_errors.get(issue_id, "Failed")
    for issue_id in self.queue.failed_ids
}
```

**Note on downstream consumers**: `_load_state()` and `_scan_issues()` only consume `.keys()` of `failed_issues`, so changing the values has no impact on resume behavior.

## Integration Map

### Files to Modify
- `scripts/little_loops/orchestrator.py` — replace `dict.fromkeys()` call at the state-write site with dict comprehension using accumulated worker errors

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel_manager.py` — likely where `WorkerResult` objects are collected; may need to surface error strings to orchestrator
- `scripts/little_loops/worker.py` — source of per-issue error strings passed back to orchestrator

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/cli/parallel.py` — `main_parallel()` instantiates `ParallelOrchestrator` and calls `.run()`; no changes needed but will exercise the fixed code path [Agent 1 finding]
- `scripts/little_loops/cli/sprint/run.py` — `_cmd_sprint_run()` creates `ParallelOrchestrator` per wave and calls `._load_state()`, `._save_state()`, `._cleanup()`, `.run()`; only consumes `.keys()` of `failed_issues` for skip logic so no changes needed, but is the primary exerciser of the fixed path [Agent 1 finding]
- `scripts/little_loops/parallel/__init__.py` — exports `ParallelOrchestrator`, `OrchestratorState`, `WorkerResult`; no changes needed [Agent 1 finding]

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_orchestrator.py` — add test verifying `failed_issues` maps to real error strings when workers report failures
- `scripts/tests/test_parallel_manager.py` — verify error propagation from worker to orchestrator (**NOTE**: this file does not exist; `test_orchestrator.py` is the correct target — see Codebase Research Findings above)

_Wiring pass added by `/ll:wire-issue`:_

**Tests to update (extend existing):**
- `test_orchestrator.py::TestOnWorkerComplete::test_on_worker_complete_failure` (~line 1494) — currently only asserts `queue.mark_failed` called; extend to also assert `orchestrator._worker_errors["BUG-001"] == "Processing failed"` [Agent 3 finding]
- `test_orchestrator.py::TestOnWorkerComplete::test_on_worker_complete_failure_marks_failed` (~line 2836) — same gap; extend to assert `_worker_errors` populated with `result.error` [Agent 3 finding]

**New tests to write in `test_orchestrator.py`:**
- `TestStateManagement::test_save_state_uses_worker_errors_not_generic_failed` — set `orchestrator._worker_errors = {"BUG-002": "Claude CLI exited with stderr: tool not found"}`, call `_save_state()`, assert `saved["failed_issues"]["BUG-002"] == "Claude CLI exited with stderr: tool not found"` and `!= "Failed"` [Agent 3 finding]
- `TestStateManagement::test_save_state_fallback_for_unknown_failed_id` — failed ID in queue with no `_worker_errors` entry; assert `saved["failed_issues"]["BUG-003"] == "Failed"` (fallback) [Agent 3 finding]
- `TestOnWorkerComplete::test_on_worker_complete_stores_error_in_worker_errors` — `WorkerResult(error="Claude CLI exited with code 1: stderr output here")`; assert `_worker_errors["BUG-001"] == "Claude CLI exited with code 1: stderr output here"` [Agent 3 finding]
- `TestOnWorkerComplete::test_on_worker_complete_stores_fallback_when_error_is_none` — `WorkerResult(error=None)`; assert `_worker_errors["BUG-002"] == "Failed"` [Agent 3 finding]

**Pattern to follow** for `WorkerResult` construction: `test_on_worker_complete_failure` (line 1494) and `TestWorkerResult` class in `test_parallel_types.py`.

### Documentation
- N/A

### Configuration
- N/A

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Corrected Files to Modify:**
- `scripts/little_loops/parallel/orchestrator.py` — two changes needed:
  1. `ParallelOrchestrator.__init__()`: initialize `self._worker_errors: dict[str, str] = {}`
  2. `ParallelOrchestrator._on_worker_complete()` (~line 961 failure branch): store `self._worker_errors[result.issue_id] = result.error or "Failed"` before calling `self.queue.mark_failed()`
  3. `ParallelOrchestrator._save_state()` (~line 599): replace `dict.fromkeys(...)` with dict comprehension using `_worker_errors`
  4. Additional `mark_failed` call sites for merge failures (~lines 924, 927, 958, 1028, 1039, 1069): populate `_worker_errors` with merge failure reasons

**Corrected Dependent Files:**
- `scripts/little_loops/parallel/worker_pool.py` — source of `WorkerResult.error`; already populated with detailed strings at all failure paths in `_process_issue()`; no changes needed here
- `scripts/little_loops/parallel/priority_queue.py` — `IssuePriorityQueue.mark_failed()` takes only an ID; **no change needed** — error accumulation happens in orchestrator, not queue
- `scripts/little_loops/parallel/types.py` — `WorkerResult.error: str | None` and `OrchestratorState.failed_issues: dict[str, str]`; no changes needed

**Similar patterns for the fix:**
- `scripts/little_loops/state.py` in `StateManager.mark_failed(issue_id, reason)` — sequential path accumulates per-issue reasons directly into `state.failed_issues[issue_id] = reason`
- `scripts/little_loops/cli/sprint/run.py` (~lines 358, 429) — `state.failed_issues[issue_id] = "reason string"` direct assignment pattern

**Corrected Tests:**
- `scripts/tests/test_orchestrator.py` in `test_save_state_writes_file()` (~line 1092) — existing test to extend: assert `failed_issues["BUG-XXX"]` equals `WorkerResult.error`, not `"Failed"`
- `scripts/tests/test_state.py` in `TestStateManager.test_mark_failed()` — precedent test pattern showing `assert manager.state.failed_issues["BUG-003"] == "Timeout after 3600s"`
- No `test_parallel_manager.py` exists; `test_orchestrator.py` is the right target

## Verification

1. Apply fixes for BUG-1381, BUG-1382, and this bug
2. Run `ll-sprint bug-fixes --only-ids <failing-id>`
3. Open `.parallel-manage-state.json` — `failed_issues` should show the actual error string rather than `"Failed"`

## Related Issues

- BUG-1381: subprocess output parser silently discards result events (root cause)
- BUG-1382: worker pool error messages use only stderr (middle layer)

## Labels

`bug`, `orchestrator`, `parallel-sprint`, `state-file`, `error-reporting`

## Resolution

**Fixed** in `scripts/little_loops/parallel/orchestrator.py`:

1. Added `self._worker_errors: dict[str, str] = {}` accumulator in `__init__`
2. Populated `_worker_errors` at every `mark_failed` site in `_on_worker_complete`, `_merge_sequential`, and `_wait_for_completion` with the actual error string (or a descriptive fallback)
3. Replaced `dict.fromkeys(self.queue.failed_ids, "Failed")` in `_save_state` with a dict comprehension that looks up each issue's real error from `_worker_errors`

`failed_issues` in `.parallel-manage-state.json` now maps each failed issue ID to its actual error message.

## Status

**Closed** | Created: 2026-05-09 | Resolved: 2026-05-09 | Priority: P2

## Session Log
- `/ll:manage-issue` - 2026-05-09T17:45:49Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c49660b3-0907-465e-b442-b379b2d1ada1.jsonl`
- `/ll:ready-issue` - 2026-05-09T17:41:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/c49660b3-0907-465e-b442-b379b2d1ada1.jsonl`
- `/ll:confidence-check` - 2026-05-09T18:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/074a8ea3-cf5b-40c7-aa71-7820f518b8e8.jsonl`
- `/ll:wire-issue` - 2026-05-09T17:38:01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a14a3932-428b-48b4-812b-96120fc2fe9a.jsonl`
- `/ll:refine-issue` - 2026-05-09T17:32:34 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e376f922-0fff-4125-b1ac-98cec8ed6b39.jsonl`
- `/ll:format-issue` - 2026-05-09T16:53:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19555582-4ac3-4961-9f72-7680d5a59791.jsonl`
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

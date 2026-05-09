---
id: BUG-1383
type: BUG
priority: P2
status: active
captured_at: "2026-05-09T01:55:56Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
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

## Integration Map

### Files to Modify
- `scripts/little_loops/orchestrator.py` — replace `dict.fromkeys()` call at the state-write site with dict comprehension using accumulated worker errors

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel_manager.py` — likely where `WorkerResult` objects are collected; may need to surface error strings to orchestrator
- `scripts/little_loops/worker.py` — source of per-issue error strings passed back to orchestrator

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_orchestrator.py` — add test verifying `failed_issues` maps to real error strings when workers report failures
- `scripts/tests/test_parallel_manager.py` — verify error propagation from worker to orchestrator

### Documentation
- N/A

### Configuration
- N/A

## Verification

1. Apply fixes for BUG-1381, BUG-1382, and this bug
2. Run `ll-sprint bug-fixes --only-ids <failing-id>`
3. Open `.parallel-manage-state.json` — `failed_issues` should show the actual error string rather than `"Failed"`

## Related Issues

- BUG-1381: subprocess output parser silently discards result events (root cause)
- BUG-1382: worker pool error messages use only stderr (middle layer)

## Labels

`bug`, `orchestrator`, `parallel-sprint`, `state-file`, `error-reporting`

## Status

**Open** | Created: 2026-05-09 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-05-09T16:53:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/19555582-4ac3-4961-9f72-7680d5a59791.jsonl`
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

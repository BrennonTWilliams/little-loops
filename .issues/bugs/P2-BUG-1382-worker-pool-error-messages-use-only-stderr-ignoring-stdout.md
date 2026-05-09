---
id: BUG-1382
type: BUG
priority: P2
status: active
captured_at: "2026-05-09T01:55:56Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
---

# BUG-1382: worker pool error messages use only stderr ignoring stdout

## Problem Statement

When `ready-issue` or `manage-issue` subprocess calls fail in the parallel worker pool, the error message is constructed using only `stderr`:

```python
error=f"ready-issue failed: {ready_result.stderr}"
```

Claude CLI writes errors to stdout as JSON events, not to stderr. Since stderr is always empty for Claude CLI failures, this produces truncated messages like `"ready-issue failed: "` with nothing after the colon.

## Root Cause

**File**: `scripts/little_loops/worker_pool.py` (lines 302 and 462)

The worker pool assumes the conventional Unix error model where stderr contains error text. Claude CLI uses `--output-format stream-json` and puts all output (including errors) into stdout JSON events. The result is that `ready_result.stderr` is always empty when Claude CLI fails.

This is a secondary bug downstream of BUG-1381 (result events are discarded before stdout can be useful), but it would remain a problem even after BUG-1381 is fixed if the fallback logic is not added.

## Impact

- All `ll-sprint` and `ll-parallel` failures show empty error strings in logs and state files
- Operators have no information about failure cause at the point of failure
- Debugging requires manually searching raw session JSONL files

## Expected Behavior

When `stderr` is empty, the error message should include a snippet of `stdout` so some diagnostic information is preserved even in the worst case.

## Implementation Steps

1. Locate both error-construction sites in `worker_pool.py` (lines ~302 and ~462)
2. Replace the bare `ready_result.stderr` reference with a fallback expression
3. Truncate the stdout fallback to avoid flooding state files with multi-KB output
4. Apply the same pattern to both `ready-issue` and `manage-issue` error paths

## Suggested Fix

```python
# Before (both locations):
error=f"ready-issue failed: {ready_result.stderr}"

# After:
err_detail = ready_result.stderr or (ready_result.stdout or "")[:500]
error=f"ready-issue failed: {err_detail}"
```

Apply the same fix at the `manage-issue` equivalent location (~line 462).

## Verification

1. After fixing BUG-1381 and this bug, trigger a sprint failure
2. The error entry in `.parallel-manage-state.json` should contain either stderr text or a 500-char stdout snippet
3. The worker log line should be informative rather than truncated

## Related Issues

- BUG-1381: subprocess output parser silently discards result events (primary cause)
- BUG-1383: orchestrator state file overwrites failure details (downstream)

## Session Log
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

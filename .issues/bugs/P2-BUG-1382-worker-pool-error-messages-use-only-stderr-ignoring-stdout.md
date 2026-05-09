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

## Summary

When `ready-issue` or `manage-issue` subprocess calls fail in the parallel worker pool, the error message is constructed using only `stderr`:

```python
error=f"ready-issue failed: {ready_result.stderr}"
```

Claude CLI writes errors to stdout as JSON events, not to stderr. Since stderr is always empty for Claude CLI failures, this produces truncated messages like `"ready-issue failed: "` with nothing after the colon.

## Current Behavior

`worker_pool.py` constructs failure error messages using `ready_result.stderr`. For Claude CLI subprocesses, `stderr` is always empty because all output — including errors — is written to stdout as `--output-format stream-json` events. The resulting error messages are always truncated to `"ready-issue failed: "` with no diagnostic detail.

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

## Steps to Reproduce

1. Trigger a sprint failure via `ll-sprint` or `ll-parallel` where `ready-issue` exits non-zero
2. Check `.parallel-manage-state.json` — observe `"ready-issue failed: "` with nothing after the colon
3. Check worker logs — observe the same truncated error message
4. Observe: `ready_result.stderr` is always empty because Claude CLI writes to stdout

## Implementation Steps

1. Locate both error-construction sites in `worker_pool.py` (lines ~302 and ~462)
2. Replace the bare `ready_result.stderr` reference with a fallback expression
3. Truncate the stdout fallback to avoid flooding state files with multi-KB output
4. Apply the same pattern to both `ready-issue` and `manage-issue` error paths

## Integration Map

### Files to Modify
- `scripts/little_loops/worker_pool.py` — update error message construction at `_run_ready_issue()` (~line 302) and `_run_manage_issue()` (~line 462)

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "worker_pool" scripts/`

### Similar Patterns
- TBD - search for similar stderr-only usage: `grep -rn "\.stderr" scripts/little_loops/`

### Tests
- TBD - identify test files for `worker_pool`

### Documentation
- N/A

### Configuration
- N/A

## Proposed Solution

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

## Labels
`bug`, `worker-pool`, `error-handling`, `captured`

## Status
**Open** | Created: 2026-05-09 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-05-09T16:54:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d87a2dd4-2942-4324-b2d7-27ac23ef9a20.jsonl`
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

---
id: BUG-1381
type: BUG
priority: P2
status: active
captured_at: "2026-05-09T01:55:56Z"
discovered_date: "2026-05-09"
discovered_by: capture-issue
---

# BUG-1381: subprocess output parser silently discards result events

## Problem Statement

When Claude CLI runs with `--output-format stream-json`, it emits multiple JSON event types including `result`, `assistant`, `tool_use`, and `system/init`. The output parser in `subprocess_utils.py` only keeps `assistant` and `system/init` events — all other event types, including `result`, are silently discarded with `continue`.

The `result` event is where Claude CLI reports exit status and error details when a subprocess fails. By discarding it, all diagnostic information about why a subprocess failed is lost before it can be surfaced.

## Root Cause

**File**: `scripts/little_loops/subprocess_utils.py` (~line 213)

```python
else:
    continue  # skip other event types (result, tool_use, etc.)
```

The `run_claude_command()` function's streaming JSON parser has no handler for `result`-type events. When Claude CLI exits non-zero, the error reason is in the `result` event's `error` or `result` field, but this is unconditionally skipped.

## Impact

- Sprint runs (`ll-sprint`, `ll-parallel`) that fail show empty error messages: `"ready-issue failed: "` with nothing after the colon
- `.parallel-manage-state.json` stores no useful failure detail
- Operators cannot determine why a sprint failed without manual log inspection
- Cascades into BUG-1382 (worker_pool stderr fallback) and BUG-1383 (orchestrator state overwrite)

## Expected Behavior

When a Claude CLI subprocess exits non-zero, the error text from the `result` event should be captured and made available as part of the `stderr` output or a dedicated error field on the result object.

## Implementation Steps

1. In `run_claude_command()` in `subprocess_utils.py`, add a handler for `etype == "result"` before the `else: continue` branch
2. Extract `event.get("error") or event.get("result", "")` from the result event
3. If non-empty, append it to `stderr_lines` with a `[result]` prefix so downstream callers see it
4. Ensure the handler does not break the existing `assistant`/`system` event flow

## Suggested Fix

```python
elif etype == "result":
    result_error = event.get("error") or event.get("result", "")
    if result_error:
        stderr_lines.append(f"[result] {result_error}")
    continue
```

**Location**: `scripts/little_loops/subprocess_utils.py` around line 213, inside the streaming JSON event loop.

## Verification

1. Run `ll-sprint bug-fixes --only-ids <any-failing-id>` after the fix
2. Check `.parallel-manage-state.json` — `failed_issues` values should contain actual error text instead of `"Failed"`
3. The worker log should show `"ready-issue failed: [result] <actual-error>"` instead of `"ready-issue failed: "`

## Related Issues

- BUG-1382: worker_pool.py error messages use only stderr (downstream effect)
- BUG-1383: orchestrator state file overwrites failure details (downstream effect)

## Session Log
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

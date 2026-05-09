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

## Summary

When Claude CLI runs with `--output-format stream-json`, it emits multiple JSON event types including `result`, `assistant`, `tool_use`, and `system/init`. The output parser in `subprocess_utils.py` only keeps `assistant` and `system/init` events — all other event types, including `result`, are silently discarded with `continue`.

The `result` event is where Claude CLI reports exit status and error details when a subprocess fails. By discarding it, all diagnostic information about why a subprocess failed is lost before it can be surfaced.

## Current Behavior

The `run_claude_command()` function in `subprocess_utils.py` parses `--output-format stream-json` output but only handles `assistant` and `system/init` event types. All other event types — including `result` events that contain exit status and error details — are silently skipped via `continue`. When a Claude CLI subprocess exits non-zero, all failure diagnostic information is lost before it can be surfaced to callers.

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

## Steps to Reproduce

1. Run `ll-sprint` or `ll-parallel` with an issue that causes `ready-issue` or `manage-issue` to exit non-zero
2. After the sprint completes, inspect `.parallel-manage-state.json`
3. Observe: `failed_issues` entries contain `"ready-issue failed: "` with nothing after the colon
4. Observe: no diagnostic text from the Claude CLI subprocess is captured

## Implementation Steps

1. In `run_claude_command()` in `subprocess_utils.py`, add a handler for `etype == "result"` before the `else: continue` branch
2. Extract `event.get("error") or event.get("result", "")` from the result event
3. If non-empty, append it to `stderr_lines` with a `[result]` prefix so downstream callers see it
4. Ensure the handler does not break the existing `assistant`/`system` event flow

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — add `result` event handler in `run_claude_command()` streaming JSON loop

### Dependent Files (Callers/Importers)
- TBD - use grep to find references: `grep -r "run_claude_command" scripts/`

### Similar Patterns
- TBD - search for consistent event handling: `grep -rn "etype ==" scripts/little_loops/`

### Tests
- TBD - identify test files for `subprocess_utils`

### Documentation
- N/A

### Configuration
- N/A

## Proposed Solution

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

## Labels
`bug`, `subprocess`, `parser`, `captured`

## Status
**Open** | Created: 2026-05-09 | Priority: P2

## Session Log
- `/ll:format-issue` - 2026-05-09T16:54:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d87a2dd4-2942-4324-b2d7-27ac23ef9a20.jsonl`
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

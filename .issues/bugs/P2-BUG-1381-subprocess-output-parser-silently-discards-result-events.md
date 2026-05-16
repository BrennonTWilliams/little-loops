---
id: BUG-1381
type: BUG
priority: P2
status: done
captured_at: '2026-05-09T01:55:56Z'
completed_at: '2026-05-09T17:11:55Z'
discovered_date: '2026-05-09'
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 85
score_complexity: 25
score_test_coverage: 25
score_ambiguity: 25
score_change_surface: 10
---

# BUG-1381: subprocess output parser silently discards result events

## Summary

When Claude CLI runs with `--output-format stream-json`, it emits multiple JSON event types including `result`, `assistant`, `tool_use`, and `system/init`. The output parser in `subprocess_utils.py` only keeps `assistant` and `system/init` events — all other event types, including `result`, are silently discarded with `continue`.

The `result` event is where Claude CLI reports exit status and error details when a subprocess fails. By discarding it, all diagnostic information about why a subprocess failed is lost before it can be surfaced.

## Current Behavior

The `run_claude_command()` function in `subprocess_utils.py` parses `--output-format stream-json` output but only handles `assistant` and `system/init` event types. All other event types — including `result` events that contain exit status and error details — are silently skipped via `continue`. When a Claude CLI subprocess exits non-zero, all failure diagnostic information is lost before it can be surfaced to callers.

## Root Cause

**File**: `scripts/little_loops/subprocess_utils.py` (line 377)

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

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be verified/included in the implementation:_

5. Verify `scripts/little_loops/fsm/runners.py` (`DefaultActionRunner.run()`) — no code change needed, but confirm that `ActionResult.stderr` now carries `[result]` prefixed text through to `fsm/executor.py` `_route_action()` as intended
6. Verify `scripts/little_loops/issue_lifecycle.py` (`classify_failure()`) — confirm that `[result] <error text>` prefix does not inadvertently trigger TRANSIENT classification for errors that should be REAL; the `[result]` prefix itself is harmless but the error text content matters
7. Add `test_result_event_is_error_appends_to_stderr` to `TestRunClaudeCommandModelDetection` in `test_subprocess_utils.py`
8. Add `test_result_event_no_is_error_does_not_append_to_stderr` to `TestRunClaudeCommandModelDetection` in `test_subprocess_utils.py`
9. Update `docs/reference/API.md` `run_claude_command` section to document that `CompletedProcess.stderr` includes `[result] <error>` lines on `is_error=True` result events

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- **Step 1 correction**: The `elif etype == "result":` branch **already exists** at `subprocess_utils.py:377` — extend it, do NOT add a new branch.
- The branch currently only calls `on_usage()`; add extraction of `event.get("is_error")` and `event.get("error")` before the `continue`, then append to `stderr_lines` if non-empty.
- `stderr_lines` is initialized at `subprocess_utils.py:305`; it becomes `CompletedProcess.stderr` returned to all callers.
- After the fix, `worker_pool.py:456` will produce `error=f"manage-issue failed: <actual Claude error text>"` instead of an empty trailing string.
- **Scope note**: `orchestrator._save_state()` hardcodes `dict.fromkeys(failed_ids, "Failed")` (BUG-1383) — this fix improves logger output and `WorkerResult.error` but does not change the `.parallel-manage-state.json` value; that requires BUG-1383.
- Test helper: use `_make_single_line_selector()` from `TestRunClaudeCommandModelDetection` in `test_subprocess_utils.py:1336` for new test; mock a result event with `{"type": "result", "is_error": true, "error": "session failed"}` and assert it appears in `result.stderr`.

## Integration Map

### Files to Modify
- `scripts/little_loops/subprocess_utils.py` — add `result` event handler in `run_claude_command()` streaming JSON loop

### Dependent Files (Callers/Importers)
- `scripts/little_loops/parallel/worker_pool.py` — `WorkerPool._run_claude_command()` (line 641) aliases `run_claude_command` as `_run_claude_base`; at line 456 constructs `error=f"manage-issue failed: {manage_result.stderr}"` — empty without this fix
- `scripts/little_loops/issue_manager.py` — wrapper at line 97 calls `_run_claude_base`; `process_issue_inplace()` at line 767 falls back to `result.stderr or result.stdout` but still misses structured `result` event error data
- `scripts/little_loops/cli/action.py` — `cmd_action()` collects its own `stderr_lines` via `stream_callback`; shares accumulation pattern, unaffected by this fix

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/little_loops/fsm/runners.py` — `DefaultActionRunner.run()` calls `run_claude_command()` at line 119 and sets `ActionResult(stderr=completed.stderr, ...)`; after the fix, FSM action steps with `is_error=True` result events will propagate `[result] <error>` through `ActionResult.stderr` into `classify_failure()` via `fsm/executor.py`
- `scripts/little_loops/fsm/executor.py` — `_route_action()` at line 684 combines `action_result.output + action_result.stderr` into `_combined` for `classify_failure()`; the fix expands what appears in `action_result.stderr`, which may change failure classification for FSM loop steps
- `scripts/little_loops/issue_lifecycle.py` — `classify_failure()` at line 54 receives `result.stderr` as `error_output` and does case-insensitive substring matching; the `[result]` prefix is benign but error text from result events (e.g., "prompt is too long") may now trigger TRANSIENT classification where it previously triggered REAL

### Similar Patterns
- `scripts/little_loops/subprocess_utils.py:377` — the `elif etype == "result":` branch **already exists** and reads `usage` from the event; the fix extends this branch to also read `event.get("is_error")` and `event.get("error")`
- `scripts/little_loops/fsm/evaluators.py:657` — `evaluate_llm_structured()` shows the full `result` event field access pattern: `subtype`, `is_error`, `structured_output`, `result` (legacy)

### Tests
- `scripts/tests/test_subprocess_utils.py` — existing tests: `test_on_usage_callback_called_with_result_event` (line 1492) and `test_unknown_event_type_skipped` (line 1468); add new test for `is_error: true` result event appending to `stderr`
- `scripts/tests/test_subprocess_mocks.py` — `TestRunClaudeCommand.test_on_usage_forwarded_through_wrapper()` (line 204) shows mock event pattern to follow for error-propagation test

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_subprocess_utils.py` — **new test**: `test_result_event_is_error_appends_to_stderr` in `TestRunClaudeCommandModelDetection`; use `_make_single_line_selector()` helper; feed `{"type": "result", "is_error": true, "result": "Permission denied: tool failed"}` and assert `"[result] Permission denied: tool failed" in result.stderr`
- `scripts/tests/test_subprocess_utils.py` — **new test**: `test_result_event_no_is_error_does_not_append_to_stderr` in `TestRunClaudeCommandModelDetection`; same setup without `is_error` field; assert `result.stderr == ""` to guard the no-op path
- No existing tests break — no currently-existing test feeds a `result` event with `is_error=True` into the streaming loop AND asserts on `result.stderr`

### Documentation
- N/A

_Wiring pass added by `/ll:wire-issue`:_
- `docs/reference/API.md` — `run_claude_command` section (around line 1994) states "Returns: `CompletedProcess` with stdout/stderr captured" but does not document that `CompletedProcess.stderr` will now include `[result] <error>` lines when a result event with `is_error=True` is present; update to document this behavior

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

**Location**: `scripts/little_loops/subprocess_utils.py` line 377, inside the streaming JSON event loop.

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

## Resolution

**Status**: Fixed
**Completed**: 2026-05-09T17:11:55Z
**Fix**: Extended the `elif etype == "result":` branch in `run_claude_command()` to extract `event.get("is_error")` and `event.get("error")` (falling back to `event.get("result")`). When `is_error` is truthy and error text is non-empty, appends `[result] <error>` to `stderr_lines`, making failure diagnostics available to all callers via `CompletedProcess.stderr`.

**Files changed**:
- `scripts/little_loops/subprocess_utils.py` — added error extraction in `result` event handler
- `scripts/tests/test_subprocess_utils.py` — added `test_result_event_is_error_appends_to_stderr` and `test_result_event_no_is_error_does_not_append_to_stderr`
- `docs/reference/API.md` — documented `[result]`-prefixed stderr behavior

## Session Log
- `/ll:ready-issue` - 2026-05-09T17:10:05 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/17942ca2-2a72-4fee-9617-7186ec68032d.jsonl`
- `/ll:confidence-check` - 2026-05-09T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/73e189c2-e1b8-4ed9-9d39-49351d7af088.jsonl`
- `/ll:wire-issue` - 2026-05-09T17:06:03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/99670389-b94b-4da0-92a2-394f540ed26b.jsonl`
- `/ll:refine-issue` - 2026-05-09T16:59:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d24f0aab-3407-484e-9776-09b8ceba7a15.jsonl`
- `/ll:format-issue` - 2026-05-09T16:54:11 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d87a2dd4-2942-4324-b2d7-27ac23ef9a20.jsonl`
- `/ll:capture-issue` - 2026-05-09T01:55:56Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fff9609e-8a5a-401a-87db-430505c5cf93.jsonl`

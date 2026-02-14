---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-327: ll-auto continuation bypasses skill completion logic

## Summary

When `ll-auto` detects a `CONTEXT_HANDOFF` signal during `/ll:manage-issue`, it spawns a continuation session by passing raw context via `claude -p '...'` instead of invoking `/ll:resume` or `/ll:manage-issue --resume`. This means the continuation session runs without the manage_issue skill's lifecycle context, so the file-move-to-completed step never executes even when implementation succeeds.

## Current Behavior

1. `ll-auto` runs `claude -p '/ll:manage-issue bug fix BUG-XXX'`
2. Session hits context limit, emits `CONTEXT_HANDOFF` with continuation prompt
3. `ll-auto` detects handoff, reads continuation prompt content
4. Spawns new session: `claude -p '<raw continuation prompt>'` — no skill invocation
5. Continuation session implements the fix successfully but doesn't move issue to `completed/`
6. Verify phase sees issue still in `bugs/`, reports "0 issues processed"

## Expected Behavior

Continuation sessions should invoke the manage_issue skill so its completion logic (moving issue file, updating status) runs after successful implementation. Either:
- Use `/ll:manage-issue bug fix BUG-XXX --resume`
- Or use `/ll:resume` which reads `.claude/ll-continue-prompt.md`

## Steps to Reproduce

1. Run `ll-auto --only BUG-XXXX` on an issue complex enough to trigger context handoff
2. Observe the continuation session is invoked with raw `-p` content
3. Even if implementation succeeds, issue is not moved to `completed/`
4. Summary reports "Issues processed: 0"

## Actual Behavior

Implementation succeeds in the continuation session but all bookkeeping is skipped — issue stays in `bugs/` with status "Implemented" in content but file not moved.

## Root Cause

- **File**: `scripts/little_loops/issue_manager.py`
- **Anchor**: `run_with_continuation()` function, continuation command construction after `detect_context_handoff()`
- **Cause**: The continuation command is built as raw prompt content (`current_command = prompt_content.replace(...)`) instead of re-invoking `/ll:manage-issue ... --resume`

## Proposed Solution

Modify `ll-auto`'s handoff handling to invoke the skill in the continuation session:

```python
# In run_with_continuation(), instead of:
current_command = prompt_content.replace('"', '\\"')

# Wrap continuation in skill invocation that preserves lifecycle:
current_command = f"/ll:manage-issue {type_name} {action} {issue_id} --resume"
```

This ensures the manage_issue skill loads, reads the continuation prompt from `.claude/ll-continue-prompt.md`, and runs its full lifecycle including completion.

Note: `run_with_continuation` may need additional parameters (issue type, action, issue ID) to construct the skill command. The caller at line ~481 already has this context.

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_manager.py` — `run_with_continuation()` continuation command construction

### Dependent Files (Callers/Importers)
- `ll-auto` CLI entry point

### Similar Patterns
- `scripts/little_loops/parallel/worker_pool.py` — has identical handoff handling pattern at ~line 722, needs same fix for consistency

### Tests
- `scripts/tests/test_issue_manager.py` — add test for continuation command format

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate handoff detection and continuation command construction in `issue_manager.py`
2. Change continuation command to use `/ll:manage-issue ... --resume` instead of raw prompt
3. Verify `/ll:resume` or `--resume` flag properly reads `.claude/ll-continue-prompt.md`
4. Add test covering continuation command format

## Impact

- **Priority**: P2 - Causes silent failure in automated workflows; work is done but not tracked
- **Effort**: Small - Single code change in command construction
- **Risk**: Low - Only affects continuation path, well-isolated
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `ll-auto`, `captured`

---

## Status

**Completed** | Created: 2026-02-11 | Completed: 2026-02-11 | Priority: P2

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-11
- **Status**: Completed

### Changes Made
- `scripts/little_loops/issue_manager.py`: Changed continuation command from raw prompt content to `initial_command + " --resume"`
- `scripts/little_loops/parallel/worker_pool.py`: Same fix for parallel worker continuation
- `scripts/tests/test_issue_manager.py`: Added test verifying continuation uses `--resume` flag

### Verification Results
- Tests: PASS (2675 passed)
- Lint: PASS

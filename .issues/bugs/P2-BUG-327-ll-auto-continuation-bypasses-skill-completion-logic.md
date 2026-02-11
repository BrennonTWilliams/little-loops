---
discovered_date: 2026-02-11
discovered_by: capture_issue
---

# BUG-327: ll-auto continuation bypasses skill completion logic

## Summary

When `ll-auto` detects a `CONTEXT_HANDOFF` signal during `/ll:manage_issue`, it spawns a continuation session by passing raw context via `claude -p '...'` instead of invoking `/ll:resume` or `/ll:manage_issue --resume`. This means the continuation session runs without the manage_issue skill's lifecycle context, so the file-move-to-completed step never executes even when implementation succeeds.

## Current Behavior

1. `ll-auto` runs `claude -p '/ll:manage_issue bug fix BUG-XXX'`
2. Session hits context limit, emits `CONTEXT_HANDOFF` with continuation prompt
3. `ll-auto` detects handoff, reads continuation prompt content
4. Spawns new session: `claude -p '<raw continuation prompt>'` — no skill invocation
5. Continuation session implements the fix successfully but doesn't move issue to `completed/`
6. Verify phase sees issue still in `bugs/`, reports "0 issues processed"

## Expected Behavior

Continuation sessions should invoke the manage_issue skill so its completion logic (moving issue file, updating status) runs after successful implementation. Either:
- Use `/ll:manage_issue bug fix BUG-XXX --resume`
- Or use `/ll:resume` which reads `.claude/ll-continue-prompt.md`

## Steps to Reproduce

1. Run `ll-auto --only BUG-XXXX` on an issue complex enough to trigger context handoff
2. Observe the continuation session is invoked with raw `-p` content
3. Even if implementation succeeds, issue is not moved to `completed/`
4. Summary reports "Issues processed: 0"

## Actual Behavior

Implementation succeeds in the continuation session but all bookkeeping is skipped — issue stays in `bugs/` with status "Implemented" in content but file not moved.

## Root Cause

- **File**: `scripts/little_loops/auto.py` (or equivalent ll-auto entry point)
- **Anchor**: Continuation session spawning logic after `CONTEXT_HANDOFF` detection
- **Cause**: The continuation command is built as raw `-p '<context>'` instead of `-p '/ll:manage_issue ... --resume'`

## Proposed Solution

Modify `ll-auto`'s handoff handling to invoke the skill in the continuation session:

```python
# Instead of:
cmd = f"claude --dangerously-skip-permissions -p '{continuation_prompt}'"

# Use:
cmd = f"claude --dangerously-skip-permissions -p '/ll:manage_issue {type} fix {issue_id} --resume'"
```

This ensures the manage_issue skill loads, reads the continuation prompt from `.claude/ll-continue-prompt.md`, and runs its full lifecycle including completion.

## Integration Map

### Files to Modify
- `scripts/little_loops/auto.py` — continuation session command construction

### Dependent Files (Callers/Importers)
- `ll-auto` CLI entry point

### Similar Patterns
- `ll-parallel` may have similar handoff handling — check for consistency

### Tests
- `scripts/tests/test_auto.py` — add test for continuation command format

### Documentation
- N/A

### Configuration
- N/A

## Implementation Steps

1. Locate handoff detection and continuation command construction in `auto.py`
2. Change continuation command to use `/ll:manage_issue ... --resume` instead of raw prompt
3. Verify `/ll:resume` or `--resume` flag properly reads `.claude/ll-continue-prompt.md`
4. Add test covering continuation command format

## Impact

- **Priority**: P2 - Causes silent failure in automated workflows; work is done but not tracked
- **Effort**: Small - Single code change in command construction
- **Risk**: Low - Only affects continuation path, well-isolated
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize_issues` to discover and link relevant docs._

## Labels

`bug`, `ll-auto`, `captured`

---

## Status

**Open** | Created: 2026-02-11 | Priority: P2

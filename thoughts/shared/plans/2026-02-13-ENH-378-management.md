# ENH-378: precompact-state.sh exit 2 for visible feedback - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-378-precompact-state-exit-2-for-visible-feedback.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

`hooks/scripts/precompact-state.sh` preserves task state before context compaction. At line 84, it exits with code 0 after writing a stderr message at line 82. Per `docs/claude-code/hooks-reference.md:460`, exit 0 stderr is only visible in verbose mode (Ctrl+O). Exit 2 for PreCompact is non-blocking and "Shows stderr to user only".

### Key Discoveries
- `hooks/scripts/precompact-state.sh:84` — `exit 0` after stderr message
- `docs/claude-code/hooks-reference.md:460` — PreCompact exit 2: "No [can't block] | Shows stderr to user only"
- `hooks/scripts/context-monitor.sh:283` — existing exit 2 pattern for PostToolUse user feedback

### Patterns to Follow
- `context-monitor.sh:282-283` uses `exit 2` with stderr for user-visible feedback — same pattern needed here

## Desired End State

`precompact-state.sh` exits with code 2 so the stderr message is visible to the user without verbose mode.

### How to Verify
- Script exits with code 2 (check source)
- Lint, tests, and type checks pass
- Comment updated to reflect new semantics

## What We're NOT Doing
- Not changing the stderr message text
- Not modifying other hook scripts' exit codes
- Not adding new PreCompact hook behavior

## Solution Approach

Change `exit 0` to `exit 2` at line 84 and update the inline comment to reflect the new semantics.

## Implementation Phases

### Phase 1: Change Exit Code

#### Changes Required

**File**: `hooks/scripts/precompact-state.sh`
**Line 84**: Replace `exit 0` with `exit 2` and update comment

```bash
# Before (line 84):
exit 0

# After:
exit 2  # PreCompact: non-blocking, shows stderr to user
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/`
- [ ] Lint passes: `ruff check scripts/`
- [ ] Types pass: `python -m mypy scripts/little_loops/`
- [ ] `grep -c 'exit 2' hooks/scripts/precompact-state.sh` shows the exit 2 is present

## Testing Strategy

No unit tests needed — this is a shell script exit code change. Verified by:
1. Source inspection confirming `exit 2` at end of script
2. Existing test suite passing (no regressions)

## References
- Issue: `.issues/enhancements/P4-ENH-378-precompact-state-exit-2-for-visible-feedback.md`
- Exit code docs: `docs/claude-code/hooks-reference.md:460`
- Similar pattern: `hooks/scripts/context-monitor.sh:282-283`

# BUG-361: user-prompt-check.sh exit 2 erases user prompt — Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-361-user-prompt-check-exit-2-erases-user-prompt.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

`hooks/scripts/user-prompt-check.sh` is a `UserPromptSubmit` hook that fires on every user prompt. When prompt optimization is enabled and the prompt passes all bypass checks, the script builds optimization content from a template and attempts to inject it into the conversation.

### Key Discoveries
- `user-prompt-check.sh:100` — outputs content to stderr with `>&2`
- `user-prompt-check.sh:101` — exits with code 2
- `user-prompt-check.sh:103` — dead `exit 0` never reached
- Per `docs/claude-code/hooks-reference.md:449`: UserPromptSubmit + exit 2 = "Blocks prompt processing and erases the prompt"
- The correct pattern for adding context: exit 0 + stdout (plain text or JSON)

### Current State
- Other hooks like `context-monitor.sh` correctly use exit 2 for `PostToolUse` events (where it shows stderr to Claude)
- `check-duplicate-issue-id.sh` demonstrates proper exit 0 + JSON patterns for `PreToolUse`
- Test at `test_hooks_integration.py:191` accepts both exit codes 0 and 2

## Desired End State

The script should use `exit 0` with stdout output so that:
1. The user's original prompt is preserved
2. The optimization template content is added as context alongside the prompt
3. No dead code remains

### How to Verify
- Script exits with code 0 when optimization triggers (not 2)
- Output goes to stdout (not stderr)
- Dead `exit 0` on line 103 is removed
- Tests pass with updated expectations
- Lint and type checks pass

## What We're NOT Doing

- Not changing the bypass logic or template substitution
- Not changing the hook configuration in hooks.json
- Not refactoring the template file
- Not changing how other hooks work

## Problem Analysis

The comment on line 98 references GitHub issue #11224, suggesting exit 2 + stderr was used to "ensure it reaches Claude." This may have been correct at the time or for a different hook event, but for `UserPromptSubmit`, exit 2 means "block and erase the prompt."

## Solution Approach

Minimal fix: change the output mechanism from stderr+exit 2 to stdout+exit 0, and remove dead code.

## Implementation Phases

### Phase 1: Fix the hook script

#### Overview
Change exit code and output stream in `user-prompt-check.sh`.

#### Changes Required

**File**: `hooks/scripts/user-prompt-check.sh`
**Changes**: Replace lines 98-103

From:
```bash
# Output to stderr with exit 2 to ensure it reaches Claude
# Reference: https://github.com/anthropics/claude-code/issues/11224
echo "$HOOK_CONTENT" >&2
exit 2

exit 0
```

To:
```bash
# Output to stdout with exit 0 — added as context alongside the user's prompt
# Reference: docs/claude-code/hooks-reference.md (UserPromptSubmit decision control)
echo "$HOOK_CONTENT"
exit 0
```

### Phase 2: Update tests

#### Overview
Update the test assertion that currently accepts exit code 2.

#### Changes Required

**File**: `scripts/tests/test_hooks_integration.py`
**Changes**: Update line 191 and comment on lines 193-194

From:
```python
            # Should exit cleanly (either 0 for skip or 2 for optimization)
            assert result.returncode in (0, 2), f"Unexpected exit code: {result.returncode}"

            # No errors on stderr (except valid hook output)
            # The hook may output prompts on stderr with exit 2
```

To:
```python
            # Should exit cleanly with 0 (skip or optimization context added)
            assert result.returncode == 0, f"Unexpected exit code: {result.returncode}"

            # No errors on stderr (optimization output goes to stdout)
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_hooks_integration.py -v`
- [ ] Lint passes: `ruff check scripts/`

## Testing Strategy

### Unit Tests
- Existing parametrized tests cover special character handling
- Tests now verify exit code is always 0
- Verify no stderr output for normal operation

## References

- Original issue: `.issues/bugs/P2-BUG-361-user-prompt-check-exit-2-erases-user-prompt.md`
- Hooks reference: `docs/claude-code/hooks-reference.md:449` (exit 2 behavior table)
- Hooks reference: `docs/claude-code/hooks-reference.md:671-700` (UserPromptSubmit decision control)
- Similar correct pattern: `hooks/scripts/check-duplicate-issue-id.sh:17-20`

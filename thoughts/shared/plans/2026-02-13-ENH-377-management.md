# ENH-377: Remove silently-ignored matchers from UserPromptSubmit and Stop hooks - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P4-ENH-377-remove-ignored-matchers-from-userpromptsubmit-and-stop.md`
- **Type**: enhancement
- **Priority**: P4
- **Action**: improve

## Current State Analysis

`hooks/hooks.json` defines six hook events. Both `UserPromptSubmit` (line 17) and `Stop` (line 53) include `"matcher": "*"` fields that are silently ignored by Claude Code's hook system. Per `docs/claude-code/hooks-reference.md`, these events don't support matchers and always fire on every occurrence.

### Key Discoveries
- `hooks/hooks.json:17` — UserPromptSubmit has `"matcher": "*"` (ignored)
- `hooks/hooks.json:53` — Stop has `"matcher": "*"` (ignored)
- `docs/claude-code/hooks-reference.md:194` — Documents that these matchers are silently ignored
- Other events (SessionStart, PreToolUse, PostToolUse, PreCompact) correctly use matchers

## Desired End State

`hooks/hooks.json` with `"matcher"` removed from `UserPromptSubmit` and `Stop` entries only.

### How to Verify
- JSON is valid after edits
- No behavioral change (matchers were already ignored)

## What We're NOT Doing

- Not changing matchers on SessionStart, PreToolUse, PostToolUse, or PreCompact (those support matchers)
- Not adding any new fields or restructuring the file

## Solution Approach

Delete the `"matcher": "*"` line from both `UserPromptSubmit` and `Stop` entries in `hooks/hooks.json`.

## Implementation Phases

### Phase 1: Remove matchers

#### Changes Required

**File**: `hooks/hooks.json`
- Remove `"matcher": "*",` from UserPromptSubmit entry (line 17)
- Remove `"matcher": "*",` from Stop entry (line 53)

#### Success Criteria

**Automated Verification**:
- [ ] `python -c "import json; json.load(open('hooks/hooks.json'))"` — JSON is valid
- [ ] `python -m pytest scripts/tests/` — Tests pass

## References

- Issue: `.issues/enhancements/P4-ENH-377-remove-ignored-matchers-from-userpromptsubmit-and-stop.md`
- Hooks reference: `docs/claude-code/hooks-reference.md:194`

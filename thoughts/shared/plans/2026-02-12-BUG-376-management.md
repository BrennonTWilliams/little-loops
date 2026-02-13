# BUG-376: Hook timeouts 1000x too large - Implementation Plan

## Issue Reference
- **File**: `.issues/bugs/P2-BUG-376-hook-timeouts-1000x-too-large-seconds-not-ms.md`
- **Type**: bug
- **Priority**: P2
- **Action**: fix

## Current State Analysis

All 6 hooks in `hooks/hooks.json` use timeout values assuming milliseconds (e.g., `5000` for 5s). Per `docs/claude-code/hooks-reference.md` line 255, `timeout` is in **seconds**. Current values create 50–250 minute timeouts instead of 3–15 seconds.

### Key Discoveries
- `hooks/hooks.json:10` — SessionStart timeout: `5000` (83 min, intended 5s)
- `hooks/hooks.json:22` — UserPromptSubmit timeout: `3000` (50 min, intended 3s)
- `hooks/hooks.json:34` — PreToolUse timeout: `5000` (83 min, intended 5s)
- `hooks/hooks.json:46` — PostToolUse timeout: `5000` (83 min, intended 5s)
- `hooks/hooks.json:58` — Stop timeout: `15000` (250 min, intended 15s)
- `hooks/hooks.json:70` — PreCompact timeout: `5000` (83 min, intended 5s)
- `docs/claude-code/hooks-reference.md:255` — "Seconds before canceling. Defaults: 600 for command, 30 for prompt, 60 for agent"

## Desired End State

All timeout values divided by 1000 to reflect correct seconds units.

### How to Verify
- Read hooks.json and confirm values are 5, 3, 5, 5, 15, 5
- JSON remains valid

## What We're NOT Doing
- Not changing hook commands or matchers
- Not changing any other hook configuration
- Not adding comments to JSON (not supported)

## Solution Approach

Simple find-and-replace of 6 integer values in hooks.json.

## Implementation Phases

### Phase 1: Fix Timeout Values

**File**: `hooks/hooks.json`
**Changes**: Replace all 6 timeout values

| Hook | Old | New |
|:-----|:----|:----|
| SessionStart | 5000 | 5 |
| UserPromptSubmit | 3000 | 3 |
| PreToolUse | 5000 | 5 |
| PostToolUse | 5000 | 5 |
| Stop | 15000 | 15 |
| PreCompact | 5000 | 5 |

#### Success Criteria
- [ ] All 6 timeout values corrected
- [ ] JSON is valid
- [ ] No other changes to the file

## References
- Original issue: `.issues/bugs/P2-BUG-376-hook-timeouts-1000x-too-large-seconds-not-ms.md`
- Hooks reference: `docs/claude-code/hooks-reference.md:255`

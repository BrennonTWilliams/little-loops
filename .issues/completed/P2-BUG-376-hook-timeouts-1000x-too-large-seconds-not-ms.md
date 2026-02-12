---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
supersedes: P4-ENH-362 (that issue assumed milliseconds; the unit is seconds)
---

# BUG-376: All hook timeout values are 1000x too large — unit is seconds, not milliseconds

## Summary

All 6 hooks in `hooks/hooks.json` use timeout values like `5000` and `15000`, assuming milliseconds. Per the hooks reference, the `timeout` field is in **seconds**. The actual timeouts are 50–250 minutes instead of the intended 3–15 seconds.

Previously filed ENH-362 proposed reducing the Stop timeout from "15000ms to 8000ms" — but 15000 is already 15000 **seconds** (250 minutes), not 15 seconds.

## Location

- **File**: `hooks/hooks.json` — all 6 hook entries

## Steps to Reproduce

1. Open `hooks/hooks.json`
2. Observe all 6 hook entries have timeout values like `5000`, `3000`, `15000`
3. Compare against `docs/claude-code/hooks-reference.md` which states timeout is in **seconds**
4. Observe: a timeout of `5000` means 5000 seconds (83 minutes), not 5 seconds

## Actual Behavior

All hook timeouts are 1000x larger than intended. A hung hook script would block Claude Code for 50–250 minutes instead of the intended 3–15 seconds.

## Current Behavior

| Hook | Config Value | Actual Timeout | Intended |
|:-----|:-------------|:---------------|:---------|
| SessionStart | `5000` | 83 min | ~5s |
| UserPromptSubmit | `3000` | 50 min | ~3s |
| PreToolUse | `5000` | 83 min | ~5s |
| PostToolUse | `5000` | 83 min | ~5s |
| Stop | `15000` | 250 min | ~15s |
| PreCompact | `5000` | 83 min | ~5s |

## Expected Behavior

```json
"timeout": 5     // SessionStart (was 5000)
"timeout": 3     // UserPromptSubmit (was 3000)
"timeout": 5     // PreToolUse (was 5000)
"timeout": 5     // PostToolUse (was 5000)
"timeout": 15    // Stop (was 15000)
"timeout": 5     // PreCompact (was 5000)
```

## Root Cause

- **File**: `hooks/hooks.json`
- **Anchor**: all 6 hook `timeout` fields
- **Cause**: Values were written assuming milliseconds (e.g., `5000` for 5s) but the Claude Code hooks API interprets `timeout` as seconds per the hooks reference documentation.

## Proposed Solution

Divide each timeout value by 1000:

```json
"timeout": 5      // SessionStart  (was 5000)
"timeout": 3      // UserPromptSubmit (was 3000)
"timeout": 5      // PreToolUse  (was 5000)
"timeout": 5      // PostToolUse (was 5000)
"timeout": 15     // Stop  (was 15000)
"timeout": 5      // PreCompact  (was 5000)
```

## Reference

- `docs/claude-code/hooks-reference.md` — Common fields table: `timeout | no | Seconds before canceling. Defaults: 600 for command, 30 for prompt, 60 for agent`
- `docs/claude-code/hooks-reference.md` — Debug output example: `[DEBUG] Executing hook command: <Your command> with timeout 600000ms` (600 seconds → 600000ms internally)

## Impact

- **Priority**: P2 (a hung script blocks Claude Code for up to 250 minutes instead of 15 seconds)
- **Effort**: Trivial — divide each value by 1000
- **Risk**: Low — correcting to intended values

## Labels

`bug`, `hooks`, `configuration`, `all-hooks`

## Session Log
- `/ll:manage_issue` - 2026-02-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/48db0381-0764-40ba-82b8-463944cc1eba.jsonl`

---

## Resolution

- **Action**: fix
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `hooks/hooks.json`: Divided all 6 timeout values by 1000 (seconds, not milliseconds)
  - SessionStart: 5000 → 5
  - UserPromptSubmit: 3000 → 3
  - PreToolUse: 5000 → 5
  - PostToolUse: 5000 → 5
  - Stop: 15000 → 15
  - PreCompact: 5000 → 5

### Verification Results
- Tests: PASS (2694 passed)
- Lint: PASS

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-12 | Priority: P2

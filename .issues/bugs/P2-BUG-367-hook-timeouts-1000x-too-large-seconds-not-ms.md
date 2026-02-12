---
discovered_date: 2026-02-12
discovered_by: hooks-reference-audit
supersedes: P4-ENH-362 (that issue assumed milliseconds; the unit is seconds)
---

# BUG-367: All hook timeout values are 1000x too large — unit is seconds, not milliseconds

## Summary

All 6 hooks in `hooks/hooks.json` use timeout values like `5000` and `15000`, assuming milliseconds. Per the hooks reference, the `timeout` field is in **seconds**. The actual timeouts are 50–250 minutes instead of the intended 3–15 seconds.

Previously filed ENH-362 proposed reducing the Stop timeout from "15000ms to 8000ms" — but 15000 is already 15000 **seconds** (250 minutes), not 15 seconds.

## Location

- **File**: `hooks/hooks.json` — all 6 hook entries

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

## Reference

- `docs/claude-code/hooks-reference.md` — Common fields table: `timeout | no | Seconds before canceling. Defaults: 600 for command, 30 for prompt, 60 for agent`
- `docs/claude-code/hooks-reference.md` — Debug output example: `[DEBUG] Executing hook command: <Your command> with timeout 600000ms` (600 seconds → 600000ms internally)

## Impact

- **Priority**: P2 (a hung script blocks Claude Code for up to 250 minutes instead of 15 seconds)
- **Effort**: Trivial — divide each value by 1000
- **Risk**: Low — correcting to intended values

## Labels

`bug`, `hooks`, `configuration`, `all-hooks`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P2

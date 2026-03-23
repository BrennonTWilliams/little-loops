---
id: BUG-865
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# BUG-865: context-monitor exits 2 on every tool call after threshold (no rate-limit)

## Summary

After the 80% context threshold is crossed in `context-monitor.sh`, every subsequent tool call fires `exit 2` with a stderr message. There is no rate-limiting — each of the 10+ consecutive Read calls in a busy session each produce a "PostToolUse:Read hook error" in the UI, creating a disruptive flood of error messages.

## Current Behavior

Once `USAGE_PERCENT >= THRESHOLD`, every tool call that reaches the exit-2 path (lines 326-335 of `context-monitor.sh`) emits a reminder and exits 2. With `set -euo pipefail` and no cooldown, 10 consecutive Read operations produce 10 "hook error" entries in the Claude Code UI.

## Expected Behavior

The exit 2 reminder should fire at most once per 60 seconds. Between reminders, the hook should write state and exit 0 silently. The user sees the warning periodically rather than on every single tool call.

## Motivation

The flood of "hook error" messages is disruptive and erodes trust in the hook system. Users are more likely to disable `context_monitor` entirely than tolerate the noise, defeating the purpose of the feature. Rate-limiting the reminder gives the same signal with dramatically less friction.

## Steps to Reproduce

1. Run a session until context usage exceeds 80%
2. Make 10+ consecutive Read/tool calls without running `/ll:handoff`
3. Observe: 10 "PostToolUse:Read hook error" messages in the UI

## Root Cause

- **File**: `hooks/scripts/context-monitor.sh`
- **Anchor**: `main()` → exit 2 block (after `HANDOFF_COMPLETE` check)
- **Cause**: No `last_reminder_at` tracking. Every call that passes the threshold and fails the `HANDOFF_COMPLETE` check unconditionally reaches `exit 2`. The `HANDOFF_COMPLETE = true` short-circuit (line 302) only fires after `/ll:handoff` is explicitly run.

## Proposed Solution

Add a `last_reminder_at` field to state. Before `exit 2`, check if 60 seconds have elapsed since the last reminder. If not, write state and `exit 0` silently.

```bash
# After extracting HANDOFF_COMPLETE (~line 245), extract:
LAST_REMINDER_AT=$(echo "$STATE" | jq -r '.last_reminder_at // ""')

# Before exit 2 block, add cooldown check:
NOW_EPOCH=$(date +%s)
LAST_EPOCH=$(to_epoch "${LAST_REMINDER_AT:-}")
if [ "$LAST_EPOCH" -gt 0 ] && [ $((NOW_EPOCH - LAST_EPOCH)) -lt 60 ]; then
    write_state "$NEW_STATE"
    release_lock "$STATE_LOCK"
    exit 0
fi
# Update last_reminder_at before exit 2:
NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$(date -u +%Y-%m-%dT%H:%M:%SZ)" '.last_reminder_at = $t')
```

## Integration Map

### Files to Modify
- `hooks/scripts/context-monitor.sh` — add `last_reminder_at` tracking and cooldown check

### Dependent Files (Callers/Importers)
- `hooks/hooks.json` — registers context-monitor.sh as PostToolUse hook

### Similar Patterns
- `hooks/scripts/user-prompt-check.sh` — similar exit 2 pattern, may benefit from same treatment

### Tests
- No existing shell tests for context-monitor.sh; verify manually per plan verification steps

### Documentation
- `docs/reference/hooks.md` (if exists) — may document hook behavior

### Configuration
- `ll-config.json` `context_monitor` section — no new config keys needed (hardcode 60s or make configurable)

## Implementation Steps

1. Extract `LAST_REMINDER_AT` from state after `HANDOFF_COMPLETE` extraction
2. Add 60-second cooldown check before the `exit 2` block
3. Update `last_reminder_at` in `NEW_STATE` before emitting the reminder
4. Verify: trigger 10+ Read calls above threshold, confirm only 1 "hook error" in 60s window

## Impact

- **Priority**: P2 — Disruptive UX regression; erodes confidence in hook system; users likely to disable context_monitor
- **Effort**: Small — ~10 lines added to context-monitor.sh; no new dependencies
- **Risk**: Low — cooldown logic is additive; existing behavior preserved outside the rate-limit window
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`hooks`, `context-monitor`, `captured`

## Session Log
- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/520e79f8-0528-4c6d-92c0-e09d2d2aa372.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P2

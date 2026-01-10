---
discovered_commit: null
discovered_branch: main
discovered_date: 2026-01-10T00:00:00Z
discovered_by: manual
---

# ENH-013: Persistent Handoff Reminder Until Completion

## Summary

Enhance the context-monitor hook to persistently remind Claude to run `/ll:handoff` after crossing the context threshold, continuing reminders on every PostToolUse until handoff is actually completed.

## Motivation

The current implementation outputs a single reminder when the 80% context threshold is crossed, then sets `handoff_triggered: true` to prevent spam. However, Claude may ignore or get distracted from this single message, leading to context exhaustion without a proper handoff.

Previous attempts with prompt-based hooks caused infinite recursion. This approach stays fully command-based while being more persistent.

## Current Behavior

1. PostToolUse hook tracks estimated token usage
2. When threshold (80%) is crossed, outputs: "Run /ll:handoff"
3. Sets `handoff_triggered: true` - never reminds again
4. Claude may ignore, context exhausts, work is lost

## Expected Behavior

1. PostToolUse hook tracks estimated token usage
2. When threshold crossed, records `threshold_crossed_at` timestamp
3. On EVERY subsequent PostToolUse:
   - Check if `.claude/ll-continue-prompt.md` exists AND was modified after `threshold_crossed_at`
   - If NO: output reminder with current usage percentage
   - If YES: handoff complete, stop reminding
4. Persistent reminders make it hard for Claude to ignore

## Proposed Implementation

### 1. State File Changes

Update `.claude/ll-context-state.json` schema:

```json
{
  "session_start": "2026-01-10T10:30:00Z",
  "estimated_tokens": 125000,
  "tool_calls": 63,
  "threshold_crossed_at": "2026-01-10T11:45:00Z",
  "handoff_complete": false,
  "breakdown": {
    "read": 60000,
    "bash": 30000
  }
}
```

New fields:
- `threshold_crossed_at`: ISO timestamp when threshold was first crossed (replaces `handoff_triggered` boolean)
- `handoff_complete`: Explicitly track completion

### 2. Updated Logic in context-monitor.sh

```bash
# After threshold check
if [ "$USAGE_PERCENT" -ge "$THRESHOLD" ]; then
    # Record threshold crossing time if not already set
    THRESHOLD_TIME=$(jq -r '.threshold_crossed_at // ""' "$STATE_FILE")
    if [ -z "$THRESHOLD_TIME" ]; then
        THRESHOLD_TIME=$(date -u +%Y-%m-%dT%H:%M:%SZ)
        NEW_STATE=$(echo "$NEW_STATE" | jq --arg t "$THRESHOLD_TIME" '.threshold_crossed_at = $t')
    fi

    # Check if handoff was completed
    HANDOFF_DONE=false
    if [ -f ".claude/ll-continue-prompt.md" ]; then
        PROMPT_MTIME=$(stat -f %m ".claude/ll-continue-prompt.md" 2>/dev/null || echo "0")
        THRESHOLD_EPOCH=$(date -j -f "%Y-%m-%dT%H:%M:%SZ" "$THRESHOLD_TIME" +%s 2>/dev/null || echo "0")
        if [ "$PROMPT_MTIME" -gt "$THRESHOLD_EPOCH" ]; then
            HANDOFF_DONE=true
            NEW_STATE=$(echo "$NEW_STATE" | jq '.handoff_complete = true')
        fi
    fi

    # Output reminder if handoff not done
    if [ "$HANDOFF_DONE" = "false" ]; then
        echo "[ll] Context ~${USAGE_PERCENT}% used. Run /ll:handoff to save your work."
    fi
fi
```

### 3. Cross-Platform Compatibility

Handle differences between macOS and Linux for `stat` and `date` commands:

```bash
# Get file mtime (cross-platform)
get_mtime() {
    if stat -f %m "$1" 2>/dev/null; then
        return  # macOS
    fi
    stat -c %Y "$1" 2>/dev/null  # Linux
}

# Parse ISO date to epoch (cross-platform)
parse_iso_date() {
    if date -j -f "%Y-%m-%dT%H:%M:%SZ" "$1" +%s 2>/dev/null; then
        return  # macOS
    fi
    date -d "$1" +%s 2>/dev/null  # Linux
}
```

## Location

- **Modified**: `hooks/scripts/context-monitor.sh`
- **Modified**: `hooks/prompts/context-monitor.md` (update documentation)

## Acceptance Criteria

- [ ] State file records `threshold_crossed_at` timestamp when threshold first crossed
- [ ] Reminder outputs on every PostToolUse after threshold until handoff complete
- [ ] Handoff detected by checking `.claude/ll-continue-prompt.md` modification time
- [ ] Reminders stop once handoff file is updated after threshold crossing
- [ ] Works on both macOS and Linux
- [ ] No prompt-based hooks (command-only to avoid recursion)

## Impact

- **Severity**: Medium - Prevents work loss from ignored handoff prompts
- **Effort**: Small - Modification to existing script
- **Risk**: Low - Command-based hook, no recursion risk

## Dependencies

- Existing context-monitor.sh hook
- `/ll:handoff` command (writes to `.claude/ll-continue-prompt.md`)

## Blocked By

None

## Blocks

None

## Labels

`enhancement`, `hooks`, `context-management`, `handoff`

---

## Status

**Open** | Created: 2026-01-10 | Priority: P2

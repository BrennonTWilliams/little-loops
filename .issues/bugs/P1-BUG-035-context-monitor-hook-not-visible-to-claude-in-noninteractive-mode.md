# BUG-035: Context Monitor Hook Output Not Visible to Claude in Non-Interactive Mode

## Summary

The `context-monitor.sh` PostToolUse hook outputs plain text warnings when context threshold is reached, but this output is not visible to Claude in non-interactive mode (`claude -p`). This breaks automatic session handoff for `ll-auto` and `ll-parallel`.

## Current Behavior

1. Hook runs on every PostToolUse event (confirmed working)
2. When context >= 80%, outputs: `[ll] Context ~82% used... Run /ll:handoff...`
3. Exits with code 0
4. **In non-interactive mode**: stdout with exit 0 only appears in verbose mode for users, NOT as feedback to Claude
5. Claude never sees the warning and never knows to run `/ll:handoff`
6. Context eventually exhausts without handoff occurring

## Expected Behavior

Claude should receive the context warning as feedback and autonomously run `/ll:handoff` before context exhaustion.

## Root Cause

Per Claude Code hook documentation:
- Exit code 0: stdout shown to user in verbose mode only
- Exit code 2 with stderr: feedback sent to Claude
- JSON output with `"decision": "block"` and `"reason"`: reason sent to Claude as feedback

The current implementation uses plain text with `exit 0`, which doesn't trigger Claude feedback.

## Affected Components

- `hooks/scripts/context-monitor.sh` (lines 237-242)
- `ll-auto` (issue_manager.py) - detection works, but never triggers
- `ll-parallel` (worker_pool.py) - detection works, but never triggers

## Impact

| Mode | Hook Runs | Claude Sees Warning | Handoff Works |
|------|-----------|---------------------|---------------|
| Interactive | Yes | Yes (verbose/user) | User can act |
| Non-interactive | Yes | **No** | **No** |

## Proposed Fix

Update `context-monitor.sh` to output JSON with decision when threshold reached:

```bash
# Instead of plain text output:
echo '{
  "decision": "block",
  "reason": "[ll] Context ~'"${USAGE_PERCENT}"'% used. Run /ll:handoff to preserve your work before context exhaustion.",
  "continue": true
}'
```

With `"continue": true`, processing continues but Claude receives the `reason` as feedback.

## Files to Modify

- `hooks/scripts/context-monitor.sh`

## Testing

1. Run `ll-auto` on a task that consumes significant context
2. Verify Claude receives context warning feedback
3. Verify Claude runs `/ll:handoff` autonomously
4. Verify `ll-auto` detects `CONTEXT_HANDOFF` signal and spawns continuation

## References

- `docs/SESSION_HANDOFF.md` - Documents expected behavior
- `scripts/little_loops/subprocess_utils.py:24-37` - Detection logic (works correctly)
- Claude Code hooks documentation: https://code.claude.com/docs/en/hooks.md#hook-output

## Priority Justification

P1 - This is a core automation feature that is documented but non-functional. Users relying on automatic context handoff in `ll-auto`/`ll-parallel` will experience context exhaustion failures.

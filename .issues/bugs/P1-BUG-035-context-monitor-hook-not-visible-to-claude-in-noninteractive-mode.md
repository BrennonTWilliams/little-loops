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

Per Claude Code hook documentation and GitHub issues #3983 and #11224:
- Exit code 0 with stdout: shown to user in verbose mode only, NOT sent to Claude as feedback
- Exit code 2 with stderr: feedback sent to Claude (recommended for PostToolUse)
- JSON output with `"decision": "block"` and `"reason"`: works for Stop/SubagentStop hooks only, NOT PostToolUse (see issue #3983)

The current implementation uses plain text with `exit 0`, which doesn't trigger Claude feedback in non-interactive mode.

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

Update `context-monitor.sh` (lines 235-242) to output to stderr with exit code 2:

```bash
# Handoff not complete - output reminder to Claude
# Use exit 2 with stderr to ensure feedback reaches Claude in non-interactive mode
# Reference: https://github.com/anthropics/claude-code/issues/11224
write_state "$NEW_STATE"
echo "[ll] Context ~${USAGE_PERCENT}% used (${NEW_TOKENS}/${CONTEXT_LIMIT} tokens estimated). Run /ll:handoff to preserve your work before context exhaustion." >&2
exit 2
```

**Why this works**: Per Claude Code hook documentation and GitHub issue #11224, PostToolUse hooks with exit code 2 send stderr to Claude as feedback. This is the documented and tested approach for PostToolUse hooks.

**Note**: The JSON output format with `"decision": "block"` documented for hooks does NOT work for PostToolUse hooks (see GitHub issue #3983). That format is only for Stop/SubagentStop hooks.

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

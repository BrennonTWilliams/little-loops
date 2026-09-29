---
target: Claude Code hooks
date: '2026-09-28'
status: proven
assertions:
- claim: PreToolUse stdin JSON has hook_event_name == PreToolUse
  result: pass
- claim: PreToolUse stdin JSON has tool_name == Bash and tool_input.command
  result: pass
- claim: PreToolUse stdin JSON includes session_id and cwd
  result: pass
- claim: exit 2 blocks the tool call (command never runs)
  result: pass
- claim: exit 2 stderr text is fed back to the model
  result: pass
- claim: exit 0 with no output allows the tool call
  result: pass
- claim: exit 0 + permissionDecision deny blocks the tool call
  result: pass
- claim: permissionDecisionReason is fed back to the model
  result: pass
- claim: hook with non-matching matcher (Write) does not fire for Bash
  result: pass
raw_output_path: .ll/learning-tests/raw/claude-code-hooks.txt
---

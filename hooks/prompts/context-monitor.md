---
event: PostToolUse
---

# Context Monitor Hook

Proactively estimate context usage and automatically trigger handoff before hitting limits.

## Check if Enabled

1. Read config from `.claude/ll-config.json` or `ll-config.json`
2. Check `context_monitor.enabled` - if `false` or missing, **silently exit** (no output)

## Configuration Defaults

```json
{
  "context_monitor": {
    "enabled": false,
    "auto_handoff_threshold": 80,
    "context_limit_estimate": 150000,
    "state_file": ".claude/ll-context-state.json",
    "estimate_weights": {
      "read_per_line": 10,
      "tool_call_base": 100,
      "bash_output_per_char": 0.3
    }
  }
}
```

## Context Estimation Logic

For each tool call, estimate tokens added to context:

| Tool | Estimation Formula |
|------|-------------------|
| Read | `lines_read × read_per_line` |
| Grep | `output_lines × read_per_line × 0.5` |
| Bash | `output_chars × bash_output_per_char` |
| Glob | `file_count × 20` (paths are short) |
| Write/Edit | `lines_changed × read_per_line × 0.3` |
| Task | `2000` (subagent results are summarized) |
| WebFetch | `1500` (typical page summary) |
| Other | `tool_call_base` |

### Running Total

1. Read current state from `state_file` (default: `.claude/ll-context-state.json`)
2. If missing or malformed, initialize:
   ```json
   {
     "session_start": "<ISO timestamp>",
     "estimated_tokens": 0,
     "tool_calls": 0,
     "handoff_triggered": false
   }
   ```
3. Add estimated tokens from current tool call
4. Increment `tool_calls`
5. Write updated state

## Auto-Handoff Logic

Calculate: `usage_percent = (estimated_tokens / context_limit_estimate) × 100`

### At Auto-Handoff Threshold (default 80%)

If `usage_percent >= auto_handoff_threshold` AND `handoff_triggered != true`:

1. Update `handoff_triggered` to `true` in state file
2. Output notification:
   ```
   [ll] Context ~{usage_percent}% used - triggering automatic handoff
   ```
3. **Execute `/ll:handoff` command** to generate continuation prompt and signal handoff

This ensures:
- Work is preserved before context exhaustion
- Fresh session can continue seamlessly
- No manual intervention required

## State File Format

`.claude/ll-context-state.json`:
```json
{
  "session_start": "2026-01-06T10:30:00Z",
  "estimated_tokens": 120000,
  "tool_calls": 63,
  "handoff_triggered": true,
  "breakdown": {
    "Read": 60000,
    "Bash": 30000,
    "Grep": 15000,
    "other": 15000
  }
}
```

## Important Notes

- This is a **heuristic estimation** - actual token usage varies
- Conservative estimates are better than optimistic ones
- Handoff triggers **once** per session (won't spam)
- Silent operation when disabled (default)
- The `/ll:handoff` command preserves all state for fresh session resume

## Reset Behavior

The state file is **not** automatically reset. To reset:
- Delete `.claude/ll-context-state.json`
- Or start a new session (SessionStart hook resets automatically)

A new session starts with fresh context = fresh tracking.

---
discovered_date: 2026-03-23
discovered_by: capture-issue
---

# ENH-872: UserPromptSubmit hook timeout 3s too tight in hooks.json

## Summary

The `UserPromptSubmit` hook in `hooks.json` has a 3-second timeout — the tightest of any hook in the file. The script it runs (`user-prompt-check.sh`) sources `common.sh`, reads and parses `ll-config.json` with `jq`, reads a markdown template file (~100+ lines), and performs string substitution on the prompt. On a cold filesystem cache or slow start, 3 seconds is insufficient and the hook times out, silently dropping the optimization. All other hooks use 5–15 seconds.

## Current Behavior

```json
{
  "type": "command",
  "command": "bash ${CLAUDE_PLUGIN_ROOT}/hooks/scripts/user-prompt-check.sh",
  "timeout": 3,
  "statusMessage": "Checking prompt..."
}
```

3-second timeout. Under cold-start conditions, the script may not finish before the timeout, causing the optimization template to be silently dropped.

## Expected Behavior

The `UserPromptSubmit` hook should have a 5-second timeout (consistent with `SessionStart`, `PostToolUse`, and `PreCompact`), giving the script adequate time to complete even on a cold start.

## Motivation

A tight timeout here means the plugin's prompt optimization feature fails intermittently in a way that's invisible to the user (hook silently times out, no error shown). Since this hook fires on every user prompt, intermittent failures mean the optimization feature is unreliable. Increasing from 3s to 5s aligns with the rest of the hooks.json and has no perceptible UX cost.

## Proposed Solution

```json
// Before:
"timeout": 3,

// After:
"timeout": 5,
```

## Integration Map

### Files to Modify
- `hooks/hooks.json` — update `UserPromptSubmit` timeout

### Dependent Files (Callers/Importers)
- N/A — timeout is consumed by the Claude Code harness

### Similar Patterns
- `hooks/hooks.json` — all other hooks use 5–15s; this should match

### Tests
- N/A — timeout value is a configuration parameter

### Documentation
- N/A

### Configuration
- `hooks/hooks.json` — the only file to change

## Implementation Steps

1. Update `timeout` from `3` to `5` for `UserPromptSubmit` in `hooks/hooks.json`
2. Verify no regression: test that hook completes within 5s under cold-start conditions

## Scope Boundaries

- Only change the `UserPromptSubmit` timeout value — no changes to the script itself
- Do not change other hook timeouts

## Impact

- **Priority**: P4 - Low urgency; only affects cold-start reliability of an already-broken feature (BUG-868); fix BUG-868 first
- **Effort**: Small - Single integer change in JSON config
- **Risk**: Low - Timeout increase only; no behavior changes
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`hooks`, `enhancement`, `captured`

## Session Log
- `/ll:format-issue` - 2026-03-23T22:42:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1072ecd2-d140-48fe-a825-c355ae538fff.jsonl`

- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e087610-8d6c-49f4-bacd-b3c561cb7252.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P4

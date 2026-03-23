---
discovered_date: 2026-03-23
discovered_by: capture-issue
confidence_score: 100
outcome_confidence: 75
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
- `hooks/hooks.json:23` — `"timeout": 3` in the `UserPromptSubmit` hook entry

### Dependent Files (Callers/Importers)
- N/A — timeout is consumed by the Claude Code harness

### Similar Patterns
- `hooks/hooks.json` — all other hooks: `SessionStart` (5s), `PreToolUse` (5s), `PostToolUse` (5s, 5s), `Stop` (15s), `PreCompact` (5s)

### Tests
- N/A — timeout value is a configuration parameter

### Documentation
- N/A

### Configuration
- `hooks/hooks.json` — the only file to change

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `hooks/hooks.json:17-28` — full `UserPromptSubmit` block; only `timeout` on line 23 needs changing
- `hooks/scripts/user-prompt-check.sh` — sources `hooks/scripts/lib/common.sh` (233 lines) via `ll_resolve_config`, which reads and parses `ll-config.json` with `jq`; this is the primary cold-start overhead source
- `hooks/prompts/optimize-prompt-hook.md` — 96 lines (the template file read at end of script); note: the script references this via `${CLAUDE_PLUGIN_ROOT}/prompts/optimize-prompt-hook.md` but the actual path is `hooks/prompts/optimize-prompt-hook.md` — this path discrepancy is tracked separately as BUG-868

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
- `/ll:confidence-check` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1b17f620-f2da-44e2-8f69-81831236e135.jsonl`
- `/ll:refine-issue` - 2026-03-23T23:00:57 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/8ae56235-5e0d-486f-88e4-8d835df079c9.jsonl`
- `/ll:format-issue` - 2026-03-23T22:42:58 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/1072ecd2-d140-48fe-a825-c355ae538fff.jsonl`

- `/ll:capture-issue` - 2026-03-23T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0e087610-8d6c-49f4-bacd-b3c561cb7252.jsonl`

---

**Open** | Created: 2026-03-23 | Priority: P4

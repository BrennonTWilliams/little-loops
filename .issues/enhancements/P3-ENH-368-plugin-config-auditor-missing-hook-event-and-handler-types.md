---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-368: plugin-config-auditor missing hook event types and handler types

## Summary

The `plugin-config-auditor` agent only recognizes 8 of 14 official Claude Code hook event types and only knows about `command` hooks, missing the `prompt` and `agent` hook handler types. This causes the auditor to flag valid hook configurations as errors. Additionally, the timeout recommendation (<5s) is overly aggressive compared to official defaults.

## Current Behavior

The auditor at `agents/plugin-config-auditor.md:57` lists recognized event types as:
`PreToolUse, PostToolUse, Stop, SessionStart, UserPromptSubmit, PreCompact, SubagentStop, Notification`

Missing 6 event types:
- `PermissionRequest` - fires when permission dialog appears
- `PostToolUseFailure` - fires after a tool call fails
- `SubagentStart` - fires when a subagent is spawned
- `TeammateIdle` - fires when an agent team teammate goes idle
- `TaskCompleted` - fires when a task is marked completed
- `SessionEnd` - fires when a session terminates

The auditor only knows about `type: "command"` hooks, missing:
- `type: "prompt"` - LLM-evaluated prompt hooks
- `type: "agent"` - multi-turn subagent verification hooks

The auditor also doesn't know about hook handler fields: `async`, `statusMessage`, `once`, `model`.

The timeout recommendation at line 58 says `<5s recommended` but official defaults are:
- Command hooks: 600s
- Prompt hooks: 30s
- Agent hooks: 60s

## Expected Behavior

1. All 14 official hook event types should be recognized
2. All 3 hook handler types (`command`, `prompt`, `agent`) should be known
3. Hook handler fields (`async`, `statusMessage`, `once`, `model`) should be validated
4. Timeout recommendations should be type-specific and aligned with official defaults

## Motivation

When the auditor flags valid hook configurations as unrecognized, it produces false positive warnings that reduce trust in the audit results. Users may ignore real issues buried among false positives.

## Proposed Solution

Update `agents/plugin-config-auditor.md`:

1. Replace the event types list at line 57 with all 14 types
2. Add `prompt` and `agent` to recognized hook types in the audit checklist
3. Add validation of additional handler fields (`async`, `statusMessage`, `once`, `model`)
4. Change timeout recommendation from blanket `<5s` to type-specific defaults

## Implementation Steps

1. Update recognized event types in `agents/plugin-config-auditor.md`
2. Update hook audit checklist for new handler types and fields
3. Adjust timeout recommendation to be type-aware

## Impact

- **Priority**: P3 - Produces false positives in audit results
- **Effort**: Small - Single file update with known correct values
- **Risk**: Low - Only affects audit agent prompts
- **Breaking Change**: No

## Scope Boundaries

- Out of scope: Validating hook handler JSON output schemas
- Out of scope: Adding hook configuration linting beyond structure validation

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Agent definitions |
| guidelines | .claude/CLAUDE.md | Plugin component structure |

## Labels

`enhancement`, `captured`, `audit`, `hooks`

## Session Log
- `/ll:capture_issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/00ffa686-5907-4ed1-8765-93f478b14da2.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3

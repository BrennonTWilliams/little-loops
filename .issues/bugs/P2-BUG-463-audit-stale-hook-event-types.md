---
discovered_date: 2026-02-22
discovered_by: conversation-analysis
---

# BUG-463: Audit recognizes only 14 of 17 hook event types

## Motivation

The plugin-config-auditor's hardcoded event type enum creates false positives for users who use newer Claude Code hook events. A developer using `ConfigChange` to react to settings changes, or `WorktreeCreate`/`WorktreeRemove` to manage worktree lifecycle, will have valid hooks flagged as errors — causing them to either remove the hooks or distrust the audit. Keeping the event type list current ensures the audit remains a reliable correctness signal rather than a source of false alarms.

## Summary

The `plugin-config-auditor` agent hardcodes 14 hook event types in its validation prompt, but Claude Code now supports 17 event types. Hooks using `ConfigChange`, `WorktreeCreate`, or `WorktreeRemove` would be flagged as invalid by the audit even though they are legitimate. Additionally, event-specific handler type restrictions are not validated (e.g., `ConfigChange` only supports `command` type, not `prompt` or `agent`).

## Current Behavior

The plugin-config-auditor agent (`agents/plugin-config-auditor.md`) lists these 14 event types as the valid set:

`SessionStart`, `UserPromptSubmit`, `PreToolUse`, `PermissionRequest`, `PostToolUse`, `PostToolUseFailure`, `Notification`, `SubagentStart`, `SubagentStop`, `Stop`, `TeammateIdle`, `TaskCompleted`, `PreCompact`, `SessionEnd`

Missing event types:
- **`ConfigChange`** — fires when settings change; matchers: `user_settings`, `project_settings`, `local_settings`, `policy_settings`, `skills`; supports `command` type only; can block (except `policy_settings`)
- **`WorktreeCreate`** — fires when a worktree is created; supports `command` type only; stdout used as worktree path; non-zero exit = fail
- **`WorktreeRemove`** — fires on worktree cleanup; supports `command` type only; non-blocking

Additionally, the audit does not validate:
- Event-specific handler type restrictions (only some events support `prompt`/`agent` types)
- The `once` field (skills-only hook field)
- The `async` field (background execution for command hooks)
- Event-specific output field support (`additionalContext`, `updatedInput`, `updatedMCPToolOutput` vary by event)

## Expected Behavior

1. All 17 event types should be recognized as valid
2. Handler type should be validated per-event (8 events support all 3 types; 9 events support `command` only)
3. The `once` and `async` fields should be validated when present
4. Warn if a `prompt` or `agent` handler is defined for a command-only event

## Steps to Reproduce

1. Create a `hooks/hooks.json` with a hook using `ConfigChange`, `WorktreeCreate`, or `WorktreeRemove` as the `event` value
2. Run `/ll:audit-claude-config`
3. Observe: the audit flags the event type as invalid (not in the recognized set)
4. Expected: the event type is accepted as valid

## Actual Behavior

Running `/ll:audit-claude-config` with a `hooks.json` containing `ConfigChange`, `WorktreeCreate`, or `WorktreeRemove` events produces a false positive error: the audit reports the event type as unrecognized, flagging a valid hook configuration as an error that must be fixed.

## Root Cause

- **File**: `agents/plugin-config-auditor.md`
- **Anchor**: Hook event type validation section (hardcoded enum list)
- **Cause**: The event type enum was defined when Claude Code supported 14 hook event types. Three new types (`ConfigChange`, `WorktreeCreate`, `WorktreeRemove`) were added to Claude Code without a corresponding update to the auditor's validation list. Event-specific handler type restrictions were also never specified in the original implementation.

## Integration Map

### Files to Modify
- `agents/plugin-config-auditor.md` — Update the event type enum from 14 to 17; add per-event handler type validation rules; add `once`/`async` field validation

### Dependent Files
- `skills/audit-claude-config/SKILL.md` — References "14 official types" in comments; update to 17

## Implementation Steps

1. Update the 14-type enum in `agents/plugin-config-auditor.md` to include `ConfigChange`, `WorktreeCreate`, `WorktreeRemove`
2. Add a handler-type-per-event validation table (which events support which handler types)
3. Add validation for `once` field (only valid in skill-scoped hooks)
4. Add validation for `async` field (only valid for `command` type handlers)
5. Update any references to "14 types" in SKILL.md comments

## Impact

- **Priority**: P2 — This is a correctness bug; valid hooks are flagged as errors
- **Effort**: Low — Prompt text updates only, no structural changes
- **Risk**: Low — Additive validation; existing checks unchanged
- **Breaking Change**: No

## Labels

`bug`, `captured`, `agents`, `audit-claude-config`

## Resolution

**Fixed** in `agents/plugin-config-auditor.md` and `skills/audit-claude-config/SKILL.md`:

1. Updated recognized event type enum from 14 to 17 — added `ConfigChange`, `WorktreeCreate`, `WorktreeRemove`
2. Added per-event handler type validation: 8 events support all 3 types (command/prompt/agent); 9 are command-only
3. Added `once` field validation: only valid in skill/agent frontmatter hooks
4. Added `async` field validation: only valid for `command` type handlers
5. Updated audit checklist with explicit command-only event list and new field checks
6. Updated SKILL.md comment from "14 official types" to "17 official types"

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`
- `/ll:manage-issue bug fix BUG-463` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/`

---

## Status

**Closed** | Created: 2026-02-22 | Resolved: 2026-02-22 | Priority: P2

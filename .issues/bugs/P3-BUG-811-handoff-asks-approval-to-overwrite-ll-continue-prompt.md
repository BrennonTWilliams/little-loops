---
id: BUG-811
type: BUG
priority: P3
status: Closed - Already Fixed
discovered_date: 2026-03-18
discovered_by: capture-issue
---

# BUG-811: handoff asks for approval to overwrite ll-continue-prompt.md

## Summary

`/ll:handoff` prompts the user for approval before overwriting `.claude/ll-continue-prompt.md`. Since this file is always meant to be overwritten on every handoff, the approval prompt is unnecessary friction — it should always overwrite without asking.

## Current Behavior

When `/ll:handoff` writes the continuation prompt to `.claude/ll-continue-prompt.md`, Claude Code's `Write` tool triggers a user approval prompt (since the file already exists from a previous handoff). The user must approve the overwrite before the handoff completes.

## Expected Behavior

`/ll:handoff` should always overwrite `.claude/ll-continue-prompt.md` without asking for user approval. The file is a session continuation artifact that is always safe to overwrite.

## Steps to Reproduce

1. Run `/ll:handoff` once so that `.claude/ll-continue-prompt.md` exists.
2. Run `/ll:handoff` again.
3. Observe: Claude Code prompts for approval to overwrite the existing file.

## Motivation

The approval prompt interrupts the handoff flow for no benefit. The file is a well-known output artifact of `/ll:handoff` and overwriting it is always intentional. Users should not need to approve this every session.

## Proposed Solution

Add `Write(.claude/ll-continue-prompt.md)` to the canonical allow list that `/ll:init` (Step 10) and `/ll:configure allowed-tools` append to the target settings file. It should sit alongside the existing `Bash(ll-*)` entries:

```json
"Bash(ll-issues:*)",
"Bash(ll-auto:*)",
...
"Bash(ll-check-links:*)",
"Write(.claude/ll-continue-prompt.md)"
```

This ensures any project that runs `/ll:init` or re-runs `/ll:configure allowed-tools` gets the permission pre-authorized, eliminating the approval prompt on every subsequent handoff.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — add `Write(.claude/ll-continue-prompt.md)` to the canonical allow list in Step 10
- `skills/configure/SKILL.md` — same canonical list referenced in the `allowed-tools` section

### Dependent Files (Callers/Importers)
- `.claude/settings.json` / `.claude/settings.local.json` in target projects — populated by init/configure

### Similar Patterns
- All other `Bash(ll-*:*)` entries in the canonical allow list follow the same pattern

### Tests
- N/A — skill instruction update, not unit-testable

### Documentation
- N/A

### Configuration
- N/A — the fix is in the skill instructions that generate settings entries

## Implementation Steps

1. Add `"Write(.claude/ll-continue-prompt.md)"` to the canonical allow list in `skills/init/SKILL.md` (Step 10)
2. Add the same entry to the canonical allow list in `skills/configure/SKILL.md` (`allowed-tools` section)
3. Verify: run `/ll:init` or `/ll:configure allowed-tools` and confirm the entry appears in the target settings file
4. Verify: run `/ll:handoff` twice and confirm no approval prompt on second run

## Impact

- **Priority**: P3 - Minor UX friction but affects every handoff session
- **Effort**: Small - one-line settings change or minor command update
- **Risk**: Low - isolated change to command behavior or settings
- **Breaking Change**: No

## Related Key Documentation

_No documents linked. Run `/ll:normalize-issues` to discover and link relevant docs._

## Labels

`bug`, `captured`, `ux`, `handoff`

## Session Log
- `/ll:ready-issue` - 2026-03-19T04:32:33 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/7bb6a792-a2fe-4d51-b678-f9c1a1745893.jsonl`
- `/ll:refine-issue` - 2026-03-19T04:31:35 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4dd7eb52-05b2-4dee-89fa-f20e6fb0fa81.jsonl`

- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0769f82c-7917-4279-b938-66dfdf42d867.jsonl`

---

**Open** | Created: 2026-03-18 | Priority: P3

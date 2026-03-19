---
id: BUG-811
type: BUG
priority: P3
status: open
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

Add `.claude/ll-continue-prompt.md` to the project's `settings.json` write permissions so Claude Code does not prompt for approval when the file already exists. Alternatively, update `commands/handoff.md` to instruct Claude to use `Bash` with a heredoc redirect instead of the `Write` tool, bypassing the approval prompt.

A cleaner long-term solution is to add a `write_file_no_confirm` pattern in settings that covers this path.

## Integration Map

### Files to Modify
- `commands/handoff.md` — update write instruction to avoid triggering approval prompt

### Dependent Files (Callers/Importers)
- `.claude/settings.json` or `.claude/settings.local.json` — may need permission entry for `.claude/ll-continue-prompt.md`

### Similar Patterns
- Other commands that write well-known output files (e.g., plan files) may have the same issue

### Tests
- N/A — command behavior, not unit-testable

### Documentation
- N/A

### Configuration
- `.claude/settings.json` — potential write permissions entry

## Implementation Steps

1. Decide approach: settings permission vs. Bash heredoc in command
2. If settings: add `ll-continue-prompt.md` write permission to `.claude/settings.json`
3. If command: update `commands/handoff.md` to use `Bash` redirect instead of `Write` tool
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

- `/ll:capture-issue` - 2026-03-18T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/0769f82c-7917-4279-b938-66dfdf42d867.jsonl`

---

**Open** | Created: 2026-03-18 | Priority: P3

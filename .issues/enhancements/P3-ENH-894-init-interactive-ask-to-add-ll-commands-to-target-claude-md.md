---
type: ENH
id: ENH-894
title: Ask to add ll- CLI commands to target project CLAUDE.md during init --interactive
priority: P3
status: open
created: 2026-03-26
discovered_by: capture-issue
---

# ENH-894: Ask to add ll- CLI commands to target project CLAUDE.md during init --interactive

## Summary

When `/ll:init --interactive` asks whether to register ll- CLI commands in `.claude/settings.json` or `.claude/settings.local.json`, it should also ask if those commands should be documented in the target project's `CLAUDE.md` file (creating the file if none exists).

## Current Behavior

The init wizard asks whether to add ll- CLI commands to `.claude/settings.json` or `.claude/settings.local.json` (the permissions/allowed-tools configuration). It does not ask about updating or creating the target project's `CLAUDE.md` to document the available ll- CLI commands.

## Expected Behavior

After asking about settings file registration, the init wizard includes an additional prompt:

> "Would you also like to add ll- CLI command documentation to your project's `CLAUDE.md`? (Creates the file if it doesn't exist)"

If the user answers yes:
1. Check if `.claude/CLAUDE.md` (or `CLAUDE.md`) exists in the target project
2. If it exists, append an `## little-loops` section with the CLI commands list
3. If it does not exist, create it with a minimal structure including the CLI commands section

## Motivation

Developers who install little-loops via init and configure the settings permissions still need to discover the available `ll-` CLI commands. Adding this to `CLAUDE.md` gives all contributors (and future Claude Code sessions in that project) immediate visibility into the available commands, without requiring them to remember to run `/ll:help` or read the README.

## Proposed Solution

In `skills/init/SKILL.md`, add a new step after the current settings.json/settings.local.json question:

1. Display the question about adding ll- commands to `CLAUDE.md`
2. If yes, detect whether `.claude/CLAUDE.md` exists in the target project
3. If it exists, append a `## little-loops Commands` (or similar heading) section with the standard ll- CLI commands list
4. If it does not exist, create `.claude/CLAUDE.md` with a header block and the commands section

The section to append/create should include the core CLI commands (ll-auto, ll-parallel, ll-sprint, ll-loop, ll-issues, etc.) with brief one-line descriptions, mirroring what's in the little-loops README or CLAUDE.md.

## Integration Map

### Files to Modify
- `skills/init/SKILL.md` — Add a new interactive step after the settings.json question; implement file detection, append, or create logic

### Similar Patterns
- Existing Step 9 gitignore additions follow a similar "conditionally write to a file" pattern
- The settings.json step is the direct predecessor to this new step

### Tests
- Manual: run `/ll:init --interactive` in a temp project directory with and without an existing `CLAUDE.md`; verify the appended/created section is correct

### Documentation
- No additional docs needed — this step is self-documenting through the wizard

### Configuration
- Could optionally be controlled by a config flag (e.g., `init.add_claude_md_commands: true`) but not required for initial implementation

## Implementation Steps

1. Locate the settings.json question step in `skills/init/SKILL.md`
2. Add a follow-up question: "Add ll- command documentation to CLAUDE.md?" (yes/no)
3. On yes: check for `.claude/CLAUDE.md` existence in the target project root
4. If exists: append a `## little-loops Commands` section with CLI command list
5. If not exists: create `.claude/CLAUDE.md` with a minimal template + commands section
6. Stage any created/modified `CLAUDE.md` file via `git add`

## Impact

- **Priority**: P3 — Improves discoverability for new project adopters
- **Effort**: Small-Medium — One new wizard step + file create/append logic
- **Risk**: Low — Additive only; no existing behavior changed
- **Breaking Change**: No

## Related Key Documentation

| Document | Relevance |
|----------|-----------|
| `skills/init/SKILL.md` | Target file for the new init wizard step |
| `.claude/CLAUDE.md` | Example of the ll- commands documentation format to replicate |
| `README.md` | Documents the ll- CLI commands; source for section content |

## Labels

`enhancement`, `init`, `onboarding`, `claude-md`, `discoverability`

## Session Log
- `/ll:capture-issue` - 2026-03-26T19:38:22Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/fffc83c9-009a-4696-8010-040737bf7247.jsonl`

---

## Status

**Open** | Created: 2026-03-26 | Priority: P3

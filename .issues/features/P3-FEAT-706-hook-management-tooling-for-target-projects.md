---
discovered_date: 2026-03-12
discovered_by: capture-issue
---

# FEAT-706: Hook management tooling for target projects

## Summary

Little-loops has no tooling to read, evaluate, or install hooks in a target project's `.claude/settings.json`. Users who don't load little-loops as a Claude Code plugin have no supported path to configure hooks, and there's no way to inspect or repair hook configuration through little-loops tooling.

## Use Case

A developer installs little-loops, runs `/ll:init`, enables context monitoring and handoff, but is using little-loops via CLAUDE.md rather than as a registered plugin. Currently, there is no command to:
- Show what hooks are currently configured (plugin hooks vs. settings.json hooks)
- Install the relevant hook entries into the project's `.claude/settings.json`
- Validate whether configured hooks point to real scripts
- Diagnose why a hook-dependent feature isn't working

## Acceptance Criteria

- [ ] A command or skill can display current hook configuration (both plugin-level and target `.claude/settings.json`)
- [ ] A command or skill can install little-loops hook entries into a target project's `.claude/settings.json`
- [ ] Installed hooks correctly reference plugin scripts via `${CLAUDE_PLUGIN_ROOT}`
- [ ] The tool validates that referenced script paths exist before installing
- [ ] Existing hooks in `.claude/settings.json` are preserved (additive, not destructive)
- [ ] A `--dry-run` flag shows what would be installed without making changes

## Proposed Solution

Add a `/ll:configure hooks` sub-command (or extend `/ll:configure`) with the following capabilities:

### `show` mode
- Display a table of all hooks: source (plugin vs. settings.json), event type, script path, enabled status
- Flag any hooks whose script paths don't resolve

### `install` mode
- Read `hooks/hooks.json` from the plugin
- Generate equivalent entries for `.claude/settings.json` with absolute or `${CLAUDE_PLUGIN_ROOT}`-relative paths
- Merge into existing `.claude/settings.json` without overwriting unrelated keys
- Report what was added

### `validate` mode
- Check each configured hook (both sources) for: script existence, executable bit, timeout reasonableness
- Report issues by severity

## Scope Boundaries

- **In scope**: Read/install/validate hooks in target project `.claude/settings.json`; display combined hook state
- **Out of scope**: Modifying the plugin's own `hooks/hooks.json`; hooks for non-little-loops tools

## Implementation Steps

1. Identify Claude Code's `.claude/settings.json` hook schema (structure for inline hook definitions)
2. Create `skills/configure/hooks.md` or extend `skills/configure/SKILL.md` with a `hooks` subcommand
3. Implement `show`: parse plugin `hooks/hooks.json` + target `.claude/settings.json`, display unified table
4. Implement `install`: generate settings.json hook entries from plugin hooks, merge safely
5. Implement `validate`: check script existence and executable bit for all configured hooks
6. Add `--dry-run` support for `install` mode
7. Surface from `/ll:configure` dispatcher

## Integration Map

### Files to Create/Modify
- `skills/configure/SKILL.md` — add `hooks` subcommand dispatch
- `skills/configure/hooks.md` — new file implementing hook management logic
- `hooks/hooks.json` — source of truth for plugin hook definitions (read-only from this tool)

### Related Issues
- ENH-705: Init should validate plugin loading and hook activation (complementary — ENH-705 warns, this FEAT fixes)

## Session Log
- `/ll:capture-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4922c4e9-2029-4f68-b0a3-04ae4dbcd620.jsonl`

---
discovered_date: 2026-03-12
discovered_by: capture-issue
confidence_score: 93
outcome_confidence: 78
---

# FEAT-706: Hook management tooling for target projects

## Summary

Little-loops has no tooling to read, evaluate, or install hooks in a target project's `.claude/settings.json`. Users who don't load little-loops as a Claude Code plugin have no supported path to configure hooks, and there's no way to inspect or repair hook configuration through little-loops tooling.

## Current Behavior

Little-loops has no tooling to read, evaluate, or install hooks in a target project's `.claude/settings.json`. Users who load little-loops via CLAUDE.md (rather than as a registered plugin) have no supported path to configure hooks. There is no way to inspect what hooks are active, diagnose why a hook-dependent feature isn't working, or validate that configured hooks point to real scripts.

## Expected Behavior

A `/ll:configure hooks` command (or sub-command) provides three modes:
- **show**: Display a unified table of all hooks (plugin-level and settings.json), their event types, script paths, and enabled status, flagging any broken paths
- **install**: Generate and merge hook entries into `.claude/settings.json` from the plugin's `hooks/hooks.json`, preserving existing unrelated keys
- **validate**: Check each configured hook for script existence, executable bit, and timeout reasonableness, reporting issues by severity

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

### Files to Modify
- `skills/configure/SKILL.md` — add `hooks` subcommand dispatch
- `skills/configure/hooks.md` — new file implementing hook management logic
- `hooks/hooks.json` — source of truth for plugin hook definitions (read-only from this tool)

### Dependent Files (Callers/Importers)
- `skills/configure/SKILL.md` — dispatcher that routes to sub-commands
- `hooks/hooks.json` — source of truth for plugin hook definitions (read-only)

### Similar Patterns
- Existing `/ll:configure` sub-command dispatch pattern

### Tests
- TBD — manual validation of show/install/validate modes against a test project

### Documentation
- `docs/ARCHITECTURE.md` — update if hook management becomes a new subsystem
- `/ll:help` output — new sub-command needs listing

### Configuration
- `.claude/settings.json` — target file for hook installation
- `hooks/hooks.json` — read-only source for hook definitions

### Related Issues
- ENH-705: Init should validate plugin loading and hook activation (complementary — ENH-705 warns, this FEAT fixes)

## Impact

- **Priority**: P3 - Quality-of-life improvement for non-plugin users; not blocking core functionality
- **Effort**: Medium - Requires new skill file with three modes, JSON merging logic, and path validation
- **Risk**: Low - Additive only; writes to `.claude/settings.json` are guarded by `--dry-run` and preserve existing keys
- **Breaking Change**: No

## Labels

`feature`, `hooks`, `tooling`, `configure`

---

## Verification Notes

- **Date**: 2026-03-13
- **Verdict**: VALID
- `hooks/hooks.json` exists and is the described source of truth. No `skills/configure/hooks.md` file exists. The `skills/configure/SKILL.md` has no `hooks` subcommand dispatch. Feature not yet implemented.

## Status

**Open** | Created: 2026-03-12 | Priority: P3

## Session Log
- `/ll:confidence-check` - 2026-03-14T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/337af39a-dc8b-48d6-9e2a-cd244f708584.jsonl`
- `/ll:verify-issues` - 2026-03-13T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4a26704e-7913-498d-addf-8cd6c2ce63ff.jsonl`
- `/ll:capture-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/4922c4e9-2029-4f68-b0a3-04ae4dbcd620.jsonl`
- `/ll:format-issue` - 2026-03-12T00:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/e5037113-2ca1-4048-ba39-278c6ef9c09c.jsonl`

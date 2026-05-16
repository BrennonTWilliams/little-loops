# P1-BUG-076: Duplicate Plugin Manifests with Missing Component Paths

## Summary

The plugin has two `plugin.json` files with conflicting content. The canonical location (`.claude-plugin/plugin.json`) is missing the component path registrations for commands, skills, and agents.

## Problem

Two manifest files exist:

| Location | Has Component Paths | Is Canonical |
|----------|---------------------|--------------|
| `plugin.json` (root) | Yes | No |
| `.claude-plugin/plugin.json` | No | Yes |

### Current State

**Root `plugin.json`** (non-canonical, won't be discovered):
```json
{
  "name": "ll",
  "version": "1.0.0",
  "commands": "./commands/",
  "skills": "./skills/",
  "agents": "./agents/",
  "hooks": "./hooks/hooks.json"
}
```

**`.claude-plugin/plugin.json`** (canonical, incomplete):
```json
{
  "name": "ll",
  "version": "1.0.0",
  "hooks": "./hooks/hooks.json"
  // MISSING: commands, skills, agents
}
```

## Impact

- Claude Code plugin discovery reads from `.claude-plugin/plugin.json`
- Component registrations in root `plugin.json` are not discovered
- Plugin may rely on auto-discovery fallback rather than explicit registration
- Confusing for contributors who see two conflicting manifests

## Root Cause

Likely historical - the plugin may have been created before the `.claude-plugin/` convention was established, and the migration was incomplete.

## Solution

1. Merge component paths into `.claude-plugin/plugin.json`
2. Delete root `plugin.json`
3. Ensure all metadata (version, description, keywords, etc.) is preserved

### Target State

**`.claude-plugin/plugin.json`** (consolidated):
```json
{
  "name": "ll",
  "version": "1.0.0",
  "description": "Development workflow toolkit for Claude Code with issue management, code quality commands, and automated processing",
  "author": {
    "name": "little-loops"
  },
  "license": "MIT",
  "homepage": "https://github.com/BrennonTWilliams/little-loops",
  "keywords": [
    "development",
    "workflow",
    "issue-management",
    "automation",
    "code-quality"
  ],
  "commands": "./commands/",
  "skills": "./skills/",
  "agents": "./agents/",
  "hooks": "./hooks/hooks.json"
}
```

## Acceptance Criteria

- [x] Root `plugin.json` is kept as the tracked source of truth
- [x] All component paths (commands, skills, agents, hooks) are registered in both manifests
- [x] All metadata preserved (version, description, author, license, etc.)
- [x] `.claude-plugin/plugin.json` (gitignored local copy) updated with correct `../` paths
- [ ] Plugin loads correctly after changes (requires manual verification)

## Files to Modify

- `.claude-plugin/plugin.json` - Add missing component paths
- `plugin.json` (root) - Delete

## Testing

1. After changes, start a new Claude Code session
2. Verify `/ll:help` lists all commands
3. Verify agents are available via Task tool
4. Verify skills are discoverable

## Discovered By

Plugin structure audit using `plugin-dev:plugin-structure` skill

---

## Resolution

- **Action**: fix
- **Completed**: 2026-01-16
- **Status**: Completed

### Changes Made
- `.claude-plugin/plugin.json`: Added `commands`, `skills`, `agents` paths with `../` prefix to reference repo root; fixed `hooks` path to use `../hooks/hooks.json`
- Root `plugin.json`: Kept as tracked source (unchanged - already had correct `./` paths)

### Implementation Notes
- Root `plugin.json` is the tracked source of truth that gets committed and distributed
- `.claude-plugin/` is gitignored (local installation artifact)
- `.claude-plugin/plugin.json` uses `../` paths because it's inside `.claude-plugin/` and needs to reference repo root
- Root `plugin.json` uses `./` paths since it's at repo root
- Both manifests now have all component paths registered

### Verification Results
- JSON: VALID (both files)
- Path resolution: All paths resolve correctly to existing directories
- Root plugin.json: KEPT (tracked source of truth)
- .claude-plugin/plugin.json: UPDATED (gitignored local copy)

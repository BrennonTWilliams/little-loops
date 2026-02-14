---
discovered_date: 2026-02-12
discovered_by: plugin-audit
---

# ENH-374: plugin.json declares commands/skills but omits agents and hooks

## Summary

`.claude-plugin/plugin.json` explicitly declares `commands` and `skills` paths, but omits `agents` and `hooks` — even though both directories exist at default locations and are auto-discovered. This creates an inconsistency: some components are explicitly declared while others rely on auto-discovery.

## Location

- **File**: `.claude-plugin/plugin.json`

## Current Behavior

```json
{
  "commands": ["./commands"],
  "skills": ["./skills"]
}
```

The `agents/` directory (8 agents) and `hooks/hooks.json` (6 hooks) are loaded via auto-discovery but not declared in the manifest.

## Expected Behavior

Either:
1. **Add the missing declarations** for consistency:
   ```json
   {
     "commands": ["./commands"],
     "skills": ["./skills"],
     "agents": ["./agents"],
     "hooks": "./hooks/hooks.json"
   }
   ```
2. **Remove all declarations** and rely entirely on auto-discovery (all components are at default locations)

Option 1 is recommended — explicit declarations make the manifest a single source of truth for the plugin's component inventory.

## Motivation

This enhancement would:
- Make the plugin manifest the single source of truth for the complete component inventory
- Business value: Contributors and tooling can inspect `plugin.json` to discover all plugin components without guessing about auto-discovery conventions
- Technical debt: Eliminates inconsistency where `commands` and `skills` are declared but `agents` and `hooks` rely on implicit auto-discovery

## Proposed Solution

Add explicit `agents` and `hooks` declarations to `.claude-plugin/plugin.json` (Option 1 from Expected Behavior). This makes the manifest a single source of truth without changing runtime behavior, since all components are at default locations and currently auto-discovered.

**Note**: This depends on the Claude Code plugin.json schema supporting `agents` and `hooks` keys — verify before implementing.

## Scope Boundaries

- **In scope**: Adding `agents` and `hooks` declarations to `plugin.json`
- **Out of scope**: Changing auto-discovery behavior, modifying agent/hook file locations, or restructuring the plugin directory layout
- **Out of scope**: Removing existing `commands`/`skills` declarations (Option 2 from Expected Behavior is not pursued)

## Implementation Steps

1. **Add agents declaration**: Add `"agents": ["./agents"]` to `.claude-plugin/plugin.json`
2. **Add hooks declaration**: Add `"hooks": "./hooks/hooks.json"` to `.claude-plugin/plugin.json`
3. **Verify schema compatibility**: Confirm the plugin.json schema supports `agents` and `hooks` keys
4. **Verify component discovery**: Ensure all 8 agents and 6 hooks are still discovered and functional after the change
5. **Test plugin loading**: Verify the plugin loads correctly with the updated manifest

## Integration Map

- **Files to Modify**: `.claude-plugin/plugin.json`
- **Dependent Files (Callers/Importers)**: Claude Code plugin loader, `hooks/hooks.json`, `agents/` directory
- **Similar Patterns**: ENH-366 (closed as duplicate of this issue)
- **Tests**: N/A — plugin.json metadata addition; verified by Claude Code plugin loading
- **Documentation**: N/A — plugin manifest metadata improvement
- **Configuration**: `.claude-plugin/plugin.json`

## Impact

- **Priority**: P4
- **Effort**: Trivial
- **Risk**: None — behavior is unchanged either way

## Labels

`enhancement`, `config`, `plugin-manifest`

## Blocked By

_None_

## Blocks

_None — ENH-366 closed (won't-fix, duplicate of this issue)._

## Session Log
- `/ll:format-issue --all --auto` - 2026-02-13
- `/ll:manage-issue enhancement improve ENH-374` - 2026-02-14

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: VALID
- `plugin.json` still only declares `commands` and `skills` (confirmed)
- `agents/` directory has 8 agents, `hooks/hooks.json` has 6 hooks — both undeclared
- **BUG-364 blocker resolved**: marketplace JSON version mismatch fixed — this issue is unblocked

---

## Resolution

- **Resolved**: 2026-02-14
- **Action**: Added explicit `agents` declaration to `.claude-plugin/plugin.json` with all 8 agent file paths
- **Partial scope**: Only `agents` was added. `hooks` was intentionally excluded — Claude Code v2.1+ auto-discovers `hooks/hooks.json` and adding it explicitly causes duplicate file errors. This is the correct approach per the plugin schema.
- **Files changed**: `.claude-plugin/plugin.json`
- **Tests**: 2834 passed, 4 skipped
- **Plan**: `thoughts/shared/plans/2026-02-14-ENH-374-management.md`

## Status

**Completed** | Created: 2026-02-12 | Resolved: 2026-02-14 | Priority: P4

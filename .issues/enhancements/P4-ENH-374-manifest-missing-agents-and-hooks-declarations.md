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

## Impact

- **Priority**: P4
- **Effort**: Trivial
- **Risk**: None — behavior is unchanged either way

## Labels

`enhancement`, `config`, `plugin-manifest`

## Blocked By

- BUG-364: marketplace JSON version mismatch (shared plugin.json)

## Blocks

- ENH-366: add agents directory to plugin.json (shared plugin.json)

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4

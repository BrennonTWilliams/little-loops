---
discovered_date: 2026-01-18
discovered_by: plugin_structure_audit
---

# ENH-088: Remove or Document Empty .mcp.json File

## Summary

The `.mcp.json` file at the plugin root contains only an empty `mcpServers` object, serving no functional purpose.

## Current State

`.mcp.json` contents:
```json
{
  "mcpServers": {}
}
```

## Options

### Option A: Remove the File

If no MCP servers are planned, delete the file entirely:
```bash
git rm .mcp.json
```

### Option B: Document as Placeholder

If the file is intentionally kept as a placeholder for future MCP integrations, add a comment or update documentation explaining its purpose.

Note: JSON doesn't support comments, so documentation would need to be:
1. In a README or CONTRIBUTING.md section
2. As a descriptive key in the JSON itself:
   ```json
   {
     "_comment": "Placeholder for future MCP server integrations",
     "mcpServers": {}
   }
   ```

## Recommendation

Remove the file (Option A) unless there's a specific reason to keep it. It can be added back when MCP servers are actually configured.

## Impact

- Minor cleanup
- Reduces confusion about plugin configuration
- No functional impact since the object is empty

## References

- Plugin structure specification recommends only including `.mcp.json` when MCP servers are defined
- `plugin.json` does not reference this file

## Discovered By

Plugin structure audit using `plugin-dev:plugin-structure` skill

---

## Verification Notes

**Verified: 2026-01-28 - INVALID**

The `.mcp.json` file is required by the Claude Code plugin specification. Even when empty (containing only `"mcpServers": {}`), it serves an important purpose:

1. **Signals MCP capability** - The presence of `.mcp.json` tells Claude Code that this plugin supports MCP server configuration
2. **Plugin structure requirement** - The plugin specification expects this file to exist for MCP-enabled plugins
3. **Future-proofing** - Provides the structure for when MCP servers are actually configured

While the file currently contains no configured servers, removing it would break the plugin's MCP capability declaration. The "placeholder" argument is valid - this file signals intent to support MCP integrations.

**Verdict**: This issue describes a non-problem. The empty `.mcp.json` file is correct and necessary per the Claude Code plugin specification.

---

## Status

**Invalid** | Created: 2026-01-18 | Verified: 2026-01-28 | Priority: P4

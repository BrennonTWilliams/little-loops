---
discovered_date: 2026-02-12
discovered_by: plugin-audit
---

# ENH-366: Remove empty .mcp.json placeholder file

## Summary

The root `.mcp.json` file contains only `{"mcpServers": {}}` — an empty MCP server configuration. This file is unnecessary and adds clutter since no MCP servers are configured.

## Location

- **File**: `.mcp.json`

## Current Behavior

An empty MCP config file exists at the plugin root. The plugin loads it and registers zero MCP servers.

## Expected Behavior

Remove `.mcp.json` entirely. If MCP servers are needed in the future, the file can be recreated. Per the plugins reference, MCP configuration is auto-discovered at the default `.mcp.json` location, so no manifest changes are needed.

## Impact

- **Priority**: P5
- **Effort**: Trivial
- **Risk**: None

## Labels

`enhancement`, `cleanup`, `plugin-manifest`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P5

---
discovered_date: 2026-02-12
discovered_by: plugin-audit
---

# ENH-375: Remove empty .mcp.json placeholder file

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

---

## Verification Notes

- **Verified**: 2026-02-12
- **Verdict**: NEEDS_UPDATE
- File exists with `{"mcpServers": {}}` as claimed
- **However**: `.mcp.json` is already listed in `.gitignore` (line 55). The file is not tracked by version control.
- Impact is lower than described — only affects developers who have the file locally
- Claude Code still reads the file from the filesystem regardless of git tracking, so the "loads and registers zero MCP servers" claim is plausible
- Issue should acknowledge the gitignored status and clarify whether the file was ever committed or is purely a local artifact

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: 2026-02-12
- **Reason**: Low utility relative to implementation complexity

### Tradeoff Review Scores
- Utility: LOW
- Implementation Effort: LOW
- Complexity Added: LOW
- Technical Debt Risk: LOW
- Maintenance Overhead: LOW

### Rationale
File is already gitignored per verification notes, making this a local-only cleanup with minimal impact. Not worth tracking as an issue.

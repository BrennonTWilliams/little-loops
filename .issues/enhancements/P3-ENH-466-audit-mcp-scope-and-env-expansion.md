---
discovered_date: 2026-02-22
discovered_by: conversation-analysis
---

# ENH-466: Audit MCP configs across all scopes with env variable expansion validation

## Summary

The audit validates `.mcp.json` (project-scope) but does not cover user-scope MCP configs in `~/.claude.json`, local-scope MCP configs (also in `~/.claude.json` under project paths), or managed MCP (`managed-mcp.json`). It also does not validate environment variable expansion syntax (`${VAR}`, `${VAR:-default}`) used in `.mcp.json` fields, or the MCP approval control settings (`enableAllProjectMcpServers`, `enabledMcpjsonServers`, `disabledMcpjsonServers`, `allowedMcpServers`, `deniedMcpServers`).

## Current Behavior

Wave 1 Task 3 validates `.mcp.json` at project root:
- Server commands exist and are executable
- No duplicate server names
- Environment variables not hardcoded (secrets check)
- Scope appropriateness (global vs project)

Not covered:
1. **`~/.claude.json` MCP entries** — user-scope (`mcpServers` field) and local-scope (under project path keys) MCP server configs
2. **`managed-mcp.json`** — enterprise-managed MCP servers at system directories
3. **Environment variable expansion** — `${VAR}` and `${VAR:-default}` syntax in `command`, `args`, `env`, `url`, `headers` fields; no validation that referenced env vars are defined
4. **HTTP/SSE transport** — `.mcp.json` supports `type: "http"` and `type: "sse"` with `url` and `headers` fields, not just `type: "stdio"` with `command`/`args`
5. **MCP approval settings** — `enableAllProjectMcpServers`, `enabledMcpjsonServers`, `disabledMcpjsonServers` (in settings) control which project MCP servers are auto-approved; `allowedMcpServers`, `deniedMcpServers` (managed-only) control enterprise policy
6. **Agent-scoped MCP** — agents can define `mcpServers` in their frontmatter; these are not cross-referenced
7. **Plugin-scoped MCP** — plugins can provide `.mcp.json` or inline `mcpServers` in `plugin.json`

## Expected Behavior

1. Discover and validate MCP configs across all scopes (project, user, local, managed, agent, plugin)
2. Validate `${VAR}` references — warn if env var is not currently set (informational) or has malformed syntax
3. Validate all transport types (`stdio`, `http`, `sse`) with type-appropriate field checks
4. Cross-reference MCP approval settings against discovered servers
5. Detect conflicts: same server name at multiple scopes, managed deny overriding project config
6. Agent `mcpServers` entries validated for structure

## Motivation

MCP configuration errors are among the most confusing runtime failures in Claude Code: servers silently fail to start when env vars are unexpectedly unset, HTTP/SSE transports are misconfigured, or a managed-policy deny overrides a project-level allow without warning. The current audit only checks `.mcp.json` at project scope, missing user-scope, local-scope, and managed MCP configs entirely. Expanding MCP coverage ensures that the most common causes of "server not available" errors are caught by the audit before they surface as cryptic runtime failures.

## Proposed Solution

Extend the Wave 1 MCP config auditor to discover configs across all scopes: user-scope and local-scope entries in `~/.claude.json`, and `managed-mcp.json` at system directories. Add `${VAR}` / `${VAR:-default}` expansion syntax validation (warn if referenced env var is not currently set). Add HTTP/SSE transport validation for `url` format and `headers` structure. Add MCP approval settings cross-referencing (`enableAllProjectMcpServers`, `enabledMcpjsonServers`, `disabledMcpjsonServers`). Add scope conflict detection for server names defined at multiple scopes, and validate agent-scoped `mcpServers` frontmatter fields. Update `report-template.md` with a MCP scope breakdown section.

## Integration Map

### Files to Modify
- `skills/audit-claude-config/SKILL.md` — Extend Wave 1 Task 3 MCP scope; add env var expansion validation
- `skills/audit-claude-config/report-template.md` — Add MCP scope breakdown section
- `agents/plugin-config-auditor.md` — Add agent `mcpServers` field validation (see also ENH-464)
- `agents/consistency-checker.md` — Add cross-references: MCP approval settings → server names; agent mcpServers → valid structure

## Implementation Steps

1. Add `~/.claude.json` MCP config discovery (user-scope and local-scope)
2. Add `managed-mcp.json` detection at system directories
3. Add `${VAR}` / `${VAR:-default}` syntax validation in MCP config fields
4. Add HTTP/SSE transport validation (url format, headers structure)
5. Add MCP approval settings cross-referencing
6. Add scope conflict detection (same server name across scopes)
7. Update report template with MCP scope breakdown

## Impact

- **Priority**: P3 — MCP misconfigurations cause confusing runtime errors but are less common than settings issues
- **Effort**: Medium — Multiple file locations to discover; env var expansion parsing
- **Risk**: Low — Additive audit
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Discovering MCP configs across all scopes (project, user, local, managed, agent, plugin); validating env var expansion syntax; validating HTTP/SSE transport types; cross-referencing approval settings; detecting scope conflicts
- **Out of scope**: Validating MCP server functionality (connecting to servers), validating MCP tool schemas, suggesting MCP server configurations

## Labels

`enhancement`, `captured`, `skills`, `audit-claude-config`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`

## Blocked By

- ENH-464
- ENH-465

---

## Status

**Open** | Created: 2026-02-22 | Priority: P3

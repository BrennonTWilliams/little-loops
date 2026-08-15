---
target: codex
date: '2026-08-15'
status: proven
assertions:
- claim: Codex MCP server definitions are TOML tables under [mcp_servers.<name>] carrying a command key
  result: pass
- claim: Codex MCP server tables support optional args, tool_timeout_sec, and enabled keys
  result: pass
- claim: Codex stores MCP server definitions in the single global ~/.codex/config.toml, not scoped per-project
  result: pass
- claim: Codex reads a standalone project-local .codex/*.toml file for MCP server definitions
  result: fail
- claim: .codex/agents/*.toml is a known project-local read path, contrasting with the absent MCP file precedent
  result: pass
raw_output_path: .ll/learning-tests/raw/codex.txt
---

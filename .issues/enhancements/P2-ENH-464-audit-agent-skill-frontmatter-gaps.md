---
discovered_date: 2026-02-22
discovered_by: conversation-analysis
---

# ENH-464: Audit missing agent and skill frontmatter field validation

## Summary

The `plugin-config-auditor` agent validates agent files for description quality, examples, tool lists, and model selection, but does not validate several frontmatter fields that Claude Code supports. Similarly, skill frontmatter validation is missing several fields. Users with misconfigured frontmatter get no feedback from the audit.

## Current Behavior

### Agent fields NOT validated:
- `background` (boolean) — whether agent always runs as background task
- `isolation` (`worktree`) — whether agent runs in isolated git worktree
- `memory` (`user`, `project`, `local`) — persistent memory configuration; the corresponding directories (`.claude/agent-memory/`, `.claude/agent-memory-local/`, `~/.claude/agent-memory/`) are not checked
- `mcpServers` — inline MCP server definitions scoped to the agent
- `skills` — skills to preload into the agent (full content injected at startup)
- `permissionMode` — (`default`, `acceptEdits`, `dontAsk`, `bypassPermissions`, `plan`)
- `maxTurns` — maximum agentic turns
- `disallowedTools` — tool denylist (complement of existing `tools` check)

### Skill fields NOT validated:
- `once` — run only once per session
- `context` (`fork`) — run in isolated subagent
- `agent` — which subagent type to use with `context: fork`
- `hooks` — lifecycle hooks scoped to skill lifetime
- `!`command`` dynamic context injection syntax — not checked for validity
- `${CLAUDE_SESSION_ID}` substitution — not listed in known substitutions

## Expected Behavior

The plugin-config-auditor should validate:

**For agents:**
1. `background` is boolean if present
2. `isolation` is `worktree` or absent
3. `memory` is one of `user`, `project`, `local` if present; warn if memory directory doesn't exist yet (informational, not error)
4. `mcpServers` entries have valid structure (command exists, etc.)
5. `skills` references resolve to existing skill directories
6. `permissionMode` is one of the 5 valid values
7. `maxTurns` is a positive integer if present
8. `disallowedTools` entries don't overlap with `tools` entries

**For skills:**
1. `once` is boolean if present
2. `context: fork` has a corresponding `agent` field (or uses default)
3. `agent` value resolves to an existing agent definition
4. `hooks` entries follow hook validation rules (same as hooks.json validation)
5. `!`command`` syntax references executable commands

## Motivation

Agents and skills in this plugin use frontmatter fields (`background`, `isolation`, `memory`, `once`, `context: fork`) that the audit does not validate. A misconfigured `permissionMode`, an agent with `isolation: worktree` missing a matching memory-directory, or a skill with `context: fork` missing the required `agent` field will silently fail at runtime with no audit warning. Closing these validation gaps ensures that agent/skill misconfigurations are caught early rather than surfacing as confusing runtime failures.

## Proposed Solution

Extend the `plugin-config-auditor` agent prompt to validate the additional frontmatter fields for agents (`background`, `isolation`, `memory`, `mcpServers`, `skills`, `permissionMode`, `maxTurns`, `disallowedTools`) and for skills (`once`, `context`, `agent`, `hooks`). Add corresponding Wave 2 cross-reference checks to `consistency-checker` for new reference types: agent `skills` field → skill directories exist, skill `agent` field → agent file exists, agent `mcpServers` → valid server structure.

## Integration Map

### Files to Modify
- `agents/plugin-config-auditor.md` — Extend per-agent and per-skill validation sections with new field checks

### Dependent Files
- `agents/consistency-checker.md` — Wave 2 should cross-reference: agent `skills` → skill dirs exist; agent `mcpServers` → valid config; skill `agent` → agent file exists

## Implementation Steps

1. Add agent frontmatter field validation rules to plugin-config-auditor
2. Add skill frontmatter field validation rules
3. Add cross-reference checks to consistency-checker for new fields (skills → dirs, agent → files)
4. Test with agents that use `memory`, `isolation`, and `background` fields

## Impact

- **Priority**: P2 — Missing validation means misconfigured agents/skills fail silently at runtime
- **Effort**: Low-Medium — Prompt additions to existing agent; some new cross-references
- **Risk**: Low — Additive validation
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding validation for the listed agent and skill frontmatter fields in plugin-config-auditor; adding Wave 2 cross-references for `skills` → dirs and `agent` → files
- **Out of scope**: Validating hook content within skill `hooks` fields (deferred to BUG-463 fixes), modifying agent/skill behavior, adding new frontmatter fields to the spec

## Labels

`enhancement`, `captured`, `agents`, `audit-claude-config`

## Session Log
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/38aa90ae-336c-46b5-839d-82b4dc01908c.jsonl`
- `/ll:format-issue` - 2026-02-22 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6952751c-b227-418e-a8d3-d419ea5b0bf6.jsonl`

## Blocks

- ENH-466

## Resolution

**Completed**: 2026-02-22

### Changes Made
- `agents/plugin-config-auditor.md` — Added 8 agent frontmatter field validation rules (background, isolation, memory, mcpServers, skills, permissionMode, maxTurns, disallowedTools) to Core Responsibilities and Audit Checklist; added 5 skill frontmatter field validation rules (once, context, agent, hooks) to Core Responsibilities and Audit Checklist; extended Discovered References section with 3 new Wave 2 handoff items
- `agents/consistency-checker.md` — Added 3 new cross-reference checks to Cross-Reference Matrix (Agents → Skills, Skills → Agents, Agents → mcpServers); added collection steps to Step 1; added 3 output format table sections; added 3 summary rows; updated Core Responsibilities with new internal reference types

### Out of Scope (deferred)
- `!command` dynamic context injection syntax validation — not part of standard frontmatter field validation
- `${CLAUDE_SESSION_ID}` substitution validation — not part of standard frontmatter field validation
- Hook content validation within skill `hooks` fields — deferred per issue scope boundaries

---

## Status

**Completed** | Created: 2026-02-22 | Completed: 2026-02-22 | Priority: P2

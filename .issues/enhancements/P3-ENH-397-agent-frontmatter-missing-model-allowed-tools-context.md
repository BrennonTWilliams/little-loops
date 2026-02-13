---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-397: Agent frontmatter missing model, allowed-tools, and context fields

## Summary

All 8 agents in `agents/` have only `name` and `description` in their frontmatter. Per `docs/claude-code/custom-subagents.md`, agents should specify `model` (cost/capability tradeoff), `allowed-tools` (security scoping), and optionally `context` to control what conversation history the agent sees.

## Current Behavior

Every agent file has minimal frontmatter:
```yaml
---
name: codebase-analyzer
description: "..."
---
```

No `model`, `allowed-tools`, or `context` fields are specified, meaning all agents inherit the parent model and have access to all tools — including write tools (Edit, Write, Bash) that read-only agents should not need.

## Expected Behavior

Each agent should specify:
1. **`model`**: `haiku` for simple read-only search agents, `sonnet` for analysis agents requiring deeper reasoning
2. **`allowed-tools`**: Read-only agents should be restricted to `Read`, `Glob`, `Grep`, `WebFetch`, `WebSearch` — not `Edit`, `Write`, `Bash`, `NotebookEdit`
3. **`context`** (optional): Agents that don't need conversation history should set `context: none`

Example:
```yaml
---
name: codebase-locator
description: "..."
model: haiku
allowed-tools: ["Read", "Glob", "Grep", "WebFetch", "WebSearch"]
---
```

## Agents to Update

| Agent | Suggested model | Tool profile |
|-------|----------------|--------------|
| `codebase-analyzer` | sonnet | read-only |
| `codebase-locator` | haiku | read-only |
| `codebase-pattern-finder` | sonnet | read-only |
| `consistency-checker` | sonnet | read-only |
| `plugin-config-auditor` | sonnet | read-only |
| `prompt-optimizer` | sonnet | read-only + Write (outputs results) |
| `web-search-researcher` | sonnet | read-only + WebSearch + WebFetch |
| `workflow-pattern-analyzer` | sonnet | read-only + Write (outputs YAML) |

## Integration Map

### Files to Modify
- `agents/codebase-analyzer.md`
- `agents/codebase-locator.md`
- `agents/codebase-pattern-finder.md`
- `agents/consistency-checker.md`
- `agents/plugin-config-auditor.md`
- `agents/prompt-optimizer.md`
- `agents/web-search-researcher.md`
- `agents/workflow-pattern-analyzer.md`

### Tests
- Verify each agent still functions correctly after adding tool restrictions

## Implementation Steps

1. Review each agent's body to determine actual tool usage
2. Add `model` field based on complexity (haiku vs sonnet)
3. Add `allowed-tools` array restricting to only needed tools
4. Add `context` field where agents don't need conversation history
5. Test each agent still works with restricted tools

## Impact

- **Priority**: P3 - Security/scoping improvement for all agents
- **Effort**: Small - Frontmatter additions to 8 files
- **Risk**: Low - Additive changes, but tool restrictions could break agents if too narrow
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding frontmatter fields to existing agent files
- **Out of scope**: Rewriting agent body content or changing agent behavior

## Labels

`enhancement`, `agents`, `security`, `configuration`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3

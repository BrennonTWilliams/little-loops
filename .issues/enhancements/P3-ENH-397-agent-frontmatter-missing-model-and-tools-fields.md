---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-397: Agent frontmatter missing model and tools fields

## Summary

All 8 agents in `agents/` have only `name` and `description` in their frontmatter. Per `docs/claude-code/cli-reference.md` (lines 83-97), agents support `model` (cost/capability tradeoff), `tools` (restrict available tools), and `disallowedTools` (explicitly deny tools) fields in their YAML frontmatter.

## Current Behavior

Every agent file has minimal frontmatter:
```yaml
---
name: codebase-analyzer
description: "..."
---
```

No `model` or `tools` fields are specified, meaning all agents inherit the parent model and have access to all tools — including write tools (Edit, Write, Bash) that read-only agents should not need.

## Expected Behavior

Each agent should specify:
1. **`model`**: `sonnet` for analysis agents requiring deeper reasoning, `inherit` (default) where the parent model is appropriate
2. **`tools`**: Read-only agents should be restricted to `["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` — excluding `Edit`, `Write`, `Bash`, `NotebookEdit`

Example:
```yaml
---
name: codebase-locator
description: "..."
model: inherit
tools: ["Read", "Glob", "Grep", "WebFetch", "WebSearch"]
---
```

## Motivation

This enhancement would:
- Improve security scoping by restricting each agent to only the tools it needs
- Business value: Cost optimization by selecting appropriate models per agent instead of always inheriting the parent model
- Technical debt: Aligns agent frontmatter with documented fields in `docs/claude-code/cli-reference.md` (lines 83-97)

## Agents to Update

| Agent | Suggested model | `tools` array |
|-------|----------------|---------------|
| `codebase-analyzer` | sonnet | `["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` |
| `codebase-locator` | inherit | `["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` |
| `codebase-pattern-finder` | sonnet | `["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` |
| `consistency-checker` | sonnet | `["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` |
| `plugin-config-auditor` | sonnet | `["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` |
| `prompt-optimizer` | sonnet | `["Read", "Glob", "Grep", "WebFetch", "WebSearch", "Write"]` |
| `web-search-researcher` | sonnet | `["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` |
| `workflow-pattern-analyzer` | sonnet | `["Read", "Glob", "Grep", "WebFetch", "WebSearch", "Write"]` |

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
- N/A — agent markdown files are not Python-testable; verified via manual invocation of dependent skills/commands

### Documentation
- `.claude/CLAUDE.md` — update agent references if count/names change
- `docs/ARCHITECTURE.md` — update agent architecture section

## Verification Notes

**Task tool not needed by read-only agents** (verified 2026-02-13): Grep of all agent bodies confirms none of the 6 read-only agents (`codebase-analyzer`, `codebase-locator`, `codebase-pattern-finder`, `consistency-checker`, `plugin-config-auditor`, `web-search-researcher`) invoke or reference the `Task` tool. Matches for "Task", "subagent", and "spawn" in `consistency-checker` and `plugin-config-auditor` are string-level validation of `subagent_type` references using `Grep`/`Glob`/`Read` — not actual Task tool invocations. The proposed read-only tools array `["Read", "Glob", "Grep", "WebFetch", "WebSearch"]` is sufficient.

**Prior related issues**: ENH-355 (adding `model: default` cosmetically) was closed via tradeoff review as low-utility. This issue differs — it proposes intentional `model: sonnet` assignments and tool restrictions with actual behavioral impact.

## Implementation Steps

1. Review each agent's body to determine actual tool usage
2. Add `model` field based on complexity (sonnet vs inherit)
3. Add `tools` array restricting to only needed tools per the table above
4. Test each agent still works with restricted tools

## Impact

- **Priority**: P3 - Security/scoping improvement for all agents
- **Effort**: Small - Frontmatter additions to 8 files
- **Risk**: Low - Additive changes; read-only tool set verified sufficient for all 6 read-only agents
- **Breaking Change**: No

## Scope Boundaries

- **In scope**: Adding frontmatter fields to existing agent files
- **Out of scope**: Rewriting agent body content or changing agent behavior

## Labels

`enhancement`, `agents`, `security`, `configuration`

## Session Log
- /ll:format-issue --all --auto - 2026-02-13
- `/ll:manage-issue` - 2026-02-13T$(date -u +%H:%M:%SZ) - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d2b13850-f9ae-4a64-804e-64400913263a.jsonl`

---

## Resolution

- **Action**: improve
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- `agents/codebase-analyzer.md`: Added `model: sonnet` and read-only `tools` array
- `agents/codebase-locator.md`: Added `model: inherit` and read-only `tools` array
- `agents/codebase-pattern-finder.md`: Added `model: sonnet` and read-only `tools` array
- `agents/consistency-checker.md`: Added `model: sonnet` and read-only `tools` array
- `agents/plugin-config-auditor.md`: Added `model: sonnet` and read-only `tools` array
- `agents/prompt-optimizer.md`: Added `model: sonnet` and read-only+Write `tools` array
- `agents/web-search-researcher.md`: Added `model: sonnet` and read-only `tools` array
- `agents/workflow-pattern-analyzer.md`: Added `model: sonnet` and read-only+Write `tools` array

### Verification Results
- Tests: PASS (2733 passed)
- Lint: PASS
- Integration: PASS

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-13 | Priority: P3

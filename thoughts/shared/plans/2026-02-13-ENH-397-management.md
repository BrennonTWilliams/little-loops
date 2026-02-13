# ENH-397: Agent frontmatter missing model and tools fields - Implementation Plan

## Issue Reference
- **File**: `.issues/enhancements/P3-ENH-397-agent-frontmatter-missing-model-and-tools-fields.md`
- **Type**: enhancement
- **Priority**: P3
- **Action**: improve

## Current State Analysis

All 8 agents in `agents/` have only `name` and `description` in their frontmatter. Per `docs/claude-code/cli-reference.md`, agents support `model`, `tools`, and `disallowedTools` fields.

## Desired End State

Each agent has `model` and `tools` fields in frontmatter matching the table in the issue:
- 6 read-only agents: `tools: ["Read", "Glob", "Grep", "WebFetch", "WebSearch"]`
- 2 write agents (prompt-optimizer, workflow-pattern-analyzer): add `Write` to tools
- Model assignments: `sonnet` for analysis/reasoning agents, `inherit` for codebase-locator

## What We're NOT Doing

- Not changing agent body content
- Not adding `disallowedTools`, `skills`, `mcpServers`, or `maxTurns` fields
- Not changing agent behavior beyond tool/model restrictions

## Implementation Phases

### Phase 1: Update all 8 agent frontmatter files

Add `model` and `tools` fields to each agent's YAML frontmatter per the issue table.

#### Success Criteria
- [ ] All 8 agent files have `model` and `tools` fields
- [ ] Lint passes: `ruff check scripts/`
- [ ] YAML frontmatter is valid in all files

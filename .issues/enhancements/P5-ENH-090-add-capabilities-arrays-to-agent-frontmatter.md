# ENH-090: Add Capabilities Arrays to Agent Frontmatter

## Status

**Closed - Invalid** (2026-01-17)

The `capabilities` field is not a supported frontmatter field in Claude Code's agent specification. Official documentation lists supported fields as: `name`, `description`, `tools`, `disallowedTools`, `model`, `permissionMode`, `skills`, `hooks`. The `capabilities` field shown in plugin documentation examples is not processed by the Claude Code runtime and would be silently ignored.

## Summary

Agent `.md` files use a custom frontmatter format that differs from the documented plugin structure example. Adding `capabilities` arrays could improve agent discoverability and documentation.

## Current State

Example from `agents/codebase-analyzer.md`:
```yaml
---
name: codebase-analyzer
description: |
  Analyzes codebase implementation details...
allowed_tools:
  - Read
  - Grep
  - Glob
  - LS
model: sonnet
---
```

## Documented Example Format

From plugin structure specification:
```yaml
---
description: Agent role and expertise
capabilities:
  - Specific task 1
  - Specific task 2
---
```

## Proposed Enhancement

Add `capabilities` arrays to complement existing descriptions:

```yaml
---
name: codebase-analyzer
description: |
  Analyzes codebase implementation details...
capabilities:
  - Trace data flow through components
  - Identify architectural patterns
  - Document implementation with file:line references
  - Analyze function call chains
allowed_tools:
  - Read
  - Grep
  - Glob
  - LS
model: sonnet
---
```

## Affected Files

- `agents/codebase-analyzer.md`
- `agents/codebase-locator.md`
- `agents/codebase-pattern-finder.md`
- `agents/consistency-checker.md`
- `agents/plugin-config-auditor.md`
- `agents/prompt-optimizer.md`
- `agents/web-search-researcher.md`
- `agents/workflow-pattern-analyzer.md`

## Benefits

- Structured list of agent capabilities for tooling
- Improved discoverability
- Clearer documentation of what each agent can do
- Aligns with plugin structure specification

## Priority

Low priority - agents function correctly with current format. The `description` field already contains capability information in prose form. This would add structured metadata.

## Notes

- The current format with `name`, `description`, `allowed_tools`, `model`, and `color` works correctly
- This enhancement adds optional structured metadata
- Existing descriptions contain capability information but in unstructured prose

## References

- Plugin structure specification agent example
- Current agent files in `agents/` directory

## Discovered By

Plugin structure audit using `plugin-dev:plugin-structure` skill

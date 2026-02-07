---
discovered_date: 2026-02-07
discovered_by: capture_issue
---

# ENH-269: Unify feature flag checking across consumers

## Summary

The plugin has 8 `enabled` boolean flags scattered across `ll-config.json` sections (`context_monitor`, `documents`, `product`, `sync`, `continuation`, `prompt_optimization`, `workflow.phase_gates`, `workflow.deep_research`), each checked independently by its consumers using 3 different patterns. There is no centralized enforcement, validation, or consistent checking mechanism.

## Context

Identified from conversation analyzing the feature flagging system in `ll-config.json`. Analysis revealed:

- **Shell hooks** use `jq` to read flags directly from the JSON file
- **Command/skill markdown** uses `{{config.X.enabled}}` template interpolation with prose guard clauses
- **Conditional phases** rely on the LLM reading and obeying prose instructions (e.g., "skip if documents.enabled is not true")

No consumer validates that required sub-configuration exists when a feature is enabled (e.g., `sync.enabled: true` without `sync.github` being configured).

## Current Behavior

Each feature independently:
1. Defines its own `enabled` boolean in its config section
2. Each consumer reimplements the check using whichever pattern is convenient
3. No startup validation warns about misconfigured enabled features
4. No centralized view of flag state beyond `/ll:configure` display output

## Expected Behavior

A consistent pattern for feature flag checking that:
1. Provides a single source of truth for which features are enabled
2. Validates that required sub-configuration exists when a feature is enabled
3. Uses a consistent checking pattern across shell hooks, commands, and skills
4. Optionally warns at session start about misconfigured features

## Proposed Solution

Options to evaluate:

1. **Lightweight**: Add a shared shell function (`ll-feature-check.sh`) that hooks and scripts source, plus standardize the template interpolation pattern in commands/skills
2. **Validation layer**: Add a config validation step to `session-start.sh` that checks enabled features have required sub-config populated
3. **Full registry**: Create a formal feature flag registry with lifecycle management (likely over-engineered at current scale of 8 flags)

Recommendation: Start with options 1+2 — standardize the checking pattern and add startup validation. A full registry is premature at 8 flags.

## Impact

- **Priority**: P3
- **Effort**: Medium - touches hooks, potentially commands/skills documentation
- **Risk**: Low - additive changes, doesn't break existing behavior

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Plugin architecture and hook system design |
| guidelines | .claude/CLAUDE.md | Config file locations and project structure |

## Verification Notes

Verified 2026-02-07. Original issue stated 6 enabled flags; corrected to 8 after discovering `workflow.phase_gates.enabled` and `workflow.deep_research.enabled` in `config-schema.json`. All other claims verified accurate: shell hooks use `jq`, commands/skills use template interpolation, prose-based guard clauses exist, and no sub-configuration validation is performed.

## Labels

`enhancement`, `captured`

---

## Status

**Open** | Created: 2026-02-07 | Priority: P3

---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-366: Add agents directory declaration to plugin.json

## Summary

The `agents/` directory contains 8 agent definition files actively referenced by 5+ commands via `subagent_type`, but `.claude-plugin/plugin.json` only declares `commands` and `skills` directories. The `agents` directory is undeclared.

## Location

- **File**: `.claude-plugin/plugin.json`

## Current Behavior

```json
{
  "commands": ["./commands"],
  "skills": ["./skills"]
}
```

## Expected Behavior

```json
{
  "commands": ["./commands"],
  "skills": ["./skills"],
  "agents": ["./agents"]
}
```

Note: This depends on whether the plugin.json schema supports an `agents` key. If not, this is informational only.

## Motivation

This enhancement would:
- Ensure manifest completeness for plugin component discovery — all directories are explicitly declared
- Business value: The plugin manifest becomes a single source of truth for the component inventory, improving discoverability for contributors
- Technical debt: Eliminates inconsistency where some component directories are declared and others rely on auto-discovery

## Implementation Steps

1. **Verify plugin.json schema**: Confirm the Claude Code plugin schema supports an `"agents"` key in `plugin.json`
2. **Add agents entry**: Add `"agents": ["./agents"]` to `.claude-plugin/plugin.json`
3. **Verify agent discovery**: Confirm all 8 agents in `agents/` are still discovered and functional after the change
4. **Update documentation**: If any docs reference the plugin manifest structure, update them to reflect the new key

## Integration Map

- **Files to Modify**: `.claude-plugin/plugin.json`
- **Dependent Files (Callers/Importers)**: Commands referencing `subagent_type` (5+ commands)
- **Similar Patterns**: ENH-374 (manifest missing agents and hooks declarations)
- **Tests**: N/A — plugin.json metadata addition; verified by Claude Code plugin loading and agent discovery
- **Documentation**: N/A — plugin manifest metadata improvement
- **Configuration**: `.claude-plugin/plugin.json`

## Impact

- **Priority**: P5
- **Effort**: Trivial
- **Risk**: None

## Blocked By

- ENH-279: audit skill vs command allocation (shared plugin.json)
- ENH-374: manifest missing agents and hooks declarations (shared plugin.json)
- ENH-319: improve ll-analyze-workflows (shared plugin.json)

## Labels

`enhancement`, `config`, `agents`

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13

## Verification Notes

- **Verified**: 2026-02-13
- **Verdict**: NEEDS_UPDATE
- Core issue valid: `plugin.json` still only declares `commands` and `skills`
- 8 agents confirmed in `agents/` directory
- **BUG-364 blocker resolved**: marketplace version mismatch fixed — should be removed from Blocked By
- **Schema verification still needed**: Issue correctly notes this depends on whether plugin.json schema supports `agents` key — should verify before implementing

---

## Status

**Open** | Created: 2026-02-12 | Priority: P5

---

## Tradeoff Review Note

**Reviewed**: 2026-02-12 by `/ll:tradeoff_review_issues`

### Scores
| Dimension | Score |
|-----------|-------|
| Utility to project | LOW |
| Implementation effort | LOW |
| Complexity added | LOW |
| Technical debt risk | LOW |
| Maintenance overhead | LOW |

### Recommendation
Update first - The issue itself acknowledges uncertainty: "depends on whether the plugin.json schema supports an agents key." This should be verified against the actual Claude Code plugin schema before implementation. If the schema doesn't support it, the issue should be closed.

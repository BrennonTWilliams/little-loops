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

## Impact

- **Priority**: P5
- **Effort**: Trivial
- **Risk**: None

## Labels

`enhancement`, `config`, `agents`

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

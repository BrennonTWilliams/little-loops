---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# BUG-365: analyze-workflows command uses legacy TodoWrite tool name

## Summary

`commands/analyze-workflows.md` lists `TodoWrite` in its `allowed-tools` frontmatter (line 10). `TodoWrite` is the legacy tool name; the current Claude Code tools are `TaskCreate`, `TaskUpdate`, `TaskList`, and `TaskGet`.

## Location

- **File**: `commands/analyze-workflows.md:10`

## Current Behavior

```yaml
allowed-tools: [..., TodoWrite]
```

## Expected Behavior

```yaml
allowed-tools: [..., TaskCreate, TaskUpdate, TaskList]
```

## Impact

- **Priority**: P4
- **Effort**: Trivial
- **Risk**: Low - may have no runtime impact if allowed-tools is advisory

## Labels

`bug`, `commands`, `legacy`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P4

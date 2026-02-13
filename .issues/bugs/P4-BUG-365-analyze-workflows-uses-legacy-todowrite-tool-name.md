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

## Motivation

This bug would:
- Fix a legacy tool name reference that could cause tool blocking if `allowed-tools` is enforced
- Business value: Ensures commands stay current with Claude Code's evolving tool API
- Technical debt: Eliminates stale `TodoWrite` reference that diverges from current `TaskCreate`/`TaskUpdate`/`TaskList` naming

## Root Cause

- **File**: `commands/analyze-workflows.md:10`
- **Anchor**: `in allowed-tools frontmatter`
- **Cause**: The `allowed-tools` list was authored when the task tool was called `TodoWrite` and was never updated after the rename to `TaskCreate`/`TaskUpdate`/`TaskList`/`TaskGet`

## Implementation Steps

1. Open `commands/analyze-workflows.md`
2. Replace `TodoWrite` in the `allowed-tools` frontmatter with `TaskCreate, TaskUpdate, TaskList`
3. Verify no other references to `TodoWrite` remain in the file
4. Test that the command still executes correctly

## Integration Map

### Files to Modify
- `commands/analyze-workflows.md` — update `allowed-tools` frontmatter

### Dependent Files (Callers/Importers)
- N/A

### Similar Patterns
- Other commands may also reference `TodoWrite` (see BUG-363)

### Tests
- N/A — command markdown frontmatter change; verified by running /ll:analyze-workflows

### Documentation
- N/A — internal tool name fix

### Configuration
- N/A

## Impact

- **Priority**: P4
- **Effort**: Trivial
- **Risk**: Low - may have no runtime impact if allowed-tools is advisory

## Labels

`bug`, `commands`, `legacy`

---

## Session Log
- `/ll:format_issue --all --auto` - 2026-02-13

## Status

**Open** | Created: 2026-02-12 | Priority: P4

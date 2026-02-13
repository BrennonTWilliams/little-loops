---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-401: Add argument-hint to commands with arguments

## Summary

Per `docs/claude-code/skills.md`, `argument-hint` provides autocomplete hints in the `/` menu. Commands that accept `arguments` in their frontmatter should include `argument-hint` for better UX — showing users what input is expected before they invoke the command.

## Current Behavior

Commands define `arguments` but no `argument-hint`:
```yaml
---
description: "..."
arguments: "issue_file_path"
# no argument-hint
---
```

Users see the command in the `/` menu but get no visual hint about what argument is expected.

## Expected Behavior

Commands with arguments should include `argument-hint`:
```yaml
---
description: "..."
arguments: "issue_file_path"
argument-hint: "<issue-file>"
---
```

This shows in the `/` menu as: `/ll:manage_issue <issue-file>`

## Integration Map

### Files to Modify
- All command files in `commands/` that have `arguments:` in frontmatter

### Tests
- Visual verification that hints appear in `/` menu

## Implementation Steps

1. Grep all command files for `arguments:` in frontmatter
2. For each, add an appropriate `argument-hint` value:
   - Issue commands: `"<issue-file>"` or `"<issue-id>"`
   - Path commands: `"<path>"`
   - Sprint commands: `"<sprint-name>"`
   - PR commands: `"<pr-number>"`
3. Verify hints render correctly in Claude Code's `/` menu

## Impact

- **Priority**: P5 - UX polish, no functional change
- **Effort**: Trivial - Add one frontmatter line per command
- **Risk**: None
- **Breaking Change**: No

## Blocked By

- BUG-402: Commands reference $ARGUMENTS inconsistently — $ARGUMENTS placement must be resolved before adding argument-hints

## Labels

`enhancement`, `commands`, `ux`, `configuration`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P5

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

This shows in the `/` menu as: `/ll:manage-issue <issue-file>`

## Motivation

This enhancement would:
- Provide better UX with autocomplete hints visible in the `/` command menu
- Business value: Users immediately see what input a command expects without consulting documentation
- Technical debt: Aligns command frontmatter with all documented optional fields in the skills reference

## Integration Map

### Files to Modify
- All command files in `commands/` that have `arguments:` in frontmatter

### Tests
- N/A — command markdown frontmatter additions are not Python-testable; verified by checking hints appear in `/` menu

### Documentation
- N/A — UX polish, no user-facing documentation needed

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

## Scope Boundaries

- **In scope**: Adding `argument-hint` frontmatter to commands that have `arguments`
- **Out of scope**: Changing command argument parsing or adding new arguments to commands

## Blocked By

- ~~BUG-402~~: Completed — $ARGUMENTS placement resolved

## Labels

`enhancement`, `commands`, `ux`, `configuration`

## Resolution

- **Action**: improve
- **Completed**: 2026-02-13
- **Status**: Completed

### Changes Made
- 20 command files: Added `argument-hint` frontmatter field
- 7 skill files: Added `argument-hint` frontmatter field

### Verification Results
- Tests: N/A (markdown frontmatter only)
- Lint: N/A
- Types: N/A
- Integration: PASS (all 27 files with `arguments:` now have `argument-hint:`)

## Session Log
- /ll:format-issue --all --auto - 2026-02-13
- /ll:manage-issue - 2026-02-13

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-13 | Priority: P5

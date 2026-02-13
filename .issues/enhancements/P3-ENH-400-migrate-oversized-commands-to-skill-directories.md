---
discovered_date: 2026-02-12
discovered_by: audit_claude_config
---

# ENH-400: Migrate 8 oversized commands to skill directories with supporting files

## Summary

Per `docs/claude-code/skills.md`, files should be under 500 lines with reference content in supporting files. 8 commands far exceed this limit. The skill directory structure (`<name>/SKILL.md` + supporting files) recommended in `docs/claude-code/create-plugin.md` allows extracting templates, examples, and reference sections into separate files read via `Read` tool references.

## Current Behavior

8 commands exceed the 500-line recommendation:

| Command | Lines | Over by |
|---------|-------|---------|
| `create_loop.md` | 1,249 | +749 |
| `init.md` | 1,142 | +642 |
| `configure.md` | 1,044 | +544 |
| `manage_issue.md` | 740 | +240 |
| `format_issue.md` | 713 | +213 |
| `audit_claude_config.md` | 628 | +128 |
| `capture_issue.md` | 614 | +114 |
| `audit_docs.md` | 506 | +6 |

## Expected Behavior

Each oversized command should be converted to a skill directory under `skills/`:
```
skills/
  create-loop/
    SKILL.md          # Core logic, under 500 lines
    templates.md      # FSM templates and examples
    paradigms.md      # Paradigm reference
  init/
    SKILL.md          # Core wizard flow
    templates.md      # Config templates
    defaults.md       # Default configuration reference
```

The main `SKILL.md` references supporting files with `Read` instructions:
```markdown
For the issue template, read `skills/init/templates.md`
```

## Integration Map

### Files to Modify
- `commands/create_loop.md` -> `skills/create-loop/SKILL.md` + supporting files
- `commands/init.md` -> `skills/init/SKILL.md` + supporting files
- `commands/configure.md` -> `skills/configure/SKILL.md` + supporting files
- `commands/manage_issue.md` -> `skills/manage-issue/SKILL.md` + supporting files
- `commands/format_issue.md` -> `skills/format-issue/SKILL.md` + supporting files
- `commands/audit_claude_config.md` -> `skills/audit-claude-config/SKILL.md` + supporting files
- `commands/capture_issue.md` -> `skills/capture-issue/SKILL.md` + supporting files
- `commands/audit_docs.md` -> `skills/audit-docs/SKILL.md` + supporting files

### Dependent Files
- `.claude-plugin/plugin.json` — update commands/skills paths
- `CLAUDE.md` — update command/skill references

### Tests
- Verify each migrated skill still invokable via `/ll:*`

## Implementation Steps

1. For each oversized command, identify extractable sections (templates, examples, reference tables, configuration blocks)
2. Create skill directory with `SKILL.md` (core logic) + supporting files
3. Replace inline content in `SKILL.md` with `Read` references to supporting files
4. Remove old command file from `commands/`
5. Update plugin manifest paths
6. Verify each skill is invokable and functions correctly

## Impact

- **Priority**: P3 - Improves maintainability and follows best practices
- **Effort**: Large - 8 commands to migrate, each requiring content analysis and splitting
- **Risk**: Medium - Path changes could break invocations if not updated everywhere
- **Breaking Change**: No (skills invoked via `/ll:` prefix remain the same)

## Scope Boundaries

- **In scope**: Converting oversized commands to skill directories with supporting files
- **Out of scope**: Rewriting command logic or changing behavior; `audit_docs.md` at 506 lines is borderline and could be deferred

## Blocks

- BUG-402: Commands reference $ARGUMENTS inconsistently — command restructuring should complete before fixing argument references

## Related Issues

- ENH-279: Audit skill vs command allocation (broader skill/command allocation review)

## Labels

`enhancement`, `commands`, `skills`, `refactoring`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P3

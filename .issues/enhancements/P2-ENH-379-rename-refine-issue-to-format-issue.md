---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-379: Rename refine_issue to format_issue for honest naming

## Summary

The current `/ll:refine_issue` command primarily performs template v2.0 section alignment (renaming v1.0 sections to v2.0 names) and structural gap-filling with boilerplate content. Its name implies substantive refinement — researching the codebase, identifying knowledge gaps, gathering clarifying information — but its actual behavior is template format conversion. Rename it to `format_issue` (or `align_issue`) so the command name honestly reflects what it does.

## Current Behavior

`/ll:refine_issue` is named as if it performs deep issue refinement, but its center of gravity is:
- Step 2.5: Template v1.0 → v2.0 section header renaming
- Step 3: Structural gap identification (missing template sections, not missing knowledge)
- Step 3.6 (auto mode): Boilerplate inference from existing content (reformatting, not researching)
- No codebase research happens — the command never reads source code

The `--template-align-only` flag already exists, acknowledging that template alignment is the primary behavior.

## Expected Behavior

The command should be renamed to `format_issue` (or `align_issue`) with matching filename, skill registration, and documentation references. The `--template-align-only` flag may become unnecessary or could remain for a "header-rename-only" sub-mode. All references in CLAUDE.md, help output, pipeline documentation, and integration sections of other commands should be updated.

## Motivation

- **User trust**: Command names should honestly describe behavior. A misleadingly named command erodes confidence in the toolkit.
- **Pipeline clarity**: The issue pipeline (`capture → refine → ready → manage`) should have each step clearly named for what it does.
- **Namespace**: Renaming frees the `refine_issue` name for a new command (FEAT-380) that does actual substantive refinement.

## Proposed Solution

1. Rename `commands/refine_issue.md` → `commands/format_issue.md`
2. Update command registration in plugin manifest, CLAUDE.md, and help command
3. Update all cross-references in other commands (ready_issue, manage_issue, capture_issue, etc.)
4. Update pipeline documentation to show `capture → format → refine → ready → manage`
5. Update `issue-sections.json` `_meta.description` if it references `refine_issue`
6. Consider whether `--template-align-only` flag is still needed or if the base behavior is already "format only"

## Integration Map

### Files to Modify
- `commands/refine_issue.md` → rename to `commands/format_issue.md`
- `.claude/CLAUDE.md` — command list and pipeline references
- `commands/help.md` — if it lists commands explicitly
- `commands/ready_issue.md` — integration/next-steps references
- `commands/capture_issue.md` — integration/next-steps references
- `commands/manage_issue.md` — pipeline references
- `templates/issue-sections.json` — `_meta.description` reference

### Dependent Files (Callers/Importers)
- `scripts/little_loops/` — any Python code referencing `refine_issue` by name
- `.sprints/` — sprint definitions referencing `/ll:refine_issue`

### Similar Patterns
- N/A

### Tests
- TBD — check if any tests reference `refine_issue` by name

### Documentation
- `docs/ARCHITECTURE.md` — if it documents the issue pipeline
- `CONTRIBUTING.md` — if it references the refinement step

### Configuration
- `.claude-plugin/plugin.json` — command registration

## Implementation Steps

1. Rename the command file and update its internal content
2. Update all cross-references across commands and docs
3. Update plugin manifest registration
4. Verify no broken references remain

## Impact

- **Priority**: P2 - Misleading naming actively confuses the pipeline; blocks FEAT-380
- **Effort**: Small - File rename plus text find-and-replace across a known set of files
- **Risk**: Low - No logic changes, purely naming
- **Breaking Change**: Yes - Users of `/ll:refine_issue` will need to use `/ll:format_issue`

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Lists refine_issue in command table and pipeline |
| architecture | docs/ARCHITECTURE.md | Documents issue lifecycle pipeline |

## Labels

`enhancement`, `commands`, `naming`, `captured`

## Session Log
- `/ll:capture_issue` - 2026-02-12T12:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d65a885a-6b92-4b2e-be03-ca8f0f08c767.jsonl`

---

## Status

**Open** | Created: 2026-02-12 | Priority: P2

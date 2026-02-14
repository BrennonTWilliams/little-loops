---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-379: Rename refine_issue to format_issue for honest naming

## Summary

The current `/ll:refine-issue` command primarily performs template v2.0 section alignment (renaming v1.0 sections to v2.0 names) and structural gap-filling with boilerplate content. Its name implies substantive refinement — researching the codebase, identifying knowledge gaps, gathering clarifying information — but its actual behavior is template format conversion. Rename it to `format_issue` (or `align_issue`) so the command name honestly reflects what it does.

## Current Behavior

`/ll:refine-issue` is named as if it performs deep issue refinement, but its center of gravity is:
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
2. Update CLAUDE.md, help command, and README.md command table references
3. Update all cross-references in other commands (ready_issue, manage_issue, capture_issue, etc.)
4. Update pipeline documentation to show `capture → format → refine → ready → manage`
5. Update `issue-sections.json` `_meta.description` reference to `refine_issue`
6. Update `skills/issue-workflow/SKILL.md`, `docs/COMMANDS.md`, `docs/ISSUE_TEMPLATE.md`, `CONTRIBUTING.md`
7. Update `scripts/tests/test_session_log.py` references
8. Remove the `--template-align-only` flag — the base behavior of `format_issue` is already template alignment, making this flag redundant

## Integration Map

### Files to Modify
- `commands/refine_issue.md` → rename to `commands/format_issue.md`
- `.claude/CLAUDE.md` — command list and pipeline references (line 52)
- `commands/help.md` — lists `refine_issue` explicitly
- `commands/ready_issue.md` — integration/next-steps references
- `commands/capture_issue.md` — integration/next-steps references
- `commands/manage_issue.md` — pipeline references
- `templates/issue-sections.json` — `_meta.description` reference (line 4)
- `skills/issue-workflow/SKILL.md` — references `refine_issue` in workflow steps
- `README.md` — command table reference (line 110)

### Dependent Files (Callers/Importers)
- `scripts/tests/test_session_log.py` — references `/ll:refine-issue` in session log append tests (lines 86, 92, 112, 117)

### Similar Patterns
- N/A

### Tests
- `scripts/tests/test_session_log.py` — references `/ll:refine-issue` (lines 86, 92, 112, 117)

### Documentation
- `docs/COMMANDS.md` — references `refine_issue`
- `docs/ISSUE_TEMPLATE.md` — references `refine_issue`
- `CONTRIBUTING.md` — references the refinement step (line 298)
- `CHANGELOG.md` — historical references (leave unchanged, these are release history)

### Configuration
- N/A — commands are registered via `commands/` directory convention, not explicitly in `plugin.json`

## Implementation Steps

1. Rename the command file and update its internal content
2. Update all cross-references across commands and docs
3. Update plugin manifest registration
4. Verify no broken references remain

## Scope Boundaries

- **In scope**: Rename files, update all references (commands, docs, config, tests, CLAUDE.md), remove `--template-align-only` flag, resolve the flag's references in command definition
- **Out of scope**: Changing command behavior/logic, adding deprecation aliases, updating external docs/blog posts, modifying the issue pipeline processing order

## Success Metrics

- `grep -r 'refine_issue' .` returns 0 hits outside `.issues/completed/`, `.git/`, and `thoughts/` (historical plans)
- Every command, doc, config, and test file that referenced `refine_issue` now references `format_issue`
- `/ll:format-issue` works identically to the current `/ll:refine-issue` (minus the removed `--template-align-only` flag)

## Impact

- **Priority**: P2 - Misleading naming actively confuses the pipeline; blocks FEAT-380
- **Effort**: Small - File rename plus text find-and-replace across a known set of files
- **Risk**: Low - No logic changes, purely naming
- **Breaking Change**: Yes - Users of `/ll:refine-issue` will need to use `/ll:format-issue`

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| guidelines | .claude/CLAUDE.md | Lists refine_issue in command table and pipeline |
| architecture | docs/ARCHITECTURE.md | Documents issue lifecycle pipeline |

## Labels

`enhancement`, `commands`, `naming`, `captured`

## Resolution

- **Action**: implement
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `commands/refine_issue.md` → `commands/format_issue.md` [RENAMED] - command file with all internal references updated, `--template-align-only` flag removed
- `.claude/CLAUDE.md` [MODIFIED] - command listing updated
- `commands/help.md` [MODIFIED] - detailed listing and quick reference updated
- `templates/issue-sections.json` [MODIFIED] - `_meta.description` updated
- `skills/issue-workflow/SKILL.md` [MODIFIED] - workflow reference updated
- `README.md` [MODIFIED] - command table updated
- `docs/COMMANDS.md` [MODIFIED] - section header, table, and workflow updated
- `docs/ISSUE_TEMPLATE.md` [MODIFIED] - 4 inline references updated
- `CONTRIBUTING.md` [MODIFIED] - example updated
- `scripts/tests/test_session_log.py` [MODIFIED] - 4 test string references updated
- `IMPLEMENTATION_SUMMARY.md` [MODIFIED] - 6 references updated
- `affected-components-proposal.md` [MODIFIED] - 1 reference updated
- `docs/demo/README.md` [MODIFIED] - 2 references updated
- `docs/demo/scenarios.md` [MODIFIED] - 3 references updated

### Verification Results
- Tests: PASS (2695 passed)
- Lint: PASS
- Grep check: PASS (0 stray references outside excluded paths)

## Session Log
- `/ll:capture-issue` - 2026-02-12T12:00:00Z - `~/.claude/projects/<project>/d65a885a-6b92-4b2e-be03-ca8f0f08c767.jsonl`
- `/ll:refine-issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/20b6856b-a7ac-47b6-8baa-a7778f9cdfe3.jsonl`
- `/ll:manage-issue` - 2026-02-12T20:00:00Z - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/08cd37d5-4064-41cb-84d2-76a97c6cb047.jsonl`

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-12 | Priority: P2

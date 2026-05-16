---
discovered_date: 2026-03-01
discovered_by: capture-issue
---

# ENH-520: Deprecate and Remove ll-next-id

## Summary

Remove the standalone `ll-next-id` CLI tool, which is fully redundant with `ll-issues next-id`. Both call `get_next_issue_number()` and print the result. Consolidating to one entry point reduces tool surface confusion.

## Current Behavior

Two CLI tools perform the identical operation:
- `ll-next-id` — standalone tool in `cli/next_id.py`
- `ll-issues next-id` — subcommand of `ll-issues` in `cli/issues/next_id.py`

Both call `get_next_issue_number(config)` and print the zero-padded result. The `ll-next-id` epilog already notes: "This command is available as 'll-issues next-id' in the unified ll-issues CLI. Both forms remain functional."

## Expected Behavior

Only `ll-issues next-id` exists. The standalone `ll-next-id` entry point is removed from `pyproject.toml`, its CLI module deleted, and all references updated.

## Motivation

The ENH-500 CLI tool consolidation audit identified this as the only genuinely redundant tool pair. Removing it reduces the CLI surface from 13 to 12 tools, keeping within the 10–20 recommended range while eliminating a source of "which one do I use?" confusion.

## Proposed Solution

### Core Removal
1. Remove `ll-next-id` entry from `scripts/pyproject.toml` `[project.scripts]`
2. Delete `scripts/little_loops/cli/next_id.py`
3. Remove `main_next_id` import/export from `scripts/little_loops/cli/__init__.py`
4. Delete or update `scripts/tests/test_cli_next_id.py`

### Documentation Updates (remove `ll-next-id` references)
5. Update `commands/help.md` — remove `ll-next-id` from CLI TOOLS section
6. Update `.claude/CLAUDE.md` — remove `ll-next-id` from CLI Tools list
7. Update `README.md` — remove `ll-next-id` section

### Command/Skill Updates (replace `ll-next-id` → `ll-issues next-id`)
8. Update `commands/scan-codebase.md` — replace `ll-next-id` with `ll-issues next-id` (lines 228, 230)
9. Update `commands/scan-product.md` — replace `ll-next-id` with `ll-issues next-id` (lines 207, 209)
10. Update `skills/capture-issue/SKILL.md` — update allowed-tools and bash reference (lines 12, 201)
11. Update `skills/issue-size-review/SKILL.md` — update allowed-tools and bash reference (lines 10, 119)
12. Update `commands/normalize-issues.md` — update allowed-tools and bash reference (lines 7, 165)
13. Update `commands/find-dead-code.md` — replace bash reference (line 253)

## Implementation Steps

1. Remove entry point and source file
2. Update all documentation references
3. Remove or update tests
4. Verify `ll-issues next-id` still works correctly

## Integration Map

### Files to Modify
- `scripts/pyproject.toml` — remove `ll-next-id` entry point
- `scripts/little_loops/cli/next_id.py` — delete file
- `scripts/little_loops/cli/__init__.py` — remove `main_next_id` import/export
- `scripts/tests/test_cli_next_id.py` — delete or update

### Dependent Files (Callers/Importers)
- `commands/scan-codebase.md` — instructs agents to run `ll-next-id`
- `commands/scan-product.md` — instructs agents to run `ll-next-id`
- `skills/capture-issue/SKILL.md` — allowed-tools and bash reference
- `skills/issue-size-review/SKILL.md` — allowed-tools and bash reference
- `commands/normalize-issues.md` — allowed-tools and bash reference
- `commands/find-dead-code.md` — bash reference

### Similar Patterns
- N/A — this is the only standalone-to-subcommand migration

### Tests
- `scripts/tests/test_cli_next_id.py` — delete (functionality tested via `ll-issues next-id`)

### Documentation
- `commands/help.md` — CLI tools list
- `.claude/CLAUDE.md` — CLI Tools section
- `README.md` — ll-next-id subsection

### Configuration
- N/A

## Scope Boundaries

- Only the standalone `ll-next-id` entry point is removed; `ll-issues next-id` is unchanged
- No changes to the underlying `get_next_issue_number()` function or `issue_parser` module
- No changes to any other CLI tools or their entry points
- Documentation updates limited to removing `ll-next-id` references (not restructuring docs)

## Impact

- **Priority**: P4 — Low; tool works fine, just redundant
- **Effort**: Low — straightforward deletion
- **Risk**: Low — `ll-issues next-id` is the replacement
- **Breaking Change**: Yes (minor) — users of `ll-next-id` must switch to `ll-issues next-id`

## Labels

`enhancement`, `cli`, `cleanup`, `tooling`

## Resolution

Removed the standalone `ll-next-id` CLI tool. All 13 references across commands, skills, and documentation updated to use `ll-issues next-id`. Parity test removed; dedicated test file deleted.

### Changes
- Deleted `scripts/little_loops/cli/next_id.py`
- Deleted `scripts/tests/test_cli_next_id.py`
- Removed `ll-next-id` entry point from `scripts/pyproject.toml`
- Removed `main_next_id` import/export from `scripts/little_loops/cli/__init__.py`
- Updated allowed-tools and bash references in 4 commands and 2 skills
- Removed `ll-next-id` from documentation (CLAUDE.md, help.md, README.md)
- Removed parity test from `scripts/tests/test_issues_cli.py`

### Verification
- Tests: 3030 passed
- Lint: All checks passed
- Types: No issues in 87 source files

## Session Log
- `/ll:capture-issue` - 2026-03-01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`
- `/ll:manage-issue` - 2026-03-01 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ffa88660-2b5b-4a83-a475-9f7a9def1102.jsonl`

---

## Status

**Completed** | Created: 2026-03-01 | Completed: 2026-03-01 | Priority: P4

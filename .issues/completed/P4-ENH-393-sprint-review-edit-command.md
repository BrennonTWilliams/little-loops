---
discovered_date: 2026-02-12
discovered_by: capture_issue
---

# ENH-393: Add `ll-sprint edit` CLI subcommand for sprint modifications

## Summary

After creating a sprint with `/ll:create_sprint` or `ll-sprint create`, there is no way to edit the sprint beyond `ll-sprint show` (read-only) or deleting and recreating. Add an `ll-sprint edit` subcommand for deterministic sprint YAML mutations — adding/removing issues, pruning invalid references, and re-running validation.

## Current Behavior

Sprint post-creation workflow is limited to:
- `ll-sprint show` — read-only view with warnings but no fix actions
- `ll-sprint delete` + recreate — loses any manual adjustments
- Manual YAML editing — error-prone, no validation

## Expected Behavior

A new `ll-sprint edit` subcommand that supports:

```
ll-sprint edit sprint-1 --add BUG-045,ENH-050
ll-sprint edit sprint-1 --remove BUG-001
ll-sprint edit sprint-1 --prune          # remove invalid/completed refs
ll-sprint edit sprint-1 --revalidate     # re-run validation, show fixable issues
```

- `--add` — add issue IDs to an existing sprint (validates they exist)
- `--remove` — remove issue IDs from a sprint
- `--prune` — automatically remove invalid (missing file) and completed issue references
- `--revalidate` — re-run dependency analysis and report warnings after edits

## Motivation

When `/ll:create_sprint` suggests groupings via AskUserQuestion, the user selects quickly but the resulting sprint may have stale references, broken dependencies, or issues that have since been completed. The operations needed to fix these are deterministic YAML mutations that fit naturally as a CLI subcommand alongside the existing `create`, `show`, `delete` pattern.

## Proposed Solution

Add an `edit` subcommand to `ll-sprint` in `scripts/little_loops/cli/sprint.py`. The implementation is a thin layer over the existing `SprintManager` which already provides `validate_issues()`, `load()`, and `save()`.

## Scope Boundaries

- Out of scope: AI-guided sprint review (see ENH-394)
- Out of scope: Sprint execution logic changes
- Out of scope: Sprint history/versioning

## Implementation Steps

1. Add `edit` subparser to `main_sprint()` with `--add`, `--remove`, `--prune`, `--revalidate` flags
2. Implement `_cmd_sprint_edit()` using existing `SprintManager.validate_issues()` and `Sprint.save()`
3. Add `--prune` logic: load sprint, validate issues, remove any that are invalid or in `.issues/completed/`
4. Add `--revalidate` logic: re-run dependency analysis (reuse `_render_dependency_analysis`) after edits

## Impact

- **Priority**: P4 - Quality-of-life improvement, workarounds exist
- **Effort**: Low - Thin layer over existing `SprintManager` methods
- **Risk**: Low - Additive, no changes to existing sprint execution
- **Breaking Change**: No

## Success Metrics

- Users can add/remove issues from sprints without recreating
- `--prune` automatically removes all issues that `show` currently only warns about

## Related Key Documentation

| Category | Document | Relevance |
|----------|----------|-----------|
| architecture | docs/ARCHITECTURE.md | Sprint system architecture |
| implementation | scripts/little_loops/cli/sprint.py | Existing subcommand pattern |
| implementation | scripts/little_loops/sprint.py | SprintManager API |

## Labels

`enhancement`, `sprint`, `cli`, `captured`

## Resolution

- **Action**: implement
- **Completed**: 2026-02-12
- **Status**: Completed

### Changes Made
- `scripts/little_loops/cli/sprint.py`: Added `edit` subparser with `--add`, `--remove`, `--prune`, `--revalidate` flags and `_cmd_sprint_edit()` handler
- `scripts/tests/test_sprint.py`: Added `TestSprintEdit` class with 12 tests covering all flags, edge cases, and error paths

### Verification Results
- Tests: PASS (54/54)
- Lint: PASS
- Types: PASS

## Session Log
- `/ll:capture_issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/ab030831-19f7-4fb7-8753-c1c282a30c99.jsonl`
- `/ll:manage_issue` - 2026-02-12 - `~/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/a13b20f4-ebee-4f6b-a02a-30e13ee128d1.jsonl`

---

## Status

**Completed** | Created: 2026-02-12 | Completed: 2026-02-12 | Priority: P4

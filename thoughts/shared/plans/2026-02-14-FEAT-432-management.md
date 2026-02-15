# Implementation Plan: FEAT-432 — ll-deps fix command

**Issue**: P3-FEAT-432-dependency-validation-auto-fix-command.md
**Date**: 2026-02-14
**Action**: implement

## Summary

Add a `fix` subcommand to `ll-deps` that auto-repairs broken dependency references, stale completed refs, and missing backlinks. Cycles are explicitly out of scope.

## Research Findings

### Current Architecture
- `dependency_mapper.py` contains the full CLI (`main()` at line 913) with `analyze` and `validate` subcommands
- `validate_dependencies()` (line 461) returns a `ValidationResult` dataclass with:
  - `broken_refs`: `list[tuple[str, str]]` — (issue_id, missing_ref_id)
  - `stale_completed_refs`: `list[tuple[str, str]]` — (issue_id, completed_ref_id)
  - `missing_backlinks`: `list[tuple[str, str]]` — (issue_id, should_have_backlink_from)
  - `cycles`: `list[list[str]]` — out of scope for fix
- `_add_to_section()` (line 778) already adds entries to markdown sections
- No `_remove_from_section()` exists yet — needs to be created
- `add_dry_run_arg()` in `cli_args.py` provides standard `--dry-run/-n` pattern
- Issue files use `## Blocked By` and `## Blocks` sections with `- ISSUE-ID` list items
- `ISSUE_ID_PATTERN` regex in `issue_parser.py:22` matches `^[-*]\s+\*{0,2}([A-Z]+-\d+)`

### Existing Patterns to Follow
- Subcommand structure: `subparsers.add_parser()` with command-specific args
- `_load_issues()` helper returns `(issues, issue_contents, completed_ids)` tuple
- File modification: read with `read_text(encoding="utf-8")`, write with `write_text()`
- `_add_to_section()` handles both creating new sections and appending to existing ones
- `apply_proposals()` returns sorted list of modified file paths

## Implementation Plan

### Phase 1: Add `_remove_from_section()` helper

**File**: `scripts/little_loops/dependency_mapper.py` (after `_add_to_section`, ~line 842)

Create a helper that removes an issue ID from a markdown section:
- Find the section header with regex (same pattern as `_add_to_section`)
- Find the list item line containing the target issue ID
- Remove the line
- If the section becomes empty (no list items left), remove the entire section
- Write the file back

### Phase 2: Add `fix_dependencies()` function

**File**: `scripts/little_loops/dependency_mapper.py` (after `_remove_from_section`)

```python
@dataclass
class FixResult:
    changes: list[str]         # Human-readable descriptions
    modified_files: set[str]   # Paths of modified files

def fix_dependencies(
    issues: list[IssueInfo],
    completed_ids: set[str] | None = None,
    all_known_ids: set[str] | None = None,
    dry_run: bool = False,
) -> FixResult:
```

Logic:
1. Call `validate_dependencies()` to get the `ValidationResult`
2. Build `issue_path_map: dict[str, Path]` from issues list
3. For each `broken_ref` (issue_id, ref_id): remove ref_id from issue_id's `## Blocked By`
4. For each `stale_completed_ref` (issue_id, ref_id): remove ref_id from issue_id's `## Blocked By`
5. For each `missing_backlink` (issue_id, ref_id): add issue_id to ref_id's `## Blocks` section
6. Skip cycles (out of scope — report count in output)
7. If `dry_run`, collect changes but don't write files

### Phase 3: Add `fix` subcommand to CLI

**File**: `scripts/little_loops/dependency_mapper.py` in `main()` (after validate subparser, ~line 985)

- Add `fix` subparser with `--dry-run/-n` and `--sprint` arguments
- Route to `fix_dependencies()` in the command dispatch section
- Print human-readable report of changes made
- Return 0 on success

### Phase 4: Add tests

**File**: `scripts/tests/test_dependency_mapper.py`

Tests for `_remove_from_section()`:
- [x] Remove entry from section with multiple items
- [x] Remove last entry removes entire section
- [x] No-op when entry not present
- [x] Handles section at end of file

Tests for `fix_dependencies()`:
- [x] Fixes broken refs (removes from Blocked By)
- [x] Fixes stale completed refs (removes from Blocked By)
- [x] Adds missing backlinks (adds to Blocks)
- [x] Dry run doesn't modify files
- [x] Returns correct change descriptions
- [x] Skips cycles (no changes for cycles)
- [x] No changes when no issues found

Tests for CLI `fix` subcommand:
- [x] `ll-deps fix` with issues to fix
- [x] `ll-deps fix --dry-run` previews without changes
- [x] `ll-deps fix` with no issues returns 0

## Success Criteria

- [ ] `_remove_from_section()` correctly removes entries from markdown sections
- [ ] `fix_dependencies()` removes broken refs from Blocked By sections
- [ ] `fix_dependencies()` removes stale completed refs from Blocked By sections
- [ ] `fix_dependencies()` adds missing backlinks to Blocks sections
- [ ] `fix_dependencies()` with `dry_run=True` makes no file changes
- [ ] `ll-deps fix` CLI subcommand works end-to-end
- [ ] `ll-deps fix --dry-run` previews changes
- [ ] All tests pass: `python -m pytest scripts/tests/test_dependency_mapper.py -v`
- [ ] Type checking passes: `python -m mypy scripts/little_loops/dependency_mapper.py`
- [ ] Linting passes: `ruff check scripts/little_loops/dependency_mapper.py`

## Risk Assessment

- **Low risk**: Changes are additive (new function + new subcommand)
- **Safety**: `--dry-run` flag and `git diff` provide review before commit
- **No breaking changes**: Existing `analyze` and `validate` subcommands unchanged

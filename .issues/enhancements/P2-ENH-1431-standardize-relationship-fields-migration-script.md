---
id: ENH-1431
type: ENH
priority: P2
parent: ENH-1391
depends_on:
- ENH-1430
status: open
---

# ENH-1431: Standardize Relationship Fields — Migration Script

## Summary

Write and register the `ll-migrate-relationships` CLI that renames `parent_issue:` → `parent:` and `related:` → `relates_to:` across all existing issue files. Update `recursive-refine.yaml` grep pattern and corresponding test fixtures. Depends on ENH-1430 (parser must recognize new fields before migration runs).

## Parent Issue

Decomposed from ENH-1391: Standardize Issue Relationship Fields

## Scope

Covers implementation steps 3, 10, 11, and 12 from the parent (wiring stays with the implementation per TDD mode).

## Proposed Solution

### Step 3 — `scripts/little_loops/cli/migrate_relationships.py`

Follow `scripts/little_loops/cli/migrate.py` structure exactly:
- `main_migrate_relationships()` entry point with `--dry-run` flag
- Use `parse_frontmatter()` from `scripts/little_loops/frontmatter.py` to detect `parent_issue:` and `related:` keys
- Use `_set_fields(content, {"parent": value})` for in-place rename (no YAML round-trip)
- Glob `.issues/**/*.md`, iterate and print `[DRY RUN] RENAME ...` prefix in dry-run mode
- Migrate `parent_issue:` → `parent:` and `related:` → `relates_to:` in a single pass

Also update `scripts/little_loops/loops/recursive-refine.yaml`: change the shell grep pattern from `parent_issue:` to `parent:` (the loop finds child issues by grepping for the parent ID).

### Step 10 — `scripts/pyproject.toml`

Add to `[project.scripts]`:
```toml
ll-migrate-relationships = "little_loops.cli:main_migrate_relationships"
```

### Step 11 — `scripts/little_loops/cli/__init__.py`

Add export (follow the `from .migrate import main_migrate` pattern):
```python
from .migrate_relationships import main_migrate_relationships
```

### Step 12 — `scripts/tests/test_loops_recursive_refine.py`

Update fixture files at lines ~1029–1036: change `parent_issue: ENH-100` to `parent: ENH-100` to stay in sync with the `recursive-refine.yaml` grep pattern change.

## Files to Modify

- `scripts/little_loops/cli/migrate_relationships.py` — new file
- `scripts/little_loops/loops/recursive-refine.yaml` — grep pattern update
- `scripts/pyproject.toml` — CLI registration (wiring)
- `scripts/little_loops/cli/__init__.py` — export (wiring)
- `scripts/tests/test_loops_recursive_refine.py` — fixture update

## Tests

- `scripts/tests/test_migrate_relationships.py` — new test file; follow `_make_project()` / `_run_migrate()` / `_make_mock_run()` helpers from `scripts/tests/test_issue_migration.py`; `_run_migrate_relationships` shim calls `main_migrate_relationships`; no `subprocess.run` mock needed if migration does in-place `file.write_text()` only

## Acceptance Criteria

- `ll-migrate-relationships --dry-run` lists all files containing `parent_issue:` or `related:` without modifying them
- Running the script on a project with `parent_issue:` fields renames them to `parent:` in-place
- Running the script on a project with `related:` fields renames them to `relates_to:` in-place
- `recursive-refine.yaml` loop finds child issues correctly after migration (greps for `parent:`)
- `test_loops_recursive_refine.py` fixtures pass with `parent:` frontmatter
- `ll-migrate-relationships` is installable via `pip install -e ./scripts`

## Scope Boundaries

- **In scope**: Migration script, pyproject.toml + __init__.py wiring, recursive-refine.yaml grep, test fixtures
- **Out of scope**: Schema changes (ENH-1430), dependency graph logic (ENH-1432), docs/skills (ENH-1433)
- **Depends on**: ENH-1430 — parser must recognize `parent:` before running migration

## Session Log
- `/ll:issue-size-review` - 2026-05-10T22:45:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/9d7aaebe-3f48-42d8-9447-6f3abf7cabd4.jsonl`

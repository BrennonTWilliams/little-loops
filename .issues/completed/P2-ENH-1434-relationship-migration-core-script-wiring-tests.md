---
id: ENH-1434
type: ENH
priority: P2

depends_on:
- ENH-1430
status: done
completed_at: 2026-05-11T00:18:00Z
confidence_score: 100
outcome_confidence: 86
score_complexity: 18
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 25
parent: ENH-1431
---

# ENH-1434: Relationship Migration — Core Script, Wiring, and Tests

## Summary

Implement the `ll-migrate-relationships` CLI that renames `parent_issue:` → `parent:` and `related:` → `relates_to:` in all issue files. Wire it into `pyproject.toml` and `cli/__init__.py`. Update `recursive-refine.yaml` grep pattern and the affected test fixture locations.

## Current Behavior

No `ll-migrate-relationships` CLI exists. Issue files continue to use the deprecated `parent_issue:` and `related:` frontmatter keys. The `recursive-refine.yaml` loop greps for `parent_issue:` to build its child-issue map, and test fixtures write `parent_issue:` frontmatter.

## Expected Behavior

See Acceptance Criteria below. Running `ll-migrate-relationships` renames `parent_issue:` → `parent:` and `related:` → `relates_to:` in-place across all issue files. `recursive-refine.yaml` greps for `parent:`. All related tests pass with updated fixture frontmatter.

## Parent Issue

Decomposed from ENH-1431: Standardize Relationship Fields — Migration Script

## Scope

Covers Steps 3, 10, 11, 12, and 13 from ENH-1431. Wiring stays with implementation per TDD mode.

## Proposed Solution

### Step 3 — `scripts/little_loops/cli/migrate_relationships.py`

Follow `scripts/little_loops/cli/migrate.py` structure exactly:
- `main_migrate_relationships()` entry point with `--dry-run` flag
- Use `parse_frontmatter()` from `scripts/little_loops/frontmatter.py` to detect `parent_issue:` and `related:` keys
- Copy `_set_fields` and `_FM_FIELD_RE` from `migrate.py` (lines 17 and 20–43) into this file
- Use `_set_fields(content, {"parent": value})` then strip old key via regex: `re.sub(r"^parent_issue:.*\n", "", updated, flags=re.MULTILINE)`
- Glob `.issues/**/*.md`, iterate and print `[DRY RUN] RENAME ...` prefix in dry-run mode
- Migrate `parent_issue:` → `parent:` and `related:` → `relates_to:` in a single pass

Also update `scripts/little_loops/loops/recursive-refine.yaml` line 681: change the Python block's `f'parent_issue: {iid}'` → `f'parent: {iid}'` in `build_parent_map()` / `done` state.

**Critical notes (from `/ll:refine-issue`)**:
- `_set_fields()` is defined in `migrate.py` itself (lines 20–43), not imported from `frontmatter.py` — it only adds/overwrites, does not remove old keys
- Use `add_dry_run_arg(parser)` and `add_config_arg(parser)` from `scripts/little_loops/cli_args.py`
- For `related:` rename: do a raw key rename only (do not parse the value format)

### Step 10 — `scripts/pyproject.toml`

Add to `[project.scripts]` after the `ll-migrate` line (~line 64):
```toml
ll-migrate-relationships = "little_loops.cli:main_migrate_relationships"
```

### Step 11 — `scripts/little_loops/cli/__init__.py`

Add export after the `from .migrate import main_migrate` line (~line 31):
```python
from .migrate_relationships import main_migrate_relationships
```
Add `"main_migrate_relationships"` to `__all__` and add `ll-migrate-relationships` to the module docstring CLI bullet list.

### Step 12 — `scripts/tests/test_loops_recursive_refine.py` (lines 1029–1037)

Update three `write_text()` fixture calls: change `parent_issue: ENH-100` → `parent: ENH-100` and `parent_issue: ENH-201` → `parent: ENH-201`.

### Step 13 — `scripts/tests/test_loops_recursive_refine.py` (line 775)

Update the assertion on the `build_parent_map()` grep command string: `f'parent_issue: {iid}'` → `f'parent: {iid}'`. This line is outside the 1029–1037 range but must also change.

### Wiring Phase (added by `/ll:wire-issue`)

_Touchpoints identified by wiring analysis — include during implementation:_

1. After creating `migrate_relationships.py` and wiring it into `cli/__init__.py` (Step 11), run `python -m pytest scripts/tests/test_ll_loop_state.py -x` to confirm no import-time errors before proceeding.
2. When grepping for `parent_issue` to find all changes, the following matches are **intentional** and must NOT be changed:
   - `test_issue_parser.py:1620` — tests deprecated-alias backward compatibility
   - `test_issue_lifecycle.py:1260` — event payload field, not frontmatter key

## Integration Map

### Files to Create
- `scripts/little_loops/cli/migrate_relationships.py` — new migration CLI; copy `_set_fields` and `_FM_FIELD_RE` from `migrate.py` (lines 17 and 20–43)
- `scripts/tests/test_migrate_relationships.py` — new test file; follow `_make_project()` / `_run_migrate()` / `_make_mock_run()` helpers from `scripts/tests/test_issue_migration.py`; use `_run_migrate_relationships` shim calling `main_migrate_relationships`

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml:681` — Python block in `build_parent_map()` / `done` state
- `scripts/pyproject.toml:~64` — Add entry point after `ll-migrate` line
- `scripts/little_loops/cli/__init__.py:~31` — Import, `__all__`, and docstring bullet
- `scripts/tests/test_loops_recursive_refine.py:775` — grep command assertion
- `scripts/tests/test_loops_recursive_refine.py:1029–1037` — Three fixture `write_text()` calls

### Similar Patterns (Template Files)
- `scripts/little_loops/cli/migrate.py` — full implementation template
- `scripts/tests/test_issue_migration.py` — test template

### Tests

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_migrate_relationships.py` — new file to create; follow `_make_project` / `_run_migrate` class pattern from `test_issue_migration.py` [planned in Files to Create]
- `scripts/tests/test_loops_recursive_refine.py:775` — `TestDoneSummary._DONE_SCRIPT` class constant is a verbatim copy of the recursive-refine YAML's embedded Python/bash script; the grep string at this line must change to `parent:` to stay in sync with the YAML update at line 681 [Step 13]
- `scripts/tests/test_loops_recursive_refine.py:1026–1037` — `test_decomposition_tree_three_levels` three `write_text()` fixture calls; change `parent_issue:` → `parent:` [Step 12]
- `scripts/tests/test_ll_loop_state.py` — validation target (no changes needed); 9 test methods each do `from little_loops.cli import main_loop` at call time — if `migrate_relationships.py` has an import-time error when wired into `cli/__init__.py`, all 9 fail at collection; run after Step 11 to confirm clean import

**Do NOT modify (intentional test behavior):**
- `scripts/tests/test_issue_parser.py:1620` — `TestDeprecationAliasHandling.test_parse_parent_issue_alias_emits_warning` intentionally writes `parent_issue:` frontmatter to exercise the deprecated-alias warning path in `issue_parser.py`; must stay as `parent_issue:`
- `scripts/tests/test_issue_lifecycle.py:1260` — asserts `event["parent_issue_id"]` which is an event payload field emitted by `capture_bug_from_failure()`, not an issue frontmatter key; unrelated to the frontmatter migration

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**`_FM_FIELD_RE` exact definition** (migrate.py line 17):
```python
_FM_FIELD_RE = re.compile(r"^---\s*$", re.MULTILINE)
```
Matches lines that are `---` with optional trailing whitespace; used in `_set_fields` to locate the closing `---` delimiter when inserting a new key.

**`pyproject.toml` slot** — insert after the `ll-migrate` line and before `ll-logs`:
```toml
ll-migrate = "little_loops.cli:main_migrate"
ll-migrate-relationships = "little_loops.cli:main_migrate_relationships"  # new
ll-logs = "little_loops.cli:main_logs"
```

**Test class structure** to follow from `test_issue_migration.py` (not module-level functions):
- `TestMigrateCompleted` — lines 91–176: files from completed/ to type dirs
- `TestMigrateDeferred` — lines 179–209: files from deferred/ to type dirs
- `TestMigrateDryRun` — lines 212–244: --dry-run flag behaviour
- `TestMigrateEdgeCases` — lines 247–310: untyped files, collisions, etc.
For `test_migrate_relationships.py`, use equivalent classes: `TestMigrateRelationshipsParentIssue`, `TestMigrateRelationshipsRelated`, `TestMigrateRelationshipsDryRun`, `TestMigrateRelationshipsEdgeCases`.

**`_make_mock_run()` not needed** — the new migration only reads/writes files (no `git ls-files`, `git log`, or `git mv` calls), so tests can call `main_migrate_relationships()` directly without subprocess mocking. Use `_run_migrate_relationships(project, *extra_args)` shim following `_run_migrate()` pattern (patch `sys.argv`, call `main_migrate_relationships()`).

**Corrected line range** for write_text fixture calls: research confirms they start at **line 1026**, not 1029. Step 12 below should reference lines 1026–1037.

**Exact fixture strings** needing change in `test_loops_recursive_refine.py:1026–1037`:
```python
# Before (3 occurrences, ~lines 1029-1034):
(issues_dir / "P3-ENH-200-child-a.md").write_text("---\nid: ENH-200\nparent_issue: ENH-100\n---\n")
(issues_dir / "P3-ENH-201-child-b.md").write_text("---\nid: ENH-201\nparent_issue: ENH-100\n---\n")
(issues_dir / "P3-ENH-300-grandchild.md").write_text("---\nid: ENH-300\nparent_issue: ENH-201\n---\n")
# After:
(issues_dir / "P3-ENH-200-child-a.md").write_text("---\nid: ENH-200\nparent: ENH-100\n---\n")
(issues_dir / "P3-ENH-201-child-b.md").write_text("---\nid: ENH-201\nparent: ENH-100\n---\n")
(issues_dir / "P3-ENH-300-grandchild.md").write_text("---\nid: ENH-300\nparent: ENH-201\n---\n")
```

## Acceptance Criteria

- `ll-migrate-relationships --dry-run` lists all files with `parent_issue:` or `related:` without modifying them
- Running on a project with `parent_issue:` fields renames them to `parent:` in-place and removes the old key
- Running on a project with `related:` fields renames them to `relates_to:` in-place
- `recursive-refine.yaml` loop finds child issues correctly after migration (greps `parent:`)
- `test_loops_recursive_refine.py` passes with `parent:` frontmatter in fixtures (lines 775 and 1029–1037)
- `ll-migrate-relationships` is installable via `pip install -e ./scripts`

## Scope Boundaries

- **In scope**: Migration script, pyproject.toml + __init__.py wiring, recursive-refine.yaml grep, test fixtures
- **Out of scope**: Doc and count assertion updates (ENH-1435), schema changes (ENH-1430), dependency graph (ENH-1432)
- **Depends on**: ENH-1430 — parser must recognize `parent:` before running migration

## Impact

- **Priority**: P2 — Required step in ENH-1431 relationship field standardization; blocks consistent frontmatter across all issue files
- **Effort**: Medium — New CLI (`migrate_relationships.py`) following the existing `migrate.py` pattern; touches pyproject.toml, `__init__.py`, one YAML loop, and two test files
- **Risk**: Low — `--dry-run` mode provided; migration is in-place string substitution; no schema or API changes
- **Breaking Change**: No — migration is additive; old key removed only after new key is written

## Labels

`enhancement`, `migration`, `cli`, `decomposed`

## Status

**Open** | Created: 2026-05-10 | Priority: P2

## Resolution

Implemented `ll-migrate-relationships` CLI that renames `parent_issue:` → `parent:` and `related:` → `relates_to:` in all issue files. Wired into `pyproject.toml` and `cli/__init__.py`. Updated `recursive-refine.yaml` grep pattern and test fixtures. Added 11 tests across 4 test classes.

## Session Log
- `/ll:manage-issue` - 2026-05-11T00:18:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/dff0f60b-9452-4723-a1a6-2beb694f0474.jsonl`
- `/ll:ready-issue` - 2026-05-10T23:35:40 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/46656486-77a1-4ce3-ae49-e9122dd04f28.jsonl`
- `/ll:wire-issue` - 2026-05-10T23:28:47 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/15a59544-3e5f-40a3-8dad-8425866f4b2a.jsonl`
- `/ll:refine-issue` - 2026-05-10T23:22:53 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/6c08b0f3-1a9e-42f4-821b-e778e9280990.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/98a93952-5a1f-4e01-9075-6dbfef3784ef.jsonl`
- `/ll:confidence-check` - 2026-05-10T23:45:00 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d4e40523-1316-42b8-8950-d3f826b7702e.jsonl`

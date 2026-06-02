---
id: ENH-1431
type: ENH
priority: P2
parent: ENH-1391
depends_on:
- ENH-1430
status: done
confidence_score: 100
outcome_confidence: 67
score_complexity: 14
score_test_coverage: 18
score_ambiguity: 25
score_change_surface: 10
size: Very Large
completed_at: 2026-05-10T00:00:00Z
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

Also update `scripts/little_loops/loops/recursive-refine.yaml`: change the Python grep pattern from `parent_issue:` to `parent:` (the loop finds child issues by grepping for the parent ID).

### Step 10 — `scripts/pyproject.toml`

Add to `[project.scripts]`:
```toml
ll-migrate-relationships = "little_loops.cli:main_migrate_relationships"
```

### Step 11 — `scripts/little_loops/cli/__init__.py`

Add export (follow the `from .migrate import main_migrate` pattern at line 31):
```python
from .migrate_relationships import main_migrate_relationships
```
Also add `"main_migrate_relationships"` to `__all__` and add `ll-migrate-relationships` to the module docstring CLI bullet list.

### Step 12 — `scripts/tests/test_loops_recursive_refine.py`

Update fixture files at lines 1029–1037: change `parent_issue: ENH-100` to `parent: ENH-100` and `parent_issue: ENH-201` to `parent: ENH-201` — three `write_text()` calls in one test to stay in sync with the `recursive-refine.yaml` grep pattern change.

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

**Critical: `_set_fields()` does not delete old keys**
`_set_fields()` is defined in `migrate.py` itself (lines 20–43) — it is not imported from `frontmatter.py`. It only adds/overwrites keys; it does **not** remove them. A rename requires two steps:
1. `updated = _set_fields(content, {"parent": old_value})` — write the canonical key
2. Strip the old key via regex: `updated = re.sub(r"^parent_issue:.*\n", "", updated, flags=re.MULTILINE)`

Copy `_set_fields` and `_FM_FIELD_RE` into `migrate_relationships.py` (or import from `migrate.py` if that import is acceptable) rather than calling `frontmatter.update_frontmatter()` (which does a full YAML round-trip and may reformat values).

**`recursive-refine.yaml` exact change location**
The grep pattern to update is inside a **Python block** (not a shell block) at line 681, in the `build_parent_map()` function inside the `done` state:
```python
['grep', '-rl', f'parent_issue: {iid}', '.issues/'],
```
Change to `f'parent: {iid}'`. The other grep calls in the file (`"Decomposed from $PARENT_ID"`) are body-text greps and are unaffected.

**`add_dry_run_arg()` / `add_config_arg()` from `cli_args.py`**
Use `add_dry_run_arg(parser)` and `add_config_arg(parser)` from `scripts/little_loops/cli_args.py` (same helpers used by `migrate.py`). After parsing: `dry_run: bool = args.dry_run`, `repo_root: Path = args.config or Path.cwd()`.

**`related:` field migration note**
`issue_parser.py` (lines 488–492) handles `related:` as both comma-delimited string and list. For migration, a raw key rename is sufficient — do not parse the value, just rename the key regardless of value format.

**Detection pattern** (from `issue_parser.py` lines 473–492):
```python
fm = parse_frontmatter(content)  # from frontmatter.py
needs_migration = "parent_issue" in fm or "related" in fm
```

### Wiring Phase (added by `/ll:wire-issue`)

_These touchpoints were identified by wiring analysis and must be included in the implementation:_

13. Update `scripts/tests/test_loops_recursive_refine.py:775` — the assertion on the `build_parent_map()` grep command string (`f'parent_issue: {iid}'` → `f'parent: {iid}'`); this is outside the lines 1029–1037 range already listed in Step 12
14. Update doc/wiring files for the new CLI tool (follow the same pattern that landed with `ll-migrate` in ENH-1420):
    - `.claude/CLAUDE.md` — add `ll-migrate-relationships` bullet to CLI Tools list
    - `README.md` — increment tool count `"18 CLI tools"` → `"19 CLI tools"`; add `### ll-migrate-relationships` section after `### ll-migrate`
    - `commands/help.md` — add `ll-migrate-relationships` line in CLI TOOLS block
    - `docs/reference/CLI.md` — add `### ll-migrate-relationships` section (flags table + examples) after `### ll-migrate`
    - `skills/configure/areas.md` — `"Authorize all 17"` → `"Authorize all 18"`; add `ll-migrate-relationships` to the enumerated list
15. Update count assertion tests that will break when the docs are updated:
    - `scripts/tests/test_create_extension_wiring.py` — `"18 CLI tools"` → `"19 CLI tools"` (2 assertions) and `"Authorize all 17"` → `"Authorize all 18"` (2 assertions)
    - `scripts/tests/test_ll_logs_wiring.py` — `"Authorize all 17"` → `"Authorize all 18"` (1 assertion)

## Integration Map

### Files to Create
- `scripts/little_loops/cli/migrate_relationships.py` — new migration CLI; copy `_set_fields` and `_FM_FIELD_RE` from `migrate.py` (lines 17 and 20–43)

### Files to Modify
- `scripts/little_loops/loops/recursive-refine.yaml:681` — Python block in `build_parent_map()` / `done` state; `parent_issue: {iid}` → `parent: {iid}`
- `scripts/pyproject.toml:~64` — Add entry point after `ll-migrate` line
- `scripts/little_loops/cli/__init__.py:~31` — Import, `__all__`, and docstring bullet
- `scripts/tests/test_loops_recursive_refine.py:1029–1037` — Three fixture `write_text()` calls

### Similar Patterns (Template Files)
- `scripts/little_loops/cli/migrate.py` — full implementation template (entry point, arg parsing, dry-run guard, file iteration, `_set_fields`, summary)
- `scripts/tests/test_issue_migration.py` — test template (`_make_project`, `_run_migrate`, `_make_mock_run`, dry-run class)

### Tests
- `scripts/tests/test_migrate_relationships.py` — new file (to create)
- `scripts/tests/test_loops_recursive_refine.py` — fixture update only (lines 1029–1037 three `write_text()` calls) **plus** line 775: the assertion on the `build_parent_map()` grep command itself (`f'parent_issue: {iid}'` → `f'parent: {iid}'`) — this is outside the 1029–1037 range but must also change

_Wiring pass added by `/ll:wire-issue`:_
- `scripts/tests/test_create_extension_wiring.py` — update **four** hardcoded count assertions that will break when docs are updated: `"18 CLI tools"` → `"19 CLI tools"` (in `TestFeat1045DocUpdates.test_readme_tool_count_is_18` and `TestFeat1229LlActionWiring.test_readme_tool_count_is_18`), `"Authorize all 17"` → `"Authorize all 18"` (in `TestConfigureAreasWiring.test_count_updated_to_17` and `test_configure_areas_count_is_17`)
- `scripts/tests/test_ll_logs_wiring.py` — update `TestConfigureAreasWiring.test_authorize_all_count_is_17`: `"Authorize all 17"` → `"Authorize all 18"` (comment says "includes ll-logs and ll-migrate"; add ll-migrate-relationships)

### Documentation

_Wiring pass added by `/ll:wire-issue`:_
- `.claude/CLAUDE.md` — "CLI Tools" bullet list (near line 119): add `ll-migrate-relationships` entry after `ll-migrate`
- `README.md` — (a) increment `"18 CLI tools"` → `"19 CLI tools"` (line 90); (b) add `### ll-migrate-relationships` section after `### ll-migrate` (line ~500)
- `commands/help.md` — CLI TOOLS block (near line 239): add `ll-migrate-relationships` line after `ll-migrate`
- `docs/reference/CLI.md` — add `### ll-migrate-relationships` section (flags table + examples) after `### ll-migrate` section (line ~1156)
- `skills/configure/areas.md` — `authorize-all` description (line 823): `"Authorize all 17"` → `"Authorize all 18"`; add `ll-migrate-relationships` to the enumerated tool list

### Dependent Issues
- ENH-1432 (`ll-deps` tooling) — reads `parent:` field after this migration runs
- ENH-1433 (docs/skills display) — references `parent:` / `relates_to:` in output

## Files to Modify

- `scripts/little_loops/cli/migrate_relationships.py` — new file
- `scripts/little_loops/loops/recursive-refine.yaml` — grep pattern update (line 681, Python block)
- `scripts/pyproject.toml` — CLI registration (wiring)
- `scripts/little_loops/cli/__init__.py` — export, `__all__`, and docstring (wiring)
- `scripts/tests/test_loops_recursive_refine.py` — fixture update (lines 1029–1037 **and** line 775 grep command assertion)
- `.claude/CLAUDE.md` — add `ll-migrate-relationships` to CLI Tools list _(wiring pass)_
- `README.md` — tool count increment + new section _(wiring pass)_
- `commands/help.md` — add CLI entry _(wiring pass)_
- `docs/reference/CLI.md` — add CLI reference section _(wiring pass)_
- `skills/configure/areas.md` — increment authorize-all count + add tool _(wiring pass)_
- `scripts/tests/test_create_extension_wiring.py` — update four count assertions _(wiring pass)_
- `scripts/tests/test_ll_logs_wiring.py` — update one count assertion _(wiring pass)_

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

## Confidence Check Notes

_Added by `/ll:confidence-check` on 2026-05-10_

**Readiness Score**: 100/100 → PROCEED
**Outcome Confidence**: 67/100 → MODERATE

### Outcome Risk Factors
- Wide change surface: 13 distinct sites spanning core Python, YAML loop, pyproject.toml, `__init__.py`, 5 doc files, and 5 test assertion files — any missed site leaves a broken test
- Test assertion synchrony: `"18 CLI tools"` → `"19 CLI tools"` and `"Authorize all 17"` → `"Authorize all 18"` are hardcoded in 3 test files (6 assertion locations); doc updates and test updates must be applied together or tests will fail mid-implementation

## Session Log
- `/ll:refine-issue` - 2026-05-10T23:07:32 - `decf63c5-13b5-4c00-af8e-c125c17d56b7.jsonl`
- `/ll:issue-size-review` - 2026-05-10T22:45:00Z - `9d7aaebe-3f48-42d8-9447-6f3abf7cabd4.jsonl`
- `/ll:wire-issue` - 2026-05-10T00:00:00 - `current.jsonl`
- `/ll:confidence-check` - 2026-05-10T00:00:00 - `f30ae2b1-a2f3-4c49-9941-782407367610.jsonl`
- `/ll:issue-size-review` - 2026-05-10T00:00:00Z - `98a93952-5a1f-4e01-9075-6dbfef3784ef.jsonl`

---

## Resolution

- **Status**: Decomposed
- **Completed**: 2026-05-10
- **Reason**: Issue too large for single session (score 11/11 — Very Large)

### Decomposed Into
- ENH-1434: Relationship Migration — Core Script, Wiring, and Tests
- ENH-1435: Relationship Migration — Docs and Count Assertion Sync

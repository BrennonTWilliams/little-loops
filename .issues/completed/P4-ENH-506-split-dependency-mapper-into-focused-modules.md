---
discovered_commit: 5d6419bad2fa3174b9f2c4062ef912bba5205e1a
discovered_branch: main
discovered_date: 2026-02-25
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 98
outcome_confidence: 79
---

# ENH-506: Split `dependency_mapper.py` into focused modules

## Summary

Architectural issue found by `/ll:audit-architecture`. `dependency_mapper.py` is 1,360 lines and handles five distinct concerns in a single module: data models, conflict analysis, dependency validation, fix operations, and CLI entry point.

## Location

- **File**: `scripts/little_loops/dependency_mapper.py`
- **Line(s)**: 1–1,361 (entire file)
- **Module**: `little_loops.dependency_mapper`

## Finding

### Current State

`dependency_mapper.py` conflates five responsibilities:

1. **Data models** (lines 95–188): `DependencyProposal`, `ParallelSafePair`, `ValidationResult`, `DependencyReport`
2. **Analysis functions** (lines 179–527): `_extract_semantic_targets`, `compute_conflict_score`, `find_file_overlaps`, `validate_dependencies`, `analyze_dependencies`
3. **Formatting/reporting** (lines 561–759): `format_report`, `format_text_graph`
4. **Fix operations** (lines 760–1004): `apply_proposals`, `_add_to_section`, `_remove_from_section`, `fix_dependencies`, `gather_all_issue_ids`, `_load_issues`
5. **CLI entry** (lines 1085–1361): `main()` with `_load_issues()` helper at lines 1040–1082

The module is imported by `cli/sprint/edit.py`, `cli/sprint/manage.py`, `cli/sprint/run.py`, `cli/sprint/show.py`, and `issue_manager.py` — meaning all consumers depend on the full 1,321-line module regardless of which functionality they need.

```python
# Current: single monolithic import
from little_loops.dependency_mapper import analyze_dependencies, format_report, fix_dependencies
```

### Impact

- **Development velocity**: Large file is slow to navigate; changes in one area risk unintentionally affecting others
- **Maintainability**: Five concerns in one file makes it hard to find and modify specific behavior
- **Testability**: `test_dependency_mapper.py` is already 1,394 lines and tests all concerns together
- **Risk**: `FixResult` class (line 918) is separated from other data models at lines 95–188 — likely grew organically

## Integration Map

### Files to Modify

- `scripts/little_loops/dependency_mapper.py` — replace with `dependency_mapper/` sub-package
- `scripts/pyproject.toml:59` — update entry point: `"little_loops.dependency_mapper:main"` → `"little_loops.cli:main_deps"`
- `scripts/little_loops/cli/__init__.py:18-31` — add `from little_loops.cli.deps import main_deps` and `"main_deps"` to `__all__`

### Dependent Files (Callers/Importers)

All consumers use deferred (inside-function) imports — no changes needed if `__init__.py` re-exports all names:

- `scripts/little_loops/cli/sprint/edit.py:107-110` — imports `analyze_dependencies`, `gather_all_issue_ids`
- `scripts/little_loops/cli/sprint/manage.py:75` — imports `gather_all_issue_ids`
- `scripts/little_loops/cli/sprint/run.py:140,147` — imports `gather_all_issue_ids`, `analyze_dependencies`
- `scripts/little_loops/cli/sprint/show.py:170,200` — imports `gather_all_issue_ids`, `analyze_dependencies`
- `scripts/little_loops/issue_manager.py:709` — imports `gather_all_issue_ids`

### Required `__init__.py` Re-Exports

The following names must be in `__all__` (sourced from test imports at `tests/test_dependency_mapper.py:9-26`):

| Name | Destination module |
|---|---|
| `DependencyProposal`, `ParallelSafePair`, `ValidationResult`, `DependencyReport`, `FixResult` | `models.py` |
| `compute_conflict_score`, `find_file_overlaps`, `validate_dependencies`, `analyze_dependencies` | `analysis.py` |
| `format_report`, `format_text_graph` | `formatting.py` |
| `apply_proposals`, `fix_dependencies`, `gather_all_issue_ids` | `operations.py` |
| `extract_file_paths` | re-exported from `text_utils` (currently imported at top of `dependency_mapper.py`) |
| `_remove_from_section` | private, re-exported for test access |
| `main` | `cli/deps.py` (or thin wrapper in `__init__.py`) |

### Similar Patterns

- `scripts/little_loops/issue_history/__init__.py` — canonical sub-package split pattern; re-exports all public + selected private names in `__all__`
- `scripts/little_loops/issue_discovery/__init__.py` — compact variant (3 sub-modules)
- `scripts/little_loops/cli/history.py` — pattern for CLI entry point (`main_history()` with lazy imports inside function)

### Tests

- `scripts/tests/test_dependency_mapper.py` — 1,548 lines; imports 16 names from `dependency_mapper`

### Test Split Naming Convention (following `issue_history` pattern)

- `tests/test_dependency_mapper_models.py` → `dependency_mapper/models.py`
- `tests/test_dependency_mapper_analysis.py` → `dependency_mapper/analysis.py`
- `tests/test_dependency_mapper_formatting.py` → `dependency_mapper/formatting.py`
- `tests/test_dependency_mapper_operations.py` → `dependency_mapper/operations.py`

### Documentation Requiring Updates

- `scripts/pyproject.toml:59` — entry point binding (see Files to Modify)
- `docs/reference/API.md:603` — documents `little_loops.dependency_mapper` module
- `docs/ARCHITECTURE.md:222,693` — references `dependency_mapper.py` in architecture diagram
- `CONTRIBUTING.md` — directory structure diagram
- `skills/map-dependencies/SKILL.md` — references `apply_proposals()` from `dependency_mapper.py`

## Proposed Solution

Split into a `dependency_mapper/` sub-package mirroring the existing `issue_history/` and `issue_discovery/` pattern:

```
scripts/little_loops/dependency_mapper/
├── __init__.py          # Re-exports for backwards compatibility
├── models.py            # DependencyProposal, ParallelSafePair, ValidationResult, DependencyReport, FixResult
├── analysis.py          # compute_conflict_score, find_file_overlaps, validate_dependencies, analyze_dependencies
├── formatting.py        # format_report, format_text_graph
└── operations.py        # apply_proposals, fix_dependencies, _add/remove_to_section helpers
```

CLI entry (`main`) moves to `scripts/little_loops/cli/deps.py` or remains as a thin wrapper in the package.

### Suggested Approach

1. Create `scripts/little_loops/dependency_mapper/` directory with `__init__.py`
2. Move data models (including `FixResult` at line 918) to `models.py` — note `FixResult` is currently ~823 lines away from the other dataclasses (DependencyProposal at line 95)
3. Move analysis functions (lines 179–558) **and** module-level constants/dicts (lines 28–91: `_CODE_FENCE`, `_PASCAL_CASE`, `_FUNCTION_REF`, `_COMPONENT_SCOPE`, `_SECTION_KEYWORDS`, `_MODIFICATION_TYPES`) to `analysis.py`
4. Move formatting functions (lines 561–757) to `formatting.py`
5. Move fix/mutation operations (lines 760–1037) to `operations.py`
6. Create `scripts/little_loops/cli/deps.py` with `main_deps()` — move `main()` (lines 1085–1361) and `_load_issues()` (lines 1040–1082) there; follow `cli/history.py` pattern
7. Update `scripts/pyproject.toml:59`: `ll-deps = "little_loops.dependency_mapper:main"` → `ll-deps = "little_loops.cli:main_deps"`
8. Update `scripts/little_loops/cli/__init__.py:18-31`: add `from little_loops.cli.deps import main_deps` and add `"main_deps"` to `__all__` (follow existing `main_history`, `main_auto` entries)
9. Update `dependency_mapper/__init__.py` to re-export all public names — include `extract_file_paths` (imported from `text_utils`) and private names needed by tests (see Integration Map above)
10. Update test file to mirror the split (or keep combined — low urgency); see Integration Map for naming convention
11. Verify all existing imports (`cli/sprint/*.py`, `issue_manager.py`) still resolve — run `python -m pytest scripts/tests/test_dependency_mapper.py -v`

### Codebase Research Findings

_Added by `/ll:refine-issue` — based on codebase analysis:_

- `__init__.py` pattern: follow `issue_history/__init__.py:1-194` exactly — docstring lists all exports by category, `__all__` re-exports both public and selected private names with `# Private functions re-exported for test access` comment
- All five external consumers use lazy (inside-function) imports; no caller files need changes if `__init__.py` re-exports correctly
- The `main()` function at `dependency_mapper.py:1085-1361` is 276 lines — it belongs in `cli/deps.py`, not in `__init__.py`, to follow the pattern used by all other CLI tools
- `FixResult` dataclass (line 917) is stranded mid-file, 740 lines from the other dataclasses — moving it to `models.py` removes this inconsistency

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low (internal refactor with re-exports for backwards compat)
- **Breaking Change**: No (if `__init__.py` re-exports all names)

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Resolution

Split `dependency_mapper.py` (1,361 lines) into a `dependency_mapper/` sub-package:
- `models.py` — 5 dataclasses (`DependencyProposal`, `ParallelSafePair`, `ValidationResult`, `DependencyReport`, `FixResult`)
- `analysis.py` — 6 module-level constants + 7 functions (conflict scoring, file overlap, validation, analysis)
- `formatting.py` — 2 functions (`format_report`, `format_text_graph`)
- `operations.py` — 5 functions (`apply_proposals`, `_add_to_section`, `_remove_from_section`, `fix_dependencies`, `gather_all_issue_ids`)
- `__init__.py` — re-exports all 16 public names + `_remove_from_section` (test access) + backward-compat `main` wrapper
- CLI migrated to `cli/deps.py` as `main_deps()` with deferred imports
- `pyproject.toml:59` updated: `ll-deps = "little_loops.cli:main_deps"`
- `cli/__init__.py` updated: added `main_deps` import and `__all__` entry
- Documentation updated in `docs/ARCHITECTURE.md`, `docs/reference/API.md`, `CONTRIBUTING.md`, `skills/map-dependencies/SKILL.md`
- All 3099 tests pass, ruff clean, mypy clean

## Status

**Completed** | Created: 2026-02-25 | Completed: 2026-03-03 | Priority: P4

## Session Log
- `/ll:verify-issues` - 2026-02-25 - Corrected line count: 1,321 → 1,337 (file has grown since issue was created)
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is well-specified with complete module split plan and caller list; no knowledge gaps identified
- `/ll:audit-architecture` - 2026-02-26 - Dependency mapping audit: dependency_mapper.py has 5 consumers (cli/sprint/edit, cli/sprint/manage, cli/sprint/run, cli/sprint/show, issue_manager.py), sits at Layer 2 in dependency hierarchy. Split would allow consumers to import only the sub-module they need (analysis vs formatting vs operations), reducing transitive load.
- `/ll:refine-issue` - 2026-03-03 - Batch re-assessment: no new knowledge gaps; still blocked by ENH-481
- `/ll:refine-issue` - 2026-03-03 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/d68fadcc-ae9f-4d69-99b8-1fe3b0ecb23f.jsonl` - Fresh codebase research: added Integration Map with 5 callers (exact file:line), complete 16-name __init__.py re-export list, missing CLI migration steps (pyproject.toml:59, cli/__init__.py), module-level constants placement note, test split naming convention, removed stale ENH-481 blocker (completed 2026-02-25)
- `/ll:manage-issue` - 2026-03-03 - Implementation: split dependency_mapper.py into 4 focused sub-modules + cli/deps.py; all tests pass (3099), ruff clean, mypy clean

## Blocked By

None — ENH-481 was completed 2026-02-25 (hardcoded category lists replaced with config-driven values; `gather_all_issue_ids` updated to accept `config: BRConfig | None = None`).

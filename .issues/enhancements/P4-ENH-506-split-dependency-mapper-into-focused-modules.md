---
discovered_commit: 5d6419bad2fa3174b9f2c4062ef912bba5205e1a
discovered_branch: main
discovered_date: 2026-02-25
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 93
outcome_confidence: 60
---

# ENH-506: Split `dependency_mapper.py` into focused modules

## Summary

Architectural issue found by `/ll:audit-architecture`. `dependency_mapper.py` is 1,337 lines and handles five distinct concerns in a single module: data models, conflict analysis, dependency validation, fix operations, and CLI entry point.

## Location

- **File**: `scripts/little_loops/dependency_mapper.py`
- **Line(s)**: 1–1,337 (entire file)
- **Module**: `little_loops.dependency_mapper`

## Finding

### Current State

`dependency_mapper.py` conflates five responsibilities:

1. **Data models** (lines 105–188): `DependencyProposal`, `ParallelSafePair`, `ValidationResult`, `DependencyReport`
2. **Analysis functions** (lines 189–520): `_extract_semantic_targets`, `compute_conflict_score`, `find_file_overlaps`, `validate_dependencies`, `analyze_dependencies`
3. **Formatting/reporting** (lines 552–743): `format_report`, `format_text_graph`
4. **Fix operations** (lines 744–1000): `apply_proposals`, `_add_to_section`, `_remove_from_section`, `fix_dependencies`, `gather_all_issue_ids`, `_load_issues`
5. **CLI entry** (lines 1057–end): `main()`

The module is imported by `cli/sprint/edit.py`, `cli/sprint/manage.py`, `cli/sprint/run.py`, `cli/sprint/show.py`, and `issue_manager.py` — meaning all consumers depend on the full 1,321-line module regardless of which functionality they need.

```python
# Current: single monolithic import
from little_loops.dependency_mapper import analyze_dependencies, format_report, fix_dependencies
```

### Impact

- **Development velocity**: Large file is slow to navigate; changes in one area risk unintentionally affecting others
- **Maintainability**: Five concerns in one file makes it hard to find and modify specific behavior
- **Testability**: `test_dependency_mapper.py` is already 1,394 lines and tests all concerns together
- **Risk**: `FixResult` class (line 902) is separated from other data models at line 105–188 — likely grew organically

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
2. Move data models (including `FixResult`) to `models.py`
3. Move analysis functions to `analysis.py`
4. Move formatting functions to `formatting.py`
5. Move fix/mutation operations to `operations.py`
6. Update `__init__.py` to re-export all public names for backwards compatibility
7. Update test file to mirror the split (or keep combined — low urgency)
8. Verify all existing imports (`cli/sprint/*.py`, `issue_manager.py`) still resolve

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low (internal refactor with re-exports for backwards compat)
- **Breaking Change**: No (if `__init__.py` re-exports all names)

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: 2026-02-25 | Priority: P4

## Session Log
- `/ll:verify-issues` - 2026-02-25 - Corrected line count: 1,321 → 1,337 (file has grown since issue was created)
- `/ll:refine-issue` - 2026-02-25 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/b0f00b27-06ea-419f-bf8b-cab2ce74db4f.jsonl` - Issue is well-specified with complete module split plan and caller list; no knowledge gaps identified

## Blocked By

- ENH-481

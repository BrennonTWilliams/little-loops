---
discovered_commit: 8c6cf90
discovered_branch: main
discovered_date: 2026-03-19T00:00:00Z
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-819: Split workflow_sequence_analyzer.py into package

## Summary

Architectural issue found by `/ll:audit-architecture`.

`workflow_sequence_analyzer.py` is 1,065 lines containing 5 dataclasses, analysis functions, IO/loading helpers, and a CLI `main()` entry point all in a single root-level module.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 1-1065 (entire file)
- **Module**: `little_loops.workflow_sequence_analyzer`

## Finding

### Current State

The file mixes four concern areas:

1. **Data models** (5 dataclasses): `SessionLink`, `EntityCluster`, `WorkflowBoundary`, `Workflow`, `WorkflowAnalysis`
2. **Analysis functions**: `extract_entities`, `calculate_boundary_weight`, `entity_overlap`, `semantic_similarity`, `_cluster_by_entities`, `_compute_boundaries`, `_detect_workflows`, `analyze_workflows`
3. **IO/loading**: `_load_messages`, `_load_patterns`, `_group_by_session`, `_parse_timestamps`, `_link_sessions`
4. **CLI entry point**: `main()`

### Impact

- **Development velocity**: Contributors must read 1,065 lines to understand any single concern
- **Maintainability**: Model changes, analysis logic, and IO are coupled in one file
- **Risk**: Low runtime risk

## Proposed Solution

Convert to a `workflow_sequence/` package (or similar):

### Suggested Approach

1. Extract dataclasses to `workflow_sequence/models.py`
2. Extract IO/loading functions to `workflow_sequence/io.py`
3. Keep analysis functions in `workflow_sequence/analysis.py`
4. Move CLI `main()` to the package `__init__.py` or a dedicated entry point
5. Update the `ll-workflows` CLI entry point reference in `setup.cfg`/`pyproject.toml`

## Impact Assessment

- **Severity**: Medium
- **Effort**: Medium
- **Risk**: Low — internal refactor, CLI entry point must be updated
- **Breaking Change**: No (if entry point is preserved)

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

---

## Status

**Open** | Created: 2026-03-19 | Priority: P3

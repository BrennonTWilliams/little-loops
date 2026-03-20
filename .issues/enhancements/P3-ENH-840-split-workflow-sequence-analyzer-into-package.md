---
discovered_commit: 8c6cf90
discovered_branch: main
discovered_date: 2026-03-19T00:00:00Z
discovered_by: audit-architecture
focus_area: large-files
confidence_score: 100
outcome_confidence: 71
---

# ENH-840: Split workflow_sequence_analyzer.py into package

## Summary

Architectural issue found by `/ll:audit-architecture`.

`workflow_sequence_analyzer.py` is 1,065 lines containing 5 dataclasses, analysis functions, IO/loading helpers, and a CLI `main()` entry point all in a single root-level module.

## Location

- **File**: `scripts/little_loops/workflow_sequence_analyzer.py`
- **Line(s)**: 1-1065 (entire file)
- **Module**: `little_loops.workflow_sequence_analyzer`

## Current Behavior

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

## Expected Behavior

`workflow_sequence_analyzer.py` is converted to a `workflow_sequence/` package with four focused modules:

- `workflow_sequence/models.py` — 5 dataclasses (`SessionLink`, `EntityCluster`, `WorkflowBoundary`, `Workflow`, `WorkflowAnalysis`)
- `workflow_sequence/io.py` — IO/loading helpers (`_load_messages`, `_load_patterns`, `_group_by_session`, `_parse_timestamps`, `_link_sessions`)
- `workflow_sequence/analysis.py` — analysis functions (`extract_entities`, `calculate_boundary_weight`, `entity_overlap`, `semantic_similarity`, etc.)
- `workflow_sequence/__init__.py` or dedicated entry module — CLI `main()` entry point

Each module is independently readable and testable. The `ll-workflows` CLI entry point is updated and continues to function identically.

## Motivation

This enhancement would:
- **Reduce cognitive load**: Contributors must navigate 1,065 lines to understand any single concern (models, IO, analysis, or CLI)
- **Enable targeted testing**: Isolated modules can be independently tested and mocked without loading the entire monolith
- **Lower maintenance risk**: Model changes, analysis logic, and IO are coupled — a change to one risks unintended side effects in others
- **Improve onboarding**: New contributors can understand the package structure at a glance via module names

## Proposed Solution

Convert to a `workflow_sequence/` package (or similar):

### Suggested Approach

1. Extract dataclasses to `workflow_sequence/models.py`
2. Extract IO/loading functions to `workflow_sequence/io.py`
3. Keep analysis functions in `workflow_sequence/analysis.py`
4. Move CLI `main()` to the package `__init__.py` or a dedicated entry point
5. Update the `ll-workflows` CLI entry point reference in `setup.cfg`/`pyproject.toml`

## Scope Boundaries

- **In scope**: Splitting `workflow_sequence_analyzer.py` into a `workflow_sequence/` package with `models.py`, `io.py`, `analysis.py`, and entry point
- **In scope**: Updating the `ll-workflows` CLI entry point reference in `pyproject.toml`/`setup.cfg`
- **Out of scope**: Changes to analysis logic or function signatures
- **Out of scope**: Renaming any public functions or classes
- **Out of scope**: Adding new functionality or tests beyond what is needed for the refactor

## Integration Map

### Files to Modify
- `scripts/little_loops/workflow_sequence_analyzer.py` — source file to be split into package

### Dependent Files (Callers/Importers)
- `scripts/little_loops/workflow_sequence_analyzer.py:14` — TYPE_CHECKING self-import (`analyze_workflows`); used in CLI docstring example
- `scripts/little_loops/parallel/file_hints.py:16` — comment reference only, not an import

### Similar Patterns
- Other sub-packages in `scripts/little_loops/`: `cli/`, `config/`, `dependency_mapper/`, `fsm/`, `issue_discovery/`, `issue_history/`, `parallel/` — use these as structural reference for package layout

### Tests
- `scripts/tests/test_workflow_sequence_analyzer.py` — primary unit tests
- `scripts/tests/test_workflow_integration.py` — integration tests
- `scripts/tests/test_issue_workflow_integration.py` — issue/workflow integration tests

### Documentation
- `docs/ARCHITECTURE.md:234` — module listed in package tree
- `docs/reference/API.md:42,2997,3005,3149,3179,3316` — module documented with function signatures and usage examples

### Configuration
- `scripts/setup.cfg:55` — `ll-workflows = "little_loops.workflow_sequence_analyzer:main"` (confirmed in setup.cfg, not pyproject.toml)

## Implementation Steps

1. Create `scripts/little_loops/workflow_sequence/` package directory with `__init__.py`
2. Extract 5 dataclasses to `workflow_sequence/models.py`
3. Extract IO/loading functions to `workflow_sequence/io.py`
4. Move analysis functions to `workflow_sequence/analysis.py`
5. Move CLI `main()` to entry point module; update `pyproject.toml`/`setup.cfg` entry point reference
6. Run tests and verify `ll-workflows` CLI continues to function identically

## Impact

- **Priority**: P3 - Medium severity architectural issue; not blocking, improves long-term maintainability
- **Effort**: Medium - Mechanical refactor with predictable scope
- **Risk**: Low — internal refactor, CLI entry point must be updated
- **Breaking Change**: No (if entry point is preserved)

## Verification Notes

**Verdict: VALID** — Verified 2026-03-19

- **File exists**: `scripts/little_loops/workflow_sequence_analyzer.py` confirmed at exactly 1,065 lines ✓
- **Dataclasses (5)**: `SessionLink` (L94), `EntityCluster` (L113), `WorkflowBoundary` (L138), `Workflow` (L162), `WorkflowAnalysis` (L193) — all confirmed ✓
- **Analysis functions**: All listed confirmed (plus unlisted `get_verb_class` L289, `_detect_handoff` L395 as minor omissions)
- **IO/loading functions**: All listed confirmed ✓
- **CLI entry point**: `main()` at L914; registered in `scripts/setup.cfg:55` as `ll-workflows = "little_loops.workflow_sequence_analyzer:main"` ✓
- **No existing package**: `workflow_sequence/` package does not yet exist — issue is still valid ✓
- **Integration Map**: Populated TBDs with verified callers, test files, and documentation references

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Session Log
- `/ll:verify-issues` - 2026-03-19T22:57:06 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:format-issue` - 2026-03-19T22:53:41 - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`
- `/ll:confidence-check` - 2026-03-19T00:00:00Z - `/Users/brennon/.claude/projects/-Users-brennon-AIProjects-brenentech-little-loops/518e3b13-53f5-4aa8-8b52-4d7a72cacfa5.jsonl`

---

## Status

**Open** | Created: 2026-03-19 | Priority: P3

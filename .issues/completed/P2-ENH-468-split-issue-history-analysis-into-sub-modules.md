---
discovered_commit: 896c4ea858eb310d1a187c9f94e9368cf49a4f18
discovered_branch: main
discovered_date: 2026-02-24
discovered_by: audit-architecture
focus_area: large-files
---

# ENH-468: Split issue_history/analysis.py into sub-modules

## Summary

Architectural issue found by `/ll:audit-architecture`. The `analysis.py` module is a procedural mega-module containing 1,785 lines with 19 top-level functions and 0 classes, handling multiple distinct analysis responsibilities.

## Current Behavior

The module `scripts/little_loops/issue_history/analysis.py` (1,785 lines) contains 19 top-level functions covering at least 6 distinct analysis domains:
- Summary/period statistics (`calculate_summary`, `_group_by_period`, `_calculate_trend`, `_analyze_subsystems`)
- Hotspot detection (`analyze_hotspots`)
- Coupling analysis (`analyze_coupling`, `_build_coupling_clusters`)
- Regression clustering (`analyze_regression_clustering`)
- Test gap / rejection / manual pattern analysis
- Technical debt metrics, complexity proxy, cross-cutting concern detection

All functions operate on `CompletedIssue` and return typed analysis dataclasses from `models.py`.

## Expected Behavior

The analysis logic is split into focused sub-modules within the `issue_history/` package, each handling a single analysis domain. Each sub-module is independently navigable and testable. The public API remains unchanged via re-exports from `__init__.py`.

## Motivation

This enhancement would:
- Improve development velocity: currently hard to locate specific analysis logic in 1,785 lines of procedural code
- Reduce maintenance risk: changes to one analysis domain can cause unintended side effects in unrelated analyses
- Improve code clarity: module-level organization replaces a flat list of 19 functions

## Proposed Solution

Split `analysis.py` into sub-modules grouped by analysis domain within the `issue_history/` package:

1. Create `issue_history/summary.py` — period metrics, summary statistics, subsystem health
2. Create `issue_history/hotspots.py` — hotspot detection and analysis
3. Create `issue_history/coupling.py` — coupling pairs and cluster analysis
4. Create `issue_history/regressions.py` — regression clustering
5. Create `issue_history/quality.py` — test gaps, rejections, manual patterns, config gaps
6. Create `issue_history/debt.py` — technical debt, complexity proxy, cross-cutting concerns, agent effectiveness
7. Update `issue_history/__init__.py` to re-export from sub-modules
8. Keep `analysis.py` as a thin facade with `analyze_all()` if needed

## Scope Boundaries

- **In scope**: Moving existing functions into sub-modules; updating imports; re-exporting from `__init__.py`
- **Out of scope**: Refactoring function internals, adding new analysis features, changing function signatures, adding classes to wrap existing functions

## Implementation Steps

1. Identify function groupings by analysis domain (summary, hotspots, coupling, regressions, quality, debt)
2. Create sub-module files and move functions to their respective modules
3. Update internal imports between relocated functions
4. Update `issue_history/__init__.py` to re-export all public functions
5. Update all external callers to use the re-exported imports
6. Run tests to verify no breakage

## Integration Map

### Files to Modify
- `scripts/little_loops/issue_history/analysis.py` — split into sub-modules
- `scripts/little_loops/issue_history/__init__.py` — update re-exports

### Dependent Files (Callers/Importers)
- `scripts/little_loops/issue_history/__init__.py` — sole direct importer of `analysis.py`; re-exports all public functions (lines 59-72). All external callers go through `__init__.py`.

### Similar Patterns
- `cli/loop/` package — already uses sub-module pattern for CLI commands

### Tests
- `scripts/tests/test_issue_history_analysis.py` — tests analysis functions (imports via `__init__.py`)
- `scripts/tests/test_issue_history_advanced_analytics.py` — tests advanced analytics functions
- `scripts/tests/test_issue_history_summary.py` — tests summary/period metrics functions
- `scripts/tests/test_cli.py` — CLI integration tests that import from `issue_history` (lines 2395-2527)

### Documentation
- N/A

### Configuration
- N/A

## Impact

- **Priority**: P2 — High maintenance burden from 1,785-line single file
- **Effort**: Medium — Pure functions are easy to relocate
- **Risk**: Low — Move functions + update imports; public API unchanged via re-exports
- **Breaking Change**: No

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`

## Resolution

**Action**: completed
**Date**: 2026-02-24
**Summary**: Split 1,785-line `analysis.py` into 6 focused sub-modules (`summary.py`, `hotspots.py`, `coupling.py`, `regressions.py`, `quality.py`, `debt.py`). Updated `analysis.py` as a thin facade containing only `_load_issue_contents` and `calculate_analysis`. Updated `__init__.py` to import from individual sub-modules. Public API unchanged. 300 tests pass, ruff and mypy clean.

**Files Created**:
- `scripts/little_loops/issue_history/summary.py`
- `scripts/little_loops/issue_history/hotspots.py`
- `scripts/little_loops/issue_history/coupling.py`
- `scripts/little_loops/issue_history/regressions.py`
- `scripts/little_loops/issue_history/quality.py`
- `scripts/little_loops/issue_history/debt.py`

**Files Modified**:
- `scripts/little_loops/issue_history/analysis.py` (thin facade, ~180 lines)
- `scripts/little_loops/issue_history/__init__.py` (imports from sub-modules)

## Session Log
- `/ll:format-issue` - 2026-02-24 - auto-format batch
- `/ll:manage-issue enhancement refactor ENH-468` - 2026-02-24 - implemented refactor

---

## Status

**Completed** | Created: 2026-02-24 | Completed: 2026-02-24 | Priority: P2

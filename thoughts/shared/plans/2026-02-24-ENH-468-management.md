# ENH-468: Split issue_history/analysis.py into Sub-Modules

**Date**: 2026-02-24
**Status**: COMPLETED

## Problem

`scripts/little_loops/issue_history/analysis.py` was a 1,785-line procedural mega-module with 19 top-level functions covering 6+ distinct analysis domains, making it difficult to navigate and maintain.

## Solution

Split into 6 focused sub-modules within the `issue_history/` package:

| Sub-module | Functions | Lines (approx) |
|---|---|---|
| `summary.py` | `calculate_summary`, `_calculate_period_label`, `_group_by_period`, `_calculate_trend`, `_analyze_subsystems` | ~200 |
| `hotspots.py` | `analyze_hotspots` | ~120 |
| `coupling.py` | `analyze_coupling`, `_build_coupling_clusters` | ~150 |
| `regressions.py` | `analyze_regression_clustering` | ~130 |
| `quality.py` | `analyze_test_gaps`, `analyze_rejection_rates`, `detect_manual_patterns`, `detect_config_gaps` + constants | ~350 |
| `debt.py` | `detect_cross_cutting_smells`, `analyze_agent_effectiveness`, `analyze_complexity_proxy`, `_calculate_debt_metrics` + constants | ~330 |
| `analysis.py` (thin facade) | `_load_issue_contents`, `calculate_analysis` | ~180 |

## Key Decisions

- **No API changes**: All 12 public functions remain accessible via `issue_history.__init__` re-exports
- **`__init__.py` updated**: Now imports from individual sub-modules instead of the monolithic `analysis.py`
- **Thin facade**: `analysis.py` retained as orchestrator, importing domain functions from sub-modules
- **Constants co-located**: `_MANUAL_PATTERNS`, `_PATTERN_TO_CONFIG` → `quality.py`; `_CROSS_CUTTING_KEYWORDS`, `_CONCERN_PATTERNS` → `debt.py`

## Verification

- 300 tests pass (test_issue_history_analysis, test_issue_history_advanced_analytics, test_issue_history_summary, test_cli)
- `ruff check` clean
- `mypy` clean (11 source files)

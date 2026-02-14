# ENH-390: Split issue_history.py into issue_history/ package

## Plan Date: 2026-02-14

## Issue Summary

Split the 3,824-line `issue_history.py` god module into an `issue_history/` package with focused submodules: models, parsing, analysis, and formatting.

## Research Findings

### Current Structure
- `scripts/little_loops/issue_history.py`: 3,824 lines, 26 dataclasses, 35 functions, 4 module constants
- Natural groupings confirmed: models (lines 77-797), parsing (lines 799-1003 + 1110-1225 + 2466-2507), analysis (lines 1006-1047 + 1228-2869), formatting (lines 1050-1102 + 2877-3824)

### Dependency Hierarchy
```
models.py       → stdlib only
parsing.py      → models.py + little_loops.frontmatter
analysis.py     → models.py + parsing.py
formatting.py   → models.py only
```

### Dependent Files (no changes needed - __init__.py re-exports preserve compatibility)
- `scripts/little_loops/cli/history.py` - lazy import inside function
- `scripts/tests/test_issue_history_parsing.py` - `from little_loops.issue_history import ...`
- `scripts/tests/test_issue_history_analysis.py` - `from little_loops.issue_history import ...`
- `scripts/tests/test_issue_history_summary.py` - `from little_loops.issue_history import ...`
- `scripts/tests/test_issue_history_advanced_analytics.py` - `from little_loops.issue_history import ...`
- `scripts/tests/test_cli.py` - both `from little_loops.issue_history import X` and `from little_loops import issue_history` (12 sites)
- `scripts/tests/test_issue_history_cli.py`

### Prior Art
- `cli.py` → `cli/` package (ENH-344): same pattern, successful
- `fsm/`, `parallel/` packages: established conventions for `__init__.py` re-exports

## Implementation Plan

### Phase 1: Create Package Structure
- [ ] Create `scripts/little_loops/issue_history/` directory
- [ ] Create `__init__.py` with full re-export of public API (matching existing `__all__`)

### Phase 2: Extract models.py
- [ ] Extract lines 77-797 (all 26 dataclasses) to `issue_history/models.py`
- [ ] Add imports: `from __future__ import annotations`, `dataclasses`, `datetime`, `pathlib`, `typing`
- [ ] No internal dependencies (only stdlib)

### Phase 3: Extract parsing.py
- [ ] Extract parsing functions to `issue_history/parsing.py`:
  - `parse_completed_issue` (804-847)
  - `_parse_discovered_by` (850-861)
  - `_parse_completion_date` (864-887)
  - `_parse_resolution_action` (890-932)
  - `_detect_processing_agent` (935-978)
  - `scan_completed_issues` (981-1003)
  - `_parse_discovered_date` (1110-1126)
  - `_extract_subsystem` (1129-1149)
  - `_extract_paths_from_issue` (1152-1178)
  - `_find_test_file` (1181-1225)
  - `scan_active_issues` (2466-2507)
- [ ] Add imports from `.models` and `little_loops.frontmatter`

### Phase 4: Extract analysis.py
- [ ] Extract analysis functions to `issue_history/analysis.py`:
  - `calculate_summary` (1006-1047)
  - `_calculate_period_label` (1228-1245)
  - `_group_by_period` (1248-1331)
  - `_calculate_trend` (1334-1369)
  - `_analyze_subsystems` (1372-1419)
  - `analyze_hotspots` (1422-1530)
  - `analyze_coupling` (1533-1607)
  - `_build_coupling_clusters` (1610-1656)
  - `analyze_regression_clustering` (1659-1779)
  - `analyze_test_gaps` (1782-1875)
  - `analyze_rejection_rates` (1878-1981)
  - Module constants: `_MANUAL_PATTERNS` (1984-2030), `_CROSS_CUTTING_KEYWORDS` (2032-2039), `_CONCERN_PATTERNS` (2042-2048)
  - `detect_manual_patterns` (2051-2126)
  - `detect_cross_cutting_smells` (2129-2223)
  - Module constant: `_PATTERN_TO_CONFIG` (2227-2280)
  - `detect_config_gaps` (2283-2376)
  - `analyze_agent_effectiveness` (2379-2463)
  - `analyze_complexity_proxy` (2510-2660)
  - `_calculate_debt_metrics` (2663-2717)
  - `calculate_analysis` (2720-2869)
- [ ] Add imports from `.models` and `.parsing`

### Phase 5: Extract formatting.py
- [ ] Extract formatting functions to `issue_history/formatting.py`:
  - `format_summary_text` (1050-1102)
  - `format_summary_json` (1093-1102)
  - `format_analysis_json` (2877-2886)
  - `format_analysis_yaml` (2889-2906)
  - `format_analysis_text` (2907-3342)
  - `format_analysis_markdown` (3343-3824)
- [ ] Add imports from `.models`

### Phase 6: Wire __init__.py
- [ ] Import and re-export all public names from submodules
- [ ] Include `__all__` matching the original module's `__all__`
- [ ] Follow established pattern from `cli/__init__.py` and `fsm/__init__.py`

### Phase 7: Delete Original
- [ ] `git rm scripts/little_loops/issue_history.py`

### Phase 8: Verify
- [ ] Run `python -m pytest scripts/tests/test_issue_history*.py scripts/tests/test_cli.py -v`
- [ ] Run `ruff check scripts/little_loops/issue_history/`
- [ ] Run `python -m mypy scripts/little_loops/issue_history/`

## Success Criteria
- [ ] All existing imports continue to work (no external changes needed)
- [ ] All tests pass
- [ ] Type checking passes
- [ ] Linting passes
- [ ] Each submodule is <1200 lines
- [ ] `from little_loops.issue_history import X` works for all public names
- [ ] `from little_loops import issue_history; issue_history.X` works for patching in tests

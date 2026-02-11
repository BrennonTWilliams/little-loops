---
discovered_commit: 51dcccd702a7f8947c624a914f353b8ec65cf55f
discovered_branch: main
discovered_date: 2026-02-10
discovered_by: audit_architecture
focus_area: large-files
---

# ENH-310: Split issue_history.py into issue_history/ package

## Summary

Architectural issue found by `/ll:audit_architecture`. The issue_history.py module is a god module containing 3,824 lines with 61 classes and functions, handling multiple distinct responsibilities.

## Location

- **File**: `scripts/little_loops/issue_history.py`
- **Lines**: 1-3824 (entire file)
- **Module**: `little_loops.issue_history`

## Finding

### Current State

issue_history.py contains 61 classes and functions with multiple responsibilities:

**Data Models** (21+ dataclasses):
- CompletedIssue, HistorySummary, PeriodMetrics, SubsystemHealth
- Hotspot, HotspotAnalysis, CouplingPair, CouplingAnalysis
- RegressionCluster, RegressionAnalysis, TestGap, TestGapAnalysis
- RejectionMetrics, RejectionAnalysis, ManualPattern, ManualPatternAnalysis
- ConfigGap, ConfigGapsAnalysis, AgentOutcome, AgentEffectivenessAnalysis
- TechnicalDebtMetrics, ComplexityProxy, ComplexityProxyAnalysis
- CrossCuttingSmell, CrossCuttingAnalysis, HistoryAnalysis

**Parsing Functions**:
- parse_completed_issue, scan_completed_issues, scan_active_issues
- _parse_discovered_by, _parse_completion_date, _parse_resolution_action

**Analysis Functions**:
- calculate_summary, calculate_analysis
- analyze_hotspots, analyze_regression_clustering, analyze_test_gaps
- analyze_rejection_rates, detect_manual_patterns, detect_config_gaps
- analyze_agent_effectiveness, analyze_complexity_proxy, detect_cross_cutting_smells

**Formatting Functions**:
- format_summary_text, format_summary_json
- format_analysis_text, format_analysis_json, format_analysis_markdown, format_analysis_yaml

This violates the Single Responsibility Principle and makes the module extremely difficult to maintain.

### Impact

- **Development velocity**: Hard to navigate and find specific functionality
- **Maintainability**: Changes to one area can affect others
- **Testability**: test_issue_history_advanced_analytics.py is 2,601 lines (also too large)
- **Risk**: Medium - Affects all history analysis features

## Proposed Solution

Split issue_history.py into an issue_history/ package with focused modules:

```
issue_history/
├── __init__.py (exports all public APIs)
├── models.py (all dataclasses)
├── parsing.py (parse_completed_issue, scan functions, _parse_* helpers)
├── analysis.py (all analyze_* and calculate_* functions)
└── formatting.py (all format_* functions)
```

### Suggested Approach

1. **Create issue_history/ package directory**
   ```bash
   mkdir scripts/little_loops/issue_history
   ```

2. **Extract data models to models.py**
   - Move all 21+ dataclasses (CompletedIssue, HistorySummary, etc.)
   - Keep dataclass dependencies together
   - Ensure proper imports for `Path`, `date`, etc.

3. **Extract parsing to parsing.py**
   - Move parse_completed_issue, scan_completed_issues, scan_active_issues
   - Move all _parse_* helper functions
   - Import models from `.models`

4. **Extract analysis to analysis.py**
   - Move calculate_summary, calculate_analysis
   - Move all analyze_* functions (analyze_hotspots, etc.)
   - Move all detect_* functions
   - Import models from `.models`
   - Import parsing functions from `.parsing`

5. **Extract formatting to formatting.py**
   - Move all format_* functions
   - Import models from `.models`

6. **Create issue_history/__init__.py with public API**
   ```python
   """Issue history analysis and summary statistics."""

   from little_loops.issue_history.analysis import (
       analyze_agent_effectiveness,
       analyze_complexity_proxy,
       analyze_hotspots,
       analyze_rejection_rates,
       analyze_regression_clustering,
       analyze_test_gaps,
       calculate_analysis,
       calculate_summary,
       detect_config_gaps,
       detect_cross_cutting_smells,
       detect_manual_patterns,
   )
   from little_loops.issue_history.formatting import (
       format_analysis_json,
       format_analysis_markdown,
       format_analysis_text,
       format_analysis_yaml,
       format_summary_json,
       format_summary_text,
   )
   from little_loops.issue_history.models import (
       AgentEffectivenessAnalysis,
       AgentOutcome,
       CompletedIssue,
       ComplexityProxy,
       ComplexityProxyAnalysis,
       ConfigGap,
       ConfigGapsAnalysis,
       CouplingAnalysis,
       CouplingPair,
       CrossCuttingAnalysis,
       CrossCuttingSmell,
       HistoryAnalysis,
       HistorySummary,
       Hotspot,
       HotspotAnalysis,
       ManualPattern,
       ManualPatternAnalysis,
       PeriodMetrics,
       RegressionAnalysis,
       RegressionCluster,
       RejectionAnalysis,
       RejectionMetrics,
       SubsystemHealth,
       TechnicalDebtMetrics,
       TestGap,
       TestGapAnalysis,
   )
   from little_loops.issue_history.parsing import (
       parse_completed_issue,
       scan_active_issues,
       scan_completed_issues,
   )

   __all__ = [
       # Models
       "CompletedIssue",
       "HistorySummary",
       "PeriodMetrics",
       # ... (all models)
       # Parsing
       "parse_completed_issue",
       "scan_completed_issues",
       "scan_active_issues",
       # Analysis
       "calculate_summary",
       "calculate_analysis",
       # ... (all analysis functions)
       # Formatting
       "format_summary_text",
       "format_summary_json",
       # ... (all formatting functions)
   ]
   ```

7. **Update imports in other modules**
   - Update `from little_loops.issue_history import` statements
   - Most should continue working via __init__.py exports

8. **Split test file**
   - Optionally split test_issue_history_advanced_analytics.py into:
     - test_issue_history_models.py
     - test_issue_history_parsing.py
     - test_issue_history_analysis.py
     - test_issue_history_formatting.py

9. **Run tests**
   ```bash
   python -m pytest scripts/tests/test_issue_history*.py -v
   ```

10. **Delete original issue_history.py**
    ```bash
    git rm scripts/little_loops/issue_history.py
    ```

## Impact Assessment

- **Severity**: High - Maintainability issue affecting all history analysis
- **Effort**: Medium - Requires careful separation of concerns and dependency management
- **Risk**: Low - Public API can remain unchanged via __init__.py
- **Breaking Change**: No - Public API preserved via issue_history/__init__.py

## Benefits

1. **Dramatically improved maintainability** - Each module has a single responsibility
2. **Better code navigation** - Easy to find models, parsing, analysis, or formatting
3. **Easier testing** - Tests can be organized by module
4. **Reduced cognitive load** - Developers work with ~1000 line files instead of 3800
5. **Better git history** - Changes isolated to specific concerns

## Labels

`enhancement`, `architecture`, `refactoring`, `auto-generated`, `god-module`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P2

---

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID
- issue_history.py is exactly 3,824 lines (matches reported size)
- issue_history/ package does not exist yet — refactoring not started
- All 61 classes/functions remain in single file

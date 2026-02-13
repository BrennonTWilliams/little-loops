---
discovered_commit: 51dcccd702a7f8947c624a914f353b8ec65cf55f
discovered_branch: main
discovered_date: 2026-02-10
discovered_by: audit_architecture
focus_area: patterns
---

# FEAT-002: Extract formatting strategies from issue_history

## Summary

Architectural improvement found by `/ll:audit_architecture`. Extract formatting logic into strategy classes to improve extensibility for new output formats.

## Location

- **Current**: `scripts/little_loops/issue_history.py` (after ENH-390: `issue_history/formatting.py`)
- **New files**: `scripts/little_loops/issue_history/formatters/`
- **Module**: `little_loops.issue_history`

## Motivation

### Current State

Formatting functions are implemented as standalone functions:
- `format_summary_text()`
- `format_summary_json()`
- `format_analysis_text()`
- `format_analysis_json()`
- `format_analysis_markdown()`
- `format_analysis_yaml()`

Adding new output formats (e.g., HTML, CSV, XML) requires:
1. Adding a new function to formatting.py
2. Updating imports and __all__
3. Adding conditionals in calling code

This approach doesn't scale well and makes it hard to:
- Add custom formatters via plugins
- Test formatters independently
- Compose formatters (e.g., JSON → HTML wrapper)

### Proposed State

Use the Strategy pattern to encapsulate formatting logic in classes, enabling:
- Easy addition of new formats
- Plugin-based custom formatters
- Composition and decoration
- Better testability

## Proposed Solution

### 1. Create Formatter Protocol

```python
# scripts/little_loops/issue_history/formatters/base.py
"""Base formatter protocol and utilities."""

from typing import Protocol, runtime_checkable

from little_loops.issue_history.models import HistorySummary, HistoryAnalysis


@runtime_checkable
class SummaryFormatter(Protocol):
    """Protocol for history summary formatters."""

    def format(self, summary: HistorySummary) -> str:
        """Format a history summary.

        Args:
            summary: The summary to format

        Returns:
            Formatted string representation
        """
        ...

    @property
    def format_name(self) -> str:
        """Return the format name (e.g., 'json', 'text', 'markdown')."""
        ...


@runtime_checkable
class AnalysisFormatter(Protocol):
    """Protocol for history analysis formatters."""

    def format(self, analysis: HistoryAnalysis) -> str:
        """Format a history analysis.

        Args:
            analysis: The analysis to format

        Returns:
            Formatted string representation
        """
        ...

    @property
    def format_name(self) -> str:
        """Return the format name (e.g., 'json', 'text', 'markdown', 'yaml')."""
        ...
```

### 2. Implement Concrete Formatters

```python
# scripts/little_loops/issue_history/formatters/text.py
"""Text formatters for summaries and analysis."""

from little_loops.issue_history.formatters.base import (
    SummaryFormatter,
    AnalysisFormatter,
)
from little_loops.issue_history.models import HistorySummary, HistoryAnalysis


class TextSummaryFormatter(SummaryFormatter):
    """Format summary as human-readable text."""

    @property
    def format_name(self) -> str:
        return "text"

    def format(self, summary: HistorySummary) -> str:
        # Implementation from current format_summary_text
        ...


class TextAnalysisFormatter(AnalysisFormatter):
    """Format analysis as human-readable text."""

    @property
    def format_name(self) -> str:
        return "text"

    def format(self, analysis: HistoryAnalysis) -> str:
        # Implementation from current format_analysis_text
        ...
```

```python
# scripts/little_loops/issue_history/formatters/json.py
"""JSON formatters for summaries and analysis."""

import json

from little_loops.issue_history.formatters.base import (
    SummaryFormatter,
    AnalysisFormatter,
)
from little_loops.issue_history.models import HistorySummary, HistoryAnalysis


class JsonSummaryFormatter(SummaryFormatter):
    """Format summary as JSON."""

    def __init__(self, indent: int = 2) -> None:
        self.indent = indent

    @property
    def format_name(self) -> str:
        return "json"

    def format(self, summary: HistorySummary) -> str:
        # Implementation from current format_summary_json
        ...


class JsonAnalysisFormatter(AnalysisFormatter):
    """Format analysis as JSON."""

    def __init__(self, indent: int = 2) -> None:
        self.indent = indent

    @property
    def format_name(self) -> str:
        return "json"

    def format(self, analysis: HistoryAnalysis) -> str:
        # Implementation from current format_analysis_json
        ...
```

### 3. Create Formatter Registry

```python
# scripts/little_loops/issue_history/formatters/registry.py
"""Formatter registration and discovery."""

from typing import Type

from little_loops.issue_history.formatters.base import (
    SummaryFormatter,
    AnalysisFormatter,
)

_SUMMARY_FORMATTERS: dict[str, Type[SummaryFormatter]] = {}
_ANALYSIS_FORMATTERS: dict[str, Type[AnalysisFormatter]] = {}


def register_summary_formatter(formatter_class: Type[SummaryFormatter]) -> None:
    """Register a summary formatter."""
    formatter = formatter_class()
    _SUMMARY_FORMATTERS[formatter.format_name] = formatter_class


def register_analysis_formatter(formatter_class: Type[AnalysisFormatter]) -> None:
    """Register an analysis formatter."""
    formatter = formatter_class()
    _ANALYSIS_FORMATTERS[formatter.format_name] = formatter_class


def get_summary_formatter(format_name: str) -> SummaryFormatter:
    """Get a summary formatter by name."""
    formatter_class = _SUMMARY_FORMATTERS.get(format_name)
    if formatter_class is None:
        raise ValueError(f"Unknown format: {format_name}")
    return formatter_class()


def get_analysis_formatter(format_name: str) -> AnalysisFormatter:
    """Get an analysis formatter by name."""
    formatter_class = _ANALYSIS_FORMATTERS.get(format_name)
    if formatter_class is None:
        raise ValueError(f"Unknown format: {format_name}")
    return formatter_class()


# Auto-register built-in formatters
from little_loops.issue_history.formatters.text import (
    TextSummaryFormatter,
    TextAnalysisFormatter,
)
from little_loops.issue_history.formatters.json import (
    JsonSummaryFormatter,
    JsonAnalysisFormatter,
)
# ... other formatters

register_summary_formatter(TextSummaryFormatter)
register_summary_formatter(JsonSummaryFormatter)
register_analysis_formatter(TextAnalysisFormatter)
register_analysis_formatter(JsonAnalysisFormatter)
# ... other formatters
```

### 4. Maintain Backward Compatibility

```python
# scripts/little_loops/issue_history/formatting.py (after ENH-390)
"""Formatting functions for history summaries and analysis.

This module provides backward-compatible function-based API
while delegating to the new strategy-based formatters.
"""

from little_loops.issue_history.formatters.registry import (
    get_summary_formatter,
    get_analysis_formatter,
)
from little_loops.issue_history.models import HistorySummary, HistoryAnalysis


def format_summary_text(summary: HistorySummary) -> str:
    """Format summary as text (backward compatible)."""
    return get_summary_formatter("text").format(summary)


def format_summary_json(summary: HistorySummary) -> str:
    """Format summary as JSON (backward compatible)."""
    return get_summary_formatter("json").format(summary)


# ... other functions
```

## Implementation Steps

1. **Create formatters/base.py with protocols** (after ENH-390)
2. **Extract text formatters** (text.py)
3. **Extract JSON formatters** (json.py)
4. **Extract markdown formatter** (markdown.py)
5. **Extract YAML formatter** (yaml.py)
6. **Create formatter registry** (registry.py)
7. **Update formatting.py** to delegate to registry
8. **Add tests** for each formatter
9. **Update documentation** with formatter plugin guide

## Impact Assessment

- **Severity**: Low - Improves extensibility, no functional change
- **Effort**: Small - Extract existing logic into strategy classes
- **Risk**: Low - Can maintain backward compatibility with function-based API
- **Breaking Change**: No - Existing functions preserved as wrappers

## Benefits

1. **Easy to add formats** - Create new class, register it
2. **Plugin support** - Third parties can add custom formatters
3. **Better testability** - Test formatters in isolation
4. **Composition** - Combine formatters (e.g., JSON → pretty HTML)
5. **Configuration** - Formatters can accept options (indent, colors, etc.)

## Future Enhancements

After this feature:
- Add HTML formatter for web dashboards
- Add CSV formatter for spreadsheet import
- Add configurable formatting options (colors, verbosity)
- Add formatter composition/decoration

## Dependencies

- **Blocks**: None
- **Blocked by**: ENH-390 (should split issue_history.py first for cleaner structure)

## Labels

`feature`, `architecture`, `extensibility`, `auto-generated`, `design-pattern`

---

## Status

**Open** | Created: 2026-02-10 | Priority: P3

---

## Verification Notes

- **Verified**: 2026-02-10
- **Verdict**: VALID
- scripts/little_loops/issue_history/formatters/ directory does not exist
- Formatting functions remain in issue_history.py as standalone functions
- No formatter protocol or registry implemented
- Dependency ENH-390 not yet completed — implementation blocked

---

## Resolution

- **Status**: Closed - Tradeoff Review
- **Completed**: 2026-02-10
- **Reason**: Low utility relative to implementation complexity (premature optimization)

### Tradeoff Review Scores
- Utility: LOW (no current need for additional formats)
- Implementation Effort: MEDIUM (extract 6+ functions, create protocols/registry)
- Complexity Added: MEDIUM (new Strategy pattern, backward compatibility)
- Technical Debt Risk: LOW (well-defined pattern)
- Maintenance Overhead: LOW (set-and-forget)

### Rationale
Current formatting functions work fine; no user demand for additional formats (HTML, CSV, XML mentioned as "future"). This is premature optimization for a hypothetical use case. Also blocked by ENH-390 which is not yet complete.

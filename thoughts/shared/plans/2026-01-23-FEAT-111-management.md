# FEAT-111: Issue History Summary Command - Implementation Plan

## Issue Reference
- **File**: .issues/features/P3-FEAT-111-history-summary-command.md
- **Type**: feature
- **Priority**: P3
- **Action**: implement

## Current State Analysis

The codebase has 116 completed issues in `.issues/completed/` with consistent filename patterns (`P[0-5]-[TYPE]-[NNN]-description.md`) and optional YAML frontmatter containing `discovered_by` metadata.

### Key Discoveries
- CLI entry points defined in `scripts/pyproject.toml:47-54`
- All CLI functions follow pattern in `scripts/little_loops/cli.py` (argparse + return int)
- Existing issue parsing in `scripts/little_loops/issue_parser.py:76-133` (`IssueInfo` dataclass)
- Frontmatter parsing in `scripts/little_loops/issue_parser.py:286-324`
- JSON output pattern in `scripts/little_loops/user_messages.py:249-258`
- Logger utility in `scripts/little_loops/logger.py`

### File Format Observations
- Issues with frontmatter: `discovered_by: audit_docs`, `discovered_by: scan_codebase`, etc.
- Issues without frontmatter exist (older issues)
- Priority extracted from filename prefix (P0-P5)
- Type extracted from filename (BUG, ENH, FEAT)
- Completion date in Resolution section: `**Completed**: YYYY-MM-DD`

## Desired End State

A new `ll-history` CLI command that:
1. Parses all completed issues from `.issues/completed/`
2. Displays summary statistics (type counts, priority distribution, discovery sources)
3. Calculates velocity metrics (issues/day, date range)
4. Outputs as formatted text (default) or JSON (`--json` flag)

### How to Verify
- Run `ll-history summary` to see formatted output
- Run `ll-history summary --json` to get machine-readable output
- Run against empty `.issues/completed/` to verify graceful handling

## What We're NOT Doing

- File hotspot detection (see FEAT-110)
- Quality metrics like test/lint pass rates
- AI-generated insights
- Slash command or skill integration
- Multiple output formats beyond text/JSON

## Solution Approach

Create a new module `scripts/little_loops/issue_history.py` that:
1. Scans `.issues/completed/` for issue files
2. Parses filename for type, priority, issue ID
3. Parses frontmatter for `discovered_by` field
4. Extracts completion date from Resolution section or file mtime
5. Calculates statistics
6. Formats output

Add CLI entry point `ll-history` in `cli.py` and `pyproject.toml`.

## Implementation Phases

### Phase 1: Core Module

#### Overview
Create the `issue_history.py` module with dataclasses and parsing functions.

#### Changes Required

**File**: `scripts/little_loops/issue_history.py`
**Changes**: Create new module

```python
"""Issue history analysis and summary statistics.

Provides analysis of completed issues including:
- Type distribution (BUG, ENH, FEAT)
- Priority distribution (P0-P5)
- Discovery source breakdown
- Completion velocity metrics
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Any


@dataclass
class CompletedIssue:
    """Parsed information from a completed issue file."""

    path: Path
    issue_type: str  # BUG, ENH, FEAT
    priority: str  # P0-P5
    issue_id: str  # e.g., BUG-001
    discovered_by: str | None = None
    completed_date: date | None = None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "path": str(self.path),
            "issue_type": self.issue_type,
            "priority": self.priority,
            "issue_id": self.issue_id,
            "discovered_by": self.discovered_by,
            "completed_date": self.completed_date.isoformat() if self.completed_date else None,
        }


@dataclass
class HistorySummary:
    """Summary statistics for completed issues."""

    total_count: int
    type_counts: dict[str, int] = field(default_factory=dict)
    priority_counts: dict[str, int] = field(default_factory=dict)
    discovery_counts: dict[str, int] = field(default_factory=dict)
    earliest_date: date | None = None
    latest_date: date | None = None

    @property
    def date_range_days(self) -> int | None:
        """Calculate days between earliest and latest completion."""
        if self.earliest_date and self.latest_date:
            return (self.latest_date - self.earliest_date).days + 1
        return None

    @property
    def velocity(self) -> float | None:
        """Calculate issues per day."""
        if self.date_range_days and self.date_range_days > 0:
            return self.total_count / self.date_range_days
        return None

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "total_count": self.total_count,
            "type_counts": self.type_counts,
            "priority_counts": self.priority_counts,
            "discovery_counts": self.discovery_counts,
            "earliest_date": self.earliest_date.isoformat() if self.earliest_date else None,
            "latest_date": self.latest_date.isoformat() if self.latest_date else None,
            "date_range_days": self.date_range_days,
            "velocity": round(self.velocity, 2) if self.velocity else None,
        }


def parse_completed_issue(file_path: Path) -> CompletedIssue:
    """Parse a completed issue file.

    Args:
        file_path: Path to the issue markdown file

    Returns:
        CompletedIssue with parsed metadata
    """
    filename = file_path.name
    content = file_path.read_text(encoding="utf-8")

    # Extract from filename: P[0-5]-[TYPE]-[NNN]-description.md
    issue_type = "UNKNOWN"
    priority = "P5"
    issue_id = "UNKNOWN"

    # Match priority
    priority_match = re.match(r"^(P\d)", filename)
    if priority_match:
        priority = priority_match.group(1)

    # Match type and ID
    type_match = re.search(r"(BUG|ENH|FEAT)-(\d+)", filename)
    if type_match:
        issue_type = type_match.group(1)
        issue_id = f"{type_match.group(1)}-{type_match.group(2)}"

    # Parse frontmatter for discovered_by
    discovered_by = _parse_discovered_by(content)

    # Parse completion date from Resolution section or file mtime
    completed_date = _parse_completion_date(content, file_path)

    return CompletedIssue(
        path=file_path,
        issue_type=issue_type,
        priority=priority,
        issue_id=issue_id,
        discovered_by=discovered_by,
        completed_date=completed_date,
    )


def _parse_discovered_by(content: str) -> str | None:
    """Extract discovered_by from YAML frontmatter.

    Args:
        content: File content

    Returns:
        discovered_by value or None
    """
    if not content.startswith("---"):
        return None

    # Find closing ---
    end_match = re.search(r"\n---\s*\n", content[3:])
    if not end_match:
        return None

    frontmatter = content[4 : 3 + end_match.start()]

    for line in frontmatter.split("\n"):
        if line.strip().startswith("discovered_by:"):
            value = line.split(":", 1)[1].strip()
            if value.lower() in ("null", "~", ""):
                return None
            return value

    return None


def _parse_completion_date(content: str, file_path: Path) -> date | None:
    """Extract completion date from Resolution section or file mtime.

    Args:
        content: File content
        file_path: Path for mtime fallback

    Returns:
        Completion date or None
    """
    # Try Resolution section: **Completed**: YYYY-MM-DD
    match = re.search(r"\*\*Completed\*\*:\s*(\d{4}-\d{2}-\d{2})", content)
    if match:
        try:
            return date.fromisoformat(match.group(1))
        except ValueError:
            pass

    # Fallback to file mtime
    try:
        mtime = file_path.stat().st_mtime
        return date.fromtimestamp(mtime)
    except OSError:
        return None


def scan_completed_issues(completed_dir: Path) -> list[CompletedIssue]:
    """Scan completed directory for issue files.

    Args:
        completed_dir: Path to .issues/completed/

    Returns:
        List of parsed CompletedIssue objects
    """
    issues: list[CompletedIssue] = []

    if not completed_dir.exists():
        return issues

    for file_path in sorted(completed_dir.glob("*.md")):
        try:
            issue = parse_completed_issue(file_path)
            issues.append(issue)
        except Exception:
            # Skip unparseable files
            continue

    return issues


def calculate_summary(issues: list[CompletedIssue]) -> HistorySummary:
    """Calculate summary statistics from issues.

    Args:
        issues: List of CompletedIssue objects

    Returns:
        HistorySummary with calculated statistics
    """
    type_counts: dict[str, int] = {}
    priority_counts: dict[str, int] = {}
    discovery_counts: dict[str, int] = {}
    dates: list[date] = []

    for issue in issues:
        # Count by type
        type_counts[issue.issue_type] = type_counts.get(issue.issue_type, 0) + 1

        # Count by priority
        priority_counts[issue.priority] = priority_counts.get(issue.priority, 0) + 1

        # Count by discovery source
        source = issue.discovered_by or "unknown"
        discovery_counts[source] = discovery_counts.get(source, 0) + 1

        # Collect dates
        if issue.completed_date:
            dates.append(issue.completed_date)

    # Sort counts for consistent output
    type_counts = dict(sorted(type_counts.items()))
    priority_counts = dict(sorted(priority_counts.items()))
    discovery_counts = dict(sorted(discovery_counts.items(), key=lambda x: (-x[1], x[0])))

    return HistorySummary(
        total_count=len(issues),
        type_counts=type_counts,
        priority_counts=priority_counts,
        discovery_counts=discovery_counts,
        earliest_date=min(dates) if dates else None,
        latest_date=max(dates) if dates else None,
    )


def format_summary_text(summary: HistorySummary) -> str:
    """Format summary as human-readable text.

    Args:
        summary: HistorySummary to format

    Returns:
        Formatted text string
    """
    lines: list[str] = []

    lines.append("Issue History Summary")
    lines.append("=" * 21)
    lines.append(f"Total Completed: {summary.total_count}")

    if summary.earliest_date and summary.latest_date:
        days = summary.date_range_days or 0
        lines.append(
            f"Date Range: {summary.earliest_date} to {summary.latest_date} ({days} days)"
        )
        if summary.velocity:
            lines.append(f"Velocity: {summary.velocity:.1f} issues/day")

    lines.append("")
    lines.append("By Type:")
    total = summary.total_count or 1
    for issue_type, count in summary.type_counts.items():
        pct = count * 100 // total
        lines.append(f"  {issue_type:5}: {count:3} ({pct:2}%)")

    lines.append("")
    lines.append("By Priority:")
    for priority, count in summary.priority_counts.items():
        pct = count * 100 // total
        lines.append(f"  {priority}:  {count:3} ({pct:2}%)")

    lines.append("")
    lines.append("By Discovery Source:")
    for source, count in summary.discovery_counts.items():
        pct = count * 100 // total
        lines.append(f"  {source:15}: {count:3} ({pct:2}%)")

    return "\n".join(lines)


def format_summary_json(summary: HistorySummary) -> str:
    """Format summary as JSON.

    Args:
        summary: HistorySummary to format

    Returns:
        JSON string
    """
    return json.dumps(summary.to_dict(), indent=2)
```

#### Success Criteria

**Automated Verification**:
- [ ] Module imports without error: `python -c "from little_loops.issue_history import *"`
- [ ] Type checking passes: `python -m mypy scripts/little_loops/issue_history.py`
- [ ] Lint passes: `ruff check scripts/little_loops/issue_history.py`

---

### Phase 2: CLI Entry Point

#### Overview
Add `main_history()` function to `cli.py` and register in `pyproject.toml`.

#### Changes Required

**File**: `scripts/little_loops/cli.py`
**Changes**: Add `main_history()` function (add before final functions, after `main_sprint()`)

```python
def main_history() -> int:
    """Entry point for ll-history command.

    Display summary statistics for completed issues.

    Returns:
        Exit code (0 = success)
    """
    from little_loops.issue_history import (
        calculate_summary,
        format_summary_json,
        format_summary_text,
        scan_completed_issues,
    )

    parser = argparse.ArgumentParser(
        prog="ll-history",
        description="Display summary statistics for completed issues",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  %(prog)s summary              # Show summary statistics
  %(prog)s summary --json       # Output as JSON
  %(prog)s summary -d /path     # Custom issues directory
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="Available commands")

    # summary subcommand
    summary_parser = subparsers.add_parser("summary", help="Show issue statistics")
    summary_parser.add_argument(
        "--json",
        action="store_true",
        help="Output as JSON instead of formatted text",
    )
    summary_parser.add_argument(
        "-d",
        "--directory",
        type=Path,
        default=None,
        help="Path to issues directory (default: .issues)",
    )

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        return 1

    if args.command == "summary":
        # Determine completed directory
        issues_dir = args.directory or Path.cwd() / ".issues"
        completed_dir = issues_dir / "completed"

        # Scan and calculate
        issues = scan_completed_issues(completed_dir)
        summary = calculate_summary(issues)

        # Output
        if args.json:
            print(format_summary_json(summary))
        else:
            print(format_summary_text(summary))

        return 0

    return 1
```

**File**: `scripts/pyproject.toml`
**Changes**: Add ll-history entry point to `[project.scripts]` section

Add this line after the existing entries:
```toml
ll-history = "little_loops.cli:main_history"
```

#### Success Criteria

**Automated Verification**:
- [ ] Lint passes: `ruff check scripts/little_loops/cli.py`
- [ ] Type checking passes: `python -m mypy scripts/little_loops/cli.py`
- [ ] Entry point registers: `pip install -e "./scripts" && ll-history --help`

---

### Phase 3: Tests

#### Overview
Add comprehensive tests for the new module.

#### Changes Required

**File**: `scripts/tests/test_issue_history.py`
**Changes**: Create new test file

```python
"""Tests for issue_history module."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import date
from pathlib import Path
from typing import TYPE_CHECKING
from unittest.mock import patch

import pytest

from little_loops.issue_history import (
    CompletedIssue,
    HistorySummary,
    calculate_summary,
    format_summary_json,
    format_summary_text,
    parse_completed_issue,
    scan_completed_issues,
)

if TYPE_CHECKING:
    from collections.abc import Generator


class TestCompletedIssue:
    """Tests for CompletedIssue dataclass."""

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        issue = CompletedIssue(
            path=Path("/test/P1-BUG-001-test.md"),
            issue_type="BUG",
            priority="P1",
            issue_id="BUG-001",
            discovered_by="scan_codebase",
            completed_date=date(2026, 1, 15),
        )
        result = issue.to_dict()

        assert result["path"] == "/test/P1-BUG-001-test.md"
        assert result["issue_type"] == "BUG"
        assert result["priority"] == "P1"
        assert result["issue_id"] == "BUG-001"
        assert result["discovered_by"] == "scan_codebase"
        assert result["completed_date"] == "2026-01-15"

    def test_to_dict_none_values(self) -> None:
        """Test to_dict with None values."""
        issue = CompletedIssue(
            path=Path("/test/P2-ENH-002-test.md"),
            issue_type="ENH",
            priority="P2",
            issue_id="ENH-002",
        )
        result = issue.to_dict()

        assert result["discovered_by"] is None
        assert result["completed_date"] is None


class TestHistorySummary:
    """Tests for HistorySummary dataclass."""

    def test_date_range_days(self) -> None:
        """Test date range calculation."""
        summary = HistorySummary(
            total_count=10,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 10),
        )
        assert summary.date_range_days == 10

    def test_date_range_days_none(self) -> None:
        """Test date range with missing dates."""
        summary = HistorySummary(total_count=10)
        assert summary.date_range_days is None

    def test_velocity(self) -> None:
        """Test velocity calculation."""
        summary = HistorySummary(
            total_count=20,
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 10),
        )
        assert summary.velocity == 2.0

    def test_velocity_none(self) -> None:
        """Test velocity with missing dates."""
        summary = HistorySummary(total_count=10)
        assert summary.velocity is None

    def test_to_dict(self) -> None:
        """Test to_dict serialization."""
        summary = HistorySummary(
            total_count=5,
            type_counts={"BUG": 3, "ENH": 2},
            priority_counts={"P1": 2, "P2": 3},
            discovery_counts={"manual": 5},
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 5),
        )
        result = summary.to_dict()

        assert result["total_count"] == 5
        assert result["type_counts"] == {"BUG": 3, "ENH": 2}
        assert result["date_range_days"] == 5
        assert result["velocity"] == 1.0


class TestParseCompletedIssue:
    """Tests for parse_completed_issue function."""

    def test_parse_with_frontmatter(self, tmp_path: Path) -> None:
        """Test parsing issue with frontmatter."""
        issue_file = tmp_path / "P1-BUG-042-test-issue.md"
        issue_file.write_text(
            """---
discovered_by: scan_codebase
---

# BUG-042: Test Issue

## Resolution

- **Completed**: 2026-01-15
"""
        )

        issue = parse_completed_issue(issue_file)

        assert issue.issue_type == "BUG"
        assert issue.priority == "P1"
        assert issue.issue_id == "BUG-042"
        assert issue.discovered_by == "scan_codebase"
        assert issue.completed_date == date(2026, 1, 15)

    def test_parse_without_frontmatter(self, tmp_path: Path) -> None:
        """Test parsing issue without frontmatter."""
        issue_file = tmp_path / "P2-ENH-007-enhancement.md"
        issue_file.write_text(
            """# ENH-007: Enhancement

## Resolution

- **Completed**: 2026-01-10
"""
        )

        issue = parse_completed_issue(issue_file)

        assert issue.issue_type == "ENH"
        assert issue.priority == "P2"
        assert issue.issue_id == "ENH-007"
        assert issue.discovered_by is None
        assert issue.completed_date == date(2026, 1, 10)

    def test_parse_feat_type(self, tmp_path: Path) -> None:
        """Test parsing FEAT type issue."""
        issue_file = tmp_path / "P3-FEAT-015-feature.md"
        issue_file.write_text("# FEAT-015: Feature\n")

        issue = parse_completed_issue(issue_file)

        assert issue.issue_type == "FEAT"
        assert issue.issue_id == "FEAT-015"


class TestScanCompletedIssues:
    """Tests for scan_completed_issues function."""

    def test_scan_empty_directory(self, tmp_path: Path) -> None:
        """Test scanning empty directory."""
        completed_dir = tmp_path / "completed"
        completed_dir.mkdir()

        issues = scan_completed_issues(completed_dir)

        assert issues == []

    def test_scan_nonexistent_directory(self, tmp_path: Path) -> None:
        """Test scanning nonexistent directory."""
        completed_dir = tmp_path / "nonexistent"

        issues = scan_completed_issues(completed_dir)

        assert issues == []

    def test_scan_multiple_issues(self, tmp_path: Path) -> None:
        """Test scanning multiple issues."""
        completed_dir = tmp_path / "completed"
        completed_dir.mkdir()

        (completed_dir / "P0-BUG-001-critical.md").write_text("# BUG-001\n")
        (completed_dir / "P1-ENH-002-improve.md").write_text("# ENH-002\n")
        (completed_dir / "P2-FEAT-003-feature.md").write_text("# FEAT-003\n")

        issues = scan_completed_issues(completed_dir)

        assert len(issues) == 3
        ids = {i.issue_id for i in issues}
        assert ids == {"BUG-001", "ENH-002", "FEAT-003"}


class TestCalculateSummary:
    """Tests for calculate_summary function."""

    def test_empty_list(self) -> None:
        """Test summary of empty list."""
        summary = calculate_summary([])

        assert summary.total_count == 0
        assert summary.type_counts == {}
        assert summary.velocity is None

    def test_type_counts(self) -> None:
        """Test type counting."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1"),
            CompletedIssue(Path("b.md"), "BUG", "P2", "BUG-2"),
            CompletedIssue(Path("c.md"), "ENH", "P1", "ENH-1"),
        ]

        summary = calculate_summary(issues)

        assert summary.type_counts == {"BUG": 2, "ENH": 1}

    def test_priority_counts(self) -> None:
        """Test priority counting."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P0", "BUG-1"),
            CompletedIssue(Path("b.md"), "BUG", "P1", "BUG-2"),
            CompletedIssue(Path("c.md"), "BUG", "P1", "BUG-3"),
        ]

        summary = calculate_summary(issues)

        assert summary.priority_counts == {"P0": 1, "P1": 2}

    def test_discovery_counts(self) -> None:
        """Test discovery source counting."""
        issues = [
            CompletedIssue(Path("a.md"), "BUG", "P1", "BUG-1", discovered_by="manual"),
            CompletedIssue(Path("b.md"), "BUG", "P1", "BUG-2", discovered_by="scan_codebase"),
            CompletedIssue(Path("c.md"), "BUG", "P1", "BUG-3"),  # None -> "unknown"
        ]

        summary = calculate_summary(issues)

        assert "manual" in summary.discovery_counts
        assert "scan_codebase" in summary.discovery_counts
        assert "unknown" in summary.discovery_counts


class TestFormatSummary:
    """Tests for format functions."""

    def test_format_summary_text(self) -> None:
        """Test text formatting."""
        summary = HistorySummary(
            total_count=10,
            type_counts={"BUG": 5, "ENH": 5},
            priority_counts={"P1": 10},
            discovery_counts={"manual": 10},
            earliest_date=date(2026, 1, 1),
            latest_date=date(2026, 1, 10),
        )

        text = format_summary_text(summary)

        assert "Total Completed: 10" in text
        assert "BUG" in text
        assert "ENH" in text
        assert "P1" in text
        assert "manual" in text

    def test_format_summary_json(self) -> None:
        """Test JSON formatting."""
        summary = HistorySummary(
            total_count=5,
            type_counts={"BUG": 5},
        )

        json_str = format_summary_json(summary)
        data = json.loads(json_str)

        assert data["total_count"] == 5
        assert data["type_counts"] == {"BUG": 5}


class TestHistoryArgumentParsing:
    """Tests for ll-history argument parsing."""

    def _parse_history_args(self, args: list[str]) -> argparse.Namespace:
        """Parse arguments using the same parser as main_history."""
        parser = argparse.ArgumentParser()
        subparsers = parser.add_subparsers(dest="command")
        summary_parser = subparsers.add_parser("summary")
        summary_parser.add_argument("--json", action="store_true")
        summary_parser.add_argument("-d", "--directory", type=Path, default=None)
        return parser.parse_args(args)

    def test_summary_default(self) -> None:
        """Test summary with defaults."""
        args = self._parse_history_args(["summary"])
        assert args.command == "summary"
        assert args.json is False
        assert args.directory is None

    def test_summary_json_flag(self) -> None:
        """Test --json flag."""
        args = self._parse_history_args(["summary", "--json"])
        assert args.json is True

    def test_summary_directory(self) -> None:
        """Test -d flag."""
        args = self._parse_history_args(["summary", "-d", "/custom/path"])
        assert args.directory == Path("/custom/path")


class TestMainHistoryIntegration:
    """Integration tests for main_history entry point."""

    def test_main_history_no_command(self) -> None:
        """Test main_history with no command shows help."""
        with patch.object(sys, "argv", ["ll-history"]):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 1

    def test_main_history_summary_empty(self, tmp_path: Path) -> None:
        """Test main_history summary with empty directory."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)

        with patch.object(
            sys, "argv", ["ll-history", "summary", "-d", str(tmp_path / ".issues")]
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0

    def test_main_history_summary_json(self, tmp_path: Path) -> None:
        """Test main_history summary --json output."""
        completed_dir = tmp_path / ".issues" / "completed"
        completed_dir.mkdir(parents=True)
        (completed_dir / "P1-BUG-001-test.md").write_text("# BUG-001\n")

        with patch.object(
            sys, "argv", ["ll-history", "summary", "--json", "-d", str(tmp_path / ".issues")]
        ):
            from little_loops.cli import main_history

            result = main_history()

        assert result == 0
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_issue_history.py -v`
- [ ] Lint passes: `ruff check scripts/tests/test_issue_history.py`

---

### Phase 4: End-to-End Verification

#### Overview
Verify the complete implementation against real data.

#### Success Criteria

**Automated Verification**:
- [ ] Full test suite: `python -m pytest scripts/tests/ -v`
- [ ] Lint all: `ruff check scripts/`
- [ ] Type check all: `python -m mypy scripts/little_loops/`
- [ ] End-to-end: `ll-history summary` (against real .issues/completed/)
- [ ] JSON output: `ll-history summary --json | python -m json.tool`

**Manual Verification**:
- [ ] Output matches expected format from issue description
- [ ] Counts match actual file counts in .issues/completed/

## Testing Strategy

### Unit Tests
- CompletedIssue dataclass serialization
- HistorySummary calculations (velocity, date range)
- Filename parsing for type/priority/ID
- Frontmatter parsing for discovered_by
- Completion date parsing

### Integration Tests
- Empty directory handling
- Real directory scanning
- CLI argument parsing
- JSON vs text output modes

## References

- Original issue: `.issues/features/P3-FEAT-111-history-summary-command.md`
- CLI patterns: `scripts/little_loops/cli.py:301-424` (main_messages)
- Issue parsing: `scripts/little_loops/issue_parser.py:76-133` (IssueInfo)
- Frontmatter parsing: `scripts/little_loops/issue_parser.py:286-324`
- Test patterns: `scripts/tests/test_cli.py:22-116` (argument parsing tests)

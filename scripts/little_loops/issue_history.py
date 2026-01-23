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
from datetime import date
from pathlib import Path
from typing import Any

__all__ = [
    "CompletedIssue",
    "HistorySummary",
    "parse_completed_issue",
    "scan_completed_issues",
    "calculate_summary",
    "format_summary_text",
    "format_summary_json",
]


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
            "completed_date": (
                self.completed_date.isoformat() if self.completed_date else None
            ),
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
            "earliest_date": (
                self.earliest_date.isoformat() if self.earliest_date else None
            ),
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
    discovery_counts = dict(
        sorted(discovery_counts.items(), key=lambda x: (-x[1], x[0]))
    )

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

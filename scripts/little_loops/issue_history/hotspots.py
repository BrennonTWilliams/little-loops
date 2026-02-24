"""Issue history hotspot detection analysis."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from little_loops.issue_history.models import (
    CompletedIssue,
    Hotspot,
    HotspotAnalysis,
)
from little_loops.issue_history.parsing import _extract_paths_from_issue


def analyze_hotspots(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> HotspotAnalysis:
    """Identify files and directories that appear repeatedly in issues.

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        HotspotAnalysis with file and directory hotspots
    """
    file_data: dict[str, dict[str, Any]] = {}  # path -> {count, ids, types}
    dir_data: dict[str, dict[str, Any]] = {}  # dir -> {count, ids, types}

    for issue in issues:
        if contents is not None and issue.path in contents:
            content = contents[issue.path]
        else:
            try:
                content = issue.path.read_text(encoding="utf-8")
            except Exception:
                continue

        paths = _extract_paths_from_issue(content)

        for path in paths:
            # Track file hotspot
            if path not in file_data:
                file_data[path] = {"count": 0, "ids": [], "types": {}}
            file_data[path]["count"] += 1
            file_data[path]["ids"].append(issue.issue_id)
            file_data[path]["types"][issue.issue_type] = (
                file_data[path]["types"].get(issue.issue_type, 0) + 1
            )

            # Track directory hotspot
            if "/" in path:
                dir_path = "/".join(path.split("/")[:-1]) + "/"
            else:
                dir_path = "./"

            if dir_path not in dir_data:
                dir_data[dir_path] = {"count": 0, "ids": [], "types": {}}
            if issue.issue_id not in dir_data[dir_path]["ids"]:
                dir_data[dir_path]["count"] += 1
                dir_data[dir_path]["ids"].append(issue.issue_id)
                dir_data[dir_path]["types"][issue.issue_type] = (
                    dir_data[dir_path]["types"].get(issue.issue_type, 0) + 1
                )

    # Convert to Hotspot objects
    file_hotspots: list[Hotspot] = []
    for path, data in file_data.items():
        bug_count = data["types"].get("BUG", 0)
        total = data["count"]
        bug_ratio = bug_count / total if total > 0 else 0.0

        # Determine churn indicator
        if total >= 5:
            churn = "high"
        elif total >= 3:
            churn = "medium"
        else:
            churn = "low"

        file_hotspots.append(
            Hotspot(
                path=path,
                issue_count=total,
                issue_ids=data["ids"],
                issue_types=data["types"],
                bug_ratio=bug_ratio,
                churn_indicator=churn,
            )
        )

    # Convert directory data to Hotspot objects
    dir_hotspots: list[Hotspot] = []
    for path, data in dir_data.items():
        bug_count = data["types"].get("BUG", 0)
        total = data["count"]
        bug_ratio = bug_count / total if total > 0 else 0.0

        if total >= 5:
            churn = "high"
        elif total >= 3:
            churn = "medium"
        else:
            churn = "low"

        dir_hotspots.append(
            Hotspot(
                path=path,
                issue_count=total,
                issue_ids=data["ids"],
                issue_types=data["types"],
                bug_ratio=bug_ratio,
                churn_indicator=churn,
            )
        )

    # Sort by issue count descending
    file_hotspots.sort(key=lambda h: -h.issue_count)
    dir_hotspots.sort(key=lambda h: -h.issue_count)

    # Identify bug magnets (>60% bug ratio, at least 3 issues)
    bug_magnets = [h for h in file_hotspots if h.bug_ratio > 0.6 and h.issue_count >= 3]
    bug_magnets.sort(key=lambda h: (-h.bug_ratio, -h.issue_count))

    return HotspotAnalysis(
        file_hotspots=file_hotspots[:10],  # Top 10
        directory_hotspots=dir_hotspots[:10],  # Top 10
        bug_magnets=bug_magnets[:5],  # Top 5
    )

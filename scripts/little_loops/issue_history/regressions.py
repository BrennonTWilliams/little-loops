"""Issue history regression clustering analysis."""

from __future__ import annotations

from pathlib import Path

from little_loops.issue_history.models import (
    CompletedIssue,
    RegressionAnalysis,
    RegressionCluster,
)
from little_loops.issue_history.parsing import _extract_paths_from_issue


def analyze_regression_clustering(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> RegressionAnalysis:
    """Detect files where bug fixes frequently lead to new bugs.

    Uses heuristics:
    1. Temporal proximity: Bug B completed within 7 days of Bug A
    2. File overlap: Both bugs affect same file(s)

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        RegressionAnalysis with clusters of related regressions
    """
    # Filter to bugs only and sort by completion date
    bugs = [i for i in issues if i.issue_type == "BUG" and i.completed_date]
    bugs.sort(key=lambda i: i.completed_date)  # type: ignore

    if len(bugs) < 2:
        return RegressionAnalysis()

    # Extract file paths for each bug
    bug_files: dict[str, set[str]] = {}  # issue_id -> set of files
    for bug in bugs:
        if contents is not None and bug.path in contents:
            content = contents[bug.path]
            paths = _extract_paths_from_issue(content)
            bug_files[bug.issue_id] = set(paths)
        else:
            try:
                content = bug.path.read_text(encoding="utf-8")
                paths = _extract_paths_from_issue(content)
                bug_files[bug.issue_id] = set(paths)
            except Exception:
                bug_files[bug.issue_id] = set()

    # Find regression pairs (temporal proximity + file overlap)
    regression_pairs: list[tuple[CompletedIssue, CompletedIssue, set[str]]] = []

    for i, bug_a in enumerate(bugs[:-1]):
        files_a = bug_files.get(bug_a.issue_id, set())
        if not files_a:
            continue

        for bug_b in bugs[i + 1 :]:
            # Check temporal proximity (within 7 days)
            days_apart = (bug_b.completed_date - bug_a.completed_date).days  # type: ignore
            if days_apart > 7:
                break  # Bugs are sorted, no need to check further

            files_b = bug_files.get(bug_b.issue_id, set())
            if not files_b:
                continue

            # Check file overlap
            overlap = files_a & files_b
            if overlap:
                regression_pairs.append((bug_a, bug_b, overlap))

    if not regression_pairs:
        return RegressionAnalysis()

    # Group by primary file (most common overlapping file)
    file_regressions: dict[str, list[tuple[str, str, int]]] = {}  # file -> [(id_a, id_b, days)]

    for bug_a, bug_b, overlap in regression_pairs:
        days = (bug_b.completed_date - bug_a.completed_date).days  # type: ignore
        for file_path in overlap:
            if file_path not in file_regressions:
                file_regressions[file_path] = []
            file_regressions[file_path].append((bug_a.issue_id, bug_b.issue_id, days))

    # Build clusters
    clusters: list[RegressionCluster] = []

    for file_path, pairs in file_regressions.items():
        # Determine time pattern
        avg_days = sum(d for _, _, d in pairs) / len(pairs)
        if avg_days < 3:
            time_pattern = "immediate"
        elif len(pairs) >= 3:
            time_pattern = "chronic"
        else:
            time_pattern = "delayed"

        # Determine severity
        if len(pairs) >= 4:
            severity = "critical"
        elif len(pairs) >= 2:
            severity = "high"
        else:
            severity = "medium"

        # Collect related files
        related_files: set[str] = set()
        for bug_a, bug_b, _ in regression_pairs:
            if file_path in (
                bug_files.get(bug_a.issue_id, set()) & bug_files.get(bug_b.issue_id, set())
            ):
                related_files.update(bug_files.get(bug_a.issue_id, set()))
                related_files.update(bug_files.get(bug_b.issue_id, set()))
        related_files.discard(file_path)

        clusters.append(
            RegressionCluster(
                primary_file=file_path,
                regression_count=len(pairs),
                fix_bug_pairs=[(a, b) for a, b, _ in pairs],
                related_files=sorted(related_files),
                time_pattern=time_pattern,
                severity=severity,
            )
        )

    # Sort by regression count descending
    clusters.sort(key=lambda c: (-c.regression_count, c.primary_file))

    # Identify most fragile files
    most_fragile = [c.primary_file for c in clusters[:5]]

    return RegressionAnalysis(
        clusters=clusters[:10],  # Top 10
        total_regression_chains=len(regression_pairs),
        most_fragile_files=most_fragile,
    )

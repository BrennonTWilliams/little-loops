"""Issue history file coupling analysis."""

from __future__ import annotations

from pathlib import Path

from little_loops.issue_history.models import (
    CompletedIssue,
    CouplingAnalysis,
    CouplingPair,
)
from little_loops.issue_history.parsing import _extract_paths_from_issue


def analyze_coupling(
    issues: list[CompletedIssue],
    contents: dict[Path, str] | None = None,
) -> CouplingAnalysis:
    """Identify files that frequently change together across issues.

    Uses Jaccard similarity to calculate coupling strength between file pairs.
    Files with coupling strength >= 0.3 and at least 2 co-occurrences are included.

    Args:
        issues: List of completed issues
        contents: Pre-loaded issue file contents (path -> content)

    Returns:
        CouplingAnalysis with coupled pairs, clusters, and hotspots
    """
    # Build file -> set of issue IDs mapping
    file_to_issues: dict[str, set[str]] = {}

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
            if path not in file_to_issues:
                file_to_issues[path] = set()
            file_to_issues[path].add(issue.issue_id)

    # Calculate pairwise coupling
    files = list(file_to_issues.keys())
    pairs: list[CouplingPair] = []

    for i, file_a in enumerate(files):
        for file_b in files[i + 1 :]:
            a_issues = file_to_issues[file_a]
            b_issues = file_to_issues[file_b]
            co_occur = a_issues & b_issues
            union = a_issues | b_issues

            if len(co_occur) < 2:  # Require at least 2 co-occurrences
                continue

            # Jaccard similarity
            strength = len(co_occur) / len(union) if union else 0.0

            if strength >= 0.3:  # Only include significant coupling
                pairs.append(
                    CouplingPair(
                        file_a=file_a,
                        file_b=file_b,
                        co_occurrence_count=len(co_occur),
                        coupling_strength=strength,
                        issue_ids=sorted(co_occur),
                    )
                )

    # Sort by coupling strength descending
    pairs.sort(key=lambda p: (-p.coupling_strength, -p.co_occurrence_count))

    # Build clusters using simple connected components
    clusters = _build_coupling_clusters(pairs)

    # Identify hotspots (files coupled with 3+ others)
    file_coupling_count: dict[str, int] = {}
    for pair in pairs:
        file_coupling_count[pair.file_a] = file_coupling_count.get(pair.file_a, 0) + 1
        file_coupling_count[pair.file_b] = file_coupling_count.get(pair.file_b, 0) + 1

    hotspots = [f for f, count in file_coupling_count.items() if count >= 3]
    hotspots.sort(key=lambda f: -file_coupling_count[f])

    return CouplingAnalysis(
        pairs=pairs[:20],  # Top 20 pairs
        clusters=clusters[:10],  # Top 10 clusters
        hotspots=hotspots[:10],  # Top 10 hotspots
    )


def _build_coupling_clusters(pairs: list[CouplingPair]) -> list[list[str]]:
    """Build clusters of coupled files using connected components.

    Args:
        pairs: List of coupling pairs

    Returns:
        List of file clusters (each cluster is a list of file paths)
    """
    # Build adjacency for high-coupling pairs (strength >= 0.5)
    adjacency: dict[str, set[str]] = {}
    for pair in pairs:
        if pair.coupling_strength >= 0.5:
            if pair.file_a not in adjacency:
                adjacency[pair.file_a] = set()
            if pair.file_b not in adjacency:
                adjacency[pair.file_b] = set()
            adjacency[pair.file_a].add(pair.file_b)
            adjacency[pair.file_b].add(pair.file_a)

    # Find connected components
    visited: set[str] = set()
    clusters: list[list[str]] = []

    for start in adjacency:
        if start in visited:
            continue
        # BFS to find component
        cluster: list[str] = []
        queue = [start]
        while queue:
            node = queue.pop(0)
            if node in visited:
                continue
            visited.add(node)
            cluster.append(node)
            for neighbor in adjacency.get(node, set()):
                if neighbor not in visited:
                    queue.append(neighbor)

        if len(cluster) >= 2:  # Only include clusters with 2+ files
            cluster.sort()
            clusters.append(cluster)

    # Sort clusters by size descending
    clusters.sort(key=lambda c: -len(c))
    return clusters

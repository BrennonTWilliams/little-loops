"""ll-issues sequence: Suggest dependency-ordered implementation sequence."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_sequence(config: BRConfig, args: argparse.Namespace) -> int:
    """Output a dependency-ordered list of active issues with rationale.

    Args:
        config: Project configuration
        args: Parsed arguments with .limit attribute

    Returns:
        Exit code (0 = success)
    """
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.issue_parser import find_issues

    issues = find_issues(config)

    if not issues:
        print("No active issues found.")
        return 0

    graph = DependencyGraph.from_issues(issues)

    try:
        ordered = graph.topological_sort()
    except ValueError as exc:
        print(f"Warning: dependency cycle detected — {exc}")
        ordered = issues  # fall back to priority order

    limit = args.limit
    shown = ordered[:limit]

    print(f"Suggested implementation sequence ({len(shown)} of {len(ordered)} issues):\n")
    for issue in shown:
        blockers = graph.blocked_by.get(issue.issue_id, set())
        if blockers:
            rationale = f"blocked by: {', '.join(sorted(blockers))}"
        else:
            rationale = "no blockers"
        print(f"  [{issue.priority}, {rationale}] {issue.issue_id}: {issue.title}")

    if len(ordered) > limit:
        remaining = len(ordered) - limit
        print(f"\n  … +{remaining} more (use --limit to show more)")

    return 0

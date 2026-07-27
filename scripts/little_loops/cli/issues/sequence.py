"""ll-issues sequence: Suggest dependency-ordered implementation sequence."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize, print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig


def cmd_sequence(config: BRConfig, args: argparse.Namespace) -> int:
    """Output a dependency-ordered list of active issues with rationale.

    Args:
        config: Project configuration
        args: Parsed arguments with .limit and optional .type attributes

    Returns:
        Exit code (0 = success)
    """
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.issue_parser import find_issues

    type_prefixes = {args.type} if getattr(args, "type", None) else None
    issues = find_issues(config, type_prefixes=type_prefixes)

    if not issues:
        print("No active issues found.")
        return 0

    all_known_ids: set[str] | None = None
    try:
        from little_loops.dependency_mapper import gather_all_issue_ids

        issues_dir = config.project_root / config.issues.base_dir
        all_known_ids = gather_all_issue_ids(issues_dir, config=config)
    except Exception:
        pass

    graph = DependencyGraph.from_issues(issues, all_known_ids=all_known_ids)

    try:
        ordered = graph.topological_sort()
    except ValueError as exc:
        print(f"Warning: dependency cycle detected — {exc}")
        ordered = issues  # fall back to priority order

    limit = args.limit
    shown = ordered[:limit]

    if getattr(args, "json", False):
        type_filter = getattr(args, "type", None)
        print_json(
            [
                {
                    "id": issue.issue_id,
                    "priority": issue.priority,
                    "title": issue.title,
                    "path": str(issue.path),
                    "blocked_by": sorted(graph.blocked_by.get(issue.issue_id, set())),
                    "blocks": issue.blocks,
                    "depends_on": sorted(graph.get_pending_prerequisites(issue.issue_id)),
                    **({"type_filter": type_filter} if type_filter else {}),
                }
                for issue in shown
            ]
        )
        return 0

    print(f"Suggested implementation sequence ({len(shown)} of {len(ordered)} issues):\n")
    for issue in shown:
        blockers = graph.blocked_by.get(issue.issue_id, set())
        prerequisites = graph.get_pending_prerequisites(issue.issue_id)
        parts = []
        if blockers:
            parts.append(f"blocked by: {', '.join(sorted(blockers))}")
        if prerequisites:
            parts.append(f"after: {', '.join(sorted(prerequisites))}")
        rationale = "; ".join(parts) if parts else "no blockers"
        issue_prefix = issue.issue_id.split("-", 1)[0]
        colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_prefix, "0"))
        colored_pri = colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))
        print(f"  [{colored_pri}, {rationale}] {colored_id}: {issue.title}")

    if len(ordered) > limit:
        remaining = len(ordered) - limit
        print(f"\n  … +{remaining} more (use --limit to show more)")

    return 0

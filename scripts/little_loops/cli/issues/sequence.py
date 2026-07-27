"""ll-issues sequence: Suggest dependency-ordered implementation sequence."""

from __future__ import annotations

import argparse
from typing import TYPE_CHECKING

from little_loops.cli.output import PRIORITY_COLOR, TYPE_COLOR, colorize, print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo


def _unverified_prose_deps(issue: IssueInfo, issue_statuses: dict[str, str]) -> list[str]:
    """Prose-claimed dependencies not backed by a structured edge.

    Mirrors the drift half of ``issue_parser.check_format_gaps()``'s
    classification (terminal targets excluded, structured edges excluded)
    but is scoped to a single already-loaded issue rather than a sweep.
    """
    from little_loops.frontmatter import parse_frontmatter, strip_frontmatter
    from little_loops.issues.prose_deps import extract_prose_deps

    content = issue.path.read_text(encoding="utf-8")
    fm = parse_frontmatter(content)

    structured_deps: set[str] = set()
    for key in ("blocked_by", "depends_on"):
        value = fm.get(key)
        if isinstance(value, list):
            structured_deps.update(str(v).strip().upper() for v in value)
        elif isinstance(value, str) and value.strip():
            structured_deps.add(value.strip().upper())

    body_only = strip_frontmatter(content)
    unverified = []
    for prose_id in sorted(extract_prose_deps(body_only)):
        if prose_id == issue.issue_id or prose_id in structured_deps:
            continue
        if issue_statuses.get(prose_id) in ("done", "cancelled"):
            continue
        unverified.append(prose_id)
    return unverified


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
    from little_loops.issue_progress import _ALL_STATUSES

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

    issue_statuses: dict[str, str] | None = None
    try:
        all_issues = find_issues(config, status_filter=set(_ALL_STATUSES))
        issue_statuses = {info.issue_id: info.status for info in all_issues}
    except Exception:
        pass

    def prose_deps_for(issue: IssueInfo) -> list[str]:
        if issue_statuses is None or graph.blocked_by.get(issue.issue_id, set()):
            return []
        try:
            return _unverified_prose_deps(issue, issue_statuses)
        except Exception:
            return []

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
                    "unverified_prose_deps": prose_deps_for(issue),
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
        prose_deps = prose_deps_for(issue)
        rationale = "; ".join(parts) if parts else "no blockers"
        if prose_deps:
            rationale += f" ⚠ prose dep {', '.join(prose_deps)}, not in blocked_by"
        issue_prefix = issue.issue_id.split("-", 1)[0]
        colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_prefix, "0"))
        colored_pri = colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))
        print(f"  [{colored_pri}, {rationale}] {colored_id}: {issue.title}")

    if len(ordered) > limit:
        remaining = len(ordered) - limit
        print(f"\n  … +{remaining} more (use --limit to show more)")

    return 0

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
    from little_loops.issue_parser import find_issues_for_graph
    from little_loops.issue_progress import _OPEN_STATUSES

    type_prefix = getattr(args, "type", None)
    is_json = getattr(args, "json", False)

    # Build wide: one graph-construction call, no type_prefixes, non-terminal
    # superset (includes deferred) — so a blocker outside the requested type
    # slice (BUG-2898) or a deferred blocker (BUG-2897) is still recognized
    # rather than silently dropped as an out-of-graph edge.
    graph_issues = find_issues_for_graph(config)

    if not graph_issues:
        print("No active issues found.")
        return 0

    all_known_ids: set[str] | None = None
    try:
        from little_loops.dependency_mapper import gather_all_issue_ids

        issues_dir = config.project_root / config.issues.base_dir
        all_known_ids = gather_all_issue_ids(issues_dir, config=config)
    except Exception:
        pass

    graph = DependencyGraph.from_issues(graph_issues, all_known_ids=all_known_ids)

    cycle_ids: set[str] = set()
    cycle_paths: dict[str, str] = {}
    try:
        ordered = graph.topological_sort()
    except ValueError as exc:
        # --json must emit a single valid JSON document on stdout, so the
        # cycle is surfaced there via the per-item in_cycle field instead of
        # these human-readable warning lines.
        if not is_json:
            print(f"Warning: dependency cycle detected — {exc}")
            print(
                "Ordering below is priority-only; cycle members marked ⚠ and cannot be sequenced.\n"
            )
        # detect_cycles() is called again here (already ran once inside
        # topological_sort() to build the exception message) — harmless at
        # current backlog sizes, not worth threading through for a single call.
        for cycle in graph.detect_cycles():
            cycle_ids.update(cycle)
            path_str = " -> ".join(cycle)
            for cid in cycle:
                cycle_paths[cid] = path_str
        ordered = sorted(graph_issues, key=lambda i: (i.priority_int, i.issue_id))

    # Narrow: apply both display filters to the ordered list, below the
    # cycle-fallback path so it's covered too.
    display = [i for i in ordered if i.status in _OPEN_STATUSES]
    if type_prefix:
        display = [i for i in display if i.issue_id.split("-", 1)[0] == type_prefix]

    if not display:
        if type_prefix:
            print(f"No active issues found for type {type_prefix}.")
        else:
            print("No active issues found.")
        return 0

    limit = args.limit
    shown = display[:limit]

    issue_statuses: dict[str, str] = {info.issue_id: info.status for info in graph_issues}
    try:
        from little_loops.issue_parser import find_issues

        terminal_issues = find_issues(config, status_filter={"done", "cancelled"})
        issue_statuses.update({info.issue_id: info.status for info in terminal_issues})
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
                    "deferred_blockers": sorted(
                        b
                        for b in graph.blocked_by.get(issue.issue_id, set())
                        if issue_statuses.get(b) == "deferred"
                    ),
                    "blocks": issue.blocks,
                    "depends_on": sorted(graph.get_pending_prerequisites(issue.issue_id)),
                    "unverified_prose_deps": prose_deps_for(issue),
                    "in_cycle": issue.issue_id in cycle_ids,
                    **({"type_filter": type_filter} if type_filter else {}),
                }
                for issue in shown
            ]
        )
        return 0

    print(f"Suggested implementation sequence ({len(shown)} of {len(display)} issues):\n")
    for issue in shown:
        if issue.issue_id in cycle_ids:
            # Structured blocked_by/after edges are what form the cycle —
            # showing the stale annotations alongside the cycle marker would
            # just repeat the same edges as noise, so suppress them here.
            rationale = f"⚠ in cycle: {cycle_paths.get(issue.issue_id, '')}"
            prose_deps = prose_deps_for(issue)
            if prose_deps:
                rationale += f" ⚠ prose dep {', '.join(prose_deps)}, not in blocked_by"
            issue_prefix = issue.issue_id.split("-", 1)[0]
            colored_id = colorize(issue.issue_id, TYPE_COLOR.get(issue_prefix, "0"))
            colored_pri = colorize(issue.priority, PRIORITY_COLOR.get(issue.priority, "0"))
            print(f"  [{colored_pri}, {rationale}] {colored_id}: {issue.title}")
            continue
        blockers = graph.blocked_by.get(issue.issue_id, set())
        prerequisites = graph.get_pending_prerequisites(issue.issue_id)
        parts = []
        if blockers:

            def _fmt_blocker(bid: str) -> str:
                return f"{bid} (deferred)" if issue_statuses.get(bid) == "deferred" else bid

            parts.append(f"blocked by: {', '.join(_fmt_blocker(b) for b in sorted(blockers))}")
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

    if len(display) > limit:
        remaining = len(display) - limit
        print(f"\n  … +{remaining} more (use --limit to show more)")

    return 0

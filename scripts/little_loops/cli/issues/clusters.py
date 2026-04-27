"""ll-issues clusters: Render issue relationship clusters as box diagrams."""

from __future__ import annotations

import argparse
from collections import deque
from typing import TYPE_CHECKING

from little_loops.cli.output import colorize, print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.issue_parser import IssueInfo

# ANSI color codes per relationship type
EDGE_COLOR: dict[str, str] = {
    "blocks": "31",  # red
    "blocked_by": "33",  # yellow
    "parent": "34",  # blue
    "sibling": "36",  # cyan
}

_BOX_HEIGHT = 4  # top border + 2 content lines + bottom border
_GAP_HEIGHT = 2  # rows between boxes for arrow drawing
_BOX_MARGIN = 2  # left-margin column offset
_MAX_BOX_WIDTH = 60


def _get_connected_components(graph: DependencyGraph, all_ids: set[str]) -> list[list[str]]:
    """BFS over undirected dependency graph to find connected components.

    Returns components sorted by size descending.
    """
    visited: set[str] = set()
    components: list[list[str]] = []

    for node in sorted(all_ids):
        if node in visited:
            continue
        component: list[str] = []
        queue: deque[str] = deque([node])
        while queue:
            current = queue.popleft()
            if current in visited:
                continue
            visited.add(current)
            component.append(current)
            neighbors = (
                graph.blocked_by.get(current, set()) | graph.blocks.get(current, set())
            ) & all_ids
            for neighbor in sorted(neighbors):
                if neighbor not in visited:
                    queue.append(neighbor)
        components.append(component)

    return sorted(components, key=len, reverse=True)


def _topo_sort_cluster(
    cluster_ids: list[str],
    blocked_by: dict[str, set[str]],
) -> tuple[list[str], bool]:
    """Topological sort (Kahn's) scoped to this cluster.

    Returns (sorted_ids, has_cycle). Nodes in cycles are appended in sorted
    order after the acyclic prefix so the caller always gets a full list.
    """
    cluster_set = set(cluster_ids)
    in_degree: dict[str, int] = dict.fromkeys(cluster_ids, 0)
    adj: dict[str, list[str]] = {id_: [] for id_ in cluster_ids}

    for id_ in cluster_ids:
        for dep in sorted(blocked_by.get(id_, set()) & cluster_set):
            in_degree[id_] += 1
            adj[dep].append(id_)

    queue: deque[str] = deque(sorted(id_ for id_, deg in in_degree.items() if deg == 0))
    result: list[str] = []

    while queue:
        node = queue.popleft()
        result.append(node)
        for dep in sorted(adj[node]):
            in_degree[dep] -= 1
            if in_degree[dep] == 0:
                queue.append(dep)

    has_cycle = len(result) < len(cluster_ids)
    if has_cycle:
        remaining = sorted(id_ for id_ in cluster_ids if id_ not in set(result))
        result.extend(remaining)

    return result, has_cycle


def _cluster_edges(cluster_ids: set[str], graph: DependencyGraph) -> list[tuple[str, str, str]]:
    """Return directed edges within a cluster as (from_id, to_id, relationship)."""
    edges: list[tuple[str, str, str]] = []
    for id_ in sorted(cluster_ids):
        for blocked_id in sorted(graph.blocks.get(id_, set())):
            if blocked_id in cluster_ids:
                edges.append((id_, blocked_id, "blocks"))
    return edges


def _render_cluster_diagram(
    ordered_ids: list[str],
    issues_map: dict[str, IssueInfo],
    edge_map: dict[tuple[str, str], str],
    box_width: int,
) -> list[str]:
    """Render a cluster as a vertical stack of box diagrams with arrows.

    Uses _draw_box from cli/loop/layout.py as the box primitive.
    Arrows are drawn between consecutive nodes; edge labels are appended
    after the arrow row so ANSI escapes don't corrupt the character grid.
    """
    # Intentional cross-module import of a private primitive; _draw_box is
    # reusable and has no FSM-specific logic when is_highlighted=False.
    from little_loops.cli.loop.layout import _draw_box

    n = len(ordered_ids)
    grid_h = n * _BOX_HEIGHT + max(0, n - 1) * _GAP_HEIGHT
    grid_w = box_width + _BOX_MARGIN * 2 + 2
    grid: list[list[str]] = [[" "] * grid_w for _ in range(grid_h)]

    center_col = _BOX_MARGIN + box_width // 2
    box_start: dict[str, int] = {}
    avail = box_width - 4  # interior width minus side margins

    for i, issue_id in enumerate(ordered_ids):
        row = i * (_BOX_HEIGHT + _GAP_HEIGHT)
        issue = issues_map[issue_id]
        title = issue.title if len(issue.title) <= avail else issue.title[: avail - 1] + "…"
        content = [f"[{issue.priority}] {issue_id}", title]
        _draw_box(grid, row, _BOX_MARGIN, box_width, _BOX_HEIGHT, content, False, "0")
        box_start[issue_id] = row

    # Annotate gap rows with arrow characters and colored edge labels.
    # Only draw connectors when a real edge exists between consecutive nodes.
    arrow_labels: dict[int, str] = {}
    for i in range(n - 1):
        a_id = ordered_ids[i]
        b_id = ordered_ids[i + 1]
        gap_row = box_start[a_id] + _BOX_HEIGHT

        rel = edge_map.get((a_id, b_id)) or edge_map.get((b_id, a_id))
        if rel:
            if gap_row < grid_h:
                grid[gap_row][center_col] = "│"
            if gap_row + 1 < grid_h:
                grid[gap_row + 1][center_col] = "▼"
            color = EDGE_COLOR.get(rel, "37")
            arrow_labels[gap_row] = colorize(f" {rel}", color)

    # Convert grid to string lines, appending annotations after arrow rows
    lines: list[str] = []
    for r, row_chars in enumerate(grid):
        line = "".join(row_chars).rstrip()
        if r in arrow_labels:
            line += arrow_labels[r]
        lines.append(line)

    while lines and not lines[-1].strip():
        lines.pop()

    # Append annotations for skip-level edges (non-consecutive in topo order).
    pos = {id_: i for i, id_ in enumerate(ordered_ids)}
    skip_edges = [
        (f, t, r)
        for (f, t), r in sorted(edge_map.items())
        if pos[t] - pos[f] > 1
    ]
    if skip_edges:
        lines.append("")
        for f, t, r in skip_edges:
            color = EDGE_COLOR.get(r, "37")
            lines.append(f"  {f} {colorize('→', color)} {t}  ({r})")

    return lines


def cmd_clusters(config: BRConfig, args: argparse.Namespace) -> int:
    """Render issue relationship clusters as box diagrams.

    Args:
        config: Project configuration (provides issue directories and CLI settings)
        args: Parsed CLI args (include_orphans: bool, min_connections: int, json: bool)

    Returns:
        Exit code (0 = success)
    """
    from little_loops.cli.output import terminal_width
    from little_loops.dependency_graph import DependencyGraph
    from little_loops.dependency_mapper.operations import gather_all_issue_ids
    from little_loops.issue_parser import find_issues

    issues = find_issues(config)
    if not issues:
        print("No active issues found.")
        return 0

    issues_dir = config.project_root / config.issues.base_dir
    all_known_ids = gather_all_issue_ids(issues_dir, config=config)
    graph = DependencyGraph.from_issues(issues, all_known_ids=all_known_ids)
    all_ids = set(graph.issues.keys())
    components = _get_connected_components(graph, all_ids)

    include_orphans: bool = getattr(args, "include_orphans", False)
    if not include_orphans:
        components = [c for c in components if len(c) > 1]

    min_conn: int = getattr(args, "min_connections", 0) or 0
    if min_conn > 0:

        def _max_degree(comp: list[str]) -> int:
            return max(
                len(graph.blocked_by.get(id_, set()) | graph.blocks.get(id_, set())) for id_ in comp
            )

        components = [c for c in components if _max_degree(c) >= min_conn]

    if not components:
        all_components = _get_connected_components(graph, all_ids)
        if all(len(c) == 1 for c in all_components):
            print("No issue relationships found. Use --include-orphans to show isolated issues.")
        else:
            print("No clusters match the specified filters.")
        return 0

    # JSON mode: emit structured data, no diagram rendering
    if getattr(args, "json", False):
        output = []
        for idx, comp in enumerate(components, 1):
            comp_set = set(comp)
            edges = _cluster_edges(comp_set, graph)
            output.append(
                {
                    "cluster_index": idx,
                    "issue_count": len(comp),
                    "issues": [
                        {
                            "id": id_,
                            "priority": graph.issues[id_].priority,
                            "title": graph.issues[id_].title,
                        }
                        for id_ in sorted(comp)
                    ],
                    "edges": [{"from": f, "to": t, "relationship": r} for f, t, r in edges],
                }
            )
        print_json(output)
        return 0

    # Text rendering
    width = terminal_width()
    box_w = max(20, min(_MAX_BOX_WIDTH, width - _BOX_MARGIN * 2 - 4))
    issues_map = graph.issues
    total_issues = sum(len(c) for c in components)

    for idx, comp in enumerate(components, 1):
        comp_set = set(comp)
        edges = _cluster_edges(comp_set, graph)
        edge_map: dict[tuple[str, str], str] = {(f, t): r for f, t, r in edges}

        ordered, has_cycle = _topo_sort_cluster(comp, graph.blocked_by)

        sep = "─" * 3
        n_issues = len(comp)
        noun = "issue" if n_issues == 1 else "issues"
        print(f"{sep} Cluster {idx} ({n_issues} {noun}) {sep}")
        if has_cycle:
            print("⚠ cycle detected — using fallback layout")

        diagram_lines = _render_cluster_diagram(ordered, issues_map, edge_map, box_w)
        print("\n".join(diagram_lines))
        print()

    n_clusters = len(components)
    cluster_noun = "cluster" if n_clusters == 1 else "clusters"
    issue_noun = "issue" if total_issues == 1 else "issues"
    print(f"{n_clusters} {cluster_noun}, {total_issues} {issue_noun} total")
    return 0

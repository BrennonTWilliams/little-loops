"""ll-issues clusters: Render issue relationship clusters as box diagrams."""

from __future__ import annotations

import argparse
from collections import deque
from typing import TYPE_CHECKING

from little_loops.cli.output import colorize, print_json

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

# ANSI color codes per relationship type
EDGE_COLOR: dict[str, str] = {
    "blocks": "31",       # red
    "blocked_by": "33",   # yellow
    "parent": "34",       # blue
    "sibling": "36",      # cyan
    "depends_on": "35",   # magenta
    "relates_to": "37",   # white/dim
}

_BOX_HEIGHT = 4  # top border + 2 content lines + bottom border
_GAP_HEIGHT = 2  # rows between boxes for arrow drawing
_BOX_MARGIN = 2  # left-margin column offset
_MAX_BOX_WIDTH = 60

# Edge type sets for --edges aliases
_ALL_EDGE_TYPES = frozenset({"blocked_by", "blocks", "depends_on", "relates_to", "parent"})
_BLOCKING_EDGE_TYPES = frozenset({"blocked_by", "blocks"})
_HARD_EDGE_TYPES = frozenset({"blocked_by", "blocks", "depends_on"})

# Active status set for --status=active default
_ACTIVE_STATUSES = frozenset({"open", "in_progress", "blocked"})

# Priority order when two relationships describe the same pair (lower = higher priority)
_EDGE_PRIORITY: dict[str, int] = {
    "blocked_by": 0,
    "blocks": 1,
    "parent": 2,
    "depends_on": 3,
    "relates_to": 4,
}


def _resolve_edge_types(edges_arg: str) -> set[str]:
    """Resolve --edges argument to a set of edge type strings."""
    if edges_arg == "all":
        return set(_ALL_EDGE_TYPES)
    if edges_arg == "blocking":
        return set(_BLOCKING_EDGE_TYPES)
    if edges_arg == "hard":
        return set(_HARD_EDGE_TYPES)
    return set(edges_arg.split(","))


def _resolve_status_set(status_arg: str) -> set[str]:
    """Resolve --status argument to a set of canonical status strings."""
    if status_arg == "active":
        return set(_ACTIVE_STATUSES)
    if status_arg == "+deferred":
        return set(_ACTIVE_STATUSES) | {"deferred"}
    if status_arg == "all":
        return {"open", "in_progress", "blocked", "done", "deferred"}
    return set(status_arg.split(","))


def _build_neighbour_map(issues: list[IssueInfo], edge_types: set[str]) -> dict[str, set[str]]:
    """Build undirected neighbour map from IssueInfo for connectivity BFS.

    Only connects issues to other issues present in the loaded list.
    """
    issue_ids = {i.issue_id for i in issues}
    neighbours: dict[str, set[str]] = {i.issue_id: set() for i in issues}

    for issue in issues:
        iid = issue.issue_id
        targets: list[str] = []

        if "blocked_by" in edge_types:
            targets.extend(issue.blocked_by)
        if "blocks" in edge_types:
            targets.extend(issue.blocks)
        if "depends_on" in edge_types:
            targets.extend(issue.depends_on)
        if "relates_to" in edge_types:
            targets.extend(issue.relates_to)
        if "parent" in edge_types and issue.parent:
            targets.append(issue.parent)

        for target in targets:
            if target in issue_ids:
                neighbours[iid].add(target)
                neighbours[target].add(iid)

    return neighbours


def _get_components(neighbours: dict[str, set[str]]) -> list[list[str]]:
    """BFS over undirected neighbour map to find connected components.

    Returns components sorted by size descending.
    """
    visited: set[str] = set()
    components: list[list[str]] = []

    for node in sorted(neighbours):
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
            for neighbor in sorted(neighbours.get(current, set())):
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


def _cluster_edges(
    cluster_ids: set[str],
    issues: list[IssueInfo],
    edge_types: set[str],
) -> list[tuple[str, str, str]]:
    """Return directed edges within a cluster as (from_id, to_id, relationship).

    Deduplicates edges between the same pair, keeping the highest-priority
    relationship type (blocked_by > blocks > parent > depends_on > relates_to).
    """
    issues_in_cluster = {i.issue_id: i for i in issues if i.issue_id in cluster_ids}
    # frozenset key → (from_id, to_id, rel) for deduplication
    best: dict[frozenset[str], tuple[str, str, str]] = {}

    for iid in sorted(cluster_ids):
        issue = issues_in_cluster.get(iid)
        if not issue:
            continue

        candidates: list[tuple[str, str, str]] = []
        if "blocked_by" in edge_types:
            for t in sorted(issue.blocked_by):
                if t in cluster_ids:
                    candidates.append((iid, t, "blocked_by"))
        if "blocks" in edge_types:
            for t in sorted(issue.blocks):
                if t in cluster_ids:
                    candidates.append((iid, t, "blocks"))
        if "depends_on" in edge_types:
            for t in sorted(issue.depends_on):
                if t in cluster_ids:
                    candidates.append((iid, t, "depends_on"))
        if "relates_to" in edge_types:
            for t in sorted(issue.relates_to):
                if t in cluster_ids:
                    candidates.append((iid, t, "relates_to"))
        if "parent" in edge_types and issue.parent and issue.parent in cluster_ids:
            candidates.append((iid, issue.parent, "parent"))

        for from_id, to_id, rel in candidates:
            key: frozenset[str] = frozenset({from_id, to_id})
            existing = best.get(key)
            if existing is None or _EDGE_PRIORITY.get(rel, 99) < _EDGE_PRIORITY.get(existing[2], 99):
                best[key] = (from_id, to_id, rel)

    return list(best.values())


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
    skip_edges = [(f, t, r) for (f, t), r in sorted(edge_map.items()) if abs(pos[t] - pos[f]) > 1]
    if skip_edges:
        lines.append("")
        for src, dst, rel in skip_edges:
            color = EDGE_COLOR.get(rel, "37")
            lines.append(f"  {src} {colorize('→', color)} {dst}  ({rel})")

    return lines


def cmd_clusters(config: BRConfig, args: argparse.Namespace) -> int:
    """Render issue relationship clusters as box diagrams.

    Args:
        config: Project configuration (provides issue directories and CLI settings)
        args: Parsed CLI args (include_orphans, min_connections, json, edges, status)

    Returns:
        Exit code (0 = success)
    """
    from little_loops.cli.output import terminal_width
    from little_loops.issue_parser import find_issues

    edges_arg: str = getattr(args, "edges", "all")
    status_arg: str = getattr(args, "status", "active")

    edge_types = _resolve_edge_types(edges_arg)
    status_set = _resolve_status_set(status_arg)

    issues = find_issues(config, status_filter=status_set)
    if not issues:
        print("No active issues found.")
        return 0

    neighbours = _build_neighbour_map(issues, edge_types)
    issues_map = {issue.issue_id: issue for issue in issues}
    components = _get_components(neighbours)

    include_orphans: bool = getattr(args, "include_orphans", False)
    if not include_orphans:
        components = [c for c in components if len(c) > 1]

    min_conn: int = getattr(args, "min_connections", 0) or 0
    if min_conn > 0:

        def _max_degree(comp: list[str]) -> int:
            return max(len(neighbours.get(id_, set())) for id_ in comp)

        components = [c for c in components if _max_degree(c) >= min_conn]

    if not components:
        all_components = _get_components(neighbours)
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
            edges = _cluster_edges(comp_set, issues, edge_types)
            output.append(
                {
                    "cluster_index": idx,
                    "issue_count": len(comp),
                    "issues": [
                        {
                            "id": id_,
                            "priority": issues_map[id_].priority,
                            "title": issues_map[id_].title,
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
    total_issues = sum(len(c) for c in components)

    # Build blocked_by map from IssueInfo for topo sort ordering
    blocked_by_map: dict[str, set[str]] = {
        issue.issue_id: set(issue.blocked_by) for issue in issues
    }

    for idx, comp in enumerate(components, 1):
        comp_set = set(comp)
        edges = _cluster_edges(comp_set, issues, edge_types)
        edge_map: dict[tuple[str, str], str] = {(f, t): r for f, t, r in edges}

        ordered, has_cycle = _topo_sort_cluster(comp, blocked_by_map)

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

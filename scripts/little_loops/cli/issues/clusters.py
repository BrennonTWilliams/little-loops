"""ll-issues clusters: Render issue relationship clusters as box diagrams."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, deque
from dataclasses import dataclass
from typing import TYPE_CHECKING

from little_loops.cli.output import (
    BOX_BL,
    BOX_ML,
    BOX_V,
    PRIORITY_COLOR,
    TYPE_COLOR,
    colorize,
    print_json,
    warning,
)

if TYPE_CHECKING:
    from little_loops.config import BRConfig
    from little_loops.issue_parser import IssueInfo

# ANSI color codes per relationship type
EDGE_COLOR: dict[str, str] = {
    "blocks": "31",  # red
    "blocked_by": "33",  # yellow
    "parent": "34",  # blue
    "depends_on": "35",  # magenta
    "relates_to": "37",  # white/dim
}

# Human-readable meaning per relationship type, shown in the legend
_EDGE_MEANING: dict[str, str] = {
    "blocked_by": "source is blocked by target",
    "blocks": "source blocks target",
    "parent": "source's parent epic is target",
    "depends_on": "source soft-depends on target",
    "relates_to": "source relates to target",
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

# Regexes for shared-palette colorization of rendered text lines
_PRIORITY_TAG_RE = re.compile(r"\[(P[0-5])\]")
_ISSUE_ID_RE = re.compile(r"\b(BUG|FEAT|ENH|EPIC)-\d+\b")


@dataclass
class _ClusterRenderData:
    """Precomputed render inputs for one cluster.

    Attributes:
        index: 1-based cluster index as printed in the header
        ids: Issue IDs in the cluster (component order)
        ordered_ids: Issue IDs in topo-sorted render order
        edges: Directed edges within the cluster as (from_id, to_id, relationship)
        has_cycle: True when the cluster's dependency edges contain a cycle
    """

    index: int
    ids: list[str]
    ordered_ids: list[str]
    edges: list[tuple[str, str, str]]
    has_cycle: bool


def _plural(n: int, word: str) -> str:
    """Return *word* pluralized with a trailing ``s`` when *n* != 1."""
    return word if n == 1 else word + "s"


def _colorize_ids(line: str) -> str:
    """Colorize ``[Pn]`` tags and issue IDs in *line* via the shared palettes.

    Uses ``PRIORITY_COLOR`` / ``TYPE_COLOR`` from ``cli/output.py`` so cluster
    output honours the user's configured theme, ``config.color``, and
    ``NO_COLOR``. Applied to fully rendered lines only — ANSI escapes are
    zero-width on screen, so box alignment is unaffected.
    """
    line = _PRIORITY_TAG_RE.sub(
        lambda m: colorize(m.group(0), PRIORITY_COLOR.get(m.group(1), "0")),
        line,
    )
    return _ISSUE_ID_RE.sub(
        lambda m: colorize(m.group(0), TYPE_COLOR.get(m.group(1), "0")),
        line,
    )


def _cluster_header(
    cd: _ClusterRenderData,
    issues_map: dict[str, IssueInfo],
    neighbours: dict[str, set[str]],
) -> str:
    """Build the enriched per-cluster header line (ENH-2336).

    In addition to the cluster index and issue count, shows the hub issue
    (max-degree node, multi-issue clusters only), priority spread
    (e.g. ``P2×1 P3×4``), blocked-status count, edge count, and an inline
    cycle flag.
    """
    sep = "─" * 3
    n = len(cd.ids)
    parts = [f"Cluster {cd.index} ({n} {_plural(n, 'issue')})"]

    if n > 1:
        hub = min(cd.ids, key=lambda id_: (-len(neighbours.get(id_, set())), id_))
        parts.append(f"hub {hub}")

    counts = Counter(issues_map[id_].priority for id_ in cd.ids)
    parts.append(" ".join(f"{p}×{counts[p]}" for p in sorted(counts)))

    blocked_n = sum(1 for id_ in cd.ids if issues_map[id_].status == "blocked")
    if blocked_n:
        parts.append(f"{blocked_n} blocked")

    parts.append(f"{len(cd.edges)} {_plural(len(cd.edges), 'edge')}")
    if cd.has_cycle:
        parts.append("cycle")

    return f"{sep} {' · '.join(parts)} {sep}"


def _render_cluster_compact(
    ordered_ids: list[str],
    issues_map: dict[str, IssueInfo],
    edges: list[tuple[str, str, str]],
) -> list[str]:
    """Render a cluster as one line per issue with its outgoing edge annotations.

    Format: ``[P3] ENH-2191  depends_on→ ENH-2184, ENH-2185``. Relationship
    labels carry the same ``EDGE_COLOR`` coloring as the box-diagram notation;
    orphans (no edges) render as a bare ``[Pn] ID`` line.
    """
    out_edges: dict[str, dict[str, list[str]]] = {}
    for from_id, to_id, rel in edges:
        out_edges.setdefault(from_id, {}).setdefault(rel, []).append(to_id)

    lines: list[str] = []
    for iid in ordered_ids:
        issue = issues_map[iid]
        line = f"[{issue.priority}] {iid}"
        rel_map = out_edges.get(iid, {})
        if rel_map:
            annotations = " · ".join(
                colorize(rel, EDGE_COLOR.get(rel, "37")) + "→ " + ", ".join(sorted(targets))
                for rel, targets in sorted(
                    rel_map.items(), key=lambda kv: _EDGE_PRIORITY.get(kv[0], 99)
                )
            )
            line += f"  {annotations}"
        lines.append(_colorize_ids(line))
    return lines


def _render_cluster_tree(
    ordered_ids: list[str],
    issues_map: dict[str, IssueInfo],
    edges: list[tuple[str, str, str]],
) -> list[str]:
    """Render a cluster as a multi-root indented dependency tree (FEAT-2337).

    Generalizes ``dependency_mapper.formatting.format_epic_tree``'s single-root
    ``├──``/``└──`` connector idiom to the cluster's multi-root case. Every edge
    in ``edges`` appears in the primary layout — either as a tree branch or, when
    both endpoints are already placed (DAG cross-edge / cycle back-edge), as a
    ``⤷`` cross-reference annotation under the node. Nothing is demoted to a
    trailing skip-edge list, so hub topologies keep all their structure.

    Roots are chosen by descending degree (the hub heuristic from
    ``_cluster_header``), tie-broken by topo order, so an EPIC with many
    ``parent`` children renders with the hub at the root and depth shown
    naturally. Cycles terminate safely via the ``visited`` set.
    """
    adj: dict[str, set[str]] = {id_: set() for id_ in ordered_ids}
    # frozenset pair → (from_id, to_id, relationship) for annotation lookup
    rel_of: dict[frozenset[str], tuple[str, str, str]] = {}
    for from_id, to_id, rel in edges:
        if from_id in adj and to_id in adj:
            adj[from_id].add(to_id)
            adj[to_id].add(from_id)
            rel_of[frozenset({from_id, to_id})] = (from_id, to_id, rel)

    order_index = {id_: i for i, id_ in enumerate(ordered_ids)}

    def _annot(parent: str, child: str) -> str:
        """Colored relationship label with a direction arrow relative to *parent*."""
        from_id, _to_id, rel = rel_of[frozenset({parent, child})]
        arrow = "→" if from_id == parent else "←"
        return f"{arrow} {colorize(rel, EDGE_COLOR.get(rel, '37'))}"

    def _node_label(iid: str) -> str:
        issue = issues_map[iid]
        return f"[{issue.priority}] {iid}  {issue.title}"

    visited: set[str] = set()
    rendered_edges: set[frozenset[str]] = set()
    lines: list[str] = []

    def _walk(node: str, child_prefix: str) -> None:
        neigh = sorted(adj[node], key=lambda x: order_index[x])
        children = [c for c in neigh if c not in visited]
        cross = [c for c in neigh if c in visited and frozenset({node, c}) not in rendered_edges]

        for c in cross:
            rendered_edges.add(frozenset({node, c}))
            lines.append(f"{child_prefix}⤷ {_annot(node, c)} {c}")

        for c in children:
            visited.add(c)
            rendered_edges.add(frozenset({node, c}))

        for i, c in enumerate(children):
            is_last = i == len(children) - 1
            connector = BOX_BL if is_last else BOX_ML
            extension = "    " if is_last else BOX_V + "   "
            lines.append(f"{child_prefix}{connector}── {_node_label(c)}  {_annot(node, c)}")
            _walk(c, child_prefix + extension)

    while True:
        unvisited = [id_ for id_ in ordered_ids if id_ not in visited]
        if not unvisited:
            break
        root = min(unvisited, key=lambda x: (-len(adj[x]), order_index[x]))
        visited.add(root)
        lines.append(_node_label(root))
        _walk(root, "")

    return [_colorize_ids(ln) for ln in lines]


def _print_legend(present_types: set[str]) -> None:
    """Print a ``Key:`` block for the edge types present in the rendered output.

    Modeled on ``refine_status._print_key``. Only edge types actually rendered
    are listed; under ``NO_COLOR`` the legend still prints, sans color.
    """
    if not present_types:
        return
    print("Key:")
    for rel in sorted(present_types, key=lambda r: _EDGE_PRIORITY.get(r, 99)):
        label = colorize(f"{rel:<12}", EDGE_COLOR.get(rel, "37"))
        print(f"  {label} {_EDGE_MEANING.get(rel, '')}")


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
            if existing is None or _EDGE_PRIORITY.get(rel, 99) < _EDGE_PRIORITY.get(
                existing[2], 99
            ):
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
    # Arrow head direction matches the semantic edge direction, not the
    # topo-sort layout order: ▼ when top→bottom matches the edge, ▲ when
    # the edge goes bottom→top (reverse of the visual stack).
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
                forward = (a_id, b_id) in edge_map
                grid[gap_row + 1][center_col] = "▼" if forward else "▲"
            color = EDGE_COLOR.get(rel, "37")
            arrow_labels[gap_row] = colorize(f" {rel}", color)

    # Convert grid to string lines, appending annotations after arrow rows.
    # Shared-palette colorization happens on the finished line so ANSI escapes
    # never enter the character grid (they would corrupt box alignment).
    lines: list[str] = []
    for r, row_chars in enumerate(grid):
        line = _colorize_ids("".join(row_chars).rstrip())
        if r in arrow_labels:
            line += arrow_labels[r]
        lines.append(line)

    while lines and not lines[-1].strip():
        lines.pop()

    # Append annotations for skip-level edges (non-consecutive in topo order).
    # Same visual language as inline edges: plain arrow, colored relationship
    # label after the edge.
    pos = {id_: i for i, id_ in enumerate(ordered_ids)}
    skip_edges = [(f, t, r) for (f, t), r in sorted(edge_map.items()) if abs(pos[t] - pos[f]) > 1]
    if skip_edges:
        lines.append("")
        for src, dst, rel in skip_edges:
            color = EDGE_COLOR.get(rel, "37")
            lines.append(_colorize_ids(f"  {src} → {dst}") + " " + colorize(rel, color))

    return lines


def cmd_clusters(config: BRConfig, args: argparse.Namespace) -> int:
    """Render issue relationship clusters as box diagrams.

    Args:
        config: Project configuration (provides issue directories and CLI settings)
        args: Parsed CLI args (include_orphans, min_connections, json, edges,
            status, cluster, limit, compact)

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

    # Scoping (ENH-2336): --cluster selects the Nth cluster (1-indexed,
    # matching the printed numbering); --limit caps how many are rendered.
    # Original indices are preserved so headers and JSON cluster_index values
    # stay stable under scoping.
    indexed: list[tuple[int, list[str]]] = list(enumerate(components, 1))

    cluster_n: int | None = getattr(args, "cluster", None)
    if cluster_n is not None:
        if cluster_n < 1 or cluster_n > len(indexed):
            print(
                f"Error: --cluster {cluster_n} is out of range "
                f"({len(indexed)} {_plural(len(indexed), 'cluster')} available)",
                file=sys.stderr,
            )
            return 1
        indexed = [indexed[cluster_n - 1]]

    suppressed = 0
    limit: int | None = getattr(args, "limit", None)
    if limit is not None:
        if limit < 1:
            print("Error: --limit must be >= 1", file=sys.stderr)
            return 1
        if len(indexed) > limit:
            suppressed = len(indexed) - limit
            indexed = indexed[:limit]

    # JSON mode: emit structured data, no diagram rendering
    if getattr(args, "json", False):
        output = []
        for idx, comp in indexed:
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
    total_issues = sum(len(comp) for _, comp in indexed)

    # Layout resolution (FEAT-2337): --layout {tree,list,boxes} with tree as the
    # new default. --compact/--summary is retained as an alias for --layout list
    # (the ENH-2336 compact renderer) so there is a single compact path; an
    # explicit --layout wins over --compact.
    layout: str | None = getattr(args, "layout", None)
    if layout is None:
        layout = "list" if getattr(args, "compact", False) else "tree"

    # Build blocked_by map from IssueInfo for topo sort ordering
    blocked_by_map: dict[str, set[str]] = {
        issue.issue_id: set(issue.blocked_by) for issue in issues
    }

    # Precompute per-cluster edges and topo order so the overview header and
    # legend can report aggregate data before the per-cluster detail dump.
    clusters_data: list[_ClusterRenderData] = []
    for idx, comp in indexed:
        comp_set = set(comp)
        edges = _cluster_edges(comp_set, issues, edge_types)
        ordered, has_cycle = _topo_sort_cluster(comp, blocked_by_map)
        clusters_data.append(_ClusterRenderData(idx, comp, ordered, edges, has_cycle))

    total_edges = sum(len(cd.edges) for cd in clusters_data)
    cycle_count = sum(1 for cd in clusters_data if cd.has_cycle)
    present_types = {rel for cd in clusters_data for _, _, rel in cd.edges}

    n_clusters = len(indexed)

    # Active-filter echo + aggregate overview, printed before the detail dump
    print(f"edges={edges_arg} · status={status_arg} · min-connections={min_conn}")
    print(
        f"{n_clusters} {_plural(n_clusters, 'cluster')} · "
        f"{total_issues} {_plural(total_issues, 'issue')} · "
        f"{total_edges} {_plural(total_edges, 'edge')} · "
        f"{cycle_count} {_plural(cycle_count, 'cycle')}"
    )
    print()
    _print_legend(present_types)
    print()

    for cd in clusters_data:
        print(_cluster_header(cd, issues_map, neighbours))
        if cd.has_cycle:
            warning("cycle detected — using fallback layout")

        if layout == "list":
            body_lines = _render_cluster_compact(cd.ordered_ids, issues_map, cd.edges)
        elif layout == "boxes":
            edge_map: dict[tuple[str, str], str] = {(f, t): r for f, t, r in cd.edges}
            body_lines = _render_cluster_diagram(cd.ordered_ids, issues_map, edge_map, box_w)
        else:  # tree (default)
            body_lines = _render_cluster_tree(cd.ordered_ids, issues_map, cd.edges)
        print("\n".join(body_lines))
        print()

    footer = (
        f"{n_clusters} {_plural(n_clusters, 'cluster')}, "
        f"{total_issues} {_plural(total_issues, 'issue')} total"
    )
    if suppressed:
        footer += f" ({suppressed} {_plural(suppressed, 'cluster')} suppressed by --limit)"
    print(footer)
    return 0

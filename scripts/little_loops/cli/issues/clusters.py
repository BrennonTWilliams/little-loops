"""ll-issues clusters: Render issue relationship clusters as box diagrams."""

from __future__ import annotations

import argparse
import re
import sys
from collections import Counter, deque
from dataclasses import dataclass, field
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

# ENH-3431: normalized-direction legend, shown once ordering edges are present.
# needs = hard ordering (blocked_by/blocks, must finish first), prefers = weak
# ordering (depends_on), ~ = undirected annotation (relates_to/parent).
_WAVES_LEGEND: list[tuple[str, str]] = [
    ("needs", "predecessor must finish first (blocked_by / blocks)"),
    ("prefers", "predecessor should finish first (depends_on)"),
    ("~", "related, not an ordering fact (relates_to / parent)"),
]

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

# ENH-3431: per-category dedup priorities. Ordering edges are deduped per
# *ordered* (from, to) pair (so both directions of a 2-cycle survive as
# distinct edges); annotation edges are deduped per unordered pair.
_ORDERING_PRIORITY: dict[str, int] = {"blocked_by": 0, "blocks": 1, "depends_on": 2}
_ANNOTATION_PRIORITY: dict[str, int] = {"parent": 0, "relates_to": 1}

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
        waves: 1-indexed wave (longest-path depth) per issue ID; None for the
            unresolved (cycle + downstream) bucket
        normalized_edges: Ordering edges as (before, after, strength)
        ready: Issue IDs with no non-terminal blocker anywhere in the project
        stale_blocked: Issue IDs with status=blocked but no active blocker
        has_ordering_edges: True when any blocked_by/blocks/depends_on edge
            is present (gates hub-vs-start header/root selection)
    """

    index: int
    ids: list[str]
    ordered_ids: list[str]
    edges: list[tuple[str, str, str]]
    has_cycle: bool
    waves: dict[str, int | None] = field(default_factory=dict)
    normalized_edges: list[tuple[str, str, str]] = field(default_factory=list)
    ready: set[str] = field(default_factory=set)
    stale_blocked: set[str] = field(default_factory=set)
    has_ordering_edges: bool = False


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
    """Build the enriched per-cluster header line (ENH-2336, re-gated by ENH-3431).

    In addition to the cluster index and issue count, shows either the start
    issue(s) and wave count (clusters with ordering edges) or the hub issue
    (max-degree node, pure parent/relates_to clusters — the FEAT-2337
    EPIC-hierarchy case), priority spread (e.g. ``P2×1 P3×4``), blocked-status
    count, edge count, and an inline cycle flag.
    """
    sep = "─" * 3
    n = len(cd.ids)
    parts = [f"Cluster {cd.index} ({n} {_plural(n, 'issue')})"]

    if n > 1:
        if cd.has_ordering_edges:
            starts = sorted(id_ for id_ in cd.ids if cd.waves.get(id_) == 1)
            if len(starts) == 1:
                parts.append(f"start {starts[0]}")
            else:
                parts.append(f"{len(starts)} start")
            n_waves = max((w for w in cd.waves.values() if w is not None), default=0)
            parts.append(f"{n_waves} {_plural(n_waves, 'wave')}")
        else:
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


def _render_cluster_waves(
    cd: _ClusterRenderData,
    issues_map: dict[str, IssueInfo],
) -> list[str]:
    """Render a cluster grouped by wave (ENH-3431's new default layout).

    Reading top-down is reading implementation order: wave 1 has no
    in-cluster prerequisite, later waves print their own ``needs``
    (predecessor) and ``unblocks`` (successor) lists per line so the legend
    is never required to interpret the diagram. ``~`` lists undirected
    ``relates_to``/``parent`` partners. *issues_map* must cover every ID this
    cluster's issues might reference as a blocker — including issues outside
    the cluster or the ``--status`` filter — so the ``⏳ waits on`` detail can
    resolve an external blocker's status.
    """
    id_set = set(cd.ids)
    succ: dict[str, set[str]] = {i: set() for i in cd.ids}
    preds: dict[str, set[str]] = {i: set() for i in cd.ids}
    for before, after, _strength in cd.normalized_edges:
        if before in id_set and after in id_set:
            succ[before].add(after)
            preds[after].add(before)

    annotations: dict[str, set[str]] = {i: set() for i in cd.ids}
    for from_id, to_id, rel in cd.edges:
        if rel in ("relates_to", "parent") and from_id in id_set and to_id in id_set:
            annotations[from_id].add(to_id)
            annotations[to_id].add(from_id)

    def _sort_key(iid: str) -> tuple[str, str, str]:
        anchor = min({iid} | annotations.get(iid, set()))
        return (anchor, issues_map[iid].priority, iid)

    lines: list[str] = []
    max_wave = max((w for w in cd.waves.values() if w is not None), default=0)

    for wave_n in range(1, max_wave + 1):
        members = sorted((i for i in cd.ids if cd.waves.get(i) == wave_n), key=_sort_key)
        if not members:
            continue
        header = f"Wave {wave_n}"
        if wave_n == 1:
            header += "  (no in-cluster prerequisite)"
        lines.append(header)

        for iid in members:
            issue = issues_map[iid]
            line = f"  [{issue.priority}] {iid}  {issue.title}"
            if iid in cd.ready:
                line += "   ready"
            if iid in cd.stale_blocked:
                line += "   ⚠ status is blocked but no active blockers"
            lines.append(line)

            needs = sorted(preds.get(iid, set()))
            if needs:
                lines.append(f"                 needs {', '.join(needs)}")
            unblocks = sorted(succ.get(iid, set()))
            if unblocks:
                lines.append(f"                 unblocks {', '.join(unblocks)}")
            related = sorted(annotations.get(iid, set()))
            if related:
                lines.append(f"                 ~ {', '.join(related)}")
            if iid not in cd.ready:
                src = issues_map[iid]
                blockers = sorted(set(src.blocked_by) | set(src.depends_on))
                waiting = [(b, issues_map[b].status) for b in blockers if b in issues_map]
                if waiting:
                    detail = ", ".join(f"{b} ({status})" for b, status in waiting)
                    lines.append(f"                 ⏳ waits on {detail}")
        lines.append("")

    if cd.has_cycle:
        unresolved = sorted(i for i in cd.ids if cd.waves.get(i) is None)
        if unresolved:
            lines.append("Unresolved (cycle)")
            for iid in unresolved:
                issue = issues_map[iid]
                lines.append(f"  [{issue.priority}] {iid}  {issue.title}")
            lines.append("")

    while lines and not lines[-1].strip():
        lines.pop()

    return [_colorize_ids(ln) for ln in lines]


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
    cd: _ClusterRenderData,
    issues_map: dict[str, IssueInfo],
) -> list[str]:
    """Render a cluster as a multi-root indented dependency tree (FEAT-2337, re-rooted by ENH-3431).

    Generalizes ``dependency_mapper.formatting.format_epic_tree``'s single-root
    ``├──``/``└──`` connector idiom to the cluster's multi-root case. Every edge
    appears in the primary layout — either as a tree branch or, when both
    endpoints are already placed (DAG cross-edge / cycle back-edge), as a
    ``⤷`` cross-reference annotation under the node. Nothing is demoted to a
    trailing skip-edge list, so hub topologies keep all their structure.

    Root selection is gated on ``cd.has_ordering_edges``:

    - No ordering edges (pure ``parent``/``relates_to`` cluster, the FEAT-2337
      EPIC-hierarchy case): unchanged hub-root heuristic — descending degree,
      topo-order tie-break — walking every edge as a branch, annotated with
      the original arrow-relative-to-parent notation.
    - Ordering edges present: roots are the wave-1 issues (topo order), walked
      over "before" edges only. ``relates_to`` — and, as a documented
      simplification of the mixed EPIC case, ``parent`` — never become tree
      branches here; they always render as ``⤷ ~`` cross-reference annotations
      (see the issue's Deviations note for the full mixed-case rule this
      narrows). Any node the wave-1 walk never reaches (e.g. a cycle with no
      wave-1 member) still renders via the hub-heuristic fallback so nothing
      is dropped.
    """
    ordered_ids = cd.ordered_ids
    edges = cd.edges
    has_ordering = cd.has_ordering_edges
    id_set = set(ordered_ids)
    order_index = {id_: i for i, id_ in enumerate(ordered_ids)}

    def _node_label(iid: str) -> str:
        issue = issues_map[iid]
        label = f"[{issue.priority}] {iid}  {issue.title}"
        if has_ordering and iid in cd.ready:
            label += "  ready"
        return label

    visited: set[str] = set()
    rendered_edges: set[frozenset[str]] = set()
    lines: list[str] = []

    if not has_ordering:
        # Legacy hub-root walk (FEAT-2337), verbatim: undirected adjacency over
        # every edge, hub-degree root selection, arrow-relative-to-parent
        # annotations inline on the branch itself.
        walk_adj: dict[str, set[str]] = {id_: set() for id_ in ordered_ids}
        rel_of: dict[frozenset[str], tuple[str, str, str]] = {}
        for from_id, to_id, rel in edges:
            if from_id not in id_set or to_id not in id_set:
                continue
            rel_of[frozenset({from_id, to_id})] = (from_id, to_id, rel)
            walk_adj[from_id].add(to_id)
            walk_adj[to_id].add(from_id)

        def _annot(parent: str, child: str) -> str:
            # BUG-3411: `from_id == parent` looks walk-relative but is not — for
            # a two-node edge, parent/child always partition {from_id, to_id},
            # so this is mathematically equivalent to `to_id == child`. The
            # arrow already reflects the edge's fixed from_id/to_id direction;
            # a hub that is from_id for one neighbor and to_id for another
            # correctly gets opposite glyphs across those edges — not a flip bug.
            from_id, _to_id, rel = rel_of[frozenset({parent, child})]
            arrow = "→" if from_id == parent else "←"
            return f"{arrow} {colorize(rel, EDGE_COLOR.get(rel, '37'))}"

        def _walk_hub(node: str, child_prefix: str) -> None:
            neigh = sorted(walk_adj[node], key=lambda x: order_index[x])
            children = [c for c in neigh if c not in visited]
            cross = [
                c for c in neigh if c in visited and frozenset({node, c}) not in rendered_edges
            ]

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
                _walk_hub(c, child_prefix + extension)

        while True:
            unvisited = [id_ for id_ in ordered_ids if id_ not in visited]
            if not unvisited:
                break
            hub = min(unvisited, key=lambda x: (-len(walk_adj[x]), order_index[x]))
            visited.add(hub)
            lines.append(_node_label(hub))
            _walk_hub(hub, "")

        return [_colorize_ids(ln) for ln in lines]

    # Ordering-edge re-root (ENH-3431): walk strictly forward over "before"
    # edges so an unvisited *predecessor* (e.g. a second wave-1 root sharing a
    # downstream child) is never mistaken for a walkable child — only true
    # successors extend the tree. relates_to/parent annotations are excluded
    # from the walk entirely and rendered as grouped `⤷ ~` lines instead.
    succ: dict[str, set[str]] = {id_: set() for id_ in ordered_ids}
    ordering_rel_of: dict[frozenset[str], tuple[str, str, str]] = {}
    annotation_partners: dict[str, dict[str, list[str]]] = {}
    for from_id, to_id, rel in edges:
        if from_id not in id_set or to_id not in id_set:
            continue
        if rel in ("relates_to", "parent"):
            annotation_partners.setdefault(from_id, {}).setdefault(rel, []).append(to_id)
            annotation_partners.setdefault(to_id, {}).setdefault(rel, []).append(from_id)
        else:
            succ[from_id if rel == "blocks" else to_id].add(to_id if rel == "blocks" else from_id)
            ordering_rel_of[frozenset({from_id, to_id})] = (from_id, to_id, rel)

    def _annot_ordering(parent: str, child: str) -> str:
        from_id, _to_id, rel = ordering_rel_of[frozenset({parent, child})]
        arrow = "→" if from_id == parent else "←"
        return f"{arrow} {colorize(rel, EDGE_COLOR.get(rel, '37'))}"

    def _annotation_lines(node: str, prefix: str) -> None:
        for rel, partners in sorted(annotation_partners.get(node, {}).items()):
            unrendered = sorted(p for p in partners if frozenset({node, p}) not in rendered_edges)
            for p in unrendered:
                rendered_edges.add(frozenset({node, p}))
            if unrendered:
                label = colorize(rel, EDGE_COLOR.get(rel, "37"))
                lines.append(f"{prefix}⤷ ~ {label} {', '.join(unrendered)}")

    def _walk(node: str, child_prefix: str) -> None:
        neigh = sorted(succ[node], key=lambda x: order_index[x])
        children = [c for c in neigh if c not in visited]
        cross = [c for c in neigh if c in visited and frozenset({node, c}) not in rendered_edges]

        for c in cross:
            rendered_edges.add(frozenset({node, c}))
            lines.append(f"{child_prefix}⤷ {_annot_ordering(node, c)} {c}")
        _annotation_lines(node, child_prefix)

        for c in children:
            visited.add(c)

        for i, c in enumerate(children):
            is_last = i == len(children) - 1
            connector = BOX_BL if is_last else BOX_ML
            extension = "    " if is_last else BOX_V + "   "
            lines.append(f"{child_prefix}{connector}── {_node_label(c)}")
            _walk(c, child_prefix + extension)

    roots = [id_ for id_ in ordered_ids if cd.waves.get(id_) == 1]
    for root in roots:
        if root in visited:
            continue
        visited.add(root)
        lines.append(_node_label(root))
        _walk(root, "")

    # Fallback for leftovers a wave-1 walk never reaches (e.g. a cycle with no
    # wave-1 member): same hub heuristic as the no-ordering path, scoped to
    # whatever ordering edges exist among the remaining nodes.
    fallback_adj: dict[str, set[str]] = {id_: set() for id_ in ordered_ids}
    for pair in ordering_rel_of:
        a, b = tuple(pair)
        fallback_adj[a].add(b)
        fallback_adj[b].add(a)
    while True:
        unvisited = [id_ for id_ in ordered_ids if id_ not in visited]
        if not unvisited:
            break
        hub = min(unvisited, key=lambda x: (-len(fallback_adj[x]), order_index[x]))
        visited.add(hub)
        lines.append(_node_label(hub))
        _walk(hub, "")

    return [_colorize_ids(ln) for ln in lines]


def _print_legend(present_types: set[str]) -> None:
    """Print a ``Key:`` block for the ordering/annotation categories present (ENH-3431).

    Shrunk from one line per raw relationship type to three normalized-
    direction categories: ``needs`` (hard: blocked_by/blocks), ``prefers``
    (weak: depends_on), ``~`` (relates_to/parent — undirected, no ordering).
    Only categories actually present are listed; under ``NO_COLOR`` the
    legend still prints, sans color.
    """
    if not present_types:
        return
    has_needs = bool(present_types & {"blocked_by", "blocks"})
    has_prefers = "depends_on" in present_types
    has_annotation = bool(present_types & {"relates_to", "parent"})
    gates = {"needs": has_needs, "prefers": has_prefers, "~": has_annotation}
    entries = [(label, meaning) for label, meaning in _WAVES_LEGEND if gates[label]]
    if not entries:
        return
    print("Key:")
    for label, meaning in entries:
        color = EDGE_COLOR.get("blocked_by" if label == "needs" else "depends_on", "37")
        colored = colorize(f"{label:<12}", color if label != "~" else "37")
        print(f"  {colored} {meaning}")


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


def _normalize_edges(edges: list[tuple[str, str, str]]) -> list[tuple[str, str, str]]:
    """Map ordering-relationship edges to a single "before" direction (ENH-3431).

    ``X blocked_by Y``, ``Y blocks X``, and ``X depends_on Y`` all mean "Y
    before X" — collapsed here to ``(before, after, strength)`` where
    ``strength`` is ``hard`` for ``blocked_by``/``blocks`` and ``weak`` for
    ``depends_on``. ``relates_to``/``parent`` are undirected annotations, not
    ordering facts, and are excluded from the result entirely.
    """
    normalized: list[tuple[str, str, str]] = []
    for from_id, to_id, rel in edges:
        if rel == "blocked_by":
            normalized.append((to_id, from_id, "hard"))
        elif rel == "blocks":
            normalized.append((from_id, to_id, "hard"))
        elif rel == "depends_on":
            normalized.append((to_id, from_id, "weak"))
    return normalized


def _order_and_waves(
    ids: list[str],
    normalized: list[tuple[str, str, str]],
) -> tuple[list[str], dict[str, int | None], bool]:
    """Single Kahn's-algorithm + longest-path pass over normalized ordering edges.

    Returns ``(ordered_ids, waves, has_cycle)`` so the topo order used by
    ``list``/``boxes``/``tree`` and the wave numbers used by ``waves``/JSON can
    never disagree — both come from this one call. ``waves`` is 1-indexed
    longest-path depth; cycle members *and* anything downstream of a cycle
    (nodes that never reach in-degree 0) get ``wave=None`` and are appended,
    in sorted-ID order, to the end of ``ordered_ids``.
    """
    id_set = set(ids)
    succ: dict[str, set[str]] = {i: set() for i in ids}
    preds: dict[str, set[str]] = {i: set() for i in ids}
    for before, after, _strength in normalized:
        if before in id_set and after in id_set and before != after:
            succ[before].add(after)
            preds[after].add(before)

    in_degree = {i: len(preds[i]) for i in ids}
    working = dict(in_degree)
    queue: deque[str] = deque(sorted(i for i in ids if in_degree[i] == 0))
    topo: list[str] = []

    while queue:
        node = queue.popleft()
        topo.append(node)
        for nxt in sorted(succ[node]):
            working[nxt] -= 1
            if working[nxt] == 0:
                queue.append(nxt)

    has_cycle = len(topo) < len(ids)

    depth: dict[str, int] = {}
    for node in topo:
        resolved = [depth[p] for p in preds[node] if p in depth]
        depth[node] = (max(resolved) + 1) if resolved else 0

    waves: dict[str, int | None] = {
        node: (depth[node] + 1 if node in depth else None) for node in ids
    }
    unresolved = sorted(i for i in ids if i not in depth)
    ordered_ids = topo + unresolved

    return ordered_ids, waves, has_cycle


def _ready_ids(
    ids: list[str],
    issues_map: dict[str, IssueInfo],
    non_terminal_ids: set[str],
) -> tuple[set[str], set[str]]:
    """Compute per-issue readiness and stale-blocked flags (ENH-3431).

    An issue is ``ready`` when every ID in its raw ``blocked_by``/``depends_on``
    (regardless of ``--edges`` or cluster membership — a blocker outside the
    cluster or outside the ``--status`` filter still counts) is absent from
    *non_terminal_ids* (i.e. terminal, or not present in the project at all).
    ``stale_blocked`` flags a ``status: blocked`` issue whose blockers are all
    terminal — the reverse signal.
    """
    ready: set[str] = set()
    stale_blocked: set[str] = set()
    for iid in ids:
        issue = issues_map[iid]
        blockers = set(issue.blocked_by) | set(issue.depends_on)
        if not (blockers & non_terminal_ids):
            ready.add(iid)
            if issue.status == "blocked":
                stale_blocked.add(iid)
    return ready, stale_blocked


def _cluster_edges(
    cluster_ids: set[str],
    issues: list[IssueInfo],
    edge_types: set[str],
) -> list[tuple[str, str, str]]:
    """Return directed edges within a cluster as (from_id, to_id, relationship).

    Per-category dedup (ENH-3431): each unordered pair may keep one *ordering*
    edge (blocked_by > blocks > depends_on) and one *annotation* edge
    (parent > relates_to) — previously ``parent`` outranked ``depends_on`` and
    silently dropped the ordering fact.

    Ordering dedup is two-staged so a genuine 2-cycle survives as two edges
    while a same-fact reciprocal declaration (e.g. "A blocks B" + "B
    blocked_by A", the common convention in this codebase) still collapses to
    one: stage 1 dedups literal ``(from, to)`` pairs by relationship priority
    (resolving a single issue declaring contradictory relations to the same
    target); stage 2 merges the survivors that normalize to the identical
    ``(before, after)`` fact. Two raw edges that normalize to *different*
    directions — the 2-cycle case — are never merged.
    """
    issues_in_cluster = {i.issue_id: i for i in issues if i.issue_id in cluster_ids}
    ordering_raw: dict[tuple[str, str], tuple[str, str, str]] = {}
    annotation_best: dict[frozenset[str], tuple[str, str, str]] = {}

    for iid in sorted(cluster_ids):
        issue = issues_in_cluster.get(iid)
        if not issue:
            continue

        ordering_candidates: list[tuple[str, str, str]] = []
        if "blocked_by" in edge_types:
            for t in sorted(issue.blocked_by):
                if t in cluster_ids:
                    ordering_candidates.append((iid, t, "blocked_by"))
        if "blocks" in edge_types:
            for t in sorted(issue.blocks):
                if t in cluster_ids:
                    ordering_candidates.append((iid, t, "blocks"))
        if "depends_on" in edge_types:
            for t in sorted(issue.depends_on):
                if t in cluster_ids:
                    ordering_candidates.append((iid, t, "depends_on"))

        for from_id, to_id, rel in ordering_candidates:
            key = (from_id, to_id)
            existing = ordering_raw.get(key)
            if existing is None or _ORDERING_PRIORITY[rel] < _ORDERING_PRIORITY[existing[2]]:
                ordering_raw[key] = (from_id, to_id, rel)

        annotation_candidates: list[tuple[str, str, str]] = []
        if "relates_to" in edge_types:
            for t in sorted(issue.relates_to):
                if t in cluster_ids:
                    annotation_candidates.append((iid, t, "relates_to"))
        if "parent" in edge_types and issue.parent and issue.parent in cluster_ids:
            annotation_candidates.append((iid, issue.parent, "parent"))

        for from_id, to_id, rel in annotation_candidates:
            akey = frozenset({from_id, to_id})
            existing_a = annotation_best.get(akey)
            if (
                existing_a is None
                or _ANNOTATION_PRIORITY[rel] < _ANNOTATION_PRIORITY[existing_a[2]]
            ):
                annotation_best[akey] = (from_id, to_id, rel)

    ordering_best: dict[tuple[str, str], tuple[str, str, str]] = {}
    for from_id, to_id, rel in ordering_raw.values():
        before, after, _strength = _normalize_edges([(from_id, to_id, rel)])[0]
        norm_key = (before, after)
        existing_n = ordering_best.get(norm_key)
        if existing_n is None or _ORDERING_PRIORITY[rel] < _ORDERING_PRIORITY[existing_n[2]]:
            ordering_best[norm_key] = (from_id, to_id, rel)

    return list(ordering_best.values()) + list(annotation_best.values())


def _render_cluster_diagram(
    ordered_ids: list[str],
    issues_map: dict[str, IssueInfo],
    normalized_edges: list[tuple[str, str, str]],
    box_width: int,
) -> list[str]:
    """Render a cluster as a vertical stack of box diagrams with arrows (ENH-3431).

    Uses _draw_box from cli/loop/layout.py as the box primitive. Since
    *ordered_ids* is already the normalized topo order, a "before" edge
    between consecutive nodes is always top-to-bottom — every connector is
    ``▼`` labelled ``needs``; ``relates_to``/``parent`` annotations never
    occupy an arrow slot (only ordering edges are considered here). A
    skip-level "before" edge (non-adjacent in the stack) is folded into the
    source box's own content as an ``unblocks:`` line instead of a trailing
    external annotation, so nothing is demoted out of the primary layout.
    """
    # Intentional cross-module import of a private primitive; _draw_box is
    # reusable and has no FSM-specific logic when is_highlighted=False.
    from little_loops.cli.loop.layout import _draw_box

    n = len(ordered_ids)
    id_set = set(ordered_ids)
    pos = {id_: i for i, id_ in enumerate(ordered_ids)}
    succ: dict[str, set[str]] = {id_: set() for id_ in ordered_ids}
    for before, after, _strength in normalized_edges:
        if before in id_set and after in id_set:
            succ[before].add(after)

    avail = box_width - 4  # interior width minus side margins
    box_contents: list[list[str]] = []
    box_heights: list[int] = []
    for issue_id in ordered_ids:
        issue = issues_map[issue_id]
        title = issue.title if len(issue.title) <= avail else issue.title[: avail - 1] + "…"
        content = [f"[{issue.priority}] {issue_id}", title]
        skip_targets = sorted(
            (t for t in succ[issue_id] if pos[t] - pos[issue_id] > 1), key=lambda t: pos[t]
        )
        if skip_targets:
            note = "unblocks: " + ", ".join(skip_targets)
            if len(note) > avail:
                note = note[: avail - 1] + "…"
            content.append(note)
        box_contents.append(content)
        box_heights.append(len(content) + 2)  # top + bottom border

    grid_h = sum(box_heights) + max(0, n - 1) * _GAP_HEIGHT
    grid_w = box_width + _BOX_MARGIN * 2 + 2
    grid: list[list[str]] = [[" "] * grid_w for _ in range(grid_h)]

    center_col = _BOX_MARGIN + box_width // 2
    box_start: dict[str, int] = {}
    row = 0
    for issue_id, content, height in zip(ordered_ids, box_contents, box_heights, strict=True):
        _draw_box(grid, row, _BOX_MARGIN, box_width, height, content, False, "0")
        box_start[issue_id] = row
        row += height + _GAP_HEIGHT

    # Connector between consecutive stack positions: always ▼/needs, since
    # ordered_ids already respects normalized "before" direction.
    arrow_labels: dict[int, str] = {}
    for i in range(n - 1):
        a_id = ordered_ids[i]
        b_id = ordered_ids[i + 1]
        gap_row = box_start[a_id] + box_heights[i]

        if b_id in succ[a_id]:
            if gap_row < grid_h:
                grid[gap_row][center_col] = "│"
            if gap_row + 1 < grid_h:
                grid[gap_row + 1][center_col] = "▼"
            arrow_labels[gap_row] = colorize(" needs", EDGE_COLOR.get("blocked_by", "37"))

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
    from little_loops.issue_parser import find_issues, find_issues_for_graph

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

    # Readiness superset (BUG-2897 pattern, ENH-3431): a blocker that is
    # deferred, filtered out, or a dangling ID must still count against
    # readiness, so this is loaded once regardless of --status and consulted
    # only for the wave-1 ready/stale_blocked computation and the JSON/waves
    # ⏳ blocker-status lookup — never for the displayed issue list itself.
    graph_issues = find_issues_for_graph(config)
    non_terminal_ids = {i.issue_id for i in graph_issues}
    lookup_map: dict[str, IssueInfo] = {i.issue_id: i for i in graph_issues}
    lookup_map.update(issues_map)

    # Precompute per-cluster edges/order/waves/readiness so JSON, the header,
    # and every layout share one answer (ENH-3431 item 2).
    clusters_data: list[_ClusterRenderData] = []
    for idx, comp in indexed:
        comp_set = set(comp)
        edges = _cluster_edges(comp_set, issues, edge_types)
        normalized = _normalize_edges(edges)
        ordered, waves, has_cycle = _order_and_waves(comp, normalized)
        ready, stale_blocked = _ready_ids(comp, issues_map, non_terminal_ids)
        has_ordering_edges = any(rel in _HARD_EDGE_TYPES for _, _, rel in edges)
        clusters_data.append(
            _ClusterRenderData(
                idx,
                comp,
                ordered,
                edges,
                has_cycle,
                waves,
                normalized,
                ready,
                stale_blocked,
                has_ordering_edges,
            )
        )

    # JSON mode: emit structured data, no diagram rendering
    if getattr(args, "json", False):
        output = []
        for cd in clusters_data:
            output.append(
                {
                    "cluster_index": cd.index,
                    "issue_count": len(cd.ids),
                    "issues": [
                        {
                            "id": id_,
                            "priority": issues_map[id_].priority,
                            "title": issues_map[id_].title,
                            "wave": cd.waves.get(id_),
                            "ready": id_ in cd.ready,
                        }
                        for id_ in sorted(cd.ids)
                    ],
                    "edges": [{"from": f, "to": t, "relationship": r} for f, t, r in cd.edges],
                    "normalized_edges": [
                        {"before": b, "after": a, "strength": s} for b, a, s in cd.normalized_edges
                    ],
                }
            )
        print_json(output)
        return 0

    # Text rendering
    width = terminal_width()
    box_w = max(20, min(_MAX_BOX_WIDTH, width - _BOX_MARGIN * 2 - 4))
    total_issues = sum(len(comp) for _, comp in indexed)

    # Layout resolution (FEAT-2337, default changed to `waves` by ENH-3431):
    # --layout {waves,tree,list,boxes}. --compact/--summary is retained as an
    # alias for --layout list (the ENH-2336 compact renderer) so there is a
    # single compact path; an explicit --layout wins over --compact.
    layout: str | None = getattr(args, "layout", None)
    if layout is None:
        layout = "list" if getattr(args, "compact", False) else "waves"

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
            body_lines = _render_cluster_diagram(
                cd.ordered_ids, issues_map, cd.normalized_edges, box_w
            )
        elif layout == "tree":
            body_lines = _render_cluster_tree(cd, issues_map)
        else:  # waves (default)
            body_lines = _render_cluster_waves(cd, lookup_map)
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

"""FSM diagram layout engine.

Implements adaptive layout for FSM diagrams using a Sugiyama-inspired
layered graph drawing approach. Supports topology detection, vertical
linear chains, side-by-side branching, and margin back-edge rendering.

Extracted from info.py and extended with adaptive layout capabilities.
"""

from __future__ import annotations

import re
from collections import deque

from wcwidth import wcswidth as _wcswidth
from wcwidth import wcwidth as _wcwidth

from little_loops.cli.output import colorize, terminal_width
from little_loops.fsm.schema import FSMLoop, StateConfig

# ---------------------------------------------------------------------------
# Edge label colorization
# ---------------------------------------------------------------------------

_EDGE_LABEL_COLORS: dict[str, str] = {
    "yes": "32",
    "no": "38;5;208",
    "error": "31",
    "partial": "33",
    "next": "2",
    "_": "2",
}


def _colorize_label(label: str) -> str:
    """Colorize a (possibly compound) edge label like 'no/error'."""
    parts = label.split("/")
    code = ""
    for part in parts:
        if part in ("no", "error"):
            code = _EDGE_LABEL_COLORS["no"]
            break
        if part == "partial" and not code:
            code = _EDGE_LABEL_COLORS["partial"]
        elif part == "yes" and not code:
            code = _EDGE_LABEL_COLORS["yes"]
        elif part in ("next", "_") and not code:
            code = _EDGE_LABEL_COLORS["next"]
    return colorize(label, code) if code else label


def _colorize_diagram_labels(diagram: str) -> str:
    """Apply ANSI color to known edge labels in a rendered diagram string.

    Labels are colorized only when bounded by box-drawing or whitespace chars
    to avoid coloring partial matches inside state names.
    """
    for label, code in _EDGE_LABEL_COLORS.items():
        colored = colorize(label, code)
        diagram = re.sub(
            r"(?<=[─ │▶\n])" + re.escape(label) + r"(?=[─ │▶\n])",
            colored,
            diagram,
        )
    return diagram


# ---------------------------------------------------------------------------
# State box badge definitions
# ---------------------------------------------------------------------------

_ACTION_TYPE_BADGES: dict[str, str] = {
    "prompt": "\u2726",  # ✦
    "slash_command": "/\u2501\u25ba",  # /━►
    "shell": "\u276f_",  # ❯_
    "mcp_tool": "\u26a1",  # ⚡
}

_SUB_LOOP_BADGE = "\u21b3\u27f3"  # ↳⟳
_ROUTE_BADGE = "\u2443"  # ⑃


def _badge_display_width(badge: str) -> int:
    """Compute terminal display width of a badge string using wcwidth."""
    w = _wcswidth(badge)
    return w if w >= 0 else len(badge)


def _get_state_badge(state: StateConfig | None) -> str:
    """Return the unicode badge string for a state, or '' if none."""
    if state is None:
        return ""
    if state.loop is not None:
        return _SUB_LOOP_BADGE
    if state.action_type:
        return _ACTION_TYPE_BADGES.get(state.action_type, f"[{state.action_type}]")
    if state.action:
        return _ACTION_TYPE_BADGES["shell"]
    if state.route is not None:
        return _ROUTE_BADGE
    return ""


# ---------------------------------------------------------------------------
# Box content helpers for multi-row diagram boxes
# ---------------------------------------------------------------------------


def _box_inner_lines(
    state: StateConfig | None,
    display_label: str,
    verbose: bool,
    inner_width: int,
) -> list[str]:
    """Return interior lines for a state box (between top and bottom borders).

    The first line is always ``display_label`` + type badge (if any).
    Subsequent lines are action content lines.  All lines fit within
    ``inner_width`` characters (content is truncated or wrapped accordingly).
    """
    # Badge is now rendered in the top-right corner by _draw_box; name row is label only
    name_line = display_label[:inner_width]

    lines: list[str] = [name_line]

    # Action lines
    if state and state.action:
        action_src = [ln.rstrip() for ln in state.action.strip().splitlines()]
        if verbose:
            for src in action_src:
                if not src:
                    continue
                # Wrap long lines to inner_width
                while len(src) > inner_width:
                    lines.append(src[:inner_width])
                    src = src[inner_width:]
                if src:
                    lines.append(src)
        else:
            # Show first non-empty line, truncated
            first = next((ln for ln in action_src if ln), "")
            if len(first) > inner_width:
                first = first[: inner_width - 1] + "\u2026"
            if first:
                lines.append(first)

    return lines


# ---------------------------------------------------------------------------
# Topology detection
# ---------------------------------------------------------------------------


def _collect_edges(fsm: FSMLoop) -> list[tuple[str, str, str]]:
    """Collect all (source, target, label) edges from an FSM."""
    edges: list[tuple[str, str, str]] = []
    for name, state in fsm.states.items():
        if state.on_yes:
            edges.append((name, state.on_yes, "yes"))
        if state.on_no:
            edges.append((name, state.on_no, "no"))
        if state.on_error:
            edges.append((name, state.on_error, "error"))
        if state.on_partial:
            edges.append((name, state.on_partial, "partial"))
        if state.next:
            edges.append((name, state.next, "next"))
        if state.route:
            for verdict, target in state.route.routes.items():
                edges.append((name, target, verdict))
            if state.route.default:
                edges.append((name, state.route.default, "_"))
    return edges


def _bfs_order(initial: str, edges: list[tuple[str, str, str]]) -> tuple[list[str], dict[str, int]]:
    """BFS from initial state. Returns (order, depth_map)."""
    order: list[str] = []
    depth: dict[str, int] = {initial: 0}
    queue: deque[str] = deque([initial])
    while queue:
        node = queue.popleft()
        order.append(node)
        for src, dst, _ in edges:
            if src == node and dst not in depth:
                depth[dst] = depth[node] + 1
                queue.append(dst)
    return order, depth


def _trace_main_path(
    fsm: FSMLoop, edges: list[tuple[str, str, str]]
) -> tuple[list[str], set[tuple[str, str]]]:
    """Trace the main (happy) path through the FSM."""
    visited: set[str] = set()
    main_path: list[str] = []
    main_edge_set: set[tuple[str, str]] = set()
    current = fsm.initial
    while current and current not in visited:
        visited.add(current)
        main_path.append(current)
        st = fsm.states.get(current)
        if not st or st.terminal:
            break
        nxt: str = st.on_yes or st.next or ""
        if not nxt and st.route:
            nxt = next(iter(st.route.routes.values()), "") or st.route.default or ""
        if nxt:
            main_edge_set.add((current, nxt))
            current = nxt
        else:
            break
    return main_path, main_edge_set


def _classify_edges(
    edges: list[tuple[str, str, str]],
    main_edge_set: set[tuple[str, str]],
    bfs_order: list[str],
) -> tuple[list[tuple[str, str, str]], list[tuple[str, str, str]]]:
    """Split non-main edges into branches and back_edges."""
    main_consumed: set[int] = set()
    for src, dst in main_edge_set:
        for i, (s, d, _) in enumerate(edges):
            if s == src and d == dst and i not in main_consumed:
                main_consumed.add(i)
                break

    branches: list[tuple[str, str, str]] = []
    back_edges: list[tuple[str, str, str]] = []
    for i, (src, dst, label) in enumerate(edges):
        if i in main_consumed:
            continue
        src_pos = bfs_order.index(src) if src in bfs_order else len(bfs_order)
        dst_pos = bfs_order.index(dst) if dst in bfs_order else len(bfs_order)
        if dst == src or dst_pos < src_pos:
            back_edges.append((src, dst, label))
        else:
            branches.append((src, dst, label))
    return branches, back_edges


class TopologyDetector:
    """Classify FSM graph topology for layout strategy selection."""

    def __init__(
        self,
        edges: list[tuple[str, str, str]],
        main_path: list[str],
        branches: list[tuple[str, str, str]],
        back_edges: list[tuple[str, str, str]],
    ) -> None:
        self._edges = edges
        self._main_path = main_path
        self._branches = branches
        self._back_edges = back_edges

    def classify(self) -> str:
        """Return 'linear', 'tree', or 'general'.

        Linear: main path only, no non-self branches, only self-loop back-edges.
        Tree: branches exist but no fan-in (every non-initial state has ≤1 incoming).
        General: everything else (full Sugiyama needed).
        """
        non_self_branches = [b for b in self._branches if b[0] != b[1]]
        non_self_back = [b for b in self._back_edges if b[0] != b[1]]

        if not non_self_branches and not non_self_back:
            return "linear"

        # Check for fan-in: any state with >1 incoming forward edge
        in_count: dict[str, int] = {}
        for _, dst, _ in self._edges:
            # Only count forward edges (not back-edges)
            in_count[dst] = in_count.get(dst, 0) + 1

        if not non_self_back and all(v <= 1 for v in in_count.values()):
            return "tree"

        return "general"


# ---------------------------------------------------------------------------
# Sugiyama layout pipeline
# ---------------------------------------------------------------------------


class LayerAssigner:
    """Assign nodes to layers using longest-path + width constraint."""

    def __init__(
        self,
        all_states: list[str],
        edges: list[tuple[str, str, str]],
        back_edge_set: set[tuple[str, str]],
        initial: str,
        max_width: int = 4,
    ) -> None:
        self._all_states = all_states
        self._edges = edges
        self._back_edge_set = back_edge_set
        self._initial = initial
        self._max_width = max_width

    def assign(self) -> list[list[str]]:
        """Return list of layers, each a list of state names (top to bottom)."""
        # Build adjacency (forward edges only)
        forward: dict[str, list[str]] = {s: [] for s in self._all_states}
        reverse: dict[str, list[str]] = {s: [] for s in self._all_states}
        seen_edges: set[tuple[str, str]] = set()
        for src, dst, _ in self._edges:
            if (src, dst) in self._back_edge_set or src == dst:
                continue
            if src in forward and dst in forward and (src, dst) not in seen_edges:
                forward[src].append(dst)
                reverse[dst].append(src)
                seen_edges.add((src, dst))

        # Longest-path layer assignment (topological order)
        layer_of: dict[str, int] = {}

        # Kahn's algorithm for topological order
        in_degree = {s: len(reverse[s]) for s in self._all_states}
        queue: deque[str] = deque()
        for s in self._all_states:
            if in_degree[s] == 0:
                queue.append(s)

        topo_order: list[str] = []
        while queue:
            node = queue.popleft()
            topo_order.append(node)
            for dst in forward[node]:
                in_degree[dst] -= 1
                if in_degree[dst] == 0:
                    queue.append(dst)

        # Handle nodes not reached by topo sort (cycles in forward graph)
        for s in self._all_states:
            if s not in set(topo_order):
                topo_order.append(s)

        # Assign layers: longest path from root
        for node in topo_order:
            if not reverse[node]:
                layer_of[node] = 0
            else:
                layer_of[node] = max(
                    (layer_of.get(p, 0) + 1 for p in reverse[node]),
                    default=0,
                )

        # Ensure initial state is at layer 0
        if self._initial in layer_of and layer_of[self._initial] != 0:
            offset = layer_of[self._initial]
            for s in layer_of:
                layer_of[s] -= offset

        # Build layers list
        max_layer = max(layer_of.values(), default=0)
        layers: list[list[str]] = [[] for _ in range(max_layer + 1)]
        for s in self._all_states:
            layer = layer_of.get(s, 0)
            layers[layer].append(s)

        # Width constraint: if any layer exceeds max_width, split
        if self._max_width > 0:
            new_layers: list[list[str]] = []
            for grp in layers:
                remaining = list(grp)
                while len(remaining) > self._max_width:
                    new_layers.append(remaining[: self._max_width])
                    remaining = remaining[self._max_width :]
                if remaining:
                    new_layers.append(remaining)
            layers = new_layers

        return layers


class CrossingMinimizer:
    """Minimize edge crossings using barycenter heuristic."""

    def __init__(
        self,
        layers: list[list[str]],
        edges: list[tuple[str, str, str]],
        back_edge_set: set[tuple[str, str]],
    ) -> None:
        self._layers = layers
        self._edges = edges
        self._back_edge_set = back_edge_set

    def minimize(self) -> list[list[str]]:
        """Return reordered layers with reduced crossings."""
        # Build position lookup
        layer_of: dict[str, int] = {}
        for i, layer in enumerate(self._layers):
            for s in layer:
                layer_of[s] = i

        # Forward adjacency (non-back, non-self)
        adj_down: dict[str, list[str]] = {}
        adj_up: dict[str, list[str]] = {}
        for src, dst, _ in self._edges:
            if (src, dst) in self._back_edge_set or src == dst:
                continue
            if src in layer_of and dst in layer_of:
                adj_down.setdefault(src, []).append(dst)
                adj_up.setdefault(dst, []).append(src)

        layers = [list(layer) for layer in self._layers]

        # 3 sweeps: down, up, down
        for sweep in range(3):
            if sweep % 2 == 0:
                # Top-down sweep
                for i in range(1, len(layers)):
                    pos_above = {s: j for j, s in enumerate(layers[i - 1])}
                    bary: dict[str, float] = {}
                    for s in layers[i]:
                        parents = [p for p in adj_up.get(s, []) if p in pos_above]
                        if parents:
                            bary[s] = sum(pos_above[p] for p in parents) / len(parents)
                        else:
                            bary[s] = float(layers[i].index(s))
                    layers[i].sort(key=lambda s: bary.get(s, 0))
            else:
                # Bottom-up sweep
                for i in range(len(layers) - 2, -1, -1):
                    pos_below = {s: j for j, s in enumerate(layers[i + 1])}
                    bary_up: dict[str, float] = {}
                    for s in layers[i]:
                        children = [c for c in adj_down.get(s, []) if c in pos_below]
                        if children:
                            bary_up[s] = sum(pos_below[c] for c in children) / len(children)
                        else:
                            bary_up[s] = float(layers[i].index(s))
                    layers[i].sort(key=lambda s: bary_up.get(s, 0))

        return layers


# ---------------------------------------------------------------------------
# Rendering helpers
# ---------------------------------------------------------------------------


def _compute_display_labels(
    all_states: list[str],
    initial: str,
    terminal_states: set[str],
) -> dict[str, str]:
    """Compute display labels with → prefix and ◉ suffix."""
    display_label: dict[str, str] = {}
    for s in all_states:
        label = s
        if s == initial:
            label = "\u2192 " + label
        if s in terminal_states:
            label = label + " \u25c9"
        display_label[s] = label
    return display_label


def _compute_box_sizes(
    all_states: list[str],
    display_label: dict[str, str],
    fsm_states: dict[str, StateConfig] | None,
    verbose: bool,
    max_box_inner: int,
) -> tuple[dict[str, list[str]], dict[str, int], dict[str, int], dict[str, str]]:
    """Compute box content, widths, and heights for all states.

    Returns (box_inner, box_width, box_height, box_badge).
    """
    box_inner: dict[str, list[str]] = {}
    box_width: dict[str, int] = {}
    box_badge: dict[str, str] = {}

    for s in all_states:
        state_obj = fsm_states.get(s) if fsm_states else None

        badge = _get_state_badge(state_obj)
        badge_w = _badge_display_width(badge) if badge else 0
        box_badge[s] = badge

        # Width must fit: name label on content row, badge on top border (with one space
        # of padding on each side: " badge ")
        base_w = max(len(display_label[s]), badge_w + 2 if badge_w else 0)

        inner_w = base_w
        if state_obj and state_obj.action and max_box_inner > 0:
            action_lines = state_obj.action.strip().splitlines()
            if verbose:
                max_action_w = max(
                    (len(ln.rstrip()) for ln in action_lines if ln.rstrip()), default=0
                )
                inner_w = max(base_w, min(max_action_w, max_box_inner))
            else:
                first_action = next((ln.rstrip() for ln in action_lines if ln.rstrip()), "")
                inner_w = max(base_w, min(len(first_action), max_box_inner))

        content = _box_inner_lines(state_obj, display_label[s], verbose, inner_w)
        actual_w = max(len(ln) for ln in content)
        inner_w = max(inner_w, actual_w)
        box_inner[s] = content
        box_width[s] = inner_w + 4  # "│ " + content + " │"

    box_height: dict[str, int] = {s: len(box_inner[s]) + 2 for s in all_states}
    return box_inner, box_width, box_height, box_badge


def _draw_box(
    grid: list[list[str]],
    row: int,
    col: int,
    width: int,
    height: int,
    content: list[str],
    is_highlighted: bool,
    highlight_color: str,
    badge: str = "",
) -> None:
    """Draw a state box onto a character grid at (row, col).

    If *badge* is provided it is placed right-aligned in the top border row with
    one space of padding on each side (``─ badge ┐``), colorized via ``_bc()``.
    """
    total_width = len(grid[0]) if grid else 0

    def _bc(ch: str) -> str:
        return colorize(ch, highlight_color) if is_highlighted else ch

    # Top border: ┌ ─ ─ … ─ ┐
    if col < total_width:
        grid[row][col] = _bc("\u250c")
    for j in range(1, width - 1):
        if col + j < total_width:
            grid[row][col + j] = _bc("\u2500")
    if col + width - 1 < total_width:
        grid[row][col + width - 1] = _bc("\u2510")

    # Overlay badge in top-right corner with one space of padding on each side: " badge ┐"
    if badge:
        badge_w = _badge_display_width(badge)
        # Trailing space between badge end and ┐
        trail_pos = col + width - 2
        if col + 1 <= trail_pos < col + width - 1 and trail_pos < total_width:
            grid[row][trail_pos] = _bc(" ")
        # Leading space before badge
        lead_pos = col + width - badge_w - 3
        if col + 1 <= lead_pos < col + width - 1 and lead_pos < total_width:
            grid[row][lead_pos] = _bc(" ")
        # Badge characters (shifted left by 1 compared to no-padding placement)
        pos = col + width - 1 - badge_w - 1
        for ch in badge:
            ch_w = _wcwidth(ch)
            if ch_w < 1:
                ch_w = 1
            if col + 1 <= pos < col + width - 1 and pos < total_width:
                grid[row][pos] = _bc(ch)
                if ch_w == 2 and pos + 1 < col + width - 1 and pos + 1 < total_width:
                    grid[row][pos + 1] = ""
            pos += ch_w

    # Content rows
    for i, line in enumerate(content):
        r = row + i + 1
        if r >= len(grid):
            break
        if col < total_width:
            grid[r][col] = _bc("\u2502")
        if col + width - 1 < total_width:
            grid[r][col + width - 1] = _bc("\u2502")
        if is_highlighted and i == 0:
            colored_line = colorize(line, f"{highlight_color};1")
            if col + 2 < total_width:
                grid[r][col + 2] = colored_line
            for j in range(1, len(line)):
                if col + 2 + j < col + width - 1:
                    grid[r][col + 2 + j] = ""
        else:
            for j, ch in enumerate(line):
                if col + 2 + j < col + width - 1:
                    grid[r][col + 2 + j] = ch

    # Padding rows between content and bottom border
    for i in range(len(content) + 1, height - 1):
        r = row + i
        if r >= len(grid):
            break
        if col < total_width:
            grid[r][col] = _bc("\u2502")
        if col + width - 1 < total_width:
            grid[r][col + width - 1] = _bc("\u2502")

    # Bottom border
    brow = row + height - 1
    if brow < len(grid):
        if col < total_width:
            grid[brow][col] = _bc("\u2514")
        for j in range(1, width - 1):
            if col + j < total_width:
                grid[brow][col + j] = _bc("\u2500")
        if col + width - 1 < total_width:
            grid[brow][col + width - 1] = _bc("\u2518")


# ---------------------------------------------------------------------------
# Layered (vertical) renderer
# ---------------------------------------------------------------------------


def _render_layered_diagram(
    layers: list[list[str]],
    edges: list[tuple[str, str, str]],
    main_edge_set: set[tuple[str, str]],
    branches: list[tuple[str, str, str]],
    back_edges: list[tuple[str, str, str]],
    initial: str,
    terminal_states: set[str] | None,
    fsm_states: dict[str, StateConfig] | None,
    verbose: bool,
    highlight_state: str | None,
    highlight_color: str,
) -> str:
    """Render FSM using layered (Sugiyama-style) vertical layout."""
    terminal_states = terminal_states or set()
    fsm_states = fsm_states or {}
    tw = terminal_width()

    # Flatten layers to get all states
    all_states = [s for layer in layers for s in layer]
    if not all_states:
        return ""

    display_label = _compute_display_labels(all_states, initial, terminal_states)

    # Compute max_box_inner based on widest layer
    max_layer_size = max(len(layer) for layer in layers)
    if verbose:
        max_box_inner = max(20, min(60, (tw - 4) // max(1, max_layer_size) - 6))
    else:
        max_box_inner = max(20, min(40, (tw - 4) // max(1, max_layer_size) - 6))

    box_inner, box_width, box_height, box_badge = _compute_box_sizes(
        all_states, display_label, fsm_states, verbose, max_box_inner
    )

    # Post-hoc layer merge: re-merge adjacent single-state layers that were
    # over-split by the conservative max_width_per_layer estimate.  Only merge
    # when both layers receive an edge from the same source state (indicating
    # they were originally one layer split by width constraint).
    available_w = tw - 20  # conservative content-area estimate
    gap_between = 6
    # Build edge target sets: for each state, which earlier states point to it
    _incoming: dict[str, set[str]] = {s: set() for layer in layers for s in layer}
    for src, dst, _ in edges:
        if src != dst and dst in _incoming:
            _incoming[dst].add(src)
    merged = True
    while merged:
        merged = False
        i = 0
        while i < len(layers) - 1:
            la, lb = layers[i], layers[i + 1]
            # Only merge single-state layers that share an incoming source
            if len(la) == 1 and len(lb) == 1:
                sources_a = _incoming.get(la[0], set())
                sources_b = _incoming.get(lb[0], set())
                shared_source = sources_a & sources_b
            else:
                shared_source = set()
            combined_w = (
                sum(box_width[s] for s in la)
                + gap_between * (len(la) - 1)
                + gap_between
                + sum(box_width[s] for s in lb)
                + gap_between * (len(lb) - 1)
            )
            if shared_source and combined_w <= available_w and len(la) + len(lb) <= 4:
                layers[i] = la + lb
                layers.pop(i + 1)
                merged = True
            else:
                i += 1

    # Collect ALL non-self-loop forward edge labels (main + branches + same-depth back-edges)
    # Multiple edges between the same pair are combined as "label1/label2"
    forward_edge_labels: dict[tuple[str, str], str] = {}
    for src, dst, lbl in edges:
        if src == dst:
            continue
        if (src, dst) in main_edge_set or (src, dst, lbl) in branches:
            if (src, dst) in forward_edge_labels:
                forward_edge_labels[(src, dst)] += "/" + lbl
            else:
                forward_edge_labels[(src, dst)] = lbl

    # True back-edges: only those going to an earlier layer (computed after layer assignment)
    # Will be finalized below after col positions are computed
    # Combine same-pair back-edges into single entries with merged labels (e.g. "error/fail")
    back_edge_labels_initial: dict[tuple[str, str], str] = {}
    for s, d, lbl in back_edges:
        if s != d:
            if (s, d) in back_edge_labels_initial:
                back_edge_labels_initial[(s, d)] += "/" + lbl
            else:
                back_edge_labels_initial[(s, d)] = lbl

    # Pre-compute layer positions to detect main-path cycle edges early.
    # This ensures back_edge_margin accounts for ALL backward-pointing edges
    # (including main-path cycles like commit → initial_state) before column
    # positions are computed.
    prelim_layer_of: dict[str, int] = {}
    for li, layer in enumerate(layers):
        for s in layer:
            prelim_layer_of[s] = li

    # Include main-path/branch edges that point backward in margin estimate
    all_back_labels: dict[tuple[str, str], str] = dict(back_edge_labels_initial)
    for (src, dst), lbl in forward_edge_labels.items():
        src_layer = prelim_layer_of.get(src, -1)
        dst_layer = prelim_layer_of.get(dst, -1)
        if dst_layer < src_layer:
            if (src, dst) in all_back_labels:
                all_back_labels[(src, dst)] += "/" + lbl
            else:
                all_back_labels[(src, dst)] = lbl

    non_self_back_initial = [(s, d, lbl) for (s, d), lbl in all_back_labels.items()]
    back_edge_margin = 0
    if non_self_back_initial:
        max_label_len = max(len(lbl) for _, _, lbl in non_self_back_initial)
        n_back_initial = len(non_self_back_initial)
        back_edge_margin = max_label_len + max(6, 2 * n_back_initial + 2)

    content_left = 2 + back_edge_margin

    # Self-loops per state
    self_loops: dict[str, list[str]] = {}
    for src, dst, lbl in back_edges:
        if src == dst:
            self_loops.setdefault(src, []).append(lbl)

    # --- Compute a common center column for alignment ---
    # For layers with single boxes, we want vertical alignment through a
    # shared center column. Use the widest single-state layer's center.
    max_single_w = max((box_width[layer[0]] for layer in layers if len(layer) == 1), default=0)
    # The common center is at content_left + max_single_w // 2
    common_center = content_left + max_single_w // 2

    # Compute column positions per layer
    col_start: dict[str, int] = {}
    col_center: dict[str, int] = {}
    layer_of: dict[str, int] = {}

    for li, layer in enumerate(layers):
        if len(layer) == 1:
            # Single-state layer: center-align to common center
            sname = layer[0]
            col_start[sname] = common_center - box_width[sname] // 2
            col_center[sname] = common_center
            layer_of[sname] = li
        else:
            # Multi-state layer: place side-by-side, centered around common_center
            gap_between = 6
            total_layer_w = sum(box_width[s] for s in layer) + gap_between * (len(layer) - 1)
            x = common_center - total_layer_w // 2
            x = max(content_left, x)
            for i, sname in enumerate(layer):
                col_start[sname] = x
                col_center[sname] = x + box_width[sname] // 2
                layer_of[sname] = li
                if i < len(layer) - 1:
                    next_s = layer[i + 1]
                    # Check for edge labels in both directions between adjacent states
                    label_fwd = forward_edge_labels.get((sname, next_s), "")
                    label_rev = forward_edge_labels.get((next_s, sname), "")
                    max_label = max(len(label_fwd), len(label_rev))
                    gap = max(gap_between, max_label + 6) if max_label > 0 else gap_between
                    x += box_width[sname] + gap
                else:
                    x += box_width[sname]

    # Reclassify back-edges based on actual layer positions
    # Only edges going to an earlier layer are true margin back-edges
    # Combine same-pair edges into merged labels (e.g. "error/fail")
    back_edge_labels_reclass: dict[tuple[str, str], str] = {}
    same_layer_edges: list[tuple[str, str, str]] = []
    for src, dst, lbl in back_edges:
        if src == dst:
            continue
        src_layer = layer_of.get(src, -1)
        dst_layer = layer_of.get(dst, -1)
        if dst_layer < src_layer:
            if (src, dst) in back_edge_labels_reclass:
                back_edge_labels_reclass[(src, dst)] += "/" + lbl
            else:
                back_edge_labels_reclass[(src, dst)] = lbl
        elif dst_layer == src_layer:
            same_layer_edges.append((src, dst, lbl))
        else:  # dst_layer > src_layer: actually forward edge
            if (src, dst) in forward_edge_labels:
                forward_edge_labels[(src, dst)] += "/" + lbl
            else:
                forward_edge_labels[(src, dst)] = lbl

    # Also reclassify main/branch edges in forward_edge_labels that point backward
    # after layer assignment (e.g. main-path cycle edges like commit → initial_state)
    backward_in_fwd: list[tuple[str, str]] = []
    for (src, dst), lbl in forward_edge_labels.items():
        src_layer = layer_of.get(src, -1)
        dst_layer = layer_of.get(dst, -1)
        if dst_layer < src_layer:
            backward_in_fwd.append((src, dst))
            if (src, dst) in back_edge_labels_reclass:
                back_edge_labels_reclass[(src, dst)] += "/" + lbl
            else:
                back_edge_labels_reclass[(src, dst)] = lbl
        elif dst_layer == src_layer and src != dst:
            backward_in_fwd.append((src, dst))
            same_layer_edges.append((src, dst, lbl))
    for key in backward_in_fwd:
        del forward_edge_labels[key]

    # Add same-layer back-edges to forward_edge_labels so gap calculation accounts for them
    for src, dst, lbl in same_layer_edges:
        if (src, dst) in forward_edge_labels:
            forward_edge_labels[(src, dst)] += "/" + lbl
        else:
            forward_edge_labels[(src, dst)] = lbl

    # Recalculate inter-box gaps for layers with newly discovered same-layer edges
    affected_layers: set[int] = set()
    for src, dst, _lbl in same_layer_edges:
        sl = layer_of.get(src, -1)
        dl = layer_of.get(dst, -1)
        if sl >= 0:
            affected_layers.add(sl)
        if dl >= 0:
            affected_layers.add(dl)
    for li in affected_layers:
        layer = layers[li]
        if len(layer) < 2:
            continue
        gap_between = 6
        total_layer_w = sum(box_width[s] for s in layer)
        # For non-adjacent same-layer edges the label lands in the gap immediately
        # adjacent to the source box (left of src for right-to-left, right of src
        # for left-to-right).  Collect those requirements so the gap is wide enough.
        extra_gap_req: dict[tuple[str, str], int] = {}
        for src, dst, lbl in same_layer_edges:
            if layer_of.get(src) != li or layer_of.get(dst) != li:
                continue
            try:
                si, di = layer.index(src), layer.index(dst)
            except ValueError:
                continue
            if abs(si - di) <= 1:
                continue  # adjacent — already handled by forward_edge_labels
            if si > di:
                key = (layer[si - 1], src)  # gap to the left of src
            else:
                key = (src, layer[si + 1])  # gap to the right of src
            extra_gap_req[key] = max(extra_gap_req.get(key, 0), len(lbl))
        # Recalculate gaps with label-aware spacing
        gaps: list[int] = []
        for i in range(len(layer) - 1):
            sname, next_s = layer[i], layer[i + 1]
            label_fwd = forward_edge_labels.get((sname, next_s), "")
            label_rev = forward_edge_labels.get((next_s, sname), "")
            max_label = max(len(label_fwd), len(label_rev), extra_gap_req.get((sname, next_s), 0))
            gap = max(gap_between, max_label + 6) if max_label > 0 else gap_between
            gaps.append(gap)
        total_layer_w += sum(gaps)
        x = common_center - total_layer_w // 2
        x = max(content_left, x)
        for i, sname in enumerate(layer):
            col_start[sname] = x
            col_center[sname] = x + box_width[sname] // 2
            if i < len(layer) - 1:
                x += box_width[sname] + gaps[i]
            else:
                x += box_width[sname]

    non_self_back = [(s, d, lbl) for (s, d), lbl in back_edge_labels_reclass.items()]

    # Recalculate back-edge margin if it changed
    if non_self_back:
        max_label_len = max(len(lbl) for _, _, lbl in non_self_back)
        n_back = len(non_self_back)
        actual_margin = max_label_len + max(6, 2 * n_back + 2)
        if actual_margin != back_edge_margin:
            # Need to recalculate positions (rare case - usually matches)
            back_edge_margin = actual_margin
            content_left = 2 + back_edge_margin

    # Identify forward skip-layer edges (span > 1 layer, not handled by consecutive renderer)
    skip_forward_edges: list[tuple[str, str, str]] = []
    for (src, dst), lbl in forward_edge_labels.items():
        src_layer = layer_of.get(src, -1)
        dst_layer = layer_of.get(dst, -1)
        if dst_layer > src_layer + 1:
            skip_forward_edges.append((src, dst, lbl))

    # Pre-compute right margin width for forward skip-layer edges
    right_edge_margin = 0
    if skip_forward_edges:
        max_fwd_label_len = max(len(lbl) for _, _, lbl in skip_forward_edges)
        right_edge_margin = max_fwd_label_len + 6

    # Compute total width needed
    total_content_w = 0
    for s in all_states:
        right = col_start[s] + box_width[s]
        total_content_w = max(total_content_w, right)
    total_width = max(total_content_w + right_edge_margin + 4, tw)

    # Compute vertical positions with space for self-loops and inter-layer arrows
    row_start: dict[str, int] = {}
    y = 0
    for li, layer in enumerate(layers):
        layer_h = max(box_height[s] for s in layer)
        for sname in layer:
            row_start[sname] = y
        y += layer_h

        # Add self-loop row if any state in this layer has self-loops
        has_self_loop = any(s in self_loops for s in layer)
        if has_self_loop:
            y += 1  # self-loop marker row

        if li < len(layers) - 1:
            y += 3  # arrow gap: │, label, ▼

    total_height = y

    # Build character grid
    grid: list[list[str]] = [[" "] * total_width for _ in range(total_height)]

    # Draw boxes
    for sname in all_states:
        is_highlighted = highlight_state is not None and sname == highlight_state
        _draw_box(
            grid,
            row_start[sname],
            col_start[sname],
            box_width[sname],
            box_height[sname],
            box_inner[sname],
            is_highlighted,
            highlight_color,
            badge=box_badge[sname],
        )

    # Precompute box-occupied (row, col) pairs so connector lines can avoid overwriting box cells
    _box_occ: dict[int, set[int]] = {}
    for _s in all_states:
        for _r in range(row_start[_s], row_start[_s] + box_height[_s]):
            _row_set = _box_occ.setdefault(_r, set())
            for _c in range(col_start[_s], col_start[_s] + box_width[_s]):
                _row_set.add(_c)

    # Draw self-loop markers immediately below their boxes
    for sname, labels in self_loops.items():
        marker = "\u21ba " + ", ".join(labels)
        r = row_start[sname] + box_height[sname]
        if r < total_height:
            cx = col_center[sname]
            pos = max(0, cx - len(marker) // 2)
            for j, ch in enumerate(marker):
                if pos + j < total_width:
                    grid[r][pos + j] = ch

    # Draw forward edges between layers (vertical arrows with labels)
    for li in range(len(layers) - 1):
        layer_h = max(box_height[s] for s in layers[li])
        has_self_loop = any(s in self_loops for s in layers[li])
        self_loop_offset = 1 if has_self_loop else 0

        # Arrow area starts after box bottom + self-loop row
        arrow_start_row = row_start[layers[li][0]] + layer_h + self_loop_offset
        arrow_end_row = row_start[layers[li + 1][0]] - 1

        # Collect all inter-layer edges from this layer to the next
        inter_edges: list[tuple[str, str, str]] = []
        for src in layers[li]:
            for dst in layers[li + 1]:
                label = forward_edge_labels.get((src, dst))
                if label is not None:
                    inter_edges.append((src, dst, label))

        # Draw each edge with its own vertical pipe to the target's center
        for src, dst, label in inter_edges:
            dst_cc = col_center[dst]
            src_left = col_start[src]
            src_right = src_left + box_width[src]

            # Horizontal connector when pipe is outside source box range
            if dst_cc >= src_right or dst_cc < src_left:
                conn_row = arrow_start_row
                if 0 <= conn_row < total_height:
                    if dst_cc >= src_right:
                        # Pipe right of source: └───┐
                        src_cc = col_center[src]
                        if 0 <= src_cc < total_width and grid[conn_row][src_cc] == " ":
                            grid[conn_row][src_cc] = "\u2514"  # └
                            start_c = src_cc + 1
                        else:
                            start_c = src_right
                        for c in range(start_c, dst_cc):
                            if 0 <= c < total_width:
                                grid[conn_row][c] = "\u2500"
                        if 0 <= dst_cc < total_width:
                            grid[conn_row][dst_cc] = "\u2510"  # ┐
                    else:
                        # Pipe left of source: ┌───┘
                        src_cc = col_center[src]
                        if 0 <= src_cc < total_width and grid[conn_row][src_cc] == " ":
                            end_c = src_cc
                            grid[conn_row][src_cc] = "\u2518"  # ┘
                        else:
                            end_c = src_left
                        for c in range(dst_cc + 1, end_c):
                            if 0 <= c < total_width:
                                grid[conn_row][c] = "\u2500"
                        if 0 <= dst_cc < total_width:
                            grid[conn_row][dst_cc] = "\u250c"  # ┌
                pipe_start = arrow_start_row + 1
            else:
                pipe_start = arrow_start_row

            # Draw vertical pipe at destination's center column
            for r in range(pipe_start, arrow_end_row):
                if 0 <= dst_cc < total_width and r < total_height:
                    grid[r][dst_cc] = "\u2502"

            # Arrow tip at destination center
            if arrow_end_row < total_height and 0 <= dst_cc < total_width:
                grid[arrow_end_row][dst_cc] = "\u25bc"

            # Label to the right of the pipe (or left if it would overlap)
            label_row = arrow_start_row
            if label_row < total_height:
                label_start = dst_cc + 2
                for j, ch in enumerate(label):
                    if label_start + j < total_width:
                        grid[label_row][label_start + j] = ch

        # Post-pass: connect horizontal gaps for multi-branch sources
        if len(inter_edges) >= 2 and 0 <= arrow_start_row < total_height:
            src_targets: dict[str, list[int]] = {}
            for src, dst, _ in inter_edges:
                if dst in col_center:
                    src_targets.setdefault(src, []).append(col_center[dst])
            for _src, centers in src_targets.items():
                if len(centers) < 2:
                    continue
                left = min(centers)
                right = max(centers)
                for c in range(left + 1, right):
                    if 0 <= c < total_width:
                        cell = grid[arrow_start_row][c]
                        if cell == " ":
                            grid[arrow_start_row][c] = "\u2500"  # ─
                        elif cell == "\u2502":  # │ → ┼
                            grid[arrow_start_row][c] = "\u253c"
                        elif cell == "\u2518":  # ┘ → ┴
                            grid[arrow_start_row][c] = "\u2534"
                        elif cell == "\u2514":  # └ → ┴
                            grid[arrow_start_row][c] = "\u2534"
                        elif cell == "\u2510":  # ┐ → ┬
                            grid[arrow_start_row][c] = "\u252c"
                        elif cell == "\u250c":  # ┌ → ┬
                            grid[arrow_start_row][c] = "\u252c"
                # Update boundary junction chars where the horizontal bar meets a pipe
                if 0 <= left < total_width and grid[arrow_start_row][left] == "\u2502":  # │ → ├
                    grid[arrow_start_row][left] = "\u251c"
                if 0 <= right < total_width and grid[arrow_start_row][right] == "\u2502":  # │ → ┤
                    grid[arrow_start_row][right] = "\u2524"

    # Draw same-layer edges (horizontal arrows between states on same layer)
    # Includes both branches and reclassified back-edges within same layer
    all_same_layer: list[tuple[str, str, str]] = list(same_layer_edges)
    for _li, layer in enumerate(layers):
        for i, src in enumerate(layer):
            for j, dst in enumerate(layer):
                if i == j:
                    continue
                label = forward_edge_labels.get((src, dst))
                if label is not None and (src, dst, label) not in all_same_layer:
                    all_same_layer.append((src, dst, label))

    for src, dst, label in all_same_layer:
        if src not in col_start or dst not in col_start:
            continue
        name_row = row_start[src] + 1
        src_right = col_start[src] + box_width[src]
        dst_right = col_start[dst] + box_width[dst]
        dst_left = col_start[dst]
        src_left = col_start[src]
        _row_boxes = _box_occ.get(name_row, set())
        if dst_left >= src_right:
            # Left to right horizontal arrow: src ──label──▶ dst
            start = src_right
            end = dst_left
            edge_text = "\u2500" + label + "\u2500\u2500\u25b6"
            available = end - start
            if available < len(edge_text):
                edge_text = edge_text[: max(1, available)]
            left_dashes = max(0, available - len(edge_text))
            for k in range(left_dashes):
                pos = start + k
                if pos < total_width and name_row < total_height and pos not in _row_boxes:
                    grid[name_row][pos] = "\u2500"
            for k, ch in enumerate(edge_text):
                pos = start + left_dashes + k
                if (
                    0 <= pos < end
                    and pos < total_width
                    and name_row < total_height
                    and pos not in _row_boxes
                ):
                    grid[name_row][pos] = ch
        elif dst_right <= src_left:
            # Right to left: dst is left of src: src → dst drawn as dst ◀──label── src
            start = dst_right
            end = src_left
            edge_text = "\u2500" + label + "\u2500\u2500\u25b6"
            available = end - start
            if available < len(edge_text):
                edge_text = edge_text[: max(1, available)]
            left_dashes = max(0, available - len(edge_text))
            for k in range(left_dashes):
                pos = start + k
                if pos < total_width and name_row < total_height and pos not in _row_boxes:
                    grid[name_row][pos] = "\u2500"
            for k, ch in enumerate(edge_text):
                pos = start + left_dashes + k
                if (
                    0 <= pos < end
                    and pos < total_width
                    and name_row < total_height
                    and pos not in _row_boxes
                ):
                    grid[name_row][pos] = ch

    # Back-edges: left-margin vertical arrows with labels
    if non_self_back:
        sorted_back = sorted(
            non_self_back,
            key=lambda e: abs(row_start.get(e[0], 0) - row_start.get(e[1], 0)),
            reverse=True,
        )
        used_cols: list[int] = []
        # Compute rightmost pipe column so labels go right of ALL pipes
        rightmost_pipe_col = 1 + (len(sorted_back) - 1) * 2

        for src, dst, label in sorted_back:
            # Source: name row of source box; target: name row of target box
            src_row = row_start.get(src, 0) + 1  # name row, not bottom border
            dst_row = row_start.get(dst, 0) + 1  # name row

            # Find a free column in the margin
            col = 1
            for uc in sorted(used_cols):
                if uc == col:
                    col += 2
            used_cols.append(col)

            if col >= content_left - 1:
                continue

            top_row = min(src_row, dst_row)
            bot_row = max(src_row, dst_row)

            # Draw vertical line in margin (exclude corner rows handled below)
            for r in range(top_row + 1, bot_row):
                if 0 <= r < total_height and col < total_width:
                    cell = grid[r][col]
                    if cell == "\u2500":  # ─ → ┼
                        grid[r][col] = "\u253c"
                    elif cell == " ":
                        grid[r][col] = "\u2502"

            # Horizontal connector from source box to margin
            # Draw right-to-left, crossing existing pipes with junction chars
            if 0 <= src_row < total_height:
                src_left = col_start.get(src, col + 1)
                _src_row_boxes = _box_occ.get(src_row, set())
                for c in range(col + 1, src_left):
                    if c < total_width and c not in _src_row_boxes:
                        cell = grid[src_row][c]
                        if cell == " ":
                            grid[src_row][c] = "\u2500"  # ─
                        elif cell == "\u2502":  # │ → ┼
                            grid[src_row][c] = "\u253c"
                        elif cell == "\u2514":  # └ → ┴
                            grid[src_row][c] = "\u2534"
                        elif cell == "\u250c":  # ┌ → ┬
                            grid[src_row][c] = "\u252c"
                        elif cell == "\u251c":  # ├ → ┼
                            grid[src_row][c] = "\u253c"
                        # Leave ─, ▶, box chars unchanged

            # Horizontal connector from margin to target box
            # Draw right-to-left, crossing existing pipes with junction chars
            dst_left = col_start.get(dst, col + 1)
            if 0 <= dst_row < total_height:
                _dst_row_boxes = _box_occ.get(dst_row, set())
                for c in range(col + 1, dst_left):
                    if c < total_width and c not in _dst_row_boxes:
                        cell = grid[dst_row][c]
                        if cell == " ":
                            grid[dst_row][c] = "\u2500"  # ─
                        elif cell == "\u2502":  # │ → ┼
                            grid[dst_row][c] = "\u253c"
                        elif cell == "\u2514":  # └ → ┴
                            grid[dst_row][c] = "\u2534"
                        elif cell == "\u250c":  # ┌ → ┬
                            grid[dst_row][c] = "\u252c"
                        elif cell == "\u251c":  # ├ → ┼
                            grid[dst_row][c] = "\u253c"

            # Corner characters at pipe-to-horizontal turn points
            for row in (src_row, dst_row):
                if 0 <= row < total_height and col < total_width:
                    existing = grid[row][col]
                    if row == bot_row:
                        # Pipe ends, turns right: └; if horizontal already crosses here: ┴
                        grid[row][col] = "\u2534" if existing == "\u2500" else "\u2514"
                    else:  # row == top_row
                        # Pipe starts going down, turns right: ┌; if horizontal already crosses here: ┬
                        grid[row][col] = "\u252c" if existing == "\u2500" else "\u250c"

            # Arrow tip at target: place ▶ at end of horizontal connector (entering box from left)
            if 0 <= dst_row < total_height and dst_left - 1 > col and dst_left - 1 < total_width:
                grid[dst_row][dst_left - 1] = "\u25b6"

            # Label on the margin line (right of ALL pipes, not just this one)
            label_row_pos = (top_row + bot_row) // 2
            if 0 <= label_row_pos < total_height:
                label_start = rightmost_pipe_col + 2
                for j, ch in enumerate(label):
                    if label_start + j < content_left - 1 and label_start + j < total_width:
                        grid[label_row_pos][label_start + j] = ch

    # Forward skip-layer edges: right-margin vertical arrows with labels
    # Symmetric to the left-margin back-edge renderer above
    if skip_forward_edges:
        sorted_fwd_skip = sorted(
            skip_forward_edges,
            key=lambda e: abs(row_start.get(e[0], 0) - row_start.get(e[1], 0)),
            reverse=True,
        )
        used_fwd_cols: list[int] = []
        # Rightmost pipe column (furthest from content) for label placement
        rightmost_fwd_pipe_col = total_content_w + 2 + (len(sorted_fwd_skip) - 1) * 2

        for src, dst, label in sorted_fwd_skip:
            src_row = row_start.get(src, 0) + 1  # name row
            dst_row = row_start.get(dst, 0) + 1  # name row

            # Allocate column in right margin (starting from content edge, going right)
            col = total_content_w + 2
            for uc in sorted(used_fwd_cols):
                if uc == col:
                    col += 2
            used_fwd_cols.append(col)

            if col >= total_width:
                continue

            top_row = min(src_row, dst_row)
            bot_row = max(src_row, dst_row)

            # Draw vertical line in right margin (exclude corner rows handled below)
            for r in range(top_row + 1, bot_row):
                if 0 <= r < total_height and col < total_width:
                    cell = grid[r][col]
                    if cell == "\u2500":  # ─ → ┼
                        grid[r][col] = "\u253c"
                    elif cell == " ":
                        grid[r][col] = "\u2502"

            # Horizontal connector from source box right side to margin
            # Draw left-to-right, crossing existing pipes with junction chars
            src_right = col_start.get(src, 0) + box_width.get(src, 0)
            _src_row_boxes = _box_occ.get(src_row, set())
            if 0 <= src_row < total_height:
                for c in range(src_right, col):
                    if 0 <= c < total_width and c not in _src_row_boxes:
                        cell = grid[src_row][c]
                        if cell == " ":
                            grid[src_row][c] = "\u2500"  # ─
                        elif cell == "\u2502":  # │ → ┼
                            grid[src_row][c] = "\u253c"
                        elif cell == "\u2518":  # ┘ → ┴
                            grid[src_row][c] = "\u2534"
                        elif cell == "\u2510":  # ┐ → ┬
                            grid[src_row][c] = "\u252c"
                        elif cell == "\u2524":  # ┤ → ┼
                            grid[src_row][c] = "\u253c"
                        # Leave ─, ◀, box chars unchanged

            # Horizontal connector from margin to destination box right side
            dst_right = col_start.get(dst, 0) + box_width.get(dst, 0)
            _dst_row_boxes = _box_occ.get(dst_row, set())
            if 0 <= dst_row < total_height:
                for c in range(dst_right, col):
                    if 0 <= c < total_width and c not in _dst_row_boxes:
                        cell = grid[dst_row][c]
                        if cell == " ":
                            grid[dst_row][c] = "\u2500"  # ─
                        elif cell == "\u2502":  # │ → ┼
                            grid[dst_row][c] = "\u253c"
                        elif cell == "\u2518":  # ┘ → ┴
                            grid[dst_row][c] = "\u2534"
                        elif cell == "\u2510":  # ┐ → ┬
                            grid[dst_row][c] = "\u252c"
                        elif cell == "\u2524":  # ┤ → ┼
                            grid[dst_row][c] = "\u253c"

            # Corner characters at pipe-to-horizontal turn points
            for row in (src_row, dst_row):
                if 0 <= row < total_height and col < total_width:
                    existing = grid[row][col]
                    if row == bot_row:
                        # Pipe ends, turns left: ┘; if horizontal crosses: ┤
                        grid[row][col] = "\u2524" if existing == "\u2500" else "\u2518"
                    else:  # row == top_row
                        # Pipe starts going down, turns left: ┐; if horizontal crosses: ┤
                        grid[row][col] = "\u2524" if existing == "\u2500" else "\u2510"

            # Arrow tip at target: ◀ entering box from right side
            if 0 <= dst_row < total_height and dst_right < col and dst_right < total_width:
                grid[dst_row][dst_right] = "\u25c0"

            # Label on the margin line (right of ALL pipes, mirroring left-margin approach)
            label_row_pos = (top_row + bot_row) // 2
            if 0 <= label_row_pos < total_height:
                label_start = rightmost_fwd_pipe_col + 2
                for j, ch in enumerate(label):
                    if label_start + j < total_width:
                        grid[label_row_pos][label_start + j] = ch

    # Convert grid to string
    lines = ["".join(row).rstrip() for row in grid]

    # Remove trailing empty lines
    while lines and not lines[-1].strip():
        lines.pop()

    # Center diagram
    max_line_len = max((len(ln) for ln in lines), default=0)
    diagram_indent = max(0, (tw - max_line_len) // 2)
    if diagram_indent > 0:
        lines = [" " * diagram_indent + ln if ln.strip() else ln for ln in lines]

    return _colorize_diagram_labels("\n".join(lines))


# ---------------------------------------------------------------------------
# FSM diagram renderer (main entry point)
# ---------------------------------------------------------------------------


def _render_fsm_diagram(
    fsm: FSMLoop,
    verbose: bool = False,
    highlight_state: str | None = None,
    highlight_color: str = "32",
) -> str:
    """Render an adaptive text diagram of the FSM graph.

    Detects FSM topology and selects appropriate layout:
    - Linear chains: vertical top-to-bottom
    - Branching/cyclic: layered Sugiyama-style

    Args:
        fsm: The FSM loop to render.
        verbose: If True, show expanded action content in boxes.
        highlight_state: If provided, render this state's box with the highlight color.
        highlight_color: ANSI SGR code for the highlighted state (default: green).
    """
    edges = _collect_edges(fsm)
    bfs_order_list, bfs_depth = _bfs_order(fsm.initial, edges)
    main_path, main_edge_set = _trace_main_path(fsm, edges)
    branches, back_edges = _classify_edges(edges, main_edge_set, bfs_order_list)

    terminal_states = {name for name, state in fsm.states.items() if state.terminal}

    # Collect all states
    all_states = list(main_path)
    for src, dst, _ in branches:
        for s in (src, dst):
            if s not in all_states:
                all_states.append(s)

    # Topology detection
    detector = TopologyDetector(edges, main_path, branches, back_edges)
    topology = detector.classify()

    # Build back-edge set for layout pipeline
    back_edge_set: set[tuple[str, str]] = set()
    for src, dst, _ in back_edges:
        if src != dst:
            back_edge_set.add((src, dst))

    tw = terminal_width()

    if topology == "linear" and len(all_states) <= 1:
        # Single state or empty — use simple horizontal
        return _render_horizontal_simple(
            main_path,
            edges,
            main_edge_set,
            branches,
            back_edges,
            bfs_order_list,
            fsm.initial,
            terminal_states,
            fsm.states,
            verbose,
            highlight_state,
            highlight_color,
        )

    # Compute max node width to determine width constraint
    # Quick estimate: widest state name or badge + padding
    max_node_w = 30  # reasonable default
    for s in all_states:
        st = fsm.states.get(s)
        badge = _get_state_badge(st)
        badge_w = _badge_display_width(badge) if badge else 0
        label = s
        if s == fsm.initial:
            label = "\u2192 " + label
        if s in terminal_states:
            label = label + " \u25c9"
        w = max(len(label), badge_w)
        max_node_w = max(max_node_w, w + 4 + 4)  # inner + borders + padding

    max_width_per_layer = max(1, (tw - 10) // (max_node_w + 4))

    # Layer assignment
    assigner = LayerAssigner(all_states, edges, back_edge_set, fsm.initial, max_width_per_layer)
    layers = assigner.assign()

    # Crossing minimization
    minimizer = CrossingMinimizer(layers, edges, back_edge_set)
    layers = minimizer.minimize()

    return _render_layered_diagram(
        layers,
        edges,
        main_edge_set,
        branches,
        back_edges,
        fsm.initial,
        terminal_states,
        fsm.states,
        verbose,
        highlight_state,
        highlight_color,
    )


def _render_horizontal_simple(
    main_path: list[str],
    edges: list[tuple[str, str, str]],
    main_edge_set: set[tuple[str, str]],
    branches: list[tuple[str, str, str]],
    back_edges: list[tuple[str, str, str]],
    bfs_order: list[str],
    initial: str,
    terminal_states: set[str],
    fsm_states: dict[str, StateConfig],
    verbose: bool,
    highlight_state: str | None,
    highlight_color: str,
) -> str:
    """Simple horizontal rendering for single-state or very simple FSMs."""
    if not main_path:
        return ""

    all_states = list(main_path)
    display_label = _compute_display_labels(all_states, initial, terminal_states)

    tw = terminal_width()
    num_main = max(1, len(main_path))
    if verbose and fsm_states and main_path:
        max_box_inner = max(20, min(60, (tw - 4) // num_main - 6))
    else:
        max_box_inner = max(20, min(40, (tw - 4) // num_main - 6))

    box_inner, box_width, box_height, box_badge = _compute_box_sizes(
        all_states, display_label, fsm_states, verbose, max_box_inner
    )

    main_height = max((box_height[s] for s in main_path), default=3)
    total_width = tw

    # Column positions
    col_start: dict[str, int] = {}
    col_center: dict[str, int] = {}
    x = 2
    for i, sname in enumerate(main_path):
        col_start[sname] = x
        col_center[sname] = x + box_width[sname] // 2
        x += box_width[sname]
        if i < len(main_path) - 1:
            x += 4

    rows: list[list[str]] = [[" "] * total_width for _ in range(main_height)]

    for sname in main_path:
        is_highlighted = highlight_state is not None and sname == highlight_state
        _draw_box(
            rows,
            0,
            col_start[sname],
            box_width[sname],
            main_height,
            box_inner[sname],
            is_highlighted,
            highlight_color,
            badge=box_badge[sname],
        )

    # Self-loops
    self_loops_list = [(s, d, lbl) for s, d, lbl in back_edges if s == d]
    lines = ["".join(row).rstrip() for row in rows]
    if self_loops_list:
        self_labels: dict[str, list[str]] = {}
        for src, _, label in self_loops_list:
            self_labels.setdefault(src, []).append(label)
        for sname, labels in self_labels.items():
            marker = "\u21ba " + ", ".join(labels)
            self_row = [" "] * total_width
            cx = col_center.get(sname, 0)
            pos = max(0, cx - len(marker) // 2)
            for j, ch in enumerate(marker):
                if pos + j < total_width:
                    self_row[pos + j] = ch
            lines.append("".join(self_row).rstrip())

    diagram_indent = max(0, (tw - (x + 4)) // 2)
    if diagram_indent > 0:
        lines = [" " * diagram_indent + ln if ln.strip() else ln for ln in lines]

    return _colorize_diagram_labels("\n".join(lines))

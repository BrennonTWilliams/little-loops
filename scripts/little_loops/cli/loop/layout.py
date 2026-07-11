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

from little_loops.cli.output import colorize, strip_ansi, terminal_width
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
    "blocked": "31",
    "retry_exhausted": "38;5;208",
    "rate_limit_exhausted": "38;5;214",
    "throttle_hard": "38;5;196",
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


def _edge_line_color(label: str) -> str:
    """Return the ANSI SGR code to use for connector characters of an edge.

    Applies the same priority cascade as ``_colorize_label`` so that line
    characters (│, ─, ▼, ▶, corners) match the semantic color of their label.
    Returns an empty string when no color applies (callers treat this as "no-op").
    """
    parts = label.split("/")
    code = ""
    for part in parts:
        if part in (
            "no",
            "error",
            "blocked",
            "retry_exhausted",
            "rate_limit_exhausted",
            "throttle_hard",
        ):
            return _EDGE_LABEL_COLORS.get(part, "31")
        if part == "partial" and not code:
            code = _EDGE_LABEL_COLORS["partial"]
        elif part == "yes" and not code:
            code = _EDGE_LABEL_COLORS["yes"]
        elif part in ("next", "_") and not code:
            code = _EDGE_LABEL_COLORS["next"]
    return code


def _colorize_diagram_labels(diagram: str, colors: dict[str, str] | None = None) -> str:
    """Apply ANSI color to known edge labels in a rendered diagram string.

    Labels are colorized only when bounded by box-drawing or whitespace chars
    to avoid coloring partial matches inside state names.

    Args:
        colors: Optional label→SGR-code mapping; falls back to _EDGE_LABEL_COLORS if None.
    """
    label_colors = colors if colors is not None else _EDGE_LABEL_COLORS
    for label, code in label_colors.items():
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


# Per-state "kind" foreground color (no background fill — kept light to match the
# ``clean`` preset aesthetic). Applied to non-active state boxes so the diagram has
# a color signal even when ``highlight_state`` is ``None`` (dry-run, ``ll-loop info``,
# initial render before any state executes, or main-scope fallback that hides the
# active state). Active states continue to use ``highlight_color`` with background
# fill via ``_draw_box``.
_ACTION_TYPE_KIND_COLORS: dict[str, str] = {
    "slash_command": "34",  # blue
    "prompt": "35",  # magenta
    "shell": "90",  # bright black (gray) — recedes on warm-paper dark theme
    "mcp_tool": "33",  # yellow
}

_SUB_LOOP_KIND_COLOR = "35"  # magenta — distinguishes nested FSMs
_TERMINAL_KIND_COLOR = "2"  # dim — end states visually recede


def _box_kind_color(state: StateConfig | None) -> str | None:
    """Return the SGR foreground code for a non-active state, or ``None`` for plain.

    Resolution order mirrors :func:`_get_state_badge` so the badge glyph and the
    border hue correspond 1:1:

    1. ``state.loop`` set → ``_SUB_LOOP_KIND_COLOR`` (magenta).
    2. ``state.action_type`` in ``_ACTION_TYPE_KIND_COLORS`` → mapped hue.
    3. bare ``state.action`` (no explicit ``action_type``) → shell hue.
    4. terminal state without action → ``_TERMINAL_KIND_COLOR`` (dim).
    5. bare ``route:`` only or empty state → ``None`` (defer to caller).
    """
    if state is None:
        return None
    if state.loop:
        return _SUB_LOOP_KIND_COLOR
    if state.action_type:
        return _ACTION_TYPE_KIND_COLORS.get(state.action_type)
    if state.action:
        return _ACTION_TYPE_KIND_COLORS["shell"]
    if state.terminal:
        return _TERMINAL_KIND_COLOR
    return None


def _badge_display_width(badge: str) -> int:
    """Compute terminal display width of a badge string using wcwidth."""
    w = _wcswidth(badge)
    return w if w >= 0 else len(badge)


def _display_width(s: str) -> int:
    """Terminal display width of a string (wcwidth), with a safe len() fallback.

    Box layout reserves *display columns*, not characters, so widths must be
    measured this way; using ``len()`` undercounts wide glyphs (CJK, some
    symbols) and overflows the box border.

    ANSI SGR / CSI sequences (``\\x1b[…m`` and friends) have zero visible
    width and must not contribute to the budget. ``wcswidth`` returns ``-1``
    for strings containing the ESC byte (it can't iterate the bytes as
    printable text), so we strip ANSI first and then measure. Plain-text
    callers (the common case — most call sites pass state names, action
    bodies, badges, or row strings before colorization) skip the strip via
    the ``\x1b`` fast path.
    """
    if "\x1b" in s:
        s = strip_ansi(s)
    w = _wcswidth(s)
    return w if w >= 0 else len(s)


def _truncate_to_width(text: str, width: int) -> str:
    """Truncate ``text`` so its display width is ≤ ``width``.

    When truncation occurs the last column is replaced with ``…`` so the result
    still fits ``width`` display columns. Wide glyphs are kept whole.
    """
    if width <= 0:
        return ""
    if _display_width(text) <= width:
        return text
    # Reserve one column for the ellipsis.
    budget = width - 1
    out: list[str] = []
    used = 0
    for ch in text:
        cw = _wcwidth(ch)
        if cw < 0:
            cw = 1
        if used + cw > budget:
            break
        out.append(ch)
        used += cw
    return "".join(out) + "…"


# Matches any CSI sequence (the same subset ``cli.output.strip_ansi`` strips).
# Used by ``_truncate_to_width_ansi`` to skip past escape codes without
# consuming width budget or counting their bytes as visible columns.
_ANSI_CSI_RE = re.compile(r"\x1b\[[0-9;]*[a-zA-Z]")


def _truncate_to_width_ansi(text: str, width: int) -> str:
    """ANSI-aware variant of :func:`_truncate_to_width`.

    Truncates ``text`` to ``≤ width`` *visible* columns while preserving any
    SGR (or other CSI) sequences embedded in it, so a colored diagram line
    keeps its styling when it overflows the terminal width. When an SGR is
    still active at the cut point, an explicit ``\\x1b[0m`` reset is emitted
    before the trailing ``…`` so the active style does not leak onto the
    next printed line.
    """
    if width <= 0:
        return ""
    if _display_width(text) <= width:
        return text
    # Reserve one column for the ellipsis.
    budget = width - 1
    out: list[str] = []
    used = 0
    sgr_open = False
    i = 0
    n = len(text)
    while i < n:
        # Pass CSI sequences through without consuming width budget.
        m = _ANSI_CSI_RE.match(text, i)
        if m is not None:
            seq = m.group(0)
            out.append(seq)
            # Only SGR sequences (final byte ``m``) affect color state. An
            # explicit reset closes any open SGR; any other SGR opens or
            # switches the active style.
            if seq == "\x1b[0m":
                sgr_open = False
            elif seq.endswith("m"):
                sgr_open = True
            i = m.end()
            continue
        cw = _wcwidth(text[i])
        if cw < 0:
            cw = 1
        if used + cw > budget:
            break
        out.append(text[i])
        used += cw
        i += 1
    result = "".join(out)
    if sgr_open:
        result += "\x1b[0m"
    return result + "…"


def _wrap_to_width(text: str, width: int) -> list[str]:
    """Hard-wrap ``text`` into chunks each ≤ ``width`` display columns.

    Splits on display width (not character count) so wide glyphs are kept whole
    and no chunk overflows the box border.
    """
    if width <= 0:
        return [text] if text else []
    chunks: list[str] = []
    cur: list[str] = []
    used = 0
    for ch in text:
        cw = _wcwidth(ch)
        if cw < 0:
            cw = 1
        if used + cw > width and cur:
            chunks.append("".join(cur))
            cur = []
            used = 0
        cur.append(ch)
        used += cw
    if cur:
        chunks.append("".join(cur))
    return chunks


def _get_state_badge(state: StateConfig | None, badges: dict[str, str] | None = None) -> str:
    """Return the unicode badge string for a state, or '' if none."""
    if state is None:
        return ""
    effective = {**_ACTION_TYPE_BADGES, **(badges or {})}
    sub_loop_badge = (badges or {}).get("sub_loop", _SUB_LOOP_BADGE)
    route_badge = (badges or {}).get("route", _ROUTE_BADGE)
    if state.loop is not None:
        return sub_loop_badge
    if state.action_type:
        return effective.get(state.action_type, f"[{state.action_type}]")
    if state.action:
        return effective["shell"]
    if state.route is not None:
        return route_badge
    return ""


# ---------------------------------------------------------------------------
# Box content helpers for multi-row diagram boxes
# ---------------------------------------------------------------------------


def _box_inner_lines(
    state: StateConfig | None,
    display_label: str,
    verbose: bool,
    inner_width: int,
    title_only: bool = False,
) -> list[str]:
    """Return interior lines for a state box (between top and bottom borders).

    The first line is always ``display_label`` + type badge (if any).
    Subsequent lines are action content lines.  All lines fit within
    ``inner_width`` characters (content is truncated or wrapped accordingly).

    When ``title_only`` is True, only the name row is returned (used by
    ``--show-diagrams=mini`` for skeleton rendering).
    """
    # Badge is now rendered in the top-right corner by _draw_box; name row is label only.
    # Truncation is by display width so wide glyphs don't overflow the box border.
    name_line = _truncate_to_width(display_label, inner_width)

    lines: list[str] = [name_line]

    if title_only:
        return lines

    # Action lines
    if state and state.action:
        action_src = [ln.rstrip() for ln in state.action.strip().splitlines()]
        if verbose:
            for src in action_src:
                if not src:
                    continue
                # Wrap long lines to inner_width (measured in display columns)
                lines.extend(_wrap_to_width(src, inner_width))
        else:
            # Show first non-empty line, truncated to display width
            first = next((ln for ln in action_src if ln), "")
            first = _truncate_to_width(first, inner_width)
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
        if state.on_blocked:
            edges.append((name, state.on_blocked, "blocked"))
        if state.on_retry_exhausted:
            edges.append((name, state.on_retry_exhausted, "retry_exhausted"))
        if state.on_rate_limit_exhausted:
            edges.append((name, state.on_rate_limit_exhausted, "rate_limit_exhausted"))
        if state.on_throttle_hard:
            edges.append((name, state.on_throttle_hard, "throttle_hard"))
        if state.next:
            edges.append((name, state.next, "next"))
        if state.route:
            for verdict, target in state.route.routes.items():
                edges.append((name, target, verdict))
            if state.route.default:
                edges.append((name, state.route.default, "_"))
        for verdict, target in state.extra_routes.items():
            edges.append((name, target, verdict))
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
    badges: dict[str, str] | None = None,
    title_only: bool = False,
) -> tuple[dict[str, list[str]], dict[str, int], dict[str, int], dict[str, str]]:
    """Compute box content, widths, and heights for all states.

    Returns (box_inner, box_width, box_height, box_badge).

    When ``title_only`` is True, action body lines are suppressed (used by
    ``--show-diagrams=mini`` for skeleton rendering); box widths are computed
    from the name label / badge only.
    """
    box_inner: dict[str, list[str]] = {}
    box_width: dict[str, int] = {}
    box_badge: dict[str, str] = {}

    for s in all_states:
        state_obj = fsm_states.get(s) if fsm_states else None

        badge = _get_state_badge(state_obj, badges)
        badge_w = _badge_display_width(badge) if badge else 0
        box_badge[s] = badge

        # Width must fit: name label on content row, badge on top border (with one space
        # of padding on each side: " badge ").  All widths are display columns.
        base_w = max(_display_width(display_label[s]), badge_w + 2 if badge_w else 0)

        inner_w = base_w
        if not title_only and state_obj and state_obj.action and max_box_inner > 0:
            action_lines = state_obj.action.strip().splitlines()
            if verbose:
                max_action_w = max(
                    (_display_width(ln.rstrip()) for ln in action_lines if ln.rstrip()), default=0
                )
                inner_w = max(base_w, min(max_action_w, max_box_inner))
            else:
                first_action = next((ln.rstrip() for ln in action_lines if ln.rstrip()), "")
                inner_w = max(base_w, min(_display_width(first_action), max_box_inner))

        content = _box_inner_lines(
            state_obj, display_label[s], verbose, inner_w, title_only=title_only
        )
        actual_w = max(_display_width(ln) for ln in content)
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
    kind_color: str | None = None,
) -> None:
    """Draw a state box onto a character grid at (row, col).

    If *badge* is provided it is placed right-aligned in the top border row with
    one space of padding on each side (``─ badge ┐``), colorized via ``_bc()``.

    If ``kind_color`` is provided and the box is not highlighted, the border,
    badge, and name-row text are colorized with it (foreground only — no
    background fill). This gives non-active state boxes a distinguishing hue
    based on their ``action_type`` / ``loop`` / ``terminal`` kind when no
    active-state highlight is available (dry-run, ``ll-loop info``), without
    changing the visual weight of the highlight.
    """
    # Effective border-color for non-highlighted boxes (foreground only).
    nc: str | None = kind_color if (not is_highlighted and kind_color) else None
    total_width = len(grid[0]) if grid else 0
    try:
        bg_code: str | None = str(int(highlight_color) + 10)
    except (ValueError, TypeError):
        bg_code = None

    # Pre-compute the combined border SGR code for highlighted boxes so
    # entire border strings can be batched into a single colorize() call.
    border_code: str | None = None
    if is_highlighted:
        border_code = f"{highlight_color};{bg_code}" if bg_code else highlight_color

    def _bc(ch: str) -> str:
        """Colorize a single character for non-batched cell writes (side borders)."""
        if not is_highlighted:
            return colorize(ch, nc) if nc else ch
        if bg_code:
            return colorize(ch, f"{highlight_color};{bg_code}")
        return colorize(ch, highlight_color)

    # ── Top border ──────────────────────────────────────────────────────
    # Batched into a single colorize() call when highlighted.  When a badge
    # is present the full border string is built in one shot — badge display
    # width drives dash-count arithmetic so wide chars are handled correctly.
    if is_highlighted and border_code:
        if not badge:
            grid[row][col] = colorize("\u250c" + "\u2500" * (width - 2) + "\u2510", border_code)
        else:
            badge_w = _badge_display_width(badge)
            dash_count = width - badge_w - 4
            grid[row][col] = colorize(
                "\u250c" + "\u2500" * dash_count + " " + badge + " " + "\u2510",
                border_code,
            )
        # Clear cells consumed by the batched border string
        for j in range(1, width):
            if col + j < total_width:
                grid[row][col + j] = ""
    else:
        if nc:
            if not badge:
                top_str = "\u250c" + "\u2500" * (width - 2) + "\u2510"
                grid[row][col] = colorize(top_str, nc)
                for j in range(1, width):
                    if col + j < total_width:
                        grid[row][col + j] = ""
            else:
                badge_w = _badge_display_width(badge)
                dash_count = width - badge_w - 4
                top_str = "\u250c" + "\u2500" * dash_count + " " + badge + " " + "\u2510"
                grid[row][col] = colorize(top_str, nc)
                for j in range(1, width):
                    if col + j < total_width:
                        grid[row][col + j] = ""
        else:
            if col < total_width:
                grid[row][col] = "\u250c"
            for j in range(1, width - 1):
                if col + j < total_width:
                    grid[row][col + j] = "\u2500"
            if col + width - 1 < total_width:
                grid[row][col + width - 1] = "\u2510"

            # Overlay badge in top-right corner (non-highlighted path only;
            # highlighted path builds the badge into the batched string above).
            if badge:
                badge_w = _badge_display_width(badge)
                trail_pos = col + width - 2
                if col + 1 <= trail_pos < col + width - 1 and trail_pos < total_width:
                    grid[row][trail_pos] = " "
                lead_pos = col + width - badge_w - 3
                if col + 1 <= lead_pos < col + width - 1 and lead_pos < total_width:
                    grid[row][lead_pos] = " "
                pos = col + width - 1 - badge_w - 1
                for ch in badge:
                    ch_w = _wcwidth(ch)
                    if ch_w < 1:
                        ch_w = 1
                    if col + 1 <= pos < col + width - 1 and pos < total_width:
                        grid[row][pos] = ch
                        if ch_w == 2 and pos + 1 < col + width - 1 and pos + 1 < total_width:
                            grid[row][pos + 1] = ""
                    pos += ch_w

    # ── Interior fill ───────────────────────────────────────────────────
    # Batched per row — a single colorize(" " * N, bg_code) replaces the
    # per-cell loop that previously generated (width-2) SGR pairs per row.
    if is_highlighted and bg_code:
        fill_str = colorize(" " * (width - 2), bg_code)
        for ri in range(row + 1, row + height - 1):
            if ri >= len(grid):
                break
            if col + 1 < total_width:
                grid[ri][col + 1] = fill_str

    # ── Content rows ────────────────────────────────────────────────────
    def _place_content_row(
        r: int,
        line: str,
        lead_code: str | None,
        text_code: str | None,
        fill_code: str | None,
    ) -> None:
        """Lay one interior line into the grid: leading space, the line itself,
        then trailing fill up to the right border.

        The line (and the trailing-fill run) are each written into a *single*
        grid cell as a multi-character string for SGR batching, so the grid
        cells those strings visually cover MUST be cleared — otherwise their
        original single-space contents survive ``"".join(row)`` and push the
        right border out (the action-row overflow bug).  Widths are display
        columns so wide glyphs are accounted for.
        """
        dw = _display_width(line)
        if col + 1 < total_width:
            grid[r][col + 1] = colorize(" ", lead_code) if lead_code else " "
        if col + 2 < total_width:
            grid[r][col + 2] = colorize(line, text_code) if text_code else line
        # Clear the cells the content string visually covers.
        for j in range(1, dw):
            cc = col + 2 + j
            if cc < col + width - 1 and cc < total_width:
                grid[r][cc] = ""
        # Trailing fill between content and the right border.
        trail_pad = width - 3 - dw
        fill_start = col + 2 + dw
        if trail_pad > 0 and fill_start < total_width:
            grid[r][fill_start] = (
                colorize(" " * trail_pad, fill_code) if fill_code else " " * trail_pad
            )
            for j in range(1, trail_pad):
                cc = fill_start + j
                if cc < col + width - 1 and cc < total_width:
                    grid[r][cc] = ""

    for i, line in enumerate(content):
        r = row + i + 1
        if r >= len(grid):
            break
        # Clear the batched fill cell for this row so content placement
        # rebuilds the interior with proper leading-space + content +
        # trailing-fill layout (the batched fill at col+1 would otherwise
        # appear before the content instead of behind it).
        if is_highlighted and bg_code:
            grid[r][col + 1] = ""
        if col < total_width:
            grid[r][col] = _bc("\u2502")
        if col + width - 1 < total_width:
            grid[r][col + width - 1] = _bc("\u2502")
        if i == 0:
            # Name row (bold; brightened on the highlighted box).
            if is_highlighted:
                lead_code: str | None = bg_code or highlight_color
                text_code: str | None = f"97;{bg_code};1" if bg_code else f"{highlight_color};1"
                fill_code: str | None = bg_code or highlight_color
            else:
                lead_code = nc
                text_code = f"{nc};1" if nc else "1"
                fill_code = nc
        else:
            # Action body rows.
            if is_highlighted and bg_code:
                lead_code = bg_code
                text_code = f"97;{bg_code}"
                fill_code = bg_code
            else:
                lead_code = None
                text_code = None
                fill_code = None
        _place_content_row(r, line, lead_code, text_code, fill_code)

    # ── Padding rows ────────────────────────────────────────────────────
    for i in range(len(content) + 1, height - 1):
        r = row + i
        if r >= len(grid):
            break
        if col < total_width:
            grid[r][col] = _bc("\u2502")
        if col + width - 1 < total_width:
            grid[r][col + width - 1] = _bc("\u2502")

    # ── Bottom border ───────────────────────────────────────────────────
    # Fully batched — same pattern as top border (no badge on bottom).
    brow = row + height - 1
    if brow < len(grid):
        if is_highlighted and border_code:
            if col < total_width:
                grid[brow][col] = colorize(
                    "\u2514" + "\u2500" * (width - 2) + "\u2518", border_code
                )
            for j in range(1, width):
                if col + j < total_width:
                    grid[brow][col + j] = ""
        elif nc:
            bot_str = "\u2514" + "\u2500" * (width - 2) + "\u2518"
            if col < total_width:
                grid[brow][col] = colorize(bot_str, nc)
            for j in range(1, width):
                if col + j < total_width:
                    grid[brow][col + j] = ""
        else:
            if col < total_width:
                grid[brow][col] = "\u2514"
            for j in range(1, width - 1):
                if col + j < total_width:
                    grid[brow][col + j] = "\u2500"
            if col + width - 1 < total_width:
                grid[brow][col + width - 1] = "\u2518"


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
    edge_label_colors: dict[str, str] | None = None,
    badges: dict[str, str] | None = None,
    title_only: bool = False,
    suppress_labels: bool = False,
    window: tuple[str | None, int] | None = None,
) -> str:
    """Render FSM using layered (Sugiyama-style) vertical layout.

    When ``title_only`` is True, per-state body lines are suppressed.
    When ``suppress_labels`` is True, inter-state edges render without labels.

    When ``window`` is ``(active_state, budget)`` the fully rendered grid is
    cropped to the ``±K`` layers around ``active_state``'s layer that fit within
    ``budget`` rows, with ``▲ N layers above …`` / ``▼ M layers below …``
    overflow banners (ENH-2410). Column positions, arrows, labels, badges and
    the active-state highlight are the genuine layered ones — only whole grid
    rows are sliced at clean layer boundaries. Returns ``""`` when even the
    active layer plus its banners does not fit ``budget`` (the caller then
    defers to a smaller diagram rung). ``active_state`` of ``None`` / unknown
    windows the top of the graph.
    """
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
        all_states,
        display_label,
        fsm_states,
        verbose,
        max_box_inner,
        badges,
        title_only=title_only,
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
        # BUG-2425: clamp the back-edge channel gutter to a fraction of the
        # terminal width so a back-edge-heavy loop can't push state boxes off
        # the right edge. Overflow channels are dropped by the draw loop's
        # `col >= content_left - 1` guard, collapsing into the bounded gutter.
        back_edge_margin = min(back_edge_margin, max(6, tw // 3))

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
        # BUG-2425: same terminal-width clamp as the initial estimate above.
        actual_margin = min(actual_margin, max(6, tw // 3))
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
            y += 2 if suppress_labels else 3  # arrow gap: suppress_labels skips label row

    total_height = y

    # Build character grid
    grid: list[list[str]] = [[" "] * total_width for _ in range(total_height)]

    # Draw boxes
    for sname in all_states:
        is_highlighted = highlight_state is not None and sname == highlight_state
        _kind = _box_kind_color(fsm_states.get(sname)) if fsm_states is not None else None
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
            kind_color=_kind,
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
        marker = "\u21ba" if suppress_labels else "\u21ba " + ", ".join(labels)
        r = row_start[sname] + box_height[sname]
        if r < total_height:
            cx = col_center[sname]
            pos = max(0, cx - len(marker) // 2)
            for j, ch in enumerate(marker):
                if pos + j < total_width:
                    grid[r][pos + j] = ch

    # Shared row tracker: prevents two labels (back-edge, skip-forward, or adjacent)
    # landing on the same grid row, which would clobber the first label written there.
    used_label_rows: set[int] = set()

    # Margin pipe spans (ENH-2410 windowed-crop cleanup): (col, top_row, bot_row,
    # label_row_pos, label_start, label_len) for every back-edge / forward
    # skip-layer pipe drawn below. When the window later crops to rows strictly
    # between top_row and bot_row (neither corner visible), the pipe is a bare
    # pass-through line with no connector or arrowhead — the overflow banners
    # already summarize what's above/below, so those segments get blanked.
    margin_pipe_spans: list[tuple[int, int, int, int, int, int]] = []

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
            ec = _edge_line_color(label)  # ANSI code for this edge's connector chars

            def _lc(ch: str, _ec: str = ec) -> str:  # noqa: E306
                return colorize(ch, _ec) if _ec else ch

            # Horizontal connector when pipe is outside source box range
            if dst_cc >= src_right or dst_cc < src_left:
                conn_row = arrow_start_row
                if 0 <= conn_row < total_height:
                    if dst_cc >= src_right:
                        # Pipe right of source: └───┐
                        src_cc = col_center[src]
                        if 0 <= src_cc < total_width and grid[conn_row][src_cc] == " ":
                            grid[conn_row][src_cc] = _lc("\u2514")  # └
                            start_c = src_cc + 1
                        else:
                            start_c = src_right
                        for c in range(start_c, dst_cc):
                            if 0 <= c < total_width:
                                grid[conn_row][c] = _lc("\u2500")
                        if 0 <= dst_cc < total_width:
                            grid[conn_row][dst_cc] = _lc("\u2510")  # ┐
                    else:
                        # Pipe left of source: ┌───┘
                        src_cc = col_center[src]
                        if 0 <= src_cc < total_width and grid[conn_row][src_cc] == " ":
                            end_c = src_cc
                            grid[conn_row][src_cc] = _lc("\u2518")  # ┘
                        else:
                            end_c = src_left
                        for c in range(dst_cc + 1, end_c):
                            if 0 <= c < total_width:
                                grid[conn_row][c] = _lc("\u2500")
                        if 0 <= dst_cc < total_width:
                            grid[conn_row][dst_cc] = _lc("\u250c")  # ┌
                pipe_start = arrow_start_row + 1
            else:
                pipe_start = arrow_start_row

            # Draw vertical pipe at destination's center column
            for r in range(pipe_start, arrow_end_row):
                if 0 <= dst_cc < total_width and r < total_height:
                    grid[r][dst_cc] = _lc("\u2502")

            # Arrow tip at destination center
            if arrow_end_row < total_height and 0 <= dst_cc < total_width:
                grid[arrow_end_row][dst_cc] = _lc("\u25bc")

            # Label to the right of the pipe.  When skip-layer forward edges
            # exist their vertical pipes occupy columns starting at
            # total_content_w+2, so clamp to total_content_w to avoid
            # overwriting them (BUG-1500).  Without skip-layer edges the right
            # margin is empty and the full total_width is available.
            label_row = arrow_start_row
            # Nudge if this row already has a label from another inter-layer edge
            # (e.g., two edges from the same source go to states in the same layer).
            # Try pipe rows (pipe_start..arrow_end_row) before giving up (BUG-1501).
            if label_row in used_label_rows:
                for _cand in range(pipe_start, arrow_end_row + 1):
                    if _cand not in used_label_rows:
                        label_row = _cand
                        break
            if label_row < total_height and not suppress_labels:
                used_label_rows.add(label_row)
                label_start = dst_cc + 2
                max_col = total_content_w if skip_forward_edges else total_width
                max_label = max_col - label_start
                if 0 < max_label < len(label):
                    label = label[: max_label - 1] + "…"
                for j, ch in enumerate(label):
                    if label_start + j < max_col:
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
        if suppress_labels:
            label = ""
        name_row = row_start[src] + 1
        src_right = col_start[src] + box_width[src]
        dst_right = col_start[dst] + box_width[dst]
        dst_left = col_start[dst]
        src_left = col_start[src]
        _row_boxes = _box_occ.get(name_row, set())
        ec = _edge_line_color(label)

        def _lc(ch: str, _ec: str = ec) -> str:  # noqa: E306
            return colorize(ch, _ec) if _ec else ch

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
                    grid[name_row][pos] = _lc("\u2500")
            for k, ch in enumerate(edge_text):
                pos = start + left_dashes + k
                if (
                    0 <= pos < end
                    and pos < total_width
                    and name_row < total_height
                    and pos not in _row_boxes
                ):
                    grid[name_row][pos] = _lc(ch)
        elif dst_right <= src_left:
            # Right to left: dst is left of src: src → dst drawn as dst ◀──label── src
            start = dst_right
            end = src_left
            edge_text = "\u25c4\u2500\u2500" + label + "\u2500"
            available = end - start
            if available < len(edge_text):
                edge_text = edge_text[: max(1, available)]
            for k, ch in enumerate(edge_text):
                pos = start + k
                if (
                    0 <= pos < end
                    and pos < total_width
                    and name_row < total_height
                    and pos not in _row_boxes
                ):
                    grid[name_row][pos] = _lc(ch)
            for k in range(start + len(edge_text), end):
                if k < total_width and name_row < total_height and k not in _row_boxes:
                    grid[name_row][k] = _lc("\u2500")

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
            ec = _edge_line_color(label)

            def _lc(ch: str, _ec: str = ec) -> str:  # noqa: E306
                return colorize(ch, _ec) if _ec else ch

            # Draw vertical line in margin (exclude corner rows handled below)
            for r in range(top_row + 1, bot_row):
                if 0 <= r < total_height and col < total_width:
                    cell = grid[r][col]
                    if cell == "\u2500":  # ─ → ┼ (junction, leave uncolored)
                        grid[r][col] = "\u253c"
                    elif cell == " ":
                        grid[r][col] = _lc("\u2502")

            # Horizontal connector from source box to margin
            # Draw right-to-left, crossing existing pipes with junction chars
            if 0 <= src_row < total_height:
                src_left = col_start.get(src, col + 1)
                _src_row_boxes = _box_occ.get(src_row, set())
                for c in range(col + 1, src_left):
                    if c < total_width and c not in _src_row_boxes:
                        cell = grid[src_row][c]
                        if cell == " ":
                            grid[src_row][c] = _lc("\u2500")  # ─
                        elif cell == "\u2502":  # │ → ┼ (junction)
                            grid[src_row][c] = "\u253c"
                        elif cell == "\u2514":  # └ → ┴ (junction)
                            grid[src_row][c] = "\u2534"
                        elif cell == "\u250c":  # ┌ → ┬ (junction)
                            grid[src_row][c] = "\u252c"
                        elif cell == "\u251c":  # ├ → ┼ (junction)
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
                            grid[dst_row][c] = _lc("\u2500")  # ─
                        elif cell == "\u2502":  # │ → ┼ (junction)
                            grid[dst_row][c] = "\u253c"
                        elif cell == "\u2514":  # └ → ┴ (junction)
                            grid[dst_row][c] = "\u2534"
                        elif cell == "\u250c":  # ┌ → ┬ (junction)
                            grid[dst_row][c] = "\u252c"
                        elif cell == "\u251c":  # ├ → ┼ (junction)
                            grid[dst_row][c] = "\u253c"

            # Corner characters at pipe-to-horizontal turn points
            for row in (src_row, dst_row):
                if 0 <= row < total_height and col < total_width:
                    existing = grid[row][col]
                    if row == bot_row:
                        # Pipe ends, turns right: └; if horizontal already crosses here: ┴
                        grid[row][col] = "\u2534" if existing == "\u2500" else _lc("\u2514")
                    else:  # row == top_row
                        # Pipe starts going down, turns right: ┌; if horizontal already crosses here: ┬
                        grid[row][col] = "\u252c" if existing == "\u2500" else _lc("\u250c")

            # Arrow tip at target: place ▶ at end of horizontal connector (entering box from left)
            if 0 <= dst_row < total_height and dst_left - 1 > col and dst_left - 1 < total_width:
                grid[dst_row][dst_left - 1] = _lc("\u25b6")

            # Label on the margin line (right of ALL pipes, not just this one)
            label_row_pos = (top_row + bot_row) // 2
            # Nudge away from already-used rows to prevent clobbering earlier labels
            if label_row_pos in used_label_rows and top_row + 1 < bot_row:
                midpoint = label_row_pos
                found = False
                for _off in range(1, bot_row - top_row):
                    for _cand in (midpoint - _off, midpoint + _off):
                        if top_row < _cand < bot_row and _cand not in used_label_rows:
                            label_row_pos = _cand
                            found = True
                            break
                    if found:
                        break
                if not found:
                    label_row_pos = top_row + 1
            used_label_rows.add(label_row_pos)
            label_start = rightmost_pipe_col + 2
            label_len = 0
            if 0 <= label_row_pos < total_height and not title_only:
                for j, ch in enumerate(label):
                    if label_start + j < content_left - 1 and label_start + j < total_width:
                        grid[label_row_pos][label_start + j] = _lc(ch)
                        label_len = j + 1
            margin_pipe_spans.append((col, top_row, bot_row, label_row_pos, label_start, label_len))

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
            ec = _edge_line_color(label)

            def _lc(ch: str, _ec: str = ec) -> str:  # noqa: E306
                return colorize(ch, _ec) if _ec else ch

            # Draw vertical line in right margin (exclude corner rows handled below)
            for r in range(top_row + 1, bot_row):
                if 0 <= r < total_height and col < total_width:
                    cell = grid[r][col]
                    if cell == "\u2500":  # ─ → ┼ (junction)
                        grid[r][col] = "\u253c"
                    elif cell == " ":
                        grid[r][col] = _lc("\u2502")

            # Horizontal connector from source box right side to margin
            # Draw left-to-right, crossing existing pipes with junction chars
            src_right = col_start.get(src, 0) + box_width.get(src, 0)
            _src_row_boxes = _box_occ.get(src_row, set())
            if 0 <= src_row < total_height:
                for c in range(src_right, col):
                    if 0 <= c < total_width and c not in _src_row_boxes:
                        cell = grid[src_row][c]
                        if cell == " ":
                            grid[src_row][c] = _lc("\u2500")  # ─
                        elif cell == "\u2502":  # │ → ┼ (junction)
                            grid[src_row][c] = "\u253c"
                        elif cell == "\u2518":  # ┘ → ┴ (junction)
                            grid[src_row][c] = "\u2534"
                        elif cell == "\u2510":  # ┐ → ┬ (junction)
                            grid[src_row][c] = "\u252c"
                        elif cell == "\u2524":  # ┤ → ┼ (junction)
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
                            grid[dst_row][c] = _lc("\u2500")  # ─
                        elif cell == "\u2502":  # │ → ┼ (junction)
                            grid[dst_row][c] = "\u253c"
                        elif cell == "\u2518":  # ┘ → ┴ (junction)
                            grid[dst_row][c] = "\u2534"
                        elif cell == "\u2510":  # ┐ → ┬ (junction)
                            grid[dst_row][c] = "\u252c"
                        elif cell == "\u2524":  # ┤ → ┼ (junction)
                            grid[dst_row][c] = "\u253c"

            # Corner characters at pipe-to-horizontal turn points
            for row in (src_row, dst_row):
                if 0 <= row < total_height and col < total_width:
                    existing = grid[row][col]
                    if row == bot_row:
                        # Pipe ends, turns left: ┘; if horizontal crosses: ┤
                        grid[row][col] = "\u2524" if existing == "\u2500" else _lc("\u2518")
                    else:  # row == top_row
                        # Pipe starts going down, turns left: ┐; if horizontal crosses: ┤
                        grid[row][col] = "\u2524" if existing == "\u2500" else _lc("\u2510")

            # Arrow tip at target: ◀ entering box from right side
            if 0 <= dst_row < total_height and dst_right < col and dst_right < total_width:
                grid[dst_row][dst_right] = _lc("\u25c0")

            # Label on the margin line (right of ALL pipes, mirroring left-margin
            # approach).  Truncate with … when label would exceed total_width
            # to prevent extending diagram lines far past the content area (BUG-1500).
            label_row_pos = (top_row + bot_row) // 2
            # Nudge to avoid row collision with a previously-placed label (back- or fwd-edge)
            if label_row_pos in used_label_rows and top_row + 1 < bot_row:
                midpoint = label_row_pos
                found = False
                for _off in range(1, bot_row - top_row):
                    for _cand in (midpoint - _off, midpoint + _off):
                        if top_row < _cand < bot_row and _cand not in used_label_rows:
                            label_row_pos = _cand
                            found = True
                            break
                    if found:
                        break
                if not found:
                    label_row_pos = top_row + 1
            used_label_rows.add(label_row_pos)
            label_start = rightmost_fwd_pipe_col + 2
            label_len = 0
            if 0 <= label_row_pos < total_height and not title_only:
                max_label = total_width - label_start
                if 0 < max_label < len(label):
                    label = label[: max_label - 1] + "…"
                for j, ch in enumerate(label):
                    if label_start + j < total_width:
                        grid[label_row_pos][label_start + j] = _lc(ch)
                        label_len = j + 1
            margin_pipe_spans.append((col, top_row, bot_row, label_row_pos, label_start, label_len))

    # Windowed crop (ENH-2410): keep only the grid rows for the ±K layers around
    # the active state that fit ``budget``. Slicing whole grid rows preserves the
    # real column positions, arrows, labels, badges and highlight. Back-edge and
    # forward-skip margin pipes whose window slice contains neither endpoint are
    # pure pass-through lines — blanked below since the overflow banners already
    # summarize what's above/below; pipes with one endpoint still visible survive
    # as meaningful truncated stubs.
    banner_above = ""
    banner_below = ""
    if window is not None:
        win_active, win_budget = window
        n_layers = len(layers)

        def _layer_top(li: int) -> int:
            return row_start[layers[li][0]]

        def _layer_bottom(li: int) -> int:
            # Exclusive bottom: past the tallest box, plus a self-loop marker row
            # if any state in the layer has one. Excludes the inter-layer arrow gap
            # so the cut lands on a clean box boundary.
            box_bot = max(row_start[s] + box_height[s] for s in layers[li])
            has_self = any(s in self_loops for s in layers[li])
            return box_bot + (1 if has_self else 0)

        if win_active is not None and win_active in layer_of:
            active_layer = layer_of[win_active]
        else:
            active_layer = 0  # unknown/None active → window the top of the graph

        def _pane_height(lo: int, hi: int) -> int:
            h = _layer_bottom(hi) - _layer_top(lo)
            if lo > 0:
                h += 1  # ▲ banner
            if hi < n_layers - 1:
                h += 1  # ▼ banner
            return h

        lo = hi = active_layer
        if _pane_height(lo, hi) > win_budget:
            # Not even the active layer plus its banners fits — defer to a
            # smaller diagram rung (neighborhood / single).
            return ""

        # Grow the window symmetrically (down, then up) while it still fits.
        while True:
            grew = False
            if hi < n_layers - 1 and _pane_height(lo, hi + 1) <= win_budget:
                hi += 1
                grew = True
            if lo > 0 and _pane_height(lo - 1, hi) <= win_budget:
                lo -= 1
                grew = True
            if not grew:
                break

        window_top = _layer_top(lo)
        window_bot = _layer_bottom(hi)

        # Blank pass-through margin pipes: segments whose window slice contains
        # neither the source nor destination corner render as a bare vertical
        # line with no connector — pure noise once the endpoints are cropped
        # away. Only untouched "│" cells are cleared; a "┼" junction means a
        # different (possibly still-visible) edge's horizontal connector
        # crosses here, so it's left alone.
        for p_col, p_top, p_bot, p_label_row, p_label_start, p_label_len in margin_pipe_spans:
            if p_top < window_top and p_bot >= window_bot:
                for r in range(window_top, window_bot):
                    if 0 <= r < total_height and 0 <= p_col < total_width:
                        if strip_ansi(grid[r][p_col]) == "│":
                            grid[r][p_col] = " "
                if window_top <= p_label_row < window_bot and p_label_len > 0:
                    for j in range(p_label_len):
                        c = p_label_start + j
                        if 0 <= c < total_width:
                            grid[p_label_row][c] = " "

        # Stub-pipe terminators at the cut boundaries: pipes that enter the
        # window from above (top cut) or exit below (bottom cut) leave a bare
        # "│" at the cut row that reads as an ordinary inter-state connector
        # that just stops. Replace those cells with open half-circle arcs — ◠
        # (curve up, flat down) for top cuts, ◡ (curve down, flat up) for
        # bottom cuts — so the "this edge leaves the windowed view" signal
        # is in-band rather than requiring the reader to cross-check the
        # banner. cell.replace preserves the surrounding SGR color so the
        # terminator continues the pipe's color. The strip_ansi guard leaves
        # corners/junctions/horizontal connectors untouched.
        if lo > 0:
            top_row_cells = grid[window_top]
            for c in range(total_width):
                if strip_ansi(top_row_cells[c]) == "│":
                    top_row_cells[c] = top_row_cells[c].replace("│", "◠")
        if hi < n_layers - 1:
            bot_row_cells = grid[window_bot - 1]
            for c in range(total_width):
                if strip_ansi(bot_row_cells[c]) == "│":
                    bot_row_cells[c] = bot_row_cells[c].replace("│", "◡")

        grid = grid[window_top:window_bot]

        if lo > 0:
            reps = [layers[li][0] for li in range(0, lo)]
            banner_above = _overflow_banner("▲", lo, reps, terminal_states, tw, above=True)
        if hi < n_layers - 1:
            reps = [layers[li][0] for li in range(hi + 1, n_layers)]
            banner_below = _overflow_banner(
                "▼", n_layers - 1 - hi, reps, terminal_states, tw, above=False
            )

    # Convert grid to string
    lines = ["".join(row).rstrip() for row in grid]

    # Remove trailing empty lines
    while lines and not lines[-1].strip():
        lines.pop()

    # Hard-clamp every output line to tw display columns so an upstream layout
    # miss (forward-skip-layer gutter, post-hoc layer merge, back-edge pipe) can
    # never emit lines that overflow the terminal. Defense in depth alongside
    # the pinned-path width filter in ``_choose_pinned_layout`` — this also
    # guards the dry-run path (``run.py``) and the streaming path when neither
    # ladder degrades a too-wide diagram in time.
    if tw > 1:
        clamped: list[str] = []
        for ln in lines:
            if _display_width(ln) > tw:
                ln = _truncate_to_width_ansi(ln, tw - 1)
            clamped.append(ln)
        lines = clamped

    # Center diagram. ``_display_width`` already handles SGR CSI sequences
    # (via ``wcswidth``) so no pre-strip is needed — and stripping here would
    # discard color information used by the post-clamp label colorizer.
    max_line_len = max((_display_width(ln) for ln in lines), default=0)
    diagram_indent = max(0, (tw - max_line_len) // 2)
    if diagram_indent > 0:
        lines = [" " * diagram_indent + ln if ln.strip() else ln for ln in lines]

    body = _colorize_diagram_labels("\n".join(lines), edge_label_colors)
    if banner_above or banner_below:
        parts = [p for p in (banner_above, body, banner_below) if p]
        return "\n".join(parts)
    return body


# ---------------------------------------------------------------------------
# FSM diagram renderer (main entry point)
# ---------------------------------------------------------------------------


_MAIN_PATH_EDGE_LABELS: frozenset[str] = frozenset({"yes", "no", "next", "_"})


def _filter_main_path_graph(
    fsm: FSMLoop, edges: list[tuple[str, str, str]]
) -> tuple[list[tuple[str, str, str]], set[str]]:
    """Filter edges to the main happy-path subgraph and the states reachable through it.

    Drops off-happy-path labels (anything not in ``_MAIN_PATH_EDGE_LABELS`` and not
    a ``route``-verdict label) plus any state unreachable from ``fsm.initial`` once
    those edges are gone. Route-verdict labels (everything emitted by ``state.route``
    other than the default ``_``) are kept since routes encode normal branching.
    """
    route_verdicts: set[str] = set()
    for _name, state in fsm.states.items():
        if state.route is not None:
            route_verdicts.update(state.route.routes.keys())
        route_verdicts.update(state.extra_routes.keys())

    def _is_main_label(label: str) -> bool:
        return label in _MAIN_PATH_EDGE_LABELS or label in route_verdicts

    filtered_edges = [(s, t, lbl) for (s, t, lbl) in edges if _is_main_label(lbl)]
    _bfs_visited_order, depth_map = _bfs_order(fsm.initial, filtered_edges)
    reachable: set[str] = set(depth_map.keys())
    filtered_edges = [
        (s, t, lbl) for (s, t, lbl) in filtered_edges if s in reachable and t in reachable
    ]
    return filtered_edges, reachable


def _render_fsm_diagram(
    fsm: FSMLoop,
    verbose: bool = False,
    highlight_state: str | None = None,
    highlight_color: str = "32",
    edge_label_colors: dict[str, str] | None = None,
    badges: dict[str, str] | None = None,
    mode: str = "full",
    *,
    suppress_labels: bool = False,
    title_only: bool = False,
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
        edge_label_colors: Optional label→SGR-code mapping for transition labels.
            Falls back to hardcoded defaults when None.
        badges: Optional glyph-key→string mapping for state type badges.
            Falls back to hardcoded defaults when None.
        mode: Controls edge scope: "main" (default when filtering active) hides
            off-happy-path edges. "full" renders every edge and state. "mini" is
            an alias for main-scope; use ``suppress_labels=True, title_only=True``
            instead. Callers that need full-detail dumps (e.g. ``ll-loop info``)
            keep the default "full".
        suppress_labels: If True, edge labels are omitted from all rendered edges.
        title_only: If True, state boxes show only the state name (no action body).
    """
    edges = _collect_edges(fsm)
    if mode in ("main", "mini"):
        edges, _reachable = _filter_main_path_graph(fsm, edges)
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
            edge_label_colors,
            badges,
            title_only=title_only or (mode == "mini"),
            suppress_labels=suppress_labels or (mode == "mini"),
        )

    # Compute max node width to determine width constraint
    # Quick estimate: widest state name or badge + padding
    max_node_w = 30  # reasonable default
    for s in all_states:
        st = fsm.states.get(s)
        badge = _get_state_badge(st, badges)
        badge_w = _badge_display_width(badge) if badge else 0
        label = s
        if s == fsm.initial:
            label = "\u2192 " + label
        if s in terminal_states:
            label = label + " \u25c9"
        w = max(_display_width(label), badge_w)
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
        edge_label_colors,
        badges,
        title_only=title_only or (mode == "mini"),
        suppress_labels=suppress_labels or (mode == "mini"),
    )


def _overflow_banner(
    glyph: str,
    count: int,
    reps: list[str],
    terminal_states: set[str],
    tw: int,
    *,
    above: bool,
) -> str:
    """Render a compact windowed-diagram overflow banner.

    ``▲ 3 layers above  (init → plan → select_step)`` /
    ``▼ 6 layers below  (… → failed ◉)``. ``reps`` are representative state
    names for the cropped-away layers (first state of each). Terminal states
    keep the ``◉`` marker. The whole banner is truncated to ``tw`` columns.
    """

    def _rep(name: str) -> str:
        return f"{name} ◉" if name in terminal_states else name

    noun = "layer" if count == 1 else "layers"
    where = "above" if above else "below"
    head = f"  {glyph} {count} {noun} {where}"
    trail = " → ".join(_rep(r) for r in reps)
    if trail:
        trail = trail if above else f"… → {trail}"
        text = f"{head}  ({trail})"
    else:
        text = head
    if _display_width(text) > tw:
        # Truncate on display width, leaving room for the ellipsis + ")".
        budget = max(0, tw - 2)
        clipped = text[:budget].rstrip()
        text = clipped + "…" + (")" if text.rstrip().endswith(")") else "")
    return text


def _render_windowed_diagram(
    fsm: FSMLoop,
    active_state: str | None,
    *,
    budget: int,
    verbose: bool = False,
    highlight_color: str = "32",
    edge_label_colors: dict[str, str] | None = None,
    badges: dict[str, str] | None = None,
    mode: str = "full",
    suppress_labels: bool = False,
    title_only: bool = False,
) -> str:
    """Render the real layered diagram cropped to ±K layers around ``active_state``.

    Runs the full layered pipeline (``LayerAssigner`` → ``CrossingMinimizer`` →
    ``_render_layered_diagram``) and asks ``_render_layered_diagram`` to slice
    the finished grid to the layers that fit ``budget`` rows around the active
    state, so layout, edges, labels, badges and the highlight are the genuine
    layered ones rather than a re-synthesized subgraph (ENH-2410).

    Returns ``""`` for empty / single-state graphs or when even a one-layer
    window does not fit ``budget`` — the caller then defers to a smaller
    ladder rung (``neighborhood`` / ``single``). ``active_state`` of ``None``
    or an unknown name windows the top of the graph.
    """
    if budget <= 0:
        return ""

    edges = _collect_edges(fsm)
    if mode in ("main", "mini"):
        edges, _reachable = _filter_main_path_graph(fsm, edges)
    bfs_order_list, _bfs_depth = _bfs_order(fsm.initial, edges)
    main_path, main_edge_set = _trace_main_path(fsm, edges)
    branches, back_edges = _classify_edges(edges, main_edge_set, bfs_order_list)

    terminal_states = {name for name, state in fsm.states.items() if state.terminal}

    all_states = list(main_path)
    for src, dst, _ in branches:
        for s in (src, dst):
            if s not in all_states:
                all_states.append(s)

    # Nothing to window on a trivial graph; the caller's larger rungs handle it.
    if len(all_states) <= 1:
        return ""

    back_edge_set: set[tuple[str, str]] = {(s, d) for (s, d, _) in back_edges if s != d}

    tw = terminal_width()
    max_node_w = 30
    for s in all_states:
        st = fsm.states.get(s)
        badge = _get_state_badge(st, badges)
        badge_w = _badge_display_width(badge) if badge else 0
        label = s
        if s == fsm.initial:
            label = "→ " + label
        if s in terminal_states:
            label = label + " ◉"
        w = max(_display_width(label), badge_w)
        max_node_w = max(max_node_w, w + 4 + 4)
    max_width_per_layer = max(1, (tw - 10) // (max_node_w + 4))

    assigner = LayerAssigner(all_states, edges, back_edge_set, fsm.initial, max_width_per_layer)
    layers = assigner.assign()
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
        active_state,
        highlight_color,
        edge_label_colors,
        badges,
        title_only=title_only or (mode == "mini"),
        suppress_labels=suppress_labels or (mode == "mini"),
        window=(active_state, budget),
    )


_PREV_STATE_COLOR = "33"  # ANSI orange/yellow border for the just-prior FSM state.


def _render_neighborhood_diagram(
    fsm: FSMLoop,
    active_state: str,
    *,
    edge_label_colors: dict[str, str] | None = None,
    badges: dict[str, str] | None = None,
    highlight_color: str = "32",
    mode: str = "full",
    prev_state: str | None = None,
) -> str:
    """Render a compact 1-hop neighborhood: predecessors → [active] → successors.

    Suitable as a fallback when the full FSM diagram does not fit the viewport.
    Bounded: ``max(len(preds), len(succs), 1) * 3`` rows (each state box is 3
    lines tall). Returns the empty string when ``active_state`` is not in
    ``fsm.states``.

    Self-loops are collapsed: a state that only points to itself contributes
    neither predecessors nor successors here.

    Args:
        mode: ``"full"`` (default) includes every edge. ``"main"`` filters edges
            through ``_filter_main_path_graph`` so off-happy-path predecessors
            (e.g. those connected only via ``on_error``) are hidden. Falls back
            to ``"full"`` if the active state would be filtered out.
        prev_state: Name of the predecessor the FSM most recently transitioned
            from. When that name appears in the rendered pred stack, its box is
            drawn with the orange ``_PREV_STATE_COLOR`` border. Silently
            skipped if the name is missing from the pred stack.
    """
    if active_state not in fsm.states:
        return ""

    edges = _collect_edges(fsm)
    if mode == "main":
        filtered_edges, reachable = _filter_main_path_graph(fsm, edges)
        if active_state in reachable:
            edges = filtered_edges
    preds = sorted({s for (s, t, _lbl) in edges if t == active_state and s != active_state})
    succs = sorted({t for (s, t, _lbl) in edges if s == active_state and t != active_state})

    terminal_states = {n for n, st in fsm.states.items() if st.terminal}

    def _label(name: str) -> str:
        label = name
        if name == fsm.initial:
            label = "→ " + label
        if name in terminal_states:
            label = label + " ◉"
        return label

    pred_labels = [_label(p) for p in preds]
    active_label = _label(active_state)
    succ_labels = [_label(s) for s in succs]

    inner_pred = max((_display_width(lbl) for lbl in pred_labels), default=0)
    inner_active = _display_width(active_label)
    inner_succ = max((_display_width(lbl) for lbl in succ_labels), default=0)

    box_w_pred = inner_pred + 4 if pred_labels else 0
    box_w_active = inner_active + 4
    box_w_succ = inner_succ + 4 if succ_labels else 0

    n_rows = max(len(pred_labels), len(succ_labels), 1)
    try:
        nd_bg_code: str | None = str(int(highlight_color) + 10)
    except (ValueError, TypeError):
        nd_bg_code = None

    def _make_box(
        label: str,
        inner_w: int,
        highlighted: bool,
        *,
        border_color: str | None = None,
    ) -> list[str]:
        top = "┌" + "─" * (inner_w + 2) + "┐"
        bot = "└" + "─" * (inner_w + 2) + "┘"
        # Pad by display width (not char count) so wide glyphs keep the box square.
        padded = label + " " * max(0, inner_w - _display_width(label))
        if highlighted:
            border_code = f"{highlight_color};{nd_bg_code}" if nd_bg_code else highlight_color
            top = colorize(top, border_code)
            bot = colorize(bot, border_code)
            if nd_bg_code:
                mid = (
                    colorize("│", border_code)
                    + colorize(" ", nd_bg_code)
                    + colorize(padded, f"97;{nd_bg_code};1")
                    + colorize(" ", nd_bg_code)
                    + colorize("│", border_code)
                )
            else:
                mid = (
                    colorize("│", border_code)
                    + " "
                    + colorize(padded, f"{highlight_color};1")
                    + " "
                    + colorize("│", border_code)
                )
        elif border_color is not None:
            top = colorize(top, border_color)
            bot = colorize(bot, border_color)
            mid = (
                colorize("│", border_color)
                + " "
                + colorize(padded, "1")
                + " "
                + colorize("│", border_color)
            )
        else:
            mid = "│ " + colorize(padded, "1") + " │"
        return [top, mid, bot]

    center_idx = (n_rows - 1) // 2

    def _build_stack(
        labels: list[str],
        box_w: int,
        *,
        color_for: dict[str, str] | None = None,
    ) -> list[str]:
        rows: list[str] = []
        # Align the stack to the arrow row (the active state's slot). Without
        # this, a shorter stack always sits at row 0 and the single ``──▶``
        # arrow drawn at ``active_line_offset`` points into empty space.
        # ``min(center_idx, n_rows - len(labels))`` caps the start so longer
        # but still-smaller stacks (e.g. 4 succs vs. 5 preds) don't overflow.
        start = max(0, min(center_idx, n_rows - len(labels)))
        color_map = color_for or {}
        for i in range(n_rows):
            j = i - start
            if 0 <= j < len(labels):
                border = color_map.get(labels[j])
                rows.extend(_make_box(labels[j], box_w - 4, False, border_color=border))
            else:
                rows.extend([" " * box_w] * 3)
        return rows

    pred_color_for: dict[str, str] = {}
    if prev_state is not None and prev_state in preds:
        pred_color_for[_label(prev_state)] = _PREV_STATE_COLOR
    # Per-state "kind" color for preds so they have distinguishing hues even when
    # the active state highlight is the only color signal otherwise. Skipped when
    # a pred already has an explicit border color (e.g. prev_state orange).
    for p in preds:
        _kc = _box_kind_color(fsm.states.get(p))
        if _kc:
            lbl = _label(p)
            pred_color_for.setdefault(lbl, _kc)
    succ_color_for: dict[str, str] = {}
    for s in succs:
        _kc = _box_kind_color(fsm.states.get(s))
        if _kc:
            succ_color_for[_label(s)] = _kc

    pred_col = (
        _build_stack(pred_labels, box_w_pred, color_for=pred_color_for) if pred_labels else None
    )
    succ_col = (
        _build_stack(succ_labels, box_w_succ, color_for=succ_color_for) if succ_labels else None
    )
    active_rows: list[str] = []
    for i in range(n_rows):
        if i == center_idx:
            active_rows.extend(_make_box(active_label, inner_active, True))
        else:
            active_rows.extend([" " * box_w_active] * 3)

    arrow = "  ──▶  "
    arrow_blank = " " * len(arrow)
    active_line_offset = center_idx * 3 + 1

    total_lines = n_rows * 3
    out_lines: list[str] = []
    for i in range(total_lines):
        parts: list[str] = []
        if pred_col is not None:
            parts.append(pred_col[i])
            parts.append(arrow if i == active_line_offset else arrow_blank)
        parts.append(active_rows[i])
        if succ_col is not None:
            parts.append(arrow if i == active_line_offset else arrow_blank)
            parts.append(succ_col[i])
        out_lines.append("".join(parts).rstrip())

    return "\n".join(out_lines)


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
    edge_label_colors: dict[str, str] | None = None,
    badges: dict[str, str] | None = None,
    title_only: bool = False,
    suppress_labels: bool = False,
) -> str:
    """Simple horizontal rendering for single-state or very simple FSMs.

    When ``title_only`` is True, per-state body lines and self-loop labels are suppressed.
    When ``suppress_labels`` is True, self-loop markers omit label text.
    """
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
        all_states,
        display_label,
        fsm_states,
        verbose,
        max_box_inner,
        badges,
        title_only=title_only,
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
        _kind = _box_kind_color(fsm_states.get(sname)) if fsm_states is not None else None
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
            kind_color=_kind,
        )

    # Self-loops
    self_loops_list = [(s, d, lbl) for s, d, lbl in back_edges if s == d]
    lines = ["".join(row).rstrip() for row in rows]
    if self_loops_list:
        self_labels: dict[str, list[str]] = {}
        for src, _, label in self_loops_list:
            self_labels.setdefault(src, []).append(label)
        for sname, labels in self_labels.items():
            marker = "\u21ba" if suppress_labels else "\u21ba " + ", ".join(labels)
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

    return _colorize_diagram_labels("\n".join(lines), edge_label_colors)

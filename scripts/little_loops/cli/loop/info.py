"""ll-loop info subcommands: list, history, show."""

from __future__ import annotations

import argparse
import re
from collections import deque
from datetime import datetime
from pathlib import Path

from little_loops.cli.loop._helpers import (
    get_builtin_loops_dir,
    load_loop_with_spec,
    resolve_loop_path,
)
from little_loops.cli.output import colorize, terminal_width
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.logger import Logger


def cmd_list(
    args: argparse.Namespace,
    loops_dir: Path,
) -> int:
    """List loops."""
    if getattr(args, "running", False):
        from little_loops.fsm.persistence import list_running_loops

        states = list_running_loops(loops_dir)
        if not states:
            print("No running loops")
            return 0
        print("Running loops:")
        for state in states:
            print(f"  {state.loop_name}: {state.current_state} (iteration {state.iteration})")
        return 0

    # Collect project loops
    project_names: set[str] = set()
    yaml_files: list[Path] = []
    if loops_dir.exists():
        yaml_files = list(loops_dir.glob("*.yaml"))
        project_names = {p.stem for p in yaml_files}

    # Collect built-in loops (excluding those overridden by project)
    builtin_dir = get_builtin_loops_dir()
    builtin_files: list[Path] = []
    if builtin_dir.exists():
        builtin_files = [
            f for f in sorted(builtin_dir.glob("*.yaml")) if f.stem not in project_names
        ]

    if not yaml_files and not builtin_files:
        print("No loops available")
        return 0

    print("Available loops:")
    for path in sorted(yaml_files):
        print(f"  {path.stem}")
    for path in builtin_files:
        print(f"  {path.stem}  [built-in]")
    return 0


def cmd_history(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
) -> int:
    """Show loop history."""
    from little_loops.fsm.persistence import get_loop_history

    events = get_loop_history(loop_name, loops_dir)

    if not events:
        print(f"No history for: {loop_name}")
        return 0

    # Show last N events
    tail = getattr(args, "tail", 50)
    for event in events[-tail:]:
        raw_ts = event.get("ts", "")
        try:
            ts = datetime.fromisoformat(raw_ts).strftime("%Y-%m-%d %H:%M:%S")
        except (ValueError, TypeError):
            ts = raw_ts[:19]
        event_type = event.get("event", "")
        details = {k: v for k, v in event.items() if k not in ("event", "ts")}
        print(f"{ts} {event_type}: {details}")

    return 0


# ---------------------------------------------------------------------------
# Edge label colors (ANSI codes)
# ---------------------------------------------------------------------------

_EDGE_LABEL_COLORS: dict[str, str] = {
    "success": "32",
    "fail": "38;5;208",
    "error": "31",
    "partial": "33",
    "next": "2",
    "_": "2",
}


def _colorize_label(label: str) -> str:
    """Colorize a (possibly compound) edge label like 'fail/error'."""
    parts = label.split("/")
    code = ""
    for part in parts:
        if part in ("fail", "error"):
            code = _EDGE_LABEL_COLORS["fail"]
            break
        if part == "partial" and not code:
            code = _EDGE_LABEL_COLORS["partial"]
        elif part == "success" and not code:
            code = _EDGE_LABEL_COLORS["success"]
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
    # Determine type badge
    badge = ""
    if state and state.action_type:
        badge = f"[{state.action_type}]"
    elif state and state.action:
        badge = "[shell]"

    # Name + badge on first line
    if badge:
        candidate = f"{display_label}  {badge}"
        if len(candidate) <= inner_width:
            name_line = candidate
        else:
            # Fit badge at the expense of name truncation
            avail = inner_width - len(badge) - 2
            name_line = (
                (display_label[:avail] + "  " + badge) if avail > 0 else candidate[:inner_width]
            )
    else:
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
# FSM diagram renderer
# ---------------------------------------------------------------------------


def _render_fsm_diagram(fsm: FSMLoop, verbose: bool = False) -> str:
    """Render an improved text diagram of the FSM graph.

    Produces three sections:
      - Main flow: the primary (happy-path) traversal with edge labels
      - Branches: alternate forward transitions not on the main path
      - Back-edges: transitions to states earlier in BFS order (cycles)
    """
    # Build all edges: (from, to, label)
    edges: list[tuple[str, str, str]] = []
    for name, state in fsm.states.items():
        if state.on_success:
            edges.append((name, state.on_success, "success"))
        if state.on_failure:
            edges.append((name, state.on_failure, "fail"))
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

    # BFS to determine a canonical ordering (used for back-edge detection)
    bfs_order: list[str] = []
    bfs_depth: dict[str, int] = {fsm.initial: 0}
    queue: deque[str] = deque([fsm.initial])
    while queue:
        node = queue.popleft()
        bfs_order.append(node)
        for src, dst, _ in edges:
            if src == node and dst not in bfs_depth:
                bfs_depth[dst] = bfs_depth[node] + 1
                queue.append(dst)

    # Trace main path: greedy walk following on_success > next > first route entry
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
        nxt: str = st.on_success or st.next or ""
        if not nxt and st.route:
            nxt = next(iter(st.route.routes.values()), "") or st.route.default or ""
        if nxt:
            main_edge_set.add((current, nxt))
            current = nxt
        else:
            break

    # Classify remaining edges as branches or back-edges.
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

    terminal_states = {name for name, state in fsm.states.items() if state.terminal}
    return _render_2d_diagram(
        main_path,
        edges,
        main_edge_set,
        branches,
        back_edges,
        bfs_order,
        initial=fsm.initial,
        terminal_states=terminal_states,
        fsm_states=fsm.states,
        verbose=verbose,
    )


def _render_2d_diagram(
    main_path: list[str],
    edges: list[tuple[str, str, str]],
    main_edge_set: set[tuple[str, str]],
    branches: list[tuple[str, str, str]],
    back_edges: list[tuple[str, str, str]],
    bfs_order: list[str],
    initial: str = "",
    terminal_states: set[str] | None = None,
    fsm_states: dict[str, StateConfig] | None = None,
    verbose: bool = False,
) -> str:
    """Render a 2D box-drawing diagram of the FSM graph."""
    if not main_path:
        return ""

    # Collect all state names (main path + off-path states)
    all_states = list(main_path)
    off_path: list[str] = []
    for src, dst, _ in branches:
        for s in (src, dst):
            if s not in all_states:
                all_states.append(s)
                off_path.append(s)

    # Compute display labels (annotate initial/terminal states in diagram)
    display_label: dict[str, str] = {}
    for s in all_states:
        label = s
        if s == initial:
            label = "\u2192 " + label
        if terminal_states and s in terminal_states:
            label = label + " \u25c9"
        display_label[s] = label

    # Compute box inner content and widths
    tw = terminal_width()
    num_main = max(1, len(main_path))
    if verbose and fsm_states and main_path:
        # In verbose mode, allow wider boxes to show more content
        max_box_inner = max(20, min(60, (tw - 4) // num_main - 6))
    else:
        max_box_inner = max(20, min(40, (tw - 4) // num_main - 6))

    box_inner: dict[str, list[str]] = {}
    box_width: dict[str, int] = {}

    for s in all_states:
        state_obj = fsm_states.get(s) if fsm_states else None

        # Compute base inner width from name+badge line
        badge = ""
        if state_obj and state_obj.action_type:
            badge = f"[{state_obj.action_type}]"
        elif state_obj and state_obj.action:
            badge = "[shell]"

        base_w = len(f"{display_label[s]}  {badge}") if badge else len(display_label[s])
        base_w = max(base_w, len(display_label[s]))

        # Allow wider boxes if action content is longer
        inner_w = base_w
        if state_obj and state_obj.action and max_box_inner > 0:
            action_lines = state_obj.action.strip().splitlines()
            if verbose:
                max_action_w = max((len(ln.rstrip()) for ln in action_lines if ln.rstrip()), default=0)
                inner_w = max(base_w, min(max_action_w, max_box_inner))
            else:
                first_action = next((ln.rstrip() for ln in action_lines if ln.rstrip()), "")
                inner_w = max(base_w, min(len(first_action), max_box_inner))

        content = _box_inner_lines(state_obj, display_label[s], verbose, inner_w)
        actual_w = max(len(ln) for ln in content)
        inner_w = max(inner_w, actual_w)
        box_inner[s] = content
        box_width[s] = inner_w + 4  # "│ " + content + " │"

    # Box heights
    box_height: dict[str, int] = {s: len(box_inner[s]) + 2 for s in all_states}
    main_height = max((box_height[s] for s in main_path), default=3)

    # Compute column positions for main path boxes
    col_start: dict[str, int] = {}
    col_center: dict[str, int] = {}
    x = 2  # left margin
    for i, sname in enumerate(main_path):
        col_start[sname] = x
        col_center[sname] = x + box_width[sname] // 2
        if i < len(main_path) - 1:
            nxt = main_path[i + 1]
            label = next(
                (lbl for s, d, lbl in edges if s == sname and d == nxt),
                "\u2192",
            )
            gap = len(label) + 6  # "──label──▶"
            x += box_width[sname] + gap
        else:
            x += box_width[sname]

    # Place off-path states below, centered under their first neighbor
    for s in off_path:
        neighbor = None
        for src, dst, _ in branches + back_edges:
            if dst == s and src in col_start:
                neighbor = src
                break
            if src == s and dst in col_start:
                neighbor = dst
                break
        if neighbor:
            nc = col_center[neighbor]
            col_start[s] = max(2, nc - box_width[s] // 2)
        else:
            col_start[s] = 2
        col_center[s] = col_start[s] + box_width[s] // 2

    total_width = x + 4
    for s in off_path:
        right_edge = col_start[s] + box_width[s] + 4
        if right_edge > total_width:
            total_width = right_edge

    diagram_indent = max(0, (tw - total_width) // 2)

    # --- Build main flow rows (uniform height for all main-path boxes) ---
    rows: list[list[str]] = [[" "] * total_width for _ in range(main_height)]

    for sname in main_path:
        cx = col_start[sname]
        w = box_width[sname]
        content = box_inner[sname]

        # Top border: rows[0]
        rows[0][cx] = "\u250c"
        for j in range(1, w - 1):
            rows[0][cx + j] = "\u2500"
        rows[0][cx + w - 1] = "\u2510"

        # Content rows: rows[1..len(content)]
        for i, line in enumerate(content):
            r = i + 1
            rows[r][cx] = "\u2502"
            rows[r][cx + w - 1] = "\u2502"
            for j, ch in enumerate(line):
                if cx + 2 + j < cx + w - 1:
                    rows[r][cx + 2 + j] = ch

        # Padding rows between content and bottom border
        for r in range(len(content) + 1, main_height - 1):
            rows[r][cx] = "\u2502"
            rows[r][cx + w - 1] = "\u2502"

        # Bottom border: rows[main_height - 1]
        brow = main_height - 1
        rows[brow][cx] = "\u2514"
        for j in range(1, w - 1):
            rows[brow][cx + j] = "\u2500"
        rows[brow][cx + w - 1] = "\u2518"

    # Draw main-path edge labels on the name row (index 1) between boxes
    for i in range(len(main_path) - 1):
        src_name = main_path[i]
        dst_name = main_path[i + 1]
        label = next(
            (lbl for s, d, lbl in edges if s == src_name and d == dst_name),
            "\u2192",
        )
        start = col_start[src_name] + box_width[src_name]
        end = col_start[dst_name]
        edge_text = "\u2500" + label + "\u2500\u2500\u25b6"
        available = end - start
        left_dashes = available - len(edge_text)
        for j in range(left_dashes):
            rows[1][start + j] = "\u2500"
        for j, ch in enumerate(edge_text):
            rows[1][start + left_dashes + j] = ch

    lines = ["".join(row).rstrip() for row in rows]

    # --- Self-loops: add ↺ marker below the box ---
    self_loops = [(s, d, lbl) for s, d, lbl in back_edges if s == d]
    if self_loops:
        self_row = [" "] * total_width
        for src, _, label in self_loops:
            cx = col_center.get(src, 0)
            marker = f"\u21ba {label}"
            pos = max(0, cx - len(marker) // 2)
            for j, ch in enumerate(marker):
                if pos + j < total_width:
                    self_row[pos + j] = ch
        lines.append("".join(self_row).rstrip())

    # --- 2D routing for non-main-path edges below the main flow ---
    non_self_branches = [(s, d, lbl) for s, d, lbl in branches if s != d]
    non_self_back = [(s, d, lbl) for s, d, lbl in back_edges if s != d]
    all_extra = non_self_branches + non_self_back

    if not all_extra:
        if diagram_indent > 0:
            lines = [" " * diagram_indent + ln if ln.strip() else ln for ln in lines]
        return _colorize_diagram_labels("\n".join(lines))

    off_path_set = set(off_path)
    main_path_set = set(main_path)

    main_extra: list[tuple[str, str, str]] = []
    off_state_edges: dict[str, list[tuple[str, str, str]]] = {s: [] for s in off_path}

    for src, dst, label in all_extra:
        if src in off_path_set:
            off_state_edges[src].append((src, dst, label))
        elif dst in off_path_set:
            off_state_edges[dst].append((src, dst, label))
        else:
            main_extra.append((src, dst, label))

    # --- Main-to-main edges: U-route below ---
    for src, dst, label in main_extra:
        src_col = col_center.get(src, 0)
        dst_col = col_center.get(dst, 0)
        left = min(src_col, dst_col)
        right = max(src_col, dst_col)

        row = [" "] * total_width
        if 0 <= dst_col < total_width:
            row[dst_col] = "\u25b2"
        if 0 <= src_col < total_width:
            row[src_col] = "\u2502"
        lines.append("".join(row).rstrip())

        row = [" "] * total_width
        if left < total_width:
            row[left] = "\u2514"
        if right < total_width:
            row[right] = "\u2518"
        for j in range(left + 1, right):
            if j < total_width:
                row[j] = "\u2500"
        label_padded = f" {label} "
        lstart = (left + right) // 2 - len(label_padded) // 2
        for j, ch in enumerate(label_padded):
            pos = lstart + j
            if left < pos < right and 0 <= pos < total_width:
                row[pos] = ch
        lines.append("".join(row).rstrip())

    # --- Off-path states: render as multi-row boxes with vertical connectors ---
    for off_s in off_path:
        state_edges = off_state_edges.get(off_s, [])
        if not state_edges:
            continue

        # Find anchor state on main path
        anchor = None
        for src, dst, _ in state_edges:
            other = dst if src == off_s else src
            if other in main_path_set:
                anchor = other
                break
        if not anchor:
            anchor = main_path[0]

        # Classify edges relative to anchor
        down_labels: list[str] = []  # anchor → off_s
        up_labels: list[str] = []  # off_s → anchor
        outgoing: list[tuple[str, str, str]] = []

        for src, dst, label in state_edges:
            if src == anchor and dst == off_s:
                down_labels.append(label)
            elif src == off_s and dst == anchor:
                up_labels.append(label)
            else:
                outgoing.append((src, dst, label))

        anchor_cc = col_center[anchor]
        off_cs = col_start[off_s]
        off_w = box_width[off_s]

        has_down = bool(down_labels)
        has_up = bool(up_labels)

        if has_down and has_up:
            down_col = anchor_cc - 1
            up_col = anchor_cc + 1
        elif has_down:
            down_col = anchor_cc
            up_col = -1
        elif has_up:
            down_col = -1
            up_col = anchor_cc
        else:
            down_col = -1
            up_col = -1

        # Vertical connector rows (fixed label collision bug: separate rows per direction)
        if has_down or has_up:
            # Row 1: vertical drop (│) and rise arrow (▲)
            row = [" "] * total_width
            if has_down and 0 <= down_col < total_width:
                row[down_col] = "\u2502"
            if has_up and 0 <= up_col < total_width:
                row[up_col] = "\u25b2"
            lines.append("".join(row).rstrip())

            # Label rows: one row per direction to prevent overlap
            if has_down:
                row = [" "] * total_width
                dlabel = "/".join(down_labels)
                dstart_ideal = down_col - len(dlabel) - 1
                if dstart_ideal >= 0:
                    dstart = dstart_ideal
                else:
                    # Label can't fit left without overlapping a pipe; place right of all pipes
                    rightmost_pipe = max(down_col, up_col if has_up else down_col)
                    dstart = rightmost_pipe + 2
                for j, ch in enumerate(dlabel):          # write label first
                    if 0 <= dstart + j < total_width:
                        row[dstart + j] = ch
                if 0 <= down_col < total_width:          # then down pipe (never overwritten)
                    row[down_col] = "\u2502"
                if has_up and 0 <= up_col < total_width: # also draw the up pipe for continuity
                    row[up_col] = "\u2502"
                lines.append("".join(row).rstrip())

            if has_up:
                row = [" "] * total_width
                ulabel = "/".join(up_labels)
                ustart = up_col + 2
                for j, ch in enumerate(ulabel):          # write label first
                    if 0 <= ustart + j < total_width:
                        row[ustart + j] = ch
                if 0 <= up_col < total_width:            # then up pipe
                    row[up_col] = "\u2502"
                if has_down and 0 <= down_col < total_width: # also draw the down pipe for continuity
                    row[down_col] = "\u2502"
                lines.append("".join(row).rstrip())

            # Arrow tips row
            row = [" "] * total_width
            if has_down and 0 <= down_col < total_width:
                row[down_col] = "\u25bc"
            if has_up and 0 <= up_col < total_width:
                row[up_col] = "\u2502"
            lines.append("".join(row).rstrip())

        # Render off-path state box (multi-row)
        off_content = box_inner[off_s]
        h = box_height[off_s]
        bx = off_cs
        bw = off_w
        box_rows_r: list[list[str]] = [[" "] * total_width for _ in range(h)]

        if bx + bw <= total_width:
            # Top border
            box_rows_r[0][bx] = "\u250c"
            for j in range(1, bw - 1):
                box_rows_r[0][bx + j] = "\u2500"
            box_rows_r[0][bx + bw - 1] = "\u2510"

            # Content rows
            for i, line in enumerate(off_content):
                r = i + 1
                box_rows_r[r][bx] = "\u2502"
                box_rows_r[r][bx + bw - 1] = "\u2502"
                for j, ch in enumerate(line):
                    if bx + 2 + j < bx + bw - 1:
                        box_rows_r[r][bx + 2 + j] = ch

            # Padding rows
            for r in range(len(off_content) + 1, h - 1):
                box_rows_r[r][bx] = "\u2502"
                box_rows_r[r][bx + bw - 1] = "\u2502"

            # Bottom border
            box_rows_r[h - 1][bx] = "\u2514"
            for j in range(1, bw - 1):
                box_rows_r[h - 1][bx + j] = "\u2500"
            box_rows_r[h - 1][bx + bw - 1] = "\u2518"

        # Draw outgoing edges from off-path box on its name row (index 1)
        for src, dst, label in outgoing:
            if src == off_s:
                start_col = bx + bw
                target_col = col_center.get(dst, start_col + len(label) + 4)
                edge_text = "\u2500" + label + "\u2500\u2500\u25b6"
                available = target_col - start_col
                if available > len(edge_text):
                    left_dashes = available - len(edge_text)
                    for j in range(left_dashes):
                        if start_col + j < total_width:
                            box_rows_r[1][start_col + j] = "\u2500"
                    for j, ch in enumerate(edge_text):
                        pos = start_col + left_dashes + j
                        if pos < total_width:
                            box_rows_r[1][pos] = ch
                else:
                    for j, ch in enumerate(edge_text):
                        if start_col + j < total_width:
                            box_rows_r[1][start_col + j] = ch

        for row in box_rows_r:
            lines.append("".join(row).rstrip())

    if diagram_indent > 0:
        lines = [" " * diagram_indent + ln if ln.strip() else ln for ln in lines]
    return _colorize_diagram_labels("\n".join(lines))


# ---------------------------------------------------------------------------
# State overview table
# ---------------------------------------------------------------------------


def _compact_transitions(state: StateConfig) -> str:
    """Return a compact transition string for the overview table."""
    raw: list[tuple[str, str]] = []
    for label, target in [
        ("success", state.on_success),
        ("fail", state.on_failure),
        ("error", state.on_error),
        ("partial", state.on_partial),
        ("next", state.next),
    ]:
        if target:
            raw.append((label, target))
    if state.route:
        for verdict, target in state.route.routes.items():
            raw.append((verdict, target))
        if state.route.default:
            raw.append(("_", state.route.default))
    if not raw:
        return "\u2014"
    # Group by target, preserving first-seen order
    seen: list[str] = []
    by_target: dict[str, list[str]] = {}
    for label, target in raw:
        if target not in by_target:
            seen.append(target)
            by_target[target] = []
        by_target[target].append(label)
    return ", ".join(f"{'/'.join(by_target[t])}\u2192{t}" for t in seen)


def _print_state_overview_table(fsm: FSMLoop) -> None:
    """Print a compact summary table of all states."""
    rows: list[tuple[str, str, str, str]] = []
    for name, state in fsm.states.items():
        # State name column
        state_col = f"\u2192 {name}" if name == fsm.initial else f"  {name}"

        # Type column
        if state.terminal:
            type_col = "\u2014"
        elif state.action_type:
            type_col = state.action_type
        elif state.action:
            type_col = "shell"
        else:
            type_col = "\u2014"

        # Action preview column
        if state.terminal:
            action_col = "(terminal)"
        elif state.action:
            src_lines = [ln.rstrip() for ln in state.action.strip().splitlines() if ln.rstrip()]
            action_col = src_lines[0] if src_lines else "\u2014"
        else:
            action_col = "\u2014"

        # Transitions column
        trans_col = _compact_transitions(state)
        rows.append((state_col, type_col, action_col, trans_col))

    if not rows:
        return

    tw = terminal_width()
    headers = ("State", "Type", "Action Preview", "Transitions")
    col0_w = max(len(headers[0]), max(len(r[0]) for r in rows))
    col1_w = max(len(headers[1]), max(len(r[1]) for r in rows))
    # Remaining width split between action preview and transitions
    fixed = col0_w + col1_w + 10  # margins + separators
    remaining = max(20, tw - fixed)
    col2_w = min(50, max(len(headers[2]), max(len(r[2]) for r in rows)), remaining * 3 // 5)
    col2_w = max(10, col2_w)
    col3_w = max(10, remaining - col2_w)

    print(f"  {headers[0]:<{col0_w}}  {headers[1]:<{col1_w}}  {headers[2]:<{col2_w}}  {headers[3]}")
    dash = "\u2500"
    print(f"  {dash * col0_w}  {dash * col1_w}  {dash * col2_w}  {dash * col3_w}")
    for state_col, type_col, action_col, trans_col in rows:
        if len(action_col) > col2_w:
            action_col = action_col[: col2_w - 1] + "\u2026"
        if len(trans_col) > col3_w:
            trans_col = trans_col[: col3_w - 1] + "\u2026"
        colored_type = colorize(type_col, "2") if type_col == "\u2014" else type_col
        print(
            f"  {state_col:<{col0_w}}  {colored_type:<{col1_w}}  "
            f"{action_col:<{col2_w}}  {trans_col}"
        )


# ---------------------------------------------------------------------------
# cmd_show
# ---------------------------------------------------------------------------

_EVALUATE_TYPE_DISPLAY: dict[str, str] = {
    "llm": "LLM",
    "llm_structured": "LLM (structured)",
    "exit_code": "exit code",
    "output_numeric": "numeric",
    "output_contains": "contains",
    "output_json": "JSON",
    "convergence": "convergence",
}


def _humanize_evaluate_type(ev_type: str) -> str:
    return _EVALUATE_TYPE_DISPLAY.get(ev_type, ev_type)


def cmd_show(
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    logger: Logger,
) -> int:
    """Show loop details and structure."""
    try:
        fsm, spec = load_loop_with_spec(loop_name, loops_dir, logger)
        path = resolve_loop_path(loop_name, loops_dir)
    except FileNotFoundError as e:
        logger.error(str(e))
        return 1
    except ValueError as e:
        logger.error(f"Invalid loop: {e}")
        return 1

    tw = terminal_width()

    # Compute stats for header
    n_states = len(fsm.states)
    n_transitions = sum(
        bool(s.on_success)
        + bool(s.on_failure)
        + bool(s.on_error)
        + bool(s.on_partial)
        + bool(s.next)
        + bool(s.on_maintain)
        + (len(s.route.routes) + bool(s.route.default) if s.route else 0)
        for s in fsm.states.values()
    )

    # --- Compact metadata header ---
    # Line 1: ── name ───────── paradigm · N states · M transitions ──
    stats_parts = []
    if fsm.paradigm:
        stats_parts.append(fsm.paradigm)
    stats_parts.append(f"{n_states} states")
    stats_parts.append(f"{n_transitions} transitions")
    stats_str = " \u00b7 ".join(stats_parts)

    header_left = f"\u2500\u2500 {loop_name} "
    header_right = f" {stats_str} \u2500\u2500"
    dashes = "\u2500" * max(0, tw - len(header_left) - len(header_right))
    print(f"{header_left}{dashes}{header_right}")

    # Line 2: source · max: N iter · handoff: X [· optional fields]
    config_parts: list[str] = [str(path), f"max: {fsm.max_iterations} iter"]
    config_parts.append(f"handoff: {fsm.on_handoff}")
    if fsm.timeout:
        config_parts.append(f"timeout: {fsm.timeout}s")
    if fsm.backoff:
        config_parts.append(f"backoff: {fsm.backoff}s")
    if fsm.maintain:
        config_parts.append("maintain: yes")
    if fsm.context:
        config_parts.append(f"context: {', '.join(fsm.context.keys())}")
    if fsm.scope:
        config_parts.append(f"scope: {', '.join(fsm.scope)}")
    llm = fsm.llm
    llm_parts = []
    if llm.model != "sonnet":
        llm_parts.append(f"model={llm.model}")
    if llm.max_tokens != 256:
        llm_parts.append(f"max_tokens={llm.max_tokens}")
    if llm.timeout != 30:
        llm_parts.append(f"timeout={llm.timeout}s")
    if llm_parts:
        config_parts.append(f"llm: {', '.join(llm_parts)}")
    print("   " + " \u00b7 ".join(config_parts))

    # --- Description ---
    description = spec.get("description", "").strip()
    if description:
        print()
        print("Description:")
        for line in description.splitlines():
            print(f"  {line}")

    # --- ASCII FSM Diagram ---
    verbose = getattr(args, "verbose", False)
    print()
    print("Diagram:")
    diagram = _render_fsm_diagram(fsm, verbose=verbose)
    if diagram:
        print(diagram)

    # --- State overview table ---
    print()
    _print_state_overview_table(fsm)

    # --- States & Transitions ---
    print()
    print("States:")
    first_state = True
    for name, state in fsm.states.items():
        if not first_state:
            print()
        first_state = False

        # Improved state section header: ── name ──── MARKERS · type ──
        right_parts = []
        if name == fsm.initial:
            right_parts.append("INITIAL")
        if state.terminal:
            right_parts.append("TERMINAL")
        if state.action_type:
            right_parts.append(state.action_type)
        right_info = " \u00b7 ".join(right_parts)
        inner_left = f"\u2500\u2500 {name} "
        inner_right = f" {right_info} \u2500\u2500" if right_info else " \u2500\u2500"
        fill = "\u2500" * max(0, tw - 2 - len(inner_left) - len(inner_right))
        print(f"  {inner_left}{fill}{inner_right}")

        if state.action:
            if verbose:
                indented = "\n      ".join(state.action.strip().splitlines())
                print(f"    action:\n      {indented}")
            elif state.action_type == "prompt":
                lines_act = state.action.strip().splitlines()
                preview = "\n      ".join(lines_act[:3])
                if len(lines_act) > 3 or len(state.action) > 200:
                    preview += " ..."
                print(f"    action:\n      {preview}")
            else:  # shell, slash_command, or None
                action_display = (
                    state.action[:70] + "..." if len(state.action) > 70 else state.action
                )
                print(f"    action: {action_display}")
        if state.evaluate:
            ev = state.evaluate
            print(f"    evaluate: {_humanize_evaluate_type(ev.type)}")
            if ev.prompt:
                if verbose:
                    print("      prompt:")
                    for line in ev.prompt.strip().splitlines():
                        print(f"    \u2502 {line}")
                else:
                    ev_lines = ev.prompt.strip().splitlines()
                    preview = ev_lines[0][:100] + (
                        " ..." if len(ev_lines) > 1 or len(ev_lines[0]) > 100 else ""
                    )
                    print(f"      prompt: {preview}")
            if ev.min_confidence != 0.5:
                print(f"      min_confidence: {ev.min_confidence}")
            if ev.operator:
                print(f"      operator: {ev.operator} {ev.target}")
            if ev.pattern:
                print(f"      pattern: {ev.pattern}")
        if state.capture:
            print(f"    capture: {state.capture}")
        if state.timeout:
            print(f"    timeout: {state.timeout}s")
        # Collect (label, target) pairs
        raw_transitions: list[tuple[str, str]] = []
        for label, target in [
            ("success", state.on_success),
            ("failure", state.on_failure),
            ("error", state.on_error),
            ("partial", state.on_partial),
            ("next", state.next),
            ("maintain", state.on_maintain),
        ]:
            if target:
                raw_transitions.append((label, target))
        if state.route:
            for verdict, target in state.route.routes.items():
                raw_transitions.append((verdict, target))
            if state.route.default:
                raw_transitions.append(("_", state.route.default))
        # Group by target, preserving first-seen order
        target_labels: dict[str, list[str]] = {}
        seen_targets: list[str] = []
        for label, target in raw_transitions:
            if target not in target_labels:
                target_labels[target] = []
                seen_targets.append(target)
            target_labels[target].append(label)
        transitions = [
            f"{_colorize_label('/'.join(target_labels[t]))} \u2500\u2500\u2192 {t}"
            for t in seen_targets
        ]
        if transitions:
            print("    Transitions:")
            for t in transitions:
                print(f"      {t}")

    # --- Commands ---
    print()
    print("Commands:")
    cmds = [
        (f"ll-loop run {loop_name}", "run"),
        (f"ll-loop test {loop_name}", "single test iteration"),
        (f"ll-loop stop {loop_name}", "stop a running loop"),
        (f"ll-loop status {loop_name}", "check if running"),
        (f"ll-loop history {loop_name}", "execution history"),
    ]
    col_width = max(len(c) for c, _ in cmds) + 2
    for cmd, comment in cmds:
        print(f"  {cmd:<{col_width}}  # {comment}")

    return 0

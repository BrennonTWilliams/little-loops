"""ll-loop info subcommands: list, history, show."""

from __future__ import annotations

import argparse
from collections import deque
from datetime import datetime
from pathlib import Path

from little_loops.cli.loop._helpers import (
    get_builtin_loops_dir,
    load_loop_with_spec,
    resolve_loop_path,
)
from little_loops.cli.output import terminal_width
from little_loops.fsm.schema import FSMLoop
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


def _render_fsm_diagram(fsm: FSMLoop) -> str:
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
    # Only consume one edge per main-path (src, dst) pair so that duplicate
    # edges (e.g. route_state→done via "pass" AND "skip") are not all dropped.
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
            label = "→ " + label
        if terminal_states and s in terminal_states:
            label = label + " ◉"
        display_label[s] = label

    # Box dimensions: 1 char padding each side
    box_width: dict[str, int] = {}
    for s in all_states:
        box_width[s] = len(display_label[s]) + 4  # "│ label │"

    # Compute column positions for main path boxes
    col_start: dict[str, int] = {}  # left edge of each box
    col_center: dict[str, int] = {}  # center column of each box
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
        # Find a neighbor on the main path
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

    total_width = x + 4  # some right margin
    # Ensure off-path boxes fit within total_width
    for s in off_path:
        right_edge = col_start[s] + box_width[s] + 4
        if right_edge > total_width:
            total_width = right_edge

    # --- Build main flow rows (3 rows: top border, name, bottom border) ---
    row_top = [" "] * total_width
    row_mid = [" "] * total_width
    row_bot = [" "] * total_width

    for sname in main_path:
        cx = col_start[sname]
        w = box_width[sname]
        # Top border: ┌──...──┐
        row_top[cx] = "\u250c"
        for j in range(1, w - 1):
            row_top[cx + j] = "\u2500"
        row_top[cx + w - 1] = "\u2510"
        # Middle: │ label │
        row_mid[cx] = "\u2502"
        row_mid[cx + w - 1] = "\u2502"
        name_start = cx + 2
        for j, ch in enumerate(display_label[sname]):
            row_mid[name_start + j] = ch
        # Bottom border: └──...──┘
        row_bot[cx] = "\u2514"
        for j in range(1, w - 1):
            row_bot[cx + j] = "\u2500"
        row_bot[cx + w - 1] = "\u2518"

    # Draw main-path edge labels on the middle row between boxes
    for i in range(len(main_path) - 1):
        src_name = main_path[i]
        dst_name = main_path[i + 1]
        label = next(
            (lbl for s, d, lbl in edges if s == src_name and d == dst_name),
            "\u2192",
        )
        start = col_start[src_name] + box_width[src_name]
        end = col_start[dst_name]
        # Fill: ──label──▶
        edge_text = "\u2500" + label + "\u2500\u2500\u25b6"
        # Right-align the edge_text, fill left side with ─
        available = end - start
        left_dashes = available - len(edge_text)
        for j in range(left_dashes):
            row_mid[start + j] = "\u2500"
        for j, ch in enumerate(edge_text):
            row_mid[start + left_dashes + j] = ch

    lines = [
        "".join(row_top).rstrip(),
        "".join(row_mid).rstrip(),
        "".join(row_bot).rstrip(),
    ]

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
        return "\n".join(lines)

    off_path_set = set(off_path)
    main_path_set = set(main_path)

    # Categorize: main-to-main edges vs edges involving off-path states
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

        # Connector row: \u25b2 at destination, \u2502 at source
        row = [" "] * total_width
        if 0 <= dst_col < total_width:
            row[dst_col] = "\u25b2"  # \u25b2
        if 0 <= src_col < total_width:
            row[src_col] = "\u2502"  # \u2502
        lines.append("".join(row).rstrip())

        # Horizontal route: \u2514\u2500\u2500\u2500label\u2500\u2500\u2500\u2518
        row = [" "] * total_width
        if left < total_width:
            row[left] = "\u2514"  # \u2514
        if right < total_width:
            row[right] = "\u2518"  # \u2518
        for j in range(left + 1, right):
            if j < total_width:
                row[j] = "\u2500"  # \u2500
        # Center the label on the horizontal segment
        label_padded = f" {label} "
        lstart = (left + right) // 2 - len(label_padded) // 2
        for j, ch in enumerate(label_padded):
            pos = lstart + j
            if left < pos < right and 0 <= pos < total_width:
                row[pos] = ch
        lines.append("".join(row).rstrip())

    # --- Off-path states: render as boxes with vertical connectors ---
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
        down_labels: list[str] = []  # anchor \u2192 off_s
        up_labels: list[str] = []  # off_s \u2192 anchor
        outgoing: list[tuple[str, str, str]] = []  # edges to/from non-anchor states

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

        # Vertical connector rows
        if has_down or has_up:
            # Row 1: vertical drops / rise arrow
            row = [" "] * total_width
            if has_down and 0 <= down_col < total_width:
                row[down_col] = "\u2502"  # \u2502
            if has_up and 0 <= up_col < total_width:
                row[up_col] = "\u25b2"  # \u25b2
            lines.append("".join(row).rstrip())

            # Row 2: labels alongside vertical lines
            row = [" "] * total_width
            if has_down and 0 <= down_col < total_width:
                row[down_col] = "\u2502"  # \u2502
                dlabel = "/".join(down_labels)
                dstart = max(0, down_col - len(dlabel) - 1)
                for j, ch in enumerate(dlabel):
                    if 0 <= dstart + j < total_width:
                        row[dstart + j] = ch
            if has_up and 0 <= up_col < total_width:
                row[up_col] = "\u2502"  # \u2502
                ulabel = "/".join(up_labels)
                ustart = up_col + 2
                for j, ch in enumerate(ulabel):
                    if 0 <= ustart + j < total_width:
                        row[ustart + j] = ch
            lines.append("".join(row).rstrip())

            # Row 3: arrow tips
            row = [" "] * total_width
            if has_down and 0 <= down_col < total_width:
                row[down_col] = "\u25bc"  # \u25bc
            if has_up and 0 <= up_col < total_width:
                row[up_col] = "\u2502"  # \u2502
            lines.append("".join(row).rstrip())

        # Render off-path state box
        bx = off_cs
        bw = off_w
        box_top_r = [" "] * total_width
        box_mid_r = [" "] * total_width
        box_bot_r = [" "] * total_width

        if bx + bw <= total_width:
            box_top_r[bx] = "\u250c"
            for j in range(1, bw - 1):
                box_top_r[bx + j] = "\u2500"
            box_top_r[bx + bw - 1] = "\u2510"

            box_mid_r[bx] = "\u2502"
            box_mid_r[bx + bw - 1] = "\u2502"
            for j, ch in enumerate(display_label[off_s]):
                box_mid_r[bx + 2 + j] = ch

            box_bot_r[bx] = "\u2514"
            for j in range(1, bw - 1):
                box_bot_r[bx + j] = "\u2500"
            box_bot_r[bx + bw - 1] = "\u2518"

        # Draw outgoing edges from off-path box on its middle row
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
                            box_mid_r[start_col + j] = "\u2500"
                    for j, ch in enumerate(edge_text):
                        pos = start_col + left_dashes + j
                        if pos < total_width:
                            box_mid_r[pos] = ch
                else:
                    for j, ch in enumerate(edge_text):
                        if start_col + j < total_width:
                            box_mid_r[start_col + j] = ch

        lines.append("".join(box_top_r).rstrip())
        lines.append("".join(box_mid_r).rstrip())
        lines.append("".join(box_bot_r).rstrip())

    return "\n".join(lines)


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

    # --- Metadata header ---
    separator_dashes = "─" * max(0, terminal_width() - len(loop_name) - 4)
    print(f"── {loop_name} {separator_dashes}")
    if fsm.paradigm:
        print(f"Paradigm: {fsm.paradigm}")
    print(f"Max iterations: {fsm.max_iterations}")
    print(f"On handoff: {fsm.on_handoff}")
    if fsm.timeout:
        print(f"Timeout: {fsm.timeout}s")
    if fsm.backoff:
        print(f"Backoff: {fsm.backoff}s")
    if fsm.maintain:
        print("Maintain: yes (restarts after completion)")
    if fsm.context:
        print(f"Context variables: {', '.join(fsm.context.keys())}")
    if fsm.scope:
        print(f"Scope: {', '.join(fsm.scope)}")
    llm = fsm.llm
    llm_parts = []
    if llm.model != "sonnet":
        llm_parts.append(f"model={llm.model}")
    if llm.max_tokens != 256:
        llm_parts.append(f"max_tokens={llm.max_tokens}")
    if llm.timeout != 30:
        llm_parts.append(f"timeout={llm.timeout}s")
    if llm_parts:
        print(f"LLM config: {', '.join(llm_parts)}")
    print(f"Source: {path}")
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
    paradigm_str = f" · {fsm.paradigm} paradigm" if fsm.paradigm else ""
    print(f"  {n_states} states · {n_transitions} transitions{paradigm_str}")

    # --- Description ---
    description = spec.get("description", "").strip()
    if description:
        print()
        print("Description:")
        for line in description.splitlines():
            print(f"  {line}")

    # --- ASCII FSM Diagram ---
    print()
    print("Diagram:")
    diagram = _render_fsm_diagram(fsm)
    if diagram:
        print(diagram)

    # --- States & Transitions ---
    print()
    print("States:")
    verbose = getattr(args, "verbose", False)
    first_state = True
    for name, state in fsm.states.items():
        if not first_state:
            print()
        first_state = False
        terminal_marker = " [TERMINAL]" if state.terminal else ""
        initial_marker = " [INITIAL]" if name == fsm.initial else ""
        type_badge = f" ({state.action_type})" if state.action_type else ""
        print(f"  [{name}]{initial_marker}{terminal_marker}{type_badge}")
        if state.action:
            if verbose:
                indented = "\n      ".join(state.action.strip().splitlines())
                print(f"    action:\n      {indented}")
            elif state.action_type == "prompt":
                lines = state.action.strip().splitlines()
                preview = "\n      ".join(lines[:3])
                if len(lines) > 3 or len(state.action) > 200:
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
                    lines = ev.prompt.strip().splitlines()
                    preview = lines[0][:100] + (
                        " ..." if len(lines) > 1 or len(lines[0]) > 100 else ""
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
        # Collect (label, target) pairs with on_ prefix stripped
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
            f"{'/'.join(target_labels[t])} \u2500\u2500\u2192 {t}" for t in seen_targets
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

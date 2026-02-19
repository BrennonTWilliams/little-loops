"""ll-loop info subcommands: list, history, show."""

from __future__ import annotations

import argparse
from collections import deque
from pathlib import Path

from little_loops.cli.loop._helpers import (
    get_builtin_loops_dir,
    load_loop_with_spec,
    resolve_loop_path,
)
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
        ts = event.get("ts", "")[:19]  # Truncate to seconds
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
            nxt = next(iter(st.route.routes.values()), None) or st.route.default or ""
        if nxt:
            main_edge_set.add((current, nxt))
            current = nxt
        else:
            break

    lines: list[str] = []

    # Render main flow with transition labels
    if main_path:
        parts: list[str] = []
        for i, sname in enumerate(main_path):
            parts.append(f"[{sname}]")
            if i < len(main_path) - 1:
                nxt_name = main_path[i + 1]
                label = next(
                    (lbl for s, d, lbl in edges if s == sname and d == nxt_name),
                    "\u2192",
                )
                parts.append(f" \u2500\u2500({label})\u2500\u2500\u25b6 ")
        lines.append("  " + "".join(parts))

    # Classify remaining edges as branches or back-edges
    branches: list[tuple[str, str, str]] = []
    back_edges: list[tuple[str, str, str]] = []
    for src, dst, label in edges:
        if (src, dst) in main_edge_set:
            continue
        src_pos = bfs_order.index(src) if src in bfs_order else len(bfs_order)
        dst_pos = bfs_order.index(dst) if dst in bfs_order else len(bfs_order)
        if dst == src or dst_pos < src_pos:
            back_edges.append((src, dst, label))
        else:
            branches.append((src, dst, label))

    if branches:
        lines.append("")
        lines.append("  Branches:")
        for src, dst, label in branches:
            lines.append(f"    [{src}] \u2500\u2500({label})\u2500\u2500\u25b6 [{dst}]")

    if back_edges:
        lines.append("")
        lines.append("  Back-edges (\u21ba):")
        for src, dst, label in back_edges:
            arrow = f"[{src}] \u2500\u2500({label})\u2500\u2500\u25b6 [{dst}]"
            if dst == src:
                lines.append(f"    {arrow}  \u21ba self-loop")
            else:
                lines.append(f"    {arrow}  \u21ba")

    return "\n".join(lines)


def cmd_show(
    loop_name: str,
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

    # --- Metadata ---
    print(f"Loop: {fsm.name}")
    if fsm.paradigm:
        print(f"Paradigm: {fsm.paradigm}")
    description = spec.get("description", "").strip()
    if description:
        print(f"Description: {description}")
    print(f"Max iterations: {fsm.max_iterations}")
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
    print(f"Source: {path}")

    # --- States & Transitions ---
    print()
    print("States:")
    for name, state in fsm.states.items():
        terminal_marker = " [TERMINAL]" if state.terminal else ""
        initial_marker = " [INITIAL]" if name == fsm.initial else ""
        print(f"  [{name}]{initial_marker}{terminal_marker}")
        if state.action:
            action_display = state.action[:70] + "..." if len(state.action) > 70 else state.action
            print(f"    action: {action_display}")
        if state.action_type:
            print(f"    type: {state.action_type}")
        if state.evaluate:
            print(f"    evaluate: {state.evaluate.type}")
        if state.on_success:
            print(f"    on_success \u2500\u2500\u2192 {state.on_success}")
        if state.on_failure:
            print(f"    on_failure \u2500\u2500\u2192 {state.on_failure}")
        if state.on_error:
            print(f"    on_error \u2500\u2500\u2192 {state.on_error}")
        if state.next:
            print(f"    next \u2500\u2500\u2192 {state.next}")
        if state.route:
            print("    route:")
            for verdict, target in state.route.routes.items():
                print(f"      {verdict} \u2500\u2500\u2192 {target}")
            if state.route.default:
                print(f"      _ \u2500\u2500\u2192 {state.route.default}")

    # --- ASCII FSM Diagram ---
    print()
    print("Diagram:")
    diagram = _render_fsm_diagram(fsm)
    if diagram:
        print(diagram)

    # --- Run Command ---
    print()
    print("Run command:")
    print(f"  ll-loop run {loop_name}")

    return 0

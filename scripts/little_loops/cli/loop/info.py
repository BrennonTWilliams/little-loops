"""ll-loop info subcommands: list, history, show."""

from __future__ import annotations

import argparse
from pathlib import Path

from little_loops.cli.loop._helpers import (
    get_builtin_loops_dir,
    load_loop_with_spec,
    resolve_loop_path,
)
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
            action_display = (
                state.action[:70] + "..." if len(state.action) > 70 else state.action
            )
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
    # Build adjacency for diagram
    edges: list[tuple[str, str, str]] = []  # (from, to, label)
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

    # Trace linear path from initial state for main flow
    visited: set[str] = set()
    main_path: list[str] = []
    current = fsm.initial
    while current and current not in visited:
        visited.add(current)
        main_path.append(current)
        st = fsm.states.get(current)
        if not st or st.terminal:
            break
        # Follow primary transition
        nxt = st.on_success or st.next
        if nxt:
            current = nxt
        elif st.route:
            # Pick first route entry as primary
            first_target = next(iter(st.route.routes.values()), None)
            current = first_target or st.route.default or ""
        else:
            break

    # Render main flow
    if main_path:
        flow_parts = [f"[{s}]" for s in main_path]
        arrow = " \u2500\u2500\u2192 "
        print(f"  {arrow.join(flow_parts)}")

    # Render back-edges and alternate transitions
    for src, dst, label in edges:
        if src in visited and dst in visited:
            # Skip edges already shown in main flow
            src_idx = main_path.index(src) if src in main_path else -1
            dst_idx = main_path.index(dst) if dst in main_path else -1
            if dst_idx == src_idx + 1 and label in ("success", "next"):
                continue
        print(f"  [{src}] \u2500\u2500({label})\u2500\u2500\u2192 [{dst}]")

    # --- Run Command ---
    print()
    print("Run command:")
    print(f"  ll-loop run {loop_name}")

    return 0

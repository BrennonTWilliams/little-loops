"""ll-loop info subcommands: list, history, show."""

from __future__ import annotations

import argparse
import os
from datetime import datetime
from pathlib import Path
from typing import Any

from little_loops.cli.loop._helpers import (
    get_builtin_loops_dir,
    load_loop_with_spec,
    resolve_loop_path,
)
from little_loops.cli.loop.layout import (  # noqa: F401
    _EDGE_LABEL_COLORS,
    _box_inner_lines,
    _colorize_diagram_labels,
    _colorize_label,
    _render_fsm_diagram,
)
from little_loops.cli.output import colorize, print_json, terminal_width
from little_loops.fsm.schema import FSMLoop, StateConfig
from little_loops.logger import Logger


def _load_loop_meta(path: Path) -> str:
    """Return description from a loop YAML file."""
    import yaml

    try:
        with open(path) as f:
            spec = yaml.safe_load(f) or {}
        desc_raw = spec.get("description", "") or ""
        return desc_raw.splitlines()[0] if desc_raw.strip() else ""
    except Exception:
        return ""


def cmd_list(
    args: argparse.Namespace,
    loops_dir: Path,
) -> int:
    """List loops."""
    status_filter = getattr(args, "status", None)
    if getattr(args, "running", False) or status_filter:
        from little_loops.fsm.persistence import list_running_loops

        states = list_running_loops(loops_dir)
        if status_filter:
            states = [s for s in states if s.status == status_filter]
        if not states:
            if status_filter:
                print(f"No loops with status: {status_filter}")
                return 1
            print("No running loops")
            return 0
        if getattr(args, "json", False):
            print_json([s.to_dict() for s in states])
            return 0
        print(colorize("Running loops:", "1"))
        _STATUS_COLORS = {"running": "32", "interrupted": "33", "stopped": "2"}
        for state in states:
            elapsed_s = (state.accumulated_ms or 0) // 1000
            elapsed_str = (
                f"{elapsed_s}s" if elapsed_s < 60 else f"{elapsed_s // 60}m {elapsed_s % 60}s"
            )
            name_str = colorize(state.loop_name, "1")
            state_str = colorize(state.current_state, "34")
            status_color = _STATUS_COLORS.get(state.status, "2")
            status_str = colorize(f"[{state.status}]", status_color)
            elapsed_colored = colorize(elapsed_str, "2")
            print(
                f"  {name_str}: {state_str} (iteration {state.iteration})"
                f" {status_str} {elapsed_colored}"
            )
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
        if getattr(args, "json", False):
            print_json([])
            return 0
        print("No loops available")
        return 0

    if getattr(args, "json", False):
        items: list[dict[str, Any]] = [{"name": p.stem, "path": str(p)} for p in sorted(yaml_files)]
        items += [{"name": p.stem, "path": str(p), "built_in": True} for p in builtin_files]
        print_json(items)
        return 0

    if yaml_files and builtin_files:
        print(colorize(f"Project loops ({len(yaml_files)}):", "1"))
        for path in sorted(yaml_files):
            desc = _load_loop_meta(path)
            name_str = colorize(path.stem, "36;1")
            desc_str = f"  {colorize(desc, '2')}" if desc else ""
            print(f"  {name_str}{desc_str}")
        print()
        print(colorize(f"Built-in loops ({len(builtin_files)}):", "1"))
        for path in builtin_files:
            desc = _load_loop_meta(path)
            name_str = colorize(path.stem, "36;1")
            desc_str = f"  {colorize(desc, '2')}" if desc else ""
            tag_str = colorize("[built-in]", "2")
            print(f"  {name_str}{desc_str}  {tag_str}")
    elif yaml_files:
        print(colorize("Available loops:", "1"))
        for path in sorted(yaml_files):
            desc = _load_loop_meta(path)
            name_str = colorize(path.stem, "36;1")
            desc_str = f"  {colorize(desc, '2')}" if desc else ""
            print(f"  {name_str}{desc_str}")
    else:
        print(colorize("Available loops:", "1"))
        for path in builtin_files:
            desc = _load_loop_meta(path)
            name_str = colorize(path.stem, "36;1")
            desc_str = f"  {colorize(desc, '2')}" if desc else ""
            tag_str = colorize("[built-in]", "2")
            print(f"  {name_str}{desc_str}  {tag_str}")
    return 0


_EVENT_TYPE_WIDTH = 16  # width of "handoff_detected"


def _truncate(text: str, max_len: int) -> str:
    """Truncate text to max_len with ellipsis."""
    if max_len < 1:
        return ""
    if len(text) <= max_len:
        return text
    return text[: max_len - 1] + "\u2026"


def _format_history_event(
    event: dict[str, Any], verbose: bool, width: int, full: bool = False
) -> str | None:
    """Format a single history event. Returns None to skip the event."""
    raw_ts = event.get("ts", "")
    try:
        ts = datetime.fromisoformat(raw_ts).strftime("%H:%M:%S")
    except (ValueError, TypeError):
        ts = raw_ts[:8] if len(raw_ts) >= 8 else raw_ts.ljust(8)

    event_type = event.get("event", "unknown")

    if event_type == "action_output" and not verbose:
        return None

    ts_str = colorize(ts, "2")
    etype_padded = event_type.ljust(_EVENT_TYPE_WIDTH)
    etype_color = "0"
    detail = ""
    extra_lines: list[str] = []

    # Indentation prefix for verbose sub-lines (aligns under event detail column)
    _indent = " " * (8 + 2 + _EVENT_TYPE_WIDTH + 2)

    if event_type == "loop_start":
        etype_color = "1"
        detail = event.get("loop", "")

    elif event_type == "loop_complete":
        etype_color = "1"
        final_state = event.get("final_state", "")
        iterations = event.get("iterations", "")
        terminated_by = event.get("terminated_by", "")
        detail = f"{final_state}  {iterations} iter  [{terminated_by}]"

    elif event_type == "loop_resume":
        etype_color = "1"
        from_state = event.get("from_state", "")
        iteration = event.get("iteration", "")
        detail = f"from={from_state}  iter={iteration}"

    elif event_type == "state_enter":
        etype_color = "34"
        state = event.get("state", "")
        iteration = event.get("iteration", "")
        detail = f"{colorize(state, '1')}  (iter {iteration})"

    elif event_type == "action_start":
        action = event.get("action", "")
        is_prompt = event.get("is_prompt", False)
        kind_label = "prompt" if is_prompt else "shell"
        kind_str = colorize(f"[{kind_label}]", "2")
        first_line = (
            next((ln.strip() for ln in action.splitlines() if ln.strip()), "")
            if is_prompt
            else action
        )
        avail = width - 8 - 2 - _EVENT_TYPE_WIDTH - 2 - len(kind_label) - 2 - 2
        detail = f"{_truncate(first_line, max(avail, 20))}  {kind_str}"

    elif event_type == "action_output":
        # Only reached in verbose mode
        etype_color = "2"
        detail = colorize("\u2502 " + event.get("line", ""), "2")

    elif event_type == "action_complete":
        exit_code = event.get("exit_code", 0)
        duration_ms = event.get("duration_ms", 0)
        if exit_code == 0:
            etype_color = "2"
            status_str = colorize("\u2713", "32")
        else:
            etype_color = "38;5;208"
            status_str = colorize(f"\u2717 exit={exit_code}", "38;5;208")
        detail = f"{status_str}  {duration_ms}ms"
        is_prompt = event.get("is_prompt", False)
        session_jsonl = event.get("session_jsonl") if is_prompt else None
        if session_jsonl:
            session_display = session_jsonl if verbose else os.path.basename(session_jsonl)
            detail += f"  session={colorize(session_display, '2')}"
        if verbose:
            output_preview = event.get("output_preview", "")
            if output_preview:
                avail_w = width - len(_indent) - 2
                preview_text = (
                    output_preview if full else _truncate(output_preview, max(avail_w, 40))
                )
                for preview_line in preview_text.splitlines()[:5]:
                    extra_lines.append(colorize(_indent + "\u2502 " + preview_line, "2"))

    elif event_type == "evaluate":
        verdict = event.get("verdict", "")
        confidence = event.get("confidence", "")
        reason = event.get("reason", "")
        if verdict == "success":
            etype_color = "32"
            verdict_str = colorize("\u2713 success", "32")
        else:
            etype_color = "38;5;208"
            verdict_str = colorize(f"\u2717 {verdict}", "38;5;208")
        conf_part = f"  confidence={confidence}" if confidence != "" else ""
        avail = width - 8 - 2 - _EVENT_TYPE_WIDTH - 2 - len("\u2713 success") - len(conf_part) - 2
        reason_part = f"  {_truncate(reason, max(avail, 20))}" if reason else ""
        detail = f"{verdict_str}{conf_part}{reason_part}"
        if verbose:
            llm_model = event.get("llm_model", "")
            llm_latency_ms = event.get("llm_latency_ms", "")
            llm_prompt = event.get("llm_prompt", "")
            llm_raw_output = event.get("llm_raw_output", "")
            if llm_model or llm_prompt:
                meta_parts = []
                if llm_model:
                    meta_parts.append(f"model={llm_model}")
                if llm_latency_ms != "":
                    meta_parts.append(f"latency={llm_latency_ms}ms")
                meta_str = "  ".join(meta_parts)
                extra_lines.append(
                    colorize(_indent + colorize("LLM Call", "2") + "  " + meta_str, "2")
                )
                avail_w = width - len(_indent) - len("Prompt:   ") - 2
                if llm_prompt:
                    prompt_text = llm_prompt if full else _truncate(llm_prompt, max(avail_w, 40))
                    extra_lines.append(colorize(_indent + "Prompt:   " + prompt_text, "2"))
                if llm_raw_output:
                    resp_text = (
                        llm_raw_output if full else _truncate(llm_raw_output, max(avail_w, 40))
                    )
                    extra_lines.append(colorize(_indent + "Response: " + resp_text, "2"))

    elif event_type == "route":
        etype_color = "2"
        from_state = event.get("from", "")
        to_state = event.get("to", "")
        detail = f"{from_state} \u2192 {colorize(to_state, '34')}"

    elif event_type == "handoff_detected":
        etype_color = "33"
        detail = f"state={event.get('state', '')}  iter={event.get('iteration', '')}"

    else:
        details = {k: v for k, v in event.items() if k not in ("event", "ts")}
        detail = "  ".join(f"{k}={v}" for k, v in details.items())

    etype_str = colorize(etype_padded, etype_color)
    main_line = f"{ts_str}  {etype_str}  {detail}"
    if extra_lines:
        return "\n".join([main_line] + extra_lines)
    return main_line


def _format_duration(ms: int) -> str:
    """Format milliseconds as a human-readable duration."""
    if ms < 1000:
        return f"{ms}ms"
    s = ms // 1000
    if s < 60:
        return f"{s}s"
    m, s = divmod(s, 60)
    if m < 60:
        return f"{m}m{s:02d}s"
    h, m = divmod(m, 60)
    return f"{h}h{m:02d}m{s:02d}s"


def _list_archived_runs(loop_name: str, loops_dir: Path, as_json: bool) -> int:
    """List archived runs for a loop."""
    import json as _json

    from little_loops.fsm.persistence import HISTORY_DIR, LoopState

    history_base = loops_dir / HISTORY_DIR / loop_name
    if not history_base.exists():
        print(f"No history for: {loop_name}")
        return 0

    # Collect (run_id, state_or_None) pairs sorted newest first by run_id
    runs: list[tuple[str, LoopState | None]] = []
    for run_dir in sorted(history_base.iterdir(), key=lambda d: d.name, reverse=True):
        if not run_dir.is_dir():
            continue
        state_file = run_dir / "state.json"
        state: LoopState | None = None
        if state_file.exists():
            try:
                data = _json.loads(state_file.read_text())
                state = LoopState.from_dict(data)
            except (ValueError, KeyError):
                pass
        runs.append((run_dir.name, state))

    if not runs:
        print(f"No history for: {loop_name}")
        return 0

    if as_json:
        print(
            _json.dumps(
                [
                    {
                        "run_id": rid,
                        "status": s.status if s else None,
                        "started_at": s.started_at if s else None,
                        "iterations": s.iteration if s else None,
                        "duration_ms": s.accumulated_ms if s else None,
                    }
                    for rid, s in runs
                ],
                indent=2,
            )
        )
        return 0

    status_colors = {
        "completed": "\033[32m",
        "failed": "\033[31m",
        "interrupted": "\033[33m",
        "awaiting_continuation": "\033[36m",
        "timed_out": "\033[33m",
        "running": "\033[34m",
    }
    reset = "\033[0m"

    print(f"Archived runs for: {loop_name} ({len(runs)} total)")
    print()

    for run_id, state in runs:
        if state is not None:
            color = status_colors.get(state.status, "")
            status_str = f"{color}{state.status}{reset}"
            duration_str = _format_duration(state.accumulated_ms) if state.accumulated_ms else "?"
            started = state.started_at[:19].replace("T", " ") if state.started_at else "?"
            iters = f"{state.iteration} iters"
        else:
            status_str = "unknown"
            duration_str = "?"
            started = "?"
            iters = "?"
        print(f"  {run_id}  {status_str}  {started}  {iters}  {duration_str}")

    print()
    print(f"To view events: ll-loop history {loop_name} <run-id>")
    return 0


def cmd_history(
    loop_name: str,
    run_id: str | None,
    args: argparse.Namespace,
    loops_dir: Path,
) -> int:
    """Show loop history.

    Without run_id: lists all archived runs with status and duration.
    With run_id: shows events for that specific archived run.
    """
    tail = getattr(args, "tail", 50)
    full = getattr(args, "full", False)
    verbose = getattr(args, "verbose", False) or full
    as_json = getattr(args, "json", False)

    if run_id is None:
        return _list_archived_runs(loop_name, loops_dir, as_json)

    # Show events for a specific archived run
    from little_loops.fsm.persistence import get_archived_events

    events = get_archived_events(loop_name, run_id, loops_dir)

    if not events:
        print(f"No events found for run: {loop_name}/{run_id}")
        return 1

    w = terminal_width()
    if not verbose:
        events = [e for e in events if e.get("event") != "action_output"]
    if as_json:
        print_json(events[-tail:])
        return 0
    for event in events[-tail:]:
        line = _format_history_event(event, verbose, w, full=full)
        if line is not None:
            print(line)

    return 0


# ---------------------------------------------------------------------------
# FSM diagram renderer — delegated to layout module (re-exported above)
# ---------------------------------------------------------------------------


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
        path = resolve_loop_path(loop_name, loops_dir)
        fsm, spec = load_loop_with_spec(loop_name, loops_dir, logger)
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
    # Line 1: ── name ───────── N states · M transitions ──
    stats_parts: list[str] = []
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

    # --- States & Transitions (verbose only) ---
    if verbose:
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

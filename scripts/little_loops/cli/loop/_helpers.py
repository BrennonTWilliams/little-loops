"""Shared helpers for ll-loop CLI subcommands."""

from __future__ import annotations

import argparse
import json
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any

from little_loops.cli.loop.diagram_modes import (
    TOPOLOGY_TO_DETAIL,
    DiagramFacets,
    resolve_facets,
)
from little_loops.cli.output import colorize, strip_ansi, terminal_size, terminal_width
from little_loops.fsm.concurrency import LockManager, _process_alive
from little_loops.logger import Logger

if TYPE_CHECKING:
    from little_loops.fsm.schema import FSMLoop

# Exit code mapping for terminated_by values
EXIT_CODES: dict[str, int] = {
    "terminal": 0,
    "signal": 0,
    "handoff": 0,
    "max_iterations": 1,
    "timeout": 1,
    "cycle_detected": 1,
    "stall_detected": 1,
}

# Minimum number of action-output rows reserved beneath the pinned pane in
# alt-screen mode. When the pinned pane plus this margin would exceed the
# terminal height, the layout falls back to a more compact diagram variant.
MIN_ACTION_ROWS = 6

# Module-level shutdown state for signal handling
_loop_shutdown_requested: bool = False
_loop_executor: Any = None
_loop_pid_file: Path | None = None
_using_alt_screen: bool = False
# Set by SIGWINCH handler when the terminal is resized; consumed by the
# display_progress callback to trigger a pinned-pane redraw on the next event.
_needs_redraw: bool = False
# Previous SIGWINCH handler, stashed when we install our own so it can be
# restored in run_foreground's finally block. ``None`` means "not installed".
_original_sigwinch: Any = None


class _TeeWriter:
    """Wraps a stream, writing to both the original and a log file (ANSI stripped on log)."""

    def __init__(self, stream: Any, log_fh: Any) -> None:
        self._stream = stream
        self._log_fh = log_fh

    def write(self, data: str) -> int:
        n = self._stream.write(data)
        self._log_fh.write(strip_ansi(data))
        return n

    def flush(self) -> None:
        self._stream.flush()
        self._log_fh.flush()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._stream, name)


def _loop_signal_handler(signum: int, frame: FrameType | None) -> None:
    """Handle shutdown signals gracefully for ll-loop.

    First signal: Set shutdown flag for graceful exit after current state.
    Second signal: Force immediate exit.
    """
    global _loop_shutdown_requested, _using_alt_screen
    if _loop_shutdown_requested:
        # Second signal - force exit
        if _loop_pid_file is not None:
            _loop_pid_file.unlink(missing_ok=True)
        if _using_alt_screen:
            # Reset the DECSTBM scroll region BEFORE exiting the alt screen,
            # otherwise the main buffer is left with a restricted scroll
            # region — visible to the user as `seq 1 50` failing to scroll
            # past the previous pinned-pane height.
            print("\033[r", end="", file=sys.stderr, flush=True)
            print("\033[?1049l", end="", file=sys.stderr, flush=True)
        print(colorize("\nForce shutdown requested", "38;5;208"), file=sys.stderr)
        sys.exit(1)
    _loop_shutdown_requested = True
    print(colorize("\nShutdown requested, will exit after current state...", "33"), file=sys.stderr)
    if _loop_executor is not None:
        _loop_executor.request_shutdown()
        # Kill any child subprocess currently blocking in the action runner
        inner = getattr(_loop_executor, "_executor", None)
        if inner is not None:
            runner = getattr(inner, "action_runner", None)
            if runner is not None:
                proc = getattr(runner, "_current_process", None)
                if proc is not None:
                    proc.kill()
            # Also kill MCP subprocesses tracked directly on FSMExecutor (_run_subprocess path)
            fsm_proc = getattr(inner, "_current_process", None)
            if fsm_proc is not None:
                fsm_proc.kill()


def _is_earliest_waiter(entry_id: str, queue_dir: Path) -> bool:
    """Return True if entry_id is the earliest-enqueued waiter in queue_dir.

    Returns True when this waiter is first or the queue is empty/unreadable,
    allowing it to proceed with acquire(). Non-first waiters return False and
    should back off to yield to the earlier waiter (ENH-1332).

    Stale entries (dead PIDs) are removed on the fly so orphaned queue files
    from crashed processes do not block live waiters indefinitely (BUG-1360).
    """
    if not queue_dir.exists():
        return True
    entries: list[dict] = []
    for f in queue_dir.glob("*.json"):
        try:
            with open(f) as fh:
                data = json.load(fh)
            pid = data.get("context", {}).get("pid")
            if pid is not None and not _process_alive(pid):
                f.unlink(missing_ok=True)
                continue
            entries.append(data)
        except (json.JSONDecodeError, KeyError, FileNotFoundError, OSError):
            continue
    if not entries:
        return True
    entries.sort(key=lambda d: d.get("enqueuedAt", ""))
    return entries[0].get("id") == entry_id


def register_loop_signal_handlers(executor: Any, pid_file: Path | None = None) -> None:
    """Register SIGINT/SIGTERM handlers for graceful loop shutdown.

    Sets up signal handling so that Ctrl-C triggers a graceful shutdown
    (calls executor.request_shutdown()) rather than raising KeyboardInterrupt.
    A second Ctrl-C forces immediate exit with PID file cleanup.

    Args:
        executor: The PersistentExecutor instance to request shutdown on.
        pid_file: Optional path to PID file to clean up on forced exit.
    """
    global _loop_shutdown_requested, _loop_executor, _loop_pid_file
    _loop_shutdown_requested = False
    _loop_executor = executor
    _loop_pid_file = pid_file
    signal.signal(signal.SIGINT, _loop_signal_handler)
    signal.signal(signal.SIGTERM, _loop_signal_handler)


# ---------------------------------------------------------------------------
# SIGWINCH handler (alt-screen pinned-pane mode only)
# ---------------------------------------------------------------------------


def _sigwinch_handler(signum: int, frame: FrameType | None) -> None:
    """Mark the pinned pane as needing a redraw after a terminal resize.

    The handler does the minimum amount of work safe to perform in a signal
    context: it just sets a flag. ``display_progress`` consumes the flag
    before processing the next FSM event and triggers the actual redraw.
    """
    global _needs_redraw
    _needs_redraw = True


def _install_sigwinch_handler() -> None:
    """Install ``_sigwinch_handler`` for SIGWINCH, stashing the prior handler.

    Idempotent — re-calling while installed is a no-op so we never leak the
    chain by overwriting our own stash. No-op on platforms without SIGWINCH
    (e.g. Windows).
    """
    global _original_sigwinch
    if not hasattr(signal, "SIGWINCH"):
        return
    if _original_sigwinch is not None:
        return
    _original_sigwinch = signal.signal(signal.SIGWINCH, _sigwinch_handler)


def _restore_sigwinch_handler() -> None:
    """Restore the SIGWINCH handler stashed by ``_install_sigwinch_handler``.

    Safe to call when no handler was installed. After this returns,
    ``_original_sigwinch`` is reset to ``None`` so the install is repeatable.
    """
    global _original_sigwinch, _needs_redraw
    if not hasattr(signal, "SIGWINCH"):
        _original_sigwinch = None
        _needs_redraw = False
        return
    if _original_sigwinch is None:
        return
    signal.signal(signal.SIGWINCH, _original_sigwinch)
    _original_sigwinch = None
    _needs_redraw = False


# ---------------------------------------------------------------------------
# Pinned-pane layout (alt-screen mode)
# ---------------------------------------------------------------------------


def _count_display_lines(text: str) -> int:
    """Return the number of terminal rows a string occupies.

    Treats each ``\\n`` as a row boundary; a trailing newline is *not*
    counted as an extra empty row. ANSI escape sequences are assumed not to
    contain newlines (true for SGR / cursor / scroll-region codes).
    """
    if not text:
        return 0
    return text.count("\n") + (0 if text.endswith("\n") else 1)


def _choose_pinned_layout(
    rows: int,
    variants: list[str],
    min_action_rows: int = MIN_ACTION_ROWS,
) -> tuple[str, int]:
    """Pick the most detailed pinned-pane variant that leaves room for action output.

    ``variants`` is an ordered list from most-detailed to least-detailed
    (e.g. ``[full, neighborhood, single_line]``). Returns
    ``(pinned_str, line_count)`` for the first variant whose height plus
    ``min_action_rows`` fits within ``rows``. If none fit, returns the
    last (smallest) variant unchanged — a degenerate terminal still gets
    *something* pinned.
    """
    last_text = ""
    last_h = 0
    for variant in variants:
        last_text = variant
        last_h = _count_display_lines(variant)
        if last_h + min_action_rows <= rows:
            return variant, last_h
    return last_text, last_h


def _render_single_line_status(fsm: FSMLoop, active_state: str | None) -> str:
    """Render the single-line fallback: ``fsm: <preds> → [<active>] → <succs>``."""
    from little_loops.cli.loop.layout import _collect_edges

    if active_state is None or active_state not in fsm.states:
        return f"fsm: · → [{active_state or '?'}] → ·"
    edges = _collect_edges(fsm)
    preds = sorted({s for (s, t, _lbl) in edges if t == active_state and s != active_state})
    succs = sorted({t for (s, t, _lbl) in edges if s == active_state and t != active_state})
    preds_s = ",".join(preds) if preds else "·"
    succs_s = ",".join(succs) if succs else "·"
    return f"fsm: {preds_s} → [{active_state}] → {succs_s}"


def _build_pinned_pane(
    detail: str,
    fsm: FSMLoop,
    parent_highlight: str | None,
    child_fsm_stack: dict[int, FSMLoop | None],
    last_state_at_depth: dict[int, str],
    iteration_line: str,
    cols: int,
    *,
    facets: DiagramFacets,
    highlight_color: str,
    edge_label_colors: dict[str, str] | None,
    badges: dict[str, str] | None,
    prev_highlight: str | None = None,
    prev_state_at_depth: dict[int, str] | None = None,
    loop_path: Path | None = None,
) -> str:
    """Compose the pinned pane (header + diagram(s) + state line + separator).

    ``detail`` selects the diagram variant: ``"full"`` (layered
    ``_render_fsm_diagram``), ``"neighborhood"`` (1-hop pred/active/succ), or
    ``"single"`` (one-line ``fsm:`` status). The returned string is intended
    to be printed with ``flush=True`` and is terminated by a horizontal
    separator (no trailing newline).
    """
    from little_loops.cli.loop.layout import (
        _collect_edges,
        _filter_main_path_graph,
        _render_fsm_diagram,
        _render_neighborhood_diagram,
    )

    verbose = facets.scope == "full" and facets.state_detail == "full"

    def _render_one(target: FSMLoop, highlight: str | None, prev: str | None) -> str:
        if detail == "single":
            return _render_single_line_status(target, highlight)
        if detail == "neighborhood":
            return _render_neighborhood_diagram(
                target,
                highlight or target.initial,
                edge_label_colors=edge_label_colors,
                badges=badges,
                highlight_color=highlight_color,
                mode=facets.scope,
                prev_state=prev,
            )
        # "full" (layered)
        scope = facets.scope
        if scope == "main" and highlight is not None:
            _filtered_edges, reachable = _filter_main_path_graph(target, _collect_edges(target))
            if highlight not in reachable:
                scope = "full"
        return _render_fsm_diagram(
            target,
            verbose=verbose,
            highlight_state=highlight,
            highlight_color=highlight_color,
            edge_label_colors=edge_label_colors,
            badges=badges,
            mode=scope,
            suppress_labels=not facets.edge_labels,
            title_only=facets.state_detail == "title",
        )

    prev_map = prev_state_at_depth or {}
    lines: list[str] = []

    # Find deepest active loop — show only that one instead of stacking all levels.
    active_fsm = fsm
    active_state = parent_highlight
    active_prev = prev_highlight
    active_depth = 0
    for d in sorted(child_fsm_stack.keys()):
        child = child_fsm_stack[d]
        if child is not None and (d + 1) in last_state_at_depth:
            active_fsm = child
            active_state = last_state_at_depth.get(d + 1)
            active_prev = prev_map.get(d + 1)
            active_depth = d + 1

    # Header: breadcrumb shows immediate parent when inside a sub-loop.
    if active_depth > 0:
        imm_parent_name = (
            fsm.name if active_depth == 1 else (child_fsm_stack.get(active_depth - 2) or fsm).name
        )
        imm_parent_state = last_state_at_depth.get(active_depth - 1, "")
        header_text = f"== loop: {active_fsm.name} ({imm_parent_name} › {imm_parent_state}) "
    else:
        header_text = f"== loop: {fsm.name} "
    lines.append(header_text + "=" * max(0, cols - len(header_text)))
    for key, value in _artifact_lines(fsm, loop_path):
        lines.append(f"  {key}: {colorize(value, '2')}")
    diagram = _render_one(active_fsm, active_state, active_prev)
    if diagram:
        lines.extend(diagram.split("\n"))

    lines.append(iteration_line)
    lines.append("─" * cols)
    return "\n".join(lines)


def _render_pinned_pane(
    fsm: FSMLoop,
    parent_highlight: str | None,
    child_fsm_stack: dict[int, FSMLoop | None],
    last_state_at_depth: dict[int, str],
    iteration_line: str,
    *,
    facets: DiagramFacets,
    highlight_color: str,
    edge_label_colors: dict[str, str] | None,
    badges: dict[str, str] | None,
    min_action_rows: int = MIN_ACTION_ROWS,
    prev_state_at_depth: dict[int, str] | None = None,
    loop_path: Path | None = None,
) -> int:
    """Render the pinned pane to stdout and set the scroll region beneath it.

    Performs (in order): reset scroll region, clear+home cursor, build all
    pinned-pane variants, pick the largest that fits, print it, set the
    DECSTBM scroll region to start one row below the pinned pane, and
    position the cursor at the top of that scroll region. Returns the
    pinned-pane height in rows so the caller can track it across events.
    """
    cols, rows = terminal_size()
    # 1. Reset any existing scroll region so the clear covers the full screen.
    print("\033[r", end="", flush=True)
    # 2. Clear + cursor home.
    print("\033[2J\033[H", end="", flush=True)

    prev_map = prev_state_at_depth or {}

    def _build(detail: str) -> str:
        return _build_pinned_pane(
            detail,
            fsm,
            parent_highlight,
            child_fsm_stack,
            last_state_at_depth,
            iteration_line,
            cols,
            facets=facets,
            highlight_color=highlight_color,
            edge_label_colors=edge_label_colors,
            badges=badges,
            prev_highlight=prev_map.get(0),
            prev_state_at_depth=prev_map,
            loop_path=loop_path,
        )

    # Build the fallback ladder based on facets source and topology.
    # Explicit topology (source="topology"): render exactly once, no degradation.
    # Preset/default with layered topology: skip neighborhood — layered→neighborhood
    # looks like a broken diagram and confuses users. Go straight to single-line.
    # Explicit neighborhood topology: neighborhood→single.
    topo_detail = TOPOLOGY_TO_DETAIL[facets.topology]
    if facets.source == "topology":
        variants = [_build(topo_detail)]
    elif topo_detail == "full":
        variants = [_build("full"), _build("single")]
    elif topo_detail == "neighborhood":
        variants = [_build("neighborhood"), _build("single")]
    else:  # inline / single
        variants = [_build("single")]

    pinned, pinned_height = _choose_pinned_layout(
        rows,
        variants,
        min_action_rows=min_action_rows,
    )
    print(pinned, flush=True)

    # Guard against degenerate terminals: scroll region must have at least
    # 1 row beneath the pinned pane. If pinned_height >= rows, skip the
    # scroll-region setup entirely — output will append normally and the
    # caller can rely on the alt-screen exit to clean up.
    if pinned_height < rows:
        # DECSTBM uses 1-indexed inclusive rows.
        print(f"\033[{pinned_height + 1};{rows}r", end="", flush=True)
        # Move cursor to the top of the scroll region.
        print(f"\033[{pinned_height + 1};1H", end="", flush=True)
    return pinned_height


class StateFeedRenderer:
    """Renders loop-state events as terminal output for foreground runs and monitor attach.

    Extracted from ``run_foreground()`` so both the foreground run path and the
    ``cmd_monitor`` attach path (FEAT-1764) can share the same rendering logic.
    """

    def __init__(
        self,
        fsm: FSMLoop,
        args: argparse.Namespace,
        highlight_color: str = "32",
        edge_label_colors: dict[str, str] | None = None,
        badges: dict[str, str] | None = None,
        loops_dir: Path | None = None,
        loop_path: Path | None = None,
    ) -> None:
        self.fsm = fsm
        self.args = args
        self.highlight_color = highlight_color
        self.edge_label_colors = edge_label_colors
        self.badges = badges
        self.loops_dir = loops_dir or Path(".")
        self.loop_path = loop_path

        # Derived from args
        self.quiet: bool = getattr(args, "quiet", False)
        self.verbose: bool = getattr(args, "verbose", False)
        self.facets: DiagramFacets | None = resolve_facets(args)
        self.show_diagrams: bool = self.facets is not None
        self.clear_screen: bool = getattr(args, "clear", False)
        self.in_pinned_mode: bool = self.show_diagrams and self.clear_screen and sys.stdout.isatty()

        # Mutable state (was closure-captured in run_foreground)
        self.current_iteration: list[int] = [0]
        self.last_state_at_depth: dict[int, str] = {}
        self.prev_state_at_depth: dict[int, str] = {}
        self.child_fsm_stack: dict[int, FSMLoop | None] = {}
        self.pinned_height: list[int] = [0]
        self.loop_start_time: float = time.monotonic()

    def _elapsed_str(self) -> str:
        elapsed_int = int(time.monotonic() - self.loop_start_time)
        if elapsed_int < 60:
            return f"{elapsed_int}s"
        return f"{elapsed_int // 60}m {elapsed_int % 60}s"

    def _redraw_pinned(self, state0: str) -> None:
        """Redraw the pinned pane in place using the current depth-0 state."""
        assert self.facets is not None
        iter_line = (
            f"[{self.current_iteration[0]}/{self.fsm.max_iterations}] "
            f"{colorize(state0, '1')} ({colorize(self._elapsed_str(), '2')})"
        )
        self.pinned_height[0] = _render_pinned_pane(
            self.fsm,
            state0,
            self.child_fsm_stack,
            self.last_state_at_depth,
            iter_line,
            facets=self.facets,
            highlight_color=self.highlight_color,
            edge_label_colors=self.edge_label_colors,
            badges=self.badges,
            prev_state_at_depth=self.prev_state_at_depth,
            loop_path=self.loop_path,
        )

    def handle_event(self, event: dict) -> None:
        """Display progress for events."""
        global _needs_redraw
        # SIGWINCH redraw: terminal was resized; re-render the pinned pane
        # before processing the next event so the layout matches the new size.
        if _needs_redraw and self.in_pinned_mode and 0 in self.last_state_at_depth:
            self._redraw_pinned(self.last_state_at_depth[0])
            _needs_redraw = False

        event_type = event.get("event")
        depth = event.get("depth", 0)
        indent = "  " * depth
        tw = terminal_width()
        max_line = tw - 8 - len(indent)

        if event_type == "state_enter":
            self.current_iteration[0] = event.get("iteration", 0)
            state = event.get("state", "")
            elapsed_str = self._elapsed_str() if not self.quiet else ""
            # Non-pinned --clear path keeps the bare full-screen clear.
            if self.clear_screen and sys.stdout.isatty() and depth == 0 and not self.in_pinned_mode:
                print("\033[2J\033[H", end="", flush=True)
            # Update last-known state at this depth and clear stale deeper entries.
            old_state = self.last_state_at_depth.get(depth)
            if old_state is not None and old_state != state:
                self.prev_state_at_depth[depth] = old_state
            self.last_state_at_depth[depth] = state
            for k in [k for k in self.last_state_at_depth if k > depth]:
                del self.last_state_at_depth[k]
                self.prev_state_at_depth.pop(k, None)
            # Load child FSM for the current state at this depth
            parent_at_depth = self.fsm if depth == 0 else self.child_fsm_stack.get(depth - 1)
            if parent_at_depth is not None and state in parent_at_depth.states:
                fsm_state = parent_at_depth.states[state]
                if fsm_state.loop is not None:
                    try:
                        self.child_fsm_stack[depth] = load_loop(
                            fsm_state.loop, self.loops_dir, Logger()
                        )
                    except (FileNotFoundError, ValueError):
                        pass
                else:
                    self.child_fsm_stack[depth] = None
            else:
                self.child_fsm_stack[depth] = None
            # Clear stale deeper child FSM entries
            for k in [k for k in self.child_fsm_stack if k > depth]:
                del self.child_fsm_stack[k]

            if self.in_pinned_mode:
                state0 = self.last_state_at_depth.get(0)
                if state0 is None:
                    state0 = state
                self._redraw_pinned(state0)
            elif self.show_diagrams:
                from little_loops.cli.loop.layout import (
                    _collect_edges,
                    _filter_main_path_graph,
                    _render_fsm_diagram,
                )

                assert self.facets is not None

                # Find deepest active loop — show only that one.
                active_fsm_diag = self.fsm
                active_highlight = self.last_state_at_depth.get(0)
                active_depth_diag = 0
                for d in sorted(self.child_fsm_stack.keys()):
                    child_at_d = self.child_fsm_stack[d]
                    if child_at_d is not None and (d + 1) in self.last_state_at_depth:
                        active_fsm_diag = child_at_d
                        active_highlight = self.last_state_at_depth.get(d + 1)
                        active_depth_diag = d + 1

                # Fall back to full scope when the highlighted state is hidden in main scope.
                active_scope = self.facets.scope
                fallback_note: str | None = None
                if active_scope == "main" and active_highlight is not None:
                    _filtered_edges, active_reachable = _filter_main_path_graph(
                        active_fsm_diag, _collect_edges(active_fsm_diag)
                    )
                    if active_highlight not in active_reachable:
                        active_scope = "full"
                        fallback_note = (
                            f"(showing full diagram: active state "
                            f"{active_highlight!r} is off the main path)"
                        )
                diagram = _render_fsm_diagram(
                    active_fsm_diag,
                    highlight_state=active_highlight,
                    highlight_color=self.highlight_color,
                    edge_label_colors=self.edge_label_colors,
                    badges=self.badges,
                    mode=active_scope,
                    suppress_labels=not self.facets.edge_labels,
                    title_only=self.facets.state_detail == "title",
                )
                # Header: breadcrumb shows immediate parent when inside a sub-loop.
                if active_depth_diag > 0:
                    imm_parent_name = (
                        self.fsm.name
                        if active_depth_diag == 1
                        else (self.child_fsm_stack.get(active_depth_diag - 2) or self.fsm).name
                    )
                    imm_parent_state = self.last_state_at_depth.get(active_depth_diag - 1, "")
                    header_text = (
                        f"== loop: {active_fsm_diag.name} ({imm_parent_name} › {imm_parent_state}) "
                    )
                else:
                    header_text = f"== loop: {self.fsm.name} "
                header = header_text + "=" * max(0, tw - len(header_text))
                print(header, flush=True)
                if fallback_note is not None:
                    print(fallback_note, flush=True)
                for key, value in _artifact_lines(self.fsm, self.loop_path):
                    print(f"  {key}: {colorize(value, '2')}", flush=True)
                print(diagram, flush=True)
            # In pinned mode the iteration line is part of the pinned pane;
            # only print it inline for non-pinned paths.
            if not self.quiet and not self.in_pinned_mode:
                print(
                    f"{indent}[{self.current_iteration[0]}/{self.fsm.max_iterations}] {colorize(state, '1')} ({colorize(elapsed_str, '2')})",
                    end="",
                    flush=True,
                )

        elif event_type == "action_start":
            if not self.quiet:
                action = event.get("action", "")
                is_prompt = event.get("is_prompt", False)
                if is_prompt:
                    lines = action.strip().splitlines()
                    line_count = len(lines)
                    prompt_badge = "✦"  # ✦
                    if self.verbose:
                        print(
                            f"{indent} -> {colorize(prompt_badge, '2')} {colorize(f'({line_count} lines)', '2')}",
                            flush=True,
                        )
                        for line in lines:
                            print(f"{indent}       {line}", flush=True)
                    else:
                        first_line = lines[0] if lines else ""
                        preview = first_line[:60] + "..." if len(first_line) > 60 else first_line
                        print(
                            f"{indent} -> {colorize(prompt_badge, '2')} {colorize(preview, '2')}",
                            flush=True,
                        )
                else:
                    if self.verbose:
                        action_display = action
                    else:
                        action_display = (
                            action[:max_line] + "..." if len(action) > max_line else action
                        )
                    print(f"{indent} -> {colorize(action_display, '2')}", flush=True)

        elif event_type == "action_output":
            if not self.quiet:
                line = event.get("line", "")
                if line.strip():
                    print(f"{indent}       {line}", flush=True)

        elif event_type == "action_complete":
            if not self.quiet:
                duration_ms = event.get("duration_ms", 0)
                exit_code = event.get("exit_code", 0)
                duration_sec = duration_ms / 1000
                if duration_sec < 60:
                    duration_str = f"{duration_sec:.1f}s"
                else:
                    minutes = int(duration_sec // 60)
                    seconds = duration_sec % 60
                    duration_str = f"{minutes}m {seconds:.0f}s"
                parts = [f"{indent}       ({colorize(duration_str, '2')})"]
                if exit_code == 124:
                    parts.append(colorize("timed out", "38;5;208"))
                elif exit_code != 0:
                    parts.append(colorize(f"exit: {exit_code}", "38;5;208"))
                print("  ".join(parts), flush=True)

        elif event_type == "evaluate":
            if not self.quiet:
                verdict = event.get("verdict", "")
                confidence = event.get("confidence")
                reason = event.get("reason", "")
                error = event.get("error", "")
                _elc = self.edge_label_colors or {}
                if verdict in ("yes", "target", "progress"):
                    _vc = _elc.get("yes", "32")
                    symbol = colorize("✓", _vc)
                    verdict_colored = colorize(verdict, _vc)
                elif verdict == "no":
                    _vc = _elc.get("no", "38;5;208")
                    symbol = colorize("✗", _vc)
                    verdict_colored = colorize(verdict, _vc)
                elif verdict == "error":
                    _vc = _elc.get("error", "38;5;208")
                    symbol = colorize("✗", _vc)
                    verdict_colored = colorize(verdict, _vc)
                else:
                    symbol = colorize("✗", "38;5;208")
                    verdict_colored = colorize(verdict, "2")
                # Build verdict line
                if error and verdict == "error":
                    verdict_line = f"{symbol} {verdict_colored}: {error}"
                elif confidence is not None:
                    verdict_line = (
                        f"{symbol} {verdict_colored} {colorize(f'({confidence:.2f})', '2')}"
                    )
                else:
                    verdict_line = f"{symbol} {verdict_colored}"
                print(f"{indent}       {verdict_line}", flush=True)
                # Show raw_preview for error verdicts to aid diagnosis
                raw_preview = event.get("raw_preview", "")
                if raw_preview and verdict == "error":
                    if self.verbose:
                        sub_lines = raw_preview.splitlines() or [""]
                        first, rest = sub_lines[0], sub_lines[1:]
                        print(f"{indent}         raw: {first}", flush=True)
                        for sub in rest:
                            print(f"{indent}              {sub}", flush=True)
                    else:
                        print(f"{indent}         raw: {raw_preview[:200]}", flush=True)
                # Show reason on a second line if present (and not already shown as error)
                if reason and not (error and verdict == "error"):
                    if self.verbose:
                        for sub in reason.splitlines() or [""]:
                            print(f"{indent}         {sub}", flush=True)
                    else:
                        reason_display = reason[:300] + "..." if len(reason) > 300 else reason
                        print(f"{indent}         {reason_display}", flush=True)

        elif event_type == "route":
            if not self.quiet:
                to_state = event.get("to", "")
                print(
                    f"{indent}       {colorize('->', '2')} {colorize(to_state, '1')}",
                    flush=True,
                )

        elif event_type == "max_iterations_summary":
            if not self.quiet:
                summary_state = event.get("summary_state", "")
                iters = event.get("iterations", 0)
                msg = f"iteration cap reached ({iters}); running summary state '{summary_state}'"
                print(f"{indent}       {colorize(msg, '38;5;208')}", flush=True)

        elif event_type == "stall_detected":
            if not self.quiet:
                state = event.get("state", "")
                exit_code = event.get("exit_code", 0)
                verdict = event.get("verdict", "")
                consecutive = event.get("consecutive", 0)
                action = event.get("action", "abort")
                triple = f"(exit_code={exit_code}, verdict='{verdict}')"
                msg = (
                    f"stall_detected: state '{state}' produced {triple} "
                    f"for {consecutive} consecutive iterations -> {action}"
                )
                print(f"{indent}       {colorize(msg, '38;5;208')}", flush=True)


def get_builtin_loops_dir() -> Path:
    """Get the path to built-in loops bundled with the plugin."""
    return Path(__file__).parent.parent.parent / "loops"


def _artifact_lines(fsm: FSMLoop, loop_path: Path | None) -> list[tuple[str, str]]:
    """Extract path-like context values from *fsm* for display in artifact headers.

    Returns a list of ``(key, value)`` pairs where *value* is a non-empty string
    that starts with ``.``, ``/``, or ``~``, or contains ``/``, and does not
    contain ``${`` (unresolved template expression). When *loop_path* is not
    ``None``, the first entry is always ``("loop", str(loop_path))``.
    """
    pairs: list[tuple[str, str]] = []
    if loop_path is not None:
        pairs.append(("loop", str(loop_path)))
    context: dict[str, Any] = getattr(fsm, "context", None) or {}
    for key, value in context.items():
        if not isinstance(value, str) or not value:
            continue
        if "${" in value:
            continue
        if value.startswith(".") or value.startswith("/") or value.startswith("~") or "/" in value:
            pairs.append((key, value))
    return pairs


def resolve_loop_path(name_or_path: str, loops_dir: Path) -> Path:
    """Resolve loop name to file path."""
    path = Path(name_or_path)
    if path.exists():
        return path

    # Try <loops_dir>/<name>.fsm.yaml first (compiled FSM)
    fsm_path = loops_dir / f"{name_or_path}.fsm.yaml"
    if fsm_path.exists():
        return fsm_path

    # Fall back to <loops_dir>/<name>.yaml
    loops_path = loops_dir / f"{name_or_path}.yaml"
    if loops_path.exists():
        return loops_path

    # Fall back to built-in loops from plugin directory
    builtin_path = get_builtin_loops_dir() / f"{name_or_path}.yaml"
    if builtin_path.exists():
        return builtin_path

    raise FileNotFoundError(f"Loop not found: {name_or_path}")


def load_loop(name_or_path: str, loops_dir: Path, logger: Logger) -> FSMLoop:
    """Load and validate a loop.

    Raises:
        FileNotFoundError: If loop not found.
        ValueError: If loop is invalid.
    """
    from little_loops.fsm.validation import load_and_validate

    path = resolve_loop_path(name_or_path, loops_dir)
    fsm, _ = load_and_validate(path)
    return fsm


def load_loop_with_spec(
    name_or_path: str, loops_dir: Path, logger: Logger
) -> tuple[FSMLoop, dict[str, Any]]:
    """Load a loop and return both the FSMLoop and raw spec dict.

    Used by commands that need access to raw YAML fields (e.g., description).

    Raises:
        FileNotFoundError: If loop not found.
        ValueError: If loop is invalid.
    """
    import yaml

    from little_loops.fsm.validation import load_and_validate

    path = resolve_loop_path(name_or_path, loops_dir)

    with open(path) as f:
        spec = yaml.safe_load(f)

    fsm, _ = load_and_validate(path)
    return fsm, spec


def print_execution_plan(fsm: FSMLoop, edge_label_colors: dict[str, str] | None = None) -> None:
    """Print dry-run execution plan."""
    _elc = edge_label_colors or {}
    _yes_color = _elc.get("yes", "32")
    tw = terminal_width()
    print(colorize(f"Execution plan for: {fsm.name}", "1"))
    print()
    print("States:")
    for name, state in fsm.states.items():
        terminal_marker = colorize(" [TERMINAL]", _yes_color) if state.terminal else ""
        print(f"  {colorize(f'[{name}]', '1')}{terminal_marker}")
        if state.action:
            if state.action_type == "prompt":
                lines = state.action.strip().splitlines()
                preview = "\n      ".join(lines[:3])
                if len(lines) > 3 or len(state.action) > 200:
                    preview += " ..."
                print(f"    action: |\n      {preview}")
            else:
                max_action = tw - 16
                action_display = (
                    state.action[:max_action] + "..."
                    if len(state.action) > max_action
                    else state.action
                )
                print(f"    action: {action_display}")
        if state.evaluate:
            print(f"    evaluate: {state.evaluate.type}")
        if state.on_yes:
            print(f"    on_yes {colorize('->', '2')} {colorize(state.on_yes, '2')}")
        if state.on_no:
            print(f"    on_no {colorize('->', '2')} {colorize(state.on_no, '2')}")
        if state.on_error:
            print(f"    on_error {colorize('->', '2')} {colorize(state.on_error, '2')}")
        if state.next:
            print(f"    next {colorize('->', '2')} {colorize(state.next, '2')}")
        if state.route:
            print("    route:")
            for verdict, target in state.route.routes.items():
                print(f"      {verdict} {colorize('->', '2')} {colorize(target, '2')}")
            if state.route.default:
                print(f"      _ {colorize('->', '2')} {colorize(state.route.default, '2')}")
    print()
    print(f"Initial state: {fsm.initial}")
    print(f"Max iterations: {fsm.max_iterations}")
    if fsm.timeout:
        print(f"Timeout: {fsm.timeout}s")
    if fsm.context:
        print("Context:")
        for key, value in fsm.context.items():
            print(f"  {key}: {value!r}")


def _make_instance_id(loop_name: str) -> str:
    """Generate a unique instance ID for a loop run."""
    return f"{loop_name}-{datetime.now().strftime('%Y%m%dT%H%M%S')}"


def run_background(
    loop_name: str, args: argparse.Namespace, loops_dir: Path, subcommand: str = "run"
) -> int:
    """Launch loop as a detached background process.

    Spawns a new process with start_new_session=True that re-executes
    the loop with --foreground-internal. The parent writes the PID file
    and returns immediately.

    Args:
        subcommand: The ll-loop subcommand to spawn ("run" or "resume").

    Returns:
        Exit code (0 = launched successfully).
    """
    running_dir = loops_dir / ".running"
    running_dir.mkdir(parents=True, exist_ok=True)

    # Pre-flight scope conflict check — detect conflicts before spawning the child
    # so the user gets immediate feedback instead of a silent child failure.
    logger = Logger()
    try:
        fsm = load_loop(loop_name, loops_dir, logger)
    except (FileNotFoundError, ValueError) as e:
        print(f"Error loading loop '{loop_name}': {e}", file=sys.stderr)
        return 1

    lock_manager = LockManager(loops_dir)
    scope = fsm.scope or ["."]
    conflict = lock_manager.find_conflict(scope)
    if conflict and not getattr(args, "queue", False) and not getattr(args, "no_lock", False):
        print(f"Scope conflict with running loop: {conflict.loop_name}", file=sys.stderr)
        print(f"  Conflicting scope: {conflict.scope}", file=sys.stderr)
        print("  Use --queue to wait for it to finish", file=sys.stderr)
        return 1

    instance_id = _make_instance_id(loop_name)
    pid_file = running_dir / f"{instance_id}.pid"
    log_file = running_dir / f"{instance_id}.log"

    # Build re-exec command with --foreground-internal instead of --background
    cmd = [
        sys.executable,
        "-m",
        "little_loops.cli.loop",
        subcommand,
        loop_name,
    ]
    input_val = getattr(args, "input", None)
    if input_val is not None:
        cmd.append(input_val)
    cmd.append("--foreground-internal")
    cmd.extend(["--instance-id", instance_id])

    # Forward relevant args
    max_iter = getattr(args, "max_iterations", None)
    if max_iter:
        cmd.extend(["--max-iterations", str(max_iter)])
    if getattr(args, "no_llm", False):
        cmd.append("--no-llm")
    llm_model = getattr(args, "llm_model", None)
    if llm_model:
        cmd.extend(["--llm-model", llm_model])
    if getattr(args, "verbose", False):
        cmd.append("--verbose")
    show_diagrams_raw = getattr(args, "show_diagrams", None)
    if show_diagrams_raw is not None:
        if show_diagrams_raw is True:
            cmd.append("--show-diagrams")
        else:
            cmd.extend(["--show-diagrams", show_diagrams_raw])
    diagram_edge_labels = getattr(args, "diagram_edge_labels", None)
    if diagram_edge_labels is not None:
        cmd.extend(["--diagram-edge-labels", diagram_edge_labels])
    diagram_state_detail = getattr(args, "diagram_state_detail", None)
    if diagram_state_detail is not None:
        cmd.extend(["--diagram-state-detail", diagram_state_detail])
    diagram_scope = getattr(args, "diagram_scope", None)
    if diagram_scope is not None:
        cmd.extend(["--diagram-scope", diagram_scope])
    if getattr(args, "quiet", False):
        cmd.append("--quiet")
    if getattr(args, "queue", False):
        cmd.append("--queue")
    if getattr(args, "no_lock", False):
        cmd.append("--no-lock")
    for kv in getattr(args, "context", None) or []:
        cmd.extend(["--context", kv])
    program_md = getattr(args, "program_md", None)
    if program_md is not None:
        cmd.extend(["--program-md", str(program_md)])
    delay = getattr(args, "delay", None)
    if delay is not None:
        cmd.extend(["--delay", str(delay)])
    handoff_threshold = getattr(args, "handoff_threshold", None)
    if handoff_threshold is not None:
        cmd.extend(["--handoff-threshold", str(handoff_threshold)])
    context_limit = getattr(args, "context_limit", None)
    if context_limit is not None:
        cmd.extend(["--context-limit", str(context_limit)])

    log_file.parent.mkdir(parents=True, exist_ok=True)
    with open(log_file, "w") as log_fh:
        process = subprocess.Popen(
            cmd,
            start_new_session=True,
            stdout=log_fh,
            stderr=log_fh,
            stdin=subprocess.DEVNULL,
        )

    pid_file.write_text(str(process.pid))
    print(
        f"Loop {colorize(loop_name, '1')} started in background (PID: {colorize(str(process.pid), '2')})"
    )
    print(f"  Log: {colorize(str(log_file), '2')}")
    print(f"  Status: {colorize(f'll-loop status {loop_name}', '2')}")
    print(f"  Stop:   {colorize(f'll-loop stop {loop_name}', '2')}")
    return 0


def run_foreground(
    executor: Any,
    fsm: FSMLoop,
    args: argparse.Namespace,
    highlight_color: str = "32",
    edge_label_colors: dict[str, str] | None = None,
    badges: dict[str, str] | None = None,
    mode: str = "run",
    instance_id: str | None = None,
    running_dir: Path | None = None,
    loop_path: Path | None = None,
) -> int:
    """Run loop with progress display.

    Args:
        highlight_color: ANSI SGR code for the active FSM state highlight in verbose mode.
        edge_label_colors: Optional label→SGR-code mapping for transition edge labels.
        badges: Optional glyph-key→string mapping for state type badges in FSM diagrams.
        mode: ``"run"`` (default) calls ``executor.run()``; ``"resume"`` calls
            ``executor.resume()`` so a resumed loop reuses the same display-wiring
            path as a fresh run (BUG-1645). In ``"resume"`` mode a ``None`` result
            from ``executor.resume()`` is treated as "nothing to resume": a warning
            is logged and exit code 1 is returned before any alt-screen sequences
            are emitted.

        instance_id: When provided and not a background-spawned child
            (``foreground_internal=False``), stdout/stderr are teed to
            ``{running_dir}/{instance_id}.log`` with ANSI sequences stripped.
        running_dir: Directory for the log file. Defaults to ``.running``
            alongside the loops directory.
    Returns:
        Exit code (0 = success).
    """
    if mode not in ("run", "resume"):
        raise ValueError(f"run_foreground: invalid mode {mode!r}; expected 'run' or 'resume'")

    _orig_stdout = sys.stdout
    _orig_stderr = sys.stderr
    _log_fh: Any = None
    if instance_id is not None and not getattr(args, "foreground_internal", False):
        _log_path = (running_dir or Path(".running")) / f"{instance_id}.log"
        _log_path.parent.mkdir(parents=True, exist_ok=True)
        _log_fh = open(_log_path, "w")
        sys.stdout = _TeeWriter(_orig_stdout, _log_fh)  # type: ignore[assignment]
        sys.stderr = _TeeWriter(_orig_stderr, _log_fh)  # type: ignore[assignment]

    try:
        # Create the state feed renderer — encapsulates display state and event handling.
        renderer = StateFeedRenderer(
            fsm,
            args,
            highlight_color=highlight_color,
            edge_label_colors=edge_label_colors,
            badges=badges,
            loops_dir=getattr(executor, "loops_dir", Path(".")),
            loop_path=loop_path,
        )
        if not renderer.quiet:
            print(f"Running loop: {colorize(fsm.name, '1')}")
            print(f"Max iterations: {colorize(str(fsm.max_iterations), '2')}")
            for key, value in _artifact_lines(fsm, loop_path):
                print(f"  {key}: {colorize(value, '2')}")
            print()

        # Wire progress display via the EventBus on PersistentExecutor
        if not renderer.quiet or renderer.show_diagrams:
            if hasattr(executor, "event_bus"):
                executor.event_bus.register(renderer.handle_event)
            else:
                executor._on_event = renderer.handle_event

        # Wire follow mode — streams history-formatted events independently of quiet
        if getattr(args, "follow", False):
            from little_loops.cli.loop.info import _format_history_event

            tw = terminal_width()
            _verbose = renderer.verbose

            def _follow_callback(event: dict[str, Any]) -> None:
                line = _format_history_event(event, verbose=_verbose, width=tw)
                if line is not None:
                    print(line, flush=True)

            if hasattr(executor, "event_bus"):
                executor.event_bus.register(_follow_callback)
            else:
                _prev_on_event = executor._on_event

                def _chained(event: dict[str, Any]) -> None:
                    if _prev_on_event:
                        _prev_on_event(event)
                    _follow_callback(event)

                executor._on_event = _chained

        # Enter alternate screen buffer when showing diagrams with clear to prevent
        # scrollback contamination from diagrams taller than the terminal height.
        global _using_alt_screen
        if renderer.show_diagrams and renderer.clear_screen and sys.stdout.isatty():
            _using_alt_screen = True
            print("\033[?1049h\033[H", end="", flush=True)
            _install_sigwinch_handler()

        try:
            if mode == "resume":
                result = executor.resume()
                # "Nothing to resume" path: no run actually executed, so don't fall
                # through to completion-line formatting. Exit cleanly with code 1.
                if result is None:
                    Logger().warning(f"Nothing to resume for: {fsm.name}")
                    return 1
            else:
                result = executor.run()
        finally:
            if _using_alt_screen:
                # Reset DECSTBM scroll region BEFORE exiting alt-screen, otherwise
                # the main buffer is left with a restricted scroll region (one of
                # the Success Metrics for ENH-1642).
                print("\033[r", end="", flush=True)
                print("\033[?1049l", end="", flush=True)
                _using_alt_screen = False
            _restore_sigwinch_handler()

        if not renderer.quiet:
            print()
            duration_sec = result.duration_ms / 1000
            if duration_sec < 60:
                duration_str = f"{duration_sec:.1f}s"
            else:
                minutes = int(duration_sec // 60)
                seconds = duration_sec % 60
                duration_str = f"{minutes}m {seconds:.0f}s"
            if result.terminated_by == "terminal":
                state_colored = colorize(result.final_state, "32")
            else:
                state_colored = colorize(result.final_state, "38;5;208")
            completion_prefix = "Resumed and completed" if mode == "resume" else "Loop completed"
            rejection_count = 0
            for _t in getattr(getattr(executor, "event_bus", None), "_transports", []):
                if hasattr(_t, "get_stats"):
                    rejection_count += _t.get_stats().get("client_rejections", 0)
            suffix = f", {rejection_count} client rejections" if rejection_count > 0 else ""
            print(
                f"{completion_prefix}: {state_colored} ({result.iterations} iterations, {duration_str}{suffix})"
            )

        return EXIT_CODES.get(result.terminated_by, 1)
    finally:
        sys.stdout = _orig_stdout
        sys.stderr = _orig_stderr
        if _log_fh is not None:
            _log_fh.close()

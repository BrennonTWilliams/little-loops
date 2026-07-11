"""Shared helpers for ll-loop CLI subcommands."""

from __future__ import annotations

import argparse
import contextlib
import json
import os
import signal
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from types import FrameType
from typing import TYPE_CHECKING, Any

from little_loops.cli import output as _output
from little_loops.cli.loop.diagram_modes import (
    TOPOLOGY_TO_DETAIL,
    DiagramFacets,
    resolve_facets,
)
from little_loops.cli.output import colorize, strip_ansi, terminal_size, terminal_width
from little_loops.fsm.concurrency import LockManager, _process_alive, resolve_scope
from little_loops.logger import Logger

if TYPE_CHECKING:
    from little_loops.fsm.schema import FSMLoop


@contextlib.contextmanager
def with_diagram_color(enabled: bool):
    """Temporarily flip ``cli.output._USE_COLOR`` while rendering a diagram.

    The FSM diagram renderer calls :func:`colorize` internally for every
    border / badge / accent, which is gated by ``_USE_COLOR``. When
    ``--show-diagrams`` is explicit the user is opting into a structured
    visualization — colors should be emitted regardless of whether stdout is
    a TTY (``FORCE_COLOR`` already covers the TTY case). When
    ``enabled=True`` this context manager forces ``_USE_COLOR=True`` for the
    render and restores the previous value on exit. ``NO_COLOR=1`` is
    honored unconditionally — when set we leave ``_USE_COLOR`` alone.

    Use ``with with_diagram_color(show_diagrams): ...`` at the four render
    sites (dry-run path, ``cmd_show``, ``StateFeedRenderer`` streaming and
    pinned paths).
    """
    if not enabled:
        yield
        return
    if os.environ.get("NO_COLOR", "") != "":
        yield
        return

    prev = _output._USE_COLOR
    _output._USE_COLOR = True
    try:
        yield
    finally:
        _output._USE_COLOR = prev


# Exit code mapping for terminated_by values
EXIT_CODES: dict[str, int] = {
    "terminal": 0,
    "interrupted": 0,
    "handoff": 0,
    "max_steps": 1,
    "timeout": 1,
    "cycle_detected": 1,
    "stall_detected": 1,
    # ENH-2522: user_stopped (clean ll-loop stop) and system_signal (kernel/SIGKILL)
    # are non-zero so callers can distinguish them from graceful paths.
    "user_stopped": 1,
    "system_signal": 1,
}

# Minimum number of action-output rows reserved beneath the pinned pane in
# alt-screen mode. When the pinned pane plus this margin would exceed the
# terminal height, the layout falls back to a more compact diagram variant.
MIN_ACTION_ROWS = 6

# Module-level shutdown state for signal handling
_loop_shutdown_requested: bool = False
_loop_executor: Any = None
_loop_pid_file: Path | None = None
_loop_marker_path: Path | None = None  # ENH-2522: user-stop.marker sentinel location
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
    Second signal: Force immediate exit (after archiving the current run,
    ENH-2516).
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
        # ENH-2516: archive the current run before sys.exit so the audit trail
        # survives a forced exit (mirrors the first-SIGINT graceful path and
        # cmd_stop's precedent at lifecycle.py:316-375). OSError is swallowed
        # — a failed archive must not prevent exit, which is the only way to
        # break out of a stuck run (defensive coding matches lifecycle.py:116).
        if _loop_executor is not None:
            try:
                _loop_executor.archive_run_only(terminated_by="interrupted_force")
            except OSError:
                pass
        sys.exit(1)
    _loop_shutdown_requested = True
    print(colorize("\nShutdown requested, will exit after current state...", "33"), file=sys.stderr)
    if _loop_executor is not None:
        # ENH-2522: mark on the executor that our own signal handler killed the
        # subprocess, so the finish helper can attribute exit_code=-9 to the
        # user signal (interrupted) rather than a kernel/OOM kill (system_signal).
        inner = getattr(_loop_executor, "_executor", None)
        if inner is not None:
            inner._signal_handler_killed_subproc = True
        _loop_executor.request_shutdown(marker_path=_loop_marker_path)
        # Kill any child subprocess currently blocking in the action runner
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


def register_loop_signal_handlers(
    executor: Any,
    pid_file: Path | None = None,
    marker_path: Path | None = None,
) -> None:
    """Register SIGINT/SIGTERM handlers for graceful loop shutdown.

    Sets up signal handling so that Ctrl-C triggers a graceful shutdown
    (calls executor.request_shutdown()) rather than raising KeyboardInterrupt.
    A second Ctrl-C forces immediate exit with PID file cleanup.

    Args:
        executor: The PersistentExecutor instance to request shutdown on.
        pid_file: Optional path to PID file to clean up on forced exit.
        marker_path: Optional path to a user-stop.marker sentinel; if present
            when shutdown is requested, the executor will tag the run as
            ``user_stopped`` instead of ``interrupted`` (ENH-2522).
    """
    global _loop_shutdown_requested, _loop_executor, _loop_pid_file, _loop_marker_path
    _loop_shutdown_requested = False
    _loop_executor = executor
    _loop_pid_file = pid_file
    _loop_marker_path = marker_path
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
    *,
    cols: int | None = None,
) -> tuple[str, int]:
    """Pick the most detailed pinned-pane variant that leaves room for action output.

    ``variants`` is an ordered list from most-detailed to least-detailed
    (e.g. ``[full, neighborhood, single_line]``). Returns
    ``(pinned_str, line_count)`` for the first variant whose height plus
    ``min_action_rows`` fits within ``rows`` AND, when ``cols`` is provided,
    whose widest line fits within ``cols`` display columns.

    The width filter was added so the pinned/TTY path degrades wide diagrams
    the same way the streaming path already does (BUG-2425). Without it, a
    rung that passes the height check can still be wider than the terminal,
    producing a broken connector layout (e.g. ``--show-diagrams clean`` on a
    back-edge-heavy FSM). If ``cols`` is ``None`` the picker falls back to
    height-only behavior. If no variant fits both filters, returns the last
    (smallest) variant unchanged — a degenerate terminal still gets *something*
    pinned.
    """
    last_text = ""
    last_h = 0
    for variant in variants:
        last_text = variant
        last_h = _count_display_lines(variant)
        if cols is not None and _variant_width(variant) > cols:
            continue  # too wide; ladder has smaller rungs to try
        if last_h + min_action_rows <= rows:
            return variant, last_h
    return last_text, last_h


def _classify_fsm_topology(fsm: FSMLoop) -> str:
    """Classify an FSM's graph shape as ``'linear' | 'tree' | 'general'``.

    Mirrors the ``TopologyDetector`` plumbing in ``_render_fsm_diagram`` over the
    full-scope edge set so the fallback ladder can branch on the loop's intrinsic
    shape (FEAT-670). Full scope (not path-filtered) is used deliberately: the
    ladder is about how the whole graph degrades, not the active happy path.
    """
    from little_loops.cli.loop.layout import (
        TopologyDetector,
        _bfs_order,
        _classify_edges,
        _collect_edges,
        _trace_main_path,
    )

    edges = _collect_edges(fsm)
    bfs_order_list, _bfs_depth = _bfs_order(fsm.initial, edges)
    main_path, main_edge_set = _trace_main_path(fsm, edges)
    branches, back_edges = _classify_edges(edges, main_edge_set, bfs_order_list)
    return TopologyDetector(edges, main_path, branches, back_edges).classify()


def _variant_width(variant: str | None) -> int:
    """Return the widest display (ANSI-stripped) line in a rendered variant.

    Uses ``_display_width`` (wcwidth) rather than ``len`` so double-width glyphs
    (emoji badges, CJK, some arrows) are sized by the columns they occupy, not
    the code points they take (BUG-2425 Part 3). Local import avoids the
    layout↔_helpers module-load cycle.
    """
    if not variant:
        return 0
    from little_loops.cli.loop.layout import _display_width

    return max((_display_width(strip_ansi(ln)) for ln in variant.split("\n")), default=0)


def _build_fallback_ladder(
    facets: DiagramFacets,
    fsm: FSMLoop,
    full_variant: str | None,
    cols: int,
) -> list[str]:
    """Order the degraded pinned-pane rungs by classified topology + failing dimension.

    Returns an ordered list of ``detail`` strings (most→least detailed) for the
    auto-degradation path (``source != "topology"``, layered topology). The list
    always starts with ``"full"`` and terminates in ``"single"`` (the
    guaranteed-fit floor). Only the *ordering* of the intermediate rungs varies;
    ``_choose_pinned_layout`` still selects the first rung that fits by height.

    Topology (FEAT-670) selects *which* detail-shedding path is preferred, and a
    width probe of the built ``full`` variant orders the general-graph rungs:

    - linear / tree (narrow, tall): title-only rungs keep every state before we
      fall to the windowed crop (ENH-2410) or the synthetic neighborhood.
    - general + too wide (fan-out): narrower title-only boxes before the window.
    - general + too tall (hub-heavy): the windowed crop before title-only.

    Title-only rungs are omitted when the ``"full"`` render already applies them
    (``state_detail == "title"`` / ``edge_labels == False``), so a user-chosen
    detail level is never double-applied (Open Question 5).
    """
    # Detail-shedding rungs that keep every state. Skip a rung when the "full"
    # render already applies it, to avoid an identical duplicate variant.
    keep_all: list[str] = []
    if facets.state_detail != "title":
        keep_all.append("title_only")
    if facets.edge_labels:
        keep_all.append("title_only_nolabels")

    topology = _classify_fsm_topology(fsm)
    too_wide = _variant_width(full_variant) > cols

    if topology in ("linear", "tree") or too_wide:
        # Narrow-but-tall chains and wide fan-outs both benefit from shedding box
        # detail (shorter and/or narrower boxes) while keeping every state,
        # before cropping to a window or collapsing to the neighborhood view.
        ladder = ["full", *keep_all, "window", "neighborhood", "single"]
    else:
        # Hub-heavy general graph that is tall but not wide: the windowed crop
        # preserves local structure better than shedding detail graph-wide.
        ladder = ["full", "window", *keep_all, "neighborhood", "single"]

    deduped: list[str] = []
    for rung in ladder:
        if rung not in deduped:
            deduped.append(rung)
    return deduped


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
    model: str | None = None,
    show_input: bool = True,
    rows: int | None = None,
    min_action_rows: int = MIN_ACTION_ROWS,
) -> str | None:
    """Compose the pinned pane (header + diagram(s) + state line + separator).

    ``detail`` selects the diagram variant: ``"full"`` (layered
    ``_render_fsm_diagram``), ``"title_only"`` / ``"title_only_nolabels"`` (the
    layered render with per-state bodies — and, for ``_nolabels``, edge labels —
    suppressed so every state stays visible in shorter/narrower boxes; ENH-2411),
    ``"window"`` (the real layered render cropped to ±K layers around the active
    state — ENH-2410), ``"neighborhood"`` (1-hop pred/active/succ), or
    ``"single"`` (one-line ``fsm:`` status). The returned
    string is intended to be printed with ``flush=True`` and is terminated by a
    horizontal separator (no trailing newline).

    ``rows`` (terminal height) and ``min_action_rows`` size the vertical budget
    for the ``"window"`` variant. Returns ``None`` when ``detail == "window"``
    and no window fits the available rows, so the caller can drop this rung from
    the fallback ladder and fall through to a smaller one.
    """
    from little_loops.cli.loop.layout import (
        _collect_edges,
        _filter_main_path_graph,
        _render_fsm_diagram,
        _render_neighborhood_diagram,
        _render_windowed_diagram,
    )

    verbose = facets.scope == "full" and facets.state_detail == "full"

    def _render_one(
        target: FSMLoop, highlight: str | None, prev: str | None, *, budget: int = 0
    ) -> str:
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
        if detail == "window":
            # Same off-happy-path guard as the layered branch: if the active
            # state was filtered out of the main-scope graph, render full scope.
            scope = facets.scope
            if scope == "main" and highlight is not None:
                _fe, reachable = _filter_main_path_graph(target, _collect_edges(target))
                if highlight not in reachable:
                    scope = "full"
            return _render_windowed_diagram(
                target,
                highlight,
                budget=budget,
                verbose=verbose,
                highlight_color=highlight_color,
                edge_label_colors=edge_label_colors,
                badges=badges,
                mode=scope,
                suppress_labels=not facets.edge_labels,
                title_only=facets.state_detail == "title",
            )
        # "full" (layered) and the "title_only" detail-shedding rungs (ENH-2411).
        # All three keep every state; the title-only rungs force shorter (and,
        # for _nolabels, narrower) boxes without introducing any new render code.
        scope = facets.scope
        if scope == "main" and highlight is not None:
            _filtered_edges, reachable = _filter_main_path_graph(target, _collect_edges(target))
            if highlight not in reachable:
                scope = "full"
        if detail == "title_only":
            render_verbose = False
            render_title_only = True
            render_suppress = not facets.edge_labels
        elif detail == "title_only_nolabels":
            render_verbose = False
            render_title_only = True
            render_suppress = True
        else:  # "full"
            render_verbose = verbose
            render_title_only = facets.state_detail == "title"
            render_suppress = not facets.edge_labels
        return _render_fsm_diagram(
            target,
            verbose=render_verbose,
            highlight_state=highlight,
            highlight_color=highlight_color,
            edge_label_colors=edge_label_colors,
            badges=badges,
            mode=scope,
            suppress_labels=render_suppress,
            title_only=render_title_only,
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
    # Clamp header artifact/model lines to `cols` display columns (the separator
    # above is already width-clamped). Otherwise a long path-like value — e.g. a
    # task `input:` that happens to contain "/" — poisons `_variant_width` for
    # every pinned rung, so `_choose_pinned_layout`'s width filter rejects all box
    # variants and collapses to the single-line `fsm:` floor (BUG: general-task).
    lines.extend(
        _render_artifact_header_lines(
            fsm, loop_path, model, _resolve_input_value(fsm, show_input), cols
        )
    )

    # Vertical budget for the windowed variant: total rows minus the header /
    # artifact / model lines already accumulated, the iteration + separator
    # rows added below, and the action-output rows reserved beneath the pane.
    win_budget = 0
    if rows is not None:
        win_budget = rows - len(lines) - 2 - min_action_rows

    diagram = _render_one(active_fsm, active_state, active_prev, budget=win_budget)
    if detail == "window" and not diagram:
        # No window fit the available rows — signal the caller to drop this rung.
        return None
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
    model: str | None = None,
    show_input: bool = True,
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

    # compact presets (clean/slim) set state_detail="title" and already sacrifice
    # action body lines; tolerate fewer rows below the diagram to avoid the
    # single-line fsm: fallback on larger loops.
    effective_min_action_rows = 3 if facets.state_detail == "title" else min_action_rows

    def _build(detail: str) -> str | None:
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
            model=model,
            show_input=show_input,
            rows=rows,
            min_action_rows=effective_min_action_rows,
        )

    # Build the fallback ladder based on facets source and topology.
    # Explicit topology (source="topology"): render exactly once, no degradation.
    # Preset/default with layered topology: topology-aware ladder (ENH-2411) —
    #   _build_fallback_ladder orders the rungs (full / title-only / window /
    #   neighborhood / single) by the FSM's classified shape and the failing
    #   viewport dimension, always terminating in the single-line floor.
    # Explicit neighborhood topology: neighborhood→single.
    topo_detail = TOPOLOGY_TO_DETAIL[facets.topology]
    raw_variants: list[str | None]
    if facets.source == "topology":
        # A "window" topology can fail to fit and return None; fall back to single.
        raw_variants = [v for v in [_build(topo_detail)] if v is not None] or [_build("single")]
    elif topo_detail == "full":
        # Build "full" once, then let the ladder builder probe its width and the
        # FSM's topology to order the remaining rungs.
        full_variant = _build("full")
        ladder = _build_fallback_ladder(facets, fsm, full_variant, cols)
        raw_variants = [full_variant if rung == "full" else _build(rung) for rung in ladder]
    elif topo_detail == "neighborhood":
        raw_variants = [_build("neighborhood"), _build("single")]
    else:  # inline / single
        raw_variants = [_build("single")]

    # Drop rungs that could not render (only "window" returns None) so
    # _choose_pinned_layout never picks a diagram-less pane over a real fallback.
    variants: list[str] = [v for v in raw_variants if v is not None]

    pinned, pinned_height = _choose_pinned_layout(
        rows,
        variants,
        min_action_rows=effective_min_action_rows,
        cols=cols,
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


def _render_streaming_diagram(
    fsm: FSMLoop,
    highlight_state: str | None,
    *,
    facets: DiagramFacets,
    highlight_color: str,
    edge_label_colors: dict[str, str] | None,
    badges: dict[str, str] | None,
    scope: str,
    cols: int,
) -> str:
    """Render the FSM diagram for the non-TTY streaming path, degrading it via
    the ENH-2411/ENH-2442 fallback ladder until it fits ``cols`` display columns.

    The pinned/TTY path routes through ``_render_pinned_pane`` →
    ``_build_fallback_ladder`` and sheds detail when a diagram won't fit. The
    streaming (background/log) path previously called ``_render_fsm_diagram``
    directly with no width budget, so a wide/back-edge-heavy loop overflowed and
    wrapped into a broken stream (BUG-2425 Defect 2). This mirrors the ladder for
    streaming: render ``full``; if it fits, use it; otherwise walk the
    topology-ordered ladder (``title_only`` / ``window`` / ``neighborhood`` /
    ``single``) and return the first rung whose widest line fits ``cols``. The
    ``window`` rung (ENH-2410) uses a per-event row budget derived from ``cols``
    (the streaming path has no scroll-region to size against). ``single`` is the
    guaranteed floor.

    ``scope`` is the already-resolved main→full scope from the caller (its
    off-happy-path fallback has already run), so every rung renders at that scope.
    """
    from little_loops.cli.loop.layout import (
        _render_fsm_diagram,
        _render_neighborhood_diagram,
        _render_windowed_diagram,
    )

    verbose = facets.scope == "full" and facets.state_detail == "full"

    def _render_rung(detail: str) -> str:
        if detail == "single":
            return _render_single_line_status(fsm, highlight_state)
        if detail == "neighborhood":
            return _render_neighborhood_diagram(
                fsm,
                highlight_state or fsm.initial,
                edge_label_colors=edge_label_colors,
                badges=badges,
                highlight_color=highlight_color,
                mode=scope,
                prev_state=None,
            )
        if detail == "window":
            return _render_windowed_diagram(
                fsm,
                highlight_state,
                budget=max(8, cols // 4),
                verbose=verbose,
                highlight_color=highlight_color,
                edge_label_colors=edge_label_colors,
                badges=badges,
                mode=scope,
                suppress_labels=not facets.edge_labels,
                title_only=facets.state_detail == "title",
            )
        # "full" and the "title_only" detail-shedding rungs (ENH-2411) — all keep
        # every state; the title-only rungs force shorter/narrower boxes.
        if detail == "title_only":
            render_verbose, render_title_only, render_suppress = False, True, not facets.edge_labels
        elif detail == "title_only_nolabels":
            render_verbose, render_title_only, render_suppress = False, True, True
        else:  # full
            render_verbose = verbose
            render_title_only = facets.state_detail == "title"
            render_suppress = not facets.edge_labels
        return _render_fsm_diagram(
            fsm,
            verbose=render_verbose,
            highlight_state=highlight_state,
            highlight_color=highlight_color,
            edge_label_colors=edge_label_colors,
            badges=badges,
            mode=scope,
            suppress_labels=render_suppress,
            title_only=render_title_only,
        )

    full_variant = _render_rung("full")
    if _variant_width(full_variant) <= cols:
        return full_variant

    ladder = _build_fallback_ladder(facets, fsm, full_variant, cols)
    for rung in ladder:
        if rung == "full":
            continue
        variant = _render_rung(rung)
        if variant and _variant_width(variant) <= cols:
            return variant

    # Guaranteed floor: the single-line status always fits.
    return _render_single_line_status(fsm, highlight_state)


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
        model: str | None = None,
        show_input: bool = True,
    ) -> None:
        self.fsm = fsm
        self.args = args
        self.highlight_color = highlight_color
        self.edge_label_colors = edge_label_colors
        self.badges = badges
        self.loops_dir = loops_dir or Path(".")
        self.loop_path = loop_path
        self.model = model
        self.show_input = show_input

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
            f"[{self.current_iteration[0]}/{self.fsm.max_steps}] "
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
            model=self.model,
            show_input=self.show_input,
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
                    except (FileNotFoundError, ValueError) as e:
                        Logger().warning(
                            f"Could not load child loop '{fsm_state.loop}' for state '{state}': {e}"
                        )
                        self.child_fsm_stack[depth] = None
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
                with with_diagram_color(True):
                    self._redraw_pinned(state0)
            elif self.show_diagrams:
                from little_loops.cli.loop.layout import (
                    _collect_edges,
                    _filter_main_path_graph,
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
                # BUG-2425: route through the ENH-2411 width-fallback ladder so a
                # wide/back-edge-heavy diagram degrades (title-only / neighborhood
                # / single) instead of overflowing the non-TTY log width.
                with with_diagram_color(True):
                    diagram = _render_streaming_diagram(
                        active_fsm_diag,
                        active_highlight,
                        facets=self.facets,
                        highlight_color=self.highlight_color,
                        edge_label_colors=self.edge_label_colors,
                        badges=self.badges,
                        scope=active_scope,
                        cols=tw,
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
                for line in _render_artifact_header_lines(
                    self.fsm,
                    self.loop_path,
                    self.model,
                    _resolve_input_value(self.fsm, self.show_input),
                    tw,
                ):
                    print(line, flush=True)
                print(diagram, flush=True)
            # In pinned mode the iteration line is part of the pinned pane;
            # only print it inline for non-pinned paths.
            if not self.quiet and not self.in_pinned_mode:
                print(
                    f"{indent}[{self.current_iteration[0]}/{self.fsm.max_steps}] {colorize(state, '1')} ({colorize(elapsed_str, '2')})",
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
            actual_model = event.get("model")
            if actual_model:
                self.model = actual_model
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

        elif event_type == "baseline_complete":
            if not self.quiet:
                h_ms = event.get("harness_duration_ms", 0)
                b_ms = event.get("baseline_duration_ms", 0)
                h_tok = event.get("harness_tokens", 0)
                b_tok = event.get("baseline_tokens", 0)
                print(
                    f"{indent}       baseline: {colorize(f'{b_ms / 1000:.1f}s', '2')}, "
                    f"{colorize(str(b_tok), '2')} tokens  |  "
                    f"harness: {colorize(f'{h_ms / 1000:.1f}s', '2')}, "
                    f"{colorize(str(h_tok), '2')} tokens",
                    flush=True,
                )

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

        elif event_type == "max_steps_summary":
            if not self.quiet:
                summary_state = event.get("summary_state", "")
                iters = event.get("iterations", 0)
                msg = f"step cap reached ({iters}); running summary state '{summary_state}'"
                print(f"{indent}       {colorize(msg, '38;5;208')}", flush=True)

        elif event_type == "max_iterations_reached_summary":
            if not self.quiet:
                summary_state = event.get("summary_state", "")
                iteration_count = event.get("iteration_count", 0)
                msg = f"iteration cap reached ({iteration_count}); running summary state '{summary_state}'"
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


def _relativize_to_cwd(value: str) -> str:
    """Shorten an absolute path that lives under the current working directory.

    Absolute paths nested under ``cwd`` are rendered relative to it (e.g.
    ``/home/user/proj/.loops/runs/x/`` -> ``.loops/runs/x/``). Any trailing
    slash on *value* is preserved. Values that are already relative, or that
    point outside ``cwd``, are returned unchanged.
    """
    try:
        path = Path(value)
        if not path.is_absolute():
            return value
        rel = path.relative_to(Path.cwd())
    except (ValueError, OSError):
        return value
    result = str(rel)
    if value.endswith("/") and not result.endswith("/"):
        result += "/"
    return result


def _display_loop_path(loop_path: Path) -> str:
    """Render *loop_path* compactly for artifact headers.

    Built-in FSM loops (bundled under :func:`get_builtin_loops_dir`) are shown
    by filename only. Project-level loops (typically under ``.loops/``) and any
    other paths under the current working directory are shown relative to it.
    Paths that resolve outside both locations are returned unchanged.
    """
    try:
        resolved = loop_path.resolve()
        builtin_dir = get_builtin_loops_dir().resolve()
        resolved.relative_to(builtin_dir)
        return loop_path.name
    except (ValueError, OSError):
        return _relativize_to_cwd(str(loop_path))


def _artifact_lines(fsm: FSMLoop, loop_path: Path | None) -> list[tuple[str, str]]:
    """Extract path-like context values from *fsm* for display in artifact headers.

    Returns a list of ``(key, value)`` pairs where *value* is a non-empty string
    that starts with ``.``, ``/``, or ``~``, or contains ``/``, and does not
    contain ``${`` (unresolved template expression). When *loop_path* is not
    ``None``, the first entry is always ``("loop", ...)`` where the value is the
    filename for built-in loops or a cwd-relative path for project-level loops.
    Other path-like values (e.g. ``run_dir``) are relativized to the current
    working directory when they live under it.
    """
    pairs: list[tuple[str, str]] = []
    if loop_path is not None:
        pairs.append(("loop", _display_loop_path(loop_path)))
    context: dict[str, Any] = getattr(fsm, "context", None) or {}
    for key, value in context.items():
        if not isinstance(value, str) or not value:
            continue
        if "${" in value:
            continue
        if value.startswith(".") or value.startswith("/") or value.startswith("~") or "/" in value:
            pairs.append((key, _relativize_to_cwd(value)))
    return pairs


def _resolve_input_value(fsm: FSMLoop, show_input: bool) -> str | None:
    """Return the run's ``--input`` string for header display, or ``None``.

    Reads ``fsm.context[fsm.input_key]`` (falling back to the literal
    ``"input"`` key), and returns ``None`` when ``show_input`` is false, the
    value is absent, empty, or not a plain string (e.g. the dict-spread case
    in ``cmd_run`` where no single scalar exists to show).
    """
    if not show_input:
        return None
    context: dict[str, Any] = getattr(fsm, "context", None) or {}
    value = context.get(fsm.input_key)
    if value is None:
        value = context.get("input")
    if not isinstance(value, str) or not value:
        return None
    return value


def _render_artifact_header_lines(
    fsm: FSMLoop,
    loop_path: Path | None,
    model: str | None,
    input_value: str | None,
    cols: int,
) -> list[str]:
    """Compose the diagram-header artifact lines.

    Packs ``input:`` onto the ``loop:`` row and ``model:`` onto the
    ``run_dir:`` row (falling back to a standalone ``model:`` line when no
    ``run_dir`` context value is present) — ``input`` never separates from
    ``loop`` and ``model`` never separates from ``run_dir``. Adjacent rows
    are then greedily merged onto a single line, front to back, as long as
    the combined row still fits within ``cols`` display columns — so all
    rows collapse to one line when there's room, and only the row(s) that
    don't fit spill onto subsequent lines. Each resulting line is clamped to
    ``cols`` via ``_truncate_to_width_ansi`` as a safety net for a single
    value too long to fit even alone.
    """
    from little_loops.cli.loop.layout import _display_width, _truncate_to_width_ansi

    artifact_pairs = _artifact_lines(fsm, loop_path)
    run_dir_present = any(key == "run_dir" for key, _ in artifact_pairs)
    rows: list[str] = []
    for key, value in artifact_pairs:
        line = f"  {key}: {colorize(value, '2')}"
        if key == "loop" and input_value:
            line += f"  input: {colorize(input_value, '2')}"
        elif key == "run_dir" and model is not None:
            line += f"  model: {colorize(model, '2')}"
        rows.append(line)
    if model is not None and not run_dir_present:
        rows.append(f"  model: {colorize(model, '2')}")

    if not rows:
        return []

    merged: list[str] = [rows[0]]
    for row in rows[1:]:
        candidate = f"{merged[-1]}  {row.strip()}"
        if _display_width(candidate) <= cols:
            merged[-1] = candidate
        else:
            merged.append(row)

    return [_truncate_to_width_ansi(line, cols) for line in merged]


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
    print(f"Max steps: {fsm.max_steps}")
    if fsm.max_iterations is not None:
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
    loop_name: str,
    args: argparse.Namespace,
    loops_dir: Path,
    subcommand: str = "run",
    instance_id: str | None = None,
) -> int:
    """Launch loop as a detached background process.

    Spawns a new process with start_new_session=True that re-executes
    the loop with --foreground-internal. The parent writes the PID file
    and returns immediately.

    Args:
        subcommand: The ll-loop subcommand to spawn ("run" or "resume").
        instance_id: Pre-resolved instance ID. When provided, skips
            _make_instance_id() allocation. Used by cmd_resume() to pass
            an already-discovered resumable instance.

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
    # Build context for scope resolution: YAML defaults + CLI --context overrides.
    # CLI --context is only forwarded to the child process (line ~1018); we parse
    # it locally so resolve_scope() can use it for the pre-flight conflict check.
    scope_context = dict(fsm.context)
    for kv in getattr(args, "context", None) or []:
        key, _, value = kv.partition("=")
        scope_context[key.strip()] = value.strip()
    scope = resolve_scope(fsm.scope or ["."], scope_context)
    conflict = lock_manager.find_conflict(
        scope,
        caller_loop_name=fsm.name,
        caller_singleton=fsm.singleton,
    )
    if conflict and not getattr(args, "queue", False) and not getattr(args, "no_lock", False):
        print(f"Scope conflict with running loop: {conflict.loop_name}", file=sys.stderr)
        print(f"  Conflicting scope: {conflict.scope}", file=sys.stderr)
        print("  Use --queue to wait for it to finish", file=sys.stderr)
        return 1

    if instance_id is None:
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
    max_steps = getattr(args, "max_steps", None)
    if max_steps:
        cmd.extend(["--max-steps", str(max_steps)])
    max_iter = getattr(args, "max_iterations", None)
    if max_iter:
        cmd.extend(["--max-iterations", str(max_iter)])
    if getattr(args, "no_llm", False):
        cmd.append("--no-llm")
    run_model = getattr(args, "run_model", None)
    if run_model:
        cmd.extend(["--model", run_model])
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
    if getattr(args, "no_host_guard", False):
        cmd.append("--no-host-guard")
    host_guard_budget_mb = getattr(args, "host_guard_budget_mb", None)
    if host_guard_budget_mb is not None:
        cmd.extend(["--host-guard-budget-mb", str(host_guard_budget_mb)])
    handoff_threshold = getattr(args, "handoff_threshold", None)
    if handoff_threshold is not None:
        cmd.extend(["--handoff-threshold", str(handoff_threshold)])
    context_limit = getattr(args, "context_limit", None)
    if context_limit is not None:
        cmd.extend(["--context-limit", str(context_limit)])
    if getattr(args, "baseline", False):
        cmd.append("--baseline")
    baseline_skill = getattr(args, "baseline_skill", None)
    if baseline_skill is not None:
        cmd.extend(["--baseline-skill", baseline_skill])
    items = getattr(args, "items", None)
    if items is not None:
        cmd.extend(["--items", str(items)])
    if getattr(args, "cross_host", False):
        cmd.append("--cross-host")
    cost_output_json = getattr(args, "cost_output_json", None)
    if cost_output_json is not None:
        cmd.extend(["--cost-output-json", str(cost_output_json)])

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
    model: str | None = None,
    show_input: bool = True,
    cost_output_json: Path | None = None,
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
            model=model,
            show_input=show_input,
        )
        if not renderer.quiet:
            print(f"Running loop: {colorize(fsm.name, '1')}")
            print(f"Max steps: {colorize(str(fsm.max_steps), '2')}")
            if fsm.max_iterations is not None:
                print(f"Max iterations: {colorize(str(fsm.max_iterations), '2')}")
            for key, value in _artifact_lines(fsm, loop_path):
                print(f"  {key}: {colorize(value, '2')}")
            if model is not None:
                print(f"  model: {colorize(model, '2')}")
            print()

        # Wire progress display via the EventBus on PersistentExecutor
        if not renderer.quiet or renderer.show_diagrams:
            if hasattr(executor, "event_bus"):
                executor.event_bus.register(renderer.handle_event)
            else:
                executor._on_event = renderer.handle_event

        # Capture the last failure-relevant message from the event stream so the
        # completion summary can surface *why* a run failed. This is the only reliable
        # source: on on_error / exception routes the executor leaves prev_result and
        # captured empty, and alt-screen teardown or non-verbose mode hide the live
        # output. action_error carries interpolation/exception reasons; a non-zero
        # action_complete carries the failing state's stdout.
        _failure_capture: dict[str, str] = {}

        def _capture_failure(event: dict[str, Any]) -> None:
            ev = event.get("event")
            if ev == "action_error" and event.get("error"):
                _failure_capture["error"] = str(event["error"])
            elif ev == "action_complete" and event.get("exit_code") not in (0, None):
                out = event.get("output") or event.get("output_preview") or ""
                if out:
                    _failure_capture["output"] = str(out)

        if not renderer.quiet:
            if hasattr(executor, "event_bus"):
                executor.event_bus.register(_capture_failure)
            else:
                _prev_capture_cb = executor._on_event

                def _chained_capture(event: dict[str, Any]) -> None:
                    if _prev_capture_cb:
                        _prev_capture_cb(event)
                    _capture_failure(event)

                executor._on_event = _chained_capture

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
            # Remember whether we were in the alt-screen so the summary block can
            # decide whether the failing state's output still needs re-printing
            # (alt-screen teardown wipes it from scrollback).
            _was_alt_screen = _using_alt_screen
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
            # A terminal state whose name is not "done" represents failure (the
            # established convention; see sub-FSM routing in executor.py). Colour
            # only genuine success green so a `failed` terminal doesn't read as a pass.
            _is_success = result.terminated_by in ("terminal", "interrupted", "handoff") and not (
                result.terminated_by == "terminal" and result.final_state != "done"
            )
            if _is_success:
                state_colored = colorize(result.final_state, "32")
            else:
                state_colored = colorize(result.final_state, "38;5;208")

            # Surface the failing state's output as the failure reason. It is otherwise
            # invisible: the alt-screen wipes it on teardown, and in non-verbose mode the
            # per-state stdout is never printed inline at all. Skip only the verbose
            # non-alt-screen case, where the live renderer already echoed it.
            if not _is_success and (_was_alt_screen or not renderer.verbose):
                reason_text = (
                    _failure_capture.get("error")
                    or _failure_capture.get("output")
                    or result.error
                    or ""
                ).strip()
                if reason_text:
                    print()
                    print(colorize("Failure reason:", "1"))
                    for _line in reason_text.splitlines()[-40:]:  # cap to bound scrollback
                        print(colorize("│ " + _line, "2"))

            completion_prefix = "Resumed and completed" if mode == "resume" else "Loop completed"
            rejection_count = 0
            for _t in getattr(getattr(executor, "event_bus", None), "_transports", []):
                if hasattr(_t, "get_stats"):
                    rejection_count += _t.get_stats().get("client_rejections", 0)
            suffix = f", {rejection_count} client rejections" if rejection_count > 0 else ""

            # Print per-state token/cost table if usage data was collected
            run_dir = fsm.context.get("run_dir", "")
            if run_dir:
                try:
                    _print_usage_summary(
                        Path(run_dir) / "usage.jsonl",
                        cost_output_json=cost_output_json,
                    )
                except Exception:
                    pass  # Non-fatal: display failure shouldn't block exit

            print(
                f"{completion_prefix}: {state_colored} ({result.iterations} iterations, {duration_str}{suffix})"
            )

            # FEAT-1822: Print A/B summary if baseline was enabled
            if run_dir:
                ab_path = Path(run_dir) / "ab.json"
                if ab_path.exists():
                    try:
                        _print_ab_summary(ab_path)
                    except Exception:
                        pass  # Non-fatal: display failure shouldn't block exit

                    # ENH-2086: Cross-host validation when --cross-host was requested
                    baseline_ctx = fsm.context.get("_baseline") or {}
                    if baseline_ctx.get("cross_host"):
                        loop_name = getattr(args, "loop", "")
                        try:
                            _run_cross_host_validation(
                                args,
                                loop_path,
                                Path(run_dir),
                                ab_path,
                                loop_name,
                            )
                        except Exception:
                            pass  # Non-fatal

        return EXIT_CODES.get(result.terminated_by, 1)
    finally:
        sys.stdout = _orig_stdout
        sys.stderr = _orig_stderr
        if _log_fh is not None:
            _log_fh.close()


def _print_usage_summary(usage_path: Path, cost_output_json: Path | None = None) -> None:
    """Print per-state token usage summary from usage.jsonl.

    Args:
        usage_path: Path to usage.jsonl written by PersistentExecutor
        cost_output_json: Optional path to also write the stable-JSON
            report (ENH-2477). Write failures are non-fatal: a missing
            parent dir or unwritable path must not block the run's
            normal exit path.
    """
    from little_loops.fsm.cost_graph import CostReport

    if not usage_path.exists():
        return
    report = CostReport.from_usage_jsonl(usage_path)
    if not report.states:
        return

    print()
    print(report.table())

    if cost_output_json is not None:
        try:
            report.write_json(cost_output_json)
        except OSError:
            pass  # Non-fatal: a failed write shouldn't block the run


def _print_ab_summary(ab_path: Path) -> None:
    """Print A/B comparison summary from ab.json.

    Args:
        ab_path: Path to ab.json file written by the executor
    """
    from little_loops.ab_writer import read_ab_json
    from little_loops.stats import wilson_ci

    results = read_ab_json(str(ab_path.parent))
    if results is None or not results.per_item:
        return

    n = len(results.per_item)
    harness_pct = results.harness_pass_rate * 100
    baseline_pct = results.baseline_pass_rate * 100
    delta_pct = results.delta * 100

    k_harness = sum(1 for item in results.per_item if item.get("harness_pass", False))
    k_baseline = sum(1 for item in results.per_item if item.get("baseline_pass", False))
    h_lo, h_hi = wilson_ci(k_harness, n)
    b_lo, b_hi = wilson_ci(k_baseline, n)

    tokens_ratio = (
        results.median_tokens_harness / results.median_tokens_baseline
        if results.median_tokens_baseline > 0
        else 0
    )
    dur_ratio = (
        results.median_duration_harness / results.median_duration_baseline
        if results.median_duration_baseline > 0
        else 0
    )

    def _fmt_dur(ms: float) -> str:
        if ms < 1000:
            return f"{ms:.0f}ms"
        elif ms < 60000:
            return f"{ms / 1000:.1f}s"
        else:
            return f"{ms / 60000:.1f}m"

    tokens_dir = "+" if tokens_ratio > 1 else "-"
    dur_dir = "+" if dur_ratio > 1 else "-"

    print()
    print(f"A/B Summary (n={n})")
    print(f"  Harness pass-rate:  {harness_pct:.0f}%  [{h_lo:.2f}, {h_hi:.2f}]")
    print(f"  Baseline pass-rate: {baseline_pct:.0f}%  [{b_lo:.2f}, {b_hi:.2f}]")
    print(f"  Delta:              {delta_pct:+.0f}%")
    print()
    print(
        f"  Median tokens:      harness={results.median_tokens_harness}  "
        f"baseline={results.median_tokens_baseline}  "
        f"({tokens_dir}{abs(tokens_ratio - 1) * 100:.0f}%)"
    )
    print(
        f"  Median duration:    harness={_fmt_dur(results.median_duration_harness)}  "
        f"baseline={_fmt_dur(results.median_duration_baseline)}  "
        f"({dur_dir}{abs(dur_ratio - 1) * 100:.0f}%)"
    )

    # Verdict line
    quality_verdict = (
        "harness wins on quality"
        if results.delta > 0
        else "baseline wins on quality"
        if results.delta < 0
        else "no quality difference"
    )
    cost_verdict = (
        f"costs ~{abs(tokens_ratio - 1) * 100:.0f}% more tokens"
        if tokens_ratio > 1
        else (
            f"costs ~{abs(tokens_ratio - 1) * 100:.0f}% fewer tokens"
            if tokens_ratio < 1
            else "same token cost"
        )
    )
    print(f"  Verdict:            {quality_verdict}, {cost_verdict}")
    print()
    print(f"Per-item: {ab_path}")


def _run_cross_host_validation(
    args: argparse.Namespace,
    loop_path: Path | None,
    primary_run_dir: Path,
    primary_ab_path: Path,
    loop_name: str,
) -> None:
    """Re-run the loop on a second available host and print a cross-host comparison.

    Identifies a second host via _PROBE_ORDER, runs the same baseline trial with
    LL_HOST_CLI overridden, then calls _print_cross_host_table if both ab.json
    files are available.
    """
    import os
    import shutil

    from little_loops.host_runner import _PROBE_ORDER, HostNotConfigured, resolve_host

    # Identify the current (primary) host
    try:
        primary_host = resolve_host().name
    except HostNotConfigured:
        primary_host = None

    # Find a second available host different from the primary
    second_host: str | None = None
    for host_name, binary in _PROBE_ORDER:
        if host_name == primary_host:
            continue
        if shutil.which(binary) is not None:
            second_host = host_name
            break

    if second_host is None:
        print("\nCross-host: only one host available — skipping cross-host validation.")
        return

    print(f"\nCross-host: running {loop_name!r} on {second_host}...")

    # Build the second-host command
    cmd = ["ll-loop", "run", "--baseline"]
    baseline_skill = getattr(args, "baseline_skill", None)
    if baseline_skill is not None:
        cmd.extend(["--baseline-skill", baseline_skill])
    items = getattr(args, "items", None)
    if items is not None:
        cmd.extend(["--items", str(items)])
    cmd.append(loop_name)

    env = dict(os.environ)
    env["LL_HOST_CLI"] = second_host

    before = time.time()
    result = subprocess.run(cmd, env=env)

    if result.returncode != 0:
        print(
            f"\nCross-host: second-host run ({second_host}) failed "
            f"(exit {result.returncode}) — no comparison available."
        )
        return

    # Find the second run's ab.json: newest file under the same runs directory
    # that appeared after the second run started and differs from the primary.
    runs_dir = primary_run_dir.parent
    candidates = sorted(
        runs_dir.glob("*/ab.json"),
        key=lambda p: p.stat().st_mtime,
        reverse=True,
    )
    second_ab_path = next(
        (p for p in candidates if p != primary_ab_path and p.stat().st_mtime >= before),
        None,
    )

    if second_ab_path is None:
        print(
            "\nCross-host: second-host run completed but no ab.json found — "
            "no comparison available."
        )
        return

    from little_loops.ab_writer import read_ab_json

    primary_results = read_ab_json(str(primary_run_dir))
    second_results = read_ab_json(str(second_ab_path.parent))

    if primary_results is None or second_results is None:
        return

    _print_cross_host_table(primary_host or "primary", primary_results, second_host, second_results)


def _print_cross_host_table(
    host1: str,
    results1: Any,
    host2: str,
    results2: Any,
) -> None:
    """Print a cross-host pass-rate comparison table with Wilson 95% CIs."""
    from little_loops.stats import wilson_ci

    def _host_stats(results: Any) -> tuple[int, int, float, float, float]:
        n = len(results.per_item)
        k = sum(1 for item in results.per_item if item.get("harness_pass", False))
        rate = results.harness_pass_rate * 100
        lo, hi = wilson_ci(k, n) if n > 0 else (0.0, 0.0)
        return n, k, rate, lo, hi

    n1, _k1, rate1, lo1, hi1 = _host_stats(results1)
    n2, _k2, rate2, lo2, hi2 = _host_stats(results2)

    print()
    print("Cross-host Comparison")
    print(f"  {'Host':<20}  {'Pass rate':>10}  {'95% CI':>18}  {'n':>5}")
    print(f"  {'-' * 20}  {'-' * 10}  {'-' * 18}  {'-' * 5}")
    print(f"  {host1:<20}  {rate1:>9.0f}%  [{lo1:.2f}, {hi1:.2f}]  {n1:>5}")
    print(f"  {host2:<20}  {rate2:>9.0f}%  [{lo2:.2f}, {hi2:.2f}]  {n2:>5}")

    # Warn when the harness-vs-baseline ordering reverses between hosts
    host1_harness_wins = results1.delta > 0
    host2_harness_wins = results2.delta > 0
    if host1_harness_wins != host2_harness_wins:
        winner1 = "harness" if host1_harness_wins else "baseline"
        winner2 = "harness" if host2_harness_wins else "baseline"
        print()
        print(
            f"  ⚠ Ordering reversal: {host1} shows {winner1} ahead, "
            f"{host2} shows {winner2} ahead. "
            "Improvement may be host-specific."
        )
    print()

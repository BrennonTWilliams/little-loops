"""ll-loop diagram/pinned-pane rendering and live event feed display.

Relocated from ``cli/loop/_helpers.py`` (ENH-2776). ``_format_history_event``
was moved down from ``cli/loop/info.py`` (which imports it back) — that move
is the break for the former ``_helpers``<->``info`` deferred-import cycle:
``info.py`` and ``cli/loop/runner.py`` both import it downward from here.
``layout.py`` does not import this module, so the ``layout`` imports below
are module-level rather than the deferred imports the original file used to
avoid a cycle that no longer exists.
"""

from __future__ import annotations

import argparse
import contextlib
import os
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

from little_loops.cli import output as _output
from little_loops.cli.loop import signals
from little_loops.cli.loop.diagram_modes import TOPOLOGY_TO_DETAIL, DiagramFacets, resolve_facets
from little_loops.cli.loop.header import _render_artifact_header_lines, _resolve_input_value
from little_loops.cli.loop.layout import (
    TopologyDetector,
    _bfs_order,
    _classify_edges,
    _collect_edges,
    _display_width,
    _filter_main_path_graph,
    _render_fsm_diagram,
    _render_neighborhood_diagram,
    _render_windowed_diagram,
    _trace_main_path,
    _truncate_to_width,
)
from little_loops.cli.output import colorize, strip_ansi, terminal_size, terminal_width
from little_loops.fsm.loop_paths import load_loop
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


# Minimum number of action-output rows reserved beneath the pinned pane in
# alt-screen mode. When the pinned pane plus this margin would exceed the
# terminal height, the layout falls back to a more compact diagram variant.
MIN_ACTION_ROWS = 6


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
    edges = _collect_edges(fsm)
    bfs_order_list, _bfs_depth = _bfs_order(fsm.initial, edges)
    main_path, main_edge_set = _trace_main_path(fsm, edges)
    branches, back_edges = _classify_edges(edges, main_edge_set, bfs_order_list)
    return TopologyDetector(edges, main_path, branches, back_edges).classify()


def _variant_width(variant: str | None) -> int:
    """Return the widest display (ANSI-stripped) line in a rendered variant.

    Uses ``_display_width`` (wcwidth) rather than ``len`` so double-width glyphs
    (emoji badges, CJK, some arrows) are sized by the columns they occupy, not
    the code points they take (BUG-2425 Part 3).
    """
    if not variant:
        return 0
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
    effort: str | None = None,
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
            fsm, loop_path, model, _resolve_input_value(fsm, show_input), cols, effort=effort
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
    effort: str | None = None,
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
            effort=effort,
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
        effort: str | None = None,
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
        self.effort = effort
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
            effort=self.effort,
            show_input=self.show_input,
        )

    def handle_event(self, event: dict) -> None:
        """Display progress for events."""
        # SIGWINCH redraw: terminal was resized; re-render the pinned pane
        # before processing the next event so the layout matches the new size.
        if signals._needs_redraw and self.in_pinned_mode and 0 in self.last_state_at_depth:
            self._redraw_pinned(self.last_state_at_depth[0])
            signals._needs_redraw = False

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
                    effort=self.effort,
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
            actual_effort = event.get("effort")
            if actual_effort:
                self.effort = actual_effort
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
                    verdict_colored = colorize(verdict, "90")
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


# ---------------------------------------------------------------------------
# History-event formatting (moved down from cli/loop/info.py — ENH-2776 cycle
# break; info.py imports _format_history_event back from here).
# ---------------------------------------------------------------------------

_EVENT_TYPE_WIDTH = 16  # width of "handoff_detected"


def _truncate(text: str, max_len: int) -> str:
    """Display-width-aware truncation (delegates to layout._truncate_to_width).

    Replaces an earlier character-count helper; keeps wide glyphs whole and
    sizes the trailing ellipsis in display columns rather than codepoints.
    """
    return _truncate_to_width(text, max_len)


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

    ts_str = colorize(ts, "90")
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
        if error := event.get("error"):
            detail += f"  {colorize(error, '31')}"

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
        kind_str = colorize(f"[{kind_label}]", "90")
        first_line = (
            next((ln.strip() for ln in action.splitlines() if ln.strip()), "")
            if is_prompt
            else action
        )
        avail = width - 8 - 2 - _EVENT_TYPE_WIDTH - 2 - len(kind_label) - 2 - 2
        detail = f"{_truncate(first_line, max(avail, 20))}  {kind_str}"

    elif event_type == "action_output":
        # Only reached in verbose mode
        etype_color = "90"
        detail = colorize("│ " + event.get("line", ""), "90")

    elif event_type == "action_complete":
        exit_code = event.get("exit_code", 0)
        duration_ms = event.get("duration_ms", 0)
        if exit_code == 0:
            etype_color = "90"
            status_str = colorize("✓", "32")
        else:
            etype_color = "38;5;208"
            status_str = colorize(f"✗ exit={exit_code}", "38;5;208")
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
                    extra_lines.append(colorize(_indent + "│ " + preview_line, "90"))

    elif event_type == "evaluate":
        verdict = event.get("verdict", "")
        confidence = event.get("confidence", "")
        reason = event.get("reason", "")
        if verdict == "yes":
            etype_color = "32"
            verdict_str = colorize("✓ yes", "32")
        else:
            etype_color = "38;5;208"
            verdict_str = colorize(f"✗ {verdict}", "38;5;208")
        conf_part = f"  confidence={confidence}" if confidence != "" else ""
        avail = width - 8 - 2 - _EVENT_TYPE_WIDTH - 2 - len("✓ yes") - len(conf_part) - 2
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
                    colorize(_indent + colorize("LLM Call", "90") + "  " + meta_str, "90")
                )
                avail_w = width - len(_indent) - len("Prompt:   ") - 2
                if llm_prompt:
                    prompt_text = llm_prompt if full else _truncate(llm_prompt, max(avail_w, 40))
                    extra_lines.append(colorize(_indent + "Prompt:   " + prompt_text, "90"))
                if llm_raw_output:
                    resp_text = (
                        llm_raw_output if full else _truncate(llm_raw_output, max(avail_w, 40))
                    )
                    extra_lines.append(colorize(_indent + "Response: " + resp_text, "90"))

    elif event_type == "route":
        etype_color = "90"
        from_state = event.get("from", "")
        to_state = event.get("to", "")
        detail = f"{from_state} → {colorize(to_state, '34')}"

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

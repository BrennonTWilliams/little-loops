"""Rectangular-border guard tests for FSM diagram rendering (layout.py).

These tests assert a structural invariant that snapshot tests do not: every
rendered state box must be a clean rectangle — its left ``│``, right ``│``, and
the ``┌┐└┘`` corners must sit at the same *display* columns (measured with
wcwidth) on every row the box spans.

This directly catches the action-row overflow regression where a box's content
row is wider than its border (BUG: ``_draw_box`` wrote a content line into a
single grid cell without clearing the cells it visually covered). Unlike a
snapshot, it cannot be silenced by ``pytest --snapshot-update``.
"""

from __future__ import annotations

import pytest
from wcwidth import wcswidth, wcwidth

from little_loops.cli.loop.layout import _render_fsm_diagram
from little_loops.cli.output import strip_ansi
from tests.helpers import make_test_fsm, make_test_state

pytestmark = pytest.mark.usefixtures("stable_snapshot_env")

_TL, _TR, _BL, _BR, _VERT = "┌", "┐", "└", "┘", "│"


def _disp_col(s: str, idx: int) -> int:
    """Display column where the character at string index ``idx`` begins."""
    w = wcswidth(s[:idx])
    return w if w >= 0 else idx


def _char_at_col(s: str, col: int) -> str | None:
    """Return the char whose display cell starts at ``col`` (None if none/inside a wide char)."""
    w = 0
    for ch in s:
        if w == col:
            return ch
        cw = wcwidth(ch)
        w += cw if cw > 0 else 1
        if w > col:
            return None
    return None


def _assert_boxes_rectangular(rendered: str) -> None:
    """Assert every ``┌…┐`` box in ``rendered`` closes as an aligned rectangle."""
    lines = [strip_ansi(ln) for ln in rendered.splitlines()]
    n = len(lines)
    boxes_checked = 0
    for r, line in enumerate(lines):
        for ti, ch in enumerate(line):
            if ch != _TL:
                continue
            tri = line.find(_TR, ti)
            if tri == -1:
                continue
            left_col = _disp_col(line, ti)
            right_col = _disp_col(line, tri)
            rr = r + 1
            found_bottom = False
            while rr < n:
                row = lines[rr]
                left_ch = _char_at_col(row, left_col)
                right_ch = _char_at_col(row, right_col)
                if left_ch == _BL:
                    assert right_ch == _BR, (
                        f"Box opened at line {r} (cols {left_col}..{right_col}): "
                        f"bottom-right corner misaligned on line {rr} — expected "
                        f"'┘' at col {right_col}, got {right_ch!r}.\n{row!r}"
                    )
                    found_bottom = True
                    break
                assert left_ch == _VERT, (
                    f"Box opened at line {r} (cols {left_col}..{right_col}): "
                    f"left border misaligned on line {rr} — expected "
                    f"'│' at col {left_col}, got {left_ch!r}.\n{row!r}"
                )
                assert right_ch == _VERT, (
                    f"Box opened at line {r} (cols {left_col}..{right_col}): "
                    f"right border misaligned on line {rr} — expected "
                    f"'│' at col {right_col}, got {right_ch!r}.\n{row!r}"
                )
                rr += 1
            assert found_bottom, (
                f"Box opened at line {r} (cols {left_col}..{right_col}) never closed."
            )
            boxes_checked += 1
    assert boxes_checked > 0, "no boxes were rendered — test FSM produced no diagram"


def test_linear_first_action_line_rectangular() -> None:
    """Default (non-verbose) render shows one action line; box must stay rectangular."""
    fsm = make_test_fsm(
        name="linear-loop",
        initial="start",
        states={
            "start": make_test_state(
                action='echo "this is a fairly long action body line"', on_yes="done"
            ),
            "done": make_test_state(terminal=True),
        },
    )
    _assert_boxes_rectangular(_render_fsm_diagram(fsm))


def test_verbose_multiline_action_rectangular() -> None:
    """Verbose render expands multiple action lines; every box must stay rectangular."""
    fsm = make_test_fsm(
        name="multiline-loop",
        initial="start",
        states={
            "start": make_test_state(
                action='ABS_DIR="${context.run_dir}"\necho "=== HEALTH CHECK ==="\nSNAP=$(probe)',
                on_yes="done",
            ),
            "done": make_test_state(terminal=True),
        },
    )
    _assert_boxes_rectangular(_render_fsm_diagram(fsm, verbose=True))


def test_branching_action_rectangular() -> None:
    """Side-by-side branch boxes with action bodies must each be rectangular."""
    fsm = make_test_fsm(
        name="branch-loop",
        initial="check",
        states={
            "check": make_test_state(action="run-check", on_yes="pass", on_no="fail"),
            "pass": make_test_state(terminal=True),
            "fail": make_test_state(action="echo fail", on_yes="check"),
        },
    )
    _assert_boxes_rectangular(_render_fsm_diagram(fsm))


def test_wide_glyph_action_rectangular() -> None:
    """Action bodies containing double-width (CJK) glyphs must not break alignment."""
    fsm = make_test_fsm(
        name="wide-loop",
        initial="start",
        states={
            "start": make_test_state(action="echo 状態 確認 テスト", on_yes="done"),
            "done": make_test_state(terminal=True),
        },
    )
    _assert_boxes_rectangular(_render_fsm_diagram(fsm, verbose=True))


def test_highlighted_action_rectangular() -> None:
    """A highlighted (active) state's action row must stay rectangular too."""
    fsm = make_test_fsm(
        name="hl-loop",
        initial="start",
        states={
            "start": make_test_state(action='echo "running the active step now"', on_yes="done"),
            "done": make_test_state(terminal=True),
        },
    )
    _assert_boxes_rectangular(_render_fsm_diagram(fsm, verbose=True, highlight_state="start"))


# ---------------------------------------------------------------------------
# BUG-2425 — width bounding for back-edge-heavy FSMs in the non-TTY stream path
# ---------------------------------------------------------------------------


def _make_back_edge_heavy_fsm(n: int = 40) -> object:
    """Build a chain ``s0 → s1 → … → sN`` where every ``s_i`` also has an
    ``on_no`` back-edge to ``s0``, producing ~N distinct back-edges. Unclamped,
    the left gutter grows ~2 cols/back-edge and overflows the terminal width."""
    states = {}
    for i in range(n):
        nxt = f"s{i + 1}" if i < n - 1 else "done"
        states[f"s{i}"] = make_test_state(action=f"echo step {i}", on_yes=nxt, on_no="s0")
    states["done"] = make_test_state(terminal=True)
    return make_test_fsm(name="back-edge-heavy", initial="s0", states=states)


def _max_line_display_width(rendered: str) -> int:
    return max(
        (max(0, wcswidth(strip_ansi(ln))) for ln in rendered.splitlines()),
        default=0,
    )


def _clean_facets() -> object:
    from little_loops.cli.loop.diagram_modes import DiagramFacets

    return DiagramFacets("layered", False, "title", "main", "preset")  # "clean" preset


def test_back_edge_gutter_clamped_to_width(monkeypatch: pytest.MonkeyPatch) -> None:
    """Part 1: the back-edge left gutter is clamped to ``tw // 3`` so state boxes
    are not pushed off the right edge. Unclamped this FSM renders ~100 cols wide
    at tw=80; clamped, no line exceeds tw."""
    tw = 80
    monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: tw)
    fsm = _make_back_edge_heavy_fsm()
    rendered = _render_fsm_diagram(fsm)
    assert _max_line_display_width(rendered) <= tw, (
        f"back-edge gutter unbounded: widest line is "
        f"{_max_line_display_width(rendered)} cols (> {tw})"
    )


def test_streaming_diagram_fits_width(monkeypatch: pytest.MonkeyPatch) -> None:
    """Part 2 (invariant): the non-TTY streaming render never emits a line wider
    than the effective width for a back-edge-heavy FSM."""
    from little_loops.cli.loop._helpers import _render_streaming_diagram

    tw = 80
    monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: tw)
    fsm = _make_back_edge_heavy_fsm()
    rendered = _render_streaming_diagram(
        fsm,
        "s0",
        facets=_clean_facets(),
        highlight_color="32",
        edge_label_colors=None,
        badges=None,
        scope="full",
        cols=tw,
    )
    assert rendered, "streaming render produced no diagram"
    assert _max_line_display_width(rendered) <= tw, (
        f"streaming diagram overflows: widest line is "
        f"{_max_line_display_width(rendered)} cols (> {tw})"
    )


def test_streaming_diagram_degrades_when_too_wide(monkeypatch: pytest.MonkeyPatch) -> None:
    """Part 2 (ladder walk): when the full diagram cannot fit ``cols``, the
    streaming path sheds detail via the ENH-2411 ladder rather than emitting the
    raw full render. A narrow ``cols`` forces degradation."""
    from little_loops.cli.loop._helpers import _render_streaming_diagram

    tw = 80
    monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: tw)
    fsm = _make_back_edge_heavy_fsm(n=8)  # full render ~55 cols; degrades below a 40-col budget
    full = _render_fsm_diagram(fsm, title_only=True, mode="full")
    cols = 40
    assert _max_line_display_width(full) > cols, "precondition: full render wider than target cols"

    rendered = _render_streaming_diagram(
        fsm,
        "s0",
        facets=_clean_facets(),
        highlight_color="32",
        edge_label_colors=None,
        badges=None,
        scope="full",
        cols=cols,
    )
    assert rendered, "streaming render produced no diagram"
    assert _max_line_display_width(rendered) <= cols, (
        f"streaming diagram did not degrade to fit: widest line is "
        f"{_max_line_display_width(rendered)} cols (> {cols})"
    )
    # The degraded render is strictly smaller than the full render it replaced.
    assert _max_line_display_width(rendered) < _max_line_display_width(full)


# ---------------------------------------------------------------------------
# ENH-2442 — windowed rung wired into the streaming path
# ---------------------------------------------------------------------------
#
# The window rung's real geometry couples to ``terminal_width()`` internally
# (its overflow banner and back-edge margins are sized against the live
# terminal, not the caller's ``cols``), so a real-FSM width probe can't
# reliably force "full too wide, window fits" without an oversized fixture.
# These tests instead patch the render primitives ``_render_streaming_diagram``
# dispatches to, isolating the ladder-walk plumbing this issue adds from that
# pre-existing (out-of-scope) geometry coupling.


def test_streaming_diagram_uses_window_rung_when_full_too_wide(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the full render doesn't fit ``cols``, the streaming walk now tries
    the windowed rung (previously unconditionally skipped) before falling to
    the neighborhood view, mirroring the pinned-pane ladder."""
    import little_loops.cli.loop.layout as layout
    from little_loops.cli.loop._helpers import _render_streaming_diagram

    cols = 60
    monkeypatch.setattr(layout, "terminal_width", lambda **_kw: cols)
    monkeypatch.setattr(layout, "_render_fsm_diagram", lambda *a, **kw: "F" * 100)
    captured_kwargs: dict[str, object] = {}

    def fake_windowed(*_args: object, **kwargs: object) -> str:
        captured_kwargs.update(kwargs)
        return "  ▲ 2 layers above  (s0 → s1)\n  │ s3 │\n  ▼ 2 layers below  (s4 → …)"

    monkeypatch.setattr(layout, "_render_windowed_diagram", fake_windowed)

    fsm = _make_back_edge_heavy_fsm(n=6)
    rendered = _render_streaming_diagram(
        fsm,
        "s3",
        facets=_clean_facets(),
        highlight_color="32",
        edge_label_colors=None,
        badges=None,
        scope="full",
        cols=cols,
    )
    assert "layers above" in rendered and "layers below" in rendered, rendered
    # Per-event row budget derived from terminal width (Proposed Solution step 1).
    assert captured_kwargs.get("budget") == max(8, cols // 4)


def test_streaming_diagram_falls_through_when_window_empty(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When the windowed render returns ``""`` (degenerate budget/graph — see
    ``_render_windowed_diagram``'s documented empty-return cases), the
    streaming walk transparently continues to the next rung rather than
    stopping on the empty variant."""
    import little_loops.cli.loop.layout as layout
    from little_loops.cli.loop._helpers import _render_streaming_diagram

    cols = 60
    monkeypatch.setattr(layout, "terminal_width", lambda **_kw: cols)
    monkeypatch.setattr(layout, "_render_fsm_diagram", lambda *a, **kw: "F" * 100)
    monkeypatch.setattr(layout, "_render_windowed_diagram", lambda *a, **kw: "")
    monkeypatch.setattr(
        layout, "_render_neighborhood_diagram", lambda *a, **kw: "NEIGHBORHOOD-MARKER"
    )

    fsm = _make_back_edge_heavy_fsm(n=6)
    rendered = _render_streaming_diagram(
        fsm,
        "s3",
        facets=_clean_facets(),
        highlight_color="32",
        edge_label_colors=None,
        badges=None,
        scope="full",
        cols=cols,
    )
    assert rendered == "NEIGHBORHOOD-MARKER", rendered


def test_streaming_ladder_walk_tries_window_before_neighborhood(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Lock-in test: the streaming rung-call sequence includes ``window``
    immediately after ``full`` and stops there once it fits, so a future
    regression re-introducing the skip guard shows up as a call-order change."""
    import little_loops.cli.loop.layout as layout
    from little_loops.cli.loop._helpers import _render_streaming_diagram

    cols = 60
    calls: list[str] = []
    monkeypatch.setattr(layout, "terminal_width", lambda **_kw: cols)
    monkeypatch.setattr(
        layout, "_render_fsm_diagram", lambda *a, **kw: calls.append("full") or "F" * 100
    )
    monkeypatch.setattr(
        layout, "_render_windowed_diagram", lambda *a, **kw: calls.append("window") or "W" * 10
    )
    monkeypatch.setattr(
        layout,
        "_render_neighborhood_diagram",
        lambda *a, **kw: calls.append("neighborhood") or "N" * 10,
    )

    fsm = _make_back_edge_heavy_fsm(n=6)
    _render_streaming_diagram(
        fsm,
        "s3",
        facets=_clean_facets(),
        highlight_color="32",
        edge_label_colors=None,
        badges=None,
        scope="full",
        cols=cols,
    )
    assert calls == ["full", "window"], calls


def test_streaming_diagram_single_state_window_degenerate_case(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Real (unmocked) degenerate-return contract: a single-state graph makes
    ``_render_windowed_diagram`` return ``""`` (``len(all_states) <= 1``), so
    the streaming walk still resolves to the single-line status floor."""
    from little_loops.cli.loop._helpers import _render_streaming_diagram
    from tests.helpers import make_test_fsm, make_test_state

    cols = 10
    monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: cols)
    fsm = make_test_fsm(initial="only", states={"only": make_test_state(terminal=True)})
    rendered = _render_streaming_diagram(
        fsm,
        "only",
        facets=_clean_facets(),
        highlight_color="32",
        edge_label_colors=None,
        badges=None,
        scope="full",
        cols=cols,
    )
    assert rendered == "fsm: · → [only] → ·", rendered


def test_variant_width_counts_display_columns() -> None:
    """Part 3: ``_variant_width`` measures display columns (wcwidth), not char
    count, so double-width glyphs are sized correctly."""
    from little_loops.cli.loop._helpers import _variant_width

    # Three CJK glyphs → 3 chars but 6 display columns.
    assert _variant_width("状態確") == 6
    # Widest line across a multi-line variant.
    assert _variant_width("ab\n状態確認") == 8


# ---------------------------------------------------------------------------
# Width-aware pinned-path picker + render-layer clamp
# ---------------------------------------------------------------------------
#
# ``--show-diagrams clean`` on a back-edge-heavy FSM used to render the full
# layered diagram even when the layout overflowed terminal width, producing
# connector tails (``───────── ─────┘``) past the visible box edges. Two layers
# of defense close the gap:
#
# 1. ``_choose_pinned_layout`` now filters variants by width before considering
#    height, so a too-wide rung falls through to a smaller one (window /
#    neighborhood / single). The streaming path has done this since BUG-2425;
#    this brings the pinned path in line.
# 2. ``_render_layered_diagram``'s final assembly hard-clamps every output line
#    to ``tw`` display columns (with ``…`` marker), so even an upstream layout
#    miss — forward-skip-layer gutter, post-hoc layer merge, etc. — cannot emit
#    a line wider than the terminal.


def test_pinned_layout_skips_too_wide_variants() -> None:
    """Fix A (direct): ``_choose_pinned_layout`` skips variants whose widest
    line exceeds ``cols`` even when their height fits. The picker used to be
    height-only; the ``clean`` preset's ladder collapses to
    ``[full, window, neighborhood, single]`` when the FSM is too wide, so
    without the width filter the broken ``full`` render was always picked."""
    from little_loops.cli.loop._helpers import _choose_pinned_layout

    too_wide = "X" * 200  # 200-col-wide single-line variant
    fitting = "Y" * 50  # 50-col-wide single-line variant
    rows = 100

    # Without cols: legacy height-only behavior — picks the first variant that
    # fits by height. (Used by the `_variant_width` baseline path.)
    chosen, _ = _choose_pinned_layout(rows, [too_wide, fitting])
    assert chosen is too_wide  # backwards-compat default

    # With cols=100: width filter rejects too_wide, falls through to fitting.
    chosen, _ = _choose_pinned_layout(rows, [too_wide, fitting], cols=100)
    assert chosen is fitting, f"picker should have skipped 200-col variant; chose {chosen[:30]!r}"

    # If every variant is too wide, the picker returns the last (smallest) one
    # — degenerate terminals still get *something* pinned.
    chosen, _ = _choose_pinned_layout(rows, [too_wide, too_wide], cols=80)
    assert chosen is too_wide


def test_pinned_pane_clean_preset_no_overflow(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix A + Fix B end-to-end: with ``--show-diagrams clean`` on a
    back-edge-heavy FSM, the pinned pane fits within terminal width — either
    by degrading to a smaller rung (width filter) or by hard-clamping output
    lines (render-layer clamp)."""
    tw = 100
    monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: tw)
    # Build a real back-edge-heavy FSM — the shape that exposed the original
    # symptom. 12 states is enough to overflow 100 cols without an aggressive
    # clamp; the picker must either filter or the renderer must clamp.
    fsm = _make_back_edge_heavy_fsm(n=12)
    rendered = _render_fsm_diagram(
        fsm,
        highlight_state="s0",
        title_only=True,
        suppress_labels=True,
        mode="main",
    )
    # Fix B invariant: every output line fits within tw display columns.
    assert rendered, "FSM rendered nothing"
    assert _max_line_display_width(rendered) <= tw, (
        f"render-layer clamp failed: widest line is "
        f"{_max_line_display_width(rendered)} cols (> {tw})"
    )
    # And the box geometry is still rectangular (clamp didn't mangle borders).
    _assert_boxes_rectangular(rendered)


def test_render_layered_diagram_output_clamped_to_tw(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Fix B (direct): when the layered layout would produce a grid wider than
    ``tw``, the final assembly hard-clamps every line to ``tw`` display columns
    with a trailing ``…`` marker. The clamp uses ``_display_width`` (wcwidth),
    so double-width glyphs are sized correctly."""
    tw = 60
    monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: tw)
    # A 12-state back-edge-heavy FSM at tw=60 overflows naturally (gutter +
    # boxes > 60). The clamp should kick in on at least one line.
    fsm = _make_back_edge_heavy_fsm(n=12)
    rendered = _render_fsm_diagram(
        fsm,
        highlight_state="s0",
        title_only=True,
        suppress_labels=True,
        mode="full",
    )
    assert rendered, "FSM rendered nothing"
    assert _max_line_display_width(rendered) <= tw, (
        f"clamp failed: widest line is {_max_line_display_width(rendered)} cols (> {tw})"
    )

    # The clamp is only supposed to fire when the layout overflows. With a
    # narrow FSM at a generous tw, no line should be truncated.
    tw_wide = 200
    monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: tw_wide)
    rendered_wide = _render_fsm_diagram(
        fsm,
        highlight_state="s0",
        title_only=True,
        suppress_labels=True,
        mode="full",
    )
    assert rendered_wide, "FSM rendered nothing"
    assert "…" not in rendered_wide, (
        "clamp fired on a diagram that fit within tw=200 — clamp logic is too eager"
    )


# ---------------------------------------------------------------------------
# Regression: terminal-width clamp must preserve ANSI styling
# ---------------------------------------------------------------------------
#
# The user reported that deep FSM box diagrams lost their color halfway down
# the printout. Root cause: ``_render_layered_diagram``'s final hard-clamp
# ran the overflow line through ``strip_ansi`` *and* ``_truncate_to_width``
# (which doesn't understand SGR bytes), so colored box borders / edges /
# arrows were replaced by plain text on every line that exceeded ``tw``.
# Fix: ``_truncate_to_width_ansi`` preserves embedded SGR CSI sequences
# while measuring width by visible columns.


def test_truncate_to_width_ansi_preserves_sgr_codes() -> None:
    """Unit test for :func:`_truncate_to_width_ansi`.

    - Surviving visible chars keep their SGR styling.
    - Width is measured in visible columns (SGR bytes do not consume budget).
    - An SGR open at the cut point is closed with ``\\x1b[0m`` *before* the
      trailing ``…`` so the active style does not leak onto the next line.
    """
    from little_loops.cli.loop.layout import _truncate_to_width_ansi

    # Two colored segments separated by a reset. Each segment is 4 visible
    # columns of ``─``; total visible width = 8 (SGR bytes excluded).
    text = "\x1b[32m────\x1b[0m\x1b[31m────\x1b[0m"
    assert wcswidth(strip_ansi(text)) == 8

    # No truncation needed: input returned verbatim.
    out_no_trunc = _truncate_to_width_ansi(text, 8)
    assert out_no_trunc == text, out_no_trunc

    # Truncate to 6 columns: keep the green segment (4 cols) + 1 col of red
    # + ``…``; the open SGR (red) is closed before ``…``.
    out_trunc = _truncate_to_width_ansi(text, 6)
    assert wcswidth(strip_ansi(out_trunc)) <= 6, strip_ansi(out_trunc)
    assert out_trunc.endswith("\x1b[0m…"), f"open SGR not closed before ellipsis: {out_trunc!r}"
    # The green segment survives intact.
    assert "\x1b[32m────\x1b[0m" in out_trunc, out_trunc
    # The red SGR (open at the cut point) is still in the output so the
    # one surviving red ``─`` renders in red.
    assert "\x1b[31m" in out_trunc, out_trunc

    # Cut right after the green segment closes: ``\x1b[31m`` has been emitted
    # (the open-red SGR) but no red char fits in the budget. The helper must
    # close that open SGR before ``…`` so the active red style does not leak
    # onto whatever the caller prints next.
    out_at_reset = _truncate_to_width_ansi(text, 5)
    assert out_at_reset.endswith("\x1b[0m…"), (
        f"open SGR (\x1b[31m emitted with no following char) not closed: {out_at_reset!r}"
    )
    # And the visible width stays within the budget.
    assert wcswidth(strip_ansi(out_at_reset)) <= 5, strip_ansi(out_at_reset)

    # ``width <= 0`` returns the empty string.
    assert _truncate_to_width_ansi(text, 0) == ""


def test_render_layered_diagram_preserves_color_when_clamping(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """End-to-end regression: at ``tw=60`` a back-edge-heavy FSM triggers
    the hard-clamp on at least one line, and the clamped output must still
    contain SGR styling for box borders / edges / arrows.

    The pre-fix clamp discarded all ANSI from overflowing lines, so deep
    diagrams lost color from the first overflow row downward; this test
    fails on the old code path and passes on the new one.
    """
    from little_loops.cli.output import colorize as real_colorize

    tw = 60
    monkeypatch.setattr("little_loops.cli.loop.layout.terminal_width", lambda **_kw: tw)

    # Force SGR emission regardless of TTY detection.
    def _always_colorize(text: str, code: str) -> str:
        return real_colorize(text, code) if code else text

    # Force color by patching the colorize reference the layout module uses.
    monkeypatch.setattr("little_loops.cli.loop.layout.colorize", _always_colorize)
    # And make sure the global _USE_COLOR is on too (defense in depth).
    monkeypatch.setattr("little_loops.cli.output._USE_COLOR", True)

    fsm = _make_back_edge_heavy_fsm(n=12)
    rendered = _render_fsm_diagram(
        fsm,
        highlight_state="s0",
        title_only=True,
        suppress_labels=True,
        mode="full",
    )
    assert rendered, "FSM rendered nothing"

    # Invariant 1: clamp still caps line widths.
    assert _max_line_display_width(rendered) <= tw, (
        f"clamp failed: widest line is {_max_line_display_width(rendered)} cols (> {tw})"
    )

    # Invariant 2 (the regression): at least one SGR CSI sequence survived
    # the clamp. ``\x1b[`` is the introducer; combined with the trailing
    # parameter byte that defines an SGR (``m``), this catches any styling
    # injected by ``_draw_box`` / per-edge ``_lc`` / label colorization.
    assert "\x1b[" in rendered and "\x1b[" in rendered.replace("\x1b[0m", ""), (
        "clamp stripped all ANSI styling from the rendered diagram — "
        "regression of the 'color lost halfway down' bug"
    )

    # Invariant 3: the clamped line(s) still contain the ellipsis, but the
    # trailing ``…`` is preceded by a reset (when an SGR was open at the
    # cut point) or by a plain char (when no SGR was open). Either way, no
    # truncated line ends with an unclosed SGR introducer.
    for ln in rendered.splitlines():
        if not ln.endswith("…"):
            continue
        # The byte immediately preceding the ellipsis must NOT be the open
        # bracket of an SGR (which would mean we cut mid-sequence).
        assert not ln.endswith("["), f"truncated line ends mid-CSI sequence: {ln!r}"


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])

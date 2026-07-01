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


def test_variant_width_counts_display_columns() -> None:
    """Part 3: ``_variant_width`` measures display columns (wcwidth), not char
    count, so double-width glyphs are sized correctly."""
    from little_loops.cli.loop._helpers import _variant_width

    # Three CJK glyphs → 3 chars but 6 display columns.
    assert _variant_width("状態確") == 6
    # Widest line across a multi-line variant.
    assert _variant_width("ab\n状態確認") == 8


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])

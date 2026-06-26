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


if __name__ == "__main__":  # pragma: no cover
    pytest.main([__file__, "-v"])

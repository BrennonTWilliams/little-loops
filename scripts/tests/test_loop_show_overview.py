"""Tests for the `ll-loop show` state overview table (`_print_state_overview_table`).

Regression coverage for sub-loop rows rendering `—` in both the Type and
Action Preview columns instead of identifying the nested loop.
"""

import io
from contextlib import redirect_stdout

from little_loops.cli.loop.info import _print_state_overview_table
from little_loops.fsm.schema import FSMLoop, StateConfig


def _render(fsm: FSMLoop) -> str:
    buf = io.StringIO()
    with redirect_stdout(buf):
        _print_state_overview_table(fsm)
    return buf.getvalue()


def test_sub_loop_row_shows_type_and_loop_name() -> None:
    """A state with a `loop:` key shows `sub-loop` Type and the loop name."""
    fsm = FSMLoop(
        name="parent",
        initial="delegate",
        states={
            "delegate": StateConfig(loop="child-loop", on_yes="done", on_no="done"),
            "done": StateConfig(terminal=True),
        },
    )

    out = _render(fsm)
    lines = [ln for ln in out.splitlines() if "delegate" in ln]
    assert lines, "expected a row for the sub-loop state"
    row = lines[0]

    # Type column identifies the row as a sub-loop, not `—`.
    assert "sub-loop" in row
    # Action Preview column names the target loop.
    assert "child-loop" in row


def test_shell_row_unaffected() -> None:
    """A plain shell state still renders its action, not sub-loop text."""
    fsm = FSMLoop(
        name="parent",
        initial="run",
        states={
            "run": StateConfig(action="echo hello", on_yes="done", on_no="done"),
            "done": StateConfig(terminal=True),
        },
    )

    out = _render(fsm)
    row = next(
        ln for ln in out.splitlines() if ln.strip().startswith(("→ run", "run")) or "run" in ln
    )
    assert "echo hello" in out
    assert "sub-loop" not in row

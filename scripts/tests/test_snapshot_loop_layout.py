"""Snapshot tests for FSM diagram rendering (layout.py).

Golden files live in scripts/tests/__snapshots__/ and are version-controlled.
To regenerate after an intentional layout change:

    pytest --snapshot-update scripts/tests/test_snapshot_loop_layout.py
"""

from __future__ import annotations

import pytest
from syrupy.assertion import SnapshotAssertion

from tests.helpers import make_test_fsm, make_test_state


@pytest.mark.usefixtures("stable_snapshot_env")
class TestFSMDiagramSnapshot:
    """Snapshot tests for _render_fsm_diagram()."""

    def test_linear_two_state_fsm(self, snapshot: SnapshotAssertion) -> None:
        """Linear start→done chain renders as vertical layout."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = make_test_fsm(
            name="linear-loop",
            initial="start",
            states={
                "start": make_test_state(action="echo start", on_yes="done"),
                "done": make_test_state(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm)
        assert snapshot == result

    def test_branching_three_state_fsm(self, snapshot: SnapshotAssertion) -> None:
        """Branching FSM with yes/no paths renders as layered layout."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = make_test_fsm(
            name="branch-loop",
            initial="check",
            states={
                "check": make_test_state(action="run-check", on_yes="pass", on_no="fail"),
                "pass": make_test_state(terminal=True),
                "fail": make_test_state(action="echo fail", on_yes="check"),
            },
        )
        result = _render_fsm_diagram(fsm)
        assert snapshot == result

    def test_linear_fsm_with_highlight(self, snapshot: SnapshotAssertion) -> None:
        """Highlighted state renders distinctly from non-highlighted states."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = make_test_fsm(
            name="highlight-loop",
            initial="start",
            states={
                "start": make_test_state(action="echo start", on_yes="middle"),
                "middle": make_test_state(action="echo middle", on_yes="done"),
                "done": make_test_state(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm, highlight_state="middle")
        assert snapshot == result

    def test_suppress_labels_mode(self, snapshot: SnapshotAssertion) -> None:
        """suppress_labels=True hides edge transition labels."""
        from little_loops.cli.loop.layout import _render_fsm_diagram

        fsm = make_test_fsm(
            name="no-labels-loop",
            initial="start",
            states={
                "start": make_test_state(action="echo start", on_yes="done", on_no="start"),
                "done": make_test_state(terminal=True),
            },
        )
        result = _render_fsm_diagram(fsm, suppress_labels=True)
        assert snapshot == result

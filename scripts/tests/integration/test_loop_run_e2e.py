"""End-to-end test: a real FSM loop through the executor (finding H2).

Builds a shell-only ``FSMLoop`` and runs it through the real ``FSMExecutor``
with NO mocks — shell actions execute in a real subprocess and routing is
driven by their real exit codes (``evaluate_exit_code``: 0->yes, 1->no). This
exercises the executor's transition/routing core, default (no explicit
``evaluate:``) evaluation, ``next`` loop-back, failure-terminal routing, and a
real emitted filesystem artifact — none of which the mock-heavy unit tests
exercise together.

The state path is captured from the executor's ``state_enter`` events, the
same telemetry ``ll-loop`` renders.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest

pytestmark = pytest.mark.integration


def _run(fsm: Any) -> tuple[Any, list[str]]:
    """Run an FSM for real and return (result, visited_state_path)."""
    from little_loops.fsm.executor import FSMExecutor

    visited: list[str] = []

    def on_event(event: dict[str, Any]) -> None:
        if event.get("event") == "state_enter":
            visited.append(event["state"])

    executor = FSMExecutor(fsm, event_callback=on_event)
    return executor.run(), visited


def _state(**kwargs: Any) -> Any:
    from little_loops.fsm.schema import StateConfig

    return StateConfig(**kwargs)


def _loop(**kwargs: Any) -> Any:
    from little_loops.fsm.schema import FSMLoop

    return FSMLoop(**kwargs)


class TestLoopRunEndToEnd:
    def test_success_path_reaches_done(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """Two passing shell states route forward to the terminal ``done`` state."""
        monkeypatch.chdir(tmp_path)
        fsm = _loop(
            name="happy-path",
            initial="setup",
            states={
                "setup": _state(
                    action="echo setup", action_type="shell", on_yes="verify", on_no="failed"
                ),
                "verify": _state(
                    action="echo verify", action_type="shell", on_yes="done", on_no="failed"
                ),
                "failed": _state(terminal=True),
                "done": _state(terminal=True),
            },
        )
        result, visited = _run(fsm)

        assert result.final_state == "done"
        assert result.terminated_by == "terminal"
        # state_enter is emitted only for executed (non-terminal) states; the
        # reached terminal is reflected in final_state, not the visited path.
        assert visited == ["setup", "verify"]
        assert "failed" not in visited

    def test_failure_path_reaches_failure_terminal(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """A real nonzero exit (``exit 1`` -> verdict ``no``) routes to the failure terminal.

        Gives the failure branch a real post-condition rather than a
        ``does-not-raise`` smoke check (audit finding M2).
        """
        monkeypatch.chdir(tmp_path)
        fsm = _loop(
            name="failure-path",
            initial="check",
            states={
                "check": _state(
                    action="exit 1", action_type="shell", on_yes="done", on_no="failed"
                ),
                "failed": _state(terminal=True),
                "done": _state(terminal=True),
            },
        )
        result, visited = _run(fsm)

        assert result.final_state == "failed"
        assert result.terminated_by == "terminal"
        # Only the single executed state is in the path; the failure terminal is final_state.
        assert visited == ["check"]
        assert "done" not in visited

    def test_repair_loop_creates_artifact_then_converges(
        self, monkeypatch: pytest.MonkeyPatch, tmp_path: Path
    ) -> None:
        """check(absent)->create->check(present)->done, producing a real artifact.

        Exercises on_no routing, a ``next`` loop-back, re-evaluation against the
        now-changed filesystem, and an emitted artifact — the executor running a
        real repair cycle end to end.
        """
        monkeypatch.chdir(tmp_path)
        artifact = tmp_path / "artifact.txt"
        assert not artifact.exists()

        fsm = _loop(
            name="repair-cycle",
            initial="check",
            states={
                # `test -f` exits 1 (verdict no) when absent, 0 (verdict yes) when present.
                "check": _state(
                    action="test -f artifact.txt",
                    action_type="shell",
                    on_yes="done",
                    on_no="create",
                ),
                "create": _state(action="touch artifact.txt", action_type="shell", next="check"),
                "done": _state(terminal=True),
            },
        )
        result, visited = _run(fsm)

        assert result.final_state == "done"
        assert result.terminated_by == "terminal"
        # Real artifact was produced by the repair state.
        assert artifact.exists()
        # The path loops back through `check` after the repair; the second `check`
        # passes and routes to the (terminal, hence un-emitted) `done` state.
        assert visited == ["check", "create", "check"]

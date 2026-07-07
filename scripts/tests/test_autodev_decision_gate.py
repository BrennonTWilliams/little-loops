"""Tests for autodev decision_needed gate at dequeue time (BUG-2513).

BUG-2513: ``decision_needed`` is only consulted downstream of
``refine_current.on_success``. Four of the five exits out of
``refine_current`` (``on_failure``, ``on_error``, ``on_no``,
``on_rate_limit_exhausted``) advance the queue without consulting the flag,
so a dequeued issue with ``decision_needed: true`` re-enters the queue and
is re-refined indefinitely without ``/ll:decide-issue`` ever running.

The fix adds a ``check_decision_at_dequeue`` state between
``dequeue_next.on_yes`` and ``refine_current`` that short-circuits straight
to ``run_decide`` when ``decision_needed: true`` — making the decision gate
independent of the sub-loop's outcome.

These tests exercise the routing shape with both structural YAML assertions
and a small FSMExecutor-driven run that confirms the gate fires before
``refine_current`` is reached.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

AUTODEV_LOOP_PATH = (
    Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"
)


def _load_autodev_yaml() -> dict[str, Any]:
    assert AUTODEV_LOOP_PATH.exists(), f"Loop file not found: {AUTODEV_LOOP_PATH}"
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())


class _StubRunner:
    """Minimal ActionRunner for FSMExecutor routing tests.

    Returns canned results keyed by action-substring so tests can assert
    state ordering without invoking real shell/subprocess actions. Mirrors
    the shape of ``MockActionRunner`` from ``test_fsm_executor.py`` but is
    intentionally local to keep this test file self-contained.
    """

    def __init__(self, results: list[tuple[str, dict[str, Any]]] | None = None) -> None:
        self._results = results or []
        self.calls: list[str] = []

    def run(
        self,
        action: str,
        timeout: int,
        is_slash_command: bool,
        **kwargs: Any,
    ) -> Any:
        from little_loops.fsm.executor import ActionResult

        del timeout, is_slash_command, kwargs
        self.calls.append(action)
        for pattern, payload in self._results:
            if pattern in action or pattern == action:
                return ActionResult(
                    output=payload.get("output", ""),
                    stderr=payload.get("stderr", ""),
                    exit_code=payload.get("exit_code", 0),
                    duration_ms=payload.get("duration_ms", 1),
                )
        return ActionResult(output="", stderr="", exit_code=0, duration_ms=1)


def _state(**kwargs: Any) -> Any:
    from little_loops.fsm.schema import StateConfig

    return StateConfig(**kwargs)


def _loop(**kwargs: Any) -> Any:
    from little_loops.fsm.schema import FSMLoop

    return FSMLoop(**kwargs)


def _run_decision_chain(
    fsm: Any, action_runner: Any
) -> tuple[Any, list[str]]:
    """Run a minimal autodev-shaped FSM and return (result, visited path)."""
    from little_loops.fsm.executor import FSMExecutor

    visited: list[str] = []

    def on_event(event: dict[str, Any]) -> None:
        if event.get("event") == "state_enter":
            visited.append(event["state"])

    executor = FSMExecutor(fsm, action_runner=action_runner, event_callback=on_event)
    return executor.run(), visited


class TestCheckDecisionAtDequeueStructural:
    """Structural assertions on autodev.yaml routing shape."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_check_decision_at_dequeue_state_exists(self, data: dict[str, Any]) -> None:
        """BUG-2513: a check_decision_at_dequeue state must exist in autodev.yaml."""
        states = data.get("states", {})
        assert "check_decision_at_dequeue" in states, (
            "check_decision_at_dequeue state missing from autodev.yaml — "
            "BUG-2513: decision_needed gate must be checked on first dequeue, "
            "before refine_current runs"
        )

    def test_check_decision_at_dequeue_uses_check_flag_predicate(
        self, data: dict[str, Any]
    ) -> None:
        """The state must call ``ll-issues check-flag <id> decision_needed``."""
        state = data["states"]["check_decision_at_dequeue"]
        action = state.get("action", "")
        assert "ll-issues check-flag" in action, (
            f"check_decision_at_dequeue.action must call 'll-issues check-flag', "
            f"got {action!r}"
        )
        assert "decision_needed" in action, (
            f"check_decision_at_dequeue.action must check the decision_needed "
            f"frontmatter field, got {action!r}"
        )

    def test_check_decision_at_dequeue_uses_shell_exit_fragment(
        self, data: dict[str, Any]
    ) -> None:
        """The state must use ``shell_exit`` fragment to route on exit code."""
        state = data["states"]["check_decision_at_dequeue"]
        assert state.get("fragment") == "shell_exit", (
            f"check_decision_at_dequeue.fragment should be 'shell_exit', "
            f"got {state.get('fragment')!r}"
        )

    def test_check_decision_at_dequeue_on_yes_routes_to_run_decide(
        self, data: dict[str, Any]
    ) -> None:
        """decision_needed=true must route directly to run_decide."""
        state = data["states"]["check_decision_at_dequeue"]
        assert state.get("on_yes") == "run_decide", (
            f"check_decision_at_dequeue.on_yes should be 'run_decide' "
            f"(BUG-2513: bypass-loop fix), got {state.get('on_yes')!r}"
        )

    def test_check_decision_at_dequeue_on_no_routes_to_refine_current(
        self, data: dict[str, Any]
    ) -> None:
        """decision_needed=false (or absent) must route to refine_current."""
        state = data["states"]["check_decision_at_dequeue"]
        assert state.get("on_no") == "refine_current", (
            f"check_decision_at_dequeue.on_no should be 'refine_current', "
            f"got {state.get('on_no')!r}"
        )

    def test_check_decision_at_dequeue_on_error_routes_to_refine_current(
        self, data: dict[str, Any]
    ) -> None:
        """An ll-issues error (e.g. issue missing) must fall through to refine_current
        rather than blocking the queue — same fail-open semantics as
        check_decision_after_refine.on_error."""
        state = data["states"]["check_decision_at_dequeue"]
        assert state.get("on_error") == "refine_current", (
            f"check_decision_at_dequeue.on_error should be 'refine_current' "
            f"(fail-open), got {state.get('on_error')!r}"
        )

    def test_dequeue_next_routes_to_check_decision_at_dequeue(
        self, data: dict[str, Any]
    ) -> None:
        """dequeue_next.on_yes must route to check_decision_at_dequeue
        (not directly to refine_current) so the gate fires on every dequeue."""
        state = data["states"]["dequeue_next"]
        assert state.get("on_yes") == "check_decision_at_dequeue", (
            f"dequeue_next.on_yes should be 'check_decision_at_dequeue' "
            f"(BUG-2513: gate must intercept every dequeue), "
            f"got {state.get('on_yes')!r}"
        )


class TestCheckDecisionAtDequeueRouting:
    """FSMExecutor-driven assertions on the new gate's routing."""

    @pytest.fixture
    def decision_chain_fsm(self) -> Any:
        """Minimal autodev-shaped FSM: dequeue_next → check_decision_at_dequeue
        → run_decide (on_yes) | refine_current (on_no / on_error)."""
        return _loop(
            name="autodev-decision-gate-mini",
            initial="dequeue_next",
            states={
                "dequeue_next": _state(
                    action="echo BUG-2501",
                    action_type="shell",
                    on_yes="check_decision_at_dequeue",
                    on_no="done",
                    on_error="done",
                ),
                "check_decision_at_dequeue": _state(
                    action="ll-issues check-flag BUG-2501 decision_needed",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="run_decide",
                    on_no="refine_current",
                    on_error="refine_current",
                ),
                "run_decide": _state(action="true", action_type="shell", next="done"),
                "refine_current": _state(action="true", action_type="shell", next="done"),
                "done": _state(terminal=True),
            },
        )

    def test_decision_needed_true_routes_run_decide_before_refine_current(
        self, decision_chain_fsm: Any
    ) -> None:
        """BUG-2513: when decision_needed=true, run_decide is reached
        before refine_current — the bypass loop is closed."""
        runner = _StubRunner(results=[("ll-issues check-flag", {"exit_code": 0})])

        result, visited = _run_decision_chain(decision_chain_fsm, runner)

        assert "run_decide" in visited, (
            f"run_decide must be entered for decision_needed=true; "
            f"visited={visited!r}"
        )
        assert "refine_current" not in visited, (
            f"refine_current must NOT be entered for decision_needed=true "
            f"(BUG-2513: gate must short-circuit before refine); "
            f"visited={visited!r}"
        )
        # Order: run_decide must precede refine_current (which must be absent).
        assert visited.index("run_decide") < (
            visited.index("refine_current") if "refine_current" in visited else len(visited)
        )

    def test_decision_needed_false_routes_to_refine_current(
        self, decision_chain_fsm: Any
    ) -> None:
        """When decision_needed=false (or absent), the gate falls through to
        refine_current — no behavioral change for non-decision issues."""
        runner = _StubRunner(results=[("ll-issues check-flag", {"exit_code": 1})])

        result, visited = _run_decision_chain(decision_chain_fsm, runner)

        assert "refine_current" in visited, (
            f"refine_current must be entered when decision_needed=false; "
            f"visited={visited!r}"
        )
        assert "run_decide" not in visited, (
            f"run_decide must NOT be entered when decision_needed=false; "
            f"visited={visited!r}"
        )

    def test_check_flag_error_falls_through_to_refine_current(
        self, decision_chain_fsm: Any
    ) -> None:
        """If ll-issues check-flag errors (e.g. issue missing), the gate
        fail-opens to refine_current rather than blocking the queue."""
        runner = _StubRunner(
            results=[("ll-issues check-flag", {"exit_code": 2, "stderr": "issue not found"})]
        )

        result, visited = _run_decision_chain(decision_chain_fsm, runner)

        assert "refine_current" in visited, (
            f"refine_current must be entered on check-flag error (fail-open); "
            f"visited={visited!r}"
        )
        assert "run_decide" not in visited, (
            f"run_decide must NOT be entered on check-flag error; "
            f"visited={visited!r}"
        )


class TestAutodevValidatesAfterFix:
    """FSM schema validation on autodev.yaml post-fix."""

    def test_autodev_yaml_loads_and_validates(self) -> None:
        """load_and_validate must succeed on autodev.yaml — no schema errors
        (covers Implementation Step 4: ``ll-loop validate autodev`` exits 0)."""
        from little_loops.fsm.validation import (
            ValidationSeverity,
            load_and_validate,
        )

        fsm, errors = load_and_validate(AUTODEV_LOOP_PATH)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, (
            f"autodev.yaml has validation errors after BUG-2513 fix: "
            f"{[str(e) for e in error_list]}"
        )
        # The new gate must be present after validation.
        assert "check_decision_at_dequeue" in fsm.states, (
            "check_decision_at_dequeue state not present after load_and_validate"
        )

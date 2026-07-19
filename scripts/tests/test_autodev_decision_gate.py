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

AUTODEV_LOOP_PATH = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"


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


def _run_decision_chain(fsm: Any, action_runner: Any) -> tuple[Any, list[str]]:
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
            f"check_decision_at_dequeue.action must call 'll-issues check-flag', got {action!r}"
        )
        assert "decision_needed" in action, (
            f"check_decision_at_dequeue.action must check the decision_needed "
            f"frontmatter field, got {action!r}"
        )

    def test_check_decision_at_dequeue_uses_shell_exit_fragment(self, data: dict[str, Any]) -> None:
        """The state must use ``shell_exit`` fragment to route on exit code."""
        state = data["states"]["check_decision_at_dequeue"]
        assert state.get("fragment") == "shell_exit", (
            f"check_decision_at_dequeue.fragment should be 'shell_exit', "
            f"got {state.get('fragment')!r}"
        )

    def test_check_decision_at_dequeue_on_yes_routes_to_check_decision_decidable(
        self, data: dict[str, Any]
    ) -> None:
        """decision_needed=true must route through check_decision_decidable so the
        deposit_options detour gets one bounded attempt before run_decide fires
        (BUG-2605: the fast path previously skipped the detour entirely)."""
        state = data["states"]["check_decision_at_dequeue"]
        assert state.get("on_yes") == "check_decision_decidable", (
            f"check_decision_at_dequeue.on_yes should be 'check_decision_decidable' "
            f"(BUG-2605: route through the deposit-options detour), "
            f"got {state.get('on_yes')!r}"
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

    def test_dequeue_next_routes_to_check_decision_at_dequeue(self, data: dict[str, Any]) -> None:
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
            f"run_decide must be entered for decision_needed=true; visited={visited!r}"
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

    def test_decision_needed_false_routes_to_refine_current(self, decision_chain_fsm: Any) -> None:
        """When decision_needed=false (or absent), the gate falls through to
        refine_current — no behavioral change for non-decision issues."""
        runner = _StubRunner(results=[("ll-issues check-flag", {"exit_code": 1})])

        result, visited = _run_decision_chain(decision_chain_fsm, runner)

        assert "refine_current" in visited, (
            f"refine_current must be entered when decision_needed=false; visited={visited!r}"
        )
        assert "run_decide" not in visited, (
            f"run_decide must NOT be entered when decision_needed=false; visited={visited!r}"
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
            f"refine_current must be entered on check-flag error (fail-open); visited={visited!r}"
        )
        assert "run_decide" not in visited, (
            f"run_decide must NOT be entered on check-flag error; visited={visited!r}"
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
            f"autodev.yaml has validation errors after BUG-2513 fix: {[str(e) for e in error_list]}"
        )
        # The new gate must be present after validation.
        assert "check_decision_at_dequeue" in fsm.states, (
            "check_decision_at_dequeue state not present after load_and_validate"
        )


class TestCheckDecisionBeforeSizeReviewStructural:
    """BUG-2519: structural assertions on the pre-size-review decision gate.

    Mirrors ``TestCheckDecisionAtDequeueStructural`` (lines 101-184) for the
    sibling gate. Most fields are covered in ``test_builtin_loops.py``; only
    the new ``on_error`` assertion is unique to this class.
    """

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_check_decision_before_size_review_state_exists(self, data: dict[str, Any]) -> None:
        """``check_decision_before_size_review`` must exist in autodev.yaml
        (BUG-1277 origin; BUG-2519 preserves it as defense-in-depth)."""
        states = data.get("states", {})
        assert "check_decision_before_size_review" in states, (
            "check_decision_before_size_review state missing from autodev.yaml — "
            "BUG-2519: pre-size-review decision gate must remain for flags added "
            "during refine"
        )

    def test_check_decision_before_size_review_uses_check_flag_predicate(
        self, data: dict[str, Any]
    ) -> None:
        """The state must call ``ll-issues check-flag <id> decision_needed``."""
        state = data["states"]["check_decision_before_size_review"]
        action = state.get("action", "")
        assert "ll-issues check-flag" in action, (
            f"check_decision_before_size_review.action must call 'll-issues check-flag', "
            f"got {action!r}"
        )
        assert "decision_needed" in action, (
            f"check_decision_before_size_review.action must check the decision_needed "
            f"frontmatter field, got {action!r}"
        )

    def test_check_decision_before_size_review_uses_shell_exit_fragment(
        self, data: dict[str, Any]
    ) -> None:
        """The state must use ``shell_exit`` fragment to route on exit code."""
        state = data["states"]["check_decision_before_size_review"]
        assert state.get("fragment") == "shell_exit", (
            f"check_decision_before_size_review.fragment should be 'shell_exit', "
            f"got {state.get('fragment')!r}"
        )

    def test_check_decision_before_size_review_on_yes_routes_to_check_decision_decidable(
        self, data: dict[str, Any]
    ) -> None:
        """decision_needed=true must route through check_decision_decidable so the
        deposit_options detour gets one bounded attempt before run_decide fires
        (BUG-2605)."""
        state = data["states"]["check_decision_before_size_review"]
        assert state.get("on_yes") == "check_decision_decidable", (
            f"check_decision_before_size_review.on_yes should be 'check_decision_decidable', "
            f"got {state.get('on_yes')!r}"
        )

    def test_check_decision_before_size_review_on_no_routes_to_run_size_review(
        self, data: dict[str, Any]
    ) -> None:
        """decision_needed=false (or absent) must route to run_size_review."""
        state = data["states"]["check_decision_before_size_review"]
        assert state.get("on_no") == "run_size_review", (
            f"check_decision_before_size_review.on_no should be 'run_size_review', "
            f"got {state.get('on_no')!r}"
        )

    def test_check_decision_before_size_review_on_error_routes_to_run_size_review(
        self, data: dict[str, Any]
    ) -> None:
        """BUG-2519 (Option B fix): ``ll-issues check-flag`` exit_code 2 (e.g. issue
        missing) must fall through to ``run_size_review`` rather than dead-ending the
        FSM. Mirrors the sibling ``check_decision_after_refine.on_error: check_passed``
        precedent at autodev.yaml:173."""
        state = data["states"]["check_decision_before_size_review"]
        assert state.get("on_error") == "run_size_review", (
            f"check_decision_before_size_review.on_error should be 'run_size_review' "
            f"(BUG-2519: close latent dead-end), got {state.get('on_error')!r}"
        )


class TestSpikeTriageStructural:
    """ENH-2640: structural assertions on the spike-remediation triad
    (check_spike_needed / run_spike / rerun_confidence_after_spike).

    Mirrors ``TestCheckDecisionBeforeSizeReviewStructural`` for the sibling gate
    introduced by the triage_outcome_failure spike-branch routing.
    """

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_spike_states_exist(self, data: dict[str, Any]) -> None:
        states = data.get("states", {})
        for name in ("check_spike_needed", "run_spike", "rerun_confidence_after_spike"):
            assert name in states, f"{name} state missing from autodev.yaml (ENH-2640)"

    def test_check_spike_needed_predicate_reads_both_flags(self, data: dict[str, Any]) -> None:
        """Predicate must be spike_needed AND NOT spike_attempted (two-field one-shot)."""
        action = data["states"]["check_spike_needed"].get("action", "")
        assert "spike_needed" in action, "check_spike_needed must read spike_needed"
        assert "spike_attempted" in action, (
            "check_spike_needed must read spike_attempted for the one-shot guard"
        )
        assert data["states"]["check_spike_needed"].get("fragment") == "shell_exit"

    def test_check_spike_needed_routing(self, data: dict[str, Any]) -> None:
        state = data["states"]["check_spike_needed"]
        assert state.get("on_yes") == "run_spike"
        assert state.get("on_no") == "check_missing_artifacts"
        assert state.get("on_error") == "check_missing_artifacts"

    def test_run_spike_invokes_spike_skill(self, data: dict[str, Any]) -> None:
        state = data["states"]["run_spike"]
        assert "/ll:spike" in state.get("action", "")
        assert "--auto" in state.get("action", "")
        assert state.get("action_type") == "slash_command"
        assert state.get("fragment") == "with_rate_limit_handling"
        assert state.get("next") == "rerun_confidence_after_spike"
        assert state.get("on_error") == "rerun_confidence_after_spike"
        assert state.get("on_rate_limit_exhausted") == "done"

    def test_rerun_confidence_after_spike_routing(self, data: dict[str, Any]) -> None:
        state = data["states"]["rerun_confidence_after_spike"]
        assert "/ll:confidence-check" in state.get("action", "")
        assert state.get("fragment") == "with_rate_limit_handling"
        assert state.get("next") == "enqueue_or_skip"
        assert state.get("on_error") == "enqueue_or_skip"
        assert state.get("on_rate_limit_exhausted") == "done"


class TestDecidePathSpikeGate:
    """BUG-2654: the decide/size-review skip path must give a pending spike its
    one shot at run_spike before writing low_readiness.

    ENH-2640 wired check_spike_needed only onto triage_outcome_failure.on_no.
    An issue routed down the decide path (or the no-decide size-review path)
    funnels through enqueue_or_skip → recheck_after_size_review and skips as
    low_readiness without ever visiting the spike gate. This gate closes that
    class by interposing check_spike_needed_before_skip on enqueue_or_skip.on_no.
    """

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_gate_state_exists(self, data: dict[str, Any]) -> None:
        assert "check_spike_needed_before_skip" in data.get("states", {}), (
            "check_spike_needed_before_skip missing from autodev.yaml (BUG-2654)"
        )

    def test_enqueue_or_skip_routes_to_spike_gate(self, data: dict[str, Any]) -> None:
        """The no-children skip edge must reach the spike gate, not skip directly."""
        state = data["states"]["enqueue_or_skip"]
        assert state.get("on_no") == "check_spike_needed_before_skip", (
            "enqueue_or_skip.on_no must route through the spike gate before "
            "recheck_after_size_review (BUG-2654)"
        )

    def test_gate_predicate_reads_both_flags(self, data: dict[str, Any]) -> None:
        """Predicate must be spike_needed AND NOT spike_attempted (one-shot)."""
        state = data["states"]["check_spike_needed_before_skip"]
        action = state.get("action", "")
        assert "spike_needed" in action
        assert "spike_attempted" in action, (
            "gate must read spike_attempted for the one-shot guard (AC 2)"
        )
        assert state.get("fragment") == "shell_exit"

    def test_gate_routing(self, data: dict[str, Any]) -> None:
        state = data["states"]["check_spike_needed_before_skip"]
        assert state.get("on_yes") == "run_spike", "spike match must reach run_spike (AC 1)"
        # No-match must preserve the leaf-skip regression (AC 3). ENH-2689 routes
        # the on_no edge through check_reconcile_needed (a pass-through for
        # non-plateau issues) before the low_readiness write; on_error still skips
        # straight to recheck_after_size_review.
        assert state.get("on_no") == "check_reconcile_needed", (
            "ENH-2689: no-match routes through check_reconcile_needed before the "
            "low_readiness skip (AC 3 preserved via its recheck_after_size_review fall-through)"
        )
        assert state.get("on_error") == "recheck_after_size_review"


class TestReconcilePlateauStructural:
    """ENH-2689: structural assertions on the post-spike reconcile plateau triad
    (check_reconcile_needed / reconcile_current / rerun_confidence_after_reconcile).

    Mirrors TestDecidePathSpikeGate for the sibling gate that catches a
    "spike ran but Readiness is bit-identical" plateau and routes one
    /ll:reconcile-issue pass before the low_readiness deferral.
    """

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_reconcile_states_exist(self, data: dict[str, Any]) -> None:
        states = data.get("states", {})
        for name in (
            "check_reconcile_needed",
            "reconcile_current",
            "rerun_confidence_after_reconcile",
        ):
            assert name in states, f"{name} missing from autodev.yaml (ENH-2689)"

    def test_spike_gate_routes_to_reconcile_gate(self, data: dict[str, Any]) -> None:
        """check_spike_needed_before_skip.on_no now interposes the reconcile gate."""
        state = data["states"]["check_spike_needed_before_skip"]
        assert state.get("on_no") == "check_reconcile_needed"

    def test_reconcile_predicate_reads_snapshot_and_guard(self, data: dict[str, Any]) -> None:
        """Predicate: pre-spike snapshot == current Readiness AND NOT reconcile_attempted."""
        state = data["states"]["check_reconcile_needed"]
        action = state.get("action", "")
        assert state.get("fragment") == "shell_exit"
        assert "autodev-pre-spike-readiness.txt" in action
        assert "confidence_score" in action
        assert "reconcile_attempted" in action, (
            "reconcile gate must read reconcile_attempted for the one-shot guard (AC 3)"
        )

    def test_reconcile_gate_routing(self, data: dict[str, Any]) -> None:
        state = data["states"]["check_reconcile_needed"]
        assert state.get("on_yes") == "reconcile_current", "plateau must reach reconcile (AC 1)"
        # Non-plateau / error must preserve the leaf-skip (AC 4).
        assert state.get("on_no") == "recheck_after_size_review"
        assert state.get("on_error") == "recheck_after_size_review"

    def test_reconcile_current_invokes_skill(self, data: dict[str, Any]) -> None:
        state = data["states"]["reconcile_current"]
        assert "/ll:reconcile-issue" in state.get("action", "")
        assert state.get("action_type") == "slash_command"
        assert state.get("next") == "rerun_confidence_after_reconcile"
        assert state.get("on_error") == "rerun_confidence_after_reconcile"
        assert state.get("on_rate_limit_exhausted") == "done"

    def test_rerun_confidence_after_reconcile_routing(self, data: dict[str, Any]) -> None:
        state = data["states"]["rerun_confidence_after_reconcile"]
        assert "/ll:confidence-check" in state.get("action", "")
        assert state.get("next") == "recheck_after_size_review"
        assert state.get("on_error") == "recheck_after_size_review"


class TestReconcilePlateauRouting:
    """ENH-2689: FSMExecutor-driven assertions on the reconcile gate routing.

    Mirrors TestCheckDecisionAtDequeueRouting's mini-FSM shape: the gate must
    fire reconcile_current on a plateau (exit 0) and fall through to
    recheck_after_size_review when there is no plateau (exit 1) or on error.
    """

    @pytest.fixture
    def reconcile_chain_fsm(self) -> Any:
        return _loop(
            name="autodev-reconcile-gate-mini",
            initial="check_spike_needed_before_skip",
            states={
                "check_spike_needed_before_skip": _state(
                    action="false",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="run_spike",
                    on_no="check_reconcile_needed",
                    on_error="recheck_after_size_review",
                ),
                "check_reconcile_needed": _state(
                    action="reconcile-predicate",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="reconcile_current",
                    on_no="recheck_after_size_review",
                    on_error="recheck_after_size_review",
                ),
                "run_spike": _state(action="true", action_type="shell", next="done"),
                "reconcile_current": _state(action="true", action_type="shell", next="done"),
                "recheck_after_size_review": _state(
                    action="true", action_type="shell", next="done"
                ),
                "done": _state(terminal=True),
            },
        )

    def test_plateau_routes_to_reconcile(self, reconcile_chain_fsm: Any) -> None:
        """Snapshot == current AND not attempted (exit 0) → reconcile_current fires
        before any low_readiness deferral."""
        runner = _StubRunner(
            results=[
                ("false", {"exit_code": 1}),
                ("reconcile-predicate", {"exit_code": 0}),
            ]
        )
        _result, visited = _run_decision_chain(reconcile_chain_fsm, runner)
        assert "reconcile_current" in visited, f"visited={visited!r}"
        assert "recheck_after_size_review" not in visited, (
            f"reconcile must precede (and here replace) the skip; visited={visited!r}"
        )

    def test_no_plateau_falls_through_to_recheck(self, reconcile_chain_fsm: Any) -> None:
        """No plateau (exit 1) → recheck_after_size_review, reconcile skipped (AC 4)."""
        runner = _StubRunner(
            results=[
                ("false", {"exit_code": 1}),
                ("reconcile-predicate", {"exit_code": 1}),
            ]
        )
        _result, visited = _run_decision_chain(reconcile_chain_fsm, runner)
        assert "recheck_after_size_review" in visited, f"visited={visited!r}"
        assert "reconcile_current" not in visited, f"visited={visited!r}"

    def test_predicate_error_falls_through_to_recheck(self, reconcile_chain_fsm: Any) -> None:
        """Predicate error (exit 2) fail-opens to recheck_after_size_review."""
        runner = _StubRunner(
            results=[
                ("false", {"exit_code": 1}),
                ("reconcile-predicate", {"exit_code": 2, "stderr": "boom"}),
            ]
        )
        _result, visited = _run_decision_chain(reconcile_chain_fsm, runner)
        assert "recheck_after_size_review" in visited, f"visited={visited!r}"
        assert "reconcile_current" not in visited, f"visited={visited!r}"


class TestCheckDecisionBeforeSizeReviewRouting:
    """BUG-2519: FSMExecutor-driven assertion on the gate's error-fallthrough.

    Drives ``recheck_scores.on_error → check_decision_before_size_review`` with
    a check-flag error exit_code, and asserts ``run_size_review`` is reached
    (not ``run_decide``) — closing the latent dead-end at the FSM-execution
    layer, not just the YAML-shape layer.
    """

    @pytest.fixture
    def size_review_chain_fsm(self) -> Any:
        """Minimal autodev-shaped FSM: recheck_scores → check_decision_before_size_review
        → run_decide (on_yes) | run_size_review (on_no / on_error).

        Mirrors the decision_chain_fsm fixture from BUG-2513 but anchored on the
        pre-size-review path.
        """
        return _loop(
            name="autodev-size-review-decision-gate-mini",
            initial="recheck_scores",
            states={
                "recheck_scores": _state(
                    action="ll-issues check-readiness BUG-2501 --readiness 85 --outcome 75",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="decide_current",
                    on_no="check_decision_before_size_review",
                    on_error="check_decision_before_size_review",
                ),
                "check_decision_before_size_review": _state(
                    action="ll-issues check-flag BUG-2501 decision_needed",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="run_decide",
                    on_no="run_size_review",
                    on_error="run_size_review",
                ),
                "decide_current": _state(action="true", action_type="shell", next="done"),
                "run_decide": _state(action="true", action_type="shell", next="done"),
                "run_size_review": _state(action="true", action_type="shell", next="done"),
                "done": _state(terminal=True),
            },
        )

    def test_check_flag_error_falls_through_to_run_size_review(
        self, size_review_chain_fsm: Any
    ) -> None:
        """BUG-2519: When recheck_scores.on_error routes into
        check_decision_before_size_review AND check-flag exits with code 2
        (issue not found), the FSM must reach run_size_review rather than
        dead-ending — proving the new on_error route closes the silent
        termination defect at the executor layer."""
        runner = _StubRunner(
            results=[
                ("ll-issues check-readiness", {"exit_code": 2, "stderr": "issue not found"}),
                ("ll-issues check-flag", {"exit_code": 2, "stderr": "issue not found"}),
            ]
        )

        result, visited = _run_decision_chain(size_review_chain_fsm, runner)

        assert "run_size_review" in visited, (
            f"run_size_review must be reached on check-flag error (BUG-2519: "
            f"close latent dead-end); visited={visited!r}"
        )
        assert "run_decide" not in visited, (
            f"run_decide must NOT be reached when decision_needed is unknown due "
            f"to check-flag error; visited={visited!r}"
        )


class TestAssertDecisionClearedStructural:
    """BUG-2595: structural assertions on the post-decide decision-gate re-check.

    Mirrors ``TestCheckDecisionAtDequeueStructural`` for the new
    ``assert_decision_cleared`` state, which sits between ``recheck_after_decide``
    (score-only gate) and ``implement_current`` so a silent ``decide-issue``
    no-op (BUG-1416) cannot leak a still-gated issue into implementation.
    """

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_recheck_after_decide_on_yes_routes_to_assert_decision_cleared(
        self, data: dict[str, Any]
    ) -> None:
        """BUG-2595: recheck_after_decide.on_yes must no longer go straight to
        implement_current — it must be re-verified by assert_decision_cleared first."""
        state = data["states"]["recheck_after_decide"]
        assert state.get("on_yes") == "assert_decision_cleared", (
            f"recheck_after_decide.on_yes should be 'assert_decision_cleared' "
            f"(BUG-2595: score pass alone does not prove decision_needed was "
            f"cleared), got {state.get('on_yes')!r}"
        )

    def test_assert_decision_cleared_state_exists(self, data: dict[str, Any]) -> None:
        states = data.get("states", {})
        assert "assert_decision_cleared" in states, (
            "assert_decision_cleared state missing from autodev.yaml — BUG-2595"
        )

    def test_assert_decision_cleared_uses_check_flag_predicate(self, data: dict[str, Any]) -> None:
        state = data["states"]["assert_decision_cleared"]
        action = state.get("action", "")
        assert "ll-issues check-flag" in action, (
            f"assert_decision_cleared.action must call 'll-issues check-flag', got {action!r}"
        )
        assert "decision_needed" in action, (
            f"assert_decision_cleared.action must check decision_needed, got {action!r}"
        )

    def test_assert_decision_cleared_uses_shell_exit_fragment(self, data: dict[str, Any]) -> None:
        state = data["states"]["assert_decision_cleared"]
        assert state.get("fragment") == "shell_exit", (
            f"assert_decision_cleared.fragment should be 'shell_exit', got {state.get('fragment')!r}"
        )

    def test_assert_decision_cleared_on_yes_routes_to_record_decision_unresolved(
        self, data: dict[str, Any]
    ) -> None:
        """decision_needed still true (check-flag exit 0) means decide-issue no-op'd
        → must NOT proceed to implement_current."""
        state = data["states"]["assert_decision_cleared"]
        assert state.get("on_yes") == "record_decision_unresolved", (
            f"assert_decision_cleared.on_yes should be 'record_decision_unresolved', "
            f"got {state.get('on_yes')!r}"
        )

    def test_assert_decision_cleared_on_no_routes_to_implement_current(
        self, data: dict[str, Any]
    ) -> None:
        """decision_needed cleared (check-flag exit 1) → safe to implement."""
        state = data["states"]["assert_decision_cleared"]
        assert state.get("on_no") == "implement_current", (
            f"assert_decision_cleared.on_no should be 'implement_current', "
            f"got {state.get('on_no')!r}"
        )

    def test_assert_decision_cleared_on_error_fails_open_to_implement_current(
        self, data: dict[str, Any]
    ) -> None:
        """A check-flag error (e.g. transient issue-lookup failure) must not
        strand the issue — fail open to implement_current like the sibling
        pre-decide gates do for their downstream target."""
        state = data["states"]["assert_decision_cleared"]
        assert state.get("on_error") == "implement_current", (
            f"assert_decision_cleared.on_error should be 'implement_current', "
            f"got {state.get('on_error')!r}"
        )

    def test_record_decision_unresolved_advances_queue_without_failing(
        self, data: dict[str, Any]
    ) -> None:
        """record_decision_unresolved records the issue distinctly (mirrors
        mark_gate_blocked) and returns to dequeue_next so the queue keeps
        draining rather than crashing the run."""
        state = data["states"].get("record_decision_unresolved", {})
        action = state.get("action", "")
        assert "autodev-decision-unresolved.txt" in action, (
            "record_decision_unresolved should record the issue to autodev-decision-unresolved.txt"
        )
        assert "/ll:decide-issue" in action, (
            "record_decision_unresolved should point the operator at /ll:decide-issue"
        )
        assert state.get("next") == "dequeue_next"

    def test_record_decision_unresolved_defers_via_set_status(self, data: dict[str, Any]) -> None:
        """ENH-2666: record_decision_unresolved aligns to rn-implement's mark_deferred
        model — stamps an automation deferral instead of leaving the issue open."""
        action = data["states"].get("record_decision_unresolved", {}).get("action", "")
        assert "ll-issues set-status" in action and "deferred" in action
        assert "--by automation" in action
        assert "--reason decision_unresolved" in action


class TestAssertDecisionClearedRouting:
    """BUG-2595: FSMExecutor-driven assertions on the new gate's routing."""

    @pytest.fixture
    def post_decide_chain_fsm(self) -> Any:
        """Minimal autodev-shaped FSM: recheck_after_decide → assert_decision_cleared
        → record_decision_unresolved (on_yes) | implement_current (on_no/on_error)."""
        return _loop(
            name="autodev-post-decide-gate-mini",
            initial="recheck_after_decide",
            states={
                "recheck_after_decide": _state(
                    action="ll-issues check-readiness BUG-2588 --readiness 90 --outcome 75",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="assert_decision_cleared",
                    on_no="done",
                    on_error="done",
                ),
                "assert_decision_cleared": _state(
                    action="ll-issues check-flag BUG-2588 decision_needed",
                    action_type="shell",
                    fragment_name="shell_exit",
                    on_yes="record_decision_unresolved",
                    on_no="implement_current",
                    on_error="implement_current",
                ),
                "record_decision_unresolved": _state(
                    action="echo BUG-2588 >> decision-unresolved.txt", next="done"
                ),
                "implement_current": _state(action="true", action_type="shell", next="done"),
                "done": _state(terminal=True),
            },
        )

    def test_decision_still_armed_routes_to_record_decision_unresolved_not_implement(
        self, post_decide_chain_fsm: Any
    ) -> None:
        """BUG-2595: scores pass but decision_needed is still true (silent
        decide-issue no-op) — must route to record_decision_unresolved, never
        implement_current."""
        runner = _StubRunner(
            results=[
                ("ll-issues check-readiness", {"exit_code": 0}),
                ("ll-issues check-flag", {"exit_code": 0}),
            ]
        )

        result, visited = _run_decision_chain(post_decide_chain_fsm, runner)

        assert "record_decision_unresolved" in visited, (
            f"record_decision_unresolved must be entered when decision_needed is "
            f"still true; visited={visited!r}"
        )
        assert "implement_current" not in visited, (
            f"implement_current must NOT be entered when decision_needed is still "
            f"true (BUG-2595: guaranteed-halt path); visited={visited!r}"
        )

    def test_decision_cleared_routes_to_implement_current(self, post_decide_chain_fsm: Any) -> None:
        """decision_needed cleared (check-flag exit 1) — the happy path — must
        still reach implement_current unchanged."""
        runner = _StubRunner(
            results=[
                ("ll-issues check-readiness", {"exit_code": 0}),
                ("ll-issues check-flag", {"exit_code": 1}),
            ]
        )

        result, visited = _run_decision_chain(post_decide_chain_fsm, runner)

        assert "implement_current" in visited, (
            f"implement_current must be entered when decision_needed is cleared; "
            f"visited={visited!r}"
        )
        assert "record_decision_unresolved" not in visited, (
            f"record_decision_unresolved must NOT be entered when decision_needed "
            f"is cleared; visited={visited!r}"
        )

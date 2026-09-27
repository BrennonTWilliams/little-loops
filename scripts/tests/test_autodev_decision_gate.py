"""Tests for autodev's decision routing (BUG-2513, reworked by ENH-3610 and ENH-3623).

ENH-3623: autodev's second-pass preparation ladder -- including the
``select_obligation_*`` selectors that re-entered the child on ``decision_needed``,
``record_reentry_exhausted``, the reconcile plateau, and the design-gate refine
remedy -- moved into ``loops/prepare-issue.yaml``, whose every decision lives in
``little_loops.preparation_policy.decide`` (table-tested in
``test_preparation_policy.py``). This file keeps the stays-deleted guards for the
decision entry points earlier issues removed from autodev, autodev's handoff edges
around ``refine_current``, and the refine-to-ready-issue child's decision contract.

ENH-3610: autodev never resolves a decision itself. The refine-to-ready-issue child
owns resolution (``check_decision_before_done``).

BUG-2513 (legacy record): ``decision_needed`` was only consulted downstream of
``refine_current.on_success``, so four of its five exits re-queued a flagged issue
without ``/ll:decide-issue`` ever running.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

AUTODEV_LOOP_PATH = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"
PREPARE_ISSUE_LOOP_PATH = AUTODEV_LOOP_PATH.parent / "prepare-issue.yaml"


def _load_autodev_yaml() -> dict[str, Any]:
    assert AUTODEV_LOOP_PATH.exists(), f"Loop file not found: {AUTODEV_LOOP_PATH}"
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())


_DECISION_STATES_REMOVED = (
    "check_decision_at_dequeue",
    "resolve_decision_at_dequeue",
    "mark_decide_ran_at_dequeue",
    "check_decision_after_refine",
    "decide_current",
    "check_decision_before_size_review",
    "triage_outcome_failure",
    "resolve_decision_direct",
)

#: ENH-3611 (commit 2): the 22 autodev spike/decision states removed; the
#: refine-to-ready-issue child owns spike and decision repair.
_SPIKE_STATES_REMOVED = (
    "check_spike_needed",
    "run_spike",
    "count_repair_cycle_spike",
    "route_spike_verdict",
    "check_spike_budget",
    "record_spike_inconclusive",
    "mark_spike_no_verdict_infra",
    "rerun_confidence_after_spike",
    "clear_scores_before_spike",
    "check_scores_present_spike",
    "check_spike_needed_before_skip",
    "resolve_decision",
    "mark_decide_ran",
    "rerun_confidence_after_decide",
    "clear_scores_before_decide",
    "check_scores_present_decide",
    "recheck_after_decide",
    "check_rearmed_spike_after_decide",
    "check_decide_rate_limited",
    "record_decision_unresolved",
    "snap_and_size_review",
    "check_proof_gate_before_implement",
)

#: ENH-3615: the nine wire / atomic / reconcile rescoring-triplet states, replaced by
#: the shared clear_scores -> rerun_confidence -> check_scores_present ->
#: route_after_rescore chain.
_RESCORE_TRIPLET_STATES_REMOVED = (
    "clear_scores_before_wire",
    "rerun_confidence_after_wire",
    "check_scores_present_wire",
    "clear_scores_before_atomic",
    "rerun_confidence_after_atomic_remediation",
    "check_scores_present_atomic",
    "clear_scores_before_reconcile",
    "rerun_confidence_after_reconcile",
    "check_scores_present_reconcile",
)


class TestRemovedDecisionEntryPoints:
    """ENH-3610: autodev's eight decision entry states stay deleted (pattern:
    ``TestAssertDecisionClearedStructural``) and no edge targets them."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    @pytest.mark.parametrize("state", _DECISION_STATES_REMOVED)
    def test_state_stays_deleted(self, data: dict[str, Any], state: str) -> None:
        assert state not in data["states"], (
            f"{state} was removed by ENH-3610 — autodev never resolves a decision itself; "
            "the refine-to-ready-issue child owns resolution"
        )

    def test_no_edge_targets_a_removed_state(self, data: dict[str, Any]) -> None:
        dangling: list[str] = []
        for name, state in data["states"].items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            for target in targets:
                if target in _DECISION_STATES_REMOVED:
                    dangling.append(f"{name} -> {target}")
        assert not dangling, dangling

    def test_no_state_calls_the_resolve_decision_oracle(self, data: dict[str, Any]) -> None:
        """ENH-3611: resolve_decision (the last oracle caller) is gone; no autodev
        state runs oracles/resolve-decision or /ll:spike."""
        callers = [
            n for n, s in data["states"].items() if s.get("loop") == "oracles/resolve-decision"
        ]
        assert callers == []
        spikers = [
            n
            for n, s in data["states"].items()
            if s.get("action_type") == "slash_command"
            and (s.get("action") or "").startswith("/ll:spike")
        ]
        assert spikers == []

    def test_spike_states_stay_deleted(self, data: dict[str, Any]) -> None:
        assert len(_SPIKE_STATES_REMOVED) == 22
        assert [n for n in _SPIKE_STATES_REMOVED if n in data["states"]] == []

    def test_no_edge_targets_a_removed_spike_state(self, data: dict[str, Any]) -> None:
        dangling: list[str] = []
        for name, state in data["states"].items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            for target in targets:
                if target in _SPIKE_STATES_REMOVED:
                    dangling.append(f"{name} -> {target}")
        assert not dangling, dangling

    @pytest.mark.parametrize("state", _RESCORE_TRIPLET_STATES_REMOVED)
    def test_rescore_triplet_state_stays_deleted(self, data: dict[str, Any], state: str) -> None:
        assert state not in data["states"]

    def test_no_edge_targets_a_removed_rescore_triplet_state(self, data: dict[str, Any]) -> None:
        dangling: list[str] = []
        for name, state in data["states"].items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            for target in targets:
                if target in _RESCORE_TRIPLET_STATES_REMOVED:
                    dangling.append(f"{name} -> {target}")
        assert not dangling, dangling

    def test_rate_limit_exhaustion_halts_through_finalize(self, data: dict[str, Any]) -> None:
        """ENH-3615, re-homed by ENH-3623: size-review exhaustion never drops the issue
        silently via dequeue_next. run_size_review now lives in prepare-issue, whose
        mark_rate_limited writes RETRYABLE_ERROR:rate_limited; autodev halts on it."""
        prepare = yaml.safe_load(PREPARE_ISSUE_LOOP_PATH.read_text())["states"]
        assert prepare["run_size_review"]["on_rate_limit_exhausted"] == "mark_rate_limited"
        route = data["states"]["route_refine_outcome"]["route"]
        assert route["RETRYABLE_ERROR:rate_limited"] == "finalize_rate_limited"

    def test_dequeue_routes_through_status_then_blockers(self, data: dict[str, Any]) -> None:
        state = data["states"]["check_status_at_dequeue"]
        assert state["on_no"] == "check_blockers_at_dequeue"
        assert state["on_error"] == "check_blockers_at_dequeue"

    def test_autodev_yaml_loads_and_validates(self) -> None:
        from little_loops.fsm.validation import ValidationSeverity, load_and_validate

        fsm, errors = load_and_validate(AUTODEV_LOOP_PATH)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, [str(e) for e in error_list]
        # ENH-3623: the obligation selectors and record_reentry_exhausted moved into
        # the preparation policy; refine_current dispatches the prepare-issue loop.
        for state in (
            "select_obligation_post_refine",
            "select_obligation_pre_implement",
            "record_reentry_exhausted",
        ):
            assert state not in fsm.states
        assert fsm.states["refine_current"].loop == "prepare-issue"


class TestRefineHandoffStructural:
    """ENH-3623: autodev's edges around the prepare-issue sub-loop."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_refine_current_success_copies_broke_down_first(self, data: dict[str, Any]) -> None:
        state = data["states"]["refine_current"]
        assert state["on_success"] == "copy_broke_down"
        assert data["states"]["copy_broke_down"]["next"] == "route_refine_success"

    def test_check_passed_edges(self, data: dict[str, Any]) -> None:
        """A passing gate goes straight to the proof gate (the policy's pre_implement
        already enforced decision/proof re-entry); a failing one skips the issue."""
        state = data["states"]["check_passed"]
        assert state["on_yes"] == "check_proof_defer_or_implement"
        assert state["on_no"] == "skip_inflight"
        assert state["on_cannot_judge"] == "skip_inflight"
        assert state["on_error"] == "skip_inflight_infra"

    def test_detect_children_falls_through_to_parent_resolved(self, data: dict[str, Any]) -> None:
        states = data["states"]
        assert states["detect_children"]["on_no"] == "check_parent_resolved"
        assert states["detect_children"]["on_error"] == "check_parent_resolved"
        assert states["check_parent_resolved"]["on_no"] == "skip_inflight"
        assert states["check_parent_resolved"]["on_error"] == "skip_inflight_infra"

    def test_route_refine_success_fallthroughs_retarget_to_check_passed(
        self, data: dict[str, Any]
    ) -> None:
        route = data["states"]["route_refine_success"]["route"]
        for token in ("READY", "BLOCKED", "MISSING", "_", "_error"):
            assert route[token] == "check_passed"


class TestChildDecisionInvariant:
    """ENH-3610: refine-to-ready-issue never reaches ``done`` with decision_needed set,
    except through write_broke_down."""

    @pytest.fixture
    def child(self) -> dict[str, Any]:
        path = AUTODEV_LOOP_PATH.parent / "refine-to-ready-issue.yaml"
        return yaml.safe_load(path.read_text())["states"]

    def test_done_edges_pass_through_decision_gate(self, child: dict[str, Any]) -> None:
        assert child["check_missing_artifacts"]["on_yes"] == "check_decision_before_done"
        # ENH-3604: the score gates collapsed into the route_score_obligation dispatch.
        assert child["route_score_obligation"]["route"]["NONE"] == "check_decision_before_done"

    def test_only_gate_write_done_record_and_class_writers_reach_done(
        self, child: dict[str, Any]
    ) -> None:
        inbound = set()
        for name, state in child.items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            if "done" in targets:
                inbound.add(name)
        # write_broke_down is the documented exception; the rest are class-writing stops.
        assert "write_done_record" in inbound
        assert "write_broke_down" in inbound
        for name in ("route_score_obligation", "check_missing_artifacts"):
            assert name not in inbound

    def test_decision_gate_routes(self, child: dict[str, Any]) -> None:
        gate = child["check_decision_before_done"]
        assert "check-flag" in gate["action"] and "decision_needed" in gate["action"]
        assert gate["on_yes"] == "check_decide_attempts"
        # ENH-3611: the proof gate sits between the decision gate and the done record.
        assert gate["on_no"] == "check_proof_before_done"
        assert gate["on_error"] == "check_proof_before_done"
        proof = child["check_proof_before_done"]
        assert proof["on_yes"] == "run_spike"
        assert proof["on_no"] == "write_done_record"
        assert proof["on_error"] == "write_done_record"

    def test_run_record_write_moved_to_write_done_record(self, child: dict[str, Any]) -> None:
        assert "run-record write" in child["write_done_record"]["action"]
        assert child["write_done_record"]["next"] == "done"
        for name in ("route_score_obligation", "check_missing_artifacts"):
            assert "run-record write" not in child[name]["action"], name


class TestSpikeTriageStructural:
    """ENH-2640, moved by ENH-3611: the spike-remediation triad now lives in the
    refine-to-ready-issue child; autodev has none of it (stays-deleted guards)."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    @pytest.fixture
    def child(self) -> dict[str, Any]:
        path = AUTODEV_LOOP_PATH.parent / "refine-to-ready-issue.yaml"
        return yaml.safe_load(path.read_text())["states"]

    def test_spike_states_removed_from_autodev(self, data: dict[str, Any]) -> None:
        states = data.get("states", {})
        for name in ("check_spike_needed", "run_spike", "rerun_confidence_after_spike"):
            assert name not in states, f"{name} was removed from autodev by ENH-3611"

    def test_child_owns_spike_states(self, child: dict[str, Any]) -> None:
        for name in ("check_spike_needed", "run_spike", "route_spike_verdict"):
            assert name in child, f"{name} missing from refine-to-ready-issue.yaml"

    def test_child_check_spike_needed_predicate_reads_both_flags(
        self, child: dict[str, Any]
    ) -> None:
        """Predicate must be spike_needed AND NOT spike_attempted (two-field one-shot)."""
        action = child["check_spike_needed"].get("action", "")
        assert "spike_needed" in action
        assert "spike_attempted" in action
        assert child["check_spike_needed"]["on_no"] == "check_missing_artifacts"

    def test_child_run_spike_invokes_spike_skill(self, child: dict[str, Any]) -> None:
        state = child["run_spike"]
        assert "/ll:spike" in state.get("action", "")
        assert "--auto" in state.get("action", "")
        assert state.get("action_type") == "slash_command"
        assert state.get("fragment") == "with_rate_limit_handling"


class TestDecidePathSpikeGate:
    """BUG-2654, reworked by ENH-3611/ENH-3623: the post-size-review skip edge is
    protected by the preparation policy's ``post_size_review`` (PROOF re-entry into the
    child) instead of autodev's own check_spike_needed_before_skip, which is gone."""

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    def test_old_gate_stays_deleted(self, data: dict[str, Any]) -> None:
        assert "check_spike_needed_before_skip" not in data.get("states", {})


class TestAssertDecisionClearedStructural:
    """BUG-2595 / ENH-3075 / ENH-3611: the post-decide decision-gate re-check
    (``assert_decision_cleared``) lives in ``oracles/resolve-decision.yaml`` and the
    caller-side chain (``recheck_after_decide``, ``record_decision_unresolved``) was
    removed from ``autodev.yaml`` by ENH-3611 — the refine-to-ready-issue child owns
    decision repair (``check_decision_before_done``). This class guards the removals
    and the child-side contract that replaced them.
    """

    @pytest.fixture
    def data(self) -> dict[str, Any]:
        return _load_autodev_yaml()

    @pytest.fixture
    def child(self) -> dict[str, Any]:
        path = AUTODEV_LOOP_PATH.parent / "refine-to-ready-issue.yaml"
        return yaml.safe_load(path.read_text())["states"]

    def test_recheck_after_decide_stays_deleted(self, data: dict[str, Any]) -> None:
        """ENH-3611: recheck_after_decide (and its ENH-3075 on_yes retarget) is gone."""
        assert "recheck_after_decide" not in data["states"]

    def test_assert_decision_cleared_absent_from_autodev_states(self, data: dict[str, Any]) -> None:
        """ENH-3075: assert_decision_cleared moved into
        oracles/resolve-decision.yaml and must leave no dangling reference or
        stale definition behind in autodev.yaml's own states block."""
        states = data.get("states", {})
        assert "assert_decision_cleared" not in states, (
            "assert_decision_cleared must be deleted from autodev.yaml's states "
            "block — it now lives in oracles/resolve-decision.yaml (ENH-3075)"
        )
        for name, state in states.items():
            for edge in ("on_yes", "on_no", "on_error", "on_success", "on_failure", "next"):
                assert state.get(edge) != "assert_decision_cleared", (
                    f"{name}.{edge} still references deleted state "
                    "assert_decision_cleared (ENH-3075)"
                )

    def test_record_decision_unresolved_stays_deleted_from_autodev(
        self, data: dict[str, Any]
    ) -> None:
        """ENH-3611: autodev's record_decision_unresolved is gone; ENH-3623: the
        surviving decision deferral is ``prep apply`` (decision_exhausted), whose
        BLOCKED:decision_unresolved record autodev routes to ledger_child_stop."""
        assert "record_decision_unresolved" not in data["states"]
        route = data["states"]["route_refine_outcome"]["route"]
        assert route["BLOCKED:decision_unresolved"] == "ledger_child_stop"

    def test_child_record_decision_unresolved_advances_and_defers(
        self, child: dict[str, Any]
    ) -> None:
        """The child's record_decision_unresolved keeps the old autodev contract:
        ledger to autodev-decision-unresolved.txt (ENH-2666 deferral via set-status)
        and stop, so autodev sees BLOCKED:decision_unresolved."""
        state = child["record_decision_unresolved"]
        action = state["action"]
        assert "autodev-decision-unresolved.txt" in action
        assert "/ll:decide-issue" in action
        assert "ll-issues set-status" in action and "deferred" in action
        assert "--by automation" in action
        assert "--reason decision_unresolved" in action
        assert state["next"] == "failed"


# ENH-2717's check_decision_after_decide_error is deleted (ENH-3075): its
# short-circuit collapses into oracles/resolve-decision.yaml's
# assert_decision_cleared, which every run_decide exit path (success or
# error) now reaches directly. The 5 routing assertions that used to live in
# TestCheckDecisionAfterDecideErrorStructural are replaced by
# test_run_decide_on_error_routes_to_assert_decision_cleared in
# TestResolveDecisionOracle (test_builtin_loops.py), modeled on
# test_run_decide_and_assert_decision_cleared_routing /
# test_assert_decision_cleared_terminal_contract in that same test class.


class TestAssertDecisionClearedRouting:
    """BUG-2595, re-rooted by ENH-3611/ENH-3623: a still-armed decision flag must never
    reach implement_current. The preparation policy's ``pre_implement`` re-enters the
    child on ``decision_needed`` (``test_preparation_policy.py``); this class pins the
    invariant on autodev's real routing table."""

    def test_implement_current_only_reached_via_proof_defer_state(self) -> None:
        states = _load_autodev_yaml()["states"]
        preds = set()
        for name, state in states.items():
            targets = [v for k, v in state.items() if k.startswith("on_") or k == "next"]
            targets += list((state.get("route") or {}).values())
            if "implement_current" in targets:
                preds.add(name)
        assert preds == {"check_proof_defer_or_implement"}

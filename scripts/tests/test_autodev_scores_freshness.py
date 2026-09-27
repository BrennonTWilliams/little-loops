"""Tests for BUG-3588: post-repair rescoring must gate on fresh scores.

ENH-3615 gave autodev one shared rescoring chain (``clear_scores`` ->
``rerun_confidence`` -> ``check_scores_present`` -> ``route_after_rescore``);
ENH-3623 moved it into the prepare-issue dispatch loop, where it is a ``RESCORE``
step of ``little_loops.preparation_policy``: the first attempt carries the
``clear_scores`` precondition, an absent score retries once and then stops
``scores_absent`` (``RETRYABLE_ERROR:infra``), and the return address is the done
fact before it. Those rules are table-tested in ``test_preparation_policy.py``
(``test_rescore_retry_then_scores_absent``, ``test_rescore_dispatch_by_origin``,
``test_either_score_missing_counts_as_absent``) and the precondition in
``test_preparation_policy_writers.py``. This file pins that the autodev-side chain
stays deleted, and the child-loop half of the guarantee.

ENH-3611 removed autodev's ``decide`` and ``spike`` triplets; that freshness
guarantee lives in the refine-to-ready-issue child (``route_spike_verdict``
``PROVEN`` -> ``confidence_check``, whose ``on_failure`` is
``mark_evidence_absent_infra``), pinned by ``TestChildSpikeRescoringFreshness``.
"""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
import yaml

AUTODEV_LOOP_PATH = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"


@pytest.fixture(scope="module")
def states() -> dict[str, Any]:
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())["states"]


class TestRoutingStructure:
    @pytest.mark.parametrize("key", ["decide", "spike"])
    def test_decide_and_spike_triplets_stay_deleted(self, states: dict[str, Any], key: str) -> None:
        """ENH-3611: autodev's decide/spike rescoring triplets moved to the child."""
        for prefix in ("clear_scores_before_", "check_scores_present_"):
            assert f"{prefix}{key}" not in states
        assert f"rerun_confidence_after_{key}" not in states
        assert "recheck_after_decide" not in states

    @pytest.mark.parametrize(
        "state",
        [
            "clear_scores",
            "rerun_confidence",
            "check_scores_present",
            "route_after_rescore",
            "mark_scores_absent_infra",
        ],
    )
    def test_shared_chain_moved_to_the_policy(self, states: dict[str, Any], state: str) -> None:
        """ENH-3623: the shared rescoring chain is a RESCORE policy step now."""
        assert state not in states

    def test_absent_scores_at_the_implement_gate_skip_not_implement(
        self, states: dict[str, Any]
    ) -> None:
        """check-readiness exit 3 (scores absent) never reaches implement_current."""
        assert states["check_passed"]["fragment"] == "harness_exit"
        assert states["check_passed"]["on_cannot_judge"] == "skip_inflight"


class TestChildSpikeRescoringFreshness:
    """BUG-3588 freshness for the spike path, now in refine-to-ready-issue (ENH-3611)."""

    @pytest.fixture(scope="class")
    def child(self) -> dict[str, Any]:
        path = AUTODEV_LOOP_PATH.parent / "refine-to-ready-issue.yaml"
        return yaml.safe_load(path.read_text())["states"]

    def test_proven_spike_rescores_through_confidence_check(self, child: dict[str, Any]) -> None:
        assert child["route_spike_verdict"]["route"]["PROVEN"] == "confidence_check"

    def test_missing_scores_after_rescore_are_infra(self, child: dict[str, Any]) -> None:
        cc = child["confidence_check"]
        assert cc["on_success"] == "route_score_obligation"
        assert cc["on_failure"] == "mark_evidence_absent_infra"
        assert cc["on_error"] == "mark_evidence_absent_infra"

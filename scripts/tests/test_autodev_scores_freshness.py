"""Tests for BUG-3588: autodev post-repair rescoring must gate on fresh scores.

The wire, atomic-remediation and reconcile repair origins share one rescoring
chain (ENH-3615): ``clear_scores`` (clear stale scores) -> ``rerun_confidence``
-> ``check_scores_present`` (retry once, then infra) -> ``route_after_rescore``,
which dispatches on the ``autodev-rescore-origin-<ID>`` marker each origin writes.
A rescoring that writes nothing can never pass on pre-repair scores nor surface
as a ``low_readiness`` quality deferral.

ENH-3611 removed autodev's ``decide`` and ``spike`` triplets; that freshness
guarantee now lives in the refine-to-ready-issue child (``route_spike_verdict``
``PROVEN`` -> ``confidence_check``, whose ``on_failure`` is
``mark_evidence_absent_infra``), pinned by ``TestChildSpikeRescoringFreshness``.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
import tempfile
from pathlib import Path
from typing import Any

import pytest
import yaml

AUTODEV_LOOP_PATH = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"

# origin -> successor of the shared chain (route_after_rescore's route target)
ORIGINS = {
    "wire": "enqueue_or_skip",
    "atomic": "regate_after_atomic_remediation",
    "reconcile": "recheck_after_size_review",
}
_ROUTE_TOKENS = {"wire": "WIRE", "atomic": "ATOMIC", "reconcile": "RECONCILE"}


@pytest.fixture(scope="module")
def states() -> dict[str, Any]:
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())["states"]


class TestRoutingStructure:
    def test_clear_then_rerun(self, states: dict[str, Any]) -> None:
        clear = states["clear_scores"]
        assert "set-scores" in clear["action"] and "--clear" in clear["action"]
        assert clear["next"] == "rerun_confidence"
        assert clear["on_error"] == "mark_scores_absent_infra"

    def test_rerun_routes_through_presence_gate(self, states: dict[str, Any]) -> None:
        state = states["rerun_confidence"]
        assert state["next"] == "check_scores_present"
        assert state["on_error"] == "check_scores_present"
        assert state["on_rate_limit_exhausted"] == "finalize_rate_limited"
        assert state["pruning_profile"]["name"] == "confidence-check-recheck"

    def test_presence_gate_routing(self, states: dict[str, Any]) -> None:
        gate = states["check_scores_present"]
        assert gate["fragment"] == "harness_exit"
        assert gate["on_yes"] == "route_after_rescore"
        # First miss retries the rescoring itself (scores are already absent).
        assert gate["on_no"] == "rerun_confidence"
        assert gate["on_cannot_judge"] == "mark_scores_absent_infra"
        assert gate["on_error"] == "mark_scores_absent_infra"

    def test_route_after_rescore_dispatches_per_origin(self, states: dict[str, Any]) -> None:
        state = states["route_after_rescore"]
        assert state["evaluate"]["type"] == "classify"
        for origin, successor in ORIGINS.items():
            assert state["route"][_ROUTE_TOKENS[origin]] == successor
        assert state["route"]["_"] == "mark_scores_absent_infra"
        assert state["route"]["_error"] == "mark_scores_absent_infra"

    def test_repair_predecessors_target_shared_chain(self, states: dict[str, Any]) -> None:
        assert states["run_refine"]["next"] == "clear_scores"
        assert states["run_refine"]["on_error"] == "clear_scores"
        assert states["remediate_oversized_atomic"]["next"] == "mark_rescore_origin_atomic"
        assert states["remediate_oversized_atomic"]["on_error"] == "mark_rescore_origin_atomic"
        assert states["mark_rescore_origin_atomic"]["next"] == "clear_scores"
        assert states["mark_rescore_origin_atomic"]["on_error"] == "mark_scores_absent_infra"
        for pred in (
            "count_repair_cycle_wire",
            "count_repair_cycle_reconcile",
            "count_repair_cycle_refine_for_design",
        ):
            assert pred in states
        for pred in ("count_repair_cycle_reconcile", "count_repair_cycle_refine_for_design"):
            assert states[pred]["next"] == "clear_scores"
            assert states[pred]["on_error"] == "clear_scores"

    @pytest.mark.parametrize(
        ("state", "origin"),
        [
            ("count_repair_cycle_wire", "wire"),
            ("count_repair_cycle_reconcile", "reconcile"),
            ("count_repair_cycle_refine_for_design", "reconcile"),
            ("mark_rescore_origin_atomic", "atomic"),
        ],
    )
    def test_entry_writes_origin_marker(
        self, states: dict[str, Any], tmp_path: Path, state: str, origin: str
    ) -> None:
        result = _run_action(states[state]["action"], tmp_path, {})
        assert result.returncode == 0, result.stderr
        assert (tmp_path / "autodev-rescore-origin-BUG-1").read_text() == origin

    def test_exactly_one_shared_chain(self, states: dict[str, Any]) -> None:
        for name in (
            "clear_scores",
            "rerun_confidence",
            "check_scores_present",
            "route_after_rescore",
        ):
            assert name in states
        for prefix in ("clear_scores_before_", "rerun_confidence_after_", "check_scores_present_"):
            assert not [n for n in states if n.startswith(prefix)]

    def test_infra_state_is_distinct_and_does_not_defer(self, states: dict[str, Any]) -> None:
        action = states["mark_scores_absent_infra"]["action"]
        assert "autodev-scores-absent.txt" in action
        assert "autodev-gate-infra.txt" not in action
        assert "[SCORES_ABSENT]" in action
        assert "autodev-inflight" in action
        assert "set-status" not in action
        assert states["mark_scores_absent_infra"]["next"] == "dequeue_next"

    def test_dequeue_next_clears_retry_markers(self, states: dict[str, Any]) -> None:
        action = states["dequeue_next"]["action"]
        assert "autodev-rescore-retry-" in action
        assert "autodev-rescore-origin-$CURRENT" in action

    @pytest.mark.parametrize(
        ("state", "exit3_target"),
        [
            # Post-sub-loop sites: absence is legitimate (breakdown before
            # scoring) — keep the pre-existing route so detect_children is reached.
            ("check_passed", "select_obligation_post_refine"),
            ("recheck_scores", "run_size_review"),
            ("recheck_after_size_review", "mark_scores_absent_infra"),
            ("regate_after_atomic_remediation", "mark_scores_absent_infra"),
        ],
    )
    def test_readiness_readers_route_exit_3(
        self, states: dict[str, Any], state: str, exit3_target: str
    ) -> None:
        assert states[state]["fragment"] == "harness_exit"
        assert states[state]["on_cannot_judge"] == exit3_target

    @pytest.mark.parametrize("key", ["decide", "spike"])
    def test_decide_and_spike_triplets_stay_deleted(self, states: dict[str, Any], key: str) -> None:
        """ENH-3611: autodev's decide/spike rescoring triplets moved to the child."""
        for prefix in ("clear_scores_before_", "check_scores_present_"):
            assert f"{prefix}{key}" not in states
        assert f"rerun_confidence_after_{key}" not in states
        assert "recheck_after_decide" not in states

    def test_check_passed_still_reaches_detect_children_on_error(
        self, states: dict[str, Any]
    ) -> None:
        assert states["check_passed"]["on_error"] == "detect_children"


def _interpolate(action: str, run_dir: Path, issue_id: str = "BUG-1") -> str:
    """Resolve the FSM ${...} placeholders the shell actions use."""
    subs = {
        "context.run_dir": str(run_dir),
        "captured.input.output:shell": issue_id,
        "captured.input.output": issue_id,
        "context.readiness_threshold:shell": "85",
        "context.outcome_threshold:shell": "65",
    }
    return re.sub(r"\$\{([^}]+)\}", lambda m: subs[m.group(1)], action)


def _run_action(
    action: str, run_dir: Path, issue: dict[str, Any], *, status: str = "open"
) -> subprocess.CompletedProcess[str]:
    """Run a real state action under bash against a stub `ll-issues` whose
    `show --json` reflects `issue` and whose `check-design` passes."""
    payload = json.dumps({"status": status, "decision_needed": "false", **issue})
    with tempfile.TemporaryDirectory() as tmp:
        stub = Path(tmp) / "ll-issues"
        stub.write_text(
            "#!/bin/sh\n"
            'case "$1" in\n'
            f"  show) cat <<'JSON'\n{payload}\nJSON\n;;\n"
            "  check-design) exit 0;;\n"
            '  path) echo "/nonexistent/issue.md";;\n'
            "  *) exit 0;;\n"
            "esac\n"
        )
        stub.chmod(0o755)
        env = {**os.environ, "PATH": f"{tmp}{os.pathsep}{os.environ['PATH']}"}
        return subprocess.run(
            ["bash", "-c", _interpolate(action, run_dir)],
            capture_output=True,
            text=True,
            check=False,
            env=env,
        )


def _seed_origin(run_dir: Path, origin: str, issue_id: str = "BUG-1") -> None:
    (run_dir / f"autodev-rescore-origin-{issue_id}").write_text(origin)


class TestPresenceGateBehavior:
    @pytest.mark.parametrize("origin", ORIGINS)
    def test_scores_present_passes(
        self, states: dict[str, Any], tmp_path: Path, origin: str
    ) -> None:
        _seed_origin(tmp_path, origin)
        action = states["check_scores_present"]["action"]
        result = _run_action(action, tmp_path, {"confidence": "90", "outcome": "70"})
        assert result.returncode == 0

    @pytest.mark.parametrize("origin", ORIGINS)
    def test_first_miss_retries_second_miss_is_infra(
        self, states: dict[str, Any], tmp_path: Path, origin: str
    ) -> None:
        _seed_origin(tmp_path, origin)
        action = states["check_scores_present"]["action"]
        absent = {"confidence": None, "outcome": None}
        assert _run_action(action, tmp_path, absent).returncode == 1
        # Retry-marker names are unchanged per origin.
        assert (tmp_path / f"autodev-rescore-retry-{origin}-BUG-1").exists()
        assert _run_action(action, tmp_path, absent).returncode == 3

    def test_retry_then_success_proceeds_and_resets_counter(
        self, states: dict[str, Any], tmp_path: Path
    ) -> None:
        _seed_origin(tmp_path, "atomic")
        action = states["check_scores_present"]["action"]
        assert _run_action(action, tmp_path, {"confidence": None, "outcome": None}).returncode == 1
        assert _run_action(action, tmp_path, {"confidence": "90", "outcome": "70"}).returncode == 0
        # Counter reset on the pass: a later miss gets its retry again.
        assert _run_action(action, tmp_path, {"confidence": None, "outcome": None}).returncode == 1

    @pytest.mark.parametrize("origin", [None, "", "bogus"])
    def test_missing_or_unknown_origin_exits_3_without_retry_marker(
        self, states: dict[str, Any], tmp_path: Path, origin: str | None
    ) -> None:
        if origin is not None:
            _seed_origin(tmp_path, origin)
        action = states["check_scores_present"]["action"]
        result = _run_action(action, tmp_path, {"confidence": None, "outcome": None})
        assert result.returncode == 3
        assert not list(tmp_path.glob("autodev-rescore-retry-*"))

    @pytest.mark.parametrize(
        "issue", [{"confidence": "90", "outcome": None}, {"confidence": None, "outcome": "70"}]
    )
    def test_either_score_missing_counts_as_absent(
        self, states: dict[str, Any], tmp_path: Path, issue: dict[str, Any]
    ) -> None:
        _seed_origin(tmp_path, "atomic")
        action = states["check_scores_present"]["action"]
        assert _run_action(action, tmp_path, issue).returncode == 1

    def test_unreadable_show_output_is_absent_not_pass(
        self, states: dict[str, Any], tmp_path: Path
    ) -> None:
        """A failing `ll-issues show` must never be read as a pass on old scores."""
        _seed_origin(tmp_path, "reconcile")
        action = states["check_scores_present"]["action"]
        with tempfile.TemporaryDirectory() as tmp:
            stub = Path(tmp) / "ll-issues"
            stub.write_text("#!/bin/sh\nexit 1\n")
            stub.chmod(0o755)
            env = {**os.environ, "PATH": f"{tmp}{os.pathsep}{os.environ['PATH']}"}
            result = subprocess.run(
                ["bash", "-c", _interpolate(action, tmp_path)],
                capture_output=True,
                text=True,
                check=False,
                env=env,
            )
        assert result.returncode == 1

    def test_dequeue_clears_markers_for_reentry(
        self, states: dict[str, Any], tmp_path: Path
    ) -> None:
        _seed_origin(tmp_path, "wire")
        gate = states["check_scores_present"]["action"]
        absent = {"confidence": None, "outcome": None}
        assert _run_action(gate, tmp_path, absent).returncode == 1
        assert list(tmp_path.glob("autodev-rescore-retry-*-BUG-1"))
        (tmp_path / "autodev-queue.txt").write_text("BUG-1\n")
        result = _run_action(states["dequeue_next"]["action"], tmp_path, absent)
        assert result.returncode == 0, result.stderr
        assert not list(tmp_path.glob("autodev-rescore-retry-*-BUG-1"))
        assert not (tmp_path / "autodev-rescore-origin-BUG-1").exists()


class TestRouteAfterRescore:
    @pytest.mark.parametrize("origin", ORIGINS)
    def test_routes_origin_and_deletes_marker(
        self, states: dict[str, Any], tmp_path: Path, origin: str
    ) -> None:
        _seed_origin(tmp_path, origin)
        result = _run_action(states["route_after_rescore"]["action"], tmp_path, {})
        assert result.stdout.strip() == _ROUTE_TOKENS[origin]
        assert not (tmp_path / "autodev-rescore-origin-BUG-1").exists()

    @pytest.mark.parametrize("origin", [None, "", "bogus"])
    def test_unknown_or_missing_origin_fails_closed(
        self, states: dict[str, Any], tmp_path: Path, origin: str | None
    ) -> None:
        if origin is not None:
            _seed_origin(tmp_path, origin)
        result = _run_action(states["route_after_rescore"]["action"], tmp_path, {})
        assert result.stdout.strip() == "UNKNOWN"
        assert states["route_after_rescore"]["route"]["UNKNOWN"] == "mark_scores_absent_infra"

    def test_two_rescorings_in_one_pass_route_to_own_successors(
        self, states: dict[str, Any], tmp_path: Path
    ) -> None:
        route = states["route_after_rescore"]
        wire = states["count_repair_cycle_wire"]["action"]
        reconcile = states["count_repair_cycle_reconcile"]["action"]
        assert _run_action(wire, tmp_path, {}).returncode == 0
        out = _run_action(route["action"], tmp_path, {}).stdout.strip()
        assert route["route"][out] == "enqueue_or_skip"
        assert _run_action(reconcile, tmp_path, {}).returncode == 0
        out = _run_action(route["action"], tmp_path, {}).stdout.strip()
        assert route["route"][out] == "recheck_after_size_review"
        # Marker consumed: a third route without an entry fails closed.
        out = _run_action(route["action"], tmp_path, {}).stdout.strip()
        assert route["route"].get(out, route["route"]["_"]) == "mark_scores_absent_infra"


@pytest.mark.parametrize("state", ["recheck_after_size_review", "regate_after_atomic_remediation"])
class TestInlineGateAbsence:
    def test_absent_scores_exit_3_not_deferral(
        self, states: dict[str, Any], tmp_path: Path, state: str
    ) -> None:
        result = _run_action(
            states[state]["action"], tmp_path, {"confidence": None, "outcome": None}
        )
        assert result.returncode == 3
        assert "[SCORES_ABSENT]" in result.stdout
        assert not (tmp_path / "autodev-skipped.txt").exists()

    def test_done_parent_without_scores_records_resolved_by_subloop(
        self, states: dict[str, Any], tmp_path: Path, state: str
    ) -> None:
        result = _run_action(
            states[state]["action"],
            tmp_path,
            {"confidence": None, "outcome": None},
            status="done",
        )
        assert result.returncode == 1
        assert "resolved_by_subloop" in (tmp_path / "autodev-skipped.txt").read_text()

    def test_scored_below_threshold_still_takes_quality_path(
        self, states: dict[str, Any], tmp_path: Path, state: str
    ) -> None:
        """Present-but-low scores are a genuine verdict, not an infra outcome."""
        result = _run_action(
            states[state]["action"], tmp_path, {"confidence": "10", "outcome": "10"}
        )
        assert result.returncode == 1
        assert "[SCORES_ABSENT]" not in result.stdout


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

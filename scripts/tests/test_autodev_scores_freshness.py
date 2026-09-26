"""Tests for BUG-3588: autodev post-repair rescoring must gate on fresh scores.

Each of the remaining ``rerun_confidence_after_*`` states (wire, atomic
remediation, reconcile) is bracketed by a ``clear_scores_before_*`` state (clear
stale scores) and a ``check_scores_present_*`` presence gate (retry once, then
infra), so a rescoring that writes nothing can never pass on pre-repair scores nor
surface as a ``low_readiness`` quality deferral.

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

# path key -> (rerun state suffix, successor of the presence gate)
PATHS = {
    "wire": ("wire", "enqueue_or_skip"),
    "atomic": ("atomic_remediation", "regate_after_atomic_remediation"),
    "reconcile": ("reconcile", "recheck_after_size_review"),
}


@pytest.fixture(scope="module")
def states() -> dict[str, Any]:
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())["states"]


class TestRoutingStructure:
    @pytest.mark.parametrize("key", PATHS)
    def test_clear_then_rerun(self, states: dict[str, Any], key: str) -> None:
        rerun, _ = PATHS[key]
        clear = states[f"clear_scores_before_{key}"]
        assert "set-scores" in clear["action"] and "--clear" in clear["action"]
        assert clear["next"] == f"rerun_confidence_after_{rerun}"
        assert clear["on_error"] == "mark_scores_absent_infra"

    @pytest.mark.parametrize("key", PATHS)
    def test_rerun_routes_through_presence_gate(self, states: dict[str, Any], key: str) -> None:
        rerun, _ = PATHS[key]
        state = states[f"rerun_confidence_after_{rerun}"]
        assert state["next"] == f"check_scores_present_{key}"
        assert state["on_error"] == f"check_scores_present_{key}"

    @pytest.mark.parametrize("key", PATHS)
    def test_presence_gate_routing(self, states: dict[str, Any], key: str) -> None:
        rerun, successor = PATHS[key]
        gate = states[f"check_scores_present_{key}"]
        assert gate["fragment"] == "harness_exit"
        assert gate["on_yes"] == successor
        # First miss retries the rescoring itself (scores are already absent).
        assert gate["on_no"] == f"rerun_confidence_after_{rerun}"
        assert gate["on_cannot_judge"] == "mark_scores_absent_infra"
        assert gate["on_error"] == "mark_scores_absent_infra"

    def test_repair_predecessors_target_clear_states(self, states: dict[str, Any]) -> None:
        assert states["run_refine"]["next"] == "clear_scores_before_wire"
        assert states["remediate_oversized_atomic"]["next"] == "clear_scores_before_atomic"
        for pred in ("count_repair_cycle_reconcile", "count_repair_cycle_refine_for_design"):
            assert states[pred]["next"] == "clear_scores_before_reconcile"
            assert states[pred]["on_error"] == "clear_scores_before_reconcile"

    def test_infra_state_is_distinct_and_does_not_defer(self, states: dict[str, Any]) -> None:
        action = states["mark_scores_absent_infra"]["action"]
        assert "autodev-scores-absent.txt" in action
        assert "autodev-gate-infra.txt" not in action
        assert "[SCORES_ABSENT]" in action
        assert "autodev-inflight" in action
        assert "set-status" not in action
        assert states["mark_scores_absent_infra"]["next"] == "dequeue_next"

    def test_dequeue_next_clears_retry_markers(self, states: dict[str, Any]) -> None:
        assert "autodev-rescore-retry-" in states["dequeue_next"]["action"]

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


class TestPresenceGateBehavior:
    @pytest.mark.parametrize("key", PATHS)
    def test_scores_present_passes(self, states: dict[str, Any], tmp_path: Path, key: str) -> None:
        action = states[f"check_scores_present_{key}"]["action"]
        result = _run_action(action, tmp_path, {"confidence": "90", "outcome": "70"})
        assert result.returncode == 0

    def test_first_miss_retries_second_miss_is_infra(
        self, states: dict[str, Any], tmp_path: Path
    ) -> None:
        action = states["check_scores_present_wire"]["action"]
        absent = {"confidence": None, "outcome": None}
        assert _run_action(action, tmp_path, absent).returncode == 1
        assert _run_action(action, tmp_path, absent).returncode == 3

    def test_retry_then_success_proceeds_and_resets_counter(
        self, states: dict[str, Any], tmp_path: Path
    ) -> None:
        action = states["check_scores_present_atomic"]["action"]
        assert _run_action(action, tmp_path, {"confidence": None, "outcome": None}).returncode == 1
        assert _run_action(action, tmp_path, {"confidence": "90", "outcome": "70"}).returncode == 0
        # Counter reset on the pass: a later miss gets its retry again.
        assert _run_action(action, tmp_path, {"confidence": None, "outcome": None}).returncode == 1

    @pytest.mark.parametrize(
        "issue", [{"confidence": "90", "outcome": None}, {"confidence": None, "outcome": "70"}]
    )
    def test_either_score_missing_counts_as_absent(
        self, states: dict[str, Any], tmp_path: Path, issue: dict[str, Any]
    ) -> None:
        action = states["check_scores_present_atomic"]["action"]
        assert _run_action(action, tmp_path, issue).returncode == 1

    def test_unreadable_show_output_is_absent_not_pass(
        self, states: dict[str, Any], tmp_path: Path
    ) -> None:
        """A failing `ll-issues show` must never be read as a pass on old scores."""
        action = states["check_scores_present_reconcile"]["action"]
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
        gate = states["check_scores_present_wire"]["action"]
        absent = {"confidence": None, "outcome": None}
        assert _run_action(gate, tmp_path, absent).returncode == 1
        assert list(tmp_path.glob("autodev-rescore-retry-*-BUG-1"))
        (tmp_path / "autodev-queue.txt").write_text("BUG-1\n")
        result = _run_action(states["dequeue_next"]["action"], tmp_path, absent)
        assert result.returncode == 0, result.stderr
        assert not list(tmp_path.glob("autodev-rescore-retry-*-BUG-1"))


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

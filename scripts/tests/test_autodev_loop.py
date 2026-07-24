"""Tests for BUG-2752 and FEAT-2751 autodev.yaml behavior.

BUG-2752: check_guard2_verdict regex misses real issue-size-review output.

The guard-2 "Very Large" skip line is freeform agent-generated prose (no fixed
template in skills/issue-size-review/SKILL.md for the 8-11 range), so
``check_guard2_verdict``'s pattern must tolerate arbitrary text between
"skipped:" and "score N", and ``check_guard2_score_fallback`` must catch any
remaining drift by probing for a bare "score N" substring.

FEAT-2751: generalizes ``check_reconcile_needed``'s plateau gate beyond the
spike-armed path via a dequeue-time ``autodev-pre-readiness.txt`` snapshot,
and adds a ``readiness_stagnated`` stagnation backstop to
``recheck_after_size_review`` once >= 2 repair-class attempts have run without
moving the score.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import yaml

from little_loops.fsm.evaluators import evaluate_output_contains

AUTODEV_LOOP_PATH = Path(__file__).parent.parent / "little_loops" / "loops" / "autodev.yaml"


def _load_autodev_yaml() -> dict[str, Any]:
    assert AUTODEV_LOOP_PATH.exists(), f"Loop file not found: {AUTODEV_LOOP_PATH}"
    return yaml.safe_load(AUTODEV_LOOP_PATH.read_text())


def _extract_python_script(action: str) -> str:
    """Pull the inline `python3 -c "..."` body out of a shell_exit action string."""
    _, _, tail = action.partition('python3 -c "')
    script, _, _ = tail.rpartition('"')
    return script


def _run_reconcile_predicate(
    run_dir: Path,
    *,
    confidence: str,
    reconcile_attempted: bool,
) -> int:
    """Run the real check_reconcile_needed predicate against synthetic input.

    Substitutes ${context.run_dir} the way the FSM interpolator would, and
    feeds the `ll-issues show --json` payload directly via stdin (bypassing
    the actual CLI call, which the FSM pipes in at runtime).
    """
    action = _load_autodev_yaml()["states"]["check_reconcile_needed"]["action"]
    script = _extract_python_script(action).replace("${context.run_dir}", str(run_dir))
    payload = json.dumps(
        {
            "confidence": confidence,
            "reconcile_attempted": "true" if reconcile_attempted else "false",
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
    )
    return result.returncode


def _pattern(states: dict[str, Any], state_name: str) -> str:
    state = states[state_name]
    return str(state["evaluate"]["pattern"])


REAL_FEAT_021_OUTPUT = (
    "FEAT-021 skipped: score 11 (Very Large) — strictly sequential, shared-infra children"
)


class TestCheckGuard2VerdictPattern:
    def test_guard2_pattern_matches_status_line(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_verdict")

        result = evaluate_output_contains(REAL_FEAT_021_OUTPUT, pattern)

        assert result.verdict == "yes"

    def test_guard2_pattern_still_matches_exact_prefix_shape(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_verdict")

        result = evaluate_output_contains("skipped: score 8 ", pattern)

        assert result.verdict == "yes"

    def test_guard2_pattern_rejects_guard1_ambiguous_line(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_verdict")

        result = evaluate_output_contains(
            "skipped: structural score 6 but outcome_confidence low is qualitative",
            pattern,
        )

        assert result.verdict == "no"

    def test_guard2_pattern_rejects_out_of_range_score(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_verdict")

        result = evaluate_output_contains("skipped: score 5 (ambiguous)", pattern)

        assert result.verdict == "no"

    def test_guard2_verdict_routes_on_no_to_fallback_state(self) -> None:
        states = _load_autodev_yaml()["states"]
        state = states["check_guard2_verdict"]

        assert state["on_no"] == "check_guard2_score_fallback"
        assert state["on_yes"] == "check_readiness_for_atomic_remediation"


class TestCheckGuard2ScoreFallback:
    def test_guard2_fallback_probe_detects_score_9(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_score_fallback")

        result = evaluate_output_contains(
            "FEAT-099 declined decomposition: score 9 way too tangled to split",
            pattern,
        )

        assert result.verdict == "yes"

    def test_guard2_fallback_probe_rejects_out_of_range_score(self) -> None:
        states = _load_autodev_yaml()["states"]
        pattern = _pattern(states, "check_guard2_score_fallback")

        result = evaluate_output_contains("looks fine, score 3, no action needed", pattern)

        assert result.verdict == "no"

    def test_guard2_fallback_routes_to_readiness_or_recheck(self) -> None:
        states = _load_autodev_yaml()["states"]
        state = states["check_guard2_score_fallback"]

        assert state["on_yes"] == "check_readiness_for_atomic_remediation"
        assert state["on_no"] == "recheck_after_size_review"

    def test_guard2_fallback_uses_evaluate_source_not_shell_action(self) -> None:
        """BUG-2594: never shell-interpolate untrusted captured text."""
        states = _load_autodev_yaml()["states"]
        state = states["check_guard2_score_fallback"]

        assert "action" not in state
        assert state["evaluate"]["source"] == "${captured.size_review_output.output}"


class TestDequeueNextPreReadinessSnapshot:
    """FEAT-2751: dequeue_next must snapshot pre-refine confidence per-issue and
    reset the repair-cycle counter / stale spike snapshot."""

    def test_action_writes_pre_readiness_snapshot(self) -> None:
        action = _load_autodev_yaml()["states"]["dequeue_next"]["action"]
        assert "autodev-pre-readiness.txt" in action

    def test_action_resets_repair_cycle_counter(self) -> None:
        action = _load_autodev_yaml()["states"]["dequeue_next"]["action"]
        assert "autodev-repair-cycle-count.txt" in action

    def test_action_clears_stale_spike_snapshot(self) -> None:
        action = _load_autodev_yaml()["states"]["dequeue_next"]["action"]
        assert "rm -f ${context.run_dir}/autodev-pre-spike-readiness.txt" in action


class TestCheckReconcileNeededFallbackSnapshot:
    """FEAT-2751: check_reconcile_needed must fall back to the dequeue-time
    autodev-pre-readiness.txt snapshot when the spike-only snapshot is absent,
    generalizing the ENH-2689 plateau gate beyond the spike-armed path."""

    def test_predicate_reads_both_snapshots(self) -> None:
        action = _load_autodev_yaml()["states"]["check_reconcile_needed"]["action"]
        assert "autodev-pre-spike-readiness.txt" in action
        assert "autodev-pre-readiness.txt" in action

    def test_fires_from_fallback_snapshot_without_spike(self, tmp_path: Path) -> None:
        """No spike snapshot exists (FEAT-021 profile); pre-readiness snapshot ==
        current confidence and no prior reconcile attempt → plateau detected."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("85")

        exit_code = _run_reconcile_predicate(tmp_path, confidence="85", reconcile_attempted=False)

        assert exit_code == 0, "plateau must be detected from the fallback snapshot alone"

    def test_prefers_spike_snapshot_when_present(self, tmp_path: Path) -> None:
        """Both snapshots exist with different values — the spike snapshot (the
        fresher pre-repair baseline) must govern the plateau comparison."""
        (tmp_path / "autodev-pre-spike-readiness.txt").write_text("85")
        (tmp_path / "autodev-pre-readiness.txt").write_text("70")

        # Current confidence matches the spike snapshot, not the stale fallback —
        # plateau should fire only because the spike snapshot is preferred.
        exit_code = _run_reconcile_predicate(tmp_path, confidence="85", reconcile_attempted=False)

        assert exit_code == 0

        # Current confidence matches the fallback snapshot instead — since the
        # spike snapshot takes precedence and does NOT match, no plateau.
        exit_code = _run_reconcile_predicate(tmp_path, confidence="70", reconcile_attempted=False)

        assert exit_code == 1

    def test_no_fire_on_confidence_improvement(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-pre-readiness.txt").write_text("85")

        exit_code = _run_reconcile_predicate(tmp_path, confidence="88", reconcile_attempted=False)

        assert exit_code == 1

    def test_no_fire_when_reconcile_already_attempted(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-pre-readiness.txt").write_text("85")

        exit_code = _run_reconcile_predicate(tmp_path, confidence="85", reconcile_attempted=True)

        assert exit_code == 1

    def test_no_fire_when_neither_snapshot_exists(self, tmp_path: Path) -> None:
        exit_code = _run_reconcile_predicate(tmp_path, confidence="85", reconcile_attempted=False)

        assert exit_code == 1


class TestRepairCycleCounterStates:
    """FEAT-2751: dedicated count_repair_cycle_* states increment the shared
    repair-cycle counter file, matching the recursive-refine counter idiom."""

    def test_all_five_counter_states_exist(self) -> None:
        states = _load_autodev_yaml()["states"]
        for name in (
            "count_repair_cycle_refine",
            "count_repair_cycle_wire",
            "count_repair_cycle_size_review",
            "count_repair_cycle_spike",
            "count_repair_cycle_reconcile",
        ):
            assert name in states, f"{name} missing from autodev.yaml (FEAT-2751)"
            assert "autodev-repair-cycle-count.txt" in states[name]["action"]

    def test_counter_increments_monotonically(self, tmp_path: Path) -> None:
        action = _load_autodev_yaml()["states"]["count_repair_cycle_refine"]["action"]
        script = action.replace("${context.run_dir}", str(tmp_path))

        seen = []
        for _ in range(3):
            subprocess.run(["bash", "-c", script], check=True)
            seen.append(int((tmp_path / "autodev-repair-cycle-count.txt").read_text()))

        assert seen == [1, 2, 3]

    def test_refine_current_routes_through_counter_before_copy_broke_down(self) -> None:
        state = _load_autodev_yaml()["states"]["refine_current"]
        assert state.get("on_success") == "count_repair_cycle_refine"
        counter_state = _load_autodev_yaml()["states"]["count_repair_cycle_refine"]
        assert counter_state.get("next") == "copy_broke_down"

    def test_run_wire_routes_through_counter_before_run_refine(self) -> None:
        state = _load_autodev_yaml()["states"]["run_wire"]
        assert state.get("next") == "count_repair_cycle_wire"
        assert state.get("on_error") == "count_repair_cycle_wire"
        counter_state = _load_autodev_yaml()["states"]["count_repair_cycle_wire"]
        assert counter_state.get("next") == "run_refine"
        assert counter_state.get("on_error") == "run_refine"

    def test_run_size_review_routes_through_counter_before_enqueue_or_skip(self) -> None:
        state = _load_autodev_yaml()["states"]["run_size_review"]
        assert state.get("next") == "count_repair_cycle_size_review"
        assert state.get("on_error") == "count_repair_cycle_size_review"
        counter_state = _load_autodev_yaml()["states"]["count_repair_cycle_size_review"]
        assert counter_state.get("next") == "enqueue_or_skip"
        assert counter_state.get("on_error") == "enqueue_or_skip"


class TestRecheckAfterSizeReviewStagnationBackstop:
    """FEAT-2751: recheck_after_size_review defers with `readiness_stagnated`
    instead of `low_readiness` once >= 2 repair-class attempts ran this cycle
    without moving Readiness past its dequeue-time snapshot."""

    def test_action_references_cycle_count_and_pre_readiness(self) -> None:
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        assert "autodev-repair-cycle-count.txt" in action
        assert "autodev-pre-readiness.txt" in action
        assert "readiness_stagnated" in action

    def test_still_writes_low_readiness_reason_unchanged(self) -> None:
        """Regression guard: the low_readiness write path must remain intact
        for issues below the cycle-count threshold."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        assert 'echo "$ID  low_readiness"' in action

    def test_stagnated_write_precedes_low_readiness_write(self) -> None:
        """The stagnation branch must be checked before falling through to the
        unconditional low_readiness write, so a stagnated issue never also
        matches the low_readiness branch."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        stagnated_idx = action.index('echo "$ID  readiness_stagnated"')
        low_readiness_idx = action.index('echo "$ID  low_readiness"')
        assert stagnated_idx < low_readiness_idx

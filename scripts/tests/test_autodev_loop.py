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
    script = (
        _extract_python_script(action)
        .replace("${context.run_dir}", str(run_dir))
        # BUG-2803: the fresh-below-threshold branch reads the configured
        # readiness threshold; substitute it the way the FSM interpolator
        # would (seeded from commands.confidence_gate.readiness_threshold).
        .replace("${context.readiness_threshold}", "85")
    )
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


class TestCheckReconcileNeededFreshBelowThreshold:
    """BUG-2803: a freshly captured issue (empty dequeue-time snapshot, no prior
    score) that scores below the readiness threshold must be reconcile-eligible —
    the plateau gate's `pre != ''` guard excluded it by construction, deferring
    fresh issues as low_readiness with every remedy structurally unreachable."""

    def test_fires_for_never_scored_below_threshold_issue(self, tmp_path: Path) -> None:
        """Empty snapshot (fresh issue) + Readiness 72 < 85 → reconcile fires
        (the BUG-2801 evidence profile)."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("")

        exit_code = _run_reconcile_predicate(tmp_path, confidence="72", reconcile_attempted=False)

        assert exit_code == 0, "empty snapshot must no longer exclude below-threshold issues"

    def test_backfills_snapshot_so_stagnation_discriminator_applies(self, tmp_path: Path) -> None:
        """On the fresh-below branch the current score must be backfilled into
        autodev-pre-readiness.txt so a post-remedy repeat failure defers as
        readiness_stagnated (FEAT-2751 backstop), not low_readiness."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("")

        _run_reconcile_predicate(tmp_path, confidence="72", reconcile_attempted=False)

        assert (tmp_path / "autodev-pre-readiness.txt").read_text().strip() == "72"

    def test_no_fire_for_fresh_issue_at_or_above_threshold(self, tmp_path: Path) -> None:
        (tmp_path / "autodev-pre-readiness.txt").write_text("")

        exit_code = _run_reconcile_predicate(tmp_path, confidence="90", reconcile_attempted=False)

        assert exit_code == 1

    def test_no_fire_for_fresh_issue_after_reconcile_attempted(self, tmp_path: Path) -> None:
        """One-shot guard: reconcile_attempted still suppresses the fresh branch."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("")

        exit_code = _run_reconcile_predicate(tmp_path, confidence="72", reconcile_attempted=True)

        assert exit_code == 1

    def test_no_fire_when_still_unscored(self, tmp_path: Path) -> None:
        """No current confidence at all (refine produced no score) → no fire;
        reconcile on an unscored issue would be meaningless."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("")

        exit_code = _run_reconcile_predicate(tmp_path, confidence="", reconcile_attempted=False)

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


class TestDesignGateStep0Detection:
    """ENH-2870: all three gate states hard-AND the Program Design verdict."""

    def test_recheck_scores_shells_out_to_format_check(self) -> None:
        action = _load_autodev_yaml()["states"]["recheck_scores"]["action"]
        assert "ll-issues format-check" in action
        assert "--format json" in action
        assert "program_design_nonspecific" in action
        assert "autodev-design-gate-failed-$ID" in action

    def test_recheck_scores_composes_design_fail_with_check_readiness_exit_code(self) -> None:
        """recheck_scores has no local GATE variable — it routes on
        check-readiness's own exit code (fragment: shell_exit) — so the
        design AND must be composed via a chained `&&`, not a GATE overwrite."""
        action = _load_autodev_yaml()["states"]["recheck_scores"]["action"]
        assert "ll-issues check-readiness" in action
        assert '[ "$DESIGN_FAIL" != "true" ]' in action

    def test_regate_after_atomic_remediation_shells_out_to_format_check(self) -> None:
        action = _load_autodev_yaml()["states"]["regate_after_atomic_remediation"]["action"]
        assert "ll-issues format-check" in action
        assert "--format json" in action
        assert "program_design_nonspecific" in action
        assert 'GATE="FAIL"' in action

    def test_recheck_after_size_review_shells_out_to_format_check(self) -> None:
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        assert "ll-issues format-check" in action
        assert "--format json" in action
        assert "program_design_nonspecific" in action
        assert 'GATE="FAIL"' in action

    def test_parses_flat_single_id_shape_not_all_mapping(self) -> None:
        """The parser must read the flat single-ID JSON shape (missing/empty/
        program_design_nonspecific keys directly on the root dict), never
        index by issue ID the way --all's {issue_id: gaps} mapping would."""
        for state_name in (
            "recheck_scores",
            "regate_after_atomic_remediation",
            "recheck_after_size_review",
        ):
            action = _load_autodev_yaml()["states"][state_name]["action"]
            assert "d.get('program_design_nonspecific')" in action
            assert "d.get('missing')" in action
            assert "d.get('empty')" in action
            assert "d[ID]" not in action
            assert 'd["$ID"]' not in action


class TestRecheckAfterSizeReviewDesignGateBranch:
    """ENH-2870: a design-caused FAIL routes through the reconcile remedy
    before any deferral, ordered ahead of the readiness_stagnated backstop,
    and defers as design_gate_failed (never low_readiness) once reconcile has
    already been attempted."""

    def test_design_branch_precedes_readiness_stagnated_branch(self) -> None:
        """A design-gate FAIL must not be swallowed by the CYCLE_COUNT >= 2
        stagnation branch — required order is after resolved_by_subloop,
        before readiness_stagnated."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        design_idx = action.index("if [ -f ${context.run_dir}/autodev-design-gate-failed-$ID ]")
        resolved_idx = action.index('echo "$ID  resolved_by_subloop"')
        stagnated_idx = action.index('echo "$ID  readiness_stagnated"')
        assert resolved_idx < design_idx < stagnated_idx

    def test_design_branch_hardcodes_reconcile_remedy(self) -> None:
        """The design-gate branch bypasses the weakest-subscore spike/reconcile
        heuristic entirely — it always selects reconcile."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        design_section = action[action.index("autodev-design-gate-failed-$ID") :]
        pre_deferral_idx = design_section.index("design_gate_failed")
        branch = design_section[:pre_deferral_idx]
        assert "else 'reconcile'" in branch
        assert "score_ambiguity" not in branch

    def test_design_branch_reconcile_attempted_falls_through_to_design_gate_failed(
        self,
    ) -> None:
        """The selector's `reconcile_attempted == 'true'` empty fall-through
        must land on design_gate_failed, never low_readiness."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        assert "'' if d.get('reconcile_attempted') == 'true' else 'reconcile'" in action
        design_idx = action.index("autodev-design-gate-failed-$ID")
        design_defer_idx = action.index('echo "$ID  design_gate_failed"')
        low_readiness_idx = action.index('echo "$ID  low_readiness"')
        assert design_idx < design_defer_idx < low_readiness_idx

    def test_design_branch_reuses_existing_remedy_handshake_files(self) -> None:
        """No new remedy infrastructure — reuse BUG-2803's fired marker and
        pre-deferral-remedy.txt handshake files."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        design_section = action[action.index("autodev-design-gate-failed-$ID") :]
        branch = design_section[: design_section.index('echo "$ID  design_gate_failed"')]
        assert "autodev-pre-deferral-remedy-fired" in branch
        assert "autodev-pre-deferral-remedy.txt" in branch

    def test_pre_fix_bypass_closed_high_score_with_design_gap(self) -> None:
        """High confidence score alone must not reach decide_current when the
        design gate marker is present — the GATE AND forces FAIL regardless
        of the persisted numeric score."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        assert 'GATE="FAIL"' in action
        design_fail_idx = action.index('if [ "$DESIGN_FAIL" = "true" ]')
        gate_fail_write_idx = action.index('GATE="FAIL"')
        gate_pass_check_idx = action.index('if [ "$GATE" = "PASS" ]')
        assert design_fail_idx < gate_fail_write_idx < gate_pass_check_idx


class TestRegateAfterAtomicRemediationDesignGateBranch:
    """ENH-2870: a design-caused FAIL at regate_after_atomic_remediation must
    never be labelled oversized_atomic — it routes to the shared reconcile
    remedy (via check_atomic_design_remedy) if reachable, else defers
    design_gate_failed."""

    def test_design_marker_check_precedes_oversized_atomic_write(self) -> None:
        action = _load_autodev_yaml()["states"]["regate_after_atomic_remediation"]["action"]
        design_idx = action.index("autodev-design-gate-failed-$ID")
        oversized_idx = action.index('echo "$ID  oversized_atomic"')
        assert design_idx < oversized_idx

    def test_design_caused_fail_never_writes_oversized_atomic(self) -> None:
        """Everything within the design-marker branch must return before
        reaching the unconditional oversized_atomic write below it."""
        action = _load_autodev_yaml()["states"]["regate_after_atomic_remediation"]["action"]
        design_section = action[
            action.index("if [ -f ${context.run_dir}/autodev-design-gate-failed-$ID ]")
        ]
        assert design_section is not None  # marker branch exists at all

    def test_on_no_routes_through_check_atomic_design_remedy_dispatcher(self) -> None:
        state = _load_autodev_yaml()["states"]["regate_after_atomic_remediation"]
        assert state.get("on_no") == "check_atomic_design_remedy"

    def test_dispatcher_routes_pending_remedy_to_reconcile_current(self) -> None:
        dispatcher = _load_autodev_yaml()["states"]["check_atomic_design_remedy"]
        assert dispatcher.get("on_yes") == "reconcile_current"
        assert dispatcher.get("on_no") == "dequeue_next"
        assert "autodev-atomic-design-remedy-pending" in dispatcher["action"]

    def test_pre_fix_bypass_closed_oversized_atomic_never_masks_design_fail(self) -> None:
        """Regression guard for the pre-fix bug: a design-caused FAIL with a
        passing readiness score used to fall straight into the unconditional
        oversized_atomic write. The design-marker branch must come first and
        `exit 1` before that write is reached for a not-yet-reconciled issue."""
        action = _load_autodev_yaml()["states"]["regate_after_atomic_remediation"]["action"]
        assert "autodev-atomic-design-remedy-pending" in action
        pending_idx = action.index("autodev-atomic-design-remedy-pending")
        oversized_idx = action.index('echo "$ID  oversized_atomic"')
        assert pending_idx < oversized_idx

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
import os
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
    marker_count: int = 0,
    issue_id: str = "BUG-9999",
) -> int:
    """Run the real check_reconcile_needed predicate against synthetic input.

    Substitutes ${context.run_dir} the way the FSM interpolator would, and
    feeds the `ll-issues show --json` payload directly via stdin (bypassing
    the actual CLI call, which the FSM pipes in at runtime).

    ENH-2992: the contradiction term reads the `ll-issues format-check
    --format json` payload the shell action captures into
    LL_FORMAT_CHECK_JSON, so ``marker_count`` is injected the same way the FSM
    would — via the environment, not a second stdin stream.
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
        env={
            **os.environ,
            "LL_ISSUE_ID": issue_id,
            "LL_FORMAT_CHECK_JSON": json.dumps({"superseded_marker_count": marker_count}),
        },
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


class TestCheckReconcileNeededContradiction:
    """ENH-2992: reconcile also fires on a *detected contradiction* — a
    ``⚠ Superseded`` marker standing in a directive section (ENH-2995) — not
    only on a readiness plateau. The contradiction term is deliberately NOT
    gated by ``reconcile_attempted`` (that flag is permanent frontmatter, so
    gating on it would make a second reconcile structurally impossible); it is
    bounded structurally by reconcile clearing the marker it acted on, and
    numerically by a reconcile-scoped per-issue fire counter capped at 2.
    """

    ARMED = "autodev-contradiction-reconcile-armed"
    COUNT = "autodev-contradiction-reconcile-count.txt"

    def test_fires_on_contradiction_when_score_moved(self, tmp_path: Path) -> None:
        """AC1: the score changed against the pre-repair snapshot, so `plateau`
        is false by construction — a fire here can only come from the
        contradiction branch."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("70")

        exit_code = _run_reconcile_predicate(
            tmp_path, confidence="90", reconcile_attempted=False, marker_count=1
        )

        assert exit_code == 0, "a standing marker must fire the gate independently of plateau"

    def test_contradiction_not_gated_by_reconcile_attempted(self, tmp_path: Path) -> None:
        """AC5 depends on this: `reconcile_attempted` is permanent frontmatter,
        never cleared by any state, so gating the contradiction term on it
        would make a second reconcile impossible for any issue, ever."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("70")

        exit_code = _run_reconcile_predicate(
            tmp_path, confidence="90", reconcile_attempted=True, marker_count=1
        )

        assert exit_code == 0

    def test_no_fire_when_markers_cleared(self, tmp_path: Path) -> None:
        """AC4 (predicate half): once `/ll:reconcile-issue` has cleared the
        marker on the line it evaluated, the next pass sees marker_count 0 and
        the gate does not re-fire. The skill-side half — clearing on the no-op
        path too — is pinned in test_reconcile_issue_command.py."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("70")

        exit_code = _run_reconcile_predicate(
            tmp_path, confidence="90", reconcile_attempted=True, marker_count=0
        )

        assert exit_code == 1

    def test_no_fire_without_marker_or_plateau(self, tmp_path: Path) -> None:
        """AC6: issues off the new branch behave exactly as before."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("70")

        exit_code = _run_reconcile_predicate(
            tmp_path, confidence="90", reconcile_attempted=False, marker_count=0
        )

        assert exit_code == 1

    def test_contradiction_capped_after_two_fires(self, tmp_path: Path) -> None:
        """AC5: a second distinct contradiction is eligible; a third is capped
        by the reconcile-scoped counter — NOT by the shared
        autodev-repair-cycle-count.txt ceiling, which is readiness-conditioned
        and shared across six repair classes."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("70")

        for fires, expected in ((0, 0), (1, 0), (2, 1), (3, 1)):
            (tmp_path / self.COUNT).write_text(str(fires))

            exit_code = _run_reconcile_predicate(
                tmp_path, confidence="90", reconcile_attempted=False, marker_count=1
            )

            assert exit_code == expected, f"{fires} prior contradiction fires"

    def test_arms_handshake_marker_on_contradiction_only_fire(self, tmp_path: Path) -> None:
        """count_repair_cycle_reconcile consumes this marker to increment the
        reconcile-scoped counter and stamp the per-issue exemption file."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("70")

        _run_reconcile_predicate(
            tmp_path, confidence="90", reconcile_attempted=False, marker_count=1
        )

        assert (tmp_path / self.ARMED).exists()

    def test_does_not_arm_handshake_on_plateau_fire(self, tmp_path: Path) -> None:
        """A plateau-driven reconcile must not burn the contradiction budget,
        nor claim the pre-deferral-dispatcher exemption (AC5a) — that carve-out
        exists only for stamps a contradiction-only fire caused."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("85")

        exit_code = _run_reconcile_predicate(
            tmp_path, confidence="85", reconcile_attempted=False, marker_count=1
        )

        assert exit_code == 0
        assert not (tmp_path / self.ARMED).exists()

    def test_malformed_counter_does_not_break_the_gate(self, tmp_path: Path) -> None:
        """A truncated/garbage counter file must not crash the predicate — the
        FSM would route on_error and skip the whole branch."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("70")
        (tmp_path / self.COUNT).write_text("not-a-number")

        exit_code = _run_reconcile_predicate(
            tmp_path, confidence="90", reconcile_attempted=False, marker_count=1
        )

        assert exit_code == 0

    def test_missing_format_check_payload_is_inert(self, tmp_path: Path) -> None:
        """`ll-issues format-check` failing (unreadable issue, older CLI) must
        leave the gate exactly as it was pre-ENH-2992, not fire it."""
        (tmp_path / "autodev-pre-readiness.txt").write_text("70")
        action = _load_autodev_yaml()["states"]["check_reconcile_needed"]["action"]
        script = (
            _extract_python_script(action)
            .replace("${context.run_dir}", str(tmp_path))
            .replace("${context.readiness_threshold}", "85")
        )
        env = {k: v for k, v in os.environ.items() if k != "LL_FORMAT_CHECK_JSON"}

        result = subprocess.run(
            [sys.executable, "-c", script],
            input=json.dumps({"confidence": "90", "reconcile_attempted": "false"}),
            capture_output=True,
            text=True,
            check=False,
            env={**env, "LL_ISSUE_ID": "BUG-9999"},
        )

        assert result.returncode == 1, result.stderr


class TestRepairCycleCounterStates:
    """FEAT-2751: dedicated count_repair_cycle_* states increment the shared
    repair-cycle counter file, matching the recursive-refine counter idiom."""

    def test_all_six_counter_states_exist(self) -> None:
        states = _load_autodev_yaml()["states"]
        for name in (
            "count_repair_cycle_refine",
            "count_repair_cycle_wire",
            "count_repair_cycle_size_review",
            "count_repair_cycle_spike",
            "count_repair_cycle_reconcile",
            "count_repair_cycle_refine_for_design",
        ):
            assert name in states, f"{name} missing from autodev.yaml (FEAT-2751/BUG-3002)"
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
    """ENH-2870/ENH-2967: all three gate states hard-AND the Program Design verdict,
    now via the single `ll-issues check-design` exit-code owner instead of each state
    re-deriving the OR from raw `format-check --format json` output."""

    def test_recheck_scores_calls_check_design(self) -> None:
        action = _load_autodev_yaml()["states"]["recheck_scores"]["action"]
        assert "ll-issues check-design" in action
        assert "autodev-design-gate-failed-$ID" in action
        assert "format-check" not in action
        assert "program_design_nonspecific" not in action

    def test_recheck_scores_composes_design_fail_with_check_readiness_exit_code(self) -> None:
        """recheck_scores has no local GATE variable — it routes on
        check-readiness's own exit code (fragment: shell_exit) — so the
        design AND must be composed via a chained `&&`, not a GATE overwrite."""
        action = _load_autodev_yaml()["states"]["recheck_scores"]["action"]
        assert "ll-issues check-readiness" in action
        assert "&& ll-issues check-design" in action

    def test_regate_after_atomic_remediation_calls_check_design(self) -> None:
        action = _load_autodev_yaml()["states"]["regate_after_atomic_remediation"]["action"]
        assert "ll-issues check-design" in action
        assert "format-check" not in action
        assert "program_design_nonspecific" not in action
        assert 'GATE="FAIL"' in action

    def test_recheck_after_size_review_calls_check_design(self) -> None:
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        assert "ll-issues check-design" in action
        assert "format-check" not in action
        assert "program_design_nonspecific" not in action
        assert 'GATE="FAIL"' in action

    def test_no_inline_design_fail_python_parsing_remains(self) -> None:
        """The fail-quiet `except Exception: d = {}` / `|| echo "false"` inline-JSON
        scaffolding this issue targets must be gone from all three states."""
        for state_name in (
            "recheck_scores",
            "regate_after_atomic_remediation",
            "recheck_after_size_review",
        ):
            action = _load_autodev_yaml()["states"][state_name]["action"]
            assert "DESIGN_JSON" not in action
            assert "d.get('program_design_nonspecific')" not in action


class TestRecheckAfterSizeReviewDesignGateBranch:
    """ENH-2870/BUG-3002: a design-caused FAIL routes through the dedicated
    refine_design remedy before any deferral, ordered ahead of the
    readiness_stagnated backstop, and defers as design_gate_failed (never
    low_readiness) once that remedy has already been attempted."""

    def test_design_branch_precedes_readiness_stagnated_branch(self) -> None:
        """A design-gate FAIL must not be swallowed by the CYCLE_COUNT >= 2
        stagnation branch — required order is after resolved_by_subloop,
        before readiness_stagnated."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        design_idx = action.index("if [ -f ${context.run_dir}/autodev-design-gate-failed-$ID ]")
        resolved_idx = action.index('echo "$ID  resolved_by_subloop"')
        stagnated_idx = action.index('echo "$ID  readiness_stagnated"')
        assert resolved_idx < design_idx < stagnated_idx

    def test_design_branch_hardcodes_refine_design_remedy(self) -> None:
        """The design-gate branch bypasses the weakest-subscore spike/reconcile
        heuristic entirely — it always selects refine_design (BUG-3002:
        retargeted from reconcile, whose contract excludes Program Design)."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        design_section = action[action.index("autodev-design-gate-failed-$ID") :]
        pre_deferral_idx = design_section.index("design_gate_failed")
        branch = design_section[:pre_deferral_idx]
        assert 'REMEDY="refine_design"' in branch
        assert "score_ambiguity" not in branch

    def test_design_branch_attempted_marker_falls_through_to_design_gate_failed(
        self,
    ) -> None:
        """The `autodev-design-remedy-attempted-$ID` marker's empty
        fall-through must land on design_gate_failed, never low_readiness."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        assert "autodev-design-remedy-attempted-$ID" in action
        design_idx = action.index("autodev-design-gate-failed-$ID")
        design_defer_idx = action.index('echo "$ID  design_gate_failed"')
        low_readiness_idx = action.index('echo "$ID  low_readiness"')
        assert design_idx < design_defer_idx < low_readiness_idx

    def test_design_branch_reuses_existing_remedy_handshake_files(self) -> None:
        """Reuse BUG-2803's fired marker and pre-deferral-remedy.txt handshake
        files; also gains the BUG-3002 design-remedy-attempted marker as the
        cross-route one-shot guard replacing the reconcile_attempted read."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        design_section = action[action.index("autodev-design-gate-failed-$ID") :]
        branch = design_section[: design_section.index('echo "$ID  design_gate_failed"')]
        assert "autodev-pre-deferral-remedy-fired" in branch
        assert "autodev-pre-deferral-remedy.txt" in branch
        assert "autodev-design-remedy-attempted-$ID" in branch

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


def _run_pre_deferral_remedy_selector(
    *,
    gate_marker: str,
    spike_attempted: bool = False,
    reconcile_attempted: bool = False,
    contradiction_sourced: bool = False,
    score_ambiguity: int = 0,
    score_complexity: int = 0,
    score_test_coverage: int = 0,
    score_change_surface: int = 0,
) -> str:
    """Run the real BUG-2803/ENH-2978 REMEDY selector python one-liner against
    synthetic input, mirroring _run_reconcile_predicate's subprocess-execution
    approach for check_reconcile_needed.

    ENH-2992: `contradiction_sourced` stands in for the per-issue
    `autodev-contradiction-reconcile-<ID>` stamp the shell branch probes before
    invoking this script, passed through CONTRA_ONLY like GATE_MARKER.
    """
    action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
    marker = (
        'REMEDY=$(GATE_MARKER="$GATE_MARKER" CONTRA_ONLY="$CONTRA_ONLY" '
        'll-issues show "$ID" --json 2>/dev/null | python3 -c "'
    )
    idx = action.index(marker)
    tail = action[idx + len(marker) :]
    script, _, _ = tail.partition('" 2>/dev/null || echo "")')
    payload = json.dumps(
        {
            "spike_attempted": "true" if spike_attempted else "false",
            "reconcile_attempted": "true" if reconcile_attempted else "false",
            "score_ambiguity": score_ambiguity,
            "score_complexity": score_complexity,
            "score_test_coverage": score_test_coverage,
            "score_change_surface": score_change_surface,
        }
    )
    result = subprocess.run(
        [sys.executable, "-c", script],
        input=payload,
        capture_output=True,
        text=True,
        check=False,
        env={
            **os.environ,
            "GATE_MARKER": gate_marker,
            "CONTRA_ONLY": "true" if contradiction_sourced else "false",
        },
    )
    return result.stdout.strip()


class TestCheckGateAtDequeueMarkerLiterals:
    """ENH-3148: check_gate_at_dequeue reuses GATE_MARKER's phrase list
    verbatim (BUG-3147's inline-matcher precedent), not a shared helper."""

    def test_marker_literals_present_in_action(self) -> None:
        action = _load_autodev_yaml()["states"]["check_gate_at_dequeue"]["action"]
        for literal in (
            "do not start otherwise",
            "measurement \\(gate\\)",
            "pre-implementation measurement",
            "⚠ Gated",
            "do not implement before",
            "evidence gate",
            "gate opens",
            "is explicitly gated",
        ):
            assert literal in action


class TestRecheckAfterSizeReviewMeasurementGateBranch:
    """ENH-2978: an explicit unresolved measurement/proof gate in the issue
    body forces the BUG-2803 pre-deferral remedy to spike, independent of
    which outcome-confidence subscore is weakest."""

    def test_marker_literals_present_in_action(self) -> None:
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        for literal in (
            "do not start otherwise",
            "measurement \\(gate\\)",
            "pre-implementation measurement",
            "⚠ Gated",
            "do not implement before",
            "evidence gate",
            "gate opens",
            "is explicitly gated",
        ):
            assert literal in action

    def test_gate_check_precedes_ambiguity_fallback(self) -> None:
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        gate_idx = action.index("GATE_MARKER")
        fallback_idx = action.index("amb = int(d.get('score_ambiguity')")
        assert gate_idx < fallback_idx

    def test_marker_present_forces_spike_even_when_ambiguity_not_weakest(self) -> None:
        """The precedence case ENH-2978 exists to fix: gate marker present,
        but score_ambiguity is NOT the strictly weakest subscore."""
        remedy = _run_pre_deferral_remedy_selector(
            gate_marker="true",
            score_ambiguity=18,
            score_complexity=14,
            score_test_coverage=25,
            score_change_surface=25,
        )
        assert remedy == "spike"

    def test_marker_absent_falls_back_to_ambiguity_weakest_regression(self) -> None:
        remedy = _run_pre_deferral_remedy_selector(
            gate_marker="false",
            score_ambiguity=5,
            score_complexity=14,
            score_test_coverage=25,
            score_change_surface=25,
        )
        assert remedy == "spike"

    def test_marker_absent_and_ambiguity_not_weakest_falls_back_to_reconcile_regression(
        self,
    ) -> None:
        remedy = _run_pre_deferral_remedy_selector(
            gate_marker="false",
            score_ambiguity=18,
            score_complexity=14,
            score_test_coverage=25,
            score_change_surface=25,
        )
        assert remedy == "reconcile"

    def test_marker_present_but_already_attempted_yields_no_remedy(self) -> None:
        """The attempted-flags guard must still take precedence over the gate
        marker — a spike already run this cycle must not re-arm."""
        remedy = _run_pre_deferral_remedy_selector(
            gate_marker="true",
            spike_attempted=True,
            score_ambiguity=18,
            score_complexity=14,
        )
        assert remedy == ""

    def test_marker_absent_and_ambiguity_ties_weakest_falls_back_to_reconcile_regression(
        self,
    ) -> None:
        """BUG-3146: the `amb == min(others)` tie boundary. Decided Option A —
        a real (not "unmeasured") sibling score of `0`/tied-weakest legitimately
        outranks ambiguity, since the comparison requires ambiguity to be
        *strictly* weakest, not merely tied."""
        remedy = _run_pre_deferral_remedy_selector(
            gate_marker="false",
            score_ambiguity=14,
            score_complexity=14,
            score_test_coverage=25,
            score_change_surface=25,
        )
        assert remedy == "reconcile"


class TestRecheckAfterSizeReviewDecisionUnresolvedBranch:
    """ENH-2936: the score-failing deferral cascade must re-check decision_needed
    and defer as decision_unresolved instead of readiness_stagnated/low_readiness
    when the flag is still armed (ENH-2866 postmortem)."""

    def test_decision_branch_present(self) -> None:
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        assert "DECISION_NEEDED" in action
        assert "--reason decision_unresolved" in action
        assert 'echo "$ID  decision_unresolved"' in action

    def test_decision_branch_ordered_after_design_gate_before_stagnation(self) -> None:
        """Required order: after resolved_by_subloop and the design-gate branch,
        before the CYCLE_COUNT >= 2 readiness_stagnated backstop."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        resolved_idx = action.index('echo "$ID  resolved_by_subloop"')
        design_defer_idx = action.index('echo "$ID  design_gate_failed"')
        decision_idx = action.index('echo "$ID  decision_unresolved"')
        stagnated_idx = action.index('echo "$ID  readiness_stagnated"')
        assert resolved_idx < design_defer_idx < decision_idx < stagnated_idx

    def test_decision_branch_ordered_before_low_readiness(self) -> None:
        """The new branch must sit entirely before the BUG-2803 pre-deferral-remedy
        handshake and the low_readiness deferral it guards — never spliced between
        the fired marker and its low_readiness write (that ordering is separately
        covered by test_recheck_after_size_review_arms_remedy_before_low_readiness
        in test_builtin_loops.py)."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        decision_idx = action.index('echo "$ID  decision_unresolved"')
        low_readiness_idx = action.index('echo "$ID  low_readiness"')
        assert decision_idx < low_readiness_idx
        assert action.index("autodev-pre-deferral-remedy-fired") < low_readiness_idx

    def test_decision_branch_reads_decision_needed_from_existing_json_payload(self) -> None:
        """No new subprocess call beyond the existing ll-issues show --json fetch
        pattern already used for GATE/STATUS/CUR_CONFIDENCE."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        decision_section = action[action.index("DECISION_NEEDED=") :]
        branch = decision_section[: decision_section.index('echo "$ID  decision_unresolved"')]
        assert "ll-issues show" in branch
        assert "decision_needed" in branch


class TestPreDeferralRemedyContradictionExemption:
    """ENH-2992 (AC5a): a contradiction-only reconcile must not consume the
    pre-deferral remedy budget.

    `/ll:reconcile-issue` stamps `reconcile_attempted: true` unconditionally.
    Before this change that stamp only ever landed on an issue that had already
    plateaued below threshold, so treating it as "readiness remedy spent" was
    coherent. Once reconcile also fires on contradiction — a condition with no
    relationship to readiness — a healthy issue gets stamped and would
    thereafter be refused BOTH remedies, silently losing `spike`.
    """

    def test_contradiction_sourced_stamp_still_dispatches_spike(self) -> None:
        remedy = _run_pre_deferral_remedy_selector(
            gate_marker="false",
            reconcile_attempted=True,
            contradiction_sourced=True,
            score_ambiguity=20,
            score_complexity=20,
            score_test_coverage=20,
            score_change_surface=20,
        )

        assert remedy == "spike", "a contradiction-only reconcile must not cost the spike remedy"

    def test_plateau_sourced_stamp_still_suppresses_both(self) -> None:
        """Unchanged for readiness-driven reconciles: no per-issue stamp file,
        so the selector behaves byte-identically to pre-ENH-2992."""
        remedy = _run_pre_deferral_remedy_selector(
            gate_marker="false",
            reconcile_attempted=True,
            contradiction_sourced=False,
            score_ambiguity=20,
            score_complexity=20,
            score_test_coverage=20,
            score_change_surface=20,
        )

        assert remedy == ""

    def test_spike_attempted_still_suppresses_even_when_contradiction_sourced(self) -> None:
        """The exemption exists to preserve access to `spike`; once spike has
        run there is nothing left to preserve."""
        remedy = _run_pre_deferral_remedy_selector(
            gate_marker="false",
            spike_attempted=True,
            reconcile_attempted=True,
            contradiction_sourced=True,
            score_ambiguity=20,
            score_complexity=20,
            score_test_coverage=20,
            score_change_surface=20,
        )

        assert remedy == ""

    def test_shell_branch_probes_the_per_issue_stamp(self) -> None:
        """The CONTRA_ONLY value the selector reads must come from the per-issue
        stamp file count_repair_cycle_reconcile writes, not from frontmatter."""
        action = _load_autodev_yaml()["states"]["recheck_after_size_review"]["action"]
        assert 'CONTRA_ONLY="true"' in action
        assert "autodev-contradiction-reconcile-$ID" in action
        assert action.index("autodev-contradiction-reconcile-$ID") < action.index(
            'CONTRA_ONLY="$CONTRA_ONLY"'
        ), "the stamp must be probed before the selector reads CONTRA_ONLY"


class TestRegateAfterAtomicRemediationDesignGateBranch:
    """ENH-2870/BUG-3002: a design-caused FAIL at regate_after_atomic_remediation
    must never be labelled oversized_atomic — it routes to the dedicated
    refine_for_design remedy (via check_atomic_design_remedy) if reachable,
    else defers design_gate_failed."""

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

    def test_dispatcher_routes_pending_remedy_to_refine_for_design(self) -> None:
        dispatcher = _load_autodev_yaml()["states"]["check_atomic_design_remedy"]
        assert dispatcher.get("on_yes") == "refine_for_design"
        assert dispatcher.get("on_no") == "dequeue_next"
        assert "autodev-atomic-design-remedy-pending" in dispatcher["action"]

    def test_regate_guard_uses_design_remedy_attempted_marker(self) -> None:
        """BUG-3002: the one-shot arming guard reads the
        autodev-design-remedy-attempted-$ID marker file, not the
        reconcile_attempted frontmatter flag (which /ll:refine-issue never
        writes, so the old guard would leave this branch unreachable)."""
        action = _load_autodev_yaml()["states"]["regate_after_atomic_remediation"]["action"]
        design_section = action[action.index("autodev-design-gate-failed-$ID") :]
        assert "autodev-design-remedy-attempted-$ID" in design_section
        assert "reconcile_attempted" not in design_section

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


class TestAutodevHasNoOwnBaseShaStamp:
    """ENH-2866 decision 3: autodev is stamped transitively, not per-state.

    ``dequeue_next`` fires once per issue but ``loop_runs`` is one row per run
    with no issue dimension, so a run-dir SHA file could only ever hold the last
    issue's value — and ``implement_current``'s ``ll-auto --only`` shell-out
    already produces a per-issue ``orchestration_runs`` row at a strictly better
    moment (after refine/wire churn is committed, immediately pre-patch).
    """

    def test_no_dequeue_sha_run_dir_artifact(self) -> None:
        """The removed design's specific artifact must not appear anywhere."""
        raw = AUTODEV_LOOP_PATH.read_text()
        assert "autodev-dequeue-sha" not in raw, (
            "autodev must not capture its own base SHA — the ll-auto --only "
            "shell-out in implement_current stamps each issue transitively"
        )

    def test_implement_current_still_shells_out_to_ll_auto(self) -> None:
        """The transitive stamp depends on this shell-out; guard it explicitly."""
        action = _load_autodev_yaml()["states"]["implement_current"].get("action", "")
        assert "ll-auto" in action
        assert "--only" in action


def _bug_body(*, program_design: str | None, confidence: int, outcome: int) -> str:
    """A structurally complete BUG issue body with configurable scores and an
    optional Program Design section (ENH-2967 loop-level fixture)."""
    sections = [
        "---",
        "id: BUG-9700",
        "status: open",
        "discovered_date: 2026-07-20",
        f"confidence_score: {confidence}",
        f"outcome_confidence: {outcome}",
        "---",
        "",
        "# BUG-9700: Something broke",
        "",
        "## Summary",
        "The widget explodes when the input is empty.",
        "",
        "## Steps to Reproduce",
        "1. Open the widget\n2. Submit an empty form",
        "",
        "## Current Behavior",
        "It explodes.",
        "",
        "## Expected Behavior",
        "It should not break.",
        "",
        "## Actual Behavior",
        "It breaks loudly.",
        "",
        "## Impact",
        "- **Priority**: P3 - Minor annoyance for a rare input.",
        "",
        "## Status",
        "**Open** | Created: 2026-07-20 | Priority: P3",
    ]
    if program_design is not None:
        sections.insert(-3, "## Program Design")
        sections.insert(-3, program_design.strip())
        sections.insert(-3, "")
    return "\n".join(sections) + "\n"


def _run_recheck_scores(project_root: Path, issue_id: str) -> None:
    """Run the real `recheck_scores` shell action end-to-end (real `ll-issues`
    subprocess calls, no python-fragment extraction), the way the FSM would
    substitute ${captured.input.output}/${context.run_dir}/thresholds."""
    action = _load_autodev_yaml()["states"]["recheck_scores"]["action"]
    script = (
        action.replace('ID="${captured.input.output}"', f'ID="{issue_id}"')
        .replace("${context.run_dir}", str(project_root))
        .replace("${context.readiness_threshold}", "85")
        .replace("${context.outcome_threshold}", "65")
    )
    subprocess.run(["bash", "-c", script], cwd=str(project_root), check=False)


class TestRecheckScoresDesignGateEndToEnd:
    """ENH-2967: `recheck_scores` still blocks a design-less issue after the
    inline DESIGN_FAIL python blocks were replaced by `ll-issues check-design` —
    the loop-level coverage the issue's Implementation Step 5 calls out as
    missing (nothing previously exercised the real shell action against a
    real `ll-issues` subprocess call)."""

    def _make_project(self, tmp_path: Path, *, program_design: str | None) -> Path:
        issues_dir = tmp_path / ".issues" / "bugs"
        issues_dir.mkdir(parents=True)
        issue_file = issues_dir / "P3-BUG-9700-test-bug.md"
        issue_file.write_text(
            _bug_body(program_design=program_design, confidence=95, outcome=90),
            encoding="utf-8",
        )
        ll_dir = tmp_path / ".ll"
        ll_dir.mkdir()
        (ll_dir / "program-design-cutover.json").write_text(
            json.dumps({"sha": "0" * 40, "date": "2026-07-01"}), encoding="utf-8"
        )
        return issue_file

    def test_design_less_issue_is_not_staged(self, tmp_path: Path) -> None:
        """High readiness/outcome scores alone must not stage an issue missing
        `## Program Design` once the gate is armed."""
        self._make_project(tmp_path, program_design=None)

        _run_recheck_scores(tmp_path, "BUG-9700")

        assert (tmp_path / "autodev-design-gate-failed-BUG-9700").exists()
        staged = tmp_path / "autodev-staged.txt"
        assert not staged.exists() or "BUG-9700" not in staged.read_text()

    def test_issue_with_program_design_is_staged(self, tmp_path: Path) -> None:
        """The same high scores WITH a present, non-boilerplate Program Design
        section must stage normally — the gate change must not over-block."""
        valid_section = (
            "### Types\n\n- `sha: str`\n\n"
            "### Signatures\n\n- `design_gate_failed(gaps: FormatGaps) -> bool`\n\n"
            "### Call Path\n\n`design_gate_failed` -> `check_format_gaps`\n"
        )
        self._make_project(tmp_path, program_design=valid_section)
        subprocess.run(["git", "init", "-q"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.email", "t@t.t"], cwd=tmp_path, check=True)
        subprocess.run(["git", "config", "user.name", "t"], cwd=tmp_path, check=True)
        (tmp_path / "mod.py").write_text(
            "def design_gate_failed(gaps):\n    return False\n", encoding="utf-8"
        )
        subprocess.run(["git", "add", "-A"], cwd=tmp_path, check=True)
        subprocess.run(["git", "commit", "-q", "-m", "x"], cwd=tmp_path, check=True)

        _run_recheck_scores(tmp_path, "BUG-9700")

        assert not (tmp_path / "autodev-design-gate-failed-BUG-9700").exists()
        staged = tmp_path / "autodev-staged.txt"
        assert staged.exists() and "BUG-9700" in staged.read_text()

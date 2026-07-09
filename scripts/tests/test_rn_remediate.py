"""Tests for the rn-remediate standalone sub-loop.

Extracted from test_rn_implement.py as part of ENH-1938 (decompose
rn-implement.yaml monolith into sub-loops).
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import yaml

from little_loops.fsm import is_runnable_loop
from little_loops.fsm.validation import (
    ValidationSeverity,
    load_and_validate,
    validate_fsm,
)

LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
RN_REMEDIATE_PATH = LOOPS_DIR / "rn-remediate.yaml"


def _load_loop() -> dict:
    """Load the rn-remediate YAML file."""
    with open(RN_REMEDIATE_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# TestAssessAndScorePersistence — States: assess, verify_scores_persisted
# ---------------------------------------------------------------------------


class TestAssessAndScorePersistence:
    """Tests for the confidence-check invocation and score persistence."""

    def test_assess_is_slash_command(self) -> None:
        """assess invokes confidence-check as a slash_command."""
        data = _load_loop()
        assess = data["states"]["assess"]
        assert assess["action_type"] == "slash_command"
        assert "/ll:confidence-check" in assess["action"]

    def test_assess_wraps_with_rate_limit_handling(self) -> None:
        """assess uses with_rate_limit_handling fragment."""
        data = _load_loop()
        assess = data["states"]["assess"]
        assert assess.get("fragment") == "with_rate_limit_handling"

    def test_assess_rate_limit_exhausted_routes_to_diagnostic(self) -> None:
        """assess routes to rate_limit_diagnostic on rate limit exhaustion."""
        data = _load_loop()
        assess = data["states"]["assess"]
        assert assess["on_rate_limit_exhausted"] == "rate_limit_diagnostic"

    def test_assess_on_no_routes_to_refine_first(self) -> None:
        """assess routes no → refine_first (ENH-2247).

        First-pass scoring on an unscored issue is not a content diagnosis, so it
        uses the lighter refine_first (--auto), not the destructive refine.
        """
        data = _load_loop()
        assess = data["states"]["assess"]
        assert assess["on_no"] == "refine_first"

    def test_verify_scores_persisted_uses_exit_code_evaluator(self) -> None:
        """verify_scores_persisted uses exit_code evaluator (not output_numeric)."""
        data = _load_loop()
        vsp = data["states"]["verify_scores_persisted"]
        assert vsp.get("action_type") == "shell"
        assert vsp.get("fragment") is None
        assert vsp.get("evaluate", {}).get("type") == "exit_code"

    def test_verify_scores_persisted_checks_frontmatter(self) -> None:
        """verify_scores_persisted validates confidence_score and outcome_confidence."""
        data = _load_loop()
        vsp = data["states"]["verify_scores_persisted"]
        assert "confidence_score:" in vsp["action"]
        assert "outcome_confidence:" in vsp["action"]

    def test_verify_scores_persisted_writes_pre_scores(self) -> None:
        """verify_scores_persisted writes pre_scores JSON to run_dir."""
        data = _load_loop()
        vsp = data["states"]["verify_scores_persisted"]
        assert "pre_scores_" in vsp["action"]

    def test_verify_scores_persisted_on_no_routes_to_failed(self) -> None:
        """verify_scores_persisted routes to failed when retries exhausted."""
        data = _load_loop()
        vsp = data["states"]["verify_scores_persisted"]
        assert vsp["on_no"] == "emit_scores_missing"


# ---------------------------------------------------------------------------
# TestReadinessAndDecisionGates — States: check_readiness, check_outcome, check_decision_needed
# ---------------------------------------------------------------------------


class TestReadinessAndDecisionGates:
    """Tests for the readiness gate, outcome gate, and decision flag."""

    def test_check_readiness_uses_shell_exit(self) -> None:
        """check_readiness uses shell_exit fragment (exit_code evaluator)."""
        data = _load_loop()
        cr = data["states"]["check_readiness"]
        assert cr.get("fragment") == "shell_exit"

    def test_check_readiness_routes_yes_to_implement(self) -> None:
        """check_readiness routes to check_complexity_pre_implement when readiness passes."""
        data = _load_loop()
        cr = data["states"]["check_readiness"]
        assert cr["on_yes"] == "check_complexity_pre_implement"

    def test_check_readiness_routes_no_to_check_outcome(self) -> None:
        """check_readiness routes to check_outcome when readiness fails."""
        data = _load_loop()
        cr = data["states"]["check_readiness"]
        assert cr["on_no"] == "check_outcome"

    def test_check_outcome_uses_shell_exit(self) -> None:
        """check_outcome uses shell_exit fragment."""
        data = _load_loop()
        co = data["states"]["check_outcome"]
        assert co.get("fragment") == "shell_exit"

    def test_check_outcome_uses_outcome_threshold_context(self) -> None:
        """check_outcome reads context.outcome_threshold."""
        data = _load_loop()
        co = data["states"]["check_outcome"]
        assert "${context.outcome_threshold}" in co["action"]

    def test_check_outcome_routes_yes_to_refine(self) -> None:
        """check_outcome routes to check_wire_needed_outcome when outcome passes (BUG-2007 Defect 4).

        When check_readiness fails the joint gate but check_outcome passes the
        outcome-only test, the deficiency is in confidence_score. Routing to
        diagnose was a dead path — its IMPLEMENT branch requires both thresholds,
        which check_readiness already found false. check_wire_needed_outcome gates
        wiring before routing to refine so the confidence gap is addressed correctly.
        """
        data = _load_loop()
        co = data["states"]["check_outcome"]
        assert co["on_yes"] == "check_wire_needed_outcome"

    def test_check_outcome_routes_no_to_check_decision_needed(self) -> None:
        """check_outcome routes to check_decision_needed when outcome fails."""
        data = _load_loop()
        co = data["states"]["check_outcome"]
        assert co["on_no"] == "check_decision_needed"

    def test_check_wire_needed_outcome_routes_no_and_error_to_refine_first(self) -> None:
        """check_wire_needed_outcome routes no/error → refine_first (ENH-2247).

        Reached when outcome already passes but readiness fails (confidence is the
        gap) and an integration map is present — a score-threshold trigger, not a
        content diagnosis. ENH-2247 closed this gap (the issue's original caller list
        omitted it) so it no longer hits the destructive refine.
        """
        data = _load_loop()
        cwno = data["states"]["check_wire_needed_outcome"]
        assert cwno["on_yes"] == "wire"
        assert cwno["on_no"] == "refine_first"
        assert cwno["on_error"] == "refine_first"

    def test_check_decision_needed_uses_check_flag(self) -> None:
        """check_decision_needed uses ll-issues check-flag."""
        data = _load_loop()
        cdn = data["states"]["check_decision_needed"]
        assert "ll-issues check-flag" in cdn["action"]
        assert "decision_needed" in cdn["action"]

    def test_check_decision_needed_routes_yes_to_decide(self) -> None:
        """check_decision_needed routes to check_decision_decidable when flag is true
        (ENH-2443: a validation gate now sits between check_decision_needed and decide)."""
        data = _load_loop()
        cdn = data["states"]["check_decision_needed"]
        assert cdn["on_yes"] == "check_decision_decidable"

    def test_check_decision_needed_routes_no_to_diagnose(self) -> None:
        """check_decision_needed routes to diagnose when flag is false."""
        data = _load_loop()
        cdn = data["states"]["check_decision_needed"]
        assert cdn["on_no"] == "diagnose"


# ---------------------------------------------------------------------------
# TestCheckDecisionDecidableState — State: check_decision_decidable (ENH-2443)
# ---------------------------------------------------------------------------


class TestCheckDecisionDecidableState:
    """check_decision_decidable validates before decide (ENH-2443)."""

    def test_state_exists_and_uses_shell_exit(self) -> None:
        data = _load_loop()
        cdd = data["states"]["check_decision_decidable"]
        assert cdd.get("fragment") == "shell_exit"

    def test_action_calls_check_decidable_cli(self) -> None:
        """Uses the deterministic ll-issues check-decidable companion CLI, not the
        LLM skill directly — shell states cannot dispatch slash commands."""
        data = _load_loop()
        cdd = data["states"]["check_decision_decidable"]
        assert "ll-issues check-decidable" in cdd["action"]

    def test_routes_yes_to_decide(self) -> None:
        data = _load_loop()
        cdd = data["states"]["check_decision_decidable"]
        assert cdd["on_yes"] == "decide"

    def test_routes_no_to_deposit_options(self) -> None:
        data = _load_loop()
        cdd = data["states"]["check_decision_decidable"]
        assert cdd["on_no"] == "deposit_options"

    def test_fail_open_on_error(self) -> None:
        """A validation-tooling error still routes to decide (fail-open, mirrors
        check_decision_needed_post)."""
        data = _load_loop()
        cdd = data["states"]["check_decision_decidable"]
        assert cdd["on_error"] == "decide"

    def test_marker_bounded_second_pass_short_circuits(self) -> None:
        """The marker check comes before invoking the CLI, so a second pass through
        this state skips re-validation entirely once deposit_options has run."""
        data = _load_loop()
        action = data["states"]["check_decision_decidable"]["action"]
        assert "decide_options_deposited_${context.issue_id}.txt" in action
        assert action.index("if [") < action.index("ll-issues check-decidable")


# ---------------------------------------------------------------------------
# TestDepositOptionsState — States: deposit_options, record_options_deposited
#   (ENH-2443)
# ---------------------------------------------------------------------------


class TestDepositOptionsState:
    """deposit_options runs /ll:refine-issue --auto to deposit options (ENH-2443)."""

    def test_uses_with_rate_limit_handling(self) -> None:
        data = _load_loop()
        do = data["states"]["deposit_options"]
        assert do.get("fragment") == "with_rate_limit_handling"

    def test_action_is_refine_issue_auto_no_full_rewrite(self) -> None:
        data = _load_loop()
        do = data["states"]["deposit_options"]
        assert do["action_type"] == "slash_command"
        assert "/ll:refine-issue" in do["action"]
        assert "--auto" in do["action"]
        assert "--full-rewrite" not in do["action"]

    def test_routes_yes_and_partial_to_record_marker(self) -> None:
        data = _load_loop()
        do = data["states"]["deposit_options"]
        assert do["on_yes"] == "record_options_deposited"
        assert do["on_partial"] == "record_options_deposited"

    def test_routes_no_and_error_to_decide(self) -> None:
        """Falls through to decide with no enumerable options if refine also can't
        deposit — check_convergence still escalates, now with a distinguishable token."""
        data = _load_loop()
        do = data["states"]["deposit_options"]
        assert do["on_no"] == "decide"
        assert do["on_error"] == "decide"

    def test_rate_limit_exhausted_routes_to_diagnostic(self) -> None:
        data = _load_loop()
        do = data["states"]["deposit_options"]
        assert do["on_rate_limit_exhausted"] == "rate_limit_diagnostic"


class TestRecordOptionsDepositedState:
    """record_options_deposited writes the write-once marker (ENH-2443)."""

    def test_writes_per_issue_marker(self) -> None:
        data = _load_loop()
        rod = data["states"]["record_options_deposited"]
        assert rod["action_type"] == "shell"
        assert "decide_options_deposited_${context.issue_id}.txt" in rod["action"]

    def test_routes_to_open_question_progress(self) -> None:
        """ENH-2446: record_options_deposited -> check_open_question_progress (progress gate),
        not directly back to check_decision_decidable. The progress gate decides
        whether to retry (on_yes -> check_decision_decidable) or fall through to
        decide (on_no / on_error).
        """
        data = _load_loop()
        rod = data["states"]["record_options_deposited"]
        assert rod["next"] == "check_open_question_progress"

    def test_open_question_progress_state_exists(self) -> None:
        """ENH-2446: new check_open_question_progress state sits between
        record_options_deposited and check_decision_decidable, gates re-fire
        on the open_question_stall evaluator.
        """
        data = _load_loop()
        cop = data["states"]["check_open_question_progress"]
        assert cop.get("fragment") == "open_question_stall_gate"
        assert cop["on_yes"] == "check_decision_decidable"
        assert cop["on_no"] == "decide"
        assert cop["on_error"] == "decide"


class TestDecisionDecidableFlow:
    """State-flow walk: check_decision_needed -> check_decision_decidable (no) ->
    deposit_options -> record_options_deposited -> check_open_question_progress (yes) ->
    check_decision_decidable (yes) -> decide (ENH-2443 + ENH-2446)."""

    def test_full_retry_loop_reaches_decide(self) -> None:
        data = _load_loop()
        states = data["states"]

        assert states["check_decision_needed"]["on_yes"] == "check_decision_decidable"
        assert states["check_decision_decidable"]["on_no"] == "deposit_options"
        assert states["deposit_options"]["on_yes"] == "record_options_deposited"
        assert states["record_options_deposited"]["next"] == "check_open_question_progress"
        # ENH-2446: progress gate routes on_yes back to check_decision_decidable,
        # which on the second pass short-circuits via marker file -> decide.
        assert states["check_open_question_progress"]["on_yes"] == "check_decision_decidable"
        assert states["check_decision_decidable"]["on_yes"] == "decide"


class TestCheckDecisionDecidableCoverageAware:
    """ENH-2446: check_decision_decidable chains the coverage-aware
    check-open-questions probe before the ENH-2443 check-decidable fallback."""

    def test_chains_check_open_questions_first(self) -> None:
        data = _load_loop()
        action = data["states"]["check_decision_decidable"]["action"]
        assert "check-open-questions" in action
        # The chained probe runs BEFORE check-decidable — coverage gap detection
        # takes precedence so the mixed case (resolved options + open questions)
        # routes to deposit_options instead of straight to decide.
        assert action.index("check-open-questions") < action.index("check-decidable")


class TestManualReviewRecommendedToken:
    """emit_needs_manual_review distinguishes MANUAL_REVIEW_RECOMMENDED from
    MANUAL_REVIEW_NEEDED via the deposit-options marker (ENH-2443)."""

    def test_checks_marker_file(self) -> None:
        data = _load_loop()
        action = data["states"]["emit_needs_manual_review"]["action"]
        assert "decide_options_deposited_${context.issue_id}.txt" in action

    def test_emits_both_tokens(self) -> None:
        data = _load_loop()
        action = data["states"]["emit_needs_manual_review"]["action"]
        assert "MANUAL_REVIEW_RECOMMENDED" in action
        assert "MANUAL_REVIEW_NEEDED" in action

    def test_still_writes_subloop_outcome_file(self) -> None:
        data = _load_loop()
        action = data["states"]["emit_needs_manual_review"]["action"]
        assert "subloop_outcome_${context.issue_id}.txt" in action

    def test_writes_manual_review_handoff_md(self) -> None:
        """ENH-2530: emit_needs_manual_review also writes a per-issue handoff markdown
        under ${context.run_dir}/ alongside the existing token sidecar."""
        data = _load_loop()
        action = data["states"]["emit_needs_manual_review"]["action"]
        assert "manual_review_handoff_" in action, (
            "emit_needs_manual_review must write manual_review_handoff_<ID>.md "
            "(ENH-2530) — per-issue diagnostic for human operators"
        )
        assert "${context.issue_id}" in action, (
            "handoff filename must scope to the per-issue ID via ${context.issue_id}"
        )
        assert "${context.run_dir}" in action, (
            "handoff file must live under ${context.run_dir}/ per MR-3"
        )


# ---------------------------------------------------------------------------
# TestDiagnoseRouting — States: diagnose (classify evaluator + route: table)
# ---------------------------------------------------------------------------


class TestDiagnoseRouting:
    """Tests for the dimensional diagnosis state and classify-based route: table."""

    def test_diagnose_is_shell_action(self) -> None:
        """diagnose state is action_type: shell."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        assert diag["action_type"] == "shell"

    def test_diagnose_has_classify_evaluator(self) -> None:
        """diagnose uses classify evaluator and has no capture field."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        assert diag.get("evaluate", {}).get("type") == "classify"
        assert diag.get("capture") is None

    def test_diagnose_uses_json_keys_not_frontmatter_names(self) -> None:
        """diagnose uses JSON keys (.confidence, .outcome), not frontmatter names."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        action = diag["action"]
        assert ".confidence" in action
        assert ".outcome" in action
        assert ".score_complexity" in action
        assert ".score_ambiguity" in action
        assert ".score_change_surface" in action

    def test_diagnose_outputs_all_routing_tokens(self) -> None:
        """diagnose shell script contains all routing tokens including REFINE_LIGHT.

        ENH-2223: the catch-all else branch now outputs REFINE_LIGHT (lighter
        --auto refine without --full-rewrite) instead of REFINE.
        """
        data = _load_loop()
        diag = data["states"]["diagnose"]
        action = diag["action"]
        for token in ("IMPLEMENT", "DECIDE", "WIRE", "REFINE", "REFINE_LIGHT", "DECOMPOSE"):
            assert f'echo "{token}"' in action or f'"{token}"' in action, (
                f"diagnose must output {token}"
            )

    def test_diagnose_has_implement_threshold_logic(self) -> None:
        """diagnose checks confidence >= readiness AND outcome >= outcome thresholds."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        action = diag["action"]
        assert "CONFIDENCE" in action
        assert "OUTCOME" in action
        assert "READINESS_THRESHOLD" in action or "ge" in action

    def test_diagnose_on_error_routes_to_failed(self) -> None:
        """diagnose _error arm in route: table routes to emit_implement_failed."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        assert diag["route"]["_error"] == "emit_implement_failed"

    def test_diagnose_route_table_covers_all_tokens(self) -> None:
        """diagnose route: table maps all tokens + default + error to correct targets.

        ENH-2223: REFINE_LIGHT token added — maps to refine_light (--auto without
        --full-rewrite) for residual minor gaps in the catch-all branch.
        """
        data = _load_loop()
        route = data["states"]["diagnose"]["route"]
        # IMPLEMENT goes through the marker-gate
        assert route["IMPLEMENT"] == "gate_implement"
        assert route["DECIDE"] == "decide"
        assert route["WIRE"] == "wire"
        assert route["REFINE"] == "refine"
        assert route["REFINE_LIGHT"] == "refine_light"
        assert route["DECOMPOSE"] == "emit_needs_decompose"
        # unmatched token fallback
        assert route["_"] == "emit_implement_failed"
        # shell non-zero exit arm
        assert route["_error"] == "emit_implement_failed"

    def test_diagnose_logs_to_diagnosis_json(self) -> None:
        """diagnose writes structured diagnosis data to run_dir."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        assert "diagnosis_" in diag["action"]
        assert ".json" in diag["action"]


# ---------------------------------------------------------------------------
# TestRemediationActions — States: implement, decide, wire, refine
# ---------------------------------------------------------------------------


class TestRemediationActions:
    """Tests for the four remediation action states."""

    def test_implement_is_shell_action(self) -> None:
        """implement invokes ll-auto --only as a shell command."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl["action_type"] == "shell"
        assert "ll-auto --only" in impl["action"]

    def test_implement_routes_to_done(self) -> None:
        """implement routes to run_code_gate on success (FEAT-2552) — the gate is the
        final arbiter of IMPLEMENTED. The previous direct-to-emit_implemented route
        is intentionally broken; gate → emit_implemented on pass / record_gate_failure
        on fail. Queue management stays in parent."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl["on_yes"] == "run_code_gate"

    def test_implement_failure_routes_to_failed(self) -> None:
        """implement routes to check_learning_gate on failure — the learning-gate check
        (550659db) is first in the failure chain, falling through to the auth guard
        (check_impl_auth) and then emit_implement_failed."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl["on_no"] == "check_learning_gate"
        assert impl["on_error"] == "check_learning_gate"

    def test_decide_is_slash_command_with_auto(self) -> None:
        """decide invokes /ll:decide-issue --auto as a slash_command."""
        data = _load_loop()
        dec = data["states"]["decide"]
        assert dec["action_type"] == "slash_command"
        assert "/ll:decide-issue" in dec["action"]
        assert "--auto" in dec["action"]

    def test_decide_wraps_with_rate_limit_handling(self) -> None:
        """decide uses with_rate_limit_handling fragment."""
        data = _load_loop()
        dec = data["states"]["decide"]
        assert dec.get("fragment") == "with_rate_limit_handling"

    def test_decide_routes_to_re_assess_on_yes(self) -> None:
        """decide routes to re_assess on yes (decision recorded → re-evaluate scores).

        BUG-2169: decide/wire/refine use on_yes/on_no/on_partial (slash_command routing),
        not on_success/on_error (sub-loop delegation routing).
        ENH-2307: on_yes stays re_assess; on_no/on_error route to emit_implement_failed.
        """
        data = _load_loop()
        dec = data["states"]["decide"]
        assert dec["on_yes"] == "re_assess"
        assert dec["on_partial"] == "re_assess"

    def test_decide_failure_routes_to_emit_implement_failed(self) -> None:
        """decide routes on_no → emit_needs_manual_review, on_error → emit_implement_failed (BUG-2396).

        When /ll:decide-issue --auto cannot auto-resolve (author-gated decision), the loop
        classifies the outcome as MANUAL_REVIEW_NEEDED, not an implementation failure.
        on_error (genuine infra crash) still routes to emit_implement_failed.
        """
        data = _load_loop()
        dec = data["states"]["decide"]
        assert dec["on_no"] == "emit_needs_manual_review"
        assert dec["on_error"] == "emit_implement_failed"

    def test_wire_is_slash_command_with_auto(self) -> None:
        """wire invokes /ll:wire-issue --auto as a slash_command."""
        data = _load_loop()
        wire = data["states"]["wire"]
        assert wire["action_type"] == "slash_command"
        assert "/ll:wire-issue" in wire["action"]
        assert "--auto" in wire["action"]

    def test_wire_routes_through_mark_wired_on_success(self) -> None:
        """wire routes through mark_wired on yes/partial (BUG-2007 Defect 1).

        Marker-gate: on_yes/on_partial hop through mark_wired (which sets the wired
        marker, then continues to check_decision_needed_post) so the pre-implement
        gate can confirm a wire ran. BUG-2222: mark_wired continues to
        check_decision_needed_post so wiring that sets decision_needed:true routes
        to /ll:decide-issue automatically. ENH-2247: on_no routes to refine_first
        (--auto), not the destructive refine — a wiring failure is an integration-map
        problem, not a prose-content problem, so a full rewrite is not warranted.

        BUG-2169: uses slash_command routing (on_yes/on_no/on_partial), not
        sub-loop delegation keys (on_success/on_error).
        """
        data = _load_loop()
        wire = data["states"]["wire"]
        assert wire["on_yes"] == "mark_wired"
        assert wire["on_partial"] == "mark_wired"
        assert data["states"]["mark_wired"]["next"] == "check_decision_needed_post"
        assert wire["on_no"] == "refine_first"

    def test_refine_uses_full_rewrite_flag(self) -> None:
        """refine uses --full-rewrite flag."""
        data = _load_loop()
        ref = data["states"]["refine"]
        assert "--full-rewrite" in ref["action"]

    def test_refine_routes_through_mark_refined(self) -> None:
        """refine routes through mark_refined on yes/partial (marker-gate).

        BUG-2169: uses slash_command routing (on_yes/on_partial), not on_success.
        BUG-2222: mark_refined continues to check_decision_needed_post so refinement
        that deposits decision options (decision_needed:true) routes to /ll:decide-issue.
        """
        data = _load_loop()
        ref = data["states"]["refine"]
        assert ref["on_yes"] == "mark_refined"
        assert ref["on_partial"] == "mark_refined"
        assert data["states"]["mark_refined"]["next"] == "check_decision_needed_post"

    def test_refine_failure_routes_to_failed(self) -> None:
        """refine routes to emit_implement_failed on no (slash_command on_no = LLM decline).

        BUG-2169: refine uses slash_command routing, so the failure path is on_no
        (the LLM refused/declined to refine), not on_error (infrastructure error).
        """
        data = _load_loop()
        ref = data["states"]["refine"]
        assert ref["on_no"] == "emit_implement_failed"

    def test_refine_light_exists_and_omits_full_rewrite(self) -> None:
        """refine_light uses --auto without --full-rewrite (ENH-2223).

        diagnose catch-all routes to refine_light so residual minor gaps don't
        get the destructive full-rewrite action.
        """
        data = _load_loop()
        rl = data["states"]["refine_light"]
        assert "/ll:refine-issue" in rl["action"]
        assert "--auto" in rl["action"]
        assert "--full-rewrite" not in rl["action"]

    def test_refine_light_routes_through_mark_refined(self) -> None:
        """refine_light routes through mark_refined on yes/partial (same as refine).

        Shares the same marker-gate path so gate_implement can confirm a refine
        pass occurred regardless of whether full or light refine ran.
        """
        data = _load_loop()
        rl = data["states"]["refine_light"]
        assert rl["on_yes"] == "mark_refined"
        assert rl["on_partial"] == "mark_refined"
        assert rl["on_no"] == "emit_implement_failed"

    def test_refine_first_exists_and_omits_full_rewrite(self) -> None:
        """refine_first uses --auto without --full-rewrite (ENH-2247).

        First-pass / policy-gate / wire-failure / confidence-gap callers route here
        so partially-correct content is patched, not bulldozed.
        """
        data = _load_loop()
        rf = data["states"]["refine_first"]
        assert "/ll:refine-issue" in rf["action"]
        assert "--auto" in rf["action"]
        assert "--full-rewrite" not in rf["action"]

    def test_refine_first_routes_through_mark_refined(self) -> None:
        """refine_first shares the marker-gate path (mark_refined on yes/partial)."""
        data = _load_loop()
        rf = data["states"]["refine_first"]
        assert rf["on_yes"] == "mark_refined"
        assert rf["on_partial"] == "mark_refined"
        assert rf["on_no"] == "emit_implement_failed"
        assert data["states"]["mark_refined"]["next"] == "check_decision_needed_post"

    def test_refine_followup_uses_gap_analysis_not_full_rewrite(self) -> None:
        """refine_followup uses --auto --gap-analysis without --full-rewrite (ENH-2247).

        re_assess on_no routes here: a full-rewrite already ran this cycle, so the
        follow-up patches remaining gaps additively instead of re-bulldozing.
        """
        data = _load_loop()
        rfu = data["states"]["refine_followup"]
        assert "/ll:refine-issue" in rfu["action"]
        assert "--auto" in rfu["action"]
        assert "--gap-analysis" in rfu["action"]
        assert "--full-rewrite" not in rfu["action"]

    def test_refine_followup_routes_through_mark_refined(self) -> None:
        """refine_followup shares the marker-gate path (mark_refined on yes/partial)."""
        data = _load_loop()
        rfu = data["states"]["refine_followup"]
        assert rfu["on_yes"] == "mark_refined"
        assert rfu["on_partial"] == "mark_refined"
        assert rfu["on_no"] == "emit_implement_failed"

    def test_only_diagnose_route_reaches_destructive_refine(self) -> None:
        """The destructive refine (--full-rewrite) is reachable ONLY from diagnose → REFINE.

        ENH-2247: every other caller (assess, gate_implement, wire,
        check_wire_needed_outcome, re_assess) routes to a lighter variant. This guards
        against a future re-route accidentally re-pointing a caller at the destructive
        state. Walk every transition key on every state and assert no state other than
        the diagnose route-table targets `refine`.
        """
        data = _load_loop()
        transition_keys = (
            "on_yes",
            "on_no",
            "on_partial",
            "on_success",
            "on_error",
            "on_failure",
            "on_rate_limit_exhausted",
            "next",
        )
        offenders = []
        for name, state in data["states"].items():
            if not isinstance(state, dict):
                continue
            for key in transition_keys:
                if state.get(key) == "refine":
                    offenders.append(f"{name}.{key}")
            # route: tables — only diagnose's REFINE entry is allowed
            for token, target in (state.get("route") or {}).items():
                if target == "refine" and not (name == "diagnose" and token == "REFINE"):
                    offenders.append(f"{name}.route.{token}")
        assert offenders == [], f"unexpected routes into destructive refine: {offenders}"
        # And confirm the one allowed route is intact.
        assert data["states"]["diagnose"]["route"]["REFINE"] == "refine"

    def test_check_complexity_pre_implement_on_yes_routes_to_wire_check(self) -> None:
        """check_complexity_pre_implement routes both bands to check_wire_pre_implement (ENH-2223).

        An issue that already passes the readiness gate (confidence >= 85, outcome >= 75)
        does not need --full-rewrite even if complexity is high. Both branches route
        to check_wire_pre_implement; ENH-2163 enforcement is applied by
        check_wire_pre_implement.on_no → gate_implement (BUG-2306).
        """
        data = _load_loop()
        ccpi = data["states"]["check_complexity_pre_implement"]
        assert ccpi["on_yes"] == "check_wire_pre_implement"
        assert ccpi["on_no"] == "check_wire_pre_implement"
        assert ccpi["on_error"] == "check_wire_pre_implement"

    def test_diagnose_catch_all_outputs_refine_light(self) -> None:
        """diagnose catch-all else branch outputs REFINE_LIGHT, not REFINE (ENH-2223).

        The final else branch applies only when no dimensional problem is detected
        (no high ambiguity, no high complexity, no low confidence, no high
        change_surface). A lighter --auto refine is appropriate for such minor gaps.
        """
        data = _load_loop()
        action = data["states"]["diagnose"]["action"]
        # The else block must output REFINE_LIGHT (not a bare REFINE)
        assert 'echo "REFINE_LIGHT"' in action
        # The bare catch-all REFINE must not appear after the DECOMPOSE branch
        # (dimensional REFINE branches earlier in the script are still valid)
        decompose_pos = action.index("DECOMPOSE")
        catchall_pos = action.index("REFINE_LIGHT")
        assert catchall_pos > decompose_pos, "REFINE_LIGHT catch-all must follow DECOMPOSE branch"


# ---------------------------------------------------------------------------
# TestMarkerGate — States: gate_implement, route_gate_refine, route_gate_wire,
#   mark_refined, mark_wired (require_refine_and_wire enforcement)
# ---------------------------------------------------------------------------


class TestMarkerGate:
    """An above-minimal-complexity issue must be refined AND wired at least once
    before implement. The gate is a marker-driven choke point in front of
    implement, fed by monotonic refined_/wired_ markers and a stable
    complexity_band snapshot."""

    def test_require_refine_and_wire_default_true(self) -> None:
        """The enforcement toggle defaults to true."""
        data = _load_loop()
        assert data["context"]["require_refine_and_wire"] is True

    def test_complexity_band_snapshotted_in_verify_scores_persisted(self) -> None:
        """verify_scores_persisted writes a stable complexity_band file (once)."""
        data = _load_loop()
        action = data["states"]["verify_scores_persisted"]["action"]
        assert "complexity_band_" in action
        assert "ABOVE_MINIMAL" in action
        assert "diagnose_complexity_threshold" in action

    def test_marker_writers_are_monotonic_and_route_to_decision_check(self) -> None:
        """mark_refined/mark_wired write a marker file and continue to check_decision_needed_post.

        BUG-2222: markers route through check_decision_needed_post (not directly to
        re_assess) so that a refinement/wiring pass that deposits decision options
        triggers /ll:decide-issue before the redundant confidence check.
        """
        data = _load_loop()
        mr = data["states"]["mark_refined"]
        mw = data["states"]["mark_wired"]
        assert "refined_" in mr["action"]
        assert mr["next"] == "check_decision_needed_post"
        assert "wired_" in mw["action"]
        assert mw["next"] == "check_decision_needed_post"

    def test_gate_emits_three_disjoint_tokens(self) -> None:
        """gate_implement emits IMPLEMENT / NEED_REFINE / NEED_WIRE and captures it."""
        data = _load_loop()
        gate = data["states"]["gate_implement"]
        assert gate["action_type"] == "shell"
        action = gate["action"]
        assert "NEED_REFINE" in action
        assert "NEED_WIRE" in action
        assert "IMPLEMENT" in action
        assert gate.get("capture") == "gate_decision"
        # Fail-open: a gate error implements rather than blocking.
        assert gate["on_error"] == "implement"

    def test_gate_honors_band_and_flag_short_circuits(self) -> None:
        """gate reads the require flag and the complexity band before requiring markers."""
        data = _load_loop()
        action = data["states"]["gate_implement"]["action"]
        assert "require_refine_and_wire" in action
        assert "ABOVE_MINIMAL" in action
        assert "refined_" in action
        assert "wired_" in action

    def test_gate_router_cascade_forces_refine_then_wire_then_implement(self) -> None:
        """route_gate_refine → refine_first; else route_gate_wire → wire; else implement.

        ENH-2247: the marker-policy gate is not a content diagnosis, so NEED_REFINE
        routes to the lighter refine_first (--auto), not the destructive refine.
        """
        data = _load_loop()
        gate = data["states"]["gate_implement"]
        assert gate["next"] == "route_gate_refine"
        rgr = data["states"]["route_gate_refine"]
        assert rgr["evaluate"]["type"] == "output_contains"
        assert "${captured.gate_decision.output}" in rgr["evaluate"]["source"]
        assert rgr["evaluate"]["pattern"] == "NEED_REFINE"
        assert rgr["on_yes"] == "refine_first"
        assert rgr["on_no"] == "route_gate_wire"
        assert rgr["on_error"] == "implement"
        rgw = data["states"]["route_gate_wire"]
        assert rgw["evaluate"]["pattern"] == "NEED_WIRE"
        assert rgw["on_yes"] == "wire"
        assert rgw["on_no"] == "implement"
        assert rgw["on_error"] == "implement"

    def test_above_minimal_entry_points_route_through_gate(self) -> None:
        """All above-minimal routes to implement go through gate_implement first (BUG-2306)."""
        data = _load_loop()
        # diagnose IMPLEMENT token routes through the marker-gate
        assert data["states"]["diagnose"]["route"]["IMPLEMENT"] == "gate_implement"
        # check_convergence CONVERGED_PASS token routes through the marker-gate
        assert data["states"]["check_convergence"]["route"]["CONVERGED_PASS"] == "gate_implement"
        # check_wire_pre_implement on_no (change_surface > 0) must also route through gate
        assert data["states"]["check_wire_pre_implement"]["on_no"] == "gate_implement"

    def test_wire_pre_implement_routes_nonzero_change_surface_to_gate(self) -> None:
        """check_wire_pre_implement on_no routes to gate_implement, not implement (BUG-2306).

        check_wire_pre_implement is reachable from BOTH complexity bands (both
        ABOVE_MINIMAL and MINIMAL route through check_complexity_pre_implement → here).
        A non-zero change_surface (on_no, exit 1) must go through gate_implement so
        ENH-2163 enforcement applies regardless of complexity band. Zero change_surface
        (on_yes) continues to wire. Errors fail open to implement.
        """
        data = _load_loop()
        cwpi = data["states"]["check_wire_pre_implement"]
        assert cwpi["on_no"] == "gate_implement"
        assert cwpi["on_error"] == "implement"


# ---------------------------------------------------------------------------
# TestReassessAndConvergence — States: re_assess, verify_re_assess_scores,
#   check_convergence, route_conv_pass, route_conv_improved
# ---------------------------------------------------------------------------


class TestReassessAndConvergence:
    """Tests for the re-assessment and convergence detection chain."""

    def test_re_assess_mirrors_assess_structure(self) -> None:
        """re_assess has the same structure as assess."""
        data = _load_loop()
        reassess = data["states"]["re_assess"]
        assert reassess["action_type"] == "slash_command"
        assert "/ll:confidence-check" in reassess["action"]
        assert reassess.get("fragment") == "with_rate_limit_handling"

    def test_re_assess_routes_to_verify_re_assess_scores(self) -> None:
        """re_assess routes to verify_re_assess_scores on success."""
        data = _load_loop()
        reassess = data["states"]["re_assess"]
        assert reassess["on_success"] == "verify_re_assess_scores"

    def test_re_assess_has_on_partial_route(self) -> None:
        """re_assess routes partial → verify_re_assess_scores (MR-4 — BUG-2115)."""
        data = _load_loop()
        reassess = data["states"]["re_assess"]
        assert reassess.get("on_partial") == "verify_re_assess_scores"

    def test_re_assess_has_on_no_route(self) -> None:
        """re_assess routes no → refine_followup (MR-4 — BUG-2115; ENH-2247).

        ENH-2247: a full-rewrite pass already ran this cycle, so the follow-up
        patches remaining gaps additively (refine_followup, --auto --gap-analysis)
        rather than re-bulldozing the first pass's improvements.
        """
        data = _load_loop()
        reassess = data["states"]["re_assess"]
        assert reassess.get("on_no") == "refine_followup"

    def test_verify_re_assess_scores_uses_exit_code_evaluator(self) -> None:
        """verify_re_assess_scores uses exit_code evaluator (not output_numeric)."""
        data = _load_loop()
        vras = data["states"]["verify_re_assess_scores"]
        assert vras.get("action_type") == "shell"
        assert vras.get("fragment") is None
        assert vras.get("evaluate", {}).get("type") == "exit_code"

    def test_verify_re_assess_scores_writes_post_scores(self) -> None:
        """verify_re_assess_scores writes post_scores JSON to run_dir."""
        data = _load_loop()
        vras = data["states"]["verify_re_assess_scores"]
        assert "post_scores_" in vras["action"]

    def test_verify_re_assess_scores_routes_to_check_convergence(self) -> None:
        """verify_re_assess_scores routes to check_convergence on success."""
        data = _load_loop()
        vras = data["states"]["verify_re_assess_scores"]
        assert vras["on_yes"] == "check_convergence"

    def test_check_convergence_is_shell_action(self) -> None:
        """check_convergence is a shell action."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        assert cc["action_type"] == "shell"

    def test_check_convergence_outputs_compound_tokens(self) -> None:
        """check_convergence outputs CONVERGED_PASS/IMPROVED/STALLED, not bare tokens."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        action = cc["action"]
        assert "CONVERGED_PASS" in action
        assert "CONVERGED_IMPROVED" in action
        assert "CONVERGED_STALLED" in action

    def test_check_convergence_no_bare_pass_token(self) -> None:
        """check_convergence does NOT output bare 'PASS' (regression guard)."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        action = cc["action"]
        # Check that bare PASS doesn't appear as a standalone echo
        lines = [ln.strip() for ln in action.split("\n")]
        for line in lines:
            if line.startswith('echo "') and "PASS" in line:
                assert "CONVERGED" in line, f"Line uses bare PASS without CONVERGED_ prefix: {line}"

    def test_check_convergence_computes_total_delta(self) -> None:
        """check_convergence computes TOTAL_DELTA from 4 score deltas."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        action = cc["action"]
        assert "TOTAL_DELTA" in action
        assert "DELTA_CONFIDENCE" in action
        assert "DELTA_OUTCOME" in action
        assert "DELTA_COMPLEXITY" in action
        assert "DELTA_AMBIGUITY" in action

    def test_check_convergence_increments_remediation_counter(self) -> None:
        """check_convergence increments the remediation counter."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        action = cc["action"]
        assert "remediation_count_" in action

    def test_check_convergence_has_classify_evaluator(self) -> None:
        """check_convergence uses classify evaluator and has no capture field."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        assert cc.get("evaluate", {}).get("type") == "classify"
        assert cc.get("capture") is None

    def test_convergence_router_chain_is_correct(self) -> None:
        """check_convergence route: table maps all tokens to correct targets."""
        data = _load_loop()
        route = data["states"]["check_convergence"]["route"]
        # CONVERGED_PASS → marker-gate (a PASS after single refine/wire/decide)
        assert route["CONVERGED_PASS"] == "gate_implement"
        # CONVERGED_IMPROVED → budget-gated retry (ENH-2107)
        assert route["CONVERGED_IMPROVED"] == "check_remediation_budget"
        # NEEDS_MANUAL_REVIEW → escalate
        assert route["NEEDS_MANUAL_REVIEW"] == "emit_needs_manual_review"
        # CONVERGED_STALLED → budget-gated retry (ENH-2107)
        assert route["CONVERGED_STALLED"] == "check_remediation_budget"
        # unmatched token fallback (safe: treat unknown stall as budget retry)
        assert route["_"] == "check_remediation_budget"
        # shell non-zero exit → fail-open like original on_error: route_conv_pass
        assert route["_error"] == "gate_implement"

    def test_check_convergence_route_table_covers_all_tokens(self) -> None:
        """check_convergence route: table has all 4 convergence tokens + default + error."""
        data = _load_loop()
        route = data["states"]["check_convergence"]["route"]
        required = {
            "CONVERGED_PASS",
            "CONVERGED_IMPROVED",
            "NEEDS_MANUAL_REVIEW",
            "CONVERGED_STALLED",
            "_",
            "_error",
        }
        assert required.issubset(set(route.keys())), (
            f"Missing route keys: {required - set(route.keys())}"
        )

    def test_check_convergence_writes_convergence_json(self) -> None:
        """check_convergence writes convergence data to run_dir."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        assert "convergence_" in cc["action"]
        assert ".json" in cc["action"]


# ---------------------------------------------------------------------------
# TestBug2007Fixes — Defect 2 (parameterized diagnose thresholds) and
#   Defect 3 (pass-over-pass pre_scores refresh in check_convergence)
# ---------------------------------------------------------------------------


class TestBug2007Fixes:
    """Regression tests for the four rn-remediate routing/convergence defects."""

    def test_diagnose_uses_context_thresholds_not_literals(self) -> None:
        """diagnose references context.diagnose_* keys, not hardcoded 15/50 (Defect 2)."""
        data = _load_loop()
        action = data["states"]["diagnose"]["action"]
        assert "${context.diagnose_ambiguity_threshold}" in action
        assert "${context.diagnose_complexity_threshold}" in action
        assert "${context.diagnose_change_surface_threshold}" in action
        assert "${context.diagnose_confidence_floor}" in action

    def test_diagnose_routing_has_no_bare_magic_literals(self) -> None:
        """diagnose routing comparisons no longer use bare -ge 15 / -lt 50 literals."""
        data = _load_loop()
        action = data["states"]["diagnose"]["action"]
        # The routing chain below the IMPLEMENT gate must not compare against the
        # old hardcoded magic numbers directly.
        assert "-ge 15" not in action, "Found hardcoded '-ge 15' in diagnose routing"
        assert "-lt 50" not in action, "Found hardcoded '-lt 50' in diagnose routing"

    def test_check_convergence_refreshes_pre_scores(self) -> None:
        """check_convergence overwrites pre_scores with post_scores (Defect 3).

        Without this, TOTAL_DELTA accumulates across the whole session instead of
        measuring the most recent pass, so a plateaued issue never emits
        CONVERGED_STALLED.
        """
        data = _load_loop()
        action = data["states"]["check_convergence"]["action"]
        # A cp from the post-scores file to the pre-scores file must be present so
        # the next pass measures pass-over-pass delta.
        assert "cp " in action
        assert "pre_scores_" in action
        assert "post_scores_" in action


# ---------------------------------------------------------------------------
# TestRemediationBudget — State: check_remediation_budget
# ---------------------------------------------------------------------------


class TestRemediationBudget:
    """Tests for the remediation budget gating state."""

    def test_check_remediation_budget_is_shell_action(self) -> None:
        """check_remediation_budget is a shell action."""
        data = _load_loop()
        crb = data["states"]["check_remediation_budget"]
        assert crb["action_type"] == "shell"

    def test_check_remediation_budget_uses_output_numeric(self) -> None:
        """check_remediation_budget uses output_numeric evaluator."""
        data = _load_loop()
        crb = data["states"]["check_remediation_budget"]
        evaluate = crb["evaluate"]
        assert evaluate["type"] == "output_numeric"
        assert evaluate["operator"] == "lt"

    def test_check_remediation_budget_target_matches_context(self) -> None:
        """check_remediation_budget target is context.max_remediation_passes."""
        data = _load_loop()
        crb = data["states"]["check_remediation_budget"]
        evaluate = crb["evaluate"]
        assert "${context.max_remediation_passes}" in evaluate["target"]

    def test_check_remediation_budget_routes_under_to_diagnose(self) -> None:
        """Under budget routes to diagnose (re-enter deepening loop)."""
        data = _load_loop()
        crb = data["states"]["check_remediation_budget"]
        assert crb["on_yes"] == "diagnose"

    def test_check_remediation_budget_routes_exhausted_to_failed(self) -> None:
        """Budget exhausted routes to the stall-token emitter (BUG-2006).

        Budget exhaustion is stall-adjacent: the automated moves ran out without
        convergence, so the parent should defer (not silently skip) if decompose
        also declines.
        """
        data = _load_loop()
        crb = data["states"]["check_remediation_budget"]
        assert crb["on_no"] == "emit_stalled_needs_decompose"

    def test_context_max_remediation_passes_set(self) -> None:
        """max_remediation_passes context variable is set to 3."""
        data = _load_loop()
        assert data["context"]["max_remediation_passes"] == 3


# =========================================================================
# Structural & Validation Tests (added per ENH-1938 wiring pass)
# =========================================================================


class TestParameterContract:
    """Tests for the rn-remediate parameter contract."""

    def test_parameters_block_has_required_fields(self) -> None:
        """parameters block declares issue_id, readiness_threshold, outcome_threshold,
        max_remediation_passes."""
        data = _load_loop()
        params = data["parameters"]
        assert "issue_id" in params
        assert "readiness_threshold" in params
        assert "outcome_threshold" in params
        assert "max_remediation_passes" in params

    def test_parameters_issue_id_is_required_string(self) -> None:
        """issue_id: type string, required true."""
        data = _load_loop()
        param = data["parameters"]["issue_id"]
        assert param["type"] == "string"
        assert param["required"] is True

    def test_parameters_thresholds_have_defaults(self) -> None:
        """readiness_threshold default 85, outcome_threshold default 75,
        max_remediation_passes default 3."""
        data = _load_loop()
        params = data["parameters"]
        assert params["readiness_threshold"]["type"] == "integer"
        assert params["outcome_threshold"]["type"] == "integer"
        assert params["max_remediation_passes"]["type"] == "integer"


class TestTerminalStates:
    """Tests for the bare terminal state pattern."""

    def test_done_terminal_is_bare(self) -> None:
        """done has terminal: true with no action body."""
        data = _load_loop()
        done = data["states"]["done"]
        assert done.get("terminal") is True
        assert "action" not in done, "done must be bare terminal (no action body)"

    def test_failed_terminal_is_bare(self) -> None:
        """failed has terminal: true with no action body."""
        data = _load_loop()
        failed = data["states"]["failed"]
        assert failed.get("terminal") is True
        assert "action" not in failed, "failed must be bare terminal (no action body)"


class TestTopLevelDeclarations:
    """Tests for required top-level fields and imports."""

    def test_name_is_rn_remediate(self) -> None:
        """Top-level name is 'rn-remediate'."""
        data = _load_loop()
        assert data["name"] == "rn-remediate"

    def test_imports_lib_common_yaml(self) -> None:
        """Top-level import includes lib/common.yaml."""
        data = _load_loop()
        assert "import" in data
        assert "lib/common.yaml" in data["import"]

    def test_on_handoff_is_spawn(self) -> None:
        """on_handoff is set to spawn (sub-loop contract)."""
        data = _load_loop()
        assert data["on_handoff"] == "spawn"

    def test_context_defaults_match_spec(self) -> None:
        """Context defaults match the parameter defaults."""
        data = _load_loop()
        ctx = data["context"]
        assert ctx["readiness_threshold"] == 85
        assert ctx["outcome_threshold"] == 75
        assert ctx["max_remediation_passes"] == 3

    def test_context_has_diagnose_thresholds(self) -> None:
        """Context exposes overridable diagnose routing thresholds (BUG-2007 Defect 2).

        Defaults preserve the prior hardcoded literals (15/15/15/50) so existing
        callers remain backward-compatible.
        """
        data = _load_loop()
        ctx = data["context"]
        assert ctx["diagnose_ambiguity_threshold"] == 15
        assert ctx["diagnose_complexity_threshold"] == 15
        assert ctx["diagnose_change_surface_threshold"] == 15
        assert ctx["diagnose_confidence_floor"] == 50


class TestFSMHealth:
    """End-to-end FSM validation and health checks."""

    def test_fsm_validates_without_errors(self) -> None:
        """rn-remediate.yaml loads and validates without errors."""
        fsm, warnings = load_and_validate(RN_REMEDIATE_PATH)
        assert fsm is not None, "FSM must load successfully"
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"Validation errors: {[str(e) for e in error_list]}"

    def test_yaml_parses_and_is_runnable(self) -> None:
        """rn-remediate.yaml parses as valid YAML and is detected as runnable."""
        data = _load_loop()
        assert isinstance(data, dict), "Root must be a mapping"
        assert is_runnable_loop(RN_REMEDIATE_PATH), "Must be detected as runnable"

    def test_mr1_non_llm_evaluators_present(self) -> None:
        """All LLM-invoking states are paired with non-LLM evaluators (MR-1)."""
        data = _load_loop()
        # Key routing states use non-LLM evaluators
        mr1_states = {
            "check_remediation_budget": "output_numeric",
            "check_readiness": "exit_code",
            "check_outcome": "exit_code",
            "check_decision_needed": "exit_code",
            "check_decision_decidable": "exit_code",
        }
        for state_name, _expected_eval_type in mr1_states.items():
            state = data["states"].get(state_name)
            assert state is not None, f"MR-1 state '{state_name}' not found"
            if state_name == "check_remediation_budget":
                evaluate = state.get("evaluate", {})
                assert evaluate.get("type") == "output_numeric", (
                    "check_remediation_budget must use output_numeric"
                )
            else:
                assert state.get("fragment") == "shell_exit", (
                    f"State '{state_name}' should use shell_exit fragment for exit_code"
                )

        # diagnose uses classify evaluator (non-LLM token dispatch)
        assert data["states"]["diagnose"]["evaluate"]["type"] == "classify"

        # check_convergence uses classify evaluator (non-LLM token dispatch)
        assert data["states"]["check_convergence"]["evaluate"]["type"] == "classify"

    def test_route_d_states_absent(self) -> None:
        """Deleted cascade states route_d_* must not exist in the states dict."""
        data = _load_loop()
        for name in ("route_d_implement", "route_d_decide", "route_d_wire", "route_d_refine"):
            assert name not in data["states"], f"Cascade state '{name}' should be deleted"

    def test_route_conv_states_absent(self) -> None:
        """Deleted cascade states route_conv_* must not exist in the states dict."""
        data = _load_loop()
        for name in ("route_conv_pass", "route_conv_improved", "route_conv_manual_review"):
            assert name not in data["states"], f"Cascade state '{name}' should be deleted"

    def test_mr3_run_dir_used_for_writes(self) -> None:
        """No state writes to .loops/tmp/ — all file writes use ${context.run_dir}/ (MR-3)."""
        data = _load_loop()
        for name, state in data["states"].items():
            action = state.get("action", "")
            if isinstance(action, str):
                assert ".loops/tmp/" not in action, (
                    f"State '{name}' writes to .loops/tmp/ — use ${{context.run_dir}}/ instead"
                )

    def test_all_states_reachable_from_initial(self) -> None:
        """Every operational state is reachable from assess."""
        data = _load_loop()
        state_names = set(data["states"].keys())

        routing_keys = (
            "next",
            "on_yes",
            "on_no",
            "on_error",
            "on_success",
            "on_failure",
            "on_rate_limit_exhausted",
        )
        reachable: set[str] = set()
        queue = [data.get("initial", "assess")]
        while queue:
            current = queue.pop(0)
            if current in reachable or current not in data["states"]:
                continue
            reachable.add(current)
            state = data["states"][current]
            for key in routing_keys:
                target = state.get(key)
                if target and isinstance(target, str) and target not in reachable:
                    queue.append(target)
            # Also traverse route: table entries (classify + route: pattern)
            for target in state.get("route", {}).values():
                if isinstance(target, str) and target not in reachable:
                    queue.append(target)

        unreachable = state_names - reachable
        assert not unreachable, f"Unreachable states: {sorted(unreachable)}"

    def test_all_referenced_targets_exist(self) -> None:
        """Every state referenced in routing exists in the states dict."""
        data = _load_loop()
        state_names = set(data["states"].keys())
        routing_keys = (
            "next",
            "on_yes",
            "on_no",
            "on_error",
            "on_success",
            "on_failure",
            "on_rate_limit_exhausted",
        )
        for name, state in data["states"].items():
            for key in routing_keys:
                target = state.get(key)
                if target and isinstance(target, str):
                    assert target in state_names, (
                        f"State '{name}' routes to '{target}' via '{key}', "
                        f"but '{target}' is not a state"
                    )
            # Also check route: table targets
            for route_key, target in state.get("route", {}).items():
                if isinstance(target, str):
                    assert target in state_names, (
                        f"State '{name}' route['{route_key}'] → '{target}', "
                        f"but '{target}' is not a state"
                    )

    def test_no_dead_end_states(self) -> None:
        """No non-terminal states dead-end without routing."""
        data = _load_loop()
        for name, state in data["states"].items():
            if state.get("terminal"):
                continue
            if "next" in state:
                continue
            if "fragment" in state:
                # Fragment provides routing (next/on_yes/etc.) — not a dead-end
                continue
            has_route = any(
                k in state for k in ("on_yes", "on_no", "on_success", "on_failure", "on_error")
            ) or bool(state.get("route"))  # classify + route: table is also valid routing
            assert has_route, f"Non-terminal state '{name}' has no routing"

    def test_terminal_states_have_no_outgoing(self) -> None:
        """Terminal states have no outgoing routing keys."""
        data = _load_loop()
        for name, state in data["states"].items():
            if state.get("terminal"):
                routing_keys = ("next", "on_yes", "on_no", "on_error", "on_success", "on_failure")
                for key in routing_keys:
                    assert key not in state, (
                        f"Terminal state '{name}' has outgoing routing via '{key}'"
                    )


# ============================================================================
# TestOutcomeTokenChannel — ENH-1977 Fix 1/2/5 (rn-remediate side)
# ============================================================================


class TestOutcomeTokenChannel:
    """rn-remediate writes outcome tokens and uses loop-context thresholds."""

    def test_emit_states_exist(self) -> None:
        data = _load_loop()
        for name in (
            "emit_implemented",
            "emit_needs_decompose",
            "emit_needs_manual_review",
            "emit_implement_failed",
            "emit_scores_missing",
        ):
            assert name in data["states"], f"missing emit state {name}"

    def test_emit_tokens_written_to_run_dir(self) -> None:
        data = _load_loop()
        expected = {
            "emit_implemented": "IMPLEMENTED",
            "emit_needs_decompose": "NEEDS_DECOMPOSE",
            "emit_needs_manual_review": "MANUAL_REVIEW_NEEDED",
            "emit_implement_failed": "IMPLEMENT_FAILED",
            "emit_scores_missing": "SCORES_MISSING",
        }
        for name, token in expected.items():
            action = data["states"][name]["action"]
            assert token in action
            assert "subloop_outcome_" in action
            assert "${context.run_dir}" in action

    def test_emit_implemented_routes_to_done(self) -> None:
        data = _load_loop()
        assert data["states"]["emit_implemented"]["next"] == "done"

    def test_implement_success_emits_implemented(self) -> None:
        """FEAT-2552: implement.on_yes routes to run_code_gate (not directly to
        emit_implemented). emit_implemented is reached only after the gate passes
        (GATE_PASS / GATE_SKIP). on_no routing unchanged."""
        data = _load_loop()
        assert data["states"]["implement"]["on_yes"] == "run_code_gate"
        # on_no routes through check_learning_gate first (550659db), then the
        # check_impl_auth auth guard (ENH-2353), then emit_implement_failed
        assert data["states"]["implement"]["on_no"] == "check_learning_gate"

    def test_bug2006_token_disambiguation_preserved(self) -> None:
        """BUG-2006: diagnose DECOMPOSE path → emit_needs_decompose (plain token);
        budget-exhausted stall path → emit_stalled_needs_decompose (superstring token).
        ENH-2107: CONVERGED_STALLED routes through check_remediation_budget first.
        Both emit states still exist to preserve the parent's substring dispatch."""
        data = _load_loop()
        states = data["states"]
        # Genuine "too big" path via diagnose route table → plain NEEDS_DECOMPOSE
        assert states["diagnose"]["route"]["DECOMPOSE"] == "emit_needs_decompose"
        # CONVERGED_STALLED routes to budget-gated retry (ENH-2107)
        assert (
            states["check_convergence"]["route"]["CONVERGED_STALLED"] == "check_remediation_budget"
        )
        # Budget-exhausted path still emits the stall-specific superstring token
        assert states["check_remediation_budget"]["on_no"] == "emit_stalled_needs_decompose"
        # Both emitter states still exist (parent rn-implement relies on them)
        assert "emit_needs_decompose" in states
        assert "emit_stalled_needs_decompose" in states

    def test_emit_stalled_needs_decompose_writes_superstring_token(self) -> None:
        """BUG-2006: the stall emitter writes STALLED_NEEDS_DECOMPOSE (a superstring
        of NEEDS_DECOMPOSE) to a non-done terminal, so the parent's substring match
        still triggers a decomposition attempt."""
        data = _load_loop()
        esd = data["states"]["emit_stalled_needs_decompose"]
        assert "STALLED_NEEDS_DECOMPOSE" in esd["action"]
        assert esd["next"] == "failed"

    def test_check_convergence_detects_decision_needed(self) -> None:
        """check_convergence stall branch checks decision_needed for NEEDS_MANUAL_REVIEW."""
        data = _load_loop()
        action = data["states"]["check_convergence"]["action"]
        assert "POST_DECISION" in action
        assert "NEEDS_MANUAL_REVIEW" in action
        assert "decision_needed" in action

    def test_check_convergence_pass_branch_guards_decision_needed(self) -> None:
        """BUG-2193: CONVERGED_PASS branch must check decision_needed before emitting.

        The POST_DECISION guard must appear inside the pass-threshold block (before the
        CONVERGED_PASS echo), not only in the stall branch that follows it. Without this,
        a refine run that raises scores above thresholds AND sets decision_needed: true
        would emit CONVERGED_PASS and route to implement, which then fails.
        """
        data = _load_loop()
        action = data["states"]["check_convergence"]["action"]
        section_start = action.find("# Convergence rules")
        assert section_start != -1, (
            "Convergence rules section not found in check_convergence action"
        )
        section = action[section_start:]
        first_post_decision = section.find("POST_DECISION")
        first_converged_pass_echo = section.find('echo "CONVERGED_PASS"')
        assert first_post_decision != -1, "POST_DECISION guard missing from convergence section"
        assert first_converged_pass_echo != -1, (
            'echo "CONVERGED_PASS" missing from convergence section'
        )
        assert first_post_decision < first_converged_pass_echo, (
            "BUG-2193: POST_DECISION guard must appear before echo CONVERGED_PASS in pass branch"
        )

    def test_rate_limit_diagnostic_writes_token_and_fails(self) -> None:
        data = _load_loop()
        rld = data["states"]["rate_limit_diagnostic"]
        assert rld.get("fragment") == "subloop_rate_limit_diagnostic", (
            "rate_limit_diagnostic must use the subloop_rate_limit_diagnostic fragment"
        )
        assert rld.get("with", {}).get("operation") == "remediation", (
            "rate_limit_diagnostic must pass operation=remediation to the fragment"
        )

    def test_check_readiness_passes_thresholds(self) -> None:
        data = _load_loop()
        action = data["states"]["check_readiness"]["action"]
        assert "--readiness" in action and "${context.readiness_threshold}" in action
        assert "--outcome" in action and "${context.outcome_threshold}" in action

    def test_diagnose_routes_missing_artifacts_to_wire(self) -> None:
        data = _load_loop()
        action = data["states"]["diagnose"]["action"]
        assert (
            'MISSING_ARTIFACTS" = "true"' in action.replace("'", '"')
            or "MISSING_ARTIFACTS" in action
            and "WIRE" in action
        )


# ---------------------------------------------------------------------------
# TestDiagnoseAmbiguityWireDiscrimination — ENH-2116
# ---------------------------------------------------------------------------


class TestDiagnoseAmbiguityWireDiscrimination:
    """WIRE(ambiguity) branch must only fire when CHANGE_SURFACE == 0.

    When an integration map already exists (CHANGE_SURFACE > 0), high ambiguity
    is decision-driven, not a wiring gap.  The branch must fall through to REFINE
    so a full-rewrite pass can resolve the conditional logic.
    """

    def _routing_script(self) -> str:
        """Extract the priority-ordered routing section with context vars substituted."""
        data = _load_loop()
        action = data["states"]["diagnose"]["action"]
        start = action.find("# Priority-ordered routing")
        if start == -1:
            raise AssertionError("Could not locate routing section in diagnose action")
        section = action[start:]
        # Substitute context variables with their defaults
        section = section.replace("${context.diagnose_ambiguity_threshold}", "15")
        section = section.replace("${context.diagnose_complexity_threshold}", "15")
        section = section.replace("${context.diagnose_change_surface_threshold}", "15")
        section = section.replace("${context.diagnose_confidence_floor}", "50")
        return section

    def _run(
        self,
        script: str,
        *,
        confidence: int,
        outcome: int,
        ambiguity: int,
        complexity: int = 0,
        change_surface: int = 0,
        decision_needed: str = "false",
        missing_artifacts: str = "false",
    ) -> str:
        env = "\n".join(
            [
                f"CONFIDENCE={confidence}",
                f"OUTCOME={outcome}",
                "READINESS_THRESHOLD=85",
                "OUTCOME_THRESHOLD=75",
                f"AMBIGUITY={ambiguity}",
                f"COMPLEXITY={complexity}",
                f"CHANGE_SURFACE={change_surface}",
                f"DECISION_NEEDED={decision_needed}",
                f"MISSING_ARTIFACTS={missing_artifacts}",
            ]
        )
        result = subprocess.run(
            ["bash", "-c", env + "\n" + script],
            capture_output=True,
            text=True,
        )
        return result.stdout.strip()

    def test_ambiguity_high_change_surface_zero_routes_to_wire(self) -> None:
        """ambiguity=18, change_surface=0 → WIRE (integration map absent)."""
        token = self._run(
            self._routing_script(),
            confidence=100,
            outcome=56,
            ambiguity=18,
            change_surface=0,
        )
        assert token == "WIRE", f"Expected WIRE, got {token!r}"

    def test_ambiguity_high_change_surface_nonzero_routes_to_refine(self) -> None:
        """ambiguity=18, change_surface=5 → REFINE (decision-driven ambiguity, ENH-2116)."""
        token = self._run(
            self._routing_script(),
            confidence=100,
            outcome=56,
            ambiguity=18,
            change_surface=5,
        )
        assert token == "REFINE", f"Expected REFINE, got {token!r}"

    def test_wire_condition_has_change_surface_guard(self) -> None:
        """diagnose action contains CHANGE_SURFACE -eq 0 guard on the ambiguity→WIRE branch."""
        data = _load_loop()
        action = data["states"]["diagnose"]["action"]
        assert "CHANGE_SURFACE" in action and "-eq 0" in action, (
            "diagnose action must guard the ambiguity→WIRE branch with CHANGE_SURFACE -eq 0"
        )


# ---------------------------------------------------------------------------
# TestCounterIncrementInEmitImplemented — ENH-2119
# ---------------------------------------------------------------------------


class TestCounterIncrementInEmitImplemented:
    """ENH-2119: counter increment must live in emit_implemented, not implement."""

    def test_implement_does_not_reference_implemented_count(self) -> None:
        """implement state must not reference implemented_count.txt (ENH-2119)."""
        data = _load_loop()
        action = data["states"]["implement"]["action"]
        assert "implemented_count.txt" not in action, (
            "implement action must not increment implemented_count.txt; "
            "that belongs in emit_implemented (ENH-2119)"
        )

    def test_implement_does_not_reference_counted_txt(self) -> None:
        """implement state must not reference counted.txt (ENH-2119)."""
        data = _load_loop()
        action = data["states"]["implement"]["action"]
        assert "counted.txt" not in action, (
            "implement action must not reference counted.txt; "
            "dedup guard belongs in emit_implemented (ENH-2119)"
        )

    def test_emit_implemented_increments_counter(self) -> None:
        """emit_implemented state must increment implemented_count.txt (ENH-2119)."""
        data = _load_loop()
        action = data["states"]["emit_implemented"]["action"]
        assert "implemented_count.txt" in action, (
            "emit_implemented must increment implemented_count.txt (ENH-2119)"
        )

    def test_emit_implemented_writes_counted_guard(self) -> None:
        """emit_implemented state must write to counted.txt to prevent double-counting (ENH-2119)."""
        data = _load_loop()
        action = data["states"]["emit_implemented"]["action"]
        assert "counted.txt" in action, (
            "emit_implemented must append to counted.txt for dedup (ENH-2119)"
        )

    def test_emit_implemented_uses_run_dir_for_counter(self) -> None:
        """emit_implemented counter files must be scoped to run_dir (ENH-2119)."""
        data = _load_loop()
        action = data["states"]["emit_implemented"]["action"]
        assert "${context.run_dir}/implemented_count.txt" in action
        assert "${context.run_dir}/counted.txt" in action

    def test_emit_implemented_uses_quiet_grep_for_dedup(self) -> None:
        """emit_implemented dedup guard must use grep -qxF, not grep -cxF (BUG-2170).

        grep -cxF "$ID" file 2>/dev/null || echo 0 produces double output when the
        file exists but $ID is absent: grep -c outputs "0" AND exits 1, triggering
        || echo 0, so ALREADY_COUNTED captures "0\\n0" which fails the -eq 0 test.
        The fix is grep -qxF which exits 0/1 with no stdout.
        """
        data = _load_loop()
        action = data["states"]["emit_implemented"]["action"]
        assert "grep -qxF" in action, (
            "emit_implemented dedup guard must use 'grep -qxF' (not 'grep -cxF') (BUG-2170)"
        )
        assert "grep -cxF" not in action, (
            "emit_implemented must not use 'grep -cxF' — causes double-output bug (BUG-2170)"
        )

    def test_implement_action_is_minimal(self) -> None:
        """implement action contains only ll-auto invocation and exit (ENH-2119)."""
        data = _load_loop()
        action = data["states"]["implement"]["action"]
        assert "ll-auto --only" in action
        assert "exit $?" in action or "exit $EXIT_CODE" in action


# ---------------------------------------------------------------------------
# TestEnsureFormatted — BUG-2395
# ---------------------------------------------------------------------------


class TestEnsureFormatted:
    """ensure_formatted gate must exit 0 for canonical post-ENH-1392 issues.

    Before BUG-2395 fix: gate flags Labels (moved to frontmatter by ENH-1392)
    and User Story (renamed to Use Case) as missing required sections, causing
    a redundant format pass on every rn-remediate run.

    Post-ENH-2426: the gate's shell body calls `ll-issues format-check "$ID"`
    (scripts/little_loops/cli/issues/format_check.py) instead of an inline
    MISSING=$(...) heredoc. These tests verify the gate's YAML wiring calls the
    new subcommand, then exercise it end-to-end via main_issues() against a
    real temp project — mirrors test_ll_issues_format_check.py's fixtures.
    """

    def test_gate_calls_format_check_subcommand(self) -> None:
        """The gate body must invoke `ll-issues format-check`, not the old heredoc."""
        data = _load_loop()
        action = data["states"]["ensure_formatted"]["action"]
        assert "ll-issues format-check" in action, (
            "ensure_formatted action must call `ll-issues format-check` (ENH-2426)"
        )
        assert "MISSING=$(" not in action, (
            "ensure_formatted action still contains the old inline MISSING=$( heredoc"
        )

    def _write_project(self, tmp_path: Path) -> Path:
        import json

        project = tmp_path / "project"
        (project / ".ll").mkdir(parents=True)
        (project / ".ll" / "ll-config.json").write_text(
            json.dumps({"issues": {"base_dir": ".issues"}})
        )
        for cat in ("bugs", "features", "enhancements"):
            (project / ".issues" / cat).mkdir(parents=True, exist_ok=True)
        return project

    def _run_gate(self, tmp_path: Path, issue_id: str, filename: str, body: str) -> int:
        import sys
        from unittest.mock import patch

        project = self._write_project(tmp_path)
        prefix = issue_id.split("-")[0]
        subdir_map = {"BUG": "bugs", "FEAT": "features", "ENH": "enhancements"}
        (project / ".issues" / subdir_map[prefix] / filename).write_text(body)

        with patch.object(
            sys,
            "argv",
            ["ll-issues", "format-check", issue_id, "--config", str(project)],
        ):
            from little_loops.cli import main_issues

            return main_issues()

    def test_feat_frontmatter_labels_use_case_exits_0(self, tmp_path: Path) -> None:
        """feat with labels: frontmatter + ## Use Case must exit 0 (BUG-2395).

        Pre-fix: gate emits 'missing required sections: Labels; User Story' → exits 1.
        Post-fix: Labels.required demoted to false; User Story.level demoted to optional
        → gate finds all required sections and exits 0.
        """
        body = "\n".join(
            [
                "---",
                "labels:",
                "- host-compat",
                "- portfolio",
                "---",
                "",
                "# FEAT-9999: Test feature",
                "",
                "## Summary",
                "A test feature.",
                "",
                "## Current Behavior",
                "N/A — new feature.",
                "",
                "## Expected Behavior",
                "It works as described.",
                "",
                "## Use Case",
                "As a developer, I want X so that Y.",
                "",
                "## Acceptance Criteria",
                "- Criterion 1",
                "",
                "## Impact",
                "- **Priority**: P3 - Low",
                "- **Effort**: Small",
                "- **Risk**: Low",
                "- **Breaking Change**: No",
                "",
                "## Status",
                "open",
            ]
        )
        result = self._run_gate(tmp_path, "FEAT-9999", "P3-FEAT-9999-test-feature.md", body)
        assert result == 0, "Gate should exit 0 for feat with frontmatter labels + ## Use Case."

    def test_enh_deprecated_section_exits_0(self, tmp_path: Path) -> None:
        """enh without ## Current Pain Point must exit 0 (ENH-2398).

        enh-sections.json "Current Pain Point" has level: required + deprecated: true.
        The gate must skip it (mirroring is_formatted()), so an ENH issue that has
        all non-deprecated required sections but omits "Current Pain Point" exits 0.

        Pre-fix: gate includes deprecated section → exits 1 (false-positive block).
        Post-fix: deprecated guard skips it → exits 0.
        """
        body = "\n".join(
            [
                "---",
                "id: ENH-9999",
                "status: open",
                "---",
                "",
                "# ENH-9999: Test enhancement",
                "",
                "## Summary",
                "A test enhancement.",
                "",
                "## Current Behavior",
                "Things work one way.",
                "",
                "## Expected Behavior",
                "Things should work another way.",
                "",
                "## Impact",
                "- **Priority**: P4 - Low",
                "- **Effort**: Small",
                "- **Risk**: Low",
                "- **Breaking Change**: No",
                "",
                "## Scope Boundaries",
                "Out of scope: everything else.",
                "",
                "## Status",
                "open",
            ]
        )
        result = self._run_gate(tmp_path, "ENH-9999", "P3-ENH-9999-test-enhancement.md", body)
        assert result == 0, (
            "Gate should exit 0 for enh missing only deprecated 'Current Pain Point'."
        )

    def test_renamed_section_exits_1(self, tmp_path: Path) -> None:
        """A present deprecated section with a canonical replacement exits 1 (ENH-2426)."""
        body = "\n".join(
            [
                "---",
                "status: open",
                "---",
                "",
                "# BUG-9998: Test bug",
                "",
                "## Summary",
                "A test bug.",
                "",
                "## Current Behavior",
                "It breaks.",
                "",
                "## Expected Behavior",
                "It works.",
                "",
                "## Steps to Reproduce",
                "1. Do the thing.",
                "",
                "## Proposed Fix",
                "Old-style content.",
                "",
                "## Impact",
                "- **Priority**: P3 - Low",
                "",
                "## Status",
                "open",
            ]
        )
        result = self._run_gate(tmp_path, "BUG-9998", "P3-BUG-9998-test-bug.md", body)
        assert result == 1, "Gate should exit 1 for a present renamed/deprecated section."

    def test_empty_section_exits_1(self, tmp_path: Path) -> None:
        """A required header present with a whitespace-only body exits 1 (ENH-2426)."""
        body = "\n".join(
            [
                "---",
                "status: open",
                "---",
                "",
                "# BUG-9997: Test bug",
                "",
                "## Summary",
                "",
                "## Current Behavior",
                "It breaks.",
                "",
                "## Expected Behavior",
                "It works.",
                "",
                "## Steps to Reproduce",
                "1. Do the thing.",
                "",
                "## Impact",
                "- **Priority**: P3 - Low",
                "",
                "## Status",
                "open",
            ]
        )
        result = self._run_gate(tmp_path, "BUG-9997", "P3-BUG-9997-test-bug.md", body)
        assert result == 1, "Gate should exit 1 for a required section with an empty body."

    def test_boilerplate_only_section_exits_1(self, tmp_path: Path) -> None:
        """A required header whose body equals its creation_template exits 1 (ENH-2426)."""
        body = "\n".join(
            [
                "---",
                "status: open",
                "---",
                "",
                "# BUG-9996: Test bug",
                "",
                "## Summary",
                "[Description extracted from input]",
                "",
                "## Current Behavior",
                "It breaks.",
                "",
                "## Expected Behavior",
                "It works.",
                "",
                "## Steps to Reproduce",
                "1. Do the thing.",
                "",
                "## Impact",
                "- **Priority**: P3 - Low",
                "",
                "## Status",
                "open",
            ]
        )
        result = self._run_gate(tmp_path, "BUG-9996", "P3-BUG-9996-test-bug.md", body)
        assert result == 1, (
            "Gate should exit 1 for a required section left at its creation_template."
        )

    def test_clean_issue_exits_0(self, tmp_path: Path) -> None:
        """A fully-populated, non-boilerplate bug issue exits 0 (ENH-2426)."""
        body = "\n".join(
            [
                "---",
                "status: open",
                "---",
                "",
                "# BUG-9995: Test bug",
                "",
                "## Summary",
                "A real problem happens under specific conditions.",
                "",
                "## Current Behavior",
                "It breaks in a specific way.",
                "",
                "## Expected Behavior",
                "It should not break.",
                "",
                "## Steps to Reproduce",
                "1. Do the thing.",
                "2. Observe failure.",
                "",
                "## Impact",
                "- **Priority**: P3 - Low",
                "",
                "## Status",
                "open",
            ]
        )
        result = self._run_gate(tmp_path, "BUG-9995", "P3-BUG-9995-test-bug.md", body)
        assert result == 0, "Gate should exit 0 for a clean, fully-populated bug issue."


# ---------------------------------------------------------------------------
# TestRnRemediateAuthGuard — ENH-2353: auth-signature fast-fail
# ---------------------------------------------------------------------------


class TestRnRemediateAuthGuard:
    """Auth-failure fast-fail guard for rn-remediate.implement (ENH-2353)."""

    def test_implement_captures_ll_auto_output(self) -> None:
        """implement must capture its output as ll_auto_output for the auth-check state."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl.get("capture") == "ll_auto_output", (
            f"implement must set capture: ll_auto_output, got {impl.get('capture')!r}"
        )

    def test_implement_on_no_routes_to_check_learning_gate(self) -> None:
        """implement.on_no must route to check_learning_gate (the first failure-chain
        guard, 550659db), not directly to emit_implement_failed. The chain then falls
        through check_learning_gate → check_impl_auth (ENH-2353) → emit_implement_failed."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl.get("on_no") == "check_learning_gate", (
            f"implement.on_no should be 'check_learning_gate', got {impl.get('on_no')!r}"
        )

    def test_implement_on_error_routes_to_check_learning_gate(self) -> None:
        """implement.on_error must route to check_learning_gate (first failure-chain guard)."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl.get("on_error") == "check_learning_gate", (
            f"implement.on_error should be 'check_learning_gate', got {impl.get('on_error')!r}"
        )

    def test_check_impl_auth_state_exists(self) -> None:
        """check_impl_auth state must be defined in rn-remediate."""
        data = _load_loop()
        assert "check_impl_auth" in data["states"], "check_impl_auth state missing"

    def test_check_impl_auth_uses_ll_auto_auth_check_fragment(self) -> None:
        """check_impl_auth must use the ll_auto_auth_check shared fragment."""
        data = _load_loop()
        state = data["states"]["check_impl_auth"]
        assert state.get("fragment") == "ll_auto_auth_check", (
            f"check_impl_auth must use fragment: ll_auto_auth_check, got {state.get('fragment')!r}"
        )

    def test_check_impl_auth_on_yes_routes_to_emit_env_not_ready(self) -> None:
        """check_impl_auth.on_yes (auth detected) must route to emit_env_not_ready."""
        data = _load_loop()
        state = data["states"]["check_impl_auth"]
        assert state.get("on_yes") == "emit_env_not_ready", (
            f"check_impl_auth.on_yes should be 'emit_env_not_ready', got {state.get('on_yes')!r}"
        )

    def test_check_impl_auth_on_no_routes_to_emit_implement_failed(self) -> None:
        """check_impl_auth.on_no (genuine failure) must route to emit_implement_failed."""
        data = _load_loop()
        state = data["states"]["check_impl_auth"]
        assert state.get("on_no") == "emit_implement_failed", (
            f"check_impl_auth.on_no should be 'emit_implement_failed', got {state.get('on_no')!r}"
        )

    def test_emit_env_not_ready_state_exists(self) -> None:
        """emit_env_not_ready state must be defined."""
        data = _load_loop()
        assert "emit_env_not_ready" in data["states"], "emit_env_not_ready state missing"

    def test_emit_env_not_ready_writes_sidecar(self) -> None:
        """emit_env_not_ready must write subloop_outcome_ sidecar (sidecar contract, ENH-1977)."""
        data = _load_loop()
        action = data["states"]["emit_env_not_ready"].get("action", "")
        assert "subloop_outcome_" in action, (
            "emit_env_not_ready must write subloop_outcome_<ID>.txt — parent classify_remediation "
            "reads this sidecar; without it auth failures fall through as IMPLEMENT_FAILED"
        )

    def test_manual_review_emits_handoff_md(self) -> None:
        """ENH-2530: emit_needs_manual_review must write the per-issue
        manual_review_handoff_<ID>.md diagnostic alongside the token sidecar."""
        data = _load_loop()
        action = data["states"]["emit_needs_manual_review"].get("action", "")
        assert "manual_review_handoff_" in action, (
            "emit_needs_manual_review must write manual_review_handoff_<ID>.md "
            "(ENH-2530) — per-issue diagnostic for human operators reviewing "
            "parked issues; the token sidecar alone forces re-reading events.jsonl"
        )

    def test_emit_env_not_ready_writes_env_not_ready_token(self) -> None:
        """emit_env_not_ready must emit the ENV_NOT_READY outcome token."""
        data = _load_loop()
        action = data["states"]["emit_env_not_ready"].get("action", "")
        assert "ENV_NOT_READY" in action

    def test_emit_env_not_ready_routes_to_failed_terminal(self) -> None:
        """emit_env_not_ready must route to failed so the parent aborts the queue."""
        data = _load_loop()
        state = data["states"]["emit_env_not_ready"]
        assert state.get("next") == "failed"

    def test_emit_env_not_ready_has_diagnostic_echo(self) -> None:
        """emit_env_not_ready must echo a user-actionable diagnostic message."""
        data = _load_loop()
        action = data["states"]["emit_env_not_ready"].get("action", "")
        assert "echo" in action, "emit_env_not_ready must echo a diagnostic message"


# ---------------------------------------------------------------------------
# TestRunCodeGate — FEAT-2552: wire code-run-gate oracle into rn-remediate
# ---------------------------------------------------------------------------


class TestRunCodeGate:
    """FEAT-2552: rn-remediate inserts a `run_code_gate` sub-loop delegation between
    `implement` and `emit_implemented`. The oracle (`oracles/code-run-gate.yaml`,
    FEAT-2551) emits GATE_PASS / GATE_FAILED / GATE_SKIP via the
    `subloop_outcome_<ID>.txt` sidecar; the parent must route those verdicts to
    `emit_implemented` (pass / skip) or `record_gate_failure` (fail), and
    disambiguate infrastructure crashes (`on_error`) from gate code-quality failures
    via the distinct `record_gate_error` state. The gate's verdict becomes the new
    load-bearing signal for IMPLEMENTED vs IMPLEMENT_FAILED."""

    # --- run_code_gate state shape ---

    def test_run_code_gate_state_exists(self) -> None:
        data = _load_loop()
        assert "run_code_gate" in data["states"], (
            "rn-remediate must add run_code_gate state (FEAT-2552)"
        )

    def test_run_code_gate_is_subloop_delegation(self) -> None:
        """run_code_gate delegates to the code-run-gate oracle (FEAT-2551).

        The static `loop:` reference uses the `oracles/<name>` path (full
        relative path) per the loop-reference resolution contract — bare
        `code-run-gate` would not resolve under the FSM static-reference
        validator (`_validate_loop_references` at fsm/validation.py:508-544).
        """
        data = _load_loop()
        state = data["states"]["run_code_gate"]
        assert state.get("loop") == "oracles/code-run-gate", (
            f"run_code_gate.loop must be 'oracles/code-run-gate', got {state.get('loop')!r}"
        )

    def test_run_code_gate_has_with_bindings(self) -> None:
        """run_code_gate passes issue_id, run_dir, and min_pass_rate via with: bindings.

        `min_pass_rate` is a new rn-remediate context default (FEAT-2552:226-229) so
        the sub-loop dispatch never fails context-resolution for issues that don't
        override it. The oracle's evaluator target is hardcoded 0.95; the binding is
        passed for forward-compatibility and per-issue override.
        """
        data = _load_loop()
        with_bindings = data["states"]["run_code_gate"]["with"]
        assert with_bindings["issue_id"] == "${context.issue_id}"
        assert with_bindings["run_dir"] == "${context.run_dir}"
        assert with_bindings["min_pass_rate"] == "${context.min_pass_rate}"

    def test_run_code_gate_routes_on_success_to_emit_implemented(self) -> None:
        """GATE_PASS / GATE_SKIP both reach emit_implemented (the oracle maps both
        verdicts to its `done` terminal, which the executor collapses to on_success)."""
        data = _load_loop()
        state = data["states"]["run_code_gate"]
        assert state["on_success"] == "emit_implemented"

    def test_run_code_gate_routes_on_failure_to_record_gate_failure(self) -> None:
        """GATE_FAILED (oracle's failed terminal) routes to record_gate_failure,
        which writes GATE_FAILED to the sidecar for the parent to classify."""
        data = _load_loop()
        state = data["states"]["run_code_gate"]
        assert state["on_failure"] == "record_gate_failure"

    def test_run_code_gate_routes_on_error_to_record_gate_error(self) -> None:
        """ENH-2005 mirror: a gate child crash/timeout/context-resolution failure
        routes to record_gate_error (not record_gate_failure) so the parent's
        classifier can disambiguate gate infrastructure failure from gate
        code-quality failure (GATE_FAILED_INFRA tag)."""
        data = _load_loop()
        state = data["states"]["run_code_gate"]
        assert state["on_error"] == "record_gate_error"

    def test_implement_on_yes_routes_to_run_code_gate(self) -> None:
        """The implement → emit_implemented direct route is intentionally broken;
        implement.on_yes now feeds the gate (FEAT-2552 AC: an IMPLEMENTED verdict
        requires the gate to pass)."""
        data = _load_loop()
        assert data["states"]["implement"]["on_yes"] == "run_code_gate"

    # --- record_gate_failure state ---

    def test_record_gate_failure_state_exists(self) -> None:
        data = _load_loop()
        assert "record_gate_failure" in data["states"], (
            "rn-remediate must add record_gate_failure state to handle GATE_FAILED"
        )

    def test_record_gate_failure_writes_gate_failed_sidecar(self) -> None:
        """record_gate_failure writes GATE_FAILED to the sidecar so the parent's
        classify_remediation can pick it up via the route_rem_* chain."""
        data = _load_loop()
        action = data["states"]["record_gate_failure"]["action"]
        assert "GATE_FAILED" in action
        assert "subloop_outcome_" in action

    def test_record_gate_failure_increments_remediation_counter(self) -> None:
        """record_gate_failure increments the same remediation_count_<ID>.txt
        counter that check_remediation_budget enforces — so a gate failure
        consumes a budget slot without needing a parallel counter."""
        data = _load_loop()
        action = data["states"]["record_gate_failure"]["action"]
        assert "remediation_count_" in action

    def test_record_gate_failure_routes_back_to_implement(self) -> None:
        """A gate failure returns to `implement` (cheap, one extra ll-auto call
        + a re-gate) rather than dead-ending on the first failure. The budget
        check on the next convergence cycle terminates if max_remediation_passes
        is exhausted (FEAT-2552 'lazy' budget pattern)."""
        data = _load_loop()
        state = data["states"]["record_gate_failure"]
        assert state.get("next") == "implement"

    # --- record_gate_error state ---

    def test_record_gate_error_state_exists(self) -> None:
        data = _load_loop()
        assert "record_gate_error" in data["states"], (
            "rn-remediate must add record_gate_error state to disambiguate gate "
            "child crash from gate code-quality failure (ENH-2005 pattern)"
        )

    def test_record_gate_error_writes_gate_failed_infra_sidecar(self) -> None:
        """record_gate_error writes GATE_FAILED_INFRA (distinct from GATE_FAILED) so
        the parent can tally gate infrastructure failures separately from genuine
        gate code-quality failures."""
        data = _load_loop()
        action = data["states"]["record_gate_error"]["action"]
        assert "GATE_FAILED_INFRA" in action
        assert "subloop_outcome_" in action

    def test_record_gate_error_routes_to_implement_failed(self) -> None:
        """A gate child crash is an infrastructure failure (not retryable code
        quality), so record_gate_error goes straight to emit_implement_failed
        rather than back to implement (where the same crash would recur)."""
        data = _load_loop()
        state = data["states"]["record_gate_error"]
        # Routes to next: emit_implement_failed (terminal), or directly to
        # the equivalent failure emitter.
        assert state.get("next") in {"emit_implement_failed", "failed"}

    # --- context defaults ---

    def test_min_pass_rate_default_defined(self) -> None:
        """min_pass_rate is a new rn-remediate context default (FEAT-2552:226-229)
        mirroring max_remediation_passes — without it, sub-loop dispatch fails
        context-resolution for issues that don't override min_pass_rate."""
        data = _load_loop()
        ctx = data.get("context", {})
        assert "min_pass_rate" in ctx, "rn-remediate.context must define min_pass_rate default"
        assert ctx["min_pass_rate"] == 1.0, (
            f"min_pass_rate default should be 1.0 (strict pass), got {ctx['min_pass_rate']!r}"
        )

    # --- FSM validation ---

    def test_rn_remediate_validates_after_gate_wiring(self) -> None:
        """ll-loop validate rn-remediate must pass after FEAT-2552's state insertions
        (no ERROR-severity validation findings)."""
        fsm, _warnings = load_and_validate(RN_REMEDIATE_PATH)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, (
            f"rn-remediate has validation errors after FEAT-2552 wiring: "
            f"{[str(e) for e in error_list]}"
        )

    def test_run_code_gate_is_runnable(self) -> None:
        """rn-remediate remains a runnable loop after the gate wiring (no
        detection regression from the new states)."""
        assert is_runnable_loop(RN_REMEDIATE_PATH), (
            "rn-remediate must remain a runnable loop after FEAT-2552 wiring"
        )

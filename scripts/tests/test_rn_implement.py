"""Tests for the rn-implement recursive plan-and-implement FSM loop."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from unittest.mock import patch

import pytest
import yaml

from little_loops.fsm import is_runnable_loop
from little_loops.fsm.validation import (
    ValidationSeverity,
    load_and_validate,
    validate_fsm,
)

LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
RN_IMPLEMENT_PATH = LOOPS_DIR / "rn-implement.yaml"


def _load_loop() -> dict:
    """Load the rn-implement YAML file."""
    with open(RN_IMPLEMENT_PATH) as f:
        return yaml.safe_load(f)


# ---------------------------------------------------------------------------
# TestInitAndInputValidation — States: init, failed
# ---------------------------------------------------------------------------


class TestInitAndInputValidation:
    """Tests for init state input validation and run_dir setup."""

    def test_yaml_parses_and_is_runnable(self) -> None:
        """rn-implement.yaml parses as valid YAML and is detected as runnable."""
        data = _load_loop()
        assert isinstance(data, dict), "Root must be a mapping"
        assert is_runnable_loop(RN_IMPLEMENT_PATH), "Must be detected as runnable"

    def test_has_required_top_level_fields(self) -> None:
        """Top-level fields required for a valid FSM are present."""
        data = _load_loop()
        for field in ("name", "description", "initial", "states"):
            assert field in data, f"Missing required field: {field}"
        assert data["initial"] == "init"
        assert data["name"] == "rn-implement"

    def test_init_state_has_shell_action(self) -> None:
        """init state uses action_type: shell."""
        data = _load_loop()
        init = data["states"]["init"]
        assert init["action_type"] == "shell"
        assert "action" in init

    def test_init_state_detects_empty_input(self) -> None:
        """init state shell script checks for empty input."""
        data = _load_loop()
        init = data["states"]["init"]
        assert '${context.input}' in init["action"]
        assert ' -z ' in init["action"]  # empty check

    def test_init_state_routes_on_yes_no_error(self) -> None:
        """init routes to dequeue_next on success, failed on failure."""
        data = _load_loop()
        init = data["states"]["init"]
        assert init["on_yes"] == "dequeue_next"
        assert init["on_no"] == "failed"
        assert init["on_error"] == "failed"

    def test_failed_state_is_terminal(self) -> None:
        """failed state is terminal."""
        data = _load_loop()
        failed = data["states"]["failed"]
        assert failed.get("terminal") is True

    def test_done_state_is_terminal(self) -> None:
        """done state is terminal."""
        data = _load_loop()
        done = data["states"]["done"]
        assert done.get("terminal") is True


# ---------------------------------------------------------------------------
# TestDequeueAndDepthTracking — States: dequeue_next, check_depth, mark_depth_capped
# ---------------------------------------------------------------------------


class TestDequeueAndDepthTracking:
    """Tests for queue management and depth tracking."""

    def test_dequeue_next_uses_queue_pop_fragment(self) -> None:
        """dequeue_next uses the queue_pop fragment."""
        data = _load_loop()
        deq = data["states"]["dequeue_next"]
        assert deq.get("fragment") == "queue_pop"

    def test_dequeue_next_routes_to_check_depth(self) -> None:
        """dequeue_next routes to check_depth on success."""
        data = _load_loop()
        deq = data["states"]["dequeue_next"]
        assert deq["on_yes"] == "check_depth"
        assert deq["on_no"] == "done"

    def test_dequeue_next_captures_input(self) -> None:
        """dequeue_next captures the popped issue ID as input."""
        data = _load_loop()
        deq = data["states"]["dequeue_next"]
        assert deq.get("capture") == "input"

    def test_check_depth_uses_output_numeric(self) -> None:
        """check_depth uses output_numeric evaluator with lt 1."""
        data = _load_loop()
        cd = data["states"]["check_depth"]
        evaluate = cd["evaluate"]
        assert evaluate["type"] == "output_numeric"
        assert evaluate["operator"] == "lt"
        assert evaluate["target"] == 1

    def test_check_depth_routes_below_cap_to_assess(self) -> None:
        """check_depth routes to assess when depth is below cap (output 0)."""
        data = _load_loop()
        cd = data["states"]["check_depth"]
        assert cd["on_yes"] == "assess", "on_yes (depth < max) should go to assess"
        assert cd["on_no"] == "mark_depth_capped", "on_no (depth >= max) should cap"

    def test_mark_depth_capped_transitions_to_dequeue_next(self) -> None:
        """mark_depth_capped always transitions to dequeue_next."""
        data = _load_loop()
        mdc = data["states"]["mark_depth_capped"]
        assert mdc["next"] == "dequeue_next"

    def test_mark_depth_capped_logs_to_depth_capped_txt(self) -> None:
        """mark_depth_capped writes to depth_capped.txt under run_dir."""
        data = _load_loop()
        mdc = data["states"]["mark_depth_capped"]
        assert "depth_capped.txt" in mdc["action"]

    def test_depth_map_references_in_dequeue(self) -> None:
        """dequeue_next references depth_map.txt for depth tracking."""
        data = _load_loop()
        deq = data["states"]["dequeue_next"]
        assert "depth_map.txt" in deq["action"]
        assert "current_depth.txt" in deq["action"]


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

    def test_verify_scores_persisted_uses_retry_counter(self) -> None:
        """verify_scores_persisted uses retry_counter fragment."""
        data = _load_loop()
        vsp = data["states"]["verify_scores_persisted"]
        assert vsp.get("fragment") == "retry_counter"

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
        assert vsp["on_no"] == "failed"


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
        """check_readiness routes to implement when readiness passes."""
        data = _load_loop()
        cr = data["states"]["check_readiness"]
        assert cr["on_yes"] == "implement"

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

    def test_check_outcome_routes_yes_to_diagnose(self) -> None:
        """check_outcome routes to diagnose when outcome passes."""
        data = _load_loop()
        co = data["states"]["check_outcome"]
        assert co["on_yes"] == "diagnose"

    def test_check_outcome_routes_no_to_check_decision_needed(self) -> None:
        """check_outcome routes to check_decision_needed when outcome fails."""
        data = _load_loop()
        co = data["states"]["check_outcome"]
        assert co["on_no"] == "check_decision_needed"

    def test_check_decision_needed_uses_check_flag(self) -> None:
        """check_decision_needed uses ll-issues check-flag."""
        data = _load_loop()
        cdn = data["states"]["check_decision_needed"]
        assert "ll-issues check-flag" in cdn["action"]
        assert "decision_needed" in cdn["action"]

    def test_check_decision_needed_routes_yes_to_decide(self) -> None:
        """check_decision_needed routes to decide when flag is true."""
        data = _load_loop()
        cdn = data["states"]["check_decision_needed"]
        assert cdn["on_yes"] == "decide"

    def test_check_decision_needed_routes_no_to_diagnose(self) -> None:
        """check_decision_needed routes to diagnose when flag is false."""
        data = _load_loop()
        cdn = data["states"]["check_decision_needed"]
        assert cdn["on_no"] == "diagnose"


# ---------------------------------------------------------------------------
# TestDiagnoseRouting — States: diagnose, route_d_implement, route_d_decide,
#   route_d_wire, route_d_refine
# ---------------------------------------------------------------------------


class TestDiagnoseRouting:
    """Tests for the dimensional diagnosis state and 4-way token routing chain."""

    def test_diagnose_is_shell_action(self) -> None:
        """diagnose state is action_type: shell."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        assert diag["action_type"] == "shell"

    def test_diagnose_captures_output_as_diagnosis(self) -> None:
        """diagnose captures output as diagnosis."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        assert diag.get("capture") == "diagnosis"

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

    def test_diagnose_outputs_all_five_tokens(self) -> None:
        """diagnose shell script contains all 5 routing tokens."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        action = diag["action"]
        for token in ("IMPLEMENT", "DECIDE", "WIRE", "REFINE", "DECOMPOSE"):
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

    def test_diagnose_routes_to_route_d_implement(self) -> None:
        """diagnose chains into route_d_implement."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        assert diag["next"] == "route_d_implement"

    def test_diagnose_on_error_routes_to_snap_for_size_review(self) -> None:
        """diagnose on_error falls through to decomposition."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        assert diag["on_error"] == "snap_for_size_review"

    def test_router_chain_covers_all_five_tokens(self) -> None:
        """The 4 routers cover IMPLEMENT, DECIDE, WIRE, REFINE with DECOMPOSE fallthrough."""
        data = _load_loop()
        # route_d_implement → implement or route_d_decide
        assert data["states"]["route_d_implement"]["on_yes"] == "implement"
        assert data["states"]["route_d_implement"]["on_no"] == "route_d_decide"
        # route_d_decide → decide or route_d_wire
        assert data["states"]["route_d_decide"]["on_yes"] == "decide"
        assert data["states"]["route_d_decide"]["on_no"] == "route_d_wire"
        # route_d_wire → wire or route_d_refine
        assert data["states"]["route_d_wire"]["on_yes"] == "wire"
        assert data["states"]["route_d_wire"]["on_no"] == "route_d_refine"
        # route_d_refine → refine or snap_for_size_review (DECOMPOSE fallthrough)
        assert data["states"]["route_d_refine"]["on_yes"] == "refine"
        assert data["states"]["route_d_refine"]["on_no"] == "snap_for_size_review"

    def test_routers_use_output_contains_with_source(self) -> None:
        """All diagnose routers use output_contains with captured diagnosis source."""
        data = _load_loop()
        for state_name in ("route_d_implement", "route_d_decide", "route_d_wire", "route_d_refine"):
            state = data["states"][state_name]
            evaluate = state["evaluate"]
            assert evaluate["type"] == "output_contains"
            assert "${captured.diagnosis.output}" in evaluate["source"]

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

    def test_implement_routes_to_dequeue_next(self) -> None:
        """implement routes to dequeue_next on success."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl["on_yes"] == "dequeue_next"

    def test_implement_failure_routes_to_skip_issue(self) -> None:
        """implement routes to skip_issue on failure."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl["on_no"] == "skip_issue"
        assert impl["on_error"] == "skip_issue"

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

    def test_decide_routes_to_re_assess(self) -> None:
        """decide routes to re_assess on success (must re-check)."""
        data = _load_loop()
        dec = data["states"]["decide"]
        assert dec["on_success"] == "re_assess"
        assert dec["on_error"] == "re_assess"

    def test_wire_is_slash_command_with_auto(self) -> None:
        """wire invokes /ll:wire-issue --auto as a slash_command."""
        data = _load_loop()
        wire = data["states"]["wire"]
        assert wire["action_type"] == "slash_command"
        assert "/ll:wire-issue" in wire["action"]
        assert "--auto" in wire["action"]

    def test_wire_chains_into_refine(self) -> None:
        """wire always chains into refine (wiring may reveal gaps)."""
        data = _load_loop()
        wire = data["states"]["wire"]
        assert wire["on_success"] == "refine"
        assert wire["on_error"] == "refine"

    def test_refine_uses_full_rewrite_flag(self) -> None:
        """refine uses --full-rewrite flag."""
        data = _load_loop()
        ref = data["states"]["refine"]
        assert "--full-rewrite" in ref["action"]

    def test_refine_routes_to_re_assess(self) -> None:
        """refine routes to re_assess on success."""
        data = _load_loop()
        ref = data["states"]["refine"]
        assert ref["on_success"] == "re_assess"

    def test_refine_failure_routes_to_skip_issue(self) -> None:
        """refine routes to skip_issue on error."""
        data = _load_loop()
        ref = data["states"]["refine"]
        assert ref["on_error"] == "skip_issue"


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

    def test_verify_re_assess_scores_uses_retry_counter(self) -> None:
        """verify_re_assess_scores uses retry_counter fragment."""
        data = _load_loop()
        vras = data["states"]["verify_re_assess_scores"]
        assert vras.get("fragment") == "retry_counter"

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
        lines = [l.strip() for l in action.split("\n")]
        for line in lines:
            if line.startswith('echo "') and 'PASS' in line:
                assert "CONVERGED" in line, (
                    f"Line uses bare PASS without CONVERGED_ prefix: {line}"
                )

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

    def test_check_convergence_captures_as_convergence_result(self) -> None:
        """check_convergence captures output as convergence_result."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        assert cc.get("capture") == "convergence_result"

    def test_convergence_router_chain_is_correct(self) -> None:
        """Convergence routing chain: PASS → implement, IMPROVED → budget, STALLED → decompose."""
        data = _load_loop()
        # route_conv_pass
        rcp = data["states"]["route_conv_pass"]
        assert rcp["on_yes"] == "implement"
        assert rcp["on_no"] == "route_conv_improved"
        # route_conv_improved
        rci = data["states"]["route_conv_improved"]
        assert rci["on_yes"] == "check_remediation_budget"
        assert rci["on_no"] == "snap_for_size_review"

    def test_convergence_routers_use_output_contains_with_source(self) -> None:
        """Convergence routers use output_contains with captured source."""
        data = _load_loop()
        for state_name in ("route_conv_pass", "route_conv_improved"):
            state = data["states"][state_name]
            evaluate = state["evaluate"]
            assert evaluate["type"] == "output_contains"
            assert "${captured.convergence_result.output}" in evaluate["source"]

    def test_check_convergence_writes_convergence_json(self) -> None:
        """check_convergence writes convergence data to run_dir."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        assert "convergence_" in cc["action"]
        assert ".json" in cc["action"]


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

    def test_check_remediation_budget_routes_exhausted_to_decompose(self) -> None:
        """Budget exhausted routes to snap_for_size_review (decomposition)."""
        data = _load_loop()
        crb = data["states"]["check_remediation_budget"]
        assert crb["on_no"] == "snap_for_size_review"

    def test_context_max_remediation_passes_set(self) -> None:
        """max_remediation_passes context variable is set to 3."""
        data = _load_loop()
        assert data["context"]["max_remediation_passes"] == 3


# ---------------------------------------------------------------------------
# TestDecompositionChain — States: snap_for_size_review, run_size_review,
#   detect_children, enqueue_children, skip_issue
# ---------------------------------------------------------------------------


class TestDecompositionChain:
    """Tests for the decomposition path (size review → child detection → enqueue)."""

    def test_snap_for_size_review_snapshots_issues(self) -> None:
        """snap_for_size_review snapshots ll-issues list --json output."""
        data = _load_loop()
        snap = data["states"]["snap_for_size_review"]
        action = snap["action"]
        assert "ll-issues list --json" in action
        assert "issues_before_" in action

    def test_snap_for_size_review_routes_to_run_size_review(self) -> None:
        """snap_for_size_review always transitions to run_size_review."""
        data = _load_loop()
        snap = data["states"]["snap_for_size_review"]
        assert snap["next"] == "run_size_review"

    def test_run_size_review_is_slash_command(self) -> None:
        """run_size_review invokes /ll:issue-size-review as slash_command."""
        data = _load_loop()
        rsr = data["states"]["run_size_review"]
        assert rsr["action_type"] == "slash_command"
        assert "/ll:issue-size-review" in rsr["action"]

    def test_run_size_review_wraps_with_rate_limit_handling(self) -> None:
        """run_size_review uses with_rate_limit_handling fragment."""
        data = _load_loop()
        rsr = data["states"]["run_size_review"]
        assert rsr.get("fragment") == "with_rate_limit_handling"

    def test_detect_children_uses_comm_diff(self) -> None:
        """detect_children uses comm -13 for pre/post diff."""
        data = _load_loop()
        dc = data["states"]["detect_children"]
        action = dc["action"]
        assert "comm -13" in action

    def test_detect_children_filters_by_parent_reference(self) -> None:
        """detect_children filters candidates by parent ref in issue files."""
        data = _load_loop()
        dc = data["states"]["detect_children"]
        action = dc["action"]
        assert "parent:" in action or "Decomposed from" in action

    def test_detect_children_routes_yes_to_enqueue_children(self) -> None:
        """detect_children routes to enqueue_children when children found."""
        data = _load_loop()
        dc = data["states"]["detect_children"]
        assert dc["on_yes"] == "enqueue_children"

    def test_detect_children_routes_no_to_skip_issue(self) -> None:
        """detect_children routes to skip_issue when no children found."""
        data = _load_loop()
        dc = data["states"]["detect_children"]
        assert dc["on_no"] == "skip_issue"

    def test_enqueue_children_has_cycle_detection(self) -> None:
        """enqueue_children performs cycle detection via Python visited set."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert "visited" in action.lower()
        assert "cycles.txt" in action

    def test_enqueue_children_prepends_depth_first(self) -> None:
        """enqueue_children prepends children before existing queue (depth-first)."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert "echo \"$CHILDREN\"" in action
        assert "echo \"$EXISTING\"" in action

    def test_enqueue_children_routes_to_dequeue_next(self) -> None:
        """enqueue_children routes to dequeue_next after enqueuing."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        assert ec["on_yes"] == "dequeue_next"
        assert ec["on_no"] == "dequeue_next"

    def test_skip_issue_routes_to_dequeue_next(self) -> None:
        """skip_issue always routes to dequeue_next."""
        data = _load_loop()
        si = data["states"]["skip_issue"]
        assert si["next"] == "dequeue_next"


# ---------------------------------------------------------------------------
# TestCycleDetection — State: enqueue_children (cycle detection logic)
# ---------------------------------------------------------------------------


class TestCycleDetection:
    """Tests for cycle detection in enqueue_children."""

    def test_enqueue_children_checks_visited_before_enqueue(self) -> None:
        """enqueue_children reads visited.txt before enqueuing candidates."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert "visited.txt" in action

    def test_cycle_candidates_logged_to_cycles_txt(self) -> None:
        """Cycle-detected IDs are logged to cycles.txt."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert "cycles.txt" in action

    def test_enqueue_children_includes_queue_in_visited_set(self) -> None:
        """enqueue_children builds visited set from visited.txt + queue.txt."""
        data = _load_loop()
        ec = data["states"]["enqueue_children"]
        action = ec["action"]
        assert "queue.txt" in action, "Must include current queue in visited set"


# ---------------------------------------------------------------------------
# TestRateLimitAndErrorHandling — State: rate_limit_diagnostic, all wrappers
# ---------------------------------------------------------------------------


class TestRateLimitAndErrorHandling:
    """Tests for rate-limit and error handling states."""

    def test_rate_limit_diagnostic_logs_to_rate_limits_txt(self) -> None:
        """rate_limit_diagnostic writes to rate_limits.txt."""
        data = _load_loop()
        rld = data["states"]["rate_limit_diagnostic"]
        assert "rate_limits.txt" in rld["action"]

    def test_rate_limit_diagnostic_routes_to_dequeue_next(self) -> None:
        """rate_limit_diagnostic skips current issue and continues."""
        data = _load_loop()
        rld = data["states"]["rate_limit_diagnostic"]
        assert rld["next"] == "dequeue_next"

    def test_all_slash_command_states_have_rate_limit_handling(self) -> None:
        """All slash_command states wrap with with_rate_limit_handling."""
        data = _load_loop()
        slash_states = [
            name for name, state in data["states"].items()
            if state.get("action_type") == "slash_command"
        ]
        for name in slash_states:
            state = data["states"][name]
            assert state.get("fragment") == "with_rate_limit_handling", (
                f"State '{name}' is slash_command but missing with_rate_limit_handling"
            )

    def test_all_rate_limited_states_have_exhaustion_handler(self) -> None:
        """All states with with_rate_limit_handling have on_rate_limit_exhausted."""
        data = _load_loop()
        for name, state in data["states"].items():
            if state.get("fragment") == "with_rate_limit_handling":
                assert "on_rate_limit_exhausted" in state, (
                    f"State '{name}' has rate_limit_handling but no on_rate_limit_exhausted"
                )

    def test_implement_state_has_error_handler(self) -> None:
        """implement state has on_error handler."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert "on_error" in impl

    def test_failed_state_writes_checkpoint(self) -> None:
        """failed state writes checkpoint.json for potential resume."""
        data = _load_loop()
        failed = data["states"]["failed"]
        action = failed["action"]
        assert "checkpoint.json" in action

    def test_done_state_writes_summary(self) -> None:
        """done state writes summary.json with completion stats."""
        data = _load_loop()
        done = data["states"]["done"]
        action = done["action"]
        assert "summary.json" in action


# ---------------------------------------------------------------------------
# TestRoutingStructure — All states have valid routing
# ---------------------------------------------------------------------------


class TestRoutingStructure:
    """Tests that the FSM has correct routing (no dead ends, all reachable)."""

    def test_every_state_has_outgoing_edge(self) -> None:
        """Every non-terminal state has at least one outgoing transition."""
        data = _load_loop()
        for name, state in data["states"].items():
            if state.get("terminal"):
                continue
            has_outgoing = any(
                key in state
                for key in ("next", "on_yes", "on_no", "on_error", "on_success", "on_failure")
            )
            assert has_outgoing, f"State '{name}' has no outgoing transitions"

    def test_all_referenced_targets_exist(self) -> None:
        """Every state referenced in routing exists in the states dict."""
        data = _load_loop()
        state_names = set(data["states"].keys())
        routing_keys = ("next", "on_yes", "on_no", "on_error", "on_success", "on_failure",
                        "on_rate_limit_exhausted")
        for name, state in data["states"].items():
            for key in routing_keys:
                target = state.get(key)
                if target and isinstance(target, str):
                    assert target in state_names, (
                        f"State '{name}' routes to '{target}' via '{key}', "
                        f"but '{target}' is not a state"
                    )

    def test_all_states_reachable_from_init(self) -> None:
        """All states are reachable from the initial state."""
        data = _load_loop()
        state_names = set(data["states"].keys())

        # Build reachability graph
        routing_keys = ("next", "on_yes", "on_no", "on_error", "on_success", "on_failure",
                        "on_rate_limit_exhausted")
        reachable = set()
        queue = ["init"]
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

        unreachable = state_names - reachable
        assert not unreachable, f"Unreachable states: {sorted(unreachable)}"

    def test_terminal_states_have_no_outgoing(self) -> None:
        """Terminal states have no outgoing routing."""
        data = _load_loop()
        for name, state in data["states"].items():
            if state.get("terminal"):
                routing_keys = ("next", "on_yes", "on_no", "on_error", "on_success", "on_failure")
                for key in routing_keys:
                    assert key not in state, (
                        f"Terminal state '{name}' has outgoing routing via '{key}'"
                    )

    def test_no_bare_pass_token(self) -> None:
        """No output_contains evaluator uses bare 'PASS' as pattern."""
        data = _load_loop()
        for name, state in data["states"].items():
            evaluate = state.get("evaluate", {})
            if evaluate.get("type") == "output_contains":
                pattern = evaluate.get("pattern", "")
                assert pattern != "PASS", (
                    f"State '{name}' uses bare 'PASS' in output_contains — "
                    "use compound tokens like 'CONVERGED_PASS'"
                )

    def test_mr3_no_loops_tmp_writes(self) -> None:
        """No state writes to .loops/tmp/ (MR-3: run_dir isolation)."""
        data = _load_loop()
        for name, state in data["states"].items():
            action = state.get("action", "")
            if isinstance(action, str):
                assert ".loops/tmp/" not in action, (
                    f"State '{name}' writes to .loops/tmp/ — use ${context.run_dir}/ instead"
                )

    def test_mr1_non_llm_evaluators_present(self) -> None:
        """States that perform routing decisions have non-LLM evaluators (MR-1).

        Key routing states (check_convergence, check_remediation_budget, diagnose)
        use shell/output_numeric/output_contains evaluators — not purely LLM judgment.
        """
        data = _load_loop()
        mr1_states = {
            "check_convergence": "output_contains",  # via route_conv_pass/route_conv_improved
            "check_remediation_budget": "output_numeric",
            "diagnose": "output_contains",  # via route_d_* chain
            "check_depth": "output_numeric",
            "check_readiness": "exit_code",
            "check_decision_needed": "exit_code",
        }
        for state_name, expected_eval_type in mr1_states.items():
            state = data["states"].get(state_name)
            assert state is not None, f"MR-1 state '{state_name}' not found"
            # Diagnose and check_convergence use chained routers for output_contains
            if state_name in ("diagnose", "check_convergence"):
                # The router states carry the evaluator
                if state_name == "diagnose":
                    router = data["states"]["route_d_implement"]
                else:
                    router = data["states"]["route_conv_pass"]
                evaluate = router.get("evaluate", {})
                assert evaluate.get("type") == "output_contains", (
                    f"{state_name} router should use output_contains, got {evaluate.get('type')}"
                )
            else:
                evaluate = state.get("evaluate", {})
                assert evaluate.get("type") == expected_eval_type or (
                    state.get("fragment") == "shell_exit" and expected_eval_type == "exit_code"
                ), (
                    f"State '{state_name}' evaluator type {evaluate.get('type')} != "
                    f"expected {expected_eval_type}"
                )

    def test_check_convergence_pairing_uses_non_llm(self) -> None:
        """check_convergence output is routed via non-LLM output_contains evaluators."""
        data = _load_loop()
        for router_name in ("route_conv_pass", "route_conv_improved"):
            router = data["states"][router_name]
            evaluate = router["evaluate"]
            assert evaluate["type"] == "output_contains", (
                f"{router_name} must use output_contains (non-LLM) for MR-1"
            )


# ---------------------------------------------------------------------------
# TestValidation — Full FSM validation
# ---------------------------------------------------------------------------


class TestValidation:
    """End-to-end validation tests for the rn-implement loop."""

    def test_load_and_validate_no_errors(self) -> None:
        """rn-implement.yaml loads and validates without errors."""
        fsm, warnings = load_and_validate(RN_IMPLEMENT_PATH)
        assert fsm is not None, "FSM must load successfully"
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"Validation errors: {[str(e) for e in error_list]}"

    def test_no_dead_end_states(self) -> None:
        """No non-terminal states dead-end without routing."""
        data = _load_loop()
        for name, state in data["states"].items():
            if state.get("terminal"):
                continue
            # States with only next: are fine (unconditional)
            if "next" in state:
                continue
            # Must have at least one conditional routing target
            has_route = any(
                k in state
                for k in ("on_yes", "on_no", "on_success", "on_failure", "on_error")
            )
            assert has_route, f"Non-terminal state '{name}' has no routing"

    def test_context_defaults_match_spec(self) -> None:
        """Context defaults match the specification."""
        data = _load_loop()
        ctx = data["context"]
        assert ctx["readiness_threshold"] == 85
        assert ctx["outcome_threshold"] == 75
        assert ctx["max_depth"] == 3
        assert ctx["max_remediation_passes"] == 3

    def test_meta_self_eval_ok_is_false(self) -> None:
        """meta_self_eval_ok is false (MR-1 enforced)."""
        data = _load_loop()
        assert data["meta_self_eval_ok"] is False

    def test_shared_state_ok_is_false(self) -> None:
        """shared_state_ok is false (MR-3 enforced)."""
        data = _load_loop()
        assert data["shared_state_ok"] is False

    def test_initial_state_exists(self) -> None:
        """initial state 'init' exists in states dict."""
        data = _load_loop()
        assert data["initial"] in data["states"]

    def test_state_count_matches_expected(self) -> None:
        """rn-implement has at least 30 states (31+ check_depth)."""
        data = _load_loop()
        state_count = len(data["states"])
        assert state_count >= 31, (
            f"Expected 31+ states, got {state_count}"
        )

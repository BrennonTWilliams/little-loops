"""Tests for the rn-remediate standalone sub-loop.

Extracted from test_rn_implement.py as part of ENH-1938 (decompose
rn-implement.yaml monolith into sub-loops).
"""

from __future__ import annotations

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

    def test_diagnose_on_error_routes_to_failed(self) -> None:
        """diagnose on_error routes to failed (terminal) — no parent decomposition path."""
        data = _load_loop()
        diag = data["states"]["diagnose"]
        assert diag["on_error"] == "emit_implement_failed"

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
        # route_d_refine → refine or failed (DECOMPOSE fallthrough → terminal)
        assert data["states"]["route_d_refine"]["on_yes"] == "refine"
        assert data["states"]["route_d_refine"]["on_no"] == "emit_needs_decompose"

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

    def test_implement_routes_to_done(self) -> None:
        """implement routes to done (terminal) on success — queue management stays in parent."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl["on_yes"] == "emit_implemented"

    def test_implement_failure_routes_to_failed(self) -> None:
        """implement routes to failed (terminal) on failure — issue skipping stays in parent."""
        data = _load_loop()
        impl = data["states"]["implement"]
        assert impl["on_no"] == "emit_implement_failed"
        assert impl["on_error"] == "emit_implement_failed"

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

    def test_refine_failure_routes_to_failed(self) -> None:
        """refine routes to failed (terminal) on error — issue skipping stays in parent."""
        data = _load_loop()
        ref = data["states"]["refine"]
        assert ref["on_error"] == "emit_implement_failed"


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

    def test_check_convergence_captures_as_convergence_result(self) -> None:
        """check_convergence captures output as convergence_result."""
        data = _load_loop()
        cc = data["states"]["check_convergence"]
        assert cc.get("capture") == "convergence_result"

    def test_convergence_router_chain_is_correct(self) -> None:
        """Convergence routing: PASS → implement, IMPROVED → budget, STALLED → failed (terminal)."""
        data = _load_loop()
        # route_conv_pass
        rcp = data["states"]["route_conv_pass"]
        assert rcp["on_yes"] == "implement"
        assert rcp["on_no"] == "route_conv_improved"
        # route_conv_improved
        rci = data["states"]["route_conv_improved"]
        assert rci["on_yes"] == "check_remediation_budget"
        assert rci["on_no"] == "emit_needs_decompose"

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

    def test_check_remediation_budget_routes_exhausted_to_failed(self) -> None:
        """Budget exhausted routes to failed (terminal) — decomposition stays in parent."""
        data = _load_loop()
        crb = data["states"]["check_remediation_budget"]
        assert crb["on_no"] == "emit_needs_decompose"

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

        # diagnose uses output_contains via router chain
        router = data["states"]["route_d_implement"]
        assert router["evaluate"]["type"] == "output_contains"

        # check_convergence uses output_contains via router chain
        router = data["states"]["route_conv_pass"]
        assert router["evaluate"]["type"] == "output_contains"

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
        queue = ["assess"]
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

    def test_no_dead_end_states(self) -> None:
        """No non-terminal states dead-end without routing."""
        data = _load_loop()
        for name, state in data["states"].items():
            if state.get("terminal"):
                continue
            if "next" in state:
                continue
            has_route = any(
                k in state for k in ("on_yes", "on_no", "on_success", "on_failure", "on_error")
            )
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
            "emit_implement_failed",
            "emit_scores_missing",
        ):
            assert name in data["states"], f"missing emit state {name}"

    def test_emit_tokens_written_to_run_dir(self) -> None:
        data = _load_loop()
        expected = {
            "emit_implemented": "IMPLEMENTED",
            "emit_needs_decompose": "NEEDS_DECOMPOSE",
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
        data = _load_loop()
        assert data["states"]["implement"]["on_yes"] == "emit_implemented"
        assert data["states"]["implement"]["on_no"] == "emit_implement_failed"

    def test_needs_decompose_only_on_stall_paths(self) -> None:
        data = _load_loop()
        assert data["states"]["route_d_refine"]["on_no"] == "emit_needs_decompose"
        assert data["states"]["route_conv_improved"]["on_no"] == "emit_needs_decompose"
        assert data["states"]["check_remediation_budget"]["on_no"] == "emit_needs_decompose"

    def test_rate_limit_diagnostic_writes_token_and_fails(self) -> None:
        data = _load_loop()
        rld = data["states"]["rate_limit_diagnostic"]
        assert "RATE_LIMITED" in rld["action"]
        assert rld["next"] == "failed", "rate-limit must NOT terminate in done (GAP A)"

    def test_check_readiness_passes_thresholds(self) -> None:
        data = _load_loop()
        action = data["states"]["check_readiness"]["action"]
        assert "--readiness" in action and "${context.readiness_threshold}" in action
        assert "--outcome" in action and "${context.outcome_threshold}" in action

    def test_diagnose_routes_missing_artifacts_to_wire(self) -> None:
        data = _load_loop()
        action = data["states"]["diagnose"]["action"]
        assert 'MISSING_ARTIFACTS" = "true"' in action.replace("'", '"') or \
            'MISSING_ARTIFACTS' in action and 'WIRE' in action

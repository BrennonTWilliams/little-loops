"""Tests for the rn-implement queue orchestrator FSM loop."""

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
        assert "${context.input}" in init["action"]
        assert " -z " in init["action"]  # empty check

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
        assert deq["on_no"] == "report"

    def test_dequeue_next_captures_input(self) -> None:
        """dequeue_next captures the popped issue ID as input."""
        data = _load_loop()
        deq = data["states"]["dequeue_next"]
        assert deq.get("capture") == "input"

    def test_check_depth_uses_output_numeric(self) -> None:
        """check_depth uses output_numeric evaluator comparing depth to max_depth."""
        data = _load_loop()
        cd = data["states"]["check_depth"]
        evaluate = cd["evaluate"]
        assert evaluate["type"] == "output_numeric"
        assert evaluate["operator"] == "lt"
        assert evaluate["target"] == "${context.max_depth}"

    def test_check_depth_routes_below_cap_to_run_remediation(self) -> None:
        """check_depth routes to run_remediation when depth is below cap."""
        data = _load_loop()
        cd = data["states"]["check_depth"]
        assert cd["on_yes"] == "run_remediation", (
            "on_yes (depth < max) should go to run_remediation"
        )
        assert cd["on_no"] == "mark_depth_capped", "on_no (depth >= max) should cap"

    def test_check_depth_captures_current_depth(self) -> None:
        """check_depth captures the raw depth value for sub-loop delegation."""
        data = _load_loop()
        cd = data["states"]["check_depth"]
        assert cd.get("capture") == "current_depth", (
            "check_depth must capture current_depth for run_decomposition binding"
        )

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
# TestRateLimitAndErrorHandling — State: rate_limit_diagnostic, delegation wrappers
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

    def test_orchestrator_has_no_inline_slash_commands(self) -> None:
        """Orchestrator delegates all LLM actions to sub-loops — no inline slash_command states."""
        data = _load_loop()
        slash_states = [
            name
            for name, state in data["states"].items()
            if state.get("action_type") == "slash_command"
        ]
        assert len(slash_states) == 0, (
            f"Orchestrator should have 0 slash_command states; "
            f"all LLM actions are delegated to sub-loops. Found: {slash_states}"
        )

    def test_delegation_states_have_no_dead_exhaustion_handler(self) -> None:
        """ENH-1977: a loop child can never yield a rate-limit verdict, so the
        on_rate_limit_exhausted handler is removed from delegation states (the
        RATE_LIMITED outcome now arrives via the token channel)."""
        data = _load_loop()
        for name, state in data["states"].items():
            if state.get("loop") is not None:
                assert "on_rate_limit_exhausted" not in state, (
                    f"Delegation state '{name}' should not carry a dead exhaustion handler"
                )

    def test_failed_state_has_no_dead_checkpoint(self) -> None:
        """ENH-1977 Fix 3: the dead checkpoint.json write is removed (failed is a
        bare terminal whose action would be skipped by the runner anyway)."""
        data = _load_loop()
        failed = data["states"]["failed"]
        assert "action" not in failed
        assert "checkpoint.json" not in str(failed)


# ---------------------------------------------------------------------------
# TestSubLoopDelegation — States: run_remediation, run_decomposition
# ---------------------------------------------------------------------------


class TestSubLoopDelegation:
    """Tests for sub-loop delegation states."""

    # --- run_remediation ---

    def test_run_remediation_is_loop_delegation(self) -> None:
        """run_remediation delegates to rn-remediate sub-loop."""
        data = _load_loop()
        state = data["states"]["run_remediation"]
        assert state.get("loop") == "rn-remediate"

    def test_run_remediation_has_with_bindings(self) -> None:
        """run_remediation passes issue_id, thresholds, and max_passes via with: bindings."""
        data = _load_loop()
        with_bindings = data["states"]["run_remediation"]["with"]
        assert with_bindings["issue_id"] == "${captured.input.output}"
        assert with_bindings["readiness_threshold"] == "${context.readiness_threshold}"
        assert with_bindings["outcome_threshold"] == "${context.outcome_threshold}"
        assert with_bindings["max_remediation_passes"] == "${context.max_remediation_passes}"

    def test_run_remediation_routes_on_success_to_dequeue_next(self) -> None:
        """run_remediation routes to dequeue_next on success (child done = implemented)."""
        data = _load_loop()
        state = data["states"]["run_remediation"]
        assert state["on_success"] == "classify_remediation"

    def test_run_remediation_routes_on_failure_to_run_decomposition(self) -> None:
        """run_remediation routes to run_decomposition on failure (child stalled)."""
        data = _load_loop()
        state = data["states"]["run_remediation"]
        assert state["on_failure"] == "classify_remediation"

    def test_run_remediation_routes_on_error_to_skip_issue(self) -> None:
        """run_remediation routes to skip_issue on error."""
        data = _load_loop()
        state = data["states"]["run_remediation"]
        assert state["on_error"] == "classify_remediation"

    def test_run_remediation_routes_on_no_to_run_decomposition(self) -> None:
        """run_remediation routes to run_decomposition on no (timeout/max_iter/never-started)."""
        data = _load_loop()
        state = data["states"]["run_remediation"]
        assert state.get("on_no") is None  # ENH-1977: consolidated into on_failure

    def test_run_remediation_has_rate_limit_exhausted_handler(self) -> None:
        """run_remediation routes to rate_limit_diagnostic on rate limit exhaustion."""
        data = _load_loop()
        state = data["states"]["run_remediation"]
        assert "on_rate_limit_exhausted" not in state  # ENH-1977: dead route removed

    # --- run_decomposition ---

    def test_run_decomposition_is_loop_delegation(self) -> None:
        """run_decomposition delegates to rn-decompose sub-loop."""
        data = _load_loop()
        state = data["states"]["run_decomposition"]
        assert state.get("loop") == "rn-decompose"

    def test_run_decomposition_has_with_bindings(self) -> None:
        """run_decomposition passes issue_id, parent_depth, and run_dir via with: bindings."""
        data = _load_loop()
        with_bindings = data["states"]["run_decomposition"]["with"]
        assert with_bindings["issue_id"] == "${captured.input.output}"
        assert with_bindings["parent_depth"] == "${captured.current_depth.output}"
        assert with_bindings["run_dir"] == "${captured.run_dir.output}"

    def test_run_decomposition_routes_on_success_to_dequeue_next(self) -> None:
        """run_decomposition routes to dequeue_next on success (children enqueued)."""
        data = _load_loop()
        state = data["states"]["run_decomposition"]
        assert state["on_success"] == "classify_decomposition"

    def test_run_decomposition_routes_on_failure_to_skip_issue(self) -> None:
        """run_decomposition routes to skip_issue on failure (no children found)."""
        data = _load_loop()
        state = data["states"]["run_decomposition"]
        assert state["on_failure"] == "classify_decomposition"

    def test_run_decomposition_routes_on_error_to_skip_issue(self) -> None:
        """run_decomposition routes to skip_issue on error."""
        data = _load_loop()
        state = data["states"]["run_decomposition"]
        assert state["on_error"] == "classify_decomposition"

    def test_run_decomposition_routes_on_no_to_skip_issue(self) -> None:
        """run_decomposition routes to skip_issue on no (timeout/max_iter/never-started)."""
        data = _load_loop()
        state = data["states"]["run_decomposition"]
        assert state.get("on_no") is None  # ENH-1977: consolidated into on_failure

    def test_run_decomposition_has_rate_limit_exhausted_handler(self) -> None:
        """run_decomposition routes to skip_issue on rate limit exhaustion."""
        data = _load_loop()
        state = data["states"]["run_decomposition"]
        assert "on_rate_limit_exhausted" not in state  # ENH-1977: dead route removed


# ---------------------------------------------------------------------------
# TestReportAndTerminal — States: report, done
# ---------------------------------------------------------------------------


class TestReportAndTerminal:
    """Tests for the report→done pre-terminal pattern (avoids terminal-state caveat)."""

    def test_report_state_exists_and_is_not_terminal(self) -> None:
        """report state exists and is not terminal (must execute before done)."""
        data = _load_loop()
        report = data["states"]["report"]
        assert report is not None, "report state must exist"
        assert report.get("terminal") is not True, (
            "report must not be terminal — its action would be skipped"
        )

    def test_report_state_writes_summary_json(self) -> None:
        """report state writes summary.json with completion stats."""
        data = _load_loop()
        report = data["states"]["report"]
        action = report["action"]
        assert "summary.json" in action
        assert "dequeue_count.txt" in action
        assert "implemented_count.txt" in action
        assert "decomposed_count.txt" in action

    def test_report_state_transitions_to_done(self) -> None:
        """report state transitions to done via next:."""
        data = _load_loop()
        report = data["states"]["report"]
        assert report["next"] == "done", (
            "report must transition to done via next: to avoid terminal-state caveat"
        )

    def test_done_state_is_bare_terminal(self) -> None:
        """done state is a bare terminal anchor with no action."""
        data = _load_loop()
        done = data["states"]["done"]
        assert done.get("terminal") is True
        assert "action" not in done, (
            "done must be bare terminal — report handles the summary action"
        )
        # No routing keys on a bare terminal
        for key in ("next", "on_yes", "on_no", "on_error", "on_success", "on_failure"):
            assert key not in done, f"Bare terminal done must not have '{key}' routing"


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

    def test_all_states_reachable_from_init(self) -> None:
        """All states are reachable from the initial state."""
        data = _load_loop()
        state_names = set(data["states"].keys())

        # Build reachability graph
        routing_keys = (
            "next",
            "on_yes",
            "on_no",
            "on_error",
            "on_success",
            "on_failure",
            "on_rate_limit_exhausted",
        )
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
                    f"State '{name}' writes to .loops/tmp/ — use ${{context.run_dir}}/ instead"
                )

    def test_mr1_non_llm_evaluators_present(self) -> None:
        """Routing decisions use non-LLM evaluators (MR-1).

        Only check_depth remains in the orchestrator — other MR-1 states
        (diagnose, check_convergence, check_remediation_budget, check_readiness,
        check_decision_needed) moved to the rn-remediate sub-loop.
        """
        data = _load_loop()
        cd = data["states"]["check_depth"]
        evaluate = cd.get("evaluate", {})
        assert evaluate.get("type") == "output_numeric", (
            f"check_depth must use output_numeric (MR-1), got {evaluate.get('type')}"
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
            # Sub-loop delegation states have on_success/on_failure/on_error
            if state.get("loop") is not None:
                continue
            # Must have at least one conditional routing target
            has_route = any(
                k in state for k in ("on_yes", "on_no", "on_success", "on_failure", "on_error")
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

    def test_state_count_is_orchestrator_sized(self) -> None:
        """rn-implement orchestrator has ≤14 states (down from 32-state monolith)."""
        data = _load_loop()
        state_count = len(data["states"])
        assert state_count <= 24, f"Expected ≤24 states in orchestrator, got {state_count}"
        assert state_count >= 10, f"Expected ≥10 states in orchestrator, got {state_count}"


# ============================================================================
# TestParentClassifier — ENH-1977 Fix 1/3 (rn-implement parent side)
# ============================================================================


class TestParentClassifier:
    """Parent classifies sub-loop outcomes via the token channel."""

    def test_classifier_states_exist(self) -> None:
        data = _load_loop()
        for name in (
            "classify_remediation",
            "route_rem_implemented",
            "route_rem_decompose",
            "route_rem_manual_review",
            "mark_blocked",
            "route_rem_rate_limited",
            "classify_decomposition",
            "route_dec_decomposed",
            "route_dec_no_children",
            "route_dec_rate_limited",
            "record_failure",
        ):
            assert name in data["states"], f"missing {name}"

    def test_manual_review_routes_to_mark_blocked(self) -> None:
        data = _load_loop()
        rmr = data["states"]["route_rem_manual_review"]
        assert rmr["on_yes"] == "mark_blocked"
        assert rmr["on_no"] == "route_rem_rate_limited"

    def test_mark_blocked_writes_file_and_dequeues(self) -> None:
        data = _load_loop()
        mb = data["states"]["mark_blocked"]
        assert "blocked.txt" in mb["action"]
        assert mb["next"] == "dequeue_next"

    def test_loop_states_route_to_classifiers(self) -> None:
        data = _load_loop()
        rem = data["states"]["run_remediation"]
        assert rem["on_success"] == "classify_remediation"
        assert rem["on_failure"] == "classify_remediation"
        assert rem["on_error"] == "classify_remediation"
        dec = data["states"]["run_decomposition"]
        assert dec["on_success"] == "classify_decomposition"

    def test_dead_rate_limit_routes_removed(self) -> None:
        data = _load_loop()
        assert "on_rate_limit_exhausted" not in data["states"]["run_remediation"]
        assert "on_rate_limit_exhausted" not in data["states"]["run_decomposition"]
        assert "max_rate_limit_retries" not in data["states"]["run_remediation"]

    def test_implemented_routes_to_dequeue(self) -> None:
        data = _load_loop()
        assert data["states"]["route_rem_implemented"]["on_yes"] == "dequeue_next"

    def test_only_needs_decompose_routes_to_decomposition(self) -> None:
        data = _load_loop()
        assert data["states"]["route_rem_decompose"]["on_yes"] == "run_decomposition"

    def test_rate_limited_routes_to_diagnostic(self) -> None:
        data = _load_loop()
        assert data["states"]["route_rem_rate_limited"]["on_yes"] == "rate_limit_diagnostic"
        assert data["states"]["route_dec_rate_limited"]["on_yes"] == "rate_limit_diagnostic"

    def test_record_failure_appends_and_dequeues(self) -> None:
        data = _load_loop()
        rf = data["states"]["record_failure"]
        assert "failures.txt" in rf["action"]
        assert rf["next"] == "dequeue_next"

    def test_report_includes_rate_limited(self) -> None:
        data = _load_loop()
        assert "rate_limited" in data["states"]["report"]["action"]

    def test_init_supports_resume(self) -> None:
        data = _load_loop()
        action = data["states"]["init"]["action"]
        assert "${context.resume}" in action
        assert "queue.txt" in action

    def test_failed_is_bare_terminal(self) -> None:
        """Fix 3: the dead checkpoint write is removed; failed is a bare terminal."""
        data = _load_loop()
        failed = data["states"]["failed"]
        assert failed.get("terminal") is True
        assert "action" not in failed
        assert "checkpoint.json" not in str(failed)

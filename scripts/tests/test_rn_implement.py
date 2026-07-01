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

    def test_dequeue_next_is_mode_dispatch(self) -> None:
        """dequeue_next is a schedule_mode dispatch (FEAT-1991), not the FIFO pop itself."""
        data = _load_loop()
        deq = data["states"]["dequeue_next"]
        assert deq.get("action_type") == "shell"
        assert "schedule_mode" in deq["action"]
        assert "value_ranked" in deq["action"]

    def test_dequeue_next_routes_value_ranked_to_select_next(self) -> None:
        """dequeue_next routes to select_next when schedule_mode=value_ranked (on_yes)."""
        data = _load_loop()
        deq = data["states"]["dequeue_next"]
        assert deq["on_yes"] == "select_next"

    def test_dequeue_next_routes_fifo_to_fifo_pop(self) -> None:
        """dequeue_next routes to fifo_pop for default fifo mode (on_no)."""
        data = _load_loop()
        deq = data["states"]["dequeue_next"]
        assert deq["on_no"] == "fifo_pop"
        assert deq["on_error"] == "fifo_pop"

    def test_fifo_pop_uses_queue_pop_fragment(self) -> None:
        """fifo_pop uses the queue_pop fragment (FIFO path)."""
        data = _load_loop()
        fp = data["states"]["fifo_pop"]
        assert fp.get("fragment") == "queue_pop"

    def test_fifo_pop_captures_input(self) -> None:
        """fifo_pop captures the popped issue ID as input."""
        data = _load_loop()
        fp = data["states"]["fifo_pop"]
        assert fp.get("capture") == "input"

    def test_fifo_pop_routes_to_check_blocked_by(self) -> None:
        """fifo_pop.on_no (issue dequeued) routes to check_blocked_by; on_yes (QUEUE_EMPTY) to report."""
        data = _load_loop()
        fp = data["states"]["fifo_pop"]
        assert fp["on_yes"] == "report"  # output_contains(QUEUE_EMPTY): yes = queue empty
        assert fp["on_no"] == "check_blocked_by"  # no = issue dequeued → blocked_by gate

    def test_fifo_pop_references_depth_map(self) -> None:
        """fifo_pop references depth_map.txt and current_depth.txt."""
        data = _load_loop()
        fp = data["states"]["fifo_pop"]
        assert "depth_map.txt" in fp["action"]
        assert "current_depth.txt" in fp["action"]

    def test_check_depth_uses_output_numeric(self) -> None:
        """check_depth uses output_numeric evaluator comparing depth to max_depth."""
        data = _load_loop()
        cd = data["states"]["check_depth"]
        evaluate = cd["evaluate"]
        assert evaluate["type"] == "output_numeric"
        assert evaluate["operator"] == "lt"
        assert evaluate["target"] == "${context.max_depth}"

    def test_check_depth_routes_below_cap_to_check_issue_status(self) -> None:
        """BUG-2201: check_depth routes to check_issue_status (pre-flight gate) when depth is below cap."""
        data = _load_loop()
        cd = data["states"]["check_depth"]
        assert cd["on_yes"] == "check_issue_status", (
            "on_yes (depth < max) should go to check_issue_status pre-flight gate (BUG-2201)"
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
        """mark_depth_capped always transitions to dequeue_next (the dispatch)."""
        data = _load_loop()
        mdc = data["states"]["mark_depth_capped"]
        assert mdc["next"] == "dequeue_next"

    def test_mark_depth_capped_logs_to_depth_capped_txt(self) -> None:
        """mark_depth_capped writes to depth_capped.txt under run_dir."""
        data = _load_loop()
        mdc = data["states"]["mark_depth_capped"]
        assert "depth_capped.txt" in mdc["action"]


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
        """run_remediation passes issue_id, thresholds, max_passes, and run_dir via with: bindings."""
        data = _load_loop()
        with_bindings = data["states"]["run_remediation"]["with"]
        assert with_bindings["issue_id"] == "${captured.input.output}"
        assert with_bindings["readiness_threshold"] == "${context.readiness_threshold}"
        assert with_bindings["outcome_threshold"] == "${context.outcome_threshold}"
        assert with_bindings["max_remediation_passes"] == "${context.max_remediation_passes}"
        assert with_bindings["run_dir"] == "${captured.run_dir.output}", (
            "run_remediation must pass run_dir to rn-remediate so emit_implemented "
            "writes to the outer loop's run_dir (BUG-2170)"
        )

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

    def test_run_remediation_routes_on_error_to_sub_loop_crash(self) -> None:
        """ENH-2005: run_remediation routes on_error to record_sub_loop_crash.

        A sub-loop crash/timeout can fire before the child writes its outcome
        token, so on_error must NOT be laundered through classify_remediation
        (which would hit the `|| echo IMPLEMENT_FAILED` fallback).
        """
        data = _load_loop()
        state = data["states"]["run_remediation"]
        assert state["on_error"] == "record_sub_loop_crash"

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

    def test_run_decomposition_routes_on_error_to_sub_loop_crash(self) -> None:
        """ENH-2005: run_decomposition routes on_error to record_sub_loop_crash.

        Same rationale as run_remediation: an infrastructure crash must not be
        laundered into SIZE_REVIEW_FAILED via classify_decomposition's fallback.
        """
        data = _load_loop()
        state = data["states"]["run_decomposition"]
        assert state["on_error"] == "record_sub_loop_crash"

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

    def test_report_decomposed_and_skipped_use_distinct_sources(self) -> None:
        """BUG-2289: report reads decomposed and skipped from separate, disjoint files.

        decomposed_count.txt and skipped.txt must both appear as distinct tally
        sources in the report action so that no single issue can inflate both
        counters simultaneously.
        """
        data = _load_loop()
        action = data["states"]["report"]["action"]
        assert "decomposed_count.txt" in action, (
            "report must read decomposed count from decomposed_count.txt"
        )
        assert "skipped.txt" in action, "report must read skipped count from skipped.txt"


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
        assert ctx["schedule_mode"] == "fifo", "schedule_mode must default to fifo"

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
        """rn-implement orchestrator stays within orchestrator bounds.

        FEAT-1991 added fifo_pop + select_next (+2 states), raising the ceiling to 26.
        BUG-2006 added route_dec_stalled_origin + mark_deferred (+2), raising it to 28.
        ENH-2008 added check_blocked_by + route_blocked_by (+2), raising it to 30.
        ENH-2195 added re_enqueue_unblocked (+1), raising it to 31.
        ENH-2247 added route_rem_scores_missing + route_dec_size_review_failed +
        record_scores_missing + record_size_review_failed (+4), raising it to 35 —
        splitting SCORES_MISSING / SIZE_REVIEW_FAILED diagnostics out of record_failure.
        feat(loops) bbf77018 added route_rem_env_not_ready + abort_env_not_ready (+2),
        raising it to 37 — auth-signature fast-fail for ll-auto-calling loops.
        feat(loops) 550659db added route_rem_learning_gate + record_learning_gate_blocked
        (+2), raising it to 39 — learning-gate routing for ll-auto-calling loops.
        ENH-2406 added check_learning_ready + route_learning_ready + mark_learning_blocked
        (+3), raising it to 42 — pre-dequeue learning-readiness gate (mirrors ENH-2008's
        check_blocked_by + route_blocked_by two-state shape, plus its own record state).
        """
        data = _load_loop()
        state_count = len(data["states"])
        assert state_count <= 42, f"Expected ≤42 states in orchestrator, got {state_count}"
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
            "record_sub_loop_crash",
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
        # ENH-2005: on_error is split out to record_sub_loop_crash, not laundered.
        assert rem["on_error"] == "record_sub_loop_crash"
        dec = data["states"]["run_decomposition"]
        assert dec["on_success"] == "classify_decomposition"
        assert dec["on_error"] == "record_sub_loop_crash"

    def test_dead_rate_limit_routes_removed(self) -> None:
        data = _load_loop()
        assert "on_rate_limit_exhausted" not in data["states"]["run_remediation"]
        assert "on_rate_limit_exhausted" not in data["states"]["run_decomposition"]
        assert "max_rate_limit_retries" not in data["states"]["run_remediation"]

    def test_implemented_routes_to_re_enqueue(self) -> None:
        data = _load_loop()
        assert data["states"]["route_rem_implemented"]["on_yes"] == "re_enqueue_unblocked"

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

    def test_record_sub_loop_crash_records_distinct_marker(self) -> None:
        """ENH-2005: record_sub_loop_crash writes a SUB_LOOP_CRASH-tagged line to
        failures.txt (distinguishable from a clean IMPLEMENT_FAILED) and dequeues."""
        data = _load_loop()
        crash = data["states"]["record_sub_loop_crash"]
        assert "failures.txt" in crash["action"]
        assert "SUB_LOOP_CRASH" in crash["action"]
        assert crash["next"] == "dequeue_next"

    def test_skip_issue_is_sole_skipped_txt_writer(self) -> None:
        """BUG-2289: only skip_issue (and init) may write to skipped.txt in rn-implement.

        The report state treats skipped.txt and decomposed_count.txt as disjoint
        outcome buckets. Any state other than skip_issue or init that writes to
        skipped.txt (via >> or >) would cause double-counting when the report tallies
        are summed.
        """
        data = _load_loop()
        allowed_writers = {"skip_issue", "init"}
        for name, state in data["states"].items():
            action = state.get("action", "")
            # Check each line for write operations (>> append, or bare > redirect) to
            # skipped.txt. Reads (wc -l <, cat) are not flagged.
            for line in action.splitlines():
                stripped = line.strip()
                writes = ">>" in stripped and "skipped.txt" in stripped
                writes = writes or (
                    "skipped.txt" in stripped and stripped.startswith(":") and ">" in stripped
                )
                if writes and name not in allowed_writers:
                    raise AssertionError(
                        f"BUG-2289: state '{name}' writes to skipped.txt but is not "
                        f"an allowed writer (allowed: {allowed_writers}). This causes "
                        f"double-counting in the report state."
                    )

    def test_report_tallies_sub_loop_crashes_distinctly(self) -> None:
        """ENH-2005: report emits a sub_loop_crashes count separate from failed."""
        data = _load_loop()
        action = data["states"]["report"]["action"]
        assert "sub_loop_crashes" in action
        assert "SUB_LOOP_CRASH" in action

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


# ============================================================================
# TestDeferredOnStall — BUG-2006: stall + no-children defers instead of skipping
# ============================================================================


class TestDeferredOnStall:
    """A CONVERGED_STALLED → NO_CHILDREN issue defers (with reason + status), not skip."""

    def test_route_dec_no_children_routes_to_stalled_origin(self) -> None:
        """NO_CHILDREN no longer flat-skips — it disambiguates by stall origin first."""
        data = _load_loop()
        rdnc = data["states"]["route_dec_no_children"]
        assert rdnc["on_yes"] == "route_dec_stalled_origin"
        assert rdnc["on_no"] == "route_dec_rate_limited"

    def test_route_dec_stalled_origin_exists_and_matches_stall_token(self) -> None:
        """route_dec_stalled_origin matches STALLED_NEEDS_DECOMPOSE against rem_outcome."""
        data = _load_loop()
        rdso = data["states"]["route_dec_stalled_origin"]
        evaluate = rdso["evaluate"]
        assert evaluate["type"] == "output_contains"
        assert evaluate["pattern"] == "STALLED_NEEDS_DECOMPOSE"
        assert "${captured.rem_outcome.output}" in evaluate["source"]

    def test_stalled_origin_routes_stall_to_defer_else_skip(self) -> None:
        """Stall origin → mark_deferred; plain (too-large/atomic) decline → skip_issue."""
        data = _load_loop()
        rdso = data["states"]["route_dec_stalled_origin"]
        assert rdso["on_yes"] == "mark_deferred"
        assert rdso["on_no"] == "skip_issue"
        assert rdso["on_error"] == "record_failure"

    def test_mark_deferred_writes_reason_sets_status_and_dequeues(self) -> None:
        """mark_deferred records a reason to deferred.txt, sets status, and continues."""
        data = _load_loop()
        md = data["states"]["mark_deferred"]
        action = md["action"]
        assert "deferred.txt" in action
        assert "ll-issues set-status" in action and "deferred" in action
        assert "REASON" in action
        assert md["next"] == "dequeue_next"

    def test_init_initializes_deferred_txt(self) -> None:
        """init seeds an empty deferred.txt alongside the other tracking files."""
        data = _load_loop()
        assert "deferred.txt" in data["states"]["init"]["action"]

    def test_report_tallies_deferred_distinctly(self) -> None:
        """report counts and surfaces deferred separately from skipped."""
        data = _load_loop()
        action = data["states"]["report"]["action"]
        assert "deferred.txt" in action
        assert '"deferred"' in action


# ============================================================================
# TestBlockedByGate — ENH-2008: defer unmet-blocked_by issues before remediation
# ============================================================================


class TestBlockedByGate:
    """The post-dequeue gate defers issues with unmet blocked_by deps before scoring."""

    def test_check_blocked_by_state_exists(self) -> None:
        """check_blocked_by exists, captures status, routes to route_blocked_by."""
        data = _load_loop()
        cbb = data["states"]["check_blocked_by"]
        assert cbb["capture"] == "blocked_by_status"
        assert cbb["next"] == "route_blocked_by"

    def test_check_blocked_by_fails_open_on_error(self) -> None:
        """A gate error must never block processing — it routes to check_depth."""
        data = _load_loop()
        cbb = data["states"]["check_blocked_by"]
        assert cbb["on_error"] == "check_depth"

    def test_check_blocked_by_parses_frontmatter_not_show_json(self) -> None:
        """The gate reads blocked_by from the issue file frontmatter.

        `ll-issues show --json` does NOT expose blocked_by (returns null), so the
        gate parses the file's YAML frontmatter directly and diffs against the
        done set from `ll-issues list --json --status done`.
        """
        action = _load_loop()["states"]["check_blocked_by"]["action"]
        assert "blocked_by" in action
        # Diffs against the done set (command appears as a subprocess arg list).
        assert "ll-issues" in action and '"list"' in action
        assert '"--status"' in action and '"done"' in action
        # Reads the frontmatter block directly rather than a JSON projection.
        assert "read_text()" in action and "---" in action
        # Must not regress to the broken `show --json | jq .blocked_by` approach.
        assert ".blocked_by" not in action

    def test_check_blocked_by_writes_unmet_under_run_dir(self) -> None:
        """Unmet deps are recorded per-run (run_dir), not a shared path (MR-3)."""
        action = _load_loop()["states"]["check_blocked_by"]["action"]
        assert "blocked_by_unmet_" in action
        assert "${captured.run_dir.output}" in action

    def test_route_blocked_by_defers_on_blocked(self) -> None:
        """route_blocked_by sends BLOCKED → mark_deferred, else → check_learning_ready."""
        data = _load_loop()
        rbb = data["states"]["route_blocked_by"]
        evaluate = rbb["evaluate"]
        assert evaluate["type"] == "output_contains"
        assert evaluate["pattern"] == "BLOCKED"
        assert "${captured.blocked_by_status.output}" in evaluate["source"]
        assert rbb["on_yes"] == "mark_deferred"
        assert rbb["on_no"] == "check_learning_ready"
        assert rbb["on_error"] == "check_learning_ready"

    def test_mark_deferred_names_unmet_blocker(self) -> None:
        """mark_deferred reads blocked_by_unmet_<ID>.txt to name the specific blocker."""
        action = _load_loop()["states"]["mark_deferred"]["action"]
        assert "blocked_by_unmet_" in action
        assert "not done" in action


# ============================================================================
# TestLearningReadyGate — ENH-2406: pre-dequeue learning-readiness gate
# ============================================================================


class TestLearningReadyGate:
    """The post-blocked_by gate defers issues with unproven learning_tests_required
    targets before they spend a run_remediation pass (mirrors TestBlockedByGate)."""

    def test_check_learning_ready_state_exists(self) -> None:
        """check_learning_ready exists, captures status, routes to route_learning_ready."""
        data = _load_loop()
        clr = data["states"]["check_learning_ready"]
        assert clr["capture"] == "learning_ready_status"
        assert clr["next"] == "route_learning_ready"

    def test_check_learning_ready_fails_open_on_error(self) -> None:
        """A gate error must never block processing — it routes to check_depth."""
        data = _load_loop()
        clr = data["states"]["check_learning_ready"]
        assert clr["on_error"] == "check_depth"

    def test_check_learning_ready_short_circuits_on_skip_flag(self) -> None:
        """skip_learning_gate must short-circuit before any subprocess calls (Wiring Step 6)."""
        action = _load_loop()["states"]["check_learning_ready"]["action"]
        assert "${context.skip_learning_gate}" in action

    def test_check_learning_ready_uses_stale_aware_cli(self) -> None:
        """Gate shells out to `ll-learning-tests check <target> --stale-aware` per target."""
        action = _load_loop()["states"]["check_learning_ready"]["action"]
        assert "ll-learning-tests" in action
        assert '"check"' in action
        assert "--stale-aware" in action

    def test_check_learning_ready_parses_frontmatter_not_show_json(self) -> None:
        """The gate reads learning_tests_required from the issue file frontmatter,
        mirroring check_blocked_by's direct-parsing convention."""
        action = _load_loop()["states"]["check_learning_ready"]["action"]
        assert "learning_tests_required" in action
        assert "read_text()" in action and "---" in action

    def test_check_learning_ready_writes_unproven_under_run_dir(self) -> None:
        """Unproven targets are recorded per-run (run_dir), not a shared path (MR-3)."""
        action = _load_loop()["states"]["check_learning_ready"]["action"]
        assert "learning_unproven_" in action
        assert "${captured.run_dir.output}" in action

    def test_route_learning_ready_routes_on_unproven(self) -> None:
        """route_learning_ready sends UNPROVEN → mark_learning_blocked, else → check_depth."""
        data = _load_loop()
        rlr = data["states"]["route_learning_ready"]
        evaluate = rlr["evaluate"]
        assert evaluate["type"] == "output_contains"
        assert evaluate["pattern"] == "UNPROVEN"
        assert "${captured.learning_ready_status.output}" in evaluate["source"]
        assert rlr["on_yes"] == "mark_learning_blocked"
        assert rlr["on_no"] == "check_depth"
        assert rlr["on_error"] == "check_depth"

    def test_mark_learning_blocked_uses_distinct_tag(self) -> None:
        """mark_learning_blocked tags failures.txt with the PRE_DEQUEUE-distinct token
        (not the post-remediation safety-net's bare LEARNING_GATE_BLOCKED) and never
        enters run_remediation."""
        data = _load_loop()
        mlb = data["states"]["mark_learning_blocked"]
        action = mlb["action"]
        assert "LEARNING_GATE_BLOCKED_PRE_DEQUEUE" in action
        assert "failures.txt" in action
        assert "/ll:explore-api" in action
        assert mlb["next"] == "dequeue_next"

    def test_report_tallies_pre_dequeue_separately(self) -> None:
        """report must count LEARNING_GATE_BLOCKED_PRE_DEQUEUE distinctly from the
        generic LEARNING_GATE_BLOCKED safety-net tag (no double counting) and surface
        it in summary.json."""
        report = _load_loop()["states"]["report"]["action"]
        assert "LEARNING_GATE_BLOCKED_PRE_DEQUEUE" in report
        assert "learning_gate_blocked_pre_dequeue" in report

    # --- ENH-2431: auto-prove branch -----------------------------------------

    def test_auto_prove_learning_gate_flag_defaults_off(self) -> None:
        """auto_prove_learning_gate is opt-in (default empty), mirroring
        skip_learning_gate's shape but inverted (opt-in vs opt-out)."""
        data = _load_loop()
        assert data["context"]["auto_prove_learning_gate"] == ""

    def test_check_learning_ready_gates_prove_call_on_flag(self) -> None:
        """The prove-attempt branch reads auto_prove and only calls
        `ll-learning-tests prove` when it is set."""
        action = _load_loop()["states"]["check_learning_ready"]["action"]
        assert "${context.auto_prove_learning_gate}" in action
        assert '"ll-learning-tests", "prove"' in action
        assert "not proven and auto_prove" in action

    def test_check_learning_ready_prove_call_has_independent_timeout(self) -> None:
        """The prove subprocess must not reuse the cheap check call's timeout=30 —
        proving runs an LLM loop that can take minutes."""
        action = _load_loop()["states"]["check_learning_ready"]["action"]
        # The check call keeps its cheap timeout=30
        assert '"check", t, "--stale-aware"' in action
        assert 'timeout=30' in action
        # The prove call gets its own, larger timeout
        assert 'timeout=1800' in action

    def test_check_learning_ready_writes_attempted_marker(self) -> None:
        """A per-run attempted marker is written when auto-prove ran, so
        mark_learning_blocked can distinguish attempted-and-still-unproven from
        never-attempted."""
        action = _load_loop()["states"]["check_learning_ready"]["action"]
        assert "learning_prove_attempted_" in action
        assert "run_dir" in action

    def test_mark_learning_blocked_distinguishes_attempted_tag(self) -> None:
        """mark_learning_blocked checks for the attempted marker and emits the
        additive-suffix tag LEARNING_GATE_BLOCKED_PRE_DEQUEUE_ATTEMPTED (a superset
        string of LEARNING_GATE_BLOCKED_PRE_DEQUEUE) rather than an unrelated tag,
        so report's existing substring tallies don't need to change."""
        action = _load_loop()["states"]["mark_learning_blocked"]["action"]
        assert "learning_prove_attempted_" in action
        assert "LEARNING_GATE_BLOCKED_PRE_DEQUEUE_ATTEMPTED" in action
        # Still contains the base tag as a plain (non-attempted) fallback
        assert "LEARNING_GATE_BLOCKED_PRE_DEQUEUE" in action


# ============================================================================
# TestReEnqueueUnblocked — ENH-2195: re-enqueue deferred issues in same run
# ============================================================================


class TestReEnqueueUnblocked:
    """ENH-2195: re-enqueue deferred issues when their blockers resolve in the same run."""

    def test_re_enqueue_unblocked_state_exists(self) -> None:
        """re_enqueue_unblocked state is present in the FSM."""
        data = _load_loop()
        assert "re_enqueue_unblocked" in data["states"]

    def test_route_rem_implemented_routes_to_re_enqueue(self) -> None:
        """route_rem_implemented.on_yes routes to re_enqueue_unblocked, not dequeue_next."""
        data = _load_loop()
        assert data["states"]["route_rem_implemented"]["on_yes"] == "re_enqueue_unblocked"

    def test_re_enqueue_unblocked_routes_to_dequeue_next(self) -> None:
        """re_enqueue_unblocked.next routes unconditionally to dequeue_next."""
        data = _load_loop()
        state = data["states"]["re_enqueue_unblocked"]
        assert state.get("next") == "dequeue_next"

    def test_re_enqueue_reads_deferred_txt_under_run_dir(self) -> None:
        """re_enqueue_unblocked reads deferred.txt under run_dir (MR-3: no shared paths)."""
        data = _load_loop()
        action = data["states"]["re_enqueue_unblocked"]["action"]
        assert "deferred.txt" in action
        assert "${captured.run_dir.output}" in action

    def test_re_enqueue_appends_to_queue_txt_via_tmp_swap(self) -> None:
        """re_enqueue_unblocked re-adds unblocked issues to queue.txt using tmp-file swap."""
        data = _load_loop()
        action = data["states"]["re_enqueue_unblocked"]["action"]
        assert "queue.txt" in action
        assert "QUEUE.tmp" in action

    def test_re_enqueue_diffs_blocked_by_against_done_set(self) -> None:
        """re_enqueue_unblocked checks blocked_by deps against ll-issues list --status done."""
        data = _load_loop()
        action = data["states"]["re_enqueue_unblocked"]["action"]
        assert "blocked_by" in action
        assert "ll-issues" in action
        assert '"list"' in action
        assert '"--status"' in action and '"done"' in action

    def test_re_enqueue_skips_issues_with_no_blocked_by(self) -> None:
        """Stalled issues with no blocked_by deps are left in deferred.txt, not re-enqueued."""
        data = _load_loop()
        action = data["states"]["re_enqueue_unblocked"]["action"]
        assert "NO_BLOCKED_BY" in action

    def test_re_enqueue_rewrites_deferred_txt_via_tmp_swap(self) -> None:
        """re_enqueue_unblocked rewrites deferred.txt atomically, removing re-enqueued entries."""
        data = _load_loop()
        action = data["states"]["re_enqueue_unblocked"]["action"]
        assert "deferred.tmp" in action

    def test_re_enqueue_logs_re_enqueue_marker(self) -> None:
        """re_enqueue_unblocked emits [RE_ENQUEUE] to stderr for each re-enqueued issue."""
        data = _load_loop()
        action = data["states"]["re_enqueue_unblocked"]["action"]
        assert "[RE_ENQUEUE]" in action

    def test_re_enqueue_noop_on_empty_deferred(self) -> None:
        """re_enqueue_unblocked exits immediately when deferred.txt is empty or absent."""
        data = _load_loop()
        action = data["states"]["re_enqueue_unblocked"]["action"]
        assert "! -s" in action

    def test_re_enqueue_skips_stall_deferred_entries(self) -> None:
        """BUG-2202: entries deferred for non-blocked_by reasons are kept in deferred.txt unchanged."""
        data = _load_loop()
        action = data["states"]["re_enqueue_unblocked"]["action"]
        # The shell loop must extract the reason field and skip re-enqueue when it
        # does not contain "blocked_by" (e.g. "remediation stalled ..." entries).
        assert 'grep -q "blocked_by"' in action


# ============================================================================
# TestSelectNext — FEAT-1991: value-ranked dequeue
# ============================================================================


class TestSelectNext:
    """Tests for the select_next value-ranked scheduler (FEAT-1991)."""

    def test_select_next_state_exists(self) -> None:
        """select_next state is present in the FSM."""
        data = _load_loop()
        assert "select_next" in data["states"], "select_next must exist (FEAT-1991)"

    def test_select_next_uses_queue_pop_fragment(self) -> None:
        """select_next uses the queue_pop fragment for consistent exit-code evaluation."""
        data = _load_loop()
        sn = data["states"]["select_next"]
        assert sn.get("fragment") == "queue_pop"

    def test_select_next_captures_input(self) -> None:
        """select_next captures the chosen issue ID as input (same post-condition as fifo_pop)."""
        data = _load_loop()
        sn = data["states"]["select_next"]
        assert sn.get("capture") == "input"

    def test_select_next_routes_to_check_blocked_by(self) -> None:
        """select_next.on_no (issue dequeued) routes to check_blocked_by gate (ENH-2008)."""
        data = _load_loop()
        sn = data["states"]["select_next"]
        assert sn["on_no"] == "check_blocked_by"  # no = issue dequeued → blocked_by gate

    def test_select_next_routes_empty_ready_set_to_report(self) -> None:
        """select_next.on_yes (QUEUE_EMPTY) routes to report when ready set is empty."""
        data = _load_loop()
        sn = data["states"]["select_next"]
        assert sn["on_yes"] == "report"  # output_contains(QUEUE_EMPTY): yes = queue empty
        assert sn["on_error"] == "report"

    def test_select_next_reads_blocked_txt(self) -> None:
        """select_next filters manually-blocked issues via blocked.txt."""
        data = _load_loop()
        action = data["states"]["select_next"]["action"]
        assert "blocked.txt" in action

    def test_select_next_references_depth_map(self) -> None:
        """select_next reads depth_map.txt for depth tie-breaking."""
        data = _load_loop()
        action = data["states"]["select_next"]["action"]
        assert "depth_map.txt" in action

    def test_select_next_writes_current_depth(self) -> None:
        """select_next writes current_depth.txt (same post-condition as fifo_pop)."""
        data = _load_loop()
        action = data["states"]["select_next"]["action"]
        assert "current_depth.txt" in action

    def test_select_next_increments_dequeue_count(self) -> None:
        """select_next increments dequeue_count.txt (same post-condition as fifo_pop)."""
        data = _load_loop()
        action = data["states"]["select_next"]["action"]
        assert "dequeue_count.txt" in action

    def test_select_next_marks_visited(self) -> None:
        """select_next appends to visited.txt (same post-condition as fifo_pop)."""
        data = _load_loop()
        action = data["states"]["select_next"]["action"]
        assert "visited.txt" in action

    def test_select_next_uses_impact_effort(self) -> None:
        """select_next calls ll-issues impact-effort for value scoring."""
        data = _load_loop()
        action = data["states"]["select_next"]["action"]
        assert "impact-effort" in action

    def test_select_next_uses_done_status_filter(self) -> None:
        """select_next filters ready set by checking blocked_by deps against done issues."""
        data = _load_loop()
        action = data["states"]["select_next"]["action"]
        assert "done" in action
        assert "blocked_by" in action

    def test_select_next_implements_composite_ranking(self) -> None:
        """select_next computes priority weight + impact/effort composite score."""
        data = _load_loop()
        action = data["states"]["select_next"]["action"]
        assert "PRIO_WEIGHT" in action or "priority" in action
        assert "composite_score" in action or "ie_ratio" in action

    def test_select_next_uses_depth_first_tiebreak(self) -> None:
        """select_next uses depth as a tie-breaker (deeper = preferred)."""
        data = _load_loop()
        action = data["states"]["select_next"]["action"]
        assert "depth" in action.lower()
        # Must prefer deeper issues: higher depth = higher score
        assert "depth_bonus" in action or "depth *" in action

    def test_fifo_regression_schedule_mode_default(self) -> None:
        """schedule_mode defaults to 'fifo' — existing FIFO behavior is unchanged."""
        data = _load_loop()
        assert data["context"]["schedule_mode"] == "fifo"
        # dequeue_next dispatch routes fifo → fifo_pop (on_no path when mode != value_ranked)
        deq = data["states"]["dequeue_next"]
        assert deq["on_no"] == "fifo_pop"

    def test_fifo_pop_post_conditions_match_select_next(self) -> None:
        """fifo_pop and select_next set identical post-conditions (capture, depth, visited, count)."""
        data = _load_loop()
        fp = data["states"]["fifo_pop"]
        sn = data["states"]["select_next"]
        # Both must capture input
        assert fp.get("capture") == "input"
        assert sn.get("capture") == "input"
        # Both must write current_depth.txt
        assert "current_depth.txt" in fp["action"]
        assert "current_depth.txt" in sn["action"]
        # Both must update visited.txt
        assert "visited.txt" in fp["action"]
        assert "visited.txt" in sn["action"]
        # Both must increment dequeue_count.txt
        assert "dequeue_count.txt" in fp["action"]
        assert "dequeue_count.txt" in sn["action"]
        # Both must route to check_blocked_by when an issue is dequeued (on_no for output_contains)
        assert fp["on_no"] == "check_blocked_by"
        assert sn["on_no"] == "check_blocked_by"


# ---------------------------------------------------------------------------
# TestPreFlightStatusCheck — BUG-2201: pre-flight gate before run_remediation
# ---------------------------------------------------------------------------


class TestPreFlightStatusCheck:
    """BUG-2201: check_issue_status pre-flight gate inserted before run_remediation."""

    def test_check_issue_status_state_exists(self) -> None:
        """check_issue_status state exists in the FSM."""
        data = _load_loop()
        assert "check_issue_status" in data["states"], (
            "check_issue_status pre-flight state must be added (BUG-2201)"
        )

    def test_check_issue_status_is_shell_action(self) -> None:
        """check_issue_status uses action_type: shell."""
        data = _load_loop()
        state = data["states"]["check_issue_status"]
        assert state["action_type"] == "shell"

    def test_check_issue_status_reads_issue_status(self) -> None:
        """check_issue_status shell action reads the issue status field."""
        data = _load_loop()
        action = data["states"]["check_issue_status"]["action"]
        # Must resolve the issue path and check status (either via ll-issues or grep)
        assert "status" in action.lower()
        assert "${captured.input.output}" in action or "ID" in action

    def test_check_issue_status_on_yes_routes_to_skip(self) -> None:
        """check_issue_status routes done/cancelled issues to skip_issue."""
        data = _load_loop()
        state = data["states"]["check_issue_status"]
        # on_yes (already done) → skip
        assert state["on_yes"] in ("skip_issue", "dequeue_next"), (
            "on_yes (already done) must route to skip_issue or dequeue_next"
        )

    def test_check_issue_status_on_no_routes_to_run_remediation(self) -> None:
        """check_issue_status routes open issues to run_remediation."""
        data = _load_loop()
        state = data["states"]["check_issue_status"]
        assert state["on_no"] == "run_remediation", (
            "on_no (needs implementation) must route to run_remediation"
        )

    def test_check_issue_status_fails_open_to_run_remediation(self) -> None:
        """check_issue_status fails open: errors route to run_remediation, not skip."""
        data = _load_loop()
        state = data["states"]["check_issue_status"]
        assert state["on_error"] == "run_remediation", (
            "on_error must fail open to run_remediation (never block processing on a gate error)"
        )

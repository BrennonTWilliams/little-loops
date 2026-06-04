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

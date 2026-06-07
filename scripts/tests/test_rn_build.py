"""Tests for the rn-build built-in orchestration loop (FEAT-1992)."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from little_loops.fsm import is_runnable_loop
from little_loops.fsm.validation import (
    ValidationSeverity,
    load_and_validate,
)

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "rn-build.yaml"
LIB_FILE = BUILTIN_LOOPS_DIR / "lib" / "composer.yaml"
ROUTER_FILE = BUILTIN_LOOPS_DIR / "loop-router.yaml"
GOAL_CLUSTER_FILE = BUILTIN_LOOPS_DIR / "goal-cluster.yaml"

REQUIRED_STATES = {
    "init",
    "tech_research",
    "design_artifacts",
    "commit_design",
    "scope_project",
    "write_epic_id",
    "refine_seed",
    "eval_harness",
    "read_harness_name",
    "cluster_execute",
    "eval_gate",
    "check_eval_retry_budget",
    "capture_eval_failures",
    "synthesize_result",
    "done",
    "failed",
}


@pytest.fixture
def loop_data() -> dict:
    assert LOOP_FILE.exists(), f"rn-build.yaml not found at {LOOP_FILE}"
    with open(LOOP_FILE) as f:
        return yaml.safe_load(f)


@pytest.fixture
def router_data() -> dict:
    assert ROUTER_FILE.exists(), f"loop-router.yaml not found at {ROUTER_FILE}"
    with open(ROUTER_FILE) as f:
        return yaml.safe_load(f)


@pytest.fixture
def lib_data() -> dict:
    assert LIB_FILE.exists(), f"lib/composer.yaml not found at {LIB_FILE}"
    with open(LIB_FILE) as f:
        return yaml.safe_load(f)


@pytest.fixture
def goal_cluster_data() -> dict:
    assert GOAL_CLUSTER_FILE.exists(), f"goal-cluster.yaml not found at {GOAL_CLUSTER_FILE}"
    with open(GOAL_CLUSTER_FILE) as f:
        return yaml.safe_load(f)


class TestRnBuildFile:
    """Basic file and YAML-parse tests."""

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"rn-build.yaml not found at {LOOP_FILE}"

    def test_yaml_parses(self, loop_data: dict) -> None:
        assert isinstance(loop_data, dict)

    def test_has_name(self, loop_data: dict) -> None:
        assert loop_data.get("name") == "rn-build"

    def test_has_description(self, loop_data: dict) -> None:
        assert loop_data.get("description"), "rn-build.yaml must have a top-level description"

    def test_category_is_orchestration(self, loop_data: dict) -> None:
        assert loop_data.get("category") == "orchestration", (
            "rn-build is a top-level orchestration loop, not a harness"
        )

    def test_input_key_is_spec(self, loop_data: dict) -> None:
        assert loop_data.get("input_key") == "spec"

    def test_initial_state_is_init(self, loop_data: dict) -> None:
        assert loop_data.get("initial") == "init"

    def test_has_required_states(self, loop_data: dict) -> None:
        states = set(loop_data.get("states", {}).keys())
        missing = REQUIRED_STATES - states
        assert not missing, f"rn-build.yaml missing required states: {missing}"

    def test_is_runnable(self) -> None:
        assert is_runnable_loop(LOOP_FILE), f"{LOOP_FILE.name} is not recognized as runnable"

    def test_artifacts_in_run_dir(self, loop_data: dict) -> None:
        """All intermediate artifact writes use ${context.run_dir} (MR-3 compliance)."""
        states = loop_data.get("states", {})
        violations = []
        for state_name, state in states.items():
            action = state.get("action", "")
            if ".loops/tmp" in action and "${context.run_dir}" not in action:
                violations.append(state_name)
        assert not violations, (
            f"States writing to bare .loops/tmp/ instead of ${{context.run_dir}}: {violations}"
        )


class TestRnBuildFSMValidation:
    """FSM structural validation tests."""

    def test_fsm_validate_passes(self) -> None:
        _, warnings = load_and_validate(LOOP_FILE)
        errors = [w for w in warnings if w.severity == ValidationSeverity.ERROR]
        assert not errors, f"rn-build.yaml has validation errors: {[str(e) for e in errors]}"

    def test_no_mr1_violations(self) -> None:
        _, warnings = load_and_validate(LOOP_FILE)
        mr1_errors = [
            w for w in warnings
            if w.severity == ValidationSeverity.ERROR and "MR-1" in w.message
        ]
        assert not mr1_errors, f"rn-build.yaml has MR-1 violations: {[str(e) for e in mr1_errors]}"

    def test_no_mr3_violations(self) -> None:
        _, warnings = load_and_validate(LOOP_FILE)
        mr3_warnings = [
            w for w in warnings
            if w.severity in (ValidationSeverity.WARNING, ValidationSeverity.ERROR)
            and "MR-3" in w.message
        ]
        assert not mr3_warnings, (
            f"rn-build.yaml has MR-3 violations: {[str(w) for w in mr3_warnings]}"
        )


class TestRnBuildClusterExecute:
    """Tests for the cluster_execute → goal-cluster delegation contract."""

    def test_cluster_execute_targets_goal_cluster(self, loop_data: dict) -> None:
        state = loop_data["states"]["cluster_execute"]
        assert state.get("loop") == "goal-cluster", (
            "cluster_execute must delegate to goal-cluster"
        )

    def test_cluster_execute_passes_value_ranked_schedule_mode(self, loop_data: dict) -> None:
        state = loop_data["states"]["cluster_execute"]
        with_block = state.get("with", {})
        assert with_block.get("schedule_mode") == "value_ranked", (
            "cluster_execute must pass schedule_mode=value_ranked to goal-cluster so "
            "per-batch rn-implement dispatches use value-ranked dequeue"
        )

    def test_cluster_execute_passes_max_batch_size_5(self, loop_data: dict) -> None:
        state = loop_data["states"]["cluster_execute"]
        with_block = state.get("with", {})
        assert str(with_block.get("max_batch_size", "")) == "5", (
            "cluster_execute must pass max_batch_size=5 to goal-cluster (FEAT-1992 Design Notes §5)"
        )

    def test_cluster_execute_passes_epic_id_as_goals(self, loop_data: dict) -> None:
        state = loop_data["states"]["cluster_execute"]
        with_block = state.get("with", {})
        goals_val = with_block.get("goals", "")
        assert "epic_id" in goals_val, (
            "cluster_execute must pass captured epic_id as goals input to goal-cluster"
        )

    def test_cluster_execute_enables_propagate_context(self, loop_data: dict) -> None:
        state = loop_data["states"]["cluster_execute"]
        with_block = state.get("with", {})
        assert str(with_block.get("propagate_context", "")) == "true", (
            "cluster_execute must enable propagate_context for cross-batch hint propagation"
        )


class TestGoalClusterScheduleModePassthrough:
    """Tests that goal-cluster threads schedule_mode to dispatch_cluster."""

    def test_goal_cluster_has_schedule_mode_context(self, goal_cluster_data: dict) -> None:
        context = goal_cluster_data.get("context", {})
        assert "schedule_mode" in context, (
            "goal-cluster must have schedule_mode in its context block to accept "
            "schedule_mode=value_ranked from rn-build"
        )

    def test_goal_cluster_schedule_mode_default_is_fifo(self, goal_cluster_data: dict) -> None:
        context = goal_cluster_data.get("context", {})
        assert context.get("schedule_mode") == "fifo", (
            "goal-cluster schedule_mode default must be 'fifo' for backward compatibility"
        )

    def test_dispatch_cluster_threads_schedule_mode(self, goal_cluster_data: dict) -> None:
        state = goal_cluster_data["states"]["dispatch_cluster"]
        with_block = state.get("with", {})
        assert "schedule_mode" in with_block, (
            "goal-cluster's dispatch_cluster must pass schedule_mode through to sub-loop "
            "so rn-implement receives value_ranked when called from rn-build"
        )


class TestRnBuildEvalGate:
    """Tests for the eval_gate bounded re-entry logic."""

    def test_eval_gate_exists(self, loop_data: dict) -> None:
        assert "eval_gate" in loop_data["states"]

    def test_eval_gate_is_loop_delegation(self, loop_data: dict) -> None:
        state = loop_data["states"]["eval_gate"]
        assert "loop" in state, "eval_gate must be a loop delegation state"

    def test_eval_gate_routes_to_retry_budget_on_failure(self, loop_data: dict) -> None:
        state = loop_data["states"]["eval_gate"]
        assert state.get("on_no") == "check_eval_retry_budget", (
            "eval_gate on_no must route to check_eval_retry_budget for bounded re-entry"
        )

    def test_eval_gate_routes_to_synthesize_on_success(self, loop_data: dict) -> None:
        state = loop_data["states"]["eval_gate"]
        assert state.get("on_yes") == "synthesize_result", (
            "eval_gate on_yes must route to synthesize_result"
        )

    def test_retry_budget_uses_output_numeric_evaluator(self, loop_data: dict) -> None:
        state = loop_data["states"]["check_eval_retry_budget"]
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_numeric", (
            "check_eval_retry_budget must use output_numeric evaluator (non-LLM, MR-1 compatible)"
        )

    def test_retry_budget_on_yes_routes_to_capture_failures(self, loop_data: dict) -> None:
        state = loop_data["states"]["check_eval_retry_budget"]
        assert state.get("on_yes") == "capture_eval_failures", (
            "When under retry budget, must capture failures before re-entering cluster_execute"
        )

    def test_retry_budget_on_no_routes_to_synthesize(self, loop_data: dict) -> None:
        state = loop_data["states"]["check_eval_retry_budget"]
        assert state.get("on_no") == "synthesize_result", (
            "When retry budget exhausted, must proceed to synthesize_result"
        )

    def test_capture_failures_re_enters_cluster_execute(self, loop_data: dict) -> None:
        state = loop_data["states"]["capture_eval_failures"]
        assert state.get("next") == "cluster_execute", (
            "capture_eval_failures must re-enter cluster_execute after capturing failure issues"
        )

    def test_retry_counter_in_run_dir(self, loop_data: dict) -> None:
        action = loop_data["states"]["check_eval_retry_budget"].get("action", "")
        assert "eval-retry-count.txt" in action, (
            "Retry counter must be persisted in ${context.run_dir}/eval-retry-count.txt (MR-3)"
        )
        assert "${context.run_dir}" in action or "context.run_dir" in action, (
            "Retry counter path must use ${context.run_dir} (not .loops/tmp/) for MR-3 compliance"
        )


class TestRnBuildDispatchExclusion:
    """Tests that loop-router and lib/composer exclude rn-build from dispatch candidates."""

    def test_loop_router_excludes_rn_build(self, router_data: dict) -> None:
        action = router_data.get("states", {}).get("discover_loops", {}).get("action", "")
        assert "rn-build" in action, (
            "loop-router's discover_loops must add rn-build to excludes — "
            "top-level builder loops must not be offered as single-goal candidates"
        )

    def test_discover_loops_fragment_excludes_rn_build(self, lib_data: dict) -> None:
        action = lib_data["fragments"]["discover_loops"].get("action", "")
        assert "rn-build" in action, (
            "lib/composer.yaml discover_loops fragment must exclude rn-build from candidates"
        )


class TestRnBuildNotInEvalDrivenPath:
    """Tests that rn-build does NOT use eval-driven-development in its dispatch path."""

    def test_eval_driven_development_not_referenced(self, loop_data: dict) -> None:
        loop_yaml = LOOP_FILE.read_text()
        assert "eval-driven-development" not in loop_yaml, (
            "rn-build must NOT reference eval-driven-development — "
            "it dispatches via goal-cluster → rn-implement, not the legacy eval-driven path"
        )


class TestRnBuildInitState:
    """Tests for the init state spec validation logic."""

    def test_init_is_shell_action(self, loop_data: dict) -> None:
        state = loop_data["states"]["init"]
        assert state.get("action_type") == "shell"

    def test_init_validates_spec_required(self, loop_data: dict) -> None:
        action = loop_data["states"]["init"].get("action", "")
        assert "spec" in action.lower() or "SPECS" in action, (
            "init must validate that spec context variable is provided"
        )

    def test_init_uses_exit_code_evaluator(self, loop_data: dict) -> None:
        state = loop_data["states"]["init"]
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "exit_code", (
            "init must use exit_code evaluator (non-LLM gate for spec validation)"
        )

    def test_init_writes_to_run_dir(self, loop_data: dict) -> None:
        action = loop_data["states"]["init"].get("action", "")
        assert "${context.run_dir}" in action, (
            "init must create and use ${context.run_dir} for intermediate artifacts (MR-3)"
        )


@pytest.mark.slow
class TestRnBuildLiveValidation:
    """Optional live validation tests (skipped unless --run-slow flag is passed)."""

    def test_ll_loop_validate_passes(self) -> None:
        import subprocess
        result = subprocess.run(
            ["ll-loop", "validate", str(LOOP_FILE)],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0, (
            f"ll-loop validate failed for rn-build.yaml:\n{result.stdout}\n{result.stderr}"
        )

    def test_ll_loop_list_includes_rn_build(self) -> None:
        import subprocess
        result = subprocess.run(
            ["ll-loop", "list"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        assert result.returncode == 0
        assert "rn-build" in result.stdout, (
            "ll-loop list must include rn-build after it is registered as a built-in loop"
        )

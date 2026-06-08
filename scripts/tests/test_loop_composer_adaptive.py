"""Tests for loop-composer-adaptive (FEAT-1983)."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from little_loops.fsm import is_runnable_loop
from little_loops.fsm.validation import (
    ValidationSeverity,
    load_and_validate,
    validate_fsm,
)

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "loop-composer-adaptive.yaml"
LIB_FILE = BUILTIN_LOOPS_DIR / "lib" / "composer.yaml"

REQUIRED_STATES = {
    "discover_loops",
    "decompose_goal",
    "parse_plan",
    "validate_plan",
    "re_decompose",
    "check_auto_plan",
    "present_plan",
    "execute_plan",
    "read_step_loop",
    "read_step_input",
    "dispatch_step",
    "write_step_success",
    "write_step_failed",
    "increment_replan_count",
    "check_replan_budget",
    "read_completed_summaries",
    "read_last_verdict",
    "reassess",
    "parse_reassess_decision",
    "route_reassess_continue",
    "route_reassess_replan",
    "apply_replan",
    "read_checkpoints",
    "review_chain",
    "present_result",
    "abort_composer",
    "failed",
}


class TestLoopComposerAdaptiveFile:
    """Structural tests for loop-composer-adaptive.yaml top-level fields."""

    @pytest.fixture
    def loop_data(self) -> dict:
        assert LOOP_FILE.exists(), f"loop-composer-adaptive.yaml not found at {LOOP_FILE}"
        with open(LOOP_FILE) as f:
            return yaml.safe_load(f)

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists()

    def test_parses_as_yaml(self, loop_data: dict) -> None:
        assert isinstance(loop_data, dict)

    def test_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"Validation errors: {[str(e) for e in error_list]}"

    def test_name(self, loop_data: dict) -> None:
        assert loop_data.get("name") == "loop-composer-adaptive"

    def test_category(self, loop_data: dict) -> None:
        assert loop_data.get("category") == "orchestration"

    def test_input_key(self, loop_data: dict) -> None:
        assert loop_data.get("input_key") == "goal"

    def test_initial_state(self, loop_data: dict) -> None:
        assert loop_data.get("initial") == "discover_loops"

    def test_max_iterations_allows_replans(self, loop_data: dict) -> None:
        assert loop_data.get("max_iterations", 0) >= 200

    def test_imports_composer_lib(self, loop_data: dict) -> None:
        assert "lib/composer.yaml" in loop_data.get("import", [])

    def test_context_has_max_replans(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        assert "max_replans" in ctx
        assert str(ctx["max_replans"]) == "2"

    def test_is_runnable_loop(self) -> None:
        assert is_runnable_loop(LOOP_FILE)


class TestLoopComposerAdaptiveStates:
    """Per-state structural assertions for loop-composer-adaptive.yaml."""

    @pytest.fixture
    def loop_data(self) -> dict:
        with open(LOOP_FILE) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def states(self, loop_data: dict) -> dict:
        return loop_data.get("states", {})

    def test_has_all_required_states(self, states: dict) -> None:
        actual = set(states.keys())
        missing = REQUIRED_STATES - actual
        assert not missing, f"loop-composer-adaptive missing states: {missing}"

    def test_write_step_failed_routes_to_increment_not_checkpoints(self, states: dict) -> None:
        wf = states["write_step_failed"]
        assert wf.get("next") == "increment_replan_count", (
            "write_step_failed must route to increment_replan_count (adaptive path), "
            "not read_checkpoints (static path)"
        )

    def test_write_step_success_routes_to_execute_plan(self, states: dict) -> None:
        ws = states["write_step_success"]
        assert ws.get("next") == "execute_plan"

    def test_no_loops_tmp_paths(self, states: dict) -> None:
        """MR-3 guard: no state action should write to .loops/tmp/."""
        for state_name, state in states.items():
            action = state.get("action", "") or ""
            assert ".loops/tmp" not in action, (
                f"State {state_name!r} writes to .loops/tmp/ — use ${{context.run_dir}}/ instead (MR-3)"
            )

    def test_uses_run_dir_for_artifacts(self, states: dict) -> None:
        """At least one state must reference ${context.run_dir} for per-run isolation."""
        any_run_dir = any(
            "${context.run_dir}" in (state.get("action", "") or "") for state in states.values()
        )
        assert any_run_dir, "No state references ${context.run_dir} — artifact isolation missing"


class TestReplanBudget:
    """Tests for the replan budget counter (MR-1 compliance)."""

    @pytest.fixture
    def states(self) -> dict:
        with open(LOOP_FILE) as f:
            data = yaml.safe_load(f)
        return data.get("states", {})

    def test_check_replan_budget_uses_output_numeric(self, states: dict) -> None:
        state = states["check_replan_budget"]
        assert state["evaluate"]["type"] == "output_numeric"
        assert state["evaluate"]["operator"] == "lt"

    def test_check_replan_budget_reads_max_replans_from_context(self, states: dict) -> None:
        state = states["check_replan_budget"]
        assert "max_replans" in state["evaluate"]["target"]

    def test_budget_exhaustion_routes_to_abort(self, states: dict) -> None:
        state = states["check_replan_budget"]
        assert state.get("on_no") == "abort_composer"
        assert state.get("on_error") == "abort_composer"

    def test_budget_ok_routes_to_read_summaries(self, states: dict) -> None:
        state = states["check_replan_budget"]
        assert state.get("on_yes") == "read_completed_summaries"

    def test_increment_replan_count_precedes_budget_check(self, states: dict) -> None:
        inc = states["increment_replan_count"]
        assert inc.get("next") == "check_replan_budget"


class TestReassessState:
    """Tests for the reassess state and MR-1 pairing."""

    @pytest.fixture
    def loop_data(self) -> dict:
        with open(LOOP_FILE) as f:
            return yaml.safe_load(f)

    @pytest.fixture
    def states(self, loop_data: dict) -> dict:
        return loop_data.get("states", {})

    def test_reassess_uses_fragment(self, states: dict) -> None:
        state = states["reassess"]
        assert state.get("fragment") == "reassess"

    def test_reassess_fragment_has_llm_structured_evaluate(self) -> None:
        with open(LIB_FILE) as f:
            lib = yaml.safe_load(f)
        fragment = lib["fragments"]["reassess"]
        assert fragment["evaluate"]["type"] == "llm_structured"

    def test_reassess_routes_all_verdicts(self, states: dict) -> None:
        state = states["reassess"]
        assert state.get("on_yes") == "parse_reassess_decision"
        assert state.get("on_no") == "parse_reassess_decision"
        assert state.get("on_partial") == "parse_reassess_decision"
        assert state.get("on_error") == "abort_composer"

    def test_reassess_is_preceded_by_output_numeric_gate(self, states: dict) -> None:
        """MR-1: llm_structured state must be paired with non-LLM evaluator in routing chain."""
        budget = states["check_replan_budget"]
        assert budget["evaluate"]["type"] == "output_numeric"
        # The output_numeric gate routes on_yes toward the reassess state
        assert budget.get("on_yes") == "read_completed_summaries"


class TestVerdictGateRouting:
    """Tests for the CONTINUE/REPLAN_TAIL/ABORT routing chain."""

    @pytest.fixture
    def states(self) -> dict:
        with open(LOOP_FILE) as f:
            data = yaml.safe_load(f)
        return data.get("states", {})

    def test_route_reassess_continue_uses_output_contains(self, states: dict) -> None:
        state = states["route_reassess_continue"]
        assert state["evaluate"]["type"] == "output_contains"
        assert "CONTINUE" in state["evaluate"]["pattern"]

    def test_route_reassess_continue_routes_to_execute_plan_on_yes(self, states: dict) -> None:
        assert states["route_reassess_continue"].get("on_yes") == "execute_plan"

    def test_route_reassess_continue_falls_through_to_replan_check(self, states: dict) -> None:
        assert states["route_reassess_continue"].get("on_no") == "route_reassess_replan"

    def test_route_reassess_replan_routes_to_apply_replan_on_yes(self, states: dict) -> None:
        assert states["route_reassess_replan"].get("on_yes") == "apply_replan"

    def test_route_reassess_replan_routes_to_abort_on_no(self, states: dict) -> None:
        assert states["route_reassess_replan"].get("on_no") == "abort_composer"


class TestCheckpointPersistence:
    """Tests for checkpoint and plan-version artifact paths."""

    @pytest.fixture
    def states(self) -> dict:
        with open(LOOP_FILE) as f:
            data = yaml.safe_load(f)
        return data.get("states", {})

    def test_write_step_success_uses_run_dir_checkpoints(self, states: dict) -> None:
        action = states["write_step_success"].get("action", "")
        assert "${context.run_dir}" in action
        assert "checkpoints" in action

    def test_parse_plan_writes_plan_v1(self, states: dict) -> None:
        action = states["parse_plan"].get("action", "")
        assert "plans" in action
        assert "v1.json" in action

    def test_apply_replan_versions_plan(self, states: dict) -> None:
        action = states["apply_replan"].get("action", "")
        assert "plans" in action
        assert "${context.run_dir}" in action


class TestTerminalStates:
    """Tests for terminal state configuration."""

    @pytest.fixture
    def states(self) -> dict:
        with open(LOOP_FILE) as f:
            data = yaml.safe_load(f)
        return data.get("states", {})

    def test_present_result_is_terminal(self, states: dict) -> None:
        assert states["present_result"].get("terminal") is True

    def test_abort_composer_is_terminal(self, states: dict) -> None:
        assert states["abort_composer"].get("terminal") is True

    def test_failed_is_terminal(self, states: dict) -> None:
        assert states["failed"].get("terminal") is True


@pytest.mark.slow
@pytest.mark.skipif(shutil.which("claude") is None, reason="claude CLI not available")
class TestLoopComposerAdaptiveLive:
    """Live-LLM tests for loop-composer-adaptive (marked slow, requires claude CLI)."""

    def test_loop_validates_before_live_run(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, (
            f"loop-composer-adaptive must validate cleanly before any live run: "
            f"{[str(e) for e in error_list]}"
        )

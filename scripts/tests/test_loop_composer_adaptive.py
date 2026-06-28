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
    "validate_replan",
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

    def test_max_steps_allows_replans(self, loop_data: dict) -> None:
        assert loop_data.get("max_steps", 0) >= 200

    def test_imports_composer_lib(self, loop_data: dict) -> None:
        assert "lib/composer.yaml" in loop_data.get("import", [])

    def test_context_has_max_replans(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        assert "max_replans" in ctx
        assert str(ctx["max_replans"]) == "2"

    def test_context_variables(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        for key in ("goal", "auto", "include", "exclude", "max_plan_nodes", "max_replans"):
            assert key in ctx, f"context missing key: {key}"

    def test_context_defaults(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        assert ctx.get("include") == "", "include default must be empty string"
        assert ctx.get("auto") == "false", "auto must default to 'false' (HITL required)"
        assert ctx.get("max_plan_nodes") == "8"
        assert ctx.get("max_replans") == "2"

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

    def test_write_step_failed_routes_to_reassess_chain_not_checkpoints(self, states: dict) -> None:
        wf = states["write_step_failed"]
        assert wf.get("next") == "read_completed_summaries", (
            "write_step_failed must enter the reassess chain (read_completed_summaries) "
            "without consuming replan budget — the budget gate sits on the REPLAN_TAIL "
            "branch downstream, not on every failure (adaptive path), and it must not "
            "route to read_checkpoints (static path)"
        )

    def test_write_step_failed_does_not_mark_step_succeeded(self, states: dict) -> None:
        """A failed step advances the cursor but is NOT locked as succeeded, so
        REPLAN_TAIL can retry it (see apply_replan immutability boundary)."""
        action = states["write_step_failed"].get("action", "")
        assert "completed-steps.txt" in action
        assert "succeeded-steps.txt" not in action

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

    def test_budget_ok_routes_to_increment(self, states: dict) -> None:
        # On the REPLAN_TAIL branch the budget is checked BEFORE increment, so
        # max_replans=2 permits exactly 2 replans (count read while still < max).
        state = states["check_replan_budget"]
        assert state.get("on_yes") == "increment_replan_count"

    def test_budget_check_precedes_increment(self, states: dict) -> None:
        # check_replan_budget reads the count, then increment_replan_count bumps
        # it and proceeds to apply_replan (only actual replans consume budget).
        assert states["check_replan_budget"].get("on_yes") == "increment_replan_count"
        assert states["increment_replan_count"].get("next") == "apply_replan"

    def test_replan_budget_only_consumed_on_replan_branch(self, states: dict) -> None:
        # The budget gate is reached only from route_reassess_replan (REPLAN_TAIL);
        # CONTINUE routes straight to execute_plan and never consumes budget.
        assert states["route_reassess_replan"].get("on_yes") == "check_replan_budget"
        assert states["route_reassess_continue"].get("on_yes") == "execute_plan"


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

    def test_reassess_is_paired_with_output_numeric_gate(self, states: dict) -> None:
        """MR-1: the llm_structured reassess state must be paired with a non-LLM
        evaluator in its routing chain. The deterministic parse_reassess_decision
        + route_* states drive routing, and the output_numeric budget gate sits on
        the REPLAN_TAIL branch downstream of reassess."""
        budget = states["check_replan_budget"]
        assert budget["evaluate"]["type"] == "output_numeric"
        # Reachable downstream of reassess: reassess -> parse -> route_continue ->
        # route_reassess_replan -> check_replan_budget.
        assert states["route_reassess_replan"].get("on_yes") == "check_replan_budget"


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

    def test_route_reassess_replan_routes_to_budget_gate_on_yes(self, states: dict) -> None:
        # REPLAN_TAIL must pass through the budget gate before apply_replan.
        assert states["route_reassess_replan"].get("on_yes") == "check_replan_budget"

    def test_route_reassess_replan_routes_to_abort_on_no(self, states: dict) -> None:
        assert states["route_reassess_replan"].get("on_no") == "abort_composer"

    def test_apply_replan_validates_before_executing(self, states: dict) -> None:
        # The replanned (succeeded + new tail) plan is re-validated (catalog
        # membership, node cap, cycles, dup step_ids, Kahn topo-sort) before
        # dispatch; a rejected replan aborts cleanly.
        assert states["apply_replan"].get("next") == "validate_replan"
        vr = states["validate_replan"]
        assert vr.get("fragment") == "validate_plan"
        assert vr.get("on_yes") == "execute_plan"
        assert vr.get("on_no") == "abort_composer"
        assert vr.get("on_error") == "abort_composer"

    def test_apply_replan_uses_succeeded_steps_as_immutable_boundary(self, states: dict) -> None:
        # Fix #8: the immutable prefix is succeeded-steps.txt (not completed-steps),
        # and apply_replan resets the cursor so a failed step can be retried.
        action = states["apply_replan"].get("action", "")
        assert "succeeded-steps.txt" in action
        assert "completed-steps.txt" in action


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

    def test_write_step_success_records_succeeded_step(self, states: dict) -> None:
        # Fix #8: a successful step is appended to both the cursor and the
        # immutable boundary file used by apply_replan.
        action = states["write_step_success"].get("action", "")
        assert "completed-steps.txt" in action
        assert "succeeded-steps.txt" in action

    def test_no_state_interpolates_captured_output_into_python_literal(self, states: dict) -> None:
        # Fix #5: shell states read captured values from disk (quoted heredoc),
        # never `"""${captured.X.output}"""` which corrupts on quotes/backslashes.
        for name, state in states.items():
            action = state.get("action", "") or ""
            assert '"""${captured' not in action, (
                f"State {name!r} interpolates a captured value into a Python triple-quoted "
                f"literal — read it from disk via a quoted heredoc instead (fix #5)"
            )

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

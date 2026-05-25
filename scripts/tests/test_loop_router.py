"""Tests for the loop-router built-in loop."""

from __future__ import annotations

import shutil
from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "loop-router.yaml"


@pytest.fixture
def loop_data() -> dict:
    """Load the loop-router YAML."""
    assert LOOP_FILE.exists(), f"loop-router.yaml not found at {LOOP_FILE}"
    with open(LOOP_FILE) as f:
        return yaml.safe_load(f)


class TestLoopRouterFile:
    """Tests that loop-router.yaml exists and is structurally valid."""

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"loop-router.yaml not found at {LOOP_FILE}"

    def test_parses_as_yaml(self, loop_data: dict) -> None:
        assert isinstance(loop_data, dict), "root must be a mapping"

    def test_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM validation errors: {[str(e) for e in error_list]}"

    def test_name(self, loop_data: dict) -> None:
        assert loop_data.get("name") == "loop-router"

    def test_category(self, loop_data: dict) -> None:
        assert loop_data.get("category") == "routing"

    def test_input_key(self, loop_data: dict) -> None:
        assert loop_data.get("input_key") == "goal"

    def test_initial_state(self, loop_data: dict) -> None:
        assert loop_data.get("initial") == "discover_loops"

    def test_context_variables(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        assert "goal" in ctx, "context must have goal variable (populated via input_key)"
        assert "auto" in ctx, "context must have auto variable"
        assert "auto_create" in ctx, "context must have auto_create variable"
        assert "confidence_threshold" in ctx, "context must have confidence_threshold variable"
        assert "exclude" in ctx, "context must have exclude variable"

    def test_context_defaults(self, loop_data: dict) -> None:
        ctx = loop_data.get("context", {})
        assert ctx.get("goal") == "", "goal default must be empty string"
        assert ctx.get("auto") == "true", "auto default must be 'true'"
        assert ctx.get("auto_create") == "false", "auto_create default must be 'false'"
        assert ctx.get("confidence_threshold") == "0.7", (
            "confidence_threshold default must be '0.7'"
        )
        assert ctx.get("exclude") == "", "exclude default must be empty string"


class TestLoopRouterStates:
    """Tests for required states and their structure."""

    REQUIRED_STATES = {
        "discover_loops",
        "classify_goal",
        "route_branch_project",
        "route_branch_builtin",
        "score_project_loops",
        "parse_project_score",
        "score_builtin_loops",
        "parse_builtin_score",
        "extract_input",
        "select_loop",
        "present_choices",
        "apply_user_choice",
        "refresh_input",
        "dispatch",
        "review",
        "propose_new_loop",
        "check_auto_create",
        "invoke_create_loop",
        "present_result",
        "failed",
    }

    def test_has_all_required_states(self, loop_data: dict) -> None:
        actual = set(loop_data.get("states", {}).keys())
        missing = self.REQUIRED_STATES - actual
        assert not missing, f"Missing required states: {missing}"

    def test_discover_loops_is_shell(self, loop_data: dict) -> None:
        state = loop_data["states"]["discover_loops"]
        assert state.get("action_type") == "shell"
        assert "ll-loop list" in state.get("action", "")
        assert state.get("capture") == "catalog"
        assert state.get("next") == "classify_goal"
        assert state.get("on_error") == "failed"

    def test_discover_loops_excludes_self(self, loop_data: dict) -> None:
        state = loop_data["states"]["discover_loops"]
        assert "loop-router" in state.get("action", ""), (
            "discover_loops must exclude 'loop-router' from the catalog"
        )

    def test_classify_goal_is_prompt(self, loop_data: dict) -> None:
        state = loop_data["states"]["classify_goal"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "classification"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "llm_structured"

    def test_classify_goal_routes_to_branch_project(self, loop_data: dict) -> None:
        state = loop_data["states"]["classify_goal"]
        assert state.get("on_yes") == "route_branch_project"
        assert state.get("on_no") == "route_branch_project"

    def test_three_branch_targets_reachable_from_classify_goal(self, loop_data: dict) -> None:
        """All three branch targets are reachable from the classify_goal→route_branch chain."""
        states = loop_data.get("states", {})
        # classify_goal → route_branch_project
        assert states["classify_goal"]["on_yes"] == "route_branch_project"
        # route_branch_project → score_project_loops (branch A) or route_branch_builtin
        assert states["route_branch_project"]["on_yes"] == "score_project_loops"
        assert states["route_branch_project"]["on_no"] == "route_branch_builtin"
        # route_branch_builtin → score_builtin_loops (branch B) or propose_new_loop (branch C)
        assert states["route_branch_builtin"]["on_yes"] == "score_builtin_loops"
        assert states["route_branch_builtin"]["on_no"] == "propose_new_loop"

    def test_route_branch_project_is_shell_exit_code(self, loop_data: dict) -> None:
        state = loop_data["states"]["route_branch_project"]
        assert state.get("action_type") == "shell"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "exit_code"

    def test_route_branch_builtin_is_shell_exit_code(self, loop_data: dict) -> None:
        state = loop_data["states"]["route_branch_builtin"]
        assert state.get("action_type") == "shell"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "exit_code"

    def test_score_project_loops_is_prompt(self, loop_data: dict) -> None:
        state = loop_data["states"]["score_project_loops"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "project_score"

    def test_score_builtin_loops_is_prompt(self, loop_data: dict) -> None:
        state = loop_data["states"]["score_builtin_loops"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "builtin_score"

    def test_dispatch_uses_native_loop_field(self, loop_data: dict) -> None:
        state = loop_data["states"]["dispatch"]
        assert "loop" in state, "dispatch must use the native loop: field (not action_type)"
        assert "captured.chosen" in state.get("loop", ""), (
            "dispatch loop: field must reference captured.chosen.output"
        )
        assert state.get("capture") == "sub_loop_output"
        assert state.get("on_yes") == "review"
        assert state.get("on_no") == "review"
        assert state.get("on_error") == "review"

    def test_dispatch_with_binding_references_derived_params(self, loop_data: dict) -> None:
        state = loop_data["states"]["dispatch"]
        with_ = state.get("with", {})
        assert "input" in with_, "dispatch must bind an input via with:"
        assert "captured.derived_params" in with_.get("input", ""), (
            "dispatch with.input must reference captured.derived_params.output"
        )

    def test_present_choices_uses_output_contains_cancel(self, loop_data: dict) -> None:
        state = loop_data["states"]["present_choices"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "user_choice"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "output_contains"
        assert evaluate.get("pattern") == "CANCEL", (
            "present_choices must use CANCEL sentinel (not PASS/ALL_PASS)"
        )
        assert state.get("on_yes") == "present_result"
        assert state.get("on_no") == "apply_user_choice"

    def test_present_result_is_terminal(self, loop_data: dict) -> None:
        state = loop_data["states"]["present_result"]
        assert state.get("terminal") is True

    def test_failed_is_terminal(self, loop_data: dict) -> None:
        state = loop_data["states"]["failed"]
        assert state.get("terminal") is True

    def test_propose_new_loop_routes_to_check_auto_create(self, loop_data: dict) -> None:
        state = loop_data["states"]["propose_new_loop"]
        assert state.get("action_type") == "prompt"
        assert state.get("capture") == "new_loop_proposal"
        assert state.get("on_yes") == "check_auto_create"

    def test_check_auto_create_routes_to_invoke_or_result(self, loop_data: dict) -> None:
        state = loop_data["states"]["check_auto_create"]
        assert state.get("on_yes") == "invoke_create_loop"
        assert state.get("on_no") == "present_result"


@pytest.mark.slow
@pytest.mark.skipif(
    shutil.which("claude") is None,
    reason="live LLM required; skip in CI unless claude CLI is available",
)
class TestLoopRouterLive:
    """Behavioural tests requiring a live LLM (claude CLI). Guarded by --slow."""

    def test_loop_validates_before_live_run(self) -> None:
        """Sanity check — loop must validate before any live test runs."""
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM validation errors: {[str(e) for e in error_list]}"

"""Tests for the outer-loop-eval built-in loop."""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from little_loops.fsm.validation import ValidationSeverity, load_and_validate, validate_fsm

BUILTIN_LOOPS_DIR = Path(__file__).parent.parent / "little_loops" / "loops"
LOOP_FILE = BUILTIN_LOOPS_DIR / "outer-loop-eval.yaml"


@pytest.fixture
def loop_data() -> dict:
    """Load the outer-loop-eval YAML."""
    assert LOOP_FILE.exists(), f"outer-loop-eval.yaml not found at {LOOP_FILE}"
    with open(LOOP_FILE) as f:
        return yaml.safe_load(f)


class TestOuterLoopEvalFile:
    """Tests that outer-loop-eval.yaml exists and is structurally valid."""

    def test_file_exists(self) -> None:
        assert LOOP_FILE.exists(), f"outer-loop-eval.yaml not found at {LOOP_FILE}"

    def test_parses_as_yaml(self, loop_data: dict) -> None:
        assert isinstance(loop_data, dict), "root must be a mapping"

    def test_validates_as_fsm(self) -> None:
        fsm, _ = load_and_validate(LOOP_FILE)
        errors = validate_fsm(fsm)
        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert not error_list, f"FSM validation errors: {[str(e) for e in error_list]}"

    def test_name(self, loop_data: dict) -> None:
        assert loop_data.get("name") == "outer-loop-eval"

    def test_initial_state(self, loop_data: dict) -> None:
        assert loop_data.get("initial") == "validate_input"

    def test_terminal_state(self, loop_data: dict) -> None:
        states = loop_data.get("states", {})
        assert "done" in states
        assert states["done"].get("terminal") is True

    def test_context_variables(self, loop_data: dict) -> None:
        context = loop_data.get("context", {})
        assert "input" in context, "context must have input variable (target loop name)"
        assert "loop_input" in context, "context must have loop_input variable"

    def test_context_defaults(self, loop_data: dict) -> None:
        context = loop_data.get("context", {})
        assert context.get("input") == "", "input default must be empty string"
        assert context.get("loop_input") == "", "loop_input default must be empty string"


class TestOuterLoopEvalStates:
    """Tests for required states and their structure."""

    REQUIRED_STATES = {
        "validate_input",
        "load_definition",
        "analyze_definition",
        "run_sub_loop",
        "analyze_execution",
        "generate_report",
        "refine_analysis",
        "done",
    }

    def test_has_all_required_states(self, loop_data: dict) -> None:
        actual = set(loop_data.get("states", {}).keys())
        missing = self.REQUIRED_STATES - actual
        assert not missing, f"Missing required states: {missing}"

    def test_validate_input_checks_loop_name(self, loop_data: dict) -> None:
        state = loop_data["states"]["validate_input"]
        assert state.get("action_type") == "shell"
        assert "context.input" in state.get("action", "")

    def test_validate_input_routes_error_to_done(self, loop_data: dict) -> None:
        state = loop_data["states"]["validate_input"]
        assert state.get("on_error") == "done"

    def test_validate_input_routes_next_to_load_definition(self, loop_data: dict) -> None:
        state = loop_data["states"]["validate_input"]
        assert state.get("next") == "load_definition"

    def test_analyze_definition_is_slash_command(self, loop_data: dict) -> None:
        state = loop_data["states"]["analyze_definition"]
        assert state.get("action_type") == "slash_command"
        assert "debug-loop-run" in state.get("action", "")
        assert "context.input" in state.get("action", "")
        assert state.get("capture") == "definition_analysis"
        assert state.get("next") == "run_sub_loop"

    def test_run_sub_loop_is_native_loop(self, loop_data: dict) -> None:
        state = loop_data["states"]["run_sub_loop"]
        assert "loop" in state, "run_sub_loop must use native loop action (not shell)"
        assert "context.input" in state.get("loop", ""), (
            "loop field must reference context.input"
        )
        assert state.get("capture") == "sub_loop_output"
        assert state.get("on_yes") == "analyze_execution"
        assert state.get("on_no") == "analyze_execution"
        assert state.get("on_error") == "analyze_execution"
        with_ = state.get("with", {})
        assert "input" in with_, "run_sub_loop must bind input via with:"

    def test_analyze_execution_is_slash_command(self, loop_data: dict) -> None:
        state = loop_data["states"]["analyze_execution"]
        assert state.get("action_type") == "slash_command"
        assert "debug-loop-run" in state.get("action", "")
        assert "context.input" in state.get("action", "")
        assert state.get("capture") == "execution_analysis"
        assert state.get("next") == "generate_report"

    def test_generate_report_has_llm_structured_evaluator(self, loop_data: dict) -> None:
        state = loop_data["states"]["generate_report"]
        assert state.get("action_type") == "slash_command"
        assert "audit-loop-run" in state.get("action", "")
        assert state.get("capture") == "improvement_report"
        evaluate = state.get("evaluate", {})
        assert evaluate.get("type") == "llm_structured"
        assert state.get("on_yes") == "done"
        assert state.get("on_no") == "refine_analysis"

    def test_refine_analysis_loops_to_generate_report(self, loop_data: dict) -> None:
        state = loop_data["states"]["refine_analysis"]
        assert state.get("action_type") == "slash_command"
        assert "audit-loop-run" in state.get("action", "")
        assert state.get("next") == "generate_report"

    def test_load_definition_captures_loop_definition(self, loop_data: dict) -> None:
        state = loop_data["states"]["load_definition"]
        assert state.get("action_type") == "shell"
        assert "context.input" in state.get("action", "")
        assert state.get("capture") == "loop_definition"
        assert state.get("next") == "analyze_definition"

    def test_run_sub_loop_input_binding_uses_context_var(self, loop_data: dict) -> None:
        """with: binding for input must reference context.loop_input."""
        with_ = loop_data["states"]["run_sub_loop"].get("with", {})
        input_val = with_.get("input", "")
        assert "context.loop_input" in input_val, (
            "run_sub_loop with.input must reference context.loop_input"
        )

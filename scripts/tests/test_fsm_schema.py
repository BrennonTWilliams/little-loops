"""Tests for FSM schema and validation.

Tests cover:
- Dataclass construction and serialization
- Validation logic for structural correctness
- Error detection and reporting
"""

from __future__ import annotations

import tempfile
from pathlib import Path
from typing import Any

import pytest

from little_loops.fsm.schema import (
    EvaluateConfig,
    FSMLoop,
    LLMConfig,
    RouteConfig,
    StateConfig,
)
from little_loops.fsm.validation import (
    ValidationError,
    ValidationSeverity,
    load_and_validate,
    validate_fsm,
)


def make_state(
    action: str | None = None,
    on_success: str | None = None,
    on_failure: str | None = None,
    terminal: bool = False,
    next: str | None = None,
    evaluate: EvaluateConfig | None = None,
    route: RouteConfig | None = None,
) -> StateConfig:
    """Helper to create test StateConfig objects."""
    return StateConfig(
        action=action,
        on_success=on_success,
        on_failure=on_failure,
        terminal=terminal,
        next=next,
        evaluate=evaluate,
        route=route,
    )


def make_fsm(
    name: str = "test-loop",
    initial: str = "start",
    states: dict[str, StateConfig] | None = None,
    max_iterations: int = 50,
) -> FSMLoop:
    """Helper to create test FSMLoop objects."""
    if states is None:
        states = {
            "start": make_state(action="echo start", on_success="done", on_failure="done"),
            "done": make_state(terminal=True),
        }
    return FSMLoop(
        name=name,
        initial=initial,
        states=states,
        max_iterations=max_iterations,
    )


class TestEvaluateConfig:
    """Tests for EvaluateConfig dataclass."""

    def test_minimal_config(self) -> None:
        """Minimal evaluator with only type."""
        config = EvaluateConfig(type="exit_code")

        assert config.type == "exit_code"
        assert config.operator is None
        assert config.target is None

    def test_output_numeric_config(self) -> None:
        """Output numeric evaluator with operator and target."""
        config = EvaluateConfig(
            type="output_numeric",
            operator="le",
            target=5,
        )

        assert config.type == "output_numeric"
        assert config.operator == "le"
        assert config.target == 5

    def test_convergence_config(self) -> None:
        """Convergence evaluator with direction."""
        config = EvaluateConfig(
            type="convergence",
            target=0,
            tolerance=0.5,
            direction="minimize",
        )

        assert config.type == "convergence"
        assert config.target == 0
        assert config.tolerance == 0.5
        assert config.direction == "minimize"

    def test_llm_structured_config(self) -> None:
        """LLM structured evaluator with confidence settings."""
        config = EvaluateConfig(
            type="llm_structured",
            prompt="Did this succeed?",
            min_confidence=0.8,
            uncertain_suffix=True,
        )

        assert config.type == "llm_structured"
        assert config.prompt == "Did this succeed?"
        assert config.min_confidence == 0.8
        assert config.uncertain_suffix is True

    def test_to_dict_minimal(self) -> None:
        """to_dict includes only type for minimal config."""
        config = EvaluateConfig(type="exit_code")
        result = config.to_dict()

        assert result == {"type": "exit_code"}

    def test_to_dict_full(self) -> None:
        """to_dict includes all non-default fields."""
        config = EvaluateConfig(
            type="output_numeric",
            operator="eq",
            target=10,
            negate=True,
        )
        result = config.to_dict()

        assert result == {
            "type": "output_numeric",
            "operator": "eq",
            "target": 10,
            "negate": True,
        }

    def test_from_dict_minimal(self) -> None:
        """from_dict with minimal fields."""
        data = {"type": "exit_code"}
        config = EvaluateConfig.from_dict(data)

        assert config.type == "exit_code"
        assert config.operator is None

    def test_roundtrip_serialization(self) -> None:
        """Roundtrip through to_dict and from_dict."""
        original = EvaluateConfig(
            type="convergence",
            target=0,
            tolerance=1.5,
            direction="maximize",
            previous="${prev.output}",
        )

        restored = EvaluateConfig.from_dict(original.to_dict())

        assert restored.type == original.type
        assert restored.target == original.target
        assert restored.tolerance == original.tolerance
        assert restored.direction == original.direction
        assert restored.previous == original.previous


class TestRouteConfig:
    """Tests for RouteConfig dataclass."""

    def test_basic_routes(self) -> None:
        """Basic route mapping."""
        config = RouteConfig(
            routes={"success": "deploy", "failure": "fix"},
        )

        assert config.routes == {"success": "deploy", "failure": "fix"}
        assert config.default is None
        assert config.error is None

    def test_with_special_keys(self) -> None:
        """Routes with default and error keys."""
        config = RouteConfig(
            routes={"success": "done"},
            default="retry",
            error="alert",
        )

        assert config.routes == {"success": "done"}
        assert config.default == "retry"
        assert config.error == "alert"

    def test_to_dict(self) -> None:
        """to_dict includes special keys as _ and _error."""
        config = RouteConfig(
            routes={"success": "done", "failure": "fix"},
            default="retry",
            error="alert",
        )
        result = config.to_dict()

        assert result == {
            "success": "done",
            "failure": "fix",
            "_": "retry",
            "_error": "alert",
        }

    def test_from_dict(self) -> None:
        """from_dict extracts special keys."""
        data = {
            "success": "done",
            "failure": "fix",
            "_": "retry",
            "_error": "alert",
        }
        config = RouteConfig.from_dict(data)

        assert config.routes == {"success": "done", "failure": "fix"}
        assert config.default == "retry"
        assert config.error == "alert"


class TestStateConfig:
    """Tests for StateConfig dataclass."""

    def test_terminal_state(self) -> None:
        """Terminal state with no transitions."""
        state = StateConfig(terminal=True)

        assert state.terminal is True
        assert state.action is None

    def test_action_with_shorthand(self) -> None:
        """State with action and shorthand routing."""
        state = StateConfig(
            action="pytest",
            on_success="deploy",
            on_failure="fix",
        )

        assert state.action == "pytest"
        assert state.on_success == "deploy"
        assert state.on_failure == "fix"

    def test_action_with_full_route(self) -> None:
        """State with action and full route table."""
        route = RouteConfig(routes={"success": "done", "blocked": "escalate"})
        state = StateConfig(action="/ll:fix", route=route)

        assert state.route is not None
        assert state.route.routes["success"] == "done"

    def test_get_referenced_states(self) -> None:
        """get_referenced_states returns all transition targets."""
        route = RouteConfig(
            routes={"blocked": "escalate"},
            default="retry",
        )
        state = StateConfig(
            on_success="done",
            on_failure="fix",
            on_error="alert",
            route=route,
        )
        refs = state.get_referenced_states()

        assert refs == {"done", "fix", "alert", "escalate", "retry"}

    def test_roundtrip_serialization(self) -> None:
        """Roundtrip through to_dict and from_dict."""
        original = StateConfig(
            action="npm test",
            evaluate=EvaluateConfig(type="exit_code"),
            on_success="deploy",
            on_failure="fix",
            capture="test_result",
            timeout=300,
        )

        restored = StateConfig.from_dict(original.to_dict())

        assert restored.action == original.action
        assert restored.evaluate is not None
        assert restored.evaluate.type == "exit_code"
        assert restored.on_success == original.on_success
        assert restored.capture == original.capture
        assert restored.timeout == original.timeout


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_defaults(self) -> None:
        """Default LLM configuration."""
        config = LLMConfig()

        assert config.enabled is True
        assert config.model == "claude-sonnet-4-20250514"
        assert config.max_tokens == 256
        assert config.timeout == 30

    def test_disabled(self) -> None:
        """LLM disabled configuration."""
        config = LLMConfig(enabled=False)

        assert config.enabled is False

    def test_to_dict_empty_for_defaults(self) -> None:
        """to_dict returns empty dict for all defaults."""
        config = LLMConfig()
        result = config.to_dict()

        assert result == {}

    def test_to_dict_non_defaults(self) -> None:
        """to_dict includes non-default values."""
        config = LLMConfig(enabled=False, max_tokens=512)
        result = config.to_dict()

        assert result == {"enabled": False, "max_tokens": 512}


class TestFSMLoop:
    """Tests for FSMLoop dataclass."""

    def test_minimal_valid_fsm(self) -> None:
        """Two-state FSM with terminal passes validation."""
        fsm = make_fsm()

        assert fsm.name == "test-loop"
        assert fsm.initial == "start"
        assert len(fsm.states) == 2
        assert "start" in fsm.states
        assert "done" in fsm.states

    def test_get_all_state_names(self) -> None:
        """get_all_state_names returns all defined states."""
        fsm = make_fsm()
        names = fsm.get_all_state_names()

        assert names == {"start", "done"}

    def test_get_terminal_states(self) -> None:
        """get_terminal_states returns states with terminal=True."""
        fsm = make_fsm()
        terminals = fsm.get_terminal_states()

        assert terminals == {"done"}

    def test_get_all_referenced_states(self) -> None:
        """get_all_referenced_states includes initial and transitions."""
        fsm = make_fsm()
        refs = fsm.get_all_referenced_states()

        assert refs == {"start", "done"}

    def test_with_context(self) -> None:
        """FSM with context variables."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={"check": make_state(terminal=True)},
            context={"target_dir": "src/", "threshold": 5},
        )

        assert fsm.context == {"target_dir": "src/", "threshold": 5}

    def test_roundtrip_serialization(self) -> None:
        """Roundtrip through to_dict and from_dict."""
        original = FSMLoop(
            name="complex-loop",
            initial="check",
            states={
                "check": StateConfig(
                    action="pytest",
                    on_success="done",
                    on_failure="fix",
                ),
                "fix": StateConfig(
                    action="/ll:fix",
                    next="check",
                ),
                "done": StateConfig(terminal=True),
            },
            context={"max_errors": 10},
            max_iterations=20,
            timeout=3600,
        )

        restored = FSMLoop.from_dict(original.to_dict())

        assert restored.name == original.name
        assert restored.initial == original.initial
        assert len(restored.states) == 3
        assert restored.context == original.context
        assert restored.max_iterations == original.max_iterations
        assert restored.timeout == original.timeout


class TestFSMValidation:
    """Tests for FSM validation logic."""

    def test_minimal_valid_fsm(self) -> None:
        """Two-state FSM with terminal passes validation."""
        fsm = make_fsm()
        errors = validate_fsm(fsm)

        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0

    def test_missing_initial_state(self) -> None:
        """Error when initial state doesn't exist."""
        fsm = FSMLoop(
            name="test",
            initial="nonexistent",
            states={"done": make_state(terminal=True)},
        )
        errors = validate_fsm(fsm)

        assert any("Initial state 'nonexistent' not found" in e.message for e in errors)

    def test_dangling_state_reference(self) -> None:
        """Error when on_success references non-existent state."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={
                "start": make_state(action="test", on_success="missing", on_failure="done"),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("References unknown state 'missing'" in e.message for e in errors)

    def test_no_terminal_state(self) -> None:
        """Error when no state has terminal=true."""
        fsm = FSMLoop(
            name="test",
            initial="loop",
            states={
                "loop": make_state(action="test", next="loop"),
            },
        )
        errors = validate_fsm(fsm)

        assert any("No terminal state defined" in e.message for e in errors)

    def test_shorthand_and_route_mutual_exclusion(self) -> None:
        """Warning when both on_success and route defined."""
        route = RouteConfig(routes={"success": "done"})
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    on_success="done",  # shorthand
                    route=route,  # also full route
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("Both shorthand routing" in e.message for e in warnings)

    def test_current_state_reference_allowed(self) -> None:
        """$current is valid as state reference for retry."""
        route = RouteConfig(routes={"success": "done", "failure": "$current"})
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(action="test", route=route),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0

    def test_unreachable_state_warning(self) -> None:
        """Warning for states not reachable from initial."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={
                "start": make_state(action="test", on_success="done", on_failure="done"),
                "done": make_state(terminal=True),
                "orphan": make_state(action="never reached", next="done"),
            },
        )
        errors = validate_fsm(fsm)

        warnings = [e for e in errors if e.severity == ValidationSeverity.WARNING]
        assert any("not reachable" in e.message for e in warnings)

    def test_state_with_no_transition(self) -> None:
        """Error for state with no transition defined."""
        fsm = FSMLoop(
            name="test",
            initial="broken",
            states={
                "broken": StateConfig(action="test"),  # no routing
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("no transition defined" in e.message for e in errors)


class TestEvaluatorValidation:
    """Tests for evaluator-specific validation."""

    def test_output_numeric_requires_operator(self) -> None:
        """output_numeric requires operator field."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(type="output_numeric", target=5),  # no operator
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("requires 'operator' field" in e.message for e in errors)

    def test_output_json_requires_path(self) -> None:
        """output_json requires path field."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="output_json",
                        operator="eq",
                        target=0,
                        # no path
                    ),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("requires 'path' field" in e.message for e in errors)

    def test_output_contains_requires_pattern(self) -> None:
        """output_contains requires pattern field."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(type="output_contains"),  # no pattern
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("requires 'pattern' field" in e.message for e in errors)

    def test_convergence_requires_target(self) -> None:
        """convergence requires target field."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(type="convergence"),  # no target
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("requires 'target' field" in e.message for e in errors)

    def test_invalid_operator(self) -> None:
        """Invalid operator is rejected."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="output_numeric",
                        operator="invalid",
                        target=5,
                    ),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("Invalid operator" in e.message for e in errors)

    def test_negative_tolerance(self) -> None:
        """Negative tolerance is rejected for convergence."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target=0,
                        tolerance=-1,  # invalid
                    ),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("cannot be negative" in e.message for e in errors)

    def test_invalid_min_confidence(self) -> None:
        """min_confidence outside 0-1 is rejected."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        min_confidence=1.5,  # invalid
                    ),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("between 0 and 1" in e.message for e in errors)


class TestLoadAndValidate:
    """Tests for load_and_validate function."""

    def test_load_valid_yaml(self) -> None:
        """Load valid YAML file."""
        yaml_content = """
name: test-loop
initial: check
states:
  check:
    action: pytest
    on_success: done
    on_failure: done
  done:
    terminal: true
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            path = Path(f.name)

        try:
            fsm = load_and_validate(path)
            assert fsm.name == "test-loop"
            assert fsm.initial == "check"
            assert len(fsm.states) == 2
        finally:
            path.unlink()

    def test_file_not_found(self) -> None:
        """FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError):
            load_and_validate(Path("/nonexistent/path.yaml"))

    def test_missing_required_fields(self) -> None:
        """ValueError for missing required fields."""
        yaml_content = """
name: incomplete
# missing initial and states
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="missing required fields"):
                load_and_validate(path)
        finally:
            path.unlink()

    def test_validation_errors_raised(self) -> None:
        """ValueError for validation failures."""
        yaml_content = """
name: invalid-loop
initial: nonexistent
states:
  done:
    terminal: true
"""
        with tempfile.NamedTemporaryFile(
            mode="w", suffix=".yaml", delete=False
        ) as f:
            f.write(yaml_content)
            path = Path(f.name)

        try:
            with pytest.raises(ValueError, match="validation failed"):
                load_and_validate(path)
        finally:
            path.unlink()


class TestValidationError:
    """Tests for ValidationError dataclass."""

    def test_error_str_with_path(self) -> None:
        """String format includes path."""
        error = ValidationError(
            message="Test error",
            path="states.check",
            severity=ValidationSeverity.ERROR,
        )

        assert str(error) == "[ERROR] states.check: Test error"

    def test_warning_str(self) -> None:
        """String format shows WARNING for warnings."""
        error = ValidationError(
            message="Test warning",
            severity=ValidationSeverity.WARNING,
        )

        assert str(error) == "[WARNING] Test warning"

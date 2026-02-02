"""Tests for FSM schema and validation.

Tests cover:
- Dataclass construction and serialization
- Validation logic for structural correctness
- Error detection and reporting
"""

from __future__ import annotations

from pathlib import Path

import pytest
import yaml

from little_loops.fsm.schema import (
    DEFAULT_LLM_MODEL,
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


@pytest.fixture
def fsm_fixtures() -> Path:
    """Path to FSM fixture files."""
    return Path(__file__).parent / "fixtures" / "fsm"


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

    def test_action_type_field(self) -> None:
        """State with explicit action_type."""
        state = StateConfig(
            action="Analyze the code and fix bugs",
            action_type="prompt",
            on_success="done",
            on_failure="retry",
        )

        assert state.action_type == "prompt"

    def test_action_type_roundtrip(self) -> None:
        """action_type survives serialization roundtrip."""
        original = StateConfig(
            action="echo hello",
            action_type="shell",
            on_success="done",
        )

        restored = StateConfig.from_dict(original.to_dict())

        assert restored.action_type == "shell"

    def test_action_type_none_by_default(self) -> None:
        """action_type is None when not specified."""
        state = StateConfig(action="pytest")

        assert state.action_type is None

    def test_action_type_slash_command(self) -> None:
        """action_type can be slash_command."""
        state = StateConfig(
            action="/ll:commit",
            action_type="slash_command",
            on_success="done",
        )

        assert state.action_type == "slash_command"

    def test_action_type_in_to_dict(self) -> None:
        """action_type is included in to_dict output when set."""
        state = StateConfig(
            action="Analyze this",
            action_type="prompt",
        )

        result = state.to_dict()

        assert result["action_type"] == "prompt"

    def test_action_type_omitted_from_to_dict_when_none(self) -> None:
        """action_type is not in to_dict output when None."""
        state = StateConfig(action="echo test")

        result = state.to_dict()

        assert "action_type" not in result


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_defaults(self) -> None:
        """Default LLM configuration."""
        config = LLMConfig()

        assert config.enabled is True
        assert config.model == DEFAULT_LLM_MODEL
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

    def test_on_error_only_shorthand(self) -> None:
        """State with on_error and next is valid."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="risky-operation",
                    on_error="handle_error",
                    next="done",  # fallback for success/failure
                ),
                "handle_error": make_state(action="log", next="done"),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0

    def test_next_only_transition_valid(self) -> None:
        """State with only 'next' transition is valid."""
        fsm = FSMLoop(
            name="test",
            initial="step1",
            states={
                "step1": StateConfig(action="echo 1", next="step2"),
                "step2": StateConfig(action="echo 2", next="done"),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0

    def test_terminal_only_state_valid(self) -> None:
        """Terminal state with no action is valid."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={
                "start": make_state(action="test", on_success="end", on_failure="end"),
                "end": StateConfig(terminal=True),  # no action, no routing
            },
        )
        errors = validate_fsm(fsm)

        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0

    def test_self_reference_transition(self) -> None:
        """State referencing itself is valid (retry pattern)."""
        fsm = FSMLoop(
            name="test",
            initial="retry_state",
            states={
                "retry_state": StateConfig(
                    action="might-fail",
                    on_success="done",
                    on_failure="retry_state",  # self-reference
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0

    def test_circular_state_references(self) -> None:
        """Circular references without terminal produce error."""
        fsm = FSMLoop(
            name="test",
            initial="a",
            states={
                "a": StateConfig(action="step a", next="b"),
                "b": StateConfig(action="step b", next="c"),
                "c": StateConfig(action="step c", next="a"),  # circular
            },
        )
        errors = validate_fsm(fsm)

        # No terminal state error
        assert any("No terminal state defined" in e.message for e in errors)

    def test_empty_states_dict(self) -> None:
        """Empty states dict produces errors."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={},
        )
        errors = validate_fsm(fsm)

        # Initial state not found
        assert any("Initial state 'start' not found" in e.message for e in errors)
        # No terminal state
        assert any("No terminal state defined" in e.message for e in errors)

    def test_multiple_terminal_states(self) -> None:
        """Multiple terminal states are valid."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    on_success="success_end",
                    on_failure="failure_end",
                ),
                "success_end": StateConfig(terminal=True),
                "failure_end": StateConfig(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0


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

    def test_output_numeric_requires_target(self) -> None:
        """output_numeric requires target field."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(type="output_numeric", operator="eq"),  # no target
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("requires 'target' field" in e.message for e in errors)

    def test_output_json_requires_operator(self) -> None:
        """output_json requires operator field."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="output_json",
                        path="$.result",
                        target=0,
                        # no operator
                    ),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("requires 'operator' field" in e.message for e in errors)

    def test_valid_operators_accepted(self) -> None:
        """All valid operators are accepted."""
        for op in ["eq", "ne", "lt", "le", "gt", "ge"]:
            fsm = FSMLoop(
                name="test",
                initial="check",
                states={
                    "check": StateConfig(
                        action="test",
                        evaluate=EvaluateConfig(type="output_numeric", operator=op, target=5),
                        on_success="done",
                        on_failure="done",
                    ),
                    "done": make_state(terminal=True),
                },
            )
            errors = validate_fsm(fsm)

            error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
            assert len(error_list) == 0, f"Operator {op} should be valid"

    def test_convergence_invalid_direction(self) -> None:
        """Convergence with invalid direction is rejected."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target=0,
                        direction="invalid",  # type: ignore[arg-type]
                    ),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("Invalid direction" in e.message for e in errors)

    def test_convergence_valid_directions(self) -> None:
        """Convergence with valid directions passes."""
        for direction in ("minimize", "maximize"):
            fsm = FSMLoop(
                name="test",
                initial="check",
                states={
                    "check": StateConfig(
                        action="test",
                        evaluate=EvaluateConfig(
                            type="convergence",
                            target=0,
                            direction=direction,
                        ),
                        on_success="done",
                        on_failure="done",
                    ),
                    "done": make_state(terminal=True),
                },
            )
            errors = validate_fsm(fsm)

            error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
            assert len(error_list) == 0, f"Direction {direction} should be valid"

    def test_convergence_interpolation_tolerance_skips_validation(self) -> None:
        """Interpolation string tolerance skips numeric validation."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="convergence",
                        target=0,
                        tolerance="${context.tolerance}",  # interpolation string
                    ),
                    on_success="done",
                    on_failure="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
        assert len(error_list) == 0

    def test_min_confidence_boundary_values(self) -> None:
        """min_confidence at boundaries (0 and 1) is valid."""
        for confidence in [0, 0.0, 1, 1.0]:
            fsm = FSMLoop(
                name="test",
                initial="check",
                states={
                    "check": StateConfig(
                        action="test",
                        evaluate=EvaluateConfig(
                            type="llm_structured",
                            min_confidence=confidence,
                        ),
                        on_success="done",
                        on_failure="done",
                    ),
                    "done": make_state(terminal=True),
                },
            )
            errors = validate_fsm(fsm)

            error_list = [e for e in errors if e.severity == ValidationSeverity.ERROR]
            assert len(error_list) == 0, f"min_confidence={confidence} should be valid"

    def test_min_confidence_negative(self) -> None:
        """Negative min_confidence is rejected."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    evaluate=EvaluateConfig(
                        type="llm_structured",
                        min_confidence=-0.1,
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

    def test_load_valid_yaml(self, fsm_fixtures: Path) -> None:
        """Load valid YAML file."""
        fixture_path = fsm_fixtures / "valid-loop.yaml"
        fsm = load_and_validate(fixture_path)
        assert fsm.name == "test-loop"
        assert fsm.initial == "check"
        assert len(fsm.states) == 2

    def test_file_not_found(self) -> None:
        """FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="FSM file not found"):
            load_and_validate(Path("/nonexistent/path.yaml"))

    def test_missing_required_fields(self, fsm_fixtures: Path) -> None:
        """ValueError for missing required fields."""
        fixture_path = fsm_fixtures / "incomplete-loop.yaml"
        with pytest.raises(ValueError, match="missing required fields"):
            load_and_validate(fixture_path)

    def test_validation_errors_raised(self, fsm_fixtures: Path) -> None:
        """ValueError for validation failures."""
        fixture_path = fsm_fixtures / "invalid-initial-state.yaml"
        with pytest.raises(ValueError, match="validation failed"):
            load_and_validate(fixture_path)

    def test_invalid_yaml_syntax(self, fsm_fixtures: Path) -> None:
        """Invalid YAML syntax raises yaml.YAMLError."""
        fixture_path = fsm_fixtures / "invalid-yaml-syntax.yaml"
        with pytest.raises(yaml.YAMLError, match="parsing"):
            load_and_validate(fixture_path)

    def test_non_dict_yaml_root(self, fsm_fixtures: Path) -> None:
        """Non-dict YAML root raises ValueError."""
        fixture_path = fsm_fixtures / "non-dict-root.yaml"
        with pytest.raises(ValueError, match="must contain a YAML mapping"):
            load_and_validate(fixture_path)

    def test_warnings_logged_not_raised(self, fsm_fixtures: Path) -> None:
        """Warnings are logged but don't raise exceptions."""
        fixture_path = fsm_fixtures / "loop-with-unreachable-state.yaml"
        # Should not raise despite unreachable state warning
        fsm = load_and_validate(fixture_path)
        assert fsm.name == "test-loop"
        assert "orphan" in fsm.states

    def test_missing_name_field(self, fsm_fixtures: Path) -> None:
        """Missing 'name' field raises ValueError."""
        fixture_path = fsm_fixtures / "missing-name.yaml"
        with pytest.raises(ValueError, match="missing required fields.*name"):
            load_and_validate(fixture_path)

    def test_missing_states_field(self, fsm_fixtures: Path) -> None:
        """Missing 'states' field raises ValueError."""
        fixture_path = fsm_fixtures / "missing-states.yaml"
        with pytest.raises(ValueError, match="missing required fields.*states"):
            load_and_validate(fixture_path)


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

    def test_error_str_without_path(self) -> None:
        """String format without path."""
        error = ValidationError(
            message="General error",
            severity=ValidationSeverity.ERROR,
        )

        assert str(error) == "[ERROR] General error"

    def test_warning_str_with_path(self) -> None:
        """Warning format includes path."""
        error = ValidationError(
            message="Potential issue",
            path="states.orphan",
            severity=ValidationSeverity.WARNING,
        )

        assert str(error) == "[WARNING] states.orphan: Potential issue"

    def test_default_severity_is_error(self) -> None:
        """Default severity is ERROR."""
        error = ValidationError(message="Something wrong")

        assert error.severity == ValidationSeverity.ERROR

    def test_severity_enum_values(self) -> None:
        """Severity enum has expected values."""
        assert ValidationSeverity.ERROR.value == "error"
        assert ValidationSeverity.WARNING.value == "warning"

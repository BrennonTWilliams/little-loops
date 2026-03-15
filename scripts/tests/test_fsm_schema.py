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
    on_yes: str | None = None,
    on_no: str | None = None,
    terminal: bool = False,
    next: str | None = None,
    evaluate: EvaluateConfig | None = None,
    route: RouteConfig | None = None,
) -> StateConfig:
    """Helper to create test StateConfig objects."""
    return StateConfig(
        action=action,
        on_yes=on_yes,
        on_no=on_no,
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
            "start": make_state(action="echo start", on_yes="done", on_no="done"),
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
            routes={"yes": "deploy", "no": "fix"},
        )

        assert config.routes == {"yes": "deploy", "no": "fix"}
        assert config.default is None
        assert config.error is None

    def test_with_special_keys(self) -> None:
        """Routes with default and error keys."""
        config = RouteConfig(
            routes={"yes": "done"},
            default="retry",
            error="alert",
        )

        assert config.routes == {"yes": "done"}
        assert config.default == "retry"
        assert config.error == "alert"

    def test_to_dict(self) -> None:
        """to_dict includes special keys as _ and _error."""
        config = RouteConfig(
            routes={"yes": "done", "no": "fix"},
            default="retry",
            error="alert",
        )
        result = config.to_dict()

        assert result == {
            "yes": "done",
            "no": "fix",
            "_": "retry",
            "_error": "alert",
        }

    def test_from_dict(self) -> None:
        """from_dict extracts special keys."""
        data = {
            "yes": "done",
            "no": "fix",
            "_": "retry",
            "_error": "alert",
        }
        config = RouteConfig.from_dict(data)

        assert config.routes == {"yes": "done", "no": "fix"}
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
            on_yes="deploy",
            on_no="fix",
        )

        assert state.action == "pytest"
        assert state.on_yes == "deploy"
        assert state.on_no == "fix"

    def test_action_with_full_route(self) -> None:
        """State with action and full route table."""
        route = RouteConfig(routes={"yes": "done", "blocked": "escalate"})
        state = StateConfig(action="/ll:fix", route=route)

        assert state.route is not None
        assert state.route.routes["yes"] == "done"

    def test_get_referenced_states(self) -> None:
        """get_referenced_states returns all transition targets."""
        route = RouteConfig(
            routes={"blocked": "escalate"},
            default="retry",
        )
        state = StateConfig(
            on_yes="done",
            on_no="fix",
            on_error="alert",
            route=route,
        )
        refs = state.get_referenced_states()

        assert refs == {"done", "fix", "alert", "escalate", "retry"}

    def test_on_partial_field(self) -> None:
        """StateConfig accepts on_partial field."""
        state = StateConfig(
            action="check.sh",
            on_yes="done",
            on_no="done",
            on_partial="fix",
        )
        assert state.on_partial == "fix"

    def test_on_partial_in_from_dict(self) -> None:
        """from_dict reads on_partial key from YAML data."""
        data = {
            "action": "check.sh",
            "on_yes": "done",
            "on_no": "retry",
            "on_partial": "fix",
        }
        state = StateConfig.from_dict(data)
        assert state.on_partial == "fix"

    def test_on_partial_in_to_dict(self) -> None:
        """to_dict serializes on_partial when set."""
        state = StateConfig(
            action="check.sh",
            on_yes="done",
            on_partial="fix",
        )
        d = state.to_dict()
        assert d["on_partial"] == "fix"

    def test_on_partial_absent_from_to_dict_when_none(self) -> None:
        """to_dict omits on_partial key when not set."""
        state = StateConfig(action="check.sh", on_yes="done")
        d = state.to_dict()
        assert "on_partial" not in d

    def test_on_partial_in_get_referenced_states(self) -> None:
        """get_referenced_states includes on_partial target."""
        state = StateConfig(
            on_yes="done",
            on_no="retry",
            on_partial="fix",
        )
        refs = state.get_referenced_states()
        assert "fix" in refs

    def test_on_partial_roundtrip(self) -> None:
        """on_partial survives to_dict/from_dict roundtrip."""
        original = StateConfig(
            action="check.sh",
            on_yes="done",
            on_no="retry",
            on_partial="fix",
        )
        restored = StateConfig.from_dict(original.to_dict())
        assert restored.on_partial == "fix"

    def test_roundtrip_serialization(self) -> None:
        """Roundtrip through to_dict and from_dict."""
        original = StateConfig(
            action="npm test",
            evaluate=EvaluateConfig(type="exit_code"),
            on_yes="deploy",
            on_no="fix",
            capture="test_result",
            timeout=300,
        )

        restored = StateConfig.from_dict(original.to_dict())

        assert restored.action == original.action
        assert restored.evaluate is not None
        assert restored.evaluate.type == "exit_code"
        assert restored.on_yes == original.on_yes
        assert restored.capture == original.capture
        assert restored.timeout == original.timeout

    def test_action_type_field(self) -> None:
        """State with explicit action_type."""
        state = StateConfig(
            action="Analyze the code and fix bugs",
            action_type="prompt",
            on_yes="done",
            on_no="retry",
        )

        assert state.action_type == "prompt"

    def test_action_type_roundtrip(self) -> None:
        """action_type survives serialization roundtrip."""
        original = StateConfig(
            action="echo hello",
            action_type="shell",
            on_yes="done",
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
            on_yes="done",
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
                    on_yes="done",
                    on_no="fix",
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
        """Error when on_yes references non-existent state."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={
                "start": make_state(action="test", on_yes="missing", on_no="done"),
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
        """Warning when both on_yes and route defined."""
        route = RouteConfig(routes={"yes": "done"})
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="test",
                    on_yes="done",  # shorthand
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
        route = RouteConfig(routes={"yes": "done", "no": "$current"})
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
                "start": make_state(action="test", on_yes="done", on_no="done"),
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

    def test_on_partial_only_shorthand_is_valid(self) -> None:
        """State with only on_partial routing passes validation."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(action="evaluate", on_partial="check"),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert not any("no transition defined" in e.message for e in errors)

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
                "start": make_state(action="test", on_yes="end", on_no="end"),
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
                    on_yes="done",
                    on_no="retry_state",  # self-reference
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
                    on_yes="success_end",
                    on_no="failure_end",
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
                    on_yes="done",
                    on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                        on_yes="done",
                        on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                        on_yes="done",
                        on_no="done",
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
                    on_yes="done",
                    on_no="done",
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
                        on_yes="done",
                        on_no="done",
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
                    on_yes="done",
                    on_no="done",
                ),
                "done": make_state(terminal=True),
            },
        )
        errors = validate_fsm(fsm)

        assert any("between 0 and 1" in e.message for e in errors)

    def test_max_iterations_zero_rejected(self) -> None:
        """max_iterations=0 is rejected at validation time."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            max_iterations=0,
        )
        errors = validate_fsm(fsm)

        error_messages = [e.message for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("max_iterations must be > 0" in m for m in error_messages)

    def test_max_iterations_negative_rejected(self) -> None:
        """Negative max_iterations is rejected."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            max_iterations=-1,
        )
        errors = validate_fsm(fsm)

        error_messages = [e.message for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("max_iterations must be > 0" in m for m in error_messages)

    def test_max_iterations_positive_accepted(self) -> None:
        """Positive max_iterations passes validation."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            max_iterations=10,
        )
        errors = validate_fsm(fsm)

        assert not any("max_iterations" in e.message for e in errors)

    def test_backoff_negative_rejected(self) -> None:
        """Negative backoff is rejected."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            backoff=-5.0,
        )
        errors = validate_fsm(fsm)

        error_messages = [e.message for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("backoff must be >= 0" in m for m in error_messages)

    def test_backoff_zero_accepted(self) -> None:
        """backoff=0 is valid (no sleep between iterations)."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            backoff=0.0,
        )
        errors = validate_fsm(fsm)

        assert not any("backoff" in e.message for e in errors)

    def test_backoff_none_accepted(self) -> None:
        """backoff=None (unset) is valid."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            backoff=None,
        )
        errors = validate_fsm(fsm)

        assert not any("backoff" in e.message for e in errors)

    def test_timeout_zero_rejected(self) -> None:
        """timeout=0 is rejected (loop would time out immediately)."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            timeout=0,
        )
        errors = validate_fsm(fsm)

        error_messages = [e.message for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("timeout must be > 0" in m for m in error_messages)

    def test_timeout_negative_rejected(self) -> None:
        """Negative timeout is rejected."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            timeout=-1,
        )
        errors = validate_fsm(fsm)

        error_messages = [e.message for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("timeout must be > 0" in m for m in error_messages)

    def test_timeout_none_accepted(self) -> None:
        """timeout=None (unset) is valid."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            timeout=None,
        )
        errors = validate_fsm(fsm)

        assert not any("timeout" in e.message for e in errors)

    def test_llm_max_tokens_zero_rejected(self) -> None:
        """llm.max_tokens=0 is rejected."""
        from little_loops.fsm.schema import LLMConfig

        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            llm=LLMConfig(max_tokens=0),
        )
        errors = validate_fsm(fsm)

        error_messages = [e.message for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("llm.max_tokens must be > 0" in m for m in error_messages)

    def test_llm_timeout_zero_rejected(self) -> None:
        """llm.timeout=0 is rejected."""
        from little_loops.fsm.schema import LLMConfig

        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": make_state(action="test", on_yes="done", on_no="done"),
                "done": make_state(terminal=True),
            },
            llm=LLMConfig(timeout=0),
        )
        errors = validate_fsm(fsm)

        error_messages = [e.message for e in errors if e.severity == ValidationSeverity.ERROR]
        assert any("llm.timeout must be > 0" in m for m in error_messages)


class TestLoadAndValidate:
    """Tests for load_and_validate function."""

    def test_load_valid_yaml(self, fsm_fixtures: Path) -> None:
        """Load valid YAML file."""
        fixture_path = fsm_fixtures / "valid-loop.yaml"
        fsm, warnings = load_and_validate(fixture_path)
        assert fsm.name == "test-loop"
        assert fsm.initial == "check"
        assert len(fsm.states) == 2
        assert warnings == []

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
        fsm, warnings = load_and_validate(fixture_path)
        assert fsm.name == "test-loop"
        assert "orphan" in fsm.states
        assert any(w.severity == ValidationSeverity.WARNING for w in warnings)

    def test_unknown_top_level_keys_warn(self, tmp_path: Path) -> None:
        """Unknown top-level keys produce WARNING, not ERROR."""
        loop_yaml = tmp_path / "unknown-keys.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "initial: check\n"
            "max_iteration: 5\n"  # typo: should be max_iterations
            "foo: bar\n"
            "states:\n"
            "  check:\n"
            "    terminal: true\n"
        )
        fsm, warnings = load_and_validate(loop_yaml)
        assert fsm.name == "test-loop"
        unknown_warnings = [w for w in warnings if w.severity == ValidationSeverity.WARNING]
        assert len(unknown_warnings) == 1
        assert "foo" in unknown_warnings[0].message
        assert "max_iteration" in unknown_warnings[0].message
        # No errors raised
        assert all(w.severity == ValidationSeverity.WARNING for w in unknown_warnings)

    def test_known_keys_no_warning(self, tmp_path: Path) -> None:
        """Known top-level keys produce no unknown-key warning."""
        loop_yaml = tmp_path / "known-keys.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "initial: check\n"
            "max_iterations: 5\n"
            "states:\n"
            "  check:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []

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


class TestMcpToolSchema:
    """Tests for mcp_tool action_type and mcp_result evaluator in schema."""

    def test_mcp_tool_action_type_is_valid(self) -> None:
        """action_type='mcp_tool' is accepted by StateConfig."""
        state = StateConfig(
            action="browser/navigate",
            action_type="mcp_tool",
            params={"url": "https://example.com"},
            route=RouteConfig(routes={"success": "done"}),
        )
        assert state.action_type == "mcp_tool"
        assert state.params == {"url": "https://example.com"}

    def test_params_round_trips_through_dict(self) -> None:
        """params field serializes and deserializes correctly."""
        state = StateConfig(
            action="db/query",
            action_type="mcp_tool",
            params={"sql": "SELECT 1", "limit": 100},
            route=RouteConfig(routes={"success": "done"}),
        )
        d = state.to_dict()
        assert d["params"] == {"sql": "SELECT 1", "limit": 100}

        restored = StateConfig.from_dict(d)
        assert restored.params == {"sql": "SELECT 1", "limit": 100}
        assert restored.action_type == "mcp_tool"

    def test_params_absent_when_empty(self) -> None:
        """to_dict omits params when it is empty (default)."""
        state = StateConfig(action="echo hi", on_yes="done")
        d = state.to_dict()
        assert "params" not in d

    def test_params_from_dict_defaults_to_empty(self) -> None:
        """from_dict sets params to {} when key is absent."""
        state = StateConfig.from_dict({"action": "echo hi", "on_yes": "done"})
        assert state.params == {}

    def test_mcp_result_evaluator_type_is_valid(self) -> None:
        """EvaluateConfig accepts type='mcp_result'."""
        config = EvaluateConfig(type="mcp_result")
        assert config.type == "mcp_result"

    def test_mcp_result_round_trips_through_dict(self) -> None:
        """mcp_result evaluator serializes and deserializes correctly."""
        config = EvaluateConfig(type="mcp_result")
        d = config.to_dict()
        assert d["type"] == "mcp_result"
        restored = EvaluateConfig.from_dict(d)
        assert restored.type == "mcp_result"

    def test_mcp_tool_state_validation_passes(self) -> None:
        """An mcp_tool state passes validation."""
        fsm = FSMLoop(
            name="test",
            initial="fetch",
            states={
                "fetch": StateConfig(
                    action="browser/navigate",
                    action_type="mcp_tool",
                    params={"url": "https://example.com"},
                    evaluate=EvaluateConfig(type="mcp_result"),
                    route=RouteConfig(
                        routes={
                            "success": "done",
                            "tool_error": "done",
                            "not_found": "done",
                            "timeout": "done",
                        }
                    ),
                ),
                "done": StateConfig(terminal=True),
            },
        )
        from little_loops.fsm.validation import validate_fsm

        errors = validate_fsm(fsm)
        error_only = [e for e in errors if e.severity.value == "error"]
        assert error_only == []

    def test_params_on_non_mcp_tool_state_fails_validation(self) -> None:
        """Using params on a non-mcp_tool state is a validation error."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="echo hi",
                    action_type="shell",
                    params={"key": "value"},  # invalid: not mcp_tool
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        from little_loops.fsm.validation import validate_fsm

        errors = validate_fsm(fsm)
        error_messages = [str(e) for e in errors]
        assert any("params" in m and "mcp_tool" in m for m in error_messages)

    def test_params_on_shell_without_action_type_fails_validation(self) -> None:
        """Using params on a shell state (no explicit action_type) is a validation error."""
        fsm = FSMLoop(
            name="test",
            initial="check",
            states={
                "check": StateConfig(
                    action="echo hi",
                    params={"key": "value"},  # invalid: heuristic = shell
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        from little_loops.fsm.validation import validate_fsm

        errors = validate_fsm(fsm)
        error_messages = [str(e) for e in errors]
        assert any("params" in m and "mcp_tool" in m for m in error_messages)

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
    CircuitConfig,
    CommandEntry,
    CostCeilingConfig,
    EvaluateConfig,
    FSMLoop,
    LearningConfig,
    LLMConfig,
    LoopConfigOverrides,
    ParameterSpec,
    PromptSizeGuardConfig,
    RepeatedFailureConfig,
    RouteConfig,
    StateConfig,
    TargetFileSpec,
    TargetStateSpec,
    ThrottleConfig,
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
    model: str | None = None,
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
        model=model,
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

    def test_append_to_messages_from_dict(self) -> None:
        """from_dict parses append_to_messages field."""
        data = {"action": "run.sh", "append_to_messages": "${captured.run.output}", "next": "done"}
        state = StateConfig.from_dict(data)
        assert state.append_to_messages == "${captured.run.output}"

    def test_append_to_messages_roundtrip(self) -> None:
        """append_to_messages survives to_dict/from_dict roundtrip."""
        original = StateConfig(
            action="run.sh",
            append_to_messages="${captured.run.output}",
            next="done",
        )
        restored = StateConfig.from_dict(original.to_dict())
        assert restored.append_to_messages == "${captured.run.output}"

    def test_append_to_messages_default_none(self) -> None:
        """append_to_messages defaults to None when absent."""
        state = StateConfig.from_dict({"action": "run.sh", "next": "done"})
        assert state.append_to_messages is None

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

    def test_on_blocked_field(self) -> None:
        """StateConfig accepts on_blocked field."""
        state = StateConfig(
            action="check.sh",
            on_yes="done",
            on_no="done",
            on_blocked="recover",
        )
        assert state.on_blocked == "recover"

    def test_on_blocked_in_from_dict(self) -> None:
        """from_dict reads on_blocked key from YAML data."""
        data = {
            "action": "check.sh",
            "on_yes": "done",
            "on_no": "retry",
            "on_blocked": "recover",
        }
        state = StateConfig.from_dict(data)
        assert state.on_blocked == "recover"

    def test_on_blocked_in_to_dict(self) -> None:
        """to_dict serializes on_blocked when set."""
        state = StateConfig(
            action="check.sh",
            on_yes="done",
            on_blocked="recover",
        )
        d = state.to_dict()
        assert d["on_blocked"] == "recover"

    def test_on_blocked_absent_from_to_dict_when_none(self) -> None:
        """to_dict omits on_blocked key when not set."""
        state = StateConfig(action="check.sh", on_yes="done")
        d = state.to_dict()
        assert "on_blocked" not in d

    def test_on_blocked_in_get_referenced_states(self) -> None:
        """get_referenced_states includes on_blocked target."""
        state = StateConfig(
            on_yes="done",
            on_no="retry",
            on_blocked="recover",
        )
        refs = state.get_referenced_states()
        assert "recover" in refs

    def test_on_blocked_roundtrip(self) -> None:
        """on_blocked survives to_dict/from_dict roundtrip."""
        original = StateConfig(
            action="check.sh",
            on_yes="done",
            on_no="retry",
            on_blocked="recover",
        )
        restored = StateConfig.from_dict(original.to_dict())
        assert restored.on_blocked == "recover"

    def test_extra_routes_field(self) -> None:
        """StateConfig accepts extra_routes for custom on_* verdicts."""
        state = StateConfig(
            evaluate=EvaluateConfig(type="llm_structured"),
            extra_routes={"done": "final", "retry": "check"},
        )
        assert state.extra_routes == {"done": "final", "retry": "check"}

    def test_extra_routes_in_from_dict(self) -> None:
        """from_dict populates extra_routes from unknown on_* keys."""
        data = {
            "on_done": "final",
            "on_retry": "check",
        }
        state = StateConfig.from_dict(data)
        assert state.extra_routes == {"done": "final", "retry": "check"}

    def test_extra_routes_in_to_dict(self) -> None:
        """to_dict serializes extra_routes as on_<verdict> keys."""
        state = StateConfig(extra_routes={"done": "final", "retry": "check"})
        d = state.to_dict()
        assert d["on_done"] == "final"
        assert d["on_retry"] == "check"

    def test_extra_routes_absent_from_to_dict_when_empty(self) -> None:
        """to_dict omits extra on_* keys when extra_routes is empty."""
        state = StateConfig(action="check.sh", on_yes="done")
        d = state.to_dict()
        assert "on_done" not in d
        assert "on_retry" not in d

    def test_extra_routes_in_get_referenced_states(self) -> None:
        """get_referenced_states includes extra_routes target states."""
        state = StateConfig(extra_routes={"done": "final", "retry": "check"})
        refs = state.get_referenced_states()
        assert "final" in refs
        assert "check" in refs

    def test_extra_routes_roundtrip(self) -> None:
        """extra_routes survive to_dict/from_dict roundtrip."""
        original = StateConfig(
            evaluate=EvaluateConfig(type="llm_structured"),
            extra_routes={"done": "final", "retry": "check"},
        )
        restored = StateConfig.from_dict(original.to_dict())
        assert restored.extra_routes == {"done": "final", "retry": "check"}

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

    def test_retryable_exit_codes_roundtrip(self) -> None:
        """retryable_exit_codes survives to_dict/from_dict roundtrip."""
        original = StateConfig(
            action="do work",
            on_error="do_work",
            max_retries=3,
            on_retry_exhausted="diagnose",
            retryable_exit_codes=[1, 137],
        )
        restored = StateConfig.from_dict(original.to_dict())
        assert restored.retryable_exit_codes == [1, 137]
        assert restored.max_retries == 3
        assert restored.on_retry_exhausted == "diagnose"

    def test_retryable_exit_codes_is_none_by_default(self) -> None:
        state = StateConfig(action="do work")
        assert state.retryable_exit_codes is None

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

    # -------------------------------------------------------------------
    # BUG-1109: rate-limit field tests (max_rate_limit_retries,
    # on_rate_limit_exhausted, rate_limit_backoff_base_seconds)
    # -------------------------------------------------------------------

    def test_rate_limit_fields_construction(self) -> None:
        """StateConfig accepts the three rate-limit fields."""
        state = StateConfig(
            action="run",
            on_yes="done",
            on_no="done",
            max_rate_limit_retries=5,
            on_rate_limit_exhausted="recover",
            rate_limit_backoff_base_seconds=45,
        )
        assert state.max_rate_limit_retries == 5
        assert state.on_rate_limit_exhausted == "recover"
        assert state.rate_limit_backoff_base_seconds == 45

    def test_rate_limit_fields_default_none(self) -> None:
        """Rate-limit fields default to None when absent."""
        state = StateConfig(action="run")
        assert state.max_rate_limit_retries is None
        assert state.on_rate_limit_exhausted is None
        assert state.rate_limit_backoff_base_seconds is None

    def test_rate_limit_fields_from_dict(self) -> None:
        """from_dict reads rate-limit keys from YAML data."""
        data = {
            "action": "run",
            "on_yes": "done",
            "on_no": "done",
            "max_rate_limit_retries": 3,
            "on_rate_limit_exhausted": "recover",
            "rate_limit_backoff_base_seconds": 30,
        }
        state = StateConfig.from_dict(data)
        assert state.max_rate_limit_retries == 3
        assert state.on_rate_limit_exhausted == "recover"
        assert state.rate_limit_backoff_base_seconds == 30

    def test_rate_limit_fields_to_dict(self) -> None:
        """to_dict serializes rate-limit fields when set."""
        state = StateConfig(
            action="run",
            on_yes="done",
            max_rate_limit_retries=3,
            on_rate_limit_exhausted="recover",
            rate_limit_backoff_base_seconds=30,
        )
        d = state.to_dict()
        assert d["max_rate_limit_retries"] == 3
        assert d["on_rate_limit_exhausted"] == "recover"
        assert d["rate_limit_backoff_base_seconds"] == 30

    def test_rate_limit_fields_absent_from_to_dict_when_none(self) -> None:
        """to_dict omits rate-limit keys when not set."""
        state = StateConfig(action="run", on_yes="done")
        d = state.to_dict()
        assert "max_rate_limit_retries" not in d
        assert "on_rate_limit_exhausted" not in d
        assert "rate_limit_backoff_base_seconds" not in d

    def test_on_rate_limit_exhausted_in_get_referenced_states(self) -> None:
        """get_referenced_states includes on_rate_limit_exhausted target."""
        state = StateConfig(
            action="run",
            on_yes="done",
            on_no="done",
            max_rate_limit_retries=3,
            on_rate_limit_exhausted="recover",
        )
        refs = state.get_referenced_states()
        assert "recover" in refs

    def test_rate_limit_fields_roundtrip(self) -> None:
        """Rate-limit fields survive to_dict/from_dict roundtrip."""
        original = StateConfig(
            action="run",
            on_yes="done",
            on_no="done",
            max_rate_limit_retries=3,
            on_rate_limit_exhausted="recover",
            rate_limit_backoff_base_seconds=30,
        )
        restored = StateConfig.from_dict(original.to_dict())
        assert restored.max_rate_limit_retries == 3
        assert restored.on_rate_limit_exhausted == "recover"
        assert restored.rate_limit_backoff_base_seconds == 30

    # -------------------------------------------------------------------
    # ENH-1132: long-wait rate-limit fields
    # (rate_limit_max_wait_seconds, rate_limit_long_wait_ladder)
    # -------------------------------------------------------------------

    def test_long_wait_rate_limit_fields_default_none(self) -> None:
        """Long-wait rate-limit fields default to None when absent."""
        state = StateConfig(action="run")
        assert state.rate_limit_max_wait_seconds is None
        assert state.rate_limit_long_wait_ladder is None

    def test_long_wait_rate_limit_fields_from_dict(self) -> None:
        """from_dict reads long-wait keys from YAML data."""
        data = {
            "action": "run",
            "on_yes": "done",
            "rate_limit_max_wait_seconds": 21600,
            "rate_limit_long_wait_ladder": [300, 900, 1800, 3600],
        }
        state = StateConfig.from_dict(data)
        assert state.rate_limit_max_wait_seconds == 21600
        assert state.rate_limit_long_wait_ladder == [300, 900, 1800, 3600]

    def test_long_wait_rate_limit_fields_to_dict(self) -> None:
        """to_dict serializes long-wait fields when set."""
        state = StateConfig(
            action="run",
            on_yes="done",
            rate_limit_max_wait_seconds=21600,
            rate_limit_long_wait_ladder=[300, 900, 1800, 3600],
        )
        d = state.to_dict()
        assert d["rate_limit_max_wait_seconds"] == 21600
        assert d["rate_limit_long_wait_ladder"] == [300, 900, 1800, 3600]

    def test_long_wait_rate_limit_fields_absent_from_to_dict_when_none(self) -> None:
        """to_dict omits long-wait keys when not set."""
        state = StateConfig(action="run", on_yes="done")
        d = state.to_dict()
        assert "rate_limit_max_wait_seconds" not in d
        assert "rate_limit_long_wait_ladder" not in d

    def test_long_wait_rate_limit_fields_roundtrip(self) -> None:
        """Long-wait fields survive to_dict/from_dict roundtrip."""
        original = StateConfig(
            action="run",
            on_yes="done",
            rate_limit_max_wait_seconds=7200,
            rate_limit_long_wait_ladder=[60, 120, 240],
        )
        restored = StateConfig.from_dict(original.to_dict())
        assert restored.rate_limit_max_wait_seconds == 7200
        assert restored.rate_limit_long_wait_ladder == [60, 120, 240]


class TestLLMConfig:
    """Tests for LLMConfig dataclass."""

    def test_defaults(self) -> None:
        """Default LLM configuration."""
        config = LLMConfig()

        assert config.enabled is True
        assert config.model == DEFAULT_LLM_MODEL
        assert config.max_tokens == 256
        assert config.timeout == 1800

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
            max_steps=20,
            timeout=3600,
        )

        restored = FSMLoop.from_dict(original.to_dict())

        assert restored.name == original.name
        assert restored.initial == original.initial
        assert len(restored.states) == 3
        assert restored.context == original.context
        assert restored.max_steps == original.max_steps
        assert restored.timeout == original.timeout

    def test_roundtrip_on_max_iterations(self) -> None:
        """on_max_iterations field survives to_dict/from_dict roundtrip."""
        original = FSMLoop(
            name="capped-loop",
            initial="work",
            on_max_iterations="summarize",
            states={
                "work": StateConfig(action="run.sh", on_yes="done", on_no="work"),
                "summarize": StateConfig(action="summarize.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
        )

        d = original.to_dict()
        assert d["on_max_iterations"] == "summarize"

        restored = FSMLoop.from_dict(d)
        assert restored.on_max_iterations == "summarize"

    def test_on_max_iterations_omitted_when_none(self) -> None:
        """on_max_iterations is absent from to_dict when not set (default None)."""
        fsm = FSMLoop(
            name="basic",
            initial="work",
            states={
                "work": StateConfig(action="run.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        d = fsm.to_dict()
        assert "on_max_iterations" not in d

    def test_on_max_iterations_included_in_referenced_states(self) -> None:
        """get_all_referenced_states includes the on_max_iterations target."""
        fsm = FSMLoop(
            name="capped-loop",
            initial="work",
            on_max_iterations="summarize",
            states={
                "work": StateConfig(action="run.sh", on_yes="done", on_no="work"),
                "summarize": StateConfig(action="summarize.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
        )
        refs = fsm.get_all_referenced_states()
        assert "summarize" in refs


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
            "description: test\n"
            "initial: check\n"
            "max_iteration: 5\n"  # typo: should be max_iterations
            "foo: bar\n"
            "states:\n"
            "  check:\n"
            "    terminal: true\n"
        )
        fsm, warnings = load_and_validate(loop_yaml)
        assert fsm.name == "test-loop"
        unknown_warnings = [
            w
            for w in warnings
            if w.severity == ValidationSeverity.WARNING and "Unknown top-level" in w.message
        ]
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

    def test_commands_key_no_warning(self, tmp_path: Path) -> None:
        """A YAML with top-level 'commands:' block produces no unknown-key warning."""
        loop_yaml = tmp_path / "commands-key.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A parameterized loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    terminal: true\n"
            "commands:\n"
            "  - cmd: 'll-loop run test-loop --param issue_id=ENH-1367'\n"
            "    comment: 'run (replace issue_id)'\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []

    def test_missing_description_warns(self, tmp_path: Path) -> None:
        """ENH-1331: loop YAML without description: produces a WARNING."""
        loop_yaml = tmp_path / "no-description.yaml"
        loop_yaml.write_text(
            "name: test-loop\ninitial: check\nstates:\n  check:\n    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        description_warnings = [
            w
            for w in warnings
            if w.severity == ValidationSeverity.WARNING and "description" in w.message.lower()
        ]
        assert len(description_warnings) == 1
        assert "description" in description_warnings[0].message

    def test_present_description_no_warning(self, tmp_path: Path) -> None:
        """ENH-1331: loop YAML with description: produces no description warning."""
        loop_yaml = tmp_path / "with-description.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A test loop\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        description_warnings = [w for w in warnings if "No 'description' field" in w.message]
        assert description_warnings == []

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

    def test_required_inputs_key_no_warning(self, tmp_path: Path) -> None:
        """A YAML with top-level 'required_inputs:' produces no unknown-key warning."""
        loop_yaml = tmp_path / "required-inputs-key.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop that needs an input\n"
            "initial: check\n"
            "input_key: description\n"
            "required_inputs:\n"
            "  - description\n"
            "states:\n"
            "  check:\n"
            "    terminal: true\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []


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

    def test_harbor_scorer_evaluator_type_is_valid(self) -> None:
        """EvaluateConfig accepts type='harbor_scorer'."""
        config = EvaluateConfig(type="harbor_scorer")
        assert config.type == "harbor_scorer"

    def test_harbor_scorer_round_trips_through_dict(self) -> None:
        """harbor_scorer evaluator serializes and deserializes correctly."""
        config = EvaluateConfig(type="harbor_scorer")
        d = config.to_dict()
        assert d["type"] == "harbor_scorer"
        restored = EvaluateConfig.from_dict(d)
        assert restored.type == "harbor_scorer"

    def test_action_stall_evaluator_type_is_valid(self) -> None:
        """EvaluateConfig accepts type='action_stall'."""
        config = EvaluateConfig(type="action_stall")
        assert config.type == "action_stall"

    def test_action_stall_round_trips_through_dict(self) -> None:
        """action_stall evaluator serializes and deserializes with track/max_repeat."""
        config = EvaluateConfig(type="action_stall", track=["action", "output"], max_repeat=3)
        d = config.to_dict()
        assert d["type"] == "action_stall"
        assert d["track"] == ["action", "output"]
        assert d["max_repeat"] == 3
        restored = EvaluateConfig.from_dict(d)
        assert restored.type == "action_stall"
        assert restored.track == ["action", "output"]
        assert restored.max_repeat == 3

    def test_action_stall_to_dict_omits_defaults(self) -> None:
        """action_stall to_dict omits track when None and max_repeat when 2."""
        config = EvaluateConfig(type="action_stall")
        d = config.to_dict()
        assert "track" not in d
        assert "max_repeat" not in d

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

    def test_comparator_evaluator_type_is_valid(self) -> None:
        """comparator is a valid EvaluateConfig type."""
        config = EvaluateConfig(type="comparator", baseline_path=".loops/baselines/test/")
        assert config.type == "comparator"
        assert config.baseline_path == ".loops/baselines/test/"

    def test_comparator_round_trips_through_dict(self) -> None:
        """comparator evaluator serializes and deserializes correctly."""
        config = EvaluateConfig(type="comparator", baseline_path=".loops/baselines/my-loop/")
        d = config.to_dict()
        assert d["type"] == "comparator"
        assert d["baseline_path"] == ".loops/baselines/my-loop/"
        restored = EvaluateConfig.from_dict(d)
        assert restored.type == "comparator"
        assert restored.baseline_path == ".loops/baselines/my-loop/"

    def test_comparator_baseline_path_field_roundtrip(self) -> None:
        """baseline_path serializes only when non-None."""
        config_with = EvaluateConfig(type="comparator", baseline_path=".loops/baselines/x/")
        d_with = config_with.to_dict()
        assert "baseline_path" in d_with

        config_without = EvaluateConfig(type="exit_code")
        d_without = config_without.to_dict()
        assert "baseline_path" not in d_without

    def test_comparator_auto_promote_field_roundtrip(self) -> None:
        """auto_promote serializes only when True."""
        config_true = EvaluateConfig(
            type="comparator", baseline_path=".loops/baselines/x/", auto_promote=True
        )
        d_true = config_true.to_dict()
        assert d_true.get("auto_promote") is True

        config_false = EvaluateConfig(type="comparator", baseline_path=".loops/baselines/x/")
        d_false = config_false.to_dict()
        assert "auto_promote" not in d_false

        restored = EvaluateConfig.from_dict(d_true)
        assert restored.auto_promote is True

    def test_comparator_min_pairs_field_roundtrip(self) -> None:
        """min_pairs serializes only when != 1 (the default)."""
        config_default = EvaluateConfig(type="comparator", baseline_path=".loops/baselines/x/")
        d_default = config_default.to_dict()
        assert "min_pairs" not in d_default  # default omitted

        config_three = EvaluateConfig(
            type="comparator", baseline_path=".loops/baselines/x/", min_pairs=3
        )
        d_three = config_three.to_dict()
        assert d_three["min_pairs"] == 3

        restored = EvaluateConfig.from_dict(d_three)
        assert restored.min_pairs == 3


class TestSubLoopStateConfig:
    """Tests for sub-loop state configuration (FEAT-659)."""

    def test_state_config_with_loop_field(self) -> None:
        """StateConfig accepts loop field."""
        state = StateConfig(loop="child-loop", on_yes="done", on_no="error")
        assert state.loop == "child-loop"
        assert state.context_passthrough is False

    def test_state_config_context_passthrough(self) -> None:
        """StateConfig accepts context_passthrough field."""
        state = StateConfig(loop="child", context_passthrough=True, on_yes="done")
        assert state.context_passthrough is True

    def test_state_config_loop_defaults_to_none(self) -> None:
        """Existing states without loop field still work."""
        state = StateConfig(action="echo hi", on_yes="done")
        assert state.loop is None
        assert state.context_passthrough is False

    def test_to_dict_includes_loop_when_set(self) -> None:
        """to_dict includes loop and context_passthrough when set."""
        state = StateConfig(loop="child", context_passthrough=True, on_yes="done")
        d = state.to_dict()
        assert d["loop"] == "child"
        assert d["context_passthrough"] is True

    def test_to_dict_excludes_loop_when_none(self) -> None:
        """to_dict omits loop and context_passthrough when default."""
        state = StateConfig(action="echo hi", on_yes="done")
        d = state.to_dict()
        assert "loop" not in d
        assert "context_passthrough" not in d

    def test_from_dict_with_loop(self) -> None:
        """from_dict deserializes loop and context_passthrough."""
        data = {"loop": "child", "context_passthrough": True, "on_success": "done"}
        state = StateConfig.from_dict(data)
        assert state.loop == "child"
        assert state.context_passthrough is True
        assert state.on_yes == "done"  # on_success alias

    def test_from_dict_without_loop(self) -> None:
        """from_dict defaults loop to None."""
        data = {"action": "echo hi", "on_yes": "done"}
        state = StateConfig.from_dict(data)
        assert state.loop is None
        assert state.context_passthrough is False

    def test_worktree_defaults_to_none(self) -> None:
        """StateConfig.worktree defaults to None (ENH-2609)."""
        state = StateConfig(loop="child", on_yes="done")
        assert state.worktree is None

    def test_worktree_round_trip(self) -> None:
        """worktree survives from_dict -> to_dict (ENH-2609)."""
        data = {
            "loop": "autodev",
            "worktree": "${captured.epic_branch.output}",
            "on_success": "done",
        }
        state = StateConfig.from_dict(data)
        assert state.worktree == "${captured.epic_branch.output}"
        d = state.to_dict()
        assert d["worktree"] == "${captured.epic_branch.output}"

    def test_to_dict_excludes_worktree_when_none(self) -> None:
        """to_dict omits worktree when unset (ENH-2609)."""
        state = StateConfig(loop="child", on_yes="done")
        assert "worktree" not in state.to_dict()

    def test_loop_and_action_mutual_exclusion(self) -> None:
        """Validation rejects state with both loop and action."""
        fsm = FSMLoop(
            name="test",
            initial="bad",
            states={
                "bad": StateConfig(
                    loop="child",
                    action="echo hi",  # mutually exclusive with loop
                    on_yes="done",
                ),
                "done": StateConfig(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        error_messages = [str(e) for e in errors]
        assert any("loop" in m and "action" in m for m in error_messages)

    def test_sub_loop_state_no_transition_error(self) -> None:
        """A state with loop: set should not trigger 'no transition' error."""
        fsm = FSMLoop(
            name="test",
            initial="run_child",
            states={
                "run_child": StateConfig(
                    loop="child",
                    on_yes="done",
                    on_no="error",
                ),
                "done": StateConfig(terminal=True),
                "error": StateConfig(terminal=True),
            },
        )
        errors = validate_fsm(fsm)
        error_messages = [str(e) for e in errors]
        assert not any("no transition" in m.lower() for m in error_messages)


class TestLoopConfigOverrides:
    """Tests for LoopConfigOverrides dataclass (FEAT-862)."""

    def test_defaults(self) -> None:
        """All fields default to None."""
        cfg = LoopConfigOverrides()

        assert cfg.handoff_threshold is None
        assert cfg.readiness_threshold is None
        assert cfg.outcome_threshold is None
        assert cfg.max_continuations is None

    def test_to_dict_empty_for_defaults(self) -> None:
        """to_dict returns empty dict when all fields are None."""
        cfg = LoopConfigOverrides()

        assert cfg.to_dict() == {}

    def test_to_dict_with_handoff_threshold(self) -> None:
        """to_dict includes handoff_threshold when set."""
        cfg = LoopConfigOverrides(handoff_threshold=60)

        assert cfg.to_dict() == {"handoff_threshold": 60}

    def test_to_dict_with_confidence_gate_fields(self) -> None:
        """to_dict nests readiness/outcome under commands.confidence_gate."""
        cfg = LoopConfigOverrides(readiness_threshold=70, outcome_threshold=55)
        result = cfg.to_dict()

        assert result == {
            "commands": {"confidence_gate": {"readiness_threshold": 70, "outcome_threshold": 55}}
        }

    def test_to_dict_with_max_continuations(self) -> None:
        """to_dict nests max_continuations under automation."""
        cfg = LoopConfigOverrides(max_continuations=5)

        assert cfg.to_dict() == {"automation": {"max_continuations": 5}}

    def test_from_dict_handoff_threshold(self) -> None:
        """from_dict parses handoff_threshold."""
        cfg = LoopConfigOverrides.from_dict({"handoff_threshold": 60})

        assert cfg.handoff_threshold == 60
        assert cfg.readiness_threshold is None

    def test_from_dict_confidence_gate_fields(self) -> None:
        """from_dict parses nested commands.confidence_gate.*."""
        data = {
            "commands": {"confidence_gate": {"readiness_threshold": 70, "outcome_threshold": 55}}
        }
        cfg = LoopConfigOverrides.from_dict(data)

        assert cfg.readiness_threshold == 70
        assert cfg.outcome_threshold == 55
        assert cfg.handoff_threshold is None

    def test_from_dict_max_continuations(self) -> None:
        """from_dict parses nested automation.max_continuations."""
        cfg = LoopConfigOverrides.from_dict({"automation": {"max_continuations": 5}})

        assert cfg.max_continuations == 5

    def test_roundtrip(self) -> None:
        """from_dict → to_dict is lossless for all fields."""
        original = LoopConfigOverrides(
            handoff_threshold=60,
            readiness_threshold=70,
            outcome_threshold=55,
            max_continuations=5,
        )
        restored = LoopConfigOverrides.from_dict(original.to_dict())

        assert restored.handoff_threshold == 60
        assert restored.readiness_threshold == 70
        assert restored.outcome_threshold == 55
        assert restored.max_continuations == 5

    def test_fsm_loop_config_field_defaults_to_none(self) -> None:
        """FSMLoop.config is None when no config block in YAML."""
        fsm = make_fsm()

        assert fsm.config is None

    def test_fsm_loop_from_dict_with_config_block(self) -> None:
        """FSMLoop.from_dict parses config block correctly."""
        data = {
            "name": "test-loop",
            "initial": "done",
            "states": {"done": {"terminal": True}},
            "config": {"handoff_threshold": 60},
        }
        fsm = FSMLoop.from_dict(data)

        assert fsm.config is not None
        assert fsm.config.handoff_threshold == 60

    def test_fsm_loop_to_dict_includes_config(self) -> None:
        """FSMLoop.to_dict includes config block when non-default."""
        fsm = make_fsm()
        fsm.config = LoopConfigOverrides(handoff_threshold=60)
        result = fsm.to_dict()

        assert "config" in result
        assert result["config"] == {"handoff_threshold": 60}

    def test_fsm_loop_to_dict_omits_empty_config(self) -> None:
        """FSMLoop.to_dict omits config key when all fields are defaults."""
        fsm = make_fsm()
        fsm.config = LoopConfigOverrides()
        result = fsm.to_dict()

        assert "config" not in result


class TestAgentToolsStateConfig:
    """Tests for agent: and tools: FSM state fields (FEAT-1011)."""

    def test_state_config_agent_defaults_to_none(self) -> None:
        """StateConfig.agent defaults to None."""
        state = StateConfig(action="echo hi", next="done")
        assert state.agent is None

    def test_state_config_tools_defaults_to_none(self) -> None:
        """StateConfig.tools defaults to None."""
        state = StateConfig(action="echo hi", next="done")
        assert state.tools is None

    def test_state_config_accepts_agent(self) -> None:
        """StateConfig accepts agent field."""
        state = StateConfig(action="/ll:test", action_type="prompt", agent="my-agent", next="done")
        assert state.agent == "my-agent"

    def test_state_config_accepts_tools(self) -> None:
        """StateConfig accepts tools field."""
        state = StateConfig(
            action="/ll:test", action_type="prompt", tools=["Bash", "Edit"], next="done"
        )
        assert state.tools == ["Bash", "Edit"]

    def test_to_dict_includes_agent_when_set(self) -> None:
        """to_dict includes agent when set."""
        state = StateConfig(action="/ll:test", agent="my-agent", next="done")
        d = state.to_dict()
        assert d["agent"] == "my-agent"

    def test_to_dict_includes_tools_when_set(self) -> None:
        """to_dict includes tools when set."""
        state = StateConfig(action="/ll:test", tools=["Bash", "Edit"], next="done")
        d = state.to_dict()
        assert d["tools"] == ["Bash", "Edit"]

    def test_to_dict_excludes_agent_when_none(self) -> None:
        """to_dict omits agent when not set."""
        state = StateConfig(action="echo hi", next="done")
        d = state.to_dict()
        assert "agent" not in d

    def test_to_dict_excludes_tools_when_none(self) -> None:
        """to_dict omits tools when not set."""
        state = StateConfig(action="echo hi", next="done")
        d = state.to_dict()
        assert "tools" not in d

    def test_from_dict_with_agent(self) -> None:
        """from_dict deserializes agent field."""
        data = {"action": "/ll:test", "agent": "some-agent", "next": "done"}
        state = StateConfig.from_dict(data)
        assert state.agent == "some-agent"

    def test_from_dict_with_tools(self) -> None:
        """from_dict deserializes tools field."""
        data = {"action": "/ll:test", "tools": ["Bash", "Edit"], "next": "done"}
        state = StateConfig.from_dict(data)
        assert state.tools == ["Bash", "Edit"]

    def test_from_dict_without_agent_defaults_none(self) -> None:
        """from_dict defaults agent to None when absent."""
        data = {"action": "echo hi", "next": "done"}
        state = StateConfig.from_dict(data)
        assert state.agent is None

    def test_from_dict_without_tools_defaults_none(self) -> None:
        """from_dict defaults tools to None when absent."""
        data = {"action": "echo hi", "next": "done"}
        state = StateConfig.from_dict(data)
        assert state.tools is None

    def test_round_trip_agent_and_tools(self) -> None:
        """StateConfig with agent and tools round-trips through to_dict/from_dict."""
        original = StateConfig(
            action="/ll:test",
            action_type="prompt",
            agent="my-agent",
            tools=["Bash", "Edit"],
            next="done",
        )
        d = original.to_dict()
        restored = StateConfig.from_dict(d)
        assert restored.agent == "my-agent"
        assert restored.tools == ["Bash", "Edit"]


class TestModelStateConfig:
    """Tests for model: FSM state field (ENH-2073)."""

    def test_state_config_model_defaults_to_none(self) -> None:
        """StateConfig.model defaults to None."""
        state = StateConfig(action="echo hi", next="done")
        assert state.model is None

    def test_state_config_accepts_model(self) -> None:
        """StateConfig accepts model field."""
        state = StateConfig(
            action="/ll:test", action_type="prompt", model="claude-haiku-4-5-20251001", next="done"
        )
        assert state.model == "claude-haiku-4-5-20251001"

    def test_to_dict_includes_model_when_set(self) -> None:
        """to_dict includes model when set."""
        state = StateConfig(action="/ll:test", model="claude-haiku-4-5-20251001", next="done")
        d = state.to_dict()
        assert d["model"] == "claude-haiku-4-5-20251001"

    def test_to_dict_excludes_model_when_none(self) -> None:
        """to_dict omits model when not set."""
        state = StateConfig(action="echo hi", next="done")
        d = state.to_dict()
        assert "model" not in d

    def test_from_dict_with_model(self) -> None:
        """from_dict deserializes model field."""
        data = {"action": "/ll:test", "model": "claude-opus-4-8", "next": "done"}
        state = StateConfig.from_dict(data)
        assert state.model == "claude-opus-4-8"

    def test_from_dict_without_model_defaults_none(self) -> None:
        """from_dict defaults model to None when absent."""
        data = {"action": "echo hi", "next": "done"}
        state = StateConfig.from_dict(data)
        assert state.model is None

    def test_round_trip_model(self) -> None:
        """StateConfig with model round-trips through to_dict/from_dict."""
        original = StateConfig(
            action="/ll:test",
            action_type="prompt",
            model="claude-haiku-4-5-20251001",
            next="done",
        )
        d = original.to_dict()
        restored = StateConfig.from_dict(d)
        assert restored.model == "claude-haiku-4-5-20251001"


class TestParameterSpec:
    """Tests for the ParameterSpec dataclass."""

    def test_minimal_from_dict(self) -> None:
        """ParameterSpec.from_dict parses required 'type' field."""
        spec = ParameterSpec.from_dict({"type": "string"})
        assert spec.type == "string"
        assert spec.required is False
        assert spec.default is None
        assert spec.description is None
        assert spec.values is None

    def test_full_from_dict(self) -> None:
        """ParameterSpec.from_dict parses all fields."""
        spec = ParameterSpec.from_dict(
            {
                "type": "enum",
                "required": True,
                "default": None,
                "description": "Mode selector",
                "values": ["fast", "slow"],
            }
        )
        assert spec.type == "enum"
        assert spec.required is True
        assert spec.description == "Mode selector"
        assert spec.values == ["fast", "slow"]

    def test_to_dict_minimal(self) -> None:
        """to_dict omits optional fields at their defaults."""
        spec = ParameterSpec(type="integer")
        d = spec.to_dict()
        assert d == {"type": "integer"}
        assert "required" not in d
        assert "default" not in d
        assert "description" not in d
        assert "values" not in d

    def test_to_dict_full(self) -> None:
        """to_dict includes all non-default fields."""
        spec = ParameterSpec(
            type="enum",
            required=True,
            description="A choice",
            values=["a", "b"],
        )
        d = spec.to_dict()
        assert d["type"] == "enum"
        assert d["required"] is True
        assert d["description"] == "A choice"
        assert d["values"] == ["a", "b"]

    def test_round_trip_all_types(self) -> None:
        """All v1 parameter types survive from_dict/to_dict round-trip."""
        for ptype in ["string", "integer", "number", "boolean", "enum", "path"]:
            original = ParameterSpec(type=ptype)
            restored = ParameterSpec.from_dict(original.to_dict())
            assert restored.type == ptype

    def test_round_trip_with_default(self) -> None:
        """ParameterSpec with default value round-trips correctly."""
        original = ParameterSpec(type="boolean", default=False, description="Enable strict mode")
        restored = ParameterSpec.from_dict(original.to_dict())
        assert restored.type == "boolean"
        assert restored.default is False
        assert restored.description == "Enable strict mode"


class TestFSMLoopParameters:
    """Tests for FSMLoop.parameters field."""

    def test_parameters_defaults_to_empty(self) -> None:
        """FSMLoop.parameters defaults to empty dict."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert fsm.parameters == {}

    def test_to_dict_omits_empty_parameters(self) -> None:
        """to_dict does not include 'parameters' key when empty."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert "parameters" not in fsm.to_dict()

    def test_to_dict_includes_parameters(self) -> None:
        """to_dict serializes parameters block."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            parameters={
                "pr_number": ParameterSpec(type="integer", required=True),
                "branch": ParameterSpec(type="string", default="main"),
            },
        )
        d = fsm.to_dict()
        assert "parameters" in d
        assert d["parameters"]["pr_number"] == {"type": "integer", "required": True}
        assert d["parameters"]["branch"] == {"type": "string", "default": "main"}

    def test_from_dict_parses_parameters(self) -> None:
        """from_dict deserializes parameters block into ParameterSpec instances."""
        data = {
            "name": "test",
            "initial": "start",
            "states": {"start": {"terminal": True}},
            "parameters": {
                "issue_id": {"type": "string", "required": True},
                "strict": {"type": "boolean", "default": False},
            },
        }
        fsm = FSMLoop.from_dict(data)
        assert "issue_id" in fsm.parameters
        assert fsm.parameters["issue_id"].type == "string"
        assert fsm.parameters["issue_id"].required is True
        assert "strict" in fsm.parameters
        assert fsm.parameters["strict"].default is False

    def test_round_trip_parameters(self) -> None:
        """FSMLoop with parameters block round-trips through to_dict/from_dict."""
        original = FSMLoop(
            name="my-loop",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            parameters={
                "target": ParameterSpec(
                    type="string", required=True, description="Target identifier"
                ),
                "mode": ParameterSpec(type="enum", values=["fast", "slow"], default="fast"),
            },
        )
        d = original.to_dict()
        restored = FSMLoop.from_dict(d)
        assert restored.parameters["target"].type == "string"
        assert restored.parameters["target"].required is True
        assert restored.parameters["mode"].values == ["fast", "slow"]


class TestFSMLoopCommands:
    """Tests for FSMLoop.commands field (ENH-1367)."""

    def test_commands_defaults_to_empty(self) -> None:
        """FSMLoop.commands defaults to empty list."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert fsm.commands == []

    def test_to_dict_omits_empty_commands(self) -> None:
        """to_dict does not include 'commands' key when empty."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert "commands" not in fsm.to_dict()

    def test_to_dict_includes_commands(self) -> None:
        """to_dict serializes commands block when non-empty."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            commands=[
                CommandEntry(cmd="ll-loop run test --param x=1", comment="run with x"),
                CommandEntry(cmd="ll-loop test test --param x=1", comment="single test"),
            ],
        )
        d = fsm.to_dict()
        assert "commands" in d
        assert d["commands"] == [
            {"cmd": "ll-loop run test --param x=1", "comment": "run with x"},
            {"cmd": "ll-loop test test --param x=1", "comment": "single test"},
        ]

    def test_from_dict_parses_commands(self) -> None:
        """from_dict deserializes commands block into CommandEntry instances."""
        data = {
            "name": "test",
            "initial": "start",
            "states": {"start": {"terminal": True}},
            "commands": [
                {"cmd": "ll-loop run test --param issue_id=ENH-1367", "comment": "run"},
                {"cmd": "ll-loop test test --param issue_id=ENH-1367", "comment": "single test"},
            ],
        }
        fsm = FSMLoop.from_dict(data)
        assert len(fsm.commands) == 2
        assert isinstance(fsm.commands[0], CommandEntry)
        assert fsm.commands[0].cmd == "ll-loop run test --param issue_id=ENH-1367"
        assert fsm.commands[0].comment == "run"
        assert fsm.commands[1].comment == "single test"

    def test_round_trip_commands(self) -> None:
        """FSMLoop with commands block round-trips through to_dict/from_dict."""
        original = FSMLoop(
            name="my-loop",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            commands=[
                CommandEntry(
                    cmd="ll-loop run my-loop --param issue_id=P3-ENH-1367",
                    comment="run (replace issue_id with your issue)",
                ),
            ],
        )
        restored = FSMLoop.from_dict(original.to_dict())
        assert len(restored.commands) == 1
        assert restored.commands[0].cmd == original.commands[0].cmd
        assert restored.commands[0].comment == original.commands[0].comment


class TestStateConfigWith:
    """Tests for StateConfig.with_ field (YAML key: 'with')."""

    def test_with_defaults_to_empty(self) -> None:
        """StateConfig.with_ defaults to empty dict."""
        state = StateConfig(loop="child", on_yes="done")
        assert state.with_ == {}

    def test_to_dict_omits_empty_with(self) -> None:
        """to_dict does not include 'with' when with_ is empty."""
        state = StateConfig(loop="child", on_yes="done")
        assert "with" not in state.to_dict()

    def test_to_dict_includes_with(self) -> None:
        """to_dict serializes with_ as 'with' key."""
        state = StateConfig(
            loop="child",
            with_={"pr_number": "${context.target_pr}", "branch": "main"},
            on_yes="done",
        )
        d = state.to_dict()
        assert "with" in d
        assert d["with"]["pr_number"] == "${context.target_pr}"
        assert d["with"]["branch"] == "main"

    def test_from_dict_parses_with(self) -> None:
        """from_dict reads 'with' key into with_ field."""
        data = {
            "loop": "child",
            "with": {"issue_id": "${captured.input.output}"},
            "on_yes": "done",
        }
        state = StateConfig.from_dict(data)
        assert state.with_ == {"issue_id": "${captured.input.output}"}

    def test_from_dict_without_with_defaults_empty(self) -> None:
        """from_dict defaults with_ to empty dict when 'with' is absent."""
        data = {"loop": "child", "on_yes": "done"}
        state = StateConfig.from_dict(data)
        assert state.with_ == {}

    def test_round_trip_with_bindings(self) -> None:
        """StateConfig with with_ round-trips through to_dict/from_dict."""
        original = StateConfig(
            loop="analyze-pr-review",
            with_={"pr_number": "${context.target_pr}", "branch": "main"},
            on_yes="done",
            on_no="failed",
        )
        d = original.to_dict()
        restored = StateConfig.from_dict(d)
        assert restored.loop == "analyze-pr-review"
        assert restored.with_["pr_number"] == "${context.target_pr}"
        assert restored.with_["branch"] == "main"


class TestPromptSizeGuardConfig:
    """Tests for PromptSizeGuardConfig dataclass (ENH-2486)."""

    def test_defaults(self) -> None:
        cfg = PromptSizeGuardConfig()
        assert cfg.enabled is True
        assert cfg.warn_chars == 50_000

    def test_from_dict_all_fields(self) -> None:
        cfg = PromptSizeGuardConfig.from_dict({"enabled": False, "warn_chars": 1234})
        assert cfg.enabled is False
        assert cfg.warn_chars == 1234

    def test_from_dict_partial_fields(self) -> None:
        cfg = PromptSizeGuardConfig.from_dict({"warn_chars": 999})
        assert cfg.enabled is True
        assert cfg.warn_chars == 999

    def test_from_dict_empty(self) -> None:
        cfg = PromptSizeGuardConfig.from_dict({})
        assert cfg.enabled is True
        assert cfg.warn_chars == 50_000

    def test_from_dict_coerces_warn_chars_to_int(self) -> None:
        cfg = PromptSizeGuardConfig.from_dict({"warn_chars": "2048"})
        assert cfg.warn_chars == 2048

    def test_to_dict_omits_defaults(self) -> None:
        assert PromptSizeGuardConfig().to_dict() == {}

    def test_to_dict_includes_non_defaults(self) -> None:
        d = PromptSizeGuardConfig(enabled=False, warn_chars=100).to_dict()
        assert d == {"enabled": False, "warn_chars": 100}

    def test_round_trip(self) -> None:
        original = PromptSizeGuardConfig(enabled=False, warn_chars=7777)
        restored = PromptSizeGuardConfig.from_dict(original.to_dict())
        assert restored.enabled is False
        assert restored.warn_chars == 7777

    def test_fsmloop_default_omits_key(self) -> None:
        loop = FSMLoop(
            name="t",
            initial="s",
            states={"s": StateConfig(action="echo hi", terminal=True)},
        )
        assert "prompt_size_guard" not in loop.to_dict()

    def test_fsmloop_scoped_round_trip(self) -> None:
        loop = FSMLoop(
            name="t",
            initial="s",
            states={"s": StateConfig(action="echo hi", terminal=True)},
            prompt_size_guard=PromptSizeGuardConfig(warn_chars=321),
        )
        data = loop.to_dict()
        assert data["prompt_size_guard"] == {"warn_chars": 321}
        restored = FSMLoop.from_dict(data)
        assert restored.prompt_size_guard.warn_chars == 321
        assert restored.prompt_size_guard.enabled is True


class TestThrottleConfig:
    """Tests for ThrottleConfig dataclass (ENH-1115)."""

    def test_from_dict_all_fields(self) -> None:
        data = {"normal_max": 2, "warn_max": 5, "hard_max": 10}
        cfg = ThrottleConfig.from_dict(data)
        assert cfg.normal_max == 2
        assert cfg.warn_max == 5
        assert cfg.hard_max == 10

    def test_from_dict_partial_fields(self) -> None:
        cfg = ThrottleConfig.from_dict({"warn_max": 6})
        assert cfg.normal_max is None
        assert cfg.warn_max == 6
        assert cfg.hard_max is None

    def test_from_dict_empty(self) -> None:
        cfg = ThrottleConfig.from_dict({})
        assert cfg.normal_max is None
        assert cfg.warn_max is None
        assert cfg.hard_max is None

    def test_to_dict_omits_none(self) -> None:
        cfg = ThrottleConfig(warn_max=7)
        d = cfg.to_dict()
        assert d == {"warn_max": 7}
        assert "normal_max" not in d
        assert "hard_max" not in d

    def test_round_trip(self) -> None:
        original = ThrottleConfig(normal_max=3, warn_max=8, hard_max=12)
        restored = ThrottleConfig.from_dict(original.to_dict())
        assert restored.normal_max == 3
        assert restored.warn_max == 8
        assert restored.hard_max == 12

    def test_state_config_throttle_field(self) -> None:
        state = StateConfig.from_dict(
            {
                "action": "work.sh",
                "throttle": {"normal_max": 3, "warn_max": 8, "hard_max": 12},
                "on_throttle_hard": "slow-state",
                "on_yes": "done",
            }
        )
        assert state.throttle is not None
        assert state.throttle.normal_max == 3
        assert state.throttle.warn_max == 8
        assert state.throttle.hard_max == 12
        assert state.on_throttle_hard == "slow-state"

    def test_state_config_no_throttle_defaults_none(self) -> None:
        state = StateConfig.from_dict({"action": "work.sh", "on_yes": "done"})
        assert state.throttle is None
        assert state.on_throttle_hard is None

    def test_on_throttle_hard_in_known_on_keys(self) -> None:
        """on_throttle_hard must NOT appear in extra_routes."""
        state = StateConfig.from_dict(
            {"action": "work.sh", "on_throttle_hard": "fallback", "on_yes": "done"}
        )
        assert state.on_throttle_hard == "fallback"
        assert "throttle_hard" not in state.extra_routes

    def test_state_config_throttle_round_trip(self) -> None:
        original = StateConfig(
            action="work.sh",
            throttle=ThrottleConfig(normal_max=2, warn_max=5, hard_max=8),
            on_throttle_hard="slow",
            on_yes="done",
        )
        d = original.to_dict()
        restored = StateConfig.from_dict(d)
        assert restored.throttle is not None
        assert restored.throttle.normal_max == 2
        assert restored.throttle.warn_max == 5
        assert restored.throttle.hard_max == 8
        assert restored.on_throttle_hard == "slow"

    def test_on_throttle_hard_in_get_referenced_states(self) -> None:
        state = StateConfig(
            action="work.sh",
            on_throttle_hard="batch-state",
            on_yes="done",
        )
        refs = state.get_referenced_states()
        assert "batch-state" in refs

    def test_state_type_field(self) -> None:
        state = StateConfig.from_dict({"action": "work.sh", "type": "learning", "on_yes": "done"})
        assert state.type == "learning"

    def test_state_config_learning_round_trip(self) -> None:
        """FEAT-1283: StateConfig round-trips LearningConfig via to_dict/from_dict."""
        original = StateConfig(
            type="learning",
            learning=LearningConfig(
                targets=["Anthropic SDK streaming", "GitHub API rate limits"],
                max_retries=3,
            ),
            on_yes="planning",
            on_no="blocked",
        )
        d = original.to_dict()
        assert d["type"] == "learning"
        assert d["learning"] == {
            "targets": ["Anthropic SDK streaming", "GitHub API rate limits"],
            "max_retries": 3,
        }
        restored = StateConfig.from_dict(d)
        assert restored.type == "learning"
        assert restored.learning is not None
        assert restored.learning.targets == [
            "Anthropic SDK streaming",
            "GitHub API rate limits",
        ]
        assert restored.learning.max_retries == 3

    def test_state_config_learning_default_max_retries(self) -> None:
        state = StateConfig.from_dict(
            {
                "type": "learning",
                "learning": {"targets": ["x"]},
                "on_yes": "planning",
                "on_no": "blocked",
            }
        )
        assert state.learning is not None
        assert state.learning.max_retries == 2

    def test_state_config_learning_targets_csv_round_trip(self) -> None:
        """ENH-1741: targets_csv survives StateConfig.from_dict/to_dict round-trip."""
        original = StateConfig.from_dict(
            {
                "type": "learning",
                "learning": {"targets_csv": "${context.targets}"},
                "on_yes": "done",
                "on_blocked": "blocked",
            }
        )
        assert original.learning is not None
        assert original.learning.targets_csv == "${context.targets}"
        assert original.learning.targets == []
        d = original.to_dict()
        assert d["learning"]["targets_csv"] == "${context.targets}"
        restored = StateConfig.from_dict(d)
        assert restored.learning is not None
        assert restored.learning.targets_csv == "${context.targets}"

    def test_state_config_learning_max_retries_expr_round_trip(self) -> None:
        """ENH-1741: max_retries_expr survives StateConfig.from_dict/to_dict round-trip."""
        original = StateConfig.from_dict(
            {
                "type": "learning",
                "learning": {
                    "targets_csv": "${context.targets}",
                    "max_retries_expr": "${context.max_retries}",
                },
                "on_yes": "done",
                "on_blocked": "blocked",
            }
        )
        assert original.learning is not None
        assert original.learning.targets_csv == "${context.targets}"
        assert original.learning.max_retries_expr == "${context.max_retries}"
        d = original.to_dict()
        assert d["learning"]["max_retries_expr"] == "${context.max_retries}"
        restored = StateConfig.from_dict(d)
        assert restored.learning is not None
        assert restored.learning.max_retries_expr == "${context.max_retries}"


class TestTargetStateSpec:
    """ENH-1552: TargetStateSpec dataclass round-trip and defaults."""

    def test_from_dict_round_trip(self) -> None:
        original = TargetStateSpec(
            name="optimize",
            examples_file="examples/optimize.yaml",
            eval_fragment="eval-fragment-id",
        )
        restored = TargetStateSpec.from_dict(original.to_dict())
        assert restored.name == "optimize"
        assert restored.examples_file == "examples/optimize.yaml"
        assert restored.eval_fragment == "eval-fragment-id"

    def test_from_dict_fields(self) -> None:
        spec = TargetStateSpec.from_dict({"name": "s1", "examples_file": "e.yaml", "eval": "frag"})
        assert spec.name == "s1"
        assert spec.examples_file == "e.yaml"
        assert spec.eval_fragment == "frag"

    def test_to_dict_uses_eval_key(self) -> None:
        spec = TargetStateSpec(name="s", examples_file="e.yaml", eval_fragment="f")
        d = spec.to_dict()
        assert d["eval"] == "f"
        assert "eval_fragment" not in d


class TestTargetFileSpec:
    """ENH-1552: TargetFileSpec dataclass round-trip and defaults."""

    def test_from_dict_round_trip(self) -> None:
        original = TargetFileSpec(
            file="loops/my-loop.yaml",
            states=[TargetStateSpec(name="s1", examples_file="e.yaml", eval_fragment="f1")],
        )
        restored = TargetFileSpec.from_dict(original.to_dict())
        assert restored.file == "loops/my-loop.yaml"
        assert restored.glob is None
        assert len(restored.states) == 1
        assert restored.states[0].name == "s1"
        assert restored.states[0].eval_fragment == "f1"

    def test_from_dict_empty(self) -> None:
        spec = TargetFileSpec.from_dict({})
        assert spec.file is None
        assert spec.glob is None
        assert spec.states == []

    def test_from_dict_glob(self) -> None:
        spec = TargetFileSpec.from_dict({"glob": "loops/*.yaml"})
        assert spec.glob == "loops/*.yaml"
        assert spec.file is None

    def test_to_dict_omits_none(self) -> None:
        spec = TargetFileSpec(file="f.yaml")
        d = spec.to_dict()
        assert d == {"file": "f.yaml"}
        assert "glob" not in d
        assert "states" not in d

    def test_from_dict_with_states(self) -> None:
        spec = TargetFileSpec.from_dict(
            {
                "file": "loop.yaml",
                "states": [{"name": "n", "examples_file": "e.yaml", "eval": "frag"}],
            }
        )
        assert len(spec.states) == 1
        assert spec.states[0].name == "n"


class TestFSMLoopTargetsField:
    """ENH-1552: FSMLoop.targets field parsing and defaults."""

    def _make_minimal(self) -> dict:
        return {
            "name": "t",
            "description": "test",
            "initial": "s",
            "states": {"s": {"terminal": True}},
        }

    def test_from_dict_with_targets_populates_list(self) -> None:
        data = self._make_minimal()
        data["targets"] = [
            {
                "file": "loops/harness-optimize.yaml",
                "states": [{"name": "optimize", "examples_file": "e.yaml", "eval": "frag"}],
            }
        ]
        fsm = FSMLoop.from_dict(data)
        assert len(fsm.targets) == 1
        assert fsm.targets[0].file == "loops/harness-optimize.yaml"
        assert len(fsm.targets[0].states) == 1
        assert fsm.targets[0].states[0].name == "optimize"

    def test_from_dict_without_targets_defaults_to_empty(self) -> None:
        fsm = FSMLoop.from_dict(self._make_minimal())
        assert fsm.targets == []

    def test_to_dict_emits_targets_when_non_empty(self) -> None:
        data = self._make_minimal()
        data["targets"] = [
            {"file": "loop.yaml", "states": [{"name": "s", "examples_file": "e.yaml", "eval": "f"}]}
        ]
        fsm = FSMLoop.from_dict(data)
        d = fsm.to_dict()
        assert "targets" in d
        assert d["targets"][0]["file"] == "loop.yaml"

    def test_to_dict_omits_targets_when_empty(self) -> None:
        fsm = FSMLoop.from_dict(self._make_minimal())
        d = fsm.to_dict()
        assert "targets" not in d

    def test_targets_key_no_warning(self, tmp_path: Path) -> None:
        """A YAML with top-level 'targets:' produces no unknown-key warning (ENH-1552)."""
        loop_yaml = tmp_path / "targets-key.yaml"
        loop_yaml.write_text(
            "name: test-loop\n"
            "description: A loop with targets\n"
            "initial: check\n"
            "states:\n"
            "  check:\n"
            "    terminal: true\n"
            "targets:\n"
            "  - file: loops/harness-optimize.yaml\n"
            "    states:\n"
            "      - name: optimize\n"
            "        examples_file: e.yaml\n"
            "        eval: frag\n"
        )
        _, warnings = load_and_validate(loop_yaml)
        unknown_warnings = [w for w in warnings if "Unknown top-level" in w.message]
        assert unknown_warnings == []


class TestCostCeilingConfig:
    """Tests for CostCeilingConfig dataclass (ENH-2477)."""

    def test_defaults(self) -> None:
        cfg = CostCeilingConfig()
        assert cfg.cost_ceiling_per_state is None
        assert cfg.cost_warn_at is None

    def test_from_dict_all_fields(self) -> None:
        cfg = CostCeilingConfig.from_dict({"cost_ceiling_per_state": 1.5, "cost_warn_at": 0.75})
        assert cfg.cost_ceiling_per_state == 1.5
        assert cfg.cost_warn_at == 0.75

    def test_from_dict_partial_fields(self) -> None:
        cfg = CostCeilingConfig.from_dict({"cost_warn_at": 0.5})
        assert cfg.cost_ceiling_per_state is None
        assert cfg.cost_warn_at == 0.5

    def test_from_dict_empty(self) -> None:
        cfg = CostCeilingConfig.from_dict({})
        assert cfg.cost_ceiling_per_state is None
        assert cfg.cost_warn_at is None

    def test_to_dict_omits_none(self) -> None:
        assert CostCeilingConfig().to_dict() == {}

    def test_to_dict_includes_non_none(self) -> None:
        d = CostCeilingConfig(cost_ceiling_per_state=2.0).to_dict()
        assert d == {"cost_ceiling_per_state": 2.0}

    def test_round_trip(self) -> None:
        original = CostCeilingConfig(cost_ceiling_per_state=3.0, cost_warn_at=1.0)
        restored = CostCeilingConfig.from_dict(original.to_dict())
        assert restored.cost_ceiling_per_state == 3.0
        assert restored.cost_warn_at == 1.0

    def test_state_config_omits_when_unset(self) -> None:
        state = StateConfig.from_dict({"action": "work.sh", "on_yes": "done"})
        assert state.cost_ceiling is None

    def test_state_config_round_trip(self) -> None:
        state = StateConfig.from_dict(
            {
                "action": "work.sh",
                "on_yes": "done",
                "cost_ceiling": {"cost_ceiling_per_state": 2.5, "cost_warn_at": 1.0},
            }
        )
        assert state.cost_ceiling is not None
        assert state.cost_ceiling.cost_ceiling_per_state == 2.5
        assert state.cost_ceiling.cost_warn_at == 1.0
        # Round-trip through to_dict/from_dict.
        restored = StateConfig.from_dict(state.to_dict())
        assert restored.cost_ceiling is not None
        assert restored.cost_ceiling.cost_ceiling_per_state == 2.5
        assert restored.cost_ceiling.cost_warn_at == 1.0


class TestCircuitConfig:
    """FEAT-1637: CircuitConfig + RepeatedFailureConfig round-trip serialization."""

    def test_circuit_repeated_failure_round_trip(self) -> None:
        original = CircuitConfig(
            repeated_failure=RepeatedFailureConfig(window=5, on_repeated_failure="recover")
        )
        restored = CircuitConfig.from_dict(original.to_dict())
        assert restored.repeated_failure is not None
        assert restored.repeated_failure.window == 5
        assert restored.repeated_failure.on_repeated_failure == "recover"

    def test_repeated_failure_defaults_round_trip(self) -> None:
        original = RepeatedFailureConfig()
        restored = RepeatedFailureConfig.from_dict(original.to_dict())
        assert restored.window == 3
        assert restored.on_repeated_failure == "abort"

    def test_circuit_to_dict_omits_repeated_failure_when_none(self) -> None:
        assert CircuitConfig().to_dict() == {}

    def test_fsm_loop_with_circuit_round_trip(self) -> None:
        original = FSMLoop(
            name="t",
            description="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            circuit=CircuitConfig(
                repeated_failure=RepeatedFailureConfig(window=4, on_repeated_failure="bail")
            ),
        )
        d = original.to_dict()
        assert d["circuit"]["repeated_failure"] == {
            "window": 4,
            "on_repeated_failure": "bail",
        }
        restored = FSMLoop.from_dict(d)
        assert restored.circuit is not None
        assert restored.circuit.repeated_failure is not None
        assert restored.circuit.repeated_failure.window == 4
        assert restored.circuit.repeated_failure.on_repeated_failure == "bail"

    def test_fsm_loop_without_circuit_omits_key(self) -> None:
        fsm = FSMLoop(
            name="t",
            description="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )
        d = fsm.to_dict()
        assert "circuit" not in d
        restored = FSMLoop.from_dict(d)
        assert restored.circuit is None

    def test_repeated_failure_progress_paths_round_trip(self) -> None:
        paths = ["${env.PWD}/.loops/tmp/plan.md", "${env.PWD}/.loops/tmp/dod.md"]
        original = RepeatedFailureConfig(
            window=3, on_repeated_failure="diagnose", progress_paths=paths
        )
        d = original.to_dict()
        assert d["progress_paths"] == paths
        restored = RepeatedFailureConfig.from_dict(d)
        assert restored.progress_paths == paths
        assert restored.window == 3
        assert restored.on_repeated_failure == "diagnose"

    def test_repeated_failure_empty_progress_paths_omitted_from_dict(self) -> None:
        original = RepeatedFailureConfig()
        d = original.to_dict()
        assert "progress_paths" not in d

    def test_repeated_failure_defaults_include_empty_progress_paths(self) -> None:
        restored = RepeatedFailureConfig.from_dict({})
        assert restored.progress_paths == []

    def test_repeated_failure_exclude_paths_round_trip(self) -> None:
        """BUG-1767: exclude_paths serializes and deserializes correctly."""
        excl = ["${env.PWD}/.loops/tmp/plan.md", "${env.PWD}/.loops/tmp/dod.md"]
        original = RepeatedFailureConfig(
            window=3,
            on_repeated_failure="diagnose",
            exclude_paths=excl,
        )
        d = original.to_dict()
        assert d["exclude_paths"] == excl
        restored = RepeatedFailureConfig.from_dict(d)
        assert restored.exclude_paths == excl
        assert restored.progress_paths == []

    def test_repeated_failure_empty_exclude_paths_omitted_from_dict(self) -> None:
        """exclude_paths is omitted from to_dict() when empty (skip-if-default)."""
        original = RepeatedFailureConfig()
        d = original.to_dict()
        assert "exclude_paths" not in d

    def test_repeated_failure_defaults_include_empty_exclude_paths(self) -> None:
        restored = RepeatedFailureConfig.from_dict({})
        assert restored.exclude_paths == []

    # --- recurrent_window tests (ENH-2245) ---

    def test_recurrent_window_round_trip(self) -> None:
        """ENH-2245: recurrent_window serializes and deserializes correctly."""
        original = RepeatedFailureConfig(window=3, on_repeated_failure="abort", recurrent_window=5)
        d = original.to_dict()
        assert d["recurrent_window"] == 5
        restored = RepeatedFailureConfig.from_dict(d)
        assert restored.recurrent_window == 5

    def test_recurrent_window_none_omitted_from_dict(self) -> None:
        """recurrent_window=None (default) is omitted from to_dict()."""
        original = RepeatedFailureConfig()
        d = original.to_dict()
        assert "recurrent_window" not in d

    def test_recurrent_window_default_is_none(self) -> None:
        """Default recurrent_window is None (disabled)."""
        restored = RepeatedFailureConfig.from_dict({})
        assert restored.recurrent_window is None


class TestMetaSelfEvalOk:
    """ENH-1665: meta_self_eval_ok field round-trip serialization."""

    def test_meta_self_eval_ok_true_round_trips(self) -> None:
        """meta_self_eval_ok=True is present in to_dict() and restored by from_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            meta_self_eval_ok=True,
        )
        d = fsm.to_dict()
        assert d.get("meta_self_eval_ok") is True
        restored = FSMLoop.from_dict(d)
        assert restored.meta_self_eval_ok is True

    def test_meta_self_eval_ok_false_omitted_from_dict(self) -> None:
        """meta_self_eval_ok=False (default) is omitted from to_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )
        d = fsm.to_dict()
        assert "meta_self_eval_ok" not in d

    def test_meta_self_eval_ok_defaults_false(self) -> None:
        """FSMLoop.from_dict() without meta_self_eval_ok defaults to False."""
        fsm = FSMLoop.from_dict(
            {
                "name": "test",
                "initial": "s",
                "states": {"s": {"terminal": True}},
            }
        )
        assert fsm.meta_self_eval_ok is False


class TestSharedStateOk:
    """MR-3: shared_state_ok field round-trip serialization."""

    def test_shared_state_ok_true_round_trips(self) -> None:
        """shared_state_ok=True is present in to_dict() and restored by from_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            shared_state_ok=True,
        )
        d = fsm.to_dict()
        assert d.get("shared_state_ok") is True
        restored = FSMLoop.from_dict(d)
        assert restored.shared_state_ok is True

    def test_shared_state_ok_false_omitted_from_dict(self) -> None:
        """shared_state_ok=False (default) is omitted from to_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )
        d = fsm.to_dict()
        assert "shared_state_ok" not in d

    def test_shared_state_ok_defaults_false(self) -> None:
        """FSMLoop.from_dict() without shared_state_ok defaults to False."""
        fsm = FSMLoop.from_dict(
            {
                "name": "test",
                "initial": "s",
                "states": {"s": {"terminal": True}},
            }
        )
        assert fsm.shared_state_ok is False


class TestPartialRouteOk:
    """MR-4 (ENH-1917): partial_route_ok field round-trip serialization."""

    def test_partial_route_ok_true_round_trips(self) -> None:
        """partial_route_ok=True is present in to_dict() and restored by from_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            partial_route_ok=True,
        )
        d = fsm.to_dict()
        assert d.get("partial_route_ok") is True
        restored = FSMLoop.from_dict(d)
        assert restored.partial_route_ok is True

    def test_partial_route_ok_false_omitted_from_dict(self) -> None:
        """partial_route_ok=False (default) is omitted from to_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )
        d = fsm.to_dict()
        assert "partial_route_ok" not in d

    def test_partial_route_ok_defaults_false(self) -> None:
        """FSMLoop.from_dict() without partial_route_ok defaults to False."""
        fsm = FSMLoop.from_dict(
            {
                "name": "test",
                "initial": "s",
                "states": {"s": {"terminal": True}},
            }
        )
        assert fsm.partial_route_ok is False


class TestContractSchema:
    """Tests for contract evaluator type in EvaluateConfig schema."""

    def test_contract_type_is_valid(self) -> None:
        """EvaluateConfig accepts type='contract'."""
        config = EvaluateConfig(
            type="contract",
            pairs=[{"producer": "api.ts", "consumer": "hook.ts", "contract": "must match"}],
        )
        assert config.type == "contract"
        assert config.pairs == [
            {"producer": "api.ts", "consumer": "hook.ts", "contract": "must match"}
        ]

    def test_contract_round_trips_through_dict(self) -> None:
        """contract evaluator serializes and deserializes pairs correctly."""
        config = EvaluateConfig(
            type="contract",
            pairs=[
                {
                    "producer": "src/api/route.ts",
                    "producer_pattern": "NextResponse\\.json\\((.+?)\\)",
                    "consumer": "src/hooks/useProjects.ts",
                    "consumer_pattern": "fetchJson<(.+?)>",
                    "contract": "shape and field names must align",
                }
            ],
        )
        d = config.to_dict()
        assert d["type"] == "contract"
        assert d["pairs"] == config.pairs

        restored = EvaluateConfig.from_dict(d)
        assert restored.type == "contract"
        assert restored.pairs == config.pairs

    def test_contract_pairs_none_omitted_from_dict(self) -> None:
        """to_dict omits pairs when it is None (non-contract types)."""
        config = EvaluateConfig(type="exit_code")
        d = config.to_dict()
        assert "pairs" not in d

    def test_contract_pairs_from_dict_defaults_to_none(self) -> None:
        """from_dict sets pairs to None when key is absent."""
        config = EvaluateConfig.from_dict({"type": "exit_code"})
        assert config.pairs is None

    def test_contract_multiple_pairs_round_trip(self) -> None:
        """Multiple pairs serialize and deserialize correctly."""
        config = EvaluateConfig(
            type="contract",
            pairs=[
                {"producer": "api1.ts", "consumer": "hook1.ts", "contract": "rule 1"},
                {"producer": "api2.ts", "consumer": "hook2.ts", "contract": "rule 2"},
            ],
        )
        d = config.to_dict()
        restored = EvaluateConfig.from_dict(d)
        assert len(restored.pairs) == 2
        assert restored.pairs[0]["producer"] == "api1.ts"
        assert restored.pairs[1]["contract"] == "rule 2"


class TestFSMLoopRequiredInputs:
    """Tests for FSMLoop.required_inputs field (ENH-1898)."""

    def test_defaults_to_empty(self) -> None:
        """FSMLoop.required_inputs defaults to empty list."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert fsm.required_inputs == []

    def test_to_dict_omits_when_empty(self) -> None:
        """to_dict does not include 'required_inputs' key when empty."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert "required_inputs" not in fsm.to_dict()

    def test_to_dict_includes_when_set(self) -> None:
        """to_dict serializes required_inputs when non-empty."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            required_inputs=["description"],
        )
        d = fsm.to_dict()
        assert "required_inputs" in d
        assert d["required_inputs"] == ["description"]

    def test_from_dict_parses(self) -> None:
        """from_dict deserializes required_inputs list."""
        data = {
            "name": "test",
            "initial": "start",
            "states": {"start": {"terminal": True}},
            "required_inputs": ["description", "topic"],
        }
        fsm = FSMLoop.from_dict(data)
        assert fsm.required_inputs == ["description", "topic"]

    def test_round_trip(self) -> None:
        """FSMLoop with required_inputs round-trips through to_dict/from_dict."""
        original = FSMLoop(
            name="my-loop",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            required_inputs=["description"],
        )
        restored = FSMLoop.from_dict(original.to_dict())
        assert restored.required_inputs == ["description"]


class TestFSMLoopArtifactVersioning:
    """Tests for FSMLoop.artifact_versioning and artifact_versioning_ok fields (ENH-1957)."""

    def test_artifact_versioning_defaults_to_false(self) -> None:
        """FSMLoop.artifact_versioning defaults to False."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert fsm.artifact_versioning is False

    def test_artifact_versioning_ok_defaults_to_false(self) -> None:
        """FSMLoop.artifact_versioning_ok defaults to False."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert fsm.artifact_versioning_ok is False

    def test_to_dict_omits_artifact_versioning_when_false(self) -> None:
        """to_dict does not include 'artifact_versioning' key when False."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert "artifact_versioning" not in fsm.to_dict()

    def test_to_dict_omits_artifact_versioning_ok_when_false(self) -> None:
        """to_dict does not include 'artifact_versioning_ok' key when False."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
        )
        assert "artifact_versioning_ok" not in fsm.to_dict()

    def test_to_dict_includes_artifact_versioning_when_true(self) -> None:
        """to_dict serializes artifact_versioning when True."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            artifact_versioning=True,
        )
        d = fsm.to_dict()
        assert "artifact_versioning" in d
        assert d["artifact_versioning"] is True

    def test_to_dict_includes_artifact_versioning_ok_when_true(self) -> None:
        """to_dict serializes artifact_versioning_ok when True."""
        fsm = FSMLoop(
            name="test",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            artifact_versioning_ok=True,
        )
        d = fsm.to_dict()
        assert "artifact_versioning_ok" in d
        assert d["artifact_versioning_ok"] is True

    def test_from_dict_parses_artifact_versioning(self) -> None:
        """from_dict deserializes artifact_versioning boolean."""
        data = {
            "name": "test",
            "initial": "start",
            "states": {"start": {"terminal": True}},
            "artifact_versioning": True,
        }
        fsm = FSMLoop.from_dict(data)
        assert fsm.artifact_versioning is True

    def test_from_dict_parses_artifact_versioning_ok(self) -> None:
        """from_dict deserializes artifact_versioning_ok boolean."""
        data = {
            "name": "test",
            "initial": "start",
            "states": {"start": {"terminal": True}},
            "artifact_versioning_ok": True,
        }
        fsm = FSMLoop.from_dict(data)
        assert fsm.artifact_versioning_ok is True

    def test_from_dict_defaults_when_absent(self) -> None:
        """from_dict defaults both fields to False when absent from data."""
        data = {
            "name": "test",
            "initial": "start",
            "states": {"start": {"terminal": True}},
        }
        fsm = FSMLoop.from_dict(data)
        assert fsm.artifact_versioning is False
        assert fsm.artifact_versioning_ok is False

    def test_round_trip(self) -> None:
        """FSMLoop with both artifact versioning fields round-trips through to_dict/from_dict."""
        original = FSMLoop(
            name="my-loop",
            initial="start",
            states={"start": StateConfig(terminal=True)},
            artifact_versioning=True,
            artifact_versioning_ok=True,
        )
        restored = FSMLoop.from_dict(original.to_dict())
        assert restored.artifact_versioning is True
        assert restored.artifact_versioning_ok is True


class TestGeneratorFixOk:
    """MR-6 (ENH-2079): generator_fix_ok field round-trip serialization."""

    def test_generator_fix_ok_true_round_trips(self) -> None:
        """generator_fix_ok=True is present in to_dict() and restored by from_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            generator_fix_ok=True,
        )
        d = fsm.to_dict()
        assert d.get("generator_fix_ok") is True
        restored = FSMLoop.from_dict(d)
        assert restored.generator_fix_ok is True

    def test_generator_fix_ok_false_omitted_from_dict(self) -> None:
        """generator_fix_ok=False (default) is omitted from to_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )
        d = fsm.to_dict()
        assert "generator_fix_ok" not in d

    def test_generator_fix_ok_defaults_false(self) -> None:
        """FSMLoop.from_dict() without generator_fix_ok defaults to False."""
        fsm = FSMLoop.from_dict(
            {
                "name": "test",
                "initial": "s",
                "states": {"s": {"terminal": True}},
            }
        )
        assert fsm.generator_fix_ok is False


class TestBashDefaultOk:
    """MR-7 (ENH-2348): bash_default_ok field round-trip serialization."""

    def test_bash_default_ok_true_round_trips(self) -> None:
        """bash_default_ok=True is present in to_dict() and restored by from_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            bash_default_ok=True,
        )
        d = fsm.to_dict()
        assert d.get("bash_default_ok") is True
        restored = FSMLoop.from_dict(d)
        assert restored.bash_default_ok is True

    def test_bash_default_ok_false_omitted_from_dict(self) -> None:
        """bash_default_ok=False (default) is omitted from to_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )
        d = fsm.to_dict()
        assert "bash_default_ok" not in d

    def test_bash_default_ok_defaults_false(self) -> None:
        """FSMLoop.from_dict() without bash_default_ok defaults to False."""
        fsm = FSMLoop.from_dict(
            {
                "name": "test",
                "initial": "s",
                "states": {"s": {"terminal": True}},
            }
        )
        assert fsm.bash_default_ok is False


class TestUnsafeContextInterpolationOk:
    """MR-11 (BUG-2622): unsafe_context_interpolation_ok field round-trip serialization."""

    def test_unsafe_context_interpolation_ok_true_round_trips(self) -> None:
        """unsafe_context_interpolation_ok=True is present in to_dict() and restored by from_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            unsafe_context_interpolation_ok=True,
        )
        d = fsm.to_dict()
        assert d.get("unsafe_context_interpolation_ok") is True
        restored = FSMLoop.from_dict(d)
        assert restored.unsafe_context_interpolation_ok is True

    def test_unsafe_context_interpolation_ok_false_omitted_from_dict(self) -> None:
        """unsafe_context_interpolation_ok=False (default) is omitted from to_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )
        d = fsm.to_dict()
        assert "unsafe_context_interpolation_ok" not in d

    def test_unsafe_context_interpolation_ok_defaults_false(self) -> None:
        """FSMLoop.from_dict() without unsafe_context_interpolation_ok defaults to False."""
        fsm = FSMLoop.from_dict(
            {
                "name": "test",
                "initial": "s",
                "states": {"s": {"terminal": True}},
            }
        )
        assert fsm.unsafe_context_interpolation_ok is False


class TestSingleton:
    """BUG-2526: FSMLoop.singleton field round-trip serialization.

    Mirrors the `TestBashDefaultOk` (MR-7) and `TestMaintain` patterns: a top-level
    bool with default False, omitted from to_dict() when False, restored from
    from_dict() via data.get(). Used by autodev.yaml to declare singleton: true,
    serializing concurrent autodev runs at the lock layer.
    """

    def test_singleton_true_round_trips(self) -> None:
        """singleton=True is present in to_dict() and restored by from_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            singleton=True,
        )
        d = fsm.to_dict()
        assert d.get("singleton") is True
        restored = FSMLoop.from_dict(d)
        assert restored.singleton is True

    def test_singleton_false_omitted_from_dict(self) -> None:
        """singleton=False (default) is omitted from to_dict()."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )
        d = fsm.to_dict()
        assert "singleton" not in d, (
            f"singleton=False must be omitted from to_dict(); got keys: {sorted(d.keys())}"
        )

    def test_singleton_defaults_false(self) -> None:
        """FSMLoop.from_dict() without singleton key defaults to False."""
        fsm = FSMLoop.from_dict(
            {
                "name": "test",
                "initial": "s",
                "states": {"s": {"terminal": True}},
            }
        )
        assert fsm.singleton is False


class TestFSMLoopMaxStepsAndIterations:
    """Tests for BUG-2204: max_steps (step cap) and max_iterations (full-pass cap)."""

    def _minimal(self) -> FSMLoop:
        return FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
        )

    def test_max_steps_defaults_to_50(self) -> None:
        """FSMLoop.max_steps defaults to 50."""
        assert self._minimal().max_steps == 50

    def test_max_iterations_defaults_to_none(self) -> None:
        """FSMLoop.max_iterations (full-pass cap) defaults to None."""
        assert self._minimal().max_iterations is None

    def test_on_max_steps_defaults_to_none(self) -> None:
        """FSMLoop.on_max_steps defaults to None."""
        assert self._minimal().on_max_steps is None

    def test_max_steps_omitted_from_to_dict_when_50(self) -> None:
        """to_dict omits max_steps when it equals the default (50)."""
        assert "max_steps" not in self._minimal().to_dict()

    def test_max_steps_in_to_dict_when_not_50(self) -> None:
        """to_dict serializes max_steps when != 50."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            max_steps=10,
        )
        d = fsm.to_dict()
        assert d.get("max_steps") == 10

    def test_max_iterations_omitted_from_to_dict_when_none(self) -> None:
        """to_dict omits max_iterations when None."""
        assert "max_iterations" not in self._minimal().to_dict()

    def test_max_iterations_in_to_dict_when_set(self) -> None:
        """to_dict serializes max_iterations (iteration cap) when not None."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            max_iterations=3,
        )
        d = fsm.to_dict()
        assert d.get("max_iterations") == 3

    def test_on_max_steps_omitted_when_none(self) -> None:
        """to_dict omits on_max_steps when None."""
        assert "on_max_steps" not in self._minimal().to_dict()

    def test_on_max_steps_serialized_when_set(self) -> None:
        """to_dict serializes on_max_steps when set."""
        fsm = FSMLoop(
            name="test",
            initial="s",
            states={
                "s": StateConfig(action="run.sh", on_yes="t", on_no="s"),
                "summary": StateConfig(action="sum.sh", next="t"),
                "t": StateConfig(terminal=True),
            },
            on_max_steps="summary",
        )
        assert fsm.to_dict().get("on_max_steps") == "summary"

    def test_legacy_max_iterations_aliases_to_max_steps(self) -> None:
        """YAML max_iterations (without max_steps) reads as max_steps via from_dict alias."""
        fsm = FSMLoop.from_dict(
            {
                "name": "test",
                "initial": "s",
                "states": {"s": {"terminal": True}},
                "max_iterations": 30,
            }
        )
        assert fsm.max_steps == 30
        assert fsm.max_iterations is None

    def test_max_steps_and_max_iterations_coexist(self) -> None:
        """When both max_steps and max_iterations present, both are parsed independently."""
        fsm = FSMLoop.from_dict(
            {
                "name": "test",
                "initial": "s",
                "states": {"s": {"terminal": True}},
                "max_steps": 100,
                "max_iterations": 5,
            }
        )
        assert fsm.max_steps == 100
        assert fsm.max_iterations == 5

    def test_roundtrip_max_steps(self) -> None:
        """max_steps survives to_dict/from_dict roundtrip."""
        original = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            max_steps=20,
        )
        restored = FSMLoop.from_dict(original.to_dict())
        assert restored.max_steps == 20

    def test_roundtrip_max_iterations(self) -> None:
        """max_iterations (full-pass cap) survives to_dict/from_dict roundtrip."""
        original = FSMLoop(
            name="test",
            initial="s",
            states={"s": StateConfig(terminal=True)},
            max_steps=50,
            max_iterations=3,
        )
        restored = FSMLoop.from_dict(original.to_dict())
        assert restored.max_iterations == 3

    def test_on_max_steps_included_in_referenced_states(self) -> None:
        """get_all_referenced_states includes the on_max_steps target."""
        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(action="run.sh", on_yes="done", on_no="work"),
                "cap_summary": StateConfig(action="sum.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
            on_max_steps="cap_summary",
        )
        assert "cap_summary" in fsm.get_all_referenced_states()

    def test_on_max_iterations_included_in_referenced_states(self) -> None:
        """get_all_referenced_states includes the on_max_iterations target."""
        fsm = FSMLoop(
            name="test",
            initial="work",
            states={
                "work": StateConfig(action="run.sh", on_yes="done", on_no="work"),
                "iter_summary": StateConfig(action="isum.sh", next="done"),
                "done": StateConfig(terminal=True),
            },
            max_iterations=3,
            on_max_iterations="iter_summary",
        )
        assert "iter_summary" in fsm.get_all_referenced_states()

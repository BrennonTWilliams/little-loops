"""Unit tests for FSM variable interpolation."""

from __future__ import annotations

import os
from unittest import mock

import pytest

from little_loops.fsm.interpolation import (
    InterpolationContext,
    InterpolationError,
    _format_duration,
    interpolate,
    interpolate_dict,
)


class TestInterpolationContext:
    """Tests for InterpolationContext creation and resolution."""

    def test_default_values(self) -> None:
        """Context has sensible defaults."""
        ctx = InterpolationContext()
        assert ctx.context == {}
        assert ctx.captured == {}
        assert ctx.prev is None
        assert ctx.result is None
        assert ctx.state_name == ""
        assert ctx.iteration == 1

    def test_context_variable(self) -> None:
        """${context.target_dir} resolves from context dict."""
        ctx = InterpolationContext(context={"target_dir": "src/"})
        value = ctx.resolve("context", "target_dir")
        assert value == "src/"

    def test_context_nested(self) -> None:
        """${context.db.host} resolves nested path."""
        ctx = InterpolationContext(context={"db": {"host": "localhost", "port": 5432}})
        assert ctx.resolve("context", "db.host") == "localhost"
        assert ctx.resolve("context", "db.port") == 5432

    def test_captured_variable(self) -> None:
        """${captured.errors.output} resolves stored action result."""
        ctx = InterpolationContext(
            captured={
                "errors": {
                    "output": "3 errors found",
                    "exit_code": 1,
                    "duration_ms": 500,
                }
            }
        )
        assert ctx.resolve("captured", "errors.output") == "3 errors found"
        assert ctx.resolve("captured", "errors.exit_code") == 1

    def test_prev_shorthand(self) -> None:
        """${prev.output} resolves previous state result."""
        ctx = InterpolationContext(
            prev={"output": "previous output", "exit_code": 0, "state": "check"}
        )
        assert ctx.resolve("prev", "output") == "previous output"
        assert ctx.resolve("prev", "state") == "check"

    def test_prev_unavailable_raises(self) -> None:
        """Accessing prev when None raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="No previous state result"):
            ctx.resolve("prev", "output")

    def test_result_variable(self) -> None:
        """${result.verdict} resolves evaluation result."""
        ctx = InterpolationContext(result={"verdict": "success", "confidence": 0.95})
        assert ctx.resolve("result", "verdict") == "success"
        assert ctx.resolve("result", "confidence") == 0.95

    def test_result_unavailable_raises(self) -> None:
        """Accessing result when None raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="No evaluation result"):
            ctx.resolve("result", "verdict")

    def test_state_name(self) -> None:
        """${state.name} returns current state name."""
        ctx = InterpolationContext(state_name="checking")
        assert ctx.resolve("state", "name") == "checking"

    def test_state_iteration(self) -> None:
        """${state.iteration} returns current iteration."""
        ctx = InterpolationContext(iteration=5)
        assert ctx.resolve("state", "iteration") == 5

    def test_state_unknown_property(self) -> None:
        """Unknown state property raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="Unknown state property"):
            ctx.resolve("state", "unknown")

    def test_loop_name(self) -> None:
        """${loop.name} returns loop name."""
        ctx = InterpolationContext(loop_name="fix-types")
        assert ctx.resolve("loop", "name") == "fix-types"

    def test_loop_started_at(self) -> None:
        """${loop.started_at} returns start timestamp."""
        ctx = InterpolationContext(started_at="2026-01-13T10:30:00Z")
        assert ctx.resolve("loop", "started_at") == "2026-01-13T10:30:00Z"

    def test_loop_elapsed_ms(self) -> None:
        """${loop.elapsed_ms} returns raw milliseconds."""
        ctx = InterpolationContext(elapsed_ms=45000)
        assert ctx.resolve("loop", "elapsed_ms") == 45000

    def test_loop_elapsed_formatted(self) -> None:
        """${loop.elapsed} returns formatted duration."""
        ctx = InterpolationContext(elapsed_ms=125000)
        assert ctx.resolve("loop", "elapsed") == "2m 5s"

    def test_loop_unknown_property(self) -> None:
        """Unknown loop property raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="Unknown loop property"):
            ctx.resolve("loop", "unknown")

    def test_env_variable(self) -> None:
        """${env.HOME} resolves from environment."""
        ctx = InterpolationContext()
        with mock.patch.dict(os.environ, {"TEST_VAR": "test_value"}):
            assert ctx.resolve("env", "TEST_VAR") == "test_value"

    def test_env_missing_raises(self) -> None:
        """Missing environment variable raises InterpolationError."""
        ctx = InterpolationContext()
        with mock.patch.dict(os.environ, {}, clear=True):
            with pytest.raises(InterpolationError, match="not set"):
                ctx.resolve("env", "NONEXISTENT_VAR_12345")

    def test_unknown_namespace_raises(self) -> None:
        """Unknown namespace raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="Unknown namespace"):
            ctx.resolve("unknown", "path")

    def test_path_not_found_raises(self) -> None:
        """Missing path raises InterpolationError."""
        ctx = InterpolationContext(context={"a": {"b": 1}})
        with pytest.raises(InterpolationError, match="Path 'a.c' not found"):
            ctx.resolve("context", "a.c")


class TestInterpolate:
    """Tests for the interpolate function."""

    def test_simple_variable(self) -> None:
        """Single variable resolves correctly."""
        ctx = InterpolationContext(context={"name": "test"})
        result = interpolate("Hello ${context.name}!", ctx)
        assert result == "Hello test!"

    def test_multiple_variables(self) -> None:
        """Multiple variables in one string all resolve."""
        ctx = InterpolationContext(context={"cmd": "mypy", "target": "src/"})
        result = interpolate("${context.cmd} ${context.target}", ctx)
        assert result == "mypy src/"

    def test_no_variables(self) -> None:
        """String without variables passes through unchanged."""
        ctx = InterpolationContext()
        result = interpolate("plain text", ctx)
        assert result == "plain text"

    def test_escape_sequence(self) -> None:
        """$${literal} becomes ${literal}."""
        ctx = InterpolationContext()
        result = interpolate("Use $${context.var} syntax", ctx)
        assert result == "Use ${context.var} syntax"

    def test_escape_with_real_variable(self) -> None:
        """Escaped and real variables work together."""
        ctx = InterpolationContext(context={"x": "value"})
        result = interpolate("Literal $${y} and real ${context.x}", ctx)
        assert result == "Literal ${y} and real value"

    def test_invalid_format_no_dot(self) -> None:
        """Variable without namespace.path raises error."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="expected namespace.path"):
            interpolate("${varname}", ctx)

    def test_numeric_value(self) -> None:
        """Numeric values convert to strings."""
        ctx = InterpolationContext(context={"count": 42})
        result = interpolate("Count: ${context.count}", ctx)
        assert result == "Count: 42"

    def test_empty_string_value(self) -> None:
        """Empty string values interpolate as empty."""
        ctx = InterpolationContext(context={"empty": ""})
        result = interpolate("Value: [${context.empty}]", ctx)
        assert result == "Value: []"

    def test_none_value(self) -> None:
        """None values interpolate as empty string."""
        ctx = InterpolationContext(context={"nothing": None})
        result = interpolate("Value: [${context.nothing}]", ctx)
        assert result == "Value: []"

    def test_deep_nested_path(self) -> None:
        """Deeply nested paths resolve correctly."""
        ctx = InterpolationContext(context={"a": {"b": {"c": {"d": "deep"}}}})
        result = interpolate("${context.a.b.c.d}", ctx)
        assert result == "deep"


class TestInterpolateDict:
    """Tests for the interpolate_dict function."""

    def test_simple_dict(self) -> None:
        """String values in dict are interpolated."""
        ctx = InterpolationContext(context={"target": "src/"})
        obj = {"action": "mypy ${context.target}"}
        result = interpolate_dict(obj, ctx)
        assert result == {"action": "mypy src/"}

    def test_nested_dict(self) -> None:
        """Nested dicts are recursively processed."""
        ctx = InterpolationContext(context={"x": "value"})
        obj = {"outer": {"inner": "${context.x}"}}
        result = interpolate_dict(obj, ctx)
        assert result == {"outer": {"inner": "value"}}

    def test_list_values(self) -> None:
        """String values in lists are interpolated."""
        ctx = InterpolationContext(context={"a": "1", "b": "2"})
        obj = {"items": ["${context.a}", "${context.b}"]}
        result = interpolate_dict(obj, ctx)
        assert result == {"items": ["1", "2"]}

    def test_non_string_preserved(self) -> None:
        """Non-string values pass through unchanged."""
        ctx = InterpolationContext()
        obj = {"count": 5, "enabled": True, "ratio": 0.5}
        result = interpolate_dict(obj, ctx)
        assert result == {"count": 5, "enabled": True, "ratio": 0.5}

    def test_mixed_values(self) -> None:
        """Mixed value types handled correctly."""
        ctx = InterpolationContext(context={"name": "test"})
        obj = {
            "str_val": "${context.name}",
            "int_val": 42,
            "list_val": ["a", "${context.name}"],
            "dict_val": {"nested": "${context.name}"},
        }
        result = interpolate_dict(obj, ctx)
        assert result == {
            "str_val": "test",
            "int_val": 42,
            "list_val": ["a", "test"],
            "dict_val": {"nested": "test"},
        }

    def test_original_unchanged(self) -> None:
        """Original dict is not modified."""
        ctx = InterpolationContext(context={"x": "y"})
        obj = {"val": "${context.x}"}
        interpolate_dict(obj, ctx)
        assert obj == {"val": "${context.x}"}


class TestFormatDuration:
    """Tests for the _format_duration helper."""

    def test_milliseconds(self) -> None:
        """Sub-second durations show milliseconds."""
        assert _format_duration(0) == "0ms"
        assert _format_duration(500) == "500ms"
        assert _format_duration(999) == "999ms"

    def test_seconds(self) -> None:
        """1-59 seconds show just seconds."""
        assert _format_duration(1000) == "1s"
        assert _format_duration(30000) == "30s"
        assert _format_duration(59000) == "59s"

    def test_minutes(self) -> None:
        """60+ seconds show minutes and seconds."""
        assert _format_duration(60000) == "1m"
        assert _format_duration(90000) == "1m 30s"
        assert _format_duration(125000) == "2m 5s"
        assert _format_duration(3600000) == "60m"

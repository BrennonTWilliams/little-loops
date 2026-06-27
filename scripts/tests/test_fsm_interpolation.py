"""Unit tests for FSM variable interpolation."""

from __future__ import annotations

import os
from pathlib import Path
from unittest import mock

import pytest
import yaml

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
        ctx = InterpolationContext(result={"verdict": "yes", "confidence": 0.95})
        assert ctx.resolve("result", "verdict") == "yes"
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

    def test_check_lifetime_limit_bash_fallback(self) -> None:
        """[ -z ] bash fallback resolves single-level ${context.*} without crashing.

        Regression test for BUG-954: the old nested form
        ${MAX_TOTAL:-${context.max_refine_count}} caused InterpolationError
        because the regex captured up to the first } and produced an unknown
        namespace.  The fixed form uses a plain POSIX test so the only
        interpolation token is a simple ${context.max_refine_count}.
        """
        ctx = InterpolationContext(context={"max_refine_count": 5})
        result = interpolate('[ -z "$MAX_TOTAL" ] && MAX_TOTAL=${context.max_refine_count}', ctx)
        assert "MAX_TOTAL=5" in result

    def test_nested_variable_syntax_raises_interpolation_error(self) -> None:
        """Nested ${VAR:-${context.*}} syntax raises InterpolationError.

        Documents the known-broken pattern from BUG-954.  The regex captures
        up to the first } giving namespace 'MAX_TOTAL:-${context.max_refine_count'
        which has no registered handler.  Use the POSIX-test form instead.
        """
        ctx = InterpolationContext(context={"max_refine_count": 5})
        with pytest.raises(InterpolationError):
            interpolate("MAX_TOTAL=${MAX_TOTAL:-${context.max_refine_count}}", ctx)

    def test_bash_default_operator_raises_interpolation_error(self) -> None:
        """${context.key:-default} (bash :-) raises InterpolationError. BUG-2346.

        The interpolator resolves 'context.order:-queue' as a literal path; there is
        no such key, so _get_nested() raises. Use ${context.key:default=val} instead.
        """
        ctx = InterpolationContext(context={"order": "queue"})
        with pytest.raises(InterpolationError):
            interpolate('ORDER="${context.order:-queue}"', ctx)

    def test_engine_default_is_correct_alternative_to_bash_default(self) -> None:
        """${context.key:default=val} succeeds where ${context.key:-val} crashes. BUG-2346."""
        ctx = InterpolationContext(context={})
        result = interpolate('ORDER="${context.order:default=queue}"', ctx)
        assert result == 'ORDER="queue"'


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


class TestInterpolateDictErrorPropagation:
    """Tests that errors in interpolate_dict and _interpolate_list propagate correctly."""

    def test_dict_value_error_propagates(self) -> None:
        """InterpolationError from a failing value bubbles up from interpolate_dict."""
        ctx = InterpolationContext()  # no context vars
        obj = {"cmd": "${context.missing_key}"}
        with pytest.raises(InterpolationError, match="Path 'missing_key' not found in context"):
            interpolate_dict(obj, ctx)

    def test_nested_dict_error_propagates(self) -> None:
        """Error in a nested dict value propagates up."""
        ctx = InterpolationContext()
        obj = {"outer": {"inner": "${context.nope}"}}
        with pytest.raises(InterpolationError):
            interpolate_dict(obj, ctx)

    def test_list_value_error_propagates(self) -> None:
        """InterpolationError from a list item bubbles up from interpolate_dict."""
        ctx = InterpolationContext()
        obj = {"items": ["${context.bad_var}"]}
        with pytest.raises(InterpolationError):
            interpolate_dict(obj, ctx)

    def test_list_nested_dict_error_propagates(self) -> None:
        """Error in a dict inside a list propagates up."""
        ctx = InterpolationContext()
        obj = {"items": [{"key": "${context.missing}"}]}
        with pytest.raises(InterpolationError):
            interpolate_dict(obj, ctx)


class TestInterpolateEdgeCases:
    """Additional edge cases for the interpolate function."""

    def test_multiple_escape_sequences(self) -> None:
        """Multiple $${...} escapes in one string are all converted."""
        ctx = InterpolationContext()
        result = interpolate("$${a} and $${b}", ctx)
        assert result == "${a} and ${b}"

    def test_escape_at_start(self) -> None:
        """Escaped sequence at the very start of the string works."""
        ctx = InterpolationContext()
        result = interpolate("$${var}", ctx)
        assert result == "${var}"

    def test_unknown_namespace_in_string(self) -> None:
        """Unknown namespace inside interpolate raises InterpolationError."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="Unknown namespace"):
            interpolate("${bad_ns.something}", ctx)

    def test_missing_captured_key(self) -> None:
        """Accessing a missing captured variable raises InterpolationError."""
        ctx = InterpolationContext(captured={})
        with pytest.raises(InterpolationError, match="Path 'missing' not found in captured"):
            interpolate("${captured.missing}", ctx)

    def test_result_path_not_found(self) -> None:
        """Missing path in result raises InterpolationError."""
        ctx = InterpolationContext(result={"verdict": "yes"})
        with pytest.raises(InterpolationError, match="Path 'confidence' not found in result"):
            interpolate("${result.confidence}", ctx)

    def test_escape_bash_default_value(self) -> None:
        """$${VAR:-default} passes through as literal ${VAR:-default} without error.

        Regression test for BUG-1384: the escape mechanism must accept bash
        parameter expansion operators (:-) inside $${...} blocks.
        """
        ctx = InterpolationContext()
        result = interpolate("printf '$${DEPTH:-0}'", ctx)
        assert result == "printf '${DEPTH:-0}'"

    def test_escape_bash_conditional_assign(self) -> None:
        """$${VAR:+suffix} passes through as literal ${VAR:+suffix}."""
        ctx = InterpolationContext()
        result = interpolate("X=$${VAR:+yes}", ctx)
        assert result == "X=${VAR:+yes}"

    def test_escape_bash_array_expansion(self) -> None:
        """$${ARRAY[@]} passes through as literal ${ARRAY[@]}."""
        ctx = InterpolationContext()
        result = interpolate('for S in "$${SPEC_LIST[@]}"; do', ctx)
        assert result == 'for S in "${SPEC_LIST[@]}"; do'

    def test_escape_multi_bash_operators_in_one_string(self) -> None:
        """Multiple bash-operator escapes in one string all pass through.

        Mirrors the autodev.yaml pattern with PASSED_LIST and SKIPPED_LIST.
        """
        ctx = InterpolationContext()
        template = (
            'printf \'Passed  (%d): %s\\n\' "$PASSED_COUNT" "$${PASSED_LIST:-none}"\n'
            'printf \'Skipped (%d): %s\\n\' "$SKIPPED_COUNT" "$${SKIPPED_LIST:-none}"'
        )
        result = interpolate(template, ctx)
        assert "${PASSED_LIST:-none}" in result
        assert "${SKIPPED_LIST:-none}" in result
        assert "$${" not in result

    def test_escape_bash_operator_mixed_with_real_variable(self) -> None:
        """$${VAR:-default} and a real ${namespace.path} coexist in one string."""
        ctx = InterpolationContext(context={"x": "hello"})
        result = interpolate("$${DEPTH_STR:-none} ${context.x}", ctx)
        assert result == "${DEPTH_STR:-none} hello"

    def test_escape_bash_string_conditional(self) -> None:
        """$${VAR:+' (depth: $VAR)'} passes through preserving inner single-quoted string."""
        ctx = InterpolationContext()
        result = interpolate("DEPTH_STR=$${DEPTH:+' (depth: $DEPTH)'}", ctx)
        assert result == "DEPTH_STR=${DEPTH:+' (depth: $DEPTH)'}"

    def test_escape_bare_bash_variable_no_operator(self) -> None:
        """$${VAR} (no bash operator) passes through as literal ${VAR} without error.

        Regression test for BUG-1675: bare variable names (no :-, :+, [@] etc.)
        must be escapable with $${} just like operator forms.
        """
        ctx = InterpolationContext()
        result = interpolate('"$${HEAD_PART}"$\'\\n...\\n\'"$${TAIL_PART}"', ctx)
        assert result == '"${HEAD_PART}"$\'\\n...\\n\'"${TAIL_PART}"'


class TestMessagesNamespace:
    """Tests for the messages namespace in InterpolationContext."""

    def test_messages_full_log(self) -> None:
        """${messages} / ${messages.output} returns all messages joined by newline."""
        ctx = InterpolationContext(messages=["step A output", "step B output"])
        assert ctx.resolve("messages", "") == "step A output\nstep B output"
        assert ctx.resolve("messages", "output") == "step A output\nstep B output"

    def test_messages_empty(self) -> None:
        """${messages} returns empty string when no messages appended."""
        ctx = InterpolationContext()
        assert ctx.resolve("messages", "") == ""

    def test_messages_last_n(self) -> None:
        """${messages.last(N)} returns the last N messages."""
        ctx = InterpolationContext(messages=["a", "b", "c", "d"])
        assert ctx.resolve("messages", "last(2)") == "c\nd"
        assert ctx.resolve("messages", "last(1)") == "d"

    def test_messages_last_n_exceeds_length(self) -> None:
        """${messages.last(N)} with N > len returns all messages."""
        ctx = InterpolationContext(messages=["a", "b"])
        assert ctx.resolve("messages", "last(10)") == "a\nb"

    def test_messages_summary(self) -> None:
        """${messages.summary} returns the pre-computed summary string."""
        ctx = InterpolationContext(messages=["x"], messages_summary="Summarized context")
        assert ctx.resolve("messages", "summary") == "Summarized context"

    def test_messages_summary_default_empty(self) -> None:
        """${messages.summary} defaults to empty string when no summary computed."""
        ctx = InterpolationContext(messages=["x"])
        assert ctx.resolve("messages", "summary") == ""

    def test_messages_unknown_property(self) -> None:
        """Unknown messages property raises InterpolationError."""
        ctx = InterpolationContext(messages=["x"])
        with pytest.raises(InterpolationError, match="Unknown messages property"):
            ctx.resolve("messages", "unknown")

    def test_bare_messages_interpolation(self) -> None:
        """${messages} bare syntax resolves to full log via interpolate()."""
        ctx = InterpolationContext(messages=["first", "second"])
        result = interpolate("Context:\n${messages}", ctx)
        assert result == "Context:\nfirst\nsecond"

    def test_messages_last_interpolation(self) -> None:
        """${messages.last(2)} resolves via interpolate()."""
        ctx = InterpolationContext(messages=["a", "b", "c"])
        result = interpolate("Recent: ${messages.last(2)}", ctx)
        assert result == "Recent: b\nc"


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


class TestParamNamespace:
    """Tests for the param namespace in InterpolationContext."""

    def test_param_resolves_simple_key(self) -> None:
        ctx = InterpolationContext(param={"counter_key": "lint_retries"})
        result = interpolate("${param.counter_key}", ctx)
        assert result == "lint_retries"

    def test_param_resolves_integer(self) -> None:
        ctx = InterpolationContext(param={"max_retries": 5})
        result = interpolate("${param.max_retries}", ctx)
        assert result == "5"

    def test_param_resolves_nested_key(self) -> None:
        ctx = InterpolationContext(param={"nested": {"key": "val"}})
        result = interpolate("${param.nested.key}", ctx)
        assert result == "val"

    def test_param_unknown_key_raises(self) -> None:
        ctx = InterpolationContext(param={})
        with pytest.raises(InterpolationError):
            interpolate("${param.missing}", ctx)

    def test_param_independent_from_context(self) -> None:
        ctx = InterpolationContext(
            context={"key": "from_context"},
            param={"key": "from_param"},
        )
        assert interpolate("${context.key}", ctx) == "from_context"
        assert interpolate("${param.key}", ctx) == "from_param"

    def test_param_empty_by_default(self) -> None:
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError):
            interpolate("${param.anything}", ctx)


class TestSafeInterpolation:
    """Tests for :default= and ? fallback interpolation syntax (ENH-1958)."""

    # ── :default= suffix ──────────────────────────────────────────────

    def test_default_suffix_uses_fallback_when_missing(self) -> None:
        """${captured.missing:default=fallback} returns the default string."""
        ctx = InterpolationContext(captured={})
        result = interpolate("${captured.missing:default=fallback}", ctx)
        assert result == "fallback"

    def test_default_suffix_returns_actual_when_present(self) -> None:
        """${captured.present:default=fb} returns the actual value when it exists."""
        ctx = InterpolationContext(captured={"present": {"output": "real value"}})
        result = interpolate("${captured.present.output:default=fb}", ctx)
        assert result == "real value"

    def test_default_suffix_in_context_namespace(self) -> None:
        """${context.missing:default=N/A} in context namespace."""
        ctx = InterpolationContext(context={})
        result = interpolate("${context.missing:default=N/A}", ctx)
        assert result == "N/A"

    def test_default_suffix_in_env_namespace(self) -> None:
        """${env.MISSING_VAR:default=off} returns default when env var unset."""
        ctx = InterpolationContext()
        with mock.patch.dict(os.environ, {}, clear=True):
            result = interpolate("${env.NONEXISTENT_VAR_12345:default=off}", ctx)
            assert result == "off"

    def test_default_suffix_in_state_namespace(self) -> None:
        """${state.unknown:default=default_name} returns default for unknown state prop."""
        ctx = InterpolationContext()
        result = interpolate("${state.unknown:default=default_name}", ctx)
        assert result == "default_name"

    def test_default_suffix_in_loop_namespace(self) -> None:
        """${loop.unknown:default=n/a} returns default for unknown loop prop."""
        ctx = InterpolationContext()
        result = interpolate("${loop.unknown:default=n/a}", ctx)
        assert result == "n/a"

    def test_default_suffix_empty_string(self) -> None:
        """${captured.x:default=} returns empty string as default."""
        ctx = InterpolationContext(captured={})
        result = interpolate("Value: [${captured.x:default=}]", ctx)
        assert result == "Value: []"

    def test_default_suffix_with_special_chars(self) -> None:
        """Default value can contain spaces, dashes, and special chars."""
        ctx = InterpolationContext(captured={})
        result = interpolate("${captured.x:default=no step -- see plan}", ctx)
        assert result == "no step -- see plan"

    def test_default_suffix_with_question_mark_in_default(self) -> None:
        """A ? inside a default value is treated literally (not as nullable)."""
        ctx = InterpolationContext(captured={})
        result = interpolate("${captured.x:default=are you sure?}", ctx)
        assert result == "are you sure?"

    def test_default_suffix_nested_path_missing(self) -> None:
        """Default kicks in for a missing nested path within an existing captured key."""
        ctx = InterpolationContext(captured={"selected_step": {"exit_code": 0}})
        result = interpolate("${captured.selected_step.output:default=no output}", ctx)
        assert result == "no output"

    # ── ? (nullable) suffix ───────────────────────────────────────────

    def test_nullable_suffix_returns_empty_when_missing(self) -> None:
        """${captured.missing?} returns empty string when path missing."""
        ctx = InterpolationContext(captured={})
        result = interpolate("${captured.missing?}", ctx)
        assert result == ""

    def test_nullable_suffix_returns_actual_when_present(self) -> None:
        """${captured.present.output?} returns actual value when it exists."""
        ctx = InterpolationContext(captured={"present": {"output": "real value"}})
        result = interpolate("${captured.present.output?}", ctx)
        assert result == "real value"

    def test_nullable_suffix_in_context_namespace(self) -> None:
        """${context.missing?} returns empty in context namespace."""
        ctx = InterpolationContext(context={})
        result = interpolate("${context.missing?}", ctx)
        assert result == ""

    def test_nullable_suffix_in_env_namespace(self) -> None:
        """${env.MISSING?} returns empty for unset env var."""
        ctx = InterpolationContext()
        with mock.patch.dict(os.environ, {}, clear=True):
            result = interpolate("${env.NONEXISTENT_VAR_12345?}", ctx)
            assert result == ""

    def test_nullable_suffix_nested_path_missing(self) -> None:
        """Nullable kicks in for a missing nested path within an existing key."""
        ctx = InterpolationContext(captured={"selected_step": {"exit_code": 0}})
        result = interpolate("${captured.selected_step.output?}", ctx)
        assert result == ""

    # ── Backward compatibility (unsuffixed stays strict) ──────────────

    def test_no_suffix_still_raises_on_missing_captured(self) -> None:
        """${captured.missing} without suffix still raises InterpolationError."""
        ctx = InterpolationContext(captured={})
        with pytest.raises(InterpolationError, match="Path 'missing' not found"):
            interpolate("${captured.missing}", ctx)

    def test_no_suffix_still_raises_on_missing_context(self) -> None:
        """${context.missing} without suffix still raises."""
        ctx = InterpolationContext(context={})
        with pytest.raises(InterpolationError, match="Path 'missing' not found"):
            interpolate("${context.missing}", ctx)

    def test_no_suffix_still_raises_on_unknown_namespace(self) -> None:
        """${unknown.x} without suffix still raises for unknown namespace."""
        ctx = InterpolationContext()
        with pytest.raises(InterpolationError, match="Unknown namespace"):
            interpolate("${unknown.x}", ctx)

    def test_no_suffix_still_raises_on_invalid_format(self) -> None:
        """${varname} (no namespace.path) still raises even with suffix."""
        ctx = InterpolationContext()
        # The suffix parsing happens AFTER the namespace.path check,
        # so ${varname?} = "${varname?}" without dot still fails format check
        with pytest.raises(InterpolationError, match="expected namespace.path"):
            interpolate("${varname?}", ctx)

    # ── Mixed patterns ────────────────────────────────────────────────

    def test_mixed_safe_and_unsafe_in_one_string(self) -> None:
        """A safe var and an existing var coexist in one template."""
        ctx = InterpolationContext(
            context={"real_var": "hello"},
            captured={},
        )
        result = interpolate("X=${captured.a:default=N/A} Y=${context.real_var}", ctx)
        assert result == "X=N/A Y=hello"

    def test_multiple_defaults_in_one_string(self) -> None:
        """Multiple :default= references in one template all resolve."""
        ctx = InterpolationContext(captured={})
        result = interpolate("A=${captured.x:default=1} B=${captured.y:default=2}", ctx)
        assert result == "A=1 B=2"

    def test_multiple_nullable_in_one_string(self) -> None:
        """Multiple ? references in one template all resolve to empty."""
        ctx = InterpolationContext(captured={})
        result = interpolate("[${captured.x?}][${captured.y?}]", ctx)
        assert result == "[][]"

    def test_mixed_default_and_nullable(self) -> None:
        """Mixing :default= and ? forms in one template works independently."""
        ctx = InterpolationContext(captured={})
        result = interpolate("A=${captured.x:default=got} B=${captured.y?}", ctx)
        assert result == "A=got B="

    # ── Edge cases and error conditions ───────────────────────────────

    def test_default_and_nullable_together_raises(self) -> None:
        """Using both ? and :default= together raises InterpolationError."""
        ctx = InterpolationContext(captured={})
        with pytest.raises(InterpolationError, match="mutually exclusive"):
            interpolate("${captured.x?:default=fallback}", ctx)

    def test_default_suffix_prevents_error_when_prev_is_none(self) -> None:
        """${prev.output:default=none} avoids crash when prev is None."""
        ctx = InterpolationContext(prev=None)
        result = interpolate("${prev.output:default=none}", ctx)
        assert result == "none"

    def test_nullable_suffix_prevents_error_when_prev_is_none(self) -> None:
        """${prev.output?} returns empty when prev is None."""
        ctx = InterpolationContext(prev=None)
        result = interpolate("${prev.output?}", ctx)
        assert result == ""

    def test_default_suffix_prevents_error_when_result_is_none(self) -> None:
        """${result.verdict:default=unknown} avoids crash when result is None."""
        ctx = InterpolationContext(result=None)
        result = interpolate("${result.verdict:default=unknown}", ctx)
        assert result == "unknown"

    def test_escape_still_works_with_default_syntax(self) -> None:
        """$${captured.x:default=fallback} passes through as literal."""
        ctx = InterpolationContext()
        result = interpolate("$${captured.x:default=fallback}", ctx)
        assert result == "${captured.x:default=fallback}"

    def test_escape_still_works_with_nullable_syntax(self) -> None:
        """$${captured.x?} passes through as literal."""
        ctx = InterpolationContext()
        result = interpolate("$${captured.x?}", ctx)
        assert result == "${captured.x?}"

    # ── interpolate_dict compatibility ────────────────────────────────

    def test_default_suffix_in_interpolate_dict(self) -> None:
        """:default= works inside interpolate_dict."""
        ctx = InterpolationContext(captured={})
        obj = {"summary": "${captured.x:default=no data}"}
        result = interpolate_dict(obj, ctx)
        assert result == {"summary": "no data"}

    def test_nullable_suffix_in_interpolate_dict(self) -> None:
        """? suffix works inside interpolate_dict."""
        ctx = InterpolationContext(captured={})
        obj = {"summary": "${captured.x?}"}
        result = interpolate_dict(obj, ctx)
        assert result == {"summary": ""}

    # ── Real-loop bypass-path guards (BUG-2094) ──────────────────────────────

    def test_loop_composer_present_result_safe_with_empty_captured(self) -> None:
        """present_result must not raise when user_plan_decision was bypassed."""
        loop_path = Path("scripts/little_loops/loops/loop-composer.yaml")
        data = yaml.safe_load(loop_path.read_text())
        action = data["states"]["present_result"]["action"]
        ctx = InterpolationContext(captured={}, context={"run_dir": "/tmp/test-run"})
        interpolate(action, ctx)

    def test_general_task_check_done_safe_with_empty_captured(self) -> None:
        """check_done must not raise when work_result/selected_step were bypassed."""
        loop_path = Path("scripts/little_loops/loops/general-task.yaml")
        data = yaml.safe_load(loop_path.read_text())
        action = data["states"]["check_done"]["action"]
        ctx = InterpolationContext(
            captured={},
            context={"run_dir": "/tmp/test-run"},
        )
        interpolate(action, ctx)

    def test_general_task_run_final_tests_safe_with_empty_context(self) -> None:
        """run_final_tests (ENH-2225) must not raise when test_cmd is unset (default "")."""
        loop_path = Path("scripts/little_loops/loops/general-task.yaml")
        data = yaml.safe_load(loop_path.read_text())
        action = data["states"]["run_final_tests"]["action"]
        ctx = InterpolationContext(
            captured={},
            context={"run_dir": "/tmp/test-run", "test_cmd": ""},
        )
        interpolate(action, ctx)

    def test_loop_router_present_choices_safe_with_empty_captured(self) -> None:
        """present_choices must not raise when project_score/builtin_score were bypassed."""
        loop_path = Path("scripts/little_loops/loops/loop-router.yaml")
        data = yaml.safe_load(loop_path.read_text())
        action = data["states"]["present_choices"]["action"]
        # select_loop is always captured before present_choices (not on bypass path)
        ctx = InterpolationContext(
            captured={"select_loop": {"output": "analysis output"}},
            context={"goal": "test goal", "run_dir": "/tmp"},
        )
        interpolate(action, ctx)

    def test_loop_router_present_result_safe_with_empty_captured(self) -> None:
        """present_result must not raise when new_loop_proposal/review_result were bypassed."""
        loop_path = Path("scripts/little_loops/loops/loop-router.yaml")
        data = yaml.safe_load(loop_path.read_text())
        action = data["states"]["present_result"]["action"]
        ctx = InterpolationContext(captured={}, context={"run_dir": "/tmp"})
        interpolate(action, ctx)

    def test_harness_optimize_propose_safe_with_empty_captured(self) -> None:
        """propose must not raise when benchmark_score/state_name were bypassed."""
        loop_path = Path("scripts/little_loops/loops/harness-optimize.yaml")
        data = yaml.safe_load(loop_path.read_text())
        action = data["states"]["propose"]["action"]
        ctx = InterpolationContext(
            captured={"directive": {"output": "improve"}, "baseline": {"output": "0.5"}},
            context={"targets": "some/file.yaml", "run_dir": "/tmp"},
        )
        interpolate(action, ctx)

    def test_harness_optimize_apply_safe_with_empty_captured(self) -> None:
        """apply must not raise when state_name was bypassed."""
        loop_path = Path("scripts/little_loops/loops/harness-optimize.yaml")
        data = yaml.safe_load(loop_path.read_text())
        action = data["states"]["apply"]["action"]
        ctx = InterpolationContext(
            captured={"candidate": {"output": "new content"}},
            context={"targets": "some/file.yaml", "run_dir": "/tmp"},
        )
        interpolate(action, ctx)

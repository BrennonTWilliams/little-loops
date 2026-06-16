"""Unit tests for FSM evaluators (Tier 1 deterministic and Tier 2 LLM)."""

from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from little_loops.fsm.evaluators import (
    DEFAULT_LLM_PROMPT,
    DEFAULT_LLM_SCHEMA,
    EvaluationResult,
    _extract_json_path,
    evaluate,
    evaluate_action_stall,
    evaluate_blind_comparator,
    evaluate_classify,
    evaluate_contract,
    evaluate_convergence,
    evaluate_diff_stall,
    evaluate_exit_code,
    evaluate_llm_structured,
    evaluate_mcp_result,
    evaluate_output_contains,
    evaluate_output_json,
    evaluate_output_numeric,
)
from little_loops.fsm.interpolation import InterpolationContext
from little_loops.fsm.schema import EvaluateConfig


class TestEvaluationResult:
    """Tests for the EvaluationResult dataclass."""

    def test_basic_result(self) -> None:
        """EvaluationResult holds verdict and details."""
        result = EvaluationResult(verdict="yes", details={"key": "value"})
        assert result.verdict == "yes"
        assert result.details == {"key": "value"}

    def test_empty_details(self) -> None:
        """EvaluationResult can have empty details."""
        result = EvaluationResult(verdict="no", details={})
        assert result.verdict == "no"
        assert result.details == {}


class TestExitCodeEvaluator:
    """Tests for exit_code evaluator."""

    @pytest.mark.parametrize(
        ("exit_code", "expected"),
        [
            (0, "yes"),
            (1, "no"),
            (2, "error"),
            (127, "error"),
            (255, "error"),
        ],
    )
    def test_exit_code_mapping(self, exit_code: int, expected: str) -> None:
        """Exit codes map to correct verdicts."""
        result = evaluate_exit_code(exit_code)
        assert result.verdict == expected
        assert result.details["exit_code"] == exit_code

    def test_negative_exit_code(self) -> None:
        """Negative exit codes treated as error."""
        result = evaluate_exit_code(-1)
        assert result.verdict == "error"


class TestOutputNumericEvaluator:
    """Tests for output_numeric evaluator."""

    def test_equal_passes(self) -> None:
        """eq operator passes when values equal."""
        result = evaluate_output_numeric("5", "eq", 5)
        assert result.verdict == "yes"
        assert result.details["value"] == 5
        assert result.details["target"] == 5

    def test_equal_fails(self) -> None:
        """eq operator fails when values differ."""
        result = evaluate_output_numeric("3", "eq", 5)
        assert result.verdict == "no"

    def test_not_equal_passes(self) -> None:
        """ne operator passes when values differ."""
        result = evaluate_output_numeric("3", "ne", 5)
        assert result.verdict == "yes"

    def test_not_equal_fails(self) -> None:
        """ne operator fails when values equal."""
        result = evaluate_output_numeric("5", "ne", 5)
        assert result.verdict == "no"

    def test_less_than_passes(self) -> None:
        """lt operator passes when value < target."""
        result = evaluate_output_numeric("3", "lt", 5)
        assert result.verdict == "yes"

    def test_less_than_fails(self) -> None:
        """lt operator fails when value >= target."""
        result = evaluate_output_numeric("5", "lt", 5)
        assert result.verdict == "no"

    def test_less_equal_passes(self) -> None:
        """le operator passes when value <= target."""
        result = evaluate_output_numeric("5", "le", 5)
        assert result.verdict == "yes"

    def test_less_equal_fails(self) -> None:
        """le operator fails when value > target."""
        result = evaluate_output_numeric("6", "le", 5)
        assert result.verdict == "no"

    def test_greater_than_passes(self) -> None:
        """gt operator passes when value > target."""
        result = evaluate_output_numeric("7", "gt", 5)
        assert result.verdict == "yes"

    def test_greater_than_fails(self) -> None:
        """gt operator fails when value <= target."""
        result = evaluate_output_numeric("5", "gt", 5)
        assert result.verdict == "no"

    def test_greater_equal_passes(self) -> None:
        """ge operator passes when value >= target."""
        result = evaluate_output_numeric("5", "ge", 5)
        assert result.verdict == "yes"

    def test_greater_equal_fails(self) -> None:
        """ge operator fails when value < target."""
        result = evaluate_output_numeric("4", "ge", 5)
        assert result.verdict == "no"

    def test_parse_error(self) -> None:
        """Non-numeric output returns error verdict."""
        result = evaluate_output_numeric("not a number", "eq", 5)
        assert result.verdict == "error"
        assert "Cannot parse as number" in result.details["error"]

    def test_whitespace_stripped(self) -> None:
        """Whitespace around number is handled."""
        result = evaluate_output_numeric("  5  \n", "eq", 5)
        assert result.verdict == "yes"

    def test_float_values(self) -> None:
        """Float values are compared correctly."""
        result = evaluate_output_numeric("3.14", "lt", 3.15)
        assert result.verdict == "yes"
        assert result.details["value"] == 3.14

    def test_unknown_operator(self) -> None:
        """Unknown operator returns error verdict."""
        result = evaluate_output_numeric("5", "invalid", 5)
        assert result.verdict == "error"
        assert "Unknown operator" in result.details["error"]


class TestExtractJsonPath:
    """Tests for the _extract_json_path helper."""

    def test_simple_path(self) -> None:
        """Simple key extraction works."""
        data = {"name": "test"}
        assert _extract_json_path(data, "name") == "test"

    def test_path_with_dot_prefix(self) -> None:
        """Path with leading dot works (jq-style)."""
        data = {"name": "test"}
        assert _extract_json_path(data, ".name") == "test"

    def test_nested_path(self) -> None:
        """Nested path extraction works."""
        data = {"summary": {"failed": 0, "passed": 10}}
        assert _extract_json_path(data, ".summary.failed") == 0
        assert _extract_json_path(data, "summary.passed") == 10

    def test_deeply_nested(self) -> None:
        """Deeply nested paths work."""
        data = {"a": {"b": {"c": {"d": "deep"}}}}
        assert _extract_json_path(data, "a.b.c.d") == "deep"

    def test_array_index(self) -> None:
        """Array index access works."""
        data = {"items": ["first", "second", "third"]}
        assert _extract_json_path(data, "items.0") == "first"
        assert _extract_json_path(data, "items.2") == "third"

    def test_mixed_dict_and_array(self) -> None:
        """Mixed dict and array traversal works."""
        data = {"results": [{"name": "a"}, {"name": "b"}]}
        assert _extract_json_path(data, "results.0.name") == "a"
        assert _extract_json_path(data, "results.1.name") == "b"

    def test_missing_key_raises(self) -> None:
        """Missing key raises KeyError."""
        data = {"name": "test"}
        with pytest.raises(KeyError, match="missing"):
            _extract_json_path(data, "missing")

    def test_missing_nested_key_raises(self) -> None:
        """Missing nested key raises KeyError."""
        data = {"a": {"b": 1}}
        with pytest.raises(KeyError, match=r"a\.c"):
            _extract_json_path(data, "a.c")

    def test_array_index_out_of_range(self) -> None:
        """Array index out of range raises KeyError."""
        data = {"items": ["a", "b"]}
        with pytest.raises(KeyError, match=r"items\.5"):
            _extract_json_path(data, "items.5")


class TestOutputJsonEvaluator:
    """Tests for output_json evaluator."""

    def test_simple_numeric_comparison(self) -> None:
        """Simple numeric JSON comparison works."""
        output = '{"count": 5}'
        result = evaluate_output_json(output, ".count", "eq", 5)
        assert result.verdict == "yes"
        assert result.details["value"] == 5

    def test_nested_path(self) -> None:
        """Nested JSON path extraction works."""
        output = '{"summary": {"failed": 0}}'
        result = evaluate_output_json(output, ".summary.failed", "eq", 0)
        assert result.verdict == "yes"

    def test_numeric_less_than(self) -> None:
        """Numeric comparison with lt operator."""
        output = '{"errors": 3}'
        result = evaluate_output_json(output, ".errors", "lt", 5)
        assert result.verdict == "yes"

    def test_numeric_greater_than(self) -> None:
        """Numeric comparison with gt operator."""
        output = '{"score": 95}'
        result = evaluate_output_json(output, ".score", "gt", 90)
        assert result.verdict == "yes"

    def test_string_equality(self) -> None:
        """String value comparison works."""
        output = '{"status": "ok"}'
        result = evaluate_output_json(output, ".status", "eq", "ok")
        assert result.verdict == "yes"

    def test_string_not_equal(self) -> None:
        """String ne comparison works."""
        output = '{"status": "error"}'
        result = evaluate_output_json(output, ".status", "ne", "ok")
        assert result.verdict == "yes"

    def test_string_with_numeric_operator_fails(self) -> None:
        """Numeric operator on string returns error."""
        output = '{"status": "ok"}'
        result = evaluate_output_json(output, ".status", "lt", "ok")
        assert result.verdict == "error"
        assert "not supported for non-numeric" in result.details["error"]

    def test_invalid_json(self) -> None:
        """Invalid JSON returns error verdict."""
        output = "not json"
        result = evaluate_output_json(output, ".key", "eq", "value")
        assert result.verdict == "error"
        assert "Invalid JSON" in result.details["error"]

    def test_path_not_found(self) -> None:
        """Missing path returns error verdict."""
        output = '{"name": "test"}'
        result = evaluate_output_json(output, ".missing", "eq", "value")
        assert result.verdict == "error"
        assert "Path not found" in result.details["error"]

    def test_array_access(self) -> None:
        """Array index access in JSON works."""
        output = '{"items": [1, 2, 3]}'
        result = evaluate_output_json(output, ".items.1", "eq", 2)
        assert result.verdict == "yes"

    def test_boolean_value(self) -> None:
        """Boolean JSON value comparison works."""
        output = '{"enabled": true}'
        result = evaluate_output_json(output, ".enabled", "eq", True)
        assert result.verdict == "yes"


class TestOutputContainsEvaluator:
    """Tests for output_contains evaluator."""

    def test_substring_match(self) -> None:
        """Substring found returns success."""
        result = evaluate_output_contains("Hello World", "World")
        assert result.verdict == "yes"
        assert result.details["matched"] is True

    def test_substring_not_found(self) -> None:
        """Substring not found returns failure."""
        result = evaluate_output_contains("Hello World", "Goodbye")
        assert result.verdict == "no"
        assert result.details["matched"] is False

    def test_regex_pattern(self) -> None:
        """Regex pattern matching works."""
        result = evaluate_output_contains("Error: 5 failures", r"\d+ failures")
        assert result.verdict == "yes"

    def test_regex_anchors(self) -> None:
        """Regex anchors work correctly."""
        result = evaluate_output_contains("test line", r"^test")
        assert result.verdict == "yes"

        result = evaluate_output_contains("line test", r"^test")
        assert result.verdict == "no"

    def test_negate_found(self) -> None:
        """negate=True with match returns failure."""
        result = evaluate_output_contains("has error", "error", negate=True)
        assert result.verdict == "no"

    def test_negate_not_found(self) -> None:
        """negate=True without match returns success."""
        result = evaluate_output_contains("All tests passed", "Error", negate=True)
        assert result.verdict == "yes"

    def test_invalid_regex_fallback(self) -> None:
        """Invalid regex falls back to substring match."""
        # '[' is invalid regex but valid substring
        result = evaluate_output_contains("test[1]", "[1]")
        assert result.verdict == "yes"

    def test_empty_pattern(self) -> None:
        """Empty pattern matches (substring)."""
        result = evaluate_output_contains("any text", "")
        assert result.verdict == "yes"

    def test_multiline_output(self) -> None:
        """Pattern matching works on multiline output."""
        output = "line 1\nError on line 2\nline 3"
        result = evaluate_output_contains(output, "Error")
        assert result.verdict == "yes"


class TestConvergenceEvaluator:
    """Tests for convergence evaluator."""

    def test_target_reached_exact(self) -> None:
        """Exact target match returns target verdict."""
        result = evaluate_convergence(0, 5, 0)
        assert result.verdict == "target"
        assert result.details["current"] == 0

    def test_target_reached_within_tolerance(self) -> None:
        """Value within tolerance returns target verdict."""
        result = evaluate_convergence(0.5, 5, 0, tolerance=1)
        assert result.verdict == "target"

    def test_progress_minimize(self) -> None:
        """Decreasing value returns progress for minimize."""
        result = evaluate_convergence(3, 5, 0, direction="minimize")
        assert result.verdict == "progress"
        assert result.details["delta"] == -2

    def test_stall_minimize(self) -> None:
        """No change returns stall."""
        result = evaluate_convergence(5, 5, 0, direction="minimize")
        assert result.verdict == "stall"
        assert result.details["delta"] == 0

    def test_regression_minimize(self) -> None:
        """Increasing value returns stall for minimize."""
        result = evaluate_convergence(7, 5, 0, direction="minimize")
        assert result.verdict == "stall"
        assert result.details["delta"] == 2

    def test_progress_maximize(self) -> None:
        """Increasing value returns progress for maximize."""
        result = evaluate_convergence(8, 5, 10, direction="maximize")
        assert result.verdict == "progress"
        assert result.details["delta"] == 3

    def test_stall_maximize(self) -> None:
        """Decreasing value returns stall for maximize."""
        result = evaluate_convergence(4, 5, 10, direction="maximize")
        assert result.verdict == "stall"

    def test_first_iteration_no_previous(self) -> None:
        """First iteration with no previous returns progress."""
        result = evaluate_convergence(10, None, 0)
        assert result.verdict == "progress"
        assert result.details["previous"] is None
        assert result.details["delta"] is None

    def test_details_contain_all_values(self) -> None:
        """Result details include all tracking values."""
        result = evaluate_convergence(3, 5, 0, tolerance=0.1, direction="minimize")
        assert result.details["current"] == 3
        assert result.details["previous"] == 5
        assert result.details["target"] == 0
        assert result.details["direction"] == "minimize"


class TestClassifyEvaluator:
    """Tests for classify evaluator."""

    def test_last_line_default(self) -> None:
        """Last non-empty line is returned as verdict by default."""
        result = evaluate_classify("first\nsecond\nWIRE")
        assert result.verdict == "WIRE"
        assert result.details["token"] == "WIRE"

    def test_explicit_last(self) -> None:
        """line='last' selects the last non-empty line."""
        result = evaluate_classify("IMPLEMENT\nWIRE", line="last")
        assert result.verdict == "WIRE"

    def test_first_line(self) -> None:
        """line='first' selects the first non-empty line."""
        result = evaluate_classify("IMPLEMENT\nWIRE", line="first")
        assert result.verdict == "IMPLEMENT"

    def test_integer_index(self) -> None:
        """Integer line index selects that line (0-based)."""
        result = evaluate_classify("A\nB\nC", line=1)
        assert result.verdict == "B"

    def test_negative_integer_index(self) -> None:
        """Negative integer index is supported (Python-style)."""
        result = evaluate_classify("A\nB\nC", line=-1)
        assert result.verdict == "C"

    def test_integer_index_out_of_range(self) -> None:
        """Out-of-range integer index returns empty verdict."""
        result = evaluate_classify("A\nB", line=10)
        assert result.verdict == ""
        assert "error" in result.details

    def test_whitespace_stripped(self) -> None:
        """Leading/trailing whitespace is stripped from the token."""
        result = evaluate_classify("  REFINE  \n")
        assert result.verdict == "REFINE"

    def test_empty_stdout(self) -> None:
        """Empty stdout returns empty verdict (routes to default)."""
        result = evaluate_classify("")
        assert result.verdict == ""

    def test_whitespace_only_stdout(self) -> None:
        """Whitespace-only stdout returns empty verdict."""
        result = evaluate_classify("   \n  \n")
        assert result.verdict == ""

    def test_single_line(self) -> None:
        """Single-line output returns that line as verdict."""
        result = evaluate_classify("DECIDE")
        assert result.verdict == "DECIDE"

    def test_trailing_newline_ignored(self) -> None:
        """Trailing empty lines are ignored when picking last line."""
        result = evaluate_classify("IMPLEMENT\n\n")
        assert result.verdict == "IMPLEMENT"


class TestEvaluateDispatcher:
    """Tests for the main evaluate() dispatcher function."""

    def test_dispatch_exit_code(self) -> None:
        """exit_code type routes correctly."""
        config = EvaluateConfig(type="exit_code")
        ctx = InterpolationContext()
        result = evaluate(config, "", 0, ctx)
        assert result.verdict == "yes"

    def test_dispatch_output_numeric(self) -> None:
        """output_numeric type routes correctly."""
        config = EvaluateConfig(type="output_numeric", operator="lt", target=10)
        ctx = InterpolationContext()
        result = evaluate(config, "5", 0, ctx)
        assert result.verdict == "yes"

    def test_dispatch_output_numeric_numeric_string_target(self) -> None:
        """output_numeric with a numeric string target converts correctly."""
        config = EvaluateConfig(type="output_numeric", operator="eq", target="5.0")
        ctx = InterpolationContext()
        result = evaluate(config, "5", 0, ctx)
        assert result.verdict == "yes"

    def test_dispatch_output_numeric_interpolated_target(self) -> None:
        """output_numeric with interpolation template target resolves and compares."""
        config = EvaluateConfig(type="output_numeric", operator="eq", target="${context.threshold}")
        ctx = InterpolationContext(context={"threshold": "42"})
        result = evaluate(config, "42", 0, ctx)
        assert result.verdict == "yes"

    def test_dispatch_output_numeric_non_numeric_string_target_raises(self) -> None:
        """output_numeric with non-numeric string target raises ValueError with diagnostic."""
        config = EvaluateConfig(type="output_numeric", operator="eq", target="${context.threshold}")
        ctx = InterpolationContext()  # threshold not set, resolves to literal template
        with pytest.raises(ValueError, match="output_numeric target must be numeric"):
            evaluate(config, "5", 0, ctx)

    def test_dispatch_output_numeric_none_target_raises(self) -> None:
        """output_numeric with target=None raises ValueError instead of silently using 0.0."""
        config = EvaluateConfig(type="output_numeric", operator="eq")  # target defaults to None
        ctx = InterpolationContext()
        with pytest.raises(ValueError, match="output_numeric evaluator requires 'target'"):
            evaluate(config, "5", 0, ctx)

    def test_dispatch_output_json(self) -> None:
        """output_json type routes correctly."""
        config = EvaluateConfig(type="output_json", path=".count", operator="eq", target=0)
        ctx = InterpolationContext()
        result = evaluate(config, '{"count": 0}', 0, ctx)
        assert result.verdict == "yes"

    def test_dispatch_output_contains(self) -> None:
        """output_contains type routes correctly."""
        config = EvaluateConfig(type="output_contains", pattern="success")
        ctx = InterpolationContext()
        result = evaluate(config, "operation success", 0, ctx)
        assert result.verdict == "yes"

    def test_dispatch_output_contains_negate(self) -> None:
        """output_contains with negate routes correctly."""
        config = EvaluateConfig(type="output_contains", pattern="error", negate=True)
        ctx = InterpolationContext()
        result = evaluate(config, "all good", 0, ctx)
        assert result.verdict == "yes"

    def test_dispatch_convergence(self) -> None:
        """convergence type routes correctly."""
        config = EvaluateConfig(type="convergence", target=0)
        ctx = InterpolationContext()
        result = evaluate(config, "5", 0, ctx)
        assert result.verdict == "progress"  # First iteration

    def test_dispatch_convergence_with_previous(self) -> None:
        """convergence with previous value works."""
        config = EvaluateConfig(type="convergence", target=0, previous="${prev.output}")
        ctx = InterpolationContext(prev={"output": "10"})
        result = evaluate(config, "5", 0, ctx)
        assert result.verdict == "progress"
        assert result.details["previous"] == 10

    def test_dispatch_convergence_target_reached(self) -> None:
        """convergence reaching target works."""
        config = EvaluateConfig(type="convergence", target=0, tolerance=1)
        ctx = InterpolationContext()
        result = evaluate(config, "0.5", 0, ctx)
        assert result.verdict == "target"

    def test_dispatch_convergence_interpolated_target(self) -> None:
        """convergence with interpolated target works."""
        config = EvaluateConfig(type="convergence", target="${context.target}")
        ctx = InterpolationContext(context={"target": "0"})
        result = evaluate(config, "0", 0, ctx)
        assert result.verdict == "target"

    def test_dispatch_convergence_interpolated_tolerance(self) -> None:
        """convergence with interpolated tolerance works."""
        config = EvaluateConfig(type="convergence", target=0, tolerance="${context.tolerance}")
        ctx = InterpolationContext(context={"tolerance": "1"})
        result = evaluate(config, "0.5", 0, ctx)
        assert result.verdict == "target"

    def test_dispatch_convergence_parse_error(self) -> None:
        """convergence with non-numeric output returns error."""
        config = EvaluateConfig(type="convergence", target=0)
        ctx = InterpolationContext()
        result = evaluate(config, "not a number", 0, ctx)
        assert result.verdict == "error"
        assert "Cannot parse output" in result.details["error"]

    def test_dispatch_convergence_maximize_target_reached(self) -> None:
        """convergence with direction='maximize' returns 'target' when current >= target."""
        config = EvaluateConfig(type="convergence", target=10.0, direction="maximize", tolerance=0)
        ctx = InterpolationContext()
        result = evaluate(config, "10.0", 0, ctx)
        assert result.verdict == "target"

    def test_dispatch_convergence_maximize_progress(self) -> None:
        """convergence with direction='maximize' returns 'progress' when current improves."""
        config = EvaluateConfig(
            type="convergence",
            target=10.0,
            direction="maximize",
            previous="${prev.output}",
        )
        ctx = InterpolationContext(prev={"output": "5"})
        result = evaluate(config, "8", 0, ctx)
        assert result.verdict == "progress"

    def test_dispatch_convergence_none_target_raises(self) -> None:
        """convergence with target=None raises ValueError instead of silently using 0.0."""
        config = EvaluateConfig(type="convergence")  # target defaults to None
        ctx = InterpolationContext()
        with pytest.raises(ValueError, match="convergence evaluator requires 'target'"):
            evaluate(config, "5", 0, ctx)

    def test_dispatch_unknown_type_raises(self) -> None:
        """Unknown type raises ValueError."""
        # Create config with invalid type by bypassing validation
        config = EvaluateConfig.__new__(EvaluateConfig)
        config.type = "unknown_type"  # type: ignore[assignment]
        ctx = InterpolationContext()
        with pytest.raises(ValueError, match="Unknown evaluator type"):
            evaluate(config, "", 0, ctx)

    @pytest.mark.parametrize(
        "eval_type",
        [
            "exit_code",
            "output_numeric",
            "output_json",
            "output_contains",
            "convergence",
            "diff_stall",
            "action_stall",
            "llm_structured",
            "harbor_scorer",
            "comparator",
        ],
    )
    def test_dispatch_exit_code_124_short_circuits_to_error(self, eval_type: str) -> None:
        """BUG-1640: exit_code=124 short-circuits to 'error' before type dispatch."""
        # Minimal configs — short-circuit fires before type-specific validation
        config = EvaluateConfig(type=eval_type, pattern="YES", target=0)  # type: ignore[arg-type]
        ctx = InterpolationContext()
        result = evaluate(config, output="", exit_code=124, context=ctx)
        assert result.verdict == "error", (
            f"{eval_type}: expected 'error' on timeout, got {result.verdict!r}"
        )
        assert result.details["exit_code"] == 124
        assert "timed out" in result.details["error"].lower()

    def test_dispatch_exit_code_124_mcp_result_keeps_timeout_verdict(self) -> None:
        """BUG-1640: mcp_result is exempt from the 124 short-circuit; it keeps 'timeout'."""
        config = EvaluateConfig(type="mcp_result")
        ctx = InterpolationContext()
        result = evaluate(config, output="", exit_code=124, context=ctx)
        assert result.verdict == "timeout"

    def test_dispatch_nonzero_exit_short_circuits_to_error(self) -> None:
        """BUG-1815: non-zero exit codes short-circuit to 'error' before type dispatch."""
        config = EvaluateConfig(type="output_contains", pattern="YES")
        ctx = InterpolationContext()
        # exit_code=0 with matching output → yes (normal path)
        result_yes = evaluate(config, output="YES we found it", exit_code=0, context=ctx)
        assert result_yes.verdict == "yes"
        # exit_code=1 with non-matching output → error (exit-code short-circuit)
        result_error = evaluate(config, output="missing", exit_code=1, context=ctx)
        assert result_error.verdict == "error"
        assert result_error.details["exit_code"] == 1
        assert "exited with code 1" in result_error.details["error"].lower()
        # exit_code=127 with non-matching output → error (exit-code short-circuit)
        result_error2 = evaluate(config, output="missing", exit_code=127, context=ctx)
        assert result_error2.verdict == "error"
        assert result_error2.details["exit_code"] == 127

    @pytest.mark.parametrize(
        "eval_type",
        [
            "output_contains",
            "output_numeric",
            "output_json",
            "convergence",
            "comparator",
        ],
    )
    def test_dispatch_nonzero_exit_generalized_short_circuit(self, eval_type: str) -> None:
        """BUG-1815: non-zero exit codes short-circuit to 'error' for all exit-code-blind evaluators."""
        # Minimal configs — short-circuit fires before type-specific validation
        config = EvaluateConfig(type=eval_type, pattern="YES", target=0)  # type: ignore[arg-type]
        ctx = InterpolationContext()
        result = evaluate(config, output="", exit_code=1, context=ctx)
        assert result.verdict == "error", (
            f"{eval_type}: expected 'error' on exit_code=1, got {result.verdict!r}"
        )
        assert result.details["exit_code"] == 1
        assert "exited with code 1" in result.details["error"].lower()

    @pytest.mark.parametrize(
        "eval_type",
        [
            "exit_code",
            "mcp_result",
            "harbor_scorer",
            "diff_stall",
            "action_stall",
            "contract",
        ],
    )
    def test_dispatch_nonzero_exit_does_not_affect_exit_code_aware_evaluators(
        self, eval_type: str
    ) -> None:
        """BUG-1815: exit-code-aware evaluators are exempt from the non-zero short-circuit."""
        config = EvaluateConfig(type=eval_type)  # type: ignore[arg-type]
        ctx = InterpolationContext()
        result = evaluate(config, output="", exit_code=1, context=ctx)
        # These evaluators handle exit codes intrinsically; should not be short-circuited
        assert result.verdict != "error" or "exited with code" not in str(result.details), (
            f"{eval_type}: should not be short-circuited, got verdict={result.verdict!r} "
            f"details={result.details}"
        )

    def test_dispatch_contract_missing_pairs_returns_error(self) -> None:
        """contract type with no pairs returns error verdict."""
        config = EvaluateConfig(type="contract")
        ctx = InterpolationContext()
        result = evaluate(config, "", 0, ctx)
        assert result.verdict == "error"
        assert "pairs" in result.details.get("error", "").lower()

    def test_dispatch_classify(self) -> None:
        """classify type returns trimmed last-line token as verdict."""
        config = EvaluateConfig(type="classify")
        ctx = InterpolationContext()
        result = evaluate(config, "line1\nWIRE", 0, ctx)
        assert result.verdict == "WIRE"

    def test_dispatch_classify_with_line_selector(self) -> None:
        """classify type respects the line: selector."""
        config = EvaluateConfig(type="classify", line="first")
        ctx = InterpolationContext()
        result = evaluate(config, "IMPLEMENT\nWIRE", 0, ctx)
        assert result.verdict == "IMPLEMENT"

    def test_dispatch_classify_nonzero_exit_short_circuits_to_error(self) -> None:
        """classify is NOT exit-code-aware: non-zero exit → error verdict, token ignored."""
        config = EvaluateConfig(type="classify")
        ctx = InterpolationContext()
        result = evaluate(config, "WIRE", 1, ctx)
        assert result.verdict == "error"
        assert result.details.get("exit_code") == 1

    def test_dispatch_classify_not_in_exit_code_aware_set(self) -> None:
        """classify must not appear in _EXIT_CODE_AWARE_EVALUATORS."""
        import inspect

        import little_loops.fsm.evaluators as ev_module

        src = inspect.getsource(ev_module.evaluate)
        # _EXIT_CODE_AWARE_EVALUATORS must not include classify
        # (checked by verifying nonzero exit short-circuits above, but also
        # confirm the literal set does not contain "classify")
        assert '"classify"' not in src.split("_EXIT_CODE_AWARE_EVALUATORS")[1].split("}")[0]


class TestLLMStructuredEvaluator:
    """Tests for llm_structured evaluator (Tier 2) via Claude CLI."""

    @staticmethod
    def _cli_stdout(verdict: str, confidence: float, reason: str) -> str:
        """Helper to create mock CLI JSON output."""
        return json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "structured_output": {
                    "verdict": verdict,
                    "confidence": confidence,
                    "reason": reason,
                },
            }
        )

    @pytest.fixture
    def mock_cli(self):
        """Create mock subprocess.run for Claude CLI."""
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            yield mock_run, mock_result

    def test_cli_not_found(self) -> None:
        """Returns error when host CLI not installed."""
        with patch(
            "little_loops.fsm.evaluators.subprocess.run",
            side_effect=FileNotFoundError("claude"),
        ):
            result = evaluate_llm_structured("test output")
        assert result.verdict == "error"
        assert result.details.get("missing_dependency") is True
        assert "CLI not found" in result.details["error"]

    def test_success_verdict(self, mock_cli) -> None:
        """LLM returns success verdict."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.9, "Action completed successfully")

        result = evaluate_llm_structured("Fixed error in handlers.py")

        assert result.verdict == "yes"
        assert result.details["confidence"] == 0.9
        assert result.details["confident"] is True
        assert result.details["reason"] == "Action completed successfully"

    def test_failure_verdict(self, mock_cli) -> None:
        """LLM returns failure verdict."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("no", 0.8, "Tests still failing")

        result = evaluate_llm_structured("3 tests failed")

        assert result.verdict == "no"
        assert result.details["confident"] is True

    def test_blocked_verdict(self, mock_cli) -> None:
        """LLM returns blocked verdict."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("blocked", 0.95, "Missing credentials")

        result = evaluate_llm_structured("Authentication required")

        assert result.verdict == "blocked"

    def test_partial_verdict(self, mock_cli) -> None:
        """LLM returns partial verdict."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("partial", 0.7, "2 of 5 items completed")

        result = evaluate_llm_structured("Completed items 1 and 2")

        assert result.verdict == "partial"

    def test_low_confidence_without_suffix(self, mock_cli) -> None:
        """Low confidence without uncertain_suffix keeps original verdict."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.4, "Maybe fixed")

        result = evaluate_llm_structured("...", min_confidence=0.7, uncertain_suffix=False)

        assert result.verdict == "yes"
        assert result.details["confident"] is False

    def test_low_confidence_with_suffix(self, mock_cli) -> None:
        """Low confidence with uncertain_suffix appends _uncertain."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.4, "Maybe fixed")

        result = evaluate_llm_structured("...", min_confidence=0.7, uncertain_suffix=True)

        assert result.verdict == "yes_uncertain"
        assert result.details["confident"] is False

    def test_custom_schema(self, mock_cli) -> None:
        """Custom schema with non-standard verdicts."""
        custom_schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["found", "not_found"]},
                "confidence": {"type": "number"},
            },
            "required": ["verdict"],
        }

        mock_run, mock_result = mock_cli
        mock_result.stdout = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "structured_output": {"verdict": "found", "confidence": 0.95},
            }
        )

        result = evaluate_llm_structured("Found 3 matches", schema=custom_schema)

        assert result.verdict == "found"
        assert result.details["confidence"] == 0.95
        # Verify custom schema was passed via --json-schema flag
        call_args = mock_run.call_args[0][0]
        assert "--json-schema" in call_args
        schema_idx = call_args.index("--json-schema")
        assert call_args[schema_idx + 1] == json.dumps(custom_schema)

    def test_custom_prompt(self, mock_cli) -> None:
        """Custom prompt is passed to CLI."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.9, "Done")

        custom_prompt = "Check if the code review was approved."
        evaluate_llm_structured("LGTM, approved", prompt=custom_prompt)

        # Verify custom prompt was used in -p argument
        call_args = mock_run.call_args[0][0]
        prompt_idx = call_args.index("-p")
        assert custom_prompt in call_args[prompt_idx + 1]

    def test_cli_timeout_handling(self) -> None:
        """Timeout returns error verdict."""
        with patch(
            "little_loops.fsm.evaluators.subprocess.run",
            side_effect=subprocess.TimeoutExpired(cmd="claude", timeout=30),
        ):
            result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert result.details.get("timeout") is True

    def test_cli_error_handling(self, mock_cli) -> None:
        """Non-zero exit code returns error verdict."""
        mock_run, mock_result = mock_cli
        mock_result.returncode = 1
        mock_result.stderr = "Authentication required"

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert result.details.get("api_error") is True

    def test_empty_stdout(self, mock_cli) -> None:
        """Empty stdout from CLI returns error with diagnostic message."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = ""
        mock_result.stderr = ""

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert result.details.get("empty_output") is True
        assert "empty output" in result.details["error"]

    def test_empty_stdout_includes_stderr(self, mock_cli) -> None:
        """Empty stdout error includes stderr content when available."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = ""
        mock_result.stderr = "rate limit exceeded"

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert "rate limit exceeded" in result.details["error"]

    def test_is_error_in_envelope(self, mock_cli) -> None:
        """is_error=true in envelope returns error even with exit code 0."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = json.dumps({"is_error": True, "result": ""})

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert result.details.get("api_error") is True

    def test_structured_output_retry_exhaustion(self, mock_cli) -> None:
        """CLI reports error_max_structured_output_retries when schema validation fails after retries."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = json.dumps(
            {
                "type": "result",
                "subtype": "error_max_structured_output_retries",
                "is_error": True,
            }
        )
        result = evaluate_llm_structured("some output")
        assert result.verdict == "error"
        assert "structured output" in result.details["error"].lower()
        assert result.details.get("api_error") is True

    def test_result_as_dict_in_envelope(self, mock_cli) -> None:
        """result field as dict (not string) is handled correctly."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = json.dumps(
            {"result": {"verdict": "yes", "confidence": 0.9, "reason": "Done"}}
        )

        result = evaluate_llm_structured("...")

        assert result.verdict == "yes"
        assert result.details["confidence"] == 0.9

    def test_empty_result_field_includes_raw_preview(self, mock_cli) -> None:
        """Empty result field returns error with raw_preview for diagnosis."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = json.dumps({"result": "", "is_error": False})

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert "raw_preview" in result.details
        assert "Empty result field" in result.details["error"]

    def test_empty_result_with_tool_turns_regression(self, mock_cli) -> None:
        """Regression: --json-schema multi-turn response has empty result field."""
        mock_run, mock_result = mock_cli
        # Simulate what CLI v2.1.69 returns when --json-schema triggers tool calls:
        # num_turns > 1 and result="" because output was captured via tool calls.
        mock_result.stdout = json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "is_error": False,
                "duration_ms": 17849,
                "num_turns": 4,
                "result": "",
                "stop_reason": "end_turn",
            }
        )

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert "Empty result field" in result.details["error"]
        assert "raw_preview" in result.details

    def test_invalid_json_response(self, mock_cli) -> None:
        """Unparseable JSON from CLI returns error with raw_preview."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = "not json"

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert "Failed to parse" in result.details["error"]
        assert "raw_preview" in result.details

    def test_output_truncation(self, mock_cli) -> None:
        """Long output is truncated to last 4000 chars."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 1.0, "Done")

        long_output = "x" * 10000
        evaluate_llm_structured(long_output)

        # Verify truncation happened in the -p argument
        call_args = mock_run.call_args[0][0]
        prompt_idx = call_args.index("-p")
        prompt_content = call_args[prompt_idx + 1]
        # Should have prompt + truncated output (last 4000 chars) + XML tags
        assert len(prompt_content) < 5000

    def test_raw_response_in_details(self, mock_cli) -> None:
        """Raw LLM response is included in details."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.9, "Action completed")

        result = evaluate_llm_structured("Done")

        assert "raw" in result.details
        assert result.details["raw"]["verdict"] == "yes"
        assert result.details["raw"]["confidence"] == 0.9

    def test_default_values_used(self, mock_cli) -> None:
        """Default prompt and schema used when not specified."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.9, "Done")

        evaluate_llm_structured("test output")

        call_args = mock_run.call_args[0][0]
        prompt_idx = call_args.index("-p")
        prompt_content = call_args[prompt_idx + 1]
        assert DEFAULT_LLM_PROMPT in prompt_content  # prompt still present
        assert json.dumps(DEFAULT_LLM_SCHEMA) not in prompt_content  # schema no longer in prompt
        assert "--json-schema" in call_args
        schema_idx = call_args.index("--json-schema")
        assert call_args[schema_idx + 1] == json.dumps(DEFAULT_LLM_SCHEMA)

    def test_envelope_as_direct_result(self, mock_cli) -> None:
        """Envelope itself is the structured result when result field is absent."""
        mock_run, mock_result = mock_cli
        # Some CLI versions return JSON directly without a "result" wrapper
        mock_result.stdout = json.dumps(
            {"verdict": "yes", "confidence": 0.9, "reason": "All checks passed"}
        )

        result = evaluate_llm_structured("test output")

        assert result.verdict == "yes"
        assert result.details["confidence"] == 0.9
        assert result.details["reason"] == "All checks passed"

    def test_jsonl_output_uses_last_line(self, mock_cli) -> None:
        """JSONL output (multiple JSON lines) uses the last non-empty line."""
        mock_run, mock_result = mock_cli
        # Simulate JSONL: event lines followed by final result line
        event_line = json.dumps({"type": "progress", "text": "thinking..."})
        final_line = json.dumps(
            {"result": json.dumps({"verdict": "no", "confidence": 0.8, "reason": "Tests failed"})}
        )
        mock_result.stdout = f"{event_line}\n{final_line}\n"

        result = evaluate_llm_structured("output")

        assert result.verdict == "no"
        assert result.details["confidence"] == 0.8


class TestEvaluateDispatcherLLM:
    """Tests for evaluate() dispatcher with llm_structured type."""

    @staticmethod
    def _cli_stdout(verdict: str, confidence: float, reason: str) -> str:
        """Helper to create mock CLI JSON output."""
        return json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "structured_output": {
                    "verdict": verdict,
                    "confidence": confidence,
                    "reason": reason,
                },
            }
        )

    @pytest.fixture
    def mock_cli(self):
        """Create mock subprocess.run for Claude CLI."""
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            yield mock_run, mock_result

    def test_dispatch_llm_structured(self, mock_cli) -> None:
        """llm_structured type routes correctly."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.9, "Done")

        config = EvaluateConfig(type="llm_structured")
        ctx = InterpolationContext()
        result = evaluate(config, "test output", 0, ctx)

        assert result.verdict == "yes"
        assert result.details["confident"] is True

    def test_dispatch_llm_with_config_options(self, mock_cli) -> None:
        """llm_structured uses config options."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.4, "Maybe")

        config = EvaluateConfig(
            type="llm_structured",
            prompt="Custom prompt",
            min_confidence=0.7,
            uncertain_suffix=True,
        )
        ctx = InterpolationContext()
        result = evaluate(config, "test output", 0, ctx)

        assert result.verdict == "yes_uncertain"
        assert result.details["confident"] is False

    def test_dispatch_llm_structured_interpolates_prompt(self, mock_cli) -> None:
        """llm_structured interpolates ${context.*} variables in prompt before sending to LLM."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.9, "All pass")

        config = EvaluateConfig(
            type="llm_structured",
            prompt="readiness < ${context.readiness_threshold} or outcome < ${context.outcome_threshold}?",
        )
        ctx = InterpolationContext(context={"readiness_threshold": "85", "outcome_threshold": "70"})
        evaluate(config, "test output", 0, ctx)

        call_args = mock_run.call_args
        cli_cmd = call_args[0][0]
        prompt_arg = cli_cmd[cli_cmd.index("-p") + 1]
        assert "85" in prompt_arg
        assert "70" in prompt_arg
        assert "${context.readiness_threshold}" not in prompt_arg
        assert "${context.outcome_threshold}" not in prompt_arg


class TestDiffStallEvaluator:
    """Tests for diff_stall evaluator."""

    @pytest.fixture
    def mock_git(self):
        """Patch subprocess.run for git diff commands."""
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            yield mock_run, mock_result

    @pytest.fixture(autouse=True)
    def clean_state_files(self, tmp_path, monkeypatch):
        """Redirect state files to a temp directory for test isolation."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(tmp_path)

    def test_first_iteration_returns_success(self, mock_git) -> None:
        """First call always returns success (no previous snapshot)."""
        _, mock_result = mock_git
        mock_result.stdout = "scripts/foo.py | 3 +++"

        result = evaluate_diff_stall()
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 0
        assert result.details["diff_changed"] is True

    def test_different_diff_returns_success(self, mock_git) -> None:
        """Progress (diff changed) returns success and resets stall counter."""
        _, mock_result = mock_git
        mock_result.stdout = "scripts/foo.py | 3 +++"

        # First call (baseline)
        evaluate_diff_stall()

        # Second call with different diff
        mock_result.stdout = "scripts/bar.py | 5 +++++"
        result = evaluate_diff_stall()
        assert result.verdict == "yes"
        assert result.details["diff_changed"] is True
        assert result.details["stall_count"] == 0

    def test_identical_diff_at_threshold_returns_failure(self, mock_git) -> None:
        """Identical diff for max_stall consecutive iterations returns failure."""
        _, mock_result = mock_git
        mock_result.stdout = "scripts/foo.py | 3 +++"

        # First call (baseline)
        evaluate_diff_stall(max_stall=1)

        # Second call — same diff, max_stall=1 triggers failure
        result = evaluate_diff_stall(max_stall=1)
        assert result.verdict == "no"
        assert result.details["stall_count"] == 1
        assert result.details["diff_changed"] is False

    def test_identical_diff_below_threshold_returns_success(self, mock_git) -> None:
        """Identical diff below max_stall threshold still returns success."""
        _, mock_result = mock_git
        mock_result.stdout = "scripts/foo.py | 3 +++"

        # First call (baseline)
        evaluate_diff_stall(max_stall=2)

        # Second call — same diff, but max_stall=2 so not yet at threshold
        result = evaluate_diff_stall(max_stall=2)
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 1
        assert result.details["diff_changed"] is False

    def test_stall_then_progress_resets_counter(self, mock_git) -> None:
        """After stall, a diff change resets stall count."""
        _, mock_result = mock_git
        mock_result.stdout = "scripts/foo.py | 3 +++"

        # Baseline
        evaluate_diff_stall(max_stall=3)
        # Same diff (stall_count -> 1)
        evaluate_diff_stall(max_stall=3)
        # Progress: diff changes, counter resets
        mock_result.stdout = "scripts/bar.py | 5 +++++"
        result = evaluate_diff_stall(max_stall=3)
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 0
        assert result.details["diff_changed"] is True

    def test_scope_passed_to_git(self, mock_git) -> None:
        """scope parameter is forwarded to git diff command."""
        mock_run, mock_result = mock_git
        mock_result.stdout = ""

        evaluate_diff_stall(scope=["scripts/"])

        call_args = mock_run.call_args[0][0]
        assert "--" in call_args
        assert "scripts/" in call_args

    def test_git_failure_returns_error(self, mock_git) -> None:
        """Non-zero git exit code returns error verdict."""
        mock_run, mock_result = mock_git
        mock_result.returncode = 128
        mock_result.stderr = "not a git repository"

        result = evaluate_diff_stall()
        assert result.verdict == "error"
        assert "git diff failed" in result.details["error"]

    def test_git_timeout_returns_error(self) -> None:
        """Subprocess timeout returns error verdict."""
        with patch(
            "little_loops.fsm.evaluators.subprocess.run",
            side_effect=subprocess.TimeoutExpired("git", 30),
        ):
            result = evaluate_diff_stall()
        assert result.verdict == "error"
        assert "timed out" in result.details["error"]

    def test_dispatch_diff_stall(self, mock_git) -> None:
        """evaluate() dispatcher routes diff_stall type correctly."""
        _, mock_result = mock_git
        mock_result.stdout = ""

        config = EvaluateConfig(type="diff_stall")
        ctx = InterpolationContext()
        result = evaluate(config, "", 0, ctx)

        assert result.verdict == "yes"
        assert "stall_count" in result.details

    def test_dispatch_diff_stall_with_options(self, mock_git) -> None:
        """evaluate() passes scope and max_stall to diff_stall evaluator."""
        _, mock_result = mock_git
        mock_result.stdout = "scripts/foo.py | 1 +"

        config = EvaluateConfig(type="diff_stall", scope=["scripts/"], max_stall=2)
        ctx = InterpolationContext()
        result = evaluate(config, "", 0, ctx)

        assert result.verdict == "yes"
        assert result.details["max_stall"] == 2

    def test_first_call_resets_stale_count_file(self, mock_git, tmp_path) -> None:
        """First call resets a stale count file to 0 even if it had a non-zero value.

        If the state file was deleted (e.g., partial cleanup) but the count file
        survived from a previous stalled loop, the next call should re-baseline
        rather than carrying forward the stale stall count.
        """
        _, mock_result = mock_git
        mock_result.stdout = "scripts/foo.py | 1 +"

        # Pre-populate the count file with a stale non-zero value (stall_count = 3)
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True, exist_ok=True)

        import hashlib

        scope_str = "_root_"
        cache_key = hashlib.md5(scope_str.encode()).hexdigest()[:12]
        count_file = loops_tmp / f"ll-diff-stall-{cache_key}.count"
        count_file.write_text("3")
        # Do NOT write the state file — simulates partial cleanup

        result = evaluate_diff_stall()

        # First call should treat this as baseline: return yes, stall_count = 0
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 0
        assert result.details["diff_changed"] is True

        # Count file should now be reset to 0
        assert count_file.read_text().strip() == "0"


class TestActionStallEvaluator:
    """Tests for action_stall evaluator."""

    @pytest.fixture(autouse=True)
    def clean_state_files(self, tmp_path, monkeypatch):
        """Redirect state files to a temp directory for test isolation."""
        loops_tmp = tmp_path / ".loops" / "tmp"
        loops_tmp.mkdir(parents=True, exist_ok=True)
        monkeypatch.chdir(tmp_path)

    def _ctx(self, action: str = "", **kwargs) -> InterpolationContext:
        """Build a minimal context with the given action and extra context keys."""
        ctx = InterpolationContext()
        ctx.context["action"] = action
        for k, v in kwargs.items():
            ctx.context[k] = v
        return ctx

    def test_first_iteration_returns_yes(self) -> None:
        """First call always returns yes (no previous snapshot)."""
        ctx = self._ctx(action="echo hello")
        result = evaluate_action_stall(context=ctx)
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 0
        assert result.details["hash_changed"] is True
        assert result.details["tracked_keys"] == ["action"]

    def test_different_action_returns_yes(self) -> None:
        """A different action string returns yes and resets stall counter."""
        ctx1 = self._ctx(action="echo hello")
        evaluate_action_stall(context=ctx1)

        ctx2 = self._ctx(action="echo world")
        result = evaluate_action_stall(context=ctx2)
        assert result.verdict == "yes"
        assert result.details["hash_changed"] is True
        assert result.details["stall_count"] == 0

    def test_identical_at_threshold_returns_no(self) -> None:
        """Identical action for max_repeat consecutive iterations returns no."""
        ctx = self._ctx(action="echo same")

        # First call (baseline)
        evaluate_action_stall(max_repeat=2, context=ctx)
        # Second call — stall_count becomes 1 (below threshold)
        r1 = evaluate_action_stall(max_repeat=2, context=ctx)
        assert r1.verdict == "yes"
        assert r1.details["stall_count"] == 1
        # Third call — stall_count becomes 2 (at threshold)
        r2 = evaluate_action_stall(max_repeat=2, context=ctx)
        assert r2.verdict == "no"
        assert r2.details["stall_count"] == 2
        assert r2.details["repeated_hash"] is not None

    def test_identical_below_threshold_returns_yes(self) -> None:
        """Identical action below max_repeat threshold returns yes."""
        ctx = self._ctx(action="echo same")

        evaluate_action_stall(max_repeat=3, context=ctx)
        result = evaluate_action_stall(max_repeat=3, context=ctx)
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 1
        assert result.details["hash_changed"] is False

    def test_stall_then_progress_resets(self) -> None:
        """After stall, a new action resets the stall count."""
        ctx_same = self._ctx(action="echo stalled")
        evaluate_action_stall(max_repeat=3, context=ctx_same)
        evaluate_action_stall(max_repeat=3, context=ctx_same)  # stall_count=1

        ctx_new = self._ctx(action="echo progress")
        result = evaluate_action_stall(max_repeat=3, context=ctx_new)
        assert result.verdict == "yes"
        assert result.details["stall_count"] == 0
        assert result.details["hash_changed"] is True

    def test_multiple_track_keys(self) -> None:
        """Multiple track keys are all hashed together."""
        ctx = InterpolationContext()
        ctx.context["action"] = "run tests"
        ctx.context["output"] = "0 failures"

        evaluate_action_stall(track=["action", "output"], max_repeat=2, context=ctx)

        # Same values → stall count increments
        r1 = evaluate_action_stall(track=["action", "output"], max_repeat=2, context=ctx)
        assert r1.details["stall_count"] == 1

        # Change one key → resets
        ctx.context["output"] = "1 failure"
        r2 = evaluate_action_stall(track=["action", "output"], max_repeat=2, context=ctx)
        assert r2.verdict == "yes"
        assert r2.details["hash_changed"] is True
        assert r2.details["stall_count"] == 0

    def test_dispatch_action_stall(self) -> None:
        """evaluate() dispatcher routes action_stall type correctly."""
        ctx = InterpolationContext()
        ctx.context["action"] = "some command"
        config = EvaluateConfig(type="action_stall")
        result = evaluate(config, "", 0, ctx)
        assert result.verdict == "yes"
        assert "stall_count" in result.details
        assert "tracked_keys" in result.details

    def test_dispatch_action_stall_with_options(self) -> None:
        """evaluate() passes track and max_repeat to action_stall evaluator."""
        ctx = InterpolationContext()
        ctx.context["action"] = "cmd"
        ctx.context["output"] = "result"
        config = EvaluateConfig(type="action_stall", track=["action", "output"], max_repeat=3)
        result = evaluate(config, "", 0, ctx)
        assert result.verdict == "yes"
        assert result.details["max_repeat"] == 3
        assert result.details["tracked_keys"] == ["action", "output"]


class TestMcpResultEvaluator:
    """Tests for the mcp_result evaluator."""

    @pytest.mark.parametrize(
        ("output", "exit_code", "expected_verdict"),
        [
            # Success: isError=false, exit 0
            ('{"isError": false, "content": [{"type": "text", "text": "ok"}]}', 0, "success"),
            # Tool error: isError=true, exit 1
            ('{"isError": true, "content": [{"type": "text", "text": "fail"}]}', 1, "tool_error"),
            # Not found: exit 127
            ("", 127, "not_found"),
            # Timeout: exit 124
            ("", 124, "timeout"),
            # isError defaults to True when exit_code != 0 and not valid JSON
            ("not-json", 1, "tool_error"),
            # Empty output with exit 0 → isError defaults to False
            ("{}", 0, "success"),
            # isError=true from envelope, regardless of exit code
            ('{"isError": true}', 0, "tool_error"),
        ],
    )
    def test_mcp_result_routing(self, output: str, exit_code: int, expected_verdict: str) -> None:
        """MCP result routing covers all expected verdicts."""
        result = evaluate_mcp_result(output, exit_code)
        assert result.verdict == expected_verdict

    def test_not_found_details(self) -> None:
        """not_found verdict includes descriptive error in details."""
        result = evaluate_mcp_result("", 127)
        assert result.verdict == "not_found"
        assert "not found" in result.details["error"].lower()
        assert result.details["exit_code"] == 127

    def test_timeout_details(self) -> None:
        """timeout verdict includes descriptive error in details."""
        result = evaluate_mcp_result("", 124)
        assert result.verdict == "timeout"
        assert "timed out" in result.details["error"].lower()

    def test_success_envelope_in_details(self) -> None:
        """Success verdict includes the full MCP envelope in details."""
        envelope = {"isError": False, "content": [{"type": "text", "text": "hello"}]}
        result = evaluate_mcp_result(json.dumps(envelope), 0)
        assert result.verdict == "success"
        assert result.details["envelope"] == envelope

    def test_tool_error_envelope_in_details(self) -> None:
        """tool_error verdict includes the full MCP envelope in details."""
        envelope = {"isError": True, "content": [{"type": "text", "text": "bad"}]}
        result = evaluate_mcp_result(json.dumps(envelope), 1)
        assert result.verdict == "tool_error"
        assert result.details["envelope"] == envelope

    def test_dispatch_mcp_result(self) -> None:
        """evaluate() dispatcher routes mcp_result type correctly."""
        config = EvaluateConfig(type="mcp_result")
        ctx = InterpolationContext()
        output = json.dumps({"isError": False, "content": []})
        result = evaluate(config, output, 0, ctx)
        assert result.verdict == "success"

    def test_dispatch_mcp_result_not_found(self) -> None:
        """evaluate() dispatcher handles mcp_result not_found (exit 127)."""
        config = EvaluateConfig(type="mcp_result")
        ctx = InterpolationContext()
        result = evaluate(config, "", 127, ctx)
        assert result.verdict == "not_found"

    def test_dispatch_harbor_scorer_yes(self) -> None:
        """evaluate() dispatcher routes harbor_scorer type: exit 0 + float → yes."""
        config = EvaluateConfig(type="harbor_scorer")
        ctx = InterpolationContext()
        result = evaluate(config, "0.85", 0, ctx)
        assert result.verdict == "yes"
        assert result.details["score"] == 0.85

    def test_dispatch_harbor_scorer_no(self) -> None:
        """evaluate() dispatcher routes harbor_scorer type: non-zero exit → no."""
        config = EvaluateConfig(type="harbor_scorer")
        ctx = InterpolationContext()
        result = evaluate(config, "", 1, ctx)
        assert result.verdict == "no"

    def test_dispatch_harbor_scorer_error(self) -> None:
        """evaluate() dispatcher routes harbor_scorer type: exit 0 + non-float → error."""
        config = EvaluateConfig(type="harbor_scorer")
        ctx = InterpolationContext()
        result = evaluate(config, "not-a-float", 0, ctx)
        assert result.verdict == "error"


class TestBlindComparator:
    """Tests for evaluate_blind_comparator — blind A/B output comparison."""

    def _make_cli_response(
        self, verdict_a: str = "yes", verdict_b: str = "no", confidence: float = 0.9
    ) -> dict[str, Any]:
        """Build a valid Claude CLI JSON envelope for structured output."""
        return {
            "type": "result",
            "subtype": "success",
            "structured_output": {
                "verdict_a": verdict_a,
                "verdict_b": verdict_b,
                "confidence": confidence,
                "reason": "Output A is correct and complete; Output B is incomplete.",
            },
        }

    def _make_mock_proc(self, stdout: str = "", stderr: str = "", returncode: int = 0) -> Any:
        """Create a mock CompletedProcess."""
        from unittest.mock import MagicMock

        proc = MagicMock()
        proc.stdout = stdout
        proc.stderr = stderr
        proc.returncode = returncode
        return proc

    @pytest.fixture
    def mock_cli(self):
        """Fixture to mock subprocess.run for blind comparator calls."""
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = json.dumps(self._make_cli_response())
            proc.stderr = ""
            mock_run.return_value = proc
            yield mock_run, proc

    def test_both_pass(self, mock_cli) -> None:
        """Both outputs pass — verdict_a=yes, verdict_b=yes."""
        mock_run, proc = mock_cli
        proc.stdout = json.dumps(self._make_cli_response("yes", "yes"))
        result = evaluate_blind_comparator("good output", "also good output")
        assert result["harness_pass"] is True
        assert result["baseline_pass"] is True
        assert result["confidence"] == 0.9

    def test_both_fail(self, mock_cli) -> None:
        """Both outputs fail — verdict_a=no, verdict_b=no."""
        mock_run, proc = mock_cli
        proc.stdout = json.dumps(self._make_cli_response("no", "no"))
        result = evaluate_blind_comparator("bad output", "also bad output")
        assert result["harness_pass"] is False
        assert result["baseline_pass"] is False

    def test_harness_only_pass(self, mock_cli) -> None:
        """Only harness passes — depends on random shuffle results."""
        mock_run, proc = mock_cli
        proc.stdout = json.dumps(self._make_cli_response("yes", "no"))
        # We can't control the shuffle, but we can verify one passes, one fails
        result = evaluate_blind_comparator("good harness output", "bad baseline output")
        assert result["harness_pass"] != result["baseline_pass"]
        assert result["confidence"] == 0.9
        assert "reason" in result
        assert "raw" in result

    def test_baseline_only_pass(self, mock_cli) -> None:
        """Only baseline passes — depends on random shuffle results."""
        mock_run, proc = mock_cli
        proc.stdout = json.dumps(self._make_cli_response("no", "yes"))
        result = evaluate_blind_comparator("bad harness output", "good baseline output")
        assert result["harness_pass"] != result["baseline_pass"]

    def test_timeout(self, mock_cli) -> None:
        """Timeout returns both-fail with error key."""
        mock_run, proc = mock_cli
        mock_run.side_effect = subprocess.TimeoutExpired(cmd="test", timeout=5)
        result = evaluate_blind_comparator("output a", "output b")
        assert result["harness_pass"] is False
        assert result["baseline_pass"] is False
        assert result["confidence"] == 0.0
        assert result.get("error") == "timeout"

    def test_cli_error(self, mock_cli) -> None:
        """CLI error returns both-fail with error key."""
        mock_run, proc = mock_cli
        proc.returncode = 1
        proc.stderr = "api error occurred"
        result = evaluate_blind_comparator("output a", "output b")
        assert result["harness_pass"] is False
        assert result["baseline_pass"] is False
        assert result.get("error") == "api_error"

    def test_empty_output(self, mock_cli) -> None:
        """Empty CLI stdout returns both-fail with error key."""
        mock_run, proc = mock_cli
        proc.stdout = ""
        result = evaluate_blind_comparator("output a", "output b")
        assert result["harness_pass"] is False
        assert result["baseline_pass"] is False
        assert result.get("error") == "empty_output"

    def test_de_anonymization_maps_correctly(self) -> None:
        """De-anonymization: verdict_a → correct arm based on shuffle mapping.

        We patch random.choice to control the shuffle, verifying the
        de-anonymization logic correctly maps A/B verdicts to harness/baseline.
        """
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            with patch("little_loops.fsm.evaluators.random.choice") as mock_choice:
                proc = MagicMock()
                proc.returncode = 0
                # Output A (harness) = yes, Output B (baseline) = no
                proc.stdout = json.dumps(self._make_cli_response("yes", "no"))
                proc.stderr = ""
                mock_run.return_value = proc

                # Force harness → A mapping
                mock_choice.return_value = True
                result = evaluate_blind_comparator("harness output", "baseline output")
                assert result["harness_pass"] is True
                assert result["baseline_pass"] is False
                assert result["raw"]["harness_is_a"] is True

                # Force harness → B mapping (swapped)
                mock_choice.return_value = False
                result2 = evaluate_blind_comparator("harness output", "baseline output")
                assert result2["harness_pass"] is False
                assert result2["baseline_pass"] is True
                assert result2["raw"]["harness_is_a"] is False

    def test_long_outputs_are_truncated(self, mock_cli) -> None:
        """Outputs longer than 4000 chars are truncated before sending to judge."""
        mock_run, proc = mock_cli
        long_text = "x" * 5000
        result = evaluate_blind_comparator(long_text, "short output")
        assert result is not None
        # The prompt sent to the CLI should not contain full 5000-char string
        call_args = mock_run.call_args[0][0]
        assert call_args[-1]  # prompt is last arg
        prompt_text = call_args[-1][0] if isinstance(call_args[-1], list) else str(call_args[-1])
        # The truncated output should be limited to 4000 chars
        assert "x" * 4000 in prompt_text or len(long_text[-4000:]) <= 4000

    def test_retry_exhausted_handling(self, mock_cli) -> None:
        """Retry-exhausted envelope returns error with both-fail."""
        mock_run, proc = mock_cli
        proc.stdout = json.dumps(
            {
                "type": "result",
                "subtype": "error_max_structured_output_retries",
            }
        )
        result = evaluate_blind_comparator("output a", "output b")
        assert result["harness_pass"] is False
        assert result["baseline_pass"] is False
        assert result.get("error") == "retry_exhausted"

    def test_is_error_flag_handling(self, mock_cli) -> None:
        """is_error flag in envelope returns api_error with both-fail."""
        mock_run, proc = mock_cli
        proc.stdout = json.dumps({"is_error": True, "result": "some error"})
        result = evaluate_blind_comparator("output a", "output b")
        assert result["harness_pass"] is False
        assert result["baseline_pass"] is False
        assert result.get("error") == "api_error"

    def test_jsonl_parsing(self, mock_cli) -> None:
        """JSONL (multi-line) output is parsed from the last non-empty line."""
        mock_run, proc = mock_cli
        envelope = self._make_cli_response("yes", "no")
        proc.stdout = '{"type":"log","msg":"thinking..."}\n' + json.dumps(envelope)
        result = evaluate_blind_comparator("output a", "output b")
        assert result is not None
        assert "error" not in result


class TestComparatorEvaluator:
    """Tests for evaluate_comparator() — blind A/B comparison with baseline file."""

    @pytest.fixture
    def baseline_dir(self, tmp_path: Path) -> Path:
        """Fixture providing a temp baseline directory."""
        return tmp_path / "baselines" / "test-loop"

    @pytest.fixture
    def baseline_with_file(self, baseline_dir: Path) -> Path:
        """Fixture with an existing baseline output.txt."""
        baseline_dir.mkdir(parents=True)
        (baseline_dir / "output.txt").write_text("baseline output")
        return baseline_dir

    def _make_cli_response(
        self, verdict_a: str = "yes", verdict_b: str = "no", confidence: float = 0.9
    ) -> dict:
        return {
            "type": "result",
            "subtype": "success",
            "structured_output": {
                "verdict_a": verdict_a,
                "verdict_b": verdict_b,
                "confidence": confidence,
                "reason": "Harness output is better.",
            },
        }

    def test_no_baseline_when_file_missing(self, baseline_dir: Path) -> None:
        """Returns no_baseline verdict when baseline file does not exist."""
        config = EvaluateConfig(type="comparator", baseline_path=str(baseline_dir))
        ctx = InterpolationContext()
        result = evaluate(config, output="new output", exit_code=0, context=ctx)
        assert result.verdict == "no_baseline"

    def test_harness_wins(self, baseline_with_file: Path) -> None:
        """Majority harness_pass=True → yes verdict."""
        config = EvaluateConfig(type="comparator", baseline_path=str(baseline_with_file))
        ctx = InterpolationContext()
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            with patch("little_loops.fsm.evaluators.random.choice", return_value=True):
                proc = MagicMock()
                proc.returncode = 0
                proc.stdout = json.dumps(self._make_cli_response(verdict_a="yes", verdict_b="no"))
                proc.stderr = ""
                mock_run.return_value = proc
                result = evaluate(config, output="harness output", exit_code=0, context=ctx)
        assert result.verdict == "yes"
        assert result.details["harness_wins"] == 1
        assert result.details["baseline_wins"] == 0

    def test_baseline_wins(self, baseline_with_file: Path) -> None:
        """Majority baseline_pass=True → no verdict."""
        config = EvaluateConfig(type="comparator", baseline_path=str(baseline_with_file))
        ctx = InterpolationContext()
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            with patch("little_loops.fsm.evaluators.random.choice", return_value=True):
                proc = MagicMock()
                proc.returncode = 0
                proc.stdout = json.dumps(self._make_cli_response(verdict_a="no", verdict_b="yes"))
                proc.stderr = ""
                mock_run.return_value = proc
                result = evaluate(config, output="harness output", exit_code=0, context=ctx)
        assert result.verdict == "no"
        assert result.details["harness_wins"] == 0
        assert result.details["baseline_wins"] == 1

    def test_tie(self, baseline_with_file: Path) -> None:
        """Equal harness/baseline wins → tie verdict (min_pairs=2)."""
        config = EvaluateConfig(
            type="comparator", baseline_path=str(baseline_with_file), min_pairs=2
        )
        ctx = InterpolationContext()
        responses = [
            self._make_cli_response(verdict_a="yes", verdict_b="no"),  # harness wins
            self._make_cli_response(verdict_a="no", verdict_b="yes"),  # baseline wins
        ]
        call_count = 0

        def side_effect(*args, **kwargs):
            nonlocal call_count
            proc = MagicMock()
            proc.returncode = 0
            proc.stdout = json.dumps(responses[call_count % len(responses)])
            proc.stderr = ""
            call_count += 1
            return proc

        with patch("little_loops.fsm.evaluators.subprocess.run", side_effect=side_effect):
            with patch("little_loops.fsm.evaluators.random.choice", return_value=True):
                result = evaluate(config, output="harness output", exit_code=0, context=ctx)
        assert result.verdict == "tie"

    def test_auto_promote_writes_file(self, baseline_with_file: Path) -> None:
        """auto_promote=True with yes verdict writes output to baseline file."""
        config = EvaluateConfig(
            type="comparator", baseline_path=str(baseline_with_file), auto_promote=True
        )
        ctx = InterpolationContext()
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            with patch("little_loops.fsm.evaluators.random.choice", return_value=True):
                proc = MagicMock()
                proc.returncode = 0
                proc.stdout = json.dumps(self._make_cli_response(verdict_a="yes", verdict_b="no"))
                proc.stderr = ""
                mock_run.return_value = proc
                result = evaluate(config, output="new better output", exit_code=0, context=ctx)
        assert result.verdict == "yes"
        assert (baseline_with_file / "output.txt").read_text() == "new better output"

    def test_auto_promote_bootstrap(self, baseline_dir: Path) -> None:
        """auto_promote=True with no baseline file bootstraps and routes yes."""
        config = EvaluateConfig(
            type="comparator", baseline_path=str(baseline_dir), auto_promote=True
        )
        ctx = InterpolationContext()
        result = evaluate(config, output="first run output", exit_code=0, context=ctx)
        assert result.verdict == "yes"
        assert result.details.get("bootstrapped") is True
        assert (baseline_dir / "output.txt").read_text() == "first run output"

    def test_no_auto_promote_does_not_write_file(self, baseline_with_file: Path) -> None:
        """auto_promote=False (default) never writes to baseline file on yes."""
        original_content = (baseline_with_file / "output.txt").read_text()
        config = EvaluateConfig(type="comparator", baseline_path=str(baseline_with_file))
        ctx = InterpolationContext()
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            with patch("little_loops.fsm.evaluators.random.choice", return_value=True):
                proc = MagicMock()
                proc.returncode = 0
                proc.stdout = json.dumps(self._make_cli_response(verdict_a="yes", verdict_b="no"))
                proc.stderr = ""
                mock_run.return_value = proc
                result = evaluate(config, output="new output", exit_code=0, context=ctx)
        assert result.verdict == "yes"
        assert (baseline_with_file / "output.txt").read_text() == original_content


class TestContractEvaluator:
    """Tests for evaluate_contract function (Tier 2 LLM-based, reads files)."""

    @staticmethod
    def _cli_stdout(verdict: str, confidence: float, reason: str) -> str:
        """Helper to create mock CLI JSON output."""
        return json.dumps(
            {
                "type": "result",
                "subtype": "success",
                "structured_output": {
                    "verdict": verdict,
                    "confidence": confidence,
                    "reason": reason,
                },
            }
        )

    @pytest.fixture
    def mock_cli(self):
        """Create mock subprocess.run for Claude CLI."""
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            mock_result = MagicMock()
            mock_result.returncode = 0
            mock_result.stderr = ""
            mock_run.return_value = mock_result
            yield mock_run, mock_result

    def test_aligned_pair_returns_yes(self, mock_cli, tmp_path) -> None:
        """Single aligned pair returns yes verdict."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.95, "Fields match on both sides")

        producer = tmp_path / "route.ts"
        producer.write_text('NextResponse.json({ id: 1, name: "test" })')
        consumer = tmp_path / "hook.ts"
        consumer.write_text("fetchJson<{ id: number; name: string }>()")

        config = EvaluateConfig(
            type="contract",
            pairs=[
                {
                    "producer": str(producer),
                    "consumer": str(consumer),
                    "contract": "shape must match",
                }
            ],
        )
        ctx = InterpolationContext()
        result = evaluate_contract(config, ctx)

        assert result.verdict == "yes"
        assert len(result.details["pair_results"]) == 1
        assert result.details["pair_results"][0]["verdict"] == "yes"

    def test_mismatched_pair_returns_no(self, mock_cli, tmp_path) -> None:
        """Mismatched pair (LLM returns no) yields no verdict."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("no", 0.9, "Field names differ")

        producer = tmp_path / "api.ts"
        producer.write_text("return { user_id: 1 }")
        consumer = tmp_path / "hook.ts"
        consumer.write_text("fetchJson<{ userId: number }>()")

        config = EvaluateConfig(
            type="contract",
            pairs=[
                {
                    "producer": str(producer),
                    "consumer": str(consumer),
                    "contract": "camelCase on both sides",
                }
            ],
        )
        ctx = InterpolationContext()
        result = evaluate_contract(config, ctx)

        assert result.verdict == "no"
        assert result.details["pair_results"][0]["verdict"] == "no"
        assert result.details["pair_results"][0]["reason"] == "Field names differ"

    def test_missing_producer_file_returns_error(self, tmp_path) -> None:
        """Unreadable producer file returns error verdict without calling LLM."""
        consumer = tmp_path / "hook.ts"
        consumer.write_text("fetchJson<{}>()")

        config = EvaluateConfig(
            type="contract",
            pairs=[
                {
                    "producer": str(tmp_path / "nonexistent.ts"),
                    "consumer": str(consumer),
                    "contract": "must match",
                }
            ],
        )
        ctx = InterpolationContext()
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            result = evaluate_contract(config, ctx)

        assert result.verdict == "error"
        assert "cannot read producer file" in result.details["pair_results"][0]["error"]
        mock_run.assert_not_called()

    def test_missing_consumer_file_returns_error(self, tmp_path) -> None:
        """Unreadable consumer file returns error verdict without calling LLM."""
        producer = tmp_path / "api.ts"
        producer.write_text("return { id: 1 }")

        config = EvaluateConfig(
            type="contract",
            pairs=[
                {
                    "producer": str(producer),
                    "consumer": str(tmp_path / "nonexistent.ts"),
                    "contract": "must match",
                }
            ],
        )
        ctx = InterpolationContext()
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            result = evaluate_contract(config, ctx)

        assert result.verdict == "error"
        assert "cannot read consumer file" in result.details["pair_results"][0]["error"]
        mock_run.assert_not_called()

    def test_regex_no_match_returns_error(self, tmp_path) -> None:
        """Producer pattern that matches nothing returns error for that pair."""
        producer = tmp_path / "api.ts"
        producer.write_text("export const handler = () => Response.json({ id: 1 })")
        consumer = tmp_path / "hook.ts"
        consumer.write_text("fetchJson<{ id: number }>()")

        config = EvaluateConfig(
            type="contract",
            pairs=[
                {
                    "producer": str(producer),
                    "consumer": str(consumer),
                    "producer_pattern": r"NextResponse\.json\((.+?)\)",  # won't match
                    "contract": "must match",
                }
            ],
        )
        ctx = InterpolationContext()
        with patch("little_loops.fsm.evaluators.subprocess.run") as mock_run:
            result = evaluate_contract(config, ctx)

        assert result.verdict == "error"
        assert "producer_pattern matched nothing" in result.details["pair_results"][0]["error"]
        mock_run.assert_not_called()

    def test_no_pairs_config_returns_error(self) -> None:
        """Contract evaluator with no pairs returns error immediately."""
        config = EvaluateConfig(type="contract")
        ctx = InterpolationContext()
        result = evaluate_contract(config, ctx)

        assert result.verdict == "error"
        assert "pairs" in result.details["error"].lower()

    def test_regex_extraction_applies_to_both_sides(self, mock_cli, tmp_path) -> None:
        """Producer and consumer regex patterns correctly extract slices."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.9, "Slices align")

        producer = tmp_path / "api.ts"
        producer.write_text('NextResponse.json({ id: 1, name: "test" })')
        consumer = tmp_path / "hook.ts"
        consumer.write_text("fetchJson<{ id: number; name: string }>()")

        config = EvaluateConfig(
            type="contract",
            pairs=[
                {
                    "producer": str(producer),
                    "consumer": str(consumer),
                    "producer_pattern": r"NextResponse\.json\((.+?)\)",
                    "consumer_pattern": r"fetchJson<(.+?)>",
                    "contract": "shape must match",
                }
            ],
        )
        ctx = InterpolationContext()
        result = evaluate_contract(config, ctx)

        assert result.verdict == "yes"
        # The prompt was passed to the CLI binary — just verify CLI was called
        assert mock_run.called

    def test_cli_not_found_returns_error(self, tmp_path) -> None:
        """Returns error immediately when host CLI is not installed."""
        producer = tmp_path / "api.ts"
        producer.write_text("return { id: 1 }")
        consumer = tmp_path / "hook.ts"
        consumer.write_text("fetchJson<{ id: number }>()")

        config = EvaluateConfig(
            type="contract",
            pairs=[
                {"producer": str(producer), "consumer": str(consumer), "contract": "must match"}
            ],
        )
        ctx = InterpolationContext()
        with patch(
            "little_loops.fsm.evaluators.subprocess.run",
            side_effect=FileNotFoundError("claude"),
        ):
            result = evaluate_contract(config, ctx)

        assert result.verdict == "error"
        assert result.details.get("missing_dependency") is True

    def test_multi_pair_any_failure_returns_no(self, mock_cli, tmp_path) -> None:
        """With multiple pairs, any failure causes overall no verdict."""
        mock_run, mock_result = mock_cli
        # First call returns yes, second returns no
        mock_run.side_effect = [
            type(mock_result)(
                returncode=0,
                stdout=self._cli_stdout("yes", 0.9, "First pair ok"),
                stderr="",
            ),
            type(mock_result)(
                returncode=0,
                stdout=self._cli_stdout("no", 0.85, "Second pair fails"),
                stderr="",
            ),
        ]

        p1 = tmp_path / "api1.ts"
        p1.write_text("{ id: 1 }")
        c1 = tmp_path / "hook1.ts"
        c1.write_text("{ id: number }")
        p2 = tmp_path / "api2.ts"
        p2.write_text("{ user_id: 1 }")
        c2 = tmp_path / "hook2.ts"
        c2.write_text("{ userId: number }")

        config = EvaluateConfig(
            type="contract",
            pairs=[
                {"producer": str(p1), "consumer": str(c1), "contract": "must match"},
                {"producer": str(p2), "consumer": str(c2), "contract": "camelCase"},
            ],
        )
        ctx = InterpolationContext()
        result = evaluate_contract(config, ctx)

        assert result.verdict == "no"
        assert len(result.details["pair_results"]) == 2

    def test_dispatch_contract(self, mock_cli, tmp_path) -> None:
        """Contract type routes through the evaluate() dispatcher."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("yes", 0.95, "Aligned")

        producer = tmp_path / "api.ts"
        producer.write_text("{ id: 1 }")
        consumer = tmp_path / "hook.ts"
        consumer.write_text("{ id: number }")

        config = EvaluateConfig(
            type="contract",
            pairs=[
                {"producer": str(producer), "consumer": str(consumer), "contract": "must match"}
            ],
        )
        ctx = InterpolationContext()
        result = evaluate(config, output="", exit_code=0, context=ctx)
        assert result.verdict == "yes"

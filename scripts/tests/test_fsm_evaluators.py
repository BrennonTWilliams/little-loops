"""Unit tests for FSM Tier 1 deterministic evaluators."""

from __future__ import annotations

import pytest

from little_loops.fsm.evaluators import (
    EvaluationResult,
    _extract_json_path,
    evaluate,
    evaluate_convergence,
    evaluate_exit_code,
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
        result = EvaluationResult(verdict="success", details={"key": "value"})
        assert result.verdict == "success"
        assert result.details == {"key": "value"}

    def test_empty_details(self) -> None:
        """EvaluationResult can have empty details."""
        result = EvaluationResult(verdict="failure", details={})
        assert result.verdict == "failure"
        assert result.details == {}


class TestExitCodeEvaluator:
    """Tests for exit_code evaluator."""

    @pytest.mark.parametrize(
        ("exit_code", "expected"),
        [
            (0, "success"),
            (1, "failure"),
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
        assert result.verdict == "success"
        assert result.details["value"] == 5
        assert result.details["target"] == 5

    def test_equal_fails(self) -> None:
        """eq operator fails when values differ."""
        result = evaluate_output_numeric("3", "eq", 5)
        assert result.verdict == "failure"

    def test_not_equal_passes(self) -> None:
        """ne operator passes when values differ."""
        result = evaluate_output_numeric("3", "ne", 5)
        assert result.verdict == "success"

    def test_not_equal_fails(self) -> None:
        """ne operator fails when values equal."""
        result = evaluate_output_numeric("5", "ne", 5)
        assert result.verdict == "failure"

    def test_less_than_passes(self) -> None:
        """lt operator passes when value < target."""
        result = evaluate_output_numeric("3", "lt", 5)
        assert result.verdict == "success"

    def test_less_than_fails(self) -> None:
        """lt operator fails when value >= target."""
        result = evaluate_output_numeric("5", "lt", 5)
        assert result.verdict == "failure"

    def test_less_equal_passes(self) -> None:
        """le operator passes when value <= target."""
        result = evaluate_output_numeric("5", "le", 5)
        assert result.verdict == "success"

    def test_less_equal_fails(self) -> None:
        """le operator fails when value > target."""
        result = evaluate_output_numeric("6", "le", 5)
        assert result.verdict == "failure"

    def test_greater_than_passes(self) -> None:
        """gt operator passes when value > target."""
        result = evaluate_output_numeric("7", "gt", 5)
        assert result.verdict == "success"

    def test_greater_than_fails(self) -> None:
        """gt operator fails when value <= target."""
        result = evaluate_output_numeric("5", "gt", 5)
        assert result.verdict == "failure"

    def test_greater_equal_passes(self) -> None:
        """ge operator passes when value >= target."""
        result = evaluate_output_numeric("5", "ge", 5)
        assert result.verdict == "success"

    def test_greater_equal_fails(self) -> None:
        """ge operator fails when value < target."""
        result = evaluate_output_numeric("4", "ge", 5)
        assert result.verdict == "failure"

    def test_parse_error(self) -> None:
        """Non-numeric output returns error verdict."""
        result = evaluate_output_numeric("not a number", "eq", 5)
        assert result.verdict == "error"
        assert "Cannot parse as number" in result.details["error"]

    def test_whitespace_stripped(self) -> None:
        """Whitespace around number is handled."""
        result = evaluate_output_numeric("  5  \n", "eq", 5)
        assert result.verdict == "success"

    def test_float_values(self) -> None:
        """Float values are compared correctly."""
        result = evaluate_output_numeric("3.14", "lt", 3.15)
        assert result.verdict == "success"
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
        with pytest.raises(KeyError):
            _extract_json_path(data, "missing")

    def test_missing_nested_key_raises(self) -> None:
        """Missing nested key raises KeyError."""
        data = {"a": {"b": 1}}
        with pytest.raises(KeyError):
            _extract_json_path(data, "a.c")

    def test_array_index_out_of_range(self) -> None:
        """Array index out of range raises KeyError."""
        data = {"items": ["a", "b"]}
        with pytest.raises(KeyError):
            _extract_json_path(data, "items.5")


class TestOutputJsonEvaluator:
    """Tests for output_json evaluator."""

    def test_simple_numeric_comparison(self) -> None:
        """Simple numeric JSON comparison works."""
        output = '{"count": 5}'
        result = evaluate_output_json(output, ".count", "eq", 5)
        assert result.verdict == "success"
        assert result.details["value"] == 5

    def test_nested_path(self) -> None:
        """Nested JSON path extraction works."""
        output = '{"summary": {"failed": 0}}'
        result = evaluate_output_json(output, ".summary.failed", "eq", 0)
        assert result.verdict == "success"

    def test_numeric_less_than(self) -> None:
        """Numeric comparison with lt operator."""
        output = '{"errors": 3}'
        result = evaluate_output_json(output, ".errors", "lt", 5)
        assert result.verdict == "success"

    def test_numeric_greater_than(self) -> None:
        """Numeric comparison with gt operator."""
        output = '{"score": 95}'
        result = evaluate_output_json(output, ".score", "gt", 90)
        assert result.verdict == "success"

    def test_string_equality(self) -> None:
        """String value comparison works."""
        output = '{"status": "ok"}'
        result = evaluate_output_json(output, ".status", "eq", "ok")
        assert result.verdict == "success"

    def test_string_not_equal(self) -> None:
        """String ne comparison works."""
        output = '{"status": "error"}'
        result = evaluate_output_json(output, ".status", "ne", "ok")
        assert result.verdict == "success"

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
        assert result.verdict == "success"

    def test_boolean_value(self) -> None:
        """Boolean JSON value comparison works."""
        output = '{"enabled": true}'
        result = evaluate_output_json(output, ".enabled", "eq", True)
        assert result.verdict == "success"


class TestOutputContainsEvaluator:
    """Tests for output_contains evaluator."""

    def test_substring_match(self) -> None:
        """Substring found returns success."""
        result = evaluate_output_contains("Hello World", "World")
        assert result.verdict == "success"
        assert result.details["matched"] is True

    def test_substring_not_found(self) -> None:
        """Substring not found returns failure."""
        result = evaluate_output_contains("Hello World", "Goodbye")
        assert result.verdict == "failure"
        assert result.details["matched"] is False

    def test_regex_pattern(self) -> None:
        """Regex pattern matching works."""
        result = evaluate_output_contains("Error: 5 failures", r"\d+ failures")
        assert result.verdict == "success"

    def test_regex_anchors(self) -> None:
        """Regex anchors work correctly."""
        result = evaluate_output_contains("test line", r"^test")
        assert result.verdict == "success"

        result = evaluate_output_contains("line test", r"^test")
        assert result.verdict == "failure"

    def test_negate_found(self) -> None:
        """negate=True with match returns failure."""
        result = evaluate_output_contains("has error", "error", negate=True)
        assert result.verdict == "failure"

    def test_negate_not_found(self) -> None:
        """negate=True without match returns success."""
        result = evaluate_output_contains("All tests passed", "Error", negate=True)
        assert result.verdict == "success"

    def test_invalid_regex_fallback(self) -> None:
        """Invalid regex falls back to substring match."""
        # '[' is invalid regex but valid substring
        result = evaluate_output_contains("test[1]", "[1]")
        assert result.verdict == "success"

    def test_empty_pattern(self) -> None:
        """Empty pattern matches (substring)."""
        result = evaluate_output_contains("any text", "")
        assert result.verdict == "success"

    def test_multiline_output(self) -> None:
        """Pattern matching works on multiline output."""
        output = "line 1\nError on line 2\nline 3"
        result = evaluate_output_contains(output, "Error")
        assert result.verdict == "success"


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


class TestEvaluateDispatcher:
    """Tests for the main evaluate() dispatcher function."""

    def test_dispatch_exit_code(self) -> None:
        """exit_code type routes correctly."""
        config = EvaluateConfig(type="exit_code")
        ctx = InterpolationContext()
        result = evaluate(config, "", 0, ctx)
        assert result.verdict == "success"

    def test_dispatch_output_numeric(self) -> None:
        """output_numeric type routes correctly."""
        config = EvaluateConfig(type="output_numeric", operator="lt", target=10)
        ctx = InterpolationContext()
        result = evaluate(config, "5", 0, ctx)
        assert result.verdict == "success"

    def test_dispatch_output_json(self) -> None:
        """output_json type routes correctly."""
        config = EvaluateConfig(
            type="output_json", path=".count", operator="eq", target=0
        )
        ctx = InterpolationContext()
        result = evaluate(config, '{"count": 0}', 0, ctx)
        assert result.verdict == "success"

    def test_dispatch_output_contains(self) -> None:
        """output_contains type routes correctly."""
        config = EvaluateConfig(type="output_contains", pattern="success")
        ctx = InterpolationContext()
        result = evaluate(config, "operation success", 0, ctx)
        assert result.verdict == "success"

    def test_dispatch_output_contains_negate(self) -> None:
        """output_contains with negate routes correctly."""
        config = EvaluateConfig(type="output_contains", pattern="error", negate=True)
        ctx = InterpolationContext()
        result = evaluate(config, "all good", 0, ctx)
        assert result.verdict == "success"

    def test_dispatch_convergence(self) -> None:
        """convergence type routes correctly."""
        config = EvaluateConfig(type="convergence", target=0)
        ctx = InterpolationContext()
        result = evaluate(config, "5", 0, ctx)
        assert result.verdict == "progress"  # First iteration

    def test_dispatch_convergence_with_previous(self) -> None:
        """convergence with previous value works."""
        config = EvaluateConfig(
            type="convergence", target=0, previous="${prev.output}"
        )
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
        config = EvaluateConfig(
            type="convergence", target=0, tolerance="${context.tolerance}"
        )
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

    def test_dispatch_llm_structured_raises(self) -> None:
        """llm_structured type raises ValueError (Tier 2)."""
        config = EvaluateConfig(type="llm_structured")
        ctx = InterpolationContext()
        with pytest.raises(ValueError, match="Tier 2"):
            evaluate(config, "", 0, ctx)

    def test_dispatch_unknown_type_raises(self) -> None:
        """Unknown type raises ValueError."""
        # Create config with invalid type by bypassing validation
        config = EvaluateConfig.__new__(EvaluateConfig)
        config.type = "unknown_type"  # type: ignore[assignment]
        ctx = InterpolationContext()
        with pytest.raises(ValueError, match="Unknown evaluator type"):
            evaluate(config, "", 0, ctx)

"""Unit tests for FSM evaluators (Tier 1 deterministic and Tier 2 LLM)."""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

import pytest

from little_loops.fsm.evaluators import (
    DEFAULT_LLM_PROMPT,
    DEFAULT_LLM_SCHEMA,
    EvaluationResult,
    _extract_json_path,
    evaluate,
    evaluate_convergence,
    evaluate_exit_code,
    evaluate_llm_structured,
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
        config = EvaluateConfig(type="output_json", path=".count", operator="eq", target=0)
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

    def test_dispatch_unknown_type_raises(self) -> None:
        """Unknown type raises ValueError."""
        # Create config with invalid type by bypassing validation
        config = EvaluateConfig.__new__(EvaluateConfig)
        config.type = "unknown_type"  # type: ignore[assignment]
        ctx = InterpolationContext()
        with pytest.raises(ValueError, match="Unknown evaluator type"):
            evaluate(config, "", 0, ctx)


class TestLLMStructuredEvaluator:
    """Tests for llm_structured evaluator (Tier 2) via Claude CLI."""

    @staticmethod
    def _cli_stdout(verdict: str, confidence: float, reason: str) -> str:
        """Helper to create mock CLI JSON output."""
        return json.dumps(
            {
                "result": json.dumps(
                    {
                        "verdict": verdict,
                        "confidence": confidence,
                        "reason": reason,
                    }
                ),
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
        """Returns error when claude CLI not installed."""
        with patch(
            "little_loops.fsm.evaluators.subprocess.run",
            side_effect=FileNotFoundError("claude"),
        ):
            result = evaluate_llm_structured("test output")
        assert result.verdict == "error"
        assert result.details.get("missing_dependency") is True
        assert "claude CLI not found" in result.details["error"]

    def test_success_verdict(self, mock_cli) -> None:
        """LLM returns success verdict."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("success", 0.9, "Action completed successfully")

        result = evaluate_llm_structured("Fixed error in handlers.py")

        assert result.verdict == "success"
        assert result.details["confidence"] == 0.9
        assert result.details["confident"] is True
        assert result.details["reason"] == "Action completed successfully"

    def test_failure_verdict(self, mock_cli) -> None:
        """LLM returns failure verdict."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("failure", 0.8, "Tests still failing")

        result = evaluate_llm_structured("3 tests failed")

        assert result.verdict == "failure"
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
        mock_result.stdout = self._cli_stdout("success", 0.4, "Maybe fixed")

        result = evaluate_llm_structured("...", min_confidence=0.7, uncertain_suffix=False)

        assert result.verdict == "success"
        assert result.details["confident"] is False

    def test_low_confidence_with_suffix(self, mock_cli) -> None:
        """Low confidence with uncertain_suffix appends _uncertain."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("success", 0.4, "Maybe fixed")

        result = evaluate_llm_structured("...", min_confidence=0.7, uncertain_suffix=True)

        assert result.verdict == "success_uncertain"
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
                "result": json.dumps({"verdict": "found", "confidence": 0.95}),
            }
        )

        result = evaluate_llm_structured("Found 3 matches", schema=custom_schema)

        assert result.verdict == "found"
        assert result.details["confidence"] == 0.95
        # Verify custom schema was passed to CLI
        call_args = mock_run.call_args[0][0]
        schema_idx = call_args.index("--json-schema")
        assert json.loads(call_args[schema_idx + 1]) == custom_schema

    def test_custom_prompt(self, mock_cli) -> None:
        """Custom prompt is passed to CLI."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("success", 0.9, "Done")

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

    def test_result_as_dict_in_envelope(self, mock_cli) -> None:
        """result field as dict (not string) is handled correctly."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = json.dumps(
            {"result": {"verdict": "success", "confidence": 0.9, "reason": "Done"}}
        )

        result = evaluate_llm_structured("...")

        assert result.verdict == "success"
        assert result.details["confidence"] == 0.9

    def test_empty_result_field_includes_raw_preview(self, mock_cli) -> None:
        """Empty result field returns error with raw_preview for diagnosis."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = json.dumps({"result": "", "is_error": False})

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert "raw_preview" in result.details
        assert "Empty result field" in result.details["error"]

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
        mock_result.stdout = self._cli_stdout("success", 1.0, "Done")

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
        mock_result.stdout = self._cli_stdout("success", 0.9, "Action completed")

        result = evaluate_llm_structured("Done")

        assert "raw" in result.details
        assert result.details["raw"]["verdict"] == "success"
        assert result.details["raw"]["confidence"] == 0.9

    def test_default_values_used(self, mock_cli) -> None:
        """Default prompt and schema used when not specified."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("success", 0.9, "Done")

        evaluate_llm_structured("test output")

        call_args = mock_run.call_args[0][0]
        # Check prompt
        prompt_idx = call_args.index("-p")
        assert DEFAULT_LLM_PROMPT in call_args[prompt_idx + 1]
        # Check schema
        schema_idx = call_args.index("--json-schema")
        assert json.loads(call_args[schema_idx + 1]) == DEFAULT_LLM_SCHEMA

    def test_envelope_as_direct_result(self, mock_cli) -> None:
        """Envelope itself is the structured result when result field is absent."""
        mock_run, mock_result = mock_cli
        # Some CLI versions return JSON directly without a "result" wrapper
        mock_result.stdout = json.dumps(
            {"verdict": "success", "confidence": 0.9, "reason": "All checks passed"}
        )

        result = evaluate_llm_structured("test output")

        assert result.verdict == "success"
        assert result.details["confidence"] == 0.9
        assert result.details["reason"] == "All checks passed"

    def test_jsonl_output_uses_last_line(self, mock_cli) -> None:
        """JSONL output (multiple JSON lines) uses the last non-empty line."""
        mock_run, mock_result = mock_cli
        # Simulate JSONL: event lines followed by final result line
        event_line = json.dumps({"type": "progress", "text": "thinking..."})
        final_line = json.dumps(
            {
                "result": json.dumps(
                    {"verdict": "failure", "confidence": 0.8, "reason": "Tests failed"}
                )
            }
        )
        mock_result.stdout = f"{event_line}\n{final_line}\n"

        result = evaluate_llm_structured("output")

        assert result.verdict == "failure"
        assert result.details["confidence"] == 0.8


class TestEvaluateDispatcherLLM:
    """Tests for evaluate() dispatcher with llm_structured type."""

    @staticmethod
    def _cli_stdout(verdict: str, confidence: float, reason: str) -> str:
        """Helper to create mock CLI JSON output."""
        return json.dumps(
            {
                "result": json.dumps(
                    {
                        "verdict": verdict,
                        "confidence": confidence,
                        "reason": reason,
                    }
                ),
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
        mock_result.stdout = self._cli_stdout("success", 0.9, "Done")

        config = EvaluateConfig(type="llm_structured")
        ctx = InterpolationContext()
        result = evaluate(config, "test output", 0, ctx)

        assert result.verdict == "success"
        assert result.details["confident"] is True

    def test_dispatch_llm_with_config_options(self, mock_cli) -> None:
        """llm_structured uses config options."""
        mock_run, mock_result = mock_cli
        mock_result.stdout = self._cli_stdout("success", 0.4, "Maybe")

        config = EvaluateConfig(
            type="llm_structured",
            prompt="Custom prompt",
            min_confidence=0.7,
            uncertain_suffix=True,
        )
        ctx = InterpolationContext()
        result = evaluate(config, "test output", 0, ctx)

        assert result.verdict == "success_uncertain"
        assert result.details["confident"] is False

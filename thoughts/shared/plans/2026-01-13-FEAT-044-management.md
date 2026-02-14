# FEAT-044: Tier 2 LLM Evaluator - Implementation Plan

## Issue Reference
- **File**: `.issues/features/P2-FEAT-044-tier2-llm-evaluator.md`
- **Type**: feature
- **Priority**: P2
- **Action**: implement

## Current State Analysis

The FSM evaluator system is implemented in `scripts/little_loops/fsm/evaluators.py` with:
- `EvaluationResult` dataclass at line 29-39
- Tier 1 evaluators: `exit_code`, `output_numeric`, `output_json`, `output_contains`, `convergence`
- Main `evaluate()` dispatcher at lines 342-449
- Placeholder for `llm_structured` at lines 442-446 that raises `ValueError`

### Key Discoveries
- `EvaluateConfig` in `schema.py:21-72` already has LLM fields: `prompt`, `schema`, `min_confidence`, `uncertain_suffix`, `source`
- `LLMConfig` in `schema.py:280-320` provides FSM-level defaults: `model`, `max_tokens`, `timeout`, `enabled`
- Test file at `scripts/tests/test_fsm_evaluators.py` tests the ValueError stub at line 483-488
- No `anthropic` dependency in `pyproject.toml` - needs to be added
- Module exports defined in `__init__.py` - will need to export new function

### Patterns to Follow
- All Tier 1 evaluators return `EvaluationResult` with `verdict` string and `details` dict
- Error cases return `verdict="error"` with `details["error"]` message
- Dispatcher uses if/elif chain based on `config.type`
- Tests use pytest classes with parametrized test cases

## Desired End State

A fully functional `evaluate_llm_structured()` function that:
1. Calls Anthropic API with tool use for structured output
2. Returns default schema verdicts (success/failure/blocked/partial) or custom schema
3. Handles confidence thresholds with optional `_uncertain` suffix
4. Handles API errors and timeouts gracefully
5. Truncates long outputs to 4000 chars
6. Integrates with the `evaluate()` dispatcher

### How to Verify
- Unit tests pass with mocked Anthropic client
- Dispatcher routes to LLM evaluator (no longer raises ValueError)
- All acceptance criteria from issue met

## What We're NOT Doing

- Not implementing the actual FSM executor loop (FEAT-045)
- Not adding integration tests with real API calls (would require API key)
- Not modifying the LLMConfig schema (already complete)
- Not implementing multiple LLM providers (Anthropic only per issue spec)

## Problem Analysis

Slash commands (like `/ll:manage-issue`) produce natural language output that cannot be evaluated deterministically. This evaluator bridges the gap by using Claude's structured output capability to extract a structured verdict.

## Solution Approach

1. Add `anthropic` as an optional dependency in pyproject.toml
2. Create `evaluate_llm_structured()` function following existing evaluator patterns
3. Update `evaluate()` dispatcher to call the new function
4. Add comprehensive unit tests with mocked Anthropic client
5. Update module exports in `__init__.py`

## Implementation Phases

### Phase 1: Add Anthropic Dependency

#### Overview
Add `anthropic` SDK as an optional dependency for LLM evaluation.

#### Changes Required

**File**: `scripts/pyproject.toml`
**Changes**: Add anthropic to optional dependencies

```toml
[project.optional-dependencies]
dev = [
    "pytest>=7.0",
    "pytest-cov>=4.0",
    "ruff>=0.1.0",
    "mypy>=1.0",
]
llm = [
    "anthropic>=0.40.0",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] `pip install -e "./scripts[llm]"` succeeds

---

### Phase 2: Implement evaluate_llm_structured Function

#### Overview
Implement the core LLM evaluator function that calls Anthropic API with tool use.

#### Changes Required

**File**: `scripts/little_loops/fsm/evaluators.py`
**Changes**: Add DEFAULT_LLM_SCHEMA constant and evaluate_llm_structured function after the existing evaluators

```python
# After line 27 (after imports)
import anthropic

# Constants for LLM evaluator
DEFAULT_LLM_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["success", "failure", "blocked", "partial"],
            "description": (
                "- success: The action completed its goal\n"
                "- failure: The action failed, should retry\n"
                "- blocked: Cannot proceed without external help\n"
                "- partial: Made progress but not complete"
            ),
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence in this verdict (0-1)",
        },
        "reason": {
            "type": "string",
            "description": "Brief explanation",
        },
    },
    "required": ["verdict", "confidence", "reason"],
}

DEFAULT_LLM_PROMPT = "Evaluate whether this action succeeded based on its output."

# After evaluate_convergence function (around line 339)
def evaluate_llm_structured(
    output: str,
    prompt: str | None = None,
    schema: dict[str, Any] | None = None,
    min_confidence: float = 0.5,
    uncertain_suffix: bool = False,
    model: str = "claude-sonnet-4-20250514",
    max_tokens: int = 256,
    timeout: int = 30,
) -> EvaluationResult:
    """Evaluate action output using LLM with structured output.

    This is the ONLY place in the FSM system that uses LLM structured output.

    Args:
        output: Action stdout to evaluate
        prompt: Custom evaluation prompt (defaults to basic success check)
        schema: Custom JSON schema for structured response
        min_confidence: Minimum confidence threshold (0-1)
        uncertain_suffix: If True, append _uncertain to low-confidence verdicts
        model: Model identifier for API calls
        max_tokens: Maximum tokens for response
        timeout: Timeout in seconds

    Returns:
        EvaluationResult with verdict from LLM and confidence/reason in details
    """
    try:
        client = anthropic.Anthropic()
    except anthropic.AuthenticationError as e:
        return EvaluationResult(
            verdict="error",
            details={"error": f"Anthropic authentication error: {e}", "auth_error": True},
        )

    effective_schema = schema or DEFAULT_LLM_SCHEMA
    effective_prompt = prompt or DEFAULT_LLM_PROMPT

    # Truncate output to avoid context limits (keep last 4000 chars)
    truncated = output[-4000:] if len(output) > 4000 else output

    try:
        response = client.messages.create(
            model=model,
            max_tokens=max_tokens,
            timeout=timeout,
            messages=[
                {
                    "role": "user",
                    "content": f"{effective_prompt}\n\n<action_output>\n{truncated}\n</action_output>",
                }
            ],
            tools=[
                {
                    "name": "evaluate",
                    "description": "Provide your evaluation of the action result",
                    "input_schema": effective_schema,
                }
            ],
            tool_choice={"type": "tool", "name": "evaluate"},
        )
    except anthropic.APITimeoutError:
        return EvaluationResult(
            verdict="error",
            details={"error": "LLM evaluation timeout", "timeout": True},
        )
    except anthropic.APIError as e:
        return EvaluationResult(
            verdict="error",
            details={"error": f"LLM API error: {e}", "api_error": True},
        )

    # Extract structured result from tool use
    llm_result: dict[str, Any] | None = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "evaluate":
            llm_result = block.input
            break

    if llm_result is None:
        return EvaluationResult(
            verdict="error",
            details={"error": "No evaluation in LLM response"},
        )

    # Build result with confidence handling
    verdict = str(llm_result.get("verdict", "error"))
    confidence = float(llm_result.get("confidence", 1.0))
    confident = confidence >= min_confidence

    # Optionally modify verdict for low confidence
    if uncertain_suffix and not confident:
        verdict = f"{verdict}_uncertain"

    return EvaluationResult(
        verdict=verdict,
        details={
            "confidence": confidence,
            "confident": confident,
            "reason": llm_result.get("reason", ""),
            "raw": llm_result,
        },
    )
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -c "from little_loops.fsm.evaluators import evaluate_llm_structured"` succeeds
- [ ] Type checking passes: `python -m mypy scripts/little_loops/fsm/evaluators.py`

---

### Phase 3: Update evaluate() Dispatcher

#### Overview
Modify the evaluate() dispatcher to call evaluate_llm_structured instead of raising ValueError.

#### Changes Required

**File**: `scripts/little_loops/fsm/evaluators.py`
**Changes**: Replace the ValueError stub with actual call to evaluate_llm_structured

```python
# Replace lines 442-446 with:
    elif eval_type == "llm_structured":
        return evaluate_llm_structured(
            output=output,
            prompt=config.prompt,
            schema=config.schema,
            min_confidence=config.min_confidence,
            uncertain_suffix=config.uncertain_suffix,
        )
```

Note: This uses the config-level settings. The LLMConfig (loop-level model/max_tokens/timeout) would be passed separately by the FSM executor when it's implemented in FEAT-045.

#### Success Criteria

**Automated Verification**:
- [ ] Type checking passes: `python -m mypy scripts/little_loops/fsm/evaluators.py`
- [ ] Lint passes: `ruff check scripts/little_loops/fsm/evaluators.py`

---

### Phase 4: Update Module Exports

#### Overview
Add evaluate_llm_structured to public exports.

#### Changes Required

**File**: `scripts/little_loops/fsm/__init__.py`
**Changes**: Add to imports and __all__

```python
# Update imports (around line 31-39)
from little_loops.fsm.evaluators import (
    DEFAULT_LLM_SCHEMA,
    EvaluationResult,
    evaluate,
    evaluate_convergence,
    evaluate_exit_code,
    evaluate_llm_structured,
    evaluate_output_contains,
    evaluate_output_json,
    evaluate_output_numeric,
)

# Update __all__ (around line 59-80)
__all__ = [
    "DEFAULT_LLM_SCHEMA",
    "EvaluateConfig",
    "EvaluationResult",
    "FSMLoop",
    "InterpolationContext",
    "InterpolationError",
    "LLMConfig",
    "RouteConfig",
    "StateConfig",
    "ValidationError",
    "compile_paradigm",
    "evaluate",
    "evaluate_convergence",
    "evaluate_exit_code",
    "evaluate_llm_structured",
    "evaluate_output_contains",
    "evaluate_output_json",
    "evaluate_output_numeric",
    "interpolate",
    "interpolate_dict",
    "load_and_validate",
    "validate_fsm",
]
```

#### Success Criteria

**Automated Verification**:
- [ ] `python -c "from little_loops.fsm import evaluate_llm_structured, DEFAULT_LLM_SCHEMA"` succeeds

---

### Phase 5: Write Unit Tests

#### Overview
Add comprehensive unit tests with mocked Anthropic client.

#### Changes Required

**File**: `scripts/tests/test_fsm_evaluators.py`
**Changes**: Add new test class for LLM evaluator after TestEvaluateDispatcher

```python
# Add imports at top
from unittest.mock import MagicMock, patch

# Add new test class at end of file
class TestLLMStructuredEvaluator:
    """Tests for llm_structured evaluator."""

    @pytest.fixture
    def mock_anthropic(self):
        """Create mock Anthropic client and response."""
        with patch("little_loops.fsm.evaluators.anthropic") as mock_module:
            mock_client = MagicMock()
            mock_module.Anthropic.return_value = mock_client
            mock_module.APIError = Exception
            mock_module.APITimeoutError = TimeoutError
            mock_module.AuthenticationError = Exception
            yield mock_client

    def _create_tool_response(self, verdict: str, confidence: float, reason: str):
        """Helper to create mock tool use response."""
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = "evaluate"
        mock_block.input = {
            "verdict": verdict,
            "confidence": confidence,
            "reason": reason,
        }
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        return mock_response

    def test_success_verdict(self, mock_anthropic):
        """LLM returns success verdict."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "success", 0.9, "Action completed successfully"
        )

        result = evaluate_llm_structured("Fixed error in handlers.py")

        assert result.verdict == "success"
        assert result.details["confidence"] == 0.9
        assert result.details["confident"] is True
        assert result.details["reason"] == "Action completed successfully"

    def test_failure_verdict(self, mock_anthropic):
        """LLM returns failure verdict."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "failure", 0.8, "Tests still failing"
        )

        result = evaluate_llm_structured("3 tests failed")

        assert result.verdict == "failure"
        assert result.details["confident"] is True

    def test_blocked_verdict(self, mock_anthropic):
        """LLM returns blocked verdict."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "blocked", 0.95, "Missing credentials"
        )

        result = evaluate_llm_structured("Authentication required")

        assert result.verdict == "blocked"

    def test_partial_verdict(self, mock_anthropic):
        """LLM returns partial verdict."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "partial", 0.7, "2 of 5 items completed"
        )

        result = evaluate_llm_structured("Completed items 1 and 2")

        assert result.verdict == "partial"

    def test_low_confidence_without_suffix(self, mock_anthropic):
        """Low confidence without uncertain_suffix keeps original verdict."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "success", 0.4, "Maybe fixed"
        )

        result = evaluate_llm_structured(
            "...", min_confidence=0.7, uncertain_suffix=False
        )

        assert result.verdict == "success"
        assert result.details["confident"] is False

    def test_low_confidence_with_suffix(self, mock_anthropic):
        """Low confidence with uncertain_suffix appends _uncertain."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "success", 0.4, "Maybe fixed"
        )

        result = evaluate_llm_structured(
            "...", min_confidence=0.7, uncertain_suffix=True
        )

        assert result.verdict == "success_uncertain"
        assert result.details["confident"] is False

    def test_custom_schema(self, mock_anthropic):
        """Custom schema with non-standard verdicts."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        custom_schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["found", "not_found"]},
                "confidence": {"type": "number"},
            },
            "required": ["verdict"],
        }

        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = "evaluate"
        mock_block.input = {"verdict": "found", "confidence": 0.95}
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        mock_anthropic.messages.create.return_value = mock_response

        result = evaluate_llm_structured("Found 3 matches", schema=custom_schema)

        assert result.verdict == "found"
        assert result.details["confidence"] == 0.95

    def test_custom_prompt(self, mock_anthropic):
        """Custom prompt is passed to API."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "success", 0.9, "Done"
        )

        custom_prompt = "Check if the code review was approved."
        evaluate_llm_structured("LGTM, approved", prompt=custom_prompt)

        # Verify custom prompt was used
        call_args = mock_anthropic.messages.create.call_args
        message_content = call_args.kwargs["messages"][0]["content"]
        assert custom_prompt in message_content

    def test_api_timeout_handling(self, mock_anthropic):
        """Timeout returns error verdict."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.side_effect = TimeoutError("Timeout")

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert result.details.get("timeout") is True

    def test_api_error_handling(self, mock_anthropic):
        """API error returns error verdict."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.side_effect = Exception("Rate limited")

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert result.details.get("api_error") is True

    def test_no_tool_use_in_response(self, mock_anthropic):
        """Response without tool use returns error."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_response = MagicMock()
        mock_response.content = []  # No tool use blocks
        mock_anthropic.messages.create.return_value = mock_response

        result = evaluate_llm_structured("...")

        assert result.verdict == "error"
        assert "No evaluation" in result.details["error"]

    def test_output_truncation(self, mock_anthropic):
        """Long output is truncated to last 4000 chars."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "success", 1.0, "Done"
        )

        long_output = "x" * 10000
        evaluate_llm_structured(long_output)

        # Verify truncation happened
        call_args = mock_anthropic.messages.create.call_args
        message_content = call_args.kwargs["messages"][0]["content"]
        # Should have prompt + truncated output (last 4000 chars)
        assert len(message_content) < 5000

    def test_raw_response_in_details(self, mock_anthropic):
        """Raw LLM response is included in details."""
        from little_loops.fsm.evaluators import evaluate_llm_structured

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "success", 0.9, "Action completed"
        )

        result = evaluate_llm_structured("Done")

        assert "raw" in result.details
        assert result.details["raw"]["verdict"] == "success"
        assert result.details["raw"]["confidence"] == 0.9

    def test_default_values_used(self, mock_anthropic):
        """Default prompt and schema used when not specified."""
        from little_loops.fsm.evaluators import (
            DEFAULT_LLM_PROMPT,
            DEFAULT_LLM_SCHEMA,
            evaluate_llm_structured,
        )

        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "success", 0.9, "Done"
        )

        evaluate_llm_structured("test output")

        call_args = mock_anthropic.messages.create.call_args
        # Check prompt
        message_content = call_args.kwargs["messages"][0]["content"]
        assert DEFAULT_LLM_PROMPT in message_content
        # Check schema
        tool_schema = call_args.kwargs["tools"][0]["input_schema"]
        assert tool_schema == DEFAULT_LLM_SCHEMA


class TestEvaluateDispatcherLLM:
    """Tests for evaluate() dispatcher with llm_structured type."""

    @pytest.fixture
    def mock_anthropic(self):
        """Create mock Anthropic client."""
        with patch("little_loops.fsm.evaluators.anthropic") as mock_module:
            mock_client = MagicMock()
            mock_module.Anthropic.return_value = mock_client
            mock_module.APIError = Exception
            mock_module.APITimeoutError = TimeoutError
            mock_module.AuthenticationError = Exception
            yield mock_client

    def _create_tool_response(self, verdict: str, confidence: float, reason: str):
        """Helper to create mock tool use response."""
        mock_block = MagicMock()
        mock_block.type = "tool_use"
        mock_block.name = "evaluate"
        mock_block.input = {
            "verdict": verdict,
            "confidence": confidence,
            "reason": reason,
        }
        mock_response = MagicMock()
        mock_response.content = [mock_block]
        return mock_response

    def test_dispatch_llm_structured(self, mock_anthropic):
        """llm_structured type routes correctly."""
        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "success", 0.9, "Done"
        )

        config = EvaluateConfig(type="llm_structured")
        ctx = InterpolationContext()
        result = evaluate(config, "test output", 0, ctx)

        assert result.verdict == "success"
        assert result.details["confident"] is True

    def test_dispatch_llm_with_config_options(self, mock_anthropic):
        """llm_structured uses config options."""
        mock_anthropic.messages.create.return_value = self._create_tool_response(
            "success", 0.4, "Maybe"
        )

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
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_evaluators.py -v`
- [ ] All new tests pass: `python -m pytest scripts/tests/test_fsm_evaluators.py -k "LLM" -v`

---

### Phase 6: Update Existing Test

#### Overview
Update the existing test that expects ValueError to test actual functionality.

#### Changes Required

**File**: `scripts/tests/test_fsm_evaluators.py`
**Changes**: Remove or update the test_dispatch_llm_structured_raises test since it's now implemented

```python
# Delete lines 483-488 (test_dispatch_llm_structured_raises)
# This test is now replaced by TestEvaluateDispatcherLLM.test_dispatch_llm_structured
```

#### Success Criteria

**Automated Verification**:
- [ ] Tests pass: `python -m pytest scripts/tests/test_fsm_evaluators.py -v`

---

## Testing Strategy

### Unit Tests
- Mock Anthropic client to avoid real API calls
- Test all verdict types (success, failure, blocked, partial)
- Test confidence threshold handling
- Test uncertain suffix behavior
- Test custom schema support
- Test error handling (timeout, API error, auth error, no tool use)
- Test output truncation
- Test dispatcher routing

### Integration Tests
(Not implemented - would require real API key)

## References

- Original issue: `.issues/features/P2-FEAT-044-tier2-llm-evaluator.md`
- Tier 1 evaluators: `scripts/little_loops/fsm/evaluators.py:42-339`
- EvaluateConfig schema: `scripts/little_loops/fsm/schema.py:21-125`
- LLMConfig schema: `scripts/little_loops/fsm/schema.py:280-320`
- Design doc: `docs/generalized-fsm-loop.md`

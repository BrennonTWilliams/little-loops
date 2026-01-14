# FEAT-044: Tier 2 LLM Evaluator

## Summary

Implement the `llm_structured` evaluator that uses Claude API with structured output to interpret natural language action results. This is the **only** place in the FSM system that uses LLM structured output.

## Priority

P2 - Required for slash command evaluation

## Dependencies

- FEAT-040: FSM Schema Definition and Validation
- FEAT-043: Tier 1 Deterministic Evaluators (for EvaluationResult interface)

## Blocked By

- FEAT-040
- FEAT-043

## Description

Slash commands (like `/ll:manage_issue`) produce natural language output that cannot be evaluated deterministically. The `llm_structured` evaluator uses Claude's tool use with a defined schema to extract structured verdicts from this output.

### Design Principles

1. **Single Point of LLM Usage** - This is the only evaluator that makes API calls
2. **Configurable Schema** - Users can define custom verdict enums
3. **Confidence Tracking** - Results include confidence scores
4. **Graceful Degradation** - Clear error handling for API failures

### Files to Modify

```
scripts/little_loops/fsm/
└── evaluators.py  # Add evaluate_llm_structured()
```

## Technical Details

### Default Schema

When no custom schema is provided:

```python
DEFAULT_LLM_SCHEMA = {
    "type": "object",
    "properties": {
        "verdict": {
            "type": "string",
            "enum": ["success", "failure", "blocked", "partial"],
            "description": """
- success: The action completed its goal
- failure: The action failed, should retry
- blocked: Cannot proceed without external help
- partial: Made progress but not complete
"""
        },
        "confidence": {
            "type": "number",
            "minimum": 0,
            "maximum": 1,
            "description": "Confidence in this verdict (0-1)"
        },
        "reason": {
            "type": "string",
            "description": "Brief explanation"
        }
    },
    "required": ["verdict", "confidence", "reason"]
}
```

### Implementation

```python
# evaluators.py
import anthropic
from dataclasses import dataclass

@dataclass
class LLMEvaluatorConfig:
    prompt: str | None = None
    schema: dict | None = None
    min_confidence: float = 0.5
    uncertain_suffix: bool = False
    model: str = "claude-sonnet-4-20250514"
    max_tokens: int = 256
    timeout: int = 30


def evaluate_llm_structured(
    output: str,
    config: LLMEvaluatorConfig,
) -> EvaluationResult:
    """
    Evaluate action output using LLM with structured output.

    This is the ONLY place in the FSM system that uses LLM structured output.
    """
    client = anthropic.Anthropic()

    schema = config.schema or DEFAULT_LLM_SCHEMA
    prompt = config.prompt or "Evaluate whether this action succeeded based on its output."

    # Truncate output to avoid context limits
    truncated = output[-4000:] if len(output) > 4000 else output

    try:
        response = client.messages.create(
            model=config.model,
            max_tokens=config.max_tokens,
            timeout=config.timeout,
            messages=[{
                "role": "user",
                "content": f"{prompt}\n\n<action_output>\n{truncated}\n</action_output>"
            }],
            tools=[{
                "name": "evaluate",
                "description": "Provide your evaluation of the action result",
                "input_schema": schema
            }],
            tool_choice={"type": "tool", "name": "evaluate"}
        )
    except anthropic.APIError as e:
        return EvaluationResult(
            verdict="error",
            details={"error": f"LLM API error: {e}", "api_error": True}
        )
    except anthropic.APITimeoutError:
        return EvaluationResult(
            verdict="error",
            details={"error": "LLM evaluation timeout", "timeout": True}
        )

    # Extract structured result from tool use
    llm_result = None
    for block in response.content:
        if block.type == "tool_use" and block.name == "evaluate":
            llm_result = block.input
            break

    if llm_result is None:
        return EvaluationResult(
            verdict="error",
            details={"error": "No evaluation in LLM response"}
        )

    # Build result with confidence handling
    verdict = llm_result["verdict"]
    confidence = llm_result.get("confidence", 1.0)
    confident = confidence >= config.min_confidence

    # Optionally modify verdict for low confidence
    if config.uncertain_suffix and not confident:
        verdict = f"{verdict}_uncertain"

    return EvaluationResult(
        verdict=verdict,
        details={
            "confidence": confidence,
            "confident": confident,
            "reason": llm_result.get("reason", ""),
            "raw": llm_result,
        }
    )
```

### Custom Schema Example

Users can define custom verdicts for domain-specific evaluation:

```yaml
states:
  analyze:
    action: "/ll:audit_architecture patterns"
    evaluate:
      type: llm_structured
      schema:
        type: object
        properties:
          verdict:
            type: string
            enum: ["found_opportunities", "no_opportunities", "needs_investigation"]
          opportunities:
            type: array
            items: { type: string }
          confidence:
            type: number
        required: ["verdict", "confidence"]
    route:
      found_opportunities: "refactor"
      no_opportunities: "done"
      needs_investigation: "probe"
```

### Confidence-Based Routing

With `uncertain_suffix: true`, low-confidence verdicts get a suffix:

```yaml
states:
  fix:
    action: "/ll:manage_issue bug fix"
    evaluate:
      type: llm_structured
      min_confidence: 0.7
      uncertain_suffix: true
    route:
      success: "verify"
      success_uncertain: "probe"      # Low confidence → probe instead of verify
      failure: "fix"
      failure_uncertain: "probe"
      blocked: "escalate"
```

### Cost and Performance

| Metric | Value |
|--------|-------|
| Cost per evaluation | ~$0.001 (sonnet) |
| Latency | 300-800ms |
| Context used | ~4000 tokens max |

## Acceptance Criteria

- [ ] `evaluate_llm_structured()` calls Anthropic API with tool use
- [ ] Default schema provides success/failure/blocked/partial verdicts
- [ ] Custom schema support with user-defined verdict enums
- [ ] `min_confidence` threshold determines `confident` flag
- [ ] `uncertain_suffix: true` appends `_uncertain` to low-confidence verdicts
- [ ] API errors return `error` verdict with descriptive details
- [ ] Timeout handling with configurable timeout
- [ ] Output truncation to 4000 chars to avoid context limits
- [ ] Integration with `evaluate()` dispatcher from FEAT-043

## Testing Requirements

```python
# tests/unit/test_llm_evaluator.py
class TestLLMEvaluator:
    @pytest.fixture
    def mock_anthropic(self, monkeypatch):
        """Mock Anthropic client for deterministic testing."""
        mock_client = MockAnthropicClient()
        monkeypatch.setattr("anthropic.Anthropic", lambda: mock_client)
        return mock_client

    def test_success_verdict(self, mock_anthropic):
        """LLM returns success verdict."""
        mock_anthropic.set_response({
            "verdict": "success",
            "confidence": 0.9,
            "reason": "Fixed the bug"
        })

        result = evaluate_llm_structured("Fixed error in handlers.py", LLMEvaluatorConfig())
        assert result.verdict == "success"
        assert result.details["confident"] is True

    def test_low_confidence_without_suffix(self, mock_anthropic):
        """Low confidence without uncertain_suffix keeps original verdict."""
        mock_anthropic.set_response({
            "verdict": "success",
            "confidence": 0.4,
            "reason": "Maybe fixed"
        })

        config = LLMEvaluatorConfig(min_confidence=0.7, uncertain_suffix=False)
        result = evaluate_llm_structured("...", config)

        assert result.verdict == "success"  # Unchanged
        assert result.details["confident"] is False

    def test_low_confidence_with_suffix(self, mock_anthropic):
        """Low confidence with uncertain_suffix appends _uncertain."""
        mock_anthropic.set_response({
            "verdict": "success",
            "confidence": 0.4,
            "reason": "Maybe fixed"
        })

        config = LLMEvaluatorConfig(min_confidence=0.7, uncertain_suffix=True)
        result = evaluate_llm_structured("...", config)

        assert result.verdict == "success_uncertain"

    def test_custom_schema(self, mock_anthropic):
        """Custom schema with non-standard verdicts."""
        custom_schema = {
            "type": "object",
            "properties": {
                "verdict": {"type": "string", "enum": ["found", "not_found"]},
                "confidence": {"type": "number"}
            },
            "required": ["verdict"]
        }
        mock_anthropic.set_response({"verdict": "found", "confidence": 0.95})

        config = LLMEvaluatorConfig(schema=custom_schema)
        result = evaluate_llm_structured("...", config)

        assert result.verdict == "found"

    def test_api_error_handling(self, mock_anthropic):
        """API error returns error verdict."""
        mock_anthropic.raise_error(anthropic.APIError("Rate limited"))

        result = evaluate_llm_structured("...", LLMEvaluatorConfig())

        assert result.verdict == "error"
        assert "api_error" in result.details

    def test_timeout_handling(self, mock_anthropic):
        """Timeout returns error verdict."""
        mock_anthropic.raise_timeout()

        result = evaluate_llm_structured("...", LLMEvaluatorConfig())

        assert result.verdict == "error"
        assert result.details.get("timeout") is True

    def test_output_truncation(self, mock_anthropic):
        """Long output is truncated to last 4000 chars."""
        long_output = "x" * 10000
        mock_anthropic.set_response({"verdict": "success", "confidence": 1.0})

        evaluate_llm_structured(long_output, LLMEvaluatorConfig())

        # Verify truncation happened
        sent_content = mock_anthropic.last_request["messages"][0]["content"]
        assert len(sent_content) < 5000  # prompt + truncated output
```

## Reference

- Design doc: `docs/generalized-fsm-loop.md` section "Evaluator Types" - "Tier 2: LLM Evaluator"

"""Model pricing constants for token cost estimation.

Prices are in USD per million tokens ($/Mtok).
Source: Anthropic pricing page (as of June 2026).
"""

from __future__ import annotations

# Per-model pricing: {model_id: {token_type: usd_per_million}}
MODEL_PRICING: dict[str, dict[str, float]] = {
    # Claude 4.x
    "claude-opus-4-7": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_creation": 18.75,
    },
    "claude-opus-4-6": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_creation": 18.75,
    },
    "claude-sonnet-4-6": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    "claude-haiku-4-5-20251001": {
        "input": 0.80,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_creation": 1.0,
    },
    # Claude 3.x (legacy, may still appear in logs)
    "claude-opus-4-5": {
        "input": 15.0,
        "output": 75.0,
        "cache_read": 1.50,
        "cache_creation": 18.75,
    },
    "claude-sonnet-3-7": {
        "input": 3.0,
        "output": 15.0,
        "cache_read": 0.30,
        "cache_creation": 3.75,
    },
    "claude-haiku-3-5": {
        "input": 0.80,
        "output": 4.0,
        "cache_read": 0.08,
        "cache_creation": 1.0,
    },
}


def estimate_cost_usd(
    model: str,
    input_tokens: int,
    output_tokens: int,
    cache_read_tokens: int = 0,
    cache_creation_tokens: int = 0,
) -> float | None:
    """Estimate cost in USD for a token usage event.

    Returns None if the model is not in MODEL_PRICING.
    """
    pricing = MODEL_PRICING.get(model)
    if pricing is None:
        return None
    per_m = 1_000_000.0
    return (
        input_tokens * pricing["input"] / per_m
        + output_tokens * pricing["output"] / per_m
        + cache_read_tokens * pricing["cache_read"] / per_m
        + cache_creation_tokens * pricing["cache_creation"] / per_m
    )

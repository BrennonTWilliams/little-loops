"""Tests for the pricing module."""

from __future__ import annotations

from little_loops.pricing import MODEL_PRICING, estimate_cost_usd


class TestModelPricing:
    def test_known_models_present(self) -> None:
        assert "claude-opus-4-7" in MODEL_PRICING
        assert "claude-sonnet-4-6" in MODEL_PRICING
        assert "claude-haiku-4-5-20251001" in MODEL_PRICING

    def test_pricing_fields_present(self) -> None:
        for model, prices in MODEL_PRICING.items():
            assert "input" in prices, f"{model} missing input price"
            assert "output" in prices, f"{model} missing output price"
            assert "cache_read" in prices, f"{model} missing cache_read price"
            assert "cache_creation" in prices, f"{model} missing cache_creation price"

    def test_output_more_expensive_than_input(self) -> None:
        for model, prices in MODEL_PRICING.items():
            assert prices["output"] > prices["input"], (
                f"{model}: output should cost more than input"
            )


class TestEstimateCostUsd:
    def test_known_model_returns_float(self) -> None:
        cost = estimate_cost_usd("claude-sonnet-4-6", 1000, 200)
        assert cost is not None
        assert cost > 0.0

    def test_unknown_model_returns_none(self) -> None:
        assert estimate_cost_usd("unknown-model-xyz", 1000, 200) is None

    def test_zero_tokens_returns_zero(self) -> None:
        cost = estimate_cost_usd("claude-sonnet-4-6", 0, 0, 0, 0)
        assert cost == 0.0

    def test_cache_read_cheaper_than_input(self) -> None:
        # 1M cache_read tokens should cost less than 1M input tokens
        cost_input = estimate_cost_usd("claude-opus-4-7", 1_000_000, 0)
        cost_cache = estimate_cost_usd("claude-opus-4-7", 0, 0, 1_000_000, 0)
        assert cost_input is not None
        assert cost_cache is not None
        assert cost_cache < cost_input

    def test_accuracy_within_15_percent(self) -> None:
        # 1M input + 200K output for sonnet-4-6 = $3.00 + $3.00 = $6.00
        cost = estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 200_000)
        assert cost is not None
        expected = 3.0 + 15.0 * 0.2  # $3.00 + $3.00
        assert abs(cost - expected) / expected < 0.15

    def test_all_four_fields_contribute(self) -> None:
        cost_all = estimate_cost_usd("claude-opus-4-7", 100, 100, 100, 100)
        cost_input_only = estimate_cost_usd("claude-opus-4-7", 100, 0, 0, 0)
        assert cost_all is not None
        assert cost_input_only is not None
        assert cost_all > cost_input_only

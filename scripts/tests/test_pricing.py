"""Tests for the pricing module."""

from __future__ import annotations

from collections.abc import Iterator
from datetime import date
from unittest.mock import patch

import pytest

from little_loops import pricing
from little_loops.pricing import BATCH_DISCOUNT, MODEL_PRICING, estimate_cost_usd

SYNTHETIC_MODEL = "claude-synthetic-intro"

# Live rates (USD/Mtok): input, output, cache_read, cache_creation. Checked 2026-09-24.
LIVE_RATES: dict[str, tuple[float, float, float, float]] = {
    "claude-fable-5": (10.0, 50.0, 1.0, 12.50),
    "claude-opus-5": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-8": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-7": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-6": (5.0, 25.0, 0.50, 6.25),
    "claude-opus-4-5": (5.0, 25.0, 0.50, 6.25),
    "claude-sonnet-5": (2.0, 10.0, 0.20, 2.50),
    "claude-sonnet-4-6": (3.0, 15.0, 0.30, 3.75),
    "claude-sonnet-3-7": (3.0, 15.0, 0.30, 3.75),
    "claude-haiku-4-5-20251001": (1.0, 5.0, 0.10, 1.25),
    "claude-haiku-3-5": (0.80, 4.0, 0.08, 1.0),
}


@pytest.fixture
def synthetic_intro_pricing(monkeypatch: pytest.MonkeyPatch) -> Iterator[str]:
    """Register a synthetic model with an intro rate expiring 2026-08-31.

    Standard rate is 3/15/0.30/3.75; intro rate is 2/10/0.20/2.50. Yields the model id.
    """
    monkeypatch.setitem(
        MODEL_PRICING,
        SYNTHETIC_MODEL,
        {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_creation": 3.75},
    )
    monkeypatch.setitem(
        pricing.INTRO_PRICING,
        SYNTHETIC_MODEL,
        {
            "expires": "2026-08-31",
            "input": 2.0,
            "output": 10.0,
            "cache_read": 0.20,
            "cache_creation": 2.50,
        },
    )
    yield SYNTHETIC_MODEL


class TestModelPricing:
    def test_known_models_present(self) -> None:
        assert "claude-opus-4-7" in MODEL_PRICING
        assert "claude-sonnet-4-6" in MODEL_PRICING
        assert "claude-haiku-4-5-20251001" in MODEL_PRICING
        assert "claude-sonnet-5" in MODEL_PRICING
        assert "claude-opus-4-8" in MODEL_PRICING
        assert "claude-fable-5" in MODEL_PRICING

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


class TestLiveRates:
    @pytest.mark.parametrize("model", sorted(LIVE_RATES))
    def test_rates_match_live_table(self, model: str) -> None:
        inp, out, cr, cc = LIVE_RATES[model]
        assert MODEL_PRICING[model] == {
            "input": inp,
            "output": out,
            "cache_read": cr,
            "cache_creation": cc,
        }

    def test_every_model_pinned(self) -> None:
        assert set(MODEL_PRICING) == set(LIVE_RATES)

    def test_sonnet_5_standard_rate_any_date(self) -> None:
        assert estimate_cost_usd("claude-sonnet-5", 1_000_000, 1_000_000) == 12.0
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 15)
            mock_date.fromisoformat = date.fromisoformat
            assert estimate_cost_usd("claude-sonnet-5", 1_000_000, 1_000_000) == 12.0

    @pytest.mark.parametrize("model", sorted(LIVE_RATES))
    def test_batch_halves_each_rate(self, model: str) -> None:
        sync = estimate_cost_usd(model, 1_000_000, 1_000_000, 1_000_000, 1_000_000)
        batch = estimate_cost_usd(model, 1_000_000, 1_000_000, 1_000_000, 1_000_000, is_batch=True)
        assert sync is not None and batch is not None
        assert batch == sync * BATCH_DISCOUNT


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


class TestIntroPricing:
    def test_pre_expiry_uses_intro_rate(self, synthetic_intro_pricing: str) -> None:
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 15)
            mock_date.fromisoformat = date.fromisoformat
            cost = estimate_cost_usd(synthetic_intro_pricing, 1_000_000, 1_000_000)
        assert cost == 2.0 + 10.0

    def test_post_expiry_uses_standard_rate(self, synthetic_intro_pricing: str) -> None:
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 9, 1)
            mock_date.fromisoformat = date.fromisoformat
            cost = estimate_cost_usd(synthetic_intro_pricing, 1_000_000, 1_000_000)
        assert cost == 3.0 + 15.0

    def test_boundary_2026_08_31_uses_intro_rate(self, synthetic_intro_pricing: str) -> None:
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 31)
            mock_date.fromisoformat = date.fromisoformat
            cost = estimate_cost_usd(synthetic_intro_pricing, 1_000_000, 1_000_000)
        assert cost == 2.0 + 10.0

    def test_unaffected_model_regression(self, synthetic_intro_pricing: str) -> None:
        with patch("little_loops.pricing.date") as mock_date:
            mock_date.today.return_value = date(2026, 8, 15)
            mock_date.fromisoformat = date.fromisoformat
            cost = estimate_cost_usd("claude-sonnet-4-6", 1_000_000, 1_000_000)
        assert cost == 3.0 + 15.0

    def test_intro_sub_dict_has_all_rate_keys(self, synthetic_intro_pricing: str) -> None:
        for model, rates in pricing.INTRO_PRICING.items():
            for key in ("input", "output", "cache_read", "cache_creation", "expires"):
                assert key in rates, f"{model} intro pricing missing {key}"


class TestBatchDiscount:
    def test_is_batch_false_by_default(self) -> None:
        cost_default = estimate_cost_usd("claude-sonnet-4-6", 1000, 200)
        cost_explicit_false = estimate_cost_usd("claude-sonnet-4-6", 1000, 200, 0, 0, False)
        assert cost_default == cost_explicit_false

    def test_is_batch_halves_cost(self) -> None:
        cost_sync = estimate_cost_usd("claude-sonnet-4-6", 1000, 200, 50, 50)
        cost_batch = estimate_cost_usd("claude-sonnet-4-6", 1000, 200, 50, 50, is_batch=True)
        assert cost_sync is not None
        assert cost_batch is not None
        assert cost_batch == cost_sync * BATCH_DISCOUNT

    def test_is_batch_unknown_model_returns_none(self) -> None:
        assert estimate_cost_usd("unknown-model-xyz", 1000, 200, is_batch=True) is None

    def test_is_batch_zero_tokens_returns_zero(self) -> None:
        assert estimate_cost_usd("claude-sonnet-4-6", 0, 0, 0, 0, is_batch=True) == 0.0

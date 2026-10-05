"""Pure tests for ``little_loops.utility`` curves and aggregators (FEAT-3681)."""

from __future__ import annotations

import math
from datetime import UTC, datetime, timedelta, timezone

import pytest

from little_loops.utility import frequency_score, recency_score, weighted_geometric, weighted_sum

NOW = datetime(2026, 3, 15, 12, 0, 0, tzinfo=UTC)
HUGE = 10**400


class TestFrequencyScore:
    def test_zero_is_zero(self) -> None:
        assert frequency_score(0) == 0.0

    def test_legacy_formula(self) -> None:
        assert frequency_score(3) == math.log1p(3) / math.log1p(50)

    def test_reference_count_is_one_and_uncapped(self) -> None:
        assert frequency_score(50) == pytest.approx(1.0)
        assert frequency_score(61) > 1.0

    @pytest.mark.parametrize("bad", [-1, True, False, 1.5, 2.0, "3", None, HUGE])
    def test_invalid_counts_raise_value_error(self, bad: object) -> None:
        with pytest.raises(ValueError):
            frequency_score(bad)  # type: ignore[arg-type]


class TestRecencyScore:
    def test_missing_and_malformed_are_zero(self) -> None:
        assert recency_score(None, as_of=NOW) == 0.0
        assert recency_score("", as_of=NOW) == 0.0
        assert recency_score("not-a-date", as_of=NOW) == 0.0

    def test_naive_timestamp_is_zero(self) -> None:
        assert recency_score("2026-03-14T10:00:00", as_of=NOW) == 0.0

    def test_half_life(self) -> None:
        stamp = (NOW - timedelta(days=7)).isoformat()
        assert recency_score(stamp, as_of=NOW) == pytest.approx(0.5)

    def test_z_suffix(self) -> None:
        assert recency_score("2026-03-15T12:00:00Z", as_of=NOW) == 1.0

    def test_future_timestamp_exceeds_one(self) -> None:
        assert recency_score("2026-03-20T12:00:00Z", as_of=NOW) > 1.0

    def test_extreme_future_overflows(self) -> None:
        with pytest.raises(OverflowError):
            recency_score("9999-12-31T00:00:00Z", as_of=NOW)

    def test_equivalent_aware_instants_agree(self) -> None:
        other_zone = NOW.astimezone(timezone(timedelta(hours=-5)))
        stamp = "2026-03-10T00:00:00Z"
        assert recency_score(stamp, as_of=other_zone) == recency_score(stamp, as_of=NOW)

    @pytest.mark.parametrize("bad", [datetime(2026, 3, 15), "2026-03-15", None, 0])
    @pytest.mark.parametrize("stamp", [None, "", "2026-03-10T00:00:00Z"])
    def test_invalid_as_of_raises_even_without_timestamp(
        self, bad: object, stamp: str | None
    ) -> None:
        with pytest.raises(ValueError):
            recency_score(stamp, as_of=bad)  # type: ignore[arg-type]


class TestWeightedSum:
    def test_matches_legacy_arithmetic_exactly(self) -> None:
        scores = {"frequency": 0.7, "recency": 1.3, "success": 0.1}
        weights = {"frequency": 0.50, "recency": 0.30, "success": 0.20}
        assert weighted_sum(scores, weights) == 0.50 * 0.7 + 0.30 * 1.3 + 0.20 * 0.1

    def test_unnormalized_and_unclipped(self) -> None:
        assert weighted_sum({"a": 5.0, "b": 2}, {"a": 2, "b": 3}) == 16.0

    def test_empty_is_zero(self) -> None:
        assert weighted_sum({}, {}) == 0.0

    def test_iterates_in_weight_order(self) -> None:
        scores = {"a": 0.1, "b": 0.2, "c": 0.3}
        forward = weighted_sum(scores, {"a": 0.5, "b": 0.3, "c": 0.2})
        assert forward == 0.5 * 0.1 + 0.3 * 0.2 + 0.2 * 0.3

    def test_zero_weight_axis_still_needs_valid_score(self) -> None:
        assert weighted_sum({"a": 1.0, "b": 0.0}, {"a": 1, "b": 0}) == 1.0
        with pytest.raises(ValueError, match="'b'"):
            weighted_sum({"a": 1.0, "b": float("nan")}, {"a": 1, "b": 0})

    @pytest.mark.parametrize(
        ("scores", "weights"),
        [
            ({"a": None}, {"a": 1}),  # missing score
            ({}, {"a": 1}),  # absent score
            ({"a": 1, "x": 1}, {"a": 1}),  # score without weight
            ({"a": True}, {"a": 1}),
            ({"a": "1"}, {"a": 1}),
            ({"a": -0.1}, {"a": 1}),
            ({"a": float("inf")}, {"a": 1}),
            ({"a": 1}, {"a": True}),
            ({"a": 1}, {"a": -1}),
            ({"a": 1}, {"a": float("nan")}),
            ({"a": 1}, {"a": float("inf")}),
            ({"a": 1}, {"a": HUGE}),
            ({"a": HUGE}, {"a": 1}),
            ({"a": 1}, {"a": "1"}),
        ],
    )
    def test_invalid_arguments_raise_value_error(self, scores: dict, weights: dict) -> None:
        with pytest.raises(ValueError):
            weighted_sum(scores, weights)

    def test_overflow_is_a_controlled_error(self) -> None:
        with pytest.raises(ValueError, match="overflow"):
            weighted_sum({"a": 1e300, "b": 1e300}, {"a": 1e300, "b": 1e300})


class TestWeightedGeometric:
    def test_analytical_sparse_oracle(self) -> None:
        # a=0.25 and c=1.0 equally weighted: sqrt(0.25 * 1.0) = 0.5. b is missing and
        # d is disabled, so neither enters the denominator.
        scores = {"a": 0.25, "b": None, "c": 1.0, "d": 0.5}
        weights = {"a": 1, "b": 5, "c": 1, "d": 0}
        assert weighted_geometric(scores, weights) == pytest.approx(0.5)

    def test_single_zero_score_yields_floor(self) -> None:
        assert weighted_geometric({"a": 0.0}, {"a": 1}) == pytest.approx(1e-6)
        assert weighted_geometric({"a": 0.0}, {"a": 1}, floor=0.1) == pytest.approx(0.1)

    def test_value_below_floor_is_floored(self) -> None:
        assert weighted_geometric({"a": 1e-9}, {"a": 1}, floor=1e-3) == pytest.approx(1e-3)

    def test_unequal_weights(self) -> None:
        # exp((3*ln(0.5) + 1*ln(1.0)) / 4) = 0.5 ** 0.75
        got = weighted_geometric({"a": 0.5, "b": 1.0}, {"a": 3, "b": 1})
        assert got == pytest.approx(0.5**0.75)

    @pytest.mark.parametrize(
        ("scores", "weights"),
        [
            ({}, {}),
            ({"a": None}, {"a": 1}),
            ({"a": 0.5}, {"a": 0}),
            ({"a": 0.5, "b": 0.5}, {"a": 0, "b": 0}),
            ({}, {"a": 1}),
        ],
    )
    def test_none_when_no_positive_weight_axis_resolves(self, scores: dict, weights: dict) -> None:
        assert weighted_geometric(scores, weights) is None

    def test_weight_scale_invariance(self) -> None:
        scores = {"a": 0.3, "b": 0.8, "c": 0.55}
        base = weighted_geometric(scores, {"a": 1, "b": 2, "c": 3})
        for factor in (1e-12, 7.0, 1e12):
            scaled = {k: v * factor for k, v in {"a": 1, "b": 2, "c": 3}.items()}
            assert weighted_geometric(scores, scaled) == pytest.approx(base)

    def test_large_equal_weights_do_not_overflow(self) -> None:
        got = weighted_geometric({"a": 0.5, "b": 0.5}, {"a": 1e308, "b": 1e308})
        assert got == pytest.approx(0.5)

    def test_small_positive_weights(self) -> None:
        got = weighted_geometric({"a": 0.25, "b": 1.0}, {"a": 1e-300, "b": 1e-300})
        assert got == pytest.approx(0.5)

    @pytest.mark.parametrize(
        ("scores", "weights"),
        [
            ({"a": 1.5}, {"a": 1}),
            ({"a": -0.1}, {"a": 1}),
            ({"a": float("nan")}, {"a": 1}),
            ({"a": True}, {"a": 1}),
            ({"a": "0.5"}, {"a": 1}),
            ({"a": 0.5}, {"a": -1}),
            ({"a": 0.5}, {"a": float("inf")}),
            ({"a": HUGE}, {"a": 1}),
            ({"a": 0.5}, {"a": HUGE}),
            ({"x": 0.5}, {"a": 1}),  # score without a weight
            ({"a": 2.0}, {"a": 0}),  # zero-weight axis still validated
            ({"a": None}, {"a": HUGE}),  # invalid weight even on missing evidence
        ],
    )
    def test_invalid_arguments_raise_value_error(self, scores: dict, weights: dict) -> None:
        with pytest.raises(ValueError):
            weighted_geometric(scores, weights)

    @pytest.mark.parametrize("floor", [0, 0.0, 1, 1.0, -1e-6, 2, True, float("nan"), "0.1", HUGE])
    def test_invalid_floor_raises_even_on_empty_evidence(self, floor: object) -> None:
        with pytest.raises(ValueError):
            weighted_geometric({}, {}, floor=floor)  # type: ignore[arg-type]

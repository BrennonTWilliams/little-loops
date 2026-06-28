"""Unit tests for little_loops.analytics.association — PMI/lift helper."""

from __future__ import annotations

import math

import pytest

from little_loops.analytics.association import (
    LIFT_THRESHOLD,
    AssociationScores,
    compute_lift,
    compute_pmi,
)


class TestComputePMI:
    """Tests for compute_pmi() boundary cases and known values."""

    def test_neutral_pair_pmi_zero(self) -> None:
        """PMI is 0 when the pair co-occurs exactly at the frequency-prior rate."""
        # count_ab=1, count_a=2, count_b=4, total=8 → 1*8/(2*4)=1.0 → log(1)=0
        result = compute_pmi(count_ab=1, count_a=2, count_b=4, total_unigrams=8)
        assert result == pytest.approx(0.0, abs=1e-9)

    def test_above_prior_positive_pmi(self) -> None:
        """PMI is positive when pair co-occurs more than the frequency prior predicts."""
        # count_ab=4, count_a=4, count_b=4, total=8 → 4*8/(4*4)=2 → log(2)≈0.693
        result = compute_pmi(count_ab=4, count_a=4, count_b=4, total_unigrams=8)
        assert result == pytest.approx(math.log(2.0), abs=1e-9)

    def test_below_prior_negative_pmi(self) -> None:
        """PMI is negative when pair co-occurs less than the frequency prior predicts."""
        # count_ab=1, count_a=4, count_b=4, total=8 → 1*8/(4*4)=0.5 → log(0.5)≈-0.693
        result = compute_pmi(count_ab=1, count_a=4, count_b=4, total_unigrams=8)
        assert result == pytest.approx(math.log(0.5), abs=1e-9)

    def test_formula_consistency(self) -> None:
        """PMI equals log(lift) for any valid inputs."""
        cases = [
            (2, 3, 4, 10),
            (5, 8, 6, 20),
            (1, 2, 2, 6),
        ]
        for count_ab, count_a, count_b, total in cases:
            pmi = compute_pmi(count_ab, count_a, count_b, total)
            lift = compute_lift(count_ab, count_a, count_b, total)
            assert pmi == pytest.approx(math.log(lift), abs=1e-9)

    def test_zero_count_ab_raises(self) -> None:
        """count_ab=0 raises ValueError (log(0) is undefined)."""
        with pytest.raises(ValueError, match="count_ab"):
            compute_pmi(count_ab=0, count_a=3, count_b=2, total_unigrams=10)

    def test_zero_count_a_raises(self) -> None:
        """count_a=0 raises ValueError."""
        with pytest.raises(ValueError, match="count_a"):
            compute_pmi(count_ab=1, count_a=0, count_b=2, total_unigrams=10)

    def test_zero_count_b_raises(self) -> None:
        """count_b=0 raises ValueError."""
        with pytest.raises(ValueError, match="count_b"):
            compute_pmi(count_ab=1, count_a=3, count_b=0, total_unigrams=10)

    def test_zero_total_raises(self) -> None:
        """total_unigrams=0 raises ValueError."""
        with pytest.raises(ValueError, match="total_unigrams"):
            compute_pmi(count_ab=1, count_a=3, count_b=2, total_unigrams=0)

    def test_negative_count_raises(self) -> None:
        """Negative counts raise ValueError."""
        with pytest.raises(ValueError):
            compute_pmi(count_ab=-1, count_a=3, count_b=2, total_unigrams=10)


class TestComputeLift:
    """Tests for compute_lift() boundary cases and known values."""

    def test_neutral_pair_lift_one(self) -> None:
        """Lift is 1.0 when pair co-occurs at exactly the frequency-prior rate."""
        result = compute_lift(count_ab=1, count_a=2, count_b=4, total_unigrams=8)
        assert result == pytest.approx(1.0, abs=1e-9)

    def test_above_prior_lift_greater_than_one(self) -> None:
        """Lift > 1 when pair co-occurs more than chance predicts."""
        result = compute_lift(count_ab=4, count_a=4, count_b=4, total_unigrams=8)
        assert result == pytest.approx(2.0, abs=1e-9)

    def test_below_prior_lift_less_than_one(self) -> None:
        """Lift < 1 when pair co-occurs less than chance predicts."""
        result = compute_lift(count_ab=1, count_a=4, count_b=4, total_unigrams=8)
        assert result == pytest.approx(0.5, abs=1e-9)

    def test_known_value(self) -> None:
        """Verify lift = count(a,b)*total / (count_a * count_b)."""
        # 3*20 / (5*6) = 60/30 = 2.0
        result = compute_lift(count_ab=3, count_a=5, count_b=6, total_unigrams=20)
        assert result == pytest.approx(2.0, abs=1e-9)

    def test_lift_always_positive(self) -> None:
        """Lift is always positive for valid inputs."""
        cases = [(1, 1, 1, 1), (2, 3, 4, 10), (5, 8, 6, 20)]
        for args in cases:
            assert compute_lift(*args) > 0.0

    def test_zero_count_ab_raises(self) -> None:
        """count_ab=0 raises ValueError."""
        with pytest.raises(ValueError, match="count_ab"):
            compute_lift(count_ab=0, count_a=3, count_b=2, total_unigrams=10)

    def test_zero_count_a_raises(self) -> None:
        """count_a=0 raises ValueError."""
        with pytest.raises(ValueError, match="count_a"):
            compute_lift(count_ab=1, count_a=0, count_b=2, total_unigrams=10)

    def test_zero_count_b_raises(self) -> None:
        """count_b=0 raises ValueError."""
        with pytest.raises(ValueError, match="count_b"):
            compute_lift(count_ab=1, count_a=3, count_b=0, total_unigrams=10)

    def test_zero_total_raises(self) -> None:
        """total_unigrams=0 raises ValueError."""
        with pytest.raises(ValueError, match="total_unigrams"):
            compute_lift(count_ab=1, count_a=3, count_b=2, total_unigrams=0)


class TestAssociationScores:
    """Tests for AssociationScores dataclass."""

    def test_dataclass_fields(self) -> None:
        """AssociationScores has pmi and lift fields."""
        scores = AssociationScores(pmi=1.5, lift=4.5)
        assert scores.pmi == pytest.approx(1.5)
        assert scores.lift == pytest.approx(4.5)

    def test_frequency_prior_equivalent(self) -> None:
        """AssociationScores with lift < LIFT_THRESHOLD is frequency-prior equivalent."""
        below = AssociationScores(pmi=-0.693, lift=0.5)
        assert below.lift < LIFT_THRESHOLD

    def test_above_threshold(self) -> None:
        """AssociationScores with lift >= LIFT_THRESHOLD is above the frequency prior."""
        above = AssociationScores(pmi=0.693, lift=2.0)
        assert above.lift >= LIFT_THRESHOLD


class TestLiftThreshold:
    """Tests for the LIFT_THRESHOLD constant."""

    def test_threshold_is_one(self) -> None:
        """Default LIFT_THRESHOLD is 1.0 (exactly the frequency-prior rate)."""
        assert LIFT_THRESHOLD == 1.0

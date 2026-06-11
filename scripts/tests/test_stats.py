"""Unit tests for little_loops.stats — Wilson 95% binomial CI formula."""

from __future__ import annotations

import math

import pytest

from little_loops.stats import wilson_ci


class TestWilsonCI:
    """Tests for wilson_ci() boundary cases and known values."""

    def test_all_pass(self) -> None:
        """k=n: upper bound is 1.0, lower bound is in (0.7, 1)."""
        lo, hi = wilson_ci(10, 10)
        assert hi == pytest.approx(1.0)
        assert lo > 0.7
        assert lo < 1.0

    def test_all_fail(self) -> None:
        """k=0: lower bound is 0.0, upper bound is in (0, 0.3)."""
        lo, hi = wilson_ci(0, 10)
        assert lo == pytest.approx(0.0)
        assert hi > 0.0
        assert hi < 0.3

    def test_n_equals_1_pass(self) -> None:
        """n=1, k=1: upper bound is 1.0, lower is positive."""
        lo, hi = wilson_ci(1, 1)
        assert hi == pytest.approx(1.0)
        assert lo >= 0.0
        assert lo < 1.0

    def test_n_equals_1_fail(self) -> None:
        """n=1, k=0: lower bound is 0.0, upper is in (0, 1)."""
        lo, hi = wilson_ci(0, 1)
        assert lo == pytest.approx(0.0)
        assert hi > 0.0
        assert hi < 1.0

    def test_midrange_symmetric(self) -> None:
        """k=5, n=10: CI is symmetric around 0.5."""
        lo, hi = wilson_ci(5, 10)
        center = (lo + hi) / 2
        assert center == pytest.approx(0.5, abs=0.001)
        assert lo < 0.5
        assert hi > 0.5

    def test_bounds_clamped_to_unit_interval(self) -> None:
        """CI bounds are always in [0, 1] for all valid inputs."""
        cases = [(0, 1), (1, 1), (0, 100), (100, 100), (50, 100), (0, 5), (5, 5)]
        for k, n in cases:
            lo, hi = wilson_ci(k, n)
            assert 0.0 <= lo <= 1.0, f"lower={lo} out of [0,1] for k={k}, n={n}"
            assert 0.0 <= hi <= 1.0, f"upper={hi} out of [0,1] for k={k}, n={n}"

    def test_lower_le_upper(self) -> None:
        """lower <= upper for all valid inputs."""
        cases = [(0, 5), (3, 5), (5, 5), (1, 1), (0, 1), (7, 10)]
        for k, n in cases:
            lo, hi = wilson_ci(k, n)
            assert lo <= hi, f"lo={lo} > hi={hi} for k={k}, n={n}"

    def test_known_values_midrange(self) -> None:
        """Verify computed bounds match manual calculation for k=7, n=10."""
        # p=0.7, z=1.96, z²=3.8416
        # denominator = 1 + 3.8416/10 = 1.38416
        # center = (0.7 + 0.19208) / 1.38416 ≈ 0.6445
        # margin = 1.96 * sqrt(0.021 + 0.0096) / 1.38416 ≈ 0.2477
        # lower ≈ 0.397, upper ≈ 0.892
        lo, hi = wilson_ci(7, 10)
        assert lo == pytest.approx(0.397, abs=0.002)
        assert hi == pytest.approx(0.892, abs=0.002)

    def test_known_values_all_fail(self) -> None:
        """Verify computed upper bound for k=0, n=10 ≈ 0.278."""
        # p=0, center = 0.19208/1.38416 ≈ 0.1388
        # margin = 1.96*0.098/1.38416 ≈ 0.1388
        # upper = 2 * 0.1388 ≈ 0.2776
        lo, hi = wilson_ci(0, 10)
        assert lo == pytest.approx(0.0)
        assert hi == pytest.approx(0.278, abs=0.002)

    def test_invalid_n_zero(self) -> None:
        """n=0 raises ValueError."""
        with pytest.raises(ValueError, match="n must be positive"):
            wilson_ci(0, 0)

    def test_invalid_n_negative(self) -> None:
        """n<0 raises ValueError."""
        with pytest.raises(ValueError, match="n must be positive"):
            wilson_ci(0, -1)

    def test_invalid_k_negative(self) -> None:
        """k<0 raises ValueError."""
        with pytest.raises(ValueError, match="k must be in"):
            wilson_ci(-1, 10)

    def test_invalid_k_exceeds_n(self) -> None:
        """k>n raises ValueError."""
        with pytest.raises(ValueError, match="k must be in"):
            wilson_ci(11, 10)

    def test_custom_z_score(self) -> None:
        """Custom z value narrows or widens the interval."""
        lo_95, hi_95 = wilson_ci(5, 10, z=1.96)
        lo_99, hi_99 = wilson_ci(5, 10, z=2.576)
        # 99% CI must be wider than 95%
        assert lo_99 < lo_95
        assert hi_99 > hi_95

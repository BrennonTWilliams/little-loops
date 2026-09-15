"""Unit tests for little_loops.stats — Wilson 95% binomial CI formula."""

from __future__ import annotations

import pytest

from little_loops.stats import paired_direction, proportion_diff_ci, wilson_ci


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


class TestPairedDirection:
    """Tests for paired_direction() sign test on discordant pairs (ENH-3298)."""

    def test_no_discordant_pairs_is_inconclusive(self) -> None:
        """All-concordant items (b=c=0) carry no directional information."""
        per_item = [
            {"harness_pass": True, "baseline_pass": True},
            {"harness_pass": False, "baseline_pass": False},
        ]
        direction, b, c = paired_direction(per_item)
        assert direction == "inconclusive"
        assert b == 0
        assert c == 0

    def test_small_n_inconclusive(self) -> None:
        """n=5, b=2, c=0: too few discordant pairs to separate from chance."""
        per_item = [
            {"harness_pass": True, "baseline_pass": False},
            {"harness_pass": True, "baseline_pass": False},
            {"harness_pass": True, "baseline_pass": True},
            {"harness_pass": False, "baseline_pass": False},
            {"harness_pass": False, "baseline_pass": False},
        ]
        direction, b, c = paired_direction(per_item)
        assert direction == "inconclusive"
        assert b == 2
        assert c == 0

    def test_all_discordant_one_way_favors_harness(self) -> None:
        """All discordant pairs favor harness: decisive in harness's favor."""
        per_item = [{"harness_pass": True, "baseline_pass": False} for _ in range(8)]
        direction, b, c = paired_direction(per_item)
        assert direction == "harness"
        assert b == 8
        assert c == 0

    def test_all_discordant_one_way_favors_baseline(self) -> None:
        """All discordant pairs favor baseline: decisive in baseline's favor."""
        per_item = [{"harness_pass": False, "baseline_pass": True} for _ in range(8)]
        direction, b, c = paired_direction(per_item)
        assert direction == "baseline"
        assert b == 0
        assert c == 8

    def test_decisive_majority_favors_harness(self) -> None:
        """9/10 discordant pairs favor harness: separates from chance."""
        per_item = [{"harness_pass": True, "baseline_pass": False} for _ in range(9)]
        per_item.append({"harness_pass": False, "baseline_pass": True})
        direction, b, c = paired_direction(per_item)
        assert direction == "harness"
        assert b == 9
        assert c == 1

    def test_custom_keys(self) -> None:
        """harness_key/baseline_key select alternate dict keys."""
        per_item = [{"h": True, "b": False} for _ in range(8)]
        direction, b, c = paired_direction(per_item, harness_key="h", baseline_key="b")
        assert direction == "harness"
        assert b == 8
        assert c == 0


class TestProportionDiffCi:
    """Tests for proportion_diff_ci() -- Newcombe method 10 (ENH-3465 D4)."""

    def test_three_of_three_vs_zero_of_three(self) -> None:
        """The case the old CI-overlap rule got wrong: classifies decisively ahead."""
        lo, hi = proportion_diff_ci(3, 3, 0, 3)
        assert lo == pytest.approx(0.2059, abs=1e-3)
        assert hi == pytest.approx(1.0)

    def test_ten_of_ten_vs_five_of_ten(self) -> None:
        lo, _hi = proportion_diff_ci(10, 10, 5, 10)
        assert lo == pytest.approx(0.1174, abs=1e-3)

    def test_eight_of_ten_vs_three_of_ten(self) -> None:
        lo, _hi = proportion_diff_ci(8, 10, 3, 10)
        assert lo == pytest.approx(0.0665, abs=1e-3)

    def test_symmetric_case_is_negative(self) -> None:
        """Swapping the arguments negates and mirrors the interval."""
        lo, hi = proportion_diff_ci(0, 3, 3, 3)
        assert lo == pytest.approx(-1.0)
        assert hi == pytest.approx(-0.2059, abs=1e-3)

    def test_equal_proportions_straddles_zero(self) -> None:
        lo, hi = proportion_diff_ci(1, 3, 1, 3)
        assert lo < 0 < hi

    def test_raises_on_zero_n1(self) -> None:
        with pytest.raises(ValueError, match="n must be positive"):
            proportion_diff_ci(0, 0, 1, 3)

    def test_raises_on_zero_n2(self) -> None:
        with pytest.raises(ValueError, match="n must be positive"):
            proportion_diff_ci(1, 3, 0, 0)

    def test_custom_z_widens_interval(self) -> None:
        lo_95, hi_95 = proportion_diff_ci(2, 5, 1, 5, z=1.96)
        lo_99, hi_99 = proportion_diff_ci(2, 5, 1, 5, z=2.576)
        assert lo_99 < lo_95
        assert hi_99 > hi_95

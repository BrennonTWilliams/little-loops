"""Statistical utilities for loop evaluation reporting.

Provides Wilson 95% binomial confidence intervals for honest uncertainty
reporting at small sample sizes where naive ±√(p(1-p)/n) estimates are
unreliable near 0 or 1.
"""

from __future__ import annotations

import math
from typing import Any, Literal


def wilson_ci(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    """Compute Wilson binomial confidence interval.

    Formula: (p + z²/2n ± z√(p(1-p)/n + z²/4n²)) / (1 + z²/n)

    Args:
        k: Number of successes (0 <= k <= n).
        n: Total trials (n > 0).
        z: Z-score for confidence level (default 1.96 for 95% CI).

    Returns:
        (lower, upper) bounds as floats clamped to [0, 1].

    Raises:
        ValueError: If n <= 0, k < 0, or k > n.
    """
    if n <= 0:
        raise ValueError(f"n must be positive, got {n}")
    if k < 0 or k > n:
        raise ValueError(f"k must be in [0, n], got k={k}, n={n}")

    p = k / n
    z2 = z * z
    denominator = 1.0 + z2 / n
    center = (p + z2 / (2.0 * n)) / denominator
    margin = (z * math.sqrt(p * (1.0 - p) / n + z2 / (4.0 * n * n))) / denominator
    return max(0.0, center - margin), min(1.0, center + margin)


def paired_direction(
    per_item: list[dict[str, Any]],
    *,
    harness_key: str = "harness_pass",
    baseline_key: str = "baseline_pass",
) -> tuple[Literal["harness", "baseline", "inconclusive"], int, int]:
    """Sign test on paired per-item results.

    Concordant items (both arms agree) carry no directional information and
    are dropped; only discordant pairs — where the arms disagree — are
    tested. The direction is established only if the Wilson CI on the
    discordant split excludes 0.5.

    Args:
        per_item: Per-item records, each carrying a harness and baseline
            pass/fail flag.
        harness_key: Dict key for the harness pass flag.
        baseline_key: Dict key for the baseline pass flag.

    Returns:
        (direction, b, c) where direction is "harness", "baseline", or
        "inconclusive"; b is the count of items where harness passed and
        baseline failed, c is the count where baseline passed and harness
        failed.
    """
    b = sum(
        1
        for item in per_item
        if item.get(harness_key, False) and not item.get(baseline_key, False)
    )
    c = sum(
        1
        for item in per_item
        if item.get(baseline_key, False) and not item.get(harness_key, False)
    )
    if b + c == 0:
        return "inconclusive", b, c
    lo, hi = wilson_ci(b, b + c)
    if lo <= 0.5 <= hi:
        return "inconclusive", b, c
    return ("harness" if b > c else "baseline"), b, c

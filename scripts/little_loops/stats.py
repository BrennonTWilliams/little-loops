"""Statistical utilities for loop evaluation reporting.

Provides Wilson 95% binomial confidence intervals for honest uncertainty
reporting at small sample sizes where naive ±√(p(1-p)/n) estimates are
unreliable near 0 or 1.
"""

from __future__ import annotations

import math


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

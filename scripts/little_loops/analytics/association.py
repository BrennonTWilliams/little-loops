"""PMI and lift scoring for sequence association analysis."""

from __future__ import annotations

import math
from dataclasses import dataclass

LIFT_THRESHOLD = 1.0
"""Lift below this value means the pair co-occurs at or below the frequency-prior rate."""


@dataclass
class AssociationScores:
    """PMI and lift scores for a token pair.

    Attributes:
        pmi: Pointwise mutual information = log(P(a,b) / (P(a)*P(b))).
             Positive means the pair co-occurs more than chance predicts.
        lift: P(b|a) / P(b) = exp(pmi). Values < 1.0 indicate
              frequency-prior-equivalent co-occurrence.
    """

    pmi: float
    lift: float


def compute_pmi(count_ab: int, count_a: int, count_b: int, total_unigrams: int) -> float:
    """Compute pointwise mutual information for token pair (a, b).

    PMI(a,b) = log( count(a,b) * total / (count_a * count_b) )

    Uses integer counts to defer float division until the final log, minimising
    accumulation of floating-point error.

    Args:
        count_ab: Co-occurrence count of the pair.
        count_a: Unigram count of token a.
        count_b: Unigram count of token b.
        total_unigrams: Total unigram count across the corpus.

    Returns:
        PMI value (float, may be negative).

    Raises:
        ValueError: If any count is zero or negative.
    """
    if count_ab <= 0:
        raise ValueError(f"count_ab must be positive, got {count_ab}")
    if count_a <= 0:
        raise ValueError(f"count_a must be positive, got {count_a}")
    if count_b <= 0:
        raise ValueError(f"count_b must be positive, got {count_b}")
    if total_unigrams <= 0:
        raise ValueError(f"total_unigrams must be positive, got {total_unigrams}")

    return math.log(count_ab * total_unigrams / (count_a * count_b))


def compute_lift(count_ab: int, count_a: int, count_b: int, total_unigrams: int) -> float:
    """Compute lift (confidence ratio) for token pair (a, b).

    lift(a,b) = P(b|a) / P(b) = count(a,b) * total / (count_a * count_b)

    A lift of 1.0 means the pair co-occurs at exactly the frequency-prior rate.
    Values < 1.0 are frequency-prior-equivalent (not worth automating on this
    signal alone). Values > 1.0 indicate a genuine non-trivial co-occurrence.

    Args:
        count_ab: Co-occurrence count of the pair.
        count_a: Unigram count of token a.
        count_b: Unigram count of token b.
        total_unigrams: Total unigram count across the corpus.

    Returns:
        Lift value (positive float).

    Raises:
        ValueError: If any count is zero or negative.
    """
    if count_ab <= 0:
        raise ValueError(f"count_ab must be positive, got {count_ab}")
    if count_a <= 0:
        raise ValueError(f"count_a must be positive, got {count_a}")
    if count_b <= 0:
        raise ValueError(f"count_b must be positive, got {count_b}")
    if total_unigrams <= 0:
        raise ValueError(f"total_unigrams must be positive, got {total_unigrams}")

    return count_ab * total_unigrams / (count_a * count_b)

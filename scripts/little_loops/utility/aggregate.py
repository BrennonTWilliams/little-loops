"""Score aggregators: a legacy additive sum and a geometric mean.

Both accept keyed mappings, are pure, and neither accepts or evaluates gates,
vetoes, coverage, or fallback ordering (the arena adapters own those). Numeric
arguments accept ``int`` or ``float`` (booleans and numeric strings are
rejected); weights must be finite and nonnegative.
"""

from __future__ import annotations

import math
from collections.abc import Mapping
from typing import Any

__all__ = ["weighted_geometric", "weighted_sum"]


def _show(value: Any) -> str:
    """Bounded ``repr`` so an oversized integer cannot flood a diagnostic."""
    text = repr(value)
    return text if len(text) <= 40 else text[:37] + "..."


def _finite(kind: str, axis: str, value: Any) -> float:
    """Return *value* as a finite float, or raise an axis-naming ``ValueError``."""
    if isinstance(value, bool) or not isinstance(value, int | float):
        raise ValueError(f"{kind} for {axis!r} must be a number, got {_show(value)}")
    try:
        number = float(value)
    except OverflowError as exc:  # e.g. 10**400
        raise ValueError(f"{kind} for {axis!r} is too large to represent: {_show(value)}") from exc
    if not math.isfinite(number):
        raise ValueError(f"{kind} for {axis!r} must be finite, got {_show(value)}")
    return number


def _check_weights(weights: Mapping[str, Any]) -> None:
    for axis, weight in weights.items():
        if _finite("weight", axis, weight) < 0:
            raise ValueError(f"weight for {axis!r} must be nonnegative, got {_show(weight)}")


def weighted_sum(scores: Mapping[str, float], weights: Mapping[str, float]) -> float:
    """Unnormalized, unclipped ``sum(weights[k] * scores[k])`` in *weights* order.

    Every weighted axis, including a zero-weight one, needs a finite nonnegative
    score; a missing or ``None`` score is invalid. Scores above 1 are allowed.
    Plain left-to-right multiplication/addition is used (no normalization,
    clipping, or ``math.fsum``) so the legacy next-loop result is bit-identical.

    Raises:
        ValueError: invalid weights/scores, a score key without a weight, or an
            aggregate that overflows to infinity.
    """
    _check_weights(weights)
    extra = [axis for axis in scores if axis not in weights]
    if extra:
        raise ValueError(f"scores supplied without weights: {sorted(map(repr, extra))}")
    for axis in weights:
        score = scores.get(axis)
        if score is None:
            raise ValueError(f"score for {axis!r} is missing")
        if _finite("score", axis, score) < 0:
            raise ValueError(f"score for {axis!r} must be nonnegative, got {_show(score)}")
    total = 0.0
    for axis, weight in weights.items():
        total += float(weight) * float(scores[axis])
    if not math.isfinite(total):
        raise ValueError("weighted sum overflowed to a non-finite value")
    return total


def weighted_geometric(
    scores: Mapping[str, float | None],
    weights: Mapping[str, float],
    *,
    floor: float = 1e-6,
) -> float | None:
    """Weighted geometric mean over the present, positive-weight axes.

    A missing key or ``None`` score is missing evidence and is excluded; the
    remaining weights are renormalized. Present scores must lie in ``[0, 1]`` and
    are floored at *floor* before the log-space mean. Returns ``None`` when no
    positive-weight axis resolves (never an invented ``0`` or ``1``).

    Raises:
        ValueError: invalid *floor* (must be finite, ``0 < floor < 1``), weights,
            or present scores (validated even on zero-weight axes), or a score
            key without a weight.
    """
    if isinstance(floor, bool) or _finite("floor", "floor", floor) <= 0 or floor >= 1:
        raise ValueError(f"floor must be a finite number with 0 < floor < 1, got {_show(floor)}")
    _check_weights(weights)
    extra = [axis for axis in scores if axis not in weights]
    if extra:
        raise ValueError(f"scores supplied without weights: {sorted(map(repr, extra))}")
    included: list[tuple[float, float]] = []
    for axis, weight in weights.items():
        score = scores.get(axis)
        if score is None:
            continue
        value = _finite("score", axis, score)
        if not 0.0 <= value <= 1.0:
            raise ValueError(f"score for {axis!r} must be within [0, 1], got {_show(score)}")
        if float(weight) > 0:
            included.append((float(weight), value))
    if not included:
        return None
    peak = max(w for w, _ in included)
    shares = [(w / peak, v) for w, v in included]
    denominator = sum(share for share, _ in shares)
    log_mean = sum(share * math.log(max(v, floor)) for share, v in shares) / denominator
    return math.exp(log_mean)
